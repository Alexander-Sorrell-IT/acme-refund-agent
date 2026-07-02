"""Tools the agent can call. Each one logs to the reasoning bus, and the policy
decision is delegated to the DETERMINISTIC engine (policy.py) — never the LLM."""
import time
import crm, logbus, receipts
from policy import evaluate_refund

def lookup_customer(query: str):
    c = crm.find_customer(query)
    logbus.publish("tool", f"lookup_customer('{query}')",
                   {"found": bool(c), "customer_id": c["customer_id"] if c else None})
    if not c:
        return {"found": False, "message": "No customer matched that name/email."}
    return {"found": True, "customer_id": c["customer_id"], "name": c["name"],
            "orders": [{"order_id": o["order_id"], "item": o["item"]} for o in c["orders"]]}

def get_order(customer_id: str, order_id: str):
    c = crm.find_customer(customer_id)
    o = crm.get_order(c, order_id)
    logbus.publish("tool", f"get_order({customer_id}, {order_id})",
                   {"owned": bool(o)})
    if not o:
        # R8 — ownership / existence check failed
        return {"owned": False, "message": "That order was not found on this customer's account (R8)."}
    return {"owned": True, **o}

def evaluate_refund_policy(customer_id: str, order_id: str):
    c = crm.find_customer(customer_id)
    o = crm.get_order(c, order_id)
    if not c or not o:
        v = {"decision": "DENY", "rule": "R8", "reason": "Order does not belong to this customer.",
             "refund_amount": 0.0, "refund_type": "none"}
        logbus.publish("verdict", "DENY (R8) — ownership failed", v)
        return v
    verdict = evaluate_refund(c, o).dict()
    logbus.publish("verdict", f"{verdict['decision']} ({verdict['rule']})", verdict)
    # verifiable-receipt fold: write a tamper-evident, offline-verifiable receipt for this decision
    rc = receipts.append_receipt(customer_id, order_id, verdict, ts=str(round(time.time(), 3)))
    logbus.publish("receipt", f"receipt #{rc['seq']} sealed — hash {rc['hash'][:12]}…", {"seq": rc["seq"], "hash": rc["hash"]})
    return verdict

def issue_refund(customer_id: str, order_id: str):
    """Issue a refund. The verdict is RE-DERIVED here from the deterministic engine and is the
    sole authority — this function never accepts a verdict from its caller, so nothing upstream
    (a jailbroken LLM, a buggy orchestrator, a direct call) can push through a refund the policy
    denies. The safety invariant lives in the function that moves the money."""
    c = crm.find_customer(customer_id)
    o = crm.get_order(c, order_id)
    if not c or not o:
        logbus.publish("tool", f"issue_refund BLOCKED for {order_id}", {"reason": "order not owned (R8)"})
        return {"issued": False, "message": "Refund not issued — order not found on this account (R8)."}
    verdict = evaluate_refund(c, o).dict()   # authoritative, re-derived at the point of payment
    if verdict["decision"] not in ("APPROVE_FULL", "STORE_CREDIT"):
        logbus.publish("tool", f"issue_refund BLOCKED for {order_id}",
                       {"reason": f"policy verdict is {verdict['decision']} ({verdict['rule']})"})
        return {"issued": False, "message": f"Refund not issued — policy verdict is {verdict['decision']} ({verdict['rule']})."}
    crm.mark_refunded(order_id)
    logbus.publish("tool", f"issue_refund({order_id})",
                   {"amount": verdict["refund_amount"], "type": verdict["refund_type"], "rule": verdict["rule"]})
    return {"issued": True, "amount": verdict["refund_amount"], "type": verdict["refund_type"], "rule": verdict["rule"]}

TOOLS = {"lookup_customer": lookup_customer, "get_order": get_order,
         "evaluate_refund_policy": evaluate_refund_policy, "issue_refund": issue_refund}
