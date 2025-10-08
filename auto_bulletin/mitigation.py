import json
import requests
from typing import Dict, List, Optional
import os


class MitigationHandler:
    def __init__(self, api_key: str, mitigations_file: str = 'product_mitigations.json'):
        """
        Initialize the MitigationHandler with Cohere API key and mitigations database file.
        
        Args:
            api_key (str): Cohere API key
            mitigations_file (str): Path to the JSON file containing product mitigations
        """
        self.api_key = api_key
        base_dir = os.path.dirname(os.path.abspath(__file__))
        self.mitigations_file = os.path.join(base_dir, mitigations_file) if not os.path.isabs(mitigations_file) else mitigations_file
        self.mitigations_db = self._load_mitigations()

    def _load_mitigations(self) -> Dict:
        """Load mitigations from JSON file."""
        try:
            with open(self.mitigations_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            print(f"Error: Mitigations file {self.mitigations_file} is not a valid JSON.")
            return {}
        except FileNotFoundError:
            print(f"Warning: Mitigations file {self.mitigations_file} not found. Creating empty database.")
            return {}

    def find_mitigation_by_title(self, titre: str) -> Optional[Dict[str, str]]:
        """
        Find mitigation by checking if product names in the mitigations database appear in the 'titre' field.

        Args:
            titre (str): Title of the advisory.

        Returns:
            Optional[Dict[str, str]]: A dictionary containing the matched product and mitigation, or the "General" mitigation.
        """
        normalized_title = titre.lower()
        for product, mitigation in self.mitigations_db.items():
            if product.lower() in normalized_title:
                return {"Product": product, "Mitigation": mitigation}

        # Fallback to "General" mitigation if no specific product is found
        general_mitigation = self.mitigations_db.get("General")
        if general_mitigation:
            return {"Product": "General", "Mitigation": general_mitigation}

        return None

    def generate_mitigation(self, product: str, affected_versions: List[str], old_mitigation: Optional[Dict]) -> str:
        """
        Generate a new mitigation using Cohere based on the old mitigation and affected versions.
        
        Args:
            product (str): Name of the product.
            affected_versions (List[str]): List of affected versions/descriptions.
            old_mitigation (Optional[Dict]): Previous mitigation data as reference example.
        
        Returns:
            str: Generated mitigation text in JSON format.
        """
        if not old_mitigation:
            return json.dumps({
                "recommendation": "Appliquer les correctifs de sécurité",
                "versions": ["Mettre à jour vers la dernière version sécurisée"]
            }, ensure_ascii=False)

        # Prepare old mitigation as reference
        old_mitigation_example = json.dumps(old_mitigation, ensure_ascii=False, indent=2)
        
        # Create strict and specific prompt
        user_message = f"""Tu es un expert en cybersécurité. Ta tâche est de générer une stratégie de mitigation au format JSON strict.

PRODUIT: {product}
VERSIONS/SYSTÈMES AFFECTÉS: {json.dumps(affected_versions, ensure_ascii=False)}

ANCIENNE MITIGATION (à utiliser comme référence):
{old_mitigation_example}

RÈGLES STRICTES À RESPECTER:

1. FORMAT DE SORTIE OBLIGATOIRE:
{{
    "recommendation": "texte de la recommandation",
    "versions": ["version1", "version2", "version3"]
}}

2. RÈGLES POUR "recommendation":
   - Une phrase courte et claire décrivant l'action à effectuer
   - Exemples: "Mise à jour vers la version:", "Appliquer les correctifs de sécurité", "Mettre à jour le produit"
   - PAS de liste ou énumération dans ce champ

3. RÈGLES POUR "versions":
   - TOUJOURS un tableau (array) de chaînes de caractères
   - Chaque élément du tableau = UNE SEULE version ou action
   - INTERDIT de mettre plusieurs versions séparées par des virgules dans un seul élément
   - Si les versions affectées contiennent des numéros de version (ex: "6.0.41", "7.0.18"):
     * Créer un élément distinct pour chaque version
     * Format: "Nom Produit X.X.X ou ultérieure"
   - Si les versions affectées sont descriptives (ex: "sans correctifs"):
     * Créer des actions claires: ["Appliquer les derniers correctifs de sécurité disponibles"]

EXEMPLES CONCRETS:

Exemple 1 - Versions numériques:
Input: ["Zabbix Agent 6.0.41", "Zabbix Agent 7.0.18", "Zabbix 6.0.41"]
Output:
{{
    "recommendation": "Mise à jour Zabbix vers la version:",
    "versions": [
        "Zabbix Agent 6.0.41 ou ultérieure",
        "Zabbix Agent 7.0.18 ou ultérieure",
        "Zabbix 6.0.41 ou ultérieure"
    ]
}}

Exemple 2 - Descriptions de correctifs:
Input: ["Enterprise Application Service pour Java sans les derniers correctifs de sécurité"]
Output:
{{
    "recommendation": "Appliquer les correctifs de sécurité",
    "versions": ["Appliquer les derniers correctifs de sécurité disponibles"]
}}

Exemple 3 - Versions multiples avec sous-versions:
Input: ["Windows Server 2019 (toutes versions)", "Windows Server 2022 23H2"]
Output:
{{
    "recommendation": "Appliquer les mises à jour de sécurité Windows",
    "versions": [
        "Windows Server 2019 (dernière version sécurisée)",
        "Windows Server 2022 23H2 ou ultérieure"
    ]
}}

INSTRUCTIONS FINALES:
- Génère UNIQUEMENT le JSON, sans texte avant ou après
- Chaque version doit être un élément séparé dans le tableau
- Utilise l'ancienne mitigation comme guide de style et structure
- Respecte exactement le format JSON indiqué

GÉNÈRE MAINTENANT LE JSON:"""

        try:
            models_to_try = [
                'command-a-03-2025',
                'command-r-plus-08-2024',
                'command-r-08-2024',
                'command-r'
            ]
            
            for model_name in models_to_try:
                try:
                    print(f"Attempting model: {model_name}")
                    
                    response = requests.post(
                        'https://api.cohere.ai/v1/chat',
                        json={
                            'model': model_name,
                            'message': user_message,
                            'max_tokens': 500,
                            'temperature': 0.1,
                            'stop_sequences': ['\n\n\n', 'RÈGLES', 'EXEMPLES']
                        },
                        headers={'Authorization': f'Bearer {self.api_key}'},
                        verify=False
                    )

                    if response.status_code == 200:
                        data = response.json()
                        generated_text = (data.get('text') or data.get('generation', {}).get('text', '')).strip()
                        
                        # Clean unwanted prefixes and common issues
                        unwanted_phrases = [
                            "Voici le JSON pour ces données :",
                            "Voici la nouvelle stratégie d'atténuation :",
                            "Bien sûr, voici",
                            "Voici le JSON:",
                            "JSON:",
                            "Sortie:",
                            "Output:",
                            "```json",
                            "```",
                            "GÉNÈRE MAINTENANT LE JSON:",
                            "Le JSON généré:"
                        ]
                        for phrase in unwanted_phrases:
                            generated_text = generated_text.replace(phrase, "").strip()
                        
                        # Additional cleaning for common model issues
                        # Remove trailing commas before closing braces/brackets
                        import re
                        generated_text = re.sub(r',(\s*[}\]])', r'\1', generated_text)
                        
                        # Remove any text after the closing brace
                        brace_index = generated_text.rfind('}')
                        if brace_index != -1:
                            generated_text = generated_text[:brace_index + 1]
                        
                        # Find the first opening brace to remove any leading text
                        brace_start = generated_text.find('{')
                        if brace_start != -1:
                            generated_text = generated_text[brace_start:]
                        
                        # Debug: Log the raw response for inspection
                        print(f"Raw response from {model_name}:")
                        print(f"'{generated_text}'")
                        print(f"Length: {len(generated_text)}")
                        
                        # Validate JSON
                        validated = self._validate_json(generated_text)
                        if validated:
                            print(f"Successfully generated mitigation with model: {model_name}")
                            return validated
                        else:
                            print(f"Model {model_name} generated invalid JSON, trying next...")
                            continue
                    else:
                        print(f"HTTP {response.status_code} for model {model_name}")
                        if response.status_code == 404:
                            continue
                        
                except Exception as e:
                    print(f"Error with model {model_name}: {str(e)}")
                    continue
            
            # Fallback if all models fail
            print("All models failed, creating fallback mitigation")
            return self._create_fallback(affected_versions)
            
        except Exception as e:
            print(f"Critical error: {str(e)}")
            return self._create_fallback(affected_versions)

    def _validate_json(self, response: str) -> Optional[str]:
        """Validate and normalize JSON response."""
        # Try multiple JSON extraction methods
        json_candidates = [response]
        
        # Method 1: Try to extract JSON from between first { and last }
        import re
        json_match = re.search(r'\{.*\}', response, re.DOTALL)
        if json_match:
            json_candidates.append(json_match.group(0))
        
        # Method 2: Try to find JSON that starts with {"recommendation"
        rec_match = re.search(r'\{"recommendation".*?\}', response, re.DOTALL)
        if rec_match:
            json_candidates.append(rec_match.group(0))
        
        for candidate in json_candidates:
            try:
                parsed = json.loads(candidate.strip())

                if not isinstance(parsed, dict):
                    print(f"Validation failed: Response is not a dict, got {type(parsed)}")
                    continue
                
                if "recommendation" not in parsed or "versions" not in parsed:
                    print(f"Validation failed: Missing required keys. Has: {list(parsed.keys())}")
                    continue

                # Ensure versions is a list
                versions = parsed.get("versions", [])
                if not isinstance(versions, list):
                    print(f"Validation failed: 'versions' is not a list, got {type(versions)}: {versions}")
                    continue

                # Normalize versions: split any comma-separated strings
                normalized_versions = []
                for v in versions:
                    if isinstance(v, str):
                        # Split on commas if present
                        if ',' in v:
                            normalized_versions.extend([item.strip() for item in v.split(',') if item.strip()])
                        else:
                            normalized_versions.append(v.strip())
                    else:
                        normalized_versions.append(str(v).strip())

                # Remove duplicates while preserving order
                seen = set()
                unique_versions = []
                for version in normalized_versions:
                    if version not in seen:
                        seen.add(version)
                        unique_versions.append(version)

                parsed["versions"] = unique_versions
                return json.dumps(parsed, ensure_ascii=False)

            except json.JSONDecodeError as e:
                print(f"JSON decode error with candidate: {e}")
                continue
            except Exception as e:
                print(f"Validation error with candidate: {e}")
                continue
        
        # If all candidates failed
        print(f"All JSON candidates failed. Original response: '{response}'")
        return None

    def _create_fallback(self, affected_versions: List[str]) -> str:
        """Create a fallback mitigation when generation fails."""
        # Split any comma-separated versions
        clean_versions = []
        for v in affected_versions:
            if isinstance(v, str) and ',' in v:
                clean_versions.extend([x.strip() for x in v.split(',') if x.strip()])
            else:
                clean_versions.append(v.strip() if isinstance(v, str) else str(v).strip())
        
        if not clean_versions:
            clean_versions = ["Mettre à jour vers la dernière version sécurisée"]
        
        return json.dumps({
            "recommendation": "Appliquer les correctifs de sécurité",
            "versions": clean_versions
        }, ensure_ascii=False)

    def process_advisory(self, advisory: Dict) -> str:
        """
        Process an advisory JSON object to generate a mitigation.

        Args:
            advisory (Dict): JSON object containing advisory details.

        Returns:
            str: Generated mitigation in JSON format.
        """
        titre = advisory.get("titre", "")
        produits_affectés = advisory.get("Produits affectés", [])

        if not titre:
            return json.dumps({"error": "Advisory missing 'titre' field."})
        
        if not produits_affectés:
            return json.dumps({"error": "Advisory missing 'Produits affectés' field."})

        # Find matching product and mitigation
        matching_mitigation = self.find_mitigation_by_title(titre)
        if not matching_mitigation:
            return json.dumps({"error": f"Aucune mitigation disponible pour: {titre}"})

        product = matching_mitigation["Product"]
        old_mitigation = matching_mitigation["Mitigation"]

        # Generate mitigation
        generated_mitigation = self.generate_mitigation(product, produits_affectés, old_mitigation)

        # Parse and structure the response
        try:
            mitigation_dict = json.loads(generated_mitigation)
            
            return json.dumps({
                product: {
                    "recommendation": mitigation_dict.get("recommendation", ""),
                    "versions": mitigation_dict.get("versions", [])
                }
            }, ensure_ascii=False, indent=2)
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            return json.dumps({
                product: {
                    "recommendation": "Appliquer les correctifs de sécurité",
                    "versions": ["Erreur de génération - Contacter l'équipe de sécurité"]
                }
            }, ensure_ascii=False, indent=2)