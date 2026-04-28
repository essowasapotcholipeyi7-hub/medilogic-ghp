import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'medilogic-secret-key-2024')
    GOOGLE_SHEETS_CREDENTIALS = 'credentials.json'
    SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1yLVp-zwjCFhYx5VZVZN1HXRRgYEyak8kiHHtwWpkLEE')
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'essowasainfo60@gmail.com')
    
    # Email configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME', '')