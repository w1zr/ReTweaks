# tests/test_ai_assistant.py
import json

import pytest

from core import ai_assistant as AI

STATIC = {
    "os": {"name": "Microsoft Windows 11 Home", "version": "10.0.26100", "build": "26100"},
    "computer": {"manufacturer": "iBUYPOWER", "model": "TMI7N4601", "serial": "SN-SECRET-999"},
    "cpu": {"name": "Intel(R) Core(TM) i7-14700F", "cores": 20, "threads": 28,
            "serial": "CPUSERIAL123"},
    "gpus": [{"name": "NVIDIA GeForce RTX 4060", "vram_gb": 8.0, "driver_version": "32.0.15.6094",
              "driver_date": "2025-01-10", "luid": "0x1234", "pnp_id": "PCI\\VEN_10DE&SERIAL"}],
    "ram": {"total_gb": 31.8, "type": "DDR5", "running_mts": 5600,
            "sticks": [{"part": "PARTNO", "maker": "X", "serial": "RAMSERIAL"}]},
    "disks": [{"name": "Samsung SSD 990 SN: S7XXXXXX", "size_gb": 2000, "media": "SSD",
               "bus": "NVMe", "health": "Healthy", "letters": ["C:"], "serial": "DISKSERIAL"}],
    "network": [{"name": "Wi-Fi", "mac": "AA:BB:CC:11:22:33", "ip": "192.168.1.50"}],
    "computer_name": "RYDER-DESKTOP",
    "product_key": "AAAAA-BBBBB-CCCCC-DDDDD-EEEEE",
    "monitors": [{"name": "Dell SERIALMON", "maker": "DEL"}],
}
SAMPLE = {"cpu": {"load": 12.4, "temp_c": 55.0},
          "gpus": [{"load": 30.0, "temp_c": 48.0, "vram_used_gb": 1.234}],
          "ram": {"percent": 40.0}}


def specs(**kw):
    return AI.build_specs_summary(STATIC, SAMPLE, [{"width": 1920, "height": 1080, "hz": 144.0}],
                                  extra_terms=kw.get("terms", ["RYDER-DESKTOP", "ryder"]))


def test_specs_contains_useful_facts():
    t = specs()
    for s in ("Windows 11 Home", "i7-14700F", "RTX 4060", "8 GB VRAM", "31.8 GB", "DDR5",
              "2000 GB", "NVMe", "Healthy", "1920x1080 at 144 Hz", "CPU load 12%", "55 C"):
        assert s in t


def test_specs_redaction():
    t = specs()
    for bad in ("SN-SECRET-999", "CPUSERIAL123", "RAMSERIAL", "DISKSERIAL", "RYDER-DESKTOP",
                "AA:BB:CC:11:22:33", "192.168.1.50", "AAAAA-BBBBB", "PARTNO", "SERIALMON",
                "Samsung", "TMI7N4601", "0x1234", "VEN_10DE"):
        assert bad not in t


def test_scrub_removes_private_patterns():
    s = AI.scrub("host RYDER-PC at 10.0.0.5 mac 00-1A-2B-3C-4D-5E in C:\\Users\\ryder\\x", ["RYDER-PC"])
    for bad in ("RYDER-PC", "10.0.0.5", "00-1A-2B", "Users"):
        assert bad not in s


def test_scrub_applies_to_whitelisted_fields():
    st = {"cpu": {"name": "CPU 192.168.0.9 RYDER-DESKTOP"}}
    t = AI.build_specs_summary(st, extra_terms=["RYDER-DESKTOP"])
    assert "192.168" not in t and "RYDER-DESKTOP" not in t


def test_specs_empty_and_unknown_vram():
    assert AI.build_specs_summary({}, None, None, extra_terms=[]) == ""
    t = AI.build_specs_summary({"gpus": [{"name": "GPU X", "vram_gb": None}]}, extra_terms=[])
    assert "VRAM unavailable" in t


def test_body_has_system_instruction_and_pages():
    body = AI.build_request_body([{"role": "user", "text": "hi"}])
    sys_text = body["systemInstruction"]["parts"][0]["text"]
    assert "RYTWEAKS" in sys_text and "anti-cheat" in sys_text and "guaranteed" in sys_text
    for page in AI.PAGE_NAMES:
        assert page in sys_text
    assert body["contents"] == [{"role": "user", "parts": [{"text": "hi"}]}]
    assert body["generationConfig"]["maxOutputTokens"] > 0
    json.dumps(body)


def test_body_specs_toggle():
    on = AI.build_request_body([{"role": "user", "text": "x"}], "CPU: Test")
    off = AI.build_request_body([{"role": "user", "text": "x"}], None)
    assert "CPU: Test" in on["systemInstruction"]["parts"][0]["text"]
    assert "CPU: Test" not in off["systemInstruction"]["parts"][0]["text"]
    assert off["systemInstruction"]["parts"][0]["text"] == AI.SYSTEM_INSTRUCTION


def test_history_trimmed_and_starts_with_user():
    hist = []
    for i in range(30):
        hist.append({"role": "user", "text": f"q{i}"})
        hist.append({"role": "model", "text": f"a{i}"})
    body = AI.build_request_body(hist)
    c = body["contents"]
    assert len(c) <= AI.MAX_HISTORY
    assert c[0]["role"] == "user"
    assert c[-1]["parts"][0]["text"] == "a29"
    # odd cut that would start on a model turn is fixed
    t = AI.trim_history([{"role": "model", "text": "a"}, {"role": "user", "text": "b"}], 5)
    assert t[0]["role"] == "user"
    assert AI.trim_history([]) == []


def test_parse_response_ok_and_variants():
    ok = {"candidates": [{"content": {"parts": [{"text": "Hello "}, {"text": "world"}]},
                          "finishReason": "STOP"}]}
    assert AI.parse_response(ok) == "Hello world"
    cut = {"candidates": [{"content": {"parts": [{"text": "abc"}]}, "finishReason": "MAX_TOKENS"}]}
    assert "cut off" in AI.parse_response(cut)
    th = {"candidates": [{"content": {"parts": [{"text": "hmm", "thought": True}, {"text": "ans"}]}}]}
    assert AI.parse_response(th) == "ans"


def test_parse_response_errors():
    with pytest.raises(AI.AIError, match="safety"):
        AI.parse_response({"promptFeedback": {"blockReason": "SAFETY"}})
    with pytest.raises(AI.AIError, match="no answer"):
        AI.parse_response({"candidates": []})
    with pytest.raises(AI.AIError, match="withheld"):
        AI.parse_response({"candidates": [{"finishReason": "SAFETY"}]})
    with pytest.raises(AI.AIError):
        AI.parse_response("nope")


def test_parse_error_messages():
    body400 = json.dumps({"error": {"code": 400, "status": "INVALID_ARGUMENT",
                                    "message": "API key not valid. Please pass a valid API key."}})
    assert "key isn't valid" in AI.parse_error(400, body400)
    body429 = json.dumps({"error": {"code": 429, "status": "RESOURCE_EXHAUSTED", "message": "Quota"}})
    assert "free-tier limit" in AI.parse_error(429, body429)
    region = json.dumps({"error": {"code": 400, "status": "FAILED_PRECONDITION",
                                   "message": "User location is not supported for the API use."}})
    assert "region" in AI.parse_error(400, region)
    assert "region" in AI.parse_error(403, "{}")
    assert "busy right now" in AI.parse_error(503, "")
    assert "model" in AI.parse_error(404, "")
    assert "400" in AI.parse_error(400, json.dumps({"error": {"message": "bad field"}}))
    # snake_case code format from the docs
    assert "free-tier limit" in AI.parse_error(429, json.dumps({"error": {"code": "quota_exceeded", "message": "x"}}))


def test_parse_error_never_echoes_key():
    key = "AIzaSECRETKEY123"
    body = json.dumps({"error": {"message": f"bad request for {key}"}})
    assert key not in AI.parse_error(400, body, key)


def test_parse_models():
    data = {"models": [
        {"name": "models/gemini-3.8-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash-tts", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-flash-image", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.6-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-3.9-pro", "supportedGenerationMethods": ["generateContent"]},
    ]}
    assert AI.parse_models(data) == ["gemini-3.8-flash", "gemini-3.6-flash"]
    assert AI.parse_models({}) == []


def test_decode_blob_and_unavailable():
    assert AI.decode_blob("abc".encode("utf-16-le")) == "abc"
    assert AI.decode_blob("abc") == "abc"
    assert AI.decode_blob(None) is None
    if not AI.credentials_available():
        assert AI.load_key() is None
        with pytest.raises(AI.AIError):
            AI.save_key("k")


def test_save_load_delete_key_roundtrip(monkeypatch):
    """Credential Manager stores raw bytes; we write the key's UTF-16-LE text and read it back."""
    store = {}
    monkeypatch.setattr(AI, "_advapi", object())
    monkeypatch.setattr(AI, "_cred_write", lambda t, blob, c: store.__setitem__(t, bytes(blob)))
    monkeypatch.setattr(AI, "_cred_read", lambda t: store.get(t))
    monkeypatch.setattr(AI, "_cred_delete", lambda t: store.pop(t, None) is not None or True)
    AI.save_key("  AQ.test-key-123  ")
    assert store[AI.CRED_TARGET] == "AQ.test-key-123".encode("utf-16-le")
    assert AI.load_key() == "AQ.test-key-123"
    assert AI.delete_key() and AI.load_key() is None


def test_save_key_reports_the_real_read_error(monkeypatch):
    monkeypatch.setattr(AI, "_advapi", object())
    monkeypatch.setattr(AI, "_cred_write", lambda t, blob, c: None)

    def bad_read(t):
        raise AI.AIError("Reading from Windows Credential Manager failed: Access is denied. (Windows error 5).")
    monkeypatch.setattr(AI, "_cred_read", bad_read)
    import pytest
    with pytest.raises(AI.AIError, match="Access is denied"):
        AI.save_key("k")
    assert AI.load_key() is None      # load_key stays quiet; save_key shows the reason


def test_save_key_detects_a_changed_value(monkeypatch):
    monkeypatch.setattr(AI, "_advapi", object())
    monkeypatch.setattr(AI, "_cred_write", lambda t, blob, c: None)
    monkeypatch.setattr(AI, "_cred_read", lambda t: "other".encode("utf-16-le"))
    import pytest
    with pytest.raises(AI.AIError, match="different"):
        AI.save_key("k")


def _fake_generate(script):
    """script: {model: [result-or-status, ...]} consumed in order."""
    calls = []

    def gen(key, model, history, specs_text=None, timeout=None):
        calls.append(model)
        r = script[model].pop(0)
        if isinstance(r, int):
            raise AI.AIError(f"error {r}", status=r)
        return r
    return gen, calls


def test_retry_rides_out_a_503(monkeypatch):
    gen, calls = _fake_generate({"gemini-3.8-flash": [503, 503, "hi"]})
    monkeypatch.setattr(AI, "generate", gen)
    waits = []
    assert AI.generate_with_retry("k", "gemini-3.8-flash", [], sleep=waits.append) == ("hi", "gemini-3.8-flash")
    assert waits == [1.5, 4.0] and calls == ["gemini-3.8-flash"] * 3


def test_retry_falls_back_to_another_model(monkeypatch):
    gen, calls = _fake_generate({"gemini-3.8-flash": [503, 503, 503], "gemini-3.6-flash": ["ok"]})
    monkeypatch.setattr(AI, "generate", gen)
    text, used = AI.generate_with_retry("k", "gemini-3.8-flash", [], sleep=lambda s: None)
    assert (text, used) == ("ok", "gemini-3.6-flash")


def test_rate_limit_waits_once_then_moves_on(monkeypatch):
    gen, calls = _fake_generate({"gemini-3.8-flash": [429, 429], "gemini-3.6-flash": ["ok"]})
    monkeypatch.setattr(AI, "generate", gen)
    waits = []
    assert AI.generate_with_retry("k", "gemini-3.8-flash", [], sleep=waits.append)[1] == "gemini-3.6-flash"
    assert waits == [4.0]


def test_bad_key_is_not_retried(monkeypatch):
    gen, calls = _fake_generate({"gemini-3.8-flash": [400]})
    monkeypatch.setattr(AI, "generate", gen)
    import pytest
    with pytest.raises(AI.AIError):
        AI.generate_with_retry("k", "gemini-3.8-flash", [], sleep=lambda s: None)
    assert calls == ["gemini-3.8-flash"]


def test_gives_up_with_last_error_when_everything_is_busy(monkeypatch):
    busy = {m: [503] * 5 for m in AI.FALLBACK_MODELS}
    gen, calls = _fake_generate(busy)
    monkeypatch.setattr(AI, "generate", gen)
    import pytest
    with pytest.raises(AI.AIError) as e:
        AI.generate_with_retry("k", "gemini-3.8-flash", [], sleep=lambda s: None)
    assert e.value.busy
