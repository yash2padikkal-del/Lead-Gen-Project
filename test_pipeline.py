from enrichment.pipeline import LeadGenerationPipeline


# No external providers connected yet.
pipeline = LeadGenerationPipeline()


lead = {
    "brand_name": "Example Streetwear",
    "website": "https://example.com",
    "instagram_handle": "@example",
    "is_apparel_brand": True
}


result = pipeline.process_lead(lead)


print("\nPIPELINE RESULT")
print("--------------------------")

print("Brand:", result["brand_name"])
print("Status:", result["status"])

print("Priority:", result["priority_score"])

print("Features:", result["features"])

print("Errors:", result["errors"])