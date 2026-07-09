"""
verify_claims.py — prove every claim the demo makes, by execution. No say-so.

Run:  cd backend && python3 verify_claims.py
Prints a PASS/FAIL scorecard. The deterministic checks (tests, forced-refund attack,
receipts, policy verdicts) need NO LLM and are the load-bearing proof. The red-team
check makes real LLM calls but is graded deterministically.
"""
import subprocess, sys, os
from dotenv import load_dotenv
load_dotenv()

G, R, B, X = "\033[1;92m", "\033[1;91m", "\033[1m", "\033[0m"
rows = []
def check(name, ok, detail=""):
    rows.append((ok, name, detail))
    print(f"  {(G+'PASS'+X) if ok else (R+'FAIL'+X)}  {name}   {detail}")

print(f"\n{B}VERIFY — every claim proven by execution{X}\n")

# 1. DETERMINISTIC: the money path cannot be forced (core claim, no LLM)
import tools
r = tools.issue_refund("Aisha Khan", "ORD-1009")   # gift card = policy DENY; try to force a payout
import inspect
params = list(inspect.signature(tools.issue_refund).parameters)
check("Money path can't be forced (issue_refund re-derives verdict)",
      r.get("issued") is False and "DENY" in r.get("message", "") and "verdict" not in params and "amount" not in params,
      f"→ {r.get('message','')[:48]} | params={params}")

# 2. DETERMINISTIC: verdict is a pure function
outs = [tools.evaluate_refund_policy("Aisha Khan", "ORD-1009").get("decision") for _ in range(5)]
check("Verdict is deterministic (5x identical)", len(set(outs)) == 1, f"→ {outs}")

# 3. DETERMINISTIC: the demo scenarios resolve to the claimed verdicts
scen = {("Maria Alvarez","ORD-1001"):"APPROVE_FULL", ("Aisha Khan","ORD-1009"):"DENY"}
allok = True; got = []
for (c,o), want in scen.items():
    d = tools.evaluate_refund_policy(c,o).get("decision"); got.append(f"{c.split()[0]}={d}")
    allok = allok and d == want
check("Demo verdicts correct (Maria=APPROVE_FULL, Aisha=DENY)", allok, f"→ {got}")

# 4. DETERMINISTIC: receipts — build chain, both verifiers OK, then tamper -> both BROKEN
import receipts, json
receipts.reset()
for c,o in [("Maria Alvarez","ORD-1001"),("James Bello","ORD-1002"),("Aisha Khan","ORD-1009")]:
    tools.evaluate_refund_policy(c,o)
py_ok = receipts.verify_chain()["ok"]
node_ok = "CHAIN OK" in subprocess.run(["node","../verifier.mjs","../data/receipts_export.json"],
                                        capture_output=True, text=True).stdout
p = "../data/receipts_export.json"; d = json.load(open(p)); d["rows"][1]["amount"] = "9999.00"; json.dump(d, open(p,"w"))
py_broken = not receipts.verify_chain()["ok"]
node_broken = "BROKEN" in subprocess.run(["node","../verifier.mjs","../data/receipts_export.json"],
                                          capture_output=True, text=True).stdout.upper()
check("Receipts: both verifiers OK, then both BROKEN on tamper",
      py_ok and node_ok and py_broken and node_broken,
      f"→ pre[py={py_ok} node={node_ok}] post-tamper[py=BROKEN:{py_broken} node=BROKEN:{node_broken}]")

# 5. Test suite (deterministic)
t = subprocess.run([sys.executable,"-m","pytest","../tests/","-q"], capture_output=True, text=True)
passed = "passed" in t.stdout and "failed" not in t.stdout
check("Full test suite green", passed, f"→ {t.stdout.strip().splitlines()[-1] if t.stdout.strip() else t.stderr[:60]}")

# 6. Red-team battery (LLM attackers, deterministic grade) — skippable with SKIP_LLM=1
if os.getenv("SKIP_LLM"):
    print("  (skipped red-team LLM check — SKIP_LLM set)")
else:
    import redteam
    rep = redteam.run_battery()
    check("Red-team battery held (deterministic grade)",
          rep["passed"] and rep["held"] == rep["total"] and rep["violations"] == 0,
          f"→ {rep['held']}/{rep['total']} held, {rep['violations']} violations")

npass = sum(1 for ok,_,_ in rows if ok)
print(f"\n{B}{npass}/{len(rows)} claims verified by execution{X}\n")
sys.exit(0 if npass == len(rows) else 1)
