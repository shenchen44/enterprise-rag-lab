"""Live local-stack smoke test; creates isolated test users and private documents."""

import httpx, uuid, time, json
from pathlib import Path

BASE = "http://127.0.0.1:9080/api"
c = httpx.Client(base_url=BASE, timeout=240)
checks = []


def check(name, condition):
    assert condition, name
    checks.append(name)
    print("PASS", name, flush=True)


def account():
    r = c.post(
        "/auth/register",
        json={
            "email": f"qa-{uuid.uuid4().hex}@example.com",
            "name": "平台验证",
            "password": "LocalTest2026!",
        },
    )
    r.raise_for_status()
    return {"Authorization": "Bearer " + r.json()["token"]}


a, b = account(), account()
overview = c.get("/overview", headers=a)
overview.raise_for_status()
overview = overview.json()
check("real benchmark catalog", len(overview["documents"]) >= 10)
check(
    "real evaluation reports",
    len(overview["evaluations"]) == 3
    and any(
        abs(x["answerCorrectness"] - 0.5792766536857288) < 1e-8
        for x in overview["evaluations"]
        if x["id"] == "optimized"
    ),
)
u = c.post(
    "/documents",
    headers=a,
    files={
        "file": (
            "orion-research.txt",
            b"Orion Corporation reported revenue of 42 million dollars for fiscal year 2025. Revenue increased from 35 million dollars in fiscal year 2024. This document belongs only to its uploader.",
            "text/plain",
        )
    },
)
u.raise_for_status()
doc = u.json()["id"]
for _ in range(60):
    docs = c.get("/documents", headers=a).json()
    d = next(x for x in docs if x["id"] == doc)
    if d["status"] != "PROCESSING":
        break
    time.sleep(0.25)
check("private upload indexed", d["status"] == "READY" and d["chunks"] > 0)
check(
    "document ownership",
    c.get("/documents/" + doc + "/file", headers=b).status_code == 404,
)
conv = c.post("/conversations", headers=a).json()["id"]
body = {
    "question": "What was Orion revenue in fiscal year 2025?",
    "mode": "evidence",
    "documentIds": [doc],
    "idempotencyKey": uuid.uuid4().hex,
}
r = c.post("/conversations/" + conv + "/messages", headers=a, json=body)
r.raise_for_status()
run = r.json()["id"]
r2 = c.post("/conversations/" + conv + "/messages", headers=a, json=body)
r2.raise_for_status()
check("idempotent request", r2.json()["id"] == run)
body["question"] = "different input"
check(
    "idempotency conflict",
    c.post("/conversations/" + conv + "/messages", headers=a, json=body).status_code
    == 409,
)
with c.stream("GET", "/runs/" + run + "/events", headers=a) as stream:
    stream.raise_for_status()
    snapshots = [
        json.loads(line[5:]) for line in stream.iter_lines() if line.startswith("data:")
    ]
check(
    "SSE snapshots and terminal event",
    len(snapshots) > 0 and snapshots[-1]["status"] == "SUCCEEDED",
)
final = snapshots[-1]
check(
    "grounded answer and citations",
    "42 million" in final["answer"] and final["citations"][0]["documentId"] == doc,
)
check(
    "conversation ownership",
    c.get("/conversations/" + conv + "/messages", headers=b).status_code == 404,
)
check("run ownership", c.get("/runs/" + run, headers=b).status_code == 404)
msgs = c.get("/conversations/" + conv + "/messages", headers=a).json()
check("persistent messages", len(msgs) == 2 and msgs[-1]["status"] == "SUCCEEDED")
check(
    "file validation",
    c.post(
        "/documents",
        headers=a,
        files={"file": ("fake.pdf", b"not PDF", "application/pdf")},
    ).status_code
    == 400,
)
check(
    "evaluation detail",
    len(c.get("/evaluations/optimized", headers=a).json()["rows"]) == 46,
)
c.patch(
    "/conversations/" + conv, headers=a, json={"title": "验证后重命名"}
).raise_for_status()
check(
    "rename conversation",
    any(
        x["id"] == conv and x["title"] == "验证后重命名"
        for x in c.get("/conversations", headers=a).json()
    ),
)
c.post("/auth/logout", headers=b).raise_for_status()
check("logout revokes token", c.get("/auth/me", headers=b).status_code == 401)
result = {
    "checks": checks,
    "passed": len(checks),
    "privateDocumentId": doc,
    "conversationId": conv,
    "runId": run,
}
Path("e2e-results.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
print("All local-stack checks passed.", flush=True)
