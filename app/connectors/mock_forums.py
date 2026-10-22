"""Offline mock of Discourse and Dev.to, so these connectors run and certify without network or accounts."""
import itertools
import json
import re
from datetime import datetime, timezone

import httpx


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "post"


def make_forum_transport() -> httpx.MockTransport:
    ids = itertools.count(1)
    topics: dict[str, dict] = {}
    articles: dict[str, dict] = {}

    def body_of(request: httpx.Request) -> dict:
        try:
            return json.loads(request.content or b"{}")
        except ValueError:
            return {}

    def handler(request: httpx.Request) -> httpx.Response:
        path, method = request.url.path, request.method

        # ---- Discourse ----
        if path == "/posts.json" and method == "POST":
            if not request.headers.get("Api-Key"):
                return httpx.Response(403, json={"errors": ["You are not permitted to view the requested resource."]})
            data = body_of(request)
            if not data.get("title") or not data.get("raw"):
                return httpx.Response(422, json={"errors": ["title and raw are required"]})
            tid = next(ids)
            topics[str(tid)] = {"id": tid, "slug": _slug(data["title"]), "deleted_at": None}
            return httpx.Response(200, json={"id": tid * 10, "topic_id": tid, "topic_slug": topics[str(tid)]["slug"]})
        m = re.fullmatch(r"/t/(\d+)\.json", path)
        if m:
            topic = topics.get(m.group(1))
            if topic is None:
                return httpx.Response(404, json={"errors": ["not found"]})
            if method == "GET":
                return httpx.Response(200, json=topic)
            if method == "DELETE":
                topic["deleted_at"] = datetime.now(timezone.utc).isoformat()  # staff still see soft-deleted topics
                return httpx.Response(200, json={})

        # ---- Dev.to ----
        if path == "/api/articles" and method == "POST":
            if not request.headers.get("api-key"):
                return httpx.Response(401, json={"error": "unauthorized", "status": 401})
            article = body_of(request).get("article") or {}
            if not article.get("title"):
                return httpx.Response(422, json={"error": "title can't be blank", "status": 422})
            aid = next(ids)
            articles[str(aid)] = {"id": aid, "published": bool(article.get("published")),
                                  "url": f"https://dev.to/mock/{_slug(article['title'])}-{aid}"}
            return httpx.Response(201, json=articles[str(aid)])
        m = re.fullmatch(r"/api/articles/(\d+)", path)
        if m:
            art = articles.get(m.group(1))
            if method == "GET":
                if art is None or not art["published"]:  # like the real API: unpublished articles are not public
                    return httpx.Response(404, json={"error": "not found", "status": 404})
                return httpx.Response(200, json=art)
            if method == "PUT":
                if art is None:
                    return httpx.Response(404, json={"error": "not found", "status": 404})
                art["published"] = bool((body_of(request).get("article") or {}).get("published", art["published"]))
                return httpx.Response(200, json=art)

        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)