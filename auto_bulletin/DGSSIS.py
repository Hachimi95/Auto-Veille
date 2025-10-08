import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import chardet
import urllib3
import re
from .mitigation import MitigationHandler
from .description import DescriptionHandler
from .score import calculate_cvss_range


# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class DGSSIScraper:
    def __init__(self, mitigation_handler, description_handler):
        self.words_to_remove = ['critiques', 'le navigateur' , 'activement' , 'exploité', 'critique', 'exploitées', 'sont',  'plusieurs']
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.mitigation_handler = mitigation_handler 
        self.description_handler = description_handler

    def clean_title(self, title):
        # Replace 'affectant' with 'dans'
        title = title.replace('affectant', 'dans')
        
        # Remove specified words        
        words_to_remove = ['Patch', 'Tuesday', 'Décembre', '2024', 'navigateur', 'affectant', 'Patch', 'Tuesday', 'Décembre', '2024']
        for word in words_to_remove:
            title = title.replace(word, '')

        # Remove other specified words
        for word in self.words_to_remove:
            if word != 'affectant':
                title = title.replace(word, '')
        
        # Clean up extra spaces
        title = ' '.join(title.split())
        

        # Add prefix based on vulnerability type
        if 'Zero-day' in title:
            title = title.replace('Zero-day', 'Une Vulnérabilité Zero-day')
        if title.startswith('Vulnérabilités'):
            title = 'Multiple ' + title
        elif title.startswith('Vulnérabilité'):
            title = 'Une ' + title
            
        return title

    def detect_active_exploitation(self, description):
        """Detect if there is mention of active exploitation in the description."""
        exploitation_phrases = [
            "est activement exploitée",
            "sont activement exploitées",
            "zero-day",
            "0-day"
        ]
        
        for phrase in exploitation_phrases:
            if phrase.lower() in description.lower():
                return "YES"
        return "NON"

    

    def extract_cve_ids(self, identificateurs):
        """Extract CVE IDs from the identificateurs externes section."""
        cve_ids = []
        for item in identificateurs:
            # Use regex to find all CVE patterns in the text
            # This will handle CVEs separated by spaces, &nbsp;, or other whitespace
            cve_matches = re.findall(r'CVE-\d{4}-\d+', item, re.IGNORECASE)
            cve_ids.extend(cve_matches)
        
        # Remove duplicates and return sorted list
        unique_cves = list(set(cve_ids))
        unique_cves.sort()  # Sort for consistent output
        return unique_cves

    def scrape_bulletin(self, url):
        try:
            response = requests.get(url, headers=self.headers, verify=False)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            data = {}
            
            # Extract title and clean it
            table = soup.find('table', class_='table-bordered')
            if table:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all('td')
                    if len(cells) == 2:
                        key = cells[0].text.strip()
                        value = cells[1].text.strip()
                        if key == "Titre":
                            data['titre'] = self.clean_title(value)
                        elif key == "Date de publication":
                            date_match = re.search(r'\d+.*\d{4}', value)
                            if date_match:
                                raw_date = date_match.group()
                                try:
                                    # Convert date to standard format
                                    date_obj = datetime.strptime(raw_date, '%d %B %Y')
                                    data['Date'] = date_obj.strftime('%d/%m/%Y')
                                except ValueError:
                                    data['Date'] = raw_date

            # Extract affected systems
            systemes_affected = soup.find('div', {'class': 'field--name-field-systemes-affectes'})
            if systemes_affected:
                affected_systems = [li.text.strip() for li in systemes_affected.find_all('li')]
                
                # Remove "Toutes les versions de" from each affected system
                data['Produits affectés'] = [
                    re.sub(r"^Toutes les versions de\s*", "", system) for system in affected_systems
                ]

            # Extract CVE IDs
            identificateurs = soup.find('div', {'class': 'field--name-field-identificateurs-externes'})
            if identificateurs:
                # Try to extract from list items first (original format)
                li_elements = identificateurs.find_all('li')
                if li_elements:
                    data['identificateurs_externes'] = [li.text.strip() for li in li_elements]
                    data['CVEs ID'] = self.extract_cve_ids(data['identificateurs_externes'])
                else:
                    # Try to extract from paragraph elements (new format)
                    p_elements = identificateurs.find_all('p')
                    if p_elements:
                        # Extract text from all paragraphs and spans
                        all_text = []
                        for p in p_elements:
                            all_text.append(p.get_text(strip=True))
                        data['identificateurs_externes'] = all_text
                        data['CVEs ID'] = self.extract_cve_ids(all_text)
                    else:
                        # Fallback: extract CVEs directly from the entire section
                        section_text = identificateurs.get_text(strip=True)
                        data['identificateurs_externes'] = [section_text]
                        data['CVEs ID'] = self.extract_cve_ids([section_text])

            # Extract description
            bilan = soup.find('div', {'class': 'field--name-body'})
            if bilan:
                content = bilan.find('div', class_='field__item')
                if content:
                    raw_description = content.text.strip()
                    # Extract product name from title if available
                    product_name = self.description_handler.extract_product_name(data.get('titre', ''))
                    # Format the description using the handler
                    data['Description'] = self.description_handler.format_description(
                        raw_description,
                        product_name
                    )
                    # Check for active exploitation
                    data['Exploit'] = self.detect_active_exploitation(data['Description'])

            # Extract risks
            risque = soup.find('div', {'class': 'field--name-field-risque'})
            if risque:
                # Try to extract from list items first (original format)
                li_elements = risque.find_all('li')
                if li_elements:
                    data['risques'] = [li.text.strip() for li in li_elements]
                else:
                    # Try to extract from paragraph elements (new format)
                    p_elements = risque.find_all('p')
                    if p_elements:
                        data['risques'] = [p.text.strip() for p in p_elements if p.text.strip()]
                    else:
                        # Fallback: extract text directly from the risk section
                        risk_text = risque.get_text(strip=True)
                        if risk_text:
                            data['risques'] = [risk_text]
                        else:
                            data['risques'] = []

            # Extract references
            reference = soup.find('div', {'class': 'field--name-field-reference'})
            if reference:
                data['Références'] = [link['href'] for link in reference.find_all('a')]

            # Generate mitigations
            mitigation_result = self.mitigation_handler.process_advisory(data)
            try:
                mitigation_obj = json.loads(mitigation_result)
            except Exception:
                mitigation_obj = {'Aucune mitigation': {'recommendation': str(mitigation_result), 'versions': []}}

            # Normalize mitigation structure to avoid raw JSON showing in UI
            from auto_bulletin.utils import normalize_mitigations
            normalized = normalize_mitigations(mitigation_obj)
            if not normalized:
                data['Mitigations'] = [{'Aucune mitigation': {'recommendation': 'Aucune mitigation disponible', 'versions': []}}]
            else:
                data['Mitigations'] = normalized


            # Calculate CVSS score if CVEs are available
            if data.get('CVEs ID'):
                data['score'] = calculate_cvss_range(data['CVEs ID'])
            else:
                data['score'] = "-"

            # Calculate Delai based on CVSS score
            from . import auto_json
            data['Delai'] = auto_json.calculate_delai_from_score(data['score'])

            return data

        except Exception as e:
            print(f"An error occurred: {str(e)}")
            return None

    def save_to_json(self, data, filename='dgssi_bulletin.json'):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Data successfully saved to {filename}")
        except Exception as e:
            print(f"Error saving to JSON: {e}")
