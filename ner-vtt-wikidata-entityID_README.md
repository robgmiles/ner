# Named Entity Recognition & Wikidata Linking for WebVTT Transcripts

## Overview

This script extracts named entities (people, places, organizations) from WebVTT transcript files (oral histories, video captions, interviews) and links them to Wikidata identifiers. It preserves timestamps, provides confidence scoring, and enriches entities with authority file identifiers.

## Features

- **WebVTT Parsing**: Processes subtitle/transcript files with timestamp preservation
- **Smart Segmentation**: Stitches short cues together to capture entities spanning boundaries
- **Wikidata Linking**: Two-stage linking via spacy-entity-linker + Wikidata Search API
- **Confidence Scoring**: Automatic quality assessment with review flagging
- **Authority Enrichment**: Optional VIAF, LCNAF, ORCID, Getty TGN IDs
- **Multiple Outputs**: JSONL and CSV formats with separate review file
- **Custom Patterns**: Support for archive-specific entity ruler patterns

---

## Installation

### 1. Install Python

Ensure you have Python 3.7+ installed:
```bash
python --version
# or
python3 --version
```

### 2. Install Required Libraries

Open your terminal/command prompt and run:

```bash
# Core NLP library
pip install spacy

# Download a spaCy model
# Transformer model (best accuracy, slower, ~460MB)
python -m spacy download en_core_web_trf

# OR medium model (good balance, ~91MB)
python -m spacy download en_core_web_md

# OR small model (fastest, least accurate, ~13MB)
python -m spacy download en_core_web_sm
```

### 3. Install Wikidata Linking Library (CRITICAL)

```bash
# This library enables Wikidata entity linking
pip install spacy-entity-linker
```

### 4. Install WebVTT Parser (CRITICAL)

```bash
# This library parses WebVTT transcript files
pip install webvtt-py
```

### 5. Install Utilities

```bash
# Progress bars and HTTP requests
pip install tqdm requests
```

### Complete One-Line Installation

```bash
pip install spacy webvtt-py spacy-entity-linker tqdm requests
python -m spacy download en_core_web_trf
```

---

## Setup

### 1. Save the Script

- Copy the Python script
- Save it as `ner-vtt-wikidata-entityID.py`
- Place it in your working directory

### 2. Prepare Your WebVTT Files

Your WebVTT files should look like this:

```
WEBVTT

00:00:01.000 --> 00:00:05.000
Eleanor Rathbone spoke about social reform in Parliament.

00:00:05.500 --> 00:00:10.000
She worked closely with Somerville College in Oxford.

00:00:10.500 --> 00:00:15.000
The Salvation Army supported her housing initiatives.
```

**File structure:**
```
your_project/
├── ner-vtt-wikidata-entityID.py
├── transcripts/
│   ├── interview_001.vtt
│   ├── interview_002.vtt
│   └── interview_003.vtt
└── output/
    (will be created automatically)
```

---

## Usage

### Basic Usage

Process a single VTT file:
```bash
python ner-vtt-wikidata-entityID.py --input interview.vtt --out-dir ./output
```

Process all VTT files in a directory:
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output
```

### With Authority Enrichment

Add VIAF, LCNAF, ORCID, Getty TGN IDs:
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --enrich-authorities
```

### Using Different Models

```bash
# Use medium model (faster, less accurate)
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --model en_core_web_md

# Use small model (fastest, least accurate)
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --model en_core_web_sm
```

### Custom Confidence Thresholds

```bash
# Accept entities with confidence ≥ 0.65, flag for review if < 0.80
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --accept-threshold 0.65 --review-threshold 0.80
```

### Advanced: Custom Entity Patterns

Create a JSONL file with custom patterns (`patterns.jsonl`):
```json
{"label":"ORG","pattern":"Somerville College"}
{"label":"PERSON","pattern":"Eleanor Rathbone"}
{"label":"ORG","pattern":"Salvation Army"}
```

Run with patterns:
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --patterns ./patterns.jsonl
```

### Disable Wikidata Linking

Extract entities only (no linking):
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --no-linking
```

### All Options

```bash
python ner-vtt-wikidata-entityID.py \
    --input ./transcripts \
    --out-dir ./output \
    --model en_core_web_trf \
    --patterns ./patterns.jsonl \
    --labels PERSON,ORG,GPE,LOC,FAC \
    --context-tokens 10 \
    --accept-threshold 0.60 \
    --review-threshold 0.75 \
    --max-seconds-per-seg 15 \
    --max-tokens-per-seg 75 \
    --enrich-authorities
```

---

## Output Files

The script creates three output files in your specified output directory:

### 1. `entities.jsonl`
**Format**: JSON Lines (one JSON object per line)  
**Content**: Every entity mention with full details

Example line:
```json
{
  "file_id": "interview_001.vtt",
  "cue_start": "00:01:23.000",
  "cue_end": "00:01:27.000",
  "mention_text": "Eleanor Rathbone",
  "label": "PERSON",
  "context": "spoke about Eleanor Rathbone and her work with",
  "char_start": 145,
  "char_end": 161,
  "wikidata_qid": "Q234567",
  "wikidata_label": "Eleanor Rathbone",
  "candidates": [
    {"qid": "Q234567", "label": "Eleanor Rathbone", "score": 0.87, "aliases": ["E. Rathbone"]},
    {"qid": "Q999999", "label": "Eleanor Rathbone (artist)", "score": 0.23, "aliases": []}
  ],
  "other_ids": {
    "viaf": "12345678",
    "lcnaf": "n79123456",
    "wikipedia_en": "https://en.wikipedia.org/wiki/Eleanor_Rathbone",
    "wikidata_url": "https://www.wikidata.org/wiki/Q234567"
  },
  "link_confidence": 0.87,
  "needs_review": false,
  "notes": ""
}
```

**Use for**: API integration, programmatic processing, data pipelines

### 2. `entities.csv`
**Format**: Comma-separated values  
**Content**: Same data as JSONL in tabular format

| file_id | cue_start | cue_end | mention_text | label | context | wikidata_qid | wikidata_label | link_confidence | needs_review |
|---------|-----------|---------|--------------|-------|---------|--------------|----------------|-----------------|--------------|
| interview_001.vtt | 00:01:23.000 | 00:01:27.000 | Eleanor Rathbone | PERSON | ...Eleanor Rathbone and her... | Q234567 | Eleanor Rathbone | 0.87 | false |

**Notes**: 
- `candidates` and `other_ids` columns contain JSON strings
- Can be opened in Excel/Google Sheets/LibreOffice

**Use for**: Manual review, spreadsheet analysis, filtering

### 3. `entities_needs_review.csv`
**Format**: Comma-separated values  
**Content**: Subset of entities where `needs_review = true`

Same structure as `entities.csv`, but only includes entities that need manual validation.

**Use for**: Quality control workflow, manual entity verification

---

## How Wikidata Linking Works

### Two-Stage Linking Process

#### Stage 1: spacy-entity-linker (Primary Method)

The script uses the **spacy-entity-linker** library which:
- Maintains an offline knowledge base of Wikidata entities
- Searches for matches when entities are detected
- Returns a ranked list of candidates with confidence scores
- Very fast (no API calls required)

**Example:**
```
Entity detected: "Eleanor Rathbone"
  ↓
spacy-entity-linker searches KB
  ↓
Returns candidates:
  1. Q234567 "Eleanor Rathbone" (politician) - score: 0.87
  2. Q999999 "Eleanor Rathbone" (artist) - score: 0.23
  ↓
Top candidate selected: Q234567
```

#### Stage 2: Wikidata Search API (Fallback)

If spacy-entity-linker finds no candidates, the script:

1. **Normalizes the text** using `normalize_for_wd()`:
   - Removes possessives: `"Rathbone's"` → `"Rathbone"`
   - Removes leading articles: `"the Board"` → `"Board"`
   - Tries singular forms: `"Pankhursts"` → `"Pankhurst"`
   - Creates Title Case variants

2. **Queries Wikidata Search API** for each variant:
   ```
   GET https://www.wikidata.org/w/api.php
   ?action=wbsearchentities
   &search=Eleanor Rathbone
   &language=en
   &format=json
   ```

3. **Selects best match**:
   - Prefers exact label matches (confidence: 0.85)
   - Falls back to top search result (confidence: 0.65)

### Confidence Scoring

| Score | Source | Meaning |
|-------|--------|---------|
| 0.85 | Wikidata Search | Exact label match in search results |
| 0.75 | spacy-entity-linker | Alias match (entity text matches known alias) |
| 0.70 | spacy-entity-linker | Direct QID assignment |
| 0.65 | Wikidata Search | Top result (non-exact match) |
| 0.55 | spacy-entity-linker | Candidate match (no alias confirmation) |

### Accept & Review Thresholds

- **Accept Threshold** (default: 0.60)
  - Entities with confidence ≥ this value get assigned a Wikidata QID
  - Entities below this get `wikidata_qid = null`

- **Review Threshold** (default: 0.75)
  - Entities with confidence < this value get `needs_review = true`
  - Even if they're accepted (above accept threshold)
  - Enables quality control workflow

**Examples:**
- Confidence 0.87: Accepted, no review needed
- Confidence 0.68: Accepted, needs review
- Confidence 0.55: Rejected (no QID assigned), needs review

---

## Authority File Enrichment

### When to Use `--enrich-authorities`

Enable this flag when you want:
- VIAF identifiers for linking to library catalogs
- Library of Congress authority records
- ORCID IDs for researchers
- Getty TGN IDs for place names
- Wikipedia URLs for easy reference
- Direct Wikidata URLs

**Warning**: This makes additional API calls to Wikidata, so processing will be slower.

### What Gets Retrieved

For each **accepted** Wikidata QID, the script fetches:

#### 1. VIAF (Virtual International Authority File)
- **Wikidata Property**: P214
- **Format**: Numeric ID (e.g., `12345678`)
- **Use**: Links to library catalogs worldwide
- **Example URL**: `https://viaf.org/viaf/12345678`

#### 2. LCNAF (Library of Congress Name Authority File)
- **Wikidata Property**: P244
- **Format**: Alphanumeric (e.g., `n79123456`)
- **Use**: US Library of Congress authority records
- **Example URL**: `https://id.loc.gov/authorities/names/n79123456`

#### 3. ORCID (Open Researcher and Contributor ID)
- **Wikidata Property**: P496
- **Format**: 0000-0000-0000-0000 (e.g., `0000-0002-1234-5678`)
- **Use**: Identifies academic researchers
- **Example URL**: `https://orcid.org/0000-0002-1234-5678`

#### 4. Getty TGN (Thesaurus of Geographic Names)
- **Wikidata Property**: P1667
- **Format**: Numeric ID (e.g., `7008038`)
- **Use**: Geographic places authority file
- **Example URL**: `http://vocab.getty.edu/tgn/7008038`

#### 5. English Wikipedia URL
- **Source**: Wikidata sitelinks
- **Format**: `https://en.wikipedia.org/wiki/Eleanor_Rathbone`
- **Use**: Easy access to Wikipedia article

#### 6. Wikidata URL
- **Format**: `https://www.wikidata.org/wiki/Q234567`
- **Use**: Direct link to Wikidata entity page

### How It Works

```
Accepted entity with QID = Q234567
  ↓
Fetch: https://www.wikidata.org/wiki/Special:EntityData/Q234567.json
  ↓
Parse JSON response:
  - Check claims.P214 → VIAF ID
  - Check claims.P244 → LCNAF ID
  - Check claims.P496 → ORCID
  - Check claims.P1667 → Getty TGN
  - Check sitelinks.enwiki → Wikipedia URL
  ↓
Store in other_ids dictionary
```

---

## Text Processing Pipeline

### Step 1: Load VTT File

```python
Input: interview_001.vtt

Cue 1: 00:00:01.000 --> 00:00:05.000
  Text: "Eleanor Rathbone spoke about social reform"

Cue 2: 00:00:05.500 --> 00:00:10.000
  Text: "in Parliament during the 1930s"
```

### Step 2: Segment Stitching

**Why?** Short VTT cues often split entity mentions across boundaries.

**Process:**
- Combines consecutive cues until hitting token or time limit
- Default limits: 50 tokens OR 10 seconds per segment
- Maintains character-to-cue mapping for timestamp tracking

```python
Before stitching:
  Cue 1: "Eleanor Rathbone spoke about social reform"
  Cue 2: "in Parliament during the 1930s"

After stitching:
  Segment 1: "Eleanor Rathbone spoke about social reform in Parliament during the 1930s"
  Mapping: chars 0-45 → Cue 1, chars 46-78 → Cue 2
```

**Benefits:**
- Captures entities split across cues: "Eleanor Rathbone" won't be cut off
- Provides more context for NER accuracy
- Enables proper timestamp attribution

### Step 3: Named Entity Recognition

```python
Segment: "Eleanor Rathbone spoke about social reform in Parliament during the 1930s"
  ↓
spaCy NER processes text
  ↓
Detected entities:
  - "Eleanor Rathbone" (PERSON) at chars 0-16
  - "Parliament" (ORG) at chars 47-57
  - "the 1930s" (DATE) at chars 65-74
  ↓
Filter by labels (keep PERSON, ORG, GPE, LOC)
  ↓
Kept entities: "Eleanor Rathbone", "Parliament"
```

### Step 4: Context Extraction

For each entity, extract ±N tokens of context (default: 8 tokens):

```python
Entity: "Eleanor Rathbone" at tokens 0-1
  ↓
Context window: tokens -8 to 9
  (no tokens before start, so starts at 0)
  ↓
Context: "Eleanor Rathbone spoke about social reform in Parliament during the"
```

### Step 5: Wikidata Linking

```python
Entity: "Eleanor Rathbone"
  ↓
spacy-entity-linker search
  ↓
Candidates found:
  1. Q234567 "Eleanor Rathbone" - score: 0.87
  2. Q999999 "Eleanor Rathbone (artist)" - score: 0.23
  ↓
Top candidate selected: Q234567 with confidence 0.87
  ↓
Check thresholds:
  - 0.87 ≥ 0.60 (accept) → ✓ Assign QID
  - 0.87 ≥ 0.75 (review) → ✓ No review needed
```

### Step 6: Timestamp Mapping

Map entity's character span back to original VTT cues:

```python
Entity char span: 0-16 in stitched segment
  ↓
Check character-to-cue mapping
  ↓
Chars 0-16 overlap with Cue 1
  ↓
Cue 1 timing: 00:00:01.000 --> 00:00:05.000
  ↓
Assign timestamps:
  cue_start: "00:00:01.000"
  cue_end: "00:00:05.000"
```

### Step 7: Authority Enrichment (if enabled)

```python
QID: Q234567
  ↓
Fetch https://www.wikidata.org/wiki/Special:EntityData/Q234567.json
  ↓
Extract authority IDs:
  {
    "viaf": "12345678",
    "lcnaf": "n79123456",
    "wikipedia_en": "https://en.wikipedia.org/wiki/Eleanor_Rathbone",
    "wikidata_url": "https://www.wikidata.org/wiki/Q234567"
  }
```

### Step 8: Output Generation

Create MentionRow object and write to files:

```python
{
  "file_id": "interview_001.vtt",
  "cue_start": "00:00:01.000",
  "cue_end": "00:00:05.000",
  "mention_text": "Eleanor Rathbone",
  "label": "PERSON",
  "context": "Eleanor Rathbone spoke about social reform in Parliament during the",
  "char_start": 0,
  "char_end": 16,
  "wikidata_qid": "Q234567",
  "wikidata_label": "Eleanor Rathbone",
  "candidates": [...],
  "other_ids": {...},
  "link_confidence": 0.87,
  "needs_review": false,
  "notes": ""
}
```

---

## Command-Line Options Reference

### Required Arguments

| Option | Description | Example |
|--------|-------------|---------|
| `--input` | Path to .vtt file or directory | `--input ./transcripts` |

### Optional Arguments

| Option | Default | Description |
|--------|---------|-------------|
| `--out-dir` | `./out` | Output directory (created if missing) |
| `--model` | `en_core_web_trf` | spaCy model to use |
| `--patterns` | None | EntityRuler patterns JSONL file |
| `--labels` | `PERSON,ORG,GPE,LOC` | Comma-separated entity labels to extract |
| `--context-tokens` | `8` | Context tokens on each side of entity |
| `--accept-threshold` | `0.60` | Accept entities with confidence ≥ this |
| `--review-threshold` | `0.75` | Flag review if confidence < this |
| `--max-seconds-per-seg` | `10.0` | Max seconds per stitched segment |
| `--max-tokens-per-seg` | `50` | Max tokens per stitched segment |
| `--enrich-authorities` | Flag (off by default) | Fetch VIAF/LCNAF/ORCID/TGN/URLs |
| `--no-linking` | Flag (off by default) | Disable Wikidata linking |

### Entity Label Options

Available spaCy entity types (extend `--labels` as needed):

| Label | Description | Example |
|-------|-------------|---------|
| `PERSON` | People, including fictional | "Eleanor Rathbone", "Jane Austen" |
| `ORG` | Organizations | "Salvation Army", "Oxford University" |
| `GPE` | Geopolitical entities | "London", "United Kingdom", "Paris" |
| `LOC` | Non-GPE locations | "River Thames", "Mount Everest" |
| `FAC` | Facilities/buildings | "Westminster Abbey", "Tower Bridge" |
| `NORP` | Nationalities/religious/political groups | "British", "Catholic", "Conservative" |
| `EVENT` | Named events | "World War II", "Great Depression" |
| `DATE` | Dates/periods | "1930s", "March 15", "the 19th century" |
| `TIME` | Times | "3pm", "morning", "midnight" |
| `WORK_OF_ART` | Titles of works | "Pride and Prejudice", "Mona Lisa" |
| `LAW` | Named laws | "Constitution", "Bill of Rights" |

Example with more labels:
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --labels PERSON,ORG,GPE,LOC,FAC,EVENT,DATE,NORP
```

---

## Troubleshooting

### Error: `ModuleNotFoundError: No module named 'spacy'`

**Solution:**
```bash
pip install spacy
```

### Error: `ModuleNotFoundError: No module named 'spacy_entity_linker'`

**Solution:**
```bash
pip install spacy-entity-linker
```

This is **critical** for Wikidata linking. Without it, all entities will have `wikidata_qid = null`.

### Error: `ModuleNotFoundError: No module named 'webvtt'`

**Solution:**
```bash
pip install webvtt-py
```

This is **required** to parse VTT files.

### Error: `Can't find model 'en_core_web_trf'`

**Solution:**
```bash
python -m spacy download en_core_web_trf
```

Or use a different model:
```bash
python -m spacy download en_core_web_sm
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --model en_core_web_sm
```

### Error: `spacy-entity-linker installed but not linking`

The script prints pipeline components. Look for this output:
```
[pipeline components] ['sentencizer', 'ner', 'entityLinker']
```

If `entityLinker` is missing, try:
```bash
pip uninstall spacy-entity-linker
pip install spacy-entity-linker
```

### All Entities Have `wikidata_qid = null`

**Possible causes:**

1. **spacy-entity-linker not installed** (most common)
   ```bash
   pip install spacy-entity-linker
   ```

2. **--no-linking flag used accidentally**
   - Remove the flag from your command

3. **Entities genuinely not in Wikidata**
   - Check the `candidates` field to see if any matches were found
   - Try manual Wikidata search for the entity text

### Processing is Very Slow

**Solutions:**

1. **Use a smaller/faster model:**
   ```bash
   python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output --model en_core_web_sm
   ```

2. **Disable authority enrichment:**
   - Remove `--enrich-authorities` flag (saves API calls)

3. **Process files in batches:**
   ```bash
   python ner-vtt-wikidata-entityID.py --input ./transcripts/batch1 --out-dir ./output
   python ner-vtt-wikidata-entityID.py --input ./transcripts/batch2 --out-dir ./output
   ```

### VTT File Not Being Recognized

**Check your file:**
- Must have `.vtt` extension (case-insensitive)
- Must be valid WebVTT format
- Must contain timestamp lines in format: `HH:MM:SS.mmm --> HH:MM:SS.mmm`

**Test with minimal file:**
```
WEBVTT

00:00:00.000 --> 00:00:05.000
Test sentence with Eleanor Rathbone.
```

### Rate Limiting from Wikidata

**Symptoms:**
- Errors mentioning HTTP 429 or rate limiting
- Many entities failing to link

**Solutions:**
1. The script has built-in retries with backoff
2. Process fewer files at a time
3. Add delays between batches (process manually)
4. Update the User-Agent in the script (line 276) with your email:
   ```python
   SESSION.headers.update({"User-Agent": "YourProject/1.0 (+mailto:your.email@example.com)"})
   ```

---

## Performance Expectations

### Processing Speed by Model

| Model | Speed | Accuracy | Size | Recommendation |
|-------|-------|----------|------|----------------|
| `en_core_web_sm` | ~0.5-1 sec/minute | Good | 13 MB | Testing, large archives |
| `en_core_web_md` | ~1-2 sec/minute | Better | 91 MB | Production, balanced |
| `en_core_web_trf` | ~3-5 sec/minute | Best | 460 MB | High-quality, research |

*Processing time per minute of transcript (approximate)*

### With/Without Authority Enrichment

| Configuration | Additional Time | Notes |
|---------------|-----------------|-------|
| Basic (no enrichment) | +0 sec | Fast, no extra API calls |
| `--enrich-authorities` | +0.5-1 sec per entity | One API call per accepted entity |

### Example: 60-minute Interview

**Assumptions:**
- 60 minutes of transcript
- ~150 entity mentions detected
- 100 accepted entities (confidence ≥ 0.60)

| Model | No Enrichment | With Enrichment |
|-------|---------------|-----------------|
| Small | ~30-60 sec | ~2-3 min |
| Medium | ~1-2 min | ~3-4 min |
| Transformer | ~3-5 min | ~5-7 min |

---

## Workflow Recommendations

### 1. Initial Testing (Small Model, No Enrichment)

```bash
python ner-vtt-wikidata-entityID.py --input sample.vtt --out-dir ./test --model en_core_web_sm
```

**Review output:**
- Check if entities are being detected
- Verify Wikidata linking is working
- Assess quality of timestamps

### 2. Full Processing (Best Model)

```bash
python ner-vtt-wikidata-entityID.py --input ./all_transcripts --out-dir ./output --model en_core_web_trf
```

**Let run overnight if processing many files.**

### 3. Manual Review

```bash
# Open the needs_review file in Excel/Google Sheets
open ./output/entities_needs_review.csv
```

**For each entity flagged for review:**
- Check if the Wikidata QID is correct
- Verify it's actually the right person/place/org
- Look at alternative candidates in the `candidates` field
- Decide: Accept, Reject, or Choose Different QID

### 4. Authority Enrichment (After Review)

Once you're satisfied with the Wikidata QIDs:

```bash
python ner-vtt-wikidata-entityID.py --input ./all_transcripts --out-dir ./output_enriched \
    --model en_core_web_trf --enrich-authorities
```

This creates a final dataset with all authority IDs.

### 5. Integration

- Use `entities.jsonl` for databases/APIs
- Use `entities.csv` for spreadsheet analysis
- Link to VIAF/LCNAF/Wikipedia using authority IDs
- Build search interfaces with timestamps for video navigation

---

## Advanced Usage

### Custom Entity Ruler Patterns

Create archive-specific patterns to improve accuracy for known entities.

**Create `patterns.jsonl`:**
```json
{"label":"PERSON","pattern":"Eleanor Rathbone"}
{"label":"PERSON","pattern":"Millicent Fawcett"}
{"label":"ORG","pattern":"Somerville College"}
{"label":"ORG","pattern":"Salvation Army"}
{"label":"GPE","pattern":"Westminster"}
{"label":"FAC","pattern":"British Library"}
{"label":"PERSON","pattern":[{"LOWER":"prof."},{"IS_TITLE":true}]}
{"label":"PERSON","pattern":[{"LOWER":"dr."},{"IS_TITLE":true}]}
{"label":"ORG","pattern":[{"LOWER":"university"},{"LOWER":"of"},{"IS_TITLE":true}]}
```

**Pattern types:**

**String patterns:**
```json
{"label":"PERSON","pattern":"Eleanor Rathbone"}
```

**Token patterns (more flexible):**
```json
{"label":"PERSON","pattern":[
  {"LOWER":"prof."},
  {"IS_TITLE":true}
]}
```

This matches "Prof. Smith", "Prof. Jones", etc.

**Run with patterns:**
```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --patterns ./patterns.jsonl
```

**Benefits:**
- Ensures known entities are always detected
- Overrides model's default NER when pattern matches
- Useful for organizational names, projects, places specific to your archive

### Adjusting Segment Size

For transcripts with very short or very long cues:

```bash
# Larger segments (more context, slower)
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --max-tokens-per-seg 100 --max-seconds-per-seg 20

# Smaller segments (faster, less context)
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --max-tokens-per-seg 30 --max-seconds-per-seg 5
```

**When to adjust:**
- Short segments: Dense, rapid speech with many entities
- Large segments: Slow, contemplative interviews where entities are spread out

### Extracting More Entity Types

```bash
python ner-vtt-wikidata-entityID.py --input ./transcripts --out-dir ./output \
    --labels PERSON,ORG,GPE,LOC,FAC,EVENT,DATE,NORP,WORK_OF_ART
```

**Warning**: 
- More labels = more entities = larger output files
- DATE, TIME may create many low-value entries
- CARDINAL, ORDINAL, QUANTITY rarely need Wikidata linking

### Batch Processing with Shell Scripts

**Bash script** (`process_batches.sh`):
```bash
#!/bin/bash

for dir in batch_*; do
    echo "Processing $dir..."
    python ner-vtt-wikidata-entityID.py --input "$dir" --out-dir "./output/$dir" \
        --model en_core_web_trf --enrich-authorities
    sleep 60  # 1-minute pause between batches to avoid rate limiting
done

echo "All batches complete!"
```

**Usage:**
```bash
chmod +x process_batches.sh
./process_batches.sh
```

---

## Output Data Schema

### JSONL Schema

```typescript
{
  file_id: string,              // VTT filename
  cue_start: string,            // "HH:MM:SS.mmm"
  cue_end: string,              // "HH:MM:SS.mmm"
  mention_text: string,         // Entity text as it appears
  label: string,                // PERSON | ORG | GPE | LOC | FAC | ...
  context: string,              // Surrounding text (±N tokens)
  char_start: number,           // Character offset in segment
  char_end: number,             // Character offset in segment
  wikidata_qid: string | null,  // "Q123456" or null
  wikidata_label: string | null,// Wikidata preferred label
  candidates: Array<{           // All candidates from linker
    qid: string,
    label: string,
    score: number | null,
    aliases: string[]
  }>,
  other_ids: {                  // Authority IDs (if enriched)
    viaf?: string,
    lcnaf?: string,
    orcid?: string,
    tgn?: string,
    wikipedia_en?: string,
    wikidata_url?: string
  },
  link_confidence: number | null,  // 0.0-1.0
  needs_review: boolean,           // true if below review threshold
  notes: string                    // Processing notes
}
```

### CSV Schema

Same fields as JSONL, but:
- `candidates` is a JSON string (parse with `JSON.parse()`)
- `other_ids` is a JSON string (parse with `JSON.parse()`)

**Example row:**
```csv
file_id,cue_start,cue_end,mention_text,label,context,char_start,char_end,wikidata_qid,wikidata_label,candidates,other_ids,link_confidence,needs_review,notes
interview_001.vtt,00:01:23.000,00:01:27.000,Eleanor Rathbone,PERSON,"spoke about Eleanor Rathbone and her work",145,161,Q234567,Eleanor Rathbone,"[{""qid"":""Q234567"",""label"":""Eleanor Rathbone"",""score"":0.87,""aliases"":[""E. Rathbone""]}]","{""viaf"":""12345678"",""wikipedia_en"":""https://en.wikipedia.org/wiki/Eleanor_Rathbone""}",0.87,false,
```

---

## Next Steps for Linked Data

### 1. Manual Review & Correction

**Review process:**
1. Sort `entities_needs_review.csv` by `link_confidence` (lowest first)
2. For each entity:
   - Check if QID matches the context
   - Look at `candidates` array for alternatives
   - Search Wikidata manually if unsure: https://www.wikidata.org
3. Create a corrections file mapping old QID → new QID
4. Apply corrections programmatically

### 2. RDF/Linked Open Data Export

Convert JSONL to RDF triples for semantic web:

```turtle
@prefix schema: <http://schema.org/> .
@prefix wd: <http://www.wikidata.org/entity/> .
@prefix dct: <http://purl.org/dc/terms/> .

<interview_001#mention_1> a schema:Person ;
    schema:name "Eleanor Rathbone" ;
    schema:sameAs wd:Q234567 ;
    dct:temporal "00:01:23.000 - 00:01:27.000" ;
    dct:isPartOf <interview_001> .
```

### 3. Build Search Interface

Use timestamps to create clickable search results:

```
Search: "Eleanor Rathbone"

Results:
- interview_001.vtt at 00:01:23 → [Play video at this timestamp]
- interview_003.vtt at 00:15:42 → [Play video at this timestamp]
- interview_007.vtt at 00:08:15 → [Play video at this timestamp]
```

### 4. Network Analysis

Build entity co-occurrence networks:
- Which people appear together in interviews?
- Which organizations are frequently mentioned with which people?
- Temporal patterns (which entities appear in which time periods?)

### 5. Authority File Integration

Link to external systems using the enriched IDs:

```
Eleanor Rathbone (Q234567)
  ├─ VIAF: https://viaf.org/viaf/12345678
  ├─ Library of Congress: https://id.loc.gov/authorities/names/n79123456
  ├─ Wikipedia: https://en.wikipedia.org/wiki/Eleanor_Rathbone
  └─ Wikidata: https://www.wikidata.org/wiki/Q234567
```

### 6. Visualization

Create interactive visualizations:
- Timeline of entities mentioned over interview duration
- Network graphs of entity relationships
- Geographic maps of places mentioned
- Word clouds weighted by entity frequency

---

## Support & Customization

### Getting Help

1. **Check this README** for common issues
2. **Run with verbose output**: Check console for pipeline component list
3. **Test with minimal VTT file**: Isolate the problem
4. **Verify installations**: All libraries installed correctly?

### Script Customization

The script is designed to be modular. You can customize:

- **Entity types** (`DEFAULT_LABELS` at line 81)
- **Confidence thresholds** (change defaults at lines 76-77)
- **Segment sizes** (lines 79-80)
- **Authority properties** (`WANTED_PROPS` at lines 290-295)
- **User-Agent** (line 276) - update with your project details

### Contact

For questions specific to:
- **spaCy**: https://spacy.io/usage
- **spacy-entity-linker**: https://github.com/egerber/spacy-entity-linker
- **Wikidata**: https://www.wikidata.org/wiki/Wikidata:Introduction
- **WebVTT format**: https://www.w3.org/TR/webvtt1/

---

## License & Citation

### Software License

This script is provided for research and archival purposes.

### When Publishing Results

If you use this tool in research or published projects, please:

1. **Cite your data sources**:
   - Original interview/transcript collection
   - Wikidata (https://www.wikidata.org)
   - Any authority files used (VIAF, LCNAF, etc.)

2. **Document your methodology**:
   - spaCy model used (`en_core_web_trf`, `en_core_web_md`, etc.)
   - Confidence thresholds applied
   - Manual review/correction process
   - Entity types extracted

3. **Note limitations**:
   - NER is not 100% accurate
   - Wikidata linking confidence levels
   - Manual corrections applied

**Example citation text:**
> Named entities were extracted using spaCy 3.x (en_core_web_trf model) and linked to Wikidata identifiers using spacy-entity-linker. Entities with confidence scores below 0.75 were manually reviewed and corrected where necessary. Authority file identifiers (VIAF, LCNAF, ORCID, Getty TGN) were retrieved from Wikidata entity records.

---

## Version History

### Version 1.0 (Current)
- WebVTT transcript parsing with timestamp preservation
- spaCy transformer NER (en_core_web_trf default)
- Two-stage Wikidata linking (spacy-entity-linker + Search API)
- Confidence scoring and review flagging
- Authority ID enrichment (VIAF, LCNAF, ORCID, TGN)
- JSONL and CSV output formats
- Custom EntityRuler pattern support
- Configurable thresholds and parameters

---

*Last updated: February 2025*
