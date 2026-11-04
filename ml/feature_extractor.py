import requests
import json
import re

from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from xml.etree import ElementTree


HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; LeadGenResearchBot/1.0)"
}

TIMEOUT = (5, 10)
MAX_SITEMAPS = 40
MAX_PRODUCTS = 300

PRODUCT_KEYWORDS = [
    "product",
    "products",
    "pdp",
    "catalog",
    "catalogue",
    "collection"
]

IGNORE_KEYWORDS = [
    "article",
    "blog",
    "news",
    "help",
    "support",
    "locator",
    "store",
    "author",
    "video"
]


# --------------------------------------------------
# WEBSITE REQUESTS
# --------------------------------------------------

def fetch_page(url):

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        if response.status_code != 200:
            print(f"Unavailable ({response.status_code}): {url}")
            return None

        return response.text

    except requests.RequestException as e:

        print(f"Request failed: {url} | {e}")
        return None

def verify_website(url):
    """
    Verify whether a candidate website is accessible.

    Returns:
        verified:
            Website responds successfully.

        invalid:
            Website is definitively invalid or redirects
            to a blocked social/marketplace platform.

        inconclusive:
            Website could not be verified because of a
            timeout, network error, rate limit or server error.
    """

    import requests

    from enrichment.qualification import website_host

    if not url:
        return {
            "status": "invalid",
            "reason": "Website URL is missing",
            "http_status": None,
            "final_url": None,
        }

    raw_url = str(url).strip()

    if not raw_url.startswith(("http://", "https://")):
        raw_url = "https://" + raw_url

    if not website_host(raw_url):
        return {
            "status": "invalid",
            "reason": "Invalid or non-first-party website URL",
            "http_status": None,
            "final_url": None,
        }

    try:

        response = requests.get(
            raw_url,
            timeout=(5, 10),
            allow_redirects=True,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            }
        )

        status_code = response.status_code
        final_url = response.url

        final_host = website_host(final_url)

        if not final_host:

            return {
                "status": "invalid",
                "reason": "Website redirects to a non-first-party platform",
                "http_status": status_code,
                "final_url": final_url,
            }

        if 200 <= status_code < 400:

            return {
                "status": "verified",
                "reason": "Website responded successfully",
                "http_status": status_code,
                "final_url": final_url,
            }

        if status_code in (404, 410):

            return {
                "status": "invalid",
                "reason": f"Website returned HTTP {status_code}",
                "http_status": status_code,
                "final_url": final_url,
            }

        if status_code in (403, 429):

            return {
                "status": "inconclusive",
                "reason": f"Website verification blocked by HTTP {status_code}",
                "http_status": status_code,
                "final_url": final_url,
            }

        if status_code >= 500:

            return {
                "status": "inconclusive",
                "reason": f"Website server error: HTTP {status_code}",
                "http_status": status_code,
                "final_url": final_url,
            }

        return {
            "status": "inconclusive",
            "reason": f"Unexpected HTTP response: {status_code}",
            "http_status": status_code,
            "final_url": final_url,
        }

    except requests.exceptions.Timeout:

        return {
            "status": "inconclusive",
            "reason": "Website request timed out",
            "http_status": None,
            "final_url": None,
        }

    except requests.exceptions.ConnectionError:

        return {
            "status": "inconclusive",
            "reason": "Website connection failed",
            "http_status": None,
            "final_url": None,
        }

    except requests.exceptions.RequestException as error:

        return {
            "status": "inconclusive",
            "reason": f"Website request failed: {error}",
            "http_status": None,
            "final_url": None,
        }
# --------------------------------------------------
# WEBSITE QUALITY
# --------------------------------------------------

def calculate_website_quality(soup, url):

    score = 0
    evidence = []

    if url.startswith("https://"):
        score += 15
        evidence.append("HTTPS enabled")

    title = soup.find("title")

    if title and len(title.get_text(strip=True)) > 5:
        score += 10
        evidence.append("Page title present")

    description = soup.find(
        "meta",
        attrs={"name": "description"}
    )

    if description and description.get("content"):
        score += 10
        evidence.append("Meta description present")

    viewport = soup.find(
        "meta",
        attrs={"name": "viewport"}
    )

    if viewport:
        score += 10
        evidence.append("Mobile viewport configured")

    headings = soup.find_all(["h1", "h2", "h3"])

    if len(headings) >= 3:
        score += 10
        evidence.append("Structured heading hierarchy")

    images = soup.find_all("img")

    if len(images) >= 3:
        score += 10
        evidence.append("Multiple images present")

    if images:

        alt_ratio = sum(
            1 for image in images if image.get("alt")
        ) / len(images)

        score += int(10 * alt_ratio)

        if alt_ratio >= 0.7:
            evidence.append("Good image accessibility")

    structured_data = soup.find_all(
        "script",
        attrs={"type": "application/ld+json"}
    )

    if structured_data:
        score += 10
        evidence.append("Structured data present")

    links = [
        a.get("href", "").lower()
        for a in soup.find_all("a")
    ]

    if any("contact" in link for link in links):
        score += 5
        evidence.append("Contact page linked")

    if any("about" in link for link in links):
        score += 5
        evidence.append("About page linked")

    social_domains = [
        "instagram.com",
        "facebook.com",
        "tiktok.com",
        "pinterest.com"
    ]

    if any(
        domain in link
        for link in links
        for domain in social_domains
    ):
        score += 5
        evidence.append("Social profiles linked")

    return min(score, 100), evidence


# --------------------------------------------------
# SITEMAP PRIORITY
# --------------------------------------------------

def sitemap_priority(url):

    name = url.lower()

    # Ignore irrelevant sitemap categories
    if any(keyword in name for keyword in IGNORE_KEYWORDS):
        return 0

    # Highest priority: product-related sitemaps
    if any(keyword in name for keyword in PRODUCT_KEYWORDS):
        return 3

    # General sitemap indexes
    if "sitemap" in name:
        return 1

    return 0


def sort_sitemaps(sitemaps):

    return sorted(
        set(sitemaps),
        key=sitemap_priority,
        reverse=True
    )


# --------------------------------------------------
# SITEMAP DISCOVERY
# --------------------------------------------------

def discover_sitemaps(base_url):

    parsed = urlparse(base_url)

    robots_url = (
        f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    )

    sitemaps = []

    print("\nDiscovering sitemaps...")

    try:

        response = requests.get(
            robots_url,
            headers=HEADERS,
            timeout=TIMEOUT
        )

        if response.status_code == 200:

            for line in response.text.splitlines():

                if line.lower().startswith("sitemap:"):

                    sitemap = line.split(":", 1)[1].strip()

                    if sitemap:
                        sitemaps.append(sitemap)

                        print(f"Discovered: {sitemap}")

    except requests.RequestException:
        print("Could not retrieve robots.txt.")

    # Fallback locations
    if not sitemaps:

        sitemaps.extend([
            urljoin(base_url, "/sitemap.xml"),
            urljoin(base_url, "/sitemap_index.xml")
        ])

    return sort_sitemaps(sitemaps)


# --------------------------------------------------
# STRUCTURED PRODUCT DATA
# --------------------------------------------------

def extract_structured_products(soup, base_url):

    products = set()

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"}
    ):

        try:

            data = json.loads(
                script.string or script.get_text()
            )

            def inspect_json(item):

                if isinstance(item, dict):

                    item_type = item.get("@type", [])

                    if isinstance(item_type, str):
                        item_type = [item_type]

                    if "Product" in item_type:

                        product_url = item.get("url")

                        if product_url:
                            products.add(
                                urljoin(base_url, product_url)
                            )

                    for value in item.values():
                        inspect_json(value)

                elif isinstance(item, list):

                    for value in item:
                        inspect_json(value)

            inspect_json(data)

        except (json.JSONDecodeError, TypeError):
            continue

    return products


# --------------------------------------------------
# PRODUCT URL VALIDATION
# --------------------------------------------------

def is_product_url(url):

    path = urlparse(url).path.lower()

    product_patterns = [
        r"/products?/[^/]+/?$",
        r"/p/[^/]+/?$",
        r"/product/[^/]+/?$",
        r"/[^/]+/t/[^/]+$"
    ]

    return any(
        re.search(pattern, path)
        for pattern in product_patterns
    )


# --------------------------------------------------
# PRODUCT COUNT
# --------------------------------------------------

def count_products(soup, base_url):

    products = set()
    product_sources = {}

    print("\nExtracting homepage product links...")

    for link in soup.find_all("a", href=True):

        href = link["href"]

        full_url = urljoin(base_url, href)

        if is_product_url(full_url):

            products.add(full_url.split("?")[0])

            product_sources[full_url.split("?")[0]] = "Homepage"

    print(f"Homepage products found: {len(products)}")

    # Structured data
    structured_products = extract_structured_products(
        soup,
        base_url
    )

    for product in structured_products:

        product = product.split("?")[0]

        products.add(product)
        product_sources[product] = "Structured data"

    print(f"Products after structured data: {len(products)}")

    # Sitemap discovery
    sitemap_queue = discover_sitemaps(base_url)

    visited_sitemaps = set()
    sitemap_product_counts = {}

    while (
        sitemap_queue
        and len(visited_sitemaps) < MAX_SITEMAPS
        and len(products) < MAX_PRODUCTS
    ):

        sitemap_url = sitemap_queue.pop(0)

        if sitemap_url in visited_sitemaps:
            continue

        visited_sitemaps.add(sitemap_url)

        print(
            f"\nChecking sitemap "
            f"{len(visited_sitemaps)}/{MAX_SITEMAPS}: "
            f"{sitemap_url}"
        )

        sitemap_content = fetch_page(sitemap_url)

        if not sitemap_content:
            continue

        try:

            root = ElementTree.fromstring(
                sitemap_content
            )

            found_products = 0

            for element in root.iter():

                if not element.tag.endswith("loc"):
                    continue

                location = element.text or ""
                location = location.strip()

                if not location:
                    continue

                # Product URL
                if is_product_url(location):

                    product = location.split("?")[0]

                    if product not in products:
                        products.add(product)

                    product_sources[product] = sitemap_url
                    found_products += 1

                # Nested sitemap
                elif (
                    "sitemap" in location.lower()
                    and location not in visited_sitemaps
                ):

                    if sitemap_priority(location) > 0:
                        sitemap_queue.append(location)

                if len(products) >= MAX_PRODUCTS:
                    break

            sitemap_product_counts[sitemap_url] = found_products

            print(
                f"Products discovered in this sitemap: "
                f"{found_products}"
            )

        except ElementTree.ParseError:

            print("Invalid sitemap XML.")
            continue

        # Re-sort the queue after discovering nested sitemaps
        sitemap_queue = sort_sitemaps(sitemap_queue)

    return min(len(products), MAX_PRODUCTS), {

        "products_found": len(products),

        "sitemaps_checked": len(visited_sitemaps),

        "sitemap_product_counts": sitemap_product_counts,

        "product_sources": product_sources,

        "source": (
            "Homepage links, structured data "
            "and priority-based sitemap crawling"
        )
    }


# --------------------------------------------------
# PREMIUM POSITIONING
# --------------------------------------------------

# Price thresholds are deliberately currency-specific. Unknown currencies
# are recorded as evidence but are not used to infer a price tier.
PRICE_THRESHOLDS = {
    "USD": (150, 400),
    "INR": (10000, 30000),
    "GBP": (120, 350),
    "EUR": (140, 400),
    "AUD": (200, 550),
    "CAD": (200, 550),
    "NZD": (220, 600),
    "SGD": (200, 550),
    "AED": (600, 1800),
    "PHP": (5000, 15000),
    "JPY": (20000, 60000),
    "CNY": (1000, 3000),
    "HKD": (1200, 3500),
}

PREMIUM_LANGUAGE_GROUPS = {
    "craftsmanship": [
        "handcrafted", "handmade", "made by hand",
        "artisan", "artisanal", "craftsmanship",
        "hand-finished", "hand finished"
    ],
    "materials": [
        "full-grain leather", "full grain leather",
        "italian leather", "cashmere", "merino wool",
        "silk", "fine wool", "organic cotton",
        "premium leather", "天然"
    ],
    "exclusivity": [
        "limited edition", "limited release",
        "exclusive collection", "made to order",
        "bespoke", "custom-made", "custom made",
        "numbered edition", "small-batch", "small batch"
    ],
    "luxury_positioning": [
        "luxury", "designer", "couture",
        "atelier", " haute couture", "high fashion",
        "heritage collection"
    ],
    "brand_storytelling": [
        "heritage", "established in", "since 19",
        "since 20", "our legacy", "house of",
        "signature collection"
    ],
}

GENERIC_MARKETING_TERMS = {
    "premium": 3,
    "quality": 1,
    "high quality": 2,
    "finest": 2,
    "elevated": 2,
    "refined": 2,
    "timeless": 2,
}


def _normalise_text(value):
    return re.sub(r"\s+", " ", str(value or "")).strip().lower()


def _extract_offer_prices(data, results):
    """Recursively collect price and currency pairs from JSON-LD."""
    if isinstance(data, dict):
        offers = data.get("offers")

        if isinstance(offers, dict):
            price = offers.get("price")
            currency = offers.get("priceCurrency")

            if price is not None:
                try:
                    results.append((float(str(price).replace(",", "")),
                                    str(currency or "").upper()))
                except (ValueError, TypeError):
                    pass

            # AggregateOffer may expose lowPrice/highPrice instead.
            for key in ("lowPrice", "highPrice"):
                value = offers.get(key)
                if value is not None:
                    try:
                        results.append((float(str(value).replace(",", "")),
                                        str(currency or "").upper()))
                    except (ValueError, TypeError):
                        pass

        elif isinstance(offers, list):
            for offer in offers:
                _extract_offer_prices({"offers": offer}, results)

        # Some pages place offers inside @graph or nested product objects.
        for key, value in data.items():
            if key != "offers":
                _extract_offer_prices(value, results)

    elif isinstance(data, list):
        for item in data:
            _extract_offer_prices(item, results)


def extract_page_prices(soup):
    """Extract structured prices from JSON-LD and common product meta tags."""
    prices = []

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"}
    ):
        try:
            data = json.loads(script.string or script.get_text())
            _extract_offer_prices(data, prices)
        except (json.JSONDecodeError, TypeError):
            continue

    # Open Graph / product metadata is common on ecommerce product pages.
    amount = (
        soup.find("meta", attrs={"property": "product:price:amount"})
        or soup.find("meta", attrs={"property": "og:price:amount"})
        or soup.find("meta", attrs={"itemprop": "price"})
    )

    currency = (
        soup.find("meta", attrs={"property": "product:price:currency"})
        or soup.find("meta", attrs={"property": "og:price:currency"})
        or soup.find("meta", attrs={"itemprop": "priceCurrency"})
    )

    if amount and amount.get("content"):
        try:
            value = float(amount.get("content").replace(",", ""))
            code = currency.get("content", "").upper() if currency else ""
            prices.append((value, code))
        except (ValueError, TypeError):
            pass

    # Remove exact duplicate observations.
    return list(set(prices))


def _median(values):
    values = sorted(values)
    if not values:
        return None

    middle = len(values) // 2
    if len(values) % 2:
        return values[middle]

    return (values[middle - 1] + values[middle]) / 2


def _analyse_premium_pages(soups):
    all_text = []
    all_prices = []

    for page_soup in soups:
        all_text.append(_normalise_text(page_soup.get_text(" ", strip=True)))
        all_prices.extend(extract_page_prices(page_soup))

    combined_text = " ".join(all_text)

    score = 0
    evidence = {
        "language_signals": {},
        "generic_terms": [],
        "price_observations": [],
        "price_signal": None,
        "pages_analysed": len(soups),
    }

    # Score distinct groups, not every repeated occurrence. Repeating a
    # keyword in navigation or boilerplate should not inflate the score.
    group_points = {
        "craftsmanship": 15,
        "materials": 12,
        "exclusivity": 15,
        "luxury_positioning": 18,
        "brand_storytelling": 8,
    }

    for group, terms in PREMIUM_LANGUAGE_GROUPS.items():
        found = [term for term in terms if term in combined_text]
        if found:
            score += group_points[group]
            evidence["language_signals"][group] = found

    for term, points in GENERIC_MARKETING_TERMS.items():
        if term in combined_text:
            score += points
            evidence["generic_terms"].append(term)

    # Use only currencies for which we have explicit thresholds.
    prices_by_currency = {}
    for price, currency in all_prices:
        if price <= 0:
            continue

        evidence["price_observations"].append({
            "price": price,
            "currency": currency or "unknown"
        })

        if currency in PRICE_THRESHOLDS:
            prices_by_currency.setdefault(currency, []).append(price)

    # Select the currency with the most observations; do not mix currencies.
    if prices_by_currency:
        currency = max(
            prices_by_currency,
            key=lambda key: len(prices_by_currency[key])
        )
        median_price = _median(prices_by_currency[currency])
        premium_threshold, luxury_threshold = PRICE_THRESHOLDS[currency]

        if median_price >= luxury_threshold:
            score += 35
            evidence["price_signal"] = {
                "currency": currency,
                "median_price": round(median_price, 2),
                "classification": "luxury_price_band",
            }
        elif median_price >= premium_threshold:
            score += 25
            evidence["price_signal"] = {
                "currency": currency,
                "median_price": round(median_price, 2),
                "classification": "premium_price_band",
            }
        else:
            evidence["price_signal"] = {
                "currency": currency,
                "median_price": round(median_price, 2),
                "classification": "below_premium_threshold",
            }

    score = min(score, 100)

    if score >= 65:
        tier = "luxury"
    elif score >= 40:
        tier = "premium"
    elif score >= 20:
        tier = "mid_market"
    else:
        tier = "mass_market_or_unclassified"

    return score, tier, evidence


def detect_premium_positioning(soup, product_urls=None):
    """
    Estimate premium positioning using homepage language and a small sample
    of product pages. This is a heuristic, not a definitive brand valuation.
    """
    soups_to_analyse = [soup]
    sampled_urls = []

    # Product detail pages are often where prices and material details live.
    # Keep this deliberately small to avoid hammering a target website.
    for product_url in list(dict.fromkeys(product_urls or []))[:5]:
        html = fetch_page(product_url)
        if not html:
            continue

        product_soup = BeautifulSoup(html, "html.parser")
        soups_to_analyse.append(product_soup)
        sampled_urls.append(product_url)

    score, tier, evidence = _analyse_premium_pages(soups_to_analyse)

    evidence["sampled_product_pages"] = sampled_urls
    evidence["premium_score"] = score
    evidence["tier"] = tier
    evidence["method"] = (
        "Homepage and up to five product pages; language groups and "
        "currency-aware median structured pricing"
    )

    # Keep the original binary feature expected by the current ANN.
    # A score of 40+ is treated as premium positioning.
    premium_positioning = int(score >= 40)

    return premium_positioning, evidence


# --------------------------------------------------
# MAIN FEATURE EXTRACTOR
# --------------------------------------------------

def extract_features(url):

    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    print(f"\nStarting extraction: {url}")

    html = fetch_page(url)

    if not html:
        return None

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    print("\nCalculating website quality...")

    website_quality, quality_evidence = (
        calculate_website_quality(soup, url)
    )

    print("\nCounting products...")

    product_count, product_evidence = (
        count_products(soup, url)
    )

    print("\nDetecting premium positioning...")

    product_urls = list(product_evidence.get("product_sources", {}).keys())

    premium_positioning, premium_evidence = (
        detect_premium_positioning(soup, product_urls)
    )

    return {

        "website_quality": website_quality,

        "product_count": product_count,

        "premium_positioning": premium_positioning,

        "evidence": {

            "website_quality": quality_evidence,

            "product_count": product_evidence,

            "premium_positioning": premium_evidence
        },

        "missing_features": [
            "active_ads",
            "ad_duration",
            "social_activity",
            "brand_age",
            "posting_frequency"
        ]
    }


# --------------------------------------------------
# TESTING
# --------------------------------------------------

if __name__ == "__main__":

    website = input(
        "Enter apparel brand website: "
    ).strip()

    result = extract_features(website)

    if result:

        print("\nEXTRACTED FEATURES")
        print("==============================")

        for key, value in result.items():
            print(f"\n{key}: {value}")

    else:

        print("\nCould not extract website information.")

