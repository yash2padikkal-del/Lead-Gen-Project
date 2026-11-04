from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import torch

from ml.model import LeadClassifier


BASE_DIR = Path(__file__).parent

MODEL_PATH = BASE_DIR / "lead_classifier.pth"
SCALER_PATH = BASE_DIR / "scaler.joblib"


FEATURES = [
    "active_ads",
    "ad_duration",
    "website_quality",
    "social_activity",
    "product_count",
    "brand_age",
    "posting_frequency",
    "premium_positioning"
]


FEATURE_RANGES = {
    "active_ads": (0, 50),
    "ad_duration": (0, 180),
    "website_quality": (0, 100),
    "social_activity": (0, 100),
    "product_count": (0, 300),
    "brand_age": (1, 120),
    "posting_frequency": (0, 60),
    "premium_positioning": (0, 1)
}


MINIMUM_FEATURES = 3


class LeadInference:

    def __init__(self):

        if not MODEL_PATH.exists():

            raise FileNotFoundError(
                f"Model checkpoint not found: {MODEL_PATH}"
            )

        if not SCALER_PATH.exists():

            raise FileNotFoundError(
                f"Scaler not found: {SCALER_PATH}"
            )

        self.scaler = joblib.load(SCALER_PATH)

        self.model = LeadClassifier(input_size=16)

        self.model.load_state_dict(
            torch.load(
                MODEL_PATH,
                map_location="cpu",
                weights_only=True
            )
        )

        self.model.eval()


    def predict(self, features):

        values = []
        mask = []

        observed = []
        missing = []

        for name in FEATURES:

            value = features.get(name)

            if value is None:

                values.append(float(self.scaler.mean_[FEATURES.index(name)]))

                mask.append(0.0)

                missing.append(name)

                continue

            try:

                value = float(value)

            except (TypeError, ValueError):

                raise ValueError(
                    f"Invalid value for {name}: {value}"
                )

            if not np.isfinite(value):

                raise ValueError(
                    f"{name} must be finite."
                )

            minimum, maximum = FEATURE_RANGES[name]

            if not minimum <= value <= maximum:

                raise ValueError(
                    f"{name} must be between "
                    f"{minimum} and {maximum}."
                )

            values.append(value)

            mask.append(1.0)

            observed.append(name)


        available_count = len(observed)

        if available_count < MINIMUM_FEATURES:

            raise ValueError(
                f"At least {MINIMUM_FEATURES} features are required. "
                f"Only {available_count} available."
            )


        # Scale values

        dataframe = pd.DataFrame(
            [values],
            columns=FEATURES
        )

        scaled = self.scaler.transform(dataframe)[0]


        # Apply availability mask

        scaled = scaled * np.array(mask)

        model_input = np.concatenate([
            scaled,
            np.array(mask)
        ])


        tensor = torch.tensor(
            model_input,
            dtype=torch.float32
        ).unsqueeze(0)


        # Prediction

        with torch.no_grad():

            logits = self.model(tensor)

            probability = torch.sigmoid(logits).item()


        return {

            "priority_score": round(probability * 100, 2),

            "priority_probability": round(probability, 4),

            "model_version": "lead_classifier_v2_masked",

            "available_features": available_count,

            "feature_coverage": round(
                available_count / len(FEATURES),
                3
            ),

            "observed_features": observed,

            "missing_features": missing,

            "score_type": (
                "complete"
                if available_count == len(FEATURES)
                else "partial"
            )
        }


if __name__ == "__main__":

    inference = LeadInference()

    features = {

        "active_ads": 12,

        "ad_duration": 45,

        "website_quality": 85,

        "social_activity": None,

        "product_count": 120,

        "brand_age": None,

        "posting_frequency": 20,

        "premium_positioning": 1
    }

    result = inference.predict(features)

    print("\nANN INFERENCE TEST")
    print("--------------------------")

    for key, value in result.items():

        print(f"{key}: {value}")