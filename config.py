import os
from pathlib import Path

basedir = Path(__file__).parent

import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY') or 'dev-secret-key-change-in-production'
    # Local development: use database in project root
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or \
        'sqlite:///' + str(basedir / 'database' / 'commEnergy.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False