import torch
import torch.nn as nn
import torch.optim as optim
import joblib

from pathlib import Path
from torch.utils.data import TensorDataset, DataLoader

from ml.model import LeadClassifier
from ml.preprocessing import prepare_data


torch.manual_seed(42)

BASE_DIR = Path(__file__).parent

MODEL_PATH = BASE_DIR / "lead_classifier.pth"
SCALER_PATH = BASE_DIR / "scaler.joblib"


# Load dataset

(
    X_train,
    X_val,
    X_test,
    y_train,
    y_val,
    y_test,
    scaler
) = prepare_data()


joblib.dump(scaler, SCALER_PATH)


# Convert to tensors

X_train = torch.tensor(X_train, dtype=torch.float32)
X_val = torch.tensor(X_val, dtype=torch.float32)
X_test = torch.tensor(X_test, dtype=torch.float32)

y_train = torch.tensor(
    y_train,
    dtype=torch.float32
).reshape(-1, 1)

y_val = torch.tensor(
    y_val,
    dtype=torch.float32
).reshape(-1, 1)


# Random feature masking

def apply_feature_dropout(x):

    batch_size, feature_count = x.shape

    masks = torch.zeros_like(x)

    for i in range(batch_size):

        available = torch.randint(
            3,
            feature_count + 1,
            (1,)
        ).item()

        selected = torch.randperm(feature_count)[:available]

        masks[i, selected] = 1.0

    masked_features = x * masks

    model_input = torch.cat(
        [masked_features, masks],
        dim=1
    )

    return model_input


# Validation masks are fixed for reproducibility

def create_validation_inputs(x, repetitions=5):

    inputs = []

    generator = torch.Generator().manual_seed(123)

    for _ in range(repetitions):

        masks = torch.zeros_like(x)

        for i in range(len(x)):

            available = torch.randint(
                3,
                x.shape[1] + 1,
                (1,),
                generator=generator
            ).item()

            selected = torch.randperm(
                x.shape[1],
                generator=generator
            )[:available]

            masks[i, selected] = 1.0

        masked = x * masks

        inputs.append(
            torch.cat([masked, masks], dim=1)
        )

    return inputs


# DataLoaders

train_dataset = TensorDataset(X_train, y_train)
val_dataset = TensorDataset(X_val, y_val)

train_loader = DataLoader(
    train_dataset,
    batch_size=32,
    shuffle=True
)

val_loader = DataLoader(
    val_dataset,
    batch_size=32,
    shuffle=False
)


# Prepare validation inputs

validation_inputs = create_validation_inputs(X_val)


# Initialise ANN

model = LeadClassifier(input_size=16)


criterion = nn.BCEWithLogitsLoss()

optimizer = optim.Adam(
    model.parameters(),
    lr=0.001,
    weight_decay=0.0001
)


# Training configuration

epochs = 100
patience = 10

best_val_loss = float("inf")
counter = 0


# Training loop

for epoch in range(epochs):

    model.train()

    train_loss = 0

    for inputs, labels in train_loader:

        model_inputs = apply_feature_dropout(inputs)

        outputs = model(model_inputs)

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

        for masked_inputs in validation_inputs:

            outputs = model(masked_inputs)

            loss = criterion(
                outputs,
                y_val
            )

            val_loss += loss.item()

    val_loss /= len(validation_inputs)


    # Save best model

    if val_loss < best_val_loss:

        best_val_loss = val_loss

        counter = 0

        torch.save(
            model.state_dict(),
            MODEL_PATH
        )

    else:

        counter += 1


    if (epoch + 1) % 5 == 0:

        print(
            f"Epoch [{epoch + 1}/{epochs}] "
            f"Train Loss: {train_loss:.4f} "
            f"Val Loss: {val_loss:.4f}"
        )


    if counter >= patience:

        print("\nEarly stopping triggered!")

        break


print("\nTraining completed!")

print("Best validation loss:", best_val_loss)

print("Model saved:", MODEL_PATH)