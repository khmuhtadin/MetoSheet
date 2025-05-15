# MetoSheet - Facebook Ads Data Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.7+](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)

> Seamlessly sync Facebook Ads performance data to Google Sheets with automated data fetching, multi-account support, and customizable date ranges.

![Project Banner](docs/assets/banner.png)

## 🚀 Features

- 📊 Automated Facebook Ads metrics collection
- 🔄 Daily Google Sheets synchronization
- 👥 Multi-account management
- 📅 Flexible date range selection
- 🌐 Timezone support (GMT+7)
- 📝 Comprehensive logging
- ⚠️ Robust error handling
- 💳 Automated billing transaction tracking
- 🧾 Indonesian VAT (11%) calculation
- 📃 Invoice URL generation
- 💰 Multi-currency support

## 📋 Prerequisites

Before you begin, ensure you have:

- Python 3.7 or higher
- Facebook Marketing API access
- Google Sheets API enabled
- Google Cloud Console project
- Basic understanding of Facebook Ads Manager

## 🛠️ Installation

1. Clone the repository:

```bash
git clone https://github.com/khmuhtadin/metosheet.git
cd metosheet
```

2. Set up a virtual environment (recommended):

```bash
python -m venv venv
source venv/bin/activate  # For Unix/macOS
```

3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Configure environment variables:

```bash
cp .env.example .env
```

5. Edit `.env` with your credentials:

```env
//Facebook API Credentials
META_ACCESS_TOKEN=your_facebook_access_token

//Facebook Ad Account IDs
ad_account1=act_123456789
ad_account2=act_123456789
ad_account3=act_123456789

//Google Sheets Configuration
spreadsheet_name_pub=your_google_spreadsheet_name
credentials_file=path_to_your_google_credentials.json
```

## 💻 Usage

### Basic Usage

```bash
# Fetch yesterday's data
python main.py

# Fetch specific date (use YYYY-MM-DD format)
python main.py --date 2024-01-15

# Fetch date range (use YYYY-MM-DD format)
python main.py --start-date 2024-01-01 --end-date 2024-01-15

# Fetch billing transactions
python billing.py --start-date 2024-01-01 --end-date 2024-01-31

# Fetch last 90 days of billing data
python billing.py --last-days 90

# Enable debug mode for detailed API responses
python billing.py --debug
```

### 🤖 Automated Daily Sync

This project includes GitHub Actions workflow for automated daily data synchronization. The sync runs every day at 08:00 GMT+7.

#### Setup Instructions

1. Fork this repository
2. Go to repository Settings > Secrets and variables > Actions
3. Add the following repository secrets:

   | Secret Name            | Description                      |
   | ---------------------- | -------------------------------- |
   | `META_ACCESS_TOKEN`    | Your Facebook API token          |
   | `AD_ACCOUNT1`          | First Facebook ad account ID     |
   | `AD_ACCOUNT2`          | Second Facebook ad account ID    |
   | `AD_ACCOUNT3`          | Third Facebook ad account ID     |
   | `SPREADSHEET_NAME_PUB` | Your Google Sheets name          |
   | `GOOGLE_CREDENTIALS`   | Your Google service account JSON |

#### Manual Trigger

You can manually trigger the sync anytime:

1. Go to your repository's Actions tab
2. Select "Daily Facebook Ads Sync"
3. Click "Run workflow"

The automation will run daily at 08:00 GMT+7 and can be manually triggered as needed.

## 📊 Data Structure

### Metrics Collected

| Metric        | Description                      |
| ------------- | -------------------------------- |
| Campaign Name | Name of the advertising campaign |
| Account Name  | Associated Facebook Ads account  |
| Impressions   | Number of times ads were viewed  |
| Spend         | Total amount spent               |
| CPM           | Cost per 1000 impressions        |
| Clicks        | Total number of clicks           |
| CPC           | Cost per click                   |
| CTR           | Click-through rate               |
| Reach         | Unique users reached             |

## 🤝 Contributing

We welcome contributions! Here's how you can help:

1. Fork the repository
2. Create a feature branch:

```bash
git checkout -b feature/AmazingFeature
```

3. Commit changes:

```bash
git commit -m 'Add AmazingFeature'
```

4. Push to your branch:

```bash
git push origin feature/AmazingFeature
```

5. Open a Pull Request

Please read our [Contributing Guidelines](CONTRIBUTING.md) for details.

## 🔒 Security

- Never commit sensitive credentials
- Use environment variables for secrets
- Regularly rotate API tokens

## 🐛 Known Issues

See [Issues](https://github.com/khmuhtadin/metosheet/issues) for a list of known issues and planned improvements.

## 📜 License

This project is licensed under the MIT License - see [LICENSE.md](LICENSE.md)

## 🙏 Acknowledgments

- [Facebook Marketing API](https://developers.facebook.com/docs/marketing-apis/)
- [Google Sheets API](https://developers.google.com/sheets/api)
- [gspread](https://github.com/burnash/gspread)

## 📬 Contact

Khairul Muhtadin

- Twitter: [@khmuhtadin](https://twitter.com/khmuhtadin)
- Email: hello@khmuhtadin.com
- Discord: khmuhtadin

⭐️ Star me on GitHub — it motivates a lot!

# Meta Ads Transaction Fetcher

This script fetches Meta (Facebook) Ads transaction data and stores it in a Google Sheet for easy tracking and reporting.

## Features

- Fetches transaction data from multiple Meta Ad accounts
- Extracts transaction details including transaction ID, date, amount, and card information
- Calculates tax amounts based on configurable tax rate
- Stores data in Google Sheets with duplicate prevention
- Handles API pagination and rate limiting
- Supports date range filtering via command-line arguments

## Requirements

- Python 3.7+
- Google API credentials for Google Sheets access
- Meta (Facebook) API access token with permissions to access Ad account data
- Environment variables configured in a `.env` file

## Installation

1. Clone this repository:

   ```
   git clone https://github.com/yourusername/meta-billing-fetcher.git
   cd meta-billing-fetcher
   ```

2. Install the required packages:

   ```
   pip install -r requirements.txt
   ```

3. Create a `.env` file with the following variables:

   ```
   # Meta API credentials
   META_ACCESS_TOKEN=your_meta_api_token_here

   # Google Sheets credentials
   credentials_file=path_to_google_sheets_credentials.json
   spreadsheet_name_pub="Your Google Spreadsheet Name"

   # Account IDs (add all accounts you want to track)
   otc=act_123456789
   rho=act_987654321
   # ... additional accounts as needed

   # Optional configuration
   TAX_RATE=0.11
   TIMEZONE_OFFSET=7
   API_TIMEOUT=15
   API_RETRIES=3
   ```

4. Set up Google Sheets API access:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Create a new project or select an existing one
   - Enable the Google Sheets API
   - Create a service account and download the JSON credentials file
   - Share your Google Sheet with the service account email address

## Usage

Basic usage:

```
python billing.py
```

This will fetch transaction data for the last 90 days for all configured accounts.

### Command-line options:

```
python billing.py --help
```

Output:

```
usage: billing.py [-h] [--start-date START_DATE] [--end-date END_DATE] [--last-days LAST_DAYS] [--debug]

Fetch Facebook Ads Transaction data

optional arguments:
  -h, --help            show this help message and exit
  --start-date START_DATE
                        Start date in YYYY-MM-DD format
  --end-date END_DATE   End date in YYYY-MM-DD format
  --last-days LAST_DAYS
                        Fetch data for the last N days (default: 90)
  --debug               Enable verbose debugging
```

Examples:

1. Fetch data for a specific date range:

   ```
   python billing.py --start-date 2024-01-01 --end-date 2024-01-31
   ```

2. Fetch data for the last 30 days with debug information:
   ```
   python billing.py --last-days 30 --debug
   ```

## Output

The script writes transaction data to a worksheet named "Meta Transaction IDs" in your specified Google Spreadsheet with the following columns:

- Account: Ad account name
- Transaction ID: Unique transaction identifier
- Faktur Pajak: (Empty column for manual tax invoice number entry)
- Date: Transaction date in YYYY-MM-DD format
- Amount: Original transaction amount
- With Tax: Amount including tax (calculated based on TAX_RATE)
- Card: Card number (last 4 digits)
- URL Invoice: Direct link to the invoice in Meta Business Manager

## Troubleshooting

- **Missing Data**: Meta API typically only provides recent data (90-180 days). For older data, download reports directly from Meta Business Manager.
- **API Errors**: Check your access token permissions and validity.
- **Rate Limiting**: The script includes automatic retry logic for rate limiting. If you consistently hit limits, try reducing the date range.
- **Google Sheets Errors**: Ensure the service account has edit access to the spreadsheet.

## License

This project is licensed under the MIT License - see the LICENSE file for details.
