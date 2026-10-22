"""Posting-rules engine. Pure functions, so it is easy to test and to reuse (preflight check, certification).

A destination's rules live in its config (data, not code):

    "rules": {
        "frequency_cap": {"max_posts": 1, "window_hours": 168},   # at most 1 post per week
        "self_promo_allowed": false,
        "link_policy": {"allowed": true, "max_links": 2},
        "disclosure_required": true                                # AI-content disclosure
    }

Result of evaluate(): allow (maybe with a changed rendition), block (with a reason) or reschedule (with a date).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from app.connectors.base import LINK_RE
from app.errors import AppError, ErrorCode
from app.schemas import Destination, Rendition

DISCLOSURE_LINE = "Disclosure: this post was created with AI assistance."


@dataclass
class RuleViolation:
    rule: str
    code: ErrorCode
    message: str
    details: dict = field(default_factory=dict)

    def to_error(self, retryable: bool | None = None) -> AppError:
        return AppError(self.code, self.message, details={"rule": self.rule, **self.details}, retryable=retryable)


@dataclass
class RuleDecision:
    action: str  # allow | block | reschedule
    rendition: Rendition
    violation: RuleViolation | None = None
    reschedule_at: datetime | None = None
    notes: list[str] = field(default_factory=list)  # things we changed or noticed, reported as warnings
    checked: list[str] = field(default_factory=list)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _rules(destination: Destination) -> dict:
    rules = destination.config.get("rules") or {}
    if not isinstance(rules, dict):
        raise AppError(ErrorCode.VALIDATION_ERROR, "destination.config.rules must be an object",
                       details={"destination": destination.id})
    return rules


def cap_window_hours(destination: Destination) -> float | None:
    cap = _rules(destination).get("frequency_cap")
    if not cap:
        return None
    try:
        return float(cap["window_hours"])
    except (KeyError, TypeError, ValueError):
        raise AppError(ErrorCode.VALIDATION_ERROR, "frequency_cap needs max_posts and window_hours",
                       details={"destination": destination.id})


def _links(rendition: Rendition) -> set[str]:
    found = {u.rstrip(".,);") for u in LINK_RE.findall(rendition.body)}
    if rendition.canonical_url:
        found.add(rendition.canonical_url)
    return found


def evaluate(rendition: Rendition, destination: Destination, recent_posts: list[datetime], now: datetime) -> RuleDecision:
    """recent_posts: times of our earlier successful posts to this destination (inside the cap window)."""
    rules = _rules(destination)
    checked: list[str] = []
    notes: list[str] = []

    # 1. Self-promotion: a promotional post to a no-promotion destination is blocked (waiting will not fix it).
    if "self_promo_allowed" in rules:
        checked.append("self_promotion")
        if rendition.is_promotional and rules["self_promo_allowed"] is False:
            v = RuleViolation("self_promotion", ErrorCode.DEST_RULE_SELF_PROMOTION,
                              "This destination does not allow self-promotion and the post is marked promotional",
                              {"destination": destination.id})
            return RuleDecision("block", rendition, violation=v, checked=checked)

    # 2. Link policy.
    policy = rules.get("link_policy")
    if policy:
        checked.append("link_policy")
        links = _links(rendition)
        if policy.get("allowed") is False and links:
            v = RuleViolation("link_policy", ErrorCode.DEST_RULE_LINK_POLICY, "This destination does not allow links",
                              {"links": sorted(links)})
            return RuleDecision("block", rendition, violation=v, checked=checked)
        max_links = policy.get("max_links")
        if max_links is not None and len(links) > int(max_links):
            v = RuleViolation("link_policy", ErrorCode.DEST_RULE_LINK_POLICY,
                              f"Too many links: {len(links)} (limit {max_links})",
                              {"limit": int(max_links), "actual": len(links), "links": sorted(links)})
            return RuleDecision("block", rendition, violation=v, checked=checked)

    # 3. Frequency cap: reschedule to the moment a slot opens.
    window = cap_window_hours(destination)
    if window is not None:
        checked.append("frequency_cap")
        cap = rules["frequency_cap"]
        try:
            max_posts = int(cap["max_posts"])
        except (KeyError, TypeError, ValueError):
            raise AppError(ErrorCode.VALIDATION_ERROR, "frequency_cap needs max_posts and window_hours",
                           details={"destination": destination.id})
        horizon = now - timedelta(hours=window)
        inside = sorted(_aware(t) for t in recent_posts if _aware(t) > horizon)
        if len(inside) >= max_posts:
            slot_opens = inside[len(inside) - max_posts] + timedelta(hours=window)
            v = RuleViolation("frequency_cap", ErrorCode.DEST_RULE_FREQUENCY_CAP,
                              f"Frequency cap reached ({max_posts} post(s) per {window:g} hours)",
                              {"max_posts": max_posts, "window_hours": window, "posts_in_window": len(inside),
                               "reschedule_at": slot_opens.isoformat()})
            return RuleDecision("reschedule", rendition, violation=v, reschedule_at=slot_opens, checked=checked)

    # 4. AI-content disclosure: add the line (once) and say so.
    if rules.get("disclosure_required"):
        checked.append("ai_disclosure")
        if rendition.ai_generated and DISCLOSURE_LINE not in rendition.body:
            rendition = rendition.model_copy(update={"body": f"{rendition.body.rstrip()}\n\n{DISCLOSURE_LINE}"})
            notes.append("ai_disclosure: added the required AI-content disclosure line")

    return RuleDecision("allow", rendition, notes=notes, checked=checked)
