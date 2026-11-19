"""
Zbieranie ofert z portali w jedną listę. Nie zna szczegółów żadnego portalu: każdy ma własny
skrypt (otodom.py, nieruchomosci_online.py) z tym samym zestawem funkcji:

    NAME                      nazwa portalu pokazywana na stronie
    matches(url)              czy adres wyszukiwania należy do tego portalu
    search(url, label)        ({id: oferta}, błąd albo None): oferty ze wszystkich stron wyników
    card(oferta)              współrzędne, rok budowy i parametry z karty oferty albo None
    CARD_REQUEST              czy card() wysyła zapytanie (OLX bierze dane ze strony wyników: False)

Oferta ze strony wyników ma w każdym portalu te same pola:
    id, portal, link, title, type ("flat" albo "house"), price, rent, area, pricePerM2, rooms,
    floor, photo, advertiser, listed (RRRR-MM-DD albo ""), excerpt, deliveryYear.
Pola, których portal nie podaje, są puste (None albo "").

Tu też są dwa pliki wspólne dla portali: stan.json (karty ofert, żeby nie pobierać ich
ponownie) i wykluczenia.json (obszary narysowane na mapie przez mapa.py).
"""

import json
import sys
from datetime import date
from pathlib import Path

import nieruchomosci_online
import olx
import otodom
import siec

HERE = Path(__file__).resolve().parent
CACHE_FILE = HERE / "stan.json"
ZONES_FILE = HERE / "wykluczenia.json"
ADS_FILE = HERE / "ogloszenia.json"
SOURCES = [otodom, nieruchomosci_online, olx]
MAX_EMPTY_CARDS = 10  # tyle kart z rzędu bez danych i uznajemy, że portal blokuje zapytania


def source_for(url):
    for source in SOURCES:
        if source.matches(url):
            return source
    names = ", ".join(f"{source.NAME} ({source.HOST})" for source in SOURCES)
    sys.exit(f"Nieznany portal w adresie wyszukiwania: {url}\nObsługiwane portale: {names}.")


def search_entries(config):
    """Wyszukiwania z config.toml jako {nazwa: adres}. Zalecany zapis to tabela [wyszukiwania] z parami
    nazwa = "adres"; działa też lista adresów (nazwy to wtedy numery 1, 2, ...) i starsze klucze
    otodom_urls oraz otodom_url."""
    entries = config.get("wyszukiwania") or config.get("otodom_urls") or config.get("otodom_url")
    if isinstance(entries, str):
        entries = [entries]
    if isinstance(entries, list):
        entries = {str(n): url for n, url in enumerate(entries, start=1)}
    if (not isinstance(entries, dict) or not entries
            or not all(isinstance(url, str) and url.strip() for url in entries.values())):
        sys.exit('Wpisz w config.toml wyszukiwania jako tabelę: [wyszukiwania] z liniami nazwa = "https://www.otodom.pl/...".')
    return {str(name): url.strip() for name, url in entries.items()}


def load_ads():
    """Oferty zapisane przy poprzednich pobraniach: {nazwa wyszukiwania: {"url", "date", "ads"}}."""
    try:
        return json.loads(ADS_FILE.read_text(encoding="utf-8")) if ADS_FILE.exists() else {}
    except ValueError:
        return {}


def save_ads(stored):
    # opis ofert jest długi, a strona pokazuje tylko jego początek
    slim = {name: {**entry, "ads": {ad_id: {**ad, "excerpt": (ad.get("excerpt") or "")[:400]}
                                    for ad_id, ad in entry["ads"].items()}}
            for name, entry in stored.items()}
    ADS_FILE.write_text(json.dumps(slim, ensure_ascii=False), encoding="utf-8")


def collect(entries, selected=()):
    """Oferty z wyszukiwań jako ({id: oferta}, problemy, uwagi).

    selected: nazwy wyszukiwań do pobrania teraz (puste: wszystkie). Pozostałe są brane z poprzedniego
    pobrania (ogloszenia.json), więc ranking zawiera wszystko, a odświeża się tylko to, co wybrane.
    Problem to wyszukiwanie, z którego pobrano tylko część stron (reszty nie czekamy, a brakujące oferty
    zostają z poprzedniego pobrania). Uwaga to informacja, np. że dane pochodzą sprzed kilku dni."""
    unknown = [name for name in selected if name not in entries]
    if unknown:
        sys.exit(f"Nieznane wyszukiwanie: {', '.join(unknown)}. W config.toml są: {', '.join(entries)}.")
    stored, ads, problems, notes = load_ads(), {}, [], []
    result = {}
    for name, url in entries.items():
        old = stored.get(name) if stored.get(name, {}).get("url") == url else None  # zmieniony adres: dane nieaktualne
        if selected and name not in selected:
            if old:
                result[name] = old
                ads.update(old["ads"])
                notes.append(f"{name}: oferty z pobrania {old['date']}, nie odświeżano")
            else:
                notes.append(f"{name}: brak zapisanych ofert, uruchom python dojazdy.py {name}")
            continue
        found, error = source_for(url).search(url, f"{name}: ")
        if error:
            problems.append(error)
            print(f"\nUwaga: {error}")
            found = {**(old["ads"] if old else {}), **found}  # niepełne pobranie nie kasuje poprzedniego
        fresh = not error or (old is None) or len(found) > len(old["ads"])
        result[name] = {"url": url, "date": date.today().isoformat() if fresh else old["date"], "ads": found}
        ads.update(found)
    save_ads(result)
    return ads, problems, notes


def load_zones():
    """Obszary wykluczone na mapie: lista wieloboków [[lat, lng], ...]. Brak pliku: brak obszarów."""
    if not ZONES_FILE.exists():
        return []
    try:
        zones = json.loads(ZONES_FILE.read_text(encoding="utf-8"))["obszary"]
        return [[(float(lat), float(lng)) for lat, lng in ring] for ring in zones if len(ring) >= 3]
    except (ValueError, KeyError, TypeError):
        sys.exit(f"Nie umiem odczytać {ZONES_FILE.name}. Napraw plik albo usuń go i narysuj obszary od nowa.")


def in_zone(lat, lng, zones):
    """Czy punkt leży w którymś z obszarów (reguła parzystości, działa też dla nieregularnych pętli)."""
    for ring in zones:
        inside = False
        for (lat1, lng1), (lat2, lng2) in zip(ring, ring[1:] + ring[:1]):
            if (lat1 > lat) != (lat2 > lat) and lng < (lng2 - lng1) * (lat - lat1) / (lat2 - lat1) + lng1:
                inside = not inside
        if inside:
            return True
    return False


def load_cache():
    return json.loads(CACHE_FILE.read_text(encoding="utf-8")) if CACHE_FILE.exists() else {}


def skip_reason(ad, year, max_year):
    """Powód pominięcia oferty jeszcze przed liczeniem dojazdów albo None."""
    if not ad["price"]:
        return "bez ceny"
    if max_year and year and year > max_year:
        return f"rok budowy po {max_year}"
    return None


def stale_details(ad, details):
    """Czy zapisana karta oferty jest niepełna albo ze starszej wersji skryptu i trzeba ją pobrać jeszcze raz.
    Pusta (details = None) jest też niepełna: oferta wypadła z obszaru wykluczonego albo karty nie było."""
    details = details or {}
    # "plans": krótka wersja, która oddzielała rzuty od zdjęć; mają je też zdjęcia, więc pobieramy od nowa
    return "photos" not in details or "plans" in details or source_for(ad["link"]).stale(details)


def fetch_details(ad_ids, ads, cache, zones=()):
    """Pobiera karty ofert i zapisuje w cache współrzędne i rok budowy. Współrzędnych nie ma w wynikach
    wyszukiwania, więc karta jest potrzebna, żeby sprawdzić obszary wykluczone. Dla ofert z takiego obszaru
    zapisuje tylko lokalizację, bez zdjęć i parametrów. Oferty z portalu, który przestał odpowiadać,
    są pomijane (nie czekamy na nie); brakujące karty uzupełni kolejne uruchomienie."""
    if not ad_ids:
        return
    requests_needed = sum(source_for(ads[ad_id]["link"]).CARD_REQUEST for ad_id in ad_ids)
    print(f"Pobieram karty {len(ad_ids)} ofert"
          + (f" (ok. {max(1, round(requests_needed * 2.5 / 60))} min)" if requests_needed else "") + "...")
    empty_in_a_row = {}
    try:
        for n, ad_id in enumerate(ad_ids, start=1):
            ad = ads[ad_id]
            source = source_for(ad["link"])
            if source.CARD_REQUEST and siec.blocked(ad["link"]):
                continue
            details = source.card(ad)
            if details:
                if in_zone(details["lat"], details["lng"], zones):
                    del details["details"]
                cache[ad_id] = details
                empty_in_a_row[ad["portal"]] = 0
            elif source.CARD_REQUEST:  # portal bez danych w odpowiedziach: wygląda na blokadę
                empty_in_a_row[ad["portal"]] = empty_in_a_row.get(ad["portal"], 0) + 1
                if empty_in_a_row[ad["portal"]] >= MAX_EMPTY_CARDS:
                    siec.block(ad["link"], f"{MAX_EMPTY_CARDS} ogłoszeń z rzędu bez danych")
            print(f"  {n}/{len(ad_ids)}", end="\r")
            if source.CARD_REQUEST:
                siec.pause()
    finally:  # postęp zostaje zapisany także po przerwaniu (Ctrl+C)
        CACHE_FILE.write_text(json.dumps(cache), encoding="utf-8")
