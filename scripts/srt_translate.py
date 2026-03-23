#!/usr/bin/env python3.11
"""
Generate translation-optimized SRT subtitles from ElevenLabs Scribe JSON.
Merges Anki sentence cues into larger blocks (≤20 MeCab tokens) for translation.
"""

import sys
from pathlib import Path

from srt_common import (
    Bunsetsu, Segment, Line, Cue,
    MERGE_GAP_LIMIT,
    load_bunsetsu, bunsetsu_to_anki_cues,
    write_srt, write_html, print_cue_summary,
)

TRANSLATE_MAX_TOKENS = 20  # max MeCab tokens per translate cue


def _bunsetsu_to_speaker_lines(bunsetsu_list: list[Bunsetsu]) -> list[Line]:
    """Group bunsetsu into lines by speaker runs."""
    lines: list[Line] = []
    current: list[Bunsetsu] = [bunsetsu_list[0]]
    for b in bunsetsu_list[1:]:
        if b.speaker != current[-1].speaker:
            lines.append(Line(segments=[Segment(bunsetsu=current)]))
            current = [b]
        else:
            current.append(b)
    lines.append(Line(segments=[Segment(bunsetsu=current)]))
    return lines


def anki_to_translate_cues(anki_cues: list[Cue]) -> list[Cue]:
    """Merge adjacent Anki cues into larger translation-friendly blocks.

    Merge if:
    - No time gap ≥ MERGE_GAP_LIMIT between them
    - Combined MeCab token count ≤ TRANSLATE_MAX_TOKENS
    """
    if not anki_cues:
        return []

    def token_count(cue: Cue) -> int:
        return sum(b.morph_count for ln in cue.lines for seg in ln.segments for b in seg.bunsetsu)

    def all_bunsetsu(cue: Cue) -> list[Bunsetsu]:
        return [b for ln in cue.lines for seg in ln.segments for b in seg.bunsetsu]

    result: list[Cue] = [anki_cues[0]]

    for cue in anki_cues[1:]:
        prev = result[-1]
        gap = cue.start - prev.end
        combined_tokens = token_count(prev) + token_count(cue)

        if gap < MERGE_GAP_LIMIT and combined_tokens <= TRANSLATE_MAX_TOKENS:
            combined = all_bunsetsu(prev) + all_bunsetsu(cue)
            result[-1] = Cue(lines=_bunsetsu_to_speaker_lines(combined))
        else:
            result.append(cue)

    return result


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elevenlabs_scribe.json>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    all_bunsetsu = load_bunsetsu(json_path)

    anki_cues = bunsetsu_to_anki_cues(all_bunsetsu)
    cues = anki_to_translate_cues(anki_cues)

    # Write outputs
    json_stem = Path(json_path).stem
    parent = Path(json_path).parent

    html_path = str(parent / f"{json_stem}_translate.html")
    write_html(cues, html_path)

    srt_path = str(parent / f"{json_stem}.translate.srt")
    write_srt(cues, srt_path)

    print_cue_summary("Translate cues", cues)


if __name__ == "__main__":
    main()
