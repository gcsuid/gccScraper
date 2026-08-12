# Daily Leads

A Python script that selects and manages GCC (Global Capability Centre) leads from your CSV file.

## Features

- **Daily Selection**: Automatically pulls 5 new leads each time you run it
- **Smart Tracking**: Marks leads as "done" so they're never recommended again
- **Auto-Reset**: When all leads are processed, automatically resets for a new cycle
- **JSON Tracking**: Maintains a clean tracking file with processed leads and timestamps

## How It Works

1. **First Run**: Selects the first 5 unprocessed leads from `sanitised_gcc_leads.csv`
2. **Marks as Done**: Automatically adds them to `leads_tracking.json`
3. **Next Run**: Selects 5 different leads (skips previously selected ones)
4. **Auto-Reset**: When all leads are done, resets the tracking and cycles through again

## Usage

### Run Once Daily
```bash
python daily_leads.py
```

### Automate Daily Execution

**Windows (Task Scheduler):**
1. Open Task Scheduler
2. Create Basic Task > Name: "Daily Leads Selector"
3. Trigger: Daily at your preferred time
4. Action: `python C:\path\to\daily_leads.py`

**Linux/Mac (Crontab):**
```bash
# Daily at 9 AM
0 9 * * * cd /path/to/project && python daily_leads.py
```

### PowerShell Script (Optional)
Create `run_daily_leads.ps1`:
```powershell
Set-Location "C:\Users\KIIT\Desktop\personal_project\sweetPython\gccScraper"
python daily_leads.py
```

Run with Task Scheduler as: `powershell -ExecutionPolicy Bypass -File run_daily_leads.ps1`

## Files

- **`daily_leads.py`**: Main script
- **`leads_tracking.json`**: Persistent tracking file (auto-created on first run)
  - Stores company names already processed
  - Tracks last execution timestamp
- **`sanitised_gcc_leads.csv`**: Your source data

## Output Example

```
======================================================================
[DAILY LEADS SELECTION] - 2026-08-12 01:01:42
======================================================================

1. Warner Bros. Discovery
   Location: Hyderabad
   Posted: 2026-05-16T05:18:29.688Z
   Source: ollama_qwen
   URL: https://www.linkedin.com/posts/gcc-marketwatch_...

2. New York-based Pico Technology
   Location: Hyderabad
   Posted: 2026-04-13T05:48:22.697Z
   Source: ollama_qwen
   URL: https://www.linkedin.com/posts/gcc-marketwatch_...

[... 3 more leads ...]

======================================================================
[DONE] Marked 5 leads as processed
Remaining unprocessed leads: 667
======================================================================
```

## Reset/Start Over

If you want to reset and start from the beginning:
1. Delete `leads_tracking.json`
2. Run the script again

## Notes

- The script uses company name as the unique identifier
- No external dependencies required (uses Python standard library)
- Tracking file is human-readable JSON for easy inspection
- Completely safe - no data is modified, only tracked
