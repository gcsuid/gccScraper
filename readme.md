# GCC Hunt

The goal of this application is to identify which **Global Capability Centers (GCCs)** have opened in **India after COVID**, and among those, which ones can be targeted for career opportunities.

## Approach

- Scraping LinkedIn directly is difficult, so I used an **Apify scraper** to extract data from trusted LinkedIn GCC watchdogs.
- After scraping, I used another script to **sanitize the output** into a cleaner CSV format.
- The final CSV contains:
  - Company name
  - Name of the person who runs the company
  - also any insights you can gain about the company.

The pipeline updates the existing CSV files only. The sanitized lead file uses
the normalized company name as its only lead uniqueness key: it keeps one row
per company, appends only new companies, and combines unique person names from
later posts into the existing company's `person_names` cell. Post IDs and URLs
are used only to avoid reprocessing the same raw source post.

## Current Run Flow

Run `python main.py`.

This is the data-only command. It does not send email. Do not run
`daily_leads.py` unless you later want the separate daily selection/email
feature.

The pipeline now:

- Scrapes the latest LinkedIn posts from the configured watch pages
- Reads `state.json` to find the last processed post timestamp
- Filters out anything older than that watermark
- De-duplicates against existing stored rows using source-level identifiers such as `id` and `linkedinUrl`
- Sanitizes only the truly new rows
- Updates `state.json` only after the CSV writes succeed
- Reads `LINKEDIN_TARGET_URLS` and `APIFY_MAX_POSTS` from `.env`
- Uses `APIFY_INITIAL_MAX_POSTS` for the first import, then `APIFY_MAX_POSTS` daily
- Updates `linkedin_posts.csv` and `sanitised_gcc_leads.csv`
- Does not require SMTP or email settings

## Ollama Cloud setup

This project uses Ollama's hosted API directly; it does **not** start or call a local Ollama model.

1. Create an API key in your Ollama account and add it to `.env`:

   ```env
   APIFY_TOKEN=...
   OLLAMA_API_KEY=...
   # Free-plan starter candidate; keep this configurable
   OLLAMA_CLOUD_MODEL=gemma4:31b
   ```

2. Run `python main.py` (or `./run_pipeline.ps1`).

For each batch of new posts, metadata is extracted first. Where names are absent, Ollama Cloud extracts them. Before writing, the pipeline sends only plausible company-name matches to Ollama Cloud for verification. A verified incoming company removes the older company row, then the newer record is written. Exact normalized names remain a safe fallback if the cloud request fails.

Ollama Free includes limited monthly usage for a smaller set of starter
models; it is not unlimited cloud inference. `gemma4:31b` is configured as the
default smaller starter candidate, but the available models and quota are
controlled by Ollama. Check the Ollama usage page if a run is rejected.

## GitHub Actions automation

`.github/workflows/daily-scraper.yml` runs the data-only scraper daily at
20:00 IST (14:30 UTC) and can also be started manually. It commits updated
`linkedin_posts.csv`, `sanitised_gcc_leads.csv`, and `state.json` back to the
repository so the watermark persists between temporary GitHub runners.
heheh