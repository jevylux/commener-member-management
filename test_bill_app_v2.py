#!/usr/bin/env python3
"""
Enhanced Test Bill Viewer Application V2
Handles quarterly report CSV with payment direction logic and database integration.
"""

from flask import Flask, render_template_string, request, jsonify
import csv
import io
import os
import json
import re
from datetime import datetime

app = Flask(__name__)

# Configuration
DATA_DIR = "/tmp/test_bills_v2"
os.makedirs(DATA_DIR, exist_ok=True)

# Default bank account for receiving payments
DEFAULT_BANK_ACCOUNT = "LU12 0019 1303 5350 3000"
DEFAULT_BANK_BIC = "BCEELULLXXX"
DEFAULT_PAYCONIQ_NUMBER = "661196114"

# Email status storage
STATUS_FILE = os.path.join(DATA_DIR, "_email_status.json")

def load_status():
    """Load email sending status."""
    if os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_status(status):
    """Save email sending status."""
    with open(STATUS_FILE, 'w') as f:
        json.dump(status, f, indent=2)

def parse_name(full_name):
    """Parse full name into firstname and name."""
    parts = full_name.strip().split()
    if len(parts) >= 2:
        # Last part is usually the last name, rest is firstname
        name = parts[-1]
        firstname = ' '.join(parts[:-1])
    else:
        name = full_name
        firstname = ""
    return firstname, name

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
                full_name = parts[0].strip()
                cons_prod = float(parts[1]) if parts[1] else 0.0
                member_fee = float(parts[2]) if parts[2] else 0.0
                amount = float(parts[3]) if parts[3] else 0.0
                
                firstname, name = parse_name(full_name)
                
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
    
    return bills, year, quarter

def get_member_payment_info(fullname):
    """
    Mock function - in real implementation, query the database.
    Returns payment method and details for a member.
    """
    # This would query the Member table in the real app
    # For testing, return simulated data
    payment_methods = {
        'Durbach Marc': {'payment': 'Payconiq', 'payconiq': '661196114', 'bank': '', 'phone': '661196114'},
        'Adams Viviane': {'payment': 'Bank', 'payconiq': '', 'bank': 'LUXX XXXX XXXX XXXX', 'phone': '123456789'},
        'Amzolini Madalin Francis': {'payment': 'Payconiq', 'payconiq': '691234567', 'bank': '', 'phone': '691234567'},
    }
    
    # Default if not found
    return payment_methods.get(fullname, {
        'payment': 'Bank',
        'payconiq': '',
        'bank': 'LUXX XXXX XXXX XXXX',
        'phone': ''
    })

def generate_email_content(bill, member_info):
    """Generate email content based on payment direction and method."""
    fullname = f"{bill['firstname']} {bill['name']}".strip()
    year = bill['year']
    quarter = bill['quarter']
    amount = f"{bill['abs_amount']:.2f}"
    
    # Determine payment details based on direction and method
    if bill['direction'] == 'pay':
        # Member needs to pay
        direction_text = "Vous devez payer"
        direction_text_en = "You need to pay"
        direction_text_lu = "Dir musst bezuelen"
        
        if member_info['payment'] == 'Payconiq':
            payment_instruction = f"Veuillez effectuer le paiement de {amount}€ via Payconiq au numéro {DEFAULT_PAYCONIQ_NUMBER}"
            payment_instruction_en = f"Please make the payment of {amount}€ via Payconiq to number {DEFAULT_PAYCONIQ_NUMBER}"
            payment_instruction_lu = f"Bezuelt w.e.g. {amount}€ iwwer Payconiq op d'Nummer {DEFAULT_PAYCONIQ_NUMBER}"
        else:
            payment_instruction = f"Veuillez effectuer le virement de {amount}€ sur le compte: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
            payment_instruction_en = f"Please transfer {amount}€ to account: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
            payment_instruction_lu = f"Iwwerweist w.e.g. {amount}€ op d'Konto: {DEFAULT_BANK_ACCOUNT} BIC: {DEFAULT_BANK_BIC}"
    else:
        # Member will receive money
        direction_text = "Vous allez recevoir"
        direction_text_en = "You will receive"
        direction_text_lu = "Dir kritt"
        
        if member_info['payment'] == 'Payconiq':
            payconiq_num = member_info.get('payconiq') or member_info.get('phone', 'votre numéro Payconiq')
            payment_instruction = f"Vous recevrez {amount}€ sur votre compte Payconiq ({payconiq_num})"
            payment_instruction_en = f"You will receive {amount}€ on your Payconiq account ({payconiq_num})"
            payment_instruction_lu = f"Dir kritt {amount}€ op Äre Payconiq Kont ({payconiq_num})"
        else:
            bank_account = member_info.get('bank', 'votre compte bancaire')
            payment_instruction = f"Vous recevrez {amount}€ sur votre compte bancaire: {bank_account}"
            payment_instruction_en = f"You will receive {amount}€ on your bank account: {bank_account}"
            payment_instruction_lu = f"Dir kritt {amount}€ op Äre Bankkonto: {bank_account}"
    
    email_body = f"""Dear {fullname},

Regarding your bill for {quarter} {year}:

{direction_text_en}: {amount}€
{payment_instruction_en}

Consumption/Production: {bill['cons_prod']:.2f}€
Membership Fee: {bill['member_fee']:.2f}€
Net Amount: {bill['amount']:.2f}€

Best regards,
Communauté Energétique

---

Cher/Chère {fullname},

Concernant votre facture pour {quarter} {year}:

{direction_text}: {amount}€
{payment_instruction}

Consommation/Production: {bill['cons_prod']:.2f}€
Carte de Membre: {bill['member_fee']:.2f}€
Montant Net: {bill['amount']:.2f}€

Cordialement,
Communauté Energétique

---

Léif {fullname},

Bezüglech Är Rechnung fir {quarter} {year}:

{direction_text_lu}: {amount}€
{payment_instruction_lu}

Verbrauch/Produktioun: {bill['cons_prod']:.2f}€
Memberkaart: {bill['member_fee']:.2f}€
Nettobedrag: {bill['amount']:.2f}€

Mat beschte Gréiss,
Communauté Energétique
"""
    
    return email_body

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bill Viewer V2 - Quarterly Report</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        h1 { color: #333; }
        h2 { color: #666; margin-top: 30px; }
        .upload-form {
            background: #f5f5f5;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .upload-form input[type="file"] {
            margin: 10px 0;
        }
        .upload-form input[type="submit"] {
            background: #4CAF50;
            color: white;
            padding: 10px 20px;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        .upload-form input[type="submit"]:hover {
            background: #45a049;
        }
        table {
            border-collapse: collapse;
            width: 100%;
            margin-top: 20px;
        }
        th, td {
            border: 1px solid #ddd;
            padding: 12px;
            text-align: left;
        }
        th {
            background-color: #4CAF50;
            color: white;
        }
        tr:nth-child(even) {
            background-color: #f2f2f2;
        }
        tr:hover {
            background-color: #ddd;
        }
        .status-pending {
            color: #ff9800;
            font-weight: bold;
        }
        .status-sent {
            color: #4CAF50;
            font-weight: bold;
        }
        .status-failed {
            color: #f44336;
            font-weight: bold;
        }
        .amount {
            text-align: right;
            font-family: monospace;
        }
        .direction-pay {
            color: #f44336;
            font-weight: bold;
        }
        .direction-receive {
            color: #4CAF50;
            font-weight: bold;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin: 20px 0;
            flex-wrap: wrap;
        }
        .stat-box {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            text-align: center;
            min-width: 120px;
        }
        .stat-box .number {
            font-size: 24px;
            font-weight: bold;
            color: #333;
        }
        .stat-box .label {
            font-size: 12px;
            color: #666;
        }
        .no-data {
            text-align: center;
            color: #999;
            padding: 40px;
        }
        .btn {
            padding: 5px 10px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
            text-decoration: none;
            display: inline-block;
        }
        .btn-send {
            background: #2196F3;
            color: white;
        }
        .btn-preview {
            background: #9C27B0;
            color: white;
        }
        .btn-resend {
            background: #FF9800;
            color: white;
        }
        .payment-method {
            font-size: 11px;
            color: #666;
            font-style: italic;
        }
        .modal {
            display: none;
            position: fixed;
            z-index: 1;
            left: 0;
            top: 0;
            width: 100%;
            height: 100%;
            overflow: auto;
            background-color: rgba(0,0,0,0.4);
        }
        .modal-content {
            background-color: #fefefe;
            margin: 5% auto;
            padding: 20px;
            border: 1px solid #888;
            width: 80%;
            max-width: 800px;
            border-radius: 5px;
        }
        .close {
            color: #aaa;
            float: right;
            font-size: 28px;
            font-weight: bold;
            cursor: pointer;
        }
        .close:hover {
            color: black;
        }
        pre {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            overflow-x: auto;
            white-space: pre-wrap;
            word-wrap: break-word;
        }
    </style>
</head>
<body>
    <h1>📄 Bill Viewer V2 - Quarterly Report</h1>
    
    <div class="upload-form">
        <h3>Upload Quarterly Report CSV</h3>
        <p>Expected format: Quarterly report with columns: Nom, Total Cons ou Prod, Carte de Membre, Montant Total à Payer</p>
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="csv_file" accept=".csv" required>
            <input type="submit" value="Process Report">
        </form>
    </div>
    
    {% if bills %}
    <h2>Report: {{ year }} {{ quarter }}</h2>
    
    <div class="stats">
        <div class="stat-box">
            <div class="number">{{ total_bills }}</div>
            <div class="label">Total Members</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #f44336;">{{ to_pay_count }}</div>
            <div class="label">Need to Pay</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #4CAF50;">{{ to_receive_count }}</div>
            <div class="label">Will Receive</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #4CAF50;">{{ "%.2f"|format(total_to_receive) }}€</div>
            <div class="label">Total to Pay Out</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #f44336;">{{ "%.2f"|format(total_to_pay) }}€</div>
            <div class="label">Total to Collect</div>
        </div>
        <div class="stat-box">
            <div class="number">{{ sent_count }}</div>
            <div class="label">Emails Sent</div>
        </div>
    </div>
    
    <form method="POST" action="/send-emails" id="sendForm">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="selectAll" onclick="toggleAll()"></th>
                    <th>Name</th>
                    <th>Cons/Prod</th>
                    <th>Member Fee</th>
                    <th>Amount</th>
                    <th>Direction</th>
                    <th>Payment Method</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for bill in bills %}
                <tr>
                    <td><input type="checkbox" name="selected" value="{{ bill.id }}"></td>
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
                    <td class="payment-method">{{ bill.payment_method }}</td>
                    <td>
                        {% if bill.status == 'sent' %}
                        <span class="status-sent">✓ Sent</span>
                        {% elif bill.status == 'failed' %}
                        <span class="status-failed">✗ Failed</span>
                        {% else %}
                        <span class="status-pending">⏳ Pending</span>
                        {% endif %}
                    </td>
                    <td>
                        <button type="button" class="btn btn-preview" onclick="showPreview('{{ bill.id }}')">Preview</button>
                        {% if bill.status == 'sent' %}
                        <button type="button" class="btn btn-resend" onclick="resendEmail('{{ bill.id }}')">Resend</button>
                        {% else %}
                        <button type="button" class="btn btn-send" onclick="sendEmail('{{ bill.id }}')">Send</button>
                        {% endif %}
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        
        <div style="margin-top: 20px;">
            <button type="submit" class="btn btn-send" style="font-size: 14px; padding: 10px 20px;">
                Send Selected Emails
            </button>
        </div>
    </form>
    
    <div id="previewModal" class="modal">
        <div class="modal-content">
            <span class="close" onclick="closeModal()">&times;</span>
            <h2>Email Preview</h2>
            <pre id="previewContent"></pre>
        </div>
    </div>
    
    <script>
        function toggleAll() {
            var checkboxes = document.querySelectorAll('input[name="selected"]');
            var selectAll = document.getElementById('selectAll');
            checkboxes.forEach(cb => cb.checked = selectAll.checked);
        }
        
        function showPreview(billId) {
            fetch('/preview/' + billId)
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
            if (event.target == modal) {
                modal.style.display = 'none';
            }
        }
        
        function sendEmail(id) {
            fetch('/send-email/' + id, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
        
        function resendEmail(id) {
            fetch('/resend-email/' + id, { method: 'POST' })
                .then(r => r.json())
                .then(data => {
                    alert(data.message);
                    location.reload();
                });
        }
    </script>
    {% else %}
    <div class="no-data">
        <h3>No report loaded yet</h3>
        <p>Upload a quarterly report CSV to see generated bills</p>
    </div>
    {% endif %}
</body>
</html>
"""

# Global storage for current bills
CURRENT_BILLS = {}

@app.route('/')
def index():
    """Main page showing bills."""
    status = load_status()
    
    # Load the most recent CSV file
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and not f.startswith('_')]
    
    bills = []
    year = None
    quarter = None
    
    if csv_files:
        # Sort by modification time (newest first)
        csv_files.sort(key=lambda f: os.path.getmtime(os.path.join(DATA_DIR, f)), reverse=True)
        latest_file = os.path.join(DATA_DIR, csv_files[0])
        
        try:
            bills, year, quarter = parse_quarterly_csv(latest_file)
            
            # Enrich bills with payment info and status
            for bill in bills:
                member_info = get_member_payment_info(bill['fullname'])
                bill['payment_method'] = member_info['payment']
                bill['payment_details'] = member_info
                bill['status'] = status.get(bill['id'], 'pending')
                CURRENT_BILLS[bill['id']] = bill
                
        except Exception as e:
            print(f"Error parsing CSV: {e}")
    
    # Calculate stats
    total_bills = len(bills)
    to_pay_count = sum(1 for b in bills if b['direction'] == 'pay')
    to_receive_count = sum(1 for b in bills if b['direction'] == 'receive')
    total_to_pay = sum(b['abs_amount'] for b in bills if b['direction'] == 'pay')
    total_to_receive = sum(b['abs_amount'] for b in bills if b['direction'] == 'receive')
    sent_count = sum(1 for b in bills if b['status'] == 'sent')
    
    return render_template_string(HTML_TEMPLATE,
                                  bills=bills,
                                  year=year,
                                  quarter=quarter,
                                  total_bills=total_bills,
                                  to_pay_count=to_pay_count,
                                  to_receive_count=to_receive_count,
                                  total_to_pay=total_to_pay,
                                  total_to_receive=total_to_receive,
                                  sent_count=sent_count)

@app.route('/upload', methods=['POST'])
def upload():
    """Handle CSV file upload."""
    if 'csv_file' not in request.files:
        return "No file uploaded", 400
    
    file = request.files['csv_file']
    if file.filename == '':
        return "No file selected", 400
    
    if file and file.filename.endswith('.csv'):
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"quarterly_report_{timestamp}.csv"
        filepath = os.path.join(DATA_DIR, filename)
        file.save(filepath)
        return f"""
        <h2>File uploaded successfully!</h2>
        <p>Saved as: {filename}</p>
        <p><a href="/">View Report</a></p>
        """
    
    return "Invalid file type", 400

@app.route('/preview/<bill_id>')
def preview_email(bill_id):
    """Preview email content for a bill."""
    bill = CURRENT_BILLS.get(bill_id)
    if not bill:
        return jsonify({'error': 'Bill not found'}), 404
    
    member_info = get_member_payment_info(bill['fullname'])
    email_body = generate_email_content(bill, member_info)
    
    return jsonify({'email_body': email_body})

@app.route('/send-email/<bill_id>', methods=['POST'])
def send_email(bill_id):
    """Send email for a specific bill."""
    bill = CURRENT_BILLS.get(bill_id)
    if not bill:
        return jsonify({'success': False, 'message': 'Bill not found'}), 404
    
    status = load_status()
    
    # Simulate sending email (would actually send in production)
    import random
    success = random.random() > 0.1  # 90% success rate
    
    if success:
        status[bill_id] = 'sent'
        message = f"Email sent to {bill['fullname']}"
    else:
        status[bill_id] = 'failed'
        message = f"Failed to send email to {bill['fullname']}"
    
    save_status(status)
    return jsonify({'success': success, 'message': message})

@app.route('/resend-email/<bill_id>', methods=['POST'])
def resend_email(bill_id):
    """Resend email for a specific bill."""
    return send_email(bill_id)

@app.route('/send-emails', methods=['POST'])
def send_emails():
    """Send emails for selected bills."""
    selected = request.form.getlist('selected')
    status = load_status()
    
    import random
    sent = 0
    failed = 0
    
    for bill_id in selected:
        success = random.random() > 0.1
        if success:
            status[bill_id] = 'sent'
            sent += 1
        else:
            status[bill_id] = 'failed'
            failed += 1
    
    save_status(status)
    
    return f"""
    <h2>Email Sending Complete</h2>
    <p>Sent: {sent}, Failed: {failed}</p>
    <p><a href="/">Back to Report</a></p>
    """

if __name__ == '__main__':
    print("=" * 60)
    print("Enhanced Bill Viewer V2 Application")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print("URL: http://localhost:8766")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8766, debug=True)
