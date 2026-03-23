#!/usr/bin/env python3.11
"""
Shared code for ElevenLabs Scribe JSON → SRT conversion.
Handles JSON loading, MeCab bunsetsu segmentation, and output writing.
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


SENTENCE_ENDERS = frozenset("。！？!?")

MERGE_GAP_LIMIT = 0.4  # seconds — segments this far apart can never be merged into one line
LINE_CHAR_LIMIT = 18
CUE_LINGER = 0.5  # seconds to extend cue end, if room before next cue


@dataclass
class Bunsetsu:
    text: str
    start: float
    end: float
    speaker: str
    ends_clause: bool = False  # True if final morpheme is clause-ending
    morph_count: int = 1  # number of MeCab morphemes in this bunsetsu

    def __repr__(self):
        return f"Bunsetsu({self.text!r}, {self.start:.2f}-{self.end:.2f}, {self.speaker}, clause={self.ends_clause})"


@dataclass
class CharToken:
    """A single character with its timestamp from ElevenLabs."""
    text: str
    start: float
    end: float
    speaker: str


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


# ── JSON loading ──────────────────────────────────────────────────────────────

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
            # Clamp sentence-ending punctuation — ElevenLabs often assigns
            # long silence after a sentence to the punctuation's end time
            if text in SENTENCE_ENDERS and end - start > 0.2:
                end = start + 0.1
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


# ── Speaker / sentence splitting ──────────────────────────────────────────────

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


# ── Bunsetsu segmentation ────────────────────────────────────────────────────

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
        morph_count=len(morphs),
    )


# ── Bunsetsu loading (JSON → all_bunsetsu) ───────────────────────────────────

def load_bunsetsu(json_path: str) -> list[Bunsetsu]:
    """Load an ElevenLabs JSON file and return all bunsetsu."""
    chars = load_chars(json_path)
    speaker_runs = split_by_speaker(chars)

    tagger = Tagger()
    all_bunsetsu: list[Bunsetsu] = []

    for run in speaker_runs:
        sentences = split_by_sentence(run)
        for sentence_chars in sentences:
            bunsetsu = chars_to_bunsetsu(sentence_chars, tagger)
            all_bunsetsu.extend(bunsetsu)

    return all_bunsetsu


# ── Anki cue builder (shared by anki and translate scripts) ───────────────────

def bunsetsu_to_anki_cues(bunsetsu_list: list[Bunsetsu]) -> list[Cue]:
    """Build cues for Anki: one sentence per cue, split on 。！？ and speaker changes.

    Long cues get split into two balanced lines at a bunsetsu boundary.
    """
    if not bunsetsu_list:
        return []

    cues: list[Cue] = []
    current: list[Bunsetsu] = []

    ANKI_COMMA_TOKEN_LIMIT = 5  # split at commas when cue has this many MeCab tokens or more

    def flush():
        if not current:
            return
        line = Line(segments=[Segment(bunsetsu=list(current))])
        cues.append(Cue(lines=[line]))
        current.clear()

    def next_section_token_count(idx: int) -> int:
        """Count MeCab tokens in the section following bunsetsu_list[idx],
        up to the next comma, period, or end of sentence."""
        count = 0
        for b2 in bunsetsu_list[idx + 1:]:
            # Stop if different speaker
            if b2.speaker != bunsetsu_list[idx].speaker:
                break
            count += b2.morph_count
            if b2.text and b2.text[-1] in SENTENCE_ENDERS or b2.text[-1] == "、":
                break
        return count

    for i, b in enumerate(bunsetsu_list):
        # Speaker change → flush previous, start new
        if current and b.speaker != current[-1].speaker:
            flush()

        # Time gap ≥ MERGE_GAP_LIMIT → flush previous
        if current and b.start - current[-1].end >= MERGE_GAP_LIMIT:
            flush()

        current.append(b)

        # Sentence-ending punctuation → flush
        if b.text and b.text[-1] in SENTENCE_ENDERS:
            flush()
        # Comma → flush if current cue has enough tokens and next section isn't tiny
        elif b.text and b.text[-1] == "、":
            token_count = sum(bu.morph_count for bu in current)
            if token_count >= ANKI_COMMA_TOKEN_LIMIT:
                next_tokens = next_section_token_count(i)
                # Only skip split if BOTH: next section is tiny AND current is small
                if not (next_tokens <= 2 and token_count <= 7):
                    flush()

    flush()  # remaining bunsetsu without trailing punctuation
    return cues


# ── Output writers ────────────────────────────────────────────────────────────

def fmt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    return f"{h}:{m:02d}:{s:06.3f}"


def fmt_srt_time(seconds: float) -> str:
    m, s = divmod(seconds, 60)
    h, m = divmod(int(m), 60)
    ms = int((s % 1) * 1000)
    return f"{h:02d}:{m:02d}:{int(s):02d},{ms:03d}"


SPEAKER_COLORS = [
    "#4a9eff", "#ff6b6b", "#51cf66", "#ffd43b", "#cc5de8",
    "#ff922b", "#20c997", "#f06595",
]


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
        # Add dash prefix when multiple speakers share a cue
        if len(cue_lines) > 1:
            speakers = [ln.speaker for ln in cue.lines]
            if len(set(speakers)) > 1:
                cue_lines = [f"- {cl}" for cl in cue_lines]
        lines.append("\n".join(cue_lines))
        lines.append("")

    Path(out_path).write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out_path}", file=sys.stderr)


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
        # Check if this cue has multiple speakers
        cue_speakers = set(ln.speaker for ln in cue.lines)
        multi_speaker = len(cue_speakers) > 1 and len(cue.lines) > 1
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
            dash = '<span style="opacity:0.5">- </span>' if multi_speaker else ''
            lines_html.append(f'<span class="cue-line">{dash}{line_text}</span>')

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


def print_cue_summary(label: str, cues: list[Cue]):
    """Print a summary of cues to stdout."""
    print(f"=== {label} ===")
    for i, c in enumerate(cues, 1):
        line_texts = " / ".join(ln.text for ln in c.lines)
        print(f"Cue {i:4d}  {c.start:8.2f}-{c.end:8.2f}  {c.duration:5.1f}s  {c.char_count:3d}ch  {len(c.lines)}L  [{c.speaker}]  {line_texts}")
