from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from config import Config
import os

db = SQLAlchemy()

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure bill output directory
    app.config['BILL_OUTPUT_DIR'] = os.path.join(os.getcwd(), 'bills')

    db.init_app(app)

    from app.routes import bp
    app.register_blueprint(bp)

    # Register the bill routes blueprint
    from app.bill_routes import bill_bp
    app.register_blueprint(bill_bp)

    return app