#!/usr/bin/env python3

# Test script to manually trigger mitigation generation and see the debug output

import sys
import os
sys.path.append('.')

def test_mitigation_generation():
    """Test mitigation generation to see debug output"""
    
    from auto_bulletin.mitigation import MitigationHandler
    import json
    
    # Set up the handler (you'll need your Cohere API key)
    api_key = "YOUR_COHERE_API_KEY"  # Replace with actual key
    handler = MitigationHandler(api_key)
    
    # Create a test advisory
    test_advisory = {
        "titre": "Vulnérabilité dans Google Chrome",
        "Produits affectés": [
            "Google Chrome version 139.x",
            "Google Chrome version 140.x"
        ]
    }
    
    print("=== Testing Mitigation Generation ===")
    print("Test advisory:")
    print(json.dumps(test_advisory, indent=2, ensure_ascii=False))
    
    print("\\n=== Calling process_advisory ===")
    result = handler.process_advisory(test_advisory)
    
    print("\\n=== Final Result ===")
    print(result)
    
    try:
        parsed_result = json.loads(result)
        print("\\n=== Parsed Result ===")
        print(json.dumps(parsed_result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"\\nError parsing result: {e}")

if __name__ == "__main__":
    test_mitigation_generation()