import torch
import numpy as np

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report
)

from ml.model import LeadClassifier
from ml.preprocessing import prepare_data


# Load data
X_train, X_val, X_test, y_train, y_val, y_test, scaler = prepare_data()

# Convert test data
X_test = torch.tensor(X_test, dtype=torch.float32)

# Load trained model
model = LeadClassifier()

model.load_state_dict(
    torch.load("ml/lead_classifier.pth", map_location="cpu", weights_only=True)
)

model.eval()

# Generate predictions
with torch.no_grad():

    logits = model(X_test)

    probabilities = torch.sigmoid(logits).numpy().flatten()

    predictions = (probabilities >= 0.5).astype(int)


# Evaluate
print("\nMODEL EVALUATION")
print("----------------------------")

print("Accuracy:", accuracy_score(y_test, predictions))

print("Precision:", precision_score(y_test, predictions))

print("Recall:", recall_score(y_test, predictions))

print("F1 Score:", f1_score(y_test, predictions))

print("ROC-AUC:", roc_auc_score(y_test, probabilities))

print("\nConfusion Matrix:")
print(confusion_matrix(y_test, predictions))

print("\nClassification Report:")
print(classification_report(y_test, predictions))