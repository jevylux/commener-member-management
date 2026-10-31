#!/usr/bin/env python3
"""Test script to verify routes are registered correctly."""

import sys
import os

# Add the app directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'app'))

# Mock the database URI for testing
os.environ['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/test.db'

try:
    from app import app
    
    print("=" * 80)
    print("REGISTERED ROUTES:")
    print("=" * 80)
    
    # Get all routes
    routes = []
    for rule in app.url_map.iter_rules():
        if not rule.endpoint.startswith('static'):
            methods = ','.join(sorted(rule.methods - {'OPTIONS', 'HEAD'}))
            routes.append({
                'methods': methods,
                'path': str(rule),
                'endpoint': rule.endpoint
            })
    
    # Sort by path for easier reading
    routes.sort(key=lambda x: x['path'])
    
    for r in routes:
        print(f"{r['methods']:20s} {r['path']:50s} -> {r['endpoint']}")
    
    print("=" * 80)
    
    # Check specifically for bill routes
    print("\nBILL ROUTES:")
    print("-" * 80)
    bill_routes = [r for r in routes if 'bill' in r['path'] or 'bill' in r['endpoint']]
    if bill_routes:
        for r in bill_routes:
            print(f"{r['methods']:20s} {r['path']:50s} -> {r['endpoint']}")
    else:
        print("NO BILL ROUTES FOUND!")
    
    print("=" * 80)
    
    # Check for accounting routes
    print("\nACCOUNTING ROUTES:")
    print("-" * 80)
    accounting_routes = [r for r in routes if 'accounting' in r['path']]
    for r in accounting_routes:
        print(f"{r['methods']:20s} {r['path']:50s} -> {r['endpoint']}")
    print("=" * 80)
    
    # Check if blueprint was registered
    print("\nBLUEPRINTS:")
    print("-" * 80)
    for bp_name in app.blueprints:
        print(f"  - {bp_name}")
    print("=" * 80)
    
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()
