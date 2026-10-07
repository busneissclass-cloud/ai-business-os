#!/usr/bin/env python3
"""Create a GitHub repo (if needed) and push a local dir as a commit.
Uses the user-connected `custom.github` credential via authd surrogate.
Usage: gh_push.py --repo ai-business-os --dir ~/workspace/ai-business-os --message "..." [--private]"""
import argparse, base64, json, os, sys, urllib.request, urllib.error

sys.path.insert(0, "/opt/hatch/skills/skill-creator/bin")
from dynamic_credentials import add_surrogate_to_request, read_json_response

API = "https://api.github.com"
HOSTS = ("api.github.com", "github.com")
CRED = "custom.github"
SKIP_DIRS = {".venv", "__pycache__", ".pytest_cache", ".git", "backups", "node_modules"}
SKIP_EXT = {".db", ".pyc"}

def api(method, path, payload=None):
    data = None
    headers = {"Accept": "application/vnd.github+json",
               "X-GitHub-Api-Version": "2022-11-28", "User-Agent": "muse-agent-deployer"}
    if payload is not None:
        data = json.dumps(payload).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, headers=headers, method=method)
    add_surrogate_to_request(req, CRED, allowed_hosts=HOSTS)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            return resp.status, read_json_response(resp)
    except urllib.error.HTTPError as exc:
        try: body = json.loads(exc.read().decode() or "{}")
        except Exception: body = {}
        return exc.code, body

def collect(root):
    files = []
    for dirpath, dirnames, names in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for n in names:
            if n == ".env" or any(n.endswith(e) for e in SKIP_EXT):
                continue
            full = os.path.join(dirpath, n)
            files.append((os.path.relpath(full, root), full))
    return sorted(files)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dir", required=True)
    ap.add_argument("--message", required=True)
    ap.add_argument("--private", action="store_true")
    a = ap.parse_args()

    s, me = api("GET", "/user")
    if s != 200:
        print(json.dumps({"ok": False, "error": "auth failed", "status": s}))
        return 1
    owner = me["login"]
    R = f"/repos/{owner}/{a.repo}"

    s, repo = api("GET", R)
    if s == 404:
        s, repo = api("POST", "/user/repos", {
            "name": a.repo, "private": a.private,
            "description": "AI Business OS — autonomous lead-gen & business agent (FastAPI + 7 agents, shadow-safe)",
            "auto_init": False})
        if s not in (200, 201):
            print(json.dumps({"ok": False, "error": "repo create failed", "status": s, "body": repo}))
            return 1
        print(f"repo created: {repo['html_url']}")
    else:
        print(f"repo exists: {repo['html_url']}")

    # current main ref (if any)
    s, ref = api("GET", f"{R}/git/ref/heads/main")
    parent_sha = ref["object"]["sha"] if s == 200 else None

    files = collect(a.dir)
    print(f"uploading {len(files)} files...")
    entries = []
    for rel, full in files:
        with open(full, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode()
        s, blob = api("POST", f"{R}/git/blobs", {"content": b64, "encoding": "base64"})
        if s != 201:
            print(json.dumps({"ok": False, "error": f"blob failed {rel}", "status": s}))
            return 1
        entries.append({"path": rel, "mode": "100644", "type": "blob", "sha": blob["sha"]})
    s, tree = api("POST", f"{R}/git/trees", {"tree": entries})
    if s != 201:
        print(json.dumps({"ok": False, "error": "tree failed", "status": s}))
        return 1
    parents = [parent_sha] if parent_sha else []
    s, commit = api("POST", f"{R}/git/commits",
                    {"message": a.message, "tree": tree["sha"], "parents": parents})
    if s != 201:
        print(json.dumps({"ok": False, "error": "commit failed", "status": s, "body": commit}))
        return 1
    if parent_sha:
        s, _ = api("PATCH", f"{R}/git/ref/heads/main", {"sha": commit["sha"]})
        if s != 200:
            print(json.dumps({"ok": False, "error": "ref update failed", "status": s}))
            return 1
    else:
        s, _ = api("POST", f"{R}/git/refs", {"ref": "refs/heads/main", "sha": commit["sha"]})
        if s != 201:
            print(json.dumps({"ok": False, "error": "ref create failed", "status": s}))
            return 1
    print(json.dumps({"ok": True, "repo": repo["html_url"], "commit": commit["sha"][:7]}))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
