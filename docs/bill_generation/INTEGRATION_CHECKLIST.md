# Integration Checklist for Bill Generation Feature

## Step-by-Step Integration Guide

### Step 1: Copy Files to ComEner Project

Copy the following files from this workspace to the ComEner application:

```bash
# Copy Python modules
cp /Users/marcdurbach/clawd-agents/coding/bill_generator.py \
   /Users/marcdurbach/Development/python/ComEner-data-management/app/

cp /Users/marcdurbach/clawd-agents/coding/bill_routes.py \
   /Users/marcdurbach/Development/python/ComEner-data-management/app/

# Copy templates (create accounting folder if needed)
mkdir -p /Users/marcdurbach/Development/python/ComEner-data-management/app/templates/accounting

cp /Users/marcdurbach/clawd-agents/coding/templates/accounting/bill_review.html \
   /Users/marcdurbach/Development/python/ComEner-data-management/app/templates/accounting/

cp /Users/marcdurbach/clawd-agents/coding/templates/accounting/bill_sent.html \
   /Users/marcdurbach/Development/python/ComEner-data-management/app/templates/accounting/
```

### Step 2: Update app/__init__.py

Add the following to `/Users/marcdurbach/Development/python/ComEner-data-management/app/__init__.py`:

```python
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
```

### Step 3: Update app/models.py

Add the `BillEmail` model class to `/Users/marcdurbach/Development/python/ComEner-data-management/app/models.py`:

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
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.beStatus not in ('pending', 'sent', 'failed'):
            raise ValueError("beStatus must be 'pending', 'sent', or 'failed'")
    
    def __repr__(self):
        return f'<BillEmail {self.beYear}-Q{self.beQuarter} Member:{self.beMemberID} Status:{self.beStatus}>'
```

Also add the relationship to the Member class:

```python
class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    # ... existing columns ...
    
    # Add this relationship at the end of the class
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
    
    # ... rest of Member class ...
```

### Step 4: Update templates/accounting/quarterly_report.html

Add this section to the form container in `/Users/marcdurbach/Development/python/ComEner-data-management/app/templates/accounting/quarterly_report.html`:

```html
<!-- Add before closing </div> of form-container -->
<div class="mt-4 pt-4 border-top">
    <h3>Create Bills</h3>
    <p>After generating the report, you can create individual PDF bills for each member.</p>
    <form action="/accounting/quarterly_report/bills" method="POST" id="billForm">
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

### Step 5: Run Database Migration

Option A: Using the Python script (recommended):
```bash
cd /Users/marcdurbach/Development/python/ComEner-data-management
python database_update.py --apply --db-path database/commEnergy.db
```

Option B: Using SQL directly:
```bash
cd /Users/marcdurbach/Development/python/ComEner-data-management
sqlite3 database/commEnergy.db < database_update.sql
```

Option C: Using Flask shell:
```bash
cd /Users/marcdurbach/Development/python/ComEner-data-management
python -c "
from app import create_app, db
from app.models import BillEmail
app = create_app()
with app.app_context():
    db.create_all()  # This will create the BillEmail table
    print('BillEmail table created successfully!')
"
```

### Step 6: Verify Installation

1. Start the Flask application:
   ```bash
   python run.py
   ```

2. Navigate to: `http://localhost:5000/accounting/quarterly_report`

3. Verify the "Create PDF Bills" button appears

4. Test bill generation:
   - Select a year and quarter
   - Click "Generate Report"
   - Click "Create PDF Bills"
   - Verify bills are created in `bills/_bills_YYYY-QN/` folder

5. Test email sending:
   - Go to the bill review page
   - Verify bills are listed with status
   - Try sending a test email (update email to test address first)

### Step 7: Configure Email Settings (Optional)

To use different email settings, update `bill_routes.py`:

```python
EMAIL_CONFIG = {
    'SMTP_SERVER': 'your-smtp-server.com',
    'SMTP_PORT': 465,
    'SMTP_USER': 'your-email@domain.com',
    'SMTP_PASSWORD': 'your-password',  # Use environment variable in production!
    'FROM_EMAIL': 'your-email@domain.com',
    'FROM_NAME': 'Your Organization Name'
}
```

### Step 8: Test and Deploy

1. Test with a small subset of members first
2. Verify PDF quality and email delivery
3. Check that status tracking works correctly
4. Deploy to production

---

## Troubleshooting Quick Reference

| Issue | Solution |
|-------|----------|
| Module not found | Ensure files are in `app/` directory |
| Template not found | Ensure templates are in `app/templates/accounting/` |
| Database error | Run migration: `python database_update.py --apply` |
| PDF not generating | Check PyMuPDF is installed: `pip install PyMuPDF` |
| Email not sending | Verify SMTP settings and credentials |
| 404 errors | Check blueprint is registered in `__init__.py` |

---

## File Locations Summary

| File | Source | Destination |
|------|--------|-------------|
| bill_generator.py | workspace/ | app/bill_generator.py |
| bill_routes.py | workspace/ | app/bill_routes.py |
| bill_review.html | workspace/templates/accounting/ | app/templates/accounting/ |
| bill_sent.html | workspace/templates/accounting/ | app/templates/accounting/ |

---

## Testing Commands

```bash
# Test bill generation
curl -X POST http://localhost:5000/accounting/quarterly_report/bills \
  -d "year=2025" \
  -d "quarter=3"

# Check bill status
curl http://localhost:5000/accounting/bills/_bills_2025-Q3/status

# List all bill folders
curl http://localhost:5000/accounting/bills/list
```

---

## Success Criteria

- [ ] Copy all 4 files to ComEner project
- [ ] Update `app/__init__.py` with blueprint registration
- [ ] Update `app/models.py` with BillEmail model
- [ ] Update `templates/accounting/quarterly_report.html` with button
- [ ] Run database migration successfully
- [ ] Verify "Create PDF Bills" button appears on quarterly report page
- [ ] Generate test bills for a quarter
- [ ] Verify bills appear in review page
- [ ] Test sending email to single recipient
- [ ] Test bulk sending
- [ ] Test resend functionality
