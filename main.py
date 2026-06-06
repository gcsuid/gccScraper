from apify_client import ApifyClient
from dotenv import load_dotenv
import pandas as pd
import os
import json

# Load environment variables
load_dotenv()

# Get Apify token
APIFY_TOKEN = os.getenv("APIFY_TOKEN")

if not APIFY_TOKEN:
    raise ValueError("APIFY_TOKEN not found in .env file")

# Initialize client
client = ApifyClient(APIFY_TOKEN)

# Input for LinkedIn scraper actor
run_input = {
    "targetUrls": [
        "https://www.linkedin.com/company/gcc-marketwatch/",
        "https://www.linkedin.com/company/et-gcc/",
    ],
    "maxPosts": 600,
    "includeQuotePosts": True,
    "includeReposts": False,
    "scrapeReactions": False,
    "postNestedReactions": False,
    "scrapeComments": False,
    "postNestedComments": False,
}

print("Starting actor...")

# Run actor
run = client.actor("A3cAPGpwBEG8RJwse").call(
    run_input=run_input
)

print(f"Run finished: {run['id']}")

# Fetch dataset
dataset = client.dataset(run["defaultDatasetId"])

records = []
all_fields = set()

print("Downloading results...")

for item in dataset.iterate_items():
    records.append(item)

    if isinstance(item, dict):
        all_fields.update(item.keys())

if not records:
    print("No records returned.")
    exit()

# Print sample item
print("\n===== SAMPLE RECORD =====")
print(json.dumps(records[0], indent=2, default=str))

# Flatten JSON
df = pd.json_normalize(records)

# Save CSV
csv_file = "linkedin_posts.csv"
df.to_csv(csv_file, index=False, encoding="utf-8-sig")

# Save field list
with open("linkedin_fields.txt", "w", encoding="utf-8") as f:
    for col in sorted(df.columns):
        f.write(col + "\n")

print("\n===== SUMMARY =====")
print(f"Records scraped : {len(df)}")
print(f"Columns found   : {len(df.columns)}")
print(f"CSV saved       : {csv_file}")
print("Fields saved    : linkedin_fields.txt")

print("\nColumns:")
for col in df.columns:
    print(col)