"""Voice module: import-safe and key-gated (no secrets needed in CI)."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import voice


def test_available_reflects_key(monkeypatch):
    monkeypatch.setattr(voice, "DG_KEY", "")
    assert voice.available() is False
    monkeypatch.setattr(voice, "DG_KEY", "some-key")
    assert voice.available() is True


def test_calls_fail_closed_without_key(monkeypatch):
    monkeypatch.setattr(voice, "DG_KEY", "")
    for fn, args in [(voice.transcribe, (b"x",)), (voice.synthesize, ("hi",))]:
        try:
            fn(*args)
            assert False, "should have raised without a key"
        except RuntimeError:
            pass
