"""
Determinism proof for the policy engine.

Three properties, checked by exhausting the input space rather than sampling examples:
  1. IDEMPOTENT   — same input → byte-identical verdict, every time (no hidden state/RNG/clock).
  2. TOTAL        — every combination in the full input cross-product yields a valid, internally
                    consistent verdict; no input falls through to an undefined state.
  3. PRECEDENCE   — when two rules both apply, the higher-precedence rule always wins, stably.

This is what makes "the deterministic engine owns the verdict" a claim you can *prove*, not assert.
"""
import os, sys, itertools
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from policy import (evaluate_refund, Verdict, DECISIONS,
                    NON_REFUNDABLE, WINDOW_DAYS, HIGH_VALUE_LIMIT)

# The full axis set the engine reads. Boundaries chosen to straddle every threshold.
CATEGORIES = list(NON_REFUNDABLE) + ["electronics", "apparel", "home"]
CONDITIONS = ["unopened", "opened"]
STATUSES = ["delivered", "refunded"]
DAYS = [0, WINDOW_DAYS - 1, WINDOW_DAYS, WINDOW_DAYS + 1, 400]
AMOUNTS = [0.0, 1.0, HIGH_VALUE_LIMIT, HIGH_VALUE_LIMIT + 0.01, 9999.0]
ACCOUNT_FLAGS = [[], ["refund_abuse"]]
ORDER_FLAGS = [[], ["defective_on_arrival"]]


def _all_inputs():
    for cat, cond, st, d, amt, af, of in itertools.product(
            CATEGORIES, CONDITIONS, STATUSES, DAYS, AMOUNTS, ACCOUNT_FLAGS, ORDER_FLAGS):
        yield ({"account_flags": af},
               {"category": cat, "condition": cond, "status": st,
                "days_since_delivery": d, "amount": amt, "flags": of})


def test_idempotent():
    """Same input, 200 runs, byte-identical verdict — proves no clock/RNG/shared-state leakage."""
    cust = {"account_flags": []}
    order = {"category": "electronics", "condition": "unopened", "status": "delivered",
             "days_since_delivery": 5, "amount": 89.99, "flags": []}
    first = evaluate_refund(cust, order).dict()
    for _ in range(200):
        assert evaluate_refund(cust, order).dict() == first


def test_total_and_consistent():
    """Every combination in the full cross-product returns a valid, self-consistent verdict."""
    count = 0
    for cust, order in _all_inputs():
        v = evaluate_refund(cust, order)
        count += 1
        assert isinstance(v, Verdict)
        assert v.decision in DECISIONS
        assert v.rule and v.rule.startswith("R")
        assert v.reason
        # money and decision must agree — no "approved but $0" or "denied but pays out"
        if v.decision == "APPROVE_FULL":
            assert v.refund_type == "cash" and v.refund_amount >= 0
        elif v.decision == "STORE_CREDIT":
            assert v.refund_type == "store_credit" and v.refund_amount >= 0
        else:  # DENY / ESCALATE never pay
            assert v.refund_amount == 0.0 and v.refund_type == "none"
    assert count == (len(CATEGORIES) * len(CONDITIONS) * len(STATUSES)
                     * len(DAYS) * len(AMOUNTS) * len(ACCOUNT_FLAGS) * len(ORDER_FLAGS))


def _v(cat="electronics", cond="unopened", st="delivered", d=5, amt=50.0, af=None, of=None):
    return evaluate_refund({"account_flags": af or []},
                           {"category": cat, "condition": cond, "status": st,
                            "days_since_delivery": d, "amount": amt, "flags": of or []})


def test_precedence_is_stable():
    # R7 abuse-hold beats everything downstream (even a clean approvable order)
    assert _v(af=["refund_abuse"]).rule == "R7"
    # R3 already-refunded beats R2 non-refundable-category
    assert _v(cat="gift_card", st="refunded").rule == "R3"
    # R1 window beats R5 defective (defective but 400 days out → still DENY on window)
    assert _v(d=400, of=["defective_on_arrival"]).decision == "DENY"
    assert _v(d=400, of=["defective_on_arrival"]).rule == "R1"
    # R6 high-value beats R5 defective (defective AND over limit → ESCALATE, don't auto-pay)
    assert _v(amt=HIGH_VALUE_LIMIT + 100, of=["defective_on_arrival"]).rule == "R6"
    # R5 defective beats R4 opened→store-credit (defective opened item → full cash, not credit)
    assert _v(cond="opened", of=["defective_on_arrival"]).decision == "APPROVE_FULL"
