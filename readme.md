# GCC Hunt

The goal of this application is to identify which **Global Capability Centers (GCCs)** have opened in **India after COVID**, and among those, which ones can be targeted for career opportunities.

## Approach

- Scraping LinkedIn directly is difficult, so I used an **Apify scraper** to extract data from trusted LinkedIn GCC watchdogs.
- After scraping, I used another script to **sanitize the output** into a cleaner CSV format.
- The final CSV contains:
  - Company name
  - Name of the person who runs the company
  - also any insights you can gain about the company.

## Current Run Flow

Run `python main.py`.

The pipeline now:

- Scrapes the latest LinkedIn posts from the configured watch pages
- Reads `state.json` to find the last processed post timestamp
- Filters out anything older than that watermark
- De-duplicates against existing stored rows using source-level identifiers such as `id` and `linkedinUrl`
- Sanitizes only the truly new rows
- Updates `state.json` only after the CSV writes succeed

## Automation Recommendation

Use **Windows Task Scheduler** first, not GitHub-hosted Actions.

Reason:

- Your sanitization step depends on local `ollama`
- `state.json` is local runtime state, which fits machine scheduling cleanly
- A GitHub-hosted runner would need either a remote LLM/API replacement or a self-hosted runner with Ollama installed

If you later replace local Ollama with an API call, then moving to GitHub Actions becomes reasonable.
