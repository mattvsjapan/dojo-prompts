#!/usr/bin/env python3
"""Reassemble translated SRT chunks into a final SRT file.

Usage:
    python3 srt_reassemble.py <output_srt_path>

Reads from /tmp/translate-srt/:
    metadata.json - Block indices and timecodes
    chunks.json   - Chunk info including output file paths

Returns exit code 0 if all chunks validated, 1 if there were mismatches.
Prints mismatched chunk IDs to stderr for retry handling.
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
mismatched = []

for chunk in chunks:
    output_path = chunk['output_path']
    expected = chunk['num_blocks']

    if not os.path.isfile(output_path):
        mismatched.append(chunk['chunk_id'])
        all_texts.extend([''] * expected)
        continue

    with open(output_path, encoding='utf-8') as f:
        content = f.read().strip()

    blocks = content.split('---BLOCK_SEP---')
    blocks = [b.strip() for b in blocks]

    if len(blocks) != expected:
        mismatched.append(chunk['chunk_id'])
        print(f'Chunk {chunk["chunk_id"]}: expected {expected} blocks, got {len(blocks)}', file=sys.stderr)
        # Still include what we have for now — caller decides whether to retry
        all_texts.extend(blocks[:expected])
        # Pad if short
        if len(blocks) < expected:
            all_texts.extend([''] * (expected - len(blocks)))
    else:
        all_texts.extend(blocks)

# Write SRT
with open(output_srt_path, 'w', encoding='utf-8') as f:
    for i, meta in enumerate(metadata):
        text = all_texts[i] if i < len(all_texts) else ''
        f.write(f'{meta["index"]}\n{meta["timecode"]}\n{text}\n\n')

if mismatched:
    print(f'MISMATCHED CHUNKS: {",".join(str(c) for c in mismatched)}', file=sys.stderr)
    sys.exit(1)
else:
    print(f'Successfully reassembled {len(metadata)} blocks to {output_srt_path}')
    sys.exit(0)
