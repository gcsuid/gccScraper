
import pandas as pd
import ast
import re
import json
import ollama

# =====================================================
# CONFIG
# =====================================================

INPUT_CSV = "linkedin_posts.csv"
OUTPUT_CSV = "sanitised_gcc_leads.csv"

OLLAMA_MODEL = "qwen2.5:3b"

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

                if company.get("name"):
                    return company["name"]

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
# OLLAMA FALLBACK
# =====================================================

def ollama_extract_names(content):

    prompt = f"""
Extract only HUMAN PERSON NAMES from this LinkedIn post.

Rules:
- Return only people names.
- Ignore companies.
- Ignore locations.
- Ignore hashtags.
- Ignore GCC names.
- Ignore organizations.

Return ONLY JSON.

Example:

{{
  "names": [
    "Rohit Gupta",
    "Sriniketh Chakravarthi"
  ]
}}

Post:

{content}
"""

    try:

        response = ollama.chat(
            model=OLLAMA_MODEL,
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        output = response["message"]["content"]

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
                len(name) > 2
                and name not in cleaned
            ):
                cleaned.append(name)

        return cleaned

    except Exception as e:

        print(f"Ollama extraction failed: {e}")

        return []


# =====================================================
# MAIN PROCESSING
# =====================================================

def process_csv():

    print(f"\nLoading {INPUT_CSV}...")

    df = pd.read_csv(INPUT_CSV)

    total_rows = len(df)

    print(f"Found {total_rows} posts\n")

    output_rows = []

    for index, row in df.iterrows():

        print(f"[{index + 1}/{total_rows}] Processing")

        content = str(row.get("content", ""))

        content_attributes = row.get(
            "contentAttributes",
            ""
        )

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

            print("   No PROFILE_MENTION found")
            print("   Using Ollama...")

            names = ollama_extract_names(content)

            source = "ollama_qwen"

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

    print("\n====================================")
    print("Completed")
    print(f"Rows Processed : {len(output_df)}")
    print(f"Saved To       : {OUTPUT_CSV}")
    print("====================================")


# =====================================================
# ENTRY
# =====================================================

if __name__ == "__main__":

    process_csv()
