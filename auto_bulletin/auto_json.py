# Auto Bulletin Library Module
# 
# This module provides scraper classes for extracting vulnerability data
# from DGSSI and CERT-FR security bulletins.
#
# Usage:
#   from auto_bulletin.auto_json import DGSSIScraper, CERTFRScraper
#   from auto_bulletin.mitigation import MitigationHandler
#   from auto_bulletin.description import DescriptionHandler
#
#   # Initialize handlers
#   mitigation_handler = MitigationHandler(api_key)
#   description_handler = DescriptionHandler(api_key)  # Only for DGSSI
#
#   # Create scrapers
#   dgssi_scraper = DGSSIScraper(mitigation_handler, description_handler)
#   certfr_scraper = CERTFRScraper(mitigation_handler)
#
#   # Extract data
#   data = dgssi_scraper.scrape_bulletin(url)
#   data = certfr_scraper.parse_advisory(url)

from auto_bulletin.CERTFR import CERTFRScraper
from auto_bulletin.DGSSIS import DGSSIScraper

def calculate_delai_from_score(score_str):
    """
    Calculate Delai (response deadline) based on CVSS score.
    
    Args:
        score_str (str): CVSS score as string (e.g., "5.4", "6.0 - 9.8", or "-")
        
    Returns:
        str: Delai value (e.g., "30 Jr", "15 Jr", "5 Jr", "2 Jr")
        
    Score ranges:
        0-5: 30 Jr
        5-7: 15 Jr  
        7-9: 5 Jr
        9-10: 2 Jr
    """
    if not score_str or score_str == "-":
        return "30 Jr"  # Default for unknown scores
    
    try:
        # Handle score ranges (e.g., "6.0 - 9.8")
        if " - " in score_str:
            parts = score_str.split(" - ")
            # Take the maximum score from the range
            max_score = float(parts[1])
        else:
            # Single score value
            max_score = float(score_str)
        
        # Apply Delai logic based on score ranges
        if max_score >= 9.0:
            return "2 Jr"
        elif max_score >= 7.0:
            return "5 Jr"
        elif max_score >= 5.0:
            return "15 Jr"
        else:
            return "30 Jr"
            
    except (ValueError, IndexError):
        # Fallback for invalid score formats
        return "30 Jr"

# Export the scraper classes and utility function for use in other modules
__all__ = ['CERTFRScraper', 'DGSSIScraper', 'calculate_delai_from_score']