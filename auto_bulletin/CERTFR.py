import requests
from bs4 import BeautifulSoup
import json
from datetime import datetime
import urllib3
import ssl
import chardet
import re
from .score import calculate_cvss_range

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class CERTFRScraper:
    def __init__(self, mitigation_handler):
        self.base_url = "https://www.cert.ssi.gouv.fr"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.mitigation_handler = mitigation_handler

    def get_page_content(self, url):
        try:
            response = requests.get(url, headers=self.headers, verify=False)
            response.raise_for_status()
            encoding = chardet.detect(response.content)['encoding']
            content = response.content.decode(encoding, errors='replace')
            return content
        except requests.RequestException as e:
            print(f"Error fetching the page: {e}")
            return None

    def parse_advisory(self, url):
        content = self.get_page_content(url)
        if not content:
            return None

        soup = BeautifulSoup(content, 'html.parser')
        advisory = {}

        # Extract title
        title_element = soup.find('div', class_='meta-title')
        if title_element and title_element.find('h1'):
            advisory['titre'] = title_element.find('h1').text.replace('Objet: ', '').strip()

        # Extract and format date
        date_element = soup.find('td', text='Date de la dernière version')
        if date_element:
            raw_date = date_element.find_next('td').text.strip()
            try:
                advisory['Date'] = datetime.strptime(raw_date, '%d %B %Y').strftime('%d/%m/%Y')
            except ValueError:
                advisory['Date'] = raw_date  # Fallback to raw date if format fails

        # Extract risks
        advisory['risques'] = self.extract_section_items(soup, 'Risque')

        # Extract affected products
        advisory['Produits affectés'] = self.extract_section_items(soup, 'Systèmes affectés')

        # Extract description (handle multiple paragraphs)
        advisory['Description'] = self.extract_section_text(soup, 'Résumé')

        # Check if there's active exploitation
        advisory['Exploit'] = self.detect_active_exploitation(advisory['Description'])

        # Extract documentation URLs
        advisory['Références'] = self.extract_documentation_urls(soup)

        # Extract CVEs
        advisory['CVEs ID'] = self.extract_cve_ids(soup)

        # Generate mitigations
        try:
            mitigation_content = self.mitigation_handler.process_advisory(advisory)
            try:
                mitigation_obj = json.loads(mitigation_content)
            except Exception:
                mitigation_obj = {'Aucune mitigation': {'recommendation': str(mitigation_content), 'versions': []}}

            # Normalize mitigation structure
            from auto_bulletin.utils import normalize_mitigations
            normalized = normalize_mitigations(mitigation_obj)
            if not normalized:
                advisory['Mitigations'] = [{'Aucune mitigation': {'recommendation': 'Aucune mitigation disponible', 'versions': []}}]
            else:
                advisory['Mitigations'] = normalized
        except Exception as e:
            print(f"Unexpected error in mitigation generation: {e}")
            advisory['Mitigations'] = [{"description": "Erreur lors de la génération des mitigations"}]

        # After extracting CVEs
        if advisory['CVEs ID']:
            advisory['score'] = calculate_cvss_range(advisory['CVEs ID'])
        else:
            advisory['score'] = "-"

        # Calculate Delai based on CVSS score
        from . import auto_json
        advisory['Delai'] = auto_json.calculate_delai_from_score(advisory['score'])

        return advisory

    def extract_section_items(self, soup, section_title):
        items = []
        section = soup.find('h2', text=re.compile(f"^{section_title}s?$", re.IGNORECASE))
        if section:
            list_section = section.find_next(['ul', 'ol'])
            if list_section:
                items = [li.text.strip() for li in list_section.find_all('li')]
        return items

    def extract_section_text(self, soup, section_title):
        section = soup.find('h2', string=re.compile(f"^{section_title}s?$", re.IGNORECASE))
        if not section:
            return ''

        paragraphs = []

        for sibling in section.find_all_next():
            if sibling.name == 'h2':
                break

            if sibling.name == 'p':
                paragraphs.append(sibling.text.strip())
        return "\n".join(paragraphs)



    def detect_active_exploitation(self, description):
        """Detect if there is mention of active exploitation in the description."""
        exploitation_phrases = [
            "est activement exploitée",
            "sont activement exploitées"
        ]
        
        # Check if any of these phrases appear in the full description
        for phrase in exploitation_phrases:
            if phrase.lower() in description.lower():
                return "YES"
        return "NON"

    def extract_documentation_urls(self, soup):
        documentation = []
        doc_section = soup.find('h2', text=re.compile(r"Documentation", re.IGNORECASE))
        if doc_section:
            doc_list = doc_section.find_next('ul')
            if doc_list:
                for item in doc_list.find_all('a'):
                    url = item.get('href')
                    if url and 'cve.org' not in url.lower():
                        documentation.append(url)
        return documentation

    def extract_cve_ids(self, soup):
        cve_ids = []
        for a_tag in soup.find_all('a', href=True):
            cve_match = re.search(r'CVE-\d{4}-\d+', a_tag.text)
            if cve_match:
                cve_ids.append(cve_match.group(0))
        return list(set(cve_ids))

    def generate_general_mitigations(self, affected_products):
        """Generate general mitigations based on affected products."""
        mitigations = []
        
        for product in affected_products:
            # Extract any versions mentioned in the product (look for versions like "versions antérieures à X")
            version_match = re.search(r'(\d+\.\d+\.\d+(?:\.\d+)?|\d{1,2}\.\d{1,2})', product)
            if version_match:
                version = version_match.group(0)
                
                # Extract product name (everything before the version information)
                product_name_match = re.match(r'([^\d]+)', product)
                if product_name_match:
                    product_name = product_name_match.group(1).strip()
                    # Add the mitigation with the format
                    mitigations.append(f"Mise à jour {product_name} vers {version} ou ultérieures.")

        return mitigations

    def save_to_json(self, advisory, filename):
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(advisory, f, ensure_ascii=False, indent=4)
            print(f"Advisory saved to {filename}")
        except Exception as e:
            print(f"Error saving to JSON: {e}")





def modify_advisory_data(advisory):
    print("\nDo you want to modify any section? (yes/no)")
    choice = input().lower()
    if choice == 'yes':
        for key, value in advisory.items():
            print(f"\nCurrent {key}: {value}")
            new_value = input(f"Enter new value for {key} (or press Enter to keep it unchanged): ")
            if new_value:
                advisory[key] = new_value
    return advisory

def main():
    # Import and initialize mitigation handler
    from .mitigation import MitigationHandler
    mitigation_handler = MitigationHandler('YasxMgUrP1VS3hv5AoakslgKO8yqhH3CpW7ktGIK')
    
    scraper = CERTFRScraper(mitigation_handler)
    url = input("Enter the URL of the advisory: ")
    advisory_data = scraper.parse_advisory(url)

    if advisory_data:
        print("\nExtracted Information:")
        for key, value in advisory_data.items():
            print(f"{key}: {value}")

        # Allow modification
        modified_advisory = modify_advisory_data(advisory_data)

        # Save to JSON
        scraper.save_to_json(modified_advisory, 'advisory_data.json')

if __name__ == "__main__":
    main()
