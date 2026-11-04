
from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, send_file, Response, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import create_engine, text, bindparam
from flask_wtf import FlaskForm
from sqlalchemy import update, func
from wtforms import StringField, SelectField, FloatField, IntegerField, TextAreaField, DateField
from wtforms.validators import DataRequired, Email, AnyOf, Optional
from models import db, Member, Pod, SharingGroup, PodSharingGroup, MemberFee, MemberFeePayment, Accounting, AccountingQuarterly
from sorting import (
    ASC,
    DESC,
    normalise,
    parse_sort,
    sort_rows,
    sort_target,
    sort_indicator,
)
from datetime import date, datetime, time
from config_generator import ConfigGenerator
import time
from pathlib import Path
from leneda_access import (
    get_all_obis_codes,
    get_obis_codes_for_pod_type,
    get_member_pods_from_db,
    get_member_info_from_db,
    request_access_for_member
)
import os
import io
import csv
import json
import smtplib
import ssl
import zipfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders

# ==============================================================================
# EMAIL CONFIGURATION - Unified for all email sending
# ==============================================================================
EMAIL_CONFIG = {
    'SMTP_SERVER': 'securemail.aplus.net',
    'SMTP_PORT': 465,
    'SMTP_USER': 'marc@durbach.com',
    'SMTP_PASSWORD': 'XJ!s9TeQZ32BcPQu@k',
    'FROM_EMAIL': 'marc@durbach.com',
    'FROM_NAME': 'Communauté Energétique',
    'BCC_EMAIL': 'stroumdeelen@durbach.com'  # BCC all emails to this address
}
PAYMENT_CONFIG = {
    'PAYCONIQ_Number': '661196114',
    'BankAccount': 'IBAN : LU12 0019 1303 5350 3000  - BIC : BCEELULL - Marc Durbach',
}


def append_line(file_path: str, line: str) -> None:
    """
    Append a line of text to a file. Creates the file if it does not exist.
    """
    path = Path(file_path)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def send_bill_email(member_email, member_name, bill_path, year, quarter, is_resend=False, test_mode=False):
    """
    Send a bill via email to a member.
    
    Args:
        member_email: Recipient email address
        member_name: Member full name
        bill_path: Path to the CSV/PDF bill file
        year: Billing year
        quarter: Billing quarter
        is_resend: Whether this is a resend
        test_mode: If True, email only goes to BCC with TEST markers
        
    Returns:
        Tuple of (success: bool, message: str)
    """
    if not member_email:
        return False, "No email address on file"
    
    try:
        transfert = ""
        # Create email message
        msg = MIMEMultipart()
        # Use plain email address to avoid SMTP rejection
        msg['From'] = EMAIL_CONFIG['FROM_EMAIL']
        
        # In test mode, only send to BCC (real recipient gets email suppressed)
        if test_mode:
            # In test mode, don't set To header to real recipient
            # Only BCC will receive it
            if EMAIL_CONFIG.get('BCC_EMAIL'):
                msg['To'] = EMAIL_CONFIG['BCC_EMAIL']  # Send to BCC address as To
                print(f"DEBUG: Test mode active. Email will be sent to BCC only: {EMAIL_CONFIG['BCC_EMAIL']}")
            else:
                return False, "No BCC email configured for test mode"
        else:
            msg['To'] = member_email
        
        # Add BCC if configured
        if EMAIL_CONFIG.get('BCC_EMAIL'):
            msg['Bcc'] = EMAIL_CONFIG['BCC_EMAIL']
        
        subject_prefix = "RESEND: " if is_resend else ""
        test_prefix = "TEST RUN - Users did not receive this email - " if test_mode else ""
        msg['Subject'] = f"{test_prefix}{subject_prefix}Communauté Energétique - Bill Q{quarter}/{year}"
        
        # Parse bill CSV to get amount and determine direction
        bill_amount = None
        try:
            import csv
            with open(bill_path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f, delimiter=';')
                for row in reader:
                    if 'Amount' in row:
                        try:
                            bill_amount = float(row['Amount'].replace(',', '.'))
                            break
                        except:
                            pass
        except Exception as e:
            print(f"DEBUG: Could not parse bill amount: {e}")
        
        # Determine direction based on amount
        if bill_amount is not None:
            if bill_amount > 0:
                # Member receives money (credit)
                amount_str = f"{abs(bill_amount):.2f}"
                direction_en = f"You will receive a credit of {amount_str}€"
                direction_fr = f"Vous recevrez un crédit de {amount_str}€"
                direction_lu = f"Dir kritt e Montant vun {amount_str}€"
                transfert = "Receive"
            else:
                # Member pays money (debit)
                #amount_str = f"{bill_amount:.2f}"
                amount_str = f"{abs(bill_amount):.2f}"
                direction_en = f"You have to pay: {amount_str}€"
                direction_fr = f"Montant à payer: {amount_str}€"
                direction_lu = f"Dir hut ze bezuelen: {amount_str}€"
                transfert = "Pay"
        else:
            direction_en = "Please see attached statement for details"
            direction_fr = "Veuillez consulter le décompte joint pour les détails"
            direction_lu = "Kuckt w.e.g. d'ugehängten Offrechnung fir Detailer"
        
        # Get member payment info from database
        member_payment_info = ""
        try:
            # Extract last name from member_name (format: "Firstname Lastname")
            name_parts = member_name.strip().split()
            if len(name_parts) >= 2:
                last_name = name_parts[-1]
                first_name = ' '.join(name_parts[:-1])
            else:
                last_name = member_name
                first_name = ""
            
            member = Member.query.filter(
                db.and_(
                    db.func.lower(Member.name) == db.func.lower(last_name),
                    db.func.lower(Member.firstname) == db.func.lower(first_name)
                )
            ).first()
            
            if not member:
                # Try matching by last name only
                member = Member.query.filter(
                    db.func.lower(Member.name) == db.func.lower(last_name)
                ).first()
            
            if member:
                payment_method = member.payment or 'Not specified'
                if payment_method == 'Payconiq':
                    payconiq_num = member.Payconiq or 'Not provided'
                    if transfert == "Receive":
                        member_payment_info = f"Payment Method: Wero ({payconiq_num})"
                    else:
                        member_payment_info = f" Wero -> {PAYMENT_CONFIG['PAYCONIQ_Number']}"
                elif payment_method == 'Bank':
                    bank_acc = member.BankAccount or 'Not provided'
                    if transfert == "Receive":
                        member_payment_info = f"Payment Method: Bank Transfer ({bank_acc})"
                    else:
                        member_payment_info = f"Bank Transfer -> {PAYMENT_CONFIG['BankAccount']}"
                else:
                    member_payment_info = f" Wero -> {PAYMENT_CONFIG['PAYCONIQ_Number']}"
            else:
                member_payment_info = "Payment Method: Not found in database"
        except Exception as e:
            print(f"DEBUG: Could not get member payment info: {e}")
            member_payment_info = "Payment Method: Error retrieving"
        
        # Add test mode notice if applicable
        test_notice = ""
        if test_mode:
            test_notice = f"""
============================================================
TEST RUN - Users did not receive this email
This is a test email. The actual recipient did not receive this message.
Intended recipient: {member_name} <{member_email}>
Only you (BCC) are receiving this copy.
============================================================

"""
        
        # Email body in 3 languages with payment info
        body = f"""{test_notice}Dear {member_name},

Please find attached your statement for Quarter {quarter}, {year}.

{direction_en}

{member_payment_info}

If you have any questions, please contact us.

Best regards,
Communauté Energétique

---

{test_notice}Cher(e) {member_name},

Veuillez trouver ci-joint votre décompte pour le Trimestre {quarter}, {year}.

{direction_fr}

{member_payment_info}

En cas de questions, n'hésitez pas à nous contacter.

Cordialement,
Communauté Energétique

---

{test_notice} {member_name},

An der Annex fannt Dir Är Offrechnung fir d'Quartal {quarter}, {year}.

{direction_lu}

{member_payment_info}

Bei Froen kontaktéiert eis w.e.g.

Mat beschte Gréiss,
Communauté Energétique
"""
        
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        
        # Attach bill file
        if os.path.exists(bill_path):
            filename = os.path.basename(bill_path)
            with open(bill_path, 'rb') as f:
                attachment = MIMEBase('application', 'octet-stream')
                attachment.set_payload(f.read())
                encoders.encode_base64(attachment)
                attachment.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(attachment)
        else:
            return False, f"Bill file not found: {bill_path}"
        
        print(f"DEBUG : Trying to send email to {member_email} from {EMAIL_CONFIG['FROM_EMAIL']} with subject {msg['Subject']} ")
        print(f"DEBUG : Bill file: {bill_path}/{filename}")
        print(f"DEBUG : Account: {EMAIL_CONFIG['SMTP_USER']} - {EMAIL_CONFIG['SMTP_PASSWORD']}")
        # Send email
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT'], context=ctx) as server:
            print(f"DEBUG : Connected to server {EMAIL_CONFIG['SMTP_SERVER']} on port {EMAIL_CONFIG['SMTP_PORT']}")
            server.login(EMAIL_CONFIG['SMTP_USER'], EMAIL_CONFIG['SMTP_PASSWORD'])
            print(f"DEBUG : Logged in as {EMAIL_CONFIG['SMTP_USER']}")
            print(f"DEBUG : Trying to send email from {EMAIL_CONFIG['FROM_EMAIL']} to {member_email} with subject {msg['Subject']}")
            print(f"DEBUG : Message is sent to {msg['To'] }")
            # Build the envelope recipient list: To + Bcc
            recipients = [msg['To']]
            if EMAIL_CONFIG.get('BCC_EMAIL'):
                recipients.append(EMAIL_CONFIG['BCC_EMAIL'])
            server.sendmail(EMAIL_CONFIG['FROM_EMAIL'], recipients, msg.as_string())
            print(f"DEBUG : Email sent to {msg['To']}")
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            append_line("/app/data/sent_emails.log", f"[{timestamp}] Email sent to {msg['To']} with subject {msg['Subject'            ]}")
            #now, wait 2 seconds
            time.sleep(2)
        if test_mode:
            return True, f"TEST email sent to BCC only (not to {member_email})", True
        return True, f"Email sent successfully to {member_email}", False
        
    except Exception as e:
        print(f"DEBUG : Error sending email to {member_email}: {str(e)}")
        return False, f"Error sending email: {str(e)}", False
    


# Add generate_ce_forms script path

from generate_ce_forms import generate_all_forms


DATA_DIR = "/app/data"
DATA_DIR_Calc ="/app/data_calc"
CONFIG_DIR = "/app/config"
#CONFIG_DIR = "/Users/marcdurbach/Development/python/ComEner-calculator/configs"

app = Flask(__name__)
#app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/marcdurbach/Development/python/ComEner-data-management/database/commEnergy.db'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////app/database/commEnergy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key' 
app.config['BILL_OUTPUT_DIR'] = '/app/data/databills'
db.init_app(app)
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])

print("=" * 50)
print("App initialized successfully")
print("Bill routes are now directly in app.py")
print("=" * 50)

# Forms
class MemberForm(FlaskForm):
    name = StringField('Name', validators=[Optional()])
    firstname = StringField('Firstname', validators=[Optional()])
    nationalId = StringField('National ID', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    phoneNumber = StringField('Phone Number', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    energyID = StringField('Energy ID', validators=[Optional()])
    energyIDName = StringField('Energy ID Name', validators=[Optional()])
    payment = SelectField('Payment Method', choices=[('', 'Select'), ('Bank', 'Bank'), ('Payconiq', 'Payconiq') ], validators=[Optional()])
    BankAccount = StringField('Bank Account', validators=[Optional()])
    Payconiq = StringField('WERO', validators=[Optional()])

class PodForm(FlaskForm):
    podlabel = StringField('Pod Label', validators=[Optional()])
    podType = SelectField('Pod Type', choices=[('Production', 'Production'), ('Consumption', 'Consumption')], validators=[DataRequired()])
    memberID = SelectField('Member', coerce=int, validators=[DataRequired()])
    podNumber = StringField('Pod Number', validators=[Optional()])
    energyproduction = FloatField('Energy Production', validators=[Optional()])
    energystorage = FloatField('Energy Storage', validators=[Optional()])

class SharingGroupForm(FlaskForm):
    sgName = StringField('Sharing Group Name', validators=[Optional()])
    sgNumber = StringField('Sharing Group Number', validators=[Optional()])
    sgType = SelectField('Pod Type', choices=[('National', 'National'), ('Local', 'Local')], validators=[DataRequired()])
    sgPrice = FloatField('Price', validators=[Optional()])

class PodSharingGroupForm(FlaskForm):
    podID = SelectField('Pod', coerce=int, validators=[DataRequired()])
    sharingGroupID = SelectField('Sharing Group', coerce=int, validators=[DataRequired()])

class MemberFeeForm(FlaskForm):
    mfamount = FloatField('Amount', validators=[Optional()])
    mfYear = IntegerField('Year', validators=[Optional()])

class MemberFeePaymentForm(FlaskForm):
    memberID = SelectField('Member', coerce=int, validators=[DataRequired()])
    memberFeeID = SelectField('Member Fee', coerce=int, validators=[DataRequired()])
    paymentDate = DateField('Payment Date', validators=[Optional()])
    paymentStatus = SelectField('Payment Status', choices=[('pending', 'Pending'), ('paid', 'Paid'), ('overdue', 'Overdue')], validators=[DataRequired()])

class AccountingForm(FlaskForm):
    accYear = IntegerField('Year', validators=[DataRequired()])
    accMonth = IntegerField('Month', validators=[DataRequired()])
    accMember = SelectField('Member', coerce=int, validators=[DataRequired()])
    accPod = SelectField('Pod', coerce=int, validators=[DataRequired()])
    accAmount = FloatField('Amount', validators=[Optional()])
    accBillingDate = DateField('Billing Date', default=date.today, validators=[Optional()])
    accSGId = SelectField('Sharing Group', coerce=int, validators=[DataRequired()]) 

def get_quarter_months(quarter):
    """Convert quarter to corresponding months"""
    quarter_months = {
        1: [1, 2, 3],   # Q1: Jan, Feb, Mar
        2: [4, 5, 6],   # Q2: Apr, May, Jun
        3: [7, 8, 9],   # Q3: Jul, Aug, Sep
        4: [10, 11, 12] # Q4: Oct, Nov, Dec
    }
    return quarter_months.get(quarter, [])

def get_member_name_map():
    """Create a mapping from member ID to full name from the members table"""
    try:
        query = text("SELECT id, Firstname, name FROM members")
        with engine.connect() as connection:
            result = connection.execute(query)
            member_map = {}
            for row in result:
                full_name = f"{row.Firstname} {row.name}"
                member_map[row.id] = full_name
            return member_map
    except Exception as e:
        print(f"Error loading members from database: {e}")
        return {}

# Routes for Members
@app.route('/members')
def list_members():
    sort_param = request.args.get('sort', 'name')
    print(f"DEBUG: sort_param={sort_param!r}")
    sort_key, sort_dir = parse_sort(sort_param, ('id', 'name', 'firstname', 'email', 'payment'))
    print(f"DEBUG: sort_key={sort_key!r}, sort_dir={sort_dir!r}")
    members = sort_rows(
        Member.query.all(),
        sort_key,
        sort_dir,
        {
            'id': lambda m: (False, m.id),
            'name': lambda m: (m.name is None, normalise(m.name)),
            'firstname': lambda m: (m.firstname is None, normalise(m.firstname)),
            'email': lambda m: (m.email is None, normalise(m.email)),
            'payment': lambda m: (m.payment is None, normalise(m.payment)),
        },
    )
    print(f"DEBUG: sorted {len(members)} members by {sort_key} {sort_dir}")
    return render_template(
        'members/list.html',
        members=members,
        sort_key=sort_key,
        sort_dir=sort_dir,
        sort_target=sort_target,
        sort_indicator=sort_indicator,
    )

@app.route('/members/new', methods=['GET', 'POST'])
def create_member():
    member_form = MemberForm()
    pod_form = PodForm()
    if member_form.validate_on_submit():
        print(member_form)
        member = Member(
            name=member_form.name.data,
            firstname=member_form.firstname.data,
            nationalId=member_form.nationalId.data,
            address=member_form.address.data,
            phoneNumber=member_form.phoneNumber.data,
            email=member_form.email.data,
            energyID=member_form.energyID.data,
            energyIDName=member_form.energyIDName.data,
            payment=member_form.payment.data,
            BankAccount=member_form.BankAccount.data,
            Payconiq=member_form.Payconiq.data
        )
        print(member)
        db.session.add(member)
        db.session.commit()
        flash('Member created successfully!', 'success')
        return redirect(url_for('list_members'))
    return render_template('members/form_new.html',member_form=member_form, pod_form=pod_form, title='Create Member')

@app.route('/members/<int:id>')
def detail_member(id):
    member = Member.query.get_or_404(id)
    return render_template('members/detail.html', member=member)

@app.route('/members/<int:id>/edit', methods=['GET', 'POST'])
def update_member(id):
    member = Member.query.get_or_404(id)
    member_form = MemberForm(obj=member)
    pod_form = PodForm()
    #pod_form.memberID.choices = [(member.id, f"{member.firstname} {member.name}")]
    pod_form.memberID.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
    pod_form.memberID.data = member.id  # Preselect the current member

    if request.method == 'POST':

        if member_form.validate_on_submit() and 'member_submit' in request.form:
            member.name = member_form.name.data
            member.firstname = member_form.firstname.data
            member.nationalId = member_form.nationalId.data
            member.address = member_form.address.data
            member.phoneNumber = member_form.phoneNumber.data
            member.email = member_form.email.data
            member.energyID = member_form.energyID.data
            member.energyIDName = member_form.energyIDName.data
            member.payment = member_form.payment.data
            member.BankAccount = member_form.BankAccount.data
            member.Payconiq = member_form.Payconiq.data

            db.session.commit()
            flash('Member updated successfully!', 'success')
            return redirect(url_for('detail_member', id=member.id))
        elif pod_form.validate_on_submit() and 'pod_submit' in request.form:
            pod = Pod(
                podlabel=pod_form.podlabel.data,
                podType=pod_form.podType.data,
                memberID=pod_form.memberID.data,
                podNumber=pod_form.podNumber.data,
                energyproduction=pod_form.energyproduction.data,
                energystorage=pod_form.energystorage.data
            )
            print(pod)
            db.session.add(pod)
            db.session.commit()
            flash('Pod added successfully!', 'success')
            return redirect(url_for('update_member', id=member.id))

    return render_template('members/form.html', member_form=member_form, pod_form=pod_form, member=member, title='Edit Member')

@app.route('/members/<int:member_id>/pods/<int:pod_id>/delete', methods=['POST'])
def delete_member_pod(member_id, pod_id):
    pod = Pod.query.get_or_404(pod_id)
    if pod.memberID != member_id:
        flash('Pod does not belong to this member!', 'danger')
        return redirect(url_for('update_member', id=member_id))
    db.session.delete(pod)
    db.session.commit()

    flash('Pod deleted successfully!', 'success')
    return redirect(url_for('update_member', id=member_id))

@app.route('/members/<int:id>/delete', methods=['POST'])
def delete_member(id):
    member = Member.query.get_or_404(id)
    db.session.delete(member)
    db.session.commit()
    flash('Member deleted successfully!', 'success')
    return redirect(url_for('list_members'))

# Routes for Pods
@app.route('/pods')
def list_pods():
    sort_param = request.args.get('sort', 'member_lastname')
    sort_key, sort_dir = parse_sort(sort_param, (
        'id', 'label', 'type', 'member_firstname', 'member_lastname',
        'number', 'production', 'storage',
    ))
    pods = sort_rows(
        db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).all(),
        sort_key,
        sort_dir,
        {
            'id': lambda p_m: (False, p_m[0].podsID),
            'label': lambda p_m: (p_m[0].podlabel is None, normalise(p_m[0].podlabel)),
            'type': lambda p_m: (p_m[0].podType is None, normalise(p_m[0].podType)),
            'member_firstname': lambda p_m: (p_m[1].firstname is None, normalise(p_m[1].firstname)),
            'member_lastname': lambda p_m: (p_m[1].name is None, normalise(p_m[1].name)),
            'number': lambda p_m: (p_m[0].podNumber is None, normalise(p_m[0].podNumber)),
            'production': lambda p_m: (p_m[0].energyproduction is None, p_m[0].energyproduction or 0),
            'storage': lambda p_m: (p_m[0].energystorage is None, p_m[0].energystorage or 0),
        },
    )
    return render_template(
        'pods/list.html',
        pods=pods,
        sort_key=sort_key,
        sort_dir=sort_dir,
        sort_target=sort_target,
        sort_indicator=sort_indicator,
    )

@app.route('/pods/new', methods=['GET', 'POST'])
def create_pod():
    form = PodForm()
    form.memberID.choices = [(m.id, f"{m.name} {m.firstname}") for m in Member.query.order_by(Member.name, Member.firstname).all()]
    if form.validate_on_submit():
        pod = Pod(
            podlabel=form.podlabel.data,
            podType=form.podType.data,
            memberID=form.memberID.data,
            podNumber=form.podNumber.data,
            energyproduction=form.energyproduction.data,
            energystorage=form.energystorage.data
        )
        db.session.add(pod)
        db.session.commit()
        flash('Pod created successfully!', 'success')
        return redirect(url_for('list_pods'))
    return render_template('pods/form.html', form=form, title='Create Pod')

@app.route('/pods/<int:id>')
def detail_pod(id):
    pod = Pod.query.get_or_404(id)
    return render_template('pods/detail.html', pod=pod)

@app.route('/pods/<int:id>/edit', methods=['GET', 'POST'])
def update_pod(id):
    pod = Pod.query.get_or_404(id)
    form = PodForm(obj=pod)
    form.memberID.choices = [(m.id, f"{m.name} {m.firstname}") for m in Member.query.order_by(Member.name, Member.firstname).all()]
    if form.validate_on_submit():
        pod.podlabel = form.podlabel.data
        pod.podType = form.podType.data
        pod.memberID = form.memberID.data
        pod.podNumber = form.podNumber.data
        pod.energyproduction = form.energyproduction.data
        pod.energystorage = form.energystorage.data
        print("trying to commit returns ",db.session.commit())
        #db.session.commit()
        flash('Pod updated successfully!', 'success')
        return redirect(url_for('detail_pod', id=pod.podsID))
    print("return ..")
    return render_template('pods/form.html', form=form, title='Edit Pod')

@app.route('/pods/<int:id>/delete', methods=['POST'])
def delete_pod(id):
    pod = Pod.query.get_or_404(id)
    db.session.delete(pod)
    db.session.commit()
    flash('Pod deleted successfully!', 'success')
    return redirect(url_for('list_pods'))

# Routes for Sharing Groups
@app.route('/sharing_groups')
def list_sharing_groups():
    sharing_groups = SharingGroup.query.all()
    return render_template('sharing_groups/list.html', sharing_groups=sharing_groups)

@app.route('/sharing_groups/new', methods=['GET', 'POST'])
def create_sharing_group():
    form = SharingGroupForm()
    if form.validate_on_submit():
        sharing_group = SharingGroup(
            sgName=form.sgName.data,
            sgNumber=form.sgNumber.data,
            sgPrice=form.sgPrice.data,
            sgType=form.sgType.data
        )
        db.session.add(sharing_group)
        db.session.commit()
        flash('Sharing Group created successfully!', 'success')
        return redirect(url_for('list_sharing_groups'))
    return render_template('sharing_groups/form.html', form=form, title='Create Sharing Group')

@app.route('/sharing_groups/<int:id>')
def detail_sharing_group(id):
    sharing_group = SharingGroup.query.get_or_404(id)
    sharing_group_pods = PodSharingGroup.query.filter_by(sharingGroupID=id).all()

    for record in sharing_group_pods:
        print(f"Pod ID: {record.podID}")
        print(f"Member ID: {record.pod_detail.memberID}")
        print(f"Pod Number: {record.pod_detail.podNumber}")
        print(f"Pod Label: {record.pod_detail.podlabel}")
        print(f"Pod Type: {record.pod_detail.podType}")
        print(f"Member Name: {record.pod_detail.member.firstname} {record.pod_detail.member.name}")
    
    return render_template('sharing_groups/detail.html', 
                         sharing_group=sharing_group, 
                         sharing_group_pods=sharing_group_pods)
@app.route('/sharing_groups/<int:id>/edit', methods=['GET', 'POST'])
def update_sharing_group(id):
    sharing_group = SharingGroup.query.get_or_404(id)
    form = SharingGroupForm(obj=sharing_group)
    if form.validate_on_submit():
        sharing_group.sgName = form.sgName.data
        sharing_group.sgNumber = form.sgNumber.data
        sharing_group.sgPrice = form.sgPrice.data
        sharing_group.sgType = form.sgType.data
        db.session.commit()
        flash('Sharing Group updated successfully!', 'success')
        return redirect(url_for('detail_sharing_group', id=sharing_group.sgID))
    return render_template('sharing_groups/form.html', form=form, title='Edit Sharing Group')

@app.route('/sharing_groups/<int:id>/delete', methods=['POST'])
def delete_sharing_group(id):
    sharing_group = SharingGroup.query.get_or_404(id)
    db.session.delete(sharing_group)
    db.session.commit()
    flash('Sharing Group deleted successfully!', 'success')
    return redirect(url_for('list_sharing_groups'))

# Routes for Pod Sharing Groups
@app.route('/pod_sharing_groups')
def list_pod_sharing_groups():
    sort_param = request.args.get('sort', 'id')
    sort_key, sort_dir = parse_sort(sort_param, ('id', 'pod', 'name'))
    
    # Get all pod sharing groups with pod and member info
    psg_list = PodSharingGroup.query.all()
    
    # Prepare sortable items
    psg_items = []
    for psg in psg_list:
        member = psg.pod.member
        owner_name = f"{member.name} {member.firstname}".strip() if member else ""
        psg_items.append({
            'msgID': psg.msgID,
            'pod': psg.pod,
            'pod_label': psg.pod.podlabel or "",
            'owner_name': owner_name,
            'sharing_group': psg.sharing_group
        })
    
    # Sort
    key_map = {
        'id': lambda x: (False, x['msgID']),
        'pod': lambda x: (x['pod_label'] is None, normalise(x['pod_label'])),
        'name': lambda x: (x['owner_name'] is None, normalise(x['owner_name'])),
    }
    psg_items = sort_rows(psg_items, sort_key, sort_dir, key_map)
    
    return render_template(
        'pod_sharing_groups/list.html',
        pod_sharing_groups=psg_items,
        sort_key=sort_key,
        sort_dir=sort_dir,
        sort_target=sort_target,
        sort_indicator=sort_indicator,
    )

@app.route('/pod_sharing_groups/new', methods=['GET', 'POST'])
def create_pod_sharing_group():
    form = PodSharingGroupForm()
    # Get all pods with member info, sorted by member name
    pods = db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).order_by(Member.name, Member.firstname).all()
    
    # Build choices with pod label + owner name, and show existing sharing group
    pod_choices = []
    for pod, member in pods:
        owner_name = f"{member.name} {member.firstname}".strip()
        # Check if pod already belongs to sharing groups
        existing_groups = PodSharingGroup.query.filter_by(podID=pod.podsID).all()
        if existing_groups:
            group_names = ', '.join([psg.sharing_group.sgName for psg in existing_groups])
            label = f"{pod.podlabel} - {owner_name} (in: {group_names})"
        else:
            label = f"{pod.podlabel} - {owner_name}"
        pod_choices.append((pod.podsID, label))
    
    form.podID.choices = pod_choices
    form.sharingGroupID.choices = [(sg.sgID, sg.sgName) for sg in SharingGroup.query.all()]
    if form.validate_on_submit():
        pod_sharing_group = PodSharingGroup(
            podID=form.podID.data,
            sharingGroupID=form.sharingGroupID.data
        )
        db.session.add(pod_sharing_group)
        db.session.commit()
        flash('Pod Sharing Group created successfully!', 'success')
        return redirect(url_for('list_pod_sharing_groups'))
    return render_template('pod_sharing_groups/form.html', form=form, title='Create Pod Sharing Group')

@app.route('/pod_sharing_groups/<int:id>')
def detail_pod_sharing_group(id):
    pod_sharing_group = PodSharingGroup.query.get_or_404(id)
    print(pod_sharing_group)
    print(f"Pod ID: {pod_sharing_group.podID}")
    print(f"Member ID: {pod_sharing_group.pod_detail.memberID}")
    print(f"Pod Number: {pod_sharing_group.pod_detail.podNumber}")
    print(f"Pod label: {pod_sharing_group.pod_detail.podlabel}")

    return render_template('pod_sharing_groups/detail.html', pod_sharing_group=pod_sharing_group)

@app.route('/pod_sharing_groups/<int:id>/edit', methods=['GET', 'POST'])
def update_pod_sharing_group(id):
    pod_sharing_group = PodSharingGroup.query.get_or_404(id)
    form = PodSharingGroupForm(obj=pod_sharing_group)
    # Get all pods with member info, sorted by member name
    pods = db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).order_by(Member.name, Member.firstname).all()
    
    # Build choices with pod label + owner name, and show existing sharing group
    pod_choices = []
    for pod, member in pods:
        owner_name = f"{member.name} {member.firstname}".strip()
        # Check if pod already belongs to sharing groups
        existing_groups = PodSharingGroup.query.filter_by(podID=pod.podsID).all()
        if existing_groups:
            group_names = ', '.join([psg.sharing_group.sgName for psg in existing_groups])
            label = f"{pod.podlabel} - {owner_name} (in: {group_names})"
        else:
            label = f"{pod.podlabel} - {owner_name}"
        pod_choices.append((pod.podsID, label))
    
    form.podID.choices = pod_choices
    form.sharingGroupID.choices = [(sg.sgID, sg.sgName) for sg in SharingGroup.query.all()]
    if form.validate_on_submit():
        pod_sharing_group.podID = form.podID.data
        pod_sharing_group.sharingGroupID = form.sharingGroupID.data
        db.session.commit()
        flash('Pod Sharing Group updated successfully!', 'success')
        return redirect(url_for('detail_pod_sharing_group', id=pod_sharing_group.msgID))
    return render_template('pod_sharing_groups/form.html', form=form, title='Edit Pod Sharing Group')

@app.route('/pod_sharing_groups/<int:id>/delete', methods=['POST'])
def delete_pod_sharing_group(id):
    pod_sharing_group = PodSharingGroup.query.get_or_404(id)
    db.session.delete(pod_sharing_group)
    db.session.commit()
    flash('Pod Sharing Group deleted successfully!', 'success')
    return redirect(url_for('list_pod_sharing_groups'))

# Routes for Member Fees
@app.route('/member_fees')
def list_member_fees():
    member_fees = MemberFee.query.all()
    form = MemberFeeForm()
    return render_template('member_fees/list.html', member_fees=member_fees, form=form)

@app.route('/member_fees/new', methods=['GET', 'POST'])
def create_member_fee():
    form = MemberFeeForm()
    if form.validate_on_submit():
        year = form.mfYear.data
        amount = form.mfamount.data
        
        # Check if a member fee already exists for this year
        existing_fee = MemberFee.query.filter_by(mfYear=year).first()
        
        if existing_fee:
            # Update existing record
            existing_fee.mfamount = amount
            member_fee = existing_fee
            flash(f'Member Fee for {year} updated successfully!', 'info')
        else:
            # Create new record
            member_fee = MemberFee(
                mfamount=amount,
                mfYear=year
            )
            db.session.add(member_fee)
            flash(f'Member Fee for {year} created successfully!', 'success')
        
        # Commit to get the member_fee ID
        db.session.commit()
        
        # Get all members
        all_members = Member.query.all()
        
        # Create or update payment records for all members
        for member in all_members:
            # Check if payment record already exists for this member and fee
            existing_payment = MemberFeePayment.query.filter_by(
                memberID=member.id,
                memberFeeID=member_fee.mfID
            ).first()
            
            if not existing_payment:
                # Create new payment record with pending status
                payment_record = MemberFeePayment(
                    memberID=member.id,
                    memberFeeID=member_fee.mfID,
                    paymentStatus='pending'
                )
                db.session.add(payment_record)
        
        db.session.commit()
        flash(f'Payment records created for all members!', 'success')
        
        return redirect(url_for('list_member_fees'))
    
    return render_template('member_fees/form.html', form=form, title='Create Member Fee')

@app.route('/member_fees/<int:id>')
def detail_member_fee(id):
    member_fee = MemberFee.query.get_or_404(id)
    # Get all payments for this member fee with member details
    payments = db.session.query(MemberFeePayment, Member).join(
        Member, MemberFeePayment.memberID == Member.id
    ).filter(MemberFeePayment.memberFeeID == id).all()
    
    # Separate paid and pending/overdue payments
    paid_payments = [(payment, member) for payment, member in payments if payment.paymentStatus == 'paid']
    pending_payments = [(payment, member) for payment, member in payments if payment.paymentStatus in ['pending', 'overdue']]
    
    return render_template('member_fees/detail.html', 
                         member_fee=member_fee, 
                         paid_payments=paid_payments,
                         pending_payments=pending_payments)
@app.route('/member_fees/<int:id>/edit', methods=['GET', 'POST'])
def update_member_fee(id):
    member_fee = MemberFee.query.get_or_404(id)
    form = MemberFeeForm(obj=member_fee)
    if form.validate_on_submit():
        member_fee.mfamount = form.mfamount.data
        member_fee.mfYear = form.mfYear.data
        db.session.commit()
        flash('Member Fee updated successfully!', 'success')
        return redirect(url_for('detail_member_fee', id=member_fee.mfID))
    return render_template('member_fees/form.html', form=form, title='Edit Member Fee')

@app.route('/member_fees/<int:id>/delete', methods=['POST'])
def delete_member_fee(id):
    member_fee = MemberFee.query.get_or_404(id)
    db.session.delete(member_fee)
    db.session.commit()
    flash('Member Fee deleted successfully!', 'success')
    return redirect(url_for('list_member_fees'))

# Routes for Member Fee Payments

@app.route('/member_fee_payments')
def list_member_fee_payments():
    # Get filter parameters from query string
    selected_year = request.args.get('year', type=int)
    selected_status = request.args.get('status', type=str)
    
    # Start with base query and eager-load member for display + sorting
    query = MemberFeePayment.query.options(db.joinedload(MemberFeePayment.member))
    
    # Apply filters if provided
    if selected_year:
        query = query.join(MemberFee).filter(MemberFee.mfYear == selected_year)
    
    if selected_status:
        query = query.filter(MemberFeePayment.paymentStatus == selected_status)
    
    # Always order by member name (last name), then firstname
    query = query.join(Member, MemberFeePayment.memberID == Member.id).order_by(Member.name, Member.firstname)
    
    member_fee_payments = query.all()
    
    # Get all available years for the dropdown
    available_years = db.session.query(MemberFee.mfYear).distinct().order_by(MemberFee.mfYear.desc()).all()
    available_years = [year[0] for year in available_years]
    
    # Get all available statuses
    available_statuses = ['pending', 'paid', 'overdue']
    
    return render_template(
        'member_fee_payments/list.html',
        member_fee_payments=member_fee_payments,
        available_years=available_years,
        available_statuses=available_statuses,
        selected_year=selected_year,
        selected_status=selected_status
    )

@app.route('/member_fee_payments/new', methods=['GET', 'POST'])
def create_member_fee_payment():
    form = MemberFeePaymentForm()
    form.memberID.choices = [(m.id, f"{m.name} {m.firstname}") for m in Member.query.order_by(Member.name, Member.firstname).all()]
    form.memberFeeID.choices = [(mf.mfID, f"{mf.mfYear} - {mf.mfamount}") for mf in MemberFee.query.all()]
    
    if form.validate_on_submit():
        member_fee_payment = MemberFeePayment(
            memberID=form.memberID.data,
            memberFeeID=form.memberFeeID.data,
            paymentDate=form.paymentDate.data,
            paymentStatus=form.paymentStatus.data
        )
        db.session.add(member_fee_payment)
        db.session.commit()
        flash('Member Fee Payment created successfully!', 'success')
        return redirect(url_for('list_member_fee_payments'))
    if request.method == 'POST' and not form.validate_on_submit():
        flash("Validation failed with error code :")
        flash(form.errors)

    return render_template('member_fee_payments/form.html', form=form, title='Create Member Fee Payment')

@app.route('/member_fee_payments/<int:id>')
def detail_member_fee_payment(id):
    member_fee_payment = MemberFeePayment.query.get_or_404(id)
    #Load the related Member and MemberFee
    member = Member.query.get_or_404(member_fee_payment.memberID)
    member_fee = MemberFee.query.get_or_404(member_fee_payment.memberFeeID)

    return render_template(
        'member_fee_payments/detail.html',
        member_fee_payment=member_fee_payment,
        member=member,
        member_fee=member_fee
    )

@app.route('/member_fee_payments/<int:id>/edit', methods=['GET', 'POST'])
def update_member_fee_payment(id):
    member_fee_payment = MemberFeePayment.query.get_or_404(id)
    form = MemberFeePaymentForm(obj=member_fee_payment)
    form.memberID.choices = [(m.id, f"{m.name} {m.firstname}") for m in Member.query.order_by(Member.name, Member.firstname).all()]
    form.memberFeeID.choices = [(mf.mfID, f"{mf.mfYear} - {mf.mfamount}") for mf in MemberFee.query.all()]
    if form.validate_on_submit():
        member_fee_payment.memberID = form.memberID.data
        member_fee_payment.memberFeeID = form.memberFeeID.data
        member_fee_payment.paymentDate = form.paymentDate.data
        member_fee_payment.paymentStatus = form.paymentStatus.data
        db.session.commit()
        flash('Member Fee Payment updated successfully!', 'success')
        return redirect(url_for('detail_member_fee_payment', id=member_fee_payment.mfpID))
    return render_template('member_fee_payments/form.html', form=form, title='Edit Member Fee Payment')

@app.route('/member_fee_payments/<int:id>/delete', methods=['POST'])
def delete_member_fee_payment(id):
    member_fee_payment = MemberFeePayment.query.get_or_404(id)
    db.session.delete(member_fee_payment)
    db.session.commit()
    flash('Member Fee Payment deleted successfully!', 'success')
    return redirect(url_for('list_member_fee_payments'))

# Routes for Accounting
@app.route('/accounting')
def list_accounting():
    accounting_records = Accounting.query.options(
        db.joinedload(Accounting.member),
        db.joinedload(Accounting.pod),
        db.joinedload(Accounting.sharingGroup)
    ).all()
    
    for record in accounting_records:
        print(f"Record ID: {record.accID}")
        print(f"Member ID: {record.accMember}")
        print(f"Pod ID: {record.accPod}")
        
        # Test member relationship
        try:
            print(f"Member: {record.member}")
            print(f"Member name: {record.member.name} {record.member.firstname}")
        except Exception as e:
            print(f"Error accessing member: {e}")
        
        # Test pod relationship
        try:
            print(f"Pod: {record.pod}")
            print(f"Pod label: {record.pod.podlabel}")
            print(f"Pod number: {record.pod.podNumber}")
        except Exception as e:
            print(f"Error accessing pod: {e}")

        print("---")
        
    return render_template('accounting/list.html', accounting_records=accounting_records)

@app.route('/accounting/new', methods=['GET', 'POST'])
def create_accounting():
    form = AccountingForm()
    form.accMember.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
    form.accPod.choices = [(p.podsID, f"{p.podlabel} {p.podNumber}") for p in Pod.query.all()]
    form.accSGId.choices = [(sg.sgID, sg.sgName) for sg in SharingGroup.query.all()]
    if form.validate_on_submit():
        accounting = Accounting(
            accYear=form.accYear.data,
            accMonth=form.accMonth.data,
            accMember=form.accMember.data,
            accPod=form.accPod.data,
            accSGId=form.accSGId.data,
            accAmount=form.accAmount.data,
            accBillingDate=form.accBillingDate.data
        )
        db.session.add(accounting)
        db.session.commit()
        flash('Accounting record created successfully!', 'success')
        return redirect(url_for('list_accounting'))
    return render_template('accounting/form.html', form=form, title='Create Accounting Record')

@app.route('/accounting/<int:id>')
def detail_accounting(id):
    accounting = Accounting.query.options(
        db.joinedload(Accounting.member),
        db.joinedload(Accounting.pod),
        db.joinedload(Accounting.sharingGroup)
    ).filter(Accounting.accID == id).first()

    print(accounting.accMember)
    print(accounting.accPod)
    print(accounting.accSGId)
    print(f"Member: {accounting.member.firstname} {accounting.member.name}")
    print(f"Pod: {accounting.pod.podlabel} - {accounting.pod.podNumber}")
    print(f"Sharing Group: {accounting.sharingGroup.sgName}")
    return render_template('accounting/detail.html', accounting=accounting)
    

@app.route('/accounting/<int:id>/edit', methods=['GET', 'POST'])
def update_accounting(id):
    accounting = Accounting.query.get_or_404(id)
    form = AccountingForm(obj=accounting)
    form.accMember.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
    form.accPod.choices = [(p.podsID, f"{p.podlabel} {p.podNumber}") for p in Pod.query.all()]
    form.accSGId.choices = [(sg.sgID, sg.sgName) for sg in SharingGroup.query.all()]

    if form.validate_on_submit():
        accounting.accYear = form.accYear.data
        accounting.accMonth = form.accMonth.data
        accounting.accMember = form.accMember.data
        accounting.accPod = form.accPod.data
        accounting.accSGId = form.accSGId.data
        accounting.accAmount = form.accAmount.data
        accounting.accBillingDate = form.accBillingDate.data
        db.session.commit()
        flash('Accounting record updated successfully!', 'success')
        return redirect(url_for('detail_accounting', id=accounting.accID))
    return render_template('accounting/form.html', form=form, title='Edit Accounting Record')

@app.route('/accounting/<int:id>/delete', methods=['POST'])
def delete_accounting(id):
    accounting = Accounting.query.get_or_404(id)
    db.session.delete(accounting)
    db.session.commit()
    flash('Accounting record deleted successfully!', 'success')
    return redirect(url_for('list_accounting'))

@app.route('/accounting/unbilled')
def list_accounting_unbilled():
    accounting_records = Accounting.query.options(
    db.joinedload(Accounting.member),
    db.joinedload(Accounting.pod),
    db.joinedload(Accounting.sharingGroup)
    ).filter(Accounting.accBillingDate.is_(None)).all()
    '''
    for record in accounting_records:
        print(f"Record ID: {record.accID}")
        print(f"Member ID: {record.accMember}")
        print(f"Pod ID: {record.accPod}")
        
        # Test member relationship
        try:
            print(f"Member: {record.member}")
            print(f"Member name: {record.member.name} {record.member.firstname}")
        except Exception as e:
            print(f"Error accessing member: {e}")
        
        # Test pod relationship
        try:
            print(f"Pod: {record.pod}")
            print(f"Pod label: {record.pod.podlabel}")
            print(f"Pod number: {record.pod.podNumber}")
        except Exception as e:
            print(f"Error accessing pod: {e}")

        print("---")
        '''
    return render_template('accounting/list_unbilled.html', accounting_records=accounting_records)

@app.route('/accounting/createbilling', methods=['GET', 'POST'])
def create_billing_file():
    # Logic for creating a billing file goes here
    # Query to sum accAmount for each accMember where accBillingDate is NULL
    results = (
        db.session.query(
            Accounting.accMember,
            func.sum(Accounting.accAmount).label('total_amount'),
            Member.name,
            Member.firstname
        )
        .join(Member, Accounting.accMember == Member.id)
        .filter(Accounting.accBillingDate.is_(None))
        .group_by(Accounting.accMember, Member.name, Member.firstname)
        .all()
    )
    
    # Calculate grand total
    grandtotal = 0
    billing_data = []
    current_datetime = datetime.now().strftime("%Y-%m-%d-%H-%M")
    decomptefilename = f"decompte-{current_datetime}.csv"
    #DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    decomptefilepath = os.path.join(DATA_DIR, decomptefilename)
    print(decomptefilename)
    csv_data = [["Nom", "Prénom", "Montant"]]
    for result in results:
        grandtotal += result.total_amount
        billing_data.append({
            'member_id': result.accMember,
            'name': result.name,
            'firstname': result.firstname,
            'total_amount': result.total_amount
        })

        csv_data.append([result.name, result.firstname, round(result.total_amount,2)])
        #print(f"Member ID: {result.accMember}, Name: {result.name} {result.firstname}, Total Amount: {result.total_amount}")
    # get total line to check difference
    csv_data.append(['Total', '', round(grandtotal,2)])
    # generate CSV file
    with open(decomptefilepath, 'w', newline='') as csv_file:
        csv_writer = csv.writer(csv_file, delimiter=';')
        csv_writer.writerows(csv_data)
    
    # Render the billing template instead of returning a dictionary

    # Update all records where accBillingDate is NULL with the current date
    #current_date = datetime.now().strftime('%Y-%m-%d')
    current_date = datetime.now().date()
    stmt = (
        update(Accounting)
        .where(Accounting.accBillingDate.is_(None))
        .values(accBillingDate=current_date)
    )
    db.session.execute(stmt)
    db.session.commit()
    return render_template('accounting/create_billing.html', 
                         billing_data=billing_data, 
                         grandtotal=grandtotal,
                         filename=decomptefilename)

@app.route('/download/<path:filename>')
def download_file(filename):
    print(filename)
    print("Current working directory:", os.getcwd())
    #DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    print(os.path.join(DATA_DIR, filename))
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

@app.route('/accounting/file_list', methods=['GET'])
def list_accounting_files():
    """Display a list of files accounting files available for download"""
    try:
        files = []
        #DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
        
        # Get all files from the folder
        for filename in os.listdir(DATA_DIR):
            file_path = os.path.join(DATA_DIR, filename)
            if os.path.isfile(file_path):  # Only include files, not directories
                file_info = {
                    'name': filename,
                    'size': os.path.getsize(file_path),
                    'modified': os.path.getmtime(file_path)
                }
                files.append(file_info)
        
        # Sort files by name
        #files.sort(key=lambda x: x['name'].lower())
        files.sort(key=lambda x: x['modified'], reverse=True)
        
        return render_template('accounting/file_list.html', files=files)
    
    except FileNotFoundError:
        return render_template('accounting/file_list.html', files=[], error="Download folder not found")

@app.route('/accounting/list_calculated_files', methods=['GET'])
def list_calculated_files():
    """Display a list of files from calculator,  available for download"""
    try:
        files = []
        for filename in os.listdir(DATA_DIR_Calc):
            file_path = os.path.join(DATA_DIR_Calc, filename)
            if os.path.isfile(file_path):
                file_info = {
                    'name': filename,
                    'size': os.path.getsize(file_path),
                    'modified': os.path.getmtime(file_path)
                }
                files.append(file_info)

        files.sort(key=lambda x: x['modified'], reverse=True)

        return render_template('accounting/file_list_calc.html', files=files)

    except FileNotFoundError:
        return render_template('accounting/file_list_calc.html', files=[], error="Download folder not found")

@app.route('/downloadcalc/<path:filename>')
def download_file_calc(filename):
    print(filename)
    print("Current working directory:", os.getcwd())
    #DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    print(os.path.join(DATA_DIR_Calc, filename))
    return send_from_directory(DATA_DIR_Calc, filename, as_attachment=True)

@app.route('/accounting/quarterly_report', methods=['GET'])
def create_quarterly_report():
    """Display the form for generating reports"""
    current_year = datetime.now().year
    return render_template('accounting/quarterly_report.html', current_year=current_year)

@app.route('/accounting/quarterly-totals-optimized', methods=['GET'])
def get_quarterly_totals_optimized():
    try:
        # Get parameters from request
        quarter = request.args.get('quarter', type=int)
        year = request.args.get('year', type=int, default=datetime.now().year)
        
        if quarter not in [1, 2, 3, 4]:
            return "Error: Quarter must be 1, 2, 3, or 4", 400
        
        # Get months for the requested quarter
        quarter_months = get_quarter_months(quarter)
        month_names = {
            1: 'January', 2: 'February', 3: 'March',
            4: 'April', 5: 'May', 6: 'June',
            7: 'July', 8: 'August', 9: 'September',
            10: 'October', 11: 'November', 12: 'December'
        }
        quarter_month_names = [month_names[m] for m in quarter_months]
        
        # Single SQL query with JOIN to members table
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
            m.name || ' ' || m.Firstname as member_name,
            COALESCE(a.accounting_total, 0) as accounting_total,
            COALESCE(uf.fee_amount, 0) as membership_fee,
            (COALESCE(a.accounting_total, 0) - COALESCE(uf.fee_amount, 0)) as total_amount
        FROM accounting_totals a
        FULL OUTER JOIN unpaid_fees uf ON a.member_id = uf.member_id
        LEFT JOIN members m ON COALESCE(a.member_id, uf.member_id) = m.id
        WHERE COALESCE(a.member_id, uf.member_id) IS NOT NULL
        ORDER BY member_name
        """).bindparams(bindparam('months', expanding=True))
        
        # Execute query
        with engine.connect() as connection:
            result = connection.execute(query, {
                'year': year, 
                'months': tuple(quarter_months)
            })
            
            # Create CSV in memory
            output = io.StringIO()
            writer = csv.writer(output)
            
            # Write detailed header
            writer.writerow(['Rapport Trimestriel'])
            writer.writerow([f'Année: {year}'])
            writer.writerow([f'Trimestre: Q{quarter}'])
            writer.writerow([f'Mois: {", ".join(quarter_month_names)}'])
            writer.writerow(['Généré le : ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow([])  # Empty row for spacing
            writer.writerow(['Nom', 'Total Cons ou Prod', 'Carte de Membre', 'Montant Total à Payer'])

            # Write data rows
            grand_total = 0
            accounting_grand_total = 0
            fee_grand_total = 0
            
            for row in result:
                member_name = row.member_name or f"Member {row.member_id}"
                accounting_total = float(row.accounting_total)
                membership_fee = float(row.membership_fee)
                total_amount = accounting_total - membership_fee
                
                grand_total += total_amount
                accounting_grand_total += accounting_total
                fee_grand_total += membership_fee
                
                writer.writerow([
                    member_name,
                    f"{accounting_total:.2f}",
                    f"{membership_fee:.2f}",
                    f"{total_amount:.2f}"
                ])
            
            # Write grand totals
            writer.writerow([])  # Empty row for spacing
            writer.writerow(['TOTAL pour contrôle', 
                           f"{accounting_grand_total:.2f}", 
                           f"{fee_grand_total:.2f}", 
                           f"{grand_total:.2f}"])
            
            # Get CSV content
            csv_content = output.getvalue()
            
            # Save file to reports folder add _{datetime.now().strftime('%Y%m%d_%H%M%S')} if you need to know when report was created
            filename = f"Quarterly_report_{year}_Q{quarter}.csv"
            filepath = os.path.join(DATA_DIR, filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                f.write(csv_content)
            
            # Prepare response with CSV file
            return Response(
                csv_content,
                mimetype="text/csv",
                headers={
                    "Content-Disposition": f"attachment; filename={filename}",
                    "Content-Type": "text/csv; charset=utf-8"
                }
            )
        
    except Exception as e:
        return f"Error generating report: {str(e)}", 500

@app.route('/accounting/reports')
def list_reports():
    """List all generated reports"""
    reports = []
    try:
        for filename in os.listdir(DATA_DIR):
            if filename.endswith('.csv'):
                filepath = os.path.join(DATA_DIR, filename)
                stat = os.stat(filepath)
                reports.append({
                    'filename': filename,
                    'created': datetime.fromtimestamp(stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    'size': f"{stat.st_size / 1024:.1f} KB"
                })
        
        # Sort by creation time (newest first)
        reports.sort(key=lambda x: x['created'], reverse=True)
        
    except Exception as e:
        return f"Error reading reports: {str(e)}", 500

    return render_template('accounting/reports_list.html', reports=reports)

@app.route('/accounting/reports/<filename>')
def download_report(filename):
    """Download a specific report"""
    try:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error downloading file: {str(e)}", 500

@app.route('/accounting/reports/delete/<filename>', methods=['POST'])
def delete_report(filename):
    """Delete a specific report"""
    try:
        filepath = os.path.join(DATA_DIR, filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return '', 204
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error deleting file: {str(e)}", 500


class ConfigGeneratorForm(FlaskForm):
    sharingGroupID = SelectField('Sharing Group', coerce=int, validators=[DataRequired()])


@app.template_filter('timestamp_to_date')
def timestamp_to_date(timestamp):
    """Convert Unix timestamp to formatted date string."""
    from datetime import datetime
    return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M')


@app.route('/configs')
def list_configs():
    """List all generated config files."""
    import os
    from pathlib import Path
    
    # Config directory
    #config_dir = os.path.expanduser("~/Development/python/ComEner-calculator/configs")
    
    configs = []
    if os.path.exists(CONFIG_DIR):
        for filename in sorted(os.listdir(CONFIG_DIR)):
            if filename.endswith('.yaml') and filename.startswith('CR'):
                file_path = os.path.join(CONFIG_DIR, filename)
                file_stat = os.stat(file_path)
                configs.append({
                    'filename': filename,
                    'size': file_stat.st_size,
                    'modified': file_stat.st_mtime,
                    'created': file_stat.st_ctime
                })
    
    return render_template('configs/list.html', configs=configs)


@app.route('/configs/create', methods=['GET', 'POST'])
def create_config():
    """Create a new config file for a sharing group."""
    form = ConfigGeneratorForm()
    form.sharingGroupID.choices = [(sg.sgID, f"{sg.sgName} ({sg.sgNumber})") for sg in SharingGroup.query.filter(SharingGroup.sgNumber.isnot(None)).order_by(SharingGroup.sgName)]
    
    preview_data = None
    selected_group = None
    
    if request.method == 'POST':
        if 'preview' in request.form:
            # Show preview of what will be generated
            sg_id = form.sharingGroupID.data
            selected_group = SharingGroup.query.get(sg_id)
            if selected_group:
                preview_data = get_config_preview(sg_id)
            return render_template('configs/form.html', form=form, selected_group=selected_group, preview_data=preview_data, title='Create Config')
        
        elif 'generate' in request.form:
            # Generate the config file
            sg_id = form.sharingGroupID.data
            sharing_group = SharingGroup.query.get(sg_id)
            
            if sharing_group and sharing_group.sgNumber:
                try:
                    import sys
                
                    db_path = app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')  
                    print("db path : ",db_path)
                    #output_dir = os.path.expanduser("~/Development/python/ComEner-calculator/configs")
                    
                    generator = ConfigGenerator(db_path, CONFIG_DIR)
                    result = generator.generate_config(sharing_group.sgNumber)
                    
                    if result:
                        flash(f'Config file generated successfully: {result.name}', 'success')
                        return redirect(url_for('list_configs'))
                    else:
                        flash('Failed to generate config file', 'danger')
                except Exception as e:
                    flash(f'Error generating config: {str(e)}', 'danger')
    
    return render_template('configs/form.html', form=form, selected_group=selected_group, preview_data=preview_data, title='Create Config')


def get_config_preview(sg_id):
    """Get preview data for config generation."""
    # Get pods for this sharing group
    pods = db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).join(
        PodSharingGroup, Pod.podsID == PodSharingGroup.podID
    ).filter(PodSharingGroup.sharingGroupID == sg_id).all()
    
    consumers = []
    producers = []
    
    for pod, member in pods:
        name = member.firstname or pod.podlabel.replace(" Consommation", "").replace(" Production", "")
        if pod.podType == 'Consumption':
            consumers.append({
                'name': name,
                'smartmeter': pod.podNumber,
                'member_name': f"{member.firstname} {member.name}".strip()
            })
        else:
            producers.append({
                'name': name,
                'smartmeter': pod.podNumber,
                'member_name': f"{member.firstname} {member.name}".strip()
            })
    
    return {
        'consumers': consumers,
        'producers': producers,
        'total_pods': len(pods)
    }


@app.route('/configs/download/<filename>')
def download_config(filename):
    """Download a config file."""
    #config_dir = os.path.expanduser("~/Development/python/ComEner-calculator/configs")
    return send_from_directory(CONFIG_DIR, filename, as_attachment=True)


@app.route('/configs/delete/<filename>', methods=['POST'])
def delete_config(filename):
    """Delete a config file."""
    #config_dir = os.path.expanduser("~/Development/python/ComEner-calculator/configs")
    file_path = os.path.join(CONFIG_DIR, filename)
    
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            flash(f'Config file {filename} deleted successfully', 'success')
        else:
            flash(f'Config file {filename} not found', 'danger')
    except Exception as e:
        flash(f'Error deleting config file: {str(e)}', 'danger')
    
    return redirect(url_for('list_configs'))


@app.route('/configs/regenerate', methods=['POST'])
def regenerate_all_configs():
    """Regenerate all config files."""
    try:
        
        db_path = app.config['SQLALCHEMY_DATABASE_URI']
        #output_dir = os.path.expanduser("~/Development/python/ComEner-calculator/configs")
        
        generator = ConfigGenerator(db_path, CONFIG_DIR)
        generated = generator.generate_all_configs()
        
        flash(f'Regenerated {len(generated)} config files', 'success')
    except Exception as e:
        flash(f'Error regenerating configs: {str(e)}', 'danger')
    
    return redirect(url_for('list_configs'))


# Leneda Metering Data Access Routes
'''from leneda_access import (
    get_all_obis_codes,
    get_member_pods,
    request_metering_data_access,
    LenedaCredentials
)'''

# Configuration for Leneda API (could also be moved to config)
LENEDA_API_KEY = os.environ.get('LENEDA_API_KEY', 'e0e3f107-1836-4717-a090-d1863fe9f30c')
LENEDA_ENERGY_ID = os.environ.get('LENEDA_ENERGY_ID', 'LUXE-MA-DU-ZPUGN')


# ===============================
# Leneda Metering Data Access Routes
# ===============================

@app.route('/members/<int:member_id>/leneda-access', methods=['GET'])
def leneda_access_form(member_id):
    """Display form for requesting Leneda metering data access."""
    member = Member.query.get_or_404(member_id)
    
    # Get member's pods
    pods = Pod.query.filter_by(memberID=member_id).all()
    pods_with_numbers = [p for p in pods if p.podNumber]
    
    # Categorize pods by type
    consumption_pods = [p for p in pods_with_numbers if p.podType == "Consumption"]
    production_pods = [p for p in pods_with_numbers if p.podType == "Production"]
    
    # Get applicable OBIS codes based on pod types
    obis_codes = {}
    
    if consumption_pods:
        obis_codes['consumption'] = get_obis_codes_for_pod_type("Consumption", include_gas=True)
    
    if production_pods:
        obis_codes['production'] = get_obis_codes_for_pod_type("Production")
    
    return render_template(
        'members/leneda_access.html',
        member=member,
        pods=pods_with_numbers,
        consumption_pods=consumption_pods,
        production_pods=production_pods,
        obis_codes=obis_codes,
        has_energy_id=bool(member.energyID)
    )


@app.route('/members/<int:member_id>/leneda-access', methods=['POST'])
def leneda_access_submit(member_id):
    """Submit Leneda metering data access request."""
    member = Member.query.get_or_404(member_id)
    
    # Validate member has Energy ID
    if not member.energyID:
        flash('Member does not have an Energy ID configured. Please update the member profile first.', 'error')
        return redirect(url_for('update_member', id=member_id))
    
    # Get selected OBIS codes from form
    selected_obis = request.form.getlist('obis_codes')
    
    if not selected_obis:
        flash('Please select at least one OBIS code.', 'error')
        return redirect(url_for('leneda_access_form', member_id=member_id))
    
    # Make the API request
    result = request_access_for_member(
        member_id=member_id,
        selected_obis_codes=selected_obis,
        db_session=db.session
    )
    
    if result['success']:
        # Calculate totals across all requests
        total_requests = result.get('request_count', 1)
        total_obis = sum(
            req.get('request_details', {}).get('obis_codes_count', 0) 
            for req in result.get('requests', [])
        )
        total_points = sum(
            req.get('request_details', {}).get('metering_points_count', 0) 
            for req in result.get('requests', [])
        )
        
        if total_requests > 1:
            flash(
                f"✅ Successfully sent {total_requests} metering data access requests for {member.firstname} {member.name}. "
                f"Requested {total_obis} OBIS code(s) for {total_points} metering point(s).",
                'success'
            )
        else:
            flash(
                f"✅ Successfully sent metering data access request for {member.firstname} {member.name}. "
                f"Requested {total_obis} OBIS code(s) for {total_points} metering point(s).",
                'success'
            )
    else:
        error_msg = result.get('error', 'Unknown error')
        # Check individual requests for specific errors
        for req in result.get('requests', []):
            if not req.get('success'):
                status_code = req.get('status_code')
                pod_type = req.get('pod_type', 'Unknown')
                req_error = req.get('error', 'Unknown error')
                if status_code == 400:
                    error_msg = f"{pod_type}: Invalid request: {req_error}. Please check the Energy ID and metering point codes."
                elif status_code == 401:
                    error_msg = f"{pod_type}: Authentication failed. Please check API credentials."
                elif status_code == 403:
                    error_msg = f"{pod_type}: Access denied. You may not have permission to request data for this member."
                elif status_code == 404:
                    error_msg = f"{pod_type}: Member or metering points not found in Leneda system."
        
        flash(f"❌ Failed to send request: {error_msg}", 'error')
    
    return redirect(url_for('leneda_access_form', member_id=member_id))


@app.route('/', methods=['GET'])
def menu():
    return render_template("menu.html", page_title="Menu")


# ===============================
# Creos Forms Generation Routes
# ===============================

@app.route('/creos-forms', methods=['GET'])
def creos_forms():
    """Display form to select sharing group and PODs for Creos forms generation."""
    sharing_groups = SharingGroup.query.all()
    
    # Get all PODs with their member info and sharing group assignments
    pods = db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).all()
    
    pods_data = []
    for pod, member in pods:
        pod_dict = {
            'podsID': pod.podsID,
            'podlabel': pod.podlabel,
            'podType': pod.podType,
            'podNumber': pod.podNumber,
            'energyproduction': float(pod.energyproduction) if pod.energyproduction else None,
            'energystorage': float(pod.energystorage) if pod.energystorage else None,
            'member_name': f"{member.firstname} {member.name}".strip(),
            'member_email': member.email,
            'sharing_groups': [
                {'sharingGroupID': sg.sharingGroupID, 'sgName': sg.sharing_group.sgName}
                for sg in pod.sharing_groups
            ]
        }
        pods_data.append(pod_dict)
    
    return render_template(
        'cereos_forms/select.html',
        sharing_groups=sharing_groups,
        pods_json=json.dumps(pods_data),
        sharing_groups_json=json.dumps([{'sgID': sg.sgID, 'sgName': sg.sgName, 'sgNumber': sg.sgNumber} for sg in sharing_groups])
    )


@app.route('/creos-forms/generate', methods=['POST'])
def generate_creos_forms():
    """Generate Ceeos forms for selected sharing group and PODs."""
    sharing_group_id = request.form.get('sharing_group', type=int)
    representative_name = request.form.get('representative_name', '')
    date_application = request.form.get('date_application', 'Dès que possible')
    pod_ids = request.form.getlist('pod_ids', type=int)
    
    if not sharing_group_id:
        flash('Please select a sharing group.', 'danger')
        return redirect(url_for('creos_forms'))
    
    if not pod_ids:
        flash('Please select at least one POD.', 'danger')
        return redirect(url_for('creos_forms'))
    
    sharing_group = SharingGroup.query.get_or_404(sharing_group_id)
    
    # Get selected PODs with member info
    selected_pods = db.session.query(Pod, Member).join(Member, Pod.memberID == Member.id).filter(Pod.podsID.in_(pod_ids)).all()
    
    # Organize by member
    members_data = {}
    for pod, member in selected_pods:
        member_key = member.id
        if member_key not in members_data:
            members_data[member_key] = {
                'name': f"{member.firstname} {member.name}".strip(),
                'email': member.email,
                'pods': []
            }
        
        pod_type = 'production' if pod.podType == 'Production' else 'consumption'
        members_data[member_key]['pods'].append({
            'number': pod.podNumber or '',
            'type': pod_type,
            'kva': str(pod.energyproduction) if pod.energyproduction else '',
            'kwh': str(pod.energystorage) if pod.energystorage else ''
        })
    
    # Prepare members list for generate_all_forms
    members_list = []
    for member_data in members_data.values():
        members_list.append({
            'name': member_data['name'],
            'pods': member_data['pods']
        })
    
    # Generate forms
    output_dir = '/Users/marcdurbach/clawd/output'
    results = generate_all_forms(
        sharing_group_id=sharing_group.sgNumber or f"CR{sharing_group.sgID:08d}",
        representative_name=representative_name or members_list[0]['name'] if members_list else '',
        date_application=date_application,
        members=members_list
    )
    
    # Create ZIP file
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"CE_Forms_{sharing_group.sgNumber or sharing_group.sgName}_{ts}.zip"
    zip_path = os.path.join(output_dir, zip_filename)
    
    with zipfile.ZipFile(zip_path, 'w') as zf:
        # Add modification form
        if results['modification_form'] and os.path.exists(results['modification_form']):
            zf.write(results['modification_form'], os.path.basename(results['modification_form']))
        
        # Add annexes
        for ann in results['annexes']:
            if ann['path'] and os.path.exists(ann['path']):
                zf.write(ann['path'], os.path.basename(ann['path']))
    
    # Calculate totals
    total_pods = sum(len(m['pods']) for m in members_list)
    total_pdfs = 1 + len(results['annexes'])  # modification + annexes
    
    # Prepare data for template
    annexes_data = []
    for ann in results['annexes']:
        annexes_data.append({
            'member': ann['member'],
            'filename': os.path.basename(ann['path']),
            'pods_count': ann['pods_count']
        })
    
    return render_template(
        'creos_forms/generated.html',
        sharing_group=sharing_group,
        modification_form=os.path.basename(results['modification_form']) if results['modification_form'] else None,
        annexes=annexes_data,
        total_pods=total_pods,
        total_pdfs=total_pdfs,
        zip_filename=zip_filename
    )


@app.route('/creos-forms/download/<zip_filename>')
def download_creos_forms(zip_filename):
    """Download the generated ZIP file."""
    output_dir = '/Users/marcdurbach/clawd/output'
    zip_path = os.path.join(output_dir, zip_filename)
    
    if os.path.exists(zip_path):
        return send_file(zip_path, as_attachment=True)
    else:
        flash('ZIP file not found.', 'danger')
        return redirect(url_for('creos_forms'))


@app.route('/creos-forms/send-email', methods=['POST'])
def send_creos_forms_email():
    """Send generated forms by email to each member."""
    zip_filename = request.form.get('zip_filename', '')
    output_dir = '/Users/marcdurbach/clawd/output'
    
    # Extract sharing group info from zip filename
    # Format: CE_Forms_{group}_{timestamp}.zip
    parts = zip_filename.replace('.zip', '').split('_')
    
    # Get the generated PDFs from the output directory
    ts = parts[-2] + '_' + parts[-1] if len(parts) >= 3 else ''
    
    # Find modification form and annexes
    pdf_files = [f for f in os.listdir(output_dir) if f.endswith('.pdf') and ts in f]
    
    # Group by member
    member_files = {}
    for pdf in pdf_files:
        if pdf.startswith('CE_Annexe2_'):
            # Extract member name from filename
            # Format: CE_Annexe2_{SG}_{MemberName}_{timestamp}.pdf
            parts_pdf = pdf.split('_')
            # Find where member name starts (after SG ID)
            if len(parts_pdf) >= 4:
                # This is tricky, let's use a different approach
                pass
    
    # For simplicity, send one email per PDF file with the member's name
    # Create email body in 3 languages
    email_body = """Dear member,

Please find attached the Creos form to be signed.

Please verify your data, print the document, sign it, and return it to me as a PDF.

Thank you in advance.

---

Chère membre,

Merci de trouver en annexe le formulaire Creos à signer.

Merci de vérifier vos données, imprimer le document, signer le document, et me le renvoyer sous forme de PDF.

En vous remerciant d'avance.

---

Léif Member,

Am Annex fannt Dir de Creos Formulaire zum Ënnerschreiwen.

Iwwerpréift w.e.g. Är Daten, dréckt d'Dokument aus, Ënnerschreift et a schéckt et mir als PDF zréck.

Merci vun hier un.
"""
    
    # Setup email
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    
    sent_count = 0
    error_count = 0
    
    # Send to each member that has an annexe
    for pdf in pdf_files:
        if pdf.startswith('CE_Annexe2_'):
            # Try to find member email from filename
            # This is a simplified approach - in production you'd query the DB
            try:
                msg = MIMEMultipart()
                # Use plain email address to avoid SMTP rejection
                msg['From'] = EMAIL_CONFIG['FROM_EMAIL']
                msg['Subject'] = 'Communauté Energétique - Creos formulaire'
                
                # For testing, send to the from email
                # In production, lookup member email from DB based on filename
                msg['To'] = EMAIL_CONFIG['FROM_EMAIL']
                
                # Add BCC if configured
                if EMAIL_CONFIG.get('BCC_EMAIL'):
                    msg['Bcc'] = EMAIL_CONFIG['BCC_EMAIL']
                
                msg.attach(MIMEText(email_body, 'plain'))
                
                # Attach the PDF
                pdf_path = os.path.join(output_dir, pdf)
                with open(pdf_path, 'rb') as f:
                    p = MIMEBase('application', 'pdf')
                    p.set_payload(f.read())
                    encoders.encode_base64(p)
                    p.add_header('Content-Disposition', f'attachment; filename={pdf}')
                    msg.attach(p)
                
                with smtplib.SMTP_SSL(EMAIL_CONFIG['SMTP_SERVER'], EMAIL_CONFIG['SMTP_PORT'], context=ctx) as s:
                    s.login(EMAIL_CONFIG['SMTP_USER'], EMAIL_CONFIG['SMTP_PASSWORD'])
                    s.sendmail(EMAIL_CONFIG['FROM_EMAIL'], EMAIL_CONFIG['FROM_EMAIL'], msg.as_string())
                
                sent_count += 1
            except Exception as e:
                error_count += 1
                print(f"Error sending email for {pdf}: {e}")
    
    if sent_count > 0:
        flash(f'Successfully sent {sent_count} emails.', 'success')
    if error_count > 0:
        flash(f'Failed to send {error_count} emails.', 'warning')
    
    return redirect(url_for('creos_forms'))


# ==============================================================================
# CSV Bill Upload Routes - Direct Implementation
# ==============================================================================

import csv
import os
import json
import random
from werkzeug.utils import secure_filename

# Configuration for CSV bills
CSV_BILL_DIR = os.path.join(DATA_DIR, 'csv_bills')
os.makedirs(CSV_BILL_DIR, exist_ok=True)

# Default payment info
DEFAULT_BANK_ACCOUNT = "LU12 0019 1303 5350 3000"
DEFAULT_BANK_BIC = "BCEELULLXXX"
DEFAULT_PAYCONIQ_NUMBER = "661196114"


def parse_quarterly_csv(filepath):
    """Parse the quarterly report CSV format."""
    bills = []
    year = None
    quarter = None
    
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # Parse header info
    for line in lines[:10]:
        if line.startswith('Année:'):
            year = line.split(':')[1].strip()
        elif line.startswith('Trimestre:'):
            quarter = line.split(':')[1].strip()
    
    # Find the data section
    data_started = False
    for line in lines:
        line = line.strip()
        if line.startswith('Nom,'):
            data_started = True
            continue
        if data_started and line and not line.startswith('TOTAL'):
            parts = line.split(',')
            if len(parts) >= 4:
                try:
                    full_name = parts[0].strip()
                    cons_prod = float(parts[1]) if parts[1] else 0.0
                    member_fee = float(parts[2]) if parts[2] else 0.0
                    amount = float(parts[3]) if parts[3] else 0.0
                    
                    # Parse name
                    name_parts = full_name.rsplit(' ', 1)
                    if len(name_parts) == 2:
                        firstname, name = name_parts[0], name_parts[1]
                    else:
                        firstname, name = full_name, ''
                    
                    bills.append({
                        'id': f"{year}_{quarter}_{name}_{firstname}".replace(' ', '_'),
                        'year': year,
                        'quarter': quarter,
                        'fullname': full_name,
                        'name': name,
                        'firstname': firstname,
                        'cons_prod': cons_prod,
                        'member_fee': member_fee,
                        'amount': amount,
                        'direction': 'pay' if amount < 0 else 'receive',
                        'abs_amount': abs(amount)
                    })
                except (ValueError, IndexError):
                    continue
    
    return bills, year, quarter

def get_member_payment_info_from_db(fullname):
    """Get payment info from database."""
    try:
        # Try to find member by fullname
        members = Member.query.all()
        for member in members:
            member_fullname = f"{member.firstname} {member.name}".strip()
            if member_fullname == fullname or member.name == fullname:
                return {
                    'payment': member.payment or 'Bank',
                    'payconiq': member.Payconiq or '',
                    'bank': member.BankAccount or '',
                    'phone': member.phoneNumber or '',
                    'email': member.email or ''
                }
    except Exception as e:
        print(f"Error querying member: {e}")
    
    return {
        'payment': 'Bank',
        'payconiq': '',
        'bank': '',
        'phone': '',
        'email': ''
    }

def generate_bill_email_content(bill, member_info):
    """Generate trilingual email content for a bill."""
    fullname = bill['fullname']
    year = bill['year']
    quarter = bill['quarter']
    amount = f"{bill['abs_amount']:.2f}"
    print("DEBUG: generate_bill_email_content called with bill:", bill)
    if bill['direction'] == 'pay':
        # Member needs to pay
        if member_info['payment'] == 'Payconiq' and DEFAULT_PAYCONIQ_NUMBER:
            fr = f"Veuillez effectuer le paiement de {amount}€ via WERO au numéro {DEFAULT_PAYCONIQ_NUMBER}"
            en = f"Please make the payment of {amount}€ via WERO to number {DEFAULT_PAYCONIQ_NUMBER}"
            lu = f"Bezuelt w.e.g. {amount}€ iwwer WERO op d'Nummer {DEFAULT_PAYCONIQ_NUMBER}"
        else:
            fr = f"Veuillez effectuer le virement de {amount}€ sur le compte: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
            en = f"Please transfer {amount}€ to account: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
            lu = f"Iwwerweist w.e.g. {amount}€ op de Konto: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
    else:
        # Member will receive money
        if member_info['payment'] == 'Payconiq' and member_info.get('payconiq'):
            payconiq_num = member_info['payconiq']
            fr = f"Vous recevrez {amount}€ sur votre compte WERO ({payconiq_num})"
            en = f"You will receive {amount}€ on your WERO account ({payconiq_num})"
            lu = f"Dir kritt {amount}€ op Äre WERO Konto ({payconiq_num})"
        elif member_info.get('bank'):
            bank = member_info['bank']
            fr = f"Vous recevrez {amount}€ sur votre compte bancaire: {bank}"
            en = f"You will receive {amount}€ on your bank account: {bank}"
            lu = f"Dir kritt {amount}€ op Äre Bankkonto: {bank}"
        else:
            fr = f"Vous recevrez {amount}€ (veuillez nous contacter pour les détails de paiement)"
            en = f"You will receive {amount}€ (please contact us for payment details)"
            lu = f"Dir kritt {amount}€ (kontaktéiert eis w.e.g. fir Bezuelungsdetailer)"
    
    return f"""Dear {fullname},

Regarding your bill for {quarter} {year}:

{en}

Consumption/Production: {bill['cons_prod']:.2f}€
Membership Fee: {bill['member_fee']:.2f}€
Net Amount: {bill['amount']:.2f}€

Best regards,
Communauté Energétique

---

Cher/Chère {fullname},

Concernant votre facture pour {quarter} {year}:

{fr}

Consommation/Production: {bill['cons_prod']:.2f}€
Carte de Membre: {bill['member_fee']:.2f}€
Montant Net: {bill['amount']:.2f}€

Cordialement,
Communauté Energétique

---

Léif {fullname},

Bezüglech Är Rechnung fir {quarter} {year}:

{lu}

Verbrauch/Produktioun: {bill['cons_prod']:.2f}€
Memberkaart: {bill['member_fee']:.2f}€
Nettobedrag: {bill['amount']:.2f}€

Mat beschte Gréiss,
Communauté Energétique
"""

@app.route('/accounting/csv_bills', methods=['GET', 'POST'])
def csv_bills():
    """Handle CSV bill selection from server files."""
    if request.method == 'POST':
        selected_file = request.form.get('csv_file')
        if selected_file:
            flash(f'File selected: {selected_file}', 'success')
            return redirect(f'/accounting/csv_bills/view/{selected_file}')
        else:
            flash('No file selected', 'error')
    
    # Scan for Quarterly_report*.csv files in /app/data
    csv_files = []
    data_dir = '/app/data'
    if os.path.exists(data_dir):
        csv_files = sorted([f for f in os.listdir(data_dir) 
                           if f.startswith('Quarterly_report') and f.endswith('.csv')],
                          reverse=True)
    
    return render_template_string(CSV_BILLS_TEMPLATE, csv_files=csv_files)

@app.route('/accounting/csv_bills/view/<filename>')
def view_csv_bills(filename):
    """View bills from a specific CSV file."""
    filepath = os.path.join('/app/data', filename)
    if not os.path.exists(filepath):
        flash('File not found', 'error')
        return redirect('/accounting/csv_bills')
    
    try:
        bills, year, quarter = parse_quarterly_csv(filepath)
        
        # Enrich with member info from DB
        for bill in bills:
            bill['member_info'] = get_member_payment_info_from_db(bill['fullname'])
        
        # Calculate stats
        to_pay = [b for b in bills if b['direction'] == 'pay']
        to_receive = [b for b in bills if b['direction'] == 'receive']
        
        stats = {
            'total': len(bills),
            'to_pay_count': len(to_pay),
            'to_receive_count': len(to_receive),
            'total_to_pay': sum(b['abs_amount'] for b in to_pay),
            'total_to_receive': sum(b['abs_amount'] for b in to_receive)
        }
        
        return render_template_string(VIEW_BILLS_TEMPLATE, 
                                      bills=bills, 
                                      year=year, 
                                      quarter=quarter,
                                      stats=stats,
                                      filename=filename)
    except Exception as e:
        flash(f'Error parsing CSV: {e}', 'error')
        return redirect('/accounting/csv_bills')

@app.route('/accounting/csv_bills/preview/<filename>/<bill_id>')
def preview_csv_bill(filename, bill_id):
    """Preview email for a specific bill."""
    filepath = os.path.join('/app/data', filename)
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    
    try:
        bills, _, _ = parse_quarterly_csv(filepath)
        bill = next((b for b in bills if b['id'] == bill_id), None)
        
        if not bill:
            return jsonify({'error': 'Bill not found'}), 404
        
        member_info = get_member_payment_info_from_db(bill['fullname'])
        email_body = generate_bill_email_content(bill, member_info)
        
        return jsonify({'email_body': email_body})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# Templates for CSV bills
CSV_BILLS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>CSV Bill Selection</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1200px; margin: 0 auto; padding: 20px; }
        h1, h2 { color: #333; }
        .file-select-form { background: #f5f5f5; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .file-select-form select { 
            width: 100%; 
            padding: 10px; 
            font-size: 14px; 
            margin-bottom: 10px;
            border: 1px solid #ddd;
            border-radius: 4px;
        }
        .btn { 
            padding: 10px 20px; 
            background: #4CAF50; 
            color: white; 
            text-decoration: none; 
            border: none;
            border-radius: 4px; 
            cursor: pointer;
            font-size: 14px;
        }
        .btn:hover { background: #45a049; }
        .no-files { 
            background: #fff3cd; 
            border: 1px solid #ffc107; 
            padding: 15px; 
            border-radius: 4px;
            color: #856404;
        }
        .info-box {
            background: #d1ecf1;
            border: 1px solid #bee5eb;
            padding: 15px;
            border-radius: 4px;
            color: #0c5460;
            margin-bottom: 20px;
        }
    </style>
</head>
<body>
    <h1>📄 CSV Bill Selection</h1>
    
    <div class="info-box">
        <strong>Scanning folder:</strong> /app/data<br>
        <strong>File pattern:</strong> Quarterly_report*.csv
    </div>
    
    {% if csv_files %}
    <div class="file-select-form">
        <h3>Select a Quarterly Report File</h3>
        <form method="POST">
            <select name="csv_file" required>
                <option value="">-- Select a file --</option>
                {% for file in csv_files %}
                <option value="{{ file }}">{{ file }}</option>
                {% endfor %}
            </select>
            <button type="submit" class="btn">View Bills</button>
        </form>
    </div>
    
    <h3>Available Files ({{ csv_files|length }} found)</h3>
    <ul>
        {% for file in csv_files %}
        <li><a href="/accounting/csv_bills/view/{{ file }}">{{ file }}</a></li>
        {% endfor %}
    </ul>
    {% else %}
    <div class="no-files">
        <strong>No Quarterly_report*.csv files found</strong> in /app/data
    </div>
    {% endif %}
    
    <p><a href="/">← Back to Menu</a></p>
</body>
</html>
'''

VIEW_BILLS_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Bills - {{ year }} {{ quarter }}</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 1400px; margin: 0 auto; padding: 20px; }
        h1, h2 { color: #333; }
        .stats { display: flex; gap: 15px; margin: 20px 0; flex-wrap: wrap; }
        .stat-box { background: #f5f5f5; padding: 15px; border-radius: 5px; text-align: center; min-width: 150px; }
        .stat-box .number { font-size: 24px; font-weight: bold; color: #333; }
        .stat-box .label { font-size: 12px; color: #666; }
        table { border-collapse: collapse; width: 100%; margin-top: 20px; }
        th, td { border: 1px solid #ddd; padding: 12px; text-align: left; }
        th { background-color: #4CAF50; color: white; }
        tr:nth-child(even) { background-color: #f2f2f2; }
        .direction-pay { color: #f44336; font-weight: bold; }
        .direction-receive { color: #4CAF50; font-weight: bold; }
        .amount { text-align: right; font-family: monospace; }
        .btn { padding: 6px 12px; border: none; border-radius: 3px; cursor: pointer; text-decoration: none; display: inline-block; margin-right: 5px; }
        .btn-preview { background: #9C27B0; color: white; }
        .modal { display: none; position: fixed; z-index: 1; left: 0; top: 0; width: 100%; height: 100%; background-color: rgba(0,0,0,0.4); }
        .modal-content { background-color: #fefefe; margin: 5% auto; padding: 20px; border: 1px solid #888; width: 80%; max-width: 800px; border-radius: 5px; }
        .close { color: #aaa; float: right; font-size: 28px; font-weight: bold; cursor: pointer; }
        pre { background: #f5f5f5; padding: 15px; border-radius: 5px; overflow-x: auto; white-space: pre-wrap; }
    </style>
</head>
<body>
    <h1>📄 Bills - {{ year }} {{ quarter }}</h1>
    
    <div class="stats">
        <div class="stat-box">
            <div class="number">{{ stats.total }}</div>
            <div class="label">Total Members</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #f44336;">{{ stats.to_pay_count }}</div>
            <div class="label">Need to Pay</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #4CAF50;">{{ stats.to_receive_count }}</div>
            <div class="label">Will Receive</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #f44336;">{{ "%.2f"|format(stats.total_to_pay) }}€</div>
            <div class="label">Total to Collect</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #4CAF50;">{{ "%.2f"|format(stats.total_to_receive) }}€</div>
            <div class="label">Total to Pay Out</div>
        </div>
    </div>
    
    <table>
        <thead>
            <tr>
                <th>Name</th>
                <th>Cons/Prod</th>
                <th>Member Fee</th>
                <th>Amount</th>
                <th>Direction</th>
                <th>Payment Method</th>
                <th>Actions</th>
            </tr>
        </thead>
        <tbody>
            {% for bill in bills %}
            <tr>
                <td>{{ bill.fullname }}</td>
                <td class="amount">{{ "%.2f"|format(bill.cons_prod) }}€</td>
                <td class="amount">{{ "%.2f"|format(bill.member_fee) }}€</td>
                <td class="amount">{{ "%.2f"|format(bill.amount) }}€</td>
                <td>
                    {% if bill.direction == 'pay' %}
                    <span class="direction-pay">↗ Pay {{ "%.2f"|format(bill.abs_amount) }}€</span>
                    {% else %}
                    <span class="direction-receive">↘ Receive {{ "%.2f"|format(bill.abs_amount) }}€</span>
                    {% endif %}
                </td>
                <td>{{ bill.member_info.payment }}</td>
                <td>
                    <button class="btn btn-preview" onclick="previewBill('{{ bill.id }}')">Preview Email</button>
                </td>
            </tr>
            {% endfor %}
        </tbody>
    </table>
    
    <div id="previewModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <h2>Email Preview</h2>
            <pre id="previewContent"></pre>
        </div>
    </div>
    
    <p style="margin-top: 20px;"><a href="/accounting/csv_bills">← Back to CSV Files</a></p>
    
    <script>
        function previewBill(billId) {
            fetch('/accounting/csv_bills/preview/{{ filename }}/' + billId)
                .then(r => r.json())
                .then(data => {
                    document.getElementById('previewContent').textContent = data.email_body;
                    document.getElementById('previewModal').style.display = 'block';
                });
        }
        function closeModal() {
            document.getElementById('previewModal').style.display = 'none';
        }
        window.onclick = function(event) {
            var modal = document.getElementById('previewModal');
            if (event.target == modal) modal.style.display = 'none';
        }
    </script>
</body>
</html>
'''


# ==============================================================================
# BILL ROUTES - Merged from bill_routes.py
# ==============================================================================


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
    base_dir = app.config.get('BILL_OUTPUT_DIR', os.path.join(os.getcwd(), 'bills'))
    return os.path.join(base_dir, folder_name)


def get_bill_status_file_path(folder_name):
    """Get path to the status JSON file for a bill folder."""
    folder_path = get_bill_folder_path(folder_name)
    return os.path.join(folder_path, '_email_status.json')


def load_bill_email_status(folder_name):
    """Load email sending status from JSON file."""
    status_file = get_bill_status_file_path(folder_name)
    if os.path.exists(status_file):
        try:
            with open(status_file, 'r') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_bill_email_status(folder_name, status):
    """Save email sending status to JSON file."""
    status_file = get_bill_status_file_path(folder_name)
    try:
        with open(status_file, 'w') as f:
            json.dump(status, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving email status: {e}")
        return False


# ==============================================================================
# EMAIL QUEUE SYSTEM - Background processing for bulk bill emails
# ==============================================================================

import threading
import queue

# Global queue for email jobs
_email_worker_thread = None
_email_worker_lock = threading.Lock()


def get_email_queue_file_path(folder_name):
    """Get path to the email queue JSON file."""
    folder_path = get_bill_folder_path(folder_name)
    return os.path.join(folder_path, '_email_queue.json')


def get_email_progress_file_path(folder_name):
    """Get path to the email progress JSON file."""
    folder_path = get_bill_folder_path(folder_name)
    return os.path.join(folder_path, '_email_progress.json')


def create_email_queue(folder_name, bill_items, test_mode=False):
    """Create an email queue file for background processing.
    
    Args:
        folder_name: The bill folder name
        bill_items: List of dicts with member_id, filename, filepath
        test_mode: Whether this is test mode
    
    Returns:
        Dict with queue info
    """
    queue_data = {
        'folder': folder_name,
        'created_at': datetime.now().isoformat(),
        'test_mode': test_mode,
        'total': len(bill_items),
        'sent': 0,
        'failed': 0,
        'pending': len(bill_items),
        'status': 'queued',  # queued, running, completed, cancelled
        'items': []
    }
    
    for item in bill_items:
        queue_data['items'].append({
            'member_id': item['member_id'],
            'member_name': item.get('member_name', f"Member {item['member_id']}"),
            'filename': item['filename'],
            'filepath': item['filepath'],
            'status': 'pending',  # pending, sending, sent, failed
            'sent_at': None,
            'error': None
        })
    
    queue_file = get_email_queue_file_path(folder_name)
    with open(queue_file, 'w') as f:
        json.dump(queue_data, f, indent=2)
    
    # Also create initial progress file
    progress_file = get_email_progress_file_path(folder_name)
    with open(progress_file, 'w') as f:
        json.dump({
            'folder': folder_name,
            'status': 'queued',
            'total': len(bill_items),
            'sent': 0,
            'failed': 0,
            'pending': len(bill_items),
            'current': None,
            'percent': 0,
            'updated_at': datetime.now().isoformat()
        }, f, indent=2)
    
    return queue_data


def load_email_queue(folder_name):
    """Load email queue data."""
    queue_file = get_email_queue_file_path(folder_name)
    if os.path.exists(queue_file):
        try:
            with open(queue_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading email queue: {e}")
    return None


def load_email_progress(folder_name):
    """Load email progress data."""
    progress_file = get_email_progress_file_path(folder_name)
    if os.path.exists(progress_file):
        try:
            with open(progress_file, 'r') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading email progress: {e}")
    return None


def save_email_progress(folder_name, progress):
    """Save email progress data."""
    progress_file = get_email_progress_file_path(folder_name)
    progress['updated_at'] = datetime.now().isoformat()
    with open(progress_file, 'w') as f:
        json.dump(progress, f, indent=2)


def update_queue_item_status(folder_name, member_id, status, error=None):
    """Update the status of a specific item in the queue and recalculate progress."""
    queue_data = load_email_queue(folder_name)
    if not queue_data:
        return
    
    for item in queue_data['items']:
        if item['member_id'] == member_id:
            item['status'] = status
            if status == 'sent':
                item['sent_at'] = datetime.now().isoformat()
            if error:
                item['error'] = error
            break
    
    # Recalculate counts
    total = len(queue_data['items'])
    sent = sum(1 for i in queue_data['items'] if i['status'] == 'sent')
    failed = sum(1 for i in queue_data['items'] if i['status'] == 'failed')
    pending = total - sent - failed
    done = sent + failed
    percent = int((done / total) * 100) if total > 0 else 0
    
    # Update queue data with counts
    queue_data['sent'] = sent
    queue_data['failed'] = failed
    queue_data['pending'] = pending
    
    # Save updated queue (includes items with member_name)
    queue_file = get_email_queue_file_path(folder_name)
    with open(queue_file, 'w') as f:
        json.dump(queue_data, f, indent=2)
    
    # Save progress (without items to keep it small, items come from queue file)
    progress = {
        'folder': folder_name,
        'status': 'running' if pending > 0 else 'completed',
        'total': total,
        'sent': sent,
        'failed': failed,
        'pending': pending,
        'current': member_id if status == 'sending' else None,
        'percent': percent,
        'updated_at': datetime.now().isoformat()
    }
    save_email_progress(folder_name, progress)


def _email_worker(folder_name):
    """Background worker that processes the email queue."""
    print(f"[EmailWorker] Starting background processing for {folder_name}")
    
    with app.app_context():
        queue_data = load_email_queue(folder_name)
        if not queue_data:
            print(f"[EmailWorker] No queue found for {folder_name}")
            return
        
        queue_data['status'] = 'running'
        queue_file = get_email_queue_file_path(folder_name)
        with open(queue_file, 'w') as f:
            json.dump(queue_data, f, indent=2)
        
        # Parse year and quarter from folder name
        folder_parts = folder_name.replace('_bills_', '').split('-')
        year = folder_parts[0] if len(folder_parts) > 0 else str(datetime.now().year)
        quarter = folder_parts[1].replace('Q', '') if len(folder_parts) > 1 and folder_parts[1].startswith('Q') else '1'
        
        test_mode = queue_data.get('test_mode', False)
        
        for item in queue_data['items']:
            if item['status'] != 'pending':
                continue
            
            member_id = item['member_id']
            filepath = item['filepath']
            
            # Update status to sending
            update_queue_item_status(folder_name, member_id, 'sending')
            
            try:
                member = Member.query.get(member_id)
                if not member:
                    update_queue_item_status(folder_name, member_id, 'failed', 'Member not found')
                    continue
                
                # Send the email
                success, message, was_test = send_bill_email(
                    member_email=member.email,
                    member_name=f"{member.firstname} {member.name}".strip(),
                    bill_path=filepath,
                    year=year,
                    quarter=quarter,
                    is_resend=False,
                    test_mode=test_mode
                )
                
                if success:
                    update_queue_item_status(folder_name, member_id, 'sent')
                    print(f"[EmailWorker] Sent to {member.firstname} {member.name}: {message}")
                else:
                    update_queue_item_status(folder_name, member_id, 'failed', message)
                    print(f"[EmailWorker] Failed for {member.firstname} {member.name}: {message}")
                
                # Small delay to avoid overwhelming SMTP server
                time.sleep(2)
                
            except Exception as e:
                update_queue_item_status(folder_name, member_id, 'failed', str(e))
                print(f"[EmailWorker] Exception for member {member_id}: {e}")
                time.sleep(2)
        
        # Mark queue as completed
        queue_data = load_email_queue(folder_name)
        if queue_data:
            queue_data['status'] = 'completed'
            with open(queue_file, 'w') as f:
                json.dump(queue_data, f, indent=2)
            
            progress = load_email_progress(folder_name)
            if progress:
                progress['status'] = 'completed'
                progress['percent'] = 100
                save_email_progress(folder_name, progress)
    
    print(f"[EmailWorker] Completed processing for {folder_name}")
    
    print(f"[EmailWorker] Completed processing for {folder_name}")


def start_email_worker(folder_name):
    """Start the background email worker thread."""
    global _email_worker_thread
    
    with _email_worker_lock:
        # Check if a worker is already running for this folder
        if _email_worker_thread and _email_worker_thread.is_alive():
            print(f"[EmailWorker] Worker already running for {folder_name}")
            return False
        
        _email_worker_thread = threading.Thread(
            target=_email_worker,
            args=(folder_name,),
            daemon=True,
            name=f"EmailWorker-{folder_name}"
        )
        _email_worker_thread.start()
        print(f"[EmailWorker] Started thread for {folder_name}")
        return True


@app.route('/accounting/bills/<folder>/send-queue', methods=['POST'])
def queue_bills_for_sending(folder):
    """POST endpoint to create email queue and start background processing.
    
    This replaces the old synchronous send_bills endpoint.
    """
    try:
        # Get parameters
        member_ids = request.form.getlist('selected_bills')
        send_all = request.form.get('send_all') == 'true'
        send_mode = request.form.get('send_mode', 'test')
        is_test_mode = (send_mode != 'live')
        
        folder_path = get_bill_folder_path(folder)
        if not os.path.exists(folder_path):
            return jsonify({'success': False, 'error': 'Folder not found'}), 404
        
        # Build list of bills to send
        bill_items = []
        for filename in os.listdir(folder_path):
            if not filename.startswith('_') and filename.endswith('.csv'):
                parts = filename.replace('.csv', '').split('_')
                member_id = None
                for part in reversed(parts):
                    if part.isdigit():
                        member_id = int(part)
                        break
                
                if member_id and (send_all or str(member_id) in member_ids):
                    # Check if already sent (unless resend)
                    status = load_bill_email_status(folder)
                    if not send_all and status.get(str(member_id), {}).get('status') == 'sent':
                        continue
                    
                    member = Member.query.get(member_id)
                    member_name = f"{member.firstname} {member.name}".strip() if member else f"Member {member_id}"
                    
                    bill_items.append({
                        'member_id': member_id,
                        'member_name': member_name,
                        'filename': filename,
                        'filepath': os.path.join(folder_path, filename)
                    })
        
        if not bill_items:
            return jsonify({'success': False, 'error': 'No bills to send'}), 400
        
        # Create queue
        queue_data = create_email_queue(folder, bill_items, test_mode=is_test_mode)
        
        # Start background worker
        started = start_email_worker(folder)
        
        return jsonify({
            'success': True,
            'message': f'Queue created with {len(bill_items)} bills. Background processing started.',
            'folder': folder,
            'total': len(bill_items),
            'test_mode': is_test_mode,
            'worker_started': started
        })
        
    except Exception as e:
        import traceback
        print(f"ERROR in queue_bills_for_sending: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/accounting/bills/<folder>/progress', methods=['GET'])
def get_email_progress(folder):
    """GET endpoint to check email sending progress."""
    try:
        progress = load_email_progress(folder)
        if not progress:
            return jsonify({'success': False, 'error': 'No progress found'}), 404
        
        # Also load queue to get detailed item status
        queue_data = load_email_queue(folder)
        if queue_data:
            progress['items'] = queue_data.get('items', [])
        
        return jsonify({
            'success': True,
            'progress': progress
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/accounting/bills/<folder>/cancel-queue', methods=['POST'])
def cancel_email_queue(folder):
    """POST endpoint to cancel the email queue."""
    try:
        queue_data = load_email_queue(folder)
        if queue_data:
            queue_data['status'] = 'cancelled'
            queue_file = get_email_queue_file_path(folder)
            with open(queue_file, 'w') as f:
                json.dump(queue_data, f, indent=2)
        
        progress = load_email_progress(folder)
        if progress:
            progress['status'] = 'cancelled'
            save_email_progress(folder, progress)
        
        return jsonify({'success': True, 'message': 'Queue cancelled'})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/accounting/bills/list')
def list_bill_folders():
    """List all generated bill folders."""
    try:
        base_dir = app.config.get('BILL_OUTPUT_DIR', os.path.join(os.getcwd(), 'bills'))
        
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
                    email_status = load_bill_email_status(folder_name)
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


# ==============================================================================
# BILL GENERATION FROM QUARTERLY REPORT (Legacy route compatibility)
# ==============================================================================
def import_quarterly_csv_to_db(filepath, year, quarter):
    """Import quarterly CSV data into accounting_quarterly table."""
    try:
        # Clear existing data for this year/quarter
        AccountingQuarterly.query.filter_by(
            aqYear=year, 
            aqQuarter=quarter
        ).delete()
        db.session.commit()
        
        # Parse CSV
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        
        # Find data section
        data_started = False
        imported_count = 0
        
        for line in lines:
            line = line.strip()
            if line.startswith('Nom,'):
                data_started = True
                continue
            if data_started and line and not line.startswith('TOTAL'):
                parts = line.split(',')
                if len(parts) >= 4:
                    try:
                        full_name = parts[0].strip()
                        cons_prod = float(parts[1]) if parts[1] else 0.0
                        member_fee = float(parts[2]) if parts[2] else 0.0
                        total_amount = float(parts[3]) if parts[3] else 0.0
                        
                        # Find member by name
                        # CSV format: "Lastname Firstname" - need to swap for DB
                        name_parts = full_name.rsplit(' ', 1)
                        if len(name_parts) == 2:
                            lastname, firstname_from_csv = name_parts[0].strip(), name_parts[1].strip()
                            # Map: CSV lastname -> DB name, CSV firstname -> DB firstname
                            firstname, name = firstname_from_csv, lastname
                        else:
                            firstname, name = full_name.strip(), ''
                        print(f"DEBUG: Looking up member: firstname='{firstname}', name='{name}'")
                        print(f"DEBUG: firstname repr: {repr(firstname)}, name repr: {repr(name)}")
                        print(f"DEBUG: firstname bytes: {firstname.encode('utf-8')}, name bytes: {name.encode('utf-8')}")
                        
                        # Check if member exists with detailed query
                        all_matches = Member.query.filter(
                            db.or_(
                                Member.firstname == firstname,
                                Member.firstname.like(f"%{firstname}%")
                            )
                        ).all()
                        print(f"DEBUG: Found {len(all_matches)} potential firstname matches")
                        for m in all_matches[:5]:
                            print(f"DEBUG: Match: id={m.id}, firstname='{m.firstname}', name='{m.name}'")
                            print(f"DEBUG: Match repr: firstname={repr(m.firstname)}, name={repr(m.name)}")
                        
                        # Case-insensitive comparison for name matching
                        member = Member.query.filter(
                            db.and_(
                                db.func.lower(Member.name) == name.lower(),
                                db.func.lower(Member.firstname) == firstname.lower()
                            )
                        ).first()
                        
                        if not member:
                            # Try with just firstname
                            member = Member.query.filter(Member.firstname == firstname).first()
                            print(f"DEBUG: Fallback by firstname only: {member}")
                        
                        if not member:
                            # Try with just name
                            member = Member.query.filter(Member.name == name).first()
                            print(f"DEBUG: Fallback by name only: {member}")
                        
                        if member:
                            # Create quarterly accounting record
                            print(f"DEBUG: Found member {member.id} for {full_name}, adding record.")
                            aq = AccountingQuarterly(
                                aqYear=year,
                                aqQuarter=quarter,
                                aqMemberID=member.id,
                                aqConsProd=cons_prod,
                                aqMemberFee=member_fee,
                                aqTotalAmount=total_amount,
                                aqSourceFile=os.path.basename(filepath)
                            )
                            db.session.add(aq)
                            imported_count += 1
                    except (ValueError, IndexError):
                        continue
        
        db.session.commit()
        return imported_count
        
    except Exception as e:
        db.session.rollback()
        print(f"Error importing CSV: {e}")
        return 0

@app.route('/accounting/quarterly_report/bills', methods=['POST'])
def generate_quarterly_bills():
    """
    POST endpoint to generate bills from quarterly report data.
    First imports CSV data to accounting_quarterly table, then queries it.
    """
    try:
        year = request.form.get('year', type=int)
        quarter = request.form.get('quarter', type=int)
        
        if not year or not quarter:
            flash('Year and quarter are required', 'error')
            return redirect('/accounting/quarterly_report')
        
        # Find the CSV file
        csv_filename = f"Quarterly_report_{year}_Q{quarter}.csv"
        csv_path = os.path.join('/app/data', csv_filename)
        
        if not os.path.exists(csv_path):
            flash(f'CSV file not found: {csv_filename}', 'error')
            return redirect('/accounting/quarterly_report')
        
        # Import CSV to database
        imported = import_quarterly_csv_to_db(csv_path, year, quarter)
        print(f"DEBUG: Imported {imported} records from {csv_filename}")
        
        if imported == 0:
            flash('No data could be imported from CSV file', 'warning')
            return redirect('/accounting/quarterly_report')
        
        # Now query the imported data
        quarterly_data = AccountingQuarterly.query.filter_by(
            aqYear=year,
            aqQuarter=quarter
        ).all()
        
        # Create bills folder
        folder_name = f"_bills_{year}-Q{quarter}"
        folder_path = os.path.join(app.config.get('BILL_OUTPUT_DIR', '/app/data/databills'), folder_name)
        os.makedirs(folder_path, exist_ok=True)
        
        # Generate bills with monthly breakdown
        bills = []
        for aq in quarterly_data:
            member = aq.member
            if member:
                bill_filename = f"Bill_{year}_Q{quarter}_{member.firstname}_{member.name}_{member.id}.csv"
                bill_path = os.path.join(folder_path, bill_filename)
                
                # Get monthly accounting data for this member
                months_in_quarter = get_quarter_months(quarter)
                
                with open(bill_path, 'w', newline='') as f:
                    writer = csv.writer(f, delimiter=';')
                    # Header with member info
                    writer.writerow(['Name', member.name])
                    writer.writerow(['Firstname', member.firstname])
                    writer.writerow(['Year', year])
                    writer.writerow(['Quarter', f"Q{quarter}"])
                    writer.writerow([])  # Empty row
                    # Column headers
                    writer.writerow(['Period', 'kWh', 'Price per kWh (EUR)', 'Amount (EUR)'])
                    
                    total_amount = 0.0
                    total_kwh = 0.0
                    
                    for month in months_in_quarter:
                        # Get accounting records for this member/month
                        monthly_records = Accounting.query.filter_by(
                            accYear=year,
                            accMonth=month,
                            accMember=member.id
                        ).all()
                        
                        month_amount = sum(float(r.accAmount) for r in monthly_records)
                        
                        # Get sharing group price (from first record if available)
                        sg_price = 0
                        if monthly_records:
                            sg = SharingGroup.query.get(monthly_records[0].accSGId)
                            if sg and sg.sgPrice:
                                sg_price = float(sg.sgPrice)
                        
                        # Calculate kWh (handle division by zero)
                        if sg_price > 0:
                            kwh = round(month_amount / sg_price, 2)
                        else:
                            kwh = 0
                        
                        month_name = datetime(year, month, 1).strftime('%B %Y')
                        writer.writerow([month_name, f"{kwh} kWh", f"{sg_price} EUR", f"{round(month_amount, 2)} EUR"])
                        
                        total_amount += month_amount
                        total_kwh += kwh
                    
                    # Check if member fee is unpaid for this year
                    member_fee_amount = 0.0
                    member_fee_unpaid = False
                    
                    # Find member fee for this year
                    member_fee = MemberFee.query.filter_by(mfYear=year).first()
                    if member_fee:
                        # Check if member has paid
                        payment = MemberFeePayment.query.filter_by(
                            memberID=member.id,
                            memberFeeID=member_fee.mfID
                        ).first()
                        
                        if not payment or payment.paymentStatus != 'paid':
                            member_fee_amount = float(member_fee.mfamount)
                            member_fee_unpaid = True
                    
                    # Add member fee line if unpaid
                    if member_fee_unpaid:
                        writer.writerow([])  # Empty row
                        writer.writerow([f'Member fee {year}', '', '', f'{round(member_fee_amount, 2)} EUR'])
                        total_amount += member_fee_amount
                    
                    # Add total row
                    writer.writerow([])  # Empty row
                    writer.writerow(['Total', f"{round(total_kwh, 2)} kWh", '', f"{round(total_amount, 2)} EUR"])
                
                bills.append({
                    'member_id': member.id,
                    'filename': bill_filename
                })
        
        # Initialize email status
        email_status = {}
        for bill in bills:
            email_status[str(bill['member_id'])] = {
                'status': 'pending',
                'sent_at': None,
                'error': None,
                'attempts': 0
            }
        
        save_bill_email_status(folder_name, email_status)
        
        flash(f"Successfully generated {len(bills)} bills.", 'success')
        print(f"DEBUG: About to redirect to /accounting/bills/{folder_name}/review")
        redirect_url = f'/accounting/bills/{folder_name}/review'
        print(f"DEBUG: Redirect URL: {redirect_url}")
        return redirect(redirect_url)
        
    except Exception as e:
        import traceback
        flash(f'Error generating bills: {str(e)}', 'error')
        print(f"ERROR: {str(e)}")
        print(traceback.format_exc())
        return redirect('/accounting/quarterly_report')


@app.route('/accounting/bills/<folder>/review', methods=['GET'])
def review_bills(folder):
    """
    GET endpoint to show bills and their email status.
    """
    print(f"DEBUG: review_bills called with folder={folder}")
    try:
        folder_path = get_bill_folder_path(folder)
        print(f"DEBUG: folder_path={folder_path}, exists={os.path.exists(folder_path)}")
        
        if not os.path.exists(folder_path):
            flash(f'Bill folder not found: {folder}', 'error')
            print(f"DEBUG: Folder not found, redirecting to quarterly_report")
            return redirect('/accounting/quarterly_report')
        
        # Parse year and quarter from folder name
        folder_parts = folder.replace('_bills_', '').split('-')
        year = folder_parts[0] if len(folder_parts) > 0 else 'Unknown'
        quarter = folder_parts[1] if len(folder_parts) > 1 else 'Unknown'
        
        # Load email status
        email_status = load_bill_email_status(folder)
        
        # Get all files in the folder
        bills = []
        for filename in os.listdir(folder_path):
            if not filename.startswith('_'):
                # Extract member info from filename
                parts = filename.replace('.csv', '').replace('.pdf', '').split('_')
                
                # Find member_id (last numeric part)
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
                
                # Get member name from database for proper formatting (Name Firstname)
                member = Member.query.get(member_id) if member_id else None
                if member:
                    member_name = f"{member.name} {member.firstname}"
                elif len(parts) >= 4:
                    # Fallback to filename parsing (reversing firstname name to name firstname)
                    name_parts = parts[3:-1] if parts[-1].isdigit() else parts[3:]
                    # Filename format is "Firstname_Name" so swap
                    if len(name_parts) >= 2:
                        member_name = f"{name_parts[-1]} {name_parts[0]}"
                    else:
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
        
        return render_template('accounting/bill_review.html',
                               folder=folder,
                               year=year,
                               quarter=quarter,
                               bills=bills,
                               total_bills=total_bills,
                               sent_bills=sent_bills,
                               pending_bills=pending_bills,
                               failed_bills=failed_bills)
        
    except Exception as e:
        import traceback
        flash(f'Error loading bill review: {str(e)}', 'error')
        print(f"DEBUG: Exception in review_bills: {str(e)}")
        print(traceback.format_exc())
        return redirect('/accounting/quarterly_report')


@app.route('/accounting/bills/<folder>/send', methods=['POST'])
def send_bills(folder):
    """
    POST endpoint to send bills via email.
    Now delegates to background queue system.
    """
    try:
        # Forward to the queue endpoint
        return queue_bills_for_sending(folder)
    except Exception as e:
        import traceback
        print(f"ERROR in send_bills: {e}")
        print(traceback.format_exc())
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/accounting/bills/<folder>/resend', methods=['POST'])
def resend_bill(folder):
    """
    POST endpoint to resend bills to members who previously failed.
    """
    try:
        import json
        from flask import request, jsonify
        
        # Check if this is an AJAX/JSON request or form POST
        if request.is_json:
            data = request.get_json()
            member_ids = data.get('member_ids', [])
        else:
            # Form data - get member_ids from form
            member_ids = request.form.getlist('member_ids')
        
        folder_path = get_bill_folder_path(folder)
        if not os.path.exists(folder_path):
            if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return jsonify({'success': False, 'error': 'Folder not found'}), 404
            else:
                flash('Folder not found', 'error')
                return redirect(f'/accounting/bills/{folder}/review')
        
        email_status = load_bill_email_status(folder)
        results = []
        sent_count = 0
        failed_count = 0
        
        for member_id in member_ids:
            member = Member.query.get(int(member_id))
            if not member:
                results.append({
                    'member_id': member_id,
                    'member_name': 'Unknown',
                    'success': False,
                    'message': 'Member not found'
                })
                failed_count += 1
                continue
            
            try:
                # Parse year and quarter from folder name
                folder_parts = folder.replace('_bills_', '').split('-')
                year = folder_parts[0] if len(folder_parts) > 0 else datetime.now().year
                quarter = folder_parts[1].replace('Q', '') if len(folder_parts) > 1 and folder_parts[1].startswith('Q') else '1'
                
                # Find the bill file for this member
                bill_filepath = None
                for filename in os.listdir(folder_path):
                    if not filename.startswith('_') and filename.endswith('.csv'):
                        parts = filename.replace('.csv', '').split('_')
                        file_member_id = None
                        for part in reversed(parts):
                            if part.isdigit():
                                file_member_id = int(part)
                                break
                        if file_member_id == int(member_id):
                            bill_filepath = os.path.join(folder_path, filename)
                            break
                
                if not bill_filepath:
                    raise Exception(f"Bill file not found for member {member_id}")
                
                # Send the email
                success, message, was_test = send_bill_email(
                    member_email=member.email,
                    member_name=f"{member.firstname} {member.name}".strip(),
                    bill_path=bill_filepath,
                    year=year,
                    quarter=quarter,
                    is_resend=True
                )
                
                if success and was_test:
                    results.append({
                        'member_id': member_id,
                        'member_name': f"{member.firstname} {member.name}",
                        'success': True,
                        'message': message,
                        'is_test': True
                    })
                    sent_count += 1
                    continue
                
                if success:
                    email_status[str(member_id)] = {
                        'status': 'sent',
                        'sent_at': datetime.now().isoformat(),
                        'error': None,
                        'attempts': email_status.get(str(member_id), {}).get('attempts', 0) + 1
                    }
                    
                    results.append({
                        'member_id': member_id,
                        'member_name': f"{member.firstname} {member.name}",
                        'success': True,
                        'message': message
                    })
                    sent_count += 1
                
                else:
                    email_status[str(member_id)] = {
                        'status': 'failed',
                        'sent_at': None,
                        'error': message,
                        'attempts': email_status.get(str(member_id), {}).get('attempts', 0) + 1
                    }
                    results.append({
                        'member_id': member_id,
                        'member_name': f"{member.firstname} {member.name}",
                        'success': False,
                        'message': message
                    })
                    failed_count += 1
                    
            except Exception as e:
                error_msg = str(e)
                email_status[str(member_id)] = {
                    'status': 'failed',
                    'sent_at': None,
                    'error': error_msg,
                    'attempts': email_status.get(str(member_id), {}).get('attempts', 0) + 1
                }
                results.append({
                    'member_id': member_id,
                    'member_name': f"{member.firstname} {member.name}",
                    'success': False,
                    'message': error_msg
                })
                failed_count += 1
        
        save_bill_email_status(folder, email_status)
        
        # Save to database
        try:
            from models import BillEmail, db
            folder_parts = folder.replace('_bills_', '').split('-')
            year = int(folder_parts[0]) if len(folder_parts) > 0 and folder_parts[0].isdigit() else datetime.now().year
            quarter_str = folder_parts[1] if len(folder_parts) > 1 else 'Q1'
            quarter = int(quarter_str.replace('Q', '')) if quarter_str.startswith('Q') else 1
            
            for result in results:
                member_id = result['member_id']
                if member_id == 'Unknown':
                    continue
                
                member = Member.query.get(member_id)
                member_email = member.email if member and member.email else None
                
                # Find existing record
                existing = BillEmail.query.filter_by(
                    beMemberID=member_id,
                    beYear=year,
                    beQuarter=quarter
                ).first()
                
                if existing:
                    existing.beStatus = 'sent' if result['success'] else 'failed'
                    if result['success']:
                        existing.beSentDate = datetime.now()
                        existing.beEmailTo = member_email
                    existing.beErrorMessage = result['message'] if not result['success'] else existing.beErrorMessage
                    if result['success']:
                        existing.beResendCount = (existing.beResendCount or 0) + 1
                    # Update filename if we have it
                    if existing.beFilename and not existing.beFilename.startswith('Bill_'):
                        # Try to find the actual filename
                        for filename in os.listdir(folder_path):
                            if not filename.startswith('_') and filename.endswith('.csv'):
                                parts = filename.replace('.csv', '').split('_')
                                file_member_id = None
                                for part in reversed(parts):
                                    if part.isdigit():
                                        file_member_id = int(part)
                                        break
                                if file_member_id == int(member_id):
                                    existing.beFilename = filename
                                    break
                else:
                    # Create new record
                    bill_filename = ''
                    for filename in os.listdir(folder_path):
                        if not filename.startswith('_') and filename.endswith('.csv'):
                            parts = filename.replace('.csv', '').split('_')
                            file_member_id = None
                            for part in reversed(parts):
                                if part.isdigit():
                                    file_member_id = int(part)
                                    break
                            if file_member_id == int(member_id):
                                bill_filename = filename
                                break
                    
                    bill_email = BillEmail(
                        beMemberID=member_id,
                        beYear=year,
                        beQuarter=quarter,
                        beFilename=bill_filename,
                        beSentDate=datetime.now() if result['success'] else None,
                        beEmailTo=member_email,
                        beStatus='sent' if result['success'] else 'failed',
                        beErrorMessage=result['message'] if not result['success'] else None,
                        beResendCount=1 if result['success'] else 0
                    )
                    db.session.add(bill_email)
            
            db.session.commit()
            print(f"DEBUG: Saved {len(results)} resend records to database")
        except Exception as db_error:
            print(f"Warning: Could not save resend to database: {db_error}")
            import traceback
            traceback.print_exc()
            try:
                db.session.rollback()
            except:
                pass
        
        # Return JSON for AJAX, redirect for form POST
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({
                'success': True,
                'sent_count': sent_count,
                'failed_count': failed_count,
                'results': results
            })
        else:
            if sent_count > 0:
                flash(f'Successfully resent {sent_count} bills.', 'success')
            if failed_count > 0:
                flash(f'Failed to resend {failed_count} bills.', 'warning')
            return redirect(f'/accounting/bills/{folder}/review')
        
    except Exception as e:
        import traceback
        print(f"ERROR in resend_bill: {e}")
        print(traceback.format_exc())
        if request.is_json or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'error': str(e)}), 500
        else:
            flash(f'Error resending bills: {str(e)}', 'error')
            return redirect(f'/accounting/bills/{folder}/review')


@app.route('/accounting/bills/<folder>/download/<filename>')
def download_bill(folder, filename):
    """
    Download a specific bill file.
    """
    try:
        folder_path = get_bill_folder_path(folder)
        file_path = os.path.join(folder_path, filename)
        
        # Security check - ensure file is within the folder
        if not os.path.abspath(file_path).startswith(os.path.abspath(folder_path)):
            flash('Invalid file path', 'error')
            return redirect('/accounting/quarterly_report')
        
        if not os.path.exists(file_path):
            flash('File not found', 'error')
            return redirect('/accounting/quarterly_report')
        
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        flash(f'Error downloading file: {str(e)}', 'error')
        return redirect('/accounting/quarterly_report')


# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)
else:
    # Print all registered routes when loaded by gunicorn
    print("\n" + "=" * 70)
    print("REGISTERED ROUTES:")
    print("=" * 70)
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith('static'):
            methods = ','.join(sorted(rule.methods - {'OPTIONS', 'HEAD'}))
            print(f"{methods:20s} {str(rule):50s} -> {rule.endpoint}")
    print("=" * 70 + "\n")