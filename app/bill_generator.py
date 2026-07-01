#!/usr/bin/env python3
"""
Bill Generator Module for ComEner Flask Application

Generates individual PDF bills for members from quarterly report data.
Uses PyMuPDF (fitz) for PDF generation.
"""

import fitz  # PyMuPDF
import os
import re
from datetime import datetime
from decimal import Decimal
from typing import List, Dict, Optional, Tuple


class BillGenerator:
    """Generate PDF bills for members from quarterly report data."""
    
    def __init__(self, output_dir: str = None):
        """
        Initialize the bill generator.
        
        Args:
            output_dir: Directory where bills will be saved. Defaults to 'bills' folder in current directory.
        """
        if output_dir is None:
            output_dir = os.path.join(os.getcwd(), 'bills')
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
    def sanitize_filename(self, name: str) -> str:
        """Remove/replace characters not safe in filenames."""
        name = re.sub(r'[^\w\s-]', '', name)
        name = re.sub(r'\s+', '_', name)
        return name
    
    def create_bill_folder(self, year: int, quarter: int) -> str:
        """
        Create a folder for bills of a specific quarter.
        
        Args:
            year: The year
            quarter: The quarter (1-4)
            
        Returns:
            Path to the created folder
        """
        folder_name = f"_bills_{year}-Q{quarter}"
        folder_path = os.path.join(self.output_dir, folder_name)
        os.makedirs(folder_path, exist_ok=True)
        return folder_path
    
    def generate_bill(
        self,
        member_id: int,
        member_name: str,
        member_firstname: str,
        member_email: str,
        member_address: str,
        year: int,
        quarter: int,
        accounting_total: float,
        membership_fee: float,
        total_amount: float,
        output_folder: str
    ) -> Tuple[str, str]:
        """
        Generate a PDF bill for a single member.
        
        Args:
            member_id: Member database ID
            member_name: Member last name
            member_firstname: Member first name
            member_email: Member email address
            member_address: Member physical address
            year: Billing year
            quarter: Billing quarter (1-4)
            accounting_total: Total consumption/production amount
            membership_fee: Annual membership fee amount
            total_amount: Total amount to pay
            output_folder: Folder to save the PDF
            
        Returns:
            Tuple of (filename, full_path)
        """
        # Create filename
        safe_name = self.sanitize_filename(f"{member_firstname}_{member_name}")
        filename = f"Bill_{year}_Q{quarter}_{safe_name}_{member_id}.pdf"
        filepath = os.path.join(output_folder, filename)
        
        # Create PDF document
        doc = fitz.open()
        page = doc.new_page(width=595, height=842)  # A4 size in points
        
        # Colors
        header_color = (0.1, 0.3, 0.5)  # Dark blue
        text_color = (0, 0, 0)  # Black
        accent_color = (0.8, 0.2, 0.2)  # Red for amounts
        
        # Fonts
        font_header = "helv"
        font_body = "helv"
        
        # Starting position
        margin = 50
        y = 50
        line_height = 18
        
        # Header - Organization Name
        y += 20
        page.insert_text((margin, y), "Communauté Energétique", 
                         fontsize=16, fontname=font_header, color=header_color)
        y += line_height + 5
        page.insert_text((margin, y), "Bill / Facture / Rechnung", 
                         fontsize=14, fontname=font_header, color=text_color)
        
        # Bill reference number
        y += line_height * 2
        bill_ref = f"Ref: {year}-Q{quarter}-{member_id:05d}"
        page.insert_text((margin, y), bill_ref, fontsize=10, fontname=font_body, color=text_color)
        
        # Date
        y += line_height
        bill_date = datetime.now().strftime("%Y-%m-%d")
        page.insert_text((margin, y), f"Date: {bill_date}", fontsize=10, fontname=font_body, color=text_color)
        
        # Member Information Box
        y += line_height * 2
        # Draw box around member info
        box_rect = fitz.Rect(margin, y - 10, 545, y + 80)
        shape = page.new_shape()
        shape.draw_rect(box_rect)
        shape.finish(width=1, color=(0.7, 0.7, 0.7))
        shape.commit()
        
        page.insert_text((margin + 5, y), "Member / Membre / Member:", 
                         fontsize=10, fontname=font_body, color=header_color)
        y += line_height
        page.insert_text((margin + 5, y), f"{member_firstname} {member_name}", 
                         fontsize=12, fontname=font_body, color=text_color)
        y += line_height
        
        if member_address:
            address_lines = member_address.split('\n')[:2]  # Limit to 2 lines
            for addr_line in address_lines:
                page.insert_text((margin + 5, y), addr_line.strip(), 
                               fontsize=9, fontname=font_body, color=text_color)
                y += line_height - 3
        
        if member_email:
            y += 5
            page.insert_text((margin + 5, y), f"Email: {member_email}", 
                           fontsize=9, fontname=font_body, color=text_color)
        
        # Billing Period
        y += line_height * 2.5
        page.insert_text((margin, y), f"Billing Period / Période de facturation / Abrechnungszeitraum:", 
                         fontsize=11, fontname=font_body, color=header_color)
        y += line_height
        
        quarter_months = {
            1: "January - March",
            2: "April - June", 
            3: "July - September",
            4: "October - December"
        }
        months = quarter_months.get(quarter, "Unknown")
        
        page.insert_text((margin, y), f"{year} - Quarter {quarter} ({months})", 
                         fontsize=10, fontname=font_body, color=text_color)
        
        # Amounts Table Header
        y += line_height * 2.5
        # Draw table header background
        header_rect = fitz.Rect(margin, y - 5, 545, y + 20)
        shape = page.new_shape()
        shape.draw_rect(header_rect)
        shape.finish(fill=(0.95, 0.95, 0.95), color=(0.7, 0.7, 0.7))
        shape.commit()
        
        page.insert_text((margin + 5, y + 10), "Description", 
                         fontsize=10, fontname=font_body, color=header_color)
        page.insert_text((400, y + 10), "Amount", 
                         fontsize=10, fontname=font_body, color=header_color)
        
        # Table content
        y += line_height * 1.5
        
        # Row 1: Consumption/Production
        page.insert_text((margin + 5, y), "Energy Consumption/Production (Consommation/Production)", 
                         fontsize=9, fontname=font_body, color=text_color)
        page.insert_text((400, y), f"{accounting_total:,.2f} €", 
                         fontsize=9, fontname=font_body, color=text_color)
        y += line_height
        
        # Row 2: Membership Fee
        page.insert_text((margin + 5, y), "Membership Fee (Cotisation annuelle)", 
                         fontsize=9, fontname=font_body, color=text_color)
        page.insert_text((400, y), f"-{membership_fee:,.2f} €", 
                         fontsize=9, fontname=font_body, color=text_color)
        y += line_height
        
        # Separator line
        y += 5
        shape = page.new_shape()
        shape.draw_line((margin, y), (545, y))
        shape.finish(width=1, color=(0.5, 0.5, 0.5))
        shape.commit()
        y += line_height
        
        # Total
        page.insert_text((margin + 5, y), "TOTAL AMOUNT DUE / MONTANT TOTAL / GESAMTBETRAG:", 
                         fontsize=11, fontname=font_header, color=header_color)
        
        # Highlight total amount
        total_color = accent_color if total_amount > 0 else (0.1, 0.5, 0.1)
        page.insert_text((400, y), f"{total_amount:,.2f} €", 
                         fontsize=12, fontname=font_header, color=total_color)
        
        # Payment Information
        y += line_height * 2
        if total_amount > 0:
            page.insert_text((margin, y), "Payment Information / Informations de paiement / Zahlungsinformationen:", 
                           fontsize=10, fontname=font_body, color=header_color)
            y += line_height
            page.insert_text((margin, y), "Please transfer the amount to the following account:", 
                           fontsize=9, fontname=font_body, color=text_color)
            y += line_height
            page.insert_text((margin + 10, y), "Account: [Your Bank Account Details Here]", 
                           fontsize=9, fontname=font_body, color=text_color)
            y += line_height
            page.insert_text((margin + 10, y), f"Reference: {bill_ref}", 
                           fontsize=9, fontname=font_body, color=text_color)
        else:
            page.insert_text((margin, y), "No payment required / Aucun paiement requis / Keine Zahlung erforderlich", 
                           fontsize=10, fontname=font_body, color=(0.1, 0.5, 0.1))
        
        # Footer
        y = 780
        page.insert_text((margin, y), "---", fontsize=8, fontname=font_body, color=(0.5, 0.5, 0.5))
        y += line_height - 5
        page.insert_text((margin, y), "Communauté Energétique - Energy Sharing Community", 
                         fontsize=8, fontname=font_body, color=(0.5, 0.5, 0.5))
        
        # Save document
        doc.save(filepath)
        doc.close()
        
        return filename, filepath
    
    def generate_bills_from_quarterly_data(
        self,
        year: int,
        quarter: int,
        member_data: List[Dict],
        db_session=None
    ) -> Dict:
        """
        Generate bills for all members in a quarterly report.
        
        Args:
            year: The billing year
            quarter: The billing quarter (1-4)
            member_data: List of dicts containing member billing data
            db_session: SQLAlchemy session to fetch full member details
            
        Returns:
            Dict with 'folder', 'bills' (list of bill info), and 'total_count'
        """
        from app.models import Member
        
        # Create folder for this batch
        folder_path = self.create_bill_folder(year, quarter)
        
        bills = []
        errors = []
        
        for data in member_data:
            try:
                member_id = data.get('member_id')
                
                # Get full member details if db_session provided
                if db_session and member_id:
                    member = db_session.query(Member).get(member_id)
                    if member:
                        member_name = member.name
                        member_firstname = member.firstname
                        member_email = member.email or ''
                        member_address = member.address or ''
                    else:
                        # Fallback to data provided
                        member_name = data.get('name', 'Unknown')
                        member_firstname = data.get('firstname', '')
                        member_email = ''
                        member_address = ''
                else:
                    member_name = data.get('name', 'Unknown')
                    member_firstname = data.get('firstname', '')
                    member_email = ''
                    member_address = ''
                
                # Generate bill
                filename, filepath = self.generate_bill(
                    member_id=member_id or 0,
                    member_name=member_name,
                    member_firstname=member_firstname,
                    member_email=member_email,
                    member_address=member_address,
                    year=year,
                    quarter=quarter,
                    accounting_total=float(data.get('accounting_total', 0)),
                    membership_fee=float(data.get('membership_fee', 0)),
                    total_amount=float(data.get('total_amount', 0)),
                    output_folder=folder_path
                )
                
                bills.append({
                    'member_id': member_id,
                    'member_name': f"{member_firstname} {member_name}".strip(),
                    'member_email': member_email,
                    'filename': filename,
                    'filepath': filepath,
                    'total_amount': data.get('total_amount', 0),
                    'status': 'generated'
                })
                
            except Exception as e:
                errors.append({
                    'member_id': data.get('member_id'),
                    'member_name': data.get('name', 'Unknown'),
                    'error': str(e)
                })
        
        return {
            'folder': os.path.basename(folder_path),
            'folder_path': folder_path,
            'year': year,
            'quarter': quarter,
            'bills': bills,
            'errors': errors,
            'total_count': len(bills),
            'error_count': len(errors)
        }


# Convenience function for direct usage
def generate_bills_for_quarter(
    year: int,
    quarter: int,
    member_data: List[Dict],
    output_dir: str = None,
    db_session=None
) -> Dict:
    """
    Convenience function to generate bills for a quarter.
    
    Args:
        year: Billing year
        quarter: Billing quarter (1-4)
        member_data: List of member billing data
        output_dir: Output directory (optional)
        db_session: Database session for fetching member details
        
    Returns:
        Dict with bill generation results
    """
    generator = BillGenerator(output_dir=output_dir)
    return generator.generate_bills_from_quarterly_data(year, quarter, member_data, db_session)


if __name__ == "__main__":
    # Example usage
    example_data = [
        {
            'member_id': 1,
            'name': 'Durbach',
            'firstname': 'Marc',
            'accounting_total': 150.50,
            'membership_fee': 50.00,
            'total_amount': 100.50
        },
        {
            'member_id': 2,
            'name': 'Smith',
            'firstname': 'John',
            'accounting_total': 200.00,
            'membership_fee': 50.00,
            'total_amount': 150.00
        }
    ]
    
    result = generate_bills_for_quarter(2025, 3, example_data)
    print(f"Generated {result['total_count']} bills in {result['folder']}")
    for bill in result['bills']:
        print(f"  - {bill['filename']} for {bill['member_name']}")
