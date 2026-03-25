---
name: style-guide
description: |
  Generate a speaking style guide from transcripts of a native Japanese speaker
  you want to sound like. Analyzes speech patterns, verbal tics, and tone.
allowed-tools:
  - Read
  - Write
  - Bash
  - AskUserQuestion
---

# Style Guide

Generate a speaking style guide for a native Japanese speaker you want to use as a "language parent" — someone whose speech patterns you want to internalize and replicate.

## Usage

Run `/style-guide` and the skill will walk you through the process.

## Prerequisites

This works best with ~20 hours of long-form content (livestreams, podcasts, interviews) where the person is speaking naturally — not scripted content.

## Workflow

### 1. Get transcripts of the language parent

Ask the user: **Do you already have transcripts or subtitle files for your language parent?**

- **If yes** — Ask for the file path(s) or directory and read them.
- **If no** — Ask: **Do you have video/audio files of them that need to be transcribed?**
  - **If yes** — Help transcribe them with ElevenLabs Scribe. Check if `$ELEVENLABS_API_KEY` is set; if not, ask the user to paste their key. Transcribe each file:
    ```bash
    curl -s -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
      -H "xi-api-key: $ELEVENLABS_API_KEY" \
      -F "model_id=scribe_v2" \
      -F "file=@video.mp4" \
      -F "language_code=ja" \
      -F "timestamps_granularity=word" \
      > video.json
    ```
    Extract the `text` field from each JSON file for analysis.
  - **If no** — Ask the user to provide a **YouTube channel URL or playlist URL** for their language parent. Then:
    1. List available videos with yt-dlp
    2. Select roughly 20 hours of long-form, unscripted content (prioritize livestreams, podcasts, interviews — avoid short or scripted videos)
    3. Download auto-generated Japanese subtitles:
       ```bash
       yt-dlp --write-auto-sub --sub-lang ja --skip-download --sub-format vtt -o "%(title)s.%(ext)s" "PLAYLIST_OR_CHANNEL_URL"
       ```
    4. Read the downloaded subtitle files for analysis.

### 2. Analyze

Produce a comprehensive Speaking Style Guide covering the analysis sections below.

### 3. Output

Write the guide to a file. The guide should be written in Japanese, with direct quotes from the transcripts as examples.

## Analysis sections

Write the guide in Japanese, with the analysis also in Japanese. Include specific examples pulled directly from the transcripts for every pattern identified.

**1. Sentence structure and rhythm**
- How do they construct sentences? Short and punchy, long and winding, or a mix?
- What's their pacing like? Do they think out loud, or deliver pre-formed thoughts?
- Do they interrupt themselves, backtrack, or redirect mid-sentence?

**2. Verbal tics and go-to phrases**
- What words or phrases do they reach for repeatedly?
- What are their signature expressions that make them instantly recognizable?
- How do they soften or strengthen their assertions?

**3. Sentence endings and particles**
- What sentence-final patterns do they favor?
- How do they mark certainty vs uncertainty?
- What particles or endings do they use that are distinctive?

**4. Fillers and connectors**
- What fillers do they use when thinking? How frequently?
- What transition words do they favor?
- How do they signal they're changing topics?

**5. How they explain things**
- Do they use analogies? What domains do they draw from?
- Do they use numbers and data, or stay abstract?
- Do they give examples? One or many?
- Do they build up from simple to complex, or start with the conclusion?

**6. How they argue and persuade**
- How do they handle disagreement?
- Do they concede points before making their own?
- How do they dismiss bad arguments?
- What rhetorical moves do they repeat?

**7. Tone and attitude**
- What's their overall stance? (authoritative, casual, humble, provocative, etc.)
- How do they use humor? (self-deprecating, sarcastic, deadpan, warm?)
- How do they project authority without being overbearing?

**8. Summary: How to sound like this person**
- List the top 10 most actionable patterns to internalize
- Provide a template showing the typical "flow" of how they answer a question or explain something

## Tips

- **More transcripts = better results.** 5 is okay, 10 is good, 20 is great.
- **Long-form unscripted content works best.** Livestreams, podcasts, and interviews reveal natural speech patterns. Scripted videos don't.
- **Iterate.** After the first analysis, feed in more transcripts and ask: "Based on these additional transcripts, what patterns did you miss? Update the style guide."
- **Add your own observations.** If you notice something the AI missed, tell it. "I notice they always say X when they're about to disagree — add that."
- **Compare to your own speech.** Once you have the guide, ask the AI: "Here's a transcript of me speaking. Compare my patterns to the style guide and tell me what's different."
