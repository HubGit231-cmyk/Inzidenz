import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime
import sys

# Debug: Aktuelles Verzeichnis anzeigen
print("📁 Aktuelles Arbeitsverzeichnis:", os.getcwd())
print("📁 Dateien im aktuellen Verzeichnis:", os.listdir("."))

# Pfad zur Koordinaten-Datei (im gleichen Verzeichnis)
try:
    sys.path.append(os.path.dirname(__file__))
    from koordinaten import CITY_COORDINATES
    print("✅ Koordinaten erfolgreich geladen")
    print(f"📊 Geladene Städte: {len(CITY_COORDINATES)}")
except ImportError as e:
    print(f"❌ Fehler beim Koordinaten-Import: {e}")
    CITY_COORDINATES = {}

# URL der Blaulicht-Seite
URL = "https://www.presseportal.de/blaulicht/d/polizei"
KEYWORDS = ["Einbruch", "Diebstahl"]

# AUSGABE-DATEI IM DATA/ ORDNER (EINE EBENE HÖHER)
OUTPUT_FILE = "../data/einbrueche_diebstaehle.txt"

# Stelle sicher, dass der Ausgabeordner existiert
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
print(f"📁 Output file: {OUTPUT_FILE}")

# Header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# Datum-Regex
DATE_PATTERN = re.compile(
    r"\b(\d{1,2})\.(\d{1,2})\.(\d{4})"
    r"|\b(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})\b",
    re.IGNORECASE
)

# Ausschlusswörter
EXCLUDE_WORDS = {
    "Container", "Fahrschule", "Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag",
    "Polizei", "Ermittler", "Täter", "Zeugen", "Hinweise", "Opfer", "Einbrecher", "Diebe", "Fahrzeug", "Wohnung"
}

# --- Global: Bereits vorhandene Einträge ---
existing_entries = set()

def load_existing_entries():
    """Lade alle bestehenden Einträge aus der TXT-Datei"""
    global existing_entries
    existing_entries = set()
    if not os.path.exists(OUTPUT_FILE):
        print("📝 Output-Datei existiert noch nicht - wird neu erstellt")
        return
    try:
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("//"):
                    existing_entries.add(line)
        print(f"📊 {len(existing_entries)} vorhandene Einträge geladen")
    except Exception as e:
        print(f"❌ Fehler beim Laden vorhandener Einträge: {e}")

def is_duplicate(entry_line):
    return entry_line in existing_entries

def extract_date_from_text(text):
    match = DATE_PATTERN.search(text)
    if not match:
        return None
    if match.group(1): # DD.MM.YYYY
        day, month, year = match.group(1), match.group(2), match.group(3)
        return f"{year}-{month.zfill(2)}-{day.zfill(2)}"
    if match.group(4): # 1. November 2025
        day, month_name, year = match.group(4), match.group(5), match.group(6)
        months = {
            "Januar": "01", "Februar": "02", "März": "03", "April": "04", "Mai": "05", "Juni": "06",
            "Juli": "07", "August": "08", "September": "09", "Oktober": "10", "November": "11", "Dezember": "12"
        }
        month = months.get(month_name.capitalize(), "01")
        return f"{year}-{month}-{day.zfill(2)}"
    return None

def extract_location_from_article(article):
    full_text = article.get_text(separator=" ", strip=True)
   
    # 1. (ots) Ort
    ots_match = re.search(r"([A-ZÄÖÜ][a-zäöüß\-]+(?:\s+[A-ZÄÖÜ][a-zäöüß\-]+)*)\s*\(ots\)", full_text)
    if ots_match:
        loc = ots_match.group(1).strip()
        if loc not in EXCLUDE_WORDS:
            return loc
    
    # 2. "in [Ort]", "bei [Ort]" etc.
    for prefix in ["in", "bei", "aus", "von", "im", "am", "an"]:
        pattern = rf"{prefix}\s+([A-ZÄÖÜ][A-Za-zäöüß0-9\-\.,]+(?:\s+[A-ZÄÖÜ][A-Za-zäöüß0-9\-\.,]+)*)"
        matches = re.finditer(pattern, full_text, re.IGNORECASE)
        for m in matches:
            candidate = m.group(1).strip(".,;")
            if (len(candidate) >= 3 and
                candidate not in EXCLUDE_WORDS and
                not any(day in candidate.lower() for day in ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"]) and
                any(c.isupper() for c in candidate)):
                return candidate
    return None

def save_to_file(location, keyword, date_str):
    if not date_str:
        print(f"⚠️ Kein Datum für: {location} - Übersprungen")
        return

    coords = []
    used_city = None

    if location:
        words = re.findall(r'[A-ZÄÖÜ][a-zäöüß]+', location)
        for word in words:
            if word in CITY_COORDINATES:
                coords = CITY_COORDINATES[word][::-1]
                used_city = word
                break

    # Baue die Ausgabezeile
    if not location:
        line = f'//{{"coords": [], "date": "{date_str}"}} // Kein Ort gefunden, {keyword}'
        status = "Ort nicht erkannt"
    elif coords:
        line = f'{{"coords": {coords}, "date": "{date_str}"}}, // {location}, {keyword}'
        status = f"Koordinaten für '{used_city}'"
    else:
        line = f'//{{"coords": [], "date": "{date_str}"}} // {location}, {keyword}'
        status = "Koordinaten fehlen"

    # Duplikatprüfung
    if is_duplicate(line):
        print(f"⚠️ Doppelt (übersprungen): {location or '—'} ({keyword}) am {date_str}")
        return

    # Schreibe neue Einträge
    try:
        with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        existing_entries.add(line)
        print(f"✅ {status}: {location or '—'} ({keyword}) am {date_str}")
    except Exception as e:
        print(f"❌ Fehler beim Schreiben: {e}")

def check_website():
    try:
        print("🌐 Starte Web-Scraping...")
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        print("✅ Website erfolgreich geladen")
        
        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find_all("article") or soup.find_all("div", class_=re.compile(r"teaser|news|item", re.I))
        print(f"📰 Gefundene Artikel: {len(articles)}")
        
        found_count = 0
        for article in articles:
            text_block = article.get_text(separator=" ", strip=True).lower()
            if not any(kw.lower() in text_block for kw in KEYWORDS):
                continue
                
            location = extract_location_from_article(article)
            date_str = extract_date_from_text(article.get_text())
            
            if not date_str:
                continue
                
            keyword = next((kw for kw in KEYWORDS if kw.lower() in text_block), "Unbekannt")
            print(f"📍 Gefunden: {location} | {keyword} | {date_str}")
            save_to_file(location, keyword, date_str)
            found_count += 1
            
        print(f"📊 Gesamt gefunden: {found_count} relevante Einträge")
            
    except Exception as e:
        print(f"❌ Fehler beim Scraping: {e}")

# --- Hauptprogramm ---
if __name__ == "__main__":
    print("🚀 Starte Blaulicht-Monitor...")
    load_existing_entries()
    check_website()
    print("✅ Scraping abgeschlossen")
