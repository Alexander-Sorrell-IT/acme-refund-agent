"""Deterministic policy engine — the verdict must be correct and stable for all 15 profiles."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import crm
from policy import evaluate_refund

EXPECTED = {  # ground truth: order_id -> (decision, rule)
    "ORD-1001": ("APPROVE_FULL", "R4"), "ORD-1002": ("DENY", "R1"),
    "ORD-1003": ("DENY", "R2"), "ORD-1004": ("DENY", "R3"),
    "ORD-1005": ("STORE_CREDIT", "R4"), "ORD-1006": ("APPROVE_FULL", "R5"),
    "ORD-1007": ("ESCALATE", "R6"), "ORD-1008": ("ESCALATE", "R7"),
    "ORD-1009": ("DENY", "R2"), "ORD-1010": ("DENY", "R2"),
    "ORD-1011": ("DENY", "R2"), "ORD-1012": ("APPROVE_FULL", "R4"),
    "ORD-1013": ("DENY", "R1"), "ORD-1014": ("DENY", "R1"),
    "ORD-1015": ("ESCALATE", "R6"),
}

def _order(oid):
    for c in crm.all_customers():
        for o in c["orders"]:
            if o["order_id"] == oid:
                return c, o
    raise KeyError(oid)

def test_all_profiles_correct():
    for oid, (dec, rule) in EXPECTED.items():
        c, o = _order(oid)
        v = evaluate_refund(c, o)
        assert v.decision == dec, f"{oid}: got {v.decision} expected {dec}"
        assert v.rule == rule, f"{oid}: got {v.rule} expected {rule}"

def test_verdict_is_deterministic():
    c, o = _order("ORD-1001")
    assert evaluate_refund(c, o).dict() == evaluate_refund(c, o).dict()

def test_precedence_window_beats_defective():
    # ORD-1014 is defective (R5) but 40 days old — window (R1) must win
    c, o = _order("ORD-1014")
    assert evaluate_refund(c, o).rule == "R1"

def test_precedence_value_beats_defective():
    # ORD-1015 is defective (R5) but $620 — high-value escalation (R6) must win
    c, o = _order("ORD-1015")
    assert evaluate_refund(c, o).rule == "R6"

def test_every_rule_is_covered():
    rules = {evaluate_refund(*_order(oid)).rule for oid in EXPECTED}
    for r in ["R1", "R2", "R3", "R4", "R5", "R6", "R7"]:
        assert r in rules, f"policy rule {r} never exercised by the fixtures"
