import os
import json
import re
import platform
import shutil
import subprocess
from datetime import datetime
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

def convert_date_format(french_date):
    """Convert French date to dd/mm/yyyy format"""
    try:
        months = {
            "janvier": "01", "février": "02", "mars": "03", "avril": "04",
            "mai": "05", "juin": "06", "juillet": "07", "août": "08",
            "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
        }
        parts = french_date.split()
        day = parts[0]
        month = months.get(parts[1].lower(), "")
        year = parts[2]
        return f"{day}/{month}/{year}" if month else french_date
    except Exception:
        return french_date

def split_version_text(text):
    """
    Split text into parts, detecting version numbers and returning a list of tuples
    indicating whether each part should be bold
    """
    version_patterns = [
        r'\d+\.\d+\.\d+\.\d+',          # Matches cases like 131.0.6778.204
        r'\d+\.\d+\.\d+\.\d+\/\.\d+',
        r'\d+\.\d+\.\d+(\+security-\d{2})?rc\d+',
        r'\d+\.\d+\.\d+(\+security-\d{2})?',
        r'\d+\.\d+\.\d+\.\d+\/\.\d+',
        r'\d+\.\d+\.\d+\.\d+',
        r'\d+\.\d+\.\d+\.\d+',
        r'\d+\.\d+\.\d+',
        r'\d{1,2}\.\d{1,2}\.x',
        r'\d+\.x', 
        r'v\d+\.\d+',
        r'\d{1,2}\.\d{1,2}',
    ]
    
    combined = '|'.join(f'({p})' for p in version_patterns)
    parts, last_end = [], 0
    for m in re.finditer(combined, text):
        s, e = m.span()
        if s > last_end:
            parts.append((text[last_end:s], False))
        parts.append((text[s:e], True))
        last_end = e
    if last_end < len(text):
        parts.append((text[last_end:], False))
    return parts

def replace_placeholders_in_paragraph(paragraph, placeholders):
    """Replace placeholders in paragraphs with formatted content."""
    original_text = paragraph.text
    original_runs = list(paragraph.runs)
    contains_placeholder = any(ph in original_text for ph in placeholders.keys())
    if not contains_placeholder:
        return

    for placeholder, value in placeholders.items():
        if placeholder in original_text:

            if placeholder == '[CVE]':
                paragraph.clear()

                # Split CVEs and calculate font size, line spacing, and space before dynamically
                cves = value.split('\n')
                cve_count = len(cves)

                # Define dynamic font size, line spacing, and space before based on the number of CVEs
                if cve_count <= 6:
                    font_size = Pt(16)
                    line_spacing = 1.6  # Larger line spacing for fewer CVEs
                    space_before = Pt(70)  # Larger space before for vertical centering
                elif cve_count <= 10:
                    font_size = Pt(15)
                    line_spacing = 1.5  # Larger line spacing for fewer CVEs
                    space_before = Pt(50)  # Larger space before for vertical centering
                elif cve_count <= 15:
                    font_size = Pt(14)
                    line_spacing = 1.4  # Medium line spacing
                    space_before = Pt(40)  # Adjusted space before
                elif cve_count <= 20:
                    font_size = Pt(13)
                    line_spacing = 1.3  # Smaller line spacing for more CVEs
                    space_before = Pt(30)  # Less space before for more CVEs
                elif cve_count <= 25:
                    font_size = Pt(12)
                    line_spacing = 1.1  # Tight line spacing for many CVEs
                    space_before = Pt(20)  # Minimal space before for many CVEs
                elif cve_count <= 30:
                    font_size = Pt(11)
                    line_spacing = 1  # Tight line spacing for many CVEs
                    space_before = Pt(20)  # Minimal space before for many CVEs
                elif cve_count <= 35:
                    font_size = Pt(11)
                    line_spacing = 0.8  # Tight line spacing for many CVEs
                    space_before = Pt(10)  # Minimal space before for many CVEs
                elif cve_count <= 40:
                    font_size = Pt(11)
                    line_spacing = 0.8 # Tight line spacing for many CVEs
                    space_before = Pt(5)  # Minimal space before for many CVEs
                elif cve_count <= 45:
                    font_size = Pt(10)
                    line_spacing = 0.5 # Tight line spacing for many CVEs
                    space_before = Pt(0)  # Minimal space before for many CVEs
                else :
                    font_size = Pt(9)
                    line_spacing = 0.1 # Tight line spacing for many CVEs
                    space_before = Pt(0.1)  # Minimal space before for many CVEs

                # Restore original paragraph properties
                if original_runs:
                    first_run = original_runs[0]
                    original_font_name = first_run.font.name
                    original_font_bold = first_run.font.bold
                    original_font_color = first_run.font.color.rgb if first_run.font.color else None
                else:
                    original_font_name = "Arial"
                    original_font_bold = False
                    original_font_color = None

                # Add each CVE on a new line with the dynamic font size
                for i, cve in enumerate(cves):
                    run = paragraph.add_run(cve.strip())
                    run.font.name = original_font_name
                    run.font.size = font_size
                    run.font.bold = original_font_bold
                    if original_font_color:
                        run.font.color.rgb = original_font_color

                    # Add a new line after each CVE (except the last one)
                    if i < len(cves) - 1:
                        paragraph.add_run('\n')

                # Set paragraph formatting with dynamic line spacing and space before
                paragraph.paragraph_format.space_after = Pt(4)
                paragraph.paragraph_format.space_before = space_before  # Adjusted space before based on CVE count
                paragraph.paragraph_format.line_spacing = line_spacing


            elif placeholder == '[Produits affectés]':
                # Store original paragraph properties
                paragraph_alignment = paragraph.alignment
                paragraph_style = paragraph.style

                paragraph.clear()
                if isinstance(value, list):
                    for i, product in enumerate(value):
                        # Add bullet symbol (•) with specific font and size
                        bullet_run = paragraph.add_run(chr(183) + "   ")  # Unicode for middle dot
                        bullet_run.font.name = "Symbol"
                        bullet_run.font.size = Pt(11)

                        # Process product text with version splitting
                        parts = split_version_text(product)
                        for text_part, should_bold in parts:
                            run = paragraph.add_run(text_part)
                            run.font.name = "Arial"  # Reset font to a standard style for the text
                            run.font.size = Pt(10)  # Reset size
                            run.font.bold = should_bold

                        # Add line break after each product (except the last one)
                        if i < len(value) - 1:
                            paragraph.add_run('\n')
                    
                    # Set paragraph formatting
                    paragraph.paragraph_format.line_spacing = 1.6  # Consistent line spacing
                    paragraph.paragraph_format.space_before = Pt(0)  # Space before each entry
                    paragraph.paragraph_format.space_after = Pt(1)
                   

                # Restore paragraph properties
                paragraph.alignment = paragraph_alignment
                paragraph.style = paragraph_style

            elif placeholder == '[Mitigations]':
                paragraph_alignment = paragraph.alignment
                paragraph_style = paragraph.style
                
                paragraph.clear()
                if isinstance(value, list):
                    for mitigation in value:
                        for key, details in mitigation.items():
                            # Fallback: if details is not a dict, treat as string
                            if not isinstance(details, dict):
                                rec_run = paragraph.add_run(str(details))
                                rec_run.font.bold = False
                                rec_run.font.name = "Arial"
                                rec_run.font.size = Pt(10)
                                paragraph.add_run('\n')
                                continue
                            # If recommendation exists, add it with spacing
                            if 'recommendation' in details:
                                # Add recommendation text
                                rec_run = paragraph.add_run(details['recommendation'])
                                rec_run.font.bold = False
                                rec_run.font.name = "Arial"
                                rec_run.font.size = Pt(10)
                                
                                # Add line break after recommendation
                                paragraph.add_run('\n')
                            
                            # Add versions with spacing between them
                            versions = details.get('versions', [])
                            for i, version in enumerate(versions):
                                # Add bullet and version
                                bullet_run = paragraph.add_run("     " + chr(216) + " ")
                                bullet_run.font.name = "Wingdings"
                                bullet_run.font.size = Pt(11)
                                
                                # Process version text with splitting
                                parts = split_version_text(version)
                                for text_part, should_bold in parts:
                                    run = paragraph.add_run(text_part)
                                    run.font.name = "Arial"
                                    run.font.size = Pt(10)
                                    run.font.bold = should_bold
                                
                                # Add line break after each version (except the last one)
                                if i < len(versions) - 1:
                                    paragraph.add_run('\n')
                            

                        # Restore paragraph properties
                        paragraph.alignment = paragraph_alignment
                        paragraph.style = paragraph_style


            else:
                # For other placeholders, replace directly and preserve formatting
                original_text = original_text.replace(placeholder, str(value))
                paragraph.clear()
                run = paragraph.add_run(original_text)

                # Preserve original formatting
                if original_runs:
                    first_run = original_runs[0]
                    run.font.name = first_run.font.name
                    run.font.size = first_run.font.size
                    run.font.bold = first_run.font.bold
                    if hasattr(first_run.font, 'color') and first_run.font.color:
                        run.font.color.rgb = first_run.font.color.rgb

def set_row_height(row, height_pt):
    """Set a fixed height for a table row"""
    tr = row._tr
    trPr = tr.get_or_add_trPr()
    trHeight = OxmlElement('w:trHeight')
    trHeight.set(qn('w:val'), str(height_pt))
    trHeight.set(qn('w:hRule'), 'exact')
    trPr.append(trHeight)

def fix_table_properties(doc):
    # Ensure we're modifying the first table only
    if len(doc.tables) >= 1:  # Check if there is at least one table
        table = doc.tables[0]  # Get the first table

        # Check if the table has at least two rows
        if len(table.rows) >= 2:
            middle_row = table.rows[1]  # Get the second row
            set_row_height(middle_row, 7800)  # Set fixed height
            
            # Set row properties to prevent text overflow
            for cell in middle_row.cells:
                for paragraph in cell.paragraphs:
                    if '[CVE]' in paragraph.text:
                        paragraph.paragraph_format.line_spacing = 1.0
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)

def _build_base_filename(advisory_data, bulletin_id):
    # Build "ddmmyyyy-ID - titre" and sanitize
    date_value = advisory_data.get("Date", "")
    formatted_date = ""
    if date_value:
        try:
            months = {
                "janvier": "01", "février": "02", "mars": "03", "avril": "04",
                "mai": "05", "juin": "06", "juillet": "07", "août": "08",
                "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
            }
            parts = date_value.split()
            day, month, year = parts[0], months.get(parts[1].lower(), "00"), parts[2]
            formatted_date = f"{day}{month}{year}"
        except Exception:
            formatted_date = ""
    titre = advisory_data.get("titre", "Unknown_Advisory")
    base = f"{formatted_date}-{bulletin_id} - {titre}"
    base = "".join(x for x in base if x.isalnum() or x in ['-', ' ', '_']).rstrip()
    return base or f"{bulletin_id}"

def _generate_docx(advisory_data, base_filename_display):
    """
    Build the DOCX from template5.docx using the same placeholder logic as before.
    Returns the absolute path to the saved DOCX.
    """
    doc = Document(os.path.join("auto_bulletin", "template5.docx"))

    # Date mapping for template fields (same as before)
    date_value = advisory_data.get("Date", "")
    date_value = convert_date_format(date_value) if date_value else ""

    placeholders = {
        "[titre]": advisory_data.get("titre", ""),
        "[CVE2]": "\n".join(advisory_data.get("CVEs ID", [])),
        "[CVE]": "\n".join(advisory_data.get("CVEs ID", [])),
        "[Produits affectés]": advisory_data.get("Produits affectés", []),
        "[Description]": advisory_data.get("Description", ""),
        "[Exploit]": advisory_data.get("Exploit", ""),
        "[Delai]": advisory_data.get("Delai", ""),
        "[score]": advisory_data.get("score", ""),
        "[Date]": date_value,
        "[Ref]": "\n".join(advisory_data.get("Références", [])),
        "[Mitigations]": advisory_data.get("Mitigations", []),
        "[risques]": "\n".join([r + "\n-" for r in advisory_data.get("risques", [])])[:-2]
    }

    # Apply replacements
    fix_table_properties(doc)
    for paragraph in doc.paragraphs:
        replace_placeholders_in_paragraph(paragraph, placeholders)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    replace_placeholders_in_paragraph(paragraph, placeholders)

    out_dir = "auto_bulletin"
    os.makedirs(out_dir, exist_ok=True)
    docx_path = os.path.join(out_dir, f"{base_filename_display}.docx")
    doc.save(docx_path)
    return os.path.abspath(docx_path)

def _windows_generate_pdf(advisory_data, base_filename_display):
    # Import Windows automation only when needed
    import pythoncom  # type: ignore
    import win32com.client  # type: ignore

    # Build DOCX first (same template flow)
    docx_path = _generate_docx(advisory_data, base_filename_display)

    # Convert to PDF via Word COM
    pdf_path = os.path.join("auto_bulletin", f"{base_filename_display}.pdf")
    pythoncom.CoInitialize()
    try:
        word = win32com.client.Dispatch("Word.Application")
        word_doc = word.Documents.Open(docx_path)
        word_doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)  # PDF
    finally:
        try:
            word_doc.Close()
        except Exception:
            pass
        word.Quit()
        pythoncom.CoUninitialize()

    return pdf_path

def _linux_generate_pdf(advisory_data, base_filename_display):
    """
    Linux path: generate the DOCX from the Word template, then convert to PDF via LibreOffice headless.
    """
    # 1) Build DOCX (keeps your template intact)
    docx_path = _generate_docx(advisory_data, base_filename_display)
    out_dir = os.path.dirname(docx_path)
    pdf_path = os.path.join(out_dir, f"{base_filename_display}.pdf")

    # 2) Find LibreOffice/soffice
    soffice = shutil.which('soffice') or shutil.which('libreoffice') or shutil.which('lowriter')
    if not soffice:
        raise RuntimeError(
            "LibreOffice (soffice) not found for DOCX->PDF conversion on Linux.\n"
            "Install it, e.g.:\n"
            "  sudo apt-get update && sudo apt-get install -y libreoffice-core libreoffice-writer fonts-dejavu\n"
            "Then retry."
        )

    # 3) Convert DOCX -> PDF headlessly
    try:
        proc = subprocess.run(
            [soffice, '--headless', '--convert-to', 'pdf', '--outdir', out_dir, docx_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"LibreOffice conversion failed: {e.stderr or e.stdout}") from e

    if not os.path.exists(pdf_path):
        # Some distros change output name; attempt to locate a PDF in out_dir matching prefix
        candidates = [f for f in os.listdir(out_dir) if f.lower().endswith('.pdf') and f.startswith(base_filename_display)]
        if candidates:
            pdf_path = os.path.join(out_dir, candidates[0])
        else:
            raise RuntimeError("DOCX created but PDF not found after conversion.")

    return pdf_path

def generate_pdf_from_json(json_path, bulletin_id):
    """Generate a PDF from JSON. Windows: Word template + win32com; Linux: LibreOffice headless conversion."""
    try:
        with open(json_path, "r", encoding="utf-8") as file:
            advisory_data = json.load(file)
        if not isinstance(advisory_data, dict):
            raise ValueError("Loaded JSON data is not a dictionary.")

        base_filename_display = _build_base_filename(advisory_data, bulletin_id)

        if platform.system().lower().startswith('win'):
            return _windows_generate_pdf(advisory_data, base_filename_display)
        else:
            return _linux_generate_pdf(advisory_data, base_filename_display)

    except Exception as e:
        raise Exception(f"Error generating PDF: {e}")