import requests
from bs4 import BeautifulSoup
import time
import re
import os
from datetime import datetime

# --- Lade externe Koordinaten-Datenbank ---
try:
    from koordinaten import CITY_COORDINATES
except ImportError:
    print("Fehler: 'koordinaten.py' nicht gefunden oder ungültig.")
    CITY_COORDINATES = {}

# URL der Blaulicht-Seite
URL = "https://www.presseportal.de/blaulicht/d/polizei"
# Schlagwörter
KEYWORDS = ["Einbruch", "Diebstahl"]
# Ausgabedatei
OUTPUT_FILE = "einbrueche_diebstaehle.txt"
# Header
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
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
    "Polizei", "Ermittler", "Täter", "Zeugen", "Hinweise", "Opfer", "Einbrecher", "Diebe", "Fahrzeug", "Wohnung",
    "Haus", "Geschäft", "Firma", "Unternehmen", "Ladendiebstahl", "PKW", "LKW", "Auto", "Werkstatt", "Garage",
    "Idstein", "Black", "Deckerstraße", "Diebe", "Täter"
}

# --- Global: Bereits vorhandene Einträge (zur Duplikatvermeidung) ---
existing_entries = set()

def load_existing_entries():
    """Lade alle bestehenden Einträge aus der TXT-Datei in ein Set (ohne Kommentare mit // am Anfang)"""
    global existing_entries
    existing_entries = set()
    if not os.path.exists(OUTPUT_FILE):
        return
    with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("//"):
                continue  # Überspringe Kommentare und Header
            if line:
                # Normalisiere: nur der eigentliche Eintrag (JSON + // Kommentar)
                existing_entries.add(line)

def is_duplicate(entry_line):
    """Prüft, ob der Eintrag bereits in der Datei existiert"""
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

# === GEÄNDERTE FUNKTION: Duplikatsschutz + Teilort-Suche ===
def save_to_file(location, keyword, date_str):
    if not date_str:
        return

    coords = []
    used_city = None

    if location:
        words = re.findall(r'[A-ZÄÖÜ][a-zäöüß]+', location)     # a-zäöüß   A-ZÄÖÜ
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

    # === DUPILKATPRÜFUNG ===
    if is_duplicate(line):
        print(f"Doppelt (übersprungen): {location or '—'} ({keyword}) am {date_str}")
        return

    # === Schreibe nur neue Einträge ===
    with open(OUTPUT_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    existing_entries.add(line)  # Merke für zukünftige Prüfungen
    print(f"{status}: {location or '—'} ({keyword}) am {date_str}")

def check_website():
    try:
        response = requests.get(URL, headers=HEADERS, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        articles = soup.find_all("article") or soup.find_all("div", class_=re.compile(r"teaser|news|item", re.I))
        for article in articles:
            text_block = article.get_text(separator=" ", strip=True).lower()
            if not any(kw.lower() in text_block for kw in KEYWORDS):
                continue
            location = extract_location_from_article(article)
            date_str = extract_date_from_text(article.get_text())
            if not date_str:
                continue
            keyword = next((kw for kw in KEYWORDS if kw.lower() in text_block), "Unbekannt")
            save_to_file(location, keyword, date_str)
    except Exception as e:
        print(f"Fehler: {e}")

# --- Hauptloop ---
if __name__ == "__main__":
    # Initialisiere Ausgabedatei mit Header (falls neu)
    if not os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(f"// Überwachung gestartet: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"// Schlagwörter: {', '.join(KEYWORDS)}\n")
    else:
        # Lade bestehende Einträge, um Duplikate zu vermeiden
        load_existing_entries()

    print("Überwachung läuft... (Strg+C zum Beenden)")
    print(f"→ {len(existing_entries)} Einträge bereits vorhanden.")
    
    while True:
        check_website()
        time.sleep(60)