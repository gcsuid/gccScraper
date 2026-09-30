import ast
import difflib
import json
import os
import re

import pandas as pd
from ollama import Client

INPUT_CSV = "linkedin_posts.csv"
OUTPUT_CSV = "sanitised_gcc_leads.csv"
OLLAMA_CLOUD_HOST = "https://ollama.com"
OLLAMA_CLOUD_MODEL = os.getenv("OLLAMA_CLOUD_MODEL", "gemma4:31b")

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
    "Mangaluru",
]


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
        r"^([A-Z][A-Za-z0-9&.,'\-\s]+?) launched ",
    ]

    for pattern in patterns:
        match = re.search(pattern, content)
        if match:
            return match.group(1).strip()

    return ""


def extract_location(content):
    content = str(content)

    for city in INDIAN_GCC_CITIES:
        if re.search(rf"\b{re.escape(city)}\b", content, re.IGNORECASE):
            return city

    return ""


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

    return sorted(set(names))


def get_ollama_cloud_client():
    """Return a client for Ollama's hosted API, never the local Ollama server."""
    api_key = os.getenv("OLLAMA_API_KEY")
    if not api_key:
        raise ValueError(
            "OLLAMA_API_KEY not found. Create an Ollama API key and add it to .env. "
            "This project is configured to use Ollama Cloud only."
        )

    return Client(
        host=OLLAMA_CLOUD_HOST,
        headers={"Authorization": f"Bearer {api_key}"},
    )


def cloud_chat(messages):
    return get_ollama_cloud_client().chat(
        model=OLLAMA_CLOUD_MODEL,
        messages=messages,
        stream=False,
        options={"temperature": 0},
    )["message"]["content"]


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
        output = cloud_chat([{"role": "user", "content": prompt}])
        match = re.search(r"\{.*\}", output, re.DOTALL)
        if not match:
            return []

        data = json.loads(match.group())
        names = data.get("names", [])
        cleaned = []

        for name in names:
            name = str(name).strip()
            if len(name) > 2 and name not in cleaned:
                cleaned.append(name)

        return cleaned
    except Exception as error:
        print(f"Ollama extraction failed: {error}")
        return []


def sanitize_dataframe(df):
    total_rows = len(df)
    print(f"Found {total_rows} posts to sanitize\n")

    output_rows = []

    for index, row in df.iterrows():
        print(f"[{index + 1}/{total_rows}] Processing")

        content = str(row.get("content", ""))
        content_attributes = row.get("contentAttributes", "")
        company = extract_company(content_attributes, content)
        location = extract_location(content)
        post_date = row.get("postedAt.date", "")
        linkedin_url = row.get("linkedinUrl", "")
        post_id = row.get("id", "")
        names = extract_names_from_attributes(content_attributes)
        source = "linkedin_metadata"

        if not names:
            print("   No PROFILE_MENTION found")
            print(f"   Using Ollama Cloud ({OLLAMA_CLOUD_MODEL})...")
            names = ollama_extract_names(content)
            source = f"ollama_cloud:{OLLAMA_CLOUD_MODEL}"

        output_rows.append(
            {
                "post_id": post_id,
                "company": company,
                "location": location,
                "post_date": post_date,
                "person_names": "; ".join(names),
                "source": source,
                "linkedin_url": linkedin_url,
                "content": content,
            }
        )

    return pd.DataFrame(output_rows)


def normalize_company_name(value):
    """Create a conservative comparison key without changing the stored company name."""
    text = str(value or "").casefold().strip()
    text = re.sub(r"\b(incorporated|inc|corp|corporation|limited|ltd|llc|plc|pvt|private)\b", "", text)
    return re.sub(r"[^a-z0-9]", "", text)


def _company_match_candidates(company, existing_companies, limit=5):
    normalized = normalize_company_name(company)
    if not normalized:
        return []

    exact = [name for name in existing_companies if normalize_company_name(name) == normalized]
    if exact:
        return exact[:limit]

    choices = {
        normalize_company_name(name): name
        for name in existing_companies
        if normalize_company_name(name)
    }
    similar_keys = difflib.get_close_matches(normalized, choices.keys(), n=limit, cutoff=0.72)
    return [choices[key] for key in similar_keys]


def find_company_replacements(incoming_df, existing_df):
    """Use one Cloud request to confirm only plausible company-name matches.

    Local normalization narrows the candidate list first, which keeps cloud cost and
    prompt size bounded. Exact normalized matches are retained as a safe fallback if
    the network/model response is unavailable.
    """
    if incoming_df.empty or existing_df.empty or "company" not in incoming_df or "company" not in existing_df:
        return set()

    existing_companies = existing_df["company"].fillna("").astype(str).tolist()
    checks = []
    exact_matches = set()
    for incoming_index, company in incoming_df["company"].fillna("").astype(str).items():
        candidates = _company_match_candidates(company, existing_companies)
        if not candidates:
            continue
        if any(normalize_company_name(company) == normalize_company_name(candidate) for candidate in candidates):
            exact_matches.add(incoming_index)
        checks.append({"incoming_index": incoming_index, "incoming_company": company, "candidates": candidates})

    if not checks:
        return set()

    prompt = """You verify company-name duplicates in GCC lead data. For each item, decide whether the
incoming company is the SAME company as one of its candidates. Treat legal-suffix and punctuation
differences as the same. Do not treat partners, customers, subsidiaries, or similarly named companies
as the same. Return ONLY JSON in this form:
{\"matches\": [{\"incoming_index\": 0, \"existing_company\": \"Example Inc\"}]}.
Every existing_company must be copied exactly from that item's candidates.\n\nChecks:\n"""

    try:
        output = cloud_chat([{"role": "user", "content": prompt + json.dumps(checks)}])
        match = re.search(r"\{.*\}", output, re.DOTALL)
        if not match:
            raise ValueError("Cloud response did not contain JSON")
        verified = json.loads(match.group()).get("matches", [])
        allowed_candidates = {
            (item["incoming_index"], candidate)
            for item in checks
            for candidate in item["candidates"]
        }
        return {
            (int(item["incoming_index"]), str(item["existing_company"]))
            for item in verified
            if (int(item["incoming_index"]), str(item["existing_company"])) in allowed_candidates
        }
    except Exception as error:
        print(f"Ollama Cloud company verification failed: {error}. Using exact-name matches only.")
        return {
            (index, candidate)
            for index, company in incoming_df["company"].fillna("").astype(str).items()
            for candidate in existing_companies
            if index in exact_matches
            and normalize_company_name(company) == normalize_company_name(candidate)
        }


def process_csv(input_csv=INPUT_CSV, output_csv=OUTPUT_CSV):
    print(f"\nLoading {input_csv}...")
    df = pd.read_csv(input_csv)
    output_df = sanitize_dataframe(df)
    output_df.to_csv(output_csv, index=False, encoding="utf-8-sig")

    print("\n====================================")
    print("Completed")
    print(f"Rows Processed : {len(output_df)}")
    print(f"Saved To       : {output_csv}")
    print("====================================")


if __name__ == "__main__":
    process_csv()
