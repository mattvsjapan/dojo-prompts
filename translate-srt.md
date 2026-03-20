---
name: translate-srt
description: |
  Translate SRT subtitle files between languages using parallel subagents.
  Handles chunking, context overlap, and reassembly automatically.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Task
  - AskUserQuestion
---

# Translate SRT Subtitles

Translate SRT subtitle files between languages using parallel subagents for speed.

## Usage

The user provides an SRT file path and a target language. Optionally, the source language can be specified or auto-detected.

Arguments (passed after `/translate-srt`):
- First arg: path to the SRT file
- Optional: source and target language can be specified inline (e.g., `/translate-srt file.srt Japanese to English`)

If any required info is missing, ask the user.

## Architecture

**CRITICAL: Do NOT read the SRT file into the main context.** Large SRT files (2000+ blocks) will blow up the context window. Instead, use Python scripts to split/reassemble on disk, and have subagents read/write their own files.

The flow is:
1. Python script parses SRT → writes chunk input files + metadata JSON to `/tmp/translate-srt/`
2. Parallel subagents each read one chunk file, translate, write one output file
3. Python script reads all output files + metadata → writes final SRT

This keeps the main context lean (only metadata + status messages).

## Workflow

### 1. Gather Inputs

Determine:
- **SRT file path** — from argument or ask the user
- **Source language** — from argument, or read just the first ~30 lines to auto-detect
- **Target language** — from argument or ask the user
- **Translation style notes** — ask if the user has specific preferences (natural speech, formal, etc.)

### 2. Split with Python

Create `/tmp/translate-srt/` and write a Python script that:

1. Reads the SRT file (handling BOM + CRLF: `encoding='utf-8-sig'`, `.replace('\r\n', '\n')`)
2. Parses into blocks (split on `\n\n+`, each block = index + timecode + text lines)
3. Saves `metadata.json` — list of `{index, timecode}` for every block (used for reassembly)
4. Splits blocks into chunks of **100 blocks each** (use 50 for small files under 500 blocks)
5. For each chunk, writes a chunk input file with:
   - Context before section (5 preceding blocks, text only, marked as context)
   - Translate section (the chunk's text lines, separated by `---BLOCK_SEP---` between blocks)
   - Context after section (5 following blocks, text only, marked as context)
6. Saves `chunks.json` — list of `{chunk_id, start_block, end_block, num_blocks, input_path, output_path}`

Chunk input file format:
```
=== CONTEXT BEFORE (do NOT translate, reference only) ===
{preceding block texts, separated by blank lines}
=== END CONTEXT BEFORE ===

=== TRANSLATE THE FOLLOWING ===
{block 1 text}
---BLOCK_SEP---
{block 2 text}
---BLOCK_SEP---
{block 3 text}
...
=== END TRANSLATE ===

=== CONTEXT AFTER (do NOT translate, reference only) ===
{following block texts, separated by blank lines}
=== END CONTEXT AFTER ===
```

### 3. Launch Parallel Subagents

Use the `Task` tool with `subagent_type: "general-purpose"` and `run_in_background: true` to launch **all chunks in parallel** (all Task calls in a single message).

Each subagent receives a prompt like:

```
You are translating {movie/show name} subtitles from {source_language} to {target_language}.

Read the file {chunk_input_path}. It contains subtitle text blocks separated by
---BLOCK_SEP--- markers, with optional context sections before/after.

Translate ONLY the blocks between "=== TRANSLATE THE FOLLOWING ===" and
"=== END TRANSLATE ===". Do NOT translate context sections.

CRITICAL RULES:
- Output one translated block per input block, separated by ---BLOCK_SEP---
- Preserve the EXACT number of blocks — this is critical for reassembly with timecodes
- Within each block, preserve the line structure (if a block has 2 lines, output 2 lines)
- Translate for natural, realistic speech — how real people actually talk
- AVOID 役割語 (yakuwarigo/role language) — no stereotypical speech patterns
- Do NOT shorten or compress. Be faithful to the full nuance and length of the original
- Preserve ALL formatting tags (<b>, <font>, </b>, </font>, <i>, etc.) exactly
- For sound effects/descriptions in tags like (MUSIC PLAYING), translate them too
- Keep proper nouns (character names, place names) in their original form or standard katakana

{any additional style notes from the user}

Write ONLY the translated blocks (with ---BLOCK_SEP--- separators) to
{chunk_output_path}. No extra text, no explanations, no headers.
```

### 4. Wait for Completion

Check output file count periodically:
```bash
ls /tmp/translate-srt/chunk_*_output.txt 2>/dev/null | wc -l
```

Wait until all output files exist before reassembling.

### 5. Reassemble with Python

Write a Python script that:
1. Loads `metadata.json` (indices + timecodes) and `chunks.json` (chunk info)
2. For each chunk, reads the output file and splits by `---BLOCK_SEP---`
3. Validates block count matches expected (pad with `[TRANSLATION MISSING]` if short, truncate if long)
4. Pairs each translated text with its original index + timecode
5. Writes the final SRT: `{index}\n{timecode}\n{translated text}\n\n` for each block

### 6. Write Output

Write the translated SRT to: `<original_name>.<target_lang_code>.srt`

Place it alongside the original file. Use a short language code for the suffix:
- English → `en`, Japanese → `ja`, Chinese → `zh`, Korean → `ko`
- Spanish → `es`, French → `fr`, German → `de`, Portuguese → `pt`, Italian → `it`

If the original filename already has a language code (e.g., `movie.ja.srt`), replace it. If not, append it.

### 7. Spot Check

Read a few sections of the output (beginning, middle, end) to verify:
- Timecodes are preserved
- Formatting tags are intact
- Block structure looks correct
- Translation quality looks natural

## Important Rules

- **Never read the full SRT into main context** — always use Python scripts to handle file I/O on disk
- **Block count is sacred**: Each subagent MUST return exactly the same number of `---BLOCK_SEP---`-separated blocks as input. Validate after reassembly.
- **Timecodes are never modified**: Only the text content changes
- **Formatting tags**: Keep `<i>`, `<b>`, `<font>`, and any other HTML-like tags intact
- **Natural translation**: Translate how real people actually talk. Avoid 役割語 (yakuwarigo). Don't compress — faithfully recreate the full nuance of the original
- **Do not proactively check on background agents** — wait for completion notifications or poll the output file count, don't read agent output files
