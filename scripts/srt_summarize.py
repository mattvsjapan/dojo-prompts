#!/usr/bin/env python3
"""Helper for the primed-summaries skill.

Drives a sliding-window summarization loop where Claude (in the harness)
acts as the AI for each window. Python handles SRT parsing, window state,
JSON validation, contiguity repair, and final SRT assembly — Claude only
reads window inputs and writes JSON outputs.

Modes:
    prepare <input_path>           Parse Scribe JSON or SRT, init state.
    next-window [source_language]  Build window brief (premise + recent + window).
    accept <json_path>             Validate/repair JSON, advance cursor.
    finalize <output_srt_path>     Build final summary SRT from accepted chunks.

`prepare` accepts either a Scribe JSON (preferred — split on punctuation,
speaker change, or long pauses) or an SRT (one block = one sentence).
The premise subagent writes premise.txt directly; this helper reads it.

State files in /tmp/primed-summaries/:
    blocks.json     Parsed SRT blocks: [{index, timecode, text}, ...]
    state.json      {cursor, total, accepted: [{start, end, summary}, ...]}
    premise.txt     2-4 sentence premise written by the premise subagent.
    window_brief.txt  Per-window brief consumed by the window subagent.
"""

import json
import os
import re
import sys

WINDOW_SIZE = 40
CORE_SIZE = 25
RECENT_SUMMARIES = 3
SENTENCE_ENDERS = frozenset('。！？!?')
PAUSE_THRESHOLD = 1.0  # seconds — gap between words that forces a sentence break
STATE_DIR = '/tmp/primed-summaries'
BLOCKS_PATH = os.path.join(STATE_DIR, 'blocks.json')
STATE_PATH = os.path.join(STATE_DIR, 'state.json')
PREMISE_PATH = os.path.join(STATE_DIR, 'premise.txt')
BRIEF_PATH = os.path.join(STATE_DIR, 'window_brief.txt')
FULL_TRANSCRIPT_PATH = os.path.join(STATE_DIR, 'full_transcript.txt')


def _fmt_srt_time(seconds):
    if seconds < 0:
        seconds = 0
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    ms = int(round((s - int(s)) * 1000))
    return f'{h:02d}:{int(m):02d}:{int(s):02d},{ms:03d}'


def _parse_srt_timecode(tc):
    """Parse 'HH:MM:SS,mmm --> HH:MM:SS,mmm' into (start_sec, end_sec)."""
    def to_sec(t):
        t = t.replace(',', '.')
        h, m, s = t.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    start, end = [p.strip() for p in tc.split(' --> ')]
    return to_sec(start), to_sec(end)


def parse_srt(srt_path):
    with open(srt_path, encoding='utf-8-sig') as f:
        content = f.read().replace('\r\n', '\n')
    blocks = []
    for raw in re.split(r'\n\n+', content.strip()):
        lines = raw.strip().split('\n')
        if len(lines) < 2:
            continue
        timecode = lines[1].strip()
        try:
            start_sec, end_sec = _parse_srt_timecode(timecode)
        except (ValueError, IndexError):
            continue
        blocks.append({
            'timecode': timecode,
            'start': start_sec,
            'end': end_sec,
            'text': ' '.join(ln.strip() for ln in lines[2:] if ln.strip()),
        })
    return blocks


def parse_scribe_json(json_path):
    """Parse a Scribe JSON file into sentence-level blocks.

    Splits on sentence-ending punctuation, speaker changes, and pauses
    >= PAUSE_THRESHOLD seconds. Each block has {timecode, start, end, text}.
    """
    with open(json_path, encoding='utf-8') as f:
        data = json.load(f)

    words = [w for w in data.get('words', []) if w.get('type') == 'word']
    if not words:
        return []

    blocks = []
    cur_words = []
    cur_speaker = None
    prev_end = None

    def flush():
        if not cur_words:
            return
        text = ''.join(w['text'] for w in cur_words).strip()
        if not text:
            return
        start = cur_words[0]['start']
        end = cur_words[-1]['end']
        blocks.append({
            'timecode': f'{_fmt_srt_time(start)} --> {_fmt_srt_time(end)}',
            'start': start,
            'end': end,
            'text': text,
        })

    for w in words:
        speaker = w.get('speaker_id')
        # Speaker change or long pause forces a break before this word
        if cur_words:
            speaker_changed = cur_speaker is not None and speaker != cur_speaker
            long_pause = prev_end is not None and (w['start'] - prev_end) >= PAUSE_THRESHOLD
            if speaker_changed or long_pause:
                flush()
                cur_words = []

        cur_words.append(w)
        cur_speaker = speaker
        prev_end = w['end']

        # Sentence-ending punctuation closes the sentence (punctuation stays with it)
        text = w['text']
        if text and text[-1] in SENTENCE_ENDERS:
            flush()
            cur_words = []
            cur_speaker = None

    flush()
    return blocks


def parse_input(path):
    """Parse either a Scribe JSON or an SRT into a list of blocks."""
    lower = path.lower()
    if lower.endswith('.json'):
        return parse_scribe_json(path)
    return parse_srt(path)


def load_state():
    with open(STATE_PATH, encoding='utf-8') as f:
        return json.load(f)


def save_state(state):
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def load_blocks():
    with open(BLOCKS_PATH, encoding='utf-8') as f:
        return json.load(f)


# ── prepare ──────────────────────────────────────────────────────────────────

def cmd_prepare(input_path):
    os.makedirs(STATE_DIR, exist_ok=True)
    blocks = parse_input(input_path)
    if not blocks:
        print(f'ERROR: no sentences found in {input_path}', file=sys.stderr)
        sys.exit(1)
    with open(BLOCKS_PATH, 'w', encoding='utf-8') as f:
        json.dump(blocks, f, ensure_ascii=False)
    # Also write a plain numbered transcript for the premise subagent
    with open(FULL_TRANSCRIPT_PATH, 'w', encoding='utf-8') as f:
        for i, b in enumerate(blocks, 1):
            f.write(f'{i}. {b["text"]}\n')
    state = {'cursor': 0, 'total': len(blocks), 'accepted': []}
    save_state(state)
    est_windows = max(1, (len(blocks) + CORE_SIZE - 1) // CORE_SIZE)
    print(f'Prepared {len(blocks)} sentences. Estimated ~{est_windows} windows.')
    print(f'Full transcript written to {FULL_TRANSCRIPT_PATH}')


# ── next-window ──────────────────────────────────────────────────────────────

def cmd_next_window(source_language='the source language'):
    state = load_state()
    blocks = load_blocks()
    cursor = state['cursor']
    total = state['total']
    if cursor >= total:
        print('DONE')
        return
    window_end = min(cursor + WINDOW_SIZE, total)
    is_final = (window_end == total)
    window = blocks[cursor:window_end]

    if os.path.exists(PREMISE_PATH):
        with open(PREMISE_PATH, encoding='utf-8') as f:
            premise = f.read().strip()
    else:
        premise = '(no premise available)'

    recent = state['accepted'][-RECENT_SUMMARIES:]
    if recent:
        recent_block = '\n'.join(
            f'- (sentences {c["start"]}-{c["end"]}) {c["summary"]}' for c in recent
        )
    else:
        recent_block = '(none — this is the first window)'

    numbered = '\n'.join(f'{i + 1}. {b["text"]}' for i, b in enumerate(window))
    batch_count = len(window)

    brief = f'''You are a content summarizer for {source_language} audio content.
You will receive a numbered list of {source_language} sentences from a video transcript.
Group them into coherent topical chunks and provide a concise English summary for each chunk.

=== CONTENT PREMISE (full-show context) ===
{premise}

=== RECENTLY SUMMARIZED CHUNKS (just before this window) ===
{recent_block}

=== SENTENCES TO SUMMARIZE (this window only) ===
{numbered}

Rules:
- Find natural breakpoints where the topic, scene, or speaker changes
- Each chunk should contain 3-15 sentences
- Write a concise English summary (1-3 sentences) capturing the key meaning
- Use the premise and recent summaries to keep names, ongoing topics, and tone consistent
- The summary should help a listener understand what they are about to hear
- Every sentence in this window must belong to exactly one chunk (no gaps, no overlaps)

Return ONLY valid JSON (no markdown, no commentary):
[
  {{"start": 1, "end": 5, "summary": "The speaker introduces themselves."}},
  {{"start": 6, "end": 12, "summary": "Discussion of the main topic."}}
]

start/end are 1-based sentence numbers within THIS window only (1..{batch_count}).
The first chunk must start at 1; the last chunk must end at {batch_count}.
Chunks must be contiguous (no gaps, no overlaps).
'''
    with open(BRIEF_PATH, 'w', encoding='utf-8') as f:
        f.write(brief)
    flag = 'FINAL' if is_final else 'PARTIAL'
    print(f'{flag} cursor={cursor} window_size={batch_count} core_size={CORE_SIZE} brief={BRIEF_PATH}')


# ── accept ──────────────────────────────────────────────────────────────────

def _parse_and_repair(chunks, batch_count):
    if not isinstance(chunks, list) or not chunks:
        raise ValueError('Response is not a non-empty JSON array')
    for c in chunks:
        if not isinstance(c, dict):
            raise ValueError(f'Chunk is not a dict: {c}')
        for k in ('start', 'end', 'summary'):
            if k not in c:
                raise ValueError(f"Missing key '{k}' in chunk: {c}")
        if not isinstance(c['start'], int) or not isinstance(c['end'], int):
            raise ValueError(f'start/end must be integers: {c}')
        if c['start'] > c['end']:
            raise ValueError(f'start > end: {c}')
        if not c['summary'] or not str(c['summary']).strip():
            raise ValueError(f'Empty summary: {c}')

    chunks.sort(key=lambda c: c['start'])
    if chunks[0]['start'] != 1:
        raise ValueError(f"First chunk starts at {chunks[0]['start']}, expected 1")
    for i in range(1, len(chunks)):
        if chunks[i]['start'] <= chunks[i - 1]['end']:
            raise ValueError(
                f"Overlap: chunk ending at {chunks[i-1]['end']} and "
                f"chunk starting at {chunks[i]['start']}"
            )
        if chunks[i]['start'] > chunks[i - 1]['end'] + 1:
            chunks[i - 1]['end'] = chunks[i]['start'] - 1
    if chunks[-1]['end'] > batch_count:
        raise ValueError(f"Last chunk ends at {chunks[-1]['end']}, exceeds {batch_count}")
    if chunks[-1]['end'] < batch_count:
        chunks[-1]['end'] = batch_count
    return chunks


def cmd_accept(json_path):
    state = load_state()
    cursor = state['cursor']
    total = state['total']
    window_end = min(cursor + WINDOW_SIZE, total)
    is_final = (window_end == total)
    batch_count = window_end - cursor

    with open(json_path, encoding='utf-8') as f:
        raw = f.read().strip()
    if raw.startswith('```'):
        lines = raw.split('\n')
        if lines[-1].strip() == '```':
            lines = lines[1:-1]
        else:
            lines = lines[1:]
        raw = '\n'.join(lines).strip()
    chunks = json.loads(raw)
    chunks = _parse_and_repair(chunks, batch_count)

    # Remap window-local 1-based to global 1-based
    for c in chunks:
        c['start'] += cursor
        c['end'] += cursor

    if is_final:
        accepted = chunks
    else:
        core_limit = cursor + CORE_SIZE
        accepted = []
        for c in chunks:
            if c['end'] <= core_limit:
                accepted.append(c)
            else:
                break
        if not accepted:
            # AI made one giant chunk; force-accept first to avoid infinite loop
            accepted.append(chunks[0])

    state['accepted'].extend({'start': c['start'], 'end': c['end'], 'summary': str(c['summary']).strip()} for c in accepted)
    state['cursor'] = accepted[-1]['end']
    save_state(state)
    print(f"Accepted {len(accepted)} chunks. cursor={state['cursor']}/{total}")


# ── finalize ─────────────────────────────────────────────────────────────────

def cmd_finalize(output_path):
    state = load_state()
    blocks = load_blocks()
    if state['cursor'] < state['total']:
        print(f"ERROR: not done — cursor={state['cursor']}/{state['total']}", file=sys.stderr)
        sys.exit(1)

    out_lines = []
    for seq, c in enumerate(state['accepted'], 1):
        first = blocks[c['start'] - 1]
        last = blocks[c['end'] - 1]
        start_ts = first['timecode'].split(' --> ')[0].strip()
        end_ts = last['timecode'].split(' --> ')[1].strip()
        out_lines.append(str(seq))
        out_lines.append(f'{start_ts} --> {end_ts}')
        out_lines.append(c['summary'])
        out_lines.append('')

    content = '\n'.join(out_lines)
    if not content.endswith('\n'):
        content += '\n'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f'Wrote {output_path} with {len(state["accepted"])} chunks.')


# ── main ─────────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    mode = sys.argv[1]
    if mode == 'prepare':
        cmd_prepare(sys.argv[2])
    elif mode == 'next-window':
        lang = sys.argv[2] if len(sys.argv) > 2 else 'the source language'
        cmd_next_window(lang)
    elif mode == 'accept':
        cmd_accept(sys.argv[2])
    elif mode == 'finalize':
        cmd_finalize(sys.argv[2])
    else:
        print(f'Unknown mode: {mode}', file=sys.stderr)
        sys.exit(2)
