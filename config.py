import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'medilogic-secret-key-2024')
    ADMIN_EMAIL = os.getenv('ADMIN_EMAIL', 'essowasainfo60@gmail.com')
    DATABASE_URL = os.getenv('DATABASE_URL', 'postgresql://...')
    
    # ⭐ ENVIRONNEMENT
    # En local: development, En production: production
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    
    # ⭐ Configuration du webhook
    CONSULTATION_APP_URL = os.getenv('CONSULTATION_APP_URL', 'http://10.156.62.79:5000')
    WEBHOOK_SECRET = os.getenv('WEBHOOK_SECRET', 'mon_secret_webhook_123456')

    SPREADSHEET_ID = os.getenv('SPREADSHEET_ID', '1yLVp-zwjCFhYx5VZVZN1HXRRgYEyak8kiHHtwWpkLEE')

    @property
    def WEBHOOK_URL(self):
        return f"{self.CONSULTATION_APP_URL}/api/webhook/patient-created"
    
    @property
    def IS_DEVELOPMENT(self):
        return self.FLASK_ENV == 'development'
    
    @property
    def IS_PRODUCTION(self):
        return self.FLASK_ENV == 'production'
    
    # Email configuration
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'True') == 'True'
    MAIL_USERNAME = os.getenv('MAIL_USERNAME', '')
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD', '')
    MAIL_DEFAULT_SENDER = os.getenv('MAIL_USERNAME', '')