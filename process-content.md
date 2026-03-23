---
name: process-content
description: |
  Download Japanese content from YouTube and process it into subtitles,
  condensed audio, and/or Anki decks. Orchestrates the other skills.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

# Process Content

Download Japanese content from YouTube and process it into study materials.

## Usage

Run `/process-content` and the skill will walk you through the process.

## Workflow

### 1. Gather everything up front

Ask the user for a YouTube URL. This can be:
- A single video
- A playlist
- A full channel

Then immediately ask what outputs they want:

> I'll download this and transcribe it. What would you like me to generate?
>
> - **Japanese subtitles** — SRT with natural bunsetsu line breaks for watching
> - **English subtitles** — translated SRT for language learning reference
> - **Condensed audio** — extract just the spoken audio for passive listening
> - **Anki deck** — generate flashcards with audio clips and subtitle text
>
> You can pick any combination.

Wait for the user to answer before starting any work.

### 2. Run everything

Once you have the URL and know what they want, execute all steps in sequence without further interaction.

**Download** with yt-dlp:

```bash
# Single video
yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]" --merge-output-format mp4 -o "%(title)s.%(ext)s" "URL"

# Playlist or channel
yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]" --merge-output-format mp4 -o "%(playlist_index)03d_%(title)s.%(ext)s" "URL"
```

**Transcribe** — This always runs. Use the **create-srt** skill's steps 1-2 to transcribe each video with ElevenLabs Scribe v2 and produce the Scribe JSON file. Read `create-srt.md` (in the same directory as this file). The JSON is the foundation for all other outputs.

**Japanese subtitles** (if selected) — Run `srt_watch.py` on the JSON to generate watch-optimized SRT files. See step 3 in `create-srt.md`.

**English subtitles** (if selected) — Use the **translate-srt** skill. Read the full skill at `translate-srt.md` (in the same directory as this file) and follow its instructions, passing the Scribe JSON file. The intermediate Japanese `.translate.srt` is cleaned up automatically.

**Condensed audio** (if selected) — Run subs2cia in condense mode. **You must use [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia)**, not the original — install/upgrade with `pip install --upgrade git+https://github.com/mattvsjapan/subs2cia.git`. Prefer the Scribe JSON as the timing source (more accurate speech gaps); fall back to SRT only if no JSON is available.
```bash
# With JSON (preferred)
subs2cia condense -i "video.mp4" "scribe_output.json" -t 1500 -p 200 --no-gen-subtitle -d out_condense

# Fallback: with SRT
subs2cia condense -i "video.mp4" -si <subtitle_index> --no-gen-subtitle -d out_condense
```

**Anki deck** (if selected) — Use the **anki** skill. Read the full skill at `anki.md` (in the same directory as this file) and follow its instructions.

### 3. Report results

Tell the user what was generated and where the output files are.
