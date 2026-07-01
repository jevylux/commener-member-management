from flask_sqlalchemy import SQLAlchemy
from datetime import date

db = SQLAlchemy()

class Member(db.Model):
    __tablename__ = 'members'
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(100))
    firstname = db.Column(db.String(100))
    nationalId = db.Column(db.String(50))
    address = db.Column(db.Text)
    phoneNumber = db.Column(db.String(20))
    email = db.Column(db.String(255))
    energyID = db.Column(db.String(50))
    energyIDName = db.Column(db.String(100))
    payment = db.Column(db.String(50))
    BankAccount = db.Column(db.String(30))
    Payconiq = db.Column(db.String(50))
    pods = db.relationship('Pod', backref='member', lazy=True)
    member_fee_payments = db.relationship('MemberFeePayment', backref='member', lazy=True)
    accounting_records_member = db.relationship('Accounting', backref='member', lazy=True)
    
    # Relationship for bill emails
    bill_emails = db.relationship('BillEmail', backref='member', lazy=True, cascade='all, delete-orphan')

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.payment not in ('', 'Bank', 'Payconiq'):
            raise ValueError("payment must be 'Bank' or 'Payconiq'")
    def __repr__(self):
        return f'<Member {self.firstname} {self.name}>'

class Pod(db.Model):
    __tablename__ = 'pods'
    podsID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    podlabel = db.Column(db.String(100))
    podType = db.Column(db.String(20), nullable=False)  # 'Production' or 'Consumption'
    memberID = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    podNumber = db.Column(db.String(50))
    energyproduction = db.Column(db.Numeric(10, 2))
    energystorage = db.Column(db.Numeric(10, 2))

    sharing_groups = db.relationship('PodSharingGroup', backref='pod', lazy=True)
    accounting_records_pod = db.relationship('Accounting', backref='pod', lazy=True)
    # esou funktioneiert dat
    '''
    The key part is backref='pod'. This creates a reverse relationship on the Accounting model, so:

From Pod → Accounting: pod.accounting_records_pod (gives you all accounting records for this pod)
From Accounting → Pod: accounting.pod (gives you the pod for this accounting record)

'''

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.podType not in ('Production', 'Consumption'):
            raise ValueError("podType must be 'Production' or 'Consumption'")

    def __repr__(self):
        return f'<Pod {self.podlabel}>'

class SharingGroup(db.Model):
    __tablename__ = 'sharingGroup'
    sgID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    sgName = db.Column(db.String(100))
    sgNumber = db.Column(db.String(50))
    sgPrice = db.Column(db.Numeric(10, 2))
    sgType = db.Column(db.String(20), nullable=False)  # 'Production'
    pods = db.relationship('PodSharingGroup', backref='sharing_group', lazy=True)
    accounting_records_sharing_group = db.relationship('Accounting', backref='sharingGroup', lazy=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.sgType not in ('National', 'Local'):
            raise ValueError("sgType must be 'National' or 'Local'")
    def __repr__(self):
        return f'<SharingGroup {self.sgName}>'

class PodSharingGroup(db.Model):
    __tablename__ = 'podSharingGroup'
    msgID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    podID = db.Column(db.Integer, db.ForeignKey('pods.podsID'), nullable=False)
    sharingGroupID = db.Column(db.Integer, db.ForeignKey('sharingGroup.sgID'), nullable=False)
    # Relationship to Pod
    pod_detail = db.relationship('Pod', backref='pod_sharing_groups', lazy=True)
    __table_args__ = (
        db.UniqueConstraint('podID', 'sharingGroupID', name='uix_pod_sharing_group'),
    )

    def __repr__(self):
        return f'<PodSharingGroup podID={self.podID} sharingGroupID={self.sharingGroupID}>'

class MemberFee(db.Model):
    __tablename__ = 'memberfee'
    mfID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    mfamount = db.Column(db.Numeric(10, 2))
    mfYear = db.Column(db.Integer)
    payments = db.relationship('MemberFeePayment', backref='member_fee', lazy=True)

    def __repr__(self):
        return f'<MemberFee {self.mfYear}>'

class MemberFeePayment(db.Model):
    __tablename__ = 'memberFeePayment'
    mfpID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    memberID = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    memberFeeID = db.Column(db.Integer, db.ForeignKey('memberfee.mfID'), nullable=False)
    paymentDate = db.Column(db.Date)
    paymentStatus = db.Column(db.String(20), default='pending')  # 'pending', 'paid', 'overdue'
    __table_args__ = (
        db.UniqueConstraint('memberID', 'memberFeeID', name='uix_member_fee_payment'),
    )

    def __repr__(self):
        return f'<MemberFeePayment memberID={self.memberID} status={self.paymentStatus}>'

class Accounting(db.Model):
    __tablename__ = 'accounting'
    accID = db.Column(db.Integer, primary_key=True, autoincrement=True)
    accYear = db.Column(db.Integer)
    accMonth = db.Column(db.Integer)
    accMember = db.Column(db.Integer, db.ForeignKey('members.id'), nullable=False)
    accPod = db.Column(db.Integer, db.ForeignKey('pods.podsID'), nullable=False)
    accAmount = db.Column(db.Numeric(10, 2))
    accBillingDate = db.Column(db.Date, default=date.today) 
    accSGId = db.Column(db.Integer, db.ForeignKey('sharingGroup.sgID'), nullable=False)
    # Relationships
    '''
    accMember = db.relationship('Member', backref='accountings')
    accSharingGroup = db.relationship('SharingGroup', backref='accountings')
    Pod = db.relationship('Pod', backref='accountings')
    '''
    __table_args__ = (
        db.UniqueConstraint('accYear', 'accMonth', 'accMember', 'accPod', 'accSGId', name='uix_accounting'),
    )

    def __repr__(self):
        return f'<Accounting {self.accYear}-{self.accMonth} memberID={self.accMember} podID={self.accPod} amount={self.accAmount}>'


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
