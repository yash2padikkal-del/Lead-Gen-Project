from typing import Protocol, Optional


class SocialProvider(Protocol):
    """
    Retrieves publicly available business social metrics.

    Expected output:
    {
        "followers": 8400,
        "social_activity": 72.5,
        "posting_frequency": 18
    }
    """

    def get_profile(self, handle: str) -> dict:
        ...


class AdvertisingProvider(Protocol):
    """
    Retrieves advertising metrics.

    Expected output:
    {
        "active_ads": 12,
        "ad_duration": 45
    }
    """

    def get_ad_metrics(
        self,
        brand_name: str,
        website: str
    ) -> dict:
        ...


class BrandMetadataProvider(Protocol):
    """
    Retrieves brand history.

    Expected output:
    {
        "brand_age": 36
    }

    brand_age is measured in months.
    """

    def get_brand_metadata(
        self,
        brand_name: str,
        website: str
    ) -> dict:
        ...