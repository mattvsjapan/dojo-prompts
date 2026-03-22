#!/usr/bin/env python3
"""Convert ElevenLabs Scribe v2 JSON output to an SRT file using BudouX.

Usage:
    python3 scribe_to_srt.py <scribe_json> <output_srt> [--max-chars N] [--gap-threshold F]

Arguments:
    scribe_json     - Path to the Scribe v2 JSON output
    output_srt      - Path for the output SRT file

Options:
    --max-chars     - Max characters per line (default: 25)
    --gap-threshold - Silence duration in seconds that splits utterances (default: 0.4)
"""

import json
import sys

import budoux

# Parse arguments
scribe_json = sys.argv[1]
output_srt = sys.argv[2]

max_chars = 25
max_total = 35
gap_threshold = 0.4

args = sys.argv[3:]
for i, arg in enumerate(args):
    if arg == '--max-chars' and i + 1 < len(args):
        max_chars = int(args[i + 1])
    elif arg == '--max-total' and i + 1 < len(args):
        max_total = int(args[i + 1])
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
        'is_event': w['type'] == 'audio_event',
        'speaker': w.get('speaker_id')
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

# Build phrase spans from all utterances
all_phrases = []

for utt in utterances:
    # Audio events (e.g. [音楽]) stay as standalone phrases
    if len(utt) == 1 and utt[0]['is_event']:
        all_phrases.append({
            'text': utt[0]['text'],
            'start': utt[0]['start'],
            'end': utt[0]['end'],
            'speaker': utt[0]['speaker'],
            'is_event': True,
        })
        continue

    # Join characters into full text and find phrase boundaries
    full_text = ''.join(c['text'] for c in utt)
    phrases = parser.parse(full_text)

    # Build a per-character map (timestamp + speaker) for each character in
    # full_text. Handles multi-character tokens (e.g. [音楽]) correctly.
    char_info = []
    for c in utt:
        for _ in c['text']:
            char_info.append({'start': c['start'], 'end': c['end'], 'speaker': c['speaker']})

    # Map phrases back to character-level timestamps and speakers
    char_idx = 0
    for phrase in phrases:
        end_idx = char_idx + len(phrase)
        all_phrases.append({
            'text': phrase,
            'start': char_info[char_idx]['start'],
            'end': char_info[min(end_idx - 1, len(char_info) - 1)]['end'],
            'speaker': char_info[char_idx]['speaker'],
            'is_event': False,
        })
        char_idx = end_idx

# Accumulate phrases into subtitle entries with up to 2 visual lines.
# Sentence-ending punctuation (。！？) ends the current entry.
# Speaker changes end the current entry.
# Audio events get their own entry.
sentence_enders = set('。！？!?')
srt_entries = []

line1 = []
line1_len = 0
line2 = []
line2_len = 0
current_speaker = all_phrases[0]['speaker'] if all_phrases else None

def flush_entry():
    global line1, line1_len, line2, line2_len
    if not line1 and not line2:
        return
    phrases = line1 + line2

    # Determine if the entry needs two lines and where to split.
    total_len = sum(len(p['text']) for p in phrases)

    # Check if any phrase ends with a comma — force split there
    comma_split = None
    if len(phrases) >= 2:
        for k in range(len(phrases) - 1):
            if phrases[k]['text'][-1] in '、,':
                comma_split = k + 1
                break  # split at first comma

    if comma_split is not None:
        top = ''.join(p['text'] for p in phrases[:comma_split])
        bot = ''.join(p['text'] for p in phrases[comma_split:])
        text = top + '\n' + bot if bot else top
    elif len(phrases) >= 2 and total_len > max_chars:
        # No comma — balance by equal length
        best_split = 1
        best_diff = float('inf')
        running = 0
        for k in range(len(phrases)):
            running += len(phrases[k]['text'])
            remainder = total_len - running
            if running <= max_chars and remainder <= max_chars:
                diff = abs(running - remainder)
                if diff < best_diff:
                    best_diff = diff
                    best_split = k + 1
        top = ''.join(p['text'] for p in phrases[:best_split])
        bot = ''.join(p['text'] for p in phrases[best_split:])
        text = top + '\n' + bot if bot else top
    else:
        text = ''.join(p['text'] for p in phrases)

    srt_entries.append({
        'start': phrases[0]['start'],
        'end': phrases[-1]['end'],
        'text': text
    })
    line1 = []
    line1_len = 0
    line2 = []
    line2_len = 0

for ps in all_phrases:
    plen = len(ps['text'])
    speaker_changed = ps['speaker'] != current_speaker
    ends_sentence = ps['text'][-1] in sentence_enders if ps['text'] else False

    # Audio events get their own entry
    if ps.get('is_event'):
        flush_entry()
        srt_entries.append({
            'start': ps['start'],
            'end': ps['end'],
            'text': ps['text']
        })
        current_speaker = ps['speaker']
        continue

    # Speaker change — flush and start fresh
    if speaker_changed and (line1 or line2):
        flush_entry()
        current_speaker = ps['speaker']

    # Try to fit on line 1, then line 2 (same max_chars cap per line,
    # max_total cap across both lines combined)
    total_len = line1_len + line2_len
    if not line2:
        if line1_len + plen <= max_chars or not line1:
            line1.append(ps)
            line1_len += plen
        elif total_len + plen <= max_total:
            # Line 1 full but total still under cap — start line 2
            line2.append(ps)
            line2_len += plen
        else:
            # Would exceed total cap — flush and start new entry
            flush_entry()
            line1.append(ps)
            line1_len += plen
    else:
        if line2_len + plen > max_chars or total_len + plen > max_total:
            # Line 2 full or total exceeded — flush and start new entry
            flush_entry()
            line1.append(ps)
            line1_len += plen
        else:
            line2.append(ps)
            line2_len += plen

    # Sentence boundary — flush after this phrase
    if ends_sentence:
        flush_entry()
        continue

    # Comma forces a line break: wrap to line 2 if on line 1,
    # or flush the entry if already on line 2.
    ends_comma = ps['text'][-1] in '、,' if ps['text'] else False
    if ends_comma:
        if line2:
            flush_entry()
        else:
            # Force next phrase onto line 2 by marking line 1 as full
            line1_len = max_chars

    current_speaker = ps['speaker']

flush_entry()

# Merge consecutive single-line entries into two-line entries so that
# quick back-and-forth dialogue doesn't flash on and off too fast.
merged_entries = []
i = 0
while i < len(srt_entries):
    e = srt_entries[i]
    is_single = '\n' not in e['text']
    if is_single and i + 1 < len(srt_entries):
        nxt = srt_entries[i + 1]
        nxt_single = '\n' not in nxt['text']
        if nxt_single:
            merged_entries.append({
                'start': e['start'],
                'end': nxt['end'],
                'text': e['text'] + '\n' + nxt['text']
            })
            i += 2
            continue
    merged_entries.append(e)
    i += 1

srt_entries = merged_entries


def fmt_time(s):
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    ms = int((s % 1) * 1000)
    return f"{int(h):02d}:{int(m):02d}:{int(s):02d},{ms:03d}"


with open(output_srt, 'w', encoding='utf-8') as f:
    for i, e in enumerate(srt_entries, 1):
        # Strip trailing 。 from each visual line — periods are redundant
        # since sentences always end at entry boundaries.
        text = '\n'.join(line.rstrip('。') for line in e['text'].split('\n'))
        f.write(f"{i}\n{fmt_time(e['start'])} --> {fmt_time(e['end'])}\n{text}\n\n")

print(f'Generated {len(srt_entries)} subtitle entries to {output_srt}')
