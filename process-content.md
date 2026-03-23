---
name: process-content
description: |
  Download Japanese content from YouTube and process it into subtitles,
  condensed audio, and/or Anki decks. Orchestrates the other skills.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - Agent
  - AskUserQuestion
---

# Process Content

Download Japanese content from YouTube and process it into study materials.

## Usage

Run `/process-content` and the skill will walk you through the process.

## Workflow

### 1. Gather everything up front

Ask the user for a YouTube URL. This can be:
- A single video
- A playlist
- A full channel

Then immediately ask what outputs they want:

> I'll download this and transcribe it. What would you like me to generate?
>
> - **Japanese subtitles** — SRT with natural bunsetsu line breaks for watching
> - **English subtitles** — translated SRT for language learning reference
> - **Condensed audio** — extract just the spoken audio for passive listening
> - **Anki deck** — generate flashcards with audio clips and subtitle text
>
> You can pick any combination.

Wait for the user to answer before starting any work.

### 2. Run everything

Once you have the URL and know what they want, execute all steps in sequence without further interaction.

**Download** with yt-dlp:

```bash
# Single video
yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]" --merge-output-format mp4 -o "%(title)s.%(ext)s" "URL"

# Playlist or channel
yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]" --merge-output-format mp4 -o "%(playlist_index)03d_%(title)s.%(ext)s" "URL"
```

**Sanitize and rename** — YouTube titles often contain Unicode characters (fraction slashes ⧸, fullwidth punctuation ＆, etc.) that break tools like curl. Rename files to a standardized format **before any processing** so all outputs (SRT, condensed audio, Anki deck) share consistent filenames.

For the show name, create a **romanized version of the full title** — not a shortened or translated summary. Use the original Japanese title as the basis and romanize it:
- 「機械オンチに「API」を説明する動画」 → `kikai_onchi_ni_api_wo_setsumei_suru_douga`
- 「ゆる言語学ラジオ」 → `yuru_gengogaku_radio`
- 「ゴールドマン・サックス マネーメイト」 → `goldman_sachs_money_mate`

Rules for the show name:
- All lowercase
- Romanize Japanese fully — do not strip it down to just the English/ASCII parts
- Underscores for spaces and punctuation
- Keep English words as-is (e.g. `api`, `radio`)
- Include season/year if relevant (e.g., `_s2`, `_2024`)

```bash
SHOW_NAME="<show_name>"
# Single video
mv *.mp4 "${SHOW_NAME}_01.mp4"
# Multiple videos (playlist/channel)
i=1; for f in *.mp4; do
  num=$(printf "%02d" $i)
  mv "$f" "${SHOW_NAME}_${num}.mp4"
  i=$((i + 1))
done
```

**IMPORTANT:** This rename must happen before transcription, condensed audio, or any other processing. subs2cia and other tools name their outputs after the input file — if you process before renaming, outputs will have mismatched names.

**Transcribe** — This always runs. Use the **create-srt** skill's steps 1-2 to transcribe each video with ElevenLabs Scribe v2 and produce the Scribe JSON file. Read `create-srt.md` (in the same directory as this file). The JSON is the foundation for all other outputs.

**Japanese subtitles** (if selected) — Run `srt_watch.py` on the JSON with `-o` to name the output after the video file:
```bash
python3 dojo-prompts/scripts/srt_watch.py -o <video_stem> <json_file_path>
```

**English subtitles** (if selected) — Use the **translate-srt** skill. Read the full skill at `translate-srt.md` (in the same directory as this file) and follow its instructions, passing the Scribe JSON file. Use `-o` to name the output after the video file (not the JSON). The intermediate Japanese `.translate.srt` should be deleted after translation is complete.

**Condensed audio** (if selected) — Run subs2cia in condense mode. **You must use [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia)**, not the original — install/upgrade with `pip install --upgrade git+https://github.com/mattvsjapan/subs2cia.git`. Prefer the Scribe JSON as the timing source (more accurate speech gaps); fall back to SRT only if no JSON is available.
```bash
# With JSON (preferred)
subs2cia condense -i "video.mp4" "scribe_output.json" -t 1500 -p 200 --no-gen-subtitle -d out_condense

# Fallback: with SRT
subs2cia condense -i "video.mp4" -si <subtitle_index> --no-gen-subtitle -d out_condense
```

**Anki deck** (if selected) — Use the **anki** skill. Read the full skill at `anki.md` (in the same directory as this file) and follow its instructions.

### 3. Report results

Tell the user what was generated and where the output files are.

## Notes

- **Audio stream language tags are unreliable.** yt-dlp sometimes tags Japanese audio as "English" because YouTube's metadata is wrong. When using subs2cia with `-tl ja`, this can cause it to skip the correct audio stream. For YouTube downloads, use `-ai 0` to explicitly select the first (usually only) audio stream rather than relying on language matching.
