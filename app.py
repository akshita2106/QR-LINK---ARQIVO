"""
app.py  —  QR Link Generator Web App
=====================================
Run:  python app.py
Open: http://localhost:5000
"""

import os
import io
import threading
from pathlib import Path
from datetime import datetime

from flask import (
    Flask,
    render_template,
    request,
    jsonify,
    send_file,
)
import pandas as pd

from processor import run_processing

app = Flask(__name__)
app.secret_key = os.urandom(24)

UPLOAD_FOLDER = Path("uploads")
OUTPUT_FOLDER = Path("output")
UPLOAD_FOLDER.mkdir(exist_ok=True)
OUTPUT_FOLDER.mkdir(exist_ok=True)

ALLOWED_EXTENSIONS = {".xlsx", ".xls"}

# In-memory store for the latest processed DataFrame (per session is complex;
# we keep one global for simplicity — fine for single-user tool)
_state = {
    "processed_df": None,
    "errors_df": None,
    "stats": None,
    "automation_log": [],
    "automation_running": False,
}


def allowed_file(filename):
    return Path(filename).suffix.lower() in ALLOWED_EXTENSIONS


# ────────────────────────────────────────────────────────────────────────────────
# ROUTES
# ────────────────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/process", methods=["POST"])
def process():
    """Receive uploaded Excel file(s), run processing, return JSON results."""
    if "files" not in request.files:
        return jsonify({"error": "No files uploaded"}), 400

    files = request.files.getlist("files")
    saved_paths = []

    for f in files:
        if f.filename == "":
            continue
        if not allowed_file(f.filename):
            return jsonify({"error": f"Invalid file type: {f.filename}"}), 400
        dest = UPLOAD_FOLDER / f.filename
        f.save(dest)
        saved_paths.append(dest)

    if not saved_paths:
        return jsonify({"error": "No valid files found"}), 400

    try:
        processed_df, errors_df, stats = run_processing(saved_paths)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    _state["processed_df"] = processed_df
    _state["errors_df"] = errors_df
    _state["stats"] = stats

    # Convert to JSON-safe format
    if not processed_df.empty:
        rows = processed_df.fillna("").to_dict(orient="records")
        columns = list(processed_df.columns)
    else:
        rows = []
        columns = []

    return jsonify({
        "stats": stats,
        "columns": columns,
        "rows": rows,
        "has_data": len(rows) > 0,
    })


@app.route("/download")
def download():
    """Download the processed Excel file."""
    df = _state.get("processed_df")
    if df is None:
        return jsonify({"error": "No processed data available"}), 404

    # Write to memory using openpyxl — no disk lock issues
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"processed_data_with_urls_{timestamp}.xlsx"
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )


@app.route("/automate", methods=["POST"])
def automate():
    """Trigger the HoverCode Selenium bot in a background thread."""
    if _state.get("automation_running"):
        return jsonify({"error": "Automation is already running"}), 400

    df = _state.get("processed_df")
    if df is None:
        return jsonify({"error": "Please process files first"}), 400

    # Write to a temporary file for the bot to consume
    temp_path = OUTPUT_FOLDER / "automation_target.xlsx"
    df.to_excel(temp_path, index=False)

    _state["automation_log"] = []
    _state["automation_running"] = True

    def run_bot_thread():
        log_list = _state["automation_log"]
        try:
            import importlib
            import hovercode_bot
            importlib.reload(hovercode_bot)
            hovercode_bot.run_bot(str(temp_path), log_list=log_list)
        except Exception as e:
            import traceback
            log_list.append(f"💥 ERROR: {e}")
            log_list.append(traceback.format_exc())
        finally:
            _state["automation_running"] = False

    t = threading.Thread(target=run_bot_thread, daemon=False)
    t.start()

    return jsonify({
        "message": "HoverCode automation started! A browser window will open — please log in, then the bot will take over."
    })


@app.route("/automate/status")
def automate_status():
    return jsonify({
        "running": _state["automation_running"],
        "log": _state["automation_log"],
    })


# ────────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("  QR Link Generator — Web App")
    print("  Open: http://localhost:5000")
    print("=" * 50 + "\n")
    app.run(debug=True, port=5000)
