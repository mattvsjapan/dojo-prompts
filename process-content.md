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

> I'll download this and create Japanese subtitles. What else would you like?
>
> - **English subtitles** — translate the Japanese SRT into English
> - **Condensed audio** — extract just the spoken audio for passive listening
> - **Subs2SRS deck** — generate an Anki deck with audio clips and subtitle text
>
> You can pick any combination, or none.

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

**Create Japanese subtitles** — This always runs. Use the **create-srt** skill to transcribe each video with ElevenLabs Scribe v2 and generate SRT files with natural bunsetsu boundaries using MeCab. Read the full skill at `create-srt.md` (in the same directory as this file) and follow its instructions for each video file.

**English subtitles** (if selected) — Use the **translate-srt** skill. Read the full skill at `translate-srt.md` (in the same directory as this file) and follow its instructions, translating from Japanese to English.

**Condensed audio** (if selected) — Run subs2cia in condense mode. **You must use [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia)**, not the original — install with `pip install git+https://github.com/mattvsjapan/subs2cia.git`.
```bash
subs2cia condense -i "*.mp4" -ai <audio_index> -si <subtitle_index> -d out_condense
```
Use the same track indices identified during the create-srt step.

**Subs2SRS deck** (if selected) — Use the **anki** skill. Read the full skill at `anki.md` (in the same directory as this file) and follow its instructions.

### 3. Report results

Tell the user what was generated and where the output files are.
