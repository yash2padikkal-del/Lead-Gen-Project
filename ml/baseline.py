import pandas as pd

from sklearn.linear_model import LogisticRegression

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix
)

from ml.preprocessing import prepare_data


# Load dataset
X_train, X_val, X_test, y_train, y_val, y_test, scaler = prepare_data()


# Initialise logistic regression
model = LogisticRegression(
    max_iter=1000,
    random_state=42
)


# Train
model.fit(X_train, y_train)


# Predictions
predictions = model.predict(X_test)

probabilities = model.predict_proba(X_test)[:, 1]


# Evaluate
results = {

    "Accuracy": accuracy_score(y_test, predictions),

    "Precision": precision_score(y_test, predictions),

    "Recall": recall_score(y_test, predictions),

    "F1 Score": f1_score(y_test, predictions),

    "ROC-AUC": roc_auc_score(y_test, probabilities)

}


print("\nLOGISTIC REGRESSION RESULTS")
print("=" * 40)

for metric, value in results.items():

    print(f"{metric}: {value:.4f}")


print("\nConfusion Matrix:")
print(confusion_matrix(y_test, predictions))


# Feature coefficients
print("\nFeature Coefficients:")

for feature, coefficient in zip(
    [
        "active_ads",
        "ad_duration",
        "website_quality",
        "social_activity",
        "product_count",
        "brand_age",
        "posting_frequency",
        "premium_positioning"
    ],
    model.coef_[0]
):

    print(f"{feature}: {coefficient:.4f}")