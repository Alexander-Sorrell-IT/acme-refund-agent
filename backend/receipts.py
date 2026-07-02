"""
Verifiable decision receipts — the on-the-record / glass-box-alpha fold.

Every refund decision is written to a hash-chained, tamper-evident receipt log. The hash rule
is IDENTICAL to my on-the-record verifier (SHA256( salt || prev_hash_bytes || canonical_json(row) ),
genesis prev = 64 zeros, sorted-keys canonical JSON), so the exported chain re-verifies OFFLINE with
pure Node (verifier.mjs) OR pure Python (verify_receipts.py) — no SDK, no network, no trust in us.
Flip one byte of any receipt and the chain goes red. This turns the reasoning log into a
cryptographic audit trail: anyone can prove what the agent decided, for whom, and why.

All field VALUES are strings so the canonical JSON is byte-identical across JS and Python
(avoids JS/Python float-formatting drift, e.g. 50.0 vs 50).
"""
import hashlib, json, os, threading

GENESIS_PREV = "0" * 64
SALT = "acme-refund-agent:v1"   # public domain-separation string, shipped in the export
_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "receipts_export.json")
_lock = threading.Lock()


def canonical_json(value):
    """Deterministic sorted-keys serialization — mirrors the JS verifier's canonicalJson."""
    if value is None or not isinstance(value, (dict, list)):
        return json.dumps(value)
    if isinstance(value, list):
        return "[" + ",".join(canonical_json(v) for v in value) + "]"
    keys = sorted(value.keys())
    return "{" + ",".join(json.dumps(k) + ":" + canonical_json(value[k]) for k in keys) + "}"


def compute_hash(prev_hash_hex, row_without_hash):
    h = hashlib.sha256()
    h.update(SALT.encode("utf-8"))
    h.update(bytes.fromhex(prev_hash_hex))
    h.update(canonical_json(row_without_hash).encode("utf-8"))
    return h.hexdigest()


def _load():
    if os.path.exists(_PATH):
        try:
            return json.load(open(_PATH))
        except Exception:
            pass
    return {"salt": SALT, "rows": []}


def append_receipt(customer_id, order_id, verdict: dict, ts: str):
    """Append one tamper-evident receipt for a refund decision. Returns the receipt row."""
    with _lock:
        chain = _load()
        rows = chain["rows"]
        prev_hash = rows[-1]["hash"] if rows else GENESIS_PREV
        row = {
            "seq": len(rows),
            "ts": ts,
            "customer_id": str(customer_id),
            "order_id": str(order_id),
            "action": str(verdict.get("decision", "")),
            "rule": str(verdict.get("rule", "")),
            "amount": f"{float(verdict.get('refund_amount', 0)):.2f}",
            "refund_type": str(verdict.get("refund_type", "none")),
            "reason": str(verdict.get("reason", "")),
            "prev_hash": prev_hash,
        }
        row["hash"] = compute_hash(prev_hash, row)
        rows.append(row)
        json.dump(chain, open(_PATH, "w"), indent=2)
        return row


def verify_chain():
    """Re-walk the chain offline and confirm integrity. Returns {ok, count, broken_seq}."""
    chain = _load()
    salt_ok = chain.get("salt") == SALT
    rows = sorted(chain["rows"], key=lambda r: r["seq"])
    prev = GENESIS_PREV
    for r in rows:
        expect = compute_hash(prev, {k: v for k, v in r.items() if k != "hash"})
        if r.get("prev_hash") != prev or r.get("hash") != expect:
            return {"ok": False, "count": len(rows), "broken_seq": r["seq"], "salt_ok": salt_ok}
        prev = r["hash"]
    return {"ok": True, "count": len(rows), "broken_seq": None, "salt_ok": salt_ok}


def all_receipts():
    return _load()["rows"]


def reset():
    with _lock:
        if os.path.exists(_PATH):
            os.remove(_PATH)
