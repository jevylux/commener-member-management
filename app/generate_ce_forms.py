#!/usr/bin/env python3
"""
Generate CE (Communauté Energétique) forms for Stroum Deelen
- CE_Formulaire_de_modification : main form with total POD count
- CE_Annexe_2 : one per member with their POD(s)

Uses PyMuPDF to draw text directly on the page at widget positions,
then removes all widgets. This bypasses form field rendering issues.
"""

import fitz  # PyMuPDF
from datetime import datetime
import os
import re

# Template paths (use EMPTY templates provided by Marc)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
TPL_MODIFICATION = os.path.join(SCRIPT_DIR, "pdf", "templates", "CE_Formulaire_de_modification_empty.pdf")
TPL_ANNEXE2 = os.path.join(SCRIPT_DIR, "pdf", "templates", "CE_Annexe_2_CEN_empty.pdf")

OUTPUT_DIR = "/Users/marcdurbach/clawd/output"


def sanitize_filename(name):
    """Remove/replace characters not safe in filenames."""
    name = re.sub(r'[^\w\s-]', '', name)
    name = re.sub(r'\s+', '_', name)
    return name


def draw_text_in_field(page, rect, text, font_size=10, color=(0, 0, 0)):
    """Draw text centered vertically in a field rectangle."""
    # Position: left-aligned with small margin, vertically centered
    x = rect.x0 + 3
    
    # Calculate vertical center
    y = rect.y0 + (rect.height / 2) + (font_size * 0.35)
    
    # Insert text
    page.insert_text(
        (x, y),
        str(text),
        fontsize=font_size,
        fontname="helv",
        color=color
    )


def draw_checkbox(page, rect, checked=True, size=None):
    """Draw a checkbox mark (X or empty box)."""
    if size is None:
        size = min(rect.width, rect.height)
    
    margin = size * 0.15
    
    if checked:
        # Draw an X
        shape = page.new_shape()
        shape.draw_line(
            (rect.x0 + margin, rect.y0 + margin),
            (rect.x1 - margin, rect.y1 - margin)
        )
        shape.draw_line(
            (rect.x0 + margin, rect.y1 - margin),
            (rect.x1 - margin, rect.y0 + margin)
        )
        shape.finish(width=1.5, color=(0, 0, 0))
        shape.commit()


def fill_pdf_fields(template_path, fields_dict, output_path):
    """
    Fill PDF by drawing text directly on page at widget positions,
    then removing all widgets.
    """
    doc = fitz.open(template_path)
    
    filled_count = 0
    widgets_to_remove = []
    
    for page in doc:
        for widget in page.widgets():
            field_name = widget.field_name
            if field_name not in fields_dict:
                continue
            
            value = fields_dict[field_name]
            rect = widget.rect
            
            if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
                # Draw checkbox
                draw_checkbox(page, rect, checked=(value == "/Yes"))
            else:
                # Draw text
                draw_text_in_field(page, rect, str(value))
            
            widgets_to_remove.append((page, widget))
            filled_count += 1
    
    # Remove all widgets
    for page, widget in widgets_to_remove:
        page.delete_widget(widget)
    
    # Save
    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    
    print(f"Filled {filled_count} fields")
    return output_path


def generate_modification_form(sharing_group_id, representative_name, date_application, total_pods, output_dir=OUTPUT_DIR):
    """Generate the main modification form."""
    fields = {
        "convention": sharing_group_id,
        "representant": representative_name,
        "Date application 1": date_application,
        "Nombre": str(total_pods),
        "Check Box 48": "/Yes",
    }
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_sg = sanitize_filename(sharing_group_id)
    filename = f"CE_Modification_{safe_sg}_{ts}.pdf"
    output_path = os.path.join(output_dir, filename)
    
    fill_pdf_fields(TPL_MODIFICATION, fields, output_path)
    
    print(f"✅ Generated modification form: {filename} ({total_pods} PODs total)")
    return output_path


def generate_annexe2(sharing_group_id, member_name, pods, output_dir=OUTPUT_DIR):
    """Generate Annexe 2 for one member."""
    fields = {
        "convention 2": sharing_group_id,
        "nom société 2": member_name,
    }
    
    # POD fields mapping - 10 POD lines (10182-10191)
    pod_base_names = [
        "Page 6 - POD - ligne 1 _ 10182",
        "Page 6 - POD - ligne 1 _ 10183",
        "Page 6 - POD - ligne 1 _ 10184",
        "Page 6 - POD - ligne 1 _ 10185",
        "Page 6 - POD - ligne 1 _ 10186",
        "Page 6 - POD - ligne 1 _ 10187",
        "Page 6 - POD - ligne 1 _ 10188",
        "Page 6 - POD - ligne 1 _ 10189",
        "Page 6 - POD - ligne 1 _ 10190",
        "Page 6 - POD - ligne 1 _ 10191",
    ]
    
    # Checkbox pairs: LEFT = consumption, RIGHT = production
    checkbox_pairs = [
        ("Page 7 - Checkbox 10", "Page 7 - Checkbox 1-1"),   # line 1
        ("Page 7 - Checkbox 14", "Page 7 - Checkbox 15"),   # line 2
        ("Page 7 - Checkbox 16", "Page 7 - Checkbox 17"),   # line 3
        ("Page 7 - Checkbox 18", "Page 7 - Checkbox 19"),   # line 4
        ("Page 7 - Checkbox 20", "Page 7 - Checkbox 21"),   # line 5
        ("Page 7 - Checkbox 22", "Page 7 - Checkbox 23"),   # line 6
        ("Page 7 - Checkbox 24", "Page 7 - Checkbox 25"),   # line 7
        ("Page 7 - Checkbox 26", "Page 7 - Checkbox 27"),   # line 8
        ("Page 7 - Checkbox 28", "Page 7 - Checkbox 29"),   # line 9
        ("Page 7 - Checkbox 30", "Page 7 - Checkbox 31"),   # line 10
    ]
    
    # kVA/kWh fields: kVA 2-11 and kWh 2-11 (maps to POD index 0-9)
    kva_fields = [f"kVA {i}" for i in range(2, 12)]
    kwh_fields = [f"kWh {i}" for i in range(2, 12)]
    
    for i, pod in enumerate(pods[:10]):  # max 10 PODs per member
        # Fill POD number (with "LU" prefix on page 2)
        fields[pod_base_names[i]] = pod.get("number", "")
        
        # Fill checkboxes: LEFT = consumption, RIGHT = production
        conso_cb, prod_cb = checkbox_pairs[i]
        pod_type = pod.get("type", "").lower()
        if pod_type in ("production", "prod", "p"):
            fields[prod_cb] = "/Yes"   # RIGHT checkbox
            fields[conso_cb] = "/Off"  # LEFT checkbox
        elif pod_type in ("consumption", "conso", "c"):
            fields[prod_cb] = "/Off"   # RIGHT checkbox
            fields[conso_cb] = "/Yes"  # LEFT checkbox
        elif pod_type in ("both", "b"):
            fields[prod_cb] = "/Yes"   # RIGHT checkbox
            fields[conso_cb] = "/Yes"  # LEFT checkbox
        else:
            fields[prod_cb] = "/Off"
            fields[conso_cb] = "/Off"
        
        # Fill kVA (puissance souscrite) and kWh (batterie)
        fields[kva_fields[i]] = pod.get("kva", "")
        fields[kwh_fields[i]] = pod.get("kwh", "")
    
    # Fill chiffre fields on page 1 (WITHOUT "LU" prefix)
    if pods:
        for i, pod in enumerate(pods[:10]):
            pod_num = pod.get("number", "")
            # Strip "LU" prefix for chiffre fields
            chiffre_val = pod_num[2:] if pod_num.upper().startswith("LU") else pod_num
            if i == 0:
                fields["chiffre"] = chiffre_val
            else:
                fields[f"chiffre {i}"] = chiffre_val
    
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_sg = sanitize_filename(sharing_group_id)
    safe_member = sanitize_filename(member_name)
    filename = f"CE_Annexe2_{safe_sg}_{safe_member}_{ts}.pdf"
    output_path = os.path.join(output_dir, filename)
    
    fill_pdf_fields(TPL_ANNEXE2, fields, output_path)
    
    print(f"✅ Generated annexe 2: {filename} ({len(pods)} PODs)")
    return output_path


def generate_all_forms(sharing_group_id, representative_name, date_application, members):
    """Generate all forms for a sharing group."""
    total_pods = sum(len(m["pods"]) for m in members)
    
    results = {
        "modification_form": None,
        "annexes": []
    }
    
    mod_path = generate_modification_form(sharing_group_id, representative_name, date_application, total_pods)
    results["modification_form"] = mod_path
    
    for member in members:
        ann_path = generate_annexe2(sharing_group_id, member["name"], member["pods"])
        results["annexes"].append({
            "member": member["name"],
            "path": ann_path,
            "pods_count": len(member["pods"])
        })
    
    return results


if __name__ == "__main__":
    members_example = [
        {
            "name": "Durbach Marc",
            "pods": [
                {"number": "LU0000010637000000000000070232023", "type": "consumption", "kva": "9", "kwh": ""},
                {"number": "LU0000010637000000000000770232023", "type": "production", "kva": "11.6", "kwh": "15"}
            ]
        }
    ]
    
    results = generate_all_forms(
        sharing_group_id="CR00006640",
        representative_name="Durbach Marc",
        date_application="02/05/2026",
        members=members_example
    )
    
    print("\n📁 Generated files:")
    print(f"  Modification form: {results['modification_form']}")
    for ann in results['annexes']:
        print(f"  Annexe 2 ({ann['member']}): {ann['path']}")
