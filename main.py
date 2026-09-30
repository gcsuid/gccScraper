import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

from sanity import find_company_replacements, sanitize_dataframe

RAW_CSV = Path("linkedin_posts.csv")
SANITIZED_CSV = Path("sanitised_gcc_leads.csv")
STATE_FILE = Path("state.json")


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_utc_timestamp(value):
    if not value or pd.isna(value):
        return None

    text = str(value).strip()
    if not text:
        return None

    if text.endswith("Z"):
        text = text[:-1] + "+00:00"

    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc)
    except ValueError:
        return None


def load_state():
    if not STATE_FILE.exists():
        return {
            "last_successful_run_at": None,
            "last_processed_post_date": None,
            "last_checked_at": None,
        }

    with STATE_FILE.open("r", encoding="utf-8") as handle:
        state = json.load(handle)

    return {
        "last_successful_run_at": state.get("last_successful_run_at"),
        "last_processed_post_date": state.get("last_processed_post_date"),
        "last_checked_at": state.get("last_checked_at"),
    }


def save_state(state):
    with STATE_FILE.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def load_existing_dataframe(path):
    if not path.exists():
        return pd.DataFrame()

    return pd.read_csv(path)


def pick_smoke_candidate(df):
    if df.empty:
        return df

    preferred = df.copy()

    if "contentAttributes" in preferred.columns:
        content_attributes = preferred["contentAttributes"].fillna("").astype(str)
        preferred = preferred[
            content_attributes.str.contains("PROFILE_MENTION", regex=False)
            | content_attributes.str.contains("COMPANY_NAME", regex=False)
        ]

    if preferred.empty:
        preferred = df

    return preferred.head(1).copy()


def validate_smoke_output(smoke_row):
    required_fields = ["company", "location", "linkedin_url"]
    missing_fields = [field for field in required_fields if not str(smoke_row.get(field, "")).strip()]

    if missing_fields:
        raise ValueError(
            f"Smoke test failed. Missing extracted fields: {', '.join(missing_fields)}"
        )


def run_smoke_test():
    raw_df = load_existing_dataframe(RAW_CSV)
    if raw_df.empty:
        raise ValueError(f"Smoke test requires cached raw data in {RAW_CSV}.")

    smoke_input_df = pick_smoke_candidate(raw_df)
    smoke_output_df = sanitize_dataframe(smoke_input_df)

    if smoke_output_df.empty:
        raise ValueError("Smoke test failed. Sanitizer returned no rows.")

    smoke_row = smoke_output_df.iloc[0].to_dict()
    validate_smoke_output(smoke_row)

    print("\n====================================")
    print("Smoke test passed")
    print(f"Company      : {smoke_row['company']}")
    print(f"Location     : {smoke_row['location']}")
    print(f"Person Names : {smoke_row.get('person_names', '')}")
    print(f"Source       : {smoke_row.get('source', '')}")
    print(f"LinkedIn URL : {smoke_row['linkedin_url']}")
    print("====================================")


def fetch_posts(client, initial_import=False):
    target_urls = [
        url.strip()
        for url in os.getenv("LINKEDIN_TARGET_URLS", "").replace(";", ",").replace("\n", ",").split(",")
        if url.strip()
    ]
    if not target_urls:
        raise ValueError(
            "LINKEDIN_TARGET_URLS not found. Add comma- or newline-separated LinkedIn URLs to .env."
        )

    run_input = {
        "targetUrls": target_urls,
        "maxPosts": int(
            os.getenv(
                "APIFY_INITIAL_MAX_POSTS" if initial_import else "APIFY_MAX_POSTS",
                "100" if initial_import else "20",
            )
        ),
        "includeQuotePosts": True,
        "includeReposts": False,
        "scrapeReactions": False,
        "postNestedReactions": False,
        "scrapeComments": False,
        "postNestedComments": False,
    }

    print("Starting actor...")
    actor_id = os.getenv("APIFY_ACTOR_ID", "harvestapi/linkedin-profile-posts")
    run = client.actor(actor_id).call(run_input=run_input)
    run_id = getattr(run, "id", None) or run["id"]
    dataset_id = getattr(run, "default_dataset_id", None) or run["defaultDatasetId"]
    print(f"Run finished: {run_id}")

    dataset = client.dataset(dataset_id)
    records = list(dataset.iterate_items())

    if not records:
        return pd.DataFrame()

    return pd.json_normalize(records)


def filter_incremental_posts(df, last_processed_post_date):
    if df.empty:
        return df

    filtered_df = df.copy()
    filtered_df["_post_dt"] = filtered_df.get("postedAt.date", pd.Series(dtype="object")).apply(
        parse_utc_timestamp
    )

    watermark = parse_utc_timestamp(last_processed_post_date)
    if watermark is not None:
        filtered_df = filtered_df[
            filtered_df["_post_dt"].notna() & (filtered_df["_post_dt"] > watermark)
        ]

    return filtered_df.drop(columns=["_post_dt"], errors="ignore")


def dedupe_raw_posts(incoming_df, existing_df):
    combined = pd.concat([existing_df, incoming_df], ignore_index=True, sort=False)

    if "id" in combined.columns:
        combined["id"] = combined["id"].astype(str).str.strip()
        combined = combined[combined["id"] != ""]
        combined = combined.drop_duplicates(subset=["id"], keep="first")
    elif "linkedinUrl" in combined.columns:
        combined["linkedinUrl"] = combined["linkedinUrl"].astype(str).str.strip()
        combined = combined.drop_duplicates(subset=["linkedinUrl"], keep="first")
    else:
        combined = combined.drop_duplicates(keep="first")

    return combined


def dedupe_sanitized_posts(incoming_df, existing_df):
    combined = pd.concat([existing_df, incoming_df], ignore_index=True, sort=False)

    for key in ["post_id", "linkedin_url"]:
        if key in combined.columns:
            combined[key] = combined[key].astype(str).str.strip()

    if "post_id" in combined.columns:
        valid_ids = combined["post_id"] != ""
        deduped_ids = combined[valid_ids].drop_duplicates(subset=["post_id"], keep="last")
        no_ids = combined[~valid_ids]
        combined = pd.concat([deduped_ids, no_ids], ignore_index=True, sort=False)

    if "linkedin_url" in combined.columns:
        combined = combined.drop_duplicates(subset=["linkedin_url"], keep="last")
    else:
        combined = combined.drop_duplicates(keep="first")

    return combined


def merge_company_records(df):
    """Return one row per company while combining all unique people and posts."""
    if df.empty or "company" not in df.columns:
        return df

    from sanity import normalize_company_name

    working = df.copy()
    working["_company_key"] = working["company"].fillna("").map(normalize_company_name)
    working["_post_dt"] = working.get("post_date", pd.Series(dtype="object")).apply(
        parse_utc_timestamp
    )

    merged_rows = []
    for company_key, group in working.groupby("_company_key", sort=False, dropna=False):
        if not company_key:
            merged_rows.extend(group.drop(columns=["_company_key", "_post_dt"]).to_dict("records"))
            continue

        group = group.sort_values("_post_dt", ascending=False, na_position="last")
        row = group.iloc[0].drop(labels=["_company_key", "_post_dt"]).to_dict()

        people = []
        for value in group.get("person_names", pd.Series(dtype="object")).fillna(""):
            for person in str(value).split(";"):
                person = " ".join(person.split()).strip()
                if person and person.casefold() not in {item.casefold() for item in people}:
                    people.append(person)
        row["person_names"] = "; ".join(people)

        for field in ["company", "location", "post_date", "source", "linkedin_url", "content"]:
            if not str(row.get(field, "") or "").strip():
                for value in group[field].fillna("") if field in group else []:
                    if str(value).strip():
                        row[field] = value
                        break

        merged_rows.append(row)

    return pd.DataFrame(merged_rows, columns=df.columns.drop(["_company_key", "_post_dt"], errors="ignore"))


def replace_existing_company_records(incoming_df, existing_df):
    """Keep the newest incoming lead when Ollama Cloud confirms the company already exists."""
    replacements = find_company_replacements(incoming_df, existing_df)
    if not replacements:
        return existing_df, 0

    from sanity import normalize_company_name

    # Remove the actual confirmed candidate, rather than every company similar to it.
    normalized_replacements = {
        normalize_company_name(existing_company)
        for _, existing_company in replacements
    }
    retained_existing = existing_df[
        ~existing_df["company"].fillna("").map(normalize_company_name).isin(normalized_replacements)
    ].copy()
    return retained_existing, len(existing_df) - len(retained_existing)


def determine_next_watermark(state, new_posts_df):
    candidate_dates = [state.get("last_processed_post_date")]

    if not new_posts_df.empty and "postedAt.date" in new_posts_df.columns:
        candidate_dates.extend(
            [
                value
                for value in new_posts_df["postedAt.date"].tolist()
                if parse_utc_timestamp(value) is not None
            ]
        )

    parsed_dates = [parse_utc_timestamp(value) for value in candidate_dates]
    parsed_dates = [value for value in parsed_dates if value is not None]

    if not parsed_dates:
        return None

    return max(parsed_dates).isoformat().replace("+00:00", "Z")


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a fast local smoke test against cached raw data.",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.smoke:
        run_smoke_test()
        return

    load_dotenv()
    apify_token = os.getenv("APIFY_TOKEN")
    ollama_api_key = os.getenv("OLLAMA_API_KEY")

    if not apify_token:
        raise ValueError("APIFY_TOKEN not found in .env file")
    if not ollama_api_key:
        raise ValueError(
            "OLLAMA_API_KEY not found in .env file. This pipeline uses Ollama Cloud directly."
        )

    state = load_state()

    print("Current state")
    print(json.dumps(state, indent=2))

    client = ApifyClient(apify_token)
    fetched_df = fetch_posts(client, initial_import=not state.get("last_processed_post_date"))

    if fetched_df.empty:
        print("No records returned by the scraper.")
        state["last_checked_at"] = utc_now_iso()
        state["last_successful_run_at"] = utc_now_iso()
        save_state(state)
        return

    incremental_df = filter_incremental_posts(
        fetched_df,
        state.get("last_processed_post_date"),
    )

    print(f"Fetched rows      : {len(fetched_df)}")
    print(f"Incremental rows  : {len(incremental_df)}")

    if incremental_df.empty:
        print("No new posts after watermark filtering.")
        state["last_checked_at"] = utc_now_iso()
        state["last_successful_run_at"] = utc_now_iso()
        save_state(state)
        return

    existing_raw_df = load_existing_dataframe(RAW_CSV)
    updated_raw_df = dedupe_raw_posts(incremental_df, existing_raw_df)

    existing_count = len(existing_raw_df)
    updated_count = len(updated_raw_df)
    new_unique_count = updated_count - existing_count

    if new_unique_count <= 0:
        print("All incremental rows were already present in the raw dataset.")
        state["last_checked_at"] = utc_now_iso()
        state["last_successful_run_at"] = utc_now_iso()
        save_state(state)
        return

    if "id" in existing_raw_df.columns:
        existing_ids = set(existing_raw_df["id"].astype(str))
        truly_new_df = incremental_df[~incremental_df["id"].astype(str).isin(existing_ids)].copy()
    elif "linkedinUrl" in existing_raw_df.columns:
        existing_urls = set(existing_raw_df["linkedinUrl"].astype(str))
        truly_new_df = incremental_df[
            ~incremental_df["linkedinUrl"].astype(str).isin(existing_urls)
        ].copy()
    else:
        truly_new_df = incremental_df.copy()

    sanitized_new_df = sanitize_dataframe(truly_new_df)
    existing_sanitized_df = load_existing_dataframe(SANITIZED_CSV)
    retained_sanitized_df, replaced_company_count = replace_existing_company_records(
        sanitized_new_df, existing_sanitized_df
    )
    updated_sanitized_df = dedupe_sanitized_posts(sanitized_new_df, retained_sanitized_df)
    updated_sanitized_df = merge_company_records(updated_sanitized_df)

    updated_raw_df.to_csv(RAW_CSV, index=False, encoding="utf-8-sig")
    updated_sanitized_df.to_csv(SANITIZED_CSV, index=False, encoding="utf-8-sig")

    state["last_checked_at"] = utc_now_iso()
    state["last_successful_run_at"] = utc_now_iso()
    state["last_processed_post_date"] = determine_next_watermark(state, truly_new_df)
    save_state(state)

    print("\n====================================")
    print("Completed")
    print(f"New unique raw rows : {len(truly_new_df)}")
    print(f"Raw rows total      : {len(updated_raw_df)}")
    print(f"Sanitized rows total: {len(updated_sanitized_df)}")
    print(f"Company rows replaced: {replaced_company_count}")
    print(f"Watermark saved     : {state['last_processed_post_date']}")
    print("====================================")


if __name__ == "__main__":
    main()
