import torch
import torch.nn as nn


class LeadClassifier(nn.Module):

    def __init__(self, input_size=16):
        super().__init__()

        self.network = nn.Sequential(
            nn.Linear(input_size, 32),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.2),

            nn.Linear(16, 8),
            nn.ReLU(),

            nn.Linear(8, 1)
        )

    def forward(self, x):
        return self.network(x)


if __name__ == "__main__":

    model = LeadClassifier()

    sample = torch.randn(5, 16)

    output = model(sample)

    print("Input shape:", sample.shape)
    print("Output shape:", output.shape)
    print("Probabilities:", torch.sigmoid(output))