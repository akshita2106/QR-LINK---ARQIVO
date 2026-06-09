<<<<<<< HEAD
# QR-LINK — ARQIVO

Automated QR code generation and management tool for [HoverCode](https://hovercode.com), integrated with [Arqivo](https://www.arqivo.com) verification links.

Upload product Excel sheets → auto-generate unique verification URLs → push dynamic QR codes to HoverCode with proper display names — all from a clean web dashboard.

---

## Features

- **Excel Processing** — Upload raw product data Excel files; the tool cleans, deduplicates, and generates unique Arqivo verification URLs for each product × quantity combination.
- **Web Dashboard** — Flask-based UI to upload files, preview processed data, download results, and trigger QR automation.
- **HoverCode Automation** — Selenium-powered bot that logs into HoverCode, generates dynamic QR codes for each URL, and sets display names automatically.
- **Smart Resume** — If the process is interrupted, the bot detects existing QR codes on the HoverCode dashboard and resumes from where it left off — no duplicates.
- **Display Name Sync** — Automatically corrects mismatched display names on existing QR codes.

---

## Project Structure

```
qr/
├── app.py                 # Flask web server (upload, process, automate)
├── processor.py           # Excel processing logic (used by Flask app)
├── process_excel.py       # Standalone Excel processor (CLI)
├── hovercode_bot.py       # Selenium bot for HoverCode automation
├── inspect_hovercode.py   # Utility to inspect HoverCode dashboard
├── requirements.txt       # Python dependencies
├── templates/
│   └── index.html         # Web UI template
├── static/
│   └── app.js             # Frontend JavaScript
├── raw_files/             # Place raw Excel files here (for CLI mode)
├── output/                # Processed Excel output & automation state
├── uploads/               # Uploaded files via web UI
└── chrome_profile/        # Persistent Chrome session data
```

---

## Setup

### Prerequisites

- Python 3.8+
- Google Chrome browser

### Installation

```bash
# Clone the repository
git clone https://github.com/akshita2106/QR-LINK---ARQIVO.git
cd QR-LINK---ARQIVO

# Install dependencies
pip install -r requirements.txt
```

---

## Usage

### 1. Start the Web App

```bash
python app.py
```

Open **http://localhost:5000** in your browser.

### 2. Upload & Process

- Click **Upload** and select your raw product Excel file(s).
- The tool processes the data, generates verification URLs, and shows a preview table.
- Click **Download** to save the processed Excel file.

### 3. Generate QR Codes on HoverCode

- Click **Automate on HoverCode** to launch the Selenium bot.
- A Chrome window opens — **log in to your HoverCode account**.
- The bot takes over and:
  1. Scans the dashboard for existing QR codes
  2. Skips any already-created QR codes with correct display names
  3. Fixes mismatched display names on existing QR codes
  4. Creates new QR codes for remaining URLs
  5. Sets the correct display name on each new QR code

### 4. Resume After Interruption

If you close the browser or stop the process mid-way:
- Simply restart the app and click **Automate** again.
- The bot re-scans the HoverCode dashboard and picks up exactly where it left off.

---

## Excel Format

The input Excel file should contain product data with columns like:

| Column | Description |
|--------|-------------|
| `Product Name` | Name of the product |
| `Quantity` / `Size` | Product variant (e.g., 1 KG, 500 GMS) |
| `Packaging` | Units per pack (e.g., x 10, x 20) |

The processor generates a `URL` column with verification links in the format:
```
https://www.arqivo.com/verify/<product-slug>
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `flask` | Web server and UI |
| `pandas` | Excel data processing |
| `openpyxl` | Excel file read/write |
| `selenium` | Browser automation for HoverCode |
| `webdriver-manager` | Auto-download ChromeDriver |
| `python-dotenv` | Environment variable management |

---

## Tech Stack

- **Backend**: Python, Flask
- **Frontend**: HTML, CSS, JavaScript
- **Automation**: Selenium WebDriver
- **Data Processing**: Pandas

---

## License

This project is for internal use.
=======
# QR-LINK---ARQIVO
>>>>>>> 69a6dcc822c7a816d8e95ad6a588beeb0bb34350
