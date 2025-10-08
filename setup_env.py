#!/usr/bin/env python3
"""
Setup script for Auto-Veille environment variables.
This script helps users set up their .env file with required API keys.
"""

import os
import shutil
import platform

def create_env_file():
    """Create .env file with required environment variables"""
    is_linux = platform.system().lower() == 'linux'
    wkhtml = shutil.which('wkhtmltopdf') if is_linux else None
    chromium = None
    if is_linux:
        chromium = (
            shutil.which('chromium')
            or shutil.which('google-chrome')
            or shutil.which('chromium-browser')
        )
    pdf_engine = 'wkhtmltopdf' if wkhtml else 'weasyprint'

    env_content = f"""# OpenRouter API Configuration
# Get your API key from: https://openrouter.ai/keys
OPENROUTER_API_KEY=your_openrouter_api_key_here

# Cohere API Configuration (for auto_bulletin features)
# Get your API key from: https://dashboard.cohere.ai/api-keys
COHERE_API_KEY=your_cohere_api_key_here

# Flask Configuration
FLASK_ENV=development
FLASK_DEBUG=True

# PDF Generation Configuration
# PDF_ENGINE options: wkhtmltopdf | weasyprint | chromium
PDF_ENGINE={pdf_engine}
# If using wkhtmltopdf, set path to the binary (auto-detected on Linux if available)
WKHTMLTOPDF_PATH={wkhtml or ''}
# If using chromium-based PDF (Playwright/Puppeteer style), set path if needed
CHROMIUM_PATH={chromium or ''}
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
    # Linux PDF hints
    if is_linux:
        if wkhtml:
            print(f"🔎 Detected wkhtmltopdf at: {wkhtml}")
        else:
            print("ℹ️ wkhtmltopdf not detected. Install it on Linux, e.g.:")
            print("   Ubuntu/Debian: sudo apt-get update && sudo apt-get install -y wkhtmltopdf")
            print("   Or use PDF_ENGINE=weasyprint (pip install weasyprint + system deps)")

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
    # Extra PDF diagnostics (non-blocking)
    pdf_engine = None
    wkhtml_path = None
    for line in content.splitlines():
        if line.startswith('PDF_ENGINE='):
            pdf_engine = line.split('=', 1)[1].strip()
        elif line.startswith('WKHTMLTOPDF_PATH='):
            wkhtml_path = line.split('=', 1)[1].strip()

    if (pdf_engine or '').lower() == 'wkhtmltopdf':
        detected = shutil.which('wkhtmltopdf')
        # Also try common install locations (systemd PATH may be minimal)
        common_paths = ['/usr/bin/wkhtmltopdf', '/usr/local/bin/wkhtmltopdf', '/snap/bin/wkhtmltopdf']
        first_existing = next((p for p in [wkhtml_path, detected, *common_paths] if p and os.path.exists(p)), None)
        if not first_existing:
            print("⚠️ PDF warning: PDF_ENGINE=wkhtmltopdf but wkhtmltopdf is not found.")
            print("   Install wkhtmltopdf or set WKHTMLTOPDF_PATH in .env")
        else:
            # Auto-fix .env if WKHTMLTOPDF_PATH is missing or empty
            if not wkhtml_path:
                print(f"🔧 Setting WKHTMLTOPDF_PATH to detected path: {first_existing}")
                backup = '.env.backup.autofix'
                try:
                    if not os.path.exists(backup):
                        shutil.copyfile('.env', backup)
                    # Append or set variable
                    lines = content.splitlines()
                    has_key = any(l.startswith('WKHTMLTOPDF_PATH=') for l in lines)
                    if has_key:
                        lines = [l if not l.startswith('WKHTMLTOPDF_PATH=') else f'WKHTMLTOPDF_PATH={first_existing}' for l in lines]
                    else:
                        lines.append(f'WKHTMLTOPDF_PATH={first_existing}')
                    with open('.env', 'w') as wf:
                        wf.write('\n'.join(lines) + '\n')
                    print("✅ Updated .env with WKHTMLTOPDF_PATH")
                except Exception as e:
                    print(f"⚠️ Could not update .env automatically: {e}")
                    print(f"   Please set WKHTMLTOPDF_PATH={first_existing} manually.")
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
