import pandas as pd

from pathlib import Path
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler


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


def prepare_data():

    path = Path(__file__).parent / "synthetic_leads.csv"

    df = pd.read_csv(path)

    X = df[FEATURES]
    y = df["is_good_lead"]

    X_train, X_temp, y_train, y_temp = train_test_split(
        X,
        y,
        test_size=0.30,
        random_state=42,
        stratify=y
    )

    X_val, X_test, y_val, y_test = train_test_split(
        X_temp,
        y_temp,
        test_size=0.50,
        random_state=42,
        stratify=y_temp
    )

    scaler = StandardScaler()

    X_train = scaler.fit_transform(X_train)

    X_val = scaler.transform(X_val)

    X_test = scaler.transform(X_test)

    print("\nDataset Split")
    print("--------------------")

    print("Training:", X_train.shape)
    print("Validation:", X_val.shape)
    print("Testing:", X_test.shape)

    return (
        X_train,
        X_val,
        X_test,
        y_train.to_numpy(),
        y_val.to_numpy(),
        y_test.to_numpy(),
        scaler
    )


if __name__ == "__main__":
    prepare_data()