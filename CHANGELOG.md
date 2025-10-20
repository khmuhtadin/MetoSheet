# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Security documentation and tooling**:
  - `SECURITY.md` - Comprehensive security policy and incident response guide
  - `GOING-PUBLIC.md` - Step-by-step guide for safely making repository public
  - `check-security.sh` - Automated security audit script
  - Enhanced `.gitignore` with comprehensive sensitive file patterns
  - Pre-public checklist and verification procedures
- **GitHub Actions automation**: Daily scheduled workflow to fetch yesterday's ads data automatically
  - Runs every day at 10:00 AM WIB (3:00 AM UTC)
  - Manual trigger support via workflow_dispatch
  - Secure credential management using GitHub Secrets
  - Complete setup documentation in `.github/README.md`
  - Automatic credential cleanup after workflow runs
- **Webhook integration**: Automatically send data to webhook endpoint after successful Google Sheets write
  - Webhook URL configuration via environment variable `WEBHOOK_URL` (optional, no default value for security)
  - Non-blocking webhook calls with timeout handling (10 seconds)
- API connection caching: Test all accounts once at startup instead of per-date
- Progress indicator for date range processing (e.g., `[1/19] Processing 2025-10-01`)
- Connection test summary with visual indicators (✅/❌)
- Clear reporting of failed accounts with account IDs

### Changed
- **BREAKING**: Updated Meta API version from v22.0 to v24.0
- Optimized batch writing to Google Sheets: Write all rows per date at once instead of individual row writes
- Improved logging: Cleaner output with focus on important information
- Enhanced error messages: More concise and actionable

### Fixed
- Fixed indentation errors in `test_api_connection()` function
- Fixed indentation errors in `initialize_google_sheets()` function
- Removed redundant API connection testing in date processing loop

### Performance
- Reduced API calls by ~27% (114 → 6 connection tests for 19-day range)
- Improved Google Sheets write performance by 15-20x through batch operations
- Script execution time reduced from >5 minutes to <1 minute for 19-day date ranges

## [1.0.0] - 2025-01-XX

### Added
- Initial release
- Meta Ads data fetching from Facebook Graph API
- Google Sheets integration for data storage
- Support for multiple ad accounts (taff, otc, rho, biu, apx, sunbuck)
- Date range support with `--start-date` and `--end-date` flags
- Single date support with `--date` flag
- Default mode: Fetch yesterday's data (GMT+7 timezone)
- Campaign-level insights with metrics: impressions, spend, CPM, clicks, CPC, CTR, reach
- Brand-specific logic for TaffOmicron campaigns
- Pagination support for large datasets
- Environment variable validation
- Google Sheets worksheet auto-creation
