"""Content tailoring: dynamically adapt text based on destination rules and relevance."""
from app.schemas import Destination, Rendition

def tailor_rendition(rendition: Rendition, destination: Destination) -> Rendition:
    """Adapts the rendition title and body based on the platform type."""
    adapted_title = rendition.title
    adapted_body = rendition.body

    # Format for forums (Discourse, Lemmy) -> Make it conversational
    if destination.connector_key in ["discourse", "lemmy"]:
        if not adapted_title.startswith("Discussion:"):
            adapted_title = f"Discussion: {adapted_title}"
        if "What do you think?" not in adapted_body:
            adapted_body = f"{adapted_body}\n\nWhat do you think? Let's discuss."

    # Format for technical blogs (Dev.to, Hashnode) -> Add canonical links
    if destination.connector_key in ["devto", "hashnode"]:
        if rendition.canonical_url and rendition.canonical_url not in adapted_body:
            adapted_body = f"{adapted_body}\n\n*Originally published at {rendition.canonical_url}*"

    # Format for chat/Slack -> Keep it brief and bold
    if destination.connector_key == "slack":
        if len(adapted_body) > 300:
            adapted_body = adapted_body[:297] + "..."

    return Rendition(
        title=adapted_title,
        body=adapted_body,
        tags=rendition.tags,
        media_urls=rendition.media_urls,
        canonical_url=rendition.canonical_url,
        is_promotional=rendition.is_promotional,
        ai_generated=rendition.ai_generated
    )
