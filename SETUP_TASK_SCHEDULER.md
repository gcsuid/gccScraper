# Daily Leads Selector with Email - Setup Guide (Option 1)

## Quick Overview

This script:
1. ✓ Selects 5 new leads daily
2. ✓ Marks them in Excel with "YES" in 'sent' column (saves as `sanitised_gcc_leads_marked.csv`)
3. ✓ Sends an email with the leads every day at 8 PM
4. ✓ Never recommends the same lead twice

---

## Step 1: Gmail App Password Setup (5 min)

You need a Gmail **App Password** (not your regular password) for security.

### Steps:

1. Go to: https://myaccount.google.com/apppasswords
2. Sign in with your Gmail account
3. You might need to enable 2-Step Verification first (if not done)
   - Go to: https://myaccount.google.com/security
   - Turn on "2-Step Verification"
4. Go back to App Passwords
5. Select: **Mail** and **Windows Computer**
6. Click **Generate**
7. Copy the 16-character password (it shows in a popup)

### Example output:
```
abcd efgh ijkl mnop
```

---

## Step 2: Create `.env` File (2 min)

1. Open Notepad
2. Copy this and **fill in your details**:

```
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
EMAIL_ADDRESS=your.email@gmail.com
EMAIL_PASSWORD=abcdefghijklmnop
RECIPIENT_EMAIL=your.email@gmail.com
```

**Important:**
- `EMAIL_ADDRESS` = Your Gmail address
- `EMAIL_PASSWORD` = The 16-char App Password from Step 1 (remove spaces)
- `RECIPIENT_EMAIL` = Where the email should be sent (can be same as EMAIL_ADDRESS)

3. Save the file as: `.env` (exact name, no .txt)
4. Place it in: `C:\Users\KIIT\Desktop\personal_project\sweetPython\gccScraper\`

---

## Step 3: Test the Script (2 min)

Run this in PowerShell:

```powershell
cd "C:\Users\KIIT\Desktop\personal_project\sweetPython\gccScraper"
python daily_leads.py
```

### You should see:
```
[DAILY LEADS SELECTION] - 2026-08-12 01:07:43
======================================================================

1. T-Mobile
   Location: Hyderabad
   ...

[EMAIL] Successfully sent to your.email@gmail.com
```

**If email fails:**
- Check `.env` file is in the right folder
- Check EMAIL_ADDRESS and EMAIL_PASSWORD are correct
- Check credentials don't have spaces
- Make sure 2FA is enabled on Gmail

---

## Step 4: Set Up Windows Task Scheduler (5 min)

### Open Task Scheduler:
1. Press `Win + R`
2. Type: `taskschd.msc`
3. Press Enter

### Create Task:
1. Click **"Create Task..."** (right panel)
2. **General Tab:**
   - Name: `Daily GCC Leads Email`
   - Description: `Send 5 GCC leads via email daily at 8 PM`
   - Check: ✓ "Run with highest privileges"

3. **Triggers Tab:**
   - Click **"New..."**
   - Begin the task: **On a schedule**
   - Daily
   - Start: `2026-08-12` (today)
   - Recur every: `1` day
   - Time: `20:00:00` (8 PM)
   - ✓ Enabled
   - Click OK

4. **Actions Tab:**
   - Click **"New..."**
   - Action: **Start a program**
   - Program/script: `C:\Users\KIIT\AppData\Roaming\uv\python\cpython-3.11-windows-x86_64-none\python.exe`
   - Arguments: `daily_leads.py`
   - Start in: `C:\Users\KIIT\Desktop\personal_project\sweetPython\gccScraper`
   - Click OK

5. **Conditions Tab:**
   - Uncheck: "Wake the computer to run this task" (optional)

6. Click **OK** to save

### Verify Task:
- Go to **Task Scheduler Library**
- Find **"Daily GCC Leads Email"**
- Double-click it, go to **Triggers** tab
- Should show: "At 8:00 PM daily"

---

## Step 5: Optional - Run on Demand (Manual Test)

To test without waiting for 8 PM:
1. Open Task Scheduler
2. Find **"Daily GCC Leads Email"**
3. Right-click → **"Run"**
4. Check your email in 10 seconds

---

## What You'll Receive in Email

```
Subject: GCC Daily Leads - 2026-08-12

Here are your 5 leads for today:

| # | Company | Location | Posted | Source | LinkedIn URL |
|---|---------|----------|--------|--------|--------------|
| 1 | T-Mobile | Hyderabad | 2026-06-04 | ollama_qwen | View Post |
| 2 | ANSR | Hyderabad | 2026-06-03 | ollama_qwen | View Post |
| ... (3 more) |
```

---

## Files Created

- **`daily_leads.py`** - Main script (run this)
- **`.env`** - Your credentials (created by you)
- **`leads_tracking.json`** - Tracks which leads were sent (auto-created)
- **`sanitised_gcc_leads_marked.csv`** - CSV with "YES" in 'sent' column for delivered leads

---

## Troubleshooting

### Email not sending?
1. Check `.env` file exists in the correct folder
2. Check EMAIL_ADDRESS is your Gmail
3. Check EMAIL_PASSWORD is the 16-char app password (no spaces)
4. Check 2FA is enabled on Gmail
5. Check RECIPIENT_EMAIL is correct

### Task not running at 8 PM?
1. Make sure your computer is on at 8 PM
2. Check Task Scheduler → Event Viewer to see error logs
3. Right-click task → Run to test manually

### Email going to spam?
1. Check spam folder
2. Whitelist sender address in your Gmail settings
3. Use your own Gmail as sender (EMAIL_ADDRESS = your Gmail)

---

## Reset/Start Over

To restart from the beginning:
1. Delete `leads_tracking.json`
2. The script will pull from the beginning again

---

## FAQ

**Q: Can I change the time to not 8 PM?**
A: Yes! In Task Scheduler → Edit Trigger, change the time.

**Q: Can I use Outlook instead of Gmail?**
A: Yes! Change SMTP settings:
```
SMTP_SERVER=smtp-mail.outlook.com
SMTP_PORT=587
EMAIL_ADDRESS=your.email@outlook.com
EMAIL_PASSWORD=your_app_password
```

**Q: What if I miss the email?**
A: Emails are logged in `leads_tracking.json`. You can always run manually.

**Q: Will I get duplicate leads?**
A: No! The script never recommends the same company twice until all are done.

**Q: Can I get more than 5 leads?**
A: Yes! Edit the script, line: `get_daily_leads(count=10)` for 10 leads.

---

**Questions? Check the script comments or the main README!**
