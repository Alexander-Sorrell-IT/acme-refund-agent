# Acme Store — Refund Policy (authoritative rules the agent enforces)

The agent NEVER improvises. Every decision cites a rule ID below. Ambiguity resolves in favor of the policy, not the customer.

| Rule | ID | Rule |
|---|---|---|
| Return window | R1 | Refunds are allowed only within **30 days of the delivery date**. Past 30 days → **DENY**. |
| Non-refundable categories | R2 | `gift_card`, `digital`, `final_sale`, and `perishable` items are **never refundable** → **DENY**. |
| Already refunded | R3 | If the order is already `refunded`, no second refund → **DENY**. |
| Item condition | R4 | `unopened` items → full refund. `opened` items → **store credit only** (not cash), unless R5 applies. |
| Defective / damaged on arrival | R5 | If the order is flagged `defective_on_arrival`, it is fully refundable even if opened, as long as within the return window (R1). |
| High-value approval | R6 | Refund amount **> $500** exceeds agent authority → **ESCALATE** to a human manager (do not auto-approve). |
| Refund-abuse hold | R7 | Customers flagged `refund_abuse` → **ESCALATE** for manual review, regardless of other rules. |
| Identity/order match | R8 | The order must belong to the requesting customer. Mismatch → **DENY**. |

## Decision precedence (apply in this order)
1. R8 (ownership) → 2. R7 (abuse hold) → 3. R3 (already refunded) → 4. R2 (non-refundable category) → 5. R1 (window) → 6. R6 (high value) → 7. R5 / R4 (condition).

Outcomes: **APPROVE_FULL**, **STORE_CREDIT**, **ESCALATE**, **DENY** — each with the citing rule ID and a customer-facing reason.
