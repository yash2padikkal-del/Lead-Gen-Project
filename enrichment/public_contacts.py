"""
Find publicly listed business contact details on a brand's own website.

- Checks robots.txt before each page request and redirect hop.
- Follows redirects only within the same host/subdomain hierarchy.
- Crawls the canonical host only.
- Prioritises contact, support, privacy, returns, refund, shipping and delivery pages.
- Uses fallback paths and extracts public emails/phone numbers with source URLs.
- Does not guess emails or access authenticated pages.
"""

from __future__ import annotations

import ipaddress
import re
import time
import urllib.robotparser
from collections import deque
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urldefrag, urlunparse

import requests
from bs4 import BeautifulSoup


USER_AGENT = "LeadGenResearchBot/1.0"
REQUEST_TIMEOUT = (5, 12)
REQUEST_DELAY_SECONDS = 1.25
MAX_REDIRECTS = 5
MAX_PAGES = 14
MAX_DISCOVERED_LINKS = 60

# Policy pages are intentionally included: they often contain customer-service numbers.
FALLBACK_PATHS = (
    "/contact", "/contact-us", "/pages/contact", "/pages/contact-us",
    "/about", "/about-us", "/pages/about",
    "/customer-service", "/customer-care", "/support", "/help", "/help-center",
    "/privacy", "/privacy-policy", "/policies/privacy-policy", "/pages/privacy-policy",
    "/returns", "/return-policy", "/returns-and-exchanges", "/refund-policy",
    "/policies/refund-policy", "/pages/returns",
    "/shipping", "/shipping-policy", "/delivery", "/delivery-information",
    "/policies/shipping-policy", "/pages/shipping-policy",
    "/terms", "/terms-and-conditions", "/terms-of-service",
)

# Do not put privacy, returns, refunds, shipping or delivery in this list.
IGNORE_KEYWORDS = (
    "blog", "article", "news", "press", "careers", "jobs", "cookies",
    "wishlist", "cart", "checkout", "login", "register", "account",
    "sitemap", "product-reviews",
)

EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.!#$%&'*+/=?^_`{|}~-]+@"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?"
    r"(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+"
)
PHONE_RE = re.compile(
    r"(?<!\w)(?:\+\s?\d{1,3}[\s().-]*)?"
    r"(?:\(?\d{2,5}\)?[\s().-]*)?"
    r"\d{3,5}[\s().-]*\d{3,5}(?!\w)"
)
REDIRECT_CODES = {301, 302, 303, 307, 308}
TRACKING_QUERY_KEYS = {
    "gclid", "fbclid", "msclkid", "ref", "source",
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
}


def normalise_website(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("A website URL is required.")
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError(f"Invalid website URL: {url}")
    if parsed.username or parsed.password:
        raise ValueError("Website URLs containing credentials are not allowed.")
    return f"{parsed.scheme}://{parsed.netloc}/"


def _normalise_page_url(url: str) -> str:
    url = urldefrag(url)[0]
    parsed = urlparse(url)
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key.lower() not in TRACKING_QUERY_KEYS
    ]
    return urlunparse((
        parsed.scheme.lower(), parsed.netloc.lower(), path, "",
        urlencode(query, doseq=True), "",
    ))


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").lower().rstrip(".")


def _origin(url: str) -> str:
    parsed = urlparse(url)
    return f"{parsed.scheme}://{parsed.netloc}/"


def _is_public_host(host: str) -> bool:
    if not host or host in {"localhost", "localhost.localdomain"} or host.endswith(".localhost"):
        return False
    try:
        return ipaddress.ip_address(host).is_global
    except ValueError:
        return True


def _same_brand_redirect(source_host: str, destination_host: str) -> bool:
    """Accept the same host and its subdomains; reject lookalike unrelated domains."""
    source = (source_host or "").lower().rstrip(".")
    destination = (destination_host or "").lower().rstrip(".")
    if not source or not destination:
        return False
    if source == destination:
        return True
    return source.endswith("." + destination) or destination.endswith("." + source)


def _robots_parser(
    session: requests.Session,
    origin: str,
) -> urllib.robotparser.RobotFileParser:
    robots_url = urljoin(origin, "/robots.txt")
    parser = urllib.robotparser.RobotFileParser()
    parser.set_url(robots_url)
    try:
        response = session.get(
            robots_url, timeout=REQUEST_TIMEOUT,
            headers={"User-Agent": USER_AGENT}, allow_redirects=False,
        )
        if response.status_code in REDIRECT_CODES:
            location = response.headers.get("Location")
            target = urljoin(robots_url, location or "")
            if not location or not _same_brand_redirect(_host(origin), _host(target)):
                parser.parse(["User-agent: *", "Disallow: /"])
                return parser
            response = session.get(
                target, timeout=REQUEST_TIMEOUT,
                headers={"User-Agent": USER_AGENT}, allow_redirects=False,
            )
        if response.status_code == 200:
            parser.parse(response.text.splitlines())
        elif response.status_code in (401, 403):
            parser.parse(["User-agent: *", "Disallow: /"])
        else:
            # A missing robots.txt (e.g. 404) does not prohibit crawling.
            parser.parse([])
    except requests.RequestException:
        parser.parse(["User-agent: *", "Disallow: /"])
    return parser


def _fetch_with_checked_redirects(
    session: requests.Session,
    start_url: str,
    robots_cache: dict[str, urllib.robotparser.RobotFileParser],
    expected_host: str | None = None,
):
    current_url = start_url
    previous_host = expected_host or _host(start_url)
    for _ in range(MAX_REDIRECTS + 1):
        current_url = _normalise_page_url(current_url)
        current_host = _host(current_url)
        if not current_host or not _is_public_host(current_host):
            return None, f"{current_url}: invalid or non-public destination host"
        if not _same_brand_redirect(previous_host, current_host):
            return None, f"{current_url}: rejected unrelated-domain redirect"

        origin = _origin(current_url)
        if origin not in robots_cache:
            robots_cache[origin] = _robots_parser(session, origin)
        if not robots_cache[origin].can_fetch(USER_AGENT, current_url):
            return None, f"{current_url}: disallowed by robots.txt"

        try:
            response = session.get(
                current_url, timeout=REQUEST_TIMEOUT, allow_redirects=False,
            )
        except requests.RequestException as exc:
            return None, f"{current_url}: {type(exc).__name__}"

        if response.status_code in REDIRECT_CODES:
            location = response.headers.get("Location")
            if not location:
                return None, f"{current_url}: redirect without Location"
            next_url = urljoin(current_url, location)
            next_host = _host(next_url)
            if not _same_brand_redirect(current_host, next_host):
                return None, f"{current_url}: rejected unrelated-domain redirect"
            previous_host = current_host
            current_url = next_url
            time.sleep(REQUEST_DELAY_SECONDS)
            continue
        return response, None
    return None, f"{start_url}: exceeded redirect limit"


def _clean_phone(raw: str) -> str | None:
    raw = re.sub(r"\s+", " ", (raw or "").strip())
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7 or len(digits) > 15 or len(set(digits)) <= 1:
        return None
    return raw


def _extract_contacts(soup: BeautifulSoup, page_url: str):
    emails: set[str] = set()
    phones: set[str] = set()

    for anchor in soup.select('a[href^="mailto:"]'):
        value = anchor.get("href", "").split(":", 1)[-1].split("?", 1)[0].strip()
        if EMAIL_RE.fullmatch(value):
            emails.add(value.lower())

    for anchor in soup.select('a[href^="tel:"]'):
        value = anchor.get("href", "").split(":", 1)[-1].split("?", 1)[0]
        phone = _clean_phone(value)
        if phone:
            phones.add(phone)

    visible_text = soup.get_text(" ", strip=True)
    visible_text = re.sub(r"\s*(\[at\]|\(at\)|\sat\s)\s*", "@", visible_text, flags=re.I)
    visible_text = re.sub(r"\s*(\[dot\]|\(dot\)|\sdot\s)\s*", ".", visible_text, flags=re.I)

    for match in EMAIL_RE.findall(visible_text):
        emails.add(match.lower())
    for match in PHONE_RE.findall(visible_text):
        phone = _clean_phone(match)
        if phone:
            phones.add(phone)

    # Also inspect JSON-LD, where many commerce sites publish contactPoint data.
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw_json = script.string or script.get_text(" ", strip=True)
        if raw_json:
            for email in EMAIL_RE.findall(raw_json):
                emails.add(email.lower())
            for match in PHONE_RE.findall(raw_json):
                phone = _clean_phone(match)
                if phone:
                    phones.add(phone)

    return emails, phones


def _link_priority(anchor) -> int | None:
    href = (anchor.get("href") or "").strip()
    if not href or href.lower().startswith((
        "mailto:", "tel:", "javascript:", "data:", "#",
    )):
        return None

    combined = " ".join((
        href,
        anchor.get_text(" ", strip=True),
        anchor.get("aria-label", ""),
        anchor.get("title", ""),
    )).lower()

    if any(word in combined for word in IGNORE_KEYWORDS):
        return None

    if any(word in combined for word in ("contact", "get in touch", "reach us")):
        return 0
    if any(word in combined for word in (
        "return", "refund", "exchange", "shipping", "delivery",
        "privacy", "policy", "terms", "legal",
    )):
        return 1
    if any(word in combined for word in (
        "customer service", "customer support", "help center",
        "help centre", "customer care",
    )):
        return 2
    if "support" in combined or "help" in combined:
        return 3
    if "about" in combined or "our story" in combined:
        return 4
    return None


def _discover_contact_links(
    soup: BeautifulSoup,
    page_url: str,
    canonical_host: str,
) -> list[tuple[int, str]]:
    discovered: list[tuple[int, str]] = []
    for anchor in soup.find_all("a", href=True):
        priority = _link_priority(anchor)
        if priority is None:
            continue
        absolute_url = _normalise_page_url(urljoin(page_url, anchor["href"]))
        parsed = urlparse(absolute_url)
        if parsed.scheme not in ("http", "https") or _host(absolute_url) != canonical_host:
            continue
        discovered.append((priority, absolute_url))

    discovered.sort(key=lambda item: item[0])
    unique: list[tuple[int, str]] = []
    seen: set[str] = set()
    for priority, url in discovered:
        if url not in seen:
            seen.add(url)
            unique.append((priority, url))
    return unique[:MAX_DISCOVERED_LINKS]


def _empty_result(
    original_website: str,
    canonical_website: str | None,
    errors: list[str],
) -> dict[str, Any]:
    return {
        "website": original_website,
        "original_website": original_website,
        "canonical_website": canonical_website,
        "business_emails": [],
        "business_phones": [],
        "email_sources": {},
        "phone_sources": {},
        "pages_checked": [],
        "pages_checked_count": 0,
        "errors": errors,
        "source_policy": (
            "Public pages on the brand's own website, including contact, support, "
            "privacy, returns, refund, shipping and delivery pages; robots.txt "
            "checked before each page and redirect request"
        ),
    }


def find_public_contacts(website: str) -> dict[str, Any]:
    original_website = normalise_website(website)
    original_host = _host(original_website)
    if not _is_public_host(original_host):
        raise ValueError("The supplied website must use a public hostname.")

    session = requests.Session()
    session.headers.update({
        "User-Agent": USER_AGENT,
        "Accept": "text/html,application/xhtml+xml",
    })
    robots_cache: dict[str, urllib.robotparser.RobotFileParser] = {}
    errors: list[str] = []

    try:
        homepage_response, homepage_error = _fetch_with_checked_redirects(
            session, original_website, robots_cache, expected_host=original_host,
        )
        if homepage_error:
            errors.append(homepage_error)
        if homepage_response is None:
            return _empty_result(original_website, None, errors)

        content_type = homepage_response.headers.get("Content-Type", "").lower()
        if homepage_response.status_code >= 400:
            errors.append(f"{homepage_response.url}: HTTP {homepage_response.status_code}")
            return _empty_result(original_website, None, errors)
        if "text/html" not in content_type:
            errors.append(f"{homepage_response.url}: non-HTML response")
            return _empty_result(original_website, None, errors)

        canonical_url = _normalise_page_url(homepage_response.url)
        canonical_host = _host(canonical_url)
        canonical_website = _origin(canonical_url)

        queue = deque()
        queued: set[str] = set()
        visited: set[str] = set()
        homepage_url = _normalise_page_url(canonical_url)
        queue.append(homepage_url)
        queued.add(homepage_url)

        email_sources: dict[str, set[str]] = {}
        phone_sources: dict[str, set[str]] = {}
        pages_checked: list[str] = []
        homepage_soup = BeautifulSoup(homepage_response.text, "html.parser")

        while queue and len(pages_checked) < MAX_PAGES:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            if url == homepage_url:
                response_url, soup = homepage_url, homepage_soup
            else:
                response, error = _fetch_with_checked_redirects(
                    session, url, robots_cache, expected_host=canonical_host,
                )
                time.sleep(REQUEST_DELAY_SECONDS)
                if error:
                    errors.append(error)
                    continue
                if response is None:
                    continue
                if response.status_code >= 400:
                    errors.append(f"{url}: HTTP {response.status_code}")
                    continue
                content_type = response.headers.get("Content-Type", "").lower()
                if "text/html" not in content_type:
                    continue
                response_url = _normalise_page_url(response.url)
                if _host(response_url) != canonical_host:
                    errors.append(f"{url}: redirected outside canonical host")
                    continue
                soup = BeautifulSoup(response.text, "html.parser")

            pages_checked.append(response_url)
            emails, phones = _extract_contacts(soup, response_url)
            for email in emails:
                email_sources.setdefault(email, set()).add(response_url)
            for phone in phones:
                phone_sources.setdefault(phone, set()).add(response_url)

            discovered = _discover_contact_links(soup, response_url, canonical_host)
            for priority, discovered_url in reversed(discovered):
                if discovered_url in visited or discovered_url in queued:
                    continue
                queued.add(discovered_url)
                if priority <= 1:
                    queue.appendleft(discovered_url)
                else:
                    queue.append(discovered_url)

            if response_url == homepage_url:
                for path in FALLBACK_PATHS:
                    fallback_url = _normalise_page_url(urljoin(canonical_website, path))
                    if fallback_url not in visited and fallback_url not in queued:
                        queued.add(fallback_url)
                        queue.append(fallback_url)

        return {
            "website": original_website,
            "original_website": original_website,
            "canonical_website": canonical_website,
            "business_emails": sorted(email_sources),
            "business_phones": sorted(phone_sources),
            "email_sources": {key: sorted(value) for key, value in email_sources.items()},
            "phone_sources": {key: sorted(value) for key, value in phone_sources.items()},
            "pages_checked": pages_checked,
            "pages_checked_count": len(pages_checked),
            "errors": errors,
            "source_policy": (
                "Public pages on the brand's own website, including contact, support, "
                "privacy, returns, refund, shipping and delivery pages; robots.txt "
                "checked before each page and redirect request"
            ),
        }
    finally:
        session.close()


if __name__ == "__main__":
    from pprint import pprint
    target = input("Brand website: ").strip()
    pprint(find_public_contacts(target))
