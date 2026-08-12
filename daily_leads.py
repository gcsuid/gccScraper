import csv
import json
import smtplib
from datetime import datetime
from pathlib import Path
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_file = Path(".env")
    if env_file.exists():
        with open(env_file, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    os.environ[key.strip()] = value.strip()

CSV_FILE = "sanitised_gcc_leads.csv"
TRACKING_FILE = "leads_tracking.json"
MARKED_CSV_FILE = "sanitised_gcc_leads_marked.csv"

SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
EMAIL_ADDRESS = os.getenv("EMAIL_ADDRESS")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
RECIPIENT_EMAIL = os.getenv("RECIPIENT_EMAIL")


def load_csv():
    leads = []
    try:
        with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                leads.append(row)
    except Exception as e:
        print(f"Error reading CSV: {e}")
    return leads


def is_priority_lead(lead):
    text = " ".join(
        [
            lead.get("company", "") or "",
            lead.get("location", "") or "",
            lead.get("content", "") or "",
        ]
    ).lower()

    gcc_keywords = [
        "gcc",
        "global capability centre",
        "global capability center",
        "global technology centre",
        "global technology center",
        "technology hub",
    ]
    india_keywords = [
        "india",
        "hyderabad",
        "bengaluru",
        "bangalore",
        "pune",
        "chennai",
        "gurugram",
        "gurgaon",
        "noida",
        "mumbai",
        "delhi",
        "mangaluru",
        "coimbatore",
        "ahmedabad",
        "kolkata",
    ]
    action_keywords = [
        "set up",
        "setup",
        "launch",
        "launched",
        "opening",
        "opened",
        "inaugurat",
        "establish",
        "new gcc",
        "new global capability centre",
        "new global capability center",
        "expand",
        "expanded",
        "expanding",
        "expansion",
        "scale",
        "scaled",
        "scaling",
        "double",
        "doubling",
        "grow",
        "growing",
    ]

    return (
        any(keyword in text for keyword in gcc_keywords)
        and any(keyword in text for keyword in india_keywords)
        and any(keyword in text for keyword in action_keywords)
    )


def load_tracking():
    if Path(TRACKING_FILE).exists():
        with open(TRACKING_FILE, "r") as f:
            return json.load(f)
    return {"processed": [], "last_run": None}


def save_tracking(tracking):
    with open(TRACKING_FILE, "w") as f:
        json.dump(tracking, f, indent=2)


def mark_in_csv(company_names):
    all_leads = load_csv()
    fieldnames = all_leads[0].keys() if all_leads else []
    if "sent" not in fieldnames:
        fieldnames = list(fieldnames) + ["sent"]

    for lead in all_leads:
        lead["sent"] = "YES" if lead["company"] in company_names else lead.get("sent", "")

    with open(MARKED_CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_leads)


def send_email(selected_leads):
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD or not RECIPIENT_EMAIL:
        print("[WARNING] Email credentials not configured. Skipping email.")
        print("         Set EMAIL_ADDRESS, EMAIL_PASSWORD, RECIPIENT_EMAIL in .env")
        return False

    try:
        html_content = f"""
        <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>GCC Daily Leads - {datetime.now().strftime('%Y-%m-%d')}</h2>
                <p>Here are your 5 leads for today:</p>
                <table border="1" cellpadding="10" style="border-collapse: collapse;">
                    <tr style="background-color: #f2f2f2;">
                        <th>#</th>
                        <th>Company</th>
                        <th>Person Name(s)</th>
                        <th>Location</th>
                    </tr>
        """

        for idx, lead in enumerate(selected_leads, 1):
            person_names = lead.get("person_names", "") or "N/A"
            html_content += f"""
                    <tr>
                        <td>{idx}</td>
                        <td><strong>{lead['company']}</strong></td>
                        <td>{person_names}</td>
                        <td>{lead['location']}</td>
                    </tr>
            """

        html_content += """
                </table>
                <p style="margin-top: 20px; font-size: 12px; color: #666;">
                    <em>Automated daily leads selection - Do not reply to this email</em>
                </p>
            </body>
        </html>
        """

        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"GCC Daily Leads - {datetime.now().strftime('%Y-%m-%d')}"
        msg["From"] = EMAIL_ADDRESS
        msg["To"] = RECIPIENT_EMAIL
        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT) as server:
            server.starttls()
            server.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
            server.send_message(msg)

        print("[EMAIL] Successfully sent to", RECIPIENT_EMAIL)
        return True
    except Exception as e:
        print(f"[ERROR] Failed to send email: {e}")
        return False


def get_daily_leads(count=5):
    all_leads = load_csv()
    if not all_leads:
        print("No leads found in CSV file.")
        return None

    tracking = load_tracking()
    processed = tracking.get("processed", [])

    available_leads = [lead for lead in all_leads if lead["company"] not in processed]

    if len(available_leads) == 0:
        print("[INFO] All leads have been processed! Resetting...")
        tracking["processed"] = []
        save_tracking(tracking)
        available_leads = all_leads

    priority_leads = [lead for lead in available_leads if is_priority_lead(lead)]
    secondary_leads = [lead for lead in available_leads if not is_priority_lead(lead)]

    selected = priority_leads[:count]
    if len(selected) < count:
        selected.extend(secondary_leads[: count - len(selected)])

    if len(selected) == 0:
        print("No leads available.")
        return None

    newly_processed = [lead["company"] for lead in selected]
    tracking["processed"].extend(newly_processed)
    tracking["last_run"] = datetime.now().isoformat()
    save_tracking(tracking)

    mark_in_csv(tracking["processed"])

    print(f"\n{'='*70}")
    print(f"[DAILY LEADS SELECTION] - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")

    for idx, lead in enumerate(selected, 1):
        person_names = lead.get("person_names", "") or "N/A"
        print(f"{idx}. {lead['company']}")
        print(f"   Person Name(s): {person_names}")
        print(f"   Location: {lead['location']}\n")

    print(f"{'='*70}")
    print(f"[MARKED] {len(newly_processed)} leads marked as sent (sent=YES)")
    print(f"Priority picks in this batch: {len([lead for lead in selected if is_priority_lead(lead)])}")
    print(f"Remaining unprocessed leads: {len(available_leads) - count}")
    print(f"Marked CSV saved as: {MARKED_CSV_FILE}")
    print(f"{'='*70}\n")

    print("[EMAIL] Attempting to send email...")
    send_email(selected)

    return selected


if __name__ == "__main__":
    get_daily_leads()
