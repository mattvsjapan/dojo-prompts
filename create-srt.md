---
name: create-srt
description: |
  Generate Japanese SRT subtitles from a video file using ElevenLabs Scribe v2
  and MeCab for natural bunsetsu boundaries.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# Create SRT

Generate natural Japanese subtitles from a video file using ElevenLabs Scribe v2 and MeCab bunsetsu segmentation.

## Usage

Run `/create-srt <video_file>` to generate an SRT file from a video.

## Requirements

```
pip install fugashi unidic-lite
```

An ElevenLabs API key with Scribe access.

## Workflow

### 1. Get the video file path and API key

Get the video file path from the argument or ask the user.

Check if `$ELEVENLABS_API_KEY` is set. If not, ask the user to paste their ElevenLabs API key. Store it as a shell variable for the duration of the session:

```bash
export ELEVENLABS_API_KEY="<key from user>"
```

### 2. Transcribe with ElevenLabs Scribe v2

Upload the video to the ElevenLabs Speech-to-Text API with word-level timestamps and diarization enabled:

```bash
curl -s -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -F "model_id=scribe_v2" \
  -F "file=@video.mp4" \
  -F "language_code=ja" \
  -F "timestamps_granularity=word" \
  -F "diarize=true" \
  > video.json
```

Name the JSON output after the video file (e.g., `kikai_onchi_01.mp4` → `kikai_onchi_01.json`) so all outputs share a consistent basename.

**Important:** The `-s` (silent) flag is required. Without it, curl's progress output gets written into the JSON file and corrupts it.

Files up to 3GB are supported. This can take a few minutes for longer videos.

### What the output looks like

The response JSON has this structure:

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
python3 dojo-prompts/scripts/srt_watch.py -o <video_stem> scribe_output.json
```

This produces `<video_stem>.srt` alongside the JSON file.

### 4. Preserve the JSON

**Do NOT delete the Scribe JSON file.** It is needed by other workflows (Anki deck generation, English translation). Only the SRT is the final output of this skill, but the JSON must be kept.

## Tuning parameters

Key constants are defined in `scripts/srt_common.py` and `scripts/srt_watch.py`:

| Parameter | Default | Effect |
|-----------|---------|--------|
| `GAP_THRESHOLD` | 0.1s | Time gap that forces a segment break between bunsetsu. |
| `MERGE_GAP_LIMIT` | 0.4s | Segments this far apart are never merged into one line. |
| `LINE_CHAR_LIMIT` | 18 | Max characters per subtitle line. |
