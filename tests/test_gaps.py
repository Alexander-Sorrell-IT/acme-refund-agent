"""Regression tests for the four gaps found in the self-audit (all deterministic, no LLM)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
import crm, tools, witness_panel
import unittest.mock as mock

# GAP 1 — issue_refund re-derives the verdict itself; it cannot be handed a fake approval
def test_issue_refund_self_guards_on_deny():
    r = tools.issue_refund("Aisha Khan", "ORD-1009")  # gift card → DENY R2
    assert r["issued"] is False and "R2" in r["message"]

def test_issue_refund_blocks_unowned_order():
    r = tools.issue_refund("Maria Alvarez", "ORD-1007")  # not Maria's order
    assert r["issued"] is False and "R8" in r["message"]

def test_issue_refund_allows_legit_approval():
    o = crm.get_order(crm.find_customer("Omar Haddad"), "ORD-1012")  # unopened, in window → APPROVE
    saved = o["status"]
    try:
        r = tools.issue_refund("Omar Haddad", "ORD-1012")
        assert r["issued"] is True and r["rule"] == "R4"
    finally:
        o["status"] = saved  # restore shared in-memory state for other tests

# GAP 2 — strict identity resolution
def test_identity_rejects_single_letter():
    assert crm.find_customer("a") is None

def test_identity_rejects_lone_lastname():
    assert crm.find_customer("ALVAREZ") is None

def test_identity_rejects_negated_name():
    assert crm.find_customer("I am definitely not Marcus Feld") is None

def test_identity_accepts_exact_identifiers():
    assert crm.find_customer("Maria Alvarez")["customer_id"] == "C001"
    assert crm.find_customer("maria.a@example.com")["customer_id"] == "C001"
    assert crm.find_customer("C001")["customer_id"] == "C001"

# GAP 3 — witness panel fails CLOSED (DEGRADED) when it lacks a quorum
def test_witness_panel_fails_closed():
    with mock.patch.object(witness_panel, "_ask",
                           lambda m, r, v: {"witness": m, "manipulated": None, "reason": "err"}):
        assert witness_panel.judge("I'll refund you!", {"decision": "DENY", "rule": "R2"})["consensus"] == "DEGRADED"
