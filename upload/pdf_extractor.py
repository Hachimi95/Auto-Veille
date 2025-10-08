import os
import json
import fitz  # PyMuPDF
import requests
from dotenv import load_dotenv
import urllib3
import re
from datetime import datetime
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Load API keys from .env file
load_dotenv()

def get_openrouter_api_key():
    """Get OpenRouter API key with fallback support"""
    # Primary API key
    primary_key = os.getenv("OPENROUTER_API_KEY")
    backup_key = os.getenv("OPENROUTER_API_KEY_BACKUP")
    
    if primary_key:
        return primary_key
    elif backup_key:
        print("⚠️ Using backup OpenRouter API key")
        return backup_key
    else:
        raise ValueError("No OpenRouter API keys found. Please set OPENROUTER_API_KEY or OPENROUTER_API_KEY_BACKUP in your .env file.")

OPENROUTER_API_KEY = get_openrouter_api_key()

# ---- Step 1: Extract text from PDF ----
def extract_text_from_pdf(pdf_path):
    """Extract text using PyMuPDF"""
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text()
        print(f"✅ Extracted {len(text)} characters from PDF")
        return text
    except Exception as e:
        print(f"❌ PDF extraction failed: {str(e)}")
        return ""

def clean_produit_name(title):
    """Clean the produit name by removing common words"""
    # Remove common words that appear in vulnerability titles
    words_to_remove = [
        'Multiples', 'vulnérabilités', 'dans', 'les', 'Une', 'vulnérabilité',
        'Multiple', 'vulnerabilities', 'in', 'the', 'A', 'vulnerability',
        'Nouvelles', 'New', 'Critical', 'Critique', 'Important', 'Important',
        'Modéré', 'Moderate', 'Faible', 'Low'
    ]
    
    # Convert to lowercase for comparison
    title_lower = title.lower()
    
    # Remove the words
    for word in words_to_remove:
        # Use regex to match whole words only
        pattern = r'\b' + re.escape(word.lower()) + r'\b'
        title_lower = re.sub(pattern, '', title_lower)
    
    # Clean up extra spaces and capitalize first letter
    cleaned = ' '.join(title_lower.split())
    if cleaned:
        cleaned = cleaned[0].upper() + cleaned[1:]
    
    return cleaned if cleaned else title

def extract_id_bulletin(filename):
    """Extract ID Bulletin from filename (e.g., '13112024-12- Multiples vulnérabilités...' -> '13112024-12')"""
    # Extract the date part before the first dash after the date
    match = re.match(r'(\d{8}-\d+)', filename)
    if match:
        return match.group(1)
    return filename

# ---- Step 2: Send text to OpenRouter API (Claude 3 Haiku) ----
def extract_security_data(text):
    """Use OpenRouter Claude model to extract structured data with fallback API keys"""
    if not text.strip():
        print("⚠️ No text to send to LLM")
        return {}

    # Get list of API keys to try
    api_keys = []
    primary_key = os.getenv("OPENROUTER_API_KEY")
    backup_key = os.getenv("OPENROUTER_API_KEY_BACKUP")
    
    if primary_key:
        api_keys.append(("Primary", primary_key))
    if backup_key:
        api_keys.append(("Backup", backup_key))
    
    if not api_keys:
        print("❌ No OpenRouter API keys available")
        return {}

    url = "https://openrouter.ai/api/v1/chat/completions"
    payload = {
        "model": "anthropic/claude-3-haiku",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Vous êtes un spécialiste de l'extraction de bulletins de sécurité. "
                    "Extrayez les données structurées des bulletins de sécurité en français. "
                    "Retournez UNIQUEMENT du JSON valide avec ces clés : "
                    "title, cves (tableau), date, description, cvss_score, "
                    "risk (tableau), "
                    "exploit, processing_time (nombre de jours pour remédiation), "
                    "affected_products (tableau), "
                    "mitigation (tableau de CHAQUE LIGNE de la section mitigations, workarounds ou remédiation, sans résumer, sans ignorer, sans condenser, même si la section est longue ou répétitive. NE JAMAIS résumer ou ignorer cette section. Retournez TOUTES les lignes telles quelles.), "
                    "reference (tableau). "
                    "Assurez-vous que chaque ligne de la section mitigation est un élément séparé du tableau, même si la section est longue. "
                    "Assurez-vous que processing_time est un nombre entier."
                )
            },
            {
                "role": "user",
                "content": text
            }
        ]
    }

    # Try each API key until one works
    for key_name, api_key in api_keys:
        try:
            print(f"🔄 Trying {key_name} API key...")
            headers = {
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://yourdomain.com",  # optional
                "X-Title": "Auto-Veille PDF Extractor"     # optional
            }
            
            response = requests.post(url, headers=headers, data=json.dumps(payload), verify=False, timeout=30)
            response.raise_for_status()
            raw = response.json()
            json_data = json.loads(raw["choices"][0]["message"]["content"])
            print(f"✅ AI extraction successful using {key_name} API key")
            return json_data
            
        except requests.exceptions.Timeout:
            print(f"⏰ {key_name} API key timed out")
            continue
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                print(f"🔑 {key_name} API key is invalid or expired")
            elif e.response.status_code == 429:
                print(f"🚫 {key_name} API key rate limit exceeded")
            else:
                print(f"❌ {key_name} API key HTTP error: {e.response.status_code}")
            continue
        except requests.exceptions.RequestException as e:
            print(f"🌐 {key_name} API key network error: {str(e)}")
            continue
        except json.JSONDecodeError as e:
            print(f"📄 {key_name} API key returned invalid JSON: {str(e)}")
            continue
        except Exception as e:
            print(f"❌ {key_name} API key failed: {str(e)}")
            continue
    
    print("❌ All API keys failed. Please check your API keys and try again.")
    return {}

# ---- Step 3: Save output to JSON ----
def save_to_json(data, output_file):
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 Data saved to {output_file}")
    except Exception as e:
        print(f"❌ Failed to save JSON: {str(e)}")


def match_clients_and_teams(title):
    """Match clients and teams based on the title of the vulnerability using database data"""
    try:
        # Import the database function
        from database import db
        
        # Get clients and their products from database
        clients_data = db.get_clients_with_products()

        matched_clients = []
        responsible_teams = []

        print(f"🔍 Client matching - Title: {title}")
        print(f"🔍 Client matching - Available clients and products: {clients_data}")

        # Match clients based on product names in the title
        title_lower = title.lower()
        
        for client_name, products in clients_data.items():
            # Skip clients that have no products
            if not products:
                print(f"🔍 Client matching - Skipping {client_name} (no products)")
                continue
                
            # Check if any of the client's products are mentioned in the title
            for product in products:
                product_name = product['name']
                responsible_resolution = product['responsible_resolution']
                product_lower = product_name.lower()
                # Improved matching logic: check if product name is contained in title
                if product_lower in title_lower:
                    matched_clients.append(client_name)
                    responsible_teams.append(responsible_resolution)
                    print(f"🔍 Client matching - Matched {client_name} for product: {product_name} with responsible: {responsible_resolution}")
                    break  # Found a match for this client, move to next client
        
        # If no matches found, don't add any clients
        if not matched_clients:
            print("🔍 Client matching - No specific matches found, no clients will be added")
            return [], []
        
        print(f"🔍 Client matching - Final matched clients: {matched_clients}")
        print(f"🔍 Client matching - Responsible teams: {responsible_teams}")

        return matched_clients, responsible_teams
    except Exception as e:
        print(f"🔍 Error in client matching: {e}")
        # Return empty lists if there's an error
        return [], []

# ---- Step 4: Main workflow ----
def main(pdf_path):
    print("🔍 Starting security bulletin extraction...")

    # Extract text
    text = extract_text_from_pdf(pdf_path)
    if not text:
        print("🚫 No text extracted, exiting.")
        return

    # Optional: save raw text for debugging
    with open("debug_raw_text.txt", "w", encoding="utf-8") as f:
        f.write(text)

    # Extract structured data via API
    data = extract_security_data(text)
    if not data:
        print("🚫 No structured data extracted, exiting.")
        return

    # Clean up the data
    if 'title' in data:
        data['produit_name'] = clean_produit_name(data['title'])
    
    # Extract ID Bulletin from filename
    filename = os.path.basename(pdf_path)
    data['id_bulletin'] = extract_id_bulletin(filename)
    
    # Set default values for new fields
    data['Date_de_notification'] = data.get('date', '')
    data['processing_time'] = data.get('processing_time', 5)  # Default 5 days
    data['risk'] = data.get('risk', 'Important')  # Default risk level
    
    # Ensure processing_time is an integer
    if isinstance(data['processing_time'], str):
        try:
            data['processing_time'] = int(data['processing_time'])
        except:
            data['processing_time'] = 5

    # Save as JSON
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    output_file = f"{base_name}_security_data.json"
    save_to_json(data, output_file)
    
    # Print the result
    print("\n📄 Extraction Results:")
    print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    # Replace this with your file path
    PDF_PATH = "10072025-08 - Multiples vulnérabilités dans les prodtuis Fortinet.pdf"
    main(PDF_PATH)
    print("✅ Processing complete")


