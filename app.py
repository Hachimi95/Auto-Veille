from flask import Flask, render_template, request, redirect, send_file, jsonify
import os
from database import db
from upload.pdf_extractor import extract_text_from_pdf, extract_security_data, match_clients_and_teams
from dotenv import load_dotenv
from datetime import datetime, timedelta
import pandas as pd
import io
from database.db import clean_field
import sqlite3
import json
import logging
import sys
import tempfile
load_dotenv()
from auto_bulletin.auto_json import DGSSIScraper, CERTFRScraper
from auto_bulletin.mitigation import MitigationHandler
from auto_bulletin.description import DescriptionHandler

# Safe PDF import with fallback
try:
    from auto_bulletin.auto_pdf import generate_pdf_from_json
except Exception as _pdf_import_err:
    def generate_pdf_from_json(*_args, **_kwargs):
        raise RuntimeError(f"PDF generation module import failed: {_pdf_import_err}")

app = Flask(__name__)

# Configure logging to stdout for systemd/journalctl
if not logging.getLogger().handlers:
    _handler = logging.StreamHandler(stream=sys.stdout)
    _handler.setFormatter(logging.Formatter('[%(asctime)s] %(levelname)s: %(message)s'))
    logging.getLogger().addHandler(_handler)
logging.getLogger().setLevel(os.getenv('LOG_LEVEL', 'INFO').upper())
app.logger.setLevel(logging.getLogger().level)

@app.route('/_health')
def _health():
    return jsonify(ok=True), 200

def sanitize_extracted_data(data: dict) -> dict:
    """Trim strings and clean list elements"""
    for key in list(data.keys()):
        if isinstance(data[key], str):
            data[key] = data[key].strip()
        elif isinstance(data[key], list):
            data[key] = [x.strip() if isinstance(x, str) else x for x in data[key]]
    return data

def normalize_mitigations(raw):
    """
    Convert mitigation input to standardized format:
    Returns: [{'recommendation': str, 'versions': [str, ...]}, ...]
    """
    import json
    
    def clean_versions(v):
        if isinstance(v, str):
            return [x.strip() for x in v.split(',') if x.strip()]
        if isinstance(v, list):
            cleaned = []
            for item in v:
                if isinstance(item, str) and ',' in item:
                    cleaned.extend([x.strip() for x in item.split(',') if x.strip()])
                else:
                    cleaned.append(item.strip() if isinstance(item, str) else str(item).strip())
            return cleaned
        return []
    
    if raw is None or raw == '':
        return []
    
    # Try JSON decode if string
    if isinstance(raw, str):
        txt = raw.strip()
        if not txt:
            return []
        try:
            raw = json.loads(txt)
        except Exception:
            return [{'recommendation': txt, 'versions': []}]
    
    # Single dict
    if isinstance(raw, dict):
        rec = (raw.get('recommendation') or '').strip()
        vers = clean_versions(raw.get('versions', []))
        return [{'recommendation': rec, 'versions': vers}] if rec or vers else []
    
    # List input
    if isinstance(raw, list):
        out = []
        for item in raw:
            if isinstance(item, dict):
                rec = (item.get('recommendation') or '').strip()
                vers = clean_versions(item.get('versions', []))
                if rec or vers:
                    out.append({'recommendation': rec, 'versions': vers})
            elif isinstance(item, str) and item.strip():
                out.append({'recommendation': item.strip(), 'versions': []})
        return out
    
    # Fallback
    return [{'recommendation': str(raw).strip(), 'versions': []}] if str(raw).strip() else []

UPLOAD_FOLDER = 'uploads'
EXPORT_FOLDER = 'exports'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(EXPORT_FOLDER, exist_ok=True)

def parse_date_to_ymd(date_str):
    """Convert date string to YYYY-MM-DD if possible, else return as is."""
    from datetime import datetime
    for fmt in ('%Y-%m-%d', '%d/%m/%Y', '%d-%m-%Y'):
        try:
            return datetime.strptime(date_str, fmt).strftime('%Y-%m-%d')
        except Exception:
            continue
    return date_str  # fallback

def format_mitigation_for_display(mitigation_data):
    """Format mitigation data for display in textarea

    Tolerant formatter: cleans recommendation text, splits/cleans versions,
    and attempts to extract version lines if they are embedded in the
    recommendation text itself.
    """
    from auto_bulletin.utils import clean_versions, clean_recommendation

    if not mitigation_data:
        return ""

    formatted_lines = []
    for mitigation in mitigation_data:
        # Flat format: {'recommendation': str, 'versions': [...]}
        if isinstance(mitigation, dict) and 'recommendation' in mitigation and 'versions' in mitigation:
            rec = clean_recommendation(mitigation.get('recommendation', ''))
            if rec:
                formatted_lines.append(rec)

            versions = clean_versions(mitigation.get('versions', []))

            # If versions are still empty, attempt to find them inside recommendation
            if not versions and rec:
                candidate_lines = [ln.strip() for ln in rec.split('\n') if ln.strip()]
                extracted = [ln for ln in candidate_lines if 'version' in ln.lower() or any(ch.isdigit() for ch in ln)]
                if extracted:
                    versions = extracted

            for v in versions:
                formatted_lines.append(v)

        else:
            # Product-based or other dict structures
            if isinstance(mitigation, dict):
                for product, details in mitigation.items():
                    if isinstance(details, dict):
                        rec = clean_recommendation(details.get('recommendation', ''))
                        if rec:
                            formatted_lines.append(rec)
                        versions = clean_versions(details.get('versions', []))
                        if not versions and rec:
                            candidate_lines = [ln.strip() for ln in rec.split('\n') if ln.strip()]
                            extracted = [ln for ln in candidate_lines if 'version' in ln.lower() or any(ch.isdigit() for ch in ln)]
                            if extracted:
                                versions = extracted
                        for v in versions:
                            formatted_lines.append(v)
                    else:
                        txt = str(details).strip()
                        if txt:
                            formatted_lines.append(txt)
            else:
                # Fallback: string or other - render as single line
                txt = str(mitigation).strip()
                if txt:
                    formatted_lines.append(txt)

    return '\n'.join(formatted_lines)
    
    # Fallback
    return '\n'.join([ln for ln in formatted_lines if ln and 'versions"' not in ln.lower() and '"versions"' not in ln.lower()])


@app.route('/')
def home():
    return render_template('home.html')

@app.route('/upload', methods=['GET', 'POST'])
def upload():
    if request.method == 'POST':
        print("🔍 Upload POST request received")
        files = request.files.getlist('pdf')
        print(f"🔍 Number of files: {len(files)}")

        for file in files:
            if file:
                print(f"🔍 Processing file: {file.filename}")
                path = os.path.join(UPLOAD_FOLDER, file.filename)
                file.save(path)
                print(f"🔍 File saved to: {path}")

                text = extract_text_from_pdf(path)
                print(f"🔍 Extracted text length: {len(text) if text else 0}")

                data = extract_security_data(text)
                print(f"🔍 Security data extracted: {bool(data)}")

                if not data:
                    print("🔍 No data extracted, skipping file")
                    continue  # skip this file

                filename = os.path.basename(file.filename)
                id_bulletin = filename.split('-')[0] + '-' + filename.split('-')[1] if '-' in filename else filename
                print(f"🔍 ID Bulletin: {id_bulletin}")

                clients, teams = match_clients_and_teams(data['title'])
                print(f"🔍 Matched clients: {clients}")
                print(f"🔍 Matched teams: {teams}")

                # If no clients matched, skip this file
                if not clients:
                    print(f"🔍 No clients matched for title: {data['title']}")
                    print(f"🔍 Skipping file: {file.filename}")
                    continue

                # Clean the product name using the existing function
                from upload.pdf_extractor import clean_produit_name
                produit_name = clean_produit_name(data.get('produit_name', data['title']))
                mitigation = clean_field(data.get('mitigation', []))
                reference = clean_field(data.get('reference', []), sep=", ")
                risk = data.get('risk', 'Important')
                if isinstance(risk, list):
                    risk = ", ".join(risk)
                cves = data.get('cves', [])
                if isinstance(cves, list):
                    cves = cves
                else:
                    cves = [cves]

                # Ensure date is in YYYY-MM-DD format
                date_de_sortie = parse_date_to_ymd(data['date'])

                vuln = {
                    'id_bulletin': id_bulletin,
                    'produit_name': produit_name,
                    'Date_de_sortie': date_de_sortie,
                    'description': data['description'],
                    'cvss_score': data['cvss_score'],
                    'mitigation': mitigation,
                    'reference': reference,
                    'cves': cves,
                    'risk': risk,
                    'processing_time': data.get('processing_time', 5),
                    'Date_de_notification': data.get('Date_de_notification', date_de_sortie)
                }
                print(f"🔍 Vulnerability data prepared: {vuln['id_bulletin']}")

                # Insert vulnerability
                db.insert_vulnerability(vuln)
                print(f"🔍 Vulnerability inserted into database")

                # Insert client tracking entries
                tracking_count = 0
                for i, client in enumerate(clients):
                    team = teams[i] if i < len(teams) else "SOC Team"
                    print(f"🔍 Using team: {team} for client: {client}")

                    for cve_id in cves:
                        # Always insert with status 'Open' and today's date by default
                        default_comment = f"{date_de_sortie} : Mail envoyé par SOC"
                        db.insert_client_tracking(id_bulletin, cve_id, {
                            'client': client,
                            'Responsable_resolution': team,
                            'comment': default_comment
                        })
                        tracking_count += 1

                print(f"🔍 Inserted {tracking_count} client tracking entries")
        print("🔍 Upload processing complete, redirecting to tracker")
        return redirect('/tracker')
    return render_template('upload.html')

@app.route('/update_vulnerability_details', methods=['POST'])
def update_vulnerability_details():
    """Update vulnerability details from the editable details modal"""
    try:
        data = request.get_json()
        row_id = data.get('row_id')
        field_name = data.get('field_name')
        new_value = data.get('new_value')
        
        if not all([row_id, field_name, new_value is not None]):
            return jsonify({'success': False, 'message': 'Missing required parameters'}), 400
        
        # Connect to database
        conn = sqlite3.connect('vuln_tracker.db')
        conn.row_factory = sqlite3.Row
        
        # Get the current row to find id_bulletin and client
        row = conn.execute('SELECT id_bulletin, client FROM client_vuln_tracking WHERE id = ?', (row_id,)).fetchone()
        if not row:
            conn.close()
            return jsonify({'success': False, 'message': 'Row not found'}), 404
        
        id_bulletin = row['id_bulletin']
        client = row['client']
        
        # Map frontend field names to database column names
        field_mapping = {
            'Produit': 'produit_name',
            'Description': 'description',
            'Impact': 'risk',
            'Remédiation': 'mitigation',
            'Référence': 'reference',
            'Commentaire': 'comment',
            'Responsable résolution': 'Responsable_resolution'
        }
        
        db_field = field_mapping.get(field_name)
        if not db_field:
            conn.close()
            return jsonify({'success': False, 'message': 'Invalid field name'}), 400
        
        # Update the field in the database
        if db_field in ['produit_name', 'description', 'risk', 'mitigation', 'reference']:
            # These fields are in the vulnerabilities table
            conn.execute(f'UPDATE vulnerabilities SET {db_field} = ? WHERE id_bulletin = ?', (new_value, id_bulletin))
        else:
            # These fields are in the client_vuln_tracking table
            conn.execute(f'UPDATE client_vuln_tracking SET {db_field} = ? WHERE id_bulletin = ? AND client = ?', (new_value, id_bulletin, client))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True, 'message': 'Field updated successfully'})
        
    except Exception as e:
        return jsonify({'success': False, 'message': f'Error updating field: {str(e)}'}), 500

@app.route('/delete_vulnerability/<id_bulletin>/<client>', methods=['POST'])
def delete_vulnerability(id_bulletin, client):
    db.delete_client_vuln_group(id_bulletin, client)
    # Preserve client scope after deletion
    return redirect(f'/tracker?client={client}')

@app.route('/tracker', methods=['GET', 'POST'])
def tracker():
    if request.method == 'POST':
        row_id = request.form.get('row_id')
        if row_id:
            status = request.form.get('status')
            comment = request.form.get('comment')
            date_traitement = request.form.get('date_traitement')
            responsable = request.form.get('responsable')
            produit = request.form.get('produit')
            # Find the id_bulletin and client for this row
            conn = sqlite3.connect('vuln_tracker.db')
            conn.row_factory = sqlite3.Row
            row = conn.execute('SELECT id_bulletin, client FROM client_vuln_tracking WHERE id = ?', (row_id,)).fetchone()
            if row:
                id_bulletin = row['id_bulletin']
                client = row['client']
                # Update client_vuln_tracking table
                conn.execute('UPDATE client_vuln_tracking SET status = ?, comment = ?, Date_de_traitement = ?, Responsable_resolution = ? WHERE id_bulletin = ? AND client = ?', (status, comment, date_traitement, responsable, id_bulletin, client))
                # Update vulnerabilities table if produit is provided
                if produit:
                    conn.execute('UPDATE vulnerabilities SET produit_name = ? WHERE id_bulletin = ?', (produit, id_bulletin))
                conn.commit()
            conn.close()
            # Preserve client scope after edit based on the row's client
            if row:
                return redirect(f"/tracker?client={client}")
            return redirect('/tracker')
    
    print("🔍 Tracker GET request received")
    db.update_daily_treatment_dates()
    client_filter = request.args.get('client')
    month = request.args.get('month')
    start_date = end_date = None
    if month:
        # month is in format YYYY-MM
        start_date = f"{month}-01"
        # Calculate end of month
        from calendar import monthrange
        year, m = map(int, month.split('-'))
        last_day = monthrange(year, m)[1]
        end_date = f"{month}-{last_day:02d}"
    
    print(f"🔍 Tracker filters - client: {client_filter}, month: {month}, start_date: {start_date}, end_date: {end_date}")
    
    db_data = db.get_client_vulns(client_filter, start_date, end_date)
    print(f"🔍 Retrieved {len(db_data) if db_data else 0} records from database")
    
    clients = db.get_client_names()
    print(f"🔍 Available clients: {clients}")
    
    return render_template('tracker.html', data=db_data, clients=clients, selected=client_filter)

@app.route('/export', methods=['POST'])
def export_excel():
    data = request.get_json()
    selected_clients = data.get('selected_clients', [])
    start_date = data.get('start_date')
    end_date = data.get('end_date')
    
    # If no clients selected, return error
    if not selected_clients:
        return jsonify({
            'success': False,
            'message': 'Veuillez sélectionner un client pour l\'export.'
        }), 400
    
    # Import auto_excel functions
    from export_excel.auto_excel import update_client_excel_file, get_available_clients
    
    # Check if all selected clients are configured
    available_clients = get_available_clients()
    invalid_clients = [client for client in selected_clients if client not in available_clients]
    if invalid_clients:
        return jsonify({
            'success': False,
            'message': f"Client(s) non configuré(s) pour l'export Excel: {', '.join(invalid_clients)}"
        }), 400

    # Use parallel processing for multiple clients
    if len(selected_clients) > 1:
        return export_multiple_clients_parallel(selected_clients, start_date, end_date)
    else:
        return export_single_client(selected_clients[0], start_date, end_date)

def export_single_client(client, start_date, end_date):
    """Export data for a single client"""
    from export_excel.auto_excel import update_client_excel_file
    
    # Get data for this specific client
    db_data = db.get_client_vulns(client, start_date, end_date)
    if not db_data:
        return jsonify({
            'success': True,
            'message': f"Aucune donnée trouvée pour {client}",
            'rows_added': 0,
            'exported_clients': []
        })

    # Transform database data to match client configuration format
    data_to_add = transform_db_data_to_excel_format(db_data)

    # Update the client's Excel file
    success = update_client_excel_file(client, data_to_add)

    if success:
        return jsonify({
            'success': True,
            'message': f"✅ {len(data_to_add)} lignes ajoutées au fichier Excel de {client}",
            'rows_added': len(data_to_add),
            'exported_clients': [client]
        })
    else:
        error_message = get_export_error_message(client)
        return jsonify({
            'success': False,
            'message': error_message,
            'rows_added': 0,
            'exported_clients': []
        })

def export_multiple_clients_parallel(selected_clients, start_date, end_date):
    """Export data for multiple clients using parallel processing"""
    import threading
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from export_excel.auto_excel import update_client_excel_file
    
    total_rows_added = 0
    export_results = []
    exported_clients = []
    
    def process_client(client):
        """Process a single client export"""
        try:
            # Get data for this specific client
            db_data = db.get_client_vulns(client, start_date, end_date)
            if not db_data:
                return {
                    'client': client,
                    'success': False,
                    'message': f"Aucune donnée trouvée pour {client}",
                    'rows_added': 0
                }

            # Transform database data to match client configuration format
            data_to_add = transform_db_data_to_excel_format(db_data)

            # Update the client's Excel file
            success = update_client_excel_file(client, data_to_add)

            if success:
                return {
                    'client': client,
                    'success': True,
                    'message': f"✅ {len(data_to_add)} lignes ajoutées au fichier Excel de {client}",
                    'rows_added': len(data_to_add)
                }
            else:
                error_message = get_export_error_message(client)
                return {
                    'client': client,
                    'success': False,
                    'message': error_message,
                    'rows_added': 0
                }
        except Exception as e:
            return {
                'client': client,
                'success': False,
                'message': f"❌ Erreur lors de l'export de {client}: {str(e)}",
                'rows_added': 0
            }

    # Use ThreadPoolExecutor for parallel processing
    with ThreadPoolExecutor(max_workers=min(len(selected_clients), 4)) as executor:
        # Submit all client processing tasks
        future_to_client = {executor.submit(process_client, client): client for client in selected_clients}
        
        # Collect results as they complete
        for future in as_completed(future_to_client):
            result = future.result()
            
            if result['success']:
                total_rows_added += result['rows_added']
                exported_clients.append(result['client'])
            
            export_results.append(result['message'])

    # Prepare response message
    message = f"Export terminé pour {len(selected_clients)} client(s).\n\n" + "\n".join(export_results)

    return jsonify({
        'success': True,
        'message': message,
        'rows_added': total_rows_added,
        'exported_clients': exported_clients
    })

def transform_db_data_to_excel_format(db_data):
    """Transform database data to Excel format"""
    data_to_add = []
    for row in db_data:
        # Map database fields to client configuration fields
        mapped_data = {
            'id': row['id_bulletin'],
            'titre': row['produit_name'],
            'status': row['status'],
            'niveau risque': row['Niveau_de_risqué'],
            'Date': row['Date_de_sortie'],
            'Date de traitement': row['Date_de_traitement'],
            'Date de notification': row['Date_de_notification'],
            'Responsable': row['Responsable_resolution'],
            'Delai': row['processing_time'],
            'Description': row['description'],
            'Mitigations': row['mitigation'],
            'Remarque': row['comment'],
            'Références': row['Référence'],
            'CVEs ID': row['cves'],
            'Concerné': 'Oui' if row['status'] not in ['Clos (Non concerné)'] else 'Non',
            'pris en charge': 'Oui' if row['status'] in ['Clos (Traité)', 'Clos (Patch cumulative)', 'Clos'] else 'Non',
            'risques': [row['risk']] if row['risk'] else [],
            'SOURCE': 'Auto-Veille'
        }
        data_to_add.append(mapped_data)
    return data_to_add

def get_export_error_message(client):
    """Get appropriate error message for export failure"""
    import os
    import json
    
    try:
        with open(os.path.join('export_excel', 'client_config.json'), 'r', encoding='utf-8') as f:
            config = json.load(f)
        if client in config:
            client_config = config[client]
            client_file_path = os.path.join('export_excel', client_config["file_path"])  # resolve relative path
            if os.path.exists(client_file_path):
                return f"❌ Échec de mise à jour du fichier Excel de {client}. Veuillez fermer le fichier Excel et réessayer."
    except:
        pass
    
    return f"❌ Échec de mise à jour du fichier Excel de {client}"


@app.route('/download_client_file/<client_name>')
def download_client_file(client_name):
    """
    Download the updated client Excel file.
    """
    try:
        # Import auto_excel functions
        from export_excel.auto_excel import get_available_clients
        
        # Check if client is configured
        available_clients = get_available_clients()
        if client_name not in available_clients:
            return f"Client '{client_name}' is not configured", 400
        
        # Load client configuration
        with open(os.path.join('export_excel', 'client_config.json'), 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        client_config = config[client_name]
        file_path = os.path.join('export_excel', client_config["file_path"]) 
        
        # Check if file exists
        if not os.path.exists(file_path):
            return f"Client file not found: {file_path}", 404
        
        # Return the file for download
        return send_file(
            file_path,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"{client_name}-Rapport.xlsx"
        )
    except Exception as e:
        return f"Error downloading file: {str(e)}", 500

@app.route('/clients', methods=['GET'])
def clients_page():
    clients = db.get_clients()
    products = db.get_products()
    # Convert sqlite3.Row to dict for Jinja
    clients = [dict(id=row[0], name=row[1]) for row in clients]
    products = [dict(id=row[0], name=row[1], client_id=row[2], responsible_resolution=row[3] if len(row) > 3 else 'SOC Team') for row in products]
    return render_template('clients.html', clients=clients, products=products)

# API endpoints for clients
@app.route('/clients', methods=['POST'])
def add_client():
    data = request.get_json()
    db.add_client(data['name'])
    return '', 204

@app.route('/clients/<int:client_id>', methods=['PUT'])
def update_client(client_id):
    data = request.get_json()
    db.update_client(client_id, data['name'])
    return '', 204

@app.route('/clients/<int:client_id>', methods=['DELETE'])
def delete_client(client_id):
    db.delete_client(client_id)
    return '', 204

# API endpoints for products
@app.route('/products', methods=['POST'])
def add_product():
    data = request.get_json()
    responsible_resolution = data.get('responsible_resolution', 'SOC Team')
    db.add_product(data['name'], data['client_id'], responsible_resolution)
    return '', 204

@app.route('/products/<int:product_id>', methods=['PUT'])
def update_product(product_id):
    data = request.get_json()
    responsible_resolution = data.get('responsible_resolution', 'SOC Team')
    db.update_product(product_id, data['name'], data['client_id'], responsible_resolution)
    return '', 204

@app.route('/products/<int:product_id>', methods=['DELETE'])
def delete_product(product_id):
    db.delete_product(product_id)
    return '', 204

@app.route('/auto_bulletin', methods=['GET', 'POST'])
def auto_bulletin():
    extraction_error = None
    extracted_data = None
    generated_files = []

    if request.method == 'POST':
        bulletin_id = request.form.get('bulletin_id')
        url = request.form.get('url')
        
        if bulletin_id and url:
            try:
                cohere_api_key = os.getenv('COHERE_API_KEY')
                
                if 'edit_data' in request.form:
                    # User is editing extracted data
                    data = {
                        'titre': request.form.get('titre', ''),
                        'CVEs ID': request.form.get('CVEs ID', '').split('\n') if request.form.get('CVEs ID') else [],
                        'Produits affectés': request.form.get('Produits affectés', '').split('\n') if request.form.get('Produits affectés') else [],
                        'Description': request.form.get('Description', ''),
                        'Mitigations': normalize_mitigations(request.form.get('Mitigations', '')),
                        'risques': request.form.get('risques', '').split('\n') if request.form.get('risques') else [],
                        'Exploit': request.form.get('Exploit', ''),
                        'Delai': request.form.get('Delai', ''),
                        'score': request.form.get('score', ''),
                        'Date': request.form.get('Date', ''),
                        'Références': request.form.get('Références', '').split('\n') if request.form.get('Références') else []
                    }
                else:
                    # User is extracting data - perform scraping
                    mitigation_handler = MitigationHandler(cohere_api_key)
                    description_handler = DescriptionHandler(cohere_api_key)
                    if "dgssi" in url.lower():
                        scraper = DGSSIScraper(mitigation_handler, description_handler)
                        data = scraper.scrape_bulletin(url)
                    elif "cert" in url.lower():
                        scraper = CERTFRScraper(mitigation_handler)
                        data = scraper.parse_advisory(url)
                    else:
                        extraction_error = "URL non reconnue. Elle doit contenir \"dgssi\" ou \"cert\"."
                        data = None

                if data:
                    # Normalize mitigations format
                    if 'Mitigations' in data:
                        data['Mitigations'] = normalize_mitigations(data['Mitigations'])
                    if 'confirm' in request.form:
                        data = sanitize_extracted_data(data)
                        for key in list(data.keys()):
                            if key in request.form:
                                value = request.form.get(key)
                                if key == 'Mitigations':
                                    data[key] = normalize_mitigations(value)
                                else:
                                    if isinstance(data[key], list):
                                        data[key] = [l.strip() for l in value.split('\n') if l.strip()]
                                    else:
                                        data[key] = value.strip()
                        with tempfile.NamedTemporaryFile('w+', delete=False, suffix='.json', encoding='utf-8') as tmp_json:
                            import json
                            json.dump(data, tmp_json, ensure_ascii=False, indent=4)
                            tmp_json.flush()
                            pdf_path = generate_pdf_from_json(tmp_json.name, bulletin_id)
                            word_path = pdf_path.replace('.pdf', '.docx')
                            app.logger.info(f"Generated PDF: {pdf_path}")
                            if os.path.exists(word_path):
                                app.logger.info(f"Generated DOCX: {word_path}")
                        generated_files = []
                        if os.path.exists(pdf_path):
                            generated_files.append({'name': os.path.basename(pdf_path), 'path': pdf_path, 'type': 'PDF'})
                        if os.path.exists(word_path):
                            generated_files.append({'name': os.path.basename(word_path), 'path': word_path, 'type': 'Word'})
                        os.unlink(tmp_json.name)
                    else:
                        extracted_data = data
                else:
                    extraction_error = 'Impossible d\'extraire les données du bulletin.'
            except Exception as e:
                app.logger.exception("Auto-bulletin generation failed")
                extraction_error = f'Erreur lors de l\'extraction: {e}'
        else:
            extraction_error = 'Veuillez fournir un identifiant de bulletin (ID) et un lien.'
    
    return render_template('auto_bulletin.html', 
                         extraction_error=extraction_error, 
                         extracted_data=extracted_data, 
                         generated_files=generated_files)

@app.route('/dashboard')
def dashboard():
    """KPI Dashboard page"""
    clients = db.get_client_names()
    return render_template('dashboard.html', clients=clients)

@app.route('/api/kpi/<kpi_type>')
def api_kpi_data(kpi_type):
    """API endpoint for KPI data"""
    client = request.args.get('client')
    month = request.args.get('month')
    
    try:
        if kpi_type == 'status_distribution':
            data = db.get_status_distribution(client, month)
        elif kpi_type == 'sla_compliance':
            data = db.get_sla_compliance(client, month)
        elif kpi_type == 'monthly_trend':
            months = int(request.args.get('months', 6))
            data = db.get_monthly_trend(client, months)
        elif kpi_type == 'monthly_evolution':
            selected_months = request.args.getlist('months')  # Get list of selected months
            data = db.get_monthly_evolution(client, selected_months)
        elif kpi_type == 'available_months':
            data = db.get_available_months(client)
        elif kpi_type == 'open_vs_closed':
            data = db.get_open_vs_closed(client, month)
        elif kpi_type == 'comprehensive_table':
            selected_months = request.args.getlist('months')
            data = db.get_comprehensive_table(client, selected_months)
        elif kpi_type == 'summary':
            data = db.get_kpi_summary(client, month)
        else:
            return jsonify({'error': 'Invalid KPI type'}), 400
        
        return jsonify({
            'success': True,
            'data': data,
            'client': client,
            'filters': {
                'month': month
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/kpi/global_overview')
def api_global_overview():
    """API endpoint for global KPI overview across all clients"""
    month = request.args.get('month')
    
    try:
        clients = db.get_client_names()
        global_data = {
            'clients_summary': {},
            'total_counts': {
                'status': {},
                'sla': {}
            }
        }
        
        # Get global totals directly (not per client to avoid double counting)
        global_open_vs_closed = db.get_open_vs_closed(None, month)
        global_sla = db.get_sla_compliance(None, month)
        
        # Store global totals
        global_data['total_counts']['status'] = global_open_vs_closed
        global_data['total_counts']['sla'] = global_sla
        
        # Also get individual client data for reference
        for client in clients:
            client_data = db.get_kpi_summary(client, month)
            global_data['clients_summary'][client] = client_data
        
        return jsonify({
            'success': True,
            'data': global_data,
            'total_clients': len(clients),
            'filters': {
                'month': month
            }
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/auto_patch', methods=['GET', 'POST'])
def auto_patch():
    message = None
    error = None
    if request.method == 'POST':
        try:
            from auto_patch.script import process_uploaded_excel
            # Get uploaded file
            file = request.files.get('excel_file')
            if not file:
                error = "Veuillez sélectionner un fichier Excel."
                return render_template('auto_patch.html', error=error, message=message)
            
            # Validate file extension
            if not file.filename.lower().endswith(('.xlsx', '.xls')):
                error = "Veuillez sélectionner un fichier Excel valide (.xlsx ou .xls)."
                return render_template('auto_patch.html', error=error, message=message)
            
            # Get sheet name (optional)
            sheet_name = request.form.get('sheet_name') or None
            
            # Process file using module
            output_path, output_filename, cleanup_fn = process_uploaded_excel(file, sheet_name)
            
            response = send_file(
                output_path,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                as_attachment=True,
                download_name=output_filename
            )
            response.call_on_close(cleanup_fn)
            return response
        except Exception as e:
            error = f"Erreur lors du traitement : {str(e)}"
    
    return render_template('auto_patch.html', error=error, message=message)


if __name__ == '__main__':
    app.run(debug=True)
