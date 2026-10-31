#!/usr/bin/env python3
"""
Leneda Metering Data Access Request Module
============================================
Standalone module for creating metering data access requests via Leneda API.
Can be used as a CLI tool or imported into the Flask app.
"""

import requests
import json
import sys
from typing import List, Dict, Optional, Tuple

# Leneda API Configuration
LENEDA_API_URL = "https://api.leneda.eu/api/metering-data-access-request"

# Your credentials (should be moved to environment variables or config file)
DEFAULT_API_KEY = "e0e3f107-1836-4717-a090-d1863fe9f30c"
DEFAULT_ENERGY_ID = "LUXE-MA-DU-ZPUGN"

# OBIS Codes organized by category and pod type applicability
OBIS_CODES = {
    "basic_consumption": {
        "code": "1-1:1.29.0",
        "unit": "kW",
        "type": "Consumption",
        "description": "Measured active consumption",
        "applies_to": ["Consumption"]
    },
    "basic_production": {
        "code": "1-1:2.29.0",
        "unit": "kW",
        "type": "Production",
        "description": "Measured active production",
        "applies_to": ["Production"]
    },
    "layer1_consumption": {
        "code": "1-65:1.29.1",
        "unit": "kW",
        "type": "Consumption",
        "description": "Consumption covered by production of layer 1 sharing Group (AIR)",
        "applies_to": ["Consumption"]
    },
    "layer2_consumption": {
        "code": "1-65:1.29.3",
        "unit": "kW",
        "type": "Consumption",
        "description": "Consumption covered by production of layer 2 sharing Group (ACR/ACF/AC1)",
        "applies_to": ["Consumption"]
    },
    "layer3_consumption": {
        "code": "1-65:1.29.2",
        "unit": "kW",
        "type": "Consumption",
        "description": "Consumption covered by production of layer 3 sharing Group (CEL)",
        "applies_to": ["Consumption"]
    },
    "layer4_consumption": {
        "code": "1-65:1.29.4",
        "unit": "kW",
        "type": "Consumption",
        "description": "Consumption covered by production of layer 4 sharing Group (APS/CER/CEN)",
        "applies_to": ["Consumption"]
    },
    "remaining_consumption": {
        "code": "1-65:1.29.9",
        "unit": "kW",
        "type": "Consumption",
        "description": "Remaining consumption after sharing invoiced by supplier",
        "applies_to": ["Consumption"]
    },
    "layer1_production": {
        "code": "1-65:2.29.1",
        "unit": "kW",
        "type": "Production",
        "description": "Production shared within layer 1 sharing Group (AIR)",
        "applies_to": ["Production"]
    },
    "layer2_production": {
        "code": "1-65:2.29.3",
        "unit": "kW",
        "type": "Production",
        "description": "Production shared within layer 2 sharing Group (ACR/ACF/AC1)",
        "applies_to": ["Production"]
    },
    "layer3_production": {
        "code": "1-65:2.29.2",
        "unit": "kW",
        "type": "Production",
        "description": "Production shared within layer 3 sharing Group (CEL)",
        "applies_to": ["Production"]
    },
    "layer4_production": {
        "code": "1-65:2.29.4",
        "unit": "kW",
        "type": "Production",
        "description": "Production shared within layer 4 sharing Group (APS/CER/CEN)",
        "applies_to": ["Production"]
    },
    "remaining_production": {
        "code": "1-65:2.29.9",
        "unit": "kW",
        "type": "Production",
        "description": "Remaining production after sharing sold to market",
        "applies_to": ["Production"]
    }
}

# Gas OBIS codes (separate category)
GAS_OBIS_CODES = {
    "gas_volume": {
        "code": "7-1:99.23.15",
        "unit": "m³",
        "type": "Consumption",
        "description": "Measured consumed volume",
        "applies_to": ["Consumption"]
    },
    "gas_standard_volume": {
        "code": "7-1:99.23.17",
        "unit": "Nm³",
        "type": "Consumption",
        "description": "Measured consumed standard volume",
        "applies_to": ["Consumption"]
    },
    "gas_energy": {
        "code": "7-20:99.33.17",
        "unit": "kWh",
        "type": "Consumption",
        "description": "Measured consumed energy",
        "applies_to": ["Consumption"]
    }
}


def get_all_obis_codes() -> Dict[str, Dict]:
    """Return all OBIS codes with their details."""
    #all_codes = {**OBIS_CODES, **GAS_OBIS_CODES}
    all_codes = {**OBIS_CODES}  # consider only Energy OBIS codes for now, gas codes can be added separately if needed
    return all_codes


def get_obis_codes_for_pod_type(pod_type: str, include_gas: bool = False) -> Dict[str, Dict]:
    """
    Get OBIS codes applicable to a specific pod type.
    
    Args:
        pod_type: 'Production' or 'Consumption'
        include_gas: Whether to include gas OBIS codes
    
    Returns:
        Dictionary of applicable OBIS codes
    """
    applicable = {}
    
    for key, code_info in OBIS_CODES.items():
        if pod_type in code_info.get("applies_to", []):
            applicable[key] = code_info
    
    '''if include_gas and pod_type == "Consumption":
        for key, code_info in GAS_OBIS_CODES.items():
            applicable[key] = code_info
    '''
    return applicable


def get_member_pods_from_db(member_id: int, db_session=None):
    """
    Get all pods for a member from the database.
    
    Args:
        member_id: The member's database ID
        db_session: SQLAlchemy session (if None, will create one)
    
    Returns:
        List of pod dictionaries with podNumber, podType, podlabel
    """
    try:
        from models import Pod
        
        if db_session is None:
            from app import db
            db_session = db.session
        
        pods = db_session.query(Pod).filter_by(memberID=member_id).all()
        
        return [
            {
                "podsID": pod.podsID,
                "podlabel": pod.podlabel,
                "podType": pod.podType,
                "podNumber": pod.podNumber
            }
            for pod in pods if pod.podNumber
        ]
    except Exception as e:
        print(f"Error fetching pods: {e}")
        return []


def get_member_info_from_db(member_id: int, db_session=None):
    """
    Get member information from the database.
    
    Args:
        member_id: The member's database ID
        db_session: SQLAlchemy session
    
    Returns:
        Dictionary with member info
    """
    try:
        from models import Member
        
        if db_session is None:
            from app import db
            db_session = db.session
        
        member = db_session.query(Member).get(member_id)
        
        if not member:
            return None
        
        return {
            "id": member.id,
            "name": member.name,
            "firstname": member.firstname,
            "energyID": member.energyID,
            "energyIDName": member.energyIDName
        }
    except Exception as e:
        print(f"Error fetching member: {e}")
        return None


def request_metering_data_access(
    from_energy_id: str,
    from_name: str,
    metering_point_codes: List[str],
    obis_codes: List[str],
    api_key: str = DEFAULT_API_KEY,
    sender_energy_id: str = DEFAULT_ENERGY_ID
) -> Dict:
    """
    Send a metering data access request to the Leneda API.
    
    Args:
        from_energy_id: Energy ID of the person/company receiving access
        from_name: Exact name as in Leneda
        metering_point_codes: List of metering point codes (pod numbers)
        obis_codes: List of OBIS codes to request access for
        api_key: Your Leneda API key
        sender_energy_id: Your Energy ID (the requester)
    
    Returns:
        Dictionary with success status and response details
    """
    headers = {
        "accept": "*/*",
        "X-Energy-Id": sender_energy_id,
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }
    
    payload = {
        "from": from_energy_id,
        "fromName": from_name,
        "meteringPointCodes": metering_point_codes,
        "obisCodes": obis_codes
    }
    
    try:
        response = requests.post(
            LENEDA_API_URL,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        response.raise_for_status()
        
        return {
            "success": True,
            "status_code": response.status_code,
            "data": response.json() if response.text else {},
            "request_details": {
                "from": from_energy_id,
                "fromName": from_name,
                "metering_points_count": len(metering_point_codes),
                "obis_codes_count": len(obis_codes)
            }
        }
    
    except requests.exceptions.RequestException as e:
        error_detail = str(e)
        status_code = None
        response_text = None
        
        if hasattr(e, 'response') and e.response is not None:
            status_code = e.response.status_code
            try:
                response_text = e.response.json()
            except:
                response_text = e.response.text
        
        return {
            "success": False,
            "error": error_detail,
            "status_code": status_code,
            "response_text": response_text
        }


def request_access_for_member(
    member_id: int,
    selected_obis_codes: List[str],
    db_session=None,
    api_key: str = DEFAULT_API_KEY,
    sender_energy_id: str = DEFAULT_ENERGY_ID
) -> Dict:
    """
    Request metering data access for a specific member.
    
    When a member has mixed Consumption and Production pods, sends separate
    requests per pod type to avoid Leneda assigning wrong OBIS codes.
    
    Args:
        member_id: The member's database ID
        selected_obis_codes: List of OBIS code strings to request
        db_session: SQLAlchemy session
        api_key: Leneda API key
        sender_energy_id: Sender's Energy ID
    
    Returns:
        Result dictionary with combined results from all requests
    """
    # Get member info
    member = get_member_info_from_db(member_id, db_session)
    
    if not member:
        return {
            "success": False,
            "error": f"Member with ID {member_id} not found"
        }
    
    if not member.get("energyID"):
        return {
            "success": False,
            "error": f"Member {member['firstname']} {member['name']} does not have an Energy ID configured"
        }
    
    # Get member's pods
    pods = get_member_pods_from_db(member_id, db_session)
    
    if not pods:
        return {
            "success": False,
            "error": f"No pods with metering point numbers found for member {member['firstname']} {member['name']}"
        }
    
    # Determine from_name
    from_name = member.get("energyIDName") or f"{member.get('firstname', '')} {member.get('name', '')}".strip()
    
    # Separate pods by type
    consumption_pods = [p for p in pods if p["podType"] == "Consumption"]
    production_pods = [p for p in pods if p["podType"] == "Production"]
    
    # Get applicable OBIS codes for each pod type from our registry
    consumption_obis_registry = get_obis_codes_for_pod_type("Consumption")
    production_obis_registry = get_obis_codes_for_pod_type("Production")
    
    # Build lookup sets of valid OBIS codes per type
    valid_consumption_codes = {c["code"] for c in consumption_obis_registry.values()}
    valid_production_codes = {c["code"] for c in production_obis_registry.values()}
    
    # Filter selected OBIS codes to only include valid ones per pod type
    consumption_obis = [code for code in selected_obis_codes if code in valid_consumption_codes]
    production_obis = [code for code in selected_obis_codes if code in valid_production_codes]
    
    # Track results
    results = []
    any_success = False
    all_errors = []
    
    # Send request for Consumption pods (if any)
    if consumption_pods and consumption_obis:
        consumption_metering_points = [p["podNumber"] for p in consumption_pods]
        
        result = request_metering_data_access(
            from_energy_id=member["energyID"],
            from_name=from_name,
            metering_point_codes=consumption_metering_points,
            obis_codes=consumption_obis,
            api_key=api_key,
            sender_energy_id=sender_energy_id
        )
        
        result["pod_type"] = "Consumption"
        result["pods"] = consumption_pods
        results.append(result)
        
        if result["success"]:
            any_success = True
        else:
            all_errors.append(f"Consumption request failed: {result.get('error', 'Unknown error')}")
    
    # Send request for Production pods (if any)
    if production_pods and production_obis:
        production_metering_points = [p["podNumber"] for p in production_pods]
        
        result = request_metering_data_access(
            from_energy_id=member["energyID"],
            from_name=from_name,
            metering_point_codes=production_metering_points,
            obis_codes=production_obis,
            api_key=api_key,
            sender_energy_id=sender_energy_id
        )
        
        result["pod_type"] = "Production"
        result["pods"] = production_pods
        results.append(result)
        
        if result["success"]:
            any_success = True
        else:
            all_errors.append(f"Production request failed: {result.get('error', 'Unknown error')}")
    
    # Check if any requests were made
    if not results:
        return {
            "success": False,
            "error": "No valid pod type / OBIS code combinations found for this member",
            "member": member,
            "pods": pods
        }
    
    # Build combined result
    combined_result = {
        "success": any_success,
        "member": member,
        "pods": pods,
        "requests": results,
        "request_count": len(results)
    }
    
    if not any_success:
        combined_result["error"] = "; ".join(all_errors) if all_errors else "All requests failed"
    
    return combined_result


# CLI Interface
def cli_main():
    """Command-line interface for standalone usage."""
    print("=" * 60)
    print("Leneda Metering Data Access Request Tool")
    print("=" * 60)
    print()
    
    # Import here to avoid issues when Flask isn't running
    try:
        from app import db
        from models import Member
    except ImportError as e:
        print(f"Error: Could not import Flask app models: {e}")
        print("This tool should be run from the project directory with the virtualenv activated.")
        sys.exit(1)
    
    # List members
    print("Loading members...")
    members = Member.query.all()
    
    if not members:
        print("No members found in database.")
        sys.exit(1)
    
    print("\nSelect a member:")
    for i, member in enumerate(members, 1):
        name = f"{member.firstname} {member.name}".strip() or "[No name]"
        energy_info = f"Energy ID: {member.energyID}" if member.energyID else "No Energy ID"
        print(f"  {i}. {name} ({energy_info})")
    
    print()
    
    # Get member selection
    while True:
        try:
            choice = input("Enter member number: ").strip()
            member_idx = int(choice) - 1
            if 0 <= member_idx < len(members):
                selected_member = members[member_idx]
                break
            else:
                print("Invalid selection. Please try again.")
        except ValueError:
            print("Please enter a valid number.")
    
    # Get member's pods
    pods = Pod.query.filter_by(memberID=selected_member.id).all()
    pods_with_numbers = [p for p in pods if p.podNumber]
    
    if not pods_with_numbers:
        print(f"\nError: No pods with metering point numbers found for {selected_member.firstname} {selected_member.name}")
        sys.exit(1)
    
    print(f"\nSelected: {selected_member.firstname} {selected_member.name}")
    print(f"Energy ID: {selected_member.energyID or 'NOT SET'}")
    print(f"\nPods found ({len(pods_with_numbers)}):")
    
    for pod in pods_with_numbers:
        print(f"  - {pod.podlabel} ({pod.podType}): {pod.podNumber}")
    
    # Categorize pods
    consumption_pods = [p for p in pods_with_numbers if p.podType == "Consumption"]
    production_pods = [p for p in pods_with_numbers if p.podType == "Production"]
    
    # Show applicable OBIS codes
    print("\n" + "=" * 60)
    print("Available OBIS Codes")
    print("=" * 60)
    
    if consumption_pods:
        print("\n📥 For Consumption Pods:")
        consumption_codes = get_obis_codes_for_pod_type("Consumption", include_gas=True)
        for i, (key, code_info) in enumerate(consumption_codes.items(), 1):
            print(f"  {i:2d}. {code_info['code']:20s} - {code_info['description']}")
    
    if production_pods:
        print("\n📤 For Production Pods:")
        production_codes = get_obis_codes_for_pod_type("Production")
        for i, (key, code_info) in enumerate(production_codes.items(), 1):
            print(f"  {i:2d}. {code_info['code']:20s} - {code_info['description']}")
    
    # Common codes for all
    print("\n⚡ Common Codes (applicable to both types):")
    common_codes = {
        k: v for k, v in OBIS_CODES.items() 
        if len(v.get("applies_to", [])) == 2
    }
    for i, (key, code_info) in enumerate(common_codes.items(), 1):
        print(f"  {i:2d}. {code_info['code']:20s} - {code_info['description']}")
    
    # Get OBIS code selection
    print("\n" + "-" * 60)
    print("Enter OBIS codes to request (comma-separated)")
    print("Examples: 1-1:1.29.0, 1-1:2.29.0")
    print("Or type 'all' to request all applicable codes")
    print("-" * 60)
    
    obis_input = input("OBIS codes: ").strip()
    
    if obis_input.lower() == "all":
        # Get all applicable codes based on pod types
        selected_codes = []
        if consumption_pods:
            selected_codes.extend([c["code"] for c in consumption_codes.values()])
        if production_pods:
            selected_codes.extend([c["code"] for c in production_codes.values()])
        selected_codes = list(set(selected_codes))  # Remove duplicates
    else:
        selected_codes = [c.strip() for c in obis_input.split(",") if c.strip()]
    
    if not selected_codes:
        print("No OBIS codes selected. Exiting.")
        sys.exit(0)
    
    print(f"\nSelected {len(selected_codes)} OBIS code(s)")
    print("\nSending request to Leneda API...")
    
    # Make the request
    result = request_access_for_member(
        member_id=selected_member.id,
        selected_obis_codes=selected_codes,
        db_session=db.session
    )
    
    print("\n" + "=" * 60)
    if result["success"]:
        print("✅ Request(s) sent successfully!")
        print(f"Total requests sent: {result.get('request_count', 1)}")
        
        for req in result.get("requests", []):
            pod_type = req.get("pod_type", "Unknown")
            print(f"\n📋 {pod_type} Request:")
            print(f"  Status: {req.get('status_code', 'N/A')}")
            print(f"  Metering points: {req.get('request_details', {}).get('metering_points_count', 0)}")
            print(f"  OBIS codes: {req.get('request_details', {}).get('obis_codes_count', 0)}")
            if req.get("data"):
                print(f"  Response: {json.dumps(req['data'], indent=2)[:200]}...")
    else:
        print("❌ Request(s) failed!")
        print(f"Error: {result.get('error', 'Unknown error')}")
        
        for req in result.get("requests", []):
            if not req.get("success"):
                pod_type = req.get("pod_type", "Unknown")
                print(f"\n📋 {pod_type} Request Failed:")
                print(f"  Error: {req.get('error', 'Unknown error')}")
                if req.get("status_code"):
                    print(f"  Status Code: {req['status_code']}")
                if req.get("response_text"):
                    print(f"  Response: {req['response_text'][:200]}...")
    print("=" * 60)


if __name__ == "__main__":
    cli_main()
