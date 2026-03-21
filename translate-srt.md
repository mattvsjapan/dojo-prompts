---
name: translate-srt
description: |
  Translate Japanese SRT subtitles into English for language learning.
  Prioritizes faithful representation of the Japanese over natural-sounding English.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Task
  - AskUserQuestion
---

# Translate SRT

Translate Japanese SRT subtitles into English for language learning purposes. These translations are meant to help learners understand what was said in Japanese — faithfulness to the original is more important than sounding natural in English.

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
- **Translation style notes** — ask if the user has specific preferences (though the default is faithful/literal for language learning)

### 2. Split with Python

**First, delete and recreate `/tmp/translate-srt/`** to ensure a clean slate — stale chunk files from previous runs will cause agents to translate wrong data:
```bash
rm -rf /tmp/translate-srt && mkdir -p /tmp/translate-srt
```

Then run the split script:
```bash
python3 dojo-prompts/scripts/srt_split.py <srt_file_path>
```

This parses the SRT, saves `metadata.json` and `chunks.json` to `/tmp/translate-srt/`, and writes chunk input files with context sections and `---BLOCK_SEP---` separators.

### 3. Verify Split Output

**GATE: Do NOT proceed to subagents until you verify the split completed successfully.** Run:
```bash
cat /tmp/translate-srt/chunks.json | python3 -c "import json,sys; chunks=json.load(sys.stdin); print(f'{len(chunks)} chunks created'); [print(f'  chunk {c[\"chunk_id\"]}: {c[\"num_blocks\"]} blocks, input exists: {__import__(\"os\").path.isfile(c[\"input_path\"])}') for c in chunks]"
```
Every chunk must show `input exists: True`. If not, the split script failed — fix it before continuing.

### 4. Launch Parallel Subagents

Use the `Task` tool with `subagent_type: "general-purpose"` and `run_in_background: true` to launch **all chunks in parallel** (all Task calls in a single message).

Each subagent receives a prompt like:

```
You are translating {movie/show name} subtitles from {source_language} to {target_language}.

Read the file {chunk_input_path}. It contains subtitle text blocks separated by
---BLOCK_SEP--- markers, with optional context sections before/after.

Translate ONLY the blocks between "=== TRANSLATE THE FOLLOWING ===" and
"=== END TRANSLATE ===". Do NOT translate context sections.

This chunk has EXACTLY {num_blocks} blocks. Your output MUST contain exactly
{num_blocks} blocks separated by {num_blocks - 1} ---BLOCK_SEP--- markers.

CRITICAL RULES:
- Output one translated block per input block, separated by ---BLOCK_SEP---
- Preserve the EXACT number of blocks ({num_blocks}) — this is critical for reassembly with timecodes
- Within each block, preserve the line structure (if a block has 2 lines, output 2 lines)
- These subtitles are for LANGUAGE LEARNING. Faithfulness to the Japanese is more important than natural-sounding English. The reader is trying to understand what was said in Japanese, not read a polished English script.
- Preserve the structure and nuance of the original Japanese. If a sentence is awkward or roundabout in Japanese, reflect that — don't clean it up into smooth English.
- Do NOT shorten, compress, or paraphrase. Translate everything that was said.
- When a Japanese word or phrase has no clean English equivalent, include the Japanese in parentheses — e.g., "it has a nostalgic feeling (懐かしい)"
- Preserve ALL formatting tags (<b>, <font>, </b>, </font>, <i>, etc.) exactly
- For sound effects/descriptions in tags like (MUSIC PLAYING), translate them too
- Keep proper nouns (character names, place names) in their original form

{any additional style notes from the user}

Write ONLY the translated blocks (with ---BLOCK_SEP--- separators) to
{chunk_output_path}. No extra text, no explanations, no headers.
```

### 5. Wait for Completion

**Do NOT poll output file existence.** A file existing on disk does not mean the agent has finished writing to it — reading a partially-written file produces corrupted/truncated output. Instead, wait for all background agent completion notifications before proceeding to reassembly. Only after every agent has reported completion should you move to step 6.

### 6. Reassemble and Validate

Run the reassembly script:
```bash
python3 dojo-prompts/scripts/srt_reassemble.py <output_srt_path>
```

This reads the chunk outputs from `/tmp/translate-srt/`, validates block counts, and writes the final SRT. If any chunks have block count mismatches, the script exits with code 1 and prints the mismatched chunk IDs to stderr.

**If reassembly reports mismatches**, re-launch subagents for only the failed chunks (same prompt, same parameters). Re-run reassembly after they complete. Continue retrying until all chunks validate or you've retried 3 times, then report any remaining failures to the user. Never silently pad with placeholder text.

### 7. Write Output

Write the translated SRT to: `<original_name>.<target_lang_code>.srt`

Place it alongside the original file. Use a short language code for the suffix:
- English → `en`, Japanese → `ja`, Chinese → `zh`, Korean → `ko`
- Spanish → `es`, French → `fr`, German → `de`, Portuguese → `pt`, Italian → `it`

If the original filename already has a language code (e.g., `movie.ja.srt`), replace it. If not, append it.

### 8. Spot Check

Read a few sections of the output (beginning, middle, end) to verify:
- Timecodes are preserved
- Formatting tags are intact
- Block structure looks correct
- Translations are faithful to the Japanese

## Important Rules

- **Never read the full SRT into main context** — always use Python scripts to handle file I/O on disk
- **Block count is sacred**: Each subagent MUST return exactly the same number of `---BLOCK_SEP---`-separated blocks as input. Validate after reassembly.
- **Timecodes are never modified**: Only the text content changes
- **Formatting tags**: Keep `<i>`, `<b>`, `<font>`, and any other HTML-like tags intact
- **Faithful translation for learning**: These translations help learners understand the Japanese. Prioritize faithfulness over natural English. Don't compress or paraphrase — preserve the full nuance and structure of the original
- **Do not proactively check on background agents** — wait for completion notifications, don't poll file existence or read agent output files mid-flight
- **Never pad with placeholders**: If a chunk has the wrong block count, retry the chunk — do not insert `[TRANSLATION MISSING]` or similar filler
