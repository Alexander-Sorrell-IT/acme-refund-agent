"""
Voice channel (bonus): browser mic → Deepgram STT → agent → Deepgram Aura TTS → browser.

One provider for both directions (the DEEPGRAM_API_KEY already in .env), so there's no
second vendor to configure. The audit layer (audit.py) is transcript-agnostic — it grades
the agent's *words* against the verdict identically whether they were typed or spoken, so the
whole safety story (deterministic verdict, output audit, receipts, enforcement) holds on the
voice path with zero changes.

Key-gated: if DEEPGRAM_API_KEY is unset the endpoints report unavailable instead of crashing,
so the text demo and CI (no secrets) are never blocked by the voice bonus.
"""
import os, requests

DG_KEY = os.getenv("DEEPGRAM_API_KEY", "").strip()
STT_URL = "https://api.deepgram.com/v1/listen"
TTS_URL = "https://api.deepgram.com/v1/speak"
TTS_VOICE = os.getenv("AURA_VOICE", "aura-asteria-en")


def available() -> bool:
    return bool(DG_KEY)


def transcribe(audio_bytes: bytes, content_type: str = "audio/webm") -> str:
    """Speech → text via Deepgram. Returns the best transcript (may be empty for silence)."""
    if not DG_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set")
    r = requests.post(
        STT_URL,
        params={"model": "nova-2", "smart_format": "true", "punctuate": "true"},
        headers={"Authorization": f"Token {DG_KEY}", "Content-Type": content_type},
        data=audio_bytes,
        timeout=30,
    )
    r.raise_for_status()
    j = r.json()
    try:
        return j["results"]["channels"][0]["alternatives"][0]["transcript"].strip()
    except (KeyError, IndexError):
        return ""


def synthesize(text: str) -> bytes:
    """Text → MP3 audio via Deepgram Aura. Returns raw audio bytes."""
    if not DG_KEY:
        raise RuntimeError("DEEPGRAM_API_KEY not set")
    r = requests.post(
        f"{TTS_URL}?model={TTS_VOICE}&encoding=mp3",
        headers={"Authorization": f"Token {DG_KEY}", "Content-Type": "application/json"},
        json={"text": text},
        timeout=30,
    )
    r.raise_for_status()
    return r.content
