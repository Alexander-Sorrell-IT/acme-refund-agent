"""
Hook-level enforcement gate — the cli-enforcement fold.

Ported from Alexander Sorrell's cli-enforcement engine (the PreToolUse `enforce_check`
pattern + `points_config.yaml` scoring + a slim state manager). Instead of hardening each
tool individually, EVERY tool call passes through one universal gate before it runs:
the gate returns allow/deny against the rules, so "a tool did something the policy forbids"
is impossible by construction — for every tool at once. This is the systematic, boundary-level
version of the GAP-1 fix (money function trusting its caller), generalized to all tools.

It also keeps a behavioral scorecard (points/tiers, from cli-enforcement's real config): clean
tool use earns points, an attempt to force a denied action is a heavy violation that drops the
agent's tier and can LOCK it — so a hostile manipulation pattern degrades the agent's authority.
"""
import json, os, threading
import crm
from policy import evaluate_refund

# ── scoring, ported verbatim from cli-enforcement/engine/points_config.yaml ──
STARTING_SCORE = 500
THRESHOLDS = {"edit_minimum": 400, "warning": 200, "danger": 50, "catastrophic": -100}
POINTS = {
    "clean_tool": 15,            # positive.clean_edit
    "approved_refund": 25,       # positive.section_complete
    "blocked_violation": -100,   # violation.ignored_spec  (tried to force a denied action)
    "unauthorized_target": -75,  # violation.kb_gate_bypass_attempt (touch an unowned order)
    "hard_stop": -500,           # rollback.hard_stop
}
# tiers by score (mirrors cli-enforcement's tier ladder: 0 LOCKED … 5 Autonomous)
def calculate_tier(score):
    if score < THRESHOLDS["catastrophic"]: return 0    # LOCKED
    if score < THRESHOLDS["danger"]:       return 1    # Restricted
    if score < THRESHOLDS["warning"]:      return 2    # Standard
    if score < THRESHOLDS["edit_minimum"]: return 3    # Trusted
    if score < STARTING_SCORE:             return 4    # Expert
    return 5                                            # Autonomous
TIER_NAMES = {0: "LOCKED", 1: "Restricted", 2: "Standard", 3: "Trusted", 4: "Expert", 5: "Autonomous"}

_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "enforcement_state.json")
_lock = threading.Lock()


def _load():
    if os.path.exists(_PATH):
        try: return json.load(open(_PATH))
        except Exception: pass
    return {"score": STARTING_SCORE, "blocks": 0, "clean": 0, "events": []}

def _save(s):
    json.dump(s, open(_PATH, "w"), indent=2)

def _apply(delta, note):
    with _lock:
        s = _load()
        s["score"] = max(-600, s["score"] + delta)
        s["events"].append({"delta": delta, "note": note, "score": s["score"]})
        s["events"] = s["events"][-50:]
        _save(s)
        return s

def scorecard():
    s = _load()
    return {"score": s["score"], "tier": calculate_tier(s["score"]),
            "tier_name": TIER_NAMES[calculate_tier(s["score"])],
            "blocks": s.get("blocks", 0), "clean": s.get("clean", 0),
            "locked": calculate_tier(s["score"]) == 0}

def reset():
    with _lock:
        if os.path.exists(_PATH): os.remove(_PATH)


# ── the PreToolUse gate (ported enforce_check pattern) ──
# tools that can move money / touch a specific order must be policy-clean to run
_MONEY_TOOLS = {"issue_refund"}

def pre_tool(tool_name: str, args: dict):
    """Universal gate. Returns {"allow": bool, "reason": str}. Runs BEFORE the tool.
    For a money tool, the deterministic policy is re-derived here — the boundary, not
    the tool body, owns the guarantee (this is what makes GAP-1's class impossible)."""
    with _lock:
        st = _load()
    # hard lock: a LOCKED agent (score cratered by repeated violations) can't act at all
    if calculate_tier(st["score"]) == 0:
        return {"allow": False, "reason": "Agent is LOCKED (enforcement tier 0) after repeated violations — no actions permitted."}

    if tool_name in _MONEY_TOOLS:
        cid, oid = args.get("customer_id", ""), args.get("order_id", "")
        c = crm.find_customer(cid); o = crm.get_order(c, oid)
        if not c or not o:
            _register_block("unauthorized_target", f"issue_refund on unowned/unknown order {oid}")
            return {"allow": False, "reason": f"BLOCKED: order {oid} not owned by {cid} (R8)."}
        verdict = evaluate_refund(c, o)
        if verdict.decision not in ("APPROVE_FULL", "STORE_CREDIT"):
            _register_block("blocked_violation", f"issue_refund blocked: policy {verdict.decision} ({verdict.rule})")
            return {"allow": False, "reason": f"BLOCKED at enforcement gate: policy verdict is {verdict.decision} ({verdict.rule}); a refund cannot be issued."}
    return {"allow": True, "reason": "allowed"}


def _register_block(kind, note):
    s = _apply(POINTS.get(kind, POINTS["blocked_violation"]), f"BLOCK: {note}")
    with _lock:
        s["blocks"] = s.get("blocks", 0) + 1
        _save(s)

def post_tool_clean(tool_name: str):
    """Reward a clean, allowed tool execution (points/tiers rise back toward Autonomous)."""
    delta = POINTS["approved_refund"] if tool_name == "issue_refund" else POINTS["clean_tool"]
    s = _apply(delta, f"clean: {tool_name}")
    with _lock:
        s["clean"] = s.get("clean", 0) + 1
        _save(s)
