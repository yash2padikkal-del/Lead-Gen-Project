"""
Streetwear Lead-Gen Monitor

Playwright Meta Ad Library
    -> Advertiser aggregation
    -> Enrichment pipeline
    -> ANN inference
    -> Airtable

No deterministic priority scoring.
Incomplete leads remain pending_enrichment.
"""

import json
import os
import re
import subprocess
import sys
import time
import uuid

from pathlib import Path
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv

from excel_export import export_to_excel

load_dotenv()

# ============================================================
# CONFIGURATION
# ============================================================

ROOT = Path(__file__).resolve().parent

AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")

AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")

AIRTABLE_TABLE_NAME = os.environ.get(
    "AIRTABLE_TABLE_NAME",
    "Leads"
)

SCRAPER_REPO = Path(
    os.environ.get(
        "FACEBOOK_SCRAPER_DIR",
        ROOT.parent / "facebook-ads-scraper"
    )
).resolve()

SCRAPER_SCRIPT = Path(
    os.environ.get(
        "FACEBOOK_SCRAPER_SCRIPT",
        SCRAPER_REPO / "playwright_scraper.py"
    )
).resolve()

SCRAPER_OUTPUT = SCRAPER_REPO / "facebook_ads.json"

SCRAPER_REGION = os.environ.get(
    "FACEBOOK_SCRAPER_REGION",
    "IN"
).strip().upper()

SCRAPER_TIMEOUT = int(
    os.environ.get(
        "FACEBOOK_SCRAPER_TIMEOUT",
        "1800"
    )
)

SCRAPER_MAX_ADS_PER_KEYWORD = int(
    os.environ.get(
        "SCRAPER_MAX_ADS_PER_KEYWORD",
        "0"
    ) or 0
)

CUSTOM_KEYWORD = os.environ.get(
    "SEARCH_KEYWORD",
    ""
).strip()

SEARCH_ID = (
    os.environ.get("SEARCH_ID", "").strip()
    or str(uuid.uuid4())
)

DEFAULT_AD_LIBRARY_KEYWORDS = [
    "streetwear brand",
    "clothing label",
    "hoodie drop",
    "oversized tee",
    "apparel brand India",
]

# Accept one keyword or multiple comma-separated keywords from the dashboard.
AD_LIBRARY_KEYWORDS = (
    [
        keyword.strip()
        for keyword in CUSTOM_KEYWORD.split(",")
        if keyword.strip()
    ]
    if CUSTOM_KEYWORD
    else DEFAULT_AD_LIBRARY_KEYWORDS
)

SEARCH_KEYWORD_FOR_RECORDS = ", ".join(AD_LIBRARY_KEYWORDS)

APPAREL_TERMS = {
    "apparel",
    "clothing",
    "streetwear",
    "fashion",
    "hoodie",
    "hoodies",
    "t-shirt",
    "tshirt",
    "tee",
    "tees",
    "shirt",
    "shirts",
    "trousers",
    "pants",
    "jeans",
    "denim",
    "sweatshirt",
    "jacket",
    "collection",
    "clothing brand",
    "fashion brand",
}

SOCIAL_HOSTS = {
    "facebook.com",
    "fb.me",
    "instagram.com",
    "wa.me",
    "whatsapp.com",
    "youtube.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "tiktok.com",
    "pinterest.com",
    "threads.net",
    "m.me",
    "play.google.com",
    "apps.apple.com",
    "share.google",
    "google.com",
    "linktr.ee",
    "bit.ly",
    "tinyurl.com",
    "t.co",
}

UNSUITABLE_HOSTS = {
    "amazon.in",
    "amazon.com",
    "flipkart.com",
    "myntra.com",
    "ajio.com",
    "meesho.com",
    "temu.com",
    "etsy.com",
    "culture-circle.com",
    "culturecircle.com",
}


# ============================================================
# SCRAPER
# ============================================================

def scraper_python():

    candidates = [

        SCRAPER_REPO / ".venv" / "Scripts" / "python.exe",

        SCRAPER_REPO / ".venv" / "bin" / "python",

    ]

    for path in candidates:

        if path.exists():

            return str(path)

    return sys.executable


def run_scraper(max_ads):

    if not SCRAPER_SCRIPT.is_file():
        raise FileNotFoundError(
            f"Facebook scraper not found: {SCRAPER_SCRIPT}"
        )

    collected = []
    seen_ids = set()

    for keyword in AD_LIBRARY_KEYWORDS:

        print(f"[info] Scraping: {keyword}")

        # Prevent stale output from a previous keyword/run being reused.
        if SCRAPER_OUTPUT.exists():
            try:
                SCRAPER_OUTPUT.unlink()
            except OSError as error:
                print(
                    f"[warn] Could not remove previous scraper output: {error}"
                )
                continue

        command = [
            scraper_python(),
            str(SCRAPER_SCRIPT),
            "--query",
            keyword,
            "--region",
            SCRAPER_REGION,
            "--max-results",
            str(max_ads),
            "--details",
        ]

        timed_out = False

        try:
            completed = subprocess.run(
                command,
                cwd=str(SCRAPER_REPO),
                capture_output=True,
                text=True,
                timeout=SCRAPER_TIMEOUT,
                check=False,
            )

            if completed.stdout:
                print(completed.stdout[-2500:])

            if completed.returncode != 0:
                print(
                    f"[warn] Scraper exited with code "
                    f"{completed.returncode} for '{keyword}'."
                )
                if completed.stderr:
                    print(completed.stderr[-2000:])
                print(
                    "[info] Checking for usable partial results..."
                )

        except subprocess.TimeoutExpired as error:
            timed_out = True
            print(
                f"[warn] Scraper timed out for '{keyword}' "
                f"after {SCRAPER_TIMEOUT} seconds."
            )

            if error.stdout:
                output = error.stdout
                if isinstance(output, bytes):
                    output = output.decode("utf-8", errors="replace")
                print(output[-2500:])

            if error.stderr:
                error_text = error.stderr
                if isinstance(error_text, bytes):
                    error_text = error_text.decode("utf-8", errors="replace")
                print(error_text[-2000:])

        if not SCRAPER_OUTPUT.exists():
            print(
                f"[warn] No fresh scraper output available for '{keyword}'."
            )
            continue

        try:
            with open(
                SCRAPER_OUTPUT,
                "r",
                encoding="utf-8"
            ) as file:
                ads = json.load(file)

        except (OSError, json.JSONDecodeError) as error:
            print(
                f"[warn] Could not read scraper output for "
                f"'{keyword}': {error}"
            )
            continue

        if not isinstance(ads, list):
            print(
                f"[warn] Scraper output for '{keyword}' "
                "was not a JSON list."
            )
            continue

        new_count = 0

        for raw_ad in ads:
            if not isinstance(raw_ad, dict):
                continue

            ad = dict(raw_ad)
            ad_id = str(ad.get("ad_id") or "").strip()

            if ad_id and ad_id in seen_ids:
                continue

            if ad_id:
                seen_ids.add(ad_id)

            ad["_matched_keyword"] = keyword
            collected.append(ad)
            new_count += 1

        label = "partial " if timed_out else ""
        print(
            f"[info] Added {new_count} unique ads "
            f"from {label}results for '{keyword}'."
        )

    if not collected:
        print("[warn] No ads were collected from any keyword.")
        return [], None

    data_dir = ROOT / "data"
    data_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    raw_path = (
        data_dir
        / f"facebook_ads_{SEARCH_ID}.json"
    )

    with open(
        raw_path,
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            collected,
            file,
            ensure_ascii=False,
            indent=2
        )

    from enrichment.providers.facebook_ads_library import (
        FacebookAdsLibraryProvider
    )

    provider = FacebookAdsLibraryProvider(
        json_paths=[raw_path]
    )

    advertisers = provider.get_advertisers()

    print(
        f"[info] Collected {len(collected)} unique ads across "
        f"{len(AD_LIBRARY_KEYWORDS)} keyword(s)."
    )

    return advertisers, raw_path


# ============================================================
# ADVERTISER PROCESSING
# ============================================================

def candidate_website(advertiser):

    """Return a plausible first-party website candidate."""

    for ad in advertiser.get("ads", []):

        raw_url = str(
            ad.get("link_url") or ""
        ).strip()

        if not raw_url:
            continue

        if not raw_url.startswith(
            ("http://", "https://")
        ):

            raw_url = "https://" + raw_url

        try:

            parsed = urlparse(raw_url)

            host = (
                parsed.hostname or ""
            ).lower().removeprefix("www.")

        except ValueError:

            continue

        if not host or "." not in host:
            continue

        blocked_hosts = (
            SOCIAL_HOSTS | UNSUITABLE_HOSTS
        )

        if any(
            host == blocked or host.endswith("." + blocked)
            for blocked in blocked_hosts
        ):

            continue

        if host in {

            "goo.gl",
            "forms.gle",
            "g.page",
            "fb.me",
            "lnk.bio",
            "bio.site",
            "beacons.ai",
            "taplink.cc",
            "onelink.me",
            "apps.shopify.com",

        }:

            continue

        if parsed.scheme not in {
            "http",
            "https"
        }:

            continue

        return (
            f"{parsed.scheme}://{parsed.netloc}"
        )

    return None


def classify_apparel_brand(advertiser):
    """
    Conservative apparel classification.

    True:
        Positive apparel evidence.

    False:
        Strong evidence of a non-apparel business.

    None:
        Insufficient evidence.
    """

    brand_name = str(
        advertiser.get("brand_name") or ""
    ).lower()

    ads = advertiser.get("ads", []) or []

    ad_bodies = [
        str(
            ad.get("body")
            or ad.get("body_text")
            or ""
        ).lower()
        for ad in ads
    ]

    combined = " ".join([
        brand_name,
        *ad_bodies,
    ])

    # Explicit non-apparel indicators.
    negative_phrases = (
        "billing software",
        "erp software",
        "enterprise resource planning",
        "packaging solutions",
        "packaging supplier",
        "sewing machine",
        "embroidery machine",
        "travel booking",
        "fantasy game",
        "mobile game",
        "cosmetics",
        "skincare",
        "wholesale supplier",
        "manufacturer for brands",
        "resale marketplace",
        "pre-owned marketplace",
        "multi-brand marketplace",
    )

    if any(
        phrase in combined
        for phrase in negative_phrases
    ):
        return False

    # Categories are useful positive evidence.
    categories = []

    for ad in ads:

        raw = ad.get(
            "advertiser_categories_json"
        )

        if isinstance(raw, str):

            try:
                raw = json.loads(raw)

            except json.JSONDecodeError:
                raw = []

        if isinstance(raw, list):

            categories.extend(
                str(item).lower()
                for item in raw
            )

    apparel_categories = {
        "clothing",
        "apparel",
        "clothing store",
        "clothing brand",
        "fashion designer",
    }

    category_evidence = any(
        category.strip() in apparel_categories
        for category in categories
    )

    # Strong product-specific signals.
    product_terms = (
        "streetwear",
        "hoodie",
        "hoodies",
        "t-shirt",
        "tshirt",
        "oversized tee",
        "graphic tee",
        "sweatshirt",
        "denim",
        "jeans",
        "trousers",
        "jacket",
        "clothing collection",
        "apparel collection",
        "new collection",
        "drop is live",
        "shop the collection",
    )

    product_evidence = any(
        re.search(
            r"\b" + re.escape(term) + r"\b",
            combined
        )
        for term in product_terms
    )

    # A category by itself can be ambiguous.
    # A product-specific advertisement is stronger evidence.
    if category_evidence or product_evidence:
        return True

    return None

def normalise_advertiser(advertiser, website):

    handle = advertiser.get(
        "instagram_handle"
    )

    if isinstance(handle, str):

        handle = handle.strip()

        if handle.startswith(
            "https://www.instagram.com/"
        ) or handle.startswith(
            "https://instagram.com/"
        ):

            handle = (
                handle.rstrip("/")
                .split("/")[-1]
            )

        handle = handle.lstrip("@") or None

    matched_keywords = sorted({

        ad.get("_matched_keyword")

        for ad in advertiser.get("ads", [])

        if ad.get("_matched_keyword")

    })

    return {

        "brand_name": str(
            advertiser.get("brand_name") or ""
        ).strip(),

        "website": website,

        "instagram_handle": handle,

        "instagram_followers": advertiser.get(
            "followers"
        ),

        "is_apparel_brand": classify_apparel_brand(
            advertiser
        ),

        "facebook_url": advertiser.get(
            "facebook_url"
        ),

        "facebook_page_id": advertiser.get(
            "page_id"
        ),

        "matched_keywords": matched_keywords,

        "ads": advertiser.get("ads", []),

    }


# ============================================================
# PIPELINE
# ============================================================

def build_pipeline(provider):

    from enrichment.pipeline import (
        LeadGenerationPipeline
    )

    return LeadGenerationPipeline(

        social_provider=provider,

        advertising_provider=provider,

        brand_metadata_provider=None,

    )


# ============================================================
# AIRTABLE RECORD CONSTRUCTION
# ============================================================

def first_value(values):

    if isinstance(values, list):

        return (
            str(values[0]).strip()
            if values
            else ""
        )

    return (
        str(values).strip()
        if values
        else ""
    )


def json_safe(value):

    try:

        return json.dumps(
            value,
            ensure_ascii=False,
            default=str
        )

    except (TypeError, ValueError):

        return str(value)


def make_airtable_record(lead, result):

    status = result.get(
        "status",
        "unknown"
    )

    contacts = (
        result.get("enrichment", {}).get(
            "contacts",
            {}
        )
    )

    emails = contacts.get(
        "business_emails",
        []
    )

    phones = contacts.get(
        "business_phones",
        []
    )

    contact_info = (
        first_value(phones)
        or first_value(emails)
    )

    if not contact_info:

        contact_info = lead.get(
            "facebook_url"
        )

        if (
            not contact_info
            and lead.get("instagram_handle")
        ):

            contact_info = (
                "https://www.instagram.com/"
                + lead["instagram_handle"]
                + "/"
            )

    ad_sample = ""

    if lead.get("ads"):

        first_ad = lead["ads"][0]

        ad_sample = str(
            first_ad.get("body")
            or first_ad.get("body_text")
            or ""
        )[:250]

    notes = [

        f"Pipeline status: {status}",

        (
            "Website candidate from Meta ad destination "
            "(ownership unverified): "
            f"{lead.get('website') or 'none'}"
        ),

        (
            "Matched search keywords: "
            + ", ".join(
                lead.get("matched_keywords", [])
            )
        ),

    ]

    if result.get("model_version"):

        notes.append(
            f"ANN model: {result['model_version']}"
        )

    if result.get("priority_probability") is not None:

        notes.append(
            "ANN output (experimental; not a calibrated "
            "acquisition probability): "
            f"{result['priority_probability']}"
        )

    if result.get("missing_features"):

        notes.append(
            "Missing ANN features: "
            + ", ".join(
                result["missing_features"]
            )
        )

    if result.get("invalid_features"):

        notes.append(
            "Invalid ANN features: "
            + json_safe(
                result["invalid_features"]
            )
        )

    if result.get("imputed_features"):

        notes.append(
            "ANN imputed features: "
            + ", ".join(
                result["imputed_features"]
            )
        )

    if result.get("score_quality"):

        notes.append(
            "ANN score quality: "
            + result["score_quality"]
        )

    qualification = result.get(
        "qualification",
        {}
    )

    if qualification.get(
        "qualification_reasons"
    ):

        notes.append(
            "Qualification: "
            + "; ".join(
                qualification["qualification_reasons"]
            )
        )

    if result.get("errors"):

        notes.append(
            "Pipeline details: "
            + "; ".join(
                map(str, result["errors"])
            )
        )

    if ad_sample:

        notes.append(
            "Sample ad: " + ad_sample
        )

    return {

        "Lead Name": lead["brand_name"][:100],

        "Company": lead["brand_name"][:100],

        "Lead Source": "Ad Library",

        "Contact Information": contact_info,

        # Only the ANN can populate this field.
        "Lead Score": (
            result.get("priority_score")
            if status == "scored"
            else None
        ),

        "Notes": " | ".join(notes)[:9500],

        "Auto-Sourced": True,

        "Search ID": SEARCH_ID,

        "Search Keyword": SEARCH_KEYWORD_FOR_RECORDS,

    }


# ============================================================
# DEBUG OUTPUT
# ============================================================

def write_debug_results(results):

    data_dir = ROOT / "data"

    data_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    path = (
        data_dir
        / f"lead_results_{SEARCH_ID}.json"
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            results,
            file,
            ensure_ascii=False,
            indent=2,
            default=str
        )

    print(
        f"[ok] Detailed results saved: {path}"
    )


# ============================================================
# AIRTABLE
# ============================================================

def write_to_airtable(records):

    if not records:

        print(
            "[info] No records to save."
        )

        return

    if not (
        AIRTABLE_API_KEY
        and AIRTABLE_BASE_ID
        and AIRTABLE_TABLE_NAME
    ):

        raise RuntimeError(
            "Airtable configuration missing."
        )

    url = (
        f"https://api.airtable.com/v0/"
        f"{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    )

    headers = {

        "Authorization": (
            f"Bearer {AIRTABLE_API_KEY}"
        ),

        "Content-Type": "application/json",

    }

    for offset in range(
        0,
        len(records),
        10
    ):

        batch = records[offset:offset + 10]

        payload = {

            "records": [
                {"fields": record}
                for record in batch
            ],

            "typecast": True,

        }

        for attempt in range(5):

            try:

                response = requests.post(

                    url,

                    headers=headers,

                    json=payload,

                    timeout=30

                )

                if (
                    response.status_code == 429
                    or response.status_code >= 500
                ):

                    if attempt == 4:

                        response.raise_for_status()

                    retry_after = response.headers.get(
                        "Retry-After"
                    )

                    wait = (

                        float(retry_after)

                        if retry_after

                        else min(
                            2 ** attempt,
                            30
                        )

                    )

                    print(
                        f"[warn] Airtable returned "
                        f"{response.status_code}; "
                        f"retrying in {wait}s"
                    )

                    time.sleep(wait)

                    continue

                response.raise_for_status()

                print(
                    f"[ok] Wrote {len(batch)} records to Airtable."
                )

                break

            except requests.RequestException as error:

                if attempt == 4:

                    print(
                        f"[error] Airtable write failed: {error}"
                    )

                    if error.response is not None:

                        print(
                            error.response.text
                        )

                    raise

                time.sleep(
                    min(2 ** attempt, 30)
                )


# ============================================================
# MAIN
# ============================================================

def main():

    configured_limit = os.environ.get(
        "SEARCH_LIMIT",
        ""
    ).strip()

    if configured_limit:

        try:
            max_ads = int(configured_limit)

            if max_ads <= 0:
                raise ValueError

        except ValueError:
            raise ValueError(
                f"Invalid SEARCH_LIMIT: {configured_limit}. "
                "Expected a positive integer."
            )

    else:

        while True:

            try:

                max_ads = int(
                    input(
                        "How many ads should I search per keyword? "
                    ).strip()
                )

                if max_ads > 0:
                    break

                print(
                    "Enter a number greater than 0."
                )

            except ValueError:

                print(
                    "Please enter a valid whole number."
                )

    print(f"[info] Search limit: {max_ads}")

    print(
        f"[info] Search ID: {SEARCH_ID}"
    )

    print(
        f"[info] Search keyword(s): "
        f"{SEARCH_KEYWORD_FOR_RECORDS}"
    )

    print(
        f"[info] Ad search limit per keyword: {max_ads}"
    )

    advertisers, raw_path = run_scraper(max_ads)

    if not advertisers:

        print(
            "[warn] No advertisers returned."
        )

        return

    print(
        f"[info] Discovered {len(advertisers)} unique advertisers. "
        "Processing every discovered advertiser; "
        "no separate advertiser cap."
    )

    from enrichment.providers.facebook_ads_library import (
        FacebookAdsLibraryProvider
    )

    provider = FacebookAdsLibraryProvider(
        json_paths=[raw_path]
    )

    pipeline = build_pipeline(provider)

    airtable_records = []

    debug_results = []

    processed_count = 0

    for advertiser in advertisers:

        brand_name = str(
            advertiser.get("brand_name") or ""
        ).strip()

        if not brand_name:
            continue

        website = candidate_website(advertiser)

        lead = normalise_advertiser(
            advertiser,
            website
        )

        processed_count += 1

        print(
            f"[{processed_count}/{len(advertisers)}] "
            f"Enriching {brand_name}"
        )

        try:

            result = pipeline.process_lead(lead)

        except Exception as error:

            result = {

                "brand_name": brand_name,

                "website": website,

                "status": "pipeline_error",

                "priority_score": None,

                "priority_probability": None,

                "errors": [

                    f"Unhandled pipeline exception: "
                    f"{type(error).__name__}: {error}"

                ],

            }

        debug_results.append({

            "lead": lead,

            "pipeline_result": result,

        })

        status = result.get(
            "status",
            "unknown"
        )

        # Keep every lead unless the pipeline explicitly rejects it.
        # This allows unscored and pending-enrichment leads through.
        is_accepted = status != "rejected"

        if is_accepted:
            airtable_records.append(
                make_airtable_record(
                    lead,
                    result
                )
            )

        print(
            f"[result] {brand_name}: {status} "
            f"(included: {is_accepted}; "
            f"ANN score: {result.get('priority_score')})"
        )

    # Keep every processed lead in debug output for auditing.
    write_debug_results(debug_results)

    # Only explicitly rejected prospects are excluded.
    write_to_airtable(airtable_records)

    # Excel uses the same inclusion rule as Airtable.
    exportable_results = [
        item
        for item in debug_results
        if item.get("pipeline_result", {}).get("status") != "rejected"
    ]

    if exportable_results:
        export_path = export_to_excel(
            results=exportable_results,
            search_id=SEARCH_ID,
            search_keywords=SEARCH_KEYWORD_FOR_RECORDS,
            output_directory=ROOT / "data" / "exports"
        )
        print(f"[ok] Lead Excel workbook generated: {export_path}")
    else:
        print("[info] No non-rejected leads found; no Excel export generated.")

    counts = {}

    for item in debug_results:

        status = item["pipeline_result"].get(
            "status",
            "unknown"
        )

        counts[status] = (
            counts.get(status, 0) + 1
        )

    print(
        f"[complete] Status summary: {counts}"
    )

    print(
        f"[complete] Processed {processed_count} advertisers; "
        f"sent {len(airtable_records)} non-rejected records to Airtable."
    )


if __name__ == "__main__":

    main()
