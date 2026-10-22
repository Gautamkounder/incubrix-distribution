"""A fake partner platform for simulation mode. Set destination.config.simulate to force a failure."""
import hashlib

import httpx


def make_mock_transport() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        sim = request.headers.get("X-Simulate", "")
        if sim == "timeout":
            raise httpx.ReadTimeout("simulated timeout", request=request)
        if sim == "429":
            return httpx.Response(429, headers={"Retry-After": "30"}, json={"error": "slow down"})
        if sim == "401":
            return httpx.Response(401, json={"error": "token expired"})
        if sim == "422":
            return httpx.Response(422, json={"error": "content rejected by platform"})
        if sim == "503":
            return httpx.Response(503, json={"error": "unavailable"})
        if request.method == "POST":
            idem = request.headers.get("Idempotency-Key", "no-key")
            post_id = "sim-" + hashlib.sha1(idem.encode()).hexdigest()[:12]  # same key -> same post id
            return httpx.Response(201, json={"id": post_id, "url": f"https://partner.example/posts/{post_id}"})
        post_id = request.url.path.rstrip("/").split("/")[-1]
        if request.method == "DELETE":
            return httpx.Response(204)
        return httpx.Response(200, json={"id": post_id, "status": "live", "url": f"https://partner.example/posts/{post_id}"})

    return httpx.MockTransport(handler)
