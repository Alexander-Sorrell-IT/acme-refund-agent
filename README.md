# Acme Refund Agent — a refund agent you can *prove* won't be talked into a bad refund

[![CI](https://github.com/Alexander-Sorrell-IT/acme-refund-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/Alexander-Sorrell-IT/acme-refund-agent/actions/workflows/ci.yml)


> Most "AI refund agent" demos are something you have to **trust**. This one is something you can **verify.**
> The LLM talks to the customer and orchestrates tools — but a **deterministic policy engine owns every
> approve/deny decision** (R1), it **can't be jailbroken** into a bad refund (adversarial red-team, R2),
> it **can't lie** about the decision in words (deterministic output audit, R3), and **every decision is
> sealed in a tamper-evident receipt** re-verifiable offline in two languages (hash-chain, R4).
> *Models propose; deterministic systems own the verdict, the safety proof, the truthfulness, and the audit trail.*

Built for the Foundersmax AI Engineer take-home. Stack: **FastAPI + Groq (llama-3.3-70b) function-calling + a pure-Python policy engine + a live reasoning-log dashboard.**

---

## The core idea: models propose, a deterministic function owns the verdict

An LLM deciding refunds is a liability — a good sob story or a prompt injection can flip it. So the model here
**never decides.** It gathers facts (customer, order), then calls `evaluate_refund_policy`, which runs a
**pure function** (`backend/policy.py`) that returns `APPROVE_FULL | STORE_CREDIT | ESCALATE | DENY` with the
**exact rule ID** it cites. `issue_refund` **re-derives that verdict server-side**, so even a fully
jailbroken model physically cannot push through a refund the policy denied.

Same order in → same verdict out, every time, with a citation. That's the whole design.

---

## What's inside

| Requirement | How it's met |
|---|---|
| **Mock data** | `data/customers.json` — 15 profiles crafted to hit every rule; `data/refund_policy.md` — 8 strict rules + precedence |
| **Agent backend** | `backend/agent.py` — Groq function-calling loop (sequential tool calls; retry-with-backoff on LLM failure, visible in the log) |
| **Tools validate policy** | `backend/tools.py` — `lookup_customer`, `get_order` (ownership check), `evaluate_refund_policy` (deterministic), `issue_refund` (re-verified) |
| **Frontend** | `frontend/index.html` customer chat · `frontend/admin.html` **real-time reasoning-log dashboard** |
| **⭐ Differentiator 1 (doomcaller fold)** | `backend/redteam.py` — **adversarial red-team harness**: an adversarial "customer" attacks the agent (prompt injection, false authority, guilt trips, urgency, double-dip) and a **deterministic grader proves the agent held the line.** Latest run: **8/8 held, 0 violations.** |

## Why the red-team harness matters (the part no one else brings)
Anyone can build a happy-path refund bot. The risk in production is the *unhappy* path — a customer
manipulating the agent into money it shouldn't give. So this repo ships the **proof of safety, not just the
feature**: `python backend/redteam.py` runs a battery of manipulation attacks and grades the agent's
*realized actions* against the ground-truth policy. It's the same principle as my
[doomcaller](https://github.com/Alexander-Sorrell-IT/doomcaller) project — an adversarial generator, a
deterministic judge. A refund agent isn't done when it works; it's done when you can't break it.

**Two levels of adversarial proof:**
- `redteam.py` — 8 *scripted* attacks (fast, deterministic). Latest: **8/8 held, 0 violations.**
- `adversary.py` — **live LLM adversaries that IMPROVISE and press across multiple turns** (fake authority → guilt → prompt injection → threats, escalating when denied). Latest: **5/5 held across 4-turn attacks, 0 violations.** `python backend/adversary.py`.

---

## Run it

```bash
cd foundersmax-refund-agent
pip install -r requirements.txt
cp .env.example .env          # add your GROQ_API_KEY (free at console.groq.com)
cd backend && uvicorn main:app --port 8099
```
- Customer chat → http://127.0.0.1:8099/
- Admin reasoning logs + **Run Red Team** → http://127.0.0.1:8099/admin

**Or with Docker:** `GROQ_API_KEY=... docker compose up` → http://127.0.0.1:8099/
**Tests:** `pip install -r requirements-dev.txt && pytest tests/ -v` — policy correctness, receipt integrity & tamper detection, output audit (runs in CI on every push, no API key needed).

Try: *"Hi, I'm Maria Alvarez, refund ORD-1001"* (approves) · *James Bello / ORD-1002* (past 30 days → held) ·
*Aisha Khan / ORD-1009* (gift card → denied) · *Isabella Rossi / ORD-1015* (over $500 → escalated) ·
then open **/admin** and hit **Run Red Team**.

## Architecture
```
customer ──chat──▶ agent loop (Groq, function-calling)
                     │  lookup_customer → get_order → evaluate_refund_policy → issue_refund
                     ▼
              POLICY ENGINE (pure function)  ── the verdict, with a rule citation
                     │
         every step ▼ published to the reasoning-log bus → /admin dashboard (SSE)

red-team ──▶ adversarial customer attacks the whole loop ──▶ deterministic grader ──▶ "held N/N, 0 violations"
```

## Design notes
- **Rule precedence** (`refund_policy.md`): ownership → abuse-hold → already-refunded → non-refundable category → window → high-value → condition. E.g. a *defective* item that's *past the window* is still denied (R1 beats R5); a *defective* item over $500 escalates (R6 beats R5).
- **`days_since_delivery`** is stored on each order so demos are stable regardless of run date.
- **⭐ Differentiator 2 (thoth fold):** `backend/audit.py` deterministically audits the agent's *reply* against the verdict — if the agent's words imply an approval when the engine said DENY (or promise cash when it's store-credit-only), it's **FLAGGED**. Same pure-function-grades-what-the-model-said principle as [thoth](https://github.com/Alexander-Sorrell-IT/thoth); it runs on text today and on the Deepgram transcript when the voice channel is on.
- **⭐ Differentiator 3 (on-the-record / glass-box-alpha fold):** `backend/receipts.py` seals **every decision into a hash-chained, tamper-evident receipt** (`SHA256(salt ‖ prev_hash ‖ canonical_json(row))`, genesis = 64 zeros). The chain re-verifies **offline in pure Python (`verify_chain`) OR pure Node — your actual `verifier.mjs` from [on-the-record](https://github.com/Alexander-Sorrell-IT/on-the-record)** — `node verifier.mjs data/receipts_export.json` → `CHAIN OK`. Flip one byte of any receipt → both verifiers report `BROKEN AT seq=N`. The reasoning log becomes a **cryptographic audit trail no one has to trust.**
- **Voice (bonus):** Deepgram STT → agent → ElevenLabs TTS; the audit above grades the spoken transcript identically.

Author: **Alexander Sorrell** · github.com/Alexander-Sorrell-IT
