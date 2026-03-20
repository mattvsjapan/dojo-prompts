---
name: subs2srs
description: |
  Create subs2srs Anki decks from video files using subs2cia. Generates audio
  clips and subtitle text for flashcard-based language learning.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
---

# Subs2SRS Deck Generator

Create subs2srs Anki decks from video files using subs2cia. Generates audio clips and subtitle text for flashcard-based language learning.

## CRITICAL: Required Fork of subs2cia

This skill **requires** [mattvsjapan's fork of subs2cia](https://github.com/mattvsjapan/subs2cia). The original/upstream subs2cia will NOT work — it lacks the `context` column, `--export-header-row`, and BCP 47 locale tag support that this skill depends on.

**If a different version of subs2cia is already installed, you MUST uninstall it first:**
```bash
pip3 uninstall subs2cia
pip3 install git+https://github.com/mattvsjapan/subs2cia.git
```

Do not proceed until the correct fork is installed.

## Usage

The user provides a source directory containing video files (typically .mkv with target language audio and subtitles). The skill processes all videos and outputs a single .apkg Anki deck. The user is an English speaker. The default target language is **Japanese**, but the user may specify another language.

## Track Selection

Use ffprobe to inspect available audio and subtitle tracks. Select the tracks matching the user's target language. If there are multiple tracks for the same language, ask the user which to use.

### Default (Japanese)
- **Audio**: `jpn`, `ja`, `japanese`, `日本語`
- **Subtitles**: `jpn`, `ja`, `japanese`, `日本語`

### Other Languages
Adapt track selection to whatever language the user specifies. Use the same ffprobe approach — match by language code and title tags.

### Check Available Tracks

Before running subs2cia, inspect a sample file to identify available tracks:

```bash
ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=language,title -of csv=p=0 "$SOURCE_DIR"/*.mkv 2>/dev/null | head -5
ffprobe -v error -select_streams s -show_entries stream=index:stream_tags=language,title -of csv=p=0 "$SOURCE_DIR"/*.mkv 2>/dev/null | head -5
```

## Base Command

**Requires [mattvsjapan's fork](https://github.com/mattvsjapan/subs2cia) — see "Required Fork" section above.**

```bash
subs2cia srs -b -i "*.mkv" -ai 0 -si 0 -p 500 -N -d out_srs --export-header-row
```

### Parameters Explained

| Flag | Value | Purpose |
|------|-------|---------|
| `srs` | - | SRS subcommand (creates Anki-ready output) |
| `-b` | - | Batch mode (process multiple files) |
| `-i` | `"*.mkv"` | Input file pattern |
| `-ai` | `0` | Audio stream index (adjust based on track inspection) |
| `-si` | `0` | Subtitle stream index (adjust based on track inspection) |
| `-p` | `500` | Padding in ms around each subtitle line |
| `-N` | - | Normalize audio levels |
| `-d` | `out_srs` | Output directory name |
| `--export-header-row` | - | Include column headers in TSV output |

## Workflow

1. Get the source directory from the user
2. **Check available audio and subtitle tracks** using ffprobe
3. **Identify target language tracks** - find the indices for the target language audio and subtitles (default: Japanese)
4. **Rename source video files** to standard format: `<show_name>_XX.mkv`
5. Navigate to the source directory
6. Run subs2cia with the appropriate track indices
7. **Generate episode summaries** - for each TSV, read subtitle text and generate a translation briefing (see Episode Summary Format below), then prepend it to every row's `context` column. Use subagents to process all TSVs in parallel.
8. **Combine all TSV files** into a single `combined.tsv`
9. **Export as .apkg** - package the combined TSV and all media files into an Anki .apkg deck, saved to the source directory
10. **Clean up** - delete the `out_srs/` directory and all intermediate files, leaving only the .apkg
11. Report the output location to the user

## File Naming Convention

Rename source video files to this format before processing:
```
<show_name>_<episode>.mkv
```

This ensures output files automatically follow the naming convention:
- `<show_name>_<episode>_<start>-<end>.mp3`

Examples:
- `kiseijuu_01.mkv` → `kiseijuu_01_585-3377.mp3`
- `oshi_no_ko_s2_13.mkv` → `oshi_no_ko_s2_13_4797-8508.mp3`

Rules for `<show_name>`:
- All lowercase
- Use underscores for spaces
- Include season/year identifiers if relevant (e.g., `s2`, `2020`)

## Execution Steps

```bash
# 1. Store the source folder
SOURCE_DIR="/path/to/source"

# 2. Check available tracks
ffprobe -v error -select_streams a -show_entries stream=index:stream_tags=language,title -of csv=p=0 "$SOURCE_DIR"/*.mkv 2>/dev/null | head -5
ffprobe -v error -select_streams s -show_entries stream=index:stream_tags=language,title -of csv=p=0 "$SOURCE_DIR"/*.mkv 2>/dev/null | head -5

# 3. Based on track inspection, determine -ai and -si values
# Select tracks matching the target language (default: Japanese)

# 4. Rename source video files to standard format
# Ask user for the show name (e.g., "kiseijuu", "oshi_no_ko_s2")
SHOW_NAME="<show_name>"
cd "$SOURCE_DIR"
for f in *.mkv; do
  # Extract episode number (handles formats like "E01", "- 01", " 01.")
  num=$(echo "$f" | sed -E 's/.*[E -]([0-9]{2})[.\-].*/\1/')
  mv "$f" "${SHOW_NAME}_${num}.mkv"
done

# 5. Run subs2cia (output files will inherit the source filename)
subs2cia srs -b -i "*.mkv" -ai <audio_index> -si <subtitle_index> -p 500 -N -d out_srs --export-header-row

# 6. Generate episode summaries and prepend to context column
#    Launch subagents in parallel (one per TSV) to:
#    a) Read subtitle text from the 'text' column
#    b) Generate a translation briefing (see Episode Summary Format below)
#    c) Prepend "Episode summary: <briefing> | " to every row's context column
#    Use this Python snippet to apply the summary to a single TSV:

# EPISODE_SUMMARY should be set per-file after reading and summarizing the text
python3 -c "
import csv, sys
tsv_path = sys.argv[1]
summary = sys.argv[2]
with open(tsv_path, encoding='utf-8') as f:
    reader = list(csv.DictReader(f, delimiter='\t'))
fieldnames = reader[0].keys()
for row in reader:
    row['context'] = 'Episode summary: ' + summary + ' | ' + row['context']
with open(tsv_path, 'w', encoding='utf-8', newline='') as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter='\t')
    writer.writeheader()
    writer.writerows(reader)
" out_srs/<filename>.tsv "EPISODE_SUMMARY_HERE"

# 7. Combine all TSV files into a single file
head -1 out_srs/*.tsv | head -1 > out_srs/combined.tsv && tail -n +2 -q out_srs/*.tsv >> out_srs/combined.tsv

# 8. Export as .apkg (see APKG Export section below)
#    Output goes to $SOURCE_DIR/<show_name>.apkg
python3 -c "<see APKG Export section>" out_srs/combined.tsv out_srs/ "${SHOW_NAME}" "$SOURCE_DIR"

# 9. Clean up intermediate files
rm -rf out_srs/

# 10. Report location of output
ls -la "$SOURCE_DIR/${SHOW_NAME}.apkg"
```

## Episode Summary Format

The episode summary serves as a **translation briefing** for an LLM that will translate individual subtitle lines. It should be a mix of English and the target language, roughly 4-6 sentences, following this structure:

```
This is a line from [show name] ([name in target language]), a [format description] hosted by [host name] ([name in target language]). The guest is [guest name in target language] ([English name if applicable]), [their title/expertise/background]. They discuss [main topic in English and target language], covering [key subtopics]. Key terms that may appear: [domain-specific terms in target language with English translations]. The conversation is [register description — e.g., casual and colloquial].
```

**Example (Japanese):**
```
This is a line from ゆる言語学ラジオ (Yuru Linguistics Radio), a conversational Japanese podcast hosted by 水野太貴 (Mizuno Taiki) and 堀元見 (Horimoto Ken). They discuss linguistic misconceptions (言語学の誤解), covering topics like prescriptivism (規範主義), etymology (語源), and phonological change (音韻変化). Key terms: 言語学 (linguistics), 方言 (dialect), 音韻 (phonology). The tone is casual and humorous, with academic terminology throughout.
```

**Example (Chinese):**
```
This is a line from 博音 (Bo Yin Podcast), a conversational Mandarin Chinese podcast hosted by 博恩 (Brian Tseng). The guest is 何立安博士, a sports science PhD specializing in strength training and physical conditioning. They discuss why people plateau in weight training (重訓卡關), covering topics like training discipline (紀律), progressive overload (漸進式超負荷), and the science behind muscle adaptation. Key terms: 重訓 (weight training), 卡關 (hitting a plateau), 肌肥大 (muscle hypertrophy). The tone is casual and colloquial, with technical fitness terminology throughout.
```

**What to include:**
- Show name and format (podcast, drama, etc.) in both English and the target language
- Host and guest names in both the target language script and romanization
- Guest's title, expertise, and relevant background
- Main topic and subtopics in both English and the target language
- Domain-specific terminology (target language term + English translation)
- Language register and conversational tone

## APKG Export

After combining TSVs, package everything into an Anki .apkg file using `genanki`. Run this inline Python script (do NOT write it to a separate file):

```bash
python3 -c "
import genanki, csv, os, sys, hashlib

tsv_path = sys.argv[1]
media_dir = sys.argv[2]
deck_name = sys.argv[3]
dest_dir = sys.argv[4]

# Generate deterministic IDs from deck name so re-imports update existing cards
deck_id = int(hashlib.md5(deck_name.encode()).hexdigest()[:8], 16)
model_id = int(hashlib.md5((deck_name + '_model').encode()).hexdigest()[:8], 16)

model = genanki.Model(
    model_id,
    deck_name + ' Model',
    fields=[
        {'name': 'Audio'},
        {'name': 'Image'},
        {'name': 'Text'},
        {'name': 'Context'},
    ],
    templates=[{
        'name': 'Listening Card',
        'qfmt': '{{Audio}}',
        'afmt': '{{FrontSide}}<hr id=answer>{{Image}}<br>{{Text}}<br><br><small>{{Context}}</small>',
    }],
    css='.card { font-family: sans-serif; font-size: 24px; text-align: center; }',
)

deck = genanki.Deck(deck_id, deck_name)
media_files = []

with open(tsv_path, encoding='utf-8') as f:
    reader = csv.DictReader(f, delimiter='\t')
    for row in reader:
        audio_filename = os.path.basename(row.get('audio', row.get('Audio', '')))
        audio_path = os.path.join(media_dir, audio_filename)
        text = row.get('text', row.get('Text', ''))
        context = row.get('context', row.get('Context', ''))

        if not audio_filename or not os.path.isfile(audio_path):
            continue

        # Screenshot column contains HTML like <img src='name.jpg'>
        screenshot_html = row.get('screenshot', row.get('Screenshot', ''))
        image_filename = ''
        image_field = ''
        if 'src=' in screenshot_html:
            image_filename = screenshot_html.split(\"src='\")[1].split(\"'\")[0]
            image_path = os.path.join(media_dir, image_filename)
            if os.path.isfile(image_path):
                image_field = '<img src=\"' + image_filename + '\">'
                media_files.append(image_path)

        note = genanki.Note(
            model=model,
            fields=[
                '[sound:' + audio_filename + ']',
                image_field,
                text,
                context,
            ],
        )
        deck.add_note(note)
        media_files.append(audio_path)

output_path = os.path.join(dest_dir, deck_name + '.apkg')
package = genanki.Package(deck)
package.media_files = media_files
package.write_to_file(output_path)
print(f'Exported {len(media_files)} cards to {output_path}')
" out_srs/combined.tsv out_srs/ "${SHOW_NAME}" "$SOURCE_DIR"
```

### APKG Notes
- The model uses a **listening card** template: front = audio only, back = text + context
- Deck and model IDs are derived from the show name so re-importing updates existing cards rather than creating duplicates
- The `genanki` package must be installed (`pip3 install genanki`)
- Screenshots are exported by default by subs2cia (disable with `--no-export-screenshot`)
- The TSV column names (`audio`, `screenshot`, `text`, `context`) come from subs2cia's `--export-header-row` output

## Output

The final output is a single file in the source directory:
- **`<show_name>.apkg`** - complete Anki deck with all audio and screenshot files embedded, ready for direct import into Anki

All intermediate files (TSVs, audio clips, screenshots, the `out_srs/` directory) are deleted after the .apkg is created.

## Adjustments

- **Different video format**: Change `*.mkv` to `*.mp4` or other format
- **Different track indices**: Adjust `-ai` and `-si` based on ffprobe output
- **More/less padding**: Adjust `-p` value (default 500ms)

## Notes

- subs2cia requires text-based subtitles (SRT, ASS). Won't work with bitmap subtitles (PGS).
- If subtitles are embedded, subs2cia extracts them automatically.
- The .apkg is written directly to the source directory; all intermediate files are cleaned up automatically.
- **Do not proactively check on background jobs.** When a long-running batch process is running in the background, do not poll for progress or read output files unless the user asks. This avoids wasting context window on progress bar output.
