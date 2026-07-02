"""Mock CRM — loads the 15 customer/order profiles and provides lookups."""
import json, os
_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "customers.json")
_CUSTOMERS = json.load(open(_PATH))

def all_customers():
    return _CUSTOMERS

def find_customer(query: str):
    """Match by email, name (case-insensitive substring), or customer_id."""
    q = (query or "").strip().lower()
    for c in _CUSTOMERS:
        if q and (q == c["customer_id"].lower() or q == c["email"].lower()
                  or q in c["name"].lower() or c["name"].lower() in q):
            return c
    return None

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
