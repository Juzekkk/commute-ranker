"""
Źródło ofert: otodom.pl (używa go oferty.py, obok nieruchomosci_online.py).

Otodom osadza dane każdej strony jako JSON (__NEXT_DATA__), więc skrypt czyta właśnie je,
a nie HTML. Strona wyników ma do 72 ofert, karta oferty dodaje współrzędne, rok budowy,
parametry i wszystkie zdjęcia. Oferty mają kształt wspólny dla wszystkich portali
(opis w oferty.py). Zapytania idą przez siec.py (ponowienia, rezygnacja przy blokadzie).
"""

import json
import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import siec

NAME = "Otodom"
HOST = "otodom.pl"
CARD_REQUEST = True  # karta oferty to osobne zapytanie
ROOMS = {word: n for n, word in enumerate(
    ["ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT", "NINE", "TEN"], start=1)}
FLOORS = {"CELLAR": "suterena", "GROUND": "parter", "ABOVE_TENTH": "> 10", "GARRET": "poddasze",
          **{word: str(n) for word, n in ROOMS.items()}}


def matches(url):
    host = urlsplit(url).hostname or ""
    return host == HOST or host.endswith("." + HOST)


def dig(data, *keys):
    """Zejście w zagnieżdżony JSON: dig(d, "a", "b") daje d["a"]["b"] albo None."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def next_data(response):
    """JSON z danymi, który Otodom osadza w każdej stronie, albo None."""
    if response is None or not response.ok:
        return None
    match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', response.text, re.S)
    try:
        return json.loads(match.group(1)) if match else None
    except ValueError:
        return None


def page_url(search_url, page):
    """Adres konkretnej strony wyników: widok listy, 72 oferty na stronę."""
    parts = urlsplit(search_url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
             if k not in ("page", "limit", "viewType")]
    query += [("viewType", "listing"), ("limit", "72"), ("page", str(page))]
    return urlunsplit(parts._replace(query=urlencode(query)))


def image_url(image):
    return image.get("large") or image.get("medium") or image.get("url")


def money(value):
    return int(value["value"]) if value and value.get("value") else None


def normalize(ad, delivery_year, estate):
    """Oferta z wyników wyszukiwania w kształcie wspólnym dla portali."""
    rooms = ad.get("roomsNumber")
    return {
        "id": str(ad["id"]), "portal": NAME, "link": f"https://www.otodom.pl/pl/oferta/{ad['slug']}",
        "title": ad.get("title") or "", "type": "house" if estate == "HOUSE" else "flat",
        "price": money(ad.get("totalPrice")), "rent": money(ad.get("rentPrice")),
        "area": ad.get("areaInSquareMeters"), "pricePerM2": money(ad.get("pricePerSquareMeter")),
        "rooms": ROOMS.get(rooms, rooms or None), "floor": FLOORS.get(ad.get("floorNumber"), ""),
        "photo": next((image_url(image) for image in ad.get("images") or [] if image_url(image)), None),
        "advertiser": "osoba prywatna" if ad.get("isPrivateOwner")
                      else dig(ad, "agency", "name") or "biuro lub deweloper",
        "listed": (ad.get("dateCreatedFirst") or ad.get("dateCreated") or "")[:10],
        "excerpt": ad.get("shortDescription") or "", "deliveryYear": delivery_year,
    }


def search(url, label=""):
    """Oferty ze wszystkich stron jednego wyszukiwania: ({id: oferta}, błąd albo None).
    Błąd oznacza, że pobrano tylko część stron; to, co jest, zostaje."""
    ads, page, total_pages = {}, 1, 1
    while page <= total_pages:
        response = siec.fetch(page_url(url, page))
        found = dig(next_data(response), "props", "pageProps", "data", "searchAds")
        if found is None:
            if response is None:
                reason = siec.blocked(url) or f"portal nie odpowiada ({siec.last_error(url)})"
            else:
                reason = (f"nie udało się odczytać strony (HTTP {response.status_code}); jeśli w przeglądarce "
                          "adres działa, Otodom mógł zmienić budowę strony")
            return ads, f"{NAME} ({label}strona {page}): {reason}; pobrano {len(ads)} ofert"
        total_pages = dig(found, "pagination", "totalPages") or 1
        for item in found.get("items") or []:
            # inwestycja deweloperska zawiera pasujące lokale w relatedAds,
            # a przewidywany termin oddania ma zapisany przy sobie
            delivery_year = dig(item, "investmentEstimatedDelivery", "year")
            for ad in item.get("relatedAds") or [item]:
                ads[str(ad["id"])] = normalize(ad, delivery_year, ad.get("estate") or item.get("estate"))
        print(f"Wyniki: {label}strona {page}/{total_pages}, ofert: {len(ads)}")
        page += 1
        siec.pause()
    return ads, None


def page_details(ad):
    """Najważniejsze parametry z karty ogłoszenia, z polskimi opisami takimi jak na Otodom."""
    values = {c.get("key"): c.get("localizedValue") for c in ad.get("characteristics") or []
              if c.get("localizedValue")}
    groups = {g.get("label"): g.get("values") or [] for g in ad.get("featuresByCategory") or []}
    lift = next((i.get("values") for i in ad.get("additionalInformation") or [] if i.get("label") == "lift"), None)
    return {
        "floors": values.get("building_floors_num"), "status": values.get("construction_status"),
        "market": values.get("market"), "building": values.get("building_type"),
        "heating": values.get("heating"), "ownership": values.get("building_ownership"),
        "deposit": values.get("deposit"), "freeFrom": values.get("free_from"),
        "lift": {"::y": True, "::n": False}.get((lift or [None])[0]),  # brak informacji: None
        "extras": groups.get("Informacje dodatkowe", []), "equipment": groups.get("Wyposażenie", []),
        # wszystkie zdjęcia, także rzuty (wyniki wyszukiwania mają tylko kilka)
        "photos": [image_url(image) for image in ad.get("images") or [] if image_url(image)],
    }


def stale(details):
    """Czy zapisaną kartę trzeba pobrać jeszcze raz (Otodom: nie ma takiego przypadku)."""
    return False


def card(ad):
    """Współrzędne, rok budowy i parametry z karty ogłoszenia albo None, jeśli się nie udało."""
    data = dig(next_data(siec.fetch(ad["link"])), "props", "pageProps", "ad")
    lat = dig(data, "location", "coordinates", "latitude")
    lng = dig(data, "location", "coordinates", "longitude")
    if lat is None or lng is None:
        return None
    year = re.search(r"\d{4}", str(dig(data, "target", "Build_year") or ""))
    return {"lat": lat, "lng": lng,
            # radius > 0: ogłoszeniodawca ukrył dokładny adres, punkt to środek okręgu
            "approximate": bool(dig(data, "location", "mapDetails", "radius")),
            "rok": int(year.group()) if year else None,
            "details": page_details(data)}
