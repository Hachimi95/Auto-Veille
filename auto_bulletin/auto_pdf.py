import os
from docx import Document
import json
import re
from datetime import datetime
from docx.shared import Pt
from docx.enum.text import WD_LINE_SPACING
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.text import WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import RGBColor
import subprocess
import platform
import shutil
import tempfile  # added
from lxml import etree

__all__ = ["generate_pdf_from_json", "generate_docx_from_json"]  # ensure import works


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
                
            # WORKAROUND: Handle wrapper format from normalize_mitigations()
            # Data arrives as: [{'Mozilla': {'recommendation': '...', 'versions': []}}]
            # with versions concatenated into recommendation string
            elif placeholder == '[Mitigations]':
                # Store original paragraph properties
                paragraph_alignment = paragraph.alignment
                paragraph_style = paragraph.style

                paragraph.clear()
                
                if isinstance(value, list):
                    for i, mitigation in enumerate(value):
                        # Parse mitigation structure
                        details = None
                        
                        if isinstance(mitigation, str):
                            try:
                                parsed = json.loads(mitigation)
                                if isinstance(parsed, dict):
                                    if len(parsed) == 1:
                                        product_key = list(parsed.keys())[0]
                                        details = parsed[product_key]
                                    else:
                                        details = parsed
                                else:
                                    details = {'recommendation': mitigation, 'versions': []}
                            except json.JSONDecodeError:
                                details = {'recommendation': mitigation, 'versions': []}
                        
                        elif isinstance(mitigation, dict):
                            if 'recommendation' in mitigation and 'versions' in mitigation:
                                details = mitigation
                            elif len(mitigation) == 1:
                                product_key = list(mitigation.keys())[0]
                                details = mitigation[product_key]
                            else:
                                details = mitigation
                        
                        else:
                            details = {'recommendation': str(mitigation), 'versions': []}
                        
                        if not isinstance(details, dict):
                            details = {'recommendation': str(details), 'versions': []}
                        
                        # Extract recommendation and versions
                        rec_text = (details.get('recommendation') or '').strip()
                        versions = details.get('versions', []) or []
                        
                        if not isinstance(versions, list):
                            versions = [versions]
                        
                        # SPECIAL HANDLING: If versions is empty but recommendation contains version info
                        if not versions and rec_text:
                            lines = rec_text.split('\n')
                            if len(lines) > 1:
                                rec_text = lines[0].strip()
                                versions = [line.strip() for line in lines[1:] if line.strip()]
                            elif ':' in rec_text:
                                parts = rec_text.split(':', 1)
                                if len(parts) == 2:
                                    rec_text = parts[0].strip() + ':'
                                    version_text = parts[1].strip()
                                    if version_text:
                                        versions = [version_text]
                        
                        # Add recommendation text (no bullet, no indent)
                        if rec_text:
                            run = paragraph.add_run(rec_text)
                            run.font.name = "Arial"
                            run.font.size = Pt(10)
                            run.font.bold = False
                            
                            # Only add newline if there are versions to follow
                            if versions:
                                paragraph.add_run('\n')
                        
                        # Add versions with bullets and indent
                        for j, version in enumerate(versions):
                            version_str = str(version).strip()
                            if version_str:
                                # Add indentation spaces before bullet
                                indent_run = paragraph.add_run("          ")  # 10 spaces for indent
                                indent_run.font.name = "Arial"
                                indent_run.font.size = Pt(10)
                                
                                # Add bullet symbol (•)
                                bullet_run = paragraph.add_run(chr(183) + "   ")
                                bullet_run.font.name = "Symbol"
                                bullet_run.font.size = Pt(11)
                                
                                # Process version text with version splitting for bold
                                parts = split_version_text(version_str)
                                for text_part, should_bold in parts:
                                    run = paragraph.add_run(text_part)
                                    run.font.name = "Arial"
                                    run.font.size = Pt(10)
                                    run.font.bold = should_bold
                                
                                # Add line break after each version (except the last one)
                                if j < len(versions) - 1:
                                    paragraph.add_run('\n')
                        
                        # Add line break between different mitigations (except the last one)
                        if i < len(value) - 1:
                            paragraph.add_run('\n')
                    
                    # Set paragraph formatting (same as Produits affectés)
                    paragraph.paragraph_format.line_spacing = 1.6
                    paragraph.paragraph_format.space_before = Pt(0)
                    paragraph.paragraph_format.space_after = Pt(1)
                    # NO left_indent here - it would affect everything including recommendation

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
    """Return executable path for LibreOffice/soffice if available, else None."""
    # Prefer explicit env var
    env = os.getenv("SOFFICE_PATH")
    candidates = [env] if env else []
    # Common binary names
    for name in ("soffice", "libreoffice", "lowriter"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    # Common absolute locations
    candidates += [
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/usr/local/bin/soffice",
        "/usr/local/bin/libreoffice",
        "/usr/lib/libreoffice/program/soffice",
        "/snap/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
    ]
    seen = set()
    for c in list(candidates):
        if not c or c in seen:
            continue
        seen.add(c)
        if os.path.exists(c) and os.access(c, os.X_OK):
            return c
    return None


def convert_docx_to_pdf_libreoffice(docx_path):
    """
    Convert DOCX to PDF using LibreOffice in headless mode.
    """
    soffice = check_libreoffice_available()
    if not soffice:
        raise RuntimeError(
            "LibreOffice (soffice) not found for DOCX->PDF conversion on Linux.\n"
            "Install it, e.g.:\n"
            "  sudo apt-get update && sudo apt-get install -y libreoffice-core libreoffice-writer fonts-dejavu\n"
            "Then retry."
        )
    output_dir = os.path.dirname(docx_path)
    base = os.path.splitext(os.path.basename(docx_path))[0]
    try:
        proc = subprocess.run(
            [soffice, "--headless", "--convert-to", "pdf", "--outdir", output_dir, docx_path],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, timeout=120
        )
        if proc.stdout:
            print(f"[auto_pdf] soffice stdout: {proc.stdout.strip()}")
        if proc.stderr:
            print(f"[auto_pdf] soffice stderr: {proc.stderr.strip()}")
    except subprocess.TimeoutExpired:
        raise RuntimeError("La conversion PDF a expiré (timeout)")
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Échec de la conversion PDF: {e.stderr or e.stdout or e}")
    # Resolve PDF path robustly
    expected_pdf = os.path.join(output_dir, f"{base}.pdf")
    if os.path.exists(expected_pdf):
        return expected_pdf
    # Fallback: find any PDF produced for this base
    for f in os.listdir(output_dir):
        if f.lower().endswith(".pdf") and f.startswith(base):
            return os.path.join(output_dir, f)
    raise RuntimeError(f"Conversion réussie mais PDF introuvable pour: {base}")


def generate_docx_from_json(json_path, bulletin_id):
    """
    Generate a DOCX file from JSON data and bulletin ID.
    """
    try:
        with open(json_path, "r", encoding="utf-8") as file:
            advisory_data = json.load(file)
        if not isinstance(advisory_data, dict):
            raise ValueError("Loaded JSON data is not a dictionary.")
        # Use absolute template path to avoid CWD issues under systemd
        tpl_dir = os.path.dirname(os.path.abspath(__file__))
        tpl_path = os.path.join(tpl_dir, "template5.docx")
        if os.path.exists(tpl_path):
            doc = Document(tpl_path)
        else:
            # Fallback to a blank document if template is missing
            doc = Document()

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
            if len(date_parts) >= 3:
                day = date_parts[0]
                month = months.get(date_parts[1].lower(), "00")
                year = date_parts[2]
                formatted_date = f"{day}{month}{year}"
            else:
                formatted_date = datetime.now().strftime("%d%m%Y")
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

        # Fix table props, then replace
        fix_table_properties(doc)
        for paragraph in doc.paragraphs:
            replace_placeholders_in_paragraph(paragraph, placeholders)
        for table in doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        replace_placeholders_in_paragraph(paragraph, placeholders)

        out_dir = os.path.dirname(os.path.abspath(__file__))
        docx_path = os.path.join(out_dir, f"{base_filename_display}.docx")
        doc.save(docx_path)
        return docx_path

    except Exception as e:
        raise Exception(f"Error generating DOCX: {e}")


def _linux_generate_pdf(advisory_data: dict, base_filename_display: str) -> str:
    """
    Compatibility path: generate DOCX then convert to PDF on Linux using LibreOffice.
    """
    # Write advisory to temp json and reuse generate_docx_from_json
    with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.json', encoding='utf-8') as tmp:
        json.dump(advisory_data, tmp, ensure_ascii=False)
        tmp.flush()
        tmp_path = tmp.name
    try:
        # Use a synthetic bulletin_id when not provided in older calls (suffix of base)
        bulletin_id = base_filename_display.split(' - ')[0] if ' - ' in base_filename_display else base_filename_display
        docx_path = generate_docx_from_json(tmp_path, bulletin_id)
        return convert_docx_to_pdf_libreoffice(docx_path)
    finally:
        try:
            os.unlink(tmp_path)
        except Exception:
            pass


def generate_pdf_from_json(json_path, bulletin_id):
    """
    Generate a PDF from JSON data. Works on both Windows and Linux.
    """
    # First generate the DOCX
    docx_path = generate_docx_from_json(json_path, bulletin_id)
    system = platform.system()
    try:
        if system == 'Windows':
            try:
                return convert_docx_to_pdf_windows(docx_path)
            except Exception as win_error:
                print(f"⚠️ Windows COM conversion failed, trying LibreOffice: {win_error}")
                return convert_docx_to_pdf_libreoffice(docx_path)
        else:
            return convert_docx_to_pdf_libreoffice(docx_path)
    except Exception as e:
        # Keep DOCX for fallback; raise wrapped for caller
        raise Exception(f"Error generating PDF: {e}")