import os
import json
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta, timezone
import argparse
import sys


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Fetch Facebook Ads data")
    parser.add_argument(
        "--date",
        type=str,
        help="Custom date in YYYY-MM-DD format. If not provided, will use yesterday.",
    )
    parser.add_argument(
        "--start-date", type=str, help="Start date in YYYY-MM-DD format for date range"
    )
    parser.add_argument(
        "--end-date", type=str, help="End date in YYYY-MM-DD format for date range"
    )
    return parser.parse_args()


def validate_date(date_str: str) -> bool:
    """Validate if the date string is in correct format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def load_environment_variables() -> Dict[str, Any]:
    """Load and return environment variables with validation."""
    load_dotenv()

    # Debug: Print all environment variables (excluding sensitive data)
    print("\nEnvironment variables loaded:")
    for key in os.environ:
        if key != "META_ACCESS_TOKEN":  # Don't print the actual token
            print(f"{key}: {os.environ[key]}")

    required_vars = {
        "META_ACCESS_TOKEN": "Facebook API access token",
        "credentials_file": "Google service account credentials file",
    }

    missing_vars = [var for var, desc in required_vars.items() if not os.getenv(var)]
    if missing_vars:
        print("Error: Missing required environment variables:")
        for var in missing_vars:
            print(f"- {var}: {required_vars[var]}")
        sys.exit(1)

    # Validate token format
    token = os.getenv("META_ACCESS_TOKEN", "")
    if not token.startswith("EAAB"):
        print(
            "Warning: Access token doesn't start with 'EAAB'. This might indicate an invalid token format."
        )

    ad_account_ids = [
        os.getenv(acc)
        for acc in ["ad_1", "ad_2", "ad_3", "ad_4", "ad_5", "ad_6"]
        if os.getenv(acc)
    ]
    if not ad_account_ids:
        print("Error: No ad account IDs found in environment variables")
        sys.exit(1)

    return {
        "access_token": token,
        "ad_account_ids": ad_account_ids,
        "spreadsheet_name": "Ads ONLY Report Tracking",
        "credentials_file": os.getenv("credentials_file"),
        "worksheet_name": os.getenv("WORKSHEET_NAME", "[wip] boost ads"),
        "webhook_url": os.getenv(
            "WEBHOOK_URL"
        ),  # Optional: Set in .env to enable webhook notifications
    }


def test_api_connection(access_token: str, ad_account_id: str) -> bool:
    """Test API connection for a given ad account."""
    if not access_token:
        print("Error: Access token is empty or None")
        return False

    url = f"https://graph.facebook.com/v24.0/{ad_account_id}"
    params = {"access_token": access_token, "fields": "account_id"}

    try:
        response = requests.get(url, params=params)
        if response.status_code == 200:
            return True
        else:
            error_data = response.json()
            print(f"Failed to connect to API for account {ad_account_id}:")
            print(f"Status code: {response.status_code}")
            print(
                f"Error message: {error_data.get('error', {}).get('message', 'Unknown error')}"
            )
            return False
    except Exception as e:
        print(f"Exception occurred while testing API connection: {str(e)}")
        return False


def test_all_accounts(access_token: str, ad_account_ids: List[str]) -> List[str]:
    """Test all ad accounts once and return list of valid account IDs."""
    print("\n" + "=" * 60)
    print("Testing API connections for all accounts...")
    print("=" * 60)

    valid_accounts = []
    failed_accounts = []

    for ad_account_id in ad_account_ids:
        print(f"Testing {ad_account_id}...", end=" ")
        if test_api_connection(access_token, ad_account_id):
            print("✅ Success")
            valid_accounts.append(ad_account_id)
        else:
            print("❌ Failed")
            failed_accounts.append(ad_account_id)

    print("\n" + "=" * 60)
    print(f"Connection Test Summary:")
    print(f"  ✅ Valid accounts: {len(valid_accounts)}")
    print(f"  ❌ Failed accounts: {len(failed_accounts)}")
    if failed_accounts:
        print(f"\n  Failed account IDs:")
        for acc in failed_accounts:
            print(f"    - {acc}")
    print("=" * 60 + "\n")

    if not valid_accounts:
        print("Error: No valid accounts available. Exiting.")
        sys.exit(1)

    return valid_accounts


def fetch_ads_performance_data(
    access_token: str, ad_account_id: str, date: str
) -> List[Dict[str, Any]]:
    """Fetch ads performance data for a given ad account with pagination support."""
    base_url = f"https://graph.facebook.com/v24.0/{ad_account_id}/insights"
    params = {
        "access_token": access_token,
        "level": "campaign",
        "time_range": json.dumps({"since": date, "until": date}),
        "fields": "campaign_name,account_name,account_id,impressions,spend,cpm,clicks,cpc,ctr,reach",
        "limit": 1000,
    }

    all_data = []
    next_url = base_url

    while next_url:
        try:
            response = requests.get(next_url, params=params)
            if response.ok:
                result = response.json()
                all_data.extend(result.get("data", []))

                next_url = result.get("paging", {}).get("next")
                params = {} if next_url else None
            else:
                print(
                    f"Failed to fetch ads performance for account {ad_account_id}: {response.json()}"
                )
                break
        except Exception as e:
            print(f"Error fetching data for account {ad_account_id}: {str(e)}")
            break

    return all_data


def get_yesterday_date() -> str:
    """Get yesterday's date in GMT+7 timezone."""
    current_datetime = datetime.now(timezone.utc) + timedelta(hours=7)
    return (current_datetime - timedelta(days=1)).strftime("%Y-%m-%d")


def get_date_range(start_date: str, end_date: str) -> List[str]:
    """Get a list of dates between start_date and end_date, inclusive."""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    date_range = []
    current = start
    while current <= end:
        date_range.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return date_range


def initialize_google_sheets(
    credentials_file: str, spreadsheet_name: str, worksheet_name: str
) -> gspread.Worksheet:
    """Initialize and return Google Sheets worksheet with error handling."""
    try:
        scope = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_file, scope
        )
        client = gspread.authorize(creds)

        # Force using 'Ads ONLY Report Tracking'
        spreadsheet_name = "Ads ONLY Report Tracking"
        print(f"\nOpening spreadsheet: {spreadsheet_name}")

        # Try to open the spreadsheet
        try:
            spreadsheet = client.open(spreadsheet_name)
            print(f"Successfully opened spreadsheet: {spreadsheet_name}")

            # Print available worksheets
            print("\nAvailable worksheets:")
            for ws in spreadsheet.worksheets():
                print(f"- {ws.title}")

        except gspread.exceptions.SpreadsheetNotFound:
            print(f"Error: Spreadsheet '{spreadsheet_name}' not found.")
            print(
                "Please check if the spreadsheet name is correct and the service account has access to it."
            )
            sys.exit(1)

        # Try to get the worksheet
        try:
            sheet = spreadsheet.worksheet(worksheet_name)
            print(f"Successfully found worksheet: {worksheet_name}")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Worksheet '{worksheet_name}' not found. Creating it...")
            sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
            header = [
                "Date",
                "Brand",
                "Campaign Name",
                "Account ID",
                "Account Name",
                "Impressions",
                "Spend",
                "CPM",
                "Clicks",
                "CPC",
                "CTR",
                "Reach",
            ]
            sheet.append_row(header)
            print(f"Created new worksheet '{worksheet_name}' with headers")

        return sheet

    except Exception as e:
        print(f"Error initializing Google Sheets: {str(e)}")
        print("Please check your credentials file and permissions.")
        sys.exit(1)


def process_data_item(
    data_item: Dict[str, Any], ad_account_id: str, date: str
) -> Tuple[List[Any], Dict[str, Any]]:
    """Process a single data item and return both row for Google Sheets and dict for webhook."""
    campaign_name = data_item.get("campaign_name", "Unknown Campaign")
    account_name = data_item.get("account_name", "Unknown Account")

    if ad_account_id == os.getenv("taff"):
        brand = "TaffOmicron" if "omi - " in campaign_name else account_name
    else:
        brand = account_name

    row = [
        date,
        brand,
        campaign_name,
        data_item.get("account_id", ""),
        account_name,
        int(data_item.get("impressions", 0)),
        float(data_item.get("spend", 0)),
        float(data_item.get("cpm", 0)),
        int(data_item.get("clicks", 0)),
        float(data_item.get("cpc", 0)),
        float(data_item.get("ctr", 0)),
        int(data_item.get("reach", 0)),
    ]

    webhook_data = {
        "date": date,
        "brand": brand,
        "campaign_name": campaign_name,
        "account_id": data_item.get("account_id", ""),
        "account_name": account_name,
        "impressions": int(data_item.get("impressions", 0)),
        "spend": float(data_item.get("spend", 0)),
        "cpm": float(data_item.get("cpm", 0)),
        "clicks": int(data_item.get("clicks", 0)),
        "cpc": float(data_item.get("cpc", 0)),
        "ctr": float(data_item.get("ctr", 0)),
        "reach": int(data_item.get("reach", 0)),
    }

    return row, webhook_data


def send_to_webhook(webhook_url: str, date: str, data: List[Dict[str, Any]]) -> bool:
    """Send data to webhook endpoint (non-blocking)."""
    if not webhook_url:
        return False

    try:
        payload = {"date": date, "total_rows": len(data), "rows": data}

        print(f"Sending {len(data)} rows to webhook...")
        response = requests.post(
            webhook_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10,
        )

        if response.status_code in [200, 201, 204]:
            print(f"✅ Webhook notification sent successfully")
            return True
        else:
            print(f"⚠️ Webhook returned status {response.status_code}: {response.text}")
            return False
    except requests.exceptions.Timeout:
        print("⚠️ Webhook request timed out (non-blocking, continuing...)")
        return False
    except Exception as e:
        print(f"⚠️ Failed to send webhook notification: {str(e)}")
        return False


def process_single_date(
    env_vars: Dict[str, Any],
    sheet: gspread.Worksheet,
    date: str,
    valid_accounts: List[str],
):
    """Process data for a single date with batch writing optimization."""
    print(f"\nProcessing data for date: {date}")
    all_rows = []
    all_webhook_data = []

    for ad_account_id in valid_accounts:
        print(f"Fetching data for account {ad_account_id}...")
        data = fetch_ads_performance_data(env_vars["access_token"], ad_account_id, date)
        print(f"Found {len(data)} campaigns for account {ad_account_id}")

        for data_item in data:
            row, webhook_data = process_data_item(data_item, ad_account_id, date)
            all_rows.append(row)
            all_webhook_data.append(webhook_data)

    # Batch write all rows at once for better performance
    if all_rows:
        print(f"Writing {len(all_rows)} rows to Google Sheets...")
        sheet.append_rows(all_rows, value_input_option="USER_ENTERED")
        print(f"✅ Successfully written {len(all_rows)} rows for date {date}")

        # Send to webhook after successful Google Sheets write
        send_to_webhook(env_vars.get("webhook_url"), date, all_webhook_data)
    else:
        print(f"No data to write for date {date}")


def main():
    args = parse_arguments()
    env_vars = load_environment_variables()

    # Test all accounts once and cache valid accounts
    valid_accounts = test_all_accounts(
        env_vars["access_token"], env_vars["ad_account_ids"]
    )

    sheet = initialize_google_sheets(
        env_vars["credentials_file"],
        env_vars["spreadsheet_name"],
        env_vars["worksheet_name"],
    )

    if args.start_date and args.end_date:
        # Date range mode
        if not (validate_date(args.start_date) and validate_date(args.end_date)):
            print("Invalid date format. Please use YYYY-MM-DD format.")
            return
        dates = get_date_range(args.start_date, args.end_date)
        print(f"\nProcessing date range from {args.start_date} to {args.end_date}")
        print(f"Total dates: {len(dates)}")
        for i, date in enumerate(dates, 1):
            print(f"\n[{i}/{len(dates)}] Processing {date}")
            process_single_date(env_vars, sheet, date, valid_accounts)
    elif args.date:
        # Single custom date mode
        if not validate_date(args.date):
            print("Invalid date format. Please use YYYY-MM-DD format.")
            return
        process_single_date(env_vars, sheet, args.date, valid_accounts)
    else:
        # Default yesterday mode
        yesterday = get_yesterday_date()
        process_single_date(env_vars, sheet, yesterday, valid_accounts)


if __name__ == "__main__":
    main()
