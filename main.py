"""
Streetwear Lead-Gen Monitor
REMINDER: REDDIT NOT WORKING - PLAYWRIGHT NEEDED

Scheduled runs use the default keyword list and configured RSS feeds.
Manual GitHub Actions runs can supply SEARCH_KEYWORD to run a targeted
Meta Ad Library search. Every lead is tagged with a Search ID and keyword
so the dashboard can show the results of an individual search.
"""

import os
import re
import sys
import time
import json
import uuid
import feedparser
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from groq import Groq
from dotenv import load_dotenv

load_dotenv()  # reads .env into environment variables for local runs

# ---------------------------------------------------------------------------
# Config (set these as GitHub Actions secrets / local .env vars, never commit)
# ---------------------------------------------------------------------------
AIRTABLE_API_KEY = os.environ.get("AIRTABLE_API_KEY")
AIRTABLE_BASE_ID = os.environ.get("AIRTABLE_BASE_ID")
AIRTABLE_TABLE_NAME = os.environ.get("AIRTABLE_TABLE_NAME", "Leads")

APIFY_API_TOKEN = os.environ.get("APIFY_API_TOKEN")
APIFY_ACTOR_ID = "igolaizola~facebook-ad-library-scraper"

GROQ_API_KEY = os.environ.get("GROQ_API_KEY")
_groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None
GROQ_MODEL = "openai/gpt-oss-120b"

# GitHub Actions supplies these for dashboard-triggered searches.
CUSTOM_KEYWORD = os.environ.get("SEARCH_KEYWORD", "").strip()
SEARCH_ID = os.environ.get("SEARCH_ID", "").strip() or str(uuid.uuid4())

# Google Alerts RSS feed URLs — create these at google.com/alerts, set delivery
# to "RSS feed", and paste the feed URLs here (one per query you set up).
RSS_FEEDS = [
    # "https://www.google.com/alerts/feeds/XXXXXXXXXXXXX/XXXXXXXXXXXXX",
]

# Keywords that bump an RSS lead's score up
POSITIVE_KEYWORDS = [
    "new drop", "launch", "launching", "streetwear", "collab",
    "collection", "just dropped", "restock", "limited edition",
    "brand new", "startup", "clothing brand", "apparel brand",
]

# Scheduled Meta Ad Library searches. A dashboard-triggered manual search
# replaces this list with the one keyword supplied by the user.
DEFAULT_AD_LIBRARY_KEYWORDS = [
    "streetwear brand",
    "clothing label",
    "hoodie drop",
    "oversized tee",
    "apparel brand India",
]

AD_LIBRARY_KEYWORDS = (
    [CUSTOM_KEYWORD]
    if CUSTOM_KEYWORD
    else DEFAULT_AD_LIBRARY_KEYWORDS
)

# Follower-count disqualification rule
FOLLOWER_DISQUALIFY_THRESHOLD = 10000

# ---------------------------------------------------------------------------
# Signal collection — RSS
# ---------------------------------------------------------------------------

def fetch_rss_signals():
    """Pull entries from configured Google Alerts RSS feeds."""
    signals = []
    for feed_url in RSS_FEEDS:
        if not feed_url.strip():
            continue
        parsed = feedparser.parse(feed_url)
        for entry in parsed.entries:
            signals.append({
                "source": "RSS",
                "title": entry.get("title", ""),
                "summary": strip_html(entry.get("summary", "")),
                "link": entry.get("link", ""),
            })
    return signals


def strip_html(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()

# ---------------------------------------------------------------------------
# Signal collection — Meta Ad Library (via Apify)
# ---------------------------------------------------------------------------

def fetch_ad_library_signals():
    """
    Calls the Apify Facebook Ad Library Scraper once per configured keyword,
    collects results, and dedupes by page_name so each brand only counts once
    even if it matched multiple keywords.
    """
    if not APIFY_API_TOKEN:
        print("[info] APIFY_API_TOKEN not set — skipping Ad Library fetch.")
        return []

    brands = {}  # page_name -> brand dict

    for keyword in AD_LIBRARY_KEYWORDS:
        print(f"[info] fetching Ad Library results for: '{keyword}'")

        run_input = {
            "category": "all",
            "country": "IN",
            "proxyConfiguration": {
                "useApifyProxy": True,
                "apifyProxyGroups": ["RESIDENTIAL"],
                "apifyProxyCountry": "IN",
            },
            "query": keyword,
            "fetchDetails": False,
        }

        url = (
            f"https://api.apify.com/v2/acts/{APIFY_ACTOR_ID}"
            f"/run-sync-get-dataset-items?token={APIFY_API_TOKEN}"
        )

        try:
            resp = requests.post(url, json=run_input, timeout=90)
            resp.raise_for_status()
            items = resp.json()
        except requests.exceptions.RequestException as e:
            print(
                f"[warn] Ad Library fetch failed for '{keyword}': {e}",
                file=sys.stderr,
            )
            continue

        for item in items:
            snapshot = item.get("snapshot", {}) or {}
            page_name = snapshot.get("page_name")
            if not page_name:
                continue

            if page_name not in brands:
                brands[page_name] = {
                    "source": "Ad Library",
                    "page_name": page_name,
                    "page_profile_url": snapshot.get("page_profile_uri"),
                    "matched_keywords": set(),
                    "ads": [],
                }

            brands[page_name]["matched_keywords"].add(keyword)
            body = snapshot.get("body", {}) or {}
            brands[page_name]["ads"].append({
                "ad_archive_id": item.get("ad_archive_id"),
                "body_text": body.get("text", ""),
                "cta_text": snapshot.get("cta_text"),
                "link_url": snapshot.get("link_url"),
            })

        time.sleep(2)  # small buffer between actor calls

    for brand in brands.values():
        brand["matched_keywords"] = sorted(brand["matched_keywords"])
        brand["ad_count"] = len(brand["ads"])

    print(
        f"[info] found {len(brands)} unique brands across "
        f"{len(AD_LIBRARY_KEYWORDS)} keyword(s)"
    )
    return list(brands.values())

# ---------------------------------------------------------------------------
# Contact enrichment — website phone number check
# ---------------------------------------------------------------------------

SOCIAL_DOMAINS = {
    "facebook.com", "instagram.com", "wa.me", "api.whatsapp.com",
    "play.google.com", "apps.apple.com", "youtube.com", "linkedin.com",
    "twitter.com", "x.com", "m.me",
}

PHONE_REGEX = re.compile(r"(?:\+91[\-\s]?)?[6-9]\d{9}\b")
CONTACT_PAGE_HINTS = ["contact", "about", "reach", "support", "get-in-touch"]
MAX_PAGES_PER_SITE = 6
PHONE_FOUND_SCORE_BOOST = 20


def extract_candidate_website(signal):
    """Find a non-social website linked from a brand's ads."""
    for ad in signal.get("ads", []):
        link = ad.get("link_url") or ""
        if not link:
            continue
        parsed = urlparse(link)
        domain = parsed.netloc.replace("www.", "")
        if domain and not any(social in domain for social in SOCIAL_DOMAINS):
            return f"{parsed.scheme}://{parsed.netloc}"
    return None


def find_phone_number_on_website(base_url):
    """Check a homepage and likely contact pages for an Indian phone number."""
    visited = set()
    to_visit = [base_url]
    pages_checked = 0

    while to_visit and pages_checked < MAX_PAGES_PER_SITE:
        url = to_visit.pop(0)
        if url in visited:
            continue
        visited.add(url)
        pages_checked += 1

        try:
            resp = requests.get(
                url,
                timeout=10,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            resp.raise_for_status()
        except requests.RequestException:
            continue

        html = resp.text

        tel_match = re.search(r'tel:([+\d][\d\-\s]{7,})', html)
        if tel_match:
            return tel_match.group(1).strip()

        text_match = PHONE_REGEX.search(html)
        if text_match:
            return text_match.group(0).strip()

        if url == base_url:
            try:
                soup = BeautifulSoup(html, "html.parser")
                for anchor in soup.find_all("a", href=True):
                    full_url = urljoin(base_url, anchor["href"])
                    if urlparse(full_url).netloc != urlparse(base_url).netloc:
                        continue
                    if any(hint in anchor["href"].lower() for hint in CONTACT_PAGE_HINTS):
                        if full_url not in visited and full_url not in to_visit:
                            to_visit.append(full_url)
            except Exception:
                pass

    return None

# ---------------------------------------------------------------------------
# Follower count check (Instagram/Facebook profile page, best-effort)
# ---------------------------------------------------------------------------

def _parse_follower_string(raw):
    """Convert strings like '12,345', '12.3K', '1.2M' into an integer."""
    raw = raw.strip().upper().replace(",", "")
    multiplier = 1
    if raw.endswith("K"):
        multiplier = 1_000
        raw = raw[:-1]
    elif raw.endswith("M"):
        multiplier = 1_000_000
        raw = raw[:-1]
    elif raw.endswith("B"):
        multiplier = 1_000_000_000
        raw = raw[:-1]
    try:
        return int(float(raw) * multiplier)
    except ValueError:
        return None


def get_follower_count(profile_url):
    """Best-effort follower extraction; None means unknown, not zero."""
    if not profile_url:
        return None

    try:
        resp = requests.get(
            profile_url,
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        resp.raise_for_status()
    except requests.RequestException:
        return None

    match = re.search(r"([\d,.]+[KMB]?)\s*Followers", resp.text, re.IGNORECASE)
    if match:
        return _parse_follower_string(match.group(1))

    return None

# ---------------------------------------------------------------------------
# Scoring — LLM contextual judge (Groq)
# ---------------------------------------------------------------------------

JUDGE_SYSTEM_PROMPT = """You are a lead-qualification judge for a marketing agency \
that pitches its services to small and mid-sized apparel/streetwear brands in India.

Given a Facebook/Instagram page name and its ad copy, decide if this is a \
GOOD LEAD: a genuine small-to-mid apparel, streetwear, or fashion brand that \
would plausibly hire a marketing agency.

Disqualify:
- Large, well-known platforms or retailers (e.g. AJIO, Myntra, Amazon, Flipkart, \
Nykaa) — too big to be a prospect
- Marketing/ad agencies, photography studios, or other service providers to brands \
(they're vendors or competitors, not leads)
- Wholesalers/manufacturers selling B2B, not direct-to-consumer brands
- Ads unrelated to apparel (fiction/app-install ads, unrelated products) that only \
matched a search keyword by coincidence
- Hiring/recruitment posts

Respond with ONLY a JSON object, no other text, in this exact shape:
{"is_good_lead": true or false, "score": 0-100, "reason": "one sentence explaining why"}
"""


def judge_brand_with_llm(signal):
    """Score an Ad Library brand with Groq; return (score, reasons)."""
    ad_texts = "\n---\n".join(
        ad.get("body_text", "")[:1000]
        for ad in signal.get("ads", [])
    )[:5000]

    user_content = (
        f"Page name: {signal.get('page_name')}\n\n"
        f"Ad copy:\n{ad_texts}"
    )

    try:
        response = _groq_client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.2,
        )
        raw_text = response.choices[0].message.content.strip()
        raw_text = raw_text.replace("```json", "").replace("```", "").strip()
        verdict = json.loads(raw_text)

        score = int(verdict.get("score", 0))
        reason = verdict.get("reason", "no reason given")
        if not verdict.get("is_good_lead", False):
            score = 0

        return score, [f"LLM judge: {reason}"]

    except Exception as e:
        print(
            f"[warn] LLM judge failed for '{signal.get('page_name')}': {e}",
            file=sys.stderr,
        )
        return 0, [f"LLM judge failed: {e}"]


def score_signal(signal):
    """Use Groq for Ad Library brands and rules for RSS signals."""
    if signal["source"] == "Ad Library":
        if not _groq_client:
            print("[info] GROQ_API_KEY not set — scoring 0.")
            return 0, ["GROQ_API_KEY not set, cannot judge"]
        score, reasons = judge_brand_with_llm(signal)
        reasons.append(
            f"(info, not scored) ad volume: {signal.get('ad_count', 0)} active ad(s)"
        )
        return score, reasons

    text = f"{signal.get('title', '')} {signal.get('summary', '')}".lower()
    score = 0
    reasons = []
    matched = [keyword for keyword in POSITIVE_KEYWORDS if keyword in text]

    if matched:
        bump = min(40, len(matched) * 10)
        score += bump
        reasons.append(f"keyword match ({', '.join(matched[:3])}): +{bump}")

    if signal["source"] == "RSS":
        score += 15
        reasons.append("Google Alert match (curated query): +15")

    return max(0, min(100, score)), reasons

# ---------------------------------------------------------------------------
# Airtable write
# ---------------------------------------------------------------------------

def write_to_airtable(leads):
    if not leads:
        print("[info] no leads passed the score threshold; nothing to write")
        return

    if not (AIRTABLE_API_KEY and AIRTABLE_BASE_ID and AIRTABLE_TABLE_NAME):
        print("[error] Airtable configuration missing; cannot save leads.", file=sys.stderr)
        raise RuntimeError("Airtable configuration missing")

    url = f"https://api.airtable.com/v0/{AIRTABLE_BASE_ID}/{AIRTABLE_TABLE_NAME}"
    headers = {
        "Authorization": f"Bearer {AIRTABLE_API_KEY}",
        "Content-Type": "application/json",
    }

    for i in range(0, len(leads), 10):
        batch = leads[i:i + 10]
        payload = {
            "records": [{"fields": lead} for lead in batch],
            "typecast": True,
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            resp.raise_for_status()
        except requests.RequestException as e:
            print(f"[error] Airtable write failed: {e}", file=sys.stderr)
            if getattr(e, "response", None) is not None:
                print(e.response.text, file=sys.stderr)
            raise

        print(f"[ok] wrote {len(batch)} leads to Airtable")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    if CUSTOM_KEYWORD:
        print(f"[info] targeted search requested: {CUSTOM_KEYWORD}")
        # A manual keyword search should preview only results for that keyword;
        # unrelated RSS results are therefore excluded from this run.
        rss_signals = []
        search_keyword_for_records = CUSTOM_KEYWORD
    else:
        print("[info] scheduled/default discovery run")
        rss_signals = fetch_rss_signals()
        search_keyword_for_records = ", ".join(AD_LIBRARY_KEYWORDS)

    ad_library_signals = fetch_ad_library_signals()[:10]
    signals = rss_signals + ad_library_signals
    print(f"[info] search ID: {SEARCH_ID}")
    print(f"[info] collected {len(signals)} raw signals")

    leads = []

    for signal in signals:
        score, reasons = score_signal(signal)

        if signal["source"] == "Ad Library":
            # Stay comfortably under Groq's 30 requests/minute free-tier limit.
            time.sleep(2.1)

        if score < 25:
            continue

        phone_number = None
        follower_count = None

        if signal["source"] == "Ad Library":
            website = extract_candidate_website(signal)
            if website:
                print(
                    f"[info] checking {website} for a phone number "
                    f"({signal['page_name']})"
                )
                phone_number = find_phone_number_on_website(website)
                if phone_number:
                    score = min(100, score + PHONE_FOUND_SCORE_BOOST)
                    reasons.append(
                        f"phone number found on website (+{PHONE_FOUND_SCORE_BOOST}): "
                        f"{phone_number}"
                    )

            follower_count = get_follower_count(signal.get("page_profile_url"))
            if follower_count is not None:
                reasons.append(f"(info, not scored) followers: {follower_count}")
                if follower_count > FOLLOWER_DISQUALIFY_THRESHOLD and not phone_number:
                    print(
                        f"[info] disqualifying '{signal['page_name']}' — "
                        f"{follower_count} followers, no phone number found"
                    )
                    continue

            sample_ad = signal["ads"][0] if signal.get("ads") else {}
            contact_info = (
                phone_number
                if phone_number
                else signal.get("page_profile_url", "")
            )
            lead = {
                "Lead Name": signal["page_name"][:100],
                "Company": signal["page_name"][:100],
                "Lead Source": signal["source"],
                "Contact Information": contact_info,
                "Lead Score": score,
                "Notes": (
                    " | ".join(reasons)
                    + f" | matched: {', '.join(signal['matched_keywords'])}"
                    + f" | sample ad: {sample_ad.get('body_text', '')[:150]}"
                ),
                "Auto-Sourced": True,
            }
        else:
            lead = {
                "Lead Name": signal["title"][:100],
                "Company": signal["title"][:100],
                "Lead Source": signal["source"],
                "Contact Information": signal.get("link", ""),
                "Lead Score": score,
                "Notes": " | ".join(reasons) + f" | link: {signal.get('link', '')}",
                "Auto-Sourced": True,
            }

        # These two Airtable columns allow the dashboard to retrieve the exact
        # results belonging to a particular manual or scheduled execution.
        lead["Search ID"] = SEARCH_ID
        lead["Search Keyword"] = search_keyword_for_records
        leads.append(lead)

    print(f"[info] {len(leads)} leads passed the score threshold")
    write_to_airtable(leads)


if __name__ == "__main__":
    main()