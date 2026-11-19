#!/usr/bin/env python3
"""
Synthetic Evaluation Dataset Generator for AI-Powered Document Intelligence System.
Generates 15 synthetic documents covering all required formats and edge cases,
along with structured Ground Truth JSON specifications.
"""

import csv
import json
import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import pymupdf
import openpyxl

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DOCS_DIR = PROJECT_ROOT / "data" / "evaluation" / "documents"
GROUND_TRUTH_DIR = PROJECT_ROOT / "data" / "evaluation" / "ground_truth"


def create_pdf(filename: str, pages_content: list[str]) -> Path:
    file_path = DOCS_DIR / filename
    doc = pymupdf.open()
    for text in pages_content:
        page = doc.new_page(width=595, height=842)  # A4
        page.insert_text((50, 70), text, fontsize=10, lineheight=1.4)
    doc.save(str(file_path))
    doc.close()
    return file_path


def create_image(filename: str, text: str, format_type: str = "PNG") -> Path:
    file_path = DOCS_DIR / filename
    img = Image.new("RGB", (800, 1000), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    # Use default font
    font = ImageFont.load_default()
    lines = text.split("\n")
    y = 50
    for line in lines:
        draw.text((50, y), line, fill=(0, 0, 0), font=font)
        y += 18
    img.save(str(file_path), format=format_type)
    return file_path


def generate_all() -> None:
    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    GROUND_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    print("Generating synthetic evaluation dataset...")

    # 1. 01_digital_single_page.pdf
    p1 = (
        "TAX INVOICE\n\n"
        "Invoice Number: INV-2026-001\n"
        "Invoice Date: 2026-11-01\n"
        "Supplier: Nexus Global Solutions Inc.\n"
        "Customer: Apex Innovations LLC\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Cloud Architecture Consulting | Qty: 10.00 | Unit Price: $100.00 | Tax: $10.00 | Total: $1,000.00\n"
        "2. Infrastructure Maintenance | Qty: 1.00 | Unit Price: $250.00 | Tax: $25.00 | Total: $250.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $1,250.00\n"
        "Tax: $125.00\n"
        "Total: $1,375.00\n"
    )
    create_pdf("01_digital_single_page.pdf", [p1])
    gt_01 = {
        "document_name": "01_digital_single_page.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-001",
                "invoice_date": "2026-11-01",
                "supplier_name": "Nexus Global Solutions Inc.",
                "customer_name": "Apex Innovations LLC",
                "currency": "USD",
                "subtotal": "1250.00",
                "tax": "125.00",
                "total": "1375.00",
                "line_items": [
                    {
                        "description": "Cloud Architecture Consulting",
                        "quantity": "10.00",
                        "unit_price": "100.00",
                        "tax": "10.00",
                        "line_total": "1000.00"
                    },
                    {
                        "description": "Infrastructure Maintenance",
                        "quantity": "1.00",
                        "unit_price": "250.00",
                        "tax": "25.00",
                        "line_total": "250.00"
                    }
                ],
                "expected_validation_issues": []
            }
        ],
        "special_conditions": ["standard_digital_single_page"]
    }
    (GROUND_TRUTH_DIR / "01_digital_single_page.json").write_text(json.dumps(gt_01, indent=2))

    # 2. 02_digital_multipage.pdf (3 pages)
    p2_1 = (
        "TAX INVOICE (Page 1 of 3)\n\n"
        "Invoice Number: INV-2026-002\n"
        "Invoice Date: 2026-11-02\n"
        "Supplier: Continental Logistics Corp.\n"
        "Customer: Vanguard Retailers\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Route Planning & Freight Handling | Qty: 2.00 | Unit Price: $150.00 | Total: $300.00\n"
        "2. Terminal Warehousing Day 1 | Qty: 1.00 | Unit Price: $150.00 | Total: $150.00\n"
        "3. Terminal Warehousing Day 2 | Qty: 1.00 | Unit Price: $150.00 | Total: $150.00\n"
    )
    p2_2 = (
        "TAX INVOICE (Page 2 of 3)\n\n"
        "Invoice Number: INV-2026-002\n"
        "CONTINUED LINE ITEMS:\n"
        "4. Long-Haul Transportation Segment A | Qty: 1.00 | Unit Price: $400.00 | Total: $400.00\n"
        "5. Refrigerated Storage Unit | Qty: 1.00 | Unit Price: $250.00 | Total: $250.00\n"
        "6. Fuel Surcharge | Qty: 1.00 | Unit Price: $250.00 | Total: $250.00\n"
    )
    p2_3 = (
        "TAX INVOICE (Page 3 of 3)\n\n"
        "Invoice Number: INV-2026-002\n"
        "CONTINUED LINE ITEMS:\n"
        "7. Dispatch Coordination Fee | Qty: 1.00 | Unit Price: $300.00 | Total: $300.00\n"
        "8. Final Mile Delivery | Qty: 1.00 | Unit Price: $200.00 | Total: $200.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $2,000.00\n"
        "Tax: $200.00\n"
        "Total: $2,200.00\n"
    )
    create_pdf("02_digital_multipage.pdf", [p2_1, p2_2, p2_3])
    gt_02 = {
        "document_name": "02_digital_multipage.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-002",
                "invoice_date": "2026-11-02",
                "supplier_name": "Continental Logistics Corp.",
                "customer_name": "Vanguard Retailers",
                "currency": "USD",
                "subtotal": "2000.00",
                "tax": "200.00",
                "total": "2200.00",
                "line_items_count": 8,
                "expected_validation_issues": []
            }
        ],
        "special_conditions": ["multi_page_pdf", "spans_3_pages"]
    }
    (GROUND_TRUTH_DIR / "02_digital_multipage.json").write_text(json.dumps(gt_02, indent=2))

    # 3. 03_discounts_and_shipping.pdf
    p3 = (
        "TAX INVOICE\n\n"
        "Invoice Number: INV-2026-003\n"
        "Invoice Date: 2026-11-03\n"
        "Supplier: Industrial Supply Depot\n"
        "Customer: Horizon Builders\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Heavy Duty Rotary Hammer | Qty: 2.00 | Unit Price: $200.00 | Total: $400.00\n"
        "2. Safety Goggles Pack | Qty: 5.00 | Unit Price: $20.00 | Total: $100.00\n\n"
        "ADJUSTMENTS:\n"
        "Subtotal: $500.00\n"
        "Discount (Contract Partner): -$50.00\n"
        "Shipping & Handling: $30.00\n"
        "Tax: $48.00\n"
        "Total: $528.00\n"
    )
    create_pdf("03_discounts_and_shipping.pdf", [p3])
    gt_03 = {
        "document_name": "03_discounts_and_shipping.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-003",
                "invoice_date": "2026-11-03",
                "supplier_name": "Industrial Supply Depot",
                "customer_name": "Horizon Builders",
                "currency": "USD",
                "subtotal": "500.00",
                "tax": "48.00",
                "total": "528.00",
                "line_items_count": 2,
                "expected_validation_issues": []
            }
        ],
        "special_conditions": ["discounts", "shipping_charges"]
    }
    (GROUND_TRUTH_DIR / "03_discounts_and_shipping.json").write_text(json.dumps(gt_03, indent=2))

    # 4. 04_arithmetic_error_invoice.pdf
    p4 = (
        "TAX INVOICE\n\n"
        "Invoice Number: INV-2026-004\n"
        "Invoice Date: 2026-11-04\n"
        "Supplier: Quality Printers Ltd.\n"
        "Customer: Acme Corporation\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Flyer Printing 500ct | Qty: 1.00 | Unit Price: $250.00 | Total: $250.00\n"
        "2. Banner Graphic Design | Qty: 1.00 | Unit Price: $150.00 | Total: $150.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $400.00\n"
        "Tax: $40.00\n"
        "Total: $490.00\n"
    )
    create_pdf("04_arithmetic_error_invoice.pdf", [p4])
    gt_04 = {
        "document_name": "04_arithmetic_error_invoice.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-004",
                "invoice_date": "2026-11-04",
                "supplier_name": "Quality Printers Ltd.",
                "customer_name": "Acme Corporation",
                "currency": "USD",
                "subtotal": "400.00",
                "tax": "40.00",
                "total": "490.00",
                "expected_validation_issues": [
                    {"issue_type": "calculation_mismatch", "field_name": "total"}
                ]
            }
        ],
        "special_conditions": ["arithmetic_error_printed_total_wrong"]
    }
    (GROUND_TRUTH_DIR / "04_arithmetic_error_invoice.json").write_text(json.dumps(gt_04, indent=2))

    # 5. 05_missing_fields_invoice.pdf
    p5 = (
        "COMMERCIAL PRO-FORMA ESTIMATE\n\n"
        "Supplier: Freelance Digital Studio\n"
        "Customer: Startup Ventures Inc.\n"
        "Currency: USD\n\n"
        "SERVICES PROVIDED:\n"
        "1. Brand Identity Package | Qty: 1.00 | Unit Price: $600.00 | Total: $600.00\n"
        "2. Social Media Kit | Qty: 1.00 | Unit Price: $250.00 | Total: $250.00\n\n"
        "TOTAL AMOUNT:\n"
        "Subtotal: $850.00\n"
        "Tax: $0.00\n"
        "Total: $850.00\n"
    )
    create_pdf("05_missing_fields_invoice.pdf", [p5])
    gt_05 = {
        "document_name": "05_missing_fields_invoice.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": None,
                "invoice_date": None,
                "supplier_name": "Freelance Digital Studio",
                "customer_name": "Startup Ventures Inc.",
                "currency": "USD",
                "subtotal": "850.00",
                "tax": "0.00",
                "total": "850.00",
                "expected_validation_issues": [
                    {"issue_type": "missing_required_field", "field_name": "invoice_number"},
                    {"issue_type": "missing_required_field", "field_name": "invoice_date"}
                ]
            }
        ],
        "special_conditions": ["missing_invoice_number", "missing_invoice_date"]
    }
    (GROUND_TRUTH_DIR / "05_missing_fields_invoice.json").write_text(json.dumps(gt_05, indent=2))

    # 6. 06_ambiguous_dates_invoice.pdf
    p6 = (
        "TAX INVOICE\n\n"
        "Invoice Number: INV-2026-006\n"
        "Invoice Date: 03/04/05\n"
        "Supplier: Vintage Tech Antiques\n"
        "Customer: Heritage Trust\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Vintage Computing Terminal | Qty: 1.00 | Unit Price: $300.00 | Total: $300.00\n"
        "2. CRT Cable Adapter | Qty: 1.00 | Unit Price: $20.00 | Total: $20.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $320.00\n"
        "Tax: $0.00\n"
        "Total: $320.00\n"
    )
    create_pdf("06_ambiguous_dates_invoice.pdf", [p6])
    gt_06 = {
        "document_name": "06_ambiguous_dates_invoice.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-006",
                "invoice_date": None,  # Ambiguous date format must parse to NULL
                "supplier_name": "Vintage Tech Antiques",
                "customer_name": "Heritage Trust",
                "currency": "USD",
                "subtotal": "320.00",
                "tax": "0.00",
                "total": "320.00",
                "needs_manual_review": True
            }
        ],
        "special_conditions": ["ambiguous_date_format_03_04_05"]
    }
    (GROUND_TRUTH_DIR / "06_ambiguous_dates_invoice.json").write_text(json.dumps(gt_06, indent=2))

    # 7. 07_multi_invoice_doc.pdf (2 invoices in 1 document)
    p7_1 = (
        "TAX INVOICE - BATCH 1\n\n"
        "Invoice Number: INV-2026-007A\n"
        "Invoice Date: 2026-11-07\n"
        "Supplier: Alpha Services Inc.\n"
        "Customer: OmniCorp\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Security Compliance Audit | Qty: 1.00 | Unit Price: $300.00 | Total: $300.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $300.00\n"
        "Tax: $30.00\n"
        "Total: $330.00\n"
    )
    p7_2 = (
        "TAX INVOICE - BATCH 2\n\n"
        "Invoice Number: INV-2026-007B\n"
        "Invoice Date: 2026-11-07\n"
        "Supplier: Beta Supplies LLC\n"
        "Customer: OmniCorp\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Server Cables Bundle | Qty: 3.00 | Unit Price: $150.00 | Total: $450.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $450.00\n"
        "Tax: $45.00\n"
        "Total: $495.00\n"
    )
    create_pdf("07_multi_invoice_doc.pdf", [p7_1, p7_2])
    gt_07 = {
        "document_name": "07_multi_invoice_doc.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 2,
        "invoices": [
            {
                "invoice_number": "INV-2026-007A",
                "invoice_date": "2026-11-07",
                "supplier_name": "Alpha Services Inc.",
                "customer_name": "OmniCorp",
                "currency": "USD",
                "subtotal": "300.00",
                "tax": "30.00",
                "total": "330.00"
            },
            {
                "invoice_number": "INV-2026-007B",
                "invoice_date": "2026-11-07",
                "supplier_name": "Beta Supplies LLC",
                "customer_name": "OmniCorp",
                "currency": "USD",
                "subtotal": "450.00",
                "tax": "45.00",
                "total": "495.00"
            }
        ],
        "special_conditions": ["multiple_invoices_single_pdf"]
    }
    (GROUND_TRUTH_DIR / "07_multi_invoice_doc.json").write_text(json.dumps(gt_07, indent=2))

    # 8. 08_multisheet_invoices.xlsx
    wb = openpyxl.Workbook()
    # Sheet 1: Services
    ws1 = wb.active
    ws1.title = "Invoice_Services"
    ws1["A1"] = "TAX INVOICE"
    ws1["A2"] = "Invoice Number: INV-2026-008S"
    ws1["A3"] = "Invoice Date: 2026-11-08"
    ws1["A4"] = "Supplier: Matrix Consulting"
    ws1["A5"] = "Customer: Zenith Corp"
    ws1["A6"] = "Currency: USD"

    ws1.append(["Description", "Quantity", "UnitPrice", "LineTotal"])
    ws1.append(["Strategic Advisory Services", 15, 200, 3000])
    ws1.append(["Systems Review Audit", 1, 500, 500])
    ws1.append([])
    ws1.append(["Subtotal", 3500])
    ws1.append(["Tax", 350])
    ws1.append(["Total", 3850])

    # Sheet 2: Hardware
    ws2 = wb.create_sheet(title="Invoice_Hardware")
    ws2["A1"] = "TAX INVOICE"
    ws2["A2"] = "Invoice Number: INV-2026-008H"
    ws2["A3"] = "Invoice Date: 2026-11-08"
    ws2["A4"] = "Supplier: Matrix Hardware"
    ws2["A5"] = "Customer: Zenith Corp"
    ws2["A6"] = "Currency: USD"

    ws2.append(["Description", "Quantity", "UnitPrice", "LineTotal"])
    ws2.append(["Edge Gateway Unit", 2, 800, 1600])
    ws2.append(["Power Supply Redundant", 2, 100, 200])
    ws2.append([])
    ws2.append(["Subtotal", 1800])
    ws2.append(["Tax", 180])
    ws2.append(["Total", 1980])

    # Sheet 3: Notes
    ws3 = wb.create_sheet(title="Internal_Notes")
    ws3["A1"] = "Non-financial memo: Approved for quarterly budget review."

    xlsx_path = DOCS_DIR / "08_multisheet_invoices.xlsx"
    wb.save(str(xlsx_path))
    gt_08 = {
        "document_name": "08_multisheet_invoices.xlsx",
        "file_type": "xlsx",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 2,
        "invoices": [
            {
                "invoice_number": "INV-2026-008S",
                "invoice_date": "2026-11-08",
                "supplier_name": "Matrix Consulting",
                "customer_name": "Zenith Corp",
                "currency": "USD",
                "subtotal": "3500.00",
                "tax": "350.00",
                "total": "3850.00"
            },
            {
                "invoice_number": "INV-2026-008H",
                "invoice_date": "2026-11-08",
                "supplier_name": "Matrix Hardware",
                "customer_name": "Zenith Corp",
                "currency": "USD",
                "subtotal": "1800.00",
                "tax": "180.00",
                "total": "1980.00"
            }
        ],
        "special_conditions": ["multi_sheet_xlsx", "multiple_invoices_spreadsheet"]
    }
    (GROUND_TRUTH_DIR / "08_multisheet_invoices.json").write_text(json.dumps(gt_08, indent=2))

    # 9. 09_tabular_invoices.csv
    csv_path = DOCS_DIR / "09_tabular_invoices.csv"
    with open(csv_path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["TAX INVOICE"])
        writer.writerow(["Invoice Number: INV-2026-009"])
        writer.writerow(["Invoice Date: 2026-11-09"])
        writer.writerow(["Supplier: Global Logistics Express"])
        writer.writerow(["Customer: Delta Manufacturing"])
        writer.writerow(["Currency: USD"])
        writer.writerow([])
        writer.writerow(["Description", "Quantity", "UnitPrice", "LineTotal"])
        writer.writerow(["Pallet Freight Domestic", "2", "350.00", "700.00"])
        writer.writerow(["Handling Fee", "1", "70.00", "70.00"])
        writer.writerow([])
        writer.writerow(["Subtotal", "770.00"])
        writer.writerow(["Tax", "77.00"])
        writer.writerow(["Total", "847.00"])

    gt_09 = {
        "document_name": "09_tabular_invoices.csv",
        "file_type": "csv",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-2026-009",
                "invoice_date": "2026-11-09",
                "supplier_name": "Global Logistics Express",
                "customer_name": "Delta Manufacturing",
                "currency": "USD",
                "subtotal": "770.00",
                "tax": "77.00",
                "total": "847.00"
            }
        ],
        "special_conditions": ["tabular_csv"]
    }
    (GROUND_TRUTH_DIR / "09_tabular_invoices.json").write_text(json.dumps(gt_09, indent=2))

    # 10. 10_duplicate_invoice_doc1.pdf
    p10 = (
        "TAX INVOICE\n\n"
        "Invoice Number: INV-DUP-2026-999\n"
        "Invoice Date: 2026-11-10\n"
        "Supplier: Omnicron Systems\n"
        "Customer: Global Enterprises\n"
        "Currency: USD\n\n"
        "LINE ITEMS:\n"
        "1. Enterprise Software License | Qty: 1.00 | Unit Price: $4,500.00 | Total: $4,500.00\n\n"
        "FINANCIAL SUMMARY:\n"
        "Subtotal: $4,500.00\n"
        "Tax: $500.00\n"
        "Total: $5,000.00\n"
    )
    create_pdf("10_duplicate_invoice_doc1.pdf", [p10])
    gt_10 = {
        "document_name": "10_duplicate_invoice_doc1.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-DUP-2026-999",
                "invoice_date": "2026-11-10",
                "supplier_name": "Omnicron Systems",
                "customer_name": "Global Enterprises",
                "currency": "USD",
                "subtotal": "4500.00",
                "tax": "500.00",
                "total": "5000.00",
                "expected_validation_issues": []
            }
        ],
        "special_conditions": ["duplicate_test_original"]
    }
    (GROUND_TRUTH_DIR / "10_duplicate_invoice_doc1.json").write_text(json.dumps(gt_10, indent=2))

    # 11. 11_duplicate_invoice_doc2.pdf (Separate document, distinct text layout, same invoice details)
    p11 = (
        "OFFICIAL REPRINT - TAX INVOICE\n\n"
        "Invoice Number: INV-DUP-2026-999\n"
        "Invoice Date: 2026-11-10\n"
        "Supplier: Omnicron Systems\n"
        "Customer: Global Enterprises\n"
        "Currency: USD\n\n"
        "ITEMIZED CHARGES:\n"
        "- Enterprise Software License: 1 x $4,500.00 = $4,500.00\n\n"
        "AMOUNT DUE:\n"
        "Subtotal: $4,500.00\n"
        "Tax: $500.00\n"
        "Total: $5,000.00\n"
    )
    create_pdf("11_duplicate_invoice_doc2.pdf", [p11])
    gt_11 = {
        "document_name": "11_duplicate_invoice_doc2.pdf",
        "file_type": "pdf",
        "expected_document_status": "COMPLETED",
        "expected_invoices_count": 1,
        "invoices": [
            {
                "invoice_number": "INV-DUP-2026-999",
                "invoice_date": "2026-11-10",
                "supplier_name": "Omnicron Systems",
                "customer_name": "Global Enterprises",
                "currency": "USD",
                "subtotal": "4500.00",
                "tax": "500.00",
                "total": "5000.00",
                "expected_validation_issues": [
                    {"issue_type": "duplicate_invoice", "field_name": "invoice_number"}
                ]
            }
        ],
        "special_conditions": ["duplicate_invoice_cross_document"]
    }
    (GROUND_TRUTH_DIR / "11_duplicate_invoice_doc2.json").write_text(json.dumps(gt_11, indent=2))

    # 12. 12_scanned_image_invoice.png
    img_text = (
        "SCANNED INVOICE RECEIPT\n\n"
        "Invoice Number: INV-2026-012\n"
        "Date: 2026-11-12\n"
        "Supplier: Swift Courier Express\n"
        "Customer: Beacon Health\n"
        "Total: $120.00\n"
    )
    create_image("12_scanned_image_invoice.png", img_text, "PNG")
    gt_12 = {
        "document_name": "12_scanned_image_invoice.png",
        "file_type": "png",
        "expected_document_status": "NEEDS_REVIEW",  # When Tesseract is unavailable, falls back to NEEDS_REVIEW
        "expected_invoices_count": 0,
        "invoices": [],
        "special_conditions": ["scanned_image_png", "ocr_dependent"]
    }
    (GROUND_TRUTH_DIR / "12_scanned_image_invoice.json").write_text(json.dumps(gt_12, indent=2))

    # 13. 13_scanned_image_invoice.jpg
    create_image("13_scanned_image_invoice.jpg", img_text, "JPEG")
    gt_13 = {
        "document_name": "13_scanned_image_invoice.jpg",
        "file_type": "jpg",
        "expected_document_status": "NEEDS_REVIEW",
        "expected_invoices_count": 0,
        "invoices": [],
        "special_conditions": ["scanned_image_jpg", "ocr_dependent"]
    }
    (GROUND_TRUTH_DIR / "13_scanned_image_invoice.json").write_text(json.dumps(gt_13, indent=2))

    # 14. 14_malformed_corrupt.pdf
    corrupt_path = DOCS_DIR / "14_malformed_corrupt.pdf"
    corrupt_path.write_bytes(b"%PDF-1.4 [MALFORMED_NON_PARSEABLE_STREAM_CORRUPT_HEADER_XYZ_1234567890]")
    gt_14 = {
        "document_name": "14_malformed_corrupt.pdf",
        "file_type": "pdf",
        "expected_document_status": "FAILED",
        "expected_invoices_count": 0,
        "invoices": [],
        "special_conditions": ["corrupted_file", "unrecoverable_error"]
    }
    (GROUND_TRUTH_DIR / "14_malformed_corrupt.json").write_text(json.dumps(gt_14, indent=2))

    # 15. 15_empty_document.pdf
    create_pdf("15_empty_document.pdf", [""])
    gt_15 = {
        "document_name": "15_empty_document.pdf",
        "file_type": "pdf",
        "expected_document_status": "FAILED",
        "expected_invoices_count": 0,
        "invoices": [],
        "special_conditions": ["empty_blank_document", "zero_chunks"]
    }
    (GROUND_TRUTH_DIR / "15_empty_document.json").write_text(json.dumps(gt_15, indent=2))

    print(f"Generated 15 synthetic documents in {DOCS_DIR}")
    print(f"Generated 15 ground truth specifications in {GROUND_TRUTH_DIR}")


if __name__ == "__main__":
    generate_all()
