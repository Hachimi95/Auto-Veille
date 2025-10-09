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
        # Detect LibreOffice
        soffice = (
            shutil.which('soffice') or shutil.which('libreoffice') or shutil.which('lowriter')
            or '/usr/bin/soffice' if os.path.exists('/usr/bin/soffice') else None
        )
    else:
        soffice = None
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

# LibreOffice (Linux DOCX -> PDF)
SOFFICE_PATH={soffice or ''}
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
            print("ℹ️ wkhtmltopdf not detected. Install it on Linux:")
            print("   sudo apt-get update && sudo apt-get install -y wkhtmltopdf")
        if soffice:
            print(f"🔎 Detected LibreOffice at: {soffice}")
        else:
            print("ℹ️ LibreOffice not detected. Install it for DOCX->PDF:")
            print("   sudo apt-get update && sudo apt-get install -y libreoffice-core libreoffice-writer fonts-dejavu")

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
    chromium_path = None
    soffice_path = None
    for line in content.splitlines():
        if line.startswith('PDF_ENGINE='):
            pdf_engine = line.split('=', 1)[1].strip()
        elif line.startswith('WKHTMLTOPDF_PATH='):
            wkhtml_path = line.split('=', 1)[1].strip()
        elif line.startswith('CHROMIUM_PATH='):
            chromium_path = line.split('=', 1)[1].strip()
        elif line.startswith('SOFFICE_PATH='):
            soffice_path = line.split('=', 1)[1].strip()

    if (pdf_engine or '').lower() == 'wkhtmltopdf':
        detected = shutil.which('wkhtmltopdf')
        effective = wkhtml_path or detected
        if not effective:
            print("⚠️ PDF warning: PDF_ENGINE=wkhtmltopdf but wkhtmltopdf is not found.")
            print("   Install wkhtmltopdf or set WKHTMLTOPDF_PATH in .env")

    # LibreOffice auto-fix on Linux
    if platform.system().lower() == 'linux':
        detected_soffice = (
            soffice_path or shutil.which('soffice') or shutil.which('libreoffice') or shutil.which('lowriter')
            or ('/usr/bin/soffice' if os.path.exists('/usr/bin/soffice') else None)
        )
        if detected_soffice and not soffice_path:
            print(f"🔧 Setting SOFFICE_PATH to detected path: {detected_soffice}")
            backup = '.env.backup.autofix'
            try:
                if not os.path.exists(backup):
                    shutil.copyfile('.env', backup)
                lines = content.splitlines()
                has_key = any(l.startswith('SOFFICE_PATH=') for l in lines)
                if has_key:
                    lines = [l if not l.startswith('SOFFICE_PATH=') else f'SOFFICE_PATH={detected_soffice}' for l in lines]
                else:
                    lines.append(f'SOFFICE_PATH={detected_soffice}')
                with open('.env', 'w') as wf:
                    wf.write('\n'.join(lines) + '\n')
                print("✅ Updated .env with SOFFICE_PATH")
            except Exception as e:
                print(f"⚠️ Could not update .env automatically: {e}")
                print(f"   Please set SOFFICE_PATH={detected_soffice} manually.")

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

# ------------------ TROUBLESHOOTING COMMAND REFERENCE (VM) ------------------
# Copy / run selectively to diagnose a failing systemd service (auto-veille)
#
# 1. Service & unit basics
# sudo systemctl status auto-veille.service --no-pager
# sudo systemctl show -p ExecStart,WorkingDirectory,Environment auto-veille.service
# sudo systemctl cat auto-veille.service
#
# 2. Logs (recent + live)
# journalctl -u auto-veille.service -n 200 --no-pager
# journalctl -u auto-veille.service -f --no-pager
# (After fixing unit or code) sudo systemctl reset-failed auto-veille.service
#
# 3. Syntax / indentation errors (common)
# cd ~/DXC-AUTO_VEILLE/Auto-Veille
# grep -nP '\t' app.py || echo "No tabs"
# python3 -m py_compile app.py
# nl -ba app.py | sed -n '660,730p'    # inspect problematic region
#
# 4. Environment & virtualenv
# source .venv/bin/activate
# python -V
# which python
# pip check
# pip freeze | grep -E 'docx|gunicorn|flask'
#
# 5. Test WSGI import outside Gunicorn
# python - <<'PY'
# import sys; sys.path.insert(0,'.')
# import app
# print("WSGI object:", hasattr(app,'app'))
# PY
#
# 6. Foreground Gunicorn (bypasses systemd wrapper)
# source .venv/bin/activate
# gunicorn -b 127.0.0.1:8000 --log-level debug --access-logfile - --error-logfile - app:app
#
# 7. Port / process checks
# sudo ss -ltnp | grep ':8000' || echo "Nothing on 8000"
# pgrep -af gunicorn || echo "No gunicorn processes"
#
# 8. Nginx (after app is healthy)
# sudo systemctl status nginx --no-pager
# sudo nginx -t
# sudo tail -n 100 /var/log/nginx/error.log
#
# 9. LibreOffice / PDF tool chain
# which soffice || which libreoffice || which lowriter || echo "No soffice"
# grep -E '^SOFFICE_PATH=' .env || echo "SOFFICE_PATH not set"
#
# 10. Environment file validation
# python setup_env.py
#
# 11. Reload systemd after editing unit file
# sudo systemctl daemon-reload
# sudo systemctl restart auto-veille.service
#
# 12. Clean restart loop state
# sudo systemctl reset-failed auto-veille.service
#
# 13. One-shot deeper debug (captures env + run)
# bash -c 'set -x; cd ~/DXC-AUTO_VEILLE/Auto-Veille; source .venv/bin/activate; env | grep -E "FLASK|PDF|SOFFICE" ; python -m py_compile app.py && gunicorn -b 127.0.0.1:8000 app:app'
#
# 14. Verify health endpoint once running
# curl -I http://127.0.0.1:8000/_health
#
# 15. Common fix pattern (tabs -> spaces)
# sed -i "s/\t/    /g" app.py && python3 -m py_compile app.py && sudo systemctl restart auto-veille.service
#
# ---------------------------------------------------------------------------
