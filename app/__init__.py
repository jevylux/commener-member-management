from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)
    app.config['BILL_OUTPUT_DIR'] = '/app/data/databills'
    db.init_app(app)

    # Note: Routes are defined directly in app.py
    # This factory function is kept for compatibility with run.py

    with app.app_context():
        print("\n=== Registered Routes ===")
        for rule in app.url_map.iter_rules():
            if 'bill' in rule.endpoint or 'bills' in str(rule):
                print(f"{rule.endpoint}: {rule}")
        print("========================\n")

    return app