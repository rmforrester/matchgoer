"""Read-only deployment provenance for the existing operational monitor.

No provider/fixture calls. Missing metadata or access is a warning, never PASS.
Use the existing project/environment token only when separately configured for
the monitor; this module does not create credentials or change service settings.
"""
import json
import os
import re
import urllib.request

PROJECT = "38e29e99-af66-49d7-afe1-5c8c4a99ca83"
ENVIRONMENT = "f38d1bc9-55ad-46ca-bc33-4fe27786a124"
SERVICES = {
    "api": "b6809ca3-5034-4c1d-806e-e4657419152e",
    "writer": "5c146d13-2a71-46d9-9a2b-04b502ab7e51",
    "monitor": "899833e9-4773-440e-b80a-521435a6c010",
    "backup": "c26af78a-fb1e-4c86-a4d7-92c4cceb9966",
    "photo-cleanup": "3579a8a3-03c7-45b3-b64a-905127aff728",
}
REPOSITORY = "rmforrester/matchgoer"


def read_json(url, *, headers=None, data=None):
    request = urllib.request.Request(url, data=data, headers={
        "User-Agent": "Matchgoer-SourceContinuity/1.0", **(headers or {})})
    with urllib.request.urlopen(request, timeout=15) as response:
        raw = response.read(2_000_001)
    if len(raw) > 2_000_000:
        raise ValueError("SOURCE_METADATA_TOO_LARGE")
    return json.loads(raw)


def assess(deployments, master, compare):
    items = []
    for name, deployment in deployments.items():
        sha = deployment.get("revision")
        row = {"service": name, "deployment_id": deployment.get("id"), "revision": sha}
        if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{40}", sha):
            row.update(status="FAIL", reason="COMMIT_PROVENANCE_UNAVAILABLE")
        else:
            try:
                ancestor = compare(sha, master).get("merge_base_commit", {}).get("sha") == sha
                row.update(status="PASS" if ancestor else "FAIL",
                           reason="CANONICAL_ANCESTOR" if ancestor else "NOT_REACHABLE_FROM_MASTER")
            except Exception:
                row.update(status="FAIL", reason="ANCESTRY_UNVERIFIED")
        items.append(row)
    passed = bool(items) and all(x["status"] == "PASS" for x in items)
    return {"status": "PASS" if passed else "FAIL", "master_revision": master, "services": items}


def check_from_environment(env=os.environ, fetch=read_json):
    token = env.get("RAILWAY_TOKEN")
    if not token:
        return {"status": "FAIL", "reason": "DEPLOYMENT_METADATA_ACCESS_UNAVAILABLE", "services": []}
    try:
        fields = " ".join('s' + str(i) + ':serviceInstance(environmentId:"' + ENVIRONMENT +
                          '",serviceId:"' + sid + '"){latestDeployment{id meta}}'
                          for i, sid in enumerate(SERVICES.values()))
        response = fetch("https://backboard.railway.com/graphql/v2",
                         headers={"Project-Access-Token": token, "Content-Type": "application/json"},
                         data=json.dumps({"query": "query {" + fields + "}"}).encode())
        if response.get("errors"):
            raise ValueError("METADATA_ACCESS_FAILED")
        deployments = {}
        for i, name in enumerate(SERVICES):
            d = response["data"]["s" + str(i)]["latestDeployment"]
            meta = d.get("meta") or {}
            meta = json.loads(meta) if isinstance(meta, str) else meta
            deployments[name] = {"id": d["id"], "revision": meta.get("commitHash")}
        base = "https://api.github.com/repos/" + REPOSITORY
        master = fetch(base + "/git/ref/heads/master")["object"]["sha"]
        if not re.fullmatch(r"[0-9a-f]{40}", master):
            raise ValueError("INVALID_MASTER_REVISION")
        return assess(deployments, master,
                      lambda sha, tip: fetch(base + "/compare/" + sha + "..." + tip))
    except Exception:
        return {"status": "FAIL", "reason": "SOURCE_CONTINUITY_UNVERIFIED", "services": []}


def extend_alert(payload, result):
    if result.get("status") == "PASS":
        return payload
    payload = dict(payload) if payload else {
        "subject": "[AMBER] Matchgoer production source continuity", "text": ""}
    text = "\nPRODUCTION SOURCE CONTINUITY: FAIL\n"
    text += result.get("reason", "One or more deployed revisions are unverified or outside canonical master.")
    payload["text"] = payload.get("text", "") + text
    return payload
