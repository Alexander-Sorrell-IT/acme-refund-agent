"""Mock CRM — loads the 15 customer/order profiles and provides lookups."""
import json, os, re
_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "customers.json")
_CUSTOMERS = json.load(open(_PATH))

def all_customers():
    return _CUSTOMERS

def find_customer(query: str):
    """Resolve a customer strictly. Only reliable identifiers or an unambiguous full name match —
    never a single letter, a lone last name, or a negated mention ("I am NOT Marcus Feld").
    Ambiguous / partial input returns None so the agent asks for an order ID or email instead."""
    q = (query or "").strip().lower()
    if not q:
        return None
    # 1) exact identifier — the reliable path (email or customer_id)
    for c in _CUSTOMERS:
        if q == c["email"].lower() or q == c["customer_id"].lower():
            return c
    # 2) exact full-name match
    for c in _CUSTOMERS:
        if q == c["name"].lower():
            return c
    # 3) full name appears as a whole phrase in free text, UNIQUELY and not negated
    matches = []
    for c in _CUSTOMERS:
        name = c["name"].lower()
        if re.search(r"\b" + re.escape(name) + r"\b", q):
            if re.search(r"\b(not|isn'?t|never|n'?t)\s+(?:\w+\s+){0,2}" + re.escape(name), q):
                continue  # negated mention — don't resolve to this person
            matches.append(c)
    return matches[0] if len(matches) == 1 else None

def get_order(customer: dict, order_id: str):
    """Return the order IF it belongs to this customer (enforces R8 ownership)."""
    if not customer:
        return None
    for o in customer.get("orders", []):
        if o["order_id"].lower() == (order_id or "").strip().lower():
            return o
    return None

def mark_refunded(order_id: str):
    for c in _CUSTOMERS:
        for o in c.get("orders", []):
            if o["order_id"] == order_id:
                o["status"] = "refunded"
                return True
    return False
