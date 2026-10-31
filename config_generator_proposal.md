# Config Generator Proposal

## Overview

Create a Python script that automatically generates YAML configuration files for the ComEner-calculator based on the existing database structure.

## Database Analysis

### Tables Used

1. **pods** - Contains all PODs (smart meters) with their type (Production/Consumption)
2. **members** - Member information including names and emails
3. **sharingGroup** - Sharing groups with sgNumber (e.g., "00006640", "00006750")
4. **podSharingGroup** - Junction table linking pods to sharing groups

### Current Sharing Groups

| ID | Name | sgNumber | sgType | Config File Pattern |
|----|------|----------|--------|---------------------|
| 1 | RueDesRomainsUewen | 00006041 | Local | CR00006041.yaml |
| 2 | RueDesRomainsEnnen | 00006640 | Local | CR00006640.yaml |
| 3 | GroupeNational | 00006750 | National | CR00006750.yaml |
| 4 | HallerHenerecht | 00007353 | Local | CR00007353.yaml |
| 5-8 | Others | - | Local | Various |

### OBIS Code Logic

From existing config files, the OBIS suffix pattern is:
- Local groups (RueDesRomainsUewen, RueDesRomainsEnnen): `.2`
- National groups (GroupeNational): `.4`

Consumption: `1-65:1.29.{suffix}`
Production: `1-65:2.29.{suffix}`

## Proposed Solution

### File: `config_generator.py`

```python
#!/usr/bin/env python3
"""
ComEner Config Generator

Generates YAML configuration files for ComEner-calculator based on database data.
"""

import yaml
import sqlite3
import os
from pathlib import Path
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum


class PodType(Enum):
    CONSUMPTION = "Consumption"
    PRODUCTION = "Production"


class GroupType(Enum):
    NATIONAL = "National"
    LOCAL = "Local"


@dataclass
class Pod:
    pod_id: int
    label: str
    pod_type: str
    number: str
    member_firstname: str
    member_name: str
    member_email: str


@dataclass
class SharingGroup:
    sg_id: int
    name: str
    sg_number: str
    sg_type: str


class ConfigGenerator:
    """Generate YAML config files from database data."""
    
    # OBIS suffix mapping based on existing configs
    OBIS_SUFFIX = {
        "National": "4",
        "Local": "2"
    }
    
    def __init__(self, db_path: str, output_dir: str):
        self.db_path = db_path
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
    def get_db_connection(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)
    
    def get_sharing_groups(self) -> List[SharingGroup]:
        """Get all sharing groups from database."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT sgID, sgName, sgNumber, sgType 
            FROM sharingGroup 
            ORDER BY sgName
        """)
        
        groups = [
            SharingGroup(
                sg_id=row[0],
                name=row[1],
                sg_number=row[2],
                sg_type=row[3]
            )
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return groups
    
    def get_pods_for_group(self, sg_id: int) -> List[Pod]:
        """Get all pods assigned to a sharing group."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT 
                p.podsID,
                p.podlabel,
                p.podType,
                p.podNumber,
                m.firstname,
                m.name,
                m.email
            FROM podSharingGroup psg
            JOIN pods p ON psg.podID = p.podsID
            JOIN members m ON p.memberID = m.id
            WHERE psg.sharingGroupID = ?
            ORDER BY p.podType, p.podlabel
        """, (sg_id,))
        
        pods = [
            Pod(
                pod_id=row[0],
                label=row[1],
                pod_type=row[2],
                number=row[3],
                member_firstname=row[4] or "",
                member_name=row[5] or "",
                member_email=row[6] or ""
            )
            for row in cursor.fetchall()
        ]
        
        conn.close()
        return pods
    
    def get_member_display_name(self, pod: Pod) -> str:
        """Generate display name for a member."""
        # Use firstname if available, otherwise use pod label (removing " Consommation"/" Production")
        if pod.member_firstname:
            return pod.member_firstname
        # Fallback: extract name from pod label
        return pod.label.replace(" Consommation", "").replace(" Production", "").replace("-Consommation", "").replace("-Production", "").replace("-Consommatioun", "").replace("-Cons", "").replace("-Produktion", "").replace("-Prod", "")
    
    def deduplicate_emails(self, pods: List[Pod]) -> List[str]:
        """Deduplicate emails for producers (one email per unique member)."""
        seen_emails = set()
        emails = []
        for pod in pods:
            email = pod.member_email
            if email and email not in seen_emails:
                emails.append(email)
                seen_emails.add(email)
            elif not email:
                emails.append("")
        return emails
    
    def build_config(self, group: SharingGroup, pods: List[Pod]) -> Dict:
        """Build the configuration dictionary."""
        obis_suffix = self.OBIS_SUFFIX.get(group.sg_type, "2")
        
        # Separate consumers and producers
        consumers = [p for p in pods if p.pod_type == "Consumption"]
        producers = [p for p in pods if p.pod_type == "Production"]
        
        # Build consumers section
        consumer_names = [self.get_member_display_name(p) for p in consumers]
        consumer_smartmeters = [p.number for p in consumers]
        consumer_obis = [f"1-65:1.29.{obis_suffix}" for _ in consumers]
        consumer_emails = [p.member_email for p in consumers]
        
        # Build producers section
        producer_names = [self.get_member_display_name(p) for p in producers]
        producer_smartmeters = [p.number for p in producers]
        producer_obis = [f"1-65:2.29.{obis_suffix}" for _ in producers]
        # For producers, deduplicate emails (one per member)
        producer_emails = self.deduplicate_emails(producers)
        
        # Handle case where producer emails might be less than names after dedup
        # Pad with empty strings or use the member email
        if len(producer_emails) < len(producer_names):
            # Get unique member emails for producers
            seen = set()
            unique_emails = []
            for p in producers:
                if p.member_email and p.member_email not in seen:
                    unique_emails.append(p.member_email)
                    seen.add(p.member_email)
            producer_emails = unique_emails
        
        config = {
            "consumers": {
                "names": consumer_names,
                "smartmeters": consumer_smartmeters,
                "obiscode": consumer_obis,
                "emails": consumer_emails
            },
            "producers": {
                "names": producer_names,
                "smartmeters": producer_smartmeters,
                "obiscode": producer_obis,
                "emails": producer_emails
            },
            "leneda": {
                "url": "https://api.leneda.lu",
                "energyId": {
                    "header": "X-ENERGY-ID",
                    "value": "LUXE-MA-DU-ZPUGN"
                },
                "apiKey": {
                    "header": "X-API-KEY",
                    "value": "e0e3f107-1836-4717-a090-d1863fe9f30c"
                },
                "api": {
                    "meteringData": "/api/metering-points/"
                }
            },
            "pricing": {
                "kwhprice": 0.11,
                "normalfee": 0.07,
                "network": 0.0759,
                "consumerprice": 0.15,
                "tax": 0.0010,
                "compensation": -0.0376,
                "tva": 0.08
            }
        }
        
        return config
    
    def generate_config(self, sg_number: str) -> Optional[Path]:
        """Generate config file for a specific sharing group."""
        # Find the group by sgNumber
        groups = self.get_sharing_groups()
        group = None
        for g in groups:
            if g.sg_number == sg_number:
                group = g
                break
        
        if not group:
            print(f"Error: Sharing group with number '{sg_number}' not found")
            return None
        
        # Get pods for this group
        pods = self.get_pods_for_group(group.sg_id)
        
        if not pods:
            print(f"Warning: No pods found for sharing group '{group.name}'")
            return None
        
        # Build config
        config = self.build_config(group, pods)
        
        # Generate filename
        filename = f"CR{sg_number}.yaml"
        output_path = self.output_dir / filename
        
        # Write YAML file
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(config, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        
        print(f"Generated: {output_path}")
        print(f"  - {len([p for p in pods if p.pod_type == 'Consumption'])} consumers")
        print(f"  - {len([p for p in pods if p.pod_type == 'Production'])} producers")
        
        return output_path
    
    def generate_all_configs(self) -> List[Path]:
        """Generate config files for all sharing groups with sgNumber."""
        groups = self.get_sharing_groups()
        generated = []
        
        for group in groups:
            if group.sg_number:  # Only generate for groups with sgNumber
                result = self.generate_config(group.sg_number)
                if result:
                    generated.append(result)
        
        return generated
    
    def list_groups(self):
        """List all available sharing groups."""
        groups = self.get_sharing_groups()
        print("\nAvailable Sharing Groups:")
        print("-" * 60)
        print(f"{'ID':<4} {'Name':<30} {'Number':<12} {'Type':<10}")
        print("-" * 60)
        for g in groups:
            print(f"{g.sg_id:<4} {g.name:<30} {g.sg_number or 'N/A':<12} {g.sg_type:<10}")
        print()
    
    def list_pods(self):
        """List all pods with their types."""
        conn = self.get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT p.podsID, p.podlabel, p.podType, m.firstname, m.name
            FROM pods p
            JOIN members m ON p.memberID = m.id
            ORDER BY p.podType, p.podlabel
        """)
        
        print("\nAvailable PODs:")
        print("-" * 70)
        print(f"{'ID':<4} {'Type':<12} {'Label':<30} {'Member':<20}")
        print("-" * 70)
        for row in cursor.fetchall():
            member_name = f"{row[3] or ''} {row[4] or ''}".strip()
            print(f"{row[0]:<4} {row[2]:<12} {row[1]:<30} {member_name:<20}")
        
        conn.close()
        print()


def interactive_mode(generator: ConfigGenerator):
    """Run interactive mode for config generation."""
    import sys
    
    print("\n" + "=" * 60)
    print("  ComEner Config Generator - Interactive Mode")
    print("=" * 60)
    
    while True:
        print("\nOptions:")
        print("  1. List available sharing groups")
        print("  2. List available PODs")
        print("  3. Generate config for a specific sharing group")
        print("  4. Generate configs for ALL sharing groups")
        print("  5. Exit")
        
        choice = input("\nEnter choice (1-5): ").strip()
        
        if choice == "1":
            generator.list_groups()
            
        elif choice == "2":
            generator.list_pods()
            
        elif choice == "3":
            sg_number = input("Enter sharing group number (e.g., 00006640): ").strip()
            if sg_number:
                generator.generate_config(sg_number)
            
        elif choice == "4":
            confirm = input("Generate configs for all groups? (yes/no): ").strip().lower()
            if confirm == "yes":
                generator.generate_all_configs()
            
        elif choice == "5":
            print("Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")


def main():
    """Main entry point."""
    import argparse
    
    # Default paths
    db_path = os.path.expanduser(
        "~/Development/python/ComEner-data-management/database/commEnergy.db"
    )
    output_dir = os.path.expanduser(
        "~/Development/python/ComEner-calculator/configs"
    )
    
    parser = argparse.ArgumentParser(
        description="Generate ComEner calculator config files from database"
    )
    parser.add_argument(
        "--db", "-d",
        default=db_path,
        help=f"Path to SQLite database (default: {db_path})"
    )
    parser.add_argument(
        "--output", "-o",
        default=output_dir,
        help=f"Output directory for config files (default: {output_dir})"
    )
    parser.add_argument(
        "--group", "-g",
        help="Generate config for specific sharing group number (e.g., 00006640)"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Generate configs for all sharing groups"
    )
    parser.add_argument(
        "--list-groups", "-l",
        action="store_true",
        help="List available sharing groups"
    )
    parser.add_argument(
        "--list-pods", "-p",
        action="store_true",
        help="List available PODs"
    )
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="Run in interactive mode"
    )
    
    args = parser.parse_args()
    
    generator = ConfigGenerator(args.db, args.output)
    
    if args.interactive:
        interactive_mode(generator)
    elif args.list_groups:
        generator.list_groups()
    elif args.list_pods:
        generator.list_pods()
    elif args.group:
        generator.generate_config(args.group)
    elif args.all:
        generator.generate_all_configs()
    else:
        # Default: interactive mode
        interactive_mode(generator)


if __name__ == "__main__":
    main()
```

## Usage Examples

### 1. Interactive Mode (default)
```bash
python config_generator.py
```

### 2. Generate specific group
```bash
python config_generator.py -g 00006640
```

### 3. Generate all groups
```bash
python config_generator.py -a
```

### 4. List available groups
```bash
python config_generator.py -l
```

### 5. Custom database/output paths
```bash
python config_generator.py -d /path/to/db.sqlite -o /path/to/output
```

## Sample Output

For `CR00006640.yaml` (RueDesRomainsEnnen):
```yaml
consumers:
  names: ["Marie-Anne", "Johann", "Alain", "Luc", "Romain"]
  smartmeters:
    - "LU0000010637000000000000070232020"
    - "LU0000010637000000000000070232021"
    - ...
  obiscode: ["1-65:1.29.2", "1-65:1.29.2", ...]
  emails: ["muckil@web.de", "gillwe@pt.lu", ...]
producers:
  names: ["Madalin", "Luc", "Alain"]
  smartmeters:
    - "LU0000010637000000000000770392841"
    - ...
  obiscode: ["1-65:2.29.2", "1-65:2.29.2", ...]
  emails: ["m.amzolini@gmail.com", "lschaus@pt.lu", ...]
leneda:
  url: "https://api.leneda.lu"
  energyId:
    header: "X-ENERGY-ID"
    value: "LUXE-MA-DU-ZPUGN"
  apiKey:
    header: "X-API-KEY"
    value: "e0e3f107-1836-4717-a090-d1863fe9f30c"
  api:
    meteringData: "/api/metering-points/"
pricing:
  kwhprice: 0.11
  normalfee: 0.07
  network: 0.0759
  consumerprice: 0.15
  tax: 0.0010
  compensation: -0.0376
  tva: 0.08
```

## Implementation Steps

1. Create `config_generator.py` in the ComEner-data-management directory
2. Ensure PyYAML is installed: `pip install pyyaml`
3. Run with `--list-groups` to see available sharing groups
4. Run with `-g 00006640` to test with one group
5. Verify output matches existing config format
6. Run with `-a` to generate all configs

## Future Enhancements

- Web UI integration for point-and-click selection
- Dry-run mode to preview changes
- Config validation against existing files
- Support for custom pricing per group
- Template overrides for specific edge cases
