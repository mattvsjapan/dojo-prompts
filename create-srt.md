---
name: create-srt
description: |
  Generate Japanese SRT subtitles from a video file using a speech-to-text
  provider (ElevenLabs Scribe v2 or Soniox) and MeCab for natural bunsetsu
  boundaries.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# Create SRT

Generate natural Japanese subtitles from a video file using a speech-to-text provider (ElevenLabs Scribe v2 or Soniox) and MeCab bunsetsu segmentation.

## Usage

Run `/create-srt <video_file>` to generate an SRT file from a video.

## Requirements

```
pip install fugashi unidic-lite requests
```

`ffmpeg` and `ffprobe` on PATH — `transcribe.py` uses them to strip the video
stream and upload audio only (a few MB instead of the whole file). If they're
missing it still works, just uploads the full file.

An API key for whichever provider you choose:
- **ElevenLabs** — `$ELEVENLABS_API_KEY` (Scribe access)
- **Soniox** — `$SONIOX_API_KEY`

## Workflow

### 1. Get the video file path and choose a provider

Get the video file path from the argument or ask the user.

**Ask the user which speech-to-text provider to use: ElevenLabs Scribe v2 or Soniox.** Both produce the same transcript JSON, so every downstream step is identical — the choice only affects transcription quality/speed and which API key is needed.

Make sure the chosen provider's key is set. If not, ask the user to paste it and export it for the session:

```bash
export ELEVENLABS_API_KEY="<key from user>"   # if ElevenLabs
export SONIOX_API_KEY="<key from user>"        # if Soniox
```

### 2. Transcribe

Run the transcribe helper with the chosen provider. It transcribes with character-level timestamps and diarization, then writes a transcript JSON in the canonical shape (same shape regardless of provider). Use `-o` to name the output after the video file:

```bash
python3 dojo-prompts/scripts/transcribe.py --provider <elevenlabs|soniox> --language ja -o <video_stem> video.mp4
```

This produces `<video_stem>.json` (e.g., `kikai_onchi_01.mp4` → `kikai_onchi_01.json`) so all outputs share a consistent basename.

Notes:
- **ElevenLabs** is a single synchronous request. Files up to 3GB; longer videos can take a few minutes.
- **Soniox** runs an async job (upload → transcribe → poll). The helper handles polling and deletes the uploaded file from your account when done.
- **Transcribe one file at a time.** STT accounts have low concurrency limits, and concurrent uploads fail with mid-upload connection resets. For multiple videos, run transcriptions sequentially — never in parallel subagents. (The helper retries transient failures with backoff, but it cannot beat an over-limit account.)
- Do not request `additional_formats` — we build the SRT ourselves from the raw word data.

### What the output looks like

Both providers write the same canonical JSON structure:

```json
{
  "language_code": "jpn",
  "language_probability": 1.0,
  "text": "Full transcript as a single string...",
  "words": [
    {
      "text": "[オープニングミュージック]",
      "start": 0.28,
      "end": 12.28,
      "type": "audio_event",
      "speaker_id": "speaker_0",
      "logprob": -0.057
    },
    {
      "text": " ",
      "start": 13.66,
      "end": 13.72,
      "type": "spacing",
      "speaker_id": "speaker_0",
      "logprob": 0.0
    },
    {
      "text": "世",
      "start": 13.72,
      "end": 13.86,
      "type": "word",
      "speaker_id": "speaker_1",
      "logprob": -0.018
    }
  ],
  "transcription_id": "..."
}
```

Key things to know:
- For Japanese, each character is returned as a separate "word" entry. We concatenate them ourselves and use MeCab to find natural bunsetsu (phrase) boundaries.
- `type` is one of: `"word"` (actual text), `"spacing"` (whitespace, skip these), `"audio_event"` (music, laughter, etc. in brackets).
- `speaker_id` identifies different speakers (useful for diarization).
- `start` and `end` are timestamps in seconds.
- Do not request `additional_formats` from the API — we build the SRT ourselves from the raw word data.

### 3. Generate the SRT with MeCab bunsetsu segmentation

MeCab with UniDic segments Japanese text into bunsetsu (phrase units), so subtitles break at natural grammatical boundaries.

Run the conversion script, using `-o` to name the output after the video file:
```bash
python3 dojo-prompts/scripts/srt_watch.py -o <video_stem> <video_stem>.json
```

This produces `<video_stem>.srt` alongside the JSON file.

### 4. Preserve the JSON

**Do NOT delete the transcript JSON file.** It is needed by other workflows (Anki deck generation, English translation). Only the SRT is the final output of this skill, but the JSON must be kept.

## Tuning parameters

Key constants are defined in `scripts/srt_common.py` and `scripts/srt_watch.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `GAP_THRESHOLD` | 0.1s | Time gap that forces a segment break between bunsetsu. |
| `MERGE_GAP_LIMIT` | 0.4s | Segments this far apart are never merged into one line. |
| `LINE_CHAR_LIMIT` | 18 | Max characters per subtitle line. |
