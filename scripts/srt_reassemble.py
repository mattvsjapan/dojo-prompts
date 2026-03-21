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

    diff = abs(len(blocks) - expected)
    threshold = max(2, int(expected * 0.10))

    if diff > threshold:
        # Large mismatch — something went seriously wrong
        failed.append(chunk['chunk_id'])
        print(f'Chunk {chunk["chunk_id"]}: expected {expected} blocks, got {len(blocks)} (>{threshold} off — likely dropped content)', file=sys.stderr)
        all_texts.extend(blocks[:expected])
        if len(blocks) < expected:
            all_texts.extend([''] * (expected - len(blocks)))
    elif diff > 0:
        # Small mismatch — probably just merged short blocks, that's fine
        print(f'Chunk {chunk["chunk_id"]}: expected {expected} blocks, got {len(blocks)} (minor, accepted)', file=sys.stderr)
        all_texts.extend(blocks[:expected])
        if len(blocks) < expected:
            all_texts.extend([''] * (expected - len(blocks)))
    else:
        all_texts.extend(blocks)

# Write SRT
with open(output_srt_path, 'w', encoding='utf-8') as f:
    for i, meta in enumerate(metadata):
        text = all_texts[i] if i < len(all_texts) else ''
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
