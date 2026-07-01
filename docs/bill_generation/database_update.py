#!/usr/bin/env python3
"""
Database Migration Script for BillEmail Table

Adds a BillEmail table to track sent bills via email.
This uses SQLAlchemy for database migration.
"""

import sys
import os
from datetime import datetime

# Add the app directory to path for importing models
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


def create_migration_script():
    """
    Create the migration script content that can be used with Flask-Migrate or Alembic.
    """
    migration_content = '''"""
Revision ID: add_bill_email_table
Revises: 
Create Date: {create_date}

Add BillEmail table for tracking bill emails.
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = 'add_bill_email_table'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """Create BillEmail table."""
    op.create_table(
        'bill_email',
        sa.Column('beID', sa.Integer(), nullable=False),
        sa.Column('beMemberID', sa.Integer(), nullable=False),
        sa.Column('beYear', sa.Integer(), nullable=False),
        sa.Column('beQuarter', sa.Integer(), nullable=False),
        sa.Column('beFilename', sa.String(length=255), nullable=False),
        sa.Column('beSentDate', sa.DateTime(), nullable=True),
        sa.Column('beEmailTo', sa.String(length=255), nullable=True),
        sa.Column('beStatus', sa.String(length=20), nullable=False, server_default='pending'),
        sa.Column('beErrorMessage', sa.Text(), nullable=True),
        sa.Column('beResendCount', sa.Integer(), nullable=False, server_default='0'),
        sa.ForeignKeyConstraint(['beMemberID'], ['members.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('beID')
    )
    
    # Create indexes for common queries
    op.create_index('ix_bill_email_member', 'bill_email', ['beMemberID'])
    op.create_index('ix_bill_email_year_quarter', 'bill_email', ['beYear', 'beQuarter'])
    op.create_index('ix_bill_email_status', 'bill_email', ['beStatus'])


def downgrade():
    """Drop BillEmail table."""
    op.drop_index('ix_bill_email_status', table_name='bill_email')
    op.drop_index('ix_bill_email_year_quarter', table_name='bill_email')
    op.drop_index('ix_bill_email_member', table_name='bill_email')
    op.drop_table('bill_email')
'''
    
    return migration_content.format(create_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f'))


def create_manual_migration_script():
    """
    Create a manual SQL migration script for databases without Alembic.
    """
    sql_content = """-- Migration: Add BillEmail table
-- Created: {create_date}

-- Create BillEmail table
CREATE TABLE IF NOT EXISTS bill_email (
    beID INTEGER PRIMARY KEY AUTOINCREMENT,
    beMemberID INTEGER NOT NULL,
    beYear INTEGER NOT NULL,
    beQuarter INTEGER NOT NULL,
    beFilename VARCHAR(255) NOT NULL,
    beSentDate DATETIME,
    beEmailTo VARCHAR(255),
    beStatus VARCHAR(20) NOT NULL DEFAULT 'pending',
    beErrorMessage TEXT,
    beResendCount INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (beMemberID) REFERENCES members (id) ON DELETE CASCADE
);

-- Create indexes for performance
CREATE INDEX IF NOT EXISTS ix_bill_email_member ON bill_email (beMemberID);
CREATE INDEX IF NOT EXISTS ix_bill_email_year_quarter ON bill_email (beYear, beQuarter);
CREATE INDEX IF NOT EXISTS ix_bill_email_status ON bill_email (beStatus);

-- Downgrade (uncomment to rollback)
-- DROP INDEX IF EXISTS ix_bill_email_status;
-- DROP INDEX IF EXISTS ix_bill_email_year_quarter;
-- DROP INDEX IF EXISTS ix_bill_email_member;
-- DROP TABLE IF EXISTS bill_email;
""".format(create_date=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    
    return sql_content


def create_model_code():
    """
    Create the Python model code to add to app/models.py
    """
    model_code = '''

class BillEmail(db.Model):
    """
    BillEmail model for tracking bill emails sent to members.
    
    Tracks the status of email sending for each bill, including:
    - When the bill was generated
    - When it was sent
    - The recipient email address
    - Success/failure status
    - Error messages for debugging
    - Resend count
    """
    __tablename__ = 'bill_email'
    
    beID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    beMemberID = db.Column(db.Integer, db.ForeignKey('members.id', ondelete='CASCADE'), nullable=False)
    beYear = db.Column(db.Integer, nullable=False)
    beQuarter = db.Column(db.Integer, nullable=False)
    beFilename = db.Column(db.String(255), nullable=False)
    beSentDate = db.Column(db.DateTime, nullable=True)
    beEmailTo = db.Column(db.String(255), nullable=True)
    beStatus = db.Column(db.String(20), nullable=False, default='pending')
    beErrorMessage = db.Column(db.Text, nullable=True)
    beResendCount = db.Column(db.Integer, nullable=False, default=0)
    
    # Relationship to Member
    member = db.relationship('Member', backref='bill_emails', lazy=True)
    
    __table_args__ = (
        db.Index('ix_bill_email_member', 'beMemberID'),
        db.Index('ix_bill_email_year_quarter', 'beYear', 'beQuarter'),
        db.Index('ix_bill_email_status', 'beStatus'),
    )
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.beStatus not in ('pending', 'sent', 'failed'):
            raise ValueError("beStatus must be 'pending', 'sent', or 'failed'")
    
    def __repr__(self):
        return f'<BillEmail {self.beYear}-Q{self.beQuarter} Member:{self.beMemberID} Status:{self.beStatus}>'
    
    def mark_as_sent(self, email_to):
        """Mark this bill as successfully sent."""
        self.beStatus = 'sent'
        self.beSentDate = datetime.now()
        self.beEmailTo = email_to
        self.beErrorMessage = None
    
    def mark_as_failed(self, error_message):
        """Mark this bill as failed to send."""
        self.beStatus = 'failed'
        self.beErrorMessage = error_message
    
    def increment_resend(self):
        """Increment the resend counter."""
        self.beResendCount = (self.beResendCount or 0) + 1
    
    def to_dict(self):
        """Convert to dictionary for API responses."""
        return {
            'id': self.beID,
            'member_id': self.beMemberID,
            'year': self.beYear,
            'quarter': self.beQuarter,
            'filename': self.beFilename,
            'sent_date': self.beSentDate.isoformat() if self.beSentDate else None,
            'email_to': self.beEmailTo,
            'status': self.beStatus,
            'error_message': self.beErrorMessage,
            'resend_count': self.beResendCount
        }


# Add relationship to Member model (add this to the Member class in models.py)
# bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
'''
    
    return model_code


def apply_migration_directly(db_path=None):
    """
    Apply the migration directly using SQLAlchemy.
    This is a helper for development/testing.
    """
    import sqlite3
    
    if db_path is None:
        # Default path from app config
        db_path = '/Users/marcdurbach/Development/python/ComEner-data-management/database/commEnergy.db'
    
    sql = create_manual_migration_script()
    
    # Extract just the CREATE statements (remove comments and downgrade section)
    lines = sql.split('\n')
    create_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('--') or stripped.startswith('/*'):
            continue
        if 'Downgrade' in line:
            break
        create_lines.append(line)
    
    create_sql = '\n'.join(create_lines)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Execute the SQL
        cursor.executescript(create_sql)
        conn.commit()
        
        print(f"✅ Migration applied successfully to {db_path}")
        print("   Created table: bill_email")
        print("   Created indexes: ix_bill_email_member, ix_bill_email_year_quarter, ix_bill_email_status")
        
    except sqlite3.Error as e:
        print(f"❌ Error applying migration: {e}")
        return False
    finally:
        if conn:
            conn.close()
    
    return True


def save_migration_files(output_dir=None):
    """
    Save migration files to the specified directory.
    """
    if output_dir is None:
        output_dir = os.getcwd()
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save Alembic-style migration
    alembic_file = os.path.join(output_dir, 'migration_add_bill_email.py')
    with open(alembic_file, 'w') as f:
        f.write(create_migration_script())
    print(f"✅ Saved: {alembic_file}")
    
    # Save manual SQL migration
    sql_file = os.path.join(output_dir, 'migration_add_bill_email.sql')
    with open(sql_file, 'w') as f:
        f.write(create_manual_migration_script())
    print(f"✅ Saved: {sql_file}")
    
    # Save model code
    model_file = os.path.join(output_dir, 'bill_email_model.py')
    with open(model_file, 'w') as f:
        f.write(create_model_code())
    print(f"✅ Saved: {model_file}")
    
    return alembic_file, sql_file, model_file


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Database migration for BillEmail table')
    parser.add_argument('--save-files', action='store_true', 
                       help='Save migration files to current directory')
    parser.add_argument('--apply', action='store_true',
                       help='Apply migration directly to database')
    parser.add_argument('--db-path', type=str, default=None,
                       help='Path to SQLite database (for --apply)')
    
    args = parser.parse_args()
    
    if args.save_files:
        save_migration_files()
    elif args.apply:
        apply_migration_directly(args.db_path)
    else:
        # Print model code to stdout
        print("=" * 60)
        print("BILL EMAIL MODEL CODE (Add this to app/models.py):")
        print("=" * 60)
        print(create_model_code())
        print("\n")
        print("=" * 60)
        print("MANUAL SQL MIGRATION (Run this on your database):")
        print("=" * 60)
        print(create_manual_migration_script())
        print("\n")
        print("To save files: python database_update.py --save-files")
        print("To apply directly: python database_update.py --apply --db-path /path/to/db.sqlite")
