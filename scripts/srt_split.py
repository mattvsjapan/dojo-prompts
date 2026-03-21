#!/usr/bin/env python3
"""Split an SRT file into chunks for parallel translation.

Usage:
    python3 srt_split.py <srt_path> [--chunk-size N]

Arguments:
    srt_path     - Path to the SRT file
    --chunk-size - Blocks per chunk (default: 100, use 50 for files under 500 blocks)

Outputs to /tmp/translate-srt/:
    metadata.json - List of {index, timecode} for every block
    chunks.json   - List of {chunk_id, start_block, end_block, num_blocks, input_path, output_path}
    chunk_N_input.txt - Chunk input files with context sections
"""

import json
import os
import re
import sys

srt_path = sys.argv[1]
chunk_size = 100

if '--chunk-size' in sys.argv:
    idx = sys.argv.index('--chunk-size')
    chunk_size = int(sys.argv[idx + 1])

output_dir = '/tmp/translate-srt'

# Read and normalize the SRT file
with open(srt_path, encoding='utf-8-sig') as f:
    content = f.read().replace('\r\n', '\n')

# Parse into blocks
raw_blocks = re.split(r'\n\n+', content.strip())
blocks = []
for block in raw_blocks:
    lines = block.strip().split('\n')
    if len(lines) < 2:
        continue
    index = lines[0].strip()
    timecode = lines[1].strip()
    text = '\n'.join(lines[2:])
    blocks.append({'index': index, 'timecode': timecode, 'text': text})

# Auto-reduce chunk size for small files
if len(blocks) < 500:
    chunk_size = min(chunk_size, 50)

# Save metadata
metadata = [{'index': b['index'], 'timecode': b['timecode']} for b in blocks]
with open(os.path.join(output_dir, 'metadata.json'), 'w', encoding='utf-8') as f:
    json.dump(metadata, f, ensure_ascii=False)

# Split into chunks and write input files
context_size = 5
chunks_info = []

for chunk_id, start in enumerate(range(0, len(blocks), chunk_size)):
    end = min(start + chunk_size, len(blocks))
    chunk_blocks = blocks[start:end]

    # Context before
    ctx_before_start = max(0, start - context_size)
    ctx_before = blocks[ctx_before_start:start]
    ctx_before_text = '\n\n'.join(b['text'] for b in ctx_before) if ctx_before else ''

    # Context after
    ctx_after_end = min(len(blocks), end + context_size)
    ctx_after = blocks[end:ctx_after_end]
    ctx_after_text = '\n\n'.join(b['text'] for b in ctx_after) if ctx_after else ''

    # Build chunk input file
    translate_text = '\n---BLOCK_SEP---\n'.join(b['text'] for b in chunk_blocks)

    input_path = os.path.join(output_dir, f'chunk_{chunk_id}_input.txt')
    output_path = os.path.join(output_dir, f'chunk_{chunk_id}_output.txt')

    with open(input_path, 'w', encoding='utf-8') as f:
        f.write('=== CONTEXT BEFORE (do NOT translate, reference only) ===\n')
        f.write(ctx_before_text + '\n')
        f.write('=== END CONTEXT BEFORE ===\n\n')
        f.write('=== TRANSLATE THE FOLLOWING ===\n')
        f.write(translate_text + '\n')
        f.write('=== END TRANSLATE ===\n\n')
        f.write('=== CONTEXT AFTER (do NOT translate, reference only) ===\n')
        f.write(ctx_after_text + '\n')
        f.write('=== END CONTEXT AFTER ===\n')

    chunks_info.append({
        'chunk_id': chunk_id,
        'start_block': start,
        'end_block': end,
        'num_blocks': end - start,
        'input_path': input_path,
        'output_path': output_path,
    })

with open(os.path.join(output_dir, 'chunks.json'), 'w', encoding='utf-8') as f:
    json.dump(chunks_info, f, ensure_ascii=False)

print(f'Split {len(blocks)} blocks into {len(chunks_info)} chunks')
