"""Verifiable receipts — chain integrity + tamper detection."""
import sys, os, json
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import receipts

def test_chain_verifies_and_tamper_is_caught(tmp_path, monkeypatch):
    monkeypatch.setattr(receipts, "_PATH", str(tmp_path / "r.json"))
    receipts.reset()
    for i in range(4):
        receipts.append_receipt(f"C00{i}", f"ORD-{i}",
            {"decision": "DENY", "rule": "R1", "refund_amount": 0, "refund_type": "none", "reason": "x"}, ts=str(i))
    assert receipts.verify_chain()["ok"] is True
    # tamper: flip one field, leave hash
    chain = json.load(open(receipts._PATH))
    chain["rows"][2]["amount"] = "9999.00"
    json.dump(chain, open(receipts._PATH, "w"))
    res = receipts.verify_chain()
    assert res["ok"] is False and res["broken_seq"] == 2

def test_genesis_prev_is_zeros(tmp_path, monkeypatch):
    monkeypatch.setattr(receipts, "_PATH", str(tmp_path / "r.json"))
    receipts.reset()
    row = receipts.append_receipt("C1", "O1", {"decision": "DENY", "rule": "R1"}, ts="0")
    assert row["prev_hash"] == "0" * 64
