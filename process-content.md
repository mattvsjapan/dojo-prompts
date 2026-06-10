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
> - **Primed-listening summary** — English-summary SRT (topical chunks) for primed-listening audio
>
> You can pick any combination.

Also ask **which speech-to-text provider to use — ElevenLabs Scribe v2 or Soniox** — and make sure the matching API key is set (`$ELEVENLABS_API_KEY` or `$SONIOX_API_KEY`). Ask this now so the run doesn't pause mid-way.

**If the URL is a playlist or channel, confirm the scale up front.** Check how many videos it contains:

```bash
yt-dlp --flat-playlist --print id "URL" | wc -l
```

Tell the user the count, remind them that every video gets downloaded and transcribed (a large batch is a long, usage-heavy run), and let them choose all videos or a subset. This up-front confirmation also stands in for the batch confirmation that primed-summaries would otherwise ask for mid-run — don't pause to re-ask later.

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

**Sanitize and rename** — Check if filenames need renaming **before any processing**. subs2cia and other tools name their outputs after the input file — if you process before renaming, outputs will have mismatched names.

**Skip renaming if** the filename is already ASCII-safe (no CJK characters, no Unicode punctuation, no special characters that break shell tools). For example, `goldman_sachs_money_mate_01.mp4` is fine as-is.

**Rename if** the filename contains Japanese/Chinese/Korean characters or problematic Unicode. Create a **romanized version of the full title** — not a shortened or translated summary:
- 「機械オンチに「API」を説明する動画」 → `kikai_onchi_ni_api_wo_setsumei_suru_douga`
- 「ゆる言語学ラジオ」 → `yuru_gengogaku_radio`
- 「ゴールドマン・サックス マネーメイト」 → `goldman_sachs_money_mate`

Rules for renaming:
- All lowercase
- Romanize Japanese fully — do not strip it down to just the English/ASCII parts
- Underscores for spaces and punctuation
- Keep English words as-is (e.g. `api`, `radio`)
- Include season/year if relevant (e.g., `_s2`, `_2024`)
- Only add episode numbers (`_01`, `_02`) when there are **multiple videos** in a series. A single standalone video does not need a number suffix.

**Transcribe** — This always runs. Use the **create-srt** skill's steps 1-2 to transcribe each video with the chosen speech-to-text provider (ElevenLabs Scribe v2 or Soniox) and produce the transcript JSON file. Read `create-srt.md` (in the same directory as this file). The JSON is the foundation for all other outputs.

> **Transcription is strictly sequential — one video at a time, in the main context.** Never spawn parallel subagents to transcribe multiple videos at once: speech-to-text accounts have low concurrency limits (as low as 2 concurrent jobs on some plans), so parallel uploads fail with mid-upload connection resets and burn usage on retries. Parallelism (e.g. primed-summaries episode subagents) is only allowed for steps that run **after** every transcript JSON exists on disk — and even then, never more than 3 concurrent subagents.

> Because this step runs without further interaction, **ask which provider to use (and confirm the matching API key is set) back in step 1**, together with the question about which outputs they want — don't pause mid-run to ask.

**Japanese subtitles** (if selected) — Run `srt_watch.py` on the JSON with `-o` to name the output after the video file:
```bash
python3 dojo-prompts/scripts/srt_watch.py -o <video_stem> <json_file_path>
```

**English subtitles** (if selected) — Use the **translate-srt** skill. Read the full skill at `translate-srt.md` (in the same directory as this file) and follow its instructions, passing the transcript JSON file. Use `-o` to name the output after the video file (not the JSON). The intermediate Japanese `.translate.srt` should be deleted after translation is complete.

**Condensed audio** (if selected) — Use the **condensed-audio** skill. Read the full skill at `condensed-audio.md` (in the same directory as this file) and follow its instructions.

**Anki deck** (if selected) — Use the **anki** skill. Read the full skill at `anki.md` (in the same directory as this file) and follow its instructions.

**Primed-listening summary** (if selected) — Use the **primed-summaries** skill. Read the full skill at `primed-summaries.md` (in the same directory as this file) and follow its instructions, passing the transcript JSON file.

### 3. Report results

Tell the user what was generated and where the output files are.

## Notes

- **Audio stream language tags are unreliable.** yt-dlp sometimes tags Japanese audio as "English" because YouTube's metadata is wrong. When using subs2cia with `-tl ja`, this can cause it to skip the correct audio stream. For YouTube downloads, use `-ai 0` to explicitly select the first (usually only) audio stream rather than relying on language matching.
