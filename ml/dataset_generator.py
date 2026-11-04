import numpy as np
import pandas as pd
from pathlib import Path

np.random.seed(42)

N = 5000

# Generate synthetic brand characteristics

data = {
    "active_ads": np.random.randint(0, 51, N),
    "ad_duration": np.random.randint(0, 181, N),
    "website_quality": np.random.uniform(0, 100, N),
    "social_activity": np.random.uniform(0, 100, N),
    "product_count": np.random.randint(0, 301, N),
    "brand_age": np.random.randint(1, 121, N),
    "posting_frequency": np.random.randint(0, 61, N),
    "premium_positioning": np.random.randint(0, 2, N)
}

df = pd.DataFrame(data)

# Calculate synthetic lead quality

score = (
    0.20 * (df["active_ads"] / 50) +
    0.15 * (df["ad_duration"] / 180) +
    0.15 * (df["website_quality"] / 100) +
    0.15 * (df["social_activity"] / 100) +
    0.10 * (df["product_count"] / 300) +
    0.05 * (df["brand_age"] / 120) +
    0.10 * (df["posting_frequency"] / 60) +
    0.10 * df["premium_positioning"]
)

# Introduce randomness

score += np.random.normal(0, 0.08, N)

score = np.clip(score, 0, 1)

# Generate labels

df["is_good_lead"] = (score >= 0.50).astype(int)

# Save dataset relative to this file

output_path = Path(__file__).parent / "synthetic_leads.csv"

df.to_csv(output_path, index=False)

# Display results

print("Dataset generated successfully!")
print(f"Saved to: {output_path}")

print("\nFirst five records:")
print(df.head())

print("\nClass distribution:")
print(df["is_good_lead"].value_counts())

print("\nDataset dimensions:", df.shape)