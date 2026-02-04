#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
vtt_ner_linker.py
-----------------
Scan WebVTT transcripts (oral histories), extract named entities (PERSON/ORG/GPE/...),
link to Wikidata with spacy-entity-linker (plus a robust fallback search), and export
CSV + JSONL with timestamps and review metadata.

Key features:
- Parses .vtt files with webvtt-py.
- Stitches short cues into sliding segments (by tokens and/or seconds) so entities spanning cue boundaries are picked up.
- spaCy transformer NER (default en_core_web_trf) + optional EntityRuler patterns.
- Wikidata linking via spacy-entity-linker with candidate list stored per mention.
- Fallback to Wikidata Search API when linker yields no candidates (e.g., conversational text).
- “Confidence proxy” thresholding (accept ≥ --accept-threshold; review if < --review-threshold).
- Optional enrichment of VIAF / LCNAF / ORCID / Getty TGN IDs, plus English Wikipedia URL and Wikidata URL.
- Outputs BOTH JSONL and CSV. CSV embeds JSON (for candidates/other_ids) as strings.

Usage (examples)
----------------
# Basic run over a folder, outputs to ./out
python vtt_ner_linker.py --input ./vtts --out-dir ./out

# Use medium model for speed, accept threshold 0.65, review if < 0.8
python vtt_ner_linker.py --input ./vtts --model en_core_web_md \
    --accept-threshold 0.65 --review-threshold 0.80

# Provide initial EntityRuler patterns (JSONL with patterns)
python vtt_ner_linker.py --input 20201007_8SUF-B-001m.vtt \
    --patterns ./entity_ruler_patterns.jsonl

# Enrich accepted QIDs with authority IDs + Wikipedia/Wikidata URLs
python vtt_ner_linker.py --input ./vtts --enrich-authorities

Dependencies
------------
pip install spacy==3.* webvtt-py spacy-entity-linker tqdm requests pandas
python -m spacy download en_core_web_trf   # or en_core_web_md / en_core_web_sm

EntityRuler patterns format (example JSONL)
-------------------------------------------
{"label":"ORG","pattern":"Somerville College"}
{"label":"PERSON","pattern":[{"LOWER":{"IN":["prof.","professor","dr.","sir","dame"]}}, {"IS_TITLE":true}]}
{"label":"ORG","pattern":"Ashmolean Museum"}
"""

import argparse
import csv
import json
import os
import re
import string
import sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import webvtt
from tqdm import tqdm

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Span
from spacy.pipeline import EntityRuler

# spacy-entity-linker (community add-on)
try:
    import spacy_entity_linker  # noqa: F401 (needed to register the component)
    _HAS_ENTITY_LINKER = True
except Exception:
    _HAS_ENTITY_LINKER = False

# ---------- Configuration Defaults ----------
DEFAULT_MODEL = "en_core_web_trf"
DEFAULT_ACCEPT_THRESHOLD = 0.60
DEFAULT_REVIEW_THRESHOLD = 0.75
DEFAULT_CONTEXT_TOKENS = 8
DEFAULT_MAX_TOKENS_PER_SEG = 50
DEFAULT_MAX_SECONDS_PER_SEG = 10.0
DEFAULT_LABELS = {"PERSON", "ORG", "GPE", "LOC"}  # extendable


@dataclass
class MentionRow:
    file_id: str
    cue_start: str
    cue_end: str
    mention_text: str
    label: str
    context: str
    char_start: int
    char_end: int
    wikidata_qid: Optional[str]
    wikidata_label: Optional[str]
    candidates: List[Dict[str, Any]]
    other_ids: Dict[str, str]
    link_confidence: Optional[float]
    needs_review: bool
    notes: str


# ---------- Helpers: time & segments ----------
def hms_to_seconds(hms: str) -> float:
    # "HH:MM:SS.MMM" → seconds (float)
    parts = hms.split(":")
    if len(parts) == 2:  # MM:SS.mmm
        mm, ss = parts
        hh = 0
    else:
        hh, mm, ss = parts
    return int(hh) * 3600 + int(mm) * 60 + float(ss)


def seconds_to_hms(seconds: float) -> str:
    # Render to WebVTT timestamp "HH:MM:SS.mmm"
    msec = int(round((seconds - int(seconds)) * 1000))
    ss_total = int(seconds)
    hh = ss_total // 3600
    mm = (ss_total % 3600) // 60
    ss = ss_total % 60
    return f"{hh:02d}:{mm:02d}:{ss:02d}.{msec:03d}"


@dataclass
class Cue:
    start: float
    end: float
    text: str


@dataclass
class Segment:
    text: str
    char_to_cue: List[Tuple[int, int, int]]  # (char_start, char_end, cue_index)
    start_cue_idx: int
    end_cue_idx: int


def load_vtt(path: Path) -> List[Cue]:
    cues: List[Cue] = []
    for c in webvtt.read(str(path)):
        # Normalize whitespace lines, strip styling if any
        txt = re.sub(r"\s+", " ", c.text.strip())
        if not txt:
            continue
        cues.append(Cue(start=hms_to_seconds(c.start), end=hms_to_seconds(c.end), text=txt))
    return cues


def stitch_cues(
    cues: List[Cue],
    nlp: Language,
    max_tokens_per_seg: int = DEFAULT_MAX_TOKENS_PER_SEG,
    max_seconds_per_seg: float = DEFAULT_MAX_SECONDS_PER_SEG,
) -> List[Segment]:
    """
    Build segments that concatenate consecutive cues until either token or time budget is hit.
    Produces a char → cue index map so entity char spans can be mapped back to cue timestamps.
    """
    segments: List[Segment] = []
    i = 0
    while i < len(cues):
        start_i = i
        seg_texts = []
        char_map: List[Tuple[int, int, int]] = []
        seg_start_time = cues[i].start
        cur_char = 0

        while i < len(cues):
            cue = cues[i]
            would_len_seconds = cue.end - seg_start_time
            candidate_text = (" ".join(seg_texts + [cue.text])).strip()
            est_tokens = len(candidate_text.split()) if candidate_text else 0

            # budget check (after the first cue is in)
            if seg_texts and (est_tokens > max_tokens_per_seg or would_len_seconds > max_seconds_per_seg):
                break

            # append cue
            prefix = "" if not seg_texts else " "
            seg_texts.append(cue.text)
            start_char = cur_char + (0 if not prefix else 1)
            end_char = start_char + len(cue.text)
            if prefix:
                # account for the space we inserted
                char_map.append((cur_char, cur_char + 1, i - 1))  # the space is mapped to previous cue
                cur_char += 1
            char_map.append((start_char, end_char, i))
            cur_char = end_char

            i += 1

        seg_text = " ".join(seg_texts)
        segments.append(Segment(text=seg_text, char_to_cue=char_map, start_cue_idx=start_i, end_cue_idx=i - 1))
    return segments


def map_span_to_time(span_start: int, span_end: int, segment: Segment, cues: List[Cue]) -> Tuple[str, str]:
    """Given a char span in a segment, compute the VTT cue time range it overlaps."""
    overlapping_indices = []
    for cstart, cend, idx in segment.char_to_cue:
        if cend <= span_start:
            continue
        if cstart >= span_end:
            continue
        overlapping_indices.append(idx)
    if not overlapping_indices:
        # Fallback: use segment bounds
        start_idx = segment.start_cue_idx
        end_idx = segment.end_cue_idx
    else:
        start_idx = min(overlapping_indices)
        end_idx = max(overlapping_indices)

    cue_start = seconds_to_hms(cues[start_idx].start)
    cue_end = seconds_to_hms(cues[end_idx].end)
    return cue_start, cue_end


# ---------- spaCy pipeline ----------
def build_nlp(model: str, patterns_path: Optional[Path]) -> Language:
    """
    Load a spaCy model, attach optional EntityRuler patterns, add a sentence segmenter,
    and register the community spacy-entity-linker (if installed). Avoids nlp.initialize().
    """
    try:
        # Disable unnecessary components for speed
        nlp = spacy.load(model, disable=["tagger", "parser", "lemmatizer", "attribute_ruler"])
    except Exception as e:
        print(f"[!] Could not load model '{model}': {e}", file=sys.stderr)
        print("    Try: python -m spacy download en_core_web_trf (or _md/_sm) and re-run.", file=sys.stderr)
        raise

    # --- Sentence segmentation ---
    # Prefer senter if the model already includes it, else fall back to sentencizer (no initialize() needed)
    if "senter" in nlp.pipe_names:
        pass  # already present
    elif "sentencizer" not in nlp.pipe_names:
        nlp.add_pipe("sentencizer", before="ner")

    # --- Optional EntityRuler rules layer (for archive-specific patterns) ---
    if patterns_path:
        try:
            ruler = nlp.add_pipe("entity_ruler", name="archive_entity_ruler", before="ner")
            ruler.from_disk(str(patterns_path))
            print(f"[+] Loaded EntityRuler patterns from: {patterns_path}")
        except Exception as e:
            print(f"[!] Could not load EntityRuler patterns: {e}", file=sys.stderr)

    # --- Entity linker (Wikidata via spacy-entity-linker) ---
    if not _HAS_ENTITY_LINKER:
        print("[!] spacy-entity-linker not installed. Install with: pip install spacy-entity-linker", file=sys.stderr)
        print("    Linking will be disabled; QIDs will be blank.", file=sys.stderr)
    else:
        if "entityLinker" not in nlp.pipe_names:
            try:
                nlp.add_pipe("entityLinker", last=True)
                print("[+] Added spacy-entity-linker to pipeline")
            except Exception as e:
                print(f"[!] Could not add entityLinker: {e}", file=sys.stderr)

    # --- Debug print for confirmation ---
    print(f"[pipeline components] {nlp.pipe_names}")

    return nlp


# ---------- Wikidata enrichment & search ----------
# ---- HTTP session for Wikidata (UA + retries) ----
import requests
from requests.adapters import HTTPAdapter, Retry

# Friendly UA so Wikimedia accepts requests; tweak the email if you like
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "LSE-NER/1.0 (+mailto:you@lse.ac.uk)"})

# Robust retries for rate limits / transient errors
retries = Retry(
    total=4,
    backoff_factor=0.6,
    status_forcelist=(429, 500, 502, 503, 504),
)
SESSION.mount("https://", HTTPAdapter(max_retries=retries))
SESSION.mount("http://", HTTPAdapter(max_retries=retries))


WIKIDATA_ENTITY_API = "https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
WIKIDATA_SEARCH_API = "https://www.wikidata.org/w/api.php"
WANTED_PROPS = {
    "P214": "viaf",
    "P244": "lcnaf",
    "P496": "orcid",
    "P1667": "tgn",  # Getty TGN ID
}


def wikidata_search(text: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        params = {
            "action": "wbsearchentities",
            "search": text,
            "language": "en",
            "format": "json",
            "limit": str(limit),
            "type": "item",
        }
        r = SESSION.get(WIKIDATA_SEARCH_API, params=params, timeout=15)
        r.raise_for_status()
        data = r.json()
        return data.get("search", []) or []
    except Exception as e:
        print(f"[!] Wikidata search failed for {text!r}: {e}", file=sys.stderr)
        return []

STOP_PREFIXES = ("the ",)  # extendable

def normalize_for_wd(text: str) -> list:
    """
    Generate a small list of cleaned variants for Wikidata search.
      "Eleanor Rathbone's" -> ["Eleanor Rathbone"]
      "Pankhursts" -> ["Pankhurst", "Pankhursts"]
      "the public assistance board" -> ["public assistance board"]
    """
    variants = []
    t = text.strip()

    # collapse whitespace, strip quotes
    t = re.sub(r"\s+", " ", t)
    t = t.strip("“”\"'` ")

    # remove trailing possessives: 's or s'
    t = re.sub(r"(?:'s|’s|s'|s’)$", "", t, flags=re.IGNORECASE)

    # drop leading stopword prefixes e.g. "the "
    tl = t.lower()
    for pref in STOP_PREFIXES:
        if tl.startswith(pref):
            t = t[len(pref):]
            break

    # strip trailing punctuation/brackets
    t = t.strip(string.punctuation + " ")

    # basic variants: original, Title Case
    variants.append(t)
    if t and not t.isupper():
        variants.append(t.title())

    # plural → singular heuristics for single-token spans
    if " " not in t:
        if re.search(r"[A-Za-z]s$", t):
            variants.append(t[:-1])  # e.g., Pankhursts -> Pankhurst
        if re.search(r"[A-Za-z]es$", t):
            variants.append(t[:-2])  # e.g., Universities -> Universitie (not perfect, but helps some acronyms/terms)

    # dedupe while preserving order
    seen = set()
    out = []
    for v in variants:
        v = v.strip()
        if v and v.lower() not in seen:
            seen.add(v.lower())
            out.append(v)
    return out


def best_wd_hit(text: str) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    """
    Return (qid, label, score_proxy) from Wikidata search for a mention.
    Tries normalized variants (strip possessives, leading 'the', plural -> singular, etc.).
    """
    variants = normalize_for_wd(text)
    for q in variants:
        hits = wikidata_search(q, limit=10)
        if not hits:
            continue
        q_low = q.strip().lower()

        # 1) prefer exact label match
        for h in hits:
            label = (h.get("label") or "").strip()
            if label.lower() == q_low:
                return h.get("id"), label, 0.85

        # 2) otherwise take the top hit
        h = hits[0]
        return h.get("id"), (h.get("label") or "").strip(), 0.65

    # nothing worked
    return None, None, None


def fetch_authority_ids(qid: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    try:
        url = WIKIDATA_ENTITY_API.format(qid=qid)
        r = SESSION.get(url, timeout=15)
        r.raise_for_status()
        data = r.json()
        ent = data["entities"][qid]

        # Claims -> VIAF / LCNAF / ORCID / TGN
        claims = ent.get("claims", {})
        for pid, key in WANTED_PROPS.items():
            if pid in claims:
                for snak in claims[pid]:
                    try:
                        val = snak["mainsnak"]["datavalue"]["value"]
                        if isinstance(val, dict) and "id" in val:
                            continue
                        if isinstance(val, (str, int)):
                            out[key] = str(val)
                            break
                    except Exception:
                        continue

        # Sitelinks -> English Wikipedia URL (if available)
        sitelinks = ent.get("sitelinks", {})
        enwiki = sitelinks.get("enwiki", {})
        if enwiki and enwiki.get("title"):
            title = enwiki["title"].replace(" ", "_")
            out["wikipedia_en"] = f"https://en.wikipedia.org/wiki/{title}"

        # Convenience: direct Wikidata URL
        out["wikidata_url"] = f"https://www.wikidata.org/wiki/{qid}"

    except Exception:
        pass
    return out


# ---------- Linking utilities ----------
def linker_candidates(ent: Span) -> List[Dict[str, Any]]:
    """Extract candidates from spacy-entity-linker into a stable JSON shape."""
    cands = []
    try:
        if hasattr(ent._, "get_candidates"):
            for c in ent._.get_candidates():
                qid = c.get("entity_id") or c.get("kb_id") or c.get("id") or ""
                label = c.get("label") or c.get("title") or ""
                score = c.get("score") if isinstance(c.get("score"), (int, float)) else None
                aliases = c.get("aliases") or c.get("alias") or []
                cands.append({"qid": qid, "label": label, "score": score, "aliases": aliases})
    except Exception:
        pass
    return cands


def top_link(ent: Span) -> Tuple[Optional[str], Optional[str], Optional[float]]:
    for attr in ("kb_qid", "kb_id_", "kb_id"):
        try:
            val = getattr(ent._, attr, None) or getattr(ent, attr, None)
            if isinstance(val, str) and val.strip():
                return val.strip(), None, 0.70
        except Exception:
            pass

    cands = linker_candidates(ent)
    if cands:
        qid = cands[0].get("qid") or None
        label = cands[0].get("label") or None
        score = cands[0].get("score")
        if score is not None:
            return qid, label, float(score)
        txt = ent.text.strip().lower()
        alias_match = any(txt == (a or "").lower() for a in (cands[0].get("aliases") or []))
        return qid, label, 0.75 if alias_match else 0.55

    qid, label, conf = best_wd_hit(ent.text)
    if not qid:
        tried = ", ".join(normalize_for_wd(ent.text))
        print(f"[!] No linker candidates and no Wikidata hits for: {ent.text!r} (tried: {tried})", file=sys.stderr)
    return qid, label, conf


# ---------- Core processing ----------
def process_file(
    path: Path,
    nlp: Language,
    labels_keep: set,
    context_tokens: int,
    accept_threshold: float,
    review_threshold: float,
    enrich_authorities: bool,
) -> List[MentionRow]:
    mentions: List[MentionRow] = []
    cues = load_vtt(path)
    if not cues:
        return mentions

    segments = stitch_cues(cues, nlp)

    # Simpler & safer: run the full pipeline (we already disabled heavy pieces at load time)
    for seg in segments:
        doc: Doc = nlp(seg.text)

        for ent in doc.ents:
            if ent.label_ not in labels_keep:
                continue

            # Context window (± N tokens) in stitched seg
            left = max(ent.start - context_tokens, 0)
            right = min(ent.end + context_tokens, len(doc))
            context = doc[left:right].text

            # Map span → cue times
            span_start = ent.start_char
            span_end = ent.end_char
            cue_start, cue_end = map_span_to_time(span_start, span_end, seg, cues)

            # Candidates + top link (with fallback)
            cands = linker_candidates(ent)
            qid, wd_label, conf = top_link(ent)

            needs_review = False
            notes = ""
            chosen_qid = None
            chosen_label = None
            other_ids = {}

            if qid is not None and (conf is None or conf >= accept_threshold):
                chosen_qid = qid
                chosen_label = wd_label
                if conf is not None and conf < review_threshold:
                    needs_review = True
                    notes = "Accepted below review threshold"
            else:
                needs_review = True
                notes = "Ambiguous or below accept threshold"

            # Optional enrichment of authority IDs & URLs
            if enrich_authorities and chosen_qid:
                other_ids = fetch_authority_ids(chosen_qid)

            mentions.append(
                MentionRow(
                    file_id=path.name,
                    cue_start=cue_start,
                    cue_end=cue_end,
                    mention_text=ent.text,
                    label=ent.label_,
                    context=context,
                    char_start=span_start,
                    char_end=span_end,
                    wikidata_qid=chosen_qid,
                    wikidata_label=chosen_label,
                    candidates=cands,
                    other_ids=other_ids,
                    link_confidence=conf,
                    needs_review=needs_review,
                    notes=notes,
                )
            )
    return mentions


# ---------- Output writers ----------
def write_jsonl(rows: List[MentionRow], out_path: Path) -> None:
    with out_path.open("w", encoding="utf-8") as f:
        for r in rows:
            obj = asdict(r)
            f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def write_csv(rows: List[MentionRow], out_path: Path) -> None:
    # Flatten JSON fields as JSON strings for CSV columns
    fieldnames = [
        "file_id", "cue_start", "cue_end", "mention_text", "label", "context",
        "char_start", "char_end", "wikidata_qid", "wikidata_label",
        "candidates", "other_ids", "link_confidence", "needs_review", "notes"
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            d = asdict(r)
            d["candidates"] = json.dumps(d["candidates"], ensure_ascii=False)
            d["other_ids"] = json.dumps(d["other_ids"], ensure_ascii=False)
            w.writerow(d)


# ---------- Main ----------
def main():
    ap = argparse.ArgumentParser(description="Extract & link entities from VTT transcripts (spaCy + Wikidata).")
    ap.add_argument("--input", required=True, help="Path to a .vtt file or a directory of .vtt files")
    ap.add_argument("--out-dir", required=False, default="./out", help="Output directory (will be created if missing)")
    ap.add_argument("--model", default=DEFAULT_MODEL, help="spaCy model (default: en_core_web_trf)")
    ap.add_argument("--patterns", default=None, help="EntityRuler patterns JSONL path (optional)")
    ap.add_argument("--labels", default="PERSON,ORG,GPE,LOC", help="Comma-separated labels to keep")
    ap.add_argument("--context-tokens", type=int, default=DEFAULT_CONTEXT_TOKENS, help="Context tokens on each side")
    ap.add_argument("--accept-threshold", type=float, default=DEFAULT_ACCEPT_THRESHOLD, help="Accept top candidate at/above this score")
    ap.add_argument("--review-threshold", type=float, default=DEFAULT_REVIEW_THRESHOLD, help="Flag needs_review if below this score (but accepted)")
    ap.add_argument("--max-seconds-per-seg", type=float, default=DEFAULT_MAX_SECONDS_PER_SEG, help="Max seconds per stitched segment")
    ap.add_argument("--max-tokens-per-seg", type=int, default=DEFAULT_MAX_TOKENS_PER_SEG, help="Max tokens per stitched segment")
    ap.add_argument("--enrich-authorities", action="store_true", help="Fetch VIAF/LCNAF/ORCID/TGN + Wikipedia/Wikidata URLs for accepted QIDs")
    ap.add_argument("--no-linking", action="store_true", help="Disable linking (ignore spacy-entity-linker even if installed)")
    args = ap.parse_args()

    in_path = Path(args.input)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    patterns_path = Path(args.patterns) if args.patterns else None

    labels_keep = set([s.strip() for s in args.labels.split(",") if s.strip()])

    nlp = build_nlp(args.model, patterns_path)

    # Optionally disable linker component at runtime
    if args.no_linking and "entityLinker" in nlp.pipe_names:
        nlp.remove_pipe("entityLinker")

    # Collect files
    files: List[Path] = []
    if in_path.is_file() and in_path.suffix.lower() == ".vtt":
        files = [in_path]
    elif in_path.is_dir():
        files = sorted([p for p in in_path.rglob("*.vtt")])
    else:
        print("[!] --input must be a .vtt file or a directory containing .vtt files", file=sys.stderr)
        sys.exit(1)

    all_rows: List[MentionRow] = []

    for f in tqdm(files, desc="Processing VTTs"):
        try:
            rows = process_file(
                path=f,
                nlp=nlp,
                labels_keep=labels_keep,
                context_tokens=args.context_tokens,
                accept_threshold=args.accept_threshold,
                review_threshold=args.review_threshold,
                enrich_authorities=args.enrich_authorities,
            )
            all_rows.extend(rows)
        except Exception as e:
            print(f"[!] Error processing {f.name}: {e}", file=sys.stderr)

    # Write outputs
    jsonl_path = out_dir / "entities.jsonl"
    csv_path = out_dir / "entities.csv"
    write_jsonl(all_rows, jsonl_path)
    write_csv(all_rows, csv_path)

    # Also write a “needs review” CSV
    review_rows = [r for r in all_rows if r.needs_review]
    write_csv(review_rows, out_dir / "entities_needs_review.csv")

    print(f"[✓] Wrote {len(all_rows)} mentions to:\n  {jsonl_path}\n  {csv_path}")
    print(f"[✓] Wrote {len(review_rows)} mentions needing review to:\n  {out_dir / 'entities_needs_review.csv'}")


if __name__ == "__main__":
    main()
