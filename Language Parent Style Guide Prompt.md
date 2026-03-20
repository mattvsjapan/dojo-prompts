## Language Parent Style Guide Prompt

Use this prompt with Claude, ChatGPT, or any capable AI to generate a speaking style guide for someone you want to sound like in your target language. This works best with 10-20 transcripts from long-form content (livestreams, podcasts, interviews) where the person is speaking naturally — not scripted content.

### How to get transcripts

1. Go to your language parent's YouTube channel
2. Use [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download auto-generated subtitles:
```
yt-dlp --write-auto-sub --sub-lang ja --skip-download --sub-format vtt "VIDEO_URL"
```
(Replace `ja` with your target language code: `ko` for Korean, `zh` for Chinese, `es` for Spanish, etc.)

3. If you can't use yt-dlp, you can also:
   - Copy auto-generated subtitles manually from YouTube (click the "..." menu → "Show transcript")
   - Use any other transcription tool on downloaded audio
   - Find existing transcripts online

### The prompt

Paste your transcripts into a conversation with the AI, then use this prompt:

---

You are a linguist specializing in natural speech analysis. I'm giving you transcripts from a native speaker I want to use as a "language parent" — someone whose speaking style I want to internalize and eventually replicate.

Analyze these transcripts and produce a comprehensive **Speaking Style Guide** covering the following areas. Write the guide in the target language, with the analysis sections also in the target language (since I'm trying to immerse myself in it). Include specific examples pulled directly from the transcripts for every pattern you identify.

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

For each section, pull **direct quotes from the transcripts** as examples. The examples should stay in the original language even if the analysis is written in another language.

---

### Tips

- **More transcripts = better results.** 5 is okay, 10 is good, 20 is great.
- **Long-form unscripted content works best.** Livestreams, podcasts, and interviews reveal natural speech patterns. Scripted videos don't.
- **Iterate.** After the first analysis, feed in more transcripts and ask: "Based on these additional transcripts, what patterns did you miss? Update the style guide."
- **Add your own observations.** If you notice something the AI missed, tell it. "I notice they always say X when they're about to disagree — add that."
- **Compare to your own speech.** Once you have the guide, ask the AI: "Here's a transcript of me speaking. Compare my patterns to the style guide and tell me what's different."

