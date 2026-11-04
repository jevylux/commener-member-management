from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from flask_wtf import FlaskForm
from sqlalchemy import update, func
from wtforms import StringField, SelectField, FloatField, IntegerField, TextAreaField, DateField
from wtforms.validators import DataRequired, Email, AnyOf, Optional
from models import db, Member, Pod, SharingGroup, PodSharingGroup, MemberFee, MemberFeePayment, Accounting
from datetime import date, datetime, time
import os
import csv

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////Users/marcdurbach/Development/python/ComEner-data-management/database/commEnergy.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'your-secret-key'
db.init_app(app)

# Forms
class MemberForm(FlaskForm):
    name = StringField('Name', validators=[Optional()])
    firstname = StringField('Firstname', validators=[Optional()])
    nationalId = StringField('National ID', validators=[Optional()])
    address = TextAreaField('Address', validators=[Optional()])
    phoneNumber = StringField('Phone Number', validators=[Optional()])
    email = StringField('Email', validators=[Optional(), Email()])
    energyID = StringField('Energy ID', validators=[Optional()])

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

# Routes for Members
@app.route('/members')
def list_members():
    members = Member.query.all()
    return render_template('members/list.html', members=members)

@app.route('/members/new', methods=['GET', 'POST'])
def create_member():
    member_form = MemberForm()
    pod_form = PodForm()
    if member_form.validate_on_submit():
        member = Member(
            name=member_form.name.data,
            firstname=member_form.firstname.data,
            nationalId=member_form.nationalId.data,
            address=member_form.address.data,
            phoneNumber=member_form.phoneNumber.data,
            email=member_form.email.data,
            energyID=member_form.energyID.data
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
    pods = Pod.query.all()
    return render_template('pods/list.html', pods=pods)

@app.route('/pods/new', methods=['GET', 'POST'])
def create_pod():
    form = PodForm()
    form.memberID.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
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
    form.memberID.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
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
            sgNumber=form.sgNumber.data
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
    pod_sharing_groups = PodSharingGroup.query.all()
    return render_template('pod_sharing_groups/list.html', pod_sharing_groups=pod_sharing_groups)

@app.route('/pod_sharing_groups/new', methods=['GET', 'POST'])
def create_pod_sharing_group():
    form = PodSharingGroupForm()
    form.podID.choices = [(p.podsID, p.podlabel) for p in Pod.query.all()]
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
    form.podID.choices = [(p.podsID, p.podlabel) for p in Pod.query.all()]
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
        member_fee = MemberFee(
            mfamount=form.mfamount.data,
            mfYear=form.mfYear.data
        )
        db.session.add(member_fee)
        db.session.commit()
        flash('Member Fee created successfully!', 'success')
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
    member_fee_payments = MemberFeePayment.query.all()
    return render_template('member_fee_payments/list.html', member_fee_payments=member_fee_payments)

@app.route('/member_fee_payments/new', methods=['GET', 'POST'])
def create_member_fee_payment():
    form = MemberFeePaymentForm()
    form.memberID.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
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
    form.memberID.choices = [(m.id, f"{m.firstname} {m.name}") for m in Member.query.all()]
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
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
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
    DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
    print(os.path.join(DATA_DIR, filename))
    return send_from_directory(DATA_DIR, filename, as_attachment=True)

@app.route('/accounting/file_list', methods=['GET'])
def file_list():
    """Display a list of files available for download"""
    try:
        files = []
        DATA_DIR = os.path.join(os.path.dirname(__file__), 'data')
        
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

@app.route('/', methods=['GET'])
def menu():
    return render_template("menu.html", page_title="Menu")


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=True)