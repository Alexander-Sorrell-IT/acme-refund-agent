"""
Deterministic refund-policy engine — the VERDICT.

Design principle (Alexander Sorrell's signature across argus / doomcaller / glass-box-alpha):
    the LLM proposes and communicates; a pure, auditable function OWNS the decision.
No model call happens in here. Given the same order, this returns the same verdict every time,
and every verdict cites the exact rule ID from data/refund_policy.md.
"""
from dataclasses import dataclass, asdict

WINDOW_DAYS = 30
HIGH_VALUE_LIMIT = 500.0
NON_REFUNDABLE = {"gift_card", "digital", "final_sale", "perishable"}

DECISIONS = {"APPROVE_FULL", "STORE_CREDIT", "ESCALATE", "DENY"}


@dataclass
class Verdict:
    decision: str          # APPROVE_FULL | STORE_CREDIT | ESCALATE | DENY
    rule: str              # e.g. "R1"
    reason: str            # customer-facing explanation
    refund_amount: float   # dollars to refund (0 if denied/escalated)
    refund_type: str       # "cash" | "store_credit" | "none"

    def dict(self):
        return asdict(self)


def evaluate_refund(customer: dict, order: dict) -> Verdict:
    """Pure function. Applies rules in the precedence order defined in refund_policy.md."""
    account_flags = customer.get("account_flags", [])
    category = order.get("category", "")
    amount = float(order.get("amount", 0))
    days = int(order.get("days_since_delivery", 0))
    condition = order.get("condition", "unopened")
    status = order.get("status", "delivered")
    order_flags = order.get("flags", [])

    # R8 — ownership is validated by the tool layer (order fetched for this customer only).

    # R7 — refund-abuse hold (overrides everything except ownership)
    if "refund_abuse" in account_flags:
        return Verdict("ESCALATE", "R7",
                       "This account is flagged for review, so I'm routing your request to a human specialist rather than deciding it automatically.",
                       0.0, "none")

    # R3 — already refunded
    if status == "refunded":
        return Verdict("DENY", "R3",
                       "Our records show this order was already refunded, so a second refund isn't possible.",
                       0.0, "none")

    # R2 — non-refundable category
    if category in NON_REFUNDABLE:
        return Verdict("DENY", "R2",
                       f"{category.replace('_',' ').title()} items are non-refundable under our policy, so I'm unable to refund this order.",
                       0.0, "none")

    # R1 — return window
    if days > WINDOW_DAYS:
        return Verdict("DENY", "R1",
                       f"This order was delivered {days} days ago, and refunds are only available within {WINDOW_DAYS} days of delivery.",
                       0.0, "none")

    # R6 — high value requires manager approval
    if amount > HIGH_VALUE_LIMIT:
        return Verdict("ESCALATE", "R6",
                       f"Because this refund is over ${HIGH_VALUE_LIMIT:.0f}, it needs a manager's approval. I've escalated it and someone will follow up.",
                       0.0, "none")

    # R5 — defective on arrival: full refund even if opened (within window)
    if "defective_on_arrival" in order_flags:
        return Verdict("APPROVE_FULL", "R5",
                       "Since this item arrived defective and it's within the return window, you're due a full refund. I've approved it.",
                       round(amount, 2), "cash")

    # R4 — condition
    if condition == "opened":
        return Verdict("STORE_CREDIT", "R4",
                       "Because this item was opened, our policy offers store credit rather than a cash refund. I've issued store credit for the full amount.",
                       round(amount, 2), "store_credit")

    # R4 — unopened, within window, refundable category, normal value
    return Verdict("APPROVE_FULL", "R4",
                   "This item is unopened and within the return window, so you're due a full refund. I've approved it.",
                   round(amount, 2), "cash")
