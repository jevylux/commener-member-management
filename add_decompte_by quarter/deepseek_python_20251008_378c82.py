from flask import Flask, request, Response, render_template, send_file
from sqlalchemy import create_engine, text
from datetime import datetime
import csv
import io
import os

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

@app.route('/')
def index():
    """Display the form for generating reports"""
    current_year = datetime.now().year
    return render_template('quarterly_report.html', current_year=current_year)


# Alternative version using JOIN in SQL for better performance
@app.route('/quarterly-totals-optimized', methods=['GET'])
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
            m.Firstname || ' ' || m.name as member_name,
            COALESCE(a.accounting_total, 0) as accounting_total,
            COALESCE(uf.fee_amount, 0) as membership_fee,
            (COALESCE(a.accounting_total, 0) + COALESCE(uf.fee_amount, 0)) as total_amount
        FROM accounting_totals a
        FULL OUTER JOIN unpaid_fees uf ON a.member_id = uf.member_id
        LEFT JOIN members m ON COALESCE(a.member_id, uf.member_id) = m.id
        WHERE COALESCE(a.member_id, uf.member_id) IS NOT NULL
        ORDER BY member_name
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
                member_name = row.member_name or f"Member {row.member_id}"
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