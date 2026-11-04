from flask import Blueprint, render_template, request, redirect, url_for, flash
from app.models import (
    SharingGroup, PodSharingGroup, Pod, Member, 
    MemberFee, Accounting, MemberFeePayment
)
from app import db

bp = Blueprint('main', __name__)

# Sharing Groups Routes
@bp.route('/sharing_groups')
def list_sharing_groups():
    groups = SharingGroup.query.all()
    return render_template('sharing_groups/list.html', groups=groups)

@bp.route('/sharing_groups/create', methods=['GET', 'POST'])
def create_sharing_group():
    if request.method == 'POST':
        group = SharingGroup(
            sgID=request.form.get('sgID'),
            sgName=request.form.get('sgName'),
            sgNumber=request.form.get('sgNumber')
        )
        db.session.add(group)
        db.session.commit()
        flash('Sharing group created successfully!', 'success')
        return redirect(url_for('main.list_sharing_groups'))
    return render_template('sharing_groups/create.html')

@bp.route('/sharing_groups/<int:id>/edit', methods=['GET', 'POST'])
def edit_sharing_group(id):
    group = SharingGroup.query.get_or_404(id)
    if request.method == 'POST':
        group.sgName = request.form.get('sgName')
        group.sgNumber = request.form.get('sgNumber')
        db.session.commit()
        flash('Sharing group updated successfully!', 'success')
        return redirect(url_for('main.list_sharing_groups'))
    return render_template('sharing_groups/edit.html', group=group)

@bp.route('/sharing_groups/<int:id>/delete', methods=['POST'])
def delete_sharing_group(id):
    group = SharingGroup.query.get_or_404(id)
    db.session.delete(group)
    db.session.commit()
    flash('Sharing group deleted successfully!', 'success')
    return redirect(url_for('main.list_sharing_groups'))

# Members Routes
@bp.route('/members')
def list_members():
    members = Member.query.all()
    return render_template('members/list.html', members=members)


# Route to update member information only
@bp.route('/members/<int:member_id>/update', methods=['GET','POST'])
def update_members(member_id):
    member = Member.query.get_or_404(member_id)
    
    try:
        member.name = request.form.get('name')
        member.Firstname = request.form.get('Firstname')
        member.nationalId = request.form.get('nationalId')
        member.address = request.form.get('address')
        member.phoneNumber = request.form.get('phoneNumber')
        member.email = request.form.get('email')
        member.energyID = request.form.get('energyID')
        
        db.session.commit()
        flash('Member updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating member: {str(e)}', 'error')
    
    return redirect(url_for('main.update_members', member_id=member_id))
# Route to delete member with all pods
@bp.route('/members/<int:member_id>/delete', methods=['POST'])
def delete_members_with_pods(member_id):
    member = Member.query.get_or_404(member_id)
    
    try:
        # Delete all associated pods first
        Pod.query.filter_by(memberID=member_id).delete()
        # Delete the member
        db.session.delete(member)
        db.session.commit()
        flash('Member and all associated pods deleted successfully!', 'success')
        return redirect(url_for('main.list_members'))  # Redirect to members list
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting member: {str(e)}', 'error')
        return redirect(url_for('main.edit_member', member_id=member_id))


@bp.route('/members/create', methods=['GET', 'POST'])
def create_members():
    if request.method == 'POST':
        print("Posting data to create member")
        try:
            # Get member data from form
            name = request.form.get('name')
            firstname = request.form.get('firstname')
            national_id = request.form.get('national_id')
            address = request.form.get('address')
            phone_number = request.form.get('phone_number')
            email = request.form.get('email')
            energy_id = request.form.get('energy_id')
            
            # Create new member
            new_member = Member(
                name=name,
                Firstname=firstname,
                nationalId=national_id,
                address=address,
                phoneNumber=phone_number,
                email=email,
                energyID=energy_id
            )
            print(f"Member object created: {new_member}")
            # Add and flush to get the member ID
            print(db.session.add(new_member))
            print(db.session.flush())

# Get pod data from form (multiple pods)
            pod_labels = request.form.getlist('pod_label[]')
            pod_types = request.form.getlist('pod_type[]')
            pod_numbers = request.form.getlist('pod_number[]')
            
            # Create pods linked to the member
            for i in range(len(pod_labels)):
                if pod_labels[i].strip():  # Only create pod if label is not empty
                    new_pod = Pod(
                        podlabel=pod_labels[i],
                        podType=pod_types[i] if i < len(pod_types) else '',
                        memberID=new_member.id,
                        podNumber=pod_numbers[i] if i < len(pod_numbers) else ''
                    )
                    print(f"Pod object created: {new_pod}")
                    print("session add",db.session.add(new_pod))
            try:
                db.session.commit()
                print("Commit successful")
            except Exception as e:
                print(f"Commit failed: {e}")
                db.session.rollback()

            flash('Member and Pod(s) added successfully!', 'success')

            return redirect(url_for('main.list_members'))
        
        except Exception as e:
            db.session.rollback()
            flash(f'Error adding member and pod: {str(e)}', 'error')
            return render_template('members/create.html')
    
    return render_template('members/create.html')

@bp.route('/members/<int:member_id>/edit', methods=['GET', 'POST'])
def edit_members(member_id):
    member = Member.query.get_or_404(member_id)
    if request.method == 'POST':
        member.name = request.form.get('name')
        member.Firstname = request.form.get('Firstname')
        member.nationalId = request.form.get('nationalId')
        member.address = request.form.get('address')
        member.phoneNumber = request.form.get('phoneNumber')
        member.email = request.form.get('email')
        member.energyID = request.form.get('energyID')
        db.session.commit()
        flash('Members updated successfully!', 'success')
        return redirect(url_for('main.list_members'))
    return render_template('members/edit.html', member=member)

@bp.route('/members/<int:member_id>/delete', methods=['POST'])
def delete_members(member_id):
    member = Member.query.get_or_404(id)
    db.session.delete(member)
    db.session.commit()
    flash('Member deleted successfully!', 'success')
    return redirect(url_for('main.list_members'))
#Route to add new pod to member
@bp.route('/members/<int:member_id>/pod/add', methods=['POST'])
def add_pod(member_id):
    member = Member.query.get_or_404(member_id)
    
    try:
        new_pod = Pod(
            podlabel=request.form.get('podlabel'),
            podType=request.form.get('podType'),
            Field5=request.form.get('Field5'),
            memberID=member_id
        )
        db.session.add(new_pod)
        db.session.commit()
        flash('Pod added successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error adding pod: {str(e)}', 'error')
    
    return redirect(url_for('main.edit_members', member_id=member_id))

# Route to update individual pod
@bp.route('/pod/<int:pod_id>/update', methods=['POST'])
def update_pod(pod_id):
    pod = Pod.query.get_or_404(pod_id)
    
    try:
        pod.podlabel = request.form.get('podlabel')
        pod.podType = request.form.get('podType')
        pod.Field5 = request.form.get('Field5')
        
        db.session.commit()
        flash('Pod updated successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error updating pod: {str(e)}', 'error')
    
    return redirect(url_for('main.edit_members', member_id=pod.memberID))

# Route to delete individual pod
@bp.route('/pod/<int:pod_id>/delete', methods=['POST'])
def delete_pod(pod_id):
    pod = Pod.query.get_or_404(pod_id)
    member_id = pod.memberID
    
    try:
        db.session.delete(pod)
        db.session.commit()
        flash('Pod deleted successfully!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error deleting pod: {str(e)}', 'error')
    
    return redirect(url_for('main.edit_members', member_id=member_id))