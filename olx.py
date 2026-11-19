"""
Źródło ofert: olx.pl, dział Nieruchomości (używa go oferty.py, obok otodom.py i
nieruchomosci_online.py).

Strona wyników OLX osadza dane jako JSON (window.__PRERENDERED_STATE__): ma ok. 40 ofert na
stronę (kolejne przez &page=N) i dla każdej cenę, parametry, wszystkie zdjęcia i współrzędne.
Nie trzeba więc otwierać kart ofert: karta powstaje z danych strony wyników, bez dodatkowych
zapytań. Zapytania idą przez siec.py (ponowienia, rezygnacja przy blokadzie). Korzystamy tylko
ze stron wyników, nie z API OLX.

Lokalizacja: OLX często ukrywa dokładny adres (show_detailed = false). Punkt jest wtedy
orientacyjny i oferta ma oznaczenie „przybliżona”, tak samo jak z Otodom.
Rok budowy OLX w tych ogłoszeniach nie podaje, więc filtr max_rok_budowy ich nie dotyczy.
"""

import html
import json
import re
from urllib.parse import urlsplit, urlunsplit

import siec

NAME = "OLX"
HOST = "olx.pl"
CARD_REQUEST = False  # karta oferty powstaje z danych strony wyników, bez zapytania
ID_PREFIX = "olx"     # żeby numer oferty nie zderzył się z numerami z innych portali
ROOMS = {"one": 1, "two": 2, "three": 3, "four": "4+"}  # "four" na OLX to „4 i więcej”
PHOTO_SIZE = "1280x960"


def matches(url):
    host = urlsplit(url).hostname or ""
    return host == HOST or host.endswith("." + HOST)


def page_url(url, page):
    """Adres strony wyników: parametr page=N (pierwsza strona bez niego)."""
    parts = urlsplit(url)
    query = [q for q in parts.query.split("&") if q and not re.fullmatch(r"page=\d+", q)]
    if page > 1:
        query.append(f"page={page}")
    return urlunsplit(parts._replace(query="&".join(query)))


def listing_state(response):
    """Dane wyników wyszukiwania osadzone w stronie albo None."""
    if response is None or not response.ok:
        return None
    match = re.search(r'window\.__PRERENDERED_STATE__\s*=\s*"((?:[^"\\]|\\.)*)"', response.text, re.S)
    try:
        return json.loads(json.loads('"' + match.group(1) + '"'))["listing"]["listing"]
    except (AttributeError, KeyError, TypeError, ValueError):
        return None


def plain_text(fragment):
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment or "")).split())


def photo_url(url):
    """Zdjęcie w jednym, wygodnym rozmiarze (serwer zmniejsza, nigdy nie powiększa)."""
    return re.sub(r";s=\d+x\d+", f";s={PHOTO_SIZE}", url.replace(":443", ""))


def to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize(ad, kind):
    """Oferta z wyników OLX w kształcie wspólnym dla portali, razem z gotową „kartą” (_card)."""
    params = {p.get("key"): p for p in ad.get("params") or []}

    def norm(key):
        return (params.get(key) or {}).get("normalizedValue")

    def label(key):
        return ((params.get(key) or {}).get("value") or "").strip()

    price = to_number(((ad.get("price") or {}).get("regularPrice") or {}).get("value"))
    area, per_m2, rent = to_number(norm("m")), to_number(norm("price_per_m")), to_number(norm("rent"))
    floor = label("floor_select")
    photos = [photo_url(url) for url in ad.get("photos") or [] if isinstance(url, str)]
    where = ad.get("map") or {}
    card = None
    if where.get("lat") is not None and where.get("lon") is not None:
        card = {
            "lat": float(where["lat"]), "lng": float(where["lon"]),
            "approximate": not where.get("show_detailed"),
            "rok": None,
            "details": {
                "floors": None, "status": None, "market": label("market").lower() or None,
                "building": label("builttype").lower() or None, "heating": None, "ownership": None,
                "deposit": None, "freeFrom": None, "lift": None,
                "extras": ["umeblowane"] if norm("furniture") == "yes" else [], "equipment": [],
                "photos": photos,
            },
        }
    return {
        "id": ID_PREFIX + str(ad["id"]), "portal": NAME, "link": ad["url"],
        "title": ad.get("title") or "", "type": kind,
        "price": int(price) if price else None, "rent": int(rent) if rent else None,
        "area": area, "pricePerM2": round(per_m2) if per_m2 else None,
        "rooms": ROOMS.get(norm("rooms")), "floor": floor.lower() if floor[:1].isalpha() else floor,
        "photo": photos[0] if photos else None,
        # nazwy sprzedających nie zapisujemy: tylko rodzaj ogłoszeniodawcy
        "advertiser": "biuro lub deweloper" if ad.get("isBusiness") else "osoba prywatna",
        "listed": (ad.get("createdTime") or "")[:10],
        "excerpt": plain_text(ad.get("description")), "deliveryYear": None,
        "_card": card,
    }


def search(url, label=""):
    """Oferty ze wszystkich stron jednego wyszukiwania: ({id: oferta}, błąd albo None).
    Błąd oznacza, że pobrano tylko część stron; to, co jest, zostaje."""
    kind = "house" if "/domy/" in urlsplit(url).path else "flat"
    ads, page, pages = {}, 1, 1
    while page <= pages:
        response = siec.fetch(page_url(url, page))
        state = listing_state(response)
        if state is None:
            if response is None:
                reason = siec.blocked(url) or f"portal nie odpowiada ({siec.last_error(url)})"
            else:
                reason = (f"nie udało się odczytać strony (HTTP {response.status_code}); jeśli w przeglądarce "
                          "adres działa, OLX mógł zmienić budowę strony")
            return ads, f"{NAME} ({label}strona {page}): {reason}; pobrano {len(ads)} ofert"
        pages = state.get("totalPages") or 1
        found = {ad["id"]: ad for ad in (normalize(item, kind) for item in state.get("ads") or [])}
        if not found or (page > 1 and all(ad_id in ads for ad_id in found)):
            break
        ads.update(found)
        print(f"Wyniki: {label}strona {page}/{pages}, ofert: {len(ads)}")
        page += 1
        siec.pause()
    return ads, None


def stale(details):
    """Czy zapisaną kartę trzeba pobrać jeszcze raz (OLX: nie ma takiego przypadku)."""
    return False


def card(ad):
    """Współrzędne i parametry oferty z danych strony wyników (bez zapytania) albo None, gdy brak lokalizacji."""
    return dict(ad["_card"]) if ad.get("_card") else None
