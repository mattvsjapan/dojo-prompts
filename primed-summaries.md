---
name: primed-summaries
description: |
  Group target-language SRT sentences into topical chunks and write a short
  English summary for each chunk. Output is a new SRT where each entry's
  timestamp spans a chunk's full time range and the text is the English
  summary. Used to build "primed listening" audio: English preview, then
  the original audio for that span.
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Task
  - AskUserQuestion
---

# Primed Summaries

Take an existing SRT in any source language and produce a **summary SRT** — a smaller SRT where each entry covers many original sentences and the text is a 1–3 sentence **English summary** of what's said in that span. This is not a translation: the AI groups sentences into topical chunks and writes fresh English summaries.

The output drives downstream "primed listening" audio (English preview → original audio for the chunk → next preview → ...).

## Usage

The user provides a path to a Scribe JSON file or an SRT file. Optionally the source language can be specified inline (e.g. `/primed-summaries file.json Japanese`).

**Always prefer JSON over SRT** — if a Scribe JSON file exists alongside the SRT (same basename), use the JSON. Only use an SRT directly if no JSON is available. If the source language is missing, read just the first ~30 lines of the SRT (or after generating one from JSON) to auto-detect.

## Architecture

**Do NOT read the full SRT into the main context.** Two kinds of subagents do all the heavy reading:

1. **Premise subagent** (one-time): reads the entire transcript and writes a 2–4 sentence premise covering genre, recurring characters/topics, and tone. Saved to `/tmp/primed-summaries/premise.txt`.
2. **Window subagents** (many, sequential): each reads one window brief — the premise + the last 3 accepted summaries + 40 numbered sentences — and returns a JSON array of chunks with English summaries.

Sequential is required because the sliding window's cursor depends on the previous window's accepted chunks. The Python helper handles SRT parsing, brief generation, JSON validation/repair, the core-region filter, and final SRT assembly.

`WINDOW_SIZE=40` sentences per window, `CORE_SIZE=25` core region — chunks ending past sentence 25 of a non-final window are discarded so chunk boundaries fall on natural topic transitions, not on window edges.

## Workflow

### 1. Gather inputs

- **Input file** — look for a Scribe JSON file (`.json`) first, then fall back to an existing SRT. Always prefer JSON.
- **Source language** — from argument or auto-detect by reading the first ~30 lines of the SRT, or by `head`-ing the JSON and inspecting a few `text` fields.

### 2. Prepare state

```bash
rm -rf /tmp/primed-summaries
python3 dojo-prompts/scripts/srt_summarize.py prepare <json_or_srt_path>
```

`prepare` accepts a Scribe JSON (preferred) or an SRT.

- **JSON branch:** sentences are split on sentence-ending punctuation (`。！？!?`), speaker changes, and pauses ≥ 1.0 second. Timestamps come straight from word-level Scribe data.
- **SRT branch:** one SRT block = one sentence.

Output: `/tmp/primed-summaries/{blocks.json,state.json,full_transcript.txt}` plus the total sentence count and estimated number of windows.

### 3. Generate the premise (one subagent, foreground)

Spawn a subagent (Task tool, `subagent_type: "general-purpose"`) with this prompt:

```
You are establishing the global context for a summarization task.

Read /tmp/primed-summaries/full_transcript.txt — it is a numbered transcript of
a {SOURCE_LANGUAGE} video. Then write a 2-4 sentence English premise covering:

- What kind of content this is (genre / format — e.g. lecture, interview,
  vlog, anime episode, podcast, recipe demo)
- Who's speaking (number of speakers, named characters/hosts if identifiable,
  approximate roles)
- The overall topic, setting, or arc
- The tone (casual, formal, comedic, instructional, etc.)

This premise will be passed to every per-window summarizer so they can write
summaries that fit the show. Keep it dense and informative — names and
specifics matter more than vague descriptors.

Write ONLY the premise (no headers, no commentary) to
/tmp/primed-summaries/premise.txt.
```

Wait for completion, then verify the file exists and is non-empty:

```bash
test -s /tmp/primed-summaries/premise.txt && cat /tmp/primed-summaries/premise.txt
```

### 4. Sliding window loop

Repeat until `next-window` prints `DONE`:

#### 4a. Build the next window brief

```bash
python3 dojo-prompts/scripts/srt_summarize.py next-window "<source_language>"
```

Output is one of:
- `DONE` — all sentences are chunked. Skip to step 5.
- `PARTIAL cursor=N window_size=M core_size=25 brief=/tmp/primed-summaries/window_brief.txt`
- `FINAL cursor=N window_size=M core_size=25 brief=/tmp/primed-summaries/window_brief.txt`

The brief file already contains the full prompt: premise + last 3 summaries + this window's numbered sentences + the rules. Don't read the brief into main context — the subagent will read it.

#### 4b. Spawn a window subagent (Task tool, foreground, sequential)

```
Read /tmp/primed-summaries/window_brief.txt and follow its instructions.
Write your JSON response (and ONLY the JSON, no markdown fences, no commentary)
to /tmp/primed-summaries/window_output.json.
```

Wait for the subagent to complete before continuing. Do not run window subagents in parallel — each window depends on the previous window's accepted chunks.

#### 4c. Accept the window

```bash
python3 dojo-prompts/scripts/srt_summarize.py accept /tmp/primed-summaries/window_output.json
```

This validates the JSON, repairs gaps, applies the core-region filter (unless `FINAL`), advances the cursor, and appends the accepted chunks to state.

If `accept` exits non-zero (malformed JSON, overlap, etc.), retry the same window: re-spawn the subagent with the same brief and re-run `accept`. After 3 failures on the same window, write a fallback JSON covering the window with uniform 5-sentence chunks and empty summaries, `accept` it, and log the cursor range to a `failed_windows.txt` file so the user can revisit those spans manually:

```bash
echo "cursor=<N> size=<M>" >> /tmp/primed-summaries/failed_windows.txt
```

Loop back to 4a.

### 5. Finalize

```bash
python3 dojo-prompts/scripts/srt_summarize.py finalize <output_path>
```

Output path convention: `<original_stem>.summary.en.srt`, placed alongside the input file (the JSON or the SRT). Strip any source-language code (e.g. `.ja`) from the stem before appending `.summary.en.srt`.

If `/tmp/primed-summaries/failed_windows.txt` exists, surface it to the user — those spans have placeholder summaries and may need a manual pass.

**Never delete the Scribe JSON.**

### 6. Spot check

Read a few entries (beginning, middle, end) of the output SRT to verify timestamps span sensible ranges and summaries read as fluent English consistent with the premise.

## Important rules

- **Never read the full SRT or full transcript into main context** — only the premise subagent and window subagents touch transcript text.
- **Sequential, not parallel** — window subagents must run one at a time. Each window's start cursor depends on which chunks the previous window accepted.
- **Summaries are English, not translations** — write fresh English describing what's said, not sentence-by-sentence translation.
- **Window-local numbering** — the JSON `start`/`end` always refer to numbers `1..M` within the current window. The helper remaps to global indices.
- **Contiguous chunks** — first chunk starts at 1, last ends at M, no gaps or overlaps. The helper repairs minor gaps but rejects overlaps.
- **3–15 sentences per chunk** — short enough to summarize tightly, long enough to be a meaningful preview.
