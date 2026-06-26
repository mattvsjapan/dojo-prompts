#!/usr/bin/env python3
"""Transcribe a video/audio file to canonical transcript JSON.

Supports two speech-to-text providers, selected with --provider:
  elevenlabs   ElevenLabs Scribe v2 (single synchronous POST)
  soniox       Soniox stt-async-v5 (upload -> create -> poll -> fetch)

Both providers write the SAME canonical JSON shape (the ElevenLabs Scribe
shape), so every downstream tool -- srt_watch.py, srt_translate.py,
srt_summarize.py, and the mattvsjapan/subs2cia fork -- consumes the output
unchanged regardless of which provider produced it:

    { "language_code": "jpn",
      "text": "<full transcript>",
      "words": [ { "text": "世", "start": 13.72, "end": 13.86,
                   "type": "word", "speaker_id": "speaker_1",
                   "logprob": -0.018 }, ... ] }

`type` is one of "word", "spacing" (whitespace, skipped downstream), or
"audio_event" (music/laughter/etc).

Usage:
    python3 scripts/transcribe.py --provider soniox -o my_video --language ja my_video.mp4

The API key is read from the environment:
    ELEVENLABS_API_KEY   for --provider elevenlabs
    SONIOX_API_KEY       for --provider soniox

If the input has a video stream, its audio is demuxed to a temp file with
ffmpeg and only that is uploaded -- a few MB instead of the whole video, which
also makes a mid-upload connection reset far less likely on the low-concurrency
STT accounts this targets. Falls back to uploading the original file when
ffmpeg/ffprobe are missing or extraction fails. Needs ffmpeg + ffprobe on PATH.
"""
import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time

import requests


# ── Retry helper ──────────────────────────────────────────────────────────────

RETRY_STATUSES = {429, 500, 502, 503, 504}

# ChunkedEncodingError/ContentDecodingError cover the connection dying while
# the response body is being received (they are RequestException subclasses,
# not ConnectionError ones).
RETRY_EXCEPTIONS = (requests.ConnectionError, requests.Timeout,
                    requests.exceptions.ChunkedEncodingError,
                    requests.exceptions.ContentDecodingError)


def request_with_retries(make_request, what: str, attempts: int = 4,
                         retry_read_timeouts: bool = True,
                         read_timeout_advice: str = ""):
    """Run make_request() (a zero-arg callable returning a Response), retrying
    with exponential backoff on transient failures: connection errors, timeouts,
    mid-body disconnects, and 429/5xx statuses.

    STT accounts have low concurrency limits (as low as 2 concurrent jobs on
    some plans), and an over-limit upload surfaces as a connection reset
    mid-POST rather than a clean 429 -- so the exception path matters as much
    as the status-code path.

    retry_read_timeouts=False is for paid, non-idempotent requests: a read
    timeout means the request was fully sent and the provider may have accepted
    (and billed) the job, so blindly re-sending risks paying twice and occupying
    a second concurrency slot. Connect timeouts and connection resets are always
    retried -- nothing was processed.

    read_timeout_advice is appended to that exit message. This script is driven
    by an AI agent, not a human, so the advice must be directly executable by
    the agent (an exact command to run, or a plain-language question to put to
    the user) -- never "check your account".
    """
    delay = 10
    for attempt in range(1, attempts + 1):
        try:
            resp = make_request()
        except RETRY_EXCEPTIONS as e:
            if (isinstance(e, requests.exceptions.ReadTimeout)
                    and not retry_read_timeouts):
                sys.exit(f"{what}: the request was fully sent but no response "
                         f"arrived within the timeout, so the provider may have "
                         f"accepted (and billed) it anyway. Not retrying "
                         f"automatically. {read_timeout_advice} ({e})")
            failure = f"{type(e).__name__}: {e}"
        else:
            if resp.status_code not in RETRY_STATUSES:
                return resp
            failure = f"HTTP {resp.status_code}: {resp.text[:500]}"
        if attempt == attempts:
            sys.exit(f"{what} failed after {attempts} attempts: {failure}")
        print(f"{what}: {failure} -- retrying in {delay}s "
              f"(attempt {attempt}/{attempts})", file=sys.stderr)
        time.sleep(delay)
        delay *= 2


# ── ElevenLabs Scribe ─────────────────────────────────────────────────────────

def transcribe_elevenlabs(audio_path: str, language: str) -> dict:
    """ElevenLabs Scribe v2. Returns the response JSON, which is already in the
    canonical shape, so it is saved verbatim."""
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key:
        sys.exit("ELEVENLABS_API_KEY is not set.")

    def post():
        # Reopen per attempt: a failed upload leaves the file handle mid-stream.
        with open(audio_path, "rb") as f:
            return requests.post(
                "https://api.elevenlabs.io/v1/speech-to-text",
                headers={"xi-api-key": key},
                data={
                    "model_id": "scribe_v2",
                    "language_code": language,
                    "timestamps_granularity": "word",
                    "diarize": "true",
                },
                files={"file": f},
                timeout=3600,
            )

    resp = request_with_retries(
        post, "ElevenLabs transcription", retry_read_timeouts=False,
        read_timeout_advice=(
            "The response IS the transcript, so without it there is nothing to "
            "recover. Tell the user in plain language: the transcription of this "
            "file timed out and may already have been billed; re-running it may "
            "bill this one file a second time. Ask whether to re-run, and only "
            "re-run after they agree."))
    if not resp.ok:
        sys.exit(f"ElevenLabs error {resp.status_code}: {resp.text[:500]}")
    return resp.json()


# ── Soniox ────────────────────────────────────────────────────────────────────

SONIOX_API = "https://api.soniox.com/v1"


def transcribe_soniox(audio_path: str, language: str) -> dict:
    """Soniox stt-async-v5. Runs the async flow and normalizes the token stream
    into the canonical Scribe shape."""
    key = os.environ.get("SONIOX_API_KEY")
    if not key:
        sys.exit("SONIOX_API_KEY is not set.")
    auth = {"Authorization": f"Bearer {key}"}

    # 1. upload
    def upload():
        # Reopen per attempt: a failed upload leaves the file handle mid-stream.
        with open(audio_path, "rb") as f:
            return requests.post(f"{SONIOX_API}/files", headers=auth,
                                 files={"file": f}, timeout=3600)

    r = request_with_retries(
        upload, "Soniox upload", retry_read_timeouts=False,
        read_timeout_advice=(
            "The file may have been stored on the account anyway. Check with: "
            "curl -s -H \"Authorization: Bearer $SONIOX_API_KEY\" "
            f"{SONIOX_API}/files -- if a file with this name is listed, DELETE "
            f"it by id ({SONIOX_API}/files/<id>) so it does not orphan account "
            "storage, then re-run this script."))
    if not r.ok:
        sys.exit(f"Soniox upload error {r.status_code}: {r.text[:500]}")
    file_id = r.json()["id"]

    # 2. create transcription
    def create():
        return requests.post(
            f"{SONIOX_API}/transcriptions",
            headers={**auth, "Content-Type": "application/json"},
            json={
                "model": "stt-async-v5",
                "file_id": file_id,
                "language_hints": [language],
                "enable_speaker_diarization": True,
            },
            timeout=120,
        )

    r = request_with_retries(
        create, "Soniox create", retry_read_timeouts=False,
        read_timeout_advice=(
            "A transcription job may have been created anyway. Check with: "
            "curl -s -H \"Authorization: Bearer $SONIOX_API_KEY\" "
            f"{SONIOX_API}/transcriptions -- if a recent job for file_id "
            f"{file_id} is listed, do NOT create another (it would occupy one "
            "of the few concurrency slots); re-running this script is only safe "
            "after deleting that job by id "
            f"({SONIOX_API}/transcriptions/<id>)."))
    if not r.ok:
        sys.exit(f"Soniox create error {r.status_code}: {r.text[:500]}")
    tid = r.json()["id"]

    # 3. poll until done (wall-clock deadline, not iteration count -- a
    # black-holed connection burns up to 60s per attempt, not 2s)
    status = None
    detail = ""
    deadline = time.monotonic() + 3600
    fail_streak = 0
    while time.monotonic() < deadline:
        try:
            r = requests.get(f"{SONIOX_API}/transcriptions/{tid}", headers=auth, timeout=60)
        except requests.RequestException as e:
            fail_streak += 1
            detail = f"{type(e).__name__}: {e}"
            if fail_streak % 30 == 1:  # one stderr note per ~minute of failures
                print(f"Soniox poll: {detail} -- still retrying", file=sys.stderr)
            time.sleep(2)
            continue
        fail_streak = 0
        if r.status_code in (401, 403, 404):
            # Permanent: bad/revoked key or deleted job. Don't poll for an hour.
            sys.exit(f"Soniox poll error {r.status_code}: {r.text[:500]}")
        detail = r.text[:500]
        try:
            status = r.json().get("status")
        except ValueError:
            pass  # malformed body; keep polling
        if status in ("completed", "error"):
            break
        time.sleep(2)
    if status != "completed":
        sys.exit(f"Soniox transcription did not complete: status={status} detail={detail}")

    # 4. fetch transcript
    def fetch():
        return requests.get(f"{SONIOX_API}/transcriptions/{tid}/transcript",
                            headers=auth, timeout=120)

    r = request_with_retries(fetch, "Soniox transcript fetch")
    if not r.ok:
        sys.exit(f"Soniox transcript error {r.status_code}: {r.text[:500]}")
    raw = r.json()

    # Best-effort cleanup so we don't leave files/jobs on the account.
    try:
        requests.delete(f"{SONIOX_API}/transcriptions/{tid}", headers=auth, timeout=60)
        requests.delete(f"{SONIOX_API}/files/{file_id}", headers=auth, timeout=60)
    except requests.RequestException:
        pass

    return soniox_to_canonical(raw)


def soniox_to_canonical(raw: dict) -> dict:
    """Convert a Soniox transcript response into the canonical Scribe shape.

    Soniox returns one token per character for Japanese (same granularity as
    Scribe), with ms timestamps and a string speaker id. Mapping:
      start_ms/1000 -> start, end_ms/1000 -> end
      speaker "1"   -> speaker_id "speaker_1"
      is_audio_event-> type "audio_event"; whitespace -> "spacing"; else "word"
      confidence    -> logprob (ln(confidence)), for fidelity; unused downstream
    """
    words = []
    for t in raw.get("tokens", []):
        text = t.get("text", "")
        start = t.get("start_ms", 0) / 1000.0
        end = t.get("end_ms", 0) / 1000.0
        speaker = t.get("speaker")
        speaker_id = f"speaker_{speaker}" if speaker is not None else "speaker_0"
        conf = t.get("confidence")
        logprob = math.log(conf) if conf and conf > 0 else 0.0

        # Soniox glues a leading space onto word tokens in spaced languages
        # (e.g. " area" in English). Japanese never has these, but split them
        # out into a spacing token defensively so concatenation stays clean.
        if t.get("is_audio_event"):
            words.append(_word(text, start, end, "audio_event", speaker_id, logprob))
            continue
        if text.strip() == "":
            words.append(_word(text, start, end, "spacing", speaker_id, logprob))
            continue
        if text != text.lstrip(" "):
            stripped = text.lstrip(" ")
            words.append(_word(" ", start, start, "spacing", speaker_id, 0.0))
            text = stripped
        words.append(_word(text, start, end, "word", speaker_id, logprob))

    full_text = raw.get("text") or "".join(w["text"] for w in words)
    return {"language_code": "jpn", "text": full_text, "words": words}


def _word(text, start, end, typ, speaker_id, logprob):
    return {
        "text": text,
        "start": round(start, 3),
        "end": round(end, 3),
        "type": typ,
        "speaker_id": speaker_id,
        "logprob": round(logprob, 4),
    }


# ── Audio extraction ──────────────────────────────────────────────────────────

# Audio codecs we can losslessly stream-copy (no re-encode) into a container
# the STT providers accept, keyed to the right extension. Anything not listed
# (e.g. ac3/dts) is re-encoded to AAC/m4a instead.
_COPY_CONTAINER = {
    "aac": ".m4a", "mp3": ".mp3", "flac": ".flac",
    "opus": ".opus", "vorbis": ".ogg",
    "pcm_s16le": ".wav", "pcm_s24le": ".wav", "pcm_f32le": ".wav",
}


def _probe_streams(path: str):
    """Return (has_video, audio_codec) via ffprobe. has_video is True only for a
    real video stream, not an attached cover image. audio_codec is None when no
    audio stream is found or ffprobe fails."""
    def probe(args):
        out = subprocess.run(["ffprobe", "-v", "error", *args, "-of",
                              "default=nw=1:nk=1", path],
                             capture_output=True, text=True)
        return out.stdout.split() if out.returncode == 0 else []

    # attached_pic == 1 marks cover-art/thumbnail video streams; a disposition
    # of 0 is a genuine video track.
    has_video = any(flag == "0" for flag in probe(
        ["-select_streams", "v", "-show_entries",
         "stream_disposition=attached_pic"]))
    acodecs = probe(["-select_streams", "a:0", "-show_entries",
                     "stream=codec_name"])
    return has_video, (acodecs[0] if acodecs else None)


def extract_audio(path: str):
    """Demux audio out of a video so we upload a few MB instead of the whole
    file (a smaller upload is also far less likely to die mid-stream on the
    low-concurrency STT accounts this script targets).

    Returns (upload_path, tmp_to_cleanup). tmp_to_cleanup is None when nothing
    was created -- already audio-only, tooling unavailable, or extraction failed
    -- and the caller uploads the original path unchanged."""
    if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
        print("transcribe: ffmpeg/ffprobe not found -- uploading the original "
              "file without stripping video (install ffmpeg to shrink uploads "
              "and reduce upload failures).", file=sys.stderr)
        return path, None

    has_video, codec = _probe_streams(path)
    if codec is None or not has_video:
        return path, None  # already audio-only (or no probable audio); leave it

    # Prefer a lossless stream-copy; fall back to an AAC re-encode for codecs we
    # can't safely copy into a common container.
    plans = []
    copy_ext = _COPY_CONTAINER.get(codec)
    if copy_ext:
        plans.append((copy_ext, ["-c:a", "copy"]))
    plans.append((".m4a", ["-c:a", "aac", "-b:a", "128k"]))

    for ext, acodec in plans:
        fd, tmp = tempfile.mkstemp(suffix=ext, prefix="transcribe_audio_")
        os.close(fd)
        run = subprocess.run(["ffmpeg", "-y", "-i", path, "-vn", *acodec, tmp],
                             capture_output=True, text=True)
        if run.returncode == 0 and os.path.getsize(tmp) > 0:
            print(f"transcribe: stripped video; uploading audio only "
                  f"({os.path.basename(tmp)}, "
                  f"{os.path.getsize(tmp) // 1024} KiB).", file=sys.stderr)
            return tmp, tmp
        if os.path.exists(tmp):
            os.remove(tmp)

    print("transcribe: audio extraction failed -- uploading the original file.",
          file=sys.stderr)
    return path, None


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Transcribe to canonical transcript JSON.")
    ap.add_argument("audio", help="Path to the video/audio file.")
    ap.add_argument("--provider", required=True, choices=["elevenlabs", "soniox"])
    ap.add_argument("--language", default="ja", help="Language code (default: ja).")
    ap.add_argument("-o", "--output", help="Output stem (default: input basename).")
    args = ap.parse_args()

    if not os.path.exists(args.audio):
        sys.exit(f"File not found: {args.audio}")

    upload_path, tmp = extract_audio(args.audio)
    try:
        if args.provider == "elevenlabs":
            data = transcribe_elevenlabs(upload_path, args.language)
        else:
            data = transcribe_soniox(upload_path, args.language)
    finally:
        if tmp and os.path.exists(tmp):
            os.remove(tmp)

    stem = args.output or os.path.splitext(os.path.basename(args.audio))[0]
    out_path = f"{stem}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"Wrote {out_path} ({len(data.get('words', []))} words, provider={args.provider})")


if __name__ == "__main__":
    main()
