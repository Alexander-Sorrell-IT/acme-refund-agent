# Foundersmax — AI Engineer Take-Home Challenge
**Role:** AI Engineer (~$150–225K, remote) · via Wellfound · Invited 2026-07-02
**Deadline:** 7 calendar days (submit by ~2026-07-09) → success leads to a final 30-min interview.
**Submit:** public GitHub repo (clean README) + a 7–10 min Loom video.

---

## THE CHALLENGE (what they want, verbatim from their email)
Build a **fully functional web application** for an **AI Customer Support Agent** that
**processes or denies e-commerce refunds** using an LLM.

### Required components
1. **Mock Data**
   - A CRM database of **15 customer profiles**
   - A **strict refund policy document** (the rules the agent enforces)
2. **Agent Backend**
   - An **agent loop** (LangGraph, CrewAI, or raw function-calling) that **dynamically calls tools** to validate policy rules
   - **BONUS:** integrate a **voice pipeline** (OpenAI Realtime API, ElevenLabs, or LiveKit)
3. **Frontend UI**
   - A clean interface with a **customer chat interface** and/or a **microphone voice component**
   - Plus an **admin dashboard** showing **real-time agent reasoning logs**

### MAIN DELIVERABLE — Loom video (7–10 min)
Walk through:
- **Live Demo:** agent handling a **standard refund** AND an **edge case / policy violation** ("holding the line"). If voice implemented, show a live spoken interaction.
- **Code Tour:** repo architecture, tool orchestration, any voice-stream handling.
- **Reasoning Logs:** where the agent handles **failures/retries** (admin panel or terminal trace).
- Include the **public GitHub repo link + clean README** with the Loom.

---

## WHY THIS IS ALEX'S TO WIN (map to existing real work)
- **"Agent that holds the line on policy"** → this is exactly **doomcaller** (agent refuses/holds under adversarial pressure) + **role_guard** deterministic control.
- **"Real-time agent reasoning logs / where it fails & retries"** → **glass-box-alpha** (verifiable reasoning, receipts) + **argus** (in-app triage logs).
- **"Tool orchestration / agent loop validating rules"** → whole portfolio; his signature is *"models propose, a deterministic function owns the verdict"* — PERFECT for a refund-policy agent (LLM reads intent, deterministic policy engine decides).

## BUILD PLAN (draft)
- **Stack:** Python (FastAPI) backend + agent loop (raw function-calling or LangGraph) · simple React/Next.js or plain HTML frontend · SQLite/JSON for the 15-profile CRM.
- **Policy engine:** deterministic rule checks (his signature) — LLM extracts the refund request → tools fetch customer/order → **deterministic policy validator** approves/denies with cited rule → agent explains.
- **Admin dashboard:** live reasoning-log stream (each tool call, each rule check, retries) — his transparency wheelhouse.
- **Edge case to demo:** a refund that violates policy (e.g., outside return window / non-refundable item) where the agent **denies and holds the line** despite customer pushback.
- **Bonus voice:** ElevenLabs or OpenAI Realtime for a spoken demo (optional, adds polish).
- **README:** architecture diagram, how to run, design rationale (lead with the deterministic-verdict principle).
- **Loom:** demo standard + edge case → code tour → reasoning logs.

## STATUS
- [ ] Scaffold repo
- [ ] Mock CRM (15 profiles) + refund policy doc
- [ ] Agent loop + policy tools
- [ ] Frontend chat + admin reasoning-log dashboard
- [ ] (bonus) voice
- [ ] README
- [ ] Record 7–10 min Loom
- [ ] Submit GitHub + Loom via Wellfound
