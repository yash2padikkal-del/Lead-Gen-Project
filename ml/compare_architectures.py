import copy
import random

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import torch.optim as optim

from torch.utils.data import TensorDataset, DataLoader

from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score
)

from ml.preprocessing import prepare_data


# Reproducibility
SEED = 42

torch.manual_seed(SEED)
np.random.seed(SEED)
random.seed(SEED)


# Device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

print("Using device:", device)


# ANN architecture
class ExperimentANN(nn.Module):

    def __init__(self, input_size, hidden1, hidden2):

        super().__init__()

        self.network = nn.Sequential(

            nn.Linear(input_size, hidden1),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(hidden1, hidden2),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(hidden2, 1)

        )

    def forward(self, x):

        return self.network(x)


# Load data
X_train, X_val, X_test, y_train, y_val, y_test, scaler = prepare_data()


# Convert to tensors
X_train = torch.tensor(X_train, dtype=torch.float32)
X_val = torch.tensor(X_val, dtype=torch.float32)
X_test = torch.tensor(X_test, dtype=torch.float32)

y_train = torch.tensor(y_train, dtype=torch.float32).reshape(-1, 1)
y_val = torch.tensor(y_val, dtype=torch.float32).reshape(-1, 1)


# DataLoaders
train_dataset = TensorDataset(X_train, y_train)
val_dataset = TensorDataset(X_val, y_val)


# Architectures to compare
architectures = {

    "Large (64-32)": (64, 32),

    "Medium (32-16)": (32, 16),

    "Small (16-8)": (16, 8)

}


results = []


# Training configuration
EPOCHS = 100
PATIENCE = 10
BATCH_SIZE = 32


# Experiment loop
for name, (hidden1, hidden2) in architectures.items():

    print(f"\n{'=' * 45}")
    print(f"Training: {name}")
    print(f"{'=' * 45}")

    # Reset seed for comparable initialisation
    torch.manual_seed(SEED)

    # Model
    model = ExperimentANN(
        input_size=8,
        hidden1=hidden1,
        hidden2=hidden2
    ).to(device)

    # Count parameters
    parameters = sum(
        p.numel() for p in model.parameters()
        if p.requires_grad
    )

    # Optimiser and loss
    criterion = nn.BCEWithLogitsLoss()

    optimizer = optim.Adam(
        model.parameters(),
        lr=0.001,
        weight_decay=0.0001
    )

    # Reproducible shuffling
    generator = torch.Generator()
    generator.manual_seed(SEED)

    train_loader = DataLoader(
        train_dataset,
        batch_size=BATCH_SIZE,
        shuffle=True,
        generator=generator
    )

    val_loader = DataLoader(
        val_dataset,
        batch_size=BATCH_SIZE,
        shuffle=False
    )

    best_val_loss = float("inf")
    best_state = None

    patience_counter = 0
    best_epoch = 0

    # Training
    for epoch in range(EPOCHS):

        model.train()

        train_loss = 0

        for inputs, labels in train_loader:

            inputs = inputs.to(device)
            labels = labels.to(device)

            outputs = model(inputs)

            loss = criterion(outputs, labels)

            optimizer.zero_grad()

            loss.backward()

            optimizer.step()

            train_loss += loss.item()

        train_loss /= len(train_loader)

        # Validation
        model.eval()

        val_loss = 0

        with torch.no_grad():

            for inputs, labels in val_loader:

                inputs = inputs.to(device)
                labels = labels.to(device)

                outputs = model(inputs)

                loss = criterion(outputs, labels)

                val_loss += loss.item()

        val_loss /= len(val_loader)

        # Checkpoint
        if val_loss < best_val_loss:

            best_val_loss = val_loss

            best_state = copy.deepcopy(model.state_dict())

            best_epoch = epoch + 1

            patience_counter = 0

        else:

            patience_counter += 1

        if (epoch + 1) % 10 == 0:

            print(
                f"Epoch {epoch + 1}: "
                f"Train Loss = {train_loss:.4f}, "
                f"Val Loss = {val_loss:.4f}"
            )

        if patience_counter >= PATIENCE:

            print("Early stopping triggered.")

            break

    # Restore best model
    model.load_state_dict(best_state)

    model.eval()

    # Test evaluation
    with torch.no_grad():

        probabilities = torch.sigmoid(
            model(X_test.to(device))
        ).cpu().numpy().flatten()

    predictions = (probabilities >= 0.5).astype(int)

    # Metrics
    accuracy = accuracy_score(y_test, predictions)

    precision = precision_score(y_test, predictions)

    recall = recall_score(y_test, predictions)

    f1 = f1_score(y_test, predictions)

    auc = roc_auc_score(y_test, probabilities)

    # Store results
    results.append({

        "Architecture": name,

        "Parameters": parameters,

        "Best Epoch": best_epoch,

        "Validation Loss": best_val_loss,

        "Accuracy": accuracy,

        "Precision": precision,

        "Recall": recall,

        "F1 Score": f1,

        "ROC-AUC": auc

    })


# Results table
results_df = pd.DataFrame(results)

print("\n\nARCHITECTURE COMPARISON")
print("=" * 100)

print(
    results_df.to_string(
        index=False,
        float_format=lambda x: f"{x:.4f}"
    )
)

# Save results
results_df.to_csv(
    "ml/architecture_results.csv",
    index=False
)

print("\nResults saved to ml/architecture_results.csv")