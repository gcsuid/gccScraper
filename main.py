import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from apify_client import ApifyClient
from dotenv import load_dotenv

from sanity import sanitize_dataframe

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


def fetch_posts(client):
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
    run = client.actor("A3cAPGpwBEG8RJwse").call(run_input=run_input)
    print(f"Run finished: {run['id']}")

    dataset = client.dataset(run["defaultDatasetId"])
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
        deduped_ids = combined[valid_ids].drop_duplicates(subset=["post_id"], keep="first")
        no_ids = combined[~valid_ids]
        combined = pd.concat([deduped_ids, no_ids], ignore_index=True, sort=False)

    if "linkedin_url" in combined.columns:
        combined = combined.drop_duplicates(subset=["linkedin_url"], keep="first")
    else:
        combined = combined.drop_duplicates(keep="first")

    return combined


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


def main():
    load_dotenv()
    apify_token = os.getenv("APIFY_TOKEN")

    if not apify_token:
        raise ValueError("APIFY_TOKEN not found in .env file")

    state = load_state()

    print("Current state")
    print(json.dumps(state, indent=2))

    client = ApifyClient(apify_token)
    fetched_df = fetch_posts(client)

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
    updated_sanitized_df = dedupe_sanitized_posts(sanitized_new_df, existing_sanitized_df)

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
    print(f"Watermark saved     : {state['last_processed_post_date']}")
    print("====================================")


if __name__ == "__main__":
    main()
