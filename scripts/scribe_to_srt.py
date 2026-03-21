#!/usr/bin/env python3
"""Convert ElevenLabs Scribe v2 JSON output to an SRT file using BudouX.

Usage:
    python3 scribe_to_srt.py <scribe_json> <output_srt> [--target-chars N] [--max-chars N] [--gap-threshold F]

Arguments:
    scribe_json     - Path to the Scribe v2 JSON output
    output_srt      - Path for the output SRT file

Options:
    --target-chars  - Preferred line length (default: 20)
    --max-chars     - Hard cap on line length (default: 35)
    --gap-threshold - Silence duration in seconds that splits utterances (default: 0.4)
"""

import json
import sys

import budoux

# Parse arguments
scribe_json = sys.argv[1]
output_srt = sys.argv[2]

target_chars = 20
max_chars = 35
gap_threshold = 0.4

args = sys.argv[3:]
for i, arg in enumerate(args):
    if arg == '--target-chars' and i + 1 < len(args):
        target_chars = int(args[i + 1])
    elif arg == '--max-chars' and i + 1 < len(args):
        max_chars = int(args[i + 1])
    elif arg == '--gap-threshold' and i + 1 < len(args):
        gap_threshold = float(args[i + 1])

parser = budoux.parser.load_default_japanese_parser()

with open(scribe_json, encoding='utf-8') as f:
    data = json.load(f)

# Build character list, skipping spacing tokens
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

# Group into utterances by silence gaps
utterances = []
current = [chars[0]]
for c in chars[1:]:
    gap = c['start'] - current[-1]['end']
    if gap >= gap_threshold:
        utterances.append(current)
        current = [c]
    else:
        current.append(c)
if current:
    utterances.append(current)

# Build subtitle entries
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
        if current_len + plen > max_chars and current_line:
            srt_entries.append({
                'start': current_line[0]['start'],
                'end': current_line[-1]['end'],
                'text': ''.join(p['text'] for p in current_line)
            })
            current_line = [ps]
            current_len = plen
        elif current_len + plen >= target_chars and current_line:
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


def fmt_time(s):
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    ms = int((s % 1) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


with open(output_srt, 'w', encoding='utf-8') as f:
    for i, e in enumerate(srt_entries, 1):
        f.write(f"{i}\n{fmt_time(e['start'])} --> {fmt_time(e['end'])}\n{e['text']}\n\n")

print(f'Generated {len(srt_entries)} subtitle entries to {output_srt}')
