# MetoSheet - Facebook Ads Data Automation

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

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

This project includes GitHub Actions workflow for automated daily data synchronization.

#### Schedule

- **Daily Run**: Every day at **10:00 AM WIB** (3:00 AM UTC)
- **Data Fetched**: Yesterday's ads performance data
- **Destination**: Automatically written to Google Sheets and sent to webhook (if configured)

#### Quick Setup

1. Fork/clone this repository
2. Go to repository `Settings` → `Secrets and variables` → `Actions`
3. Add the required repository secrets (see table below)
4. The workflow will run automatically every day at 10 AM WIB

📖 **Full documentation**: See [`.github/README.md`](.github/README.md) for detailed setup instructions, troubleshooting, and security best practices.

#### Manual Trigger

You can manually trigger the sync anytime:

1. Go to your repository's `Actions` tab
2. Select **"Daily Ads Report"** workflow
3. Click `Run workflow` → Choose branch → `Run workflow`

The automation will run daily at 10:00 AM WIB and can be manually triggered as needed.

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

This repository is designed to be safely used as a **public repository** while keeping your credentials secure.

### Key Security Features

- ✅ **No credentials in code** - All secrets use environment variables or GitHub Secrets
- ✅ **Protected git history** - No credentials have ever been committed
- ✅ **Secure CI/CD** - GitHub Actions use encrypted secrets
- ✅ **Automated checks** - Security audit script included

### Security Documentation
- 🔐 [.github/README.md](./.github/README.md) - GitHub Secrets setup guide

### Best Practices

- Never commit `.env` or `crex.json` files
- Use GitHub Secrets for CI/CD credentials
- Rotate Meta API tokens every 60-90 days
- Review pull requests carefully for security issues
- Enable Dependabot and security alerts

**🔴 Report Security Issues**: If you discover a security vulnerability, please email [your-email@example.com] instead of opening a public issue.

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

- Threads: [@khmuhtadin](https://threads.com/@khmuhtadin)
- Email: contact@khmuhtadin.com
- Discord: khmuhtadin

⭐️ Star me on GitHub — it motivates a lot!
