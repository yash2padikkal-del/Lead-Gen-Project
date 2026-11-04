"""
Qualification rules for apparel-brand leads.

Missing or inconclusive evidence remains pending_enrichment.
Only confirmed disqualifiers are rejected.
Public business contact is optional.
"""

import re
from typing import Any
from urllib.parse import urlparse

FOLLOWER_LIMIT = 10_000

BLOCKED_HOSTS = {
    "instagram.com",
    "facebook.com",
    "fb.com",
    "tiktok.com",
    "youtube.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "pinterest.com",
    "threads.net",
    "wa.me",
    "whatsapp.com",
    "m.me",
    "play.google.com",
    "apps.apple.com",
    "google.com",
    "linktr.ee",
    "bit.ly",
    "tinyurl.com",
    "t.co",
    "amazon.com",
    "amazon.in",
    "flipkart.com",
    "myntra.com",
    "ajio.com",
    "meesho.com",
    "temu.com",
    "etsy.com",
}


def parse_follower_count(value: Any) -> int | None:
    """Parse numeric follower counts, including abbreviated values."""

    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        number = int(value)
        return number if number >= 0 else None

    text = str(value).strip().lower()
    text = text.replace(",", "").replace(" ", "")

    match = re.fullmatch(
        r"(\d+(?:\.\d+)?)([kmb]?)",
        text
    )

    if not match:
        return None

    multiplier = {
        "": 1,
        "k": 1_000,
        "m": 1_000_000,
        "b": 1_000_000_000,
    }

    number = int(
        float(match.group(1)) * multiplier[match.group(2)]
    )

    return number if number >= 0 else None


def normalise_instagram_handle(value: Any) -> str | None:
    """Accept handles, @handles and Instagram profile URLs."""

    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if "instagram.com" in text.lower():
        if "://" not in text:
            text = "https://" + text

        try:
            parsed = urlparse(text)

            host = (parsed.hostname or "").lower()

            if host not in {
                "instagram.com",
                "www.instagram.com",
            }:
                return None

            text = parsed.path.strip("/").split("/")[0]

        except ValueError:
            return None

    else:
        text = text.split("?", 1)[0].strip("/")

    text = text.lstrip("@")

    if not re.fullmatch(r"[A-Za-z0-9._]{1,30}", text):
        return None

    if text.lower() in {
        "p",
        "reel",
        "reels",
        "stories",
        "explore",
        "accounts",
        "direct",
    }:
        return None

    return text


def website_host(value: Any) -> str | None:
    """Return a valid first-party hostname, or None."""

    raw = str(value or "").strip()

    if not raw:
        return None

    if "://" not in raw:
        raw = "https://" + raw

    try:
        parsed = urlparse(raw)

        host = (
            parsed.hostname or ""
        ).lower().removeprefix("www.")

    except ValueError:
        return None

    if parsed.scheme not in {"http", "https"}:
        return None

    if not host or "." not in host:
        return None

    if any(
        host == blocked or host.endswith("." + blocked)
        for blocked in BLOCKED_HOSTS
    ):
        return None

    return host


def valid_first_party_website(value: Any) -> bool:
    return website_host(value) is not None


def qualify_lead(lead: dict[str, Any]) -> dict[str, Any]:

    reasons = []
    missing = []
    hard_disqualifiers = []

    # --------------------------------------------------
    # INSTAGRAM HANDLE
    # --------------------------------------------------

    handle_value = (
        lead.get("instagram_handle")
        or lead.get("instagram_url")
    )

    handle = normalise_instagram_handle(handle_value)

    # --------------------------------------------------
    # FOLLOWERS
    # --------------------------------------------------

    raw_followers = lead.get("instagram_followers")

    # Important: fall back when the primary value is None.
    if raw_followers is None:
        raw_followers = lead.get("follower_count")

    followers = parse_follower_count(raw_followers)

    # --------------------------------------------------
    # WEBSITE
    # --------------------------------------------------

    website = lead.get("website")

    verification = lead.get("website_verification") or {}

    if not isinstance(verification, dict):
        verification = {}

    apparel = lead.get("is_apparel_brand")

    # --------------------------------------------------
    # APPAREL VALIDATION
    # --------------------------------------------------

    if apparel is False:

        hard_disqualifiers.append(
            "Confirmed not to be an apparel brand"
        )

    elif apparel is not True:

        missing.append(
            "Apparel brand status is unverified"
        )

    # --------------------------------------------------
    # INSTAGRAM VALIDATION
    # --------------------------------------------------

    if not handle:

        if handle_value:

            hard_disqualifiers.append(
                "Instagram handle is invalid"
            )

        else:

            missing.append(
                "Instagram handle is missing"
            )

    # --------------------------------------------------
    # FOLLOWER VALIDATION
    # --------------------------------------------------

    if followers is None:

        missing.append(
            "Instagram follower count is unavailable"
        )

    elif followers >= FOLLOWER_LIMIT:

        hard_disqualifiers.append(
            f"Follower count is not below {FOLLOWER_LIMIT:,}"
        )

    # --------------------------------------------------
    # WEBSITE VALIDATION
    # --------------------------------------------------

    if not website:

        missing.append(
            "First-party website is missing"
        )

    elif not valid_first_party_website(website):

        hard_disqualifiers.append(
            "Website URL is invalid or points to a non-first-party platform"
        )

    else:

        website_status = verification.get("status")

        if website_status == "invalid":

            hard_disqualifiers.append(
                verification.get("reason")
                or "Website was confirmed invalid"
            )

        elif website_status != "verified":

            missing.append(
                verification.get("reason")
                or "Website could not be verified; retry required"
            )

    # --------------------------------------------------
    # FINAL DECISION
    # --------------------------------------------------

    reasons.extend(hard_disqualifiers)
    reasons.extend(missing)

    if hard_disqualifiers:
        status = "rejected"

    elif missing:
        status = "pending_enrichment"

    else:
        status = "qualified"

    result = dict(lead)

    result["instagram_handle"] = handle
    result["instagram_followers"] = followers

    result["qualified"] = status == "qualified"
    result["qualification_status"] = status

    result["hard_disqualifiers"] = hard_disqualifiers
    result["missing_information"] = missing
    result["qualification_reasons"] = reasons

    result["qualification_rule"] = (
        "confirmed_apparel_brand AND valid_instagram_handle "
        "AND known_instagram_followers < 10000 "
        "AND verified_first_party_website; "
        "public_business_contact_optional"
    )

    return result


# --------------------------------------------------
# TESTS
# --------------------------------------------------

if __name__ == "__main__":

    cases = [

        # Valid lead.
        (
            {
                "is_apparel_brand": True,
                "instagram_handle": "label",
                "instagram_followers": 9999,
                "website": "https://label.example",
                "website_verification": {
                    "status": "verified"
                }
            },
            "qualified"
        ),

        # Inconclusive website.
        (
            {
                "is_apparel_brand": True,
                "instagram_handle": "label",
                "instagram_followers": 9999,
                "website": "https://label.example",
                "website_verification": {
                    "status": "inconclusive",
                    "reason": "HTTP 429"
                }
            },
            "pending_enrichment"
        ),

        # Follower threshold.
        (
            {
                "is_apparel_brand": True,
                "instagram_handle": "label",
                "instagram_followers": 10000,
                "website": "https://label.example",
                "website_verification": {
                    "status": "verified"
                }
            },
            "rejected"
        ),

        # Confirmed non-apparel.
        (
            {
                "is_apparel_brand": False,
                "instagram_handle": "label",
                "instagram_followers": 100,
                "website": "https://label.example",
                "website_verification": {
                    "status": "verified"
                }
            },
            "rejected"
        ),

        # Follower count fallback.
        (
            {
                "is_apparel_brand": True,
                "instagram_handle": "label",
                "instagram_followers": None,
                "follower_count": "9.5K",
                "website": "https://label.example",
                "website_verification": {
                    "status": "verified"
                }
            },
            "qualified"
        ),

        # Missing evidence is pending.
        (
            {
                "is_apparel_brand": None,
                "instagram_handle": None,
                "instagram_followers": None,
                "website": None,
            },
            "pending_enrichment"
        ),
    ]

    for item, expected in cases:

        actual = qualify_lead(item)["qualification_status"]

        assert actual == expected, (
            f"Expected {expected}, got {actual}"
        )

    # Follower parsing tests.
    assert parse_follower_count("9.5K") == 9500
    assert parse_follower_count("10K") == 10000
    assert parse_follower_count("1.2M") == 1200000
    assert parse_follower_count("850") == 850

    # Instagram parsing tests.
    assert normalise_instagram_handle("@brand") == "brand"
    assert normalise_instagram_handle(
        "https://www.instagram.com/brand/"
    ) == "brand"

    print("All qualification tests passed.")