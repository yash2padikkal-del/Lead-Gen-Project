import math
from typing import Any


FEATURE_ORDER = (
    "active_ads",
    "ad_duration",
    "website_quality",
    "social_activity",
    "product_count",
    "brand_age",
    "posting_frequency",
    "premium_positioning",
)


FEATURE_RANGES = {
    "active_ads": (0.0, 50.0),
    "ad_duration": (0.0, 180.0),
    "website_quality": (0.0, 100.0),
    "social_activity": (0.0, 100.0),
    "product_count": (0.0, 300.0),
    "brand_age": (1.0, 120.0),
    "posting_frequency": (0.0, 60.0),
    "premium_positioning": (0.0, 1.0),
}


MINIMUM_FEATURES = 3


def _number(value: Any):

    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)

    except (TypeError, ValueError, OverflowError):
        return None

    if not math.isfinite(number):
        return None

    return number


def _first(mapping, *keys):

    for key in keys:

        if key in mapping and mapping[key] is not None:
            return mapping[key]

    return None


def build_features(
    website_features=None,
    social_data=None,
    advertising_data=None,
    brand_data=None
):

    website = website_features or {}
    social = social_data or {}
    advertising = advertising_data or {}
    brand = brand_data or {}

    raw = {

        "active_ads": _first(
            advertising,
            "active_ads",
            "active_ad_count"
        ),

        "ad_duration": _first(
            advertising,
            "ad_duration",
            "average_ad_duration",
            "days_shown"
        ),

        "website_quality": _first(
            website,
            "website_quality"
        ),

        "social_activity": _first(
            social,
            "social_activity"
        ),

        "product_count": _first(
            website,
            "product_count"
        ),

        "brand_age": _first(
            brand,
            "brand_age",
            "brand_age_months"
        ),

        "posting_frequency": _first(
            social,
            "posting_frequency",
            "posts_per_month"
        ),

        "premium_positioning": _first(
            website,
            "premium_positioning"
        )
    }

    features = {}
    feature_mask = {}
    invalid = {}

    for name in FEATURE_ORDER:

        value = _number(raw[name])

        low, high = FEATURE_RANGES[name]

        if value is None:

            features[name] = None
            feature_mask[name] = 0

            continue

        if value < low or value > high:

            invalid[name] = {
                "value": value,
                "allowed_range": [low, high],
                "action": "clamped"
            }

            value = min(high, max(low, value))

        features[name] = float(value)
        feature_mask[name] = 1

    observed = [
        name for name in FEATURE_ORDER
        if feature_mask[name] == 1
    ]

    missing = [
        name for name in FEATURE_ORDER
        if feature_mask[name] == 0
    ]

    available_count = len(observed)

    return {

        "features": features,

        "feature_mask": feature_mask,

        "complete": available_count == len(FEATURE_ORDER),

        "inference_ready": available_count >= MINIMUM_FEATURES,

        "available_count": available_count,

        "coverage": round(
            available_count / len(FEATURE_ORDER),
            3
        ),

        "missing_features": missing,

        "observed_features": observed,

        "invalid_features": invalid,

        "feature_order": list(FEATURE_ORDER)
    }


if __name__ == "__main__":

    result = build_features(

        website_features={
            "website_quality": 72,
            "product_count": 48,
            "premium_positioning": 1
        },

        advertising_data={
            "active_ads": 4,
            "ad_duration": 18
        }
    )

    assert result["inference_ready"]

    assert result["available_count"] == 5

    assert result["feature_mask"]["social_activity"] == 0

    assert result["features"]["social_activity"] is None

    print("Feature-builder tests passed.")
    print(result)