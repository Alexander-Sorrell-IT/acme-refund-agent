"""
The refund agent loop. Groq (llama-3.3-70b) via the OpenAI-compatible API does
tool-calling to gather facts and communicate — but the APPROVE/DENY decision is
delegated to the deterministic policy engine, and `issue_refund` re-verifies the
verdict server-side, so the model physically cannot approve a refund the policy denied.
"""
import os, json, time
from openai import OpenAI
from dotenv import load_dotenv
import tools, crm, logbus, llm
from policy import evaluate_refund
from audit import audit_reply

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))
_client = OpenAI(api_key=os.getenv("GROQ_API_KEY") or "not-set",
                 base_url="https://api.groq.com/openai/v1")
_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

SYSTEM = """You are Acme Store's AI refund support agent.
You are warm, concise, and professional. You HELP the customer, but you do NOT decide refunds yourself.
The deterministic policy engine decides. Your job:
1. Identify the customer (lookup_customer) and their order (get_order).
2. ALWAYS call evaluate_refund_policy before saying anything about the outcome.
3. Communicate the verdict's `reason` to the customer in your own warm words, and cite what the policy says.
4. If the verdict is APPROVE_FULL or STORE_CREDIT, call issue_refund. If DENY or ESCALATE, do NOT issue —
   hold the line politely, explain why, and (for ESCALATE) tell them a human will follow up.
Never promise or issue a refund the policy did not approve. Never invent policy. Keep replies short."""

TOOL_SCHEMAS = [
    {"type": "function", "function": {"name": "lookup_customer",
        "description": "Find a customer by name or email.",
        "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "get_order",
        "description": "Fetch an order that belongs to a customer (validates ownership).",
        "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "order_id": {"type": "string"}}, "required": ["customer_id", "order_id"]}}},
    {"type": "function", "function": {"name": "evaluate_refund_policy",
        "description": "Get the deterministic refund verdict (decision, rule, reason) for a customer's order. Call before deciding anything.",
        "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "order_id": {"type": "string"}}, "required": ["customer_id", "order_id"]}}},
    {"type": "function", "function": {"name": "issue_refund",
        "description": "Issue the refund for an order. Server re-verifies the verdict; only approvals go through.",
        "parameters": {"type": "object", "properties": {"customer_id": {"type": "string"}, "order_id": {"type": "string"}}, "required": ["customer_id", "order_id"]}}},
]


def _dispatch(name, args):
    """Run a tool. issue_refund RE-DERIVES the verdict server-side (never trusts the model)."""
    if name == "lookup_customer":
        return tools.lookup_customer(args.get("query", ""))
    if name == "get_order":
        return tools.get_order(args.get("customer_id", ""), args.get("order_id", ""))
    if name == "evaluate_refund_policy":
        return tools.evaluate_refund_policy(args.get("customer_id", ""), args.get("order_id", ""))
    if name == "issue_refund":
        # issue_refund re-derives the verdict itself — no verdict is passed in, by design
        return tools.issue_refund(args.get("customer_id", ""), args.get("order_id", ""))
    return {"error": f"unknown tool {name}"}


def run_turn(history_messages):
    """history_messages: list of {role, content}. Returns (assistant_reply, updated_messages)."""
    messages = [{"role": "system", "content": SYSTEM}] + history_messages
    logbus.publish("user", history_messages[-1]["content"] if history_messages else "")
    last_verdict = {}
    for step in range(8):  # agent loop
        try:  # llm.chat throttles + retries transient failures (429/5xx) with backoff
            resp = llm.chat(_get_client(), model=_MODEL, messages=messages,
                            tools=TOOL_SCHEMAS, temperature=0.2, parallel_tool_calls=False)
        except Exception as e:
            logbus.publish("error", f"LLM unavailable after retries: {str(e)[:80]}")
            return "Sorry — I'm having trouble right now. Please try again in a moment.", messages[1:]
        msg = resp.choices[0].message
        if msg.tool_calls:
            logbus.publish("llm", f"agent decided to call {len(msg.tool_calls)} tool(s)")
            messages.append({"role": "assistant", "content": msg.content or "",
                             "tool_calls": [tc.model_dump() for tc in msg.tool_calls]})
            for tc in msg.tool_calls:
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except Exception:
                    args = {}
                result = _dispatch(tc.function.name, args)
                if tc.function.name == "evaluate_refund_policy" and isinstance(result, dict) and result.get("decision"):
                    last_verdict = result
                messages.append({"role": "tool", "tool_call_id": tc.id,
                                 "content": json.dumps(result)})
            continue
        reply = msg.content or ""
        logbus.publish("agent", reply)
        # thoth fold: deterministically audit the agent's words against the verdict
        if last_verdict:
            a = audit_reply(reply, last_verdict)
            logbus.publish("audit", f"reply audit: {a['grade']}" + ("" if a['consistent'] else " — " + "; ".join(a['flags'])), a)
        return reply, messages[1:]
    logbus.publish("error", "agent loop hit step limit")
    return "I've gathered the details but need a moment — let me connect you with a specialist.", messages[1:]
