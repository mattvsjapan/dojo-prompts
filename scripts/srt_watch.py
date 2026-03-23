#!/usr/bin/env python3.11
"""
Generate watch-optimized SRT subtitles from ElevenLabs Scribe JSON.
Fine-grained cues with bunsetsu-aware line breaks (≤18 chars/line).
"""

import sys
from pathlib import Path

from srt_common import (
    Bunsetsu, Segment, Line, Cue,
    SENTENCE_ENDERS, MERGE_GAP_LIMIT, LINE_CHAR_LIMIT,
    load_bunsetsu, write_srt, write_html, print_cue_summary,
)

GAP_THRESHOLD = 0.1  # seconds — force a segment break when gap exceeds this
PUNCTUATION_BREAKS = frozenset("。！？!?、,")


def bunsetsu_to_segments(bunsetsu_list: list[Bunsetsu]) -> list[Segment]:
    """Split bunsetsu into maximally-split segments using speaker changes,
    time gaps, punctuation, and clause boundaries."""
    if not bunsetsu_list:
        return []

    # Step 1: split on speaker changes and time gaps
    raw: list[Segment] = []
    current: list[Bunsetsu] = [bunsetsu_list[0]]

    for b in bunsetsu_list[1:]:
        prev = current[-1]
        gap = b.start - prev.end
        speaker_change = b.speaker != prev.speaker

        if speaker_change or gap >= GAP_THRESHOLD:
            raw.append(Segment(bunsetsu=current))
            current = [b]
        else:
            current.append(b)

    raw.append(Segment(bunsetsu=current))

    # Step 2: further split at punctuation boundaries
    punct: list[Segment] = []
    for seg in raw:
        sub: list[Bunsetsu] = []
        for b in seg.bunsetsu:
            sub.append(b)
            if b.text and b.text[-1] in PUNCTUATION_BREAKS:
                punct.append(Segment(bunsetsu=sub))
                sub = []
        if sub:
            punct.append(Segment(bunsetsu=sub))

    # Step 3: further split at clause boundaries
    clause_split: list[Segment] = []
    for seg in punct:
        sub: list[Bunsetsu] = []
        for b in seg.bunsetsu:
            sub.append(b)
            if b.ends_clause:
                clause_split.append(Segment(bunsetsu=sub))
                sub = []
        if sub:
            clause_split.append(Segment(bunsetsu=sub))

    # Step 4: merge back tiny segments (< MIN_SEGMENT_CHARS) into previous.
    # Never merge into a segment that contains 。 (period stays at line end).
    # If the merged result exceeds LINE_CHAR_LIMIT, re-split at a 。 boundary
    # if available, otherwise at the most balanced bunsetsu boundary.
    MIN_SEGMENT_CHARS = 8
    segments: list[Segment] = []
    for seg in clause_split:
        prev_has_period = segments and "。" in segments[-1].text
        if (segments
                and seg.char_count < MIN_SEGMENT_CHARS
                and seg.speaker == segments[-1].speaker
                and not prev_has_period):
            combined_bunsetsu = segments[-1].bunsetsu + seg.bunsetsu
            combined_chars = segments[-1].char_count + seg.char_count
            if combined_chars <= LINE_CHAR_LIMIT:
                segments[-1] = Segment(bunsetsu=combined_bunsetsu)
            else:
                # Re-split: prefer 。 boundary, fall back to balanced split
                best_split = None
                running = 0
                for i in range(len(combined_bunsetsu) - 1):
                    running += len(combined_bunsetsu[i].text)
                    if combined_bunsetsu[i].text.endswith("。"):
                        best_split = i + 1
                        break
                if best_split is None:
                    # Fall back to most balanced split
                    total = combined_chars
                    half = total / 2
                    best_split = 1
                    best_diff = float("inf")
                    running = 0
                    for i in range(len(combined_bunsetsu) - 1):
                        running += len(combined_bunsetsu[i].text)
                        diff = abs(running - half)
                        if diff < best_diff:
                            best_diff = diff
                            best_split = i + 1
                segments[-1] = Segment(bunsetsu=combined_bunsetsu[:best_split])
                segments.append(Segment(bunsetsu=combined_bunsetsu[best_split:]))
        else:
            segments.append(seg)

    return segments


def segments_to_lines(segments: list[Segment]) -> list[Line]:
    """Merge adjacent segments into lines that fit within LINE_CHAR_LIMIT.

    Segments are merged if they share a speaker and the combined text
    fits within the limit. Sentence-ending punctuation (。！？) blocks merging.
    """
    if not segments:
        return []

    lines: list[Line] = []
    current: list[Segment] = [segments[0]]
    current_chars = segments[0].char_count

    for seg in segments[1:]:
        prev = current[-1]
        # Hard wall: don't merge if current line text contains a 。 anywhere
        current_text = "".join(s.text for s in current)
        line_has_period = "。" in current_text
        prev_ends_sentence = prev.text and prev.text[-1] in SENTENCE_ENDERS
        # Hard wall: don't merge across large time gaps
        gap = seg.start - prev.end
        too_far = gap >= MERGE_GAP_LIMIT
        same_speaker = seg.speaker == prev.speaker
        fits = current_chars + seg.char_count <= LINE_CHAR_LIMIT

        if same_speaker and fits and not prev_ends_sentence and not too_far and not line_has_period:
            current.append(seg)
            current_chars += seg.char_count
        else:
            lines.append(Line(segments=current))
            current = [seg]
            current_chars = seg.char_count

    lines.append(Line(segments=current))
    return lines


def _split_line_into_two(line: Line) -> list[Line]:
    """Split an oversized line into two balanced lines at the best bunsetsu boundary.
    Prefers splitting at a 。 boundary if one exists; falls back to most balanced split."""
    # Collect all bunsetsu across all segments
    all_bunsetsu = []
    for seg in line.segments:
        all_bunsetsu.extend(seg.bunsetsu)

    if len(all_bunsetsu) <= 1:
        # Can't split further
        return [line]

    total_chars = sum(len(b.text) for b in all_bunsetsu)
    half = total_chars / 2

    # First: try to split at a 。 boundary (pick the one closest to balanced)
    best_split = None
    best_diff = float("inf")
    running = 0
    for i in range(len(all_bunsetsu) - 1):
        running += len(all_bunsetsu[i].text)
        if all_bunsetsu[i].text.endswith("。"):
            diff = abs(running - half)
            if diff < best_diff:
                best_diff = diff
                best_split = i + 1

    # Fall back to most balanced split if no 。 boundary found
    if best_split is None:
        best_split = 1
        best_diff = float("inf")
        running = 0
        for i in range(len(all_bunsetsu) - 1):
            running += len(all_bunsetsu[i].text)
            diff = abs(running - half)
            if diff < best_diff:
                best_diff = diff
                best_split = i + 1

    line1 = Line(segments=[Segment(bunsetsu=all_bunsetsu[:best_split])])
    line2 = Line(segments=[Segment(bunsetsu=all_bunsetsu[best_split:])])
    return [line1, line2]


def _merge_lines(*lines_to_merge: Line) -> Line:
    """Flatten multiple lines into a single line with all their bunsetsu."""
    all_bunsetsu = []
    for ln in lines_to_merge:
        for seg in ln.segments:
            all_bunsetsu.extend(seg.bunsetsu)
    return Line(segments=[Segment(bunsetsu=all_bunsetsu)])


def lines_to_cues(lines: list[Line]) -> list[Cue]:
    """Pair lines into cues of 1-2 lines each.

    Lines over LINE_CHAR_LIMIT become a cue on their own, split into two lines.
    Otherwise, pair adjacent lines (same speaker, no sentence boundary) into
    two-line cues.
    """
    cues: list[Cue] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        # Oversized line → split into a two-line cue
        if line.char_count > LINE_CHAR_LIMIT:
            split = _split_line_into_two(line)
            cues.append(Cue(lines=split))
            i += 1
            continue

        # Try to pair with the next line — only if one of them needs it
        if i + 1 < len(lines):
            next_line = lines[i + 1]
            next_fits = next_line.char_count <= LINE_CHAR_LIMIT
            gap = next_line.start - line.end
            too_far = gap >= MERGE_GAP_LIMIT

            def _needs_merge(ln: Line) -> bool:
                dur = ln.end - ln.start
                if dur < 0.6:
                    return True
                if dur > 0 and ln.char_count / dur > 8:
                    return True
                return False

            needs_merge = _needs_merge(line) or _needs_merge(next_line)

            if needs_merge and next_fits and not too_far:
                same_speaker = line.speaker == next_line.speaker
                if same_speaker:
                    # Rebalance: flatten all bunsetsu and re-split at best boundary
                    combined = _merge_lines(line, next_line)
                    cues.append(Cue(lines=_split_line_into_two(combined)))
                else:
                    # Different speakers: keep lines as-is, don't rebalance
                    cues.append(Cue(lines=[line, next_line]))
                i += 2
                continue

        # Single-line cue
        cues.append(Cue(lines=[line]))
        i += 1

    # Post-pass: split single-line cues that contain a mid-text 。 into two lines
    final_cues: list[Cue] = []
    for cue in cues:
        if len(cue.lines) == 1:
            text = cue.lines[0].text
            # Find 。 that's not at the very end
            period_pos = text.find("。")
            if period_pos != -1 and period_pos < len(text) - 1:
                # Split at the 。: find the bunsetsu boundary after the period
                all_bunsetsu = []
                for seg in cue.lines[0].segments:
                    all_bunsetsu.extend(seg.bunsetsu)
                running = 0
                split_at = None
                for j, b in enumerate(all_bunsetsu):
                    running += len(b.text)
                    if running > period_pos and split_at is None:
                        split_at = j + 1
                        break
                if split_at and split_at < len(all_bunsetsu):
                    line1 = Line(segments=[Segment(bunsetsu=all_bunsetsu[:split_at])])
                    line2 = Line(segments=[Segment(bunsetsu=all_bunsetsu[split_at:])])
                    final_cues.append(Cue(lines=[line1, line2]))
                    continue
        final_cues.append(cue)

    return final_cues


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elevenlabs_scribe.json>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    all_bunsetsu = load_bunsetsu(json_path)

    # Build watch cues: bunsetsu → segments → lines → cues
    segments = bunsetsu_to_segments(all_bunsetsu)
    lines = segments_to_lines(segments)
    cues = lines_to_cues(lines)

    # Write outputs
    json_stem = Path(json_path).stem
    parent = Path(json_path).parent

    html_path = str(parent / f"{json_stem}_cues.html")
    write_html(cues, html_path)

    srt_path = str(parent / f"{json_stem}.srt")
    write_srt(cues, srt_path)

    print_cue_summary("Watch cues", cues)


if __name__ == "__main__":
    main()
