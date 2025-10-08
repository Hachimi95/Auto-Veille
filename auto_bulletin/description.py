import requests
import re
from typing import Optional

class DescriptionHandler:
    def __init__(self, api_key: str):
        """
        Initialize the DescriptionHandler with Cohere API key.
        
        Args:
            api_key (str): Cohere API key
        """
        self.api_key = api_key
        self.description_template = """
Une/De multiples vulnérabilité(s) a/ont été découverte(s) dans [PRODUCT]. [IMPACT_STATEMENT].

Examples:
1. De multiples vulnérabilités ont été découvertes dans Microsoft Edge. Elles permettent à un attaquant de provoquer un contournement de la politique de sécurité et un problème de sécurité non spécifié par l'éditeur.
2. De multiples vulnérabilités ont été découvertes dans les produits Adobe. Elles permettent à un attaquant de provoquer une exécution de code arbitraire, un déni de service et un contournement de la politique de sécurité.
3. Une vulnérabilité a été découverte dans les produits Cisco. Un attaquant pourrait exploiter cette vulnérabilité en exécutant une série de commandes afin de contourner la vérification de la signature de l'image NX-OS et de charger des logiciels non vérifiés."""

    def format_description(self, raw_description: str, product_name: Optional[str] = None) -> str:
        """
        Format the raw description using Cohere's LLM to match the standard template.
        
        Args:
            raw_description (str): The raw description text extracted from the source
            product_name (str, optional): The name of the product affected
            
        Returns:
            str: Formatted description text
        """
        # Clean up the raw description
        cleaned_description = self._clean_description(raw_description)
        
        prompt = f"""
Tu es un expert en cybersécurité chargé de réécrire des descriptions de vulnérabilités pour qu'elles suivent un format standardisé.

FORMAT REQUIS (utilise EXACTEMENT cette structure):
- Commence par "Une vulnérabilité a été découverte dans [PRODUIT]." OU "De multiples vulnérabilités ont été découvertes dans [PRODUIT]."
- Continue par "Elle permet à un attaquant de..." OU "Elles permettent à un attaquant de..."

EXEMPLES À SUIVRE:
1. De multiples vulnérabilités ont été découvertes dans Microsoft Edge. Elles permettent à un attaquant de provoquer un contournement de la politique de sécurité et un problème de sécurité non spécifié par l'éditeur.
2. De multiples vulnérabilités ont été découvertes dans les produits Adobe. Elles permettent à un attaquant de provoquer une exécution de code arbitraire, un déni de service et un contournement de la politique de sécurité.
3. Une vulnérabilité zero-day a été découverte dans Google Chrome. Elle permet à un attaquant de provoquer des lectures et écritures arbitraires via une page HTML malveillante. Google Chrome indique que la vulnérabilité est activement exploitée.
4. Une vulnérabilité a été découverte dans les produits Cisco. Un attaquant pourrait exploiter cette vulnérabilité en exécutant une série de commandes afin de contourner la vérification de la signature de l'image NX-OS et de charger des logiciels non vérifiés.

DESCRIPTION BRUTE À REFORMATER:
{cleaned_description}

PRODUIT (si identifié): {product_name if product_name else "Non spécifié"}

INSTRUCTIONS:
- Génère UNIQUEMENT la description reformatée en français
- Respecte exactement la structure des exemples
- Identifie le produit concerné depuis la description brute
- Sois concis et précis
- Ne rajoute pas d'explications ou de texte supplémentaire
- Si plusieurs vulnérabilités sont mentionnées, utilise le pluriel
- N’oubliez pas de mentionner l’exploitation de la vulnérabilité s’il existe un exploit ou si la vulnérabilité est un zero-day, et utilisez l’expression : Une vulnérabilité zero-day.
"""

        try:
            # Updated model list with current Cohere models
            models_to_try = [
                'command-a-03-2025',        # Best performing model
                'command-r-plus-08-2024',   # Backup model 
                'command-r-08-2024',        # Third option
                'command-r'                 # Fallback option
            ]
            
            last_error = None
            
            for model_name in models_to_try:
                try:
                    print(f"Attempting to format description using model: {model_name}")
                    
                    response = requests.post(
                        'https://api.cohere.ai/v1/chat',
                json={
                            'model': model_name,
                            'message': prompt,
                            'max_tokens': 400,
                            'temperature': 0.3,
                            'stop_sequences': ['\n\n']
                },
                headers={'Authorization': f'Bearer {self.api_key}'},
                verify=False
            )

                    if response.status_code == 200:
                        data = response.json()
                        generated_description = (data.get('text') 
                                               or data.get('generation', {}).get('text', '')
                                               or '').strip()
                        
                        if generated_description:
                            print(f"Successfully formatted description using model: {model_name}")
                            return generated_description
                        else:
                            last_error = f"Empty generation from model {model_name}"
                            print(f"Warning: {last_error}, trying next model...")
                            continue
                            
                    elif response.status_code == 404:
                        last_error = f"Model {model_name} not found (404)"
                        print(f"Warning: {last_error}, trying next model...")
                        continue
                    else:
                        last_error = f"HTTP {response.status_code} for model {model_name}: {response.text}"
                        print(f"Warning: {last_error}, trying next model...")
                        continue
                        
                except requests.exceptions.RequestException as req_e:
                    last_error = f"Network error with model {model_name}: {str(req_e)}"
                    print(f"Warning: {last_error}, trying next model...")
                    continue
                except Exception as inner_e:
                    last_error = f"Unexpected error with model {model_name}: {str(inner_e)}"
                    print(f"Warning: {last_error}, trying next model...")
                    continue
            
            # If all models failed, return a fallback formatted description
            print(f"Warning: All models failed ({last_error}), using fallback formatting")
            return self._create_fallback_description(cleaned_description)

        except Exception as e:
            print(f"Error while calling Cohere API: {str(e)}")
            return self._create_fallback_description(raw_description)

    def _clean_description(self, raw_description: str) -> str:
        """Clean up the raw description text."""
        if not raw_description:
            return ""
        
        # Remove excessive whitespace and newlines
        cleaned = re.sub(r'\s+', ' ', raw_description.strip())
        
        # Remove HTML tags if present
        cleaned = re.sub(r'<[^>]+>', '', cleaned)
        
        # Remove common prefixes that might interfere
        prefixes_to_remove = [
            "Description:",
            "Summary:",
            "Overview:",
            "Résumé:",
            "Description :"
        ]
        
        for prefix in prefixes_to_remove:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        return cleaned

    def _clean_generated_response(self, response: str) -> str:
        """Clean up the generated response from the LLM."""
        if not response:
            return ""
        
        # Remove common unwanted prefixes/suffixes
        unwanted_phrases = [
            "Voici la description reformatée :",
            "Description reformatée :",
            "Bien sûr, voici",
            "Voici la",
            "Description:",
        ]
        
        cleaned = response.strip()
        for phrase in unwanted_phrases:
            cleaned = re.sub(rf'^{re.escape(phrase)}\s*', '', cleaned, flags=re.IGNORECASE)
        
        # Remove quotes if the entire response is wrapped in quotes
        if cleaned.startswith('"') and cleaned.endswith('"'):
            cleaned = cleaned[1:-1].strip()
        
        return cleaned

    def _validate_format(self, description: str) -> bool:
        """Validate if the generated description follows the expected format."""
        if not description:
            return False
        
        # Check if it starts with the expected pattern
        expected_starts = [
            "Une vulnérabilité a été découverte dans",
            "De multiples vulnérabilités ont été découvertes dans",
            "Une vulnérabilité a été identifiée dans",
            "De multiples vulnérabilités ont été identifiées dans"
        ]
        
        starts_correctly = any(description.startswith(start) for start in expected_starts)
        
        # Check if it contains impact statement
        contains_impact = any(phrase in description for phrase in [
            "permet à un attaquant",
            "pourrait exploiter",
            "permettent à un attaquant"
        ])
        
        return starts_correctly and contains_impact

    def _create_fallback_description(self, raw_description: str) -> str:
        """Create a fallback description when all models fail."""
        if not raw_description:
            return "Une vulnérabilité a été découverte. Les détails spécifiques ne sont pas disponibles."
        
        # Determine if single or multiple vulnerabilities
        is_multiple = any(term in raw_description.lower() for term in [
            'vulnérabilités', 'multiples', 'plusieurs', 'vulnerabilities', 'multiple'
        ])
        
        # Create basic template-compliant description
        if is_multiple:
            return "De multiples vulnérabilités ont été découvertes dans le produit concerné. Elles permettent à un attaquant de compromettre la sécurité du système."
        else:
            return "Une vulnérabilité a été découverte dans le produit concerné. Elle permet à un attaquant de compromettre la sécurité du système."

    def extract_product_name(self, title: str) -> Optional[str]:
        """
        Extract product name from the title using improved pattern matching.
        
        Args:
            title (str): The title of the security bulletin
            
        Returns:
            Optional[str]: Extracted product name or None
        """
        if not title:
            return None
        
        title_lower = title.lower()
        
        # More comprehensive patterns for product extraction
        patterns = [
            r'dans\s+([^-]+?)(?:\s*-|\s*$)',  # "dans [product] -" or "dans [product]"
            r'affectant\s+([^-]+?)(?:\s*-|\s*$)',  # "affectant [product]"
            r'de\s+([^-]+?)(?:\s*-|\s*$)',    # "de [product]"
            r'pour\s+([^-]+?)(?:\s*-|\s*$)',  # "pour [product]"
            r'concernant\s+([^-]+?)(?:\s*-|\s*$)',  # "concernant [product]"
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title_lower)
            if match:
                product = match.group(1).strip()
                # Clean up common words that might be captured
                product = re.sub(r'^(les?\s+|des?\s+)', '', product)
                if len(product) > 2:  # Ensure it's not too short
                    return product
        
        # If no pattern matches, try to extract known product names
        known_products = [
            'microsoft', 'adobe', 'cisco', 'oracle', 'google', 'apple',
            'windows', 'linux', 'chrome', 'firefox', 'edge', 'java',
            'wordpress', 'drupal', 'joomla', 'vmware', 'citrix'
        ]
        
        for product in known_products:
            if product in title_lower:
                return product.title()
        
        return None

    def process_advisory_description(self, raw_description: str) -> dict:
        """
        Process an advisory description and return formatted result with metadata.
        
        Args:
            raw_description (str): Raw description text
            
        Returns:
            dict: Processed description with metadata
        """
        formatted_description = self.format_description(raw_description=raw_description)
        
        return {
            "original_description": raw_description,
            "formatted_description": formatted_description,
            "processing_successful": self._validate_format(formatted_description)
        }