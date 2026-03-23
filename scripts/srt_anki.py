#!/usr/bin/env python3.11
"""
Generate Anki-optimized SRT subtitles from ElevenLabs Scribe JSON.
One sentence per cue, split on 。！？ and speaker changes.
"""

import sys
from pathlib import Path

from srt_common import (
    load_bunsetsu, bunsetsu_to_anki_cues,
    write_srt, write_html, print_cue_summary,
)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <elevenlabs_scribe.json>", file=sys.stderr)
        sys.exit(1)

    json_path = sys.argv[1]
    all_bunsetsu = load_bunsetsu(json_path)

    cues = bunsetsu_to_anki_cues(all_bunsetsu)

    # Write outputs
    json_stem = Path(json_path).stem
    parent = Path(json_path).parent

    html_path = str(parent / f"{json_stem}_anki.html")
    write_html(cues, html_path)

    srt_path = str(parent / f"{json_stem}.anki.srt")
    write_srt(cues, srt_path)

    print_cue_summary("Anki cues", cues)


if __name__ == "__main__":
    main()
