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

An ElevenLabs API key set as `$ELEVENLABS_API_KEY`.

## Workflow

### 1. Get the video file path

From the argument or ask the user.

### 2. Transcribe with ElevenLabs Scribe v2

Upload the video to the ElevenLabs Speech-to-Text API with word-level timestamps and diarization enabled:

```bash
curl -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -F "model_id=scribe_v2" \
  -F "file=@video.mp4" \
  -F "language_code=ja" \
  -F "timestamps_granularity=word" \
  -F "diarize=true" \
  > scribe_output.json
```

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

```python
import json
import budoux

parser = budoux.parser.load_default_japanese_parser()

with open('scribe_output.json') as f:
    data = json.load(f)

# -- Build character list, skipping spacing tokens --
chars = []
for w in data['words']:
    if w['type'] == 'spacing':
        continue
    chars.append({
        'text': w['text'],
        'start': w['start'],
        'end': w['end'],
        'is_event': w['type'] == 'audio_event'
    })

# -- Group into utterances by silence gaps >= 0.4s --
utterances = []
current = [chars[0]]
for c in chars[1:]:
    gap = c['start'] - current[-1]['end']
    if gap >= 0.4:
        utterances.append(current)
        current = [c]
    else:
        current.append(c)
if current:
    utterances.append(current)

# -- Build subtitle entries --
TARGET_CHARS = 20  # aim for this many chars per line
MAX_CHARS = 35     # never exceed this

srt_entries = []

for utt in utterances:
    # Audio events (e.g. [音楽]) stay as single entries
    if len(utt) == 1 and utt[0]['is_event']:
        srt_entries.append({
            'start': utt[0]['start'],
            'end': utt[0]['end'],
            'text': utt[0]['text']
        })
        continue

    # Join characters into full text and find phrase boundaries
    full_text = ''.join(c['text'] for c in utt)
    phrases = parser.parse(full_text)

    # Map phrases back to character-level timestamps
    char_idx = 0
    phrase_spans = []
    for phrase in phrases:
        end_idx = char_idx + len(phrase)
        phrase_spans.append({
            'text': phrase,
            'start': utt[char_idx]['start'],
            'end': utt[min(end_idx - 1, len(utt) - 1)]['end'],
        })
        char_idx = end_idx

    # Accumulate phrases into subtitle lines
    current_line = []
    current_len = 0

    for ps in phrase_spans:
        plen = len(ps['text'])
        if current_len + plen > MAX_CHARS and current_line:
            # Would exceed max — flush current line first
            srt_entries.append({
                'start': current_line[0]['start'],
                'end': current_line[-1]['end'],
                'text': ''.join(p['text'] for p in current_line)
            })
            current_line = [ps]
            current_len = plen
        elif current_len + plen >= TARGET_CHARS and current_line:
            # Hit target — include this phrase then flush
            current_line.append(ps)
            srt_entries.append({
                'start': current_line[0]['start'],
                'end': current_line[-1]['end'],
                'text': ''.join(p['text'] for p in current_line)
            })
            current_line = []
            current_len = 0
        else:
            current_line.append(ps)
            current_len += plen

    if current_line:
        srt_entries.append({
            'start': current_line[0]['start'],
            'end': current_line[-1]['end'],
            'text': ''.join(p['text'] for p in current_line)
        })

# -- Write SRT file --
def fmt_time(s):
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    ms = int((s % 1) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"

with open('output.srt', 'w', encoding='utf-8') as f:
    for i, e in enumerate(srt_entries, 1):
        f.write(f"{i}\n{fmt_time(e['start'])} --> {fmt_time(e['end'])}\n{e['text']}\n\n")
```

## Tuning parameters

| Parameter | Default | Effect |
|-----------|---------|--------|
| Gap threshold | 0.4s | Silence duration that splits utterances. Lower = more splits between phrases. Higher = longer unbroken runs. |
| `TARGET_CHARS` | 20 | Preferred line length. Lines are flushed once they reach this. |
| `MAX_CHARS` | 35 | Hard cap. Lines are force-flushed before exceeding this, even mid-phrase-group. |

For denser subtitles (e.g. a lecture), increase `TARGET_CHARS` to 25-30. For fast-paced dialogue, decrease to 15-18.

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
