# Exact Code Changes for Bill Generation Feature

This document shows the **exact** code changes needed in your existing ComEner files.

---

## File 1: `app/__init__.py`

### Current Location
`/Users/marcdurbach/Development/python/ComEner-data-management/app/__init__.py`

### What to Add

**Option A: If you have a `create_app()` function (most common)**

Find this section (around line 10-30):
```python
from app.routes import bp
app.register_blueprint(bp)
```

**Add AFTER those lines:**

```python
    # Register the bill routes blueprint
    from app.bill_routes import bill_bp
    app.register_blueprint(bill_bp)
```

**Option B: Complete updated `__init__.py` template**

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

---

## File 2: `app/models.py`

### Current Location
`/Users/marcdurbach/Development/python/ComEner-data-management/app/models.py`

### What to Add

**Step 1: Add the BillEmail class at the END of the file**

Add this entire class after all existing model classes:

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
    
    def __repr__(self):
        return f'<BillEmail {self.beYear}-Q{self.beQuarter} Member:{self.beMemberID} Status:{self.beStatus}>'
```

**Step 2: Add relationship to Member class**

Find your `Member` class (search for `class Member(db.Model):`).

Add this line at the END of the Member class (after all existing columns and before any methods):

```python
    # Relationship for bill emails
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
```

**Example - If your Member class looks like this:**

```python
class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100), nullable=False)
    firstname = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    # ... other columns ...
    
    # <-- ADD THIS LINE HERE -->
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
```

---

## File 3: `app/templates/accounting/quarterly_report.html`

### Current Location
`/Users/marcdurbach/Development/python/ComEner-data-management/app/templates/accounting/quarterly_report.html`

### What to Add

**Step 1: Find your form element**

Look for something like:
```html
<form method="post" ...>
```

Or:
```html
<form action="..." method="POST">
```

**Step 2: Add an ID to your form**

If your form doesn't have an `id`, add `id="reportForm"`:

Change:
```html
<form method="post" action="/accounting/quarterly_report">
```

To:
```html
<form method="post" action="/accounting/quarterly_report" id="reportForm">
```

**Step 3: Add IDs to year and quarter inputs**

Find your year input (search for `name="year"`):

Change:
```html
<input type="text" name="year" ...>
```

To:
```html
<input type="text" name="year" id="year" ...>
```

Find your quarter input (search for `name="quarter"`):

Change:
```html
<select name="quarter" ...>
```

To:
```html
<select name="quarter" id="quarter" ...>
```

**Step 4: Add the bill creation section**

Find the closing `</form>` tag of your report form.

Add this AFTER the `</form>` but BEFORE `{% endblock %}` or `</div>`:

```html

<!-- Bill Creation Section -->
<div class="mt-4 pt-4 border-top">
    <h3>Create Bills</h3>
    <p>After generating the report, you can create individual PDF bills for each member.</p>
    <form action="/accounting/quarterly_report/bills" method="POST" id="billForm">
        <input type="hidden" name="year" id="billYear" value="">
        <input type="hidden" name="quarter" id="billQuarter" value="">
        <button type="submit" class="btn btn-success" id="btnCreateBills" disabled>
            <i class="bi bi-file-earmark-pdf"></i> Want to create PDF Bills
        </button>
    </form>
</div>

<script>
// Enable bill creation button when report is generated
// Get the year and quarter values for the bill form
function updateBillForm() {
    var yearVal = document.getElementById('year');
    var quarterVal = document.getElementById('quarter');
    
    if (yearVal) document.getElementById('billYear').value = yearVal.value;
    if (quarterVal) document.getElementById('billQuarter').value = quarterVal.value;
    
    // Enable button if both values are set
    if (yearVal && quarterVal && yearVal.value && quarterVal.value) {
        document.getElementById('btnCreateBills').disabled = false;
    }
}

// Listen for changes
var yearInput = document.getElementById('year');
var quarterInput = document.getElementById('quarter');

if (yearInput) {
    yearInput.addEventListener('change', updateBillForm);
    yearInput.addEventListener('input', updateBillForm);
}

if (quarterInput) {
    quarterInput.addEventListener('change', updateBillForm);
}

// Initial update
updateBillForm();
</script>
```

---

## File 4: `app/routes.py` (Optional - Add Navigation Link)

### Current Location
`/Users/marcdurbach/Development/python/ComEner-data-management/app/routes.py`

### What to Add

**Add a link to the bill list page in your accounting menu/navigation**

Find where you define accounting routes or navigation.

Add this link:

```python
# In your routes, add this navigation helper if you have one
@app.context_processor
def utility_processor():
    return {
        'bill_folders_url': '/accounting/bills/list'
    }
```

Or simply add this link to your accounting template:

```html
<a href="/accounting/bills/list" class="btn btn-outline-primary">
    <i class="bi bi-folder"></i> View Bill Folders
</a>
```

---

## Summary of Exact Changes

### Lines to Add per File:

| File | Lines to Add | Location |
|------|--------------|----------|
| `app/__init__.py` | 2 lines | After `register_blueprint(bp)` |
| `app/models.py` | 25 lines | End of file (BillEmail class) |
| `app/models.py` | 1 line | Inside Member class |
| `quarterly_report.html` | 50+ lines | After report form, before endblock |

### Total New Lines in Existing Files: ~80 lines

### New Files to Copy (no changes needed):
- `app/bill_generator.py` (copy as-is)
- `app/bill_routes.py` (copy as-is)
- `app/templates/accounting/bill_review.html` (copy as-is)
- `app/templates/accounting/bill_sent.html` (copy as-is)
- `app/templates/accounting/bill_list.html` (copy as-is)

---

## Database Migration

### Option 1: Using SQL directly

Create a file called `migrate_bill_email.sql`:

```sql
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

-- Create indexes
CREATE INDEX IF NOT EXISTS ix_bill_email_member ON bill_email (beMemberID);
CREATE INDEX IF NOT EXISTS ix_bill_email_year_quarter ON bill_email (beYear, beQuarter);
CREATE INDEX IF NOT EXISTS ix_bill_email_status ON bill_email (beStatus);
```

Run it:
```bash
cd /Users/marcdurbach/Development/python/ComEner-data-management
sqlite3 database/commEnergy.db < migrate_bill_email.sql
```

### Option 2: Using Python/Flask

```bash
cd /Users/marcdurbach/Development/python/ComEner-data-management
python -c "
from app import create_app, db
from app.models import BillEmail
app = create_app()
with app.app_context():
    db.create_all()
    print('BillEmail table created!')
"
```

---

## Verification Commands

After making changes, verify with these commands:

```bash
# 1. Check Python syntax
cd /Users/marcdurbach/Development/python/ComEner-data-management
python -m py_compile app/__init__.py
python -m py_compile app/models.py
python -m py_compile app/bill_routes.py
python -m py_compile app/bill_generator.py

# 2. Start the app
python run.py

# 3. Test the route
curl -I http://localhost:5000/accounting/quarterly_report

# 4. Check database schema
sqlite3 database/commEnergy.db ".schema bill_email"
```

---

## Troubleshooting

### "Blueprint not found" error
Make sure `bill_routes.py` is in the `app/` folder and contains `bill_bp = Blueprint('bills', __name__, url_prefix='/accounting')`

### "Table not found" error
Run the database migration before starting the app

### "Template not found" error
Make sure all HTML files are in `app/templates/accounting/`

### "No module named 'app.bill_routes'" error
Check that `bill_routes.py` is in the same folder as `__init__.py` (the `app/` folder)

---

## Quick Copy-Paste Summary

### app/__init__.py - Add these 2 lines:
```python
    from app.bill_routes import bill_bp
    app.register_blueprint(bill_bp)
```

### app/models.py - Add at end:
```python
class BillEmail(db.Model):
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
    member = db.relationship('Member', backref='bill_emails', lazy=True)
    __table_args__ = (
        db.Index('ix_bill_email_member', 'beMemberID'),
        db.Index('ix_bill_email_year_quarter', 'beYear', 'beQuarter'),
        db.Index('ix_bill_email_status', 'beStatus'),
    )
```

### app/models.py - Add inside Member class:
```python
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')
```

### quarterly_report.html - Add after form:
```html
<div class="mt-4 pt-4 border-top">
    <h3>Create Bills</h3>
    <form action="/accounting/quarterly_report/bills" method="POST" id="billForm">
        <input type="hidden" name="year" id="billYear">
        <input type="hidden" name="quarter" id="billQuarter">
        <button type="submit" class="btn btn-success" id="btnCreateBills" disabled>
            Want to create PDF Bills
        </button>
    </form>
</div>
<script>
function updateBillForm() {
    var y = document.getElementById('year'), q = document.getElementById('quarter');
    if (y) document.getElementById('billYear').value = y.value;
    if (q) document.getElementById('billQuarter').value = q.value;
    document.getElementById('btnCreateBills').disabled = !(y && q && y.value && q.value);
}
if (document.getElementById('year')) document.getElementById('year').addEventListener('change', updateBillForm);
if (document.getElementById('quarter')) document.getElementById('quarter').addEventListener('change', updateBillForm);
updateBillForm();
</script>
```
