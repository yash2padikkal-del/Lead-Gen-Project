import os
import time
import requests

from datetime import datetime, timezone
from dotenv import load_dotenv


load_dotenv()


class MetaAdsProvider:

    BASE_URL = "https://api.metapi.io/v1"

    def __init__(self, api_key=None):

        self.api_key = (
            api_key or os.getenv("METAPI_API_KEY")
        )

        if not self.api_key:
            raise ValueError(
                "METAPI_API_KEY is missing."
            )

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        self.timeout = 30

    # ---------------------------------------------
    # CREATE SEARCH TASK
    # ---------------------------------------------

    def _create_task(self, brand_name):

        response = requests.post(
            f"{self.BASE_URL}/tasks",
            headers=self.headers,
            json={
                "q": brand_name,
                "country": "IN",
                "count": 100,
                "active_status": "active",
                "ad_type": "all",
                "search_type": "keyword_unordered",
                "sort_data": {
                    "mode": "relevancy_monthly_grouped",
                    "direction": "desc"
                }
            },
            timeout=self.timeout
        )

        response.raise_for_status()

        task_id = response.json().get("task_id")

        if not task_id:
            raise RuntimeError(
                "Metapi did not return a task ID."
            )

        return task_id

    # ---------------------------------------------
    # WAIT FOR TASK COMPLETION
    # ---------------------------------------------

    def _wait_for_task(self, task_id):

        deadline = time.time() + 600

        while time.time() < deadline:

            response = requests.get(
                f"{self.BASE_URL}/tasks/{task_id}/status",
                headers=self.headers,
                timeout=self.timeout
            )

            response.raise_for_status()

            data = response.json()

            status = data.get("status")

            if status == "succeeded":
                return True

            if status in {
                "failed",
                "timed_out",
                "aborted"
            }:
                raise RuntimeError(
                    f"Metapi task failed: "
                    f"{data.get('error_message', status)}"
                )

            time.sleep(5)

        raise TimeoutError(
            f"Metapi task {task_id} timed out."
        )

    # ---------------------------------------------
    # RETRIEVE RESULTS
    # ---------------------------------------------

    def _get_results(self, task_id):

        ads = []

        offset = 0
        page_size = 500

        while True:

            response = requests.get(
                f"{self.BASE_URL}/tasks/{task_id}/results",
                headers=self.headers,
                params={
                    "offset": offset,
                    "limit": page_size
                },
                timeout=60
            )

            response.raise_for_status()

            payload = response.json()

            items = payload.get("data", [])

            if not items:
                break

            ads.extend(items)

            pagination = payload.get(
                "pagination", {}
            )

            if not pagination.get("has_more"):
                break

            offset += len(items)

        return ads

    # ---------------------------------------------
    # DATE EXTRACTION
    # ---------------------------------------------

    @staticmethod
    def _parse_date(value):

        if value is None:
            return None

        if isinstance(value, (int, float)):

            try:
                return datetime.fromtimestamp(
                    value,
                    tz=timezone.utc
                )
            except (ValueError, OSError):
                return None

        if isinstance(value, str):

            try:
                return datetime.fromisoformat(
                    value.replace("Z", "+00:00")
                )
            except ValueError:
                return None

        return None

    @classmethod
    def _get_start_date(cls, ad):

        # Candidate field names: use only fields actually
        # present in the provider response.
        candidates = [
            "ad_delivery_start_time",
            "start_date",
            "ad_start_date",
            "started_at"
        ]

        for field in candidates:

            if ad.get(field) is not None:

                parsed = cls._parse_date(
                    ad[field]
                )

                if parsed:
                    return parsed

        return None

    # ---------------------------------------------
    # PUBLIC PROVIDER INTERFACE
    # ---------------------------------------------

    def get_ad_metrics(
        self,
        brand_name: str,
        website: str
    ) -> dict:

        task_id = self._create_task(
            brand_name
        )

        self._wait_for_task(task_id)

        ads = self._get_results(task_id)

        # Match the requested brand against provider page names.
        matching_ads = [
            ad for ad in ads
            if (
                (ad.get("provider_page_name") or "")
                .strip()
                .casefold()
                == brand_name.strip().casefold()
            )
        ]

        # Extract dates where available.
        start_dates = [
            self._get_start_date(ad)
            for ad in matching_ads
        ]

        start_dates = [
            date for date in start_dates
            if date is not None
        ]

        ad_duration = None

        if start_dates:

            earliest = min(start_dates)

            ad_duration = max(
                0,
                (datetime.now(timezone.utc) - earliest).days
            )

        return {
            "active_ads": len(matching_ads),
            "ad_duration": ad_duration,
            "earliest_observed_ad_date": (
                min(start_dates).isoformat()
                if start_dates else None
            ),
            "matched_ads": matching_ads,
            "total_ads_returned": len(ads),
            "date_data_available": bool(start_dates)
        }