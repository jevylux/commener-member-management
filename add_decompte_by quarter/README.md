Here's the updated solution with the actual member names from your members.csv file and file saving functionality:

**Updated Flask Application (app.py):**

```python
from flask import Flask, request, Response, render_template, send_file
from sqlalchemy import create_engine, text
from datetime import datetime
import csv
import io
import os
import pandas as pd

app = Flask(__name__)

# Database configuration (update with your actual database URI)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///your_database.db'
app.config['REPORTS_FOLDER'] = 'reports'
engine = create_engine(app.config['SQLALCHEMY_DATABASE_URI'])

# Create reports folder if it doesn't exist
os.makedirs(app.config['REPORTS_FOLDER'], exist_ok=True)

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
    """Create a mapping from member ID to full name"""
    # Load members data (adjust the path as needed)
    try:
        members_df = pd.read_csv('members.csv', delimiter=';')
        member_map = {}
        for _, row in members_df.iterrows():
            full_name = f"{row['Firstname']} {row['name']}"
            member_map[row['id']] = full_name
        return member_map
    except Exception as e:
        print(f"Error loading members.csv: {e}")
        return {}

@app.route('/')
def index():
    """Display the form for generating reports"""
    current_year = datetime.now().year
    return render_template('quarterly_report.html', current_year=current_year)

@app.route('/quarterly-totals-detailed', methods=['GET'])
def get_quarterly_totals_detailed():
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
        
        # Get member name mapping
        member_map = get_member_name_map()
        
        # SQL query to calculate totals with member names
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
            COALESCE(a.accounting_total, 0) as accounting_total,
            COALESCE(uf.fee_amount, 0) as membership_fee,
            (COALESCE(a.accounting_total, 0) + COALESCE(uf.fee_amount, 0)) as total_amount
        FROM accounting_totals a
        FULL OUTER JOIN unpaid_fees uf ON a.member_id = uf.member_id
        WHERE COALESCE(a.member_id, uf.member_id) IS NOT NULL
        ORDER BY member_id
        """)
        
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
            writer.writerow(['Quarterly Financial Report'])
            writer.writerow([f'Year: {year}'])
            writer.writerow([f'Quarter: Q{quarter}'])
            writer.writerow([f'Months: {", ".join(quarter_month_names)}'])
            writer.writerow(['Generated: ' + datetime.now().strftime('%Y-%m-%d %H:%M:%S')])
            writer.writerow([])  # Empty row for spacing
            writer.writerow(['Member Name', 'Accounting Total', 'Membership Fee', 'Total Amount'])
            
            # Write data rows
            grand_total = 0
            accounting_grand_total = 0
            fee_grand_total = 0
            
            for row in result:
                member_id = row.member_id
                member_name = member_map.get(member_id, f"Member {member_id}")
                accounting_total = float(row.accounting_total)
                membership_fee = float(row.membership_fee)
                total_amount = accounting_total + membership_fee
                
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
            writer.writerow(['GRAND TOTALS', 
                           f"{accounting_grand_total:.2f}", 
                           f"{fee_grand_total:.2f}", 
                           f"{grand_total:.2f}"])
            
            # Get CSV content
            csv_content = output.getvalue()
            
            # Save file to reports folder
            filename = f"quarterly_report_Q{quarter}_{year}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
            filepath = os.path.join(app.config['REPORTS_FOLDER'], filename)
            
            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                f.write(csv_content)
            
            # Prepare response with CSV file
            output.seek(0)
            
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

@app.route('/reports')
def list_reports():
    """List all generated reports"""
    reports = []
    try:
        for filename in os.listdir(app.config['REPORTS_FOLDER']):
            if filename.endswith('.csv'):
                filepath = os.path.join(app.config['REPORTS_FOLDER'], filename)
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
    
    return render_template('reports_list.html', reports=reports)

@app.route('/reports/<filename>')
def download_report(filename):
    """Download a specific report"""
    try:
        filepath = os.path.join(app.config['REPORTS_FOLDER'], filename)
        if os.path.exists(filepath):
            return send_file(filepath, as_attachment=True)
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error downloading file: {str(e)}", 500

@app.route('/reports/delete/<filename>', methods=['POST'])
def delete_report(filename):
    """Delete a specific report"""
    try:
        filepath = os.path.join(app.config['REPORTS_FOLDER'], filename)
        if os.path.exists(filepath):
            os.remove(filepath)
            return '', 204
        else:
            return "File not found", 404
    except Exception as e:
        return f"Error deleting file: {str(e)}", 500

if __name__ == '__main__':
    app.run(debug=True)
```

**New Template for Reports List (templates/reports_list.html):**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Generated Reports</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 50px auto;
            padding: 20px;
            background-color: #f5f5f5;
        }
        .container {
            background-color: white;
            padding: 30px;
            border-radius: 10px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        h1 {
            color: #333;
            text-align: center;
            margin-bottom: 30px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }
        th, td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f8f9fa;
            font-weight: bold;
        }
        .btn {
            padding: 8px 16px;
            text-decoration: none;
            border-radius: 4px;
            margin-right: 5px;
            display: inline-block;
        }
        .btn-download {
            background-color: #007bff;
            color: white;
        }
        .btn-delete {
            background-color: #dc3545;
            color: white;
            border: none;
            cursor: pointer;
        }
        .btn-primary {
            background-color: #007bff;
            color: white;
            padding: 10px 20px;
            text-decoration: none;
            border-radius: 5px;
            display: inline-block;
            margin-top: 20px;
        }
        .empty {
            text-align: center;
            color: #666;
            padding: 40px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Generated Reports</h1>
        
        {% if reports %}
        <table>
            <thead>
                <tr>
                    <th>Filename</th>
                    <th>Created</th>
                    <th>Size</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
                {% for report in reports %}
                <tr>
                    <td>{{ report.filename }}</td>
                    <td>{{ report.created }}</td>
                    <td>{{ report.size }}</td>
                    <td>
                        <a href="{{ url_for('download_report', filename=report.filename) }}" class="btn btn-download">
                            Download
                        </a>
                        <button onclick="deleteReport('{{ report.filename }}')" class="btn btn-delete">
                            Delete
                        </button>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
        {% else %}
        <div class="empty">
            <p>No reports generated yet.</p>
        </div>
        {% endif %}
        
        <a href="{{ url_for('index') }}" class="btn-primary">Generate New Report</a>
    </div>

    <script>
        function deleteReport(filename) {
            if (confirm('Are you sure you want to delete ' + filename + '?')) {
                fetch('/reports/delete/' + filename, {
                    method: 'POST',
                }).then(response => {
                    if (response.status === 204) {
                        location.reload();
                    } else {
                        alert('Error deleting file');
                    }
                });
            }
        }
    </script>
</body>
</html>
```

**Updated Quarterly Report Template (templates/quarterly_report.html):**

Add this link to the bottom of the existing template:

```html
<!-- Add this inside the form-container div, after the form -->
<div style="text-align: center; margin-top: 20px;">
    <a href="{{ url_for('list_reports') }}" style="color: #007bff; text-decoration: none;">
        View Generated Reports
    </a>
</div>
```

**Key Features Added:**

1. **Member Names:** Uses actual member names from your members.csv file
2. **File Storage:** Automatically saves all generated reports to a `reports` folder
3. **Reports Management:** New routes to list, download, and delete reports
4. **Timestamped Filenames:** Includes timestamp in filenames to avoid conflicts
5. **User Interface:** Web interface to manage generated reports

**Usage:**

1. **Generate Report:** Visit `/` → Select year/quarter → Download CSV
2. **View Reports:** Visit `/reports` to see all generated reports
3. **Download:** Click "Download" on any report in the list
4. **Delete:** Click "Delete" to remove reports you don't need

**File Structure:**
```
your_project/
├── app.py
├── members.csv
├── templates/
│   ├── quarterly_report.html
│   └── reports_list.html
└── reports/
    ├── quarterly_report_Q3_2025_20240115_143025.csv
    └── quarterly_report_Q2_2025_20240115_142018.csv
```

The system now uses the actual member names from your CSV file and provides a complete solution for generating, storing, and managing quarterly financial reports.