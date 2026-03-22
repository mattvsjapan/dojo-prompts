#!/usr/bin/env python3.11
"""
Convert ElevenLabs Scribe JSON (character-level timestamps) to SRT,
using MeCab/UniDic bunsetsu segmentation for natural Japanese line breaks.
"""

import json
import sys
from dataclasses import dataclass
from pathlib import Path
from fugashi import Tagger

# POS1 categories that start a new bunsetsu
BUNSETSU_STARTERS = frozenset([
    "名詞",    # noun
    "動詞",    # verb
    "形容詞",  # i-adjective
    "形状詞",  # na-adjective
    "副詞",    # adverb
    "連体詞",  # pre-noun adjectival
    "接続詞",  # conjunction
    "感動詞",  # interjection
    "代名詞",  # pronoun
])

# POS1 categories that attach to the preceding bunsetsu
# (助詞, 助動詞, 接尾辞, 記号, 補助記号, 空白)
# Anything not in BUNSETSU_STARTERS attaches by default.

# 接頭辞 starts a group but merges with the following content word,
# so it doesn't start a *separate* bunsetsu — it starts one that
# continues until the next starter after the content word.


# Clause-ending patterns: the last morpheme in a bunsetsu signals a clause boundary.
# We check (pos1, pos2) of the final morpheme.
# 助動詞 endings (た、だ、ます、です、etc.) and clause-linking 助詞.
CLAUSE_END_PARTICLES = frozenset([
    "て", "で",       # te-form
    "ば",             # conditional
    "から", "ので",   # reason
    "けど", "けれど", "けれども", "が",  # concessive
    "と", "たら", "なら",  # conditional
    "し",             # listing reasons
    "のに",           # despite
    "ながら",         # while
    "ても", "でも",   # even if
])


@dataclass
class Bunsetsu:
    text: str
    start: float
    end: float
    speaker: str
    ends_clause: bool = False  # True if final morpheme is clause-ending

    def __repr__(self):
        return f"Bunsetsu({self.text!r}, {self.start:.2f}-{self.end:.2f}, {self.speaker}, clause={self.ends_clause})"


@dataclass
class CharToken:
    """A single character with its timestamp from ElevenLabs."""
    text: str
    start: float
    end: float
    speaker: str


def load_chars(json_path: str) -> list[CharToken]:
    """Load character tokens from ElevenLabs JSON, filtering non-word items.

    Multi-character tokens (e.g. '。API') are split into individual characters
    with linearly interpolated timestamps.
    """
    with open(json_path) as f:
        data = json.load(f)

    chars = []
    for w in data["words"]:
        if w["type"] != "word":
            continue

        text = w["text"]
        start = w["start"]
        end = w["end"]
        speaker = w["speaker_id"]

        if len(text) == 1:
            chars.append(CharToken(text=text, start=start, end=end, speaker=speaker))
        else:
            # Split multi-char tokens, interpolate timing
            n = len(text)
            duration = end - start
            for i, ch in enumerate(text):
                ch_start = start + (duration * i / n)
                ch_end = start + (duration * (i + 1) / n)
                chars.append(CharToken(text=ch, start=ch_start, end=ch_end, speaker=speaker))

    return chars


SENTENCE_ENDERS = frozenset("。！？!?")


def split_by_speaker(chars: list[CharToken]) -> list[list[CharToken]]:
    """Split character stream into runs of the same speaker."""
    if not chars:
        return []

    runs = []
    current_run = [chars[0]]

    for ch in chars[1:]:
        if ch.speaker != current_run[-1].speaker:
            runs.append(current_run)
            current_run = [ch]
        else:
            current_run.append(ch)

    runs.append(current_run)
    return runs


def split_by_sentence(chars: list[CharToken]) -> list[list[CharToken]]:
    """Split a character run on sentence-ending punctuation.

    The punctuation character stays with the sentence it ends (attached left).
    """
    if not chars:
        return []

    sentences = []
    current: list[CharToken] = []

    for ch in chars:
        current.append(ch)
        if ch.text in SENTENCE_ENDERS:
            sentences.append(current)
            current = []

    if current:
        sentences.append(current)

    return sentences


def chars_to_bunsetsu(chars: list[CharToken], tagger: Tagger) -> list[Bunsetsu]:
    """
    Concatenate chars into text, run MeCab, then group morphemes into
    bunsetsu while mapping back to character-level timestamps.
    """
    if not chars:
        return []

    # Build the plain text and a char-index → CharToken mapping
    text = "".join(ch.text for ch in chars)
    speaker = chars[0].speaker

    # Run MeCab
    morphemes = tagger(text)

    # Walk through morphemes and map each back to character positions
    char_offset = 0
    bunsetsu_list: list[Bunsetsu] = []
    current_chars: list[CharToken] = []
    current_morphs: list = []  # store (surface, pos1, pos2) tuples
    prefix_active = False  # tracks 接頭辞 waiting for content word

    def flush():
        if current_chars:
            bunsetsu_list.append(_make_bunsetsu(current_chars, current_morphs, speaker))

    for morph in morphemes:
        surface = morph.surface
        pos1 = morph.feature.pos1
        pos2 = morph.feature.pos2 or ""

        morph_len = len(surface)
        morph_chars = chars[char_offset:char_offset + morph_len]
        char_offset += morph_len

        is_starter = pos1 in BUNSETSU_STARTERS
        is_prefix = pos1 == "接頭辞"

        if is_prefix:
            flush()
            current_chars = list(morph_chars)
            current_morphs = [(surface, pos1, pos2)]
            prefix_active = True

        elif is_starter:
            if prefix_active:
                current_chars.extend(morph_chars)
                current_morphs.append((surface, pos1, pos2))
                prefix_active = False
            else:
                flush()
                current_chars = list(morph_chars)
                current_morphs = [(surface, pos1, pos2)]

        else:
            if not current_chars:
                current_chars = list(morph_chars)
                current_morphs = [(surface, pos1, pos2)]
            else:
                current_chars.extend(morph_chars)
                current_morphs.append((surface, pos1, pos2))
            prefix_active = False

    flush()
    return bunsetsu_list


def _make_bunsetsu(chars: list[CharToken], morphs: list[tuple], speaker: str) -> Bunsetsu:
    text = "".join(ch.text for ch in chars)

    # Determine if this bunsetsu ends a clause
    ends_clause = False
    if morphs:
        last_surface, last_pos1, last_pos2 = morphs[-1]
        # 助動詞 at the end (た、だ、ます、です、etc.)
        if last_pos1 == "助動詞":
            ends_clause = True
        # Clause-linking 助詞
        elif last_pos1 == "助詞" and last_surface in CLAUSE_END_PARTICLES:
            ends_clause = True
        # Also check second-to-last if last is punctuation
        if len(morphs) >= 2 and last_pos1 in ("補助記号", "記号"):
            prev_surface, prev_pos1, prev_pos2 = morphs[-2]
            if prev_pos1 == "助動詞":
                ends_clause = True
            elif prev_pos1 == "助詞" and prev_surface in CLAUSE_END_PARTICLES:
                ends_clause = True

    return Bunsetsu(
        text=text,
        start=chars[0].start,
        end=chars[-1].end,
        speaker=speaker,
        ends_clause=ends_clause,
    )


@dataclass
class Segment:
    """A maximally-split unit: one or more bunsetsu between hard boundaries."""
    bunsetsu: list[Bunsetsu]

    @property
    def text(self) -> str:
        return "".join(b.text for b in self.bunsetsu)

    @property
    def start(self) -> float:
        return self.bunsetsu[0].start

    @property
    def end(self) -> float:
        return self.bunsetsu[-1].end

    @property
    def speaker(self) -> str:
        return self.bunsetsu[0].speaker

    @property
    def char_count(self) -> int:
        return sum(len(b.text) for b in self.bunsetsu)


@dataclass
class Line:
    """A single subtitle line: one or more segments merged to fit a char limit."""
    segments: list[Segment]

    @property
    def text(self) -> str:
        return "".join(s.text for s in self.segments)

    @property
    def start(self) -> float:
        return self.segments[0].start

    @property
    def end(self) -> float:
        return self.segments[-1].end

    @property
    def speaker(self) -> str:
        return self.segments[0].speaker

    @property
    def char_count(self) -> int:
        return sum(s.char_count for s in self.segments)


@dataclass
class Cue:
    """A subtitle cue: one or two lines displayed together."""
    lines: list[Line]

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    @property
    def start(self) -> float:
        return self.lines[0].start

    @property
    def end(self) -> float:
        return self.lines[-1].end

    @property
    def speaker(self) -> str:
        return self.lines[0].speaker

    @property
    def char_count(self) -> int:
        return sum(ln.char_count for ln in self.lines)

    @property
    def duration(self) -> float:
        return self.end - self.start


GAP_THRESHOLD = 0.1  # seconds — force a segment break when gap exceeds this
MERGE_GAP_LIMIT = 0.4  # seconds — segments this far apart can never be merged into one line


PUNCTUATION_BREAKS = frozenset("。！？!?、,")


LINE_CHAR_LIMIT = 18


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


def fmt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:06.3f}"


def fmt_srt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


CUE_LINGER = 0.5  # seconds to extend cue end, if room before next cue


def write_srt(cues: list[Cue], out_path: str):
    """Write an SRT subtitle file."""
    lines = []
    for i, cue in enumerate(cues, 1):
        # Extend end time by CUE_LINGER, but don't overlap next cue
        end = cue.end + CUE_LINGER
        if i < len(cues):
            next_start = cues[i].start  # cues[i] is next since enumerate starts at 1
            end = min(end, next_start)

        lines.append(str(i))
        lines.append(f"{fmt_srt_time(cue.start)} --> {fmt_srt_time(end)}")
        # Strip 。 only at the end of each line
        cue_lines = [ln.text.rstrip("。") for ln in cue.lines]
        lines.append("\n".join(cue_lines))
        lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


SPEAKER_COLORS = [
    "#4a9eff", "#ff6b6b", "#51cf66", "#ffd43b", "#cc5de8",
    "#ff922b", "#20c997", "#f06595",
]


def write_html(cues: list[Cue], out_path: str):
    """Write an HTML file that visualizes cues with line breaks shown."""
    speakers_seen: dict[str, int] = {}
    for c in cues:
        if c.speaker not in speakers_seen:
            speakers_seen[c.speaker] = len(speakers_seen)

    html = []
    html.append("""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>Cue Visualization</title>
<style>
  body { font-family: "Hiragino Sans", "Noto Sans JP", sans-serif; font-size: 18px;
         background: #1a1a2e; color: #eee; padding: 2em; line-height: 1.6; }
  .cue { background: #16213e; border-radius: 6px; padding: 8px 12px; margin: 6px 0;
         display: flex; align-items: baseline; gap: 12px; }
  .cue-meta { font-size: 12px; font-family: monospace; opacity: 0.5; white-space: nowrap;
              min-width: 200px; }
  .cue-text { font-size: 20px; }
  .cue-line { display: block; }
  .bunsetsu { border-bottom: 2px solid; padding-bottom: 1px; margin-right: 1px;
              cursor: default; }
  .separator { color: #555; margin: 0 1px; font-size: 14px; }
  .speaker-group { margin: 1.2em 0 0.3em 0; }
  .speaker-label { font-size: 13px; font-weight: bold; opacity: 0.7; }
  .gap-break { display: block; margin: 4px 0; border-top: 2px dashed #e74c3c55;
               padding-top: 4px; }
</style>
</head>
<body>
<h2>Cue Visualization <span style="font-size:14px; opacity:0.4;">(line limit: """ + f"{LINE_CHAR_LIMIT}ch" + """)</span></h2>
<p style="font-size:13px; opacity:0.5;">Each row = one cue (1-2 lines). Bunsetsu underlined. Hover for timing.</p>
<div>""")

    prev_speaker = None
    prev_cue = None
    for cue in cues:
        color = SPEAKER_COLORS[speakers_seen[cue.speaker] % len(SPEAKER_COLORS)]

        if cue.speaker != prev_speaker:
            html.append(f'<div class="speaker-group"><span class="speaker-label" style="color:{color}">{cue.speaker}</span></div>')
            prev_speaker = cue.speaker
        elif prev_cue is not None:
            gap = cue.start - prev_cue.end
            if gap >= MERGE_GAP_LIMIT:
                html.append(f'<div class="gap-break" title="gap: {gap:.2f}s"></div>')

        time_str = f"{fmt_time(cue.start)} → {fmt_time(cue.end)}"
        meta = f"{time_str}  {cue.duration:.1f}s  {cue.char_count}ch  {len(cue.lines)}L"

        lines_html = []
        for ln in cue.lines:
            ln_color = SPEAKER_COLORS[speakers_seen[ln.speaker] % len(SPEAKER_COLORS)]
            bunsetsu_spans = []
            for seg in ln.segments:
                for b in seg.bunsetsu:
                    b_time = f"{fmt_time(b.start)} → {fmt_time(b.end)}"
                    escaped = b.text.replace("&", "&amp;").replace("<", "&lt;")
                    bunsetsu_spans.append(
                        f'<span class="bunsetsu" style="border-color:{ln_color}" '
                        f'title="{b_time}">{escaped}</span>'
                    )
            line_text = '<span class="separator">|</span>'.join(bunsetsu_spans)
            lines_html.append(f'<span class="cue-line">{line_text}</span>')

        text_html = "".join(lines_html)

        html.append(
            f'<div class="cue">'
            f'<span class="cue-meta">{meta}</span>'
            f'<span class="cue-text">{text_html}</span>'
            f'</div>'
        )
        prev_cue = cue

    html.append("</div></body></html>")
    Path(out_path).write_text("\n".join(html), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elevenlabs_scribe.json>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    chars = load_chars(json_path)
    speaker_runs = split_by_speaker(chars)

    tagger = Tagger()
    all_bunsetsu: list[Bunsetsu] = []

    for run in speaker_runs:
        # Split each speaker run into sentences before feeding to MeCab
        sentences = split_by_sentence(run)
        for sentence_chars in sentences:
            bunsetsu = chars_to_bunsetsu(sentence_chars, tagger)
            all_bunsetsu.extend(bunsetsu)

    # Build cues: bunsetsu → segments → lines → cues
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

    # Print cue summary to stdout
    for i, c in enumerate(cues, 1):
        line_texts = " / ".join(ln.text for ln in c.lines)
        print(f"Cue {i:4d}  {c.start:8.2f}-{c.end:8.2f}  {c.duration:5.1f}s  {c.char_count:3d}ch  {len(c.lines)}L  [{c.speaker}]  {line_texts}")


if __name__ == "__main__":
    main()
