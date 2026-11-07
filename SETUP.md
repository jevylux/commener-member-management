# ComEner Data Management - Setup Guide

## Environment Configuration

This application uses environment variables to manage sensitive configuration data like passwords, API keys, and personal information.

### Quick Start

1. **Copy the example environment file:**
   ```bash
   cp .env.example .env
   ```

2. **Edit `.env` with your actual values:**
   ```bash
   nano .env
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application:**
   ```bash
   python run.py
   ```

## Required Environment Variables

### Flask Configuration
- `FLASK_SECRET_KEY`: Secret key for Flask sessions (generate a random string)

### SMTP Configuration
- `SMTP_SERVER`: SMTP server address (default: securemail.aplus.net)
- `SMTP_PORT`: SMTP port (default: 465)
- `SMTP_USER`: SMTP username/email
- `SMTP_PASSWORD`: SMTP password
- `FROM_EMAIL`: Email address for sending emails
- `FROM_NAME`: Display name for emails (default: Communauté Energétique)
- `BCC_EMAIL`: BCC email address for all outgoing emails

### Leneda API Configuration
- `LENEDA_API_KEY`: Your Leneda API key

### Payment Configuration
- `PAYCONIQ_NUMBER`: Your Payconiq/Wero number
- `BANK_ACCOUNT`: Your bank account details

## Security Notes

- **Never commit `.env` to version control** - it's already in `.gitignore`
- Use `.env.example` as a template for other developers
- Rotate credentials regularly
- Use strong, unique passwords for each service

## Generating a Secure Flask Secret Key

```python
import secrets
print(secrets.token_hex(32))
```

## Troubleshooting

### "Environment variable not set" errors
- Ensure `.env` file exists in the project root
- Check that all required variables are set in `.env`
- Verify `python-dotenv` is installed: `pip install python-dotenv`

### SMTP connection issues
- Verify SMTP credentials in `.env`
- Check firewall settings
- Ensure SMTP server and port are correct

### API authentication errors
- Verify `LENEDA_API_KEY` is correct
- Check API key permissions
- Ensure API key hasn't expired

## Development Setup

For development environments:

1. Use `.env.example` as a starting point
2. Set `FLASK_SECRET_KEY` to a development value
3. Use test credentials for external services when possible
4. Never use production credentials in development

## Production Deployment

For production:

1. Set environment variables through your hosting platform (not `.env` file)
2. Use strong, unique credentials
3. Enable additional security measures (HTTPS, rate limiting, etc.)
4. Regularly rotate credentials
5. Monitor for unauthorized access

## File Structure

```
ComEner-data-management/
├── .env                 # Your actual secrets (not in git)
├── .env.example         # Template for other developers
├── .gitignore           # Ensures .env is not committed
├── config.py            # Flask configuration
├── app/
│   ├── app.py           # Main application (loads env vars)
│   ├── leneda_access.py # Leneda API (loads env vars)
│   └── ...
└── SETUP.md            # This file
```

## Support

For setup issues, check:
1. Environment variables are correctly set
2. All dependencies are installed
3. Database file exists and is accessible
4. Network connectivity for external services
