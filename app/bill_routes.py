#!/usr/bin/env python3
"""
Bill Routes Module for ComEner Flask Application

Flask routes for bill generation, review, and email sending.
"""

from flask import Blueprint, render_template, request, jsonify, redirect, url_for, flash, current_app, send_from_directory
from sqlalchemy import text, func
from sqlalchemy.sql import bindparam
from datetime import datetime
import os
import sys
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import json

# Handle imports for both Docker and local development
try:
    # Try Docker-style imports first (when running from /app directory)
    from models import db, Member, Accounting, MemberFeePayment, MemberFee
    from bill_generator import BillGenerator
except ImportError:
    # Fall back to local development imports
    from app.models import db, Member, Accounting, MemberFeePayment, MemberFee
    from app.bill_generator import BillGenerator

# Create blueprint
bill_bp = Blueprint('bills', __name__)

# Email configuration
EMAIL_CONFIG = {
    'SMTP_SERVER': 'mail.aplus.net',
    'SMTP_PORT': 465,
    'SMTP_USER': 'mybot@durbach.com',
    'SMTP_PASSWORD': '7@CapPnp_cAwYvB1',  # Consider moving to environment variable
    'FROM_EMAIL': 'mybot@durbach.com',
    'FROM_NAME': 'Communauté Energétique'
}


def get_quarter_months(quarter):
    """Convert quarter to corresponding months."""
    quarter_months = {
        1: [1, 2, 3],
        2: [4, 5, 6],
        3: [7, 8, 9],
        4: [10, 11, 12]
    }
    return quarter_months.get(quarter, [])


def get_bill_folder_path(folder_name):
    """Get full path to a bill folder."""
    base_dir = current_app.config.get('BILL_OUTPUT_DIR', os.path.join(os.getcwd(), 'bills'))
    return os.path.join(base_dir, folder_name)


def get_status_file_path(folder_name):
    """Get path to the status JSON file for a bill folder."""
    folder_path = get_bill_folder_path(folder_name)
    return os.path.join(folder_path, '_email_status.json')


def load_email_status(folder_name):
    """Load email sending status from JSON file."""
    status_file = get_status_file_path(folder_name)
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_email_status(folder_name, status):
    """Save email sending status to JSON file."""
    status_file = get_status_file_path(folder_name)
    try:
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving email status: {e}")
        return False


def send_bill_email(member_email, member_name, bill_path, year, quarter, is_resend=False):
    """
    Send a bill via email to a member.
    
    Args:
        member_email: Recipient email address
        member_name: Member full name
        bill_path: Path to the PDF bill file
        year: Billing year
        quarter: Billing quarter
        is_resend: Whether this is a resend
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not member_email:
        return False, "No email address on file"
    
    try:
        # Create email message
        msg = MIMEMultipart()
        msg['From'] = f"{EMAIL_CONFIG['FROM_NAME']} <{EMAIL_CONFIG['FROM_EMAIL']}>"
        msg['To'] = member_email
        
        subject_prefix = "RESEND: " if is_resend else ""
        msg['Subject'] = f"{subject_prefix}Communauté Energétique - Bill Q{quarter}/{year}"
        
        # Email body in 3 languages
        body = f"""Dear {member_name},

Please find attached your bill for Quarter {quarter}, {year}.

If you have any questions, please contact us.

Best regards,
Communauté Energétique

---

Cher(e) {member_name},

Veuillez trouver ci-joint votre facture pour le Trimestre {quarter}, {year}.

En cas de questions, n'hésitez pas à nous contacter.

Cordialement,
Communauté Energétique

---

Léif {member_name},

Am Annex fannt Dir Är Rechnung fir d'Quartal {quarter}, {year}.

Bei Froen kontaktéiert eis w.e.g.

Mat beschte Gréiss,
Communauté Energétique
"""
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Attach PDF bill
        if os.path.exists(bill_path):
            filename = os.path.basename(bill_path)
            with open(bill_path, 'rb') as f:
                pdf_attachment = MIMEBase('application', 'pdf')
                pdf_attachment.set_payload(f.read())
                encoders.encode_base64(pdf_attachment)
                pdf_attachment.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(pdf_attachment)
        else:
            return False, f"Bill file not found: {bill_path}"
        
        # Send email
        ctx = ssl.create_default_context()
        
        with smtplib.SMTP_SSL(
            EMAIL_CONFIG['SMTP_SERVER'],
            EMAIL_CONFIG['SMTP_PORT'],
            context=ctx
        ) as server:
            server.login(EMAIL_CONFIG['SMTP_USER'], EMAIL_CONFIG['SMTP_PASSWORD'])
            server.sendmail(
                EMAIL_CONFIG['FROM_EMAIL'],
                member_email,
                msg.as_string()
            )
        
        return True, f"Email sent successfully to {member_email}"
        
    except Exception as e:
        return False, f"Error sending email: {str(e)}"


@bill_bp.route('/accounting/quarterly_report/bills', methods=['POST'])
def generate_quarterly_bills():
    """
    POST endpoint to generate bills from quarterly report data.
    Creates folder _bills_<year>-Q<quarter>.
    """
    try:
        # Get parameters from request
        year = request.form.get('year', type=int) or datetime.now().year
        quarter = request.form.get('quarter', type=int)
        
        if quarter not in [1, 2, 3, 4]:
            flash('Invalid quarter. Must be 1, 2, 3, or 4.', 'error')
            return redirect(url_for('main.create_quarterly_report'))
        
        # Get months for the quarter
        quarter_months = get_quarter_months(quarter)
        
        # Query to get quarterly data for all members with amounts
        query = text("""
        WITH accounting_totals AS (
            SELECT 
                accMember as member_id,
                SUM(accAmount) as accounting_total
            FROM accounting
            WHERE accYear = :year 
                AND accMonth IN :months
            GROUP BY accMember
        ),
        unpaid_fees AS (
            SELECT 
                mfp.memberID as member_id,
                mf.mfAmount as fee_amount
            FROM memberFeePayment mfp
            JOIN memberfee mf ON mfp.memberFeeID = mf.mfID
            WHERE (mfp.paymentStatus != 'paid' 
                OR mfp.paymentStatus IS NULL
                OR mfp.paymentDate IS NULL)
                AND mf.mfYear = :year
        )
        SELECT 
            COALESCE(a.member_id, uf.member_id) as member_id,
            m.name,
            m.firstname,
            m.email,
            m.address,
            COALESCE(a.accounting_total, 0) as accounting_total,
            COALESCE(uf.fee_amount, 0) as membership_fee,
            (COALESCE(a.accounting_total, 0) - COALESCE(uf.fee_amount, 0)) as total_amount
        FROM accounting_totals a
        FULL OUTER JOIN unpaid_fees uf ON a.member_id = uf.member_id
        LEFT JOIN members m ON COALESCE(a.member_id, uf.member_id) = m.id
        WHERE COALESCE(a.member_id, uf.member_id) IS NOT NULL
            AND (COALESCE(a.accounting_total, 0) - COALESCE(uf.fee_amount, 0)) != 0
        ORDER BY m.name, m.firstname
        """).bindparams(bindparam('months', expanding=True))
        
        # Execute query - get engine from current_app or import
        try:
            # Try to get engine from current_app config (Flask way)
            from sqlalchemy import create_engine
            engine = create_engine(current_app.config['SQLALCHEMY_DATABASE_URI'])
        except:
            # Fallback for local development
            try:
                from app import engine
            except ImportError:
                from __init__ import engine
        
        with engine.connect() as connection:
            result = connection.execute(query, {
                'year': year,
                'months': tuple(quarter_months)
            })
            
            member_data = []
            for row in result:
                member_data.append({
                    'member_id': row.member_id,
                    'name': row.name,
                    'firstname': row.firstname,
                    'email': row.email,
                    'address': row.address,
                    'accounting_total': float(row.accounting_total),
                    'membership_fee': float(row.membership_fee),
                    'total_amount': float(row.total_amount)
                })
        
        if not member_data:
            flash('No billing data found for this quarter.', 'warning')
            return redirect('/accounting/quarterly_report')
        
        # Generate bills
        output_dir = current_app.config.get('BILL_OUTPUT_DIR', os.path.join(os.getcwd(), 'bills'))
        generator = BillGenerator(output_dir=output_dir)
        
        result = generator.generate_bills_from_quarterly_data(
            year=year,
            quarter=quarter,
            member_data=member_data,
            db_session=db.session
        )
        
        # Initialize email status for all generated bills
        email_status = {}
        for bill in result['bills']:
            email_status[str(bill['member_id'])] = {
                'status': 'pending',
                'sent_at': None,
                'error': None,
                'attempts': 0
            }
        
        save_email_status(result['folder'], email_status)
        
        if result['errors']:
            flash(f"Generated {result['total_count']} bills with {result['error_count']} errors.", 'warning')
        else:
            flash(f"Successfully generated {result['total_count']} bills.", 'success')
        
        # Redirect to review page
        return redirect(f'/accounting/bills/{result["folder"]}/review')
        
    except Exception as e:
        import traceback
        flash(f'Error generating bills: {str(e)}', 'error')
        print(f"ERROR: {str(e)}")
        print(traceback.format_exc())
        return redirect('/accounting/quarterly_report')


@bill_bp.route('/accounting/bills/<folder>/review', methods=['GET'])
def review_bills(folder):
    """
    GET endpoint to show bills and their email status.
    """
    try:
        folder_path = get_bill_folder_path(folder)
        
        if not os.path.exists(folder_path):
            flash(f'Bill folder not found: {folder}', 'error')
            return redirect(url_for('main.create_quarterly_report'))
        
        # Parse year and quarter from folder name
        # Format: _bills_YYYY-QN
        folder_parts = folder.replace('_bills_', '').split('-')
        year = folder_parts[0] if len(folder_parts) > 0 else 'Unknown'
        quarter = folder_parts[1] if len(folder_parts) > 1 else 'Unknown'
        
        # Load email status
        email_status = load_email_status(folder)
        
        # Get all PDF files in the folder
        bills = []
        for filename in os.listdir(folder_path):
            if filename.endswith('.pdf') and not filename.startswith('_'):
                # Extract member info from filename
                # Format: Bill_YYYY_QN_Firstname_Name_ID.pdf
                parts = filename.replace('.pdf', '').split('_')
                
                # Find member_id (last numeric part before .pdf)
                member_id = None
                for part in reversed(parts):
                    if part.isdigit():
                        member_id = int(part)
                        break
                
                filepath = os.path.join(folder_path, filename)
                file_stat = os.stat(filepath)
                
                status_info = email_status.get(str(member_id), {
                    'status': 'pending',
                    'sent_at': None,
                    'error': None,
                    'attempts': 0
                })
                
                # Get member name from filename
                if len(parts) >= 4:
                    name_parts = parts[3:-1] if parts[-1].isdigit() else parts[3:]
                    member_name = ' '.join(name_parts).replace('_', ' ')
                else:
                    member_name = filename
                
                bills.append({
                    'filename': filename,
                    'member_id': member_id,
                    'member_name': member_name,
                    'size': f"{file_stat.st_size / 1024:.1f} KB",
                    'created': datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d %H:%M'),
                    'status': status_info.get('status', 'pending'),
                    'sent_at': status_info.get('sent_at'),
                    'error': status_info.get('error'),
                    'attempts': status_info.get('attempts', 0)
                })
        
        # Sort by member name
        bills.sort(key=lambda x: x['member_name'])
        
        # Calculate stats
        total_bills = len(bills)
        sent_bills = sum(1 for b in bills if b['status'] == 'sent')
        pending_bills = sum(1 for b in bills if b['status'] == 'pending')
        failed_bills = sum(1 for b in bills if b['status'] == 'failed')
        
        return render_template(
            'accounting/bill_review.html',
            folder=folder,
            year=year,
            quarter=quarter,
            bills=bills,
            total_bills=total_bills,
            sent_bills=sent_bills,
            pending_bills=pending_bills,
            failed_bills=failed_bills
        )
        
    except Exception as e:
        flash(f'Error loading bill review: {str(e)}', 'error')
        return redirect('/accounting/quarterly_report')


@bill_bp.route('/accounting/bills/<folder>/send', methods=['POST'])
def send_bills(folder):
    """
    POST endpoint to send bills via email.
    """
    try:
        folder_path = get_bill_folder_path(folder)
        
        if not os.path.exists(folder_path):
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        # Parse year and quarter from folder name
        folder_parts = folder.replace('_bills_', '').split('-')
        year = int(folder_parts[0]) if len(folder_parts) > 0 and folder_parts[0].isdigit() else datetime.now().year
        quarter_str = folder_parts[1] if len(folder_parts) > 1 else 'Q1'
        quarter = int(quarter_str.replace('Q', '')) if quarter_str.startswith('Q') else 1
        
        # Get selected bill IDs from request
        selected_ids = request.form.getlist('selected_bills', type=int)
        send_all = request.form.get('send_all', 'false') == 'true'
        
        # Load current email status
        email_status = load_email_status(folder)
        
        # Get bills to send
        bills_to_send = []
        for filename in os.listdir(folder_path):
            if filename.endswith('.pdf') and not filename.startswith('_'):
                # Extract member_id from filename
                parts = filename.replace('.pdf', '').split('_')
                member_id = None
                for part in reversed(parts):
                    if part.isdigit():
                        member_id = int(part)
                        break
                
                if member_id:
                    # Check if selected or sending all
                    if send_all or member_id in selected_ids:
                        # Get member info from database
                        member = Member.query.get(member_id)
                        if member:
                            bills_to_send.append({
                                'member_id': member_id,
                                'member_name': f"{member.firstname} {member.name}".strip(),
                                'member_email': member.email,
                                'filename': filename,
                                'filepath': os.path.join(folder_path, filename)
                            })
        
        # Send emails
        sent_count = 0
        failed_count = 0
        results = []
        
        for bill in bills_to_send:
            success, message = send_bill_email(
                member_email=bill['member_email'],
                member_name=bill['member_name'],
                bill_path=bill['filepath'],
                year=year,
                quarter=quarter
            )
            
            # Update status
            status_entry = email_status.get(str(bill['member_id']), {
                'status': 'pending',
                'sent_at': None,
                'error': None,
                'attempts': 0
            })
            
            status_entry['attempts'] = status_entry.get('attempts', 0) + 1
            
            if success:
                status_entry['status'] = 'sent'
                status_entry['sent_at'] = datetime.now().isoformat()
                status_entry['error'] = None
                sent_count += 1
            else:
                status_entry['status'] = 'failed'
                status_entry['error'] = message
                failed_count += 1
            
            email_status[str(bill['member_id'])] = status_entry
            
            results.append({
                'member_id': bill['member_id'],
                'member_name': bill['member_name'],
                'success': success,
                'message': message
            })
        
        # Save updated status
        save_email_status(folder, email_status)
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'results': results
            })
        else:
            if sent_count > 0:
                flash(f'Successfully sent {sent_count} bills.', 'success')
            if failed_count > 0:
                flash(f'Failed to send {failed_count} bills.', 'warning')
            return redirect(url_for('bills.review_bills', folder=folder))
        
    except Exception as e:
        error_msg = f'Error sending bills: {str(e)}'
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': error_msg}), 500
        else:
            flash(error_msg, 'error')
            return redirect(url_for('bills.review_bills', folder=folder))


@bill_bp.route('/accounting/bills/<folder>/status', methods=['GET'])
def get_bill_status(folder):
    """
    GET endpoint to check email status.
    Returns JSON with current status for all bills in the folder.
    """
    try:
        email_status = load_email_status(folder)
        
        # Calculate summary
        total = len(email_status)
        sent = sum(1 for s in email_status.values() if s.get('status') == 'sent')
        pending = sum(1 for s in email_status.values() if s.get('status') == 'pending')
        failed = sum(1 for s in email_status.values() if s.get('status') == 'failed')
        
        return jsonify({
            'success': True,
            'folder': folder,
            'summary': {
                'total': total,
                'sent': sent,
                'pending': pending,
                'failed': failed
            },
            'status': email_status
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bill_bp.route('/accounting/bills/<folder>/resend', methods=['POST'])
def resend_bill(folder):
    """
    POST endpoint to resend bills to specific members.
    """
    try:
        folder_path = get_bill_folder_path(folder)
        
        if not os.path.exists(folder_path):
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        # Parse year and quarter from folder name
        folder_parts = folder.replace('_bills_', '').split('-')
        year = int(folder_parts[0]) if len(folder_parts) > 0 and folder_parts[0].isdigit() else datetime.now().year
        quarter_str = folder_parts[1] if len(folder_parts) > 1 else 'Q1'
        quarter = int(quarter_str.replace('Q', '')) if quarter_str.startswith('Q') else 1
        
        # Get member IDs to resend
        member_ids = request.json.get('member_ids', []) if request.is_json else request.form.getlist('member_ids', type=int)
        
        if not member_ids:
            return jsonify({'success': False, 'error': 'No member IDs provided'}), 400
        
        # Load email status
        email_status = load_email_status(folder)
        
        results = []
        sent_count = 0
        failed_count = 0
        
        for member_id in member_ids:
            # Find bill file for this member
            bill_file = None
            for filename in os.listdir(folder_path):
                if filename.endswith('.pdf') and filename.endswith(f'_{member_id}.pdf'):
                    bill_file = filename
                    break
            
            if not bill_file:
                results.append({
                    'member_id': member_id,
                    'success': False,
                    'message': 'Bill file not found'
                })
                failed_count += 1
                continue
            
            # Get member info
            member = Member.query.get(member_id)
            if not member:
                results.append({
                    'member_id': member_id,
                    'success': False,
                    'message': 'Member not found'
                })
                failed_count += 1
                continue
            
            # Send email
            bill_path = os.path.join(folder_path, bill_file)
            success, message = send_bill_email(
                member_email=member.email,
                member_name=f"{member.firstname} {member.name}".strip(),
                bill_path=bill_path,
                year=year,
                quarter=quarter,
                is_resend=True
            )
            
            # Update status
            status_entry = email_status.get(str(member_id), {
                'status': 'pending',
                'sent_at': None,
                'error': None,
                'attempts': 0
            })
            
            status_entry['attempts'] = status_entry.get('attempts', 0) + 1
            
            if success:
                status_entry['status'] = 'sent'
                status_entry['sent_at'] = datetime.now().isoformat()
                status_entry['error'] = None
                sent_count += 1
            else:
                status_entry['status'] = 'failed'
                status_entry['error'] = message
                failed_count += 1
            
            email_status[str(member_id)] = status_entry
            
            results.append({
                'member_id': member_id,
                'member_name': f"{member.firstname} {member.name}".strip(),
                'success': success,
                'message': message
            })
        
        # Save updated status
        save_email_status(folder, email_status)
        
        return jsonify({
            'success': True,
            'sent_count': sent_count,
            'failed_count': failed_count,
            'results': results
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@bill_bp.route('/accounting/bills/<folder>/download/<filename>')
def download_bill(folder, filename):
    """
    Download a specific bill PDF.
    """
    folder_path = get_bill_folder_path(folder)
    
    if not os.path.exists(os.path.join(folder_path, filename)):
        flash('Bill file not found.', 'error')
        return redirect(url_for('bills.review_bills', folder=folder))
    
    return send_from_directory(folder_path, filename, as_attachment=True)


@bill_bp.route('/accounting/bills/list')
def list_bill_folders():
    """
    List all generated bill folders.
    """
    try:
        base_dir = current_app.config.get('BILL_OUTPUT_DIR', os.path.join(os.getcwd(), 'bills'))
        
        folders = []
        if os.path.exists(base_dir):
            for folder_name in os.listdir(base_dir):
                folder_path = os.path.join(base_dir, folder_name)
                if os.path.isdir(folder_path) and folder_name.startswith('_bills_'):
                    # Parse year and quarter
                    parts = folder_name.replace('_bills_', '').split('-')
                    year = parts[0] if len(parts) > 0 else 'Unknown'
                    quarter = parts[1] if len(parts) > 1 else 'Unknown'
                    
                    # Count bills
                    bill_count = len([f for f in os.listdir(folder_path) if f.endswith('.pdf') and not f.startswith('_')])
                    
                    # Load status
                    email_status = load_email_status(folder_name)
                    sent_count = sum(1 for s in email_status.values() if s.get('status') == 'sent')
                    
                    folders.append({
                        'folder': folder_name,
                        'year': year,
                        'quarter': quarter,
                        'bill_count': bill_count,
                        'sent_count': sent_count,
                        'created': datetime.fromtimestamp(os.stat(folder_path).st_ctime).strftime('%Y-%m-%d %H:%M')
                    })
        
        # Sort by creation date (newest first)
        folders.sort(key=lambda x: x['created'], reverse=True)
        
        return render_template('accounting/bill_list.html', folders=folders)
        
    except Exception as e:
        flash(f'Error listing bills: {str(e)}', 'error')
        return redirect('/')
