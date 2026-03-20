#!/usr/bin/env python3
"""
Bahria Assignment Tracker — sync.py
Scrapes Bahria University LMS (PHP-based) for assignments
and syncs new ones to Google Calendar.

Cron example (every 6 hours):
  0 */6 * * * /home/username/bahria-tracker/venv/bin/python3 /home/username/bahria-tracker/sync.py >> /home/username/bahria-tracker/cron.log 2>&1
"""

import os
import sys
import hashlib
import sqlite3
import logging
import datetime
import re

import requests
from bs4 import BeautifulSoup

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# ── Paths ─────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
DB_PATH    = os.path.join(BASE_DIR, "assignments.db")
TOKEN_FILE = os.path.join(BASE_DIR, "token.json")
LOG_FILE   = os.path.join(BASE_DIR, "cron.log")

# ── Config ────────────────────────────────────────────────
LMS_BASE         = "https://lms.bahria.edu.pk"
LMS_ASSIGN_URL   = f"{LMS_BASE}/Student/Assignments.php"
LMS_DASH_URL     = f"{LMS_BASE}/Student/Dashboard.php"

LMS_USER         = os.environ.get("BAHRIA_USER", "YOUR_ERP_ID_HERE")  # e.g. 01-131232-006
LMS_PASS         = os.environ.get("BAHRIA_PASS", "YOUR_PASSWORD_HERE")
LMS_INSTITUTE_ID = "1"   # 1=ISB E-8, 9=ISB H-11, 2=Karachi, 3=Lahore

# ── Google Calendar Config ────────────────────────────────
SCOPES      = ["https://www.googleapis.com/auth/calendar"]
CALENDAR_ID = "primary"
REMINDERS   = [1440, 180, 60, 15]

# ── Logging ───────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════
#  DATABASE
# ══════════════════════════════════════════════════════════

def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS assignments (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            fingerprint TEXT    UNIQUE NOT NULL,
            title       TEXT    NOT NULL,
            course      TEXT,
            due_date    TEXT,
            event_id    TEXT,
            synced_at   TEXT    DEFAULT (datetime('now'))
        )
    """)
    conn.commit()
    conn.close()


def fingerprint(title, course, due_date):
    raw = f"{title.lower().strip()}|{course.lower().strip()}|{due_date or ''}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def is_duplicate(title, course, due_date):
    fp = fingerprint(title, course, due_date)
    conn = sqlite3.connect(DB_PATH)
    row = conn.execute("SELECT id FROM assignments WHERE fingerprint = ?", (fp,)).fetchone()
    conn.close()
    return row is not None


def mark_synced(title, course, due_date, event_id):
    fp = fingerprint(title, course, due_date)
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        "INSERT OR IGNORE INTO assignments (fingerprint, title, course, due_date, event_id) VALUES (?,?,?,?,?)",
        (fp, title, course, due_date, event_id)
    )
    conn.commit()
    conn.close()


# ══════════════════════════════════════════════════════════
#  DATE PARSER
# ══════════════════════════════════════════════════════════

def parse_datetime(raw):
    """
    Parse LMS deadline string into (date_str, time_str) or (date_str, None).
    Handles formats like:
      "23 March 2026-05:00 pm"
      "2 March 2026-08:00 am"
      "23/03/2026"
    Returns (YYYY-MM-DD, HH:MM) or (YYYY-MM-DD, None)
    """
    if not raw:
        return None, None
    raw = raw.strip()

    # Try full datetime: "23 March 2026-05:00 pm" or "2 March 2026-08:00 am"
    dt_match = re.search(
        r"(\d{1,2}\s+[A-Za-z]+\s+\d{4})[-\s]+(\d{1,2}:\d{2}\s*[aApP][mM])",
        raw, re.IGNORECASE
    )
    if dt_match:
        try:
            dt = datetime.datetime.strptime(
                f"{dt_match.group(1)} {dt_match.group(2).strip()}",
                "%d %B %Y %I:%M %p"
            )
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")
        except ValueError:
            pass

    # Fall back to date-only formats
    date_formats = [
        ("%d/%m/%Y",  r"\d{2}/\d{2}/\d{4}"),
        ("%d-%m-%Y",  r"\d{2}-\d{2}-\d{4}"),
        ("%d-%b-%Y",  r"\d{1,2}-[A-Za-z]+-\d{4}"),
        ("%Y-%m-%d",  r"\d{4}-\d{2}-\d{2}"),
        ("%d %b %Y",  r"\d{1,2} [A-Za-z]+ \d{4}"),
        ("%d %B %Y",  r"\d{1,2} [A-Za-z]+ \d{4}"),
        ("%B %d, %Y", r"[A-Za-z]+ \d{1,2}, \d{4}"),
    ]
    for fmt, pattern in date_formats:
        m = re.search(pattern, raw, re.IGNORECASE)
        if m:
            try:
                return datetime.datetime.strptime(m.group(), fmt).strftime("%Y-%m-%d"), None
            except ValueError:
                continue
    return None, None


def parse_date(raw):
    date, _ = parse_datetime(raw)
    return date


# ══════════════════════════════════════════════════════════
#  LMS SCRAPER
# ══════════════════════════════════════════════════════════

def login():
    """
    1. GET CMS login page  -> grab ASP.NET hidden fields (ViewState etc.)
    2. POST credentials to CMS -> sets session cookie
    3. GET LMS dashboard   -> SSO shares the session, we are logged in
    """
    CMS_LOGIN = "https://cms.bahria.edu.pk/Logins/Student/Login.aspx"
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
        "Referer": CMS_LOGIN,
    })

    # Step 1: GET CMS login page for ViewState
    log.info("Fetching CMS login page...")
    try:
        resp = session.get(CMS_LOGIN, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Cannot reach CMS: {e}")
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    form_data = {
        inp["name"]: inp.get("value", "")
        for inp in soup.find_all("input", {"type": "hidden"})
        if inp.get("name")
    }
    form_data["ctl00$BodyPH$tbEnrollment"]   = LMS_USER
    form_data["ctl00$BodyPH$tbPassword"]     = LMS_PASS
    form_data["ctl00$BodyPH$ddlInstituteID"] = LMS_INSTITUTE_ID
    form_data["ctl00$BodyPH$ddlSubUserType"] = "None"
    form_data["ctl00$hfJsEnabled"]           = "1"
    form_data["__EVENTTARGET"]               = "ctl00$BodyPH$btnLogin"
    form_data["__EVENTARGUMENT"]             = ""

    # Step 2: POST to CMS
    log.info(f"Logging into CMS as {LMS_USER} (institute {LMS_INSTITUTE_ID})...")
    try:
        resp = session.post(CMS_LOGIN, data=form_data, timeout=30, allow_redirects=True)
    except requests.RequestException as e:
        log.error(f"CMS login POST failed: {e}")
        return None

    if "Login.aspx" in resp.url:
        log.error("CMS login failed — check ERP ID, password, and LMS_INSTITUTE_ID.")
        with open(os.path.join(BASE_DIR, "debug_login.html"), "w", encoding="utf-8") as f:
            f.write(resp.text)
        return None

    log.info(f"CMS login successful -> {resp.url}")

    # Step 3: Find the LMS link on the CMS dashboard and follow it
    # CMS passes a token to LMS via a redirect link — we must follow it
    log.info("Looking for LMS link on CMS dashboard...")
    cms_soup = BeautifulSoup(resp.text, "html.parser")
    lms_link = None
    for a in cms_soup.find_all("a", href=True):
        href = a["href"]
        if "lms.bahria.edu.pk" in href or ("lms" in href.lower() and "bahria" in href.lower()):
            lms_link = href
            log.info(f"Found LMS link: {lms_link}")
            break

    if lms_link:
        try:
            lms_resp = session.get(lms_link, timeout=30, allow_redirects=True)
            log.info(f"LMS link followed -> {lms_resp.url}")
        except requests.RequestException as e:
            log.error(f"Failed to follow LMS link: {e}")
            return None
    else:
        # No link found — try direct access anyway
        log.warning("No LMS link found on CMS dashboard. Trying direct access...")
        try:
            lms_resp = session.get(LMS_DASH_URL, timeout=30, allow_redirects=True)
        except requests.RequestException as e:
            log.error(f"Cannot reach LMS: {e}")
            return None

    log.info(f"LMS response URL: {lms_resp.url}")

    # Check if we actually landed on LMS
    if "lms.bahria.edu.pk" in lms_resp.url:
        log.info("LMS session confirmed.")
        return session

    # Still being redirected to CMS — dump CMS dashboard links for manual inspection
    log.error("Still being redirected to CMS. Could not establish LMS session.")
    log.error("Dumping all links from CMS dashboard to debug_cms_links.txt...")
    links = [(a.text.strip(), a["href"]) for a in cms_soup.find_all("a", href=True)]
    with open(os.path.join(BASE_DIR, "debug_cms_links.txt"), "w") as f:
        for text, href in links:
            f.write(f"{text!r:40s} -> {href}\n")
    log.error("Open debug_cms_links.txt and find the LMS link, then share it.")
    return None


def get_semester_and_courses(session):
    log.info(f"Fetching assignments page: {LMS_ASSIGN_URL}")
    try:
        resp = session.get(LMS_ASSIGN_URL, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        log.error(f"Cannot load assignments page: {e}")
        return None, {}

    log.info(f"Assignments page status: {resp.status_code}, final URL: {resp.url}")

    # Save page for inspection if parsing fails
    debug_path = os.path.join(BASE_DIR, "debug_assignments.html")
    with open(debug_path, "w", encoding="utf-8") as f:
        f.write(resp.text)
    log.info(f"Saved assignments page to {debug_path}")

    soup = BeautifulSoup(resp.text, "html.parser")

    semester_id = None
    semester_sel = soup.find("select", {"id": "semesterId"})
    if semester_sel:
        # Try selected option first, fall back to first option
        selected = semester_sel.find("option", selected=True) or semester_sel.find("option")
        if selected:
            semester_id = selected.get("value", "").strip()
            log.info(f"Current semester: {selected.text.strip()} (id={semester_id})")
    else:
        log.warning("semesterId select not found — using hardcoded Spring-2026 fallback.")
        semester_id = "MjAyNjE%3D"  # Spring-2026 fallback

    courses = {}
    course_sel = soup.find("select", {"id": "courseId"})
    if course_sel:
        for opt in course_sel.find_all("option"):
            val = opt.get("value", "").strip()
            if val:
                courses[val] = opt.text.strip()
        log.info(f"Found {len(courses)} courses: {list(courses.values())}")
    else:
        log.warning("courseId select not found in page.")

    return semester_id, courses


def scrape_course(session, semester_id, course_id, course_name):
    url = f"{LMS_ASSIGN_URL}?s={semester_id}&oc={course_id}"
    try:
        resp = session.get(url, timeout=30)
    except requests.RequestException as e:
        log.warning(f"  Could not fetch {course_name}: {e}")
        return []

    soup  = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="table")
    if not table:
        return []

    results = []
    for row in table.find_all("tr")[1:]:
        cells = row.find_all("td")
        if len(cells) < 8 or cells[0].get("colspan"):
            continue

        title        = cells[1].get_text(strip=True)
        action_cell  = cells[6]           # "Action" column
        deadline_raw = cells[7].get_text(strip=True)

        if not title or title in ["-", "N/A"]:
            continue

        action_text = action_cell.get_text(strip=True).lower()
        action_html = str(action_cell).lower()

        # Skip if deadline exceeded (red "Deadline Exceeded" div in action cell)
        if "deadline exceeded" in action_text:
            log.debug(f"    Skip (deadline exceeded): {title}")
            continue

        # Skip if no Submit button — means already submitted or not open
        if "submit" not in action_html:
            log.debug(f"    Skip (no submit button): {title}")
            continue

        due_date, due_time = parse_datetime(deadline_raw)
        results.append({"title": title, "course": course_name, "due_date": due_date, "due_time": due_time, "url": url})

    return results


def scrape_all():
    session = login()
    if not session:
        return []

    semester_id, courses = get_semester_and_courses(session)
    if not courses:
        log.error("Could not get course list from LMS.")
        return []
    if not semester_id:
        semester_id = "MjAyNjE%3D"
        log.warning(f"semester_id missing — defaulting to Spring-2026 ({semester_id})")

    all_assignments = []
    for course_id, course_name in courses.items():
        log.info(f"  Checking: {course_name}...")
        found = scrape_course(session, semester_id, course_id, course_name)
        log.info(f"    -> {len(found)} pending")
        all_assignments.extend(found)

    log.info(f"Total pending: {len(all_assignments)}")
    return all_assignments


# ══════════════════════════════════════════════════════════
#  GOOGLE CALENDAR
# ══════════════════════════════════════════════════════════

def get_calendar_service():
    if not os.path.exists(TOKEN_FILE):
        raise FileNotFoundError(f"token.json not found. Run auth.py locally first.")
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, "w") as f:
            f.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


def create_event(service, title, course, due_date, due_time=None, url=""):
    if not due_date:
        due_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()

    if due_time:
        # Timed event — deadline is at the exact time e.g. 17:00
        start_dt = f"{due_date}T{due_time}:00"
        end_dt   = f"{due_date}T{due_time}:00"
        start    = {"dateTime": start_dt, "timeZone": "Asia/Karachi"}
        end      = {"dateTime": end_dt,   "timeZone": "Asia/Karachi"}
        time_label = f" at {due_time}"
    else:
        # All-day fallback
        start    = {"date": due_date, "timeZone": "Asia/Karachi"}
        end      = {"date": due_date, "timeZone": "Asia/Karachi"}
        time_label = ""

    event = service.events().insert(
        calendarId=CALENDAR_ID,
        body={
            "summary":     f"Assignment: {title}",
            "description": f"Course: {course}\nDeadline: {due_date}{time_label}\nLMS: {url}\n\nAdded by Bahria Assignment Tracker.",
            "colorId":     "5",
            "start":       start,
            "end":         end,
            "reminders":   {"useDefault": False, "overrides": [{"method": "popup", "minutes": m} for m in REMINDERS]},
        }
    ).execute()
    return event.get("id")


# ══════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════

def main():
    log.info("=" * 55)
    log.info("Bahria LMS Assignment Tracker — sync started")
    log.info("=" * 55)

    init_db()
    assignments = scrape_all()
    if not assignments:
        log.info("No pending assignments found. Exiting.")
        return

    try:
        service = get_calendar_service()
    except FileNotFoundError as e:
        log.error(str(e))
        sys.exit(1)

    new_count = skip_count = 0
    for a in assignments:
        if is_duplicate(a["title"], a["course"], a["due_date"]):
            skip_count += 1
            continue
        try:
            event_id = create_event(service, a["title"], a["course"], a["due_date"], a.get("due_time"), a["url"])
            mark_synced(a["title"], a["course"], a["due_date"], event_id)
            time_str = (" " + a["due_time"]) if a.get("due_time") else ""
            log.info(f"  + Added: '{a['title']}' [{a['course']}] due {a['due_date'] or 'TBD'}{time_str}")
            new_count += 1
        except Exception as e:
            log.error(f"  x Failed '{a['title']}': {e}")
    log.info(f"Done -> {new_count} new, {skip_count} already existed.")
    log.info("=" * 55)


if __name__ == "__main__":
    main()
