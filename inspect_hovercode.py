"""
inspect_hovercode.py
====================
Run this script, log into HoverCode in the browser,
navigate to a QR code EDIT page, then wait — it will
print all inputs and buttons after 60 seconds.
"""
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager
import time
import sys

options = Options()
options.add_argument("--start-maximized")
options.add_experimental_option("excludeSwitches", ["enable-automation"])

service = Service(ChromeDriverManager().install())
driver = webdriver.Chrome(service=service, options=options)

driver.get("https://hovercode.com/dashboard/")
print("Chrome opened. Please:")
print("  1. Log in to HoverCode")
print("  2. Navigate to a QR code edit page (click Edit on any QR)")
print("  3. Wait - inspection will happen in 60 seconds")
sys.stdout.flush()

time.sleep(60)

print("\nCurrent URL:", driver.current_url)
print("\n--- INPUTS ---")
for inp in driver.find_elements(By.TAG_NAME, "input"):
    t = inp.get_attribute("type") or ""
    n = inp.get_attribute("name") or ""
    i = inp.get_attribute("id") or ""
    p = inp.get_attribute("placeholder") or ""
    cls = inp.get_attribute("class") or ""
    print(f"  type={t!r} name={n!r} id={i!r} placeholder={p!r}")

print("\n--- BUTTONS ---")
for btn in driver.find_elements(By.TAG_NAME, "button"):
    txt = btn.text.strip()
    typ = btn.get_attribute("type") or ""
    cls = btn.get_attribute("class") or ""
    print(f"  text={txt!r} type={typ!r}")

print("\n--- LABELS ---")
for lbl in driver.find_elements(By.TAG_NAME, "label"):
    txt = lbl.text.strip()
    frm = lbl.get_attribute("for") or ""
    if txt:
        print(f"  text={txt!r} for={frm!r}")

print("\n--- PAGE SOURCE (first 3000 chars) ---")
print(driver.page_source[:3000])

driver.quit()
print("\nDone.")
