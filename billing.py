import os
import json
from typing import List, Dict, Any
from dotenv import load_dotenv
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import argparse

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Fetch Facebook Ads Transaction data')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format')
    parser.add_argument('--last-days', type=int, default=90, help='Fetch data for the last N days')
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
    
    return {
        'access_token': os.getenv('META_ACCESS_TOKEN'),
        'ad_account_ids': [os.getenv(acc) for acc in ['taff', 'otc', 'rho', 'biu', 'apx'] if os.getenv(acc)],
        'spreadsheet_name': spreadsheet_name,
        'credentials_file': os.getenv('credentials_file')
    }

def test_api_connection(access_token: str, ad_account_id: str) -> Dict[str, Any]:
    """Test API connection and return account details."""
    url = f"https://graph.facebook.com/v21.0/{ad_account_id}"
    params = {'access_token': access_token, 'fields': 'account_id,name,currency,account_status'}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        result = response.json()
        print(f"API connection successful for account {ad_account_id}:", json.dumps(result, indent=2))
        return result
    else:
        print(f"Failed to connect to API for account {ad_account_id}: {response.json()}")
        return {}

def fetch_charge_activities(access_token: str, ad_account_id: str, start_date: str, end_date: str) -> List[Dict[str, Any]]:
    """Fetch credit line activities which contain transaction information."""
    url = f'https://graph.facebook.com/v21.0/{ad_account_id}/activities'
    params = {
        'access_token': access_token,
        'date_preset': 'custom',
        'time_start': int(datetime.strptime(start_date, '%Y-%m-%d').timestamp()),
        'time_stop': int(datetime.strptime(end_date, '%Y-%m-%d').timestamp()) + 86399,  # End of day
        'limit': 1000,
        'fields': 'event_time,event_type,extra_data'
    }
    
    # Print the request URL and params for debugging
    print(f"Request URL: {url}")
    print(f"Parameters: time_start={params['time_start']}, time_stop={params['time_stop']}")
    
    all_activities = []
    next_url = url
    
    while next_url:
        try:
            response = requests.get(next_url, params=params)
            if response.ok:
                result = response.json()
                print(f"API response: {json.dumps(result, indent=2)[:500]}...") # Show first 500 chars
                
                # Filter for relevant payment activities - broader approach
                payment_activities = [
                    activity for activity in result.get('data', [])
                    if (activity.get('event_type', '').lower().find('charge') >= 0 or 
                        activity.get('event_type', '').lower().find('payment') >= 0 or
                        activity.get('event_type', '').lower().find('bill') >= 0)
                ]
                
                # If the above filter is too restrictive, uncomment this to get all activities
                # payment_activities = result.get('data', [])
                
                all_activities.extend(payment_activities)
                
                # Check for pagination
                next_url = result.get('paging', {}).get('next')
                params = {} if next_url else None
            else:
                print(f"Failed to fetch activities for account {ad_account_id}: {response.json()}")
                break
        except Exception as e:
            print(f"Error fetching activities for account {ad_account_id}: {str(e)}")
            break
    
    return all_activities

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
                "Plus Tax (google)",
                "Card",
                "URL Invoice"
            ]
            sheet.append_row(headers)
            print("Added headers to worksheet")
        
        return sheet
        
    except Exception as e:
        print(f"Error initializing Google Sheets: {str(e)}")
        raise

def process_transaction_data(account_info: Dict[str, Any], activities: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Process activities to extract transaction information."""
    transactions = []
    account_name = account_info.get('name', 'Unknown Account')
    
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
            
        print(f"Processing activity type: {activity.get('event_type')}")
        print(f"Extra data type: {type(extra_data)}")
        print(f"Extra data content: {extra_data}")
        
        # Extract transaction ID directly from the data we have
        transaction_id = extra_data.get('transaction_id') if isinstance(extra_data, dict) else None
        
        # Extract amount - in this API it's called "new_value" based on the debug output
        amount = extra_data.get('new_value') if isinstance(extra_data, dict) else None
        
        # Calculate tax - for Indonesia, standard VAT is 11%
        # CORRECTED: Data from Meta is BEFORE tax, so we calculate tax as additional amount
        tax_amount = None
        if amount and isinstance(amount, (int, float)):
            # Calculate tax amount (11% of base amount)
            tax_rate = 0.11
            tax_amount = round(amount * tax_rate)  # 11% of pre-tax amount
        
        # Extract currency
        currency = extra_data.get('currency') if isinstance(extra_data, dict) else None
        
        # Only process entries with both transaction ID and amount
        if transaction_id and amount:
            # Get timestamp and format as date
            timestamp = activity.get('event_time')
            if timestamp:
                try:
                    # Handle ISO format timestamp (Facebook's format)
                    if isinstance(timestamp, str) and 'T' in timestamp:
                        # Parse ISO format date
                        dt = datetime.strptime(timestamp.split('+')[0], '%Y-%m-%dT%H:%M:%S')
                        event_date = dt.strftime('%Y-%m-%d')
                    elif isinstance(timestamp, (int, float)):
                        # Handle numeric timestamp
                        event_date = datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d')
                    else:
                        # Try general approach
                        event_date = timestamp.split('T')[0] if 'T' in timestamp else timestamp
                    
                    # Prepare account_id for invoice URL
                    account_id = account_info.get('id', '').replace('act_', '')
                    
                    transactions.append({
                        'account': account_name,
                        'transaction_id': transaction_id,
                        'date': event_date,
                        'amount': amount,  # Pre-tax amount from Meta
                        'tax_amount': tax_amount,  # Calculated tax amount (11%)
                        'currency': currency,
                        'card': '9816',  # Default based on your example
                        'event_type': activity.get('event_type'),
                        'account_id': account_id
                    })
                    print(f"Successfully extracted transaction: {transaction_id} - {event_date} - {amount} {currency} (Tax: {tax_amount})")
                except Exception as e:
                    print(f"Error processing date for activity: {str(e)}")
    
    return transactions

def save_to_sheets(sheet: gspread.Worksheet, transactions: List[Dict[str, Any]]):
    """Save transaction data to Google Sheets."""
    # Get existing transaction IDs to avoid duplicates
    existing_transaction_ids = sheet.col_values(2)[1:] if sheet.row_count > 1 else []
    
    count = 0
    for transaction in transactions:
        transaction_id = transaction.get('transaction_id', '')
        
        # Skip if this transaction ID is already in the sheet
        if transaction_id in existing_transaction_ids:
            print(f"Skipping duplicate transaction ID: {transaction_id}")
            continue
        
        # Get base amount and calculate tax
        base_amount = transaction.get('amount', 0)
        tax_amount = round(base_amount * 0.11)  # 11% tax
        total_amount = base_amount + tax_amount  # Total amount including tax
        
        # Get account_id from transaction data
        account_id = transaction.get('account_id', '')
        
        # Format invoice URL with proper account_id
        invoice_url = f"https://business.facebook.com/ads/manage/billing_transaction/?act={account_id}&pdf=true&print=false&source=billing_summary&tx_type=3&txid={transaction_id}"
            
        row = [
            transaction.get('account', ''),
            transaction_id,
            '',  # Faktur Pajak (empty as specified)
            transaction.get('date', ''),
            total_amount,  # Now includes tax
            tax_amount,  # Show tax amount in Plus Tax column
            transaction.get('card', '9816'),
            invoice_url
        ]
        
        sheet.append_row(row, value_input_option='USER_ENTERED')
        count += 1
        print(f"Added transaction {transaction_id} for {transaction.get('account')} on {transaction.get('date')} - Amount: {total_amount} (Base: {base_amount} + Tax: {tax_amount})")
    
    print(f"Total {count} new transactions added to Google Sheets")

def main():
    args = parse_arguments()
    env_vars = load_environment_variables()
    
    # Determine date range
    if args.start_date and args.end_date:
        if not (validate_date(args.start_date) and validate_date(args.end_date)):
            print("Invalid date format. Please use YYYY-MM-DD format.")
            return
        start_date, end_date = args.start_date, args.end_date
    else:
        start_date, end_date = get_date_range(args.last_days)
    
    print(f"Fetching transaction data from {start_date} to {end_date}")
    
    # Initialize Google Sheets
    sheet = initialize_google_sheets(env_vars['credentials_file'], env_vars['spreadsheet_name'])
    
    # Process each ad account
    for ad_account_id in env_vars['ad_account_ids']:
        account_info = test_api_connection(env_vars['access_token'], ad_account_id)
        if account_info:
            print(f"Fetching transaction data for account {ad_account_id}...")
            
            # Get activities containing transaction information
            activities = fetch_charge_activities(env_vars['access_token'], ad_account_id, start_date, end_date)
            print(f"Found {len(activities)} payment activities for account {ad_account_id}")
            
            # Process transaction data
            transactions = process_transaction_data(account_info, activities)
            print(f"Extracted {len(transactions)} transactions with IDs")
            
            # Save to Google Sheets
            if transactions:
                save_to_sheets(sheet, transactions)
            else:
                print(f"No transaction data found for account {ad_account_id} in the specified date range")

if __name__ == "__main__":
    main()