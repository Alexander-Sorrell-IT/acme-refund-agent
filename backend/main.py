"""FastAPI server: customer chat endpoint + live reasoning-log SSE stream + serves the UI."""
import os, json, asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import agent, logbus, crm

app = FastAPI(title="Acme Refund Agent")
FRONTEND = os.path.join(os.path.dirname(__file__), "..", "frontend")


@app.post("/chat")
async def chat(req: Request):
    body = await req.json()
    messages = body.get("messages", [])
    # run the (blocking) agent turn in a thread so the event loop stays free for SSE
    reply, updated = await asyncio.to_thread(agent.run_turn, messages)
    return JSONResponse({"reply": reply, "messages": updated})


@app.get("/logs")
async def logs():
    async def gen():
        async for evt in logbus.subscribe():
            yield f"data: {json.dumps(evt)}\n\n"
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/redteam")
async def run_redteam():
    import redteam
    report = await asyncio.to_thread(redteam.run_battery)
    return JSONResponse(report)


@app.post("/adversary")
async def run_adversary():
    # R2, live: improvised multi-turn adversary tries to talk the agent into a bad
    # refund on every deny/escalate target. Watch it fail in the reasoning log.
    import adversary
    report = await asyncio.to_thread(adversary.run)
    return JSONResponse(report)


@app.get("/enforcement")
async def enforcement_state():
    import enforcement
    return JSONResponse(enforcement.scorecard())


@app.get("/receipts")
async def receipts_list():
    import receipts
    return JSONResponse({"rows": receipts.all_receipts(), "verify": receipts.verify_chain(), "salt": receipts.SALT})


@app.get("/api/customers")
async def customers():
    # a directory the demo user can pull sample names/orders from
    return [{"customer_id": c["customer_id"], "name": c["name"], "email": c["email"],
             "orders": c["orders"]} for c in crm.all_customers()]


@app.get("/")
async def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))

@app.get("/admin")
async def admin():
    return FileResponse(os.path.join(FRONTEND, "admin.html"))

app.mount("/static", StaticFiles(directory=FRONTEND), name="static")
