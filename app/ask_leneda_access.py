# Alternative version using SQLAlchemy (if you're using SQLAlchemy ORM)
# to be modified and integrated into the datamanagement application

def request_metering_data_sqlalchemy(sharing_group_id=None, member_id=None):
    """
    Request metering data using SQLAlchemy ORM.
    Assumes you have Member, Pod, PodSharingGroup, and SharingGroup models defined.
    """
    from your_app.models import Member, Pod, PodSharingGroup, SharingGroup
    
    # Hardcoded OBIS codes array
    OBIS_CODES = [
        "1-1:1.29.0",
        "1-1:3.29.0",
        "1-1:2.29.0",
        "1-1:1.8.0",
        "1-1:2.8.0",
    ]
    
    # Get member information
    if member_id:
        member = Member.query.get(member_id)
    else:
        member = Member.query.filter(Member.energyID.isnot(None)).first()
    
    if not member:
        raise ValueError("No member found with energyID")
    
    from_id = member.energyID
    from_name = member.energyIDName or f"{member.Firstname} {member.name}"
    
    # Get metering points
    if sharing_group_id:
        pods = Pod.query.join(PodSharingGroup).filter(
            PodSharingGroup.sharingGroupID == sharing_group_id,
            Pod.podNumber.isnot(None)
        ).all()
    else:
        pods = Pod.query.join(PodSharingGroup).join(SharingGroup).filter(
            SharingGroup.sgNumber == 'CR00006041',
            Pod.podNumber.isnot(None)
        ).all()
    
    metering_points = [pod.podNumber for pod in pods]
    
    if not metering_points:
        raise ValueError(f"No metering points found")
    
    # Prepare API request
    api_url = current_app.config.get('NEDP_API_URL', 'https://api.test.nedp.eu/api/metering-data-access-request')
    energy_key = current_app.config.get('NEDP_ENERGY_KEY')
    api_key = current_app.config.get('NEDP_API_KEY')
    
    headers = {
        'accept': '*/*',
        'X-Energy-Id': energy_key,
        'X-API-KEY': api_key,
        'Content-Type': 'application/json'
    }
    
    payload = {
        'from': from_id,
        'fromName': from_name,
        'meteringPointCodes': metering_points,
        'obisCodes': OBIS_CODES
    }
    
    try:
        response = requests.post(api_url, headers=headers, json=payload, timeout=30)
        response.raise_for_status()
        
        return {
            'success': True,
            'status_code': response.status_code,
            'data': response.json(),
            'request_details': {
                'from': from_id,
                'fromName': from_name,
                'metering_points_count': len(metering_points),
                'obis_codes_count': len(OBIS_CODES)
            }
        }
    
    except requests.exceptions.RequestException as e:
        return {
            'success': False,
            'error': str(e),
            'status_code': getattr(e.response, 'status_code', None),
            'response_text': getattr(e.response, 'text', None)
        }
    

#example for call
from flask import Blueprint, jsonify

api_bp = Blueprint('api', __name__)

@api_bp.route('/request-metering-data', methods=['POST'])
def request_metering():
    """Endpoint to request metering data."""
    try:
        result = request_metering_data(sharing_group_id=1)
        return jsonify(result), 200 if result['success'] else 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@api_bp.route('/request-metering-data/<int:sg_id>', methods=['POST'])
def request_metering_for_group(sg_id):
    """Request metering data for specific sharing group."""
    try:
        result = request_metering_data(sharing_group_id=sg_id)
        return jsonify(result), 200 if result['success'] else 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500   

