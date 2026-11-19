"""
Źródło ofert: nieruchomosci-online.pl (używa go oferty.py, obok otodom.py).

Strona wyników (około 40 ofert, kolejne strony przez ?p=N) daje tytuł, cenę, metraż, pokoje
i piętro; karta oferty ma współrzędne (z informacją, czy przybliżone), rok budowy
i parametry w danych strukturalnych. Oferty mają kształt wspólny dla wszystkich portali
(opis w oferty.py), więc reszta skryptów nie wie, skąd oferta pochodzi.

Zdjęcia: pełna lista jest w danych strony (obiekt photos w skrypcie record), w kilku
rozmiarach; bierzemy duży (l). Zapytania idą przez siec.py (ponowienia, rezygnacja przy blokadzie).
"""

import html
import json
import re
from urllib.parse import urlsplit, urlunsplit

import siec

NAME = "Nieruchomości Online"
HOST = "nieruchomosci-online.pl"
CARD_REQUEST = True  # karta oferty to osobne zapytanie
ID_PREFIX = "no"  # żeby numer oferty nie zderzył się z numerami z Otodom
AMENITIES = {"Parking": "miejsce parkingowe", "Intercom": "domofon", "CCTV cameras": "monitoring",
             "Alarm system": "alarm", "Garden": "ogród", "Balcony": "balkon", "Garage": "garaż"}


def matches(url):
    host = urlsplit(url).hostname or ""
    return host == HOST or host.endswith("." + HOST)


def page_url(url, page):
    """Adres strony wyników: parametr p=N (pierwsza strona bez niego)."""
    parts = urlsplit(url)
    query = [q for q in parts.query.split("&") if q and not re.fullmatch(r"p=\d+", q)]
    if page > 1:
        query.append(f"p={page}")
    return urlunsplit(parts._replace(query="&".join(query)))


def text(fragment):
    """Tekst z fragmentu HTML: bez znaczników, ze zwykłymi spacjami."""
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).replace("\xa0", " ").split())


def first(pattern, source, flags=re.S):
    match = re.search(pattern, source, flags)
    return match.group(1) if match else None


def number(value):
    """Liczba z tekstu typu „4 500 zł” albo „34,07 m²”; None, gdy jej nie ma (np. „Zapytaj o cenę”)."""
    match = re.search(r"\d[\d ]*(?:,\d+)?", (value or "").replace("\xa0", " "))
    return float(match.group().replace(" ", "").replace(",", ".")) if match else None


def total_pages(page_html):
    return max([1, *(int(n) for n in re.findall(r"(?:\?|&|&amp;)p=(\d+)", page_html))])


def parse_tiles(page_html):
    """Oferty z jednej strony wyników w kształcie wspólnym dla portali."""
    ads = []
    for tile in re.split(r'(?=<div class="tile tile-tile)', page_html)[1:]:
        link = re.search(r'<a href="(https://[^"]+/(\d+)\.html)"[^>]*id="tertiary-name_\d+"[^>]*>(.*?)</a>', tile, re.S)
        if not link:
            continue
        url, ad_id, title = link.group(1), link.group(2), text(link.group(3))
        place = text(first(r'id="tertiary-province_\d+"[^>]*>(.*?)</p>', tile))
        price = number(text(first(r'id="primary-display_\d+"[^>]*>\s*<span>(.*?)</span>', tile)))
        area = number(text(first(r'id="area-display_\d+"[^>]*>(.*?)</span>', tile)))
        rooms = first(r"<span>Liczba pokoi:</span><strong>(\d+)</strong>", tile)
        slug = urlsplit(url).path.strip("/").split("/")[0]
        photo = first(r'<img[^>]+src="(https://i\.st-nieruchomosci-online\.pl/[^"]+)"', tile)
        ads.append({
            "id": ID_PREFIX + ad_id, "portal": NAME, "link": url,
            "title": f"{title}, {place}" if place else title,
            "type": "house" if slug.startswith("dom") else "flat",
            "price": int(price) if price else None, "rent": None,
            "area": area, "pricePerM2": None,
            "rooms": int(rooms) if rooms else None,
            "floor": text(first(r"<span>Piętro:</span><strong>([^<]*)</strong>", tile)),
            "photo": photo,
            "advertiser": "",  # strona wyników go nie podaje
            "listed": "",
            "excerpt": text(first(r'id="desc_\d+"[^>]*>(.*?)</p>', tile)),
            "deliveryYear": None,
            "market": first(r'data-market-type="(\w+)"', tile),  # tylko do karty oferty
        })
    return ads


def search(url, label=""):
    """Oferty ze wszystkich stron jednego wyszukiwania: ({id: oferta}, błąd albo None).
    Błąd oznacza, że pobrano tylko część stron; to, co jest, zostaje."""
    ads, page, pages = {}, 1, 1
    while page <= pages:
        response = siec.fetch(page_url(url, page))
        if response is None or not response.ok:
            reason = (siec.blocked(url) or f"portal nie odpowiada ({siec.last_error(url)})") if response is None \
                else f"HTTP {response.status_code}"
            return ads, f"{NAME} ({label}strona {page}): {reason}; pobrano {len(ads)} ofert"
        pages = max(pages, total_pages(response.text))
        tiles = parse_tiles(response.text)
        if not tiles or (page > 1 and all(ad["id"] in ads for ad in tiles)):
            if page == 1:
                return ads, f"{NAME} ({label}): nie rozpoznano ofert na stronie, sprawdź adres"
            break  # strona poza ostatnią zwraca w kółko te same oferty albo nic
        ads.update({ad["id"]: ad for ad in tiles})
        print(f"Wyniki: {label}strona {page}/{pages}, ofert: {len(ads)}")
        page += 1
        siec.pause()
    return ads, None


def structured(page_html):
    """Dane strukturalne oferty (JSON-LD z polem geo) albo None."""
    for block in re.findall(r'<script type="application/ld\+json">(.*?)</script>', page_html, re.S):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and isinstance(data.get("geo"), dict):
            return data
    return None


def map_point(page_html):
    """Punkt z obiektu mapy na stronie: (szerokość, długość, czy przybliżony) albo None."""
    raw = first(r"var map = (\{.*?\});", page_html)
    try:
        point = json.loads(raw)
        return float(point["latitude"]), float(point["longitude"]), bool(point.get("isInaccurateLocation"))
    except (TypeError, KeyError, ValueError):
        return None


def stale(details):
    """Czy zapisaną kartę trzeba pobrać jeszcze raz (starsza wersja skryptu miała tylko jedno zdjęcie)."""
    return "photosAll" not in details


def photo_urls(page_html):
    """Wszystkie zdjęcia oferty (duży rozmiar) z danych strony albo pusta lista."""
    raw = first(r"photos:\s*(\{.*?\})\s*,\s*\w+\s*:", page_html)
    try:
        sizes = json.loads(raw)
    except (TypeError, ValueError):
        return []
    for size in ("l", "x"):
        urls = [url for url in sizes.get(size) or [] if isinstance(url, str)]
        if urls:
            return urls
    return []


def card(ad):
    """Współrzędne, rok budowy i parametry z karty oferty albo None, jeśli się nie udało."""
    response = siec.fetch(ad["link"])
    if response is None or not response.ok:
        return None
    data = structured(response.text) or {}
    point = map_point(response.text)
    if point is None:  # zapasowo dane strukturalne, bez flagi dokładności
        try:
            point = float(data["geo"]["latitude"]), float(data["geo"]["longitude"]), False
        except (KeyError, TypeError, ValueError):
            return None
    lat, lng, approximate = point
    props = {p.get("name"): p.get("value") for p in data.get("additionalProperty") or [] if p.get("value")}
    year = re.search(r"\d{4}", str(data.get("yearBuilt") or props.get("Year built") or ""))
    amenities = {a.get("name") for a in data.get("amenityFeature") or [] if a.get("value")}
    deposit = text(first(r"Kaucja:</span><br/><span[^>]*>(.*?)</span>", response.text)) or None
    photos = photo_urls(response.text)
    if not photos:  # zapasowo samo pierwsze zdjęcie
        photo = first(r'id="gallery-first-photo"[^>]*><img class="desktop" src="([^"]+)"', response.text) or ad.get("photo")
        photos = [photo] if photo else []
    return {
        "lat": lat, "lng": lng,
        "approximate": approximate,
        "rok": int(year.group()) if year else None,
        "details": {
            "floors": props.get("Total floors in building"), "status": None,
            "market": {"primary": "pierwotny", "secondary": "wtórny"}.get(ad.get("market")),
            "building": props.get("Building type"), "heating": None, "ownership": None,
            "deposit": deposit, "freeFrom": None,
            "lift": True if "Elevator" in amenities else None,
            "extras": [AMENITIES[name] for name in AMENITIES if name in amenities], "equipment": [],
            "photos": photos, "photosAll": True,  # znacznik: wcześniej zapisywano tylko pierwsze zdjęcie
        },
    }
