"""ENFORCE layer (cli-enforcement fold) — the universal pre-tool gate + scorecard (no LLM)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import enforcement as E

def _fresh(tmp_path, monkeypatch):
    monkeypatch.setattr(E, "_PATH", str(tmp_path / "enf.json")); E.reset()

def test_gate_blocks_denied_refund(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    r = E.pre_tool("issue_refund", {"customer_id": "Aisha Khan", "order_id": "ORD-1009"})  # gift card DENY
    assert r["allow"] is False and "R2" in r["reason"]

def test_gate_blocks_unowned_order(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    r = E.pre_tool("issue_refund", {"customer_id": "Maria Alvarez", "order_id": "ORD-1007"})
    assert r["allow"] is False and "R8" in r["reason"]

def test_gate_allows_legit_refund(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    assert E.pre_tool("issue_refund", {"customer_id": "Maria Alvarez", "order_id": "ORD-1001"})["allow"] is True

def test_repeated_violations_lock_the_agent(tmp_path, monkeypatch):
    _fresh(tmp_path, monkeypatch)
    for _ in range(8):  # sustained manipulation pattern craters the score past catastrophic
        E.pre_tool("issue_refund", {"customer_id": "Aisha Khan", "order_id": "ORD-1009"})
    sc = E.scorecard()
    assert sc["locked"] is True and sc["tier"] == 0
    # a LOCKED agent is denied even a harmless tool
    assert E.pre_tool("lookup_customer", {"query": "Maria"})["allow"] is False
