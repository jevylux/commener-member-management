# Bill Generation and Email Sending - Implementation Summary

This document summarizes the implementation of the PDF bill generation and email sending feature for the ComEner Flask application.

## Files Created

### 1. `bill_generator.py`
**Purpose:** Module to generate individual PDF bills for each member from quarterly report data.

**Key Features:**
- Uses PyMuPDF (fitz) for PDF generation
- Creates professional-looking bills with trilingual headers (EN/FR/DE)
- Generates bills in folder structure: `_bills_<year>-Q<quarter>/`
- Calculates totals from accounting data minus membership fees
- Includes payment information section
- Sanitizes filenames for safe file storage

**Main Classes/Functions:**
- `BillGenerator` - Main class for bill generation
- `generate_bill()` - Creates a single PDF bill
- `generate_bills_from_quarterly_data()` - Batch generates bills from quarterly data
- `create_bill_folder()` - Creates organized folder structure

---

### 2. `bill_routes.py`
**Purpose:** Flask blueprint with routes for bill management and email sending.

**Routes Implemented:**

| Route | Method | Description |
|-------|--------|-------------|
| `/accounting/quarterly_report/bills` | POST | Generate bills from quarterly data. Creates folder `_bills_<year>-Q<quarter>/` |
| `/accounting/bills/<folder>/review` | GET | Display bills with email status, selection checkboxes, and send controls |
| `/accounting/bills/<folder>/send` | POST | Send emails to selected/all members with bill attachments |
| `/accounting/bills/<folder>/status` | GET | JSON endpoint to check current email sending status |
| `/accounting/bills/<folder>/resend` | POST | Resend bills to specific members (with "RESEND" subject prefix) |
| `/accounting/bills/<folder>/download/<filename>` | GET | Download a specific bill PDF |
| `/accounting/bills/list` | GET | List all generated bill folders with statistics |

**Key Features:**
- Tracks email status in JSON file per folder (`_email_status.json`)
- Supports selective sending (checkboxes for individual bills)
- Bulk operations (send all, retry all failed)
- AJAX support for async operations with progress feedback
- Uses existing email configuration (mail.aplus.net)
- Trilingual email templates (EN/FR/DE)

---

### 3. `templates/accounting/bill_review.html`
**Purpose:** Template for reviewing bills and managing email sending.

**Features:**
- Bootstrap 5 styling with responsive design
- Summary cards showing total/sent/pending/failed counts
- Progress bar showing sending completion percentage
- Interactive table with:
  - Checkboxes for selection (with "Select All" option)
  - Member name, filename, size, created date
  - Status badges (sent/pending/failed)
  - Action buttons (download, send, resend)
- Toolbar with send selected/send all/refresh actions
- Modal dialogs for:
  - Confirmation before sending
  - Real-time sending progress/results
- JavaScript for AJAX operations and dynamic updates

---

### 4. `templates/accounting/bill_sent.html`
**Purpose:** Template showing sent status and resend options after email sending.

**Features:**
- Summary cards with sent/failed/total counts
- Detailed results table with all sending attempts
- Copy results to clipboard functionality
- Failed items section with retry buttons
- Individual resend and "retry all failed" options
- Confirmation modal for resends (with RESEND notification)
- Processing spinner for async operations

---

### 5. `database_update.py`
**Purpose:** SQLAlchemy migration for BillEmail table.

**Generated Files:**
- Alembic-style migration script
- Manual SQL migration script (for SQLite)
- Python model code snippet

**BillEmail Table Schema:**
| Column | Type | Description |
|--------|------|-------------|
| beID | Integer (PK) | Auto-increment primary key |
| beMemberID | Integer (FK) | Member reference |
| beYear | Integer | Billing year |
| beQuarter | Integer | Billing quarter (1-4) |
| beFilename | String(255) | PDF filename |
| beSentDate | DateTime | When email was sent |
| beEmailTo | String(255) | Recipient email address |
| beStatus | String(20) | Status: pending/sent/failed |
| beErrorMessage | Text | Error details for debugging |
| beResendCount | Integer | Number of resend attempts |

**Indexes:**
- `ix_bill_email_member` - For member lookups
- `ix_bill_email_year_quarter` - For quarter queries
- `ix_bill_email_status` - For status filtering

---

## Existing Files to Modify

### 1. `app/__init__.py`
**Changes Required:**
Register the new bill blueprint.

```python
# Add after existing blueprint registration
from app.bill_routes import bill_bp
app.register_blueprint(bill_bp)

# Optional: Configure bill output directory
app.config['BILL_OUTPUT_DIR'] = os.path.join(os.getcwd(), 'bills')
```

---

### 2. `app/models.py`
**Changes Required:**
Add the BillEmail model class.

Add this code to the models.py file (after existing model classes):

```python
class BillEmail(db.Model):
    """Track bill emails sent to members."""
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
```

Also add the relationship to the Member class:
```python
class Member(db.Model):
    # ... existing columns ...
    
    # Add this relationship
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
```

---

### 3. `templates/accounting/quarterly_report.html`
**Changes Required:**
Add a button to create PDF bills after generating the report.

Add this inside the form-container div (after the existing form):

```html
<!-- Add this after the report form -->
<div class="mt-4 pt-4 border-top">
    <h3>Create Bills</h3>
    <p>After generating the report, you can create individual PDF bills for each member.</p>
    <form action="{{ url_for('bills.generate_quarterly_bills') }}" method="POST" id="billForm">
        <input type="hidden" name="year" id="billYear" value="">
        <input type="hidden" name="quarter" id="billQuarter" value="">
        <button type="submit" class="btn btn-success" id="btnCreateBills" disabled>
            <i class="bi bi-file-earmark-pdf"></i> Create PDF Bills
        </button>
    </form>
</div>

<script>
// Enable bill creation button when form is submitted
document.getElementById('reportForm').addEventListener('submit', function() {
    document.getElementById('billYear').value = document.getElementById('year').value;
    document.getElementById('billQuarter').value = document.getElementById('quarter').value;
    document.getElementById('btnCreateBills').disabled = false;
});

// Update bill form values on year/quarter change
document.getElementById('year').addEventListener('change', updateBillForm);
document.getElementById('quarter').addEventListener('change', updateBillForm);

function updateBillForm() {
    document.getElementById('billYear').value = document.getElementById('year').value;
    document.getElementById('billQuarter').value = document.getElementById('quarter').value;
}

// Set initial values
updateBillForm();
</script>
```

---

## Integration Steps

1. **Copy files to the ComEner project:**
   - Copy `bill_generator.py` to `app/bill_generator.py`
   - Copy `bill_routes.py` to `app/bill_routes.py`
   - Copy `templates/accounting/bill_review.html` to `app/templates/accounting/bill_review.html`
   - Copy `templates/accounting/bill_sent.html` to `app/templates/accounting/bill_sent.html`

2. **Update app/__init__.py** (see above)

3. **Update app/models.py** (see above)

4. **Update templates/accounting/quarterly_report.html** (see above)

5. **Run database migration:**
   ```bash
   python database_update.py --apply --db-path /path/to/commEnergy.db
   ```
   Or use the SQL script:
   ```bash
   sqlite3 /path/to/commEnergy.db < migration_add_bill_email.sql
   ```

6. **Install dependencies (if needed):**
   ```bash
   pip install PyMuPDF  # Already used in generate_ce_forms.py
   ```

7. **Restart the Flask application**

---

## Usage Flow

1. User goes to **Create Quarterly Report** page
2. User selects year and quarter, clicks "Generate Report"
3. Report is generated and downloaded as CSV
4. User clicks **"Create PDF Bills"** button
5. Bills are generated for all members with non-zero amounts
6. User is redirected to **Bill Review** page showing:
   - List of all generated bills
   - Email status (pending/sent/failed)
   - Checkboxes to select bills
   - Progress bar
7. User selects bills and clicks **"Send Selected"** or **"Send All"**
8. Emails are sent with bill PDFs attached
9. User sees **Bill Sent** page with results summary
10. User can retry failed sends or resend individual bills

---

## Security Considerations

- Email credentials are currently hardcoded in `bill_routes.py` - consider using environment variables
- File paths are validated before access
- SQL queries use parameterized queries to prevent injection
- Email sending has error handling to prevent information leakage

---

## Future Enhancements

1. **Store email status in database** (BillEmail table) instead of JSON files
2. **Email template editor** in the web interface
3. **Preview email** before sending
4. **Scheduled sending** for batch operations
5. **Email delivery tracking** (read receipts)
6. **Bulk resend** with different parameters
7. **Bill history** for each member
8. **Integration with payment tracking** to mark bills as paid

---

## Troubleshooting

**Issue:** Bills not generating  
**Check:** Ensure PyMuPDF is installed: `pip install PyMuPDF`

**Issue:** Emails not sending  
**Check:** Verify SMTP credentials and network connectivity to mail.aplus.net:465

**Issue:** Database errors  
**Check:** Run the migration script to create BillEmail table

**Issue:** File not found errors  
**Check:** Ensure `BILL_OUTPUT_DIR` config is set correctly in app/__init__.py
