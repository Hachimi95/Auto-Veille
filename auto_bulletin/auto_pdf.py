"""
Bulletin DOCX/PDF generator — fixed version.

Core approach:
  - Walk every <w:p> in the document tree (body + tables + text boxes + headers/footers)
  - For each paragraph, build text from DIRECT runs only (not nested sub-documents)
    This avoids the ghost paragraph problem where a body-level <w:p> has no direct runs
    but its iter() finds text inside embedded text boxes.
  - Merge split runs before matching, so placeholders like [CVE2] that Word splits
    across multiple <w:r> elements are still found and replaced.
  - Skip <mc:Fallback> blocks entirely to avoid double-processing duplicated tables.
  - Replace content by rebuilding the run XML directly, preserving original formatting.
  - The main CVE table row height is set to atLeast (not exact) so it
    shrinks correctly when there are only 1-2 CVEs.
"""

import os
import re
import json
import platform
import shutil
import subprocess
import tempfile
from copy import deepcopy
from datetime import datetime

from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from lxml import etree

__all__ = ["generate_pdf_from_json", "generate_docx_from_json"]

W   = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
MC  = "http://schemas.openxmlformats.org/markup-compatibility/2006"

MONTHS_FR = {
    "janvier": "01", "fevrier": "02", "février": "02", "mars": "03",
    "avril": "04", "mai": "05", "juin": "06", "juillet": "07",
    "aout": "08", "août": "08", "septembre": "09",
    "octobre": "10", "novembre": "11", "decembre": "12", "décembre": "12",
}

VERSION_RE = re.compile(
    r'\d+\.\d+\.\d+\.\d+\/\.\d+'
    r'|\d+\.\d+\.\d+\+security-\d{2}rc\d+'
    r'|\d+\.\d+\.\d+\+security-\d{2}'
    r'|\d+\.\d+\.\d+\.\d+'
    r'|\d+\.\d+\.\d+rc\d+'
    r'|\d+\.\d+\.\d+'
    r'|\d{1,2}\.\d{1,2}\.x'
    r'|\d+\.x'
    r'|v\d+\.\d+'
    r'|\d{1,2}\.\d{1,2}'
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def convert_date_format(french_date: str) -> str:
    try:
        parts = french_date.split()
        day, month_fr, year = parts[0], parts[1].lower(), parts[2]
        month = MONTHS_FR.get(month_fr, "")
        return f"{day}/{month}/{year}" if month else french_date
    except Exception:
        return french_date


def split_version_text(text: str):
    parts, last = [], 0
    for m in VERSION_RE.finditer(text):
        if m.start() > last:
            parts.append((text[last:m.start()], False))
        parts.append((text[m.start():m.end()], True))
        last = m.end()
    if last < len(text):
        parts.append((text[last:], False))
    return parts or [(text, False)]


def _get_fallback_ids(doc):
    return set(id(el) for el in doc.element.body.iter(f"{{{MC}}}Fallback"))


def _direct_run_text(p_elem) -> str:
    """
    Text from DIRECT w:r children only.
    Avoids the ghost-paragraph problem where a body <w:p> containing a
    drawing reports all text-box content via iter() but has no real runs.
    """
    parts = []
    for r in p_elem.findall(f"{{{W}}}r"):
        for t in r.findall(f"{{{W}}}t"):
            parts.append(t.text or "")
    return "".join(parts)


def _get_first_rPr(p_elem):
    """Return a deep copy of the first non-empty run's rPr, or None."""
    for r in p_elem.findall(f"{{{W}}}r"):
        text = "".join(t.text or "" for t in r.findall(f"{{{W}}}t"))
        if text.strip():
            rPr = r.find(f"{{{W}}}rPr")
            return deepcopy(rPr) if rPr is not None else None
    return None


def _make_run(text: str, rPr=None, font_name=None, font_size_pt=None, bold=None):
    r = OxmlElement("w:r")
    if rPr is not None:
        r.append(deepcopy(rPr))
    elif font_name or font_size_pt or bold:
        rp = OxmlElement("w:rPr")
        if font_name:
            rf = OxmlElement("w:rFonts")
            rf.set(qn("w:ascii"), font_name)
            rf.set(qn("w:hAnsi"), font_name)
            rp.append(rf)
        if font_size_pt:
            sz = OxmlElement("w:sz")
            sz.set(qn("w:val"), str(int(font_size_pt * 2)))
            rp.append(sz)
        if bold:
            rp.append(OxmlElement("w:b"))
        if len(rp):
            r.append(rp)
    t = OxmlElement("w:t")
    t.text = text
    if text and (text[0] == " " or text[-1] == " "):
        t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    return r


def _make_symbol_bullet():
    """Return a <w:r> containing a bullet in Symbol font."""
    r = OxmlElement("w:r")
    rp = OxmlElement("w:rPr")
    rf = OxmlElement("w:rFonts")
    rf.set(qn("w:ascii"), "Symbol"); rf.set(qn("w:hAnsi"), "Symbol")
    rp.append(rf)
    sz = OxmlElement("w:sz"); sz.set(qn("w:val"), "22"); rp.append(sz)
    r.append(rp)
    t = OxmlElement("w:t"); t.text = chr(183) + "   "
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    r.append(t)
    return r


def _make_br():
    r = OxmlElement("w:r")
    r.append(OxmlElement("w:br"))
    return r


def _clear_runs(p_elem):
    for r in list(p_elem.findall(f"{{{W}}}r")):
        p_elem.remove(r)


def _set_spacing(p_elem, line=None, before_pt=None, after_pt=None):
    pPr = p_elem.find(f"{{{W}}}pPr")
    if pPr is None:
        pPr = OxmlElement("w:pPr")
        p_elem.insert(0, pPr)
    sp = pPr.find(f"{{{W}}}spacing")
    if sp is None:
        sp = OxmlElement("w:spacing")
        pPr.append(sp)
    if line is not None:
        sp.set(qn("w:line"), str(int(line * 240)))
        sp.set(qn("w:lineRule"), "auto")
    if before_pt is not None:
        sp.set(qn("w:before"), str(int(before_pt * 20)))
    if after_pt is not None:
        sp.set(qn("w:after"), str(int(after_pt * 20)))


# ---------------------------------------------------------------------------
# CVE scaling
# ---------------------------------------------------------------------------

def _cve_params(n):
    if   n <= 6:  return 16, 1.6, 70
    elif n <= 10: return 15, 1.5, 50
    elif n <= 15: return 14, 1.4, 40
    elif n <= 20: return 13, 1.3, 30
    elif n <= 25: return 12, 1.1, 20
    elif n <= 30: return 11, 1.0, 20
    elif n <= 35: return 11, 0.8, 10
    elif n <= 40: return 11, 0.8,  5
    elif n <= 45: return 10, 0.5,  0
    else:         return  9, 0.1,  0


# ---------------------------------------------------------------------------
# Mitigation parsing
# ---------------------------------------------------------------------------

def _parse_mitigation(m) -> dict:
    if isinstance(m, str):
        try:
            p = json.loads(m)
            if isinstance(p, dict):
                return p if "recommendation" in p else next(iter(p.values()), {})
        except json.JSONDecodeError:
            pass
        return {"recommendation": m, "versions": []}
    if isinstance(m, dict):
        return m if "recommendation" in m else next(iter(m.values()), m)
    return {"recommendation": str(m), "versions": []}


def _expand_versions(versions):
    result = []
    for v in versions:
        v = str(v).strip()
        if not v:
            continue
        for phrase in ("ou ultérieure", "or later"):
            if v.count(phrase) > 1:
                buf = ""
                for part in re.split(f"({re.escape(phrase)})", v):
                    buf += part
                    if part == phrase:
                        result.append(buf.strip())
                        buf = ""
                if buf.strip():
                    result.append(buf.strip())
                break
        else:
            result.append(v)
    return result


# ---------------------------------------------------------------------------
# Per-paragraph replacement (works on raw lxml elements)
# ---------------------------------------------------------------------------

def _replace_in_p(p_elem, key, value):
    orig_rPr = _get_first_rPr(p_elem)

    if key in ("[CVE]", "[CVE2]"):
        cves = [c.strip() for c in str(value).split("\n") if c.strip()]
        fs, ls, sp = _cve_params(len(cves))
        _clear_runs(p_elem)
        for i, cve in enumerate(cves):
            p_elem.append(_make_run(cve, rPr=orig_rPr, font_size_pt=fs))
            if i < len(cves) - 1:
                p_elem.append(_make_br())
        _set_spacing(p_elem, line=ls, before_pt=sp, after_pt=4)

    elif key == "[Produits affectés]":
        products = value if isinstance(value, list) else [str(value)]
        _clear_runs(p_elem)
        for i, prod in enumerate(products):
            p_elem.append(_make_symbol_bullet())
            for frag, bold in split_version_text(prod):
                p_elem.append(_make_run(frag, font_name="Arial", font_size_pt=10, bold=bold))
            if i < len(products) - 1:
                p_elem.append(_make_br())
        _set_spacing(p_elem, line=1.6, before_pt=0, after_pt=1)

    elif key == "[Mitigations]":
        mits = value if isinstance(value, list) else [value]
        _clear_runs(p_elem)
        for i, mit in enumerate(mits):
            d = _parse_mitigation(mit)
            rec = (d.get("recommendation") or "").strip()
            vers = _expand_versions(d.get("versions") or [])
            if rec:
                p_elem.append(_make_run(rec, font_name="Arial", font_size_pt=10))
                if vers:
                    p_elem.append(_make_br())
            for v in vers:
                v = v.strip()
                if not v:
                    continue
                p_elem.append(_make_run("          ", font_name="Arial", font_size_pt=10))
                p_elem.append(_make_symbol_bullet())
                for frag, bold in split_version_text(v):
                    p_elem.append(_make_run(frag, font_name="Arial", font_size_pt=10, bold=bold))
                p_elem.append(_make_br())
            if i < len(mits) - 1:
                p_elem.append(_make_br())
        _set_spacing(p_elem, line=1.6, before_pt=0, after_pt=1)

    else:
        # Simple replacement — keep original run formatting
        text = _direct_run_text(p_elem).replace(key, str(value))
        _clear_runs(p_elem)
        p_elem.append(_make_run(text, rPr=orig_rPr))


# ---------------------------------------------------------------------------
# Document-wide iteration — the key fix
# ---------------------------------------------------------------------------

def _iter_all_p(doc):
    """
    Yield every real <w:p> element in the document.

    'Real' means: has at least one direct <w:r> child.
    This skips ghost body paragraphs that wrap drawings and expose all
    text-box content through iter() without having any direct runs.
    """
    fallback_ids = _get_fallback_ids(doc)

    def walk(root):
        for p in root.iter(f"{{{W}}}p"):
            if any(id(a) in fallback_ids for a in p.iterancestors()):
                continue
            if p.findall(f"{{{W}}}r"):   # must have direct runs
                yield p

    yield from walk(doc.element.body)
    for section in doc.sections:
        for hf in (section.header, section.footer,
                   section.even_page_header, section.even_page_footer,
                   section.first_page_header, section.first_page_footer):
            if hf is not None:
                yield from walk(hf._element)


def _fix_table_row_heights(doc):
    """
    Change the CVE overview table from exact fixed heights to atLeast,
    so the table doesn't stay huge when there are only a few CVEs.
    """
    fallback_ids = _get_fallback_ids(doc)
    for tbl in doc.element.body.iter(f"{{{W}}}tbl"):
        if any(id(a) in fallback_ids for a in tbl.iterancestors()):
            continue
        if etree.QName(tbl.getparent().tag).localname != "body":
            continue
        texts = [t.text or "" for t in tbl.iter(f"{{{W}}}t")]
        if not any("CVE" in tx for tx in texts):
            continue
        for tr in tbl.findall(f"{{{W}}}tr"):
            trPr = tr.find(f"{{{W}}}trPr")
            if trPr is None:
                continue
            for trH in trPr.findall(f"{{{W}}}trHeight"):
                trH.set(qn("w:hRule"), "atLeast")
                val = int(trH.get(qn("w:val"), "400"))
                if val > 800:
                    trH.set(qn("w:val"), "400")
        break


def process_document(doc, placeholders):
    _fix_table_row_heights(doc)
    for p_elem in _iter_all_p(doc):
        text = _direct_run_text(p_elem)
        if not text:
            continue
        for key in placeholders:
            if key in text:
                _replace_in_p(p_elem, key, placeholders[key])
                break


# ---------------------------------------------------------------------------
# LibreOffice
# ---------------------------------------------------------------------------

def _find_libreoffice():
    env = os.getenv("SOFFICE_PATH")
    candidates = [env] if env else []
    for name in ("soffice", "libreoffice", "lowriter"):
        p = shutil.which(name)
        if p:
            candidates.append(p)
    candidates += [
        "/usr/bin/soffice", "/usr/bin/libreoffice",
        "/usr/local/bin/soffice", "/usr/local/bin/libreoffice",
        "/usr/lib/libreoffice/program/soffice",
        "/snap/bin/libreoffice", "/opt/libreoffice/program/soffice",
    ]
    seen = set()
    for c in candidates:
        if not c or c in seen:
            continue
        seen.add(c)
        if os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    return None


def convert_docx_to_pdf_libreoffice(docx_path: str) -> str:
    soffice = _find_libreoffice()
    if not soffice:
        raise RuntimeError(
            "LibreOffice not found.\n"
            "Install: sudo apt-get install -y libreoffice-core libreoffice-writer"
        )
    out_dir = os.path.dirname(docx_path)
    base = os.path.splitext(os.path.basename(docx_path))[0]
    subprocess.run(
        [soffice, "--headless", "--convert-to", "pdf", "--outdir", out_dir, docx_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        check=True, timeout=120,
    )
    expected = os.path.join(out_dir, f"{base}.pdf")
    if os.path.exists(expected):
        return expected
    for f in os.listdir(out_dir):
        if f.lower().endswith(".pdf") and f.startswith(base):
            return os.path.join(out_dir, f)
    raise RuntimeError(f"PDF not found after conversion for: {base}")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_docx_from_json(json_path: str, bulletin_id: str, out_dir: str = None) -> str:
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError("JSON must be a top-level object.")

    date_raw = data.get("Date", "")
    if date_raw:
        parts = date_raw.split()
        if len(parts) >= 3:
            formatted_date = f"{parts[0]}{MONTHS_FR.get(parts[1].lower(), '00')}{parts[2]}"
        else:
            formatted_date = datetime.now().strftime("%d%m%Y")
    else:
        formatted_date = datetime.now().strftime("%d%m%Y")

    titre = data.get("titre", "Unknown_Advisory")
    base_name = "".join(
        c for c in f"{formatted_date}-{bulletin_id} - {titre}"
        if c.isalnum() or c in "-_ "
    ).rstrip()

    tpl_dir  = os.path.dirname(os.path.abspath(__file__))
    tpl_path = os.path.join(tpl_dir, "template5.docx")
    doc = Document(tpl_path if os.path.exists(tpl_path) else None)

    display_date = convert_date_format(date_raw) if date_raw else ""
    risques = data.get("risques", [])

    placeholders = {
        "[Titre]":             data.get("titre", ""),
        "[titre]":             data.get("titre", ""),
        "[CVE2]":              "\n".join(data.get("CVEs ID", [])),
        "[CVE]":               "\n".join(data.get("CVEs ID", [])),
        "[Produits affectés]": data.get("Produits affectés", []),
        "[Description]":       data.get("Description", ""),
        "[Exploit]":           data.get("Exploit", ""),
        "[Delai]":             data.get("Delai", ""),
        "[score]":             data.get("score", ""),
        "[Date]":              display_date,
        "[Ref]":               "\n".join(data.get("Références", [])),
        "[Mitigations]":       data.get("Mitigations", []),
        "[risques]":           "\n".join(r + "\n-" for r in risques).rstrip("\n-"),
    }

    process_document(doc, placeholders)

    if out_dir is None:
        out_dir = tpl_dir
    os.makedirs(out_dir, exist_ok=True)
    docx_path = os.path.join(out_dir, f"{base_name}.docx")
    doc.save(docx_path)
    return docx_path


def generate_pdf_from_json(json_path: str, bulletin_id: str, return_bytes: bool = False):
    tmpdir = tempfile.mkdtemp(prefix="bulletin_")
    try:
        docx_path = generate_docx_from_json(json_path, bulletin_id, out_dir=tmpdir)
        pdf_path = None
        try:
            if platform.system() == "Windows":
                try:
                    from win32com import client as win32
                    word = win32.Dispatch("Word.Application")
                    word.Visible = False
                    wb = word.Documents.Open(os.path.abspath(docx_path))
                    pdf_path = docx_path.replace(".docx", ".pdf")
                    wb.SaveAs(pdf_path, FileFormat=17)
                    wb.Close()
                    word.Quit()
                except Exception:
                    pdf_path = convert_docx_to_pdf_libreoffice(docx_path)
            else:
                pdf_path = convert_docx_to_pdf_libreoffice(docx_path)
        except Exception as e:
            print(f"[bulletin] PDF conversion failed: {e}")

        if not return_bytes:
            dest = os.path.dirname(os.path.abspath(__file__))
            final_docx = shutil.copy2(docx_path, dest)
            if pdf_path and os.path.exists(pdf_path):
                return shutil.copy2(pdf_path, dest)
            return final_docx

        result = {}
        for key, path in (("pdf", pdf_path), ("docx", docx_path)):
            if path and os.path.exists(path):
                with open(path, "rb") as f:
                    result[f"{key}_bytes"] = f.read()
                result[f"{key}_name"] = os.path.basename(path)
            else:
                result[f"{key}_bytes"] = None
                result[f"{key}_name"] = None
        return result

    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)