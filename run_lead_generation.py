import json
from pathlib import Path
from urllib.parse import urlparse

from enrichment.pipeline import pipeline
from enrichment.providers.facebook_ads_library import FacebookAdsLibraryProvider


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"

VERIFICATION_FILE = DATA_DIR / "apparel_verification.json"
OUTPUT_FILE = DATA_DIR / "lead_results.json"

FOLLOWER_LIMIT = 10_000

# These destinations are not treated as brand websites.
EXCLUDED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "whatsapp.com",
    "api.whatsapp.com",
    "google.com",
    "share.google",
    "youtube.com",
    "youtu.be",
    "amazon.in",
    "amazon.com",
    "flipkart.com",
    "myntra.com",
}


def load_apparel_verifications():
    """
    Load manual apparel confirmations keyed by Facebook page ID.

    Example:
    {
        "123456789": true
    }

    Only set a page ID to true after confirming that the advertiser
    is an independent apparel brand, rather than a marketplace,
    reseller, event organiser, or unrelated retailer.
    """

    if not VERIFICATION_FILE.exists():
        VERIFICATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        VERIFICATION_FILE.write_text(
            "{}\n",
            encoding="utf-8",
        )
        return {}

    with VERIFICATION_FILE.open("r", encoding="utf-8") as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise ValueError(
            f"{VERIFICATION_FILE} must contain a JSON object."
        )

    return {
        str(page_id): value is True
        for page_id, value in data.items()
    }


def get_domain(url):
    if not isinstance(url, str) or not url.strip():
        return None

    try:
        parsed = urlparse(
            url if "://" in url else f"https://{url}"
        )
        domain = (parsed.hostname or "").lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain or None

    except ValueError:
        return None


def is_excluded_domain(domain):
    if not domain:
        return True

    return any(
        domain == excluded or domain.endswith("." + excluded)
        for excluded in EXCLUDED_DOMAINS
    )


def choose_website(advertiser):
    """
    Choose a plausible destination domain from the advertiser's ads.

    This is a candidate URL, not proof that the site belongs to the
    advertiser. Domain matching and apparel verification remain
    separate checks.
    """

    urls = advertiser.get("websites", [])

    for url in urls:
        domain = get_domain(url)

        if not domain or is_excluded_domain(domain):
            continue

        return url

    return None


def build_lead(advertiser, apparel_verified):
    website = choose_website(advertiser)

    return {
        "brand_name": advertiser.get("brand_name"),
        "website": website,
        "instagram_handle": advertiser.get("instagram_handle"),
        "follower_count": advertiser.get("followers"),
        "is_apparel_brand": apparel_verified,
        "facebook_page_id": advertiser.get("page_id"),
        "facebook_url": advertiser.get("facebook_url"),
        "source": "facebook_ads_library",
    }


def process_advertisers():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    provider = FacebookAdsLibraryProvider()
    verifications = load_apparel_verifications()

    output = []

    for advertiser in provider.get_advertisers():
        page_id = str(advertiser.get("page_id") or "")
        brand_name = advertiser.get("brand_name")
        followers = advertiser.get("followers")
        website = choose_website(advertiser)
        instagram_handle = advertiser.get("instagram_handle")
        apparel_verified = verifications.get(page_id, False)

        base = {
            "brand_name": brand_name,
            "facebook_page_id": page_id,
            "facebook_url": advertiser.get("facebook_url"),
            "website": website,
            "instagram_handle": instagram_handle,
            "followers": followers,
            "active_ads": advertiser.get("active_ads"),
            "ad_duration": advertiser.get("ad_duration"),
            "source": "facebook_ads_library",
        }

        # Apply the hard follower threshold before website crawling.
        if followers is not None and followers >= FOLLOWER_LIMIT:
            output.append({
                **base,
                "status": "rejected",
                "reason": "Instagram follower count meets or exceeds 10,000.",
            })
            continue

        if followers is None:
            output.append({
                **base,
                "status": "pending_enrichment",
                "reason": "Instagram follower count is unavailable.",
            })
            continue

        if not instagram_handle:
            output.append({
                **base,
                "status": "pending_enrichment",
                "reason": "Instagram handle is unavailable.",
            })
            continue

        if not website:
            output.append({
                **base,
                "status": "pending_enrichment",
                "reason": "No plausible brand website found in ad destinations.",
            })
            continue

        # Do not infer apparel status from a generic Facebook category
        # such as Shopping. Require explicit verification before scoring.
        if not apparel_verified:
            output.append({
                **base,
                "status": "pending_apparel_verification",
                "reason": (
                    "Advertiser has not been verified as an independent "
                    "apparel brand."
                ),
            })
            continue

        lead = build_lead(advertiser, apparel_verified=True)
        result = pipeline.process_lead(lead)

        output.append({
            **base,
            **result,
            "facebook_page_id": page_id,
            "source": "facebook_ads_library",
        })

    with OUTPUT_FILE.open("w", encoding="utf-8") as file:
        json.dump(output, file, indent=2, ensure_ascii=False)

    counts = {}
    for item in output:
        status = item.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    print("\nLEAD GENERATION RUN COMPLETE")
    print(f"Advertisers processed: {len(output)}")
    print(f"Results saved to: {OUTPUT_FILE}")
    print("\nStatus summary:")

    for status, count in sorted(counts.items()):
        print(f"  {status}: {count}")

    print("\nAdvertiser results:")
    for item in output:
        print(
            f"  {item.get('brand_name')} | "
            f"{item.get('followers')} followers | "
            f"{item.get('status')}"
        )


if __name__ == "__main__":
    process_advertisers()
