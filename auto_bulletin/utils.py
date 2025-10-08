import json
import re
from typing import List, Dict, Any


def clean_versions(versions) -> List[str]:
    out = []
    if isinstance(versions, str):
        parts = [p.strip() for p in re.split('[,\n]+', versions) if p.strip()]
        out.extend(parts)
    elif isinstance(versions, list):
        for v in versions:
            if isinstance(v, str) and (',' in v or '\n' in v):
                out.extend([p.strip() for p in re.split('[,\n]+', v) if p.strip()])
            else:
                out.append(str(v).strip())
    else:
        out.append(str(versions))

    # Post-process: remove JSON artifact tokens and strip surrounding quotes/brackets
    cleaned = []
    for v in out:
        # Remove surrounding quotes
        v = v.strip()
        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
            v = v[1:-1].strip()
        # Remove surrounding brackets/braces
        v = v.strip('[]{} ').strip()
        # Remove known JSON token fragments embedded inside
        v = re.sub(r'"?versions"?\s*:\s*\[', '', v, flags=re.IGNORECASE).strip()
        v = re.sub(r'"?recommendation"?\s*:\s*', '', v, flags=re.IGNORECASE).strip()
        # Skip obvious JSON artifact lines
        if not v:
            continue
        if re.match(r'^"?versions"?\s*:\s*\[?$', v.lower()):
            continue
        if re.match(r'^"?recommendation"?\s*:\s*"?.+"?$', v.lower()):
            # Likely a key:value fragment, skip
            continue
        if v in ['[', ']', '{', '}', '\\n', '\\r']:
            continue
        cleaned.append(v)

    # deduplicate while preserving order
    seen = set()
    unique = []
    for v in cleaned:
        if v not in seen:
            seen.add(v)
            unique.append(v)
    return unique


def clean_recommendation(text: str) -> str:
    """Clean recommendation text from JSON artifacts and surrounding noise."""
    if not isinstance(text, str):
        return str(text)
    t = text.strip()
    # Remove JSON-like keys and braces if included
    # Remove lines that look like '"versions": [' or '"recommendation":'
    lines = [ln.strip() for ln in t.split('\n') if ln.strip()]
    clean_lines = []
    for ln in lines:
        low = ln.lower()
        if re.match(r'^"?versions"?\s*:\s*\[?$', low):
            continue
        if re.match(r'^"?recommendation"?\s*:\s*', low):
            # remove the key portion
            parts = re.split(r'\s*:\s*', ln, maxsplit=1)
            if len(parts) > 1:
                ln = parts[1].strip('" \t')
            else:
                continue
        
        # Skip lines that look like version entries (quoted version strings)
        # These should be extracted as versions, not included in recommendation
        if re.match(r'^"version\s+[0-9]', low):
            continue
        if ln.startswith('"') and ('version' in low or any(char.isdigit() for char in ln)):
            continue
        if ln in [']', '},']:
            continue
            
        # Strip surrounding quotes/brackets
        if (ln.startswith('"') and ln.endswith('"')) or (ln.startswith("'") and ln.endswith("'")):
            ln = ln[1:-1].strip()
        ln = ln.strip('[]{} ').strip()
        if ln and ln not in ['[', ']', '{', '}', '\\n', '\\r']:
            clean_lines.append(ln)

    return ' '.join(clean_lines)


def normalize_mitigations(mitigation_data) -> List[Dict[str, Any]]:
    """Normalize mitigation data into a clean list of dicts.

    Accepts strings (JSON or plain), dicts, lists and returns a list where
    each item is either a dict with 'recommendation' and 'versions' or a
    dict keyed by product name mapping to such dict.
    """
    if not mitigation_data:
        return []

    # If string, try parse JSON
    if isinstance(mitigation_data, str):
        try:
            parsed = json.loads(mitigation_data)
            mitigation_data = parsed
        except Exception:
            lines = [ln.strip() for ln in mitigation_data.split('\n') if ln.strip()]
            if not lines:
                return []
            
            def clean_line(line: str) -> str:
                # remove surrounding quotes and trailing commas and brackets
                s = line.strip().strip(',').strip()
                if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                    s = s[1:-1].strip()
                s = s.strip('[]{} ').strip()
                return s

            # Separate recommendation lines from version lines
            rec_lines = []
            version_lines = []
            in_versions_block = False
            
            for ln in lines:
                clean_ln = ln.strip()
                low = clean_ln.lower()
                
                # Check if we're entering a versions block
                if re.match(r'^"?versions"?\s*:\s*\[?$', low):
                    in_versions_block = True
                    continue
                elif clean_ln in [']', '},'] and in_versions_block:
                    in_versions_block = False
                    continue
                
                # If we're in versions block or this looks like a version line
                if in_versions_block or re.match(r'^"version\s+[0-9]', low) or (clean_ln.startswith('"') and ('version' in low or any(char.isdigit() for char in clean_ln))):
                    cleaned = clean_line(ln)
                    if cleaned:
                        version_lines.append(cleaned)
                else:
                    # This is part of the recommendation
                    if not re.match(r'^"?versions"?\s*:\s*\[?$', low) and clean_ln not in ['[', ']', '{', '}']:
                        rec_lines.append(clean_ln)
            
            recommendation = clean_recommendation('\n'.join(rec_lines)) if rec_lines else 'Mise à jour recommandée'
            versions = clean_versions(version_lines) if version_lines else []
            
            mitigation_data = [{
                'Aucune mitigation': {
                    'recommendation': recommendation,
                    'versions': versions
                }
            }]

    if isinstance(mitigation_data, dict):
        mitigation_data = [mitigation_data]

    normalized = []
    for item in mitigation_data:
        if isinstance(item, str):
            try:
                it = json.loads(item)
            except Exception:
                it = {'Aucune mitigation': {'recommendation': item, 'versions': []}}
        else:
            it = item

        if isinstance(it, dict) and 'recommendation' in it and 'versions' in it:
            rec = clean_recommendation(it.get('recommendation', ''))
            it['recommendation'] = rec
            it['versions'] = clean_versions(it.get('versions', []))
            normalized.append(it)
            continue

        if isinstance(it, dict):
            clean_item = {}
            for product, details in it.items():
                if isinstance(details, str):
                    try:
                        details_parsed = json.loads(details)
                        details = details_parsed
                    except Exception:
                        details = {'recommendation': details, 'versions': []}

                if isinstance(details, dict):
                    rec_text = details.get('recommendation', '')
                    orig_vers = details.get('versions', [])
                    
                    # Check if recommendation contains embedded JSON-like version data
                    # If so, parse it like we do for raw strings
                    if isinstance(rec_text, str) and '"versions"' in rec_text and not orig_vers:
                        # Parse the recommendation as if it were a raw string
                        parsed_versions = []
                        parsed_rec = rec_text
                        
                        lines = [ln.strip() for ln in rec_text.split('\n') if ln.strip()]
                        rec_lines = []
                        version_lines = []
                        in_versions_block = False
                        
                        for ln in lines:
                            clean_ln = ln.strip()
                            low = clean_ln.lower()
                            
                            # Check if we're entering a versions block
                            if re.match(r'^"?versions"?\s*:\s*\[?$', low):
                                in_versions_block = True
                                continue
                            elif clean_ln in [']', '},'] and in_versions_block:
                                in_versions_block = False
                                continue
                            
                            # If we're in versions block or this looks like a version line
                            if in_versions_block or re.match(r'^"version\s+[0-9]', low) or (clean_ln.startswith('"') and ('version' in low or any(char.isdigit() for char in clean_ln))):
                                def clean_line_inner(line: str) -> str:
                                    s = line.strip().strip(',').strip()
                                    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
                                        s = s[1:-1].strip()
                                    s = s.strip('[]{} ').strip()
                                    return s
                                cleaned = clean_line_inner(ln)
                                if cleaned:
                                    version_lines.append(cleaned)
                            else:
                                # This is part of the recommendation
                                if not re.match(r'^"?versions"?\s*:\s*\[?$', low) and clean_ln not in ['[', ']', '{', '}']:
                                    rec_lines.append(clean_ln)
                        
                        parsed_rec = clean_recommendation('\n'.join(rec_lines)) if rec_lines else 'Mise à jour recommandée'
                        parsed_versions = clean_versions(version_lines) if version_lines else []
                        
                        clean_item[product] = {'recommendation': parsed_rec, 'versions': parsed_versions}
                    else:
                        # Normal case
                        rec = clean_recommendation(rec_text)
                        vers = clean_versions(orig_vers)
                        clean_item[product] = {'recommendation': rec, 'versions': vers}
                else:
                    clean_item[product] = {'recommendation': str(details), 'versions': []}
            normalized.append(clean_item)
            continue

    return normalized
