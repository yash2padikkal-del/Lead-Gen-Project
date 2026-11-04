"""
Lead enrichment and ANN inference pipeline.

Qualification is metadata only. It never blocks enrichment
or ANN inference.

Every advertiser is enriched using whatever information is
available. The ANN uses the feature availability mask to
handle incomplete feature vectors.
"""

from datetime import datetime, timezone

from ml.feature_extractor import extract_features, verify_website
from ml.feature_builder import build_features
from ml.inference import LeadInference

from enrichment.public_contacts import find_public_contacts
from enrichment.qualification import qualify_lead


MINIMUM_FEATURES = 3


class LeadGenerationPipeline:

    def __init__(
        self,
        social_provider=None,
        advertising_provider=None,
        brand_metadata_provider=None,
        inference_engine=None,
    ):

        self.social_provider = social_provider
        self.advertising_provider = advertising_provider
        self.brand_metadata_provider = brand_metadata_provider

        self.inference = (
            inference_engine or LeadInference()
        )

    # --------------------------------------------------
    # PROVIDER HELPER
    # --------------------------------------------------

    @staticmethod
    def _call_provider(provider, method_name, *args):

        if provider is None:
            return {}

        method = getattr(provider, method_name, None)

        if not callable(method):
            return {}

        try:

            result = method(*args)

            return result if isinstance(result, dict) else {}

        except Exception as error:

            print(
                f"[warn] Provider error ({method_name}): {error}"
            )

            return {}

    # --------------------------------------------------
    # WEBSITE ENRICHMENT
    # --------------------------------------------------

    def _extract_website_data(self, website):

        result = {
            "website_features": {},
            "contact_data": {},
            "website_verification": {},
            "errors": [],
        }

        if not website:

            result["errors"].append(
                "Website unavailable; website enrichment skipped."
            )

            return result

        # Verify the website independently.

        try:

            result["website_verification"] = (
                verify_website(website) or {}
            )

        except Exception as error:

            result["errors"].append(
                f"Website verification failed: {error}"
            )

        verification_status = (
            result["website_verification"].get("status")
        )

        # Extract website features when verification succeeds.
        # An inaccessible website does not block other enrichment.

        if verification_status == "verified":

            try:

                result["website_features"] = (
                    extract_features(website) or {}
                )

            except Exception as error:

                result["errors"].append(
                    f"Website feature extraction failed: {error}"
                )

        else:

            reason = result["website_verification"].get(
                "reason",
                "Website could not be verified."
            )

            result["errors"].append(reason)

        # Contact information is optional.
        # Attempt it independently of qualification.

        try:

            result["contact_data"] = (
                find_public_contacts(website) or {}
            )

        except Exception as error:

            result["errors"].append(
                f"Contact extraction failed: {error}"
            )

        return result

    # --------------------------------------------------
    # MAIN PROCESSING
    # --------------------------------------------------

    def process_lead(self, lead):

        timestamp = datetime.now(
            timezone.utc
        ).isoformat()

        brand_name = lead.get("brand_name")
        website = lead.get("website")
        handle = lead.get("instagram_handle")

        result = {

            "brand_name": brand_name,

            "website": website,

            "instagram_handle": handle,

            "status": "processing",

            "priority_score": None,

            "priority_probability": None,

            "model_version": None,

            "available_features": 0,

            "feature_coverage": 0,

            "score_type": None,

            "features": {},

            "missing_features": [],

            "observed_features": [],

            "invalid_features": {},

            "qualification": {},

            "enrichment": {},

            "errors": [],

            "processed_at": timestamp,
        }

        # --------------------------------------------------
        # 1. WEBSITE ENRICHMENT
        # --------------------------------------------------

        website_data = self._extract_website_data(
            website
        )

        website_features = website_data.get(
            "website_features",
            {}
        )

        contact_data = website_data.get(
            "contact_data",
            {}
        )

        result["errors"].extend(
            website_data.get("errors", [])
        )

        # --------------------------------------------------
        # 2. SOCIAL ENRICHMENT
        # --------------------------------------------------

        social_data = self._call_provider(
            self.social_provider,
            "get_profile",
            handle
        )

        # --------------------------------------------------
        # 3. ADVERTISING ENRICHMENT
        # --------------------------------------------------

        advertising_data = self._call_provider(
            self.advertising_provider,
            "get_ad_metrics",
            brand_name,
            website
        )

        # --------------------------------------------------
        # 4. BRAND METADATA ENRICHMENT
        # --------------------------------------------------

        brand_data = self._call_provider(
            self.brand_metadata_provider,
            "get_brand_metadata",
            brand_name,
            website
        )

        # --------------------------------------------------
        # 5. STORE ALL ENRICHMENT
        # --------------------------------------------------

        result["enrichment"] = {

            "website": website_features,

            "website_verification": website_data.get(
                "website_verification",
                {}
            ),

            "contacts": contact_data,

            "social": social_data,

            "advertising": advertising_data,

            "brand": brand_data,
        }

        # --------------------------------------------------
        # 6. MERGE ENRICHED INFORMATION
        # --------------------------------------------------

        enriched_lead = dict(lead)

        enriched_lead["website_verification"] = (
            website_data.get(
                "website_verification",
                {}
            )
        )

        # Use the social provider's follower count when available.

        if social_data.get("followers") is not None:

            enriched_lead["instagram_followers"] = (
                social_data["followers"]
            )

        # Preserve contact information.
        # Contacts are not qualification requirements.

        enriched_lead["business_emails"] = (
            contact_data.get("business_emails", [])
        )

        enriched_lead["business_phones"] = (
            contact_data.get("business_phones", [])
        )

        # --------------------------------------------------
        # 7. QUALIFICATION METADATA
        # --------------------------------------------------

        try:

            qualification = qualify_lead(
                enriched_lead
            )

            result["qualification"] = {

                "qualified": qualification.get(
                    "qualified",
                    False
                ),

                "qualification_reasons": qualification.get(
                    "qualification_reasons",
                    []
                ),

                "qualification_status": qualification.get(
                    "qualification_status",
                    "pending_enrichment"
                ),

                "hard_disqualifiers": qualification.get(
                    "hard_disqualifiers",
                    []
                ),

                "missing_information": qualification.get(
                    "missing_information",
                    []
                ),

                "qualification_rule": qualification.get(
                    "qualification_rule"
                ),
            }

        except Exception as error:

            result["qualification"] = {

                "qualified": False,

                "qualification_status": "qualification_error",

                "qualification_reasons": [],

                "hard_disqualifiers": [],

                "missing_information": [
                    "Qualification could not be completed."
                ],
            }

            result["errors"].append(
                f"Qualification error: {error}"
            )

        # IMPORTANT:
        # Qualification does not control the pipeline.
        # Do not return here, even if the lead is rejected
        # or missing qualification information.

        # --------------------------------------------------
        # 8. BUILD AVAILABLE ANN FEATURES
        # --------------------------------------------------

        try:

            feature_result = build_features(

                website_features=website_features,

                social_data=social_data,

                advertising_data=advertising_data,

                brand_data=brand_data,
            )

        except Exception as error:

            result["status"] = "feature_error"

            result["errors"].append(
                f"Feature building failed: {error}"
            )

            return result

        features = feature_result.get(
            "features",
            {}
        )

        result["features"] = features

        result["missing_features"] = (
            feature_result.get(
                "missing_features",
                []
            )
        )

        result["observed_features"] = (
            feature_result.get(
                "observed_features",
                []
            )
        )

        result["invalid_features"] = (
            feature_result.get(
                "invalid_features",
                {}
            )
        )

        result["available_features"] = (
            feature_result.get(
                "available_count",
                0
            )
        )

        result["feature_coverage"] = (
            feature_result.get(
                "coverage",
                0
            )
        )

        # --------------------------------------------------
        # 9. CHECK FEATURE AVAILABILITY
        # --------------------------------------------------

        if result["available_features"] < MINIMUM_FEATURES:

            result["status"] = "pending_features"

            result["errors"].append(
                f"ANN inference requires at least "
                f"{MINIMUM_FEATURES} available features. "
                f"Only {result['available_features']} available."
            )

            return result

        # --------------------------------------------------
        # 10. ANN INFERENCE
        # --------------------------------------------------

        try:

            prediction = self.inference.predict(
                features
            )

            result["priority_score"] = (
                prediction["priority_score"]
            )

            result["priority_probability"] = (
                prediction["priority_probability"]
            )

            result["model_version"] = (
                prediction["model_version"]
            )

            result["available_features"] = (
                prediction.get(
                    "available_features",
                    result["available_features"]
                )
            )

            result["feature_coverage"] = (
                prediction.get(
                    "feature_coverage",
                    result["feature_coverage"]
                )
            )

            result["observed_features"] = (
                prediction.get(
                    "observed_features",
                    result["observed_features"]
                )
            )

            result["missing_features"] = (
                prediction.get(
                    "missing_features",
                    result["missing_features"]
                )
            )

            result["score_type"] = (
                prediction.get("score_type")
            )

            result["status"] = "scored"

        except Exception as error:

            result["status"] = "inference_error"

            result["errors"].append(
                f"ANN inference failed: {error}"
            )

        return result

