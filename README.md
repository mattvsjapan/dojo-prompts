# Immersion Dojo — AI Skills for Japanese Learners

AI-powered skills for immersion-based Japanese learning. Each skill is a structured workflow that an AI coding agent walks you through — find content, create subtitles, study with Anki, and build a speaking style modeled on a native speaker you admire.

These skills are designed for [Claude Code](https://docs.anthropic.com/en/docs/claude-code) but can be adapted for Codex or other AI coding agents.

## The workflow

1. **[Content Discovery](content-discovery.md)** — Find Japanese content that matches your personal taste, not generic "top 10 for learners" lists
2. **Download** — Use [yt-dlp](https://github.com/yt-dlp/yt-dlp) to download the content
3. **[Create SRT](create-srt.md)** — Generate Japanese subtitles from video using ElevenLabs Scribe and BudouX
4. **[Translate SRT](translate-srt.md)** — Translate the Japanese subtitles into English for reference
5. **[Primed Listening](primed-listening.lua)** — mpv script that pauses after each subtitle line, giving you time to read before listening
6. **Condensed Audio** — Use [subs2cia](https://github.com/mattvsjapan/subs2cia) to extract just the spoken audio for passive listening
7. **[Subs2SRS](subs2srs.md)** — Generate Anki decks from your content with audio clips and subtitle text
8. **[Style Guide](style-guide.md)** — Analyze a native speaker's transcripts to create a speaking style guide you can internalize

## Installation

Open your study folder in Claude Code and paste:

> Copy the skills from https://github.com/mattvsjapan/dojo-prompts into this project's .claude/skills/ directory

Claude Code will clone the repo and copy everything into place. After that, you can use `/content-discovery`, `/create-srt`, `/translate-srt`, `/subs2srs`, and `/style-guide` from that folder.

### Primed Listening (mpv script)

The primed listening script needs to be installed separately into mpv:

```bash
cp primed-listening.lua ~/.config/mpv/scripts/
```

Press `n` in mpv to toggle it on/off. See the file header for all keybindings.

### As standalone prompts

All skills also work as plain prompts — paste the contents into any AI chat (Claude, ChatGPT, etc.) and follow the instructions.

## Requirements

- [yt-dlp](https://github.com/yt-dlp/yt-dlp) for downloading content
- [ElevenLabs API key](https://elevenlabs.io/) with Scribe access (for create-srt)
- [mpv](https://mpv.io/) media player (for primed listening)
- Python packages: `budoux`, `genanki`
- [subs2cia](https://github.com/mattvsjapan/subs2cia) — **you must use this fork**, not the original. It adds context column support and other features used by the subs2srs and condensed audio steps. Install with:
  ```bash
  pip install git+https://github.com/mattvsjapan/subs2cia.git
  ```

## Part of Immersion Dojo

These skills are part of the **Immersion Dojo** course on Skool. They're open source so the community can use, improve, and adapt them.
