---
name: find-mistakes
description: |
  Analyze a large transcript of the user speaking Japanese to identify recurring
  mistakes and unnatural patterns. Optionally generates an Anki deck of corrections.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Grep
  - Glob
  - AskUserQuestion
  - Agent
---

# Find Mistakes

Analyze a long transcript (ideally ~10 hours) of the user speaking Japanese to identify recurring mistakes and unnatural patterns in their output. This works best with a large volume of speech data — trends emerge over hours that no single conversation would reveal.

## Usage

Run `/find-mistakes` and the skill will walk you through the process.

## CRITICAL: Precision over recall

**Do not hallucinate mistakes.** When AI is told to find mistakes, it has a strong tendency to invent problems that aren't there. This is worse than missing a real mistake, because false corrections erode the user's trust in genuine feedback.

Rules:
- **Only flag something if you are confident it is genuinely unnatural.** If you're unsure, leave it out.
- **If the transcript contains natural Japanese, say so.** A native speaker's transcript fed through this process should come back with zero or near-zero corrections. If you're finding mistakes in every other sentence, you are almost certainly hallucinating.
- **Distinguish between "unusual but valid" and "actually wrong."** Some phrasings are uncommon but perfectly natural. Regional dialect, casual register, and personal style are not mistakes.
- **Require multiple occurrences for pattern-level flags.** A one-off awkward phrasing could be a speech disfluency. A recurring pattern is a real issue worth flagging.

## Workflow

### 1. Get a transcript of the user speaking

Ask the user: **Do you already have a transcript of yourself speaking Japanese?**

- **If yes** — Ask for the file path(s) and read them.
- **If no** — Ask if they have audio/video recordings of themselves speaking. If they do, help them transcribe the files using ElevenLabs Scribe:

```bash
# Check for API key
echo $ELEVENLABS_API_KEY

# Transcribe each file
curl -s -X POST "https://api.elevenlabs.io/v1/speech-to-text" \
  -H "xi-api-key: $ELEVENLABS_API_KEY" \
  -F "model_id=scribe_v2" \
  -F "file=@recording.mp4" \
  -F "language_code=ja" \
  -F "timestamps_granularity=word" \
  > recording.json
```

If `$ELEVENLABS_API_KEY` is not set, ask the user to paste their key.

Extract the `text` field from each JSON file and combine them into a single transcript for analysis.

### 2. Ask about a style guide (optional)

Ask the user: **Do you have a style guide for a language parent you want to sound like?** (Created with `/style-guide`)

- **If yes** — Ask for the file path and read it. The style guide will be used to inform corrections — instead of generic "natural Japanese," corrections will reflect how the language parent would say it.
- **If no** — That's fine. Corrections will target natural Japanese in general.

### 3. Analyze the transcript

Read through the entire transcript carefully. Identify recurring issues across these categories:

**1. Grammar mistakes**
- Incorrect verb conjugations, particle misuse, tense errors, structural errors
- Things that are straightforwardly wrong, not just stylistic

**2. Unnatural phrasing**
- Phrases that are technically grammatical but that a native speaker would never say
- Direct translations from English that don't work in Japanese
- Word choices that are correct in meaning but wrong in register or context

**3. Overused expressions**
- Words or constructions the user leans on too heavily
- Things that are fine individually but become noticeable when repeated constantly
- Crutch phrases that make the speaker sound formulaic

**4. Unnatural sentence structure**
- Word order that follows English logic instead of Japanese logic
- Sentences that are too long or too complex for spoken Japanese
- Missing or misplaced topic/subject markers

**5. Register and tone mismatches**
- Mixing formal and casual speech inappropriately
- Using written-language constructions in speech
- Politeness level inconsistencies

### 4. Write the analysis to a file

Write the analysis as a Markdown file. For **every** issue identified:

1. **Quote the user's actual phrasing** from the transcript (with multiple examples if it's a recurring pattern)
2. **Explain why it's unnatural** — briefly
3. **Provide the corrected version** in natural Japanese. If a style guide was provided, the correction should reflect how the language parent would say it.

The analysis should be written in Japanese, with explanations in Japanese. Organize by category.

Name the output file based on the user's name or a label they provide (e.g., `matt_speech_analysis.md`). Ask the user what they'd like to name it.

### 5. Offer to create an Anki deck

After writing the analysis, ask the user: **Would you like me to create an Anki deck from these corrections?**

If yes, generate an `.apkg` file with one card per correction:

- **Front**: The corrected/natural version only. Never put the user's mistake on any side of the card — the goal is to burn the correct version into memory, not reinforce the mistake.
- **Back**: Empty.

Use the `apkg_export.py` script and `genanki` to create the deck. Follow the Anki deck creation process from the `anki.md` skill for packaging.

## Tips

- **More data = better results.** 5 hours is okay, 10 is good, 20 is great. The power of this approach is volume — it reveals patterns that no single conversation would expose.
- **Record yourself naturally.** Phone calls with friends (recording only your side), voice journals, talking to yourself — the more natural the context, the more useful the analysis.
- **Pair with a style guide.** The corrections are significantly better when the AI knows how you *want* to sound, not just what "correct Japanese" is in the abstract.
- **Iterate.** After fixing the patterns identified in the first pass, record more speech and run it again. Your mistakes will evolve as you improve.
- **This doesn't cover pronunciation.** This analysis is purely about sentence composition — word choice, grammar, phrasing, structure. For pronunciation, you need a human listener or mirroring practice.
