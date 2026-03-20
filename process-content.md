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

### 1. Get the source

Ask the user for a YouTube URL. This can be:
- A single video
- A playlist
- A full channel

### 2. Download with yt-dlp

Download the video(s) using yt-dlp:

```bash
# Single video
yt-dlp -o "%(title)s.%(ext)s" "URL"

# Playlist or channel
yt-dlp -o "%(playlist_index)03d_%(title)s.%(ext)s" "URL"
```

Tell the user:

> Downloading your video(s) with yt-dlp...

### 3. Create Japanese subtitles

This step always runs. Use the **create-srt** skill to transcribe each video with ElevenLabs Scribe v2 and generate SRT files with natural phrase boundaries using BudouX.

Tell the user:

> Transcribing the audio with ElevenLabs Scribe v2 and generating Japanese subtitle files...

Read the full create-srt skill at `create-srt.md` (in the same directory as this file) and follow its instructions for each video file.

### 4. Ask what else the user wants

Present the user with these options:

> Your Japanese subtitles are ready. What else would you like me to generate?
>
> - **English subtitles** — translate the Japanese SRT into English
> - **Condensed audio** — extract just the spoken audio for passive listening
> - **Subs2SRS deck** — generate an Anki deck with audio clips and subtitle text
>
> You can pick any combination, or none.

### 5. Run selected steps

For each option the user selected:

**English subtitles** — Use the **translate-srt** skill. Read the full skill at `translate-srt.md` (in the same directory as this file) and follow its instructions, translating from Japanese to English.

**Condensed audio** — Run subs2cia in condense mode. **You must use [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia)**, not the original — install with `pip install git+https://github.com/mattvsjapan/subs2cia.git`.
```bash
subs2cia condense -i "*.mkv" -ai <audio_index> -si <subtitle_index> -d out_condense
```
Use the same track indices identified during the create-srt step.

**Subs2SRS deck** — Use the **subs2srs** skill. Read the full skill at `subs2srs.md` (in the same directory as this file) and follow its instructions.

### 6. Report results

Tell the user what was generated and where the output files are.
