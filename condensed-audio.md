---
name: condensed-audio
description: |
  Generate condensed audio from video files using subs2cia. Extracts only
  the spoken dialogue as an MP3 for passive listening practice.
allowed-tools:
  - Bash
  - Read
  - Glob
  - AskUserQuestion
---

# Condensed Audio

Generate condensed audio that contains only the spoken dialogue from a video, cutting out all silence. The output is a single MP3 file for passive listening.

## Usage

Run `/condensed-audio` with a video file or directory path.

## Requirements

- [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia) — **must be this fork**, not the original. Install/upgrade with:
  ```bash
  pip install --upgrade git+https://github.com/mattvsjapan/subs2cia.git
  ```
- ffmpeg and ffprobe on PATH

## Workflow

### 1. Get the video file path

Get the video file path from the argument or ask the user.

### 2. Find the timing source

Look for input sources in this priority order:

**1. Scribe JSON file (preferred)** — Check for a `.json` file alongside the video with the same basename:
```bash
ls "${VIDEO_DIR}/${VIDEO_STEM}.json" 2>/dev/null
```
JSON gives the most accurate speech gap detection because it has character-level timestamps from ElevenLabs Scribe.

**2. External SRT file (fallback)** — Check for a `.srt` file alongside the video:
```bash
ls "${VIDEO_DIR}/${VIDEO_STEM}.srt" 2>/dev/null
```

**3. Embedded subtitle tracks (last resort)** — Use ffprobe to find embedded tracks:
```bash
ffprobe -v error -select_streams s -show_entries stream=index:stream_tags=language,title -of csv=p=0 "video.mp4"
```

### 3. Run subs2cia

**CRITICAL:** Always pass `--no-gen-subtitle` — we only want the MP3, not a condensed subtitle file.

```bash
# With JSON (preferred)
subs2cia condense -i "video.mp4" "video.json" -t 1500 -p 200 --no-gen-subtitle -d out_condense

# With external SRT (fallback)
subs2cia condense -i "video.mp4" -si 0 --no-gen-subtitle -d out_condense
```

For YouTube downloads, use `-ai 0` to explicitly select the first audio stream rather than `-tl ja` — yt-dlp sometimes mislabels audio stream languages.

### 4. Move and clean up

Move the condensed MP3 out of the output directory and into the source directory, then delete the output directory:
```bash
mv out_condense/*.mp3 "${VIDEO_DIR}/"
rm -rf out_condense/
```

**Do NOT delete the Scribe JSON file** — it may be needed by other workflows.

### 5. Report results

Tell the user where the condensed MP3 was saved.
