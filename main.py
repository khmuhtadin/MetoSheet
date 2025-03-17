import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
import argparse

def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Fetch Facebook Ads data')
    parser.add_argument('--date', type=str, help='Custom date in YYYY-MM-DD format. If not provided, will use yesterday.')
    parser.add_argument('--start-date', type=str, help='Start date in YYYY-MM-DD format for date range')
    parser.add_argument('--end-date', type=str, help='End date in YYYY-MM-DD format for date range')
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
    return {
        'access_token': os.getenv('META_ACCESS_TOKEN'),
        'ad_account_ids': [os.getenv(acc) for acc in ['taff', 'otc', 'rho', 'biu', 'apx'] if os.getenv(acc)],
        'spreadsheet_name': os.getenv('spreadsheet_name_pub'),
        'credentials_file': os.getenv('credentials_file')
    }

def test_api_connection(access_token: str, ad_account_id: str) -> bool:
    """Test API connection for a given ad account."""
    url = f"https://graph.facebook.com/v21.0/{ad_account_id}"  # Updated to v21.0
    params = {'access_token': access_token, 'fields': 'account_id'}
    response = requests.get(url, params=params)
    if response.status_code == 200:
        print(f"API connection successful for account {ad_account_id}:", json.dumps(response.json(), indent=2))
        return True
    else:
        print(f"Failed to connect to API for account {ad_account_id}: {response.json()}")
        return False

def fetch_ads_performance_data(access_token: str, ad_account_id: str, date: str) -> List[Dict[str, Any]]:
    """Fetch ads performance data for a given ad account with pagination support."""
    base_url = f'https://graph.facebook.com/v21.0/{ad_account_id}/insights'  # Updated to v21.0
    params = {
        'access_token': access_token,
        'level': 'campaign',
        'time_range': json.dumps({
            'since': date,
            'until': date
        }),
        'fields': 'campaign_name,account_name,account_id,impressions,spend,cpm,clicks,cpc,ctr,reach',
        'limit': 1000
    }
    
    all_data = []
    next_url = base_url
    
    while next_url:
        try:
            response = requests.get(next_url, params=params)
            if response.ok:
                result = response.json()
                all_data.extend(result.get('data', []))
                
                next_url = result.get('paging', {}).get('next')
                params = {} if next_url else None
            else:
                print(f"Failed to fetch ads performance for account {ad_account_id}: {response.json()}")
                break
        except Exception as e:
            print(f"Error fetching data for account {ad_account_id}: {str(e)}")
            break
    
    return all_data

def get_yesterday_date() -> str:
    """Get yesterday's date in GMT+7 timezone."""
    current_datetime = datetime.utcnow() + timedelta(hours=7)
    return (current_datetime - timedelta(days=1)).strftime('%Y-%m-%d')

def get_date_range(start_date: str, end_date: str) -> List[str]:
    """Get a list of dates between start_date and end_date, inclusive."""
    start = datetime.strptime(start_date, '%Y-%m-%d')
    end = datetime.strptime(end_date, '%Y-%m-%d')
    date_range = []
    current = start
    while current <= end:
        date_range.append(current.strftime('%Y-%m-%d'))
        current += timedelta(days=1)
    return date_range

def initialize_google_sheets(credentials_file: str, spreadsheet_name: str) -> gspread.Worksheet:
    """Initialize and return Google Sheets worksheet."""
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    creds = ServiceAccountCredentials.from_json_keyfile_name(credentials_file, scope)
    client = gspread.authorize(creds)
    sheet = client.open(spreadsheet_name).worksheet('[wip] boost ads')
    
    if not sheet.row_values(1):
        header = ["Date", "Brand", "Campaign Name", "Account ID", "Account Name", "Impressions", "Spend", "CPM", "Clicks", "CPC", "CTR", "Reach"]
        sheet.append_row(header)
    
    return sheet

def process_data_item(data_item: Dict[str, Any], ad_account_id: str, date: str) -> List[Any]:
    """Process a single data item and return a row for Google Sheets."""
    campaign_name = data_item.get('campaign_name', 'Unknown Campaign')
    account_name = data_item.get('account_name', 'Unknown Account')
    
    if ad_account_id == os.getenv('taff'):
        brand = "TaffOmicron" if "omi - " in campaign_name else account_name
    else:
        brand = account_name
    
    return [
        date,
        brand,
        campaign_name,
        data_item.get('account_id', ''),
        account_name,
        int(data_item.get('impressions', 0)),
        float(data_item.get('spend', 0)),
        float(data_item.get('cpm', 0)),
        int(data_item.get('clicks', 0)),
        float(data_item.get('cpc', 0)),
        float(data_item.get('ctr', 0)),
        int(data_item.get('reach', 0))
    ]

def process_single_date(env_vars: Dict[str, Any], sheet: gspread.Worksheet, date: str):
    """Process data for a single date."""
    print(f"\nProcessing data for date: {date}")
    for ad_account_id in env_vars['ad_account_ids']:
        if test_api_connection(env_vars['access_token'], ad_account_id):
            print(f"Fetching data for account {ad_account_id}...")
            data = fetch_ads_performance_data(env_vars['access_token'], ad_account_id, date)
            print(f"Found {len(data)} campaigns for account {ad_account_id}")
            
            for data_item in data:
                row = process_data_item(data_item, ad_account_id, date)
                sheet.append_row(row, value_input_option='USER_ENTERED')
                print(f"Data successfully appended to Google Sheets for campaign {data_item.get('campaign_name', 'Unknown Campaign')}.")

def main():
    args = parse_arguments()
    env_vars = load_environment_variables()
    sheet = initialize_google_sheets(env_vars['credentials_file'], env_vars['spreadsheet_name'])

    if args.start_date and args.end_date:
        # Date range mode
        if not (validate_date(args.start_date) and validate_date(args.end_date)):
            print("Invalid date format. Please use YYYY-MM-DD format.")
            return
        dates = get_date_range(args.start_date, args.end_date)
        print(f"Processing date range from {args.start_date} to {args.end_date}")
        for date in dates:
            process_single_date(env_vars, sheet, date)
    elif args.date:
        # Single custom date mode
        if not validate_date(args.date):
            print("Invalid date format. Please use YYYY-MM-DD format.")
            return
        process_single_date(env_vars, sheet, args.date)
    else:
        # Default yesterday mode
        yesterday = get_yesterday_date()
        process_single_date(env_vars, sheet, yesterday)

if __name__ == "__main__":
    main()