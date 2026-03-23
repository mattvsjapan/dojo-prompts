# SRT Algorithm Design

This document explains the subtitle generation pipeline in `scripts/srt_common.py`, `scripts/srt_watch.py`, `scripts/srt_anki.py`, and `scripts/srt_translate.py`. It converts ElevenLabs Scribe JSON (character-level timestamps for Japanese) into SRT subtitles with natural line breaks.

The script produces **two variants** from the same bunsetsu data:
- **Watch** — optimized for reading subtitles while watching video (short lines, timing-aware pairing)
- **Anki** — optimized for flashcard creation (one sentence per cue, no line length limits)

## Input

ElevenLabs returns **character-level** timestamps for Japanese — each character (or sometimes multi-character token like `。API`) gets its own `start`/`end` time, plus a `speaker_id` and `type` (word, spacing, audio_event). Multi-character tokens are split into individual characters with linearly interpolated timestamps.

## Pipeline Overview

The pipeline follows a "split maximally, then merge" philosophy. Stage 1 is shared; the variants diverge after that.

```
                    ┌→ Segments → Lines → Cues → Watch SRT/HTML
Characters → Bunsetsu
                    └→ Anki Cues → Anki SRT/HTML
```

Each stage is described below.

## Stage 1: Characters → Bunsetsu

**Goal:** Group individual characters into bunsetsu (文節) — the smallest natural phrase units in Japanese.

1. Characters are first split by **speaker** and then by **sentence-ending punctuation** (。！？) before being fed to MeCab. This prevents MeCab from analyzing cross-sentence text as a single unit.

2. MeCab (with UniDic via `fugashi`) tokenizes the text into morphemes. Morphemes are grouped into bunsetsu using POS-based heuristics:
   - A new bunsetsu starts at each **content word**: 名詞, 動詞, 形容詞, 形状詞, 副詞, 連体詞, 接続詞, 感動詞, 代名詞
   - **Function morphemes** (助詞, 助動詞, 接尾辞, 記号) attach to the preceding bunsetsu
   - **接頭辞** (prefixes like お, ご) start a new bunsetsu but merge with the following content word

3. Each bunsetsu is tagged with `ends_clause=True` if its final morpheme is:
   - A 助動詞 (た, だ, ます, です, etc.)
   - A clause-linking 助詞 (て, ば, から, けど, と, etc.)

4. Each bunsetsu stores `morph_count` — the number of MeCab morphemes it contains. This is used by the Anki variant for token-based splitting thresholds.

This tagging is used later for segment splitting (watch) and comma splitting (Anki).

## Watch Variant

Stages 2–5 below apply only to the **watch** variant.

## Stage 2: Bunsetsu → Segments

**Goal:** Split bunsetsu into maximally-small segments at every possible boundary, so that later stages can selectively merge them back.

Splits happen at (in order):
1. **Speaker changes** — always split
2. **Time gaps ≥ 0.1s** — even tiny pauses become segment boundaries
3. **Punctuation** (。！？、, etc.) — split after any punctuation
4. **Clause ends** — split after bunsetsu tagged `ends_clause`

**Merge-back pass:** After splitting, any segment under 8 characters is merged back into the previous segment (same speaker only). This prevents orphaned fragments like `あります。` (5ch) from becoming their own cue. Rules:
- If combined ≤ 18ch (LINE_CHAR_LIMIT): merge unconditionally
- If combined > 18ch: re-split at the nearest `。` boundary, or if none exists, at the most balanced bunsetsu boundary
- Never merge into a segment that already contains `。` (periods must stay at line ends)

## Stage 3: Segments → Lines

**Goal:** Merge adjacent segments into lines that fit within **18 characters** (LINE_CHAR_LIMIT).

A segment merges into the current line if ALL conditions are met:
- Same speaker
- Combined character count ≤ 18
- Previous segment doesn't end with 。！？
- Current line doesn't already contain 。
- Time gap between segments < 0.4s (MERGE_GAP_LIMIT)

The 0.4s gap limit prevents merging across noticeable pauses, which would keep a subtitle on screen during silence.

Each line is always a single speaker.

## Stage 4: Lines → Cues

**Goal:** Pair lines into subtitle cues of 1–2 lines each.

**Oversized lines** (>18ch) become their own cue, split into two balanced lines at the best bunsetsu boundary (preferring `。` boundaries).

**Default is single-line cues.** Two lines only get paired if at least one line **needs** merging:
- Duration < 0.6s (too brief — would flash on screen), OR
- Character density > 8 ch/s (too dense to read comfortably)

When pairing, these guards must also pass:
- Second line ≤ 18ch
- Time gap < 0.4s

**Rebalancing:** Same-speaker pairs get flattened and re-split at the most balanced bunsetsu boundary (preferring `。` boundaries). Cross-speaker pairs keep their lines as-is.

**Post-pass:** Any single-line cue with a mid-text `。` is split into two lines at the period boundary.

## Stage 5: Cues → SRT

- `。` is stripped from line ends only (mid-line `。` retained, though the pipeline should prevent these)
- Cue end times are extended by 0.5s (CUE_LINGER), capped at the next cue's start time, so subtitles don't disappear the instant speech ends

## Anki Variant

The Anki variant takes a completely different path from the shared bunsetsu data. Instead of the segment → line → cue pipeline, it builds cues directly from bunsetsu with sentence-level grouping.

### Sentence Splitting

Bunsetsu are accumulated into a cue until a split point is reached:
- **Sentence-ending punctuation** (。！？) — always starts a new cue
- **Speaker changes** — always starts a new cue
- **Commas** (、) — conditionally starts a new cue (see below)

### Comma Splitting

Long sentences without periods would produce unwieldy Anki cards. Commas are used as secondary split points, but only when the cue is long enough:

- At a comma, if the current cue has **≥ 5 MeCab tokens**, split into a new cue
- **Orphan protection:** Do NOT split if BOTH conditions are true:
  - The next section (up to the next comma/period/end) is **≤ 2 tokens**
  - The current cue is **≤ 7 tokens**

This prevents short trailing fragments like `やっぱ。` from being stranded as their own cue, while still splitting at commas in genuinely long sentences.

### No Line Limits

Unlike the watch variant, Anki cues are always single-line with no character limit. The goal is one complete thought per card, regardless of length.

## Translate Variant

The translate variant builds on the Anki cues by merging adjacent small cues into larger translation-friendly blocks.

### Merge Pass

Starting from the Anki cues, adjacent cues are merged if:
- Time gap between them is **< 0.4s** (MERGE_GAP_LIMIT)
- Combined MeCab token count is **≤ 20** (TRANSLATE_MAX_TOKENS)

Merging is allowed across speakers — cross-speaker cues get separate lines within the same block, with each speaker's content on its own line.

### Speaker Dashes

When a cue contains multiple speakers, each speaker's line is prefixed with `- ` (Netflix-style) in the SRT output. This makes speaker changes visually clear both for human readers and for the translation LLM. The HTML visualization also shows these dashes.

### Translation Pipeline Integration

The translate SRT is the input for the parallel translation pipeline (`translate-srt.md`). The reassembly script (`srt_reassemble.py`) handles formatting programmatically:
- **Merged dash fix:** If the LLM collapses `- foo\n- bar` into `- foo - bar`, the script splits them back apart by detecting ` - ` within lines starting with `- `
- **Long line balancing:** Any line over 50 characters is split into two balanced lines at the nearest word boundary
- These fixes mean the translation prompt can stay simple — no need for verbose formatting instructions

## Key Constants

| Constant | Value | Purpose |
|---|---|---|
| `GAP_THRESHOLD` | 0.1s | Minimum gap to force a segment split |
| `MERGE_GAP_LIMIT` | 0.4s | Segments/lines this far apart can never merge |
| `LINE_CHAR_LIMIT` | 18 | Max characters per line during merging |
| `MIN_SEGMENT_CHARS` | 8 | Segments smaller than this merge back into previous |
| `CUE_LINGER` | 0.5s | How long a cue stays on screen after speech ends |
| Merge trigger: duration | < 0.6s | Line needs to pair with neighbor |
| Merge trigger: density | > 8 ch/s | Line needs to pair with neighbor |
| `ANKI_COMMA_TOKEN_LIMIT` | 5 | Split at commas when cue has this many MeCab tokens |
| Anki orphan: max next tokens | 2 | Don't split if next section is this small... |
| Anki orphan: max current tokens | 7 | ...and current cue is this small |
| `TRANSLATE_MAX_TOKENS` | 20 | Max MeCab tokens per translate cue after merging |

## Design Philosophy

1. **Split first, merge later.** It's easier to combine things that are too small than to break apart things that are too large. Every possible boundary is created first, then selectively removed.

2. **Periods end lines.** `。` should never appear mid-line. This is enforced at every stage: segment merge-back, line merging, cue rebalancing, and a final post-pass.

3. **Timing-based cue pairing.** Rather than always creating two-line cues, we default to single-line and only pair when a line would be too brief or too dense to read on its own.

4. **Bunsetsu boundaries for all splits.** Every line break falls at a bunsetsu boundary, never mid-word. This is the core advantage of using MeCab over simpler character-count approaches.

## Dependencies

- `fugashi` — Python MeCab binding
- `unidic-lite` — MeCab dictionary (UniDic, not ipadic)

Install: `pip install fugashi unidic-lite`

## Usage

```bash
python3.11 scripts/srt_watch.py <elevenlabs_scribe.json>
python3.11 scripts/srt_anki.py <elevenlabs_scribe.json>
python3.11 scripts/srt_translate.py <elevenlabs_scribe.json>
```

Outputs:
- `<name>.srt` — watch subtitle file
- `<name>_cues.html` — watch visual debug view with bunsetsu boundaries, speaker colors, and timing info
- `<name>.anki.srt` — Anki subtitle file (sentence-level cues)
- `<name>_anki.html` — Anki visual debug view
- `<name>.translate.srt` — translate subtitle file (merged cues for translation pipeline)
- `<name>_translate.html` — translate visual debug view
