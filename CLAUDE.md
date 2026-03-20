# Dojo Prompts

This project contains AI skills for immersion-based Japanese learning. The skill files are located in the `dojo-prompts/` folder (the cloned repo).

## Skills

When the user asks about any of the following, read the corresponding skill file and follow its instructions:

| User says something like... | Skill file |
|---|---|
| "discover content", "find something to watch", "help me find content" | `dojo-prompts/content-discovery.md` |
| "process this video", "download and transcribe", "process content" | `dojo-prompts/process-content.md` |
| "create subtitles", "transcribe this", "make an SRT", "generate subs" | `dojo-prompts/create-srt.md` |
| "translate subtitles", "translate this SRT", "make English subs" | `dojo-prompts/translate-srt.md` |
| "make an Anki deck", "subs2srs", "create flashcards" | `dojo-prompts/subs2srs.md` |
| "style guide", "language parent", "analyze their speech" | `dojo-prompts/style-guide.md` |

When a skill is triggered, read the full skill file first, then follow its workflow step by step.

## Important

- **subs2cia**: Any step that uses subs2cia must use [mattvsjapan's fork](https://github.com/mattvsjapan/subs2cia). Install with: `pip install git+https://github.com/mattvsjapan/subs2cia.git`
- **ElevenLabs API key**: If `$ELEVENLABS_API_KEY` is not set, ask the user to paste their key before transcribing.
- **Primed Listening**: `dojo-prompts/primed-listening.lua` is an mpv script, not an AI skill. To install it, copy it to `~/.config/mpv/scripts/`.
