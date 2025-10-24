# 🔒 Auto-Veille - Vulnerability Management System

A comprehensive web application for managing and tracking security vulnerabilities across multiple clients. The system automatically extracts vulnerability information from PDF security bulletins using AI and provides a user-friendly interface for tracking, filtering, and reporting.

## ✨ Features

### 📤 Smart PDF Upload & Extraction
- Upload PDF security bulletins
- AI-powered extraction of vulnerability data using Claude 3 Haiku
- Automatic client and team matching based on product names
- Review and confirm extracted data before saving to database
- NEW: When generating via Auto Bulletin, you can confirm to automatically insert the same data into the database and tracker (no re-upload needed)

### 🔍 Advanced Vulnerability Tracking
- Track vulnerabilities by client with filtering options
- Filter by date ranges (last week, month, 3 months, year, all time)
- Update vulnerability status (Open, Closed, WIP, Pending)
- Add and edit comments for each vulnerability
- Delete vulnerabilities with confirmation

### 📊 Export & Reporting
- Export vulnerability data to Excel format
- Filter exports by client and date range
- Comprehensive reports with all vulnerability details

### 🎨 Modern User Interface
- Responsive design with modern styling
- Modal dialogs for editing and confirmation
- Color-coded status indicators
- Intuitive navigation and user experience

## 🚀 Installation (on a VM, no Git required)

1) Copy the project folder to the VM
   - Windows: e.g., C:\Auto-Veille
   - Linux: e.g., /opt/auto-veille

2) Install Python 3.10+ and create a virtual environment
   - Windows:
     - py -3.10 -m venv .venv
     - .\.venv\Scripts\activate
   - Linux:
     - python3 -m venv .venv
     - source .venv/bin/activate

3) Install dependencies
   - python -m pip install --upgrade pip wheel setuptools
   - pip install -r requirements.txt

4) Set up environment variables
   - python setup_env.py
   - Edit the generated .env and set:
     - OPENROUTER_API_KEY=...
     - OPENROUTER_API_KEY_BACKUP=...
     - COHERE_API_KEY=...

5) Initialize the database
   - python setup_db.py

6) First run (development)
   - python app.py
   - Access: http://<VM-IP>:5000 (ensure the VM firewall allows the port)

## 🖥️ VM Deployment (Production)

- Windows (Waitress)
  - Run in foreground for a quick start:
    - .\.venv\Scripts\python -m waitress --listen=0.0.0.0:5000 app:app
  - Optional: Auto-start on boot via Task Scheduler (simplest)
    - Create a basic task that runs:
      - Program: C:\Path\to\project\.venv\Scripts\python.exe
      - Arguments: -m waitress --listen=0.0.0.0:5000 app:app
      - Start in: C:\Path\to\project

- Linux (Gunicorn + systemd)
  - Quick run:
    - .venv/bin/gunicorn -w 2 -b 0.0.0.0:8000 app:app
  - Example systemd unit (/etc/systemd/system/auto-veille.service):
    - [Unit]
      - Description=Auto-Veille
      - After=network.target
    - [Service]
      - WorkingDirectory=/opt/auto-veille
      - Environment="PATH=/opt/auto-veille/.venv/bin"
      - ExecStart=/opt/auto-veille/.venv/bin/gunicorn -w 2 -b 0.0.0.0:8000 app:app
      - Restart=always
    - [Install]
      - WantedBy=multi-user.target
    - Then:
      - sudo systemctl daemon-reload
      - sudo systemctl enable --now auto-veille

- Reverse proxy (optional)
  - You can place Nginx/Apache/IIS in front to terminate TLS and proxy to 127.0.0.1:5000/8000.

- Folder permissions
  - Ensure the service account can read/write:
    - uploads/
    - exports/
    - vuln_tracker.db (created by setup_db.py in the project root)

- Firewall
  - Open the chosen port (5000 or 8000) on the VM and any upstream firewalls.

## 📁 Project Structure

```
Auto-Veille/
├── app.py                 # Main Flask application
├── database/             # Database module
│   ├── db.py             # Database operations & KPI queries
│   └── setup_db.py       # Database initialization
├── upload/               # Upload processing pipeline
│   └── pdf_extractor.py  # PDF processing and AI extraction
├── export_excel/         # Excel export process
│   ├── auto_excel.py     # Excel export logic
│   ├── client_config.json# Client Excel mapping/config
│   └── client_excel_files/ # Client workbooks
├── auto_patch/           # Auto patch Excel merge
│   └── script.py         # Merge rows and return file
├── requirements.txt      # Python dependencies
├── templates/            # HTML templates
│   ├── home.html        # Home page
│   ├── upload.html      # Upload page
│   └── tracker.html     # Vulnerability tracker
├── uploads/             # Uploaded PDF files
├── exports/             # Exported Excel files
└── vuln_tracker.db      # SQLite database
```

## 🔧 Configuration

### Client Configuration (`client_config.json`)
Configure which clients are affected by which products and assign responsible teams:

```json
{
  "Fortinet": {
    "clients": ["CDGDev", "CDG", "Idarati"],
    "responsible_team": "Network"
  },
  "Google Chrome": {
    "clients": ["CDGDev", "CDG"],
    "responsible_team": "PDT"
  }
}
```

## 📋 Usage

### 1. Upload Security Bulletin
1. Navigate to the upload page
2. Select a PDF security bulletin
3. The system will extract vulnerability information using AI
4. Review the extracted data in the tracker
5. Confirm and save to database when ready

### 1bis. Generate Bulletin (Auto Bulletin) without re-upload
1. Go to Auto Bulletin
2. Enter the source URL and bulletin ID, extract and review data
3. Check “Ajouter automatiquement aux tables (base) et au tracker” to save directly
4. Generate files (PDF/DOCX). Data is saved to DB and tracker automatically

### 2. Track Vulnerabilities
1. Use the tracker page to view all vulnerabilities
2. Filter by client and date range
3. Edit status and comments using the edit modal
4. Delete vulnerabilities with confirmation

### 3. Export Reports
1. Use the export section to download Excel reports
2. Choose to export all data or filter by client
3. Reports include all vulnerability details and tracking information

## 🗄️ Database Schema

### Tables
- **vulnerabilities**: Stores extracted vulnerability information
- **client_vuln_tracking**: Tracks vulnerability status per client

### Key Fields
- `id_bulletin`: Unique bulletin identifier
- `cve_id`: CVE identifier
- `client`: Affected client
- `status`: Vulnerability status (Open/Closed/WIP/Pending)
- `comment`: User comments
- `Responsable_resolution`: Responsible team
- `Date_de_traitement`: Treatment date

## 🔌 API Integration

The system uses OpenRouter API with Claude 3 Haiku for AI-powered text extraction. The AI extracts structured data including:
- Title and description
- CVE identifiers
- CVSS scores
- Affected products
- Mitigation strategies
- References

## 🛠️ Technologies Used

- **Backend**: Flask (Python)
- **Database**: SQLite
- **AI**: Claude 3 Haiku via OpenRouter API
- **PDF Processing**: PyMuPDF
- **Data Export**: Pandas + OpenPyXL
- **Frontend**: HTML, CSS, JavaScript

## 🔒 Security Features

- Input validation and sanitization
- Secure file upload handling
- SQL injection prevention
- Confirmation dialogs for destructive actions

## 📈 Future Enhancements

- User authentication and role-based access
- Email notifications for new vulnerabilities
- Integration with vulnerability databases
- Advanced search and filtering
- Dashboard with vulnerability statistics
- API endpoints for external integrations

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions, please open an issue in the repository or contact the development team.