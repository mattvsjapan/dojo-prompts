#!/usr/bin/env python3
"""Reassemble translated SRT chunks into a final SRT file.

Usage:
    python3 srt_reassemble.py <output_srt_path>

Reads from /tmp/translate-srt/:
    metadata.json - Block indices and timecodes
    chunks.json   - Chunk info including output file paths

Small block count mismatches (≤10%) are tolerated — the LLM sometimes merges
short blocks and that's fine. Large mismatches (>10%) or missing chunk files
cause a failure exit (code 1) so the caller can retry.
"""

import json
import os
import sys

output_srt_path = sys.argv[1]
work_dir = '/tmp/translate-srt'

with open(os.path.join(work_dir, 'metadata.json'), encoding='utf-8') as f:
    metadata = json.load(f)

with open(os.path.join(work_dir, 'chunks.json'), encoding='utf-8') as f:
    chunks = json.load(f)

all_texts = []
missing = []
failed = []

for chunk in chunks:
    output_path = chunk['output_path']
    expected = chunk['num_blocks']

    if not os.path.isfile(output_path):
        missing.append(chunk['chunk_id'])
        all_texts.extend([''] * expected)
        continue

    with open(output_path, encoding='utf-8') as f:
        content = f.read().strip()

    blocks = content.split('---BLOCK_SEP---')
    blocks = [b.strip() for b in blocks]

    if len(blocks) != expected:
        failed.append(chunk['chunk_id'])
        print(f'Chunk {chunk["chunk_id"]}: expected {expected} blocks, got {len(blocks)} — needs retry', file=sys.stderr)
        # Pad to keep indices aligned for any chunks that did succeed
        all_texts.extend(blocks[:expected])
        if len(blocks) < expected:
            all_texts.extend([''] * (expected - len(blocks)))
    else:
        all_texts.extend(blocks)

def balance_lines(text):
    """Split text into two balanced lines at a word boundary."""
    words = text.split(' ')
    if len(words) < 2:
        return text
    best_split = 1
    best_diff = float('inf')
    for k in range(1, len(words)):
        top = ' '.join(words[:k])
        bot = ' '.join(words[k:])
        diff = abs(len(top) - len(bot))
        if diff < best_diff:
            best_diff = diff
            best_split = k
    return ' '.join(words[:best_split]) + '\n' + ' '.join(words[best_split:])

# Read original SRT to check which blocks were two-line
original_srt_path = os.path.join(work_dir, 'original_line_counts.json')
original_two_line = set()
if os.path.isfile(original_srt_path):
    with open(original_srt_path, encoding='utf-8') as f:
        original_two_line = set(json.load(f))

# Write SRT
with open(output_srt_path, 'w', encoding='utf-8') as f:
    for i, meta in enumerate(metadata):
        text = all_texts[i] if i < len(all_texts) else ''
        # Split on em dash — this indicates a speaker change mid-line
        if ' — ' in text:
            text = text.replace(' — ', '\n')
        # Balance into two lines if the original Japanese block was two lines
        elif i in original_two_line and '\n' not in text:
            text = balance_lines(text)
        f.write(f'{meta["index"]}\n{meta["timecode"]}\n{text}\n\n')

errors = missing + failed
if errors:
    if missing:
        print(f'MISSING CHUNKS: {",".join(str(c) for c in missing)}', file=sys.stderr)
    if failed:
        print(f'MISMATCHED CHUNKS: {",".join(str(c) for c in failed)}', file=sys.stderr)
    sys.exit(1)
else:
    print(f'Successfully reassembled {len(metadata)} blocks to {output_srt_path}')
    sys.exit(0)
