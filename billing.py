import os
import json
import logging
import time
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import argparse
import traceback


class Config:
    """Centralized configuration management class."""

    # Default values
    DEFAULT_TAX_RATE = 0.11  # 11% VAT
    DEFAULT_API_TIMEOUT = 15  # seconds
    DEFAULT_API_RETRIES = 3
    DEFAULT_TIMEZONE_OFFSET = 7  # GMT+7 (Jakarta)
    DEFAULT_LOOKBACK_DAYS = 90

    # Meta API versions to try
    API_VERSIONS = ["v23.0", "v24.0"]

    # Account types
    ACCOUNT_TYPES = ["account_type1", "account_type2", "account_type3"]

    # Worksheet settings
    WORKSHEET_NAME = "Fetcher"
    WORKSHEET_HEADERS = [
        "Account",
        "Transaction ID",
        "Faktur Pajak",
        "Date (yyyy-mm-dd)",
        "Amount",
        "With Tax",
        "Card",
        "URL Invoice",
    ]

    def __init__(self):
        """Initialize configuration from environment variables."""
        # Load environment variables
        load_dotenv()

        # Load config values
        self.tax_rate = float(os.getenv("TAX_RATE", self.DEFAULT_TAX_RATE))
        self.api_timeout = int(os.getenv("API_TIMEOUT", self.DEFAULT_API_TIMEOUT))
        self.api_retries = int(os.getenv("API_RETRIES", self.DEFAULT_API_RETRIES))
        self.timezone_offset = int(
            os.getenv("TIMEZONE_OFFSET", self.DEFAULT_TIMEZONE_OFFSET)
        )

        # Clean and load spreadsheet name
        spreadsheet_name = os.getenv("spreadsheet_name_pub", "")
        if "#" in spreadsheet_name:
            spreadsheet_name = spreadsheet_name.split("#")[0]
        self.spreadsheet_name = (
            spreadsheet_name.replace("'", "").replace('"', "").strip()
        )

        # Load Meta access token
        self.access_token = os.getenv("META_ACCESS_TOKEN", "")

        # Load credentials file path
        self.credentials_file = os.getenv("credentials_file")

        # Load ad account IDs
        self.ad_account_ids = []
        for acc in self.ACCOUNT_TYPES:
            account_id = os.getenv(acc)
            if account_id:
                self.ad_account_ids.append(account_id)

    def is_valid(self) -> bool:
        """Check if the configuration is valid."""
        return (
            self.access_token
            and len(self.ad_account_ids) > 0
            and self.credentials_file
            and self.spreadsheet_name
        )

    def get_validation_errors(self) -> List[str]:
        """Get a list of validation error messages."""
        errors = []
        if not self.access_token:
            errors.append("META_ACCESS_TOKEN not found in .env file!")
        if not self.ad_account_ids:
            errors.append("No ad account IDs found in .env file!")
        if not self.credentials_file:
            errors.append("credentials_file not found in .env file!")
        if not self.spreadsheet_name:
            errors.append("spreadsheet_name_pub not found in .env file!")
        return errors

    def get_invoice_url(self, account_id: str, transaction_id: str) -> str:
        """Get the invoice URL for a transaction."""
        # Remove 'act_' prefix if present
        account_id = account_id.replace("act_", "")
        return f"https://business.facebook.com/ads/manage/billing_transaction/?act={account_id}&pdf=true&print=false&source=billing_summary&tx_type=3&txid={transaction_id}"


# Create a global config instance
config = Config()


# Configure logging
def setup_logging(debug: bool = False) -> None:
    """Set up logging configuration."""
    log_level = logging.DEBUG if debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # Create logger
    logger = logging.getLogger("meta_billing")
    logger.setLevel(log_level)
    # Prevent duplicate handlers if function is called multiple times
    if logger.handlers:
        return
    # Create console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    # Create formatter
    formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    # Add handler to logger
    logger.addHandler(console_handler)


# Get logger
logger = logging.getLogger("meta_billing")


# Configure requests with retry logic
def create_requests_session(
    retries: int = None,
    backoff_factor: float = 0.3,
    status_forcelist: tuple = (429, 500, 502, 503, 504),
    timeout: int = None,
) -> requests.Session:
    """Create a requests session with retry capability."""
    session = requests.Session()

    # Use values from config if not specified
    retries = retries if retries is not None else config.api_retries
    timeout = timeout if timeout is not None else config.api_timeout

    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    session.timeout = timeout
    return session


# Create a session to be used throughout the script
session = create_requests_session()


def make_api_request(
    url: str, params: Dict[str, Any], method: str = "GET"
) -> Optional[Dict[str, Any]]:
    """Make API request with retry logic and proper error handling."""
    try:
        if method.upper() == "GET":
            response = session.get(url, params=params)
        else:
            response = session.post(url, json=params)

        # Handle rate limiting specifically
        if response.status_code == 429:
            retry_after = int(response.headers.get("Retry-After", 5))
            logger.warning(f"Rate limited by API. Waiting {retry_after} seconds...")
            time.sleep(retry_after)
            # Retry the request
            return make_api_request(url, params, method)

        # Check if the request was successful
        response.raise_for_status()

        # Return JSON data if successful
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"API request failed with status code: {response.status_code}")
            logger.error(f"Response: {response.text[:200]}...")
            return None

    except requests.exceptions.RequestException as e:
        logger.error(f"Request failed: {str(e)}")
        return None
    except json.JSONDecodeError:
        logger.error("Failed to decode API response as JSON")
        return None
    except Exception as e:
        logger.error(f"Unexpected error during API request: {str(e)}")
        return None


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Fetch Facebook Ads Transaction data")
    parser.add_argument(
        "--start-date", type=str, help="Start date in YYYY-MM-DD format"
    )
    parser.add_argument("--end-date", type=str, help="End date in YYYY-MM-DD format")
    parser.add_argument(
        "--last-days",
        type=int,
        default=config.DEFAULT_LOOKBACK_DAYS,
        help=f"Fetch data for the last N days (default: {config.DEFAULT_LOOKBACK_DAYS})",
    )
    parser.add_argument("--debug", action="store_true", help="Enable verbose debugging")
    return parser.parse_args()


def validate_date(date_str: str) -> bool:
    """Validate if the date string is in correct format."""
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def load_environment_variables() -> Dict[str, Any]:
    """Load and return environment variables."""
    load_dotenv()

    # Get spreadsheet name and clean it
    spreadsheet_name = os.getenv("spreadsheet_name_pub", "")
    # Remove any quotes, comments and extra whitespace
    if "#" in spreadsheet_name:
        spreadsheet_name = spreadsheet_name.split("#")[0]
    spreadsheet_name = spreadsheet_name.replace("'", "").replace('"', "").strip()
    logger.info(f"Attempting to access spreadsheet: '{spreadsheet_name}'")

    # Debug: Print access token first few and last few characters
    access_token = os.getenv("META_ACCESS_TOKEN", "")
    token_preview = (
        f"{access_token[:5]}...{access_token[-5:]}" if access_token else "NOT FOUND"
    )
    logger.info(f"Access token loaded: {token_preview}")

    # Get ad account IDs
    ad_account_ids = []
    for acc in [
        "otc",
        "rho",
        "biu",
        "taff",
        "apx",
        "jn",
        "jm",
        "taff_shopee",
        "taff_tokopedia",
        "otc_shopee",
        "otc_tokopedia",
        "rhodey_shopee",
        "rhodey_tokopedia",
        "taffomi_shopee",
        "biutte_shopee",
        "apexel_shopee",
    ]:
        account_id = os.getenv(acc)
        if account_id:
            ad_account_ids.append(account_id)
            logger.info(f"Found account ID for {acc}: {account_id}")

    if not ad_account_ids:
        logger.warning("WARNING: No ad account IDs found in environment variables!")

    return {
        "access_token": access_token,
        "ad_account_ids": ad_account_ids,
        "spreadsheet_name": spreadsheet_name,
        "credentials_file": os.getenv("credentials_file"),
    }


def test_api_connection(access_token: str, ad_account_id: str) -> Dict[str, Any]:
    """Test API connection and return account details."""
    logger.info(f"Testing API connection for account {ad_account_id}")

    # Try current API versions
    api_versions = Config.API_VERSIONS

    for version in api_versions:
        url = f"https://graph.facebook.com/{version}/{ad_account_id}"
        params = {
            "access_token": access_token,
            "fields": "account_id,name,currency,account_status",
        }

        logger.info(f"Trying API version: {version}")

        result = make_api_request(url, params)
        if result:
            logger.info(f"API connection successful for account {ad_account_id}")
            logger.debug(f"Account details: {json.dumps(result, indent=2)}")
            logger.info(f"Using API version: {version}")
            return result
        else:
            logger.warning(f"Failed with API version {version}")

    logger.error(f"All API versions failed for account {ad_account_id}")
    return {}


def fetch_charge_activities(
    access_token: str,
    ad_account_id: str,
    start_date: str,
    end_date: str,
    debug: bool = False,
) -> List[Dict[str, Any]]:
    """Fetch credit line activities which contain transaction information."""
    # Convert dates to timestamps in GMT+7
    start_dt = datetime.strptime(start_date, "%Y-%m-%d").replace(
        hour=0, minute=0, second=0
    )
    end_dt = datetime.strptime(end_date, "%Y-%m-%d").replace(
        hour=23, minute=59, second=59
    )

    # Add 7 hours to convert to GMT+7
    start_timestamp = int(start_dt.timestamp()) + (7 * 3600)
    end_timestamp = int(end_dt.timestamp()) + (7 * 3600)

    logger.info(
        f"Fetching activities for account {ad_account_id} from {start_date} to {end_date}"
    )

    # Find working API version
    working_version = find_working_api_version(access_token, ad_account_id)
    if not working_version:
        logger.error("Could not find working API version!")
        return []

    # Use the working API version to fetch activities
    all_activities = fetch_activities_with_multiple_approaches(
        access_token,
        ad_account_id,
        working_version,
        start_date,
        end_date,
        start_timestamp,
        end_timestamp,
        debug,
    )

    # Filter for payment activities
    payment_activities = filter_payment_activities(all_activities)
    logger.info(
        f"Total payment activities found from target period: {len(payment_activities)}"
    )
    return payment_activities


def find_working_api_version(access_token: str, ad_account_id: str) -> Optional[str]:
    """Find a working API version for the given ad account."""
    api_versions = Config.API_VERSIONS

    for version in api_versions:
        test_url = f"https://graph.facebook.com/{version}/{ad_account_id}"
        test_params = {"access_token": access_token, "fields": "name"}

        result = make_api_request(test_url, test_params)
        if result:
            logger.info(f"Using API version: {version}")
            return version

    return None


def fetch_activities_with_multiple_approaches(
    access_token: str,
    ad_account_id: str,
    api_version: str,
    start_date: str,
    end_date: str,
    start_timestamp: int,
    end_timestamp: int,
    debug: bool,
) -> List[Dict[str, Any]]:
    """Try multiple approaches to fetch activities."""
    url = f"https://graph.facebook.com/{api_version}/{ad_account_id}/activities"

    # Simple approaches focused on the specific date range
    approaches = [
        # Approach 1: Direct date parameters
        {
            "access_token": access_token,
            "fields": "event_time,event_type,extra_data",
            "limit": 1000,
            "since": start_timestamp,
            "until": end_timestamp,
        },
        # Approach 2: date_preset with time_range
        {
            "access_token": access_token,
            "fields": "event_time,event_type,extra_data",
            "limit": 1000,
            "date_preset": "custom",
            "time_range": json.dumps(
                {"since": start_timestamp, "until": end_timestamp}
            ),
        },
        # Approach 3: from/to parameters
        {
            "access_token": access_token,
            "fields": "event_time,event_type,extra_data",
            "limit": 1000,
            "from": start_timestamp,
            "to": end_timestamp,
        },
    ]

    all_activities = []
    target_year_month = start_date[:7]  # YYYY-MM

    for i, params in enumerate(approaches):
        logger.info(
            f"Trying approach {i + 1} for date range {start_date} to {end_date}"
        )
        logger.debug(
            f"Parameters: {json.dumps({k: v for k, v in params.items() if k != 'access_token'})}"
        )

        result = make_api_request(url, params)
        if not result:
            logger.warning(f"Approach {i + 1} failed")
            continue

        data_count = len(result.get("data", []))
        logger.info(f"Success with approach {i + 1}! Found {data_count} activities.")

        # Check if data could be from the right time period
        if data_count > 0:
            first_date = result["data"][0].get("event_time", "")
            logger.info(f"First record date: {first_date}")

            # Filter activities by target year-month
            found_activities = []
            for activity in result.get("data", []):
                event_time = activity.get("event_time", "")
                if target_year_month in event_time:
                    found_activities.append(activity)

            if found_activities:
                logger.info(
                    f"Found {len(found_activities)} activities from {target_year_month}!"
                )

                # Check for pagination and fetch more data if available
                if "paging" in result and "next" in result["paging"]:
                    additional_activities = fetch_all_pages_from_next_url(
                        result["paging"]["next"], debug
                    )
                    # Filter additional activities
                    for activity in additional_activities:
                        event_time = activity.get("event_time", "")
                        if target_year_month in event_time:
                            found_activities.append(activity)
                    logger.info(
                        f"Found additional {len(additional_activities)} activities from pagination"
                    )

                return found_activities
            else:
                logger.info(
                    f"No data from {target_year_month} found, trying next approach..."
                )
        else:
            logger.info("No data found with this approach, trying next one...")

    # If we get here, no approach was successful
    logger.warning("\n⚠ Important Note:")
    logger.warning(f"Meta might not provide access to data from {start_date} anymore.")
    logger.warning(
        "Meta typically restricts historical data access to recent months only."
    )
    logger.warning(
        "Try a more recent date range or contact Meta support for historical data access."
    )

    return []


def fetch_all_pages_from_next_url(next_url: str, debug: bool) -> List[Dict[str, Any]]:
    """Fetch all pages of results using the next URL from pagination."""
    all_data = []
    page_count = 1
    current_url = next_url

    while current_url:
        logger.info(f"Fetching page {page_count + 1}...")

        # The URL already contains all parameters, so don't pass any params
        result = make_api_request(current_url, {})
        if not result:
            break

        new_data = result.get("data", [])
        all_data.extend(new_data)
        logger.info(f"Got {len(new_data)} more activities")
        page_count += 1

        if debug and new_data:
            logger.debug(f"Sample from page {page_count}:")
            logger.debug(json.dumps(new_data[0], indent=2)[:300] + "...")

        # Get next page URL if available
        current_url = result.get("paging", {}).get("next")

    logger.info(f"Fetched {page_count} pages with total {len(all_data)} activities")
    return all_data


def filter_payment_activities(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter activities to find payment-related ones."""
    payment_activities = [
        activity
        for activity in activities
        if (
            activity.get("event_type", "").lower().find("charge") >= 0
            or activity.get("event_type", "").lower().find("payment") >= 0
            or activity.get("event_type", "").lower().find("bill") >= 0
        )
    ]

    logger.info(
        f"Filtered {len(payment_activities)} payment activities from {len(activities)} total activities"
    )

    # Print sample of the first payment activity if available
    if payment_activities:
        logger.info("Sample payment activity:")
        logger.info(json.dumps(payment_activities[0], indent=2)[:300] + "...")

    return payment_activities


def fetch_all_pages(
    url: str, params: Dict[str, Any], first_result: Dict[str, Any], debug: bool
) -> List[Dict[str, Any]]:
    """Fetch all pages of results using pagination."""
    all_data = first_result.get("data", [])
    result = first_result
    page_count = 1

    # Handle pagination
    while "paging" in result and "next" in result["paging"]:
        next_url = result["paging"]["next"]
        logger.info(f"Fetching page {page_count + 1}...")

        try:
            response = requests.get(next_url)

            if response.status_code == 200:
                result = response.json()
                new_data = result.get("data", [])
                all_data.extend(new_data)
                logger.info(f"Got {len(new_data)} more activities")
                page_count += 1

                if debug:
                    logger.info(f"Sample from page {page_count}:")
                    if new_data:
                        logger.info(json.dumps(new_data[0], indent=2)[:300] + "...")
            else:
                logger.error(f"Error fetching next page: {response.text}")
                break
        except Exception as e:
            logger.error(f"Exception while fetching page {page_count + 1}: {str(e)}")
            break

    logger.info(f"Fetched {page_count} pages with total {len(all_data)} activities")
    return all_data


def get_date_range(days: int) -> tuple:
    """Get start and end dates based on number of days to look back."""
    end_date = datetime.utcnow() + timedelta(
        hours=config.timezone_offset
    )  # Use config timezone offset
    start_date = end_date - timedelta(days=days)
    return start_date.strftime("%Y-%m-%d"), end_date.strftime("%Y-%m-%d")


def initialize_google_sheets(
    credentials_file: str, spreadsheet_name: str
) -> gspread.Worksheet:
    """Initialize and return Google Sheets worksheet."""
    if not spreadsheet_name:
        raise ValueError("Spreadsheet name is not set in environment variables")

    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive",
    ]

    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(
            credentials_file, scope
        )
        client = gspread.authorize(creds)

        # Try to get existing spreadsheet
        try:
            spreadsheet = client.open(spreadsheet_name)
            logger.info(f"Successfully opened spreadsheet: {spreadsheet_name}")
        except gspread.exceptions.SpreadsheetNotFound:
            logger.error(f"Spreadsheet '{spreadsheet_name}' not found. Please check:")
            logger.error("1. The spreadsheet name in your .env file matches exactly")
            logger.error(
                "2. The service account email has been given access to the spreadsheet"
            )
            logger.error("3. The spreadsheet exists in Google Drive")
            raise

        # Use worksheet name from config
        worksheet_name = config.WORKSHEET_NAME

        try:
            sheet = spreadsheet.worksheet(worksheet_name)
            logger.info(f"Found existing worksheet: {worksheet_name}")
        except gspread.exceptions.WorksheetNotFound:
            logger.info(f"Creating new worksheet: {worksheet_name}")
            sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)

        # Check and set headers if needed
        if not sheet.row_values(1):
            sheet.append_row(config.WORKSHEET_HEADERS)
            logger.info("Added headers to worksheet")

        return sheet

    except Exception as e:
        logger.error(f"Error initializing Google Sheets: {str(e)}")
        traceback.print_exc()
        raise


def ensure_sheet_capacity(sheet: gspread.Worksheet, min_rows: int = 30000) -> None:
    """Ensure the sheet has enough rows to prevent range limit errors."""
    try:
        current_rows = sheet.row_count
        if current_rows < min_rows:
            additional_rows = min_rows - current_rows
            sheet.add_rows(additional_rows)
            logger.info(
                f"Added {additional_rows} rows to sheet. New total: {sheet.row_count}"
            )
    except Exception as e:
        logger.warning(f"Could not expand sheet capacity: {str(e)}")
        # This is not critical, append_row will still work


def process_transaction_data(
    account_info: Dict[str, Any], activities: List[Dict[str, Any]], debug: bool = False
) -> List[Dict[str, Any]]:
    """Process activities to extract transaction information."""
    transactions = []
    account_name = account_info.get("name", "Unknown Account")

    logger.info(f"Processing {len(activities)} activities for {account_name}")

    # Map of account names (lowercase) to default card numbers
    account_card_defaults = {
        "jakmall": "1092",
        # Add other account-specific defaults as needed
        # 'account_name': 'card_last4',
    }

    # Default card if no mapping exists
    default_card = "9816"

    for activity in activities:
        # Handle extra_data which might be a string or a dict
        extra_data_raw = activity.get("extra_data", {})

        # If extra_data is a string, try to parse it as JSON
        if isinstance(extra_data_raw, str):
            try:
                extra_data = json.loads(extra_data_raw)
            except json.JSONDecodeError:
                logger.error(f"Could not parse extra_data as JSON: {extra_data_raw}")
                extra_data = {"raw_data": extra_data_raw}
        else:
            extra_data = extra_data_raw

        # Debug: print out activity type and extra_data structure
        logger.debug(f"Processing activity type: {activity.get('event_type')}")
        logger.debug(f"Extra data type: {type(extra_data)}")

        if isinstance(extra_data, dict):
            # Just print keys to avoid large output
            logger.debug(f"Extra data keys: {list(extra_data.keys())}")
        else:
            logger.debug(f"Extra data content: {extra_data}")

        # Extract transaction ID directly from the data we have
        transaction_id = None
        if isinstance(extra_data, dict):
            # Try multiple possible keys for transaction ID
            for key in ["transaction_id", "id", "charge_id", "payment_id"]:
                if key in extra_data:
                    transaction_id = extra_data[key]
                    logger.debug(
                        f"Found transaction ID '{transaction_id}' in key '{key}'"
                    )
                    break

        # Extract amount - try different possible keys
        amount = None
        if isinstance(extra_data, dict):
            for key in ["new_value", "amount", "charge_amount", "value"]:
                if key in extra_data:
                    amount = extra_data[key]
                    logger.debug(f"Found amount '{amount}' in key '{key}'")
                    break

        # Calculate tax - use tax rate from config
        tax_amount = None
        if amount and isinstance(amount, (int, float)):
            tax_amount = round(amount * config.tax_rate)  # Use tax rate from config

        # Extract currency
        currency = None
        if isinstance(extra_data, dict):
            for key in ["currency", "funding_source_currency"]:
                if key in extra_data:
                    currency = extra_data[key]
                    break

        # Extract card number from extra_data - improved version with detailed debugging
        card_number = None
        if isinstance(extra_data, dict):
            # Add detailed debugging of card number extraction
            if debug:
                logger.debug("===== CARD NUMBER EXTRACTION DEBUGGING =====")
                logger.debug(
                    f"Account: {account_name}, Transaction ID: {transaction_id}"
                )

                # Check payment_method_details
                payment_info = extra_data.get("payment_method_details", {})
                logger.debug(f"payment_method_details type: {type(payment_info)}")
                logger.debug(f"payment_method_details content: {payment_info}")

                # Check for direct card number in extra_data
                logger.debug(
                    f"Direct card_number in extra_data: {extra_data.get('card_number')}"
                )

                # Check funding source details
                funding_source = extra_data.get("funding_source_details", {})
                logger.debug(f"funding_source_details: {funding_source}")

                # Check other potential places
                logger.debug(
                    f"payment_instrument: {extra_data.get('payment_instrument')}"
                )
                logger.debug(f"payment_details: {extra_data.get('payment_details')}")
                logger.debug(f"funding_source: {extra_data.get('funding_source')}")
                logger.debug("=========================================")

            payment_info = extra_data.get("payment_method_details", {})
            if isinstance(payment_info, str):
                try:
                    payment_info = json.loads(payment_info)
                    if debug:
                        logger.debug(f"Parsed payment_info from string: {payment_info}")
                except json.JSONDecodeError:
                    payment_info = {}
                    if debug:
                        logger.debug("Failed to parse payment_info as JSON")

            # Try different paths for card number
            if isinstance(payment_info, dict):
                card_number = payment_info.get("last4", "")
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in payment_info.last4"
                    )

            if (
                not card_number
                and isinstance(payment_info, dict)
                and payment_info.get("card_number")
            ):
                card_number = payment_info.get("card_number", "")[-4:]
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in payment_info.card_number"
                    )

            if not card_number and extra_data.get("card_number"):
                card_number = extra_data.get("card_number", "")[-4:]
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in extra_data.card_number"
                    )

            if not card_number and extra_data.get("funding_source_details", {}).get(
                "last4"
            ):
                card_number = extra_data.get("funding_source_details", {}).get("last4")
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in funding_source_details.last4"
                    )

            # Try additional potential locations for card data
            if not card_number and extra_data.get("payment_details", {}).get(
                "payment_method", {}
            ).get("card", {}).get("last4"):
                card_number = (
                    extra_data.get("payment_details", {})
                    .get("payment_method", {})
                    .get("card", {})
                    .get("last4")
                )
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in payment_details.payment_method.card.last4"
                    )

            # Try more possible paths
            if not card_number and extra_data.get("funding_source", {}).get("last4"):
                card_number = extra_data.get("funding_source", {}).get("last4")
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in funding_source.last4"
                    )

            if not card_number and extra_data.get("payment_instrument", {}).get(
                "card_last4"
            ):
                card_number = extra_data.get("payment_instrument", {}).get("card_last4")
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in payment_instrument.card_last4"
                    )

            if not card_number and extra_data.get("payment_instrument", {}).get(
                "last4"
            ):
                card_number = extra_data.get("payment_instrument", {}).get("last4")
                if debug and card_number:
                    logger.debug(
                        f"Found card number '{card_number}' in payment_instrument.last4"
                    )

            # Deep search JSON data recursively (new approach)
            if not card_number:
                card_number = find_card_number_in_json(extra_data, debug)
                if debug and card_number:
                    logger.debug(f"Found card number '{card_number}' via deep search")

        # If no card number found, use account-specific default or general default
        if not card_number:
            # Check account name (case-insensitive) against the mapping
            account_name_lower = account_name.lower()
            for account_key, card_default in account_card_defaults.items():
                if account_key in account_name_lower:
                    card_number = card_default
                    logger.info(
                        f"Using account-specific default card {card_number} for {account_name}"
                    )
                    break

            if not card_number:
                card_number = default_card
                logger.info(
                    f"Using general default card {card_number} for {account_name}"
                )

        if transaction_id and amount:
            # Get timestamp and format as date
            timestamp = activity.get("event_time")
            if timestamp:
                try:
                    # Handle ISO format timestamp (Facebook's format)
                    if isinstance(timestamp, str) and "T" in timestamp:
                        # Parse ISO format date and adjust to GMT+7
                        dt = datetime.strptime(
                            timestamp.split("+")[0], "%Y-%m-%dT%H:%M:%S"
                        )
                        dt = dt + timedelta(
                            hours=config.timezone_offset
                        )  # Use timezone offset from config
                        event_date = dt.strftime("%Y-%m-%d")
                    elif isinstance(timestamp, (int, float)):
                        # Handle numeric timestamp (already in UTC)
                        dt = datetime.fromtimestamp(timestamp)
                        dt = dt + timedelta(
                            hours=config.timezone_offset
                        )  # Use timezone offset from config
                        event_date = dt.strftime("%Y-%m-%d")
                    else:
                        # Try general approach
                        event_date = (
                            timestamp.split("T")[0] if "T" in timestamp else timestamp
                        )

                    # Prepare account_id for invoice URL
                    account_id = account_info.get("id", "").replace("act_", "")

                    transactions.append(
                        {
                            "account": account_name,
                            "transaction_id": transaction_id,
                            "date": event_date,
                            "amount": amount,
                            "tax_amount": tax_amount,
                            "currency": currency,
                            "card": card_number,  # Now uses the account-specific logic
                            "event_type": activity.get("event_type"),
                            "account_id": account_id,
                        }
                    )
                    logger.info(
                        f"Extracted transaction: {transaction_id} - {event_date} - {amount} {currency} (Tax: {tax_amount}, Card: {card_number})"
                    )
                except Exception as e:
                    logger.error(f"Error processing date for activity: {str(e)}")
                    traceback.print_exc()

    logger.info(f"Total {len(transactions)} transactions extracted")
    return transactions


def save_to_sheets(sheet: gspread.Worksheet, transactions: List[Dict[str, Any]]) -> int:
    """Save transaction data to Google Sheets using batch operations for better performance.

    Returns:
        int: Number of new transactions added
    """
    # First, get all existing transaction IDs to avoid duplicates
    try:
        existing_transaction_ids = set(
            sheet.col_values(2)[1:] if sheet.row_count > 1 else []
        )
        logger.info(
            f"Found {len(existing_transaction_ids)} existing transactions in sheet"
        )
    except Exception as e:
        logger.error(f"Error fetching existing transaction IDs: {str(e)}")
        return 0

    # Filter out transactions that already exist
    new_transactions = [
        t
        for t in transactions
        if t.get("transaction_id", "") not in existing_transaction_ids
    ]

    if not new_transactions:
        logger.info("No new transactions to add")
        return 0

    logger.info(f"Preparing to add {len(new_transactions)} new transactions")

    # Prepare batch data
    batch_rows = []

    for transaction in new_transactions:
        transaction_id = transaction.get("transaction_id", "")
        # Get base amount and calculate total with tax
        base_amount = transaction.get("amount", 0)
        total_with_tax = base_amount + round(
            base_amount * config.tax_rate
        )  # Use tax rate from config

        account_id = transaction.get("account_id", "")
        # Use the get_invoice_url method from config
        invoice_url = config.get_invoice_url(account_id, transaction_id)

        row = [
            transaction.get("account", ""),
            transaction_id,
            "",  # Faktur Pajak (empty as specified)
            transaction.get("date", ""),
            base_amount,  # Original amount without tax
            total_with_tax,  # Amount including tax
            transaction.get(
                "card", "Unknown"
            ),  # Use the actual card number from transaction
            invoice_url,
        ]

        batch_rows.append(row)

    # Use append_row for reliable insertion without range limits
    try:
        if batch_rows:
            count = 0
            logger.info(
                f"Adding {len(batch_rows)} transactions using append_row method"
            )

            for row in batch_rows:
                try:
                    sheet.append_row(row, value_input_option="USER_ENTERED")
                    count += 1
                except Exception as inner_e:
                    logger.error(f"Error adding row {count + 1}: {str(inner_e)}")
                    continue

            logger.info(f"Successfully added {count} transactions")

            # Log some details of the first few transactions
            for i, row in enumerate(batch_rows[:3]):
                logger.info(
                    f"Added: {row[1]} for {row[0]} on {row[3]} - Amount: {row[4]}, With Tax: {row[5]}"
                )

            if len(batch_rows) > 3:
                logger.info(f"... and {len(batch_rows) - 3} more transactions")

            return count
        else:
            return 0

    except Exception as e:
        logger.error(f"Unexpected error in append_row method: {str(e)}")
        traceback.print_exc()
        return 0


def find_card_number_in_json(data: Any, debug: bool = False) -> Optional[str]:
    """
    Recursively search a JSON structure for potential card number fields.

    This function looks for fields with names likely to contain card numbers
    like 'last4', 'card_number', etc.
    """
    if not isinstance(data, (dict, list)) or data is None:
        return None

    card_number_fields = [
        "last4",
        "card_number",
        "card_last4",
        "last_4",
        "cardNumber",
        "card",
    ]

    if isinstance(data, dict):
        # Check for direct card fields
        for field_name in card_number_fields:
            if field_name in data:
                value = data[field_name]
                if isinstance(value, str) and value:
                    # If the value is a full card number, take the last 4 digits
                    if len(value) > 4 and value.isdigit():
                        return value[-4:]
                    # Otherwise return as is if it looks like a card number fragment
                    elif len(value) <= 4 and value.isdigit():
                        return value

        # Recursively search in all dictionary values
        for key, value in data.items():
            result = find_card_number_in_json(value, debug)
            if result:
                if debug:
                    logger.debug(f"Found card in nested field: {key}")
                return result

    elif isinstance(data, list):
        # Search in list items
        for item in data:
            result = find_card_number_in_json(item, debug)
            if result:
                return result

    return None


# Add this function to help with debugging
def run_debug_session():
    """Run a special debug session to analyze card number extraction issues."""
    logger.info("Starting debug session for card number extraction")

    # Force debug mode
    args = parse_arguments()
    args.debug = True

    # Set up debug logging
    setup_logging(True)

    # Use specific date range
    if not args.start_date:
        args.start_date = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d")
    if not args.end_date:
        args.end_date = datetime.utcnow().strftime("%Y-%m-%d")

    logger.info(f"Debug session for date range: {args.start_date} to {args.end_date}")

    # Validate configuration
    if not config.is_valid():
        errors = config.get_validation_errors()
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return

    try:
        # Initialize Google Sheets
        sheet = initialize_google_sheets(
            config.credentials_file, config.spreadsheet_name
        )

        # Ensure sheet has enough capacity
        ensure_sheet_capacity(sheet)

        # Process each ad account
        for ad_account_id in config.ad_account_ids:
            account_info = test_api_connection(config.access_token, ad_account_id)
            if account_info:
                account_name = account_info.get("name", "Unknown")
                logger.info(
                    f"=== Analyzing account: {account_name} ({ad_account_id}) ==="
                )

                # Get activities containing transaction information
                activities = fetch_charge_activities(
                    config.access_token,
                    ad_account_id,
                    args.start_date,
                    args.end_date,
                    debug=True,
                )

                if activities:
                    # Just process for debugging, don't save
                    process_transaction_data(account_info, activities, debug=True)
                else:
                    logger.info(f"No activities found for account {ad_account_id}")

    except Exception as e:
        logger.error(f"Error in debug session: {str(e)}")
        traceback.print_exc()


def main():
    # Parse arguments first
    args = parse_arguments()

    # Set up logging with debug flag before any logging calls
    setup_logging(args.debug)

    logger.info("\n=== META ADS TRANSACTION FETCHER ===")
    logger.info(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info(f"Debug mode: {'ON' if args.debug else 'OFF'}")

    # Validate configuration
    if not config.is_valid():
        errors = config.get_validation_errors()
        for error in errors:
            logger.error(f"Configuration error: {error}")
        return

    # Log configuration info
    logger.info(f"Spreadsheet: '{config.spreadsheet_name}'")
    token_preview = (
        f"{config.access_token[:5]}...{config.access_token[-5:]}"
        if config.access_token
        else "NOT FOUND"
    )
    logger.info(f"Access token: {token_preview}")
    logger.info(f"Found {len(config.ad_account_ids)} ad account IDs")

    # Determine and validate date range
    date_range = determine_date_range(args)
    if not date_range:
        return

    start_date, end_date = date_range

    try:
        # Initialize Google Sheets
        sheet = initialize_google_sheets(
            config.credentials_file, config.spreadsheet_name
        )

        # Ensure sheet has enough capacity
        ensure_sheet_capacity(sheet)

        # Process each ad account
        found_transactions = process_ad_accounts(
            config.access_token,
            config.ad_account_ids,
            start_date,
            end_date,
            sheet,
            args.debug,
        )

        if not found_transactions:
            logger.warning("\n=== NO TRANSACTIONS FOUND ===")
            logger.warning("Check the following:")
            logger.warning(
                "1. Historical Data Limits: Meta API typically only provides recent data (90-180 days)"
            )
            logger.warning(
                "2. Try running with a more recent date range (last 30-60 days)"
            )
            logger.warning(
                "3. For older data, download reports directly from Meta Business Manager"
            )
        else:
            logger.info(
                f"Successfully found and processed transactions for the period {start_date} to {end_date}"
            )

    except Exception as e:
        logger.error(f"ERROR: {str(e)}")
        traceback.print_exc()


def determine_date_range(args: argparse.Namespace) -> Optional[Tuple[str, str]]:
    """Determine and validate the date range."""
    # If start and end dates are provided in arguments
    if args.start_date and args.end_date:
        if not (validate_date(args.start_date) and validate_date(args.end_date)):
            logger.error("ERROR: Invalid date format. Please use YYYY-MM-DD format.")
            return None
        start_date, end_date = args.start_date, args.end_date
        logger.info(f"Using command-line date range: {start_date} to {end_date}")
    else:
        # Use default date range based on --last-days argument (or config default)
        days = args.last_days if args.last_days else config.DEFAULT_LOOKBACK_DAYS
        start_date, end_date = get_date_range(days)
        logger.info(
            f"Using default date range (last {days} days): {start_date} to {end_date}"
        )

    # Verify date range makes sense
    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")

        if start_dt > end_dt:
            logger.error(
                f"ERROR: Start date {start_date} is after end date {end_date}!"
            )
            return None
    except ValueError:
        logger.error("ERROR: Could not parse dates. Please use YYYY-MM-DD format.")
        return None

    return start_date, end_date


def process_ad_accounts(
    access_token: str,
    ad_account_ids: List[str],
    start_date: str,
    end_date: str,
    sheet: gspread.Worksheet,
    debug: bool,
) -> bool:
    """Process all ad accounts and save transactions to sheet."""
    found_transactions = False

    for ad_account_id in ad_account_ids:
        account_info = test_api_connection(access_token, ad_account_id)
        if account_info:
            # Get activities containing transaction information
            activities = fetch_charge_activities(
                access_token, ad_account_id, start_date, end_date, debug=debug
            )

            if activities:
                # Process transaction data
                transactions = process_transaction_data(
                    account_info, activities, debug=debug
                )

                if transactions:
                    found_transactions = True
                    # Save to Google Sheets
                    save_to_sheets(sheet, transactions)
                else:
                    logger.info(
                        f"No valid transactions found for account {ad_account_id}"
                    )
            else:
                logger.info(
                    f"No activities found for account {ad_account_id} in the specified date range"
                )

    return found_transactions


if __name__ == "__main__":
    # Check if we're in debug session mode
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--debug-extraction":
        run_debug_session()
    else:
        main()
