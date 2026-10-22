"""Assisted connector: where automation is not allowed, build a ready-to-post pack for a person."""
from app.connectors.base import Connector
from app.schemas import Destination, Rendition


class AssistedConnector(Connector):
    def build_assist_pack(self, rendition: Rendition, destination: Destination) -> dict:
        cfg = destination.config
        rules = cfg.get("rules") or {}
        hashtags = " ".join(f"#{t.lstrip('#')}" for t in rendition.tags)
        caption = f"{rendition.title}\n\n{rendition.body}" + (f"\n\n{hashtags}" if hashtags else "")
        if rendition.canonical_url:
            caption += f"\n\nRead more: {rendition.canonical_url}"
        checklist = [f"Read the community rules first: {cfg.get('rules_url', '(add rules_url to the destination)')}"]
        if rules.get("self_promo_allowed") is False:
            checklist.append("Self-promotion is NOT allowed here. Post only if the content is genuinely non-promotional.")
        cap = rules.get("frequency_cap")
        if cap:
            checklist.append(f"Posting limit: {cap.get('max_posts')} post(s) per {cap.get('window_hours')} hours. "
                             "Check you have not posted recently.")
        if rendition.ai_generated or rules.get("disclosure_required"):
            checklist.append("Disclose that AI helped create this content, as the community requires.")
        checklist.append("After posting, paste the live URL back into IncuBrix.")
        files = [
            {"name": "caption.txt", "content": caption, "content_type": "text/plain"},
            {"name": "post.md", "content": f"# {rendition.title}\n\n{rendition.body}\n", "content_type": "text/markdown"},
        ]
        if rendition.media_urls:
            files.append({"name": "media_links.txt", "content": "\n".join(rendition.media_urls), "content_type": "text/plain"})
        return {"files": files, "caption": caption, "deep_link": cfg.get("submit_url"), "checklist": checklist}
