"""
Output audit — the transcript-truth (thoth) fold.

thoth's principle: models transcribe/propose, but a DETERMINISTIC pure function grades
what was actually said. Here we apply it to the agent's final reply (text now; the exact
same function grades the Deepgram transcript of the *spoken* reply when voice is on):
given the reply and the ground-truth policy verdict, detect any contradiction — e.g. the
agent's words imply an approval when the verdict was DENY, or a denial when it was APPROVE.

This catches the most dangerous failure in a support agent: the deterministic engine denied
the refund, but the LLM's *language* told the customer "yes." No model runs in here — same
compiled patterns, pure function, cap-the-grade-on-any-flag, exactly like thoth's scanners.
"""
import re

# Deterministic phrase scanners (compiled once; the "witnesses")
_APPROVE_SAYS = re.compile(r"\b(approved|i(?:'ve| have)? issued|processed your refund|refund (?:of )?\$|you(?:'ll| will) (?:get|receive)|money back|store credit (?:for|of|has))\b", re.I)
_DENY_SAYS    = re.compile(r"\b(unable to (?:refund|process)|can(?:'t|not) refund|not eligible|non-?refundable|denied|isn'?t possible|outside the (?:return )?window|already (?:been )?refunded)\b", re.I)
_ESCALATE_SAYS= re.compile(r"\b(escalat|a (?:manager|specialist|human)|team will (?:follow|review)|routed? (?:it|your))\b", re.I)


def audit_reply(reply: str, verdict: dict) -> dict:
    """Pure function. Returns {consistent: bool, grade: 'PASS'|'FLAG', flags: [...]}.
    A FLAG means the agent's words contradict what the deterministic engine actually decided."""
    text = reply or ""
    decision = (verdict or {}).get("decision", "")
    says_approve = bool(_APPROVE_SAYS.search(text))
    says_deny    = bool(_DENY_SAYS.search(text))
    says_escalate= bool(_ESCALATE_SAYS.search(text))
    flags = []

    if decision in ("DENY", "ESCALATE") and says_approve and not says_deny and not says_escalate:
        flags.append(f"reply implies an APPROVAL, but the verdict was {decision} — hallucinated refund language")
    if decision == "APPROVE_FULL" and says_deny and not says_approve:
        flags.append("reply implies a DENIAL, but the verdict was APPROVE_FULL — contradicts the approval")
    if decision == "STORE_CREDIT" and re.search(r"\b(cash|money back|to your (?:card|bank|account))\b", text, re.I) and not re.search(r"store credit", text, re.I):
        flags.append("reply implies a CASH refund, but the verdict was STORE_CREDIT only")
    if decision == "ESCALATE" and (says_approve or says_deny) and not says_escalate:
        flags.append("reply resolves the case, but the verdict was ESCALATE (needs a human) — should not commit")

    consistent = len(flags) == 0
    return {"consistent": consistent, "grade": "PASS" if consistent else "FLAG",
            "verdict": decision, "flags": flags}
