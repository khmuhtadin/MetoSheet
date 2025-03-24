import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import argparse
import traceback

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Fetch Facebook Ads Transaction data')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--last-days', type=int, default=90, help='Fetch data for the last N days')
    parser.add_argument('--debug', action='store_true', help='Enable verbose debugging')
    return parser.parse_args()

def validate_date(date_str: str) -> bool:
    """Validate if the date string is in correct format."""
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return True
    except ValueError:
        return False

def load_environment_variables() -> Dict[str, Any]:
    """Load and return environment variables."""
    load_dotenv()
    
    # Get spreadsheet name and clean it
    spreadsheet_name = os.getenv('spreadsheet_name_pub', '')
    # Remove any quotes, comments and extra whitespace
    if '#' in spreadsheet_name:
        spreadsheet_name = spreadsheet_name.split('#')[0]
    spreadsheet_name = spreadsheet_name.replace("'", "").replace('"', "").strip()
    print(f"Attempting to access spreadsheet: '{spreadsheet_name}'")
    
    # Debug: Print access token first few and last few characters
    access_token = os.getenv('META_ACCESS_TOKEN', '')
    token_preview = f"{access_token[:5]}...{access_token[-5:]}" if access_token else "NOT FOUND"
    print(f"Access token loaded: {token_preview}")
    
    # Get ad account IDs
    ad_account_ids = []
    for acc in ['ad_account1', 'ad_account2', 'ad_account3']:
        account_id = os.getenv(acc)
        if account_id:
            ad_account_ids.append(account_id)
            print(f"Found account ID for {acc}: {account_id}")
    
    if not ad_account_ids:
        print("WARNING: No ad account IDs found in environment variables!")
    
    return {
        'access_token': access_token,
        'ad_account_ids': ad_account_ids,
        'spreadsheet_name': spreadsheet_name,
        'credentials_file': os.getenv('credentials_file')
    }

def test_api_connection(access_token: str, ad_account_id: str) -> Dict[str, Any]:
    """Test API connection and return account details."""
    print(f"\n--- Testing API connection for account {ad_account_id} ---")
    
    # Try current API versions
    api_versions = ["v21.0", "v22.0"]
    
    for version in api_versions:
        url = f"https://graph.facebook.com/{version}/{ad_account_id}"
        params = {'access_token': access_token, 'fields': 'account_id,name,currency,account_status'}
        
        print(f"Trying API version: {version}")
        try:
            response = requests.get(url, params=params)
            print(f"Response status code: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                print(f"API connection successful for account {ad_account_id}:", json.dumps(result, indent=2))
                print(f"Using API version: {version}")
                return result
            else:
                print(f"Failed with {version}: {response.text}")
        except Exception as e:
            print(f"Error with {version}: {str(e)}")
    
    print(f"All API versions failed for account {ad_account_id}")
    return {}

def fetch_charge_activities(access_token: str, ad_account_id: str, start_date: str, end_date: str, debug: bool = False) -> List[Dict[str, Any]]:
    """Fetch credit line activities which contain transaction information."""
    # Convert dates to timestamps in GMT+7
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').replace(hour=0, minute=0, second=0)
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').replace(hour=23, minute=59, second=59)
    
    # Add 7 hours to convert to GMT+7
    start_timestamp = int(start_dt.timestamp()) + (7 * 3600)
    end_timestamp = int(end_dt.timestamp()) + (7 * 3600)
    
    print(f"\n--- Fetching activities for account {ad_account_id} ---")
    
    # Working versions
    api_versions = ["v21.0", "v22.0"]
    working_version = None
    
    for version in api_versions:
        test_url = f"https://graph.facebook.com/{version}/{ad_account_id}"
        test_params = {'access_token': access_token, 'fields': 'name'}
        
        try:
            test_response = requests.get(test_url, params=test_params)
            if test_response.status_code == 200:
                working_version = version
                print(f"Using API version: {working_version}")
                break
        except Exception:
            continue
    
    if not working_version:
        print("ERROR: Could not find working API version!")
        return []
    
    # Use the working API version
    url = f'https://graph.facebook.com/{working_version}/{ad_account_id}/activities'
    
    # Simple approaches focused on the specific date range
    approaches = [
        # Approach 1: Direct date parameters
        {
            'access_token': access_token,
            'fields': 'event_time,event_type,extra_data',
            'limit': 1000,
            'since': start_timestamp,
            'until': end_timestamp
        },
        # Approach 2: date_preset with time_range
        {
            'access_token': access_token,
            'fields': 'event_time,event_type,extra_data',
            'limit': 1000,
            'date_preset': 'custom',
            'time_range': json.dumps({
                'since': start_timestamp,
                'until': end_timestamp
            })
        },
        # Approach 3: from/to parameters
        {
            'access_token': access_token,
            'fields': 'event_time,event_type,extra_data',
            'limit': 1000,
            'from': start_timestamp,
            'to': end_timestamp
        }
    ]
    
    all_activities = []
    success = False
    
    for i, params in enumerate(approaches):
        print(f"\nTrying approach {i+1} for date range {start_date} to {end_date}:")
        print(f"Parameters: {json.dumps({k: v for k, v in params.items() if k != 'access_token'})}")
        
        try:
            response = requests.get(url, params=params)
            
            if debug:
                print(f"Full API response for approach {i+1} (truncated):")
                print(response.text[:300] + "..." if len(response.text) > 300 else response.text)
            
            if response.status_code == 200:
                result = response.json()
                data_count = len(result.get('data', []))
                print(f"Success with approach {i+1}! Found {data_count} activities.")
                
                # Check if data could be from the right time period
                if data_count > 0:
                    # Check first record date
                    first_date = result['data'][0].get('event_time', '')
                    print(f"First record date: {first_date}")
                    
                    # Filter by actual date by checking for 2024 data
                    target_year_month = start_date[:7]  # YYYY-MM
                    found_activities = []
                    
                    for activity in result.get('data', []):
                        event_time = activity.get('event_time', '')
                        if target_year_month in event_time:
                            found_activities.append(activity)
                    
                    if found_activities:
                        print(f"Found {len(found_activities)} activities from {target_year_month}!")
                        all_activities = found_activities
                        success = True
                        break
                    else:
                        print(f"No data from {target_year_month} found, trying next approach...")
                else:
                    print("No data found with this approach, trying next one...")
            else:
                print(f"API error with approach {i+1}: {response.status_code}")
                print(response.text[:200])
        except Exception as e:
            print(f"Exception with approach {i+1}: {str(e)}")
            traceback.print_exc()
    
    if not success:
        print("\n⚠ Important Note:")
        print(f"Meta might not provide access to data from {start_date} anymore.")
        print("Meta typically restricts historical data access to recent months only.")
        print("Try a more recent date range or contact Meta support for historical data access.")
    
    # Filter for payment activities
    payment_activities = filter_payment_activities(all_activities)
    print(f"Total payment activities found from target period: {len(payment_activities)}")
    return payment_activities

def filter_payment_activities(activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Filter activities to find payment-related ones."""
    payment_activities = [
        activity for activity in activities
        if (activity.get('event_type', '').lower().find('charge') >= 0 or 
            activity.get('event_type', '').lower().find('payment') >= 0 or
            activity.get('event_type', '').lower().find('bill') >= 0)
    ]
    
    print(f"Filtered {len(payment_activities)} payment activities from {len(activities)} total activities")
    
    # Print sample of the first payment activity if available
    if payment_activities:
        print("Sample payment activity:")
        print(json.dumps(payment_activities[0], indent=2)[:300] + "...")
    
    return payment_activities

def fetch_all_pages(url: str, params: Dict[str, Any], first_result: Dict[str, Any], debug: bool) -> List[Dict[str, Any]]:
    """Fetch all pages of results using pagination."""
    all_data = first_result.get('data', [])
    result = first_result
    page_count = 1
    
    # Handle pagination
    while 'paging' in result and 'next' in result['paging']:
        next_url = result['paging']['next']
        print(f"Fetching page {page_count + 1}...")
        
        try:
            response = requests.get(next_url)
            
            if response.status_code == 200:
                result = response.json()
                new_data = result.get('data', [])
                all_data.extend(new_data)
                print(f"Got {len(new_data)} more activities")
                page_count += 1
                
                if debug:
                    print(f"Sample from page {page_count}:")
                    if new_data:
                        print(json.dumps(new_data[0], indent=2)[:300] + "...")
            else:
                print(f"Error fetching next page: {response.text}")
                break
        except Exception as e:
            print(f"Exception while fetching page {page_count + 1}: {str(e)}")
            break
    
    print(f"Fetched {page_count} pages with total {len(all_data)} activities")
    return all_data

def get_date_range(days: int) -> tuple:
    """Get start and end dates based on number of days to look back."""
    end_date = datetime.utcnow() + timedelta(hours=7)  # GMT+7
    start_date = end_date - timedelta(days=days)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')

def initialize_google_sheets(credentials_file: str, spreadsheet_name: str) -> gspread.Worksheet:
    """Initialize and return Google Sheets worksheet."""
    if not spreadsheet_name:
        raise ValueError("Spreadsheet name is not set in environment variables")
        
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
        client = gspread.authorize(creds)
        
        # Try to get existing spreadsheet
        try:
            spreadsheet = client.open(spreadsheet_name)
            print(f"Successfully opened spreadsheet: {spreadsheet_name}")
        except gspread.exceptions.SpreadsheetNotFound:
            print(f"Spreadsheet '{spreadsheet_name}' not found. Please check:")
            print("1. The spreadsheet name in your .env file matches exactly")
            print("2. The service account email has been given access to the spreadsheet")
            print("3. The spreadsheet exists in Google Drive")
            raise
        
        worksheet_name = 'Meta Transaction IDs'
        
        try:
            sheet = spreadsheet.worksheet(worksheet_name)
            print(f"Found existing worksheet: {worksheet_name}")
        except gspread.exceptions.WorksheetNotFound:
            print(f"Creating new worksheet: {worksheet_name}")
            sheet = spreadsheet.add_worksheet(title=worksheet_name, rows=1000, cols=20)
        
        # Check and set headers if needed
        if not sheet.row_values(1):
            headers = [
                "Account",
                "Transaction ID",
                "Faktur Pajak",
                "Date (yyyy-mm-dd)",
                "Amount",
                "With Tax",
                "Card",
                "URL Invoice"
            ]
            sheet.append_row(headers)
            print("Added headers to worksheet")
        
        return sheet
        
    except Exception as e:
        print(f"Error initializing Google Sheets: {str(e)}")
        traceback.print_exc()
        raise

def process_transaction_data(account_info: Dict[str, Any], activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process activities to extract transaction information."""
    transactions = []
    account_name = account_info.get('name', 'Unknown Account')
    
    print(f"\n--- Processing {len(activities)} activities for {account_name} ---")
    
    for activity in activities:
        # Handle extra_data which might be a string or a dict
        extra_data_raw = activity.get('extra_data', {})
        
        # If extra_data is a string, try to parse it as JSON
        if isinstance(extra_data_raw, str):
            try:
                extra_data = json.loads(extra_data_raw)
            except json.JSONDecodeError:
                print(f"Could not parse extra_data as JSON: {extra_data_raw}")
                extra_data = {"raw_data": extra_data_raw}
        else:
            extra_data = extra_data_raw
            
        # Debug: print out activity type and extra_data structure
        print(f"\nProcessing activity type: {activity.get('event_type')}")
        print(f"Extra data type: {type(extra_data)}")
        
        if isinstance(extra_data, dict):
            # Just print keys to avoid large output
            print(f"Extra data keys: {list(extra_data.keys())}")
        else:
            print(f"Extra data content: {extra_data}")
        
        # Extract transaction ID directly from the data we have
        transaction_id = None
        if isinstance(extra_data, dict):
            # Try multiple possible keys for transaction ID
            for key in ['transaction_id', 'id', 'charge_id', 'payment_id']:
                if key in extra_data:
                    transaction_id = extra_data[key]
                    print(f"Found transaction ID '{transaction_id}' in key '{key}'")
                    break
        
        # Extract amount - try different possible keys
        amount = None
        if isinstance(extra_data, dict):
            for key in ['new_value', 'amount', 'charge_amount', 'value']:
                if key in extra_data:
                    amount = extra_data[key]
                    print(f"Found amount '{amount}' in key '{key}'")
                    break
        
        # Calculate tax - for Indonesia, standard VAT is 11%
        tax_amount = None
        if amount and isinstance(amount, (int, float)):
            # Calculate tax amount (11% of base amount)
            tax_rate = 0.11
            tax_amount = round(amount * tax_rate)  # 11% of pre-tax amount
        
        # Extract currency
        currency = None
        if isinstance(extra_data, dict):
            for key in ['currency', 'funding_source_currency']:
                if key in extra_data:
                    currency = extra_data[key]
                    break
        
        # Extract card number from extra_data - improved version
        card_number = None
        if isinstance(extra_data, dict):
            payment_info = extra_data.get('payment_method_details', {})
            if isinstance(payment_info, str):
                try:
                    payment_info = json.loads(payment_info)
                except json.JSONDecodeError:
                    payment_info = {}
            
            # Try different paths for card number
            if isinstance(payment_info, dict):
                card_number = payment_info.get('last4', '')
                
            if not card_number and isinstance(payment_info, dict) and payment_info.get('card_number'):
                card_number = payment_info.get('card_number', '')[-4:]
                
            if not card_number and extra_data.get('card_number'):
                card_number = extra_data.get('card_number', '')[-4:]
                
            if not card_number and extra_data.get('funding_source_details', {}).get('last4'):
                card_number = extra_data.get('funding_source_details', {}).get('last4')
        
        if transaction_id and amount:
            # Get timestamp and format as date
            timestamp = activity.get('event_time')
            if timestamp:
                try:
                    # Handle ISO format timestamp (Facebook's format)
                    if isinstance(timestamp, str) and 'T' in timestamp:
                        # Parse ISO format date and adjust to GMT+7
                        dt = datetime.strptime(timestamp.split('+')[0], '%Y-%m-%dT%H:%M:%S')
                        dt = dt + timedelta(hours=7)  # Adjust to GMT+7
                        event_date = dt.strftime('%Y-%m-%d')
                    elif isinstance(timestamp, (int, float)):
                        # Handle numeric timestamp (already in UTC)
                        dt = datetime.fromtimestamp(timestamp)
                        dt = dt + timedelta(hours=7)  # Adjust to GMT+7
                        event_date = dt.strftime('%Y-%m-%d')
                    else:
                        # Try general approach
                        event_date = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                    
                    # Prepare account_id for invoice URL
                    account_id = account_info.get('id', '').replace('act_', '')
                    
                    transactions.append({
                        'account': account_name,
                        'transaction_id': transaction_id,
                        'date': event_date,
                        'amount': amount,
                        'tax_amount': tax_amount,
                        'currency': currency,
                        'card': card_number if card_number else '9816',  # Default to '9816' if no card found
                        'event_type': activity.get('event_type'),
                        'account_id': account_id
                    })
                    print(f"Successfully extracted transaction: {transaction_id} - {event_date} - {amount} {currency} (Tax: {tax_amount}, Card: {card_number})")
                except Exception as e:
                    print(f"Error processing date for activity: {str(e)}")
                    traceback.print_exc()
    
    print(f"Total {len(transactions)} transactions extracted")
    return transactions

def save_to_sheets(sheet: gspread.Worksheet, transactions: List[Dict[str, Any]]):
    """Save transaction data to Google Sheets."""
    existing_transaction_ids = sheet.col_values(2)[1:] if sheet.row_count > 1 else []
    
    count = 0
    for transaction in transactions:
        transaction_id = transaction.get('transaction_id', '')
        
        if transaction_id in existing_transaction_ids:
            print(f"Skipping duplicate transaction ID: {transaction_id}")
            continue
        
        # Get base amount and calculate total with tax
        base_amount = transaction.get('amount', 0)
        total_with_tax = base_amount + round(base_amount * 0.11)  # Base + 11% tax
        
        account_id = transaction.get('account_id', '')
        invoice_url = f"https://business.facebook.com/ads/manage/billing_transaction/?act={account_id}&pdf=true&print=false&source=billing_summary&tx_type=3&txid={transaction_id}"
            
        row = [
            transaction.get('account', ''),
            transaction_id,
            '',  # Faktur Pajak (empty as specified)
            transaction.get('date', ''),
            base_amount,  # Original amount without tax
            total_with_tax,  # Amount including tax
            transaction.get('card', 'Unknown'),  # Use the actual card number from transaction
            invoice_url
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        count += 1
        print(f"Added transaction {transaction_id} for {transaction.get('account')} on {transaction.get('date')} - Amount: {base_amount}, With Tax: {total_with_tax}")
    
    print(f"Total {count} new transactions added to Google Sheets")

def main():
    args = parse_arguments()
    env_vars = load_environment_variables()
    
    print("\n=== META ADS TRANSACTION FETCHER ===")
    print(f"Run time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Debug mode: {'ON' if args.debug else 'OFF'}")
    
    # Check for required environment variables
    if not env_vars['access_token']:
        print("ERROR: META_ACCESS_TOKEN not found in .env file!")
        return
        
    if not env_vars['ad_account_ids']:
        print("ERROR: No ad account IDs found in .env file!")
        return
        
    if not env_vars['credentials_file']:
        print("ERROR: credentials_file not found in .env file!")
        return
        
    if not env_vars['spreadsheet_name']:
        print("ERROR: spreadsheet_name_pub not found in .env file!")
        return
    
    # Determine date range
    if args.start_date and args.end_date:
        if not (validate_date(args.start_date) and validate_date(args.end_date)):
            print("ERROR: Invalid date format. Please use YYYY-MM-DD format.")
            return
        start_date, end_date = args.start_date, args.end_date
        print(f"Using command-line date range: {start_date} to {end_date}")
    else:
        start_date, end_date = get_date_range(args.last_days)
        print(f"Using default date range (last {args.last_days} days): {start_date} to {end_date}")
    
    # Verify date range makes sense
    try:
        start_dt = datetime.strptime(start_date, '%Y-%m-%d')
        end_dt = datetime.strptime(end_date, '%Y-%m-%d')
        
        if start_dt > end_dt:
            print(f"ERROR: Start date {start_date} is after end date {end_date}!")
            return
    except ValueError:
        print("ERROR: Could not parse dates. Please use YYYY-MM-DD format.")
        return
    
    try:
        # Initialize Google Sheets
        sheet = initialize_google_sheets(env_vars['credentials_file'], env_vars['spreadsheet_name'])
        
        # Process each ad account
        found_transactions = False
        
        for ad_account_id in env_vars['ad_account_ids']:
            account_info = test_api_connection(env_vars['access_token'], ad_account_id)
            if account_info:
                # Get activities containing transaction information
                activities = fetch_charge_activities(
                    env_vars['access_token'], 
                    ad_account_id, 
                    start_date, 
                    end_date,
                    debug=args.debug
                )
                
                if activities:
                    # Process transaction data
                    transactions = process_transaction_data(account_info, activities)
                    
                    if transactions:
                        found_transactions = True
                        # Save to Google Sheets
                        save_to_sheets(sheet, transactions)
                    else:
                        print(f"No valid transactions found for account {ad_account_id}")
                else:
                    print(f"No activities found for account {ad_account_id} in the specified date range")
        
        if not found_transactions:
            print("\n=== NO TRANSACTIONS FOUND ===")
            print("Check the following:")
            print("1. Historical Data Limits: Meta API typically only provides recent data (90-180 days)")
            print("2. Try running with a more recent date range (last 30-60 days)")
            print("3. For older data, download reports directly from Meta Business Manager")
            
    except Exception as e:
        print(f"ERROR: {str(e)}")
        traceback.print_exc()

if __name__ == "__main__":
    main()