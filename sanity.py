
import pandas as pd
import ast
import re
import json
import os

from dotenv import load_dotenv
from huggingface_hub import InferenceClient

# =====================================================
# CONFIG
# =====================================================

INPUT_CSV = "linkedin_posts.csv"
OUTPUT_CSV = "sanitised_gcc_leads.csv"

load_dotenv()

HF_TOKEN = os.getenv("HF_TOKEN")

if not HF_TOKEN:
    raise ValueError("HF_TOKEN not found in .env")

MODEL = "deepseek-ai/DeepSeek-V4-Pro:novita"

client = InferenceClient(
    api_key=HF_TOKEN
)

INDIAN_GCC_CITIES = [
    "Hyderabad",
    "Bengaluru",
    "Bangalore",
    "Pune",
    "Chennai",
    "Mumbai",
    "Gurugram",
    "Gurgaon",
    "Noida",
    "Kochi",
    "Coimbatore",
    "Ahmedabad",
    "Delhi",
    "Kolkata",
    "Mysuru",
    "Mangalore",
    "Mangaluru"
]


# =====================================================
# COMPANY EXTRACTION
# =====================================================

def extract_company(content_attributes, content):

    try:
        attrs = ast.literal_eval(str(content_attributes))

        for item in attrs:

            if item.get("type") == "COMPANY_NAME":

                company = item.get("company", {})

                name = company.get("name")

                if name:
                    return name

    except Exception:
        pass

    content = str(content)

    patterns = [
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) has ",
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) is ",
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) will ",
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) announced ",
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) launches ",
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) launched "
    ]

    for pattern in patterns:

        match = re.search(pattern, content)

        if match:
            return match.group(1).strip()

    return ""


# =====================================================
# LOCATION EXTRACTION
# =====================================================

def extract_location(content):

    content = str(content)

    for city in INDIAN_GCC_CITIES:

        if re.search(
            rf"\b{re.escape(city)}\b",
            content,
            re.IGNORECASE
        ):
            return city

    return ""


# =====================================================
# PROFILE MENTION EXTRACTION
# =====================================================

def extract_names_from_attributes(content_attributes):

    names = []

    try:

        attrs = ast.literal_eval(str(content_attributes))

        for item in attrs:

            if item.get("type") == "PROFILE_MENTION":

                profile = item.get("profile", {})

                first = profile.get("firstName", "").strip()
                last = profile.get("lastName", "").strip()

                full_name = f"{first} {last}".strip()

                if full_name:
                    names.append(full_name)

    except Exception:
        pass

    return sorted(list(set(names)))


# =====================================================
# HF FALLBACK
# =====================================================

def hf_extract_names(content):

    prompt = f"""
Extract only HUMAN names from the LinkedIn post below.

Rules:
1. Return only people names.
2. Ignore company names.
3. Ignore city names.
4. Ignore hashtags.
5. Ignore GCC names.
6. Ignore organization names.

Return valid JSON only.

Format:

{{
  "names": []
}}

Post:

{content}
"""

    try:

        response = client.chat.completions.create(
            model=MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
            max_tokens=300
        )

        output = response.choices[0].message.content.strip()

        match = re.search(
            r"\{.*\}",
            output,
            re.DOTALL
        )

        if not match:
            return []

        data = json.loads(match.group())

        names = data.get("names", [])

        cleaned = []

        for name in names:

            name = str(name).strip()

            if (
                name
                and len(name) > 2
                and name not in cleaned
            ):
                cleaned.append(name)

        return cleaned

    except Exception as e:

        print(f"HF extraction failed: {e}")

        return []


# =====================================================
# MAIN
# =====================================================

def process_csv():

    df = pd.read_csv(INPUT_CSV)

    output_rows = []

    total = len(df)

    print(f"\nLoaded {total} posts\n")

    for index, row in df.iterrows():

        print(f"[{index + 1}/{total}] Processing...")

        content = str(row.get("content", ""))

        content_attributes = row.get("contentAttributes", "")

        company = extract_company(
            content_attributes,
            content
        )

        location = extract_location(content)

        post_date = row.get(
            "postedAt.date",
            ""
        )

        linkedin_url = row.get(
            "linkedinUrl",
            ""
        )

        names = extract_names_from_attributes(
            content_attributes
        )

        source = "linkedin_metadata"

        if not names:

            print("   No PROFILE_MENTION found -> Using HF")

            names = hf_extract_names(content)

            source = "hf_extracted"

        output_rows.append(
            {
                "company": company,
                "location": location,
                "post_date": post_date,
                "person_names": "; ".join(names),
                "source": source,
                "linkedin_url": linkedin_url,
                "content": content
            }
        )

    output_df = pd.DataFrame(output_rows)

    output_df.to_csv(
        OUTPUT_CSV,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n================================")
    print("Completed")
    print(f"Rows saved : {len(output_df)}")
    print(f"Output     : {OUTPUT_CSV}")
    print("================================")


# =====================================================
# ENTRY
# =====================================================

if __name__ == "__main__":
    process_csv()
