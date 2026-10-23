import json
import itertools
import httpx

def make_advanced_transport() -> httpx.MockTransport:
    ids = itertools.count(1)
    posts = {}

    def body_of(req: httpx.Request) -> dict:
        try:
            return json.loads(req.content or b"{}")
        except Exception:
            return {}

    def handler(req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method
        
        # Mock Hashnode
        if "/publish" in path and method == "POST":
            pid = str(next(ids))
            posts[pid] = True
            return httpx.Response(201, json={"post_id": pid, "url": f"https://hashnode.example/{pid}"})
        if "/posts/" in path and method == "GET":
            return httpx.Response(200, json={"published": True, "url": ""})
        if "/posts/" in path and method == "DELETE":
            return httpx.Response(200, json={})

        # Mock Slack
        if "/chat.postMessage" in path and method == "POST":
            ts = f"1600000000.{next(ids)}"
            return httpx.Response(200, json={"ok": True, "ts": ts})
        if "/chat.delete" in path and method == "POST":
            return httpx.Response(200, json={"ok": True})

        # Mock MRSS
        if "/feed/items" in path and method == "POST":
            iid = str(next(ids))
            return httpx.Response(201, json={"item_id": iid, "url": f"https://mrss.example/{iid}"})
        if "/feed/items/" in path and method == "GET":
            return httpx.Response(200, json={"active": True, "url": ""})
        if "/feed/items/" in path and method == "DELETE":
            return httpx.Response(200, json={})

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)
