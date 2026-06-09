import pandas as pd
import re
from pathlib import Path
from datetime import datetime

# =========================================================
# CONFIGURATION
# =========================================================

BASE_URL = "https://www.arqivo.com/verify/"

# =========================================================
# PRODUCT DETECTION PATTERN
# =========================================================

PRODUCT_PATTERN = re.compile(
    r"""
    (?=.*\d)                          # must contain number
    (?=.*(?:kg|gms|gm|ml|ltr|litre)) # must contain unit
    """,
    re.IGNORECASE | re.VERBOSE
)

BATCH_PATTERN = re.compile(r"[A-Z0-9]{5,}", re.IGNORECASE)

# =========================================================
# HELPERS
# =========================================================

def format_date(value):
    try:
        if pd.isna(value):
            return ""
        if isinstance(value, datetime):
            return value.strftime("%d-%m-%Y")
        return pd.to_datetime(value).strftime("%d-%m-%Y")
    except:
        return str(value)


def slugify_product_name(name):
    if pd.isna(name):
        return ""
    name = str(name).strip().lower()
    name = re.sub(r"\s+", " ", name)
    name = re.sub(r"(\d+)\s*(kg|gms|gm|g|ml|ltr|litre|litres)", r"\1\2", name)
    name = re.sub(r"x\s*(\d+)", r"x-\1", name)
    name = name.replace(" ", "-")
    name = re.sub(r"[^a-z0-9\-]", "", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")


def is_product(text):
    if pd.isna(text):
        return False
    text = str(text).strip().lower()
    if len(text) < 5:
        return False
    return bool(PRODUCT_PATTERN.search(text))


def extract_product_name(full_product):
    words = full_product.split()
    return words[0] if words else ""


def find_nearby_batch(df, row, col):
    for r in range(max(0, row - 3), min(df.shape[0], row + 4)):
        for c in range(max(0, col - 3), min(df.shape[1], col + 4)):
            try:
                value = str(df.iloc[r, c]).strip()
                if BATCH_PATTERN.fullmatch(value):
                    return value
            except:
                pass
    return ""


def find_nearby_dates(df, row, col):
    dates = []
    for r in range(max(0, row - 5), min(df.shape[0], row + 6)):
        for c in range(max(0, col - 5), min(df.shape[1], col + 6)):
            try:
                value = df.iloc[r, c]
                if pd.isna(value):
                    continue
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    continue
                if isinstance(value, str):
                    val_str = value.strip()
                    if val_str.isdigit() or len(val_str) < 6:
                        continue
                    if not any(char in val_str for char in ['-', '/', '.']):
                        continue
                parsed = pd.to_datetime(value, errors="coerce")
                if not pd.isna(parsed):
                    if 2000 <= parsed.year <= 2100:
                        dates.append(parsed)
            except:
                pass
    dates = sorted(list(set(dates)))
    if len(dates) >= 2:
        return dates[0].strftime("%d-%m-%Y"), dates[1].strftime("%d-%m-%Y")
    elif len(dates) == 1:
        return dates[0].strftime("%d-%m-%Y"), ""
    return "", ""


# =========================================================
# PROCESS SINGLE SHEET
# =========================================================

def process_sheet(df, file_name, sheet_name):
    processed = []
    errors = []
    seen_products = set()

    for row in range(df.shape[0]):
        for col in range(df.shape[1]):
            try:
                value = df.iloc[row, col]
                if not is_product(value):
                    continue
                full_product = str(value).strip()
                if full_product in seen_products:
                    continue
                seen_products.add(full_product)

                product_name = extract_product_name(full_product)
                batch = find_nearby_batch(df, row, col)
                mfg, exp = find_nearby_dates(df, row, col)
                slug = slugify_product_name(full_product)
                url = BASE_URL + slug

                processed.append({
                    "File": file_name,
                    "Sheet": sheet_name,
                    "Product Name": product_name,
                    "Product Name x Quantity": full_product,
                    "Batch Number": batch,
                    "Manufacturing Date": mfg,
                    "Expiry Date": exp,
                    "URL": url,
                })
            except Exception as e:
                errors.append({
                    "File": file_name,
                    "Sheet": sheet_name,
                    "Row": row,
                    "Column": col,
                    "Error": str(e),
                })

    return processed, errors


# =========================================================
# PROCESS EXCEL FILE
# =========================================================

def process_excel_file(file_path):
    file_path = Path(file_path)
    all_processed = []
    all_errors = []

    try:
        excel_file = pd.ExcelFile(file_path)
    except Exception as e:
        return [], [{"File": file_path.name, "Error": str(e)}]

    for sheet_name in excel_file.sheet_names:
        try:
            df = pd.read_excel(file_path, sheet_name=sheet_name, header=None)
            df.dropna(how="all", inplace=True)
            df.dropna(axis=1, how="all", inplace=True)
            if df.empty:
                continue
            processed, errors = process_sheet(df, file_path.name, sheet_name)
            all_processed.extend(processed)
            all_errors.extend(errors)
        except Exception as e:
            all_errors.append({"File": file_path.name, "Sheet": sheet_name, "Error": str(e)})

    return all_processed, all_errors


# =========================================================
# MAIN FUNCTION — called by Flask or CLI
# =========================================================

def run_processing(file_paths):
    """
    Takes a list of file paths (str or Path).
    Returns (processed_df, errors_df, stats_dict).
    """
    all_processed = []
    all_errors = []

    for fp in file_paths:
        processed, errors = process_excel_file(fp)
        all_processed.extend(processed)
        all_errors.extend(errors)

    processed_df = pd.DataFrame(all_processed)
    errors_df = pd.DataFrame(all_errors)

    if not processed_df.empty:
        processed_df.drop_duplicates(subset=["Product Name x Quantity"], inplace=True)
        processed_df.reset_index(drop=True, inplace=True)

    stats = {
        "files_processed": len(file_paths),
        "products_extracted": len(processed_df),
        "errors_logged": len(errors_df),
    }

    return processed_df, errors_df, stats
