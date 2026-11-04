from ml.inference import LeadInference

inference = LeadInference()

features = {
    "active_ads": 12,
    "ad_duration": 45,
    "website_quality": 85,
    "social_activity": 70,
    "product_count": 120,
    "brand_age": 36,
    "posting_frequency": 20,
    "premium_positioning": 1
}

result = inference.predict(features)

print("\nANN INFERENCE TEST")
print("--------------------------")

print("Priority score:", result["priority_score"])
print("Probability:", result["priority_probability"])
print("Model:", result["model_version"])