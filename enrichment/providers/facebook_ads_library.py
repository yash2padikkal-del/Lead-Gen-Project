import json
import os

from pathlib import Path
from collections import defaultdict
from urllib.parse import urlparse

from enrichment.qualification import (
    parse_follower_count,
    normalise_instagram_handle,
)


class FacebookAdsLibraryProvider:

    def __init__(self, json_paths=None):

        data_dir = Path(__file__).resolve().parents[2] / "data"

        if json_paths is None:

            env_path = os.getenv("FACEBOOK_ADS_JSON")

            if env_path:
                json_paths = [env_path]

            else:
                json_paths = [
                    data_dir / "facebook_ads.json",
                    data_dir / "independent_clothing.json",
                ]

        self.json_paths = [
            Path(p) for p in json_paths
        ]

        self.ads = []
        self.advertisers = {}

        self._load_data()
        self._aggregate_advertisers()

    # --------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------

    def _load_data(self):

        seen_ads = set()

        for path in self.json_paths:

            if not path.exists():

                print(
                    f"Dataset not found, skipping: {path}"
                )

                continue

            with path.open(
                "r",
                encoding="utf-8"
            ) as file:

                data = json.load(file)

            if not isinstance(data, list):

                raise ValueError(
                    f"Invalid dataset format: {path}"
                )

            for ad in data:

                if not isinstance(ad, dict):
                    continue

                ad_id = ad.get("ad_id")

                if ad_id:

                    key = str(ad_id)

                    if key in seen_ads:
                        continue

                    seen_ads.add(key)

                self.ads.append(ad)

        if not self.ads:

            raise ValueError(
                "No advertisement records were loaded."
            )

        print(
            f"Loaded {len(self.ads)} unique advertisements."
        )

    # --------------------------------------------------
    # AGGREGATE ADVERTISERS
    # --------------------------------------------------

    def _aggregate_advertisers(self):

        grouped = defaultdict(list)

        for index, ad in enumerate(self.ads):

            page_id = ad.get("advertiser_page_id")

            # Do not silently discard advertisers without page IDs.
            # Use a stable fallback identity.
            if page_id:

                key = str(page_id)

            else:

                name = str(
                    ad.get("advertiser_name") or ""
                ).strip().lower()

                if not name:
                    continue

                key = f"name:{name}"

            grouped[key].append(ad)

        for page_id, ads in grouped.items():

            active_ads = [
                ad for ad in ads
                if ad.get("is_active") is True
            ]

            # Parse numeric and abbreviated follower counts.
            followers = []

            for ad in ads:

                count = parse_follower_count(
                    ad.get("advertiser_ig_followers")
                )

                if count is not None:
                    followers.append(count)

            # Normalise Instagram handles before storing.
            usernames = []

            for ad in ads:

                handle = normalise_instagram_handle(
                    ad.get("advertiser_ig_username")
                )

                if handle:
                    usernames.append(handle)

            usernames = list(dict.fromkeys(usernames))

            durations = []

            for ad in active_ads:

                value = ad.get("days_shown")

                try:

                    if value is not None:
                        durations.append(float(value))

                except (TypeError, ValueError):
                    pass

            websites = list(dict.fromkeys(
                str(ad["link_url"]).strip()
                for ad in ads
                if ad.get("link_url")
            ))

            categories = []

            for ad in ads:

                raw_categories = ad.get(
                    "advertiser_categories_json"
                )

                if isinstance(raw_categories, str):

                    try:
                        raw_categories = json.loads(
                            raw_categories
                        )

                    except json.JSONDecodeError:
                        raw_categories = []

                if isinstance(raw_categories, list):

                    categories.extend(
                        str(category).strip()
                        for category in raw_categories
                        if category
                    )

            categories = list(dict.fromkeys(categories))

            self.advertisers[page_id] = {

                "page_id": page_id,

                "brand_name": ads[0].get(
                    "advertiser_name"
                ),

                "facebook_url": ads[0].get(
                    "advertiser_url"
                ),

                "instagram_handle": (
                    usernames[0] if usernames else None
                ),

                "followers": (
                    max(followers) if followers else None
                ),

                "active_ads": len({
                    str(ad.get("ad_id"))
                    for ad in active_ads
                    if ad.get("ad_id")
                }),

                "ad_duration": (
                    max(durations) if durations else None
                ),

                "websites": websites,

                "categories": categories,

                "ads": ads,
            }

        print(
            f"Aggregated {len(self.advertisers)} advertisers."
        )

    # --------------------------------------------------
    # ADVERTISER DISCOVERY
    # --------------------------------------------------

    def get_advertisers(self):

        return list(
            self.advertisers.values()
        )

    # --------------------------------------------------
    # SOCIAL PROVIDER
    # --------------------------------------------------

    def get_profile(self, handle):

        normalized = normalise_instagram_handle(handle)

        if not normalized:
            return {}

        normalized = normalized.lower()

        for advertiser in self.advertisers.values():

            candidate = normalise_instagram_handle(
                advertiser.get("instagram_handle")
            )

            if (
                candidate
                and candidate.lower() == normalized
            ):

                followers = advertiser.get("followers")

                if followers is None:
                    return {}

                return {
                    "followers": followers
                }

        return {}

    # --------------------------------------------------
    # ADVERTISING PROVIDER
    # --------------------------------------------------

    def get_ad_metrics(self, brand_name, website):

        if not brand_name:
            return {}

        target = brand_name.strip().lower()

        matches = [
            advertiser
            for advertiser in self.advertisers.values()
            if (
                advertiser.get("brand_name") or ""
            ).strip().lower() == target
        ]

        if len(matches) > 1:

            matches = [
                advertiser
                for advertiser in matches
                if self._website_matches(
                    website,
                    advertiser["websites"]
                )
            ]

        if len(matches) != 1:
            return {}

        advertiser = matches[0]

        return {
            "active_ads": advertiser["active_ads"],
            "ad_duration": advertiser["ad_duration"],
        }

    # --------------------------------------------------
    # WEBSITE MATCHING
    # --------------------------------------------------

    @staticmethod
    def _get_domain(url):

        if not url:
            return None

        try:

            parsed = urlparse(
                url if "://" in url else f"https://{url}"
            )

            domain = (
                parsed.hostname or ""
            ).lower()

            if domain.startswith("www."):
                domain = domain[4:]

            return domain or None

        except (ValueError, TypeError):

            return None

    @staticmethod
    def _website_matches(website, candidates):

        target = (
            FacebookAdsLibraryProvider._get_domain(
                website
            )
        )

        if not target:
            return False

        return any(
            FacebookAdsLibraryProvider._get_domain(
                candidate
            ) == target
            for candidate in candidates
        )

    # --------------------------------------------------
    # FOLLOWER FILTERING
    # --------------------------------------------------

    def get_candidates(self, follower_limit=10000):

        candidates = []

        for advertiser in self.advertisers.values():

            followers = advertiser.get("followers")

            if followers is None:
                status = "pending_enrichment"

            elif followers >= follower_limit:
                status = "rejected"

            else:
                status = "potential_candidate"

            candidates.append({

                **advertiser,

                "follower_status": status,

            })

        return candidates