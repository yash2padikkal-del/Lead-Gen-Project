from enrichment.pipeline import LeadGenerationPipeline
from enrichment.providers.meta_ads import MetaAdsProvider

pipeline = LeadGenerationPipeline(
    advertising_provider=MetaAdsProvider()
)

lead = {
    "brand_name": "YOUR TEST BRAND",
    "website": "https://example.com",
    "instagram_handle": "@yourtestbrand",
    "is_apparel_brand": True
}

result = pipeline.process_lead(lead)

print("\nPIPELINE RESULT")
print("--------------------------")
print("Status:", result["status"])
print("Priority:", result["priority_score"])
print("Advertising:", result["enrichment"].get("advertising"))
print("Errors:", result["errors"])