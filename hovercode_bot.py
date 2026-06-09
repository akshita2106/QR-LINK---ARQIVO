"""
hovercode_bot.py — HoverCode QR automation

Flow:
  1. Go to workspace dashboard
  2. Type URL in input
  3. Find + click the Generate QR code button (using form submit fallback)
  4. Wait for redirect to edit page
  5. Fill Display name (product name WITHOUT quantity suffix)
  6. Click Save changes
  7. Repeat for every URL — handles Leave-page dialogs between iterations
"""

import re
import sys
import time
import pandas as pd
import json
import hashlib
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager

WAIT_TIMEOUT  = 20
LOGIN_TIMEOUT = 180


# ─────────────────────────────────────────────────────────────────────────────
# PRODUCT NAME — strip trailing "x <number>" e.g. "Amecco 1 KG x 10" -> "Amecco 1 KG"
# ─────────────────────────────────────────────────────────────────────────────

def clean_product_name(name):
    name = str(name).strip()
    name = re.sub(r'\s+x[\s\-]+\d+\s*$', '', name, flags=re.IGNORECASE).strip()
    return name


# ─────────────────────────────────────────────────────────────────────────────
# LOGGING
# ─────────────────────────────────────────────────────────────────────────────

def log(msg, log_list=None):
    safe = str(msg).encode("ascii", errors="replace").decode("ascii")
    try:
        print(safe, flush=True)
    except Exception:
        pass
    if log_list is not None:
        log_list.append(str(msg))


# ─────────────────────────────────────────────────────────────────────────────
# DRIVER
# ─────────────────────────────────────────────────────────────────────────────

def setup_driver(log_list=None):
    log("[BOT] Starting Chrome...", log_list)
    opts = Options()
    opts.add_argument("--start-maximized")
    opts.add_argument("--disable-notifications")
    opts.add_argument("--disable-blink-features=AutomationControlled")
    opts.add_experimental_option("excludeSwitches", ["enable-automation"])
    opts.add_experimental_option("useAutomationExtension", False)
    
    try:
        svc = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=svc, options=opts)
        log("[BOT] Chrome opened successfully", log_list)
        return driver
    except Exception as e:
        log("[BOT] ERROR: Failed to start Chrome. If another Chrome window opened by the bot is still running, please close it first.", log_list)
        raise e


# ─────────────────────────────────────────────────────────────────────────────
# SAFE GET (handles Leave Page alerts)
# ─────────────────────────────────────────────────────────────────────────────

def safe_get(driver, url, log_list=None):
    """Safely navigate to a URL by disabling beforeunload prompts and handling active alerts."""
    try:
        driver.execute_script("window.onbeforeunload = null;")
    except Exception:
        pass
    
    try:
        driver.get(url)
    except Exception as e:
        # Check if an alert/confirm dialog is blocking the navigation
        try:
            alert = driver.switch_to.alert
            log(f"[BOT] Alert/dialog detected: '{alert.text}'. Accepting to proceed with navigation...", log_list)
            alert.accept()
            time.sleep(1)
        except Exception:
            raise e


# ─────────────────────────────────────────────────────────────────────────────
# SET INPUT VALUE (React-safe)
# ─────────────────────────────────────────────────────────────────────────────

def react_set_value(driver, element, value):
    """Set input value in a way React detects as a real user change."""
    driver.execute_script("""
        var nativeInputValueSetter = Object.getOwnPropertyDescriptor(
            window.HTMLInputElement.prototype, 'value').set;
        nativeInputValueSetter.call(arguments[0], arguments[1]);
        arguments[0].dispatchEvent(new Event('input',  {bubbles: true}));
        arguments[0].dispatchEvent(new Event('change', {bubbles: true}));
    """, element, value)


# ─────────────────────────────────────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────────────────────────────────────

def wait_for_login(driver, log_list=None):
    log("[BOT] Opening HoverCode...", log_list)
    safe_get(driver, "https://hovercode.com/dashboard/", log_list)
    time.sleep(2)

    cur = driver.current_url
    if not ("dashboard" in cur and "login" not in cur and "signup" not in cur):
        log("[BOT] Please log in to HoverCode in the browser...", log_list)
        WebDriverWait(driver, LOGIN_TIMEOUT).until(
            lambda d: "dashboard" in d.current_url
                      and "login" not in d.current_url
                      and "signup" not in d.current_url
        )

    time.sleep(1.5)
    workspace_url = driver.current_url
    log(f"[BOT] Logged in. Dashboard: {workspace_url}", log_list)
    return workspace_url

def get_dashboard_qrs(driver, workspace_url, log_list=None):
    """
    Scrapes the Hovercode dashboard (handling pagination & scrolling) and returns:
    (dashboard_qrs_dict, page_limit_hit_bool)
    """
    log("[BOT] Scanning Hovercode dashboard for existing QR codes...", log_list)
    safe_get(driver, workspace_url, log_list)
    
    # Wait for the dashboard page container or Generate button to load
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(text(), 'Generate') or contains(text(), 'Download')]"))
        )
    except Exception:
        pass
        
    time.sleep(3.5)  # Sleep to allow dynamic AJAX cards to render completely
    
    # Handle infinite scroll if any
    last_height = driver.execute_script("return document.body.scrollHeight")
    for _ in range(5):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1)
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            break
        last_height = new_height

    dashboard_qrs = {}
    page = 1
    page_limit_hit = False
    
    while page <= 10:  # limit pagination to 10 pages
        try:
            # Use reliable a[href*="/edit/"] selector to find all QR card edit links
            # Then walk up to the card container to extract destination URL and display name
            cards_info = driver.execute_script("""
                var results = [];
                var editLinks = document.querySelectorAll('a[href*="/edit/"]');

                for (var i = 0; i < editLinks.length; i++) {
                    var editEl = editLinks[i];
                    var editUrl = editEl.href;

                    // Walk up from the edit link to find the card container.
                    // The card container should contain the QR image, destination URL text, etc.
                    // Walk up parents until we find one that has enough height to be a card
                    // (not just a button wrapper).
                    var container = editEl.parentElement;
                    for (var depth = 0; depth < 10; depth++) {
                        if (!container || !container.parentElement) break;
                        // A card container typically has significant height and contains
                        // multiple child nodes. Stop when we find a reasonably large block.
                        var rect = container.getBoundingClientRect();
                        var text = container.innerText || "";
                        if (rect.height > 150 && text.length > 30) break;
                        container = container.parentElement;
                    }

                    var destUrl = "";
                    var displayName = "";

                    if (container) {
                        // Extract Display Name using h3.font-semibold element
                        var dnEl = container.querySelector("h3.font-semibold, h3[class*='font-semibold']");
                        if (dnEl) {
                            displayName = dnEl.innerText.trim();
                        }

                        // Extract Destination URL using h3.font-medium element
                        var urlEl = container.querySelector("h3.font-medium, h3[class*='font-medium']");
                        if (urlEl) {
                            destUrl = urlEl.innerText.trim();
                        }

                        // Fallback: look for arqivo/verify links in all anchor elements
                        if (!destUrl) {
                            var links = container.querySelectorAll("a");
                            for (var j = 0; j < links.length; j++) {
                                var href = links[j].href || "";
                                if (href.includes("arqivo.com") || href.includes("verify")) {
                                    destUrl = href;
                                    break;
                                }
                            }
                        }

                        // Second Fallback: regex search text content
                        if (!destUrl) {
                            var text = container.innerText || container.textContent || "";
                            var match = text.match(/https?:\/\/[^\\s"'<>\(\)]+/);
                            if (match) {
                                destUrl = match[0];
                            }
                        }
                    }

                    results.push({
                        displayName: displayName,
                        editUrl: editUrl,
                        destUrl: destUrl
                    });
                }
                return results;
            """)
            
            for info in cards_info:
                dest_url = info.get("destUrl", "").strip()
                display_name = info.get("displayName", "").strip()
                edit_url = info.get("editUrl", "").strip()
                
                if dest_url:
                    norm_url = dest_url.rstrip('/')
                    dashboard_qrs[norm_url] = {
                        "display_name": display_name,
                        "edit_url": edit_url
                    }
                elif display_name:
                    dashboard_qrs[display_name] = {
                        "display_name": display_name,
                        "edit_url": edit_url
                    }
        except Exception as e:
            log(f"[BOT] Error reading dashboard page {page}: {e}", log_list)
            
        # Try to find Next page button
        next_btn = None
        for by, sel in [
            (By.XPATH, "//button[contains(translate(text(), 'NEXT', 'next'), 'next')]"),
            (By.XPATH, "//a[contains(translate(text(), 'NEXT', 'next'), 'next')]"),
            (By.XPATH, "//button[contains(text(), '›') or contains(text(), '»')]"),
            (By.XPATH, "//a[contains(text(), '›') or contains(text(), '»')]"),
            (By.CSS_SELECTOR, "button[aria-label*='Next' i]"),
            (By.CSS_SELECTOR, "a[aria-label*='Next' i]"),
            (By.CSS_SELECTOR, ".pagination-next"),
        ]:
            try:
                el = driver.find_element(by, sel)
                if el.is_displayed() and el.is_enabled():
                    next_btn = el
                    break
            except Exception:
                continue
                
        if next_btn:
            if page == 10:
                page_limit_hit = True
                break
            log(f"[BOT] Found pagination. Loading next page (page {page+1})...", log_list)
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", next_btn)
                time.sleep(0.2)
                driver.execute_script("arguments[0].click();", next_btn)
                time.sleep(2.5)
                page += 1
            except Exception as e:
                log(f"[BOT] Failed to navigate to page {page+1}: {e}", log_list)
                break
        else:
            break

    log(f"[BOT] Found {len(dashboard_qrs)} existing QR configurations on the dashboard.", log_list)
    return dashboard_qrs, page_limit_hit

def update_existing_qr_display_name(driver, edit_url, product_name, workspace_url, log_list=None):
    """Directly navigates to the edit URL of a QR code to update its display name."""
    try:
        log(f"[BOT] Navigating directly to edit page: {edit_url}", log_list)
        safe_get(driver, edit_url, log_list)
        time.sleep(1.5)
        
        WebDriverWait(driver, 10).until(lambda d: "edit" in d.current_url)
        
        if not set_display_name(driver, product_name, log_list):
            return False
            
        log("[BOT] Returning to dashboard...", log_list)
        safe_get(driver, workspace_url, log_list)
        time.sleep(0.5)
        return True
    except Exception as e:
        log(f"[BOT] ERROR updating display name: {e}", log_list)
        return False

# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Type URL into the dashboard input
# ─────────────────────────────────────────────────────────────────────────────

def type_url(driver, workspace_url, url, log_list=None):
    safe_get(driver, workspace_url, log_list)
    time.sleep(0.3)  # short wait after loading workspace

    # Find the URL input
    url_input = None
    for by, sel in [
        (By.CSS_SELECTOR, "input[placeholder='https://example.com']"),
        (By.CSS_SELECTOR, "input[placeholder*='example.com']"),
        (By.CSS_SELECTOR, "input[placeholder*='https']"),
        (By.CSS_SELECTOR, "input[type='url']"),
        (By.XPATH,        "//input[contains(@placeholder,'example') or contains(@placeholder,'http')]"),
    ]:
        try:
            el = WebDriverWait(driver, 10).until(EC.element_to_be_clickable((by, sel)))
            if el.is_displayed():
                url_input = el
                break
        except Exception:
            continue

    if url_input is None:
        log("[BOT] ERROR - URL input not found", log_list)
        return False

    # Set value React-safely first, then also send_keys so the button activates
    react_set_value(driver, url_input, url)
    time.sleep(0.1)
    url_input.click()
    url_input.send_keys(Keys.END)          # move cursor to end
    url_input.send_keys(" ")              # trigger any validator
    url_input.send_keys(Keys.BACK_SPACE)  # remove the space
    time.sleep(0.2)

    log(f"[BOT] Typed: {url}", log_list)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Click Generate QR code
# ─────────────────────────────────────────────────────────────────────────────

def click_generate(driver, log_list=None):
    time.sleep(0.2)  # short wait for button to activate

    # Strategy 1: find the form containing the URL input, get its submit/last button
    gen_btn = driver.execute_script("""
        var input = document.querySelector(
            "input[placeholder='https://example.com'], input[type='url'], " +
            "input[placeholder*='example'], input[placeholder*='https']"
        );
        if (!input) return null;

        var el = input;
        for (var depth = 0; depth < 8; depth++) {
            el = el.parentElement;
            if (!el) break;
            var sub = el.querySelector('button[type="submit"]');
            if (sub && !sub.disabled) return sub;
            var btns = Array.from(el.querySelectorAll('button'));
            for (var b of btns) {
                var txt = b.innerText.trim().toLowerCase();
                if ((txt.includes('generate') || txt.includes('create qr')) && !b.disabled)
                    return b;
            }
        }
        return null;
    """)

    # Strategy 2: scan ALL buttons by innerText
    if gen_btn is None:
        gen_btn = driver.execute_script("""
            var btns = Array.from(document.querySelectorAll('button'));
            for (var b of btns) {
                var t = b.innerText.trim().toLowerCase();
                if (t === 'generate qr code' || t === 'create qr code') return b;
            }
            for (var b of btns) {
                var t = b.innerText.trim().toLowerCase();
                if (t && !b.disabled && (t.includes('generate qr') || t.includes('create qr'))) return b;
            }
            var sub = document.querySelector('button[type="submit"]:not([disabled])');
            if (sub) return sub;
            return null;
        """)

    if gen_btn is None:
        txts = driver.execute_script("""
            return Array.from(document.querySelectorAll('button'))
                .map(b => b.innerText.trim())
                .filter(t => t.length > 0);
        """)
        log(f"[BOT] ERROR - Generate button not found. Buttons: {txts}", log_list)
        return False

    log(f"[BOT] Clicking: '{gen_btn.text.strip() or gen_btn.get_attribute('innerText')}'", log_list)
    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", gen_btn)
    time.sleep(0.1)
    driver.execute_script("arguments[0].click();", gen_btn)
    return True


# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Set Display name and Save
# ─────────────────────────────────────────────────────────────────────────────

def set_display_name(driver, product_name, log_list=None):
    log(f"[BOT] Setting display name: '{product_name}'", log_list)

    # Find the display name input
    dn_input = driver.execute_script("""
        var i = document.querySelector('input[placeholder="(optional)"], input[name="name"], input[name="display_name"], input[id="name"], input[id="display_name"]');
        if (i) return i;

        var all = Array.from(document.querySelectorAll('*'));
        for (var el of all) {
            if (el.children.length === 0 &&
                el.textContent.trim().toLowerCase() === 'display name') {
                var parent = el.closest('div, section, form, li');
                if (parent) {
                    var inp = parent.querySelector('input[type="text"], input:not([type])');
                    if (inp) return inp;
                }
                var sib = el.nextElementSibling;
                while (sib) {
                    if (sib.tagName === 'INPUT') return sib;
                    var f = sib.querySelector('input');
                    if (f) return f;
                    sib = sib.nextElementSibling;
                }
            }
        }

        var inputs = Array.from(document.querySelectorAll('input'));
        var visible = inputs.filter(function(i) {
            var t = i.type || 'text';
            return t !== 'hidden' && t !== 'checkbox' && t !== 'radio'
                && i.getBoundingClientRect().height > 0;
        });
        return visible.length ? visible[visible.length - 1] : null;
    """)

    if dn_input is None:
        log("[BOT] WARNING - Display name input not found", log_list)
        return False

    ph = driver.execute_script("return arguments[0].placeholder || '';", dn_input)
    log(f"[BOT] Found input (placeholder={ph!r})", log_list)

    # Set value using React-safe method
    react_set_value(driver, dn_input, product_name)
    time.sleep(0.05)

    # Also send_keys as backup
    dn_input.click()
    dn_input.send_keys(Keys.CONTROL + "a")
    dn_input.send_keys(product_name)
    time.sleep(0.05)

    log(f"[BOT] Display name set", log_list)

    # Click the LAST Save changes button (QR management section)
    saved = driver.execute_script("""
        var btns = Array.from(document.querySelectorAll('button'));
        var saveBtns = btns.filter(b =>
            b.innerText.trim().toLowerCase().includes('save') && !b.disabled
        );
        if (saveBtns.length > 0) {
            var btn = saveBtns[saveBtns.length - 1];
            btn.click();
            return btn.innerText.trim();
        }
        return null;
    """)

    if saved:
        log(f"[BOT] Clicked '{saved}' - saving changes...", log_list)
        time.sleep(2.5)  # Wait for save request to complete
        return True
    else:
        log("[BOT] WARNING - Save button not found", log_list)
        return False


# ─────────────────────────────────────────────────────────────────────────────
# CREATE ONE QR
# ─────────────────────────────────────────────────────────────────────────────

def create_qr(driver, workspace_url, url, product_name, index, total, log_list=None):
    log(f"\n[{index}/{total}] {product_name}", log_list)
    log(f"         {url}", log_list)

    try:
        # Navigate and enter URL
        if not type_url(driver, workspace_url, url, log_list):
            return False

        # After type_url loads the dashboard, capture ALL existing edit hrefs
        # so we can identify the NEW one after generation.
        time.sleep(0.5)  # let dashboard render
        edit_hrefs_before = set(driver.execute_script("""
            return Array.from(document.querySelectorAll('a[href*="/edit/"]'))
                       .map(a => a.href);
        """))
        log(f"[BOT] Edit links before generation: {len(edit_hrefs_before)}", log_list)

        # Click Generate
        if not click_generate(driver, log_list):
            return False
        
        # Wait for either automatic redirection to edit page or a NEW edit link
        log("[BOT] Waiting for new QR code edit page or dashboard update...", log_list)
        redirected = False
        new_edit_href = None
        for _ in range(50):  # max 10 seconds wait (50 * 0.2s)
            curr_url = driver.current_url
            if "/edit/" in curr_url:
                redirected = True
                break
            # Check for new edit links that weren't present before
            edit_hrefs_now = driver.execute_script("""
                return Array.from(document.querySelectorAll('a[href*="/edit/"]'))
                           .map(a => a.href);
            """)
            new_hrefs = [h for h in edit_hrefs_now if h not in edit_hrefs_before]
            if new_hrefs:
                new_edit_href = new_hrefs[0]
                break
            time.sleep(0.2)

        if redirected:
            log(f"[BOT] Automatically redirected to edit page: {driver.current_url}", log_list)
        else:
            if new_edit_href:
                log(f"[BOT] Found new edit link: {new_edit_href}", log_list)
                # Navigate directly to the new edit URL (avoids clicking wrong card)
                safe_get(driver, new_edit_href, log_list)
            else:
                log("[BOT] WARNING - No new edit link detected. Trying first link...", log_list)
                edit_btn = driver.execute_script("""
                    return document.querySelector('a[href*="/edit/"]');
                """)
                if not edit_btn:
                    log("[BOT] ERROR - No edit button found on dashboard.", log_list)
                    return False
                driver.execute_script("arguments[0].click();", edit_btn)

            # Wait for edit page to load
            WebDriverWait(driver, 15).until(lambda d: "edit" in d.current_url)
            log(f"[BOT] On edit page: {driver.current_url}", log_list)

        # Set display name
        set_display_name(driver, product_name, log_list)

        # Land back to the dashboard immediately
        log("[BOT] Returning to dashboard...", log_list)
        safe_get(driver, workspace_url, log_list)
        time.sleep(0.5)

        log(f"[BOT] DONE [{index}/{total}]", log_list)
        return True
    except Exception as e:
        log(f"[BOT] ERROR [{index}]: {e}", log_list)
        try:
            safe_get(driver, workspace_url, log_list)
            time.sleep(0.5)
        except Exception:
            pass
        return False


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def run_bot(excel_path, log_list=None):
    excel_path = Path(excel_path)
    if not excel_path.exists():
        log(f"[BOT] ERROR - File not found: {excel_path}", log_list)
        raise FileNotFoundError(str(excel_path))

    df = pd.read_excel(excel_path)
    if "URL" not in df.columns:
        log("[BOT] ERROR - No URL column", log_list)
        raise ValueError("No URL column")

    df = df[df["URL"].notna() & (df["URL"].str.strip() != "")]
    total = len(df)
    if total == 0:
        log("[BOT] ERROR - No URLs found", log_list)
        raise ValueError("No URLs")

    log(f"[BOT] {total} QR codes to process", log_list)
    success = 0
    failed  = 0

    driver = setup_driver(log_list=log_list)
    try:
        workspace_url = wait_for_login(driver, log_list)
        dashboard_qrs, page_limit_hit = get_dashboard_qrs(driver, workspace_url, log_list)
        
        for i, (_, row) in enumerate(df.iterrows(), start=1):
            url = str(row["URL"]).strip()
            norm_url = url.rstrip('/')

            raw_name = str(row.get("Product Name x Quantity",
                           row.get("Product Name", f"Product {i}"))).strip()
            product_name = clean_product_name(raw_name)

            # Dashboard Skip/Update Check
            match_info = dashboard_qrs.get(norm_url) or dashboard_qrs.get(product_name)
            
            if match_info:
                existing_dn = match_info.get("display_name", "")
                edit_url = match_info.get("edit_url", "")
                
                if existing_dn == product_name:
                    log(f"[BOT] Dashboard Skip [{i}/{total}]: {product_name} already exists on HoverCode with correct display name.", log_list)
                    success += 1
                    continue
                else:
                    log(f"[BOT] Existing QR found for '{url}'. Correcting Display Name: '{existing_dn}' -> '{product_name}'", log_list)
                    ok = update_existing_qr_display_name(driver, edit_url, product_name, workspace_url, log_list)
                    if ok:
                        success += 1
                        dashboard_qrs[norm_url] = {
                            "display_name": product_name,
                            "edit_url": edit_url
                        }
                    else:
                        failed += 1
                    continue

            # Normal QR Generation
            ok = create_qr(driver, workspace_url, url, product_name, i, total, log_list)
            if ok:
                success += 1
                dashboard_qrs[norm_url] = {
                    "display_name": product_name,
                    "edit_url": ""
                }
            else:
                failed += 1
            
            time.sleep(0.5)

        log(f"\n[BOT] COMPLETE -- {success}/{total} created/configured successfully, {failed} failed", log_list)
        log("[BOT] Browser left open. Verify your QR codes then close it.", log_list)

    except Exception as e:
        log(f"[BOT] FATAL: {e}", log_list)
        raise


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python hovercode_bot.py <excel_path>")
        sys.exit(1)
    run_bot(sys.argv[1])
