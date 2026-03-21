---
name: create-srt
description: |
  Generate Japanese SRT subtitles from a video file using ElevenLabs Scribe v2
  and BudouX for natural phrase boundaries.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - AskUserQuestion
---

# Create SRT

Generate natural Japanese subtitles from a video file using ElevenLabs Scribe v2 and BudouX.

## Usage

Run `/create-srt <video_file>` to generate an SRT file from a video.

## Requirements

```
pip install budoux
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
  > scribe_output.json
```

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
- For Japanese, each character is returned as a separate "word" entry. We concatenate them ourselves and use BudouX to find natural phrase boundaries.
- `type` is one of: `"word"` (actual text), `"spacing"` (whitespace, skip these), `"audio_event"` (music, laughter, etc. in brackets).
- `speaker_id` identifies different speakers (useful for diarization).
- `start` and `end` are timestamps in seconds.
- Do not request `additional_formats` from the API — we build the SRT ourselves from the raw word data.

### 3. Generate the SRT with BudouX phrase boundaries

BudouX is Google's ML-based line break library for Japanese. It predicts natural phrase (bunsetsu) boundaries, so subtitles never split mid-word.

Run the conversion script:
```bash
python3 dojo-prompts/scripts/scribe_to_srt.py scribe_output.json output.srt
```

Optional flags for tuning:
```bash
python3 dojo-prompts/scripts/scribe_to_srt.py scribe_output.json output.srt --max-chars 23 --gap-threshold 0.4
```

### 4. Clean up

Delete the intermediate JSON file after the SRT has been successfully created:

```bash
rm scribe_output.json
```

## Tuning parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| Gap threshold | 0.4s | Silence duration that splits utterances. Lower = more splits between phrases. Higher = longer unbroken runs. |
| `MAX_CHARS` | 25 | Max characters per line. Both lines in a two-line entry share this cap. Lower = shorter, more frequent subtitles. |

For denser subtitles (e.g. a lecture), increase `MAX_CHARS` to 28-30. For fast-paced dialogue, decrease to 20.

## Alternative: stable-ts

If you want more control over regrouping (e.g. split by duration, merge by gap), you can use `stable-ts` instead of the manual approach above. Convert the ElevenLabs words into stable-ts format and apply regrouping rules:

```python
import stable_whisper

words_st = [{'word': w['text'], 'start': w['start'], 'end': w['end']}
            for w in data['words'] if w['type'] != 'spacing']

result = stable_whisper.WhisperResult({
    'language': 'ja',
    'segments': [{'id': 0, 'words': words_st}]
})

result.regroup('sp=。/！/？/!/?_sp=、/,_sg=.3_sl=20_mg=.05+12')
result.to_srt_vtt('output.srt', word_level=False)
```

This works but `sl` (split by length) doesn't know about Japanese word boundaries, so it can cut mid-word. The BudouX approach above avoids this problem entirely.
