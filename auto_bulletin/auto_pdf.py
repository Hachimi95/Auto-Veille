import os
from docx import Document
import json
import re
from datetime import datetime
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor
import subprocess
import platform
import shutil


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
        
        if month:
            return f"{day}/{month}/{year}"
        else:
            return french_date
    except Exception as e:
        print(f"Error converting date: {e}")
        return french_date


def split_version_text(text):
    """
    Split text into parts, detecting version numbers and returning a list of tuples
    indicating whether each part should be bold
    """
    version_patterns = [
        r'\d+\.\d+\.\d+\.\d+',
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
    
    combined_pattern = '|'.join(f'({pattern})' for pattern in version_patterns)
    parts = []
    last_end = 0
    
    for match in re.finditer(combined_pattern, text):
        start, end = match.span()
        
        if start > last_end:
            parts.append((text[last_end:start], False))
        
        parts.append((text[start:end], True))
        
        last_end = end
    
    if last_end < len(text):
        parts.append((text[last_end:], False))
    
    return parts


def replace_placeholders_in_paragraph(paragraph, placeholders):
    """Replace placeholders in paragraphs with formatted content."""
    original_text = paragraph.text
    original_runs = list(paragraph.runs)

    # Check if the paragraph contains any placeholder
    contains_placeholder = any(placeholder in original_text for placeholder in placeholders.keys())
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
                    line_spacing = 1.6
                    space_before = Pt(70)
                elif cve_count <= 10:
                    font_size = Pt(15)
                    line_spacing = 1.5
                    space_before = Pt(50)
                elif cve_count <= 15:
                    font_size = Pt(14)
                    line_spacing = 1.4
                    space_before = Pt(40)
                elif cve_count <= 20:
                    font_size = Pt(13)
                    line_spacing = 1.3
                    space_before = Pt(30)
                elif cve_count <= 25:
                    font_size = Pt(12)
                    line_spacing = 1.1
                    space_before = Pt(20)
                elif cve_count <= 30:
                    font_size = Pt(11)
                    line_spacing = 1
                    space_before = Pt(20)
                elif cve_count <= 35:
                    font_size = Pt(11)
                    line_spacing = 0.8
                    space_before = Pt(10)
                elif cve_count <= 40:
                    font_size = Pt(11)
                    line_spacing = 0.8
                    space_before = Pt(5)
                elif cve_count <= 45:
                    font_size = Pt(10)
                    line_spacing = 0.5
                    space_before = Pt(0)
                else:
                    font_size = Pt(9)
                    line_spacing = 0.1
                    space_before = Pt(0.1)

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
                paragraph.paragraph_format.space_before = space_before
                paragraph.paragraph_format.line_spacing = line_spacing


            elif placeholder == '[Produits affectés]':
                # Store original paragraph properties
                paragraph_alignment = paragraph.alignment
                paragraph_style = paragraph.style

                paragraph.clear()
                if isinstance(value, list):
                    for i, product in enumerate(value):
                        # Add bullet symbol (•) with specific font and size
                        bullet_run = paragraph.add_run(chr(183) + "   ")
                        bullet_run.font.name = "Symbol"
                        bullet_run.font.size = Pt(11)

                        # Process product text with version splitting
                        parts = split_version_text(product)
                        for text_part, should_bold in parts:
                            run = paragraph.add_run(text_part)
                            run.font.name = "Arial"
                            run.font.size = Pt(10)
                            run.font.bold = should_bold

                        # Add line break after each product (except the last one)
                        if i < len(value) - 1:
                            paragraph.add_run('\n')
                    
                    # Set paragraph formatting
                    paragraph.paragraph_format.line_spacing = 1.6
                    paragraph.paragraph_format.space_before = Pt(0)
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
                            
                            # Set paragraph formatting
                            paragraph.paragraph_format.left_indent = Pt(20)
                            paragraph.paragraph_format.line_spacing = 2 
                            
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
    """Fix table properties to ensure proper rendering"""
    # Ensure we're modifying the first table only
    if len(doc.tables) >= 1:
        table = doc.tables[0]

        # Check if the table has at least two rows
        if len(table.rows) >= 2:
            middle_row = table.rows[1]
            set_row_height(middle_row, 7800)
            
            # Set row properties to prevent text overflow
            for cell in middle_row.cells:
                for paragraph in cell.paragraphs:
                    if '[CVE]' in paragraph.text:
                        paragraph.paragraph_format.line_spacing = 1.0
                        paragraph.paragraph_format.space_before = Pt(0)
                        paragraph.paragraph_format.space_after = Pt(0)


def check_libreoffice_available():
    """Check if LibreOffice is available on the system"""
    libreoffice_commands = [
        'libreoffice',
        'soffice',
        '/usr/bin/libreoffice',
        '/usr/bin/soffice',
        '/snap/bin/libreoffice',
        '/opt/libreoffice/program/soffice',
    ]
    
    for cmd in libreoffice_commands:
        if shutil.which(cmd):
            return cmd
    
    return None


def convert_docx_to_pdf_libreoffice(docx_path):
    """
    Convert DOCX to PDF using LibreOffice in headless mode.
    
    Args:
        docx_path: Path to the DOCX file
        
    Returns:
        Path to the generated PDF file
        
    Raises:
        RuntimeError: If LibreOffice is not installed or conversion fails
    """
    libreoffice_cmd = check_libreoffice_available()
    
    if not libreoffice_cmd:
        raise RuntimeError(
            "LibreOffice n'est pas installé. Installez-le avec:\n"
            "  sudo apt-get update\n"
            "  sudo apt-get install -y libreoffice\n"
            "Puis relancez l'application."
        )
    
    # Get output directory
    output_dir = os.path.dirname(docx_path)
    
    # Convert to PDF using LibreOffice
    try:
        result = subprocess.run(
            [
                libreoffice_cmd,
                '--headless',
                '--convert-to', 'pdf',
                '--outdir', output_dir,
                docx_path
            ],
            capture_output=True,
            text=True,
            timeout=60,
            check=True
        )
        
        # Calculate expected PDF path
        pdf_path = docx_path.replace('.docx', '.pdf')
        
        if os.path.exists(pdf_path):
            return pdf_path
        else:
            raise RuntimeError(f"Conversion réussie mais PDF introuvable: {pdf_path}")
            
    except subprocess.TimeoutExpired:
        raise RuntimeError("La conversion PDF a expiré (timeout de 60s)")
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        raise RuntimeError(f"Échec de la conversion PDF: {error_msg}")


def convert_docx_to_pdf_windows(docx_path):
    """
    Convert DOCX to PDF using Windows COM automation (Microsoft Word).
    Only works on Windows with Microsoft Word installed.
    
    Args:
        docx_path: Path to the DOCX file
        
    Returns:
        Path to the generated PDF file
    """
    try:
        import win32com.client
        import pythoncom
    except ImportError:
        raise RuntimeError(
            "pywin32 n'est pas installé. Sur Windows, installez-le avec:\n"
            "  pip install pywin32"
        )
    
    pythoncom.CoInitialize()
    try:
        word = win32com.client.Dispatch("Word.Application")
        pdf_path = docx_path.replace('.docx', '.pdf')
        word_doc = word.Documents.Open(os.path.abspath(docx_path))
        word_doc.SaveAs(os.path.abspath(pdf_path), FileFormat=17)  # 17 = PDF
        word_doc.Close()
        word.Quit()
        return pdf_path
    finally:
        pythoncom.CoUninitialize()


def generate_docx_from_json(json_path, bulletin_id):
    """
    Generate a DOCX file from JSON data and bulletin ID.
    This function is exported and can be used as a fallback when PDF generation fails.
    
    Args:
        json_path: Path to JSON file with bulletin data
        bulletin_id: Bulletin identifier
        
    Returns:
        Path to generated DOCX file
    """
    try:
        # Load JSON data
        with open(json_path, "r", encoding="utf-8") as file:
            advisory_data = json.load(file)

        # Ensure advisory_data is a dictionary
        if not isinstance(advisory_data, dict):
            raise ValueError("Loaded JSON data is not a dictionary.")

        # Load Word template
        doc = Document(os.path.join("auto_bulletin", "template5.docx"))

        # Date formatting
        date_value = advisory_data.get("Date", "")
        if date_value:
            # Convert date to desired format
            date_parts = date_value.split()
            months = {
                "janvier": "01", "février": "02", "mars": "03", "avril": "04",
                "mai": "05", "juin": "06", "juillet": "07", "août": "08",
                "septembre": "09", "octobre": "10", "novembre": "11", "décembre": "12"
            }
            day = date_parts[0]
            month = months.get(date_parts[1].lower(), "00")
            year = date_parts[2]
            
            formatted_date = f"{day}{month}{year}"
        else:
            formatted_date = datetime.now().strftime("%d%m%Y")

        # Get original title with spaces
        titre = advisory_data.get("titre", "Unknown_Advisory")

        # Construct filename with space between ID and title
        base_filename_display = f"{formatted_date}-{bulletin_id} - {titre}"

        # Sanitize filename for saving
        base_filename_display = "".join(x for x in base_filename_display if x.isalnum() or x in ['-', ' ', '_']).rstrip()

        # Date formatting for display
        date_value = advisory_data.get("Date", "")
        date_value = convert_date_format(date_value) if date_value else ""

        # Map placeholders to content
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
            "[risques]": "\n".join([risque + "\n-" for risque in advisory_data.get("risques", [])])[:-2]
        }

        # Fix table properties
        fix_table_properties(doc)

        # Apply replacements to document paragraphs
        for paragraph in doc.paragraphs:
            replace_placeholders_in_paragraph(paragraph, placeholders)

        # Apply replacements to table paragraphs
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        replace_placeholders_in_paragraph(paragraph, placeholders)

        # Save the Word document
        docx_path = os.path.join("auto_bulletin", f"{base_filename_display}.docx")
        doc.save(docx_path)

        return docx_path

    except Exception as e:
        raise Exception(f"Error generating DOCX: {e}")


def generate_pdf_from_json(json_path, bulletin_id):
    """
    Generate a PDF from JSON data. Works on both Windows and Linux.
    
    On Linux: Uses LibreOffice for DOCX to PDF conversion
    On Windows: Uses Microsoft Word COM automation (if available) or LibreOffice
    
    Args:
        json_path: Path to JSON file with bulletin data
        bulletin_id: Bulletin identifier
        
    Returns:
        Path to generated PDF file
        
    Raises:
        Exception: If PDF generation fails (caller should handle and fallback to DOCX)
    """
    # First generate the DOCX
    docx_path = generate_docx_from_json(json_path, bulletin_id)
    
    # Detect platform and choose conversion method
    system = platform.system()
    
    try:
        if system == 'Windows':
            # Try Windows COM first, fall back to LibreOffice
            try:
                pdf_path = convert_docx_to_pdf_windows(docx_path)
                return pdf_path
            except Exception as win_error:
                print(f"⚠️ Windows COM conversion failed, trying LibreOffice: {win_error}")
                pdf_path = convert_docx_to_pdf_libreoffice(docx_path)
                return pdf_path
        else:
            # Linux/macOS: Use LibreOffice
            pdf_path = convert_docx_to_pdf_libreoffice(docx_path)
            return pdf_path
            
    except Exception as e:
        # Don't delete the DOCX - it's the fallback
        raise Exception(f"Erreur lors de la génération du PDF: {e}")