import httpx, time, json
from pathlib import Path

with httpx.Client(base_url="http://127.0.0.1:9080/api", timeout=240) as c:
    r = c.post(
        "/auth/login", json={"email": "demo@raglab.local", "password": "RagLab2026!"}
    )
    r.raise_for_status()
    h = {"Authorization": "Bearer " + r.json()["token"]}
    conv = c.post("/conversations", headers=h).json()["id"]
    r = c.post(
        "/conversations/" + conv + "/messages",
        headers=h,
        json={
            "question": "According to 3M’s 2022 annual report, what were its net sales for 2022? Please give the amount, units and source.",
            "mode": "live",
            "documentIds": [],
            "idempotencyKey": "native-live-" + str(time.time_ns()),
        },
    )
    r.raise_for_status()
    rid = r.json()["id"]
    print("Native RAG run submitted", rid, flush=True)
    with c.stream("GET", "/runs/" + rid + "/events", headers=h) as stream:
        stream.raise_for_status()
        last_stage = ""
        for line in stream.iter_lines():
            if not line.startswith("data:"):
                continue
            current = json.loads(line[5:])
            trace = current.get("trace") or []
            if trace and trace[-1]["stage"] != last_stage:
                last_stage = trace[-1]["stage"]
                print("Stage:", last_stage, flush=True)
            final = current
    print("STATUS", final["status"], flush=True)
    print("ANSWER", final.get("answer", "")[:1200], flush=True)
    print("CITATIONS", len(final.get("citations", [])), flush=True)
    print("ERROR", final.get("error"), flush=True)
    Path("native-live-result.json").write_text(
        json.dumps(final, ensure_ascii=False, indent=2)
    )
    assert final["status"] == "SUCCEEDED", final.get("error")
    assert final["citations"], "Expected original RAG citations"
