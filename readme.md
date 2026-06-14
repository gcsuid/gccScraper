# GCC Hunt

The goal of this application is to identify which **Global Capability Centers (GCCs)** have opened in **India after COVID**, and among those, which ones can be targeted for career opportunities.

## Approach

- Scraping LinkedIn directly is difficult, so I used an **Apify scraper** to extract data from trusted LinkedIn GCC watchdogs.
- After scraping, I used another script to **sanitize the output** into a cleaner CSV format.
- The final CSV contains:
  - Company name
  - Name of the person who runs the company