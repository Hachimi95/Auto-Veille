#!/usr/bin/env python3
"""
Setup script for Auto-Veille environment variables.
This script helps users set up their .env file with required API keys.
"""

import os

def create_env_file():
    """Create .env file with required environment variables"""
    env_content = """# OpenRouter API Configuration
# Get your API key from: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Cohere API Configuration (for auto_bulletin features)
# Get your API key from: https://dashboard.cohere.ai/api-keys
COHERE_API_KEY=your_cohere_api_key_here

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True
"""
    
    env_file_path = '.env'
    
    if os.path.exists(env_file_path):
        print("⚠️ .env file already exists. Backing up to .env.backup")
        os.rename(env_file_path, '.env.backup')
    
    with open(env_file_path, 'w') as f:
        f.write(env_content)
    
    print("✅ Created .env file")
    print("📝 Please edit .env file and add your API keys:")
    print("   - OPENROUTER_API_KEY: Get from https://openrouter.ai/keys")
    print("   - COHERE_API_KEY: Get from https://dashboard.cohere.ai/api-keys")

def check_env_file():
    """Check if .env file exists and has required variables"""
    if not os.path.exists('.env'):
        print("❌ .env file not found")
        return False
    
    with open('.env', 'r') as f:
        content = f.read()
    
    required_vars = ['OPENROUTER_API_KEY', 'COHERE_API_KEY']
    missing_vars = []
    
    for var in required_vars:
        if f"{var}=your_" in content or f"{var}=" not in content:
            missing_vars.append(var)
    
    if missing_vars:
        print(f"❌ Missing or incomplete environment variables: {', '.join(missing_vars)}")
        return False
    
    print("✅ .env file is properly configured")
    return True

if __name__ == "__main__":
    print("🔧 Auto-Veille Environment Setup")
    print("=" * 40)
    
    if check_env_file():
        print("✅ Environment is ready!")
    else:
        print("🔧 Setting up environment...")
        create_env_file()
        print("\n📋 Next steps:")
        print("1. Edit .env file with your API keys")
        print("2. Run: python setup_db.py")
        print("3. Run: python app.py")
