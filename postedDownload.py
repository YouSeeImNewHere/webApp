import re
from playwright.sync_api import Playwright, sync_playwright, expect
from dotenv import load_dotenv
import os
from bs4 import BeautifulSoup
from datetime import datetime
import csv
from typing import List

from transactionHandler import makeKey, insert_transaction

load_dotenv()
STATE_FILE = "navyfcu_state.json"
ACCOUNTS_URL = "https://digitalomni.navyfederal.org/nfcu-online-banking/accounts/list/summary"
INPUT_FILE = "downloads/navyfcu_main_9338.csv"
#INPUT_FILE = "downloads/navyfcu_bills_7613.csv"

def extract_email_body(msg) -> str:
    """
    Returns the best-effort text body from an email.message.Message.
    Prefers text/plain, falls back to text/html (converted to text).
    """
    # 1) If multipart, walk parts
    if msg.is_multipart():
        plain_text = None
        html_text = None

        for part in msg.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_text = part.get_payload(decode=True).decode(errors="ignore")
                break  # we found what we want
            elif content_type == "text/html" and html_text is None:
                html_text = part.get_payload(decode=True).decode(errors="ignore")

        if plain_text is not None:
            return plain_text.strip()

        if html_text is not None:
            # convert HTML → text
            soup = BeautifulSoup(html_text, "html.parser")
            return soup.get_text(separator="\n").strip()

        return ""

    # 2) Not multipart: single-part message
    content_type = msg.get_content_type()
    payload = msg.get_payload(decode=True).decode(errors="ignore")

    if content_type == "text/plain":
        return payload.strip()

    if content_type == "text/html":
        soup = BeautifulSoup(payload, "html.parser")
        return soup.get_text(separator="\n").strip()

    return payload.strip()

def save_navyfed_session():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)  # MUST be visible for login
        context = browser.new_context()

        page = context.new_page()
        page.goto("https://www.navyfederal.org/")

        print("\n🟦 Playwright is paused. Log in manually (username, password, MFA).")
        print("🟦 When you reach your account dashboard, click 'Resume' in the inspector.\n")

        # Pause allows you to complete login manually.
        page.pause()

        # Once logged in and resume is pressed:
        context.storage_state(path="navyfcu_state.json")
        print("✅ Session saved to navyfcu_state.json")

        browser.close()

def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(headless=False)

    def new_context():
        return browser.new_context(
            storage_state=STATE_FILE,
            accept_downloads=True,
        )

    # --- First try with existing state ---
    context = new_context()
    page = context.new_page()
    page.goto(ACCOUNTS_URL)

    # --- Detect if we got sent to login instead of accounts ---
    is_login = False

    # Simple URL-based check
    if "sign-in" in page.url.lower():
        is_login = True
    else:
        # Optional: element-based check (wrapped in try so it doesn't crash)
        try:
            login_heading = page.get_by_role("heading", name=re.compile("sign in", re.I))
            if login_heading.is_visible():
                is_login = True
        except Exception:
            pass

    if is_login:
        # Old session is invalid: refresh session and recreate context
        context.close()

        # This should log in and write a fresh STATE_FILE
        save_navyfed_session(playwright)

        # New context with updated storage_state
        context = new_context()
        page = context.new_page()
        page.goto(ACCOUNTS_URL)
        page.wait_for_load_state("networkidle")

    # ==== DOWNLOAD MAIN - 9338 CSV ====
    page.get_by_role("button", name=re.compile(r"Main - 9338")).click()
    page.get_by_role("button", name="DOWNLOAD Download Transactions").click()
    with page.expect_download() as download_info:
        page.get_by_role("menuitem", name="CSV(Excel, Google Sheets)").click()
    download = download_info.value
    download.save_as("downloads/navyfcu_main_9338.csv")

    # ==== DOWNLOAD BILLS - 7613 CSV ====
    page.get_by_role("link", name="Accounts", exact=True).click()
    page.get_by_role("button", name=re.compile(r"Bills - 7613")).click()
    page.get_by_role("button", name="DOWNLOAD Download Transactions").click()
    with page.expect_download() as download1_info:
        page.get_by_role("menuitem", name="CSV(Excel, Google Sheets)").click()
    download1 = download1_info.value
    download1.save_as("downloads/navyfcu_bills_7613.csv")

    context.close()
    browser.close()

HEADERS = [
    "Posting Date",
    "Transaction Date",
    "Amount",
    "Credit Debit Indicator",
    "type",
    "Type Group",
    "Reference",
    "Instructed Currency",
    "Currency Exchange Rate",
    "Instructed Amount",
    "Description",
    "Category",
    "Check Serial Number",
    "Card Ending"
]

def get_filtered_transactions(min_date_str: str) -> List[List[str]]:
    cutoff = datetime.strptime(min_date_str, "%m/%d/%Y")
    rows_2d: List[List[str]] = []

    # utf-8-sig strips the BOM from the first header
    with open(INPUT_FILE, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)  # default delimiter = comma

        # Normalize header names (strip BOM/whitespace)
        reader.fieldnames = [name.lstrip("\ufeff").strip() for name in reader.fieldnames]

        for row in reader:
            posting_str = row.get("Transaction Date")
            debitOrCredit = row.get("Credit Debit Indicator")
            amount_str = row.get("Amount")

            if not posting_str:
                continue  # skip blank / malformed rows

            posting_date = datetime.strptime(posting_str, "%m/%d/%Y")

            if posting_date >= cutoff:

                # --- Convert Amount + apply negative for credits ---
                try:
                    amount_val = float(amount_str)
                except:
                    amount_val = 0.0

                if debitOrCredit and debitOrCredit.lower() == "credit":
                    print(row)
                    print(debitOrCredit, " ", amount_val)
                    amount_val = -abs(amount_val)  # always negative

                # Format back to 2 decimal places as a string
                fixed_amount = f"{amount_val:.2f}"

                # Build row in correct order
                new_row = [row.get(col, "") for col in HEADERS]

                # Replace the Amount column (index 2)
                new_row[2] = fixed_amount

                rows_2d.append(new_row)

    return rows_2d


if __name__ == "__main__":
    data_2d = get_filtered_transactions("01/01/2025")
    print(f"Filtered rows: {len(data_2d)}")
    # Peek at the first row

    for row in data_2d:
        #print(row)
        postedDate = datetime.strptime(row[0], "%m/%d/%Y").strftime("%m/%d/%y")
        transactionDate = datetime.strptime(row[1], "%m/%d/%Y").strftime("%m/%d/%y")
        amount = row[2]
        card = "Navy Fed Debit"
        where = row[10]
        key = makeKey(amount, transactionDate)
        accountType = "checking"

        # print("key: ", key)
        # print("postedDate:", postedDate)
        # print("transactionDate:", transactionDate)
        # print("amount:", amount)
        # print("card:", card)
        # print("where:", where)
        # print("=================")
        insert_transaction(key, "Navy Federal", card, accountType, amount, where, transactionDate, "unknown", "CSV", postedDate)

# with sync_playwright() as playwright:
#     run(playwright)