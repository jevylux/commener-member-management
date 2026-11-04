#!/usr/bin/env python3
"""
Test Bill Viewer Application
A simple Flask app to test bill generation from CSV and email status tracking.
"""

from flask import Flask, render_template_string, request, jsonify
import csv
import io
import os
import json
from datetime import datetime

app = Flask(__name__)

# Configuration
DATA_DIR = "/tmp/test_bills"
os.makedirs(DATA_DIR, exist_ok=True)

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

# HTML Template
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Bill Viewer Test</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 1200px;
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
        .grand-total {
            font-weight: bold;
            background-color: #e0e0e0 !important;
        }
        .btn {
            padding: 5px 10px;
            border: none;
            border-radius: 3px;
            cursor: pointer;
            font-size: 12px;
        }
        .btn-send {
            background: #2196F3;
            color: white;
        }
        .btn-resend {
            background: #FF9800;
            color: white;
        }
        .stats {
            display: flex;
            gap: 20px;
            margin: 20px 0;
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
    </style>
</head>
<body>
    <h1>📄 Bill Viewer Test Application</h1>
    
    <div class="upload-form">
        <h3>Upload CSV File</h3>
        <p>Expected format: Nom, Prénom, Montant (with header row)</p>
        <form method="POST" action="/upload" enctype="multipart/form-data">
            <input type="file" name="csv_file" accept=".csv" required>
            <input type="submit" value="Generate Bills">
        </form>
    </div>
    
    {% if bills %}
    <div class="stats">
        <div class="stat-box">
            <div class="number">{{ total_bills }}</div>
            <div class="label">Total Bills</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #4CAF50;">{{ sent_count }}</div>
            <div class="label">Sent</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #ff9800;">{{ pending_count }}</div>
            <div class="label">Pending</div>
        </div>
        <div class="stat-box">
            <div class="number" style="color: #f44336;">{{ failed_count }}</div>
            <div class="label">Failed</div>
        </div>
        <div class="stat-box">
            <div class="number">{{ "%.2f"|format(grand_total) }}€</div>
            <div class="label">Grand Total</div>
        </div>
    </div>
    
    <form method="POST" action="/send-emails" id="sendForm">
        <table>
            <thead>
                <tr>
                    <th><input type="checkbox" id="selectAll" onclick="toggleAll()"></th>
                    <th>Name</th>
                    <th>Firstname</th>
                    <th>Amount</th>
                    <th>Status</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for bill in bills %}
                <tr {% if bill.is_total %}class="grand-total"{% endif %}>
                    <td>
                        {% if not bill.is_total %}
                        <input type="checkbox" name="selected" value="{{ bill.id }}">
                        {% endif %}
                    </td>
                    <td>{{ bill.name }}</td>
                    <td>{{ bill.firstname }}</td>
                    <td class="amount">{{ "%.2f"|format(bill.amount) }}€</td>
                    <td>
                        {% if bill.is_total %}
                            -
                        {% elif bill.status == 'sent' %}
                            <span class="status-sent">✓ Sent</span>
                        {% elif bill.status == 'failed' %}
                            <span class="status-failed">✗ Failed</span>
                        {% else %}
                            <span class="status-pending">⏳ Pending</span>
                        {% endif %}
                    </td>
                    <td>
                        {% if not bill.is_total %}
                            {% if bill.status == 'sent' %}
                            <button type="button" class="btn btn-resend" onclick="resendEmail({{ bill.id }})">Resend</button>
                            {% else %}
                            <button type="button" class="btn btn-send" onclick="sendEmail({{ bill.id }})">Send</button>
                            {% endif %}
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
    
    <script>
        function toggleAll() {
            var checkboxes = document.querySelectorAll('input[name="selected"]');
            var selectAll = document.getElementById('selectAll');
            checkboxes.forEach(cb => cb.checked = selectAll.checked);
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
        <h3>No bills loaded yet</h3>
        <p>Upload a CSV file to see generated bills</p>
    </div>
    {% endif %}
</body>
</html>
"""

@app.route('/')
def index():
    """Main page showing bills."""
    bills = []
    status = load_status()
    
    # Load CSV files from data directory
    csv_files = [f for f in os.listdir(DATA_DIR) if f.endswith('.csv') and not f.startswith('_')]
    
    grand_total = 0
    for csv_file in sorted(csv_files, reverse=True):
        filepath = os.path.join(DATA_DIR, csv_file)
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                reader = csv.reader(f, delimiter=';')
                header = next(reader, None)  # Skip header
                
                for row in reader:
                    if len(row) >= 3:
                        try:
                            amount = float(row[2].replace(',', '.'))
                            bill_id = f"{csv_file}_{row[0]}_{row[1]}"
                            
                            # Check if this is a total row
                            is_total = row[0].lower() in ['total', 'totaal', 'totale']
                            
                            if not is_total:
                                grand_total += amount
                            
                            bills.append({
                                'id': bill_id,
                                'name': row[0],
                                'firstname': row[1],
                                'amount': amount,
                                'status': status.get(bill_id, 'pending'),
                                'is_total': is_total
                            })
                        except ValueError:
                            continue
        except Exception as e:
            print(f"Error reading {csv_file}: {e}")
    
    # Calculate stats
    sent_count = sum(1 for b in bills if b['status'] == 'sent' and not b['is_total'])
    pending_count = sum(1 for b in bills if b['status'] == 'pending' and not b['is_total'])
    failed_count = sum(1 for b in bills if b['status'] == 'failed' and not b['is_total'])
    total_bills = len([b for b in bills if not b['is_total']])
    
    return render_template_string(HTML_TEMPLATE,
                                  bills=bills,
                                  total_bills=total_bills,
                                  sent_count=sent_count,
                                  pending_count=pending_count,
                                  failed_count=failed_count,
                                  grand_total=grand_total)

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
        filename = f"bills_{timestamp}.csv"
        filepath = os.path.join(DATA_DIR, filename)
        file.save(filepath)
        return f"""
        <h2>File uploaded successfully!</h2>
        <p>Saved as: {filename}</p>
        <p><a href="/">View Bills</a></p>
        """
    
    return "Invalid file type", 400

@app.route('/send-email/<bill_id>', methods=['POST'])
def send_email(bill_id):
    """Send email for a specific bill."""
    status = load_status()
    
    # Simulate sending email
    # In real implementation, this would send the actual email
    import random
    success = random.random() > 0.2  # 80% success rate for demo
    
    if success:
        status[bill_id] = 'sent'
        message = f"Email sent successfully for bill {bill_id}"
    else:
        status[bill_id] = 'failed'
        message = f"Failed to send email for bill {bill_id}"
    
    save_status(status)
    return jsonify({'success': success, 'message': message})

@app.route('/resend-email/<bill_id>', methods=['POST'])
def resend_email(bill_id):
    """Resend email for a specific bill."""
    status = load_status()
    
    # Simulate resending
    import random
    success = random.random() > 0.1  # 90% success rate for resend
    
    if success:
        status[bill_id] = 'sent'
        message = f"Email resent successfully for bill {bill_id}"
    else:
        status[bill_id] = 'failed'
        message = f"Failed to resend email for bill {bill_id}"
    
    save_status(status)
    return jsonify({'success': success, 'message': message})

@app.route('/send-emails', methods=['POST'])
def send_emails():
    """Send emails for selected bills."""
    selected = request.form.getlist('selected')
    status = load_status()
    
    sent = 0
    failed = 0
    
    import random
    for bill_id in selected:
        success = random.random() > 0.2
        if success:
            status[bill_id] = 'sent'
            sent += 1
        else:
            status[bill_id] = 'failed'
            failed += 1
    
    save_status(status)
    
    message = f"Sent: {sent}, Failed: {failed}"
    return f"""
    <h2>Email Sending Complete</h2>
    <p>{message}</p>
    <p><a href="/">Back to Bills</a></p>
    """

if __name__ == '__main__':
    print("=" * 60)
    print("Test Bill Viewer Application")
    print("=" * 60)
    print(f"Data directory: {DATA_DIR}")
    print("URL: http://localhost:8765")
    print("=" * 60)
    app.run(host='0.0.0.0', port=8765, debug=True)
