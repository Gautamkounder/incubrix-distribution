"""Offline mock for Ghost and Lemmy platforms."""
import json
import re
import itertools

import httpx

def make_cms_transport() -> httpx.MockTransport:
    ids = itertools.count(1)
    ghost_posts: dict[str, dict] = {}
    lemmy_posts: dict[str, dict] = {}

    def body_of(req: httpx.Request) -> dict:
        try:
            return json.loads(req.content or b"{}")
        except Exception:
            return {}

    def handler(req: httpx.Request) -> httpx.Response:
        path, method = req.url.path, req.method

        # ---- Ghost ----
        if path == "/ghost/api/admin/posts/" and method == "POST":
            if not req.headers.get("Authorization"):
                return httpx.Response(401, json={"errors": [{"message": "Access denied"}]})
            data = body_of(req)
            posts = data.get("posts", [])
            if not posts or not posts[0].get("title"):
                return httpx.Response(422, json={"errors": [{"message": "Title required"}]})
            pid = str(next(ids))
            ghost_posts[pid] = {"id": pid, "title": posts[0]["title"], "status": "published", "url": f"https://blog.example/post-{pid}"}
            return httpx.Response(201, json={"posts": [ghost_posts[pid]]})

        m_g = re.fullmatch(r"/ghost/api/admin/posts/([^/]+)/", path)
        if m_g:
            pid = m_g.group(1)
            if pid not in ghost_posts:
                return httpx.Response(404, json={"errors": [{"message": "Not found"}]})
            if method == "GET":
                return httpx.Response(200, json={"posts": [ghost_posts[pid]]})
            if method == "DELETE":
                ghost_posts.pop(pid, None)
                return httpx.Response(204)

        # ---- Lemmy ----
        if path == "/api/v3/post" and method == "POST":
            if not req.headers.get("Authorization"):
                return httpx.Response(401, json={"error": "not_logged_in"})
            data = body_of(req)
            if not data.get("name"):
                return httpx.Response(422, json={"error": "missing_name"})
            pid = str(next(ids))
            lemmy_posts[pid] = {"id": int(pid), "name": data["name"], "deleted": False}
            return httpx.Response(200, json={"post_view": {"post": lemmy_posts[pid]}})

        if path == "/api/v3/post" and method == "GET":
            query = req.url.query.decode("utf-8") if isinstance(req.url.query, bytes) else req.url.query
            m_pid = re.search(r"id=(\d+)", query)
            if m_pid:
                pid = m_pid.group(1)
                if pid in lemmy_posts:
                    if lemmy_posts[pid]["deleted"]:
                        return httpx.Response(200, json={"post_view": {"post": {"id": int(pid), "deleted": True}}})
                    return httpx.Response(200, json={"post_view": {"post": lemmy_posts[pid]}})
            return httpx.Response(404, json={"error": "could_not_find_post"})

        if path == "/api/v3/post/delete" and method == "POST":
            data = body_of(req)
            pid = str(data.get("post_id"))
            if pid in lemmy_posts:
                lemmy_posts[pid]["deleted"] = True
                return httpx.Response(200, json={"post_view": {"post": lemmy_posts[pid]}})
            return httpx.Response(404, json={"error": "post_not_found"})

        return httpx.Response(404, json={"error": "not_found"})

    return httpx.MockTransport(handler)
