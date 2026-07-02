"""thoth output audit — catches replies that contradict the verdict (no LLM)."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from audit import audit_reply

def test_flags_hallucinated_approval():
    a = audit_reply("Great news, your refund of $50 has been approved!", {"decision": "DENY"})
    assert a["grade"] == "FLAG"

def test_passes_correct_denial():
    a = audit_reply("Sorry, that item is non-refundable so I'm unable to refund it.", {"decision": "DENY"})
    assert a["grade"] == "PASS"

def test_flags_cash_when_store_credit_only():
    a = audit_reply("I've issued a full cash refund to your card.", {"decision": "STORE_CREDIT"})
    assert a["grade"] == "FLAG"
