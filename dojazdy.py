#!/usr/bin/env python3
"""
Ranking ofert z portali (Otodom, Nieruchomości Online) według czasu dojazdu komunikacją miejską.

1. Zbiera oferty z wyszukiwań z config.toml (oferty.py, a ten korzysta z otodom.py i
   nieruchomosci_online.py) i od razu odrzuca oferty bez ceny oraz inwestycje z terminem oddania
   po max_rok_budowy. Gdy portal zwraca błędy (np. 429), pobieranie jest skracane (siec.py):
   skrypt idzie dalej z tym, co już ma, i opisuje braki w podsumowaniu.
2. Dla ofert, których jeszcze nie zna, odczytuje z karty ogłoszenia współrzędne i rok budowy
   (zapamiętuje je w stan.json) i odrzuca zbyt późne roczniki oraz oferty z obszarów wykluczonych
   na mapie (wykluczenia.json): dla nich nie liczy czasów ani tras i nie zapisuje zdjęć.
3. Liczy czas dojazdu do Twoich miejsc przez Google Routes API (przyjazd we wtorek
   o 9:00) i zapamiętuje go w czasy.json na 30 dni według współrzędnych, więc oferty
   w tym samym budynku liczą się raz. Miejsca z max_minut idą pierwsze: oferta, która
   przekracza limit, nie zużywa zapytań na pozostałe miejsca. Skrypt pilnuje też
   darmowego miesięcznego limitu Google.
4. Dla ofert z rankingu pobiera z Google do 3 wariantów przejazdu do każdego miejsca
   (linie, przesiadki, godziny, kształt trasy) i zapamiętuje je w trasy.json na 30 dni.
5. Scala duplikaty z różnych portali, sortuje po tygodniowym czasie w drodze i zapisuje ranking
   do wyniki.md (do czytania), wyniki.csv (do Excela) i wyniki.json (dane dla mapa.py).

Uruchomienie:
  python dojazdy.py                    wszystkie wyszukiwania z [wyszukiwania] w config.toml
  python dojazdy.py otodom-m olx-d     tylko wybrane (nazwy z config.toml); reszta z poprzedniego pobrania
"""

import csv
import json
import math
import sys
import time
import tomllib
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import requests

import oferty
import otodom
import siec

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "config.toml"
TIMES_FILE = HERE / "czasy.json"
ROUTES_FILE = HERE / "trasy.json"
CSV_FILE = HERE / "wyniki.csv"
MD_FILE = HERE / "wyniki.md"
JSON_FILE = HERE / "wyniki.json"

GOOGLE_URL = "https://routes.googleapis.com/distanceMatrix/v2:computeRouteMatrix"
# Google liczy opłatę za każdą parę punkt-miejsce; 10 000 par miesięcznie jest za darmo.
MONTHLY_LIMIT = 9000
TIMES_MAX_AGE_DAYS = 30  # potem czas liczony jest od nowa (rozkłady się zmieniają)
ROUTES_URL = "https://routes.googleapis.com/directions/v2:computeRoutes"
ROUTES_FIELDS = ("routes.duration,routes.legs.steps.travelMode,routes.legs.steps.staticDuration,"
                 "routes.legs.steps.polyline.encodedPolyline,routes.legs.steps.transitDetails")
# trasy mają własną darmową pulę Google: 10 000 zapytań miesięcznie (jedno zapytanie = do 3 wariantów)
ROUTES_MONTHLY_LIMIT = 9000
WARSAW = ZoneInfo("Europe/Warsaw")
# darmowy limit Google odnawia się 1. dnia miesiąca o północy czasu pacyficznego (u nas ok. 9:00)
GOOGLE_BILLING_TZ = ZoneInfo("America/Los_Angeles")
WEEK = "tydzień w drodze [min]"


def dig(data, *keys):
    """Zejście w zagnieżdżony JSON: dig(d, "a", "b") daje d["a"]["b"] albo None."""
    for key in keys:
        if not isinstance(data, dict):
            return None
        data = data.get(key)
    return data


def parse_coords(place):
    try:
        lat, lng = (float(x) for x in place["wspolrzedne"].split(","))
    except (KeyError, ValueError):
        sys.exit(f'Miejsce "{place.get("nazwa")}": wpisz współrzędne w postaci '
                 'wspolrzedne = "52.2297, 21.0122"')
    return {"lat": lat, "lng": lng}


def arrival_time():
    """Najbliższy wtorek, 9:00 czasu polskiego: typowy dojazd w porannym szczycie."""
    today = datetime.now(WARSAW).date()
    tuesday = today + timedelta(days=(1 - today.weekday()) % 7 or 7)
    return datetime(tuesday.year, tuesday.month, tuesday.day, 9, tzinfo=WARSAW).isoformat()


def billing_month():
    """Miesiąc rozliczeniowy Google ("RRRR-MM"), według którego liczony jest darmowy limit."""
    return datetime.now(GOOGLE_BILLING_TZ).strftime("%Y-%m")


def point_key(p):
    return f"{p['lat']:.5f},{p['lng']:.5f}"


def time_key(pk, place):
    return f"{pk}@{point_key(place['coords'])}"


def location(p):
    return {"location": {"latLng": {"latitude": p["lat"], "longitude": p["lng"]}}}


def post_google(url, body, field_mask, api_key):
    """POST do Routes API. Przy limicie na minutę (HTTP 429) czeka i ponawia raz.
    Zwraca None, gdy limit trwa dalej (np. dzienny, ustawiony w konsoli Google)."""
    request = {"json": body, "headers": {"X-Goog-Api-Key": api_key, "X-Goog-FieldMask": field_mask},
               "timeout": 60}
    response = requests.post(url, **request)
    if response.status_code == 429:
        time.sleep(60)
        response = requests.post(url, **request)
        if response.status_code == 429:
            return None
    return response


def google_times(points, place, api_key, arrival):
    """Minuty dojazdu komunikacją z każdego punktu do miejsca, według numeru punktu.
    None: Google nie znalazł połączenia. Brak numeru: błąd dla tej pary (spróbujemy następnym razem).
    Zwraca None zamiast słownika, gdy Google odrzuca zapytania limitem (HTTP 429)."""
    response = post_google(
        GOOGLE_URL,
        {"origins": [{"waypoint": location(p)} for p in points],
         "destinations": [{"waypoint": location(place["coords"])}],
         "travelMode": "TRANSIT",
         "arrivalTime": arrival},
        "originIndex,destinationIndex,status,condition,duration", api_key)
    if response is None:
        return None
    if not response.ok:
        sys.exit(f"Błąd Google Routes API (HTTP {response.status_code}): {response.text}")
    minutes = {}
    for element in response.json():
        if dig(element, "status", "code"):
            continue
        if element.get("condition") == "ROUTE_EXISTS":
            seconds = int(element.get("duration", "0s").rstrip("s"))
            minutes[element.get("originIndex", 0)] = round(seconds / 60)
        else:
            minutes[element.get("originIndex", 0)] = None
    return minutes


def seconds(duration):
    return int((duration or "0s").rstrip("s"))


def compact_route(route):
    """Wariant przejazdu w skrócie: czas i odcinki (pieszo albo konkretna linia) z kształtem na mapę."""
    segments = []
    for step in (step for leg in route.get("legs") or [] for step in leg.get("steps") or []):
        polyline = dig(step, "polyline", "encodedPolyline")
        transit = step.get("transitDetails")
        if step.get("travelMode") == "TRANSIT" and transit:
            line, stops = transit.get("transitLine") or {}, transit.get("stopDetails") or {}
            segments.append({
                "mode": "transit", "seconds": seconds(step.get("staticDuration")),
                "line": line.get("nameShort") or line.get("name") or "",
                "vehicle": dig(line, "vehicle", "type") or "", "color": line.get("color"),
                "textColor": line.get("textColor"), "headsign": transit.get("headsign"),
                "stops": transit.get("stopCount"), "from": dig(stops, "departureStop", "name"),
                "to": dig(stops, "arrivalStop", "name"), "depart": stops.get("departureTime"),
                "arrive": stops.get("arrivalTime"), "polylines": [polyline] if polyline else []})
        elif segments and segments[-1]["mode"] == "walk":  # kroki pieszo (skręć w lewo...) w jeden odcinek
            segments[-1]["seconds"] += seconds(step.get("staticDuration"))
            segments[-1]["polylines"] += [polyline] if polyline else []
        else:
            segments.append({"mode": "walk", "seconds": seconds(step.get("staticDuration")),
                             "polylines": [polyline] if polyline else []})
    return {"seconds": seconds(route.get("duration")), "segments": segments}


def update_routes(rows, places, api_key, state):
    """Do 3 wariantów przejazdu z każdej oferty z rankingu do każdego miejsca: jedno zapytanie
    na parę. Zapamiętuje je na TIMES_MAX_AGE_DAYS; oferty w tym samym budynku liczą się raz."""
    today, month = date.today().isoformat(), billing_month()
    stale = (date.today() - timedelta(days=TIMES_MAX_AGE_DAYS)).isoformat()
    todo = {}
    for row in rows:
        for place in places:
            key = time_key(point_key(row), place)
            if state["trasy"].get(key, [None, ""])[1] < stale:
                todo[key] = (row, place)
    if not todo:
        return
    print(f"Pobieram z Google warianty tras: {len(todo)} zapytań...")
    arrival, failures = arrival_time(), 0
    for n, (key, (origin, place)) in enumerate(todo.items(), start=1):
        if state["zuzycie"].get(month, 0) >= ROUTES_MONTHLY_LIMIT:
            print(f"\nWykorzystano limit {ROUTES_MONTHLY_LIMIT} zapytań o trasy w tym miesiącu. "
                  "Pozostałe trasy pobiorę w kolejnym miesiącu.")
            return
        response = post_google(ROUTES_URL, {
            "origin": location(origin), "destination": location(place["coords"]), "travelMode": "TRANSIT",
            "arrivalTime": arrival, "computeAlternativeRoutes": True, "languageCode": "pl",
        }, ROUTES_FIELDS, api_key)
        if response is None:
            print("\nGoogle odrzuca zapytania o trasy (HTTP 429). Pozostałe pobiorę przy kolejnym uruchomieniu.")
            return
        if not response.ok:  # pojedyncza para; przerywamy dopiero przy serii błędów
            failures += 1
            if failures >= 5:
                print(f"\nGoogle zwraca błędy przy trasach (HTTP {response.status_code}): "
                      f"{response.text[:200]}. Przerywam pobieranie tras.")
                return
            continue
        failures = 0
        state["zuzycie"][month] = state["zuzycie"].get(month, 0) + 1  # płatne jest udane zapytanie
        routes = [compact_route(route) for route in response.json().get("routes") or []]
        state["trasy"][key] = [sorted(routes, key=lambda route: route["seconds"]), today]
        print(f"  {n}/{len(todo)}", end="\r")


def within_limits(state, pk, places):
    """Czy punkt mieści się w max_minut tych miejsc, do których czas jest już znany."""
    for place in places:
        entry = state["czasy"].get(time_key(pk, place))
        if "max_minut" in place and entry and (entry[0] is None or entry[0] > place["max_minut"]):
            return False
    return True


def update_times(points, places, api_key, state):
    """Dolicza czasy, których brakuje albo które są starsze niż TIMES_MAX_AGE_DAYS.
    Miejsca z max_minut idą pierwsze: punkt, który przekracza limit, nie zużywa zapytań
    na pozostałe miejsca. Nie przekracza MONTHLY_LIMIT par punkt-miejsce w miesiącu."""
    today = date.today().isoformat()
    month = billing_month()
    stale = (date.today() - timedelta(days=TIMES_MAX_AGE_DAYS)).isoformat()
    arrival = arrival_time()
    done = []
    for place in sorted(places, key=lambda p: "max_minut" not in p):
        todo = [pk for pk in points
                if state["czasy"].get(time_key(pk, place), [None, ""])[1] < stale
                and within_limits(state, pk, done)]
        done.append(place)
        for start in range(0, len(todo), 100):  # Google: max 100 par na zapytanie w trybie komunikacji
            used = state["zuzycie"].get(month, 0)
            wanted = todo[start:start + 100]
            chunk = wanted[:max(0, MONTHLY_LIMIT - used)]
            if chunk:
                result = google_times([points[pk] for pk in chunk], place, api_key, arrival)
                if result is None:
                    print("Google odrzuca zapytania (HTTP 429): wyczerpany limit ustawiony w konsoli "
                          "Google Cloud. Pozostałe czasy policzę przy kolejnym uruchomieniu.")
                    return
                state["zuzycie"][month] = used + len(chunk)
                for i, minutes in result.items():
                    state["czasy"][time_key(chunk[i], place)] = [minutes, today]
            if len(chunk) < len(wanted):
                print(f"Wykorzystano limit {MONTHLY_LIMIT} par punkt-miejsce w tym miesiącu. "
                      "Oferty bez policzonego czasu pomijam, policzę je w kolejnym miesiącu.")
                return


def migrate_times(state, cache):
    """Poprzednia wersja zapisywała czasy pod numerem oferty: przepisz je na współrzędne."""
    for key in [k for k in state["czasy"] if "," not in k.split("@")[0]]:
        ad_id, place = key.split("@")
        value = state["czasy"].pop(key)
        if ad_id in cache:
            state["czasy"].setdefault(f"{point_key(cache[ad_id])}@{place}", value)


DUPLICATE_RADIUS_M = 60  # to samo mieszkanie na dwóch portalach: ta sama cena, metraż ±1 m², bliski punkt


def merge_duplicates(rows):
    """Oferty z różnych portali, które wyglądają na to samo mieszkanie, scala w jedną (zostaje ta
    z Otodom, bo ma pełniejsze dane) z odnośnikiem do drugiego portalu. Zwraca (oferty, lista scalonych ofert, które znikają z rankingu)."""
    kept, merged = [], []
    for row in rows:
        def same(other):
            kx = 111320 * math.cos(math.radians(row["lat"]))
            return (other["portal"] != row["portal"] and other["cena [zł]"] == row["cena [zł]"]
                    and abs(float(other["m²"] or 0) - float(row["m²"] or 0)) <= 1
                    and math.hypot((other["lat"] - row["lat"]) * 110540, (other["lng"] - row["lng"]) * kx)
                    <= DUPLICATE_RADIUS_M)
        twin = next((other for other in kept if same(other)), None)
        if twin is None:
            kept.append(row)
            continue
        winner, loser = (twin, row) if twin["portal"] == otodom.NAME or row["portal"] != otodom.NAME \
            else (row, twin)
        if winner is row:
            kept[kept.index(twin)] = row
        winner.setdefault("alsoOn", []).append({"portal": loser["portal"], "link": loser["link"]})
        merged.append(loser)
    return kept, merged


def excerpt(text, limit=300):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def thousands(value):
    return f"{value:,}".replace(",", " ") if isinstance(value, int) else ""


def md_text(text):
    return str(text).replace("|", "\\|").replace("[", "(").replace("]", ")")


def md_table(numbered_rows, places, place_cols):
    lines = ["| # | Tydzień | Dojazdy [min] | Mieszkanie | Oferta |",
             "| --: | --: | --- | --- | --- |"]
    for n, row in numbered_rows:
        week = round(row[WEEK])
        commute = " · ".join(f"{md_text(place['nazwa'])} {row[col]}"
                             for place, col in zip(places, place_cols))
        if row["lokalizacja"] == "przybliżona":
            commute = "≈ " + commute
        price = f"{thousands(row['cena [zł]'])} zł"
        if row["czynsz [zł]"]:
            price += f" (czynsz {thousands(row['czynsz [zł]'])} zł)"
        flat = [price]
        if row["m²"]:
            flat.append(f"{row['m²']} m²")
        if row["pokoje"]:
            flat.append(f"{row['pokoje']} pok.")
        if row["rok budowy"]:
            flat.append(f"rok {row['rok budowy']}")
        title = row["tytuł"] if len(row["tytuł"]) <= 60 else row["tytuł"][:59] + "…"
        offer = ("nowa · " if row["nowa"] else "") + f"[{md_text(title)}]({row['link']})"
        lines.append(f"| **{n}** | {week // 60} h {week % 60:02d} min | {commute} | "
                     f"{' · '.join(flat)} | {offer} |")
    return "\n".join(lines)


def write_markdown(rows, places, place_cols, summary):
    numbered = list(enumerate(rows, start=1))
    new = [(n, row) for n, row in numbered if row["nowa"]]
    parts = [
        "# Mieszkania według czasu dojazdu", "",
        "## 📋 Podsumowanie", "",
        f"- Stan na {datetime.now(WARSAW):%Y-%m-%d %H:%M}.",
        "- Dojazd komunikacją miejską z przyjazdem we wtorek o 9:00. Tydzień to suma "
        "dojazdów tam i z powrotem według `razy_w_tygodniu`.",
        "- Znak ≈ przy dojazdach: ogłoszeniodawca podał tylko przybliżoną lokalizację.",
        *[f"- {line}" for line in summary], "",
    ]
    if 0 < len(new) < len(rows):  # przy pierwszym uruchomieniu nowe są wszystkie
        parts += ["## 🔄 Nowe od ostatniego uruchomienia", "", md_table(new, places, place_cols), ""]
    parts += ["## 📊 Ranking", "",
              md_table(numbered, places, place_cols) if rows else "Brak ofert spełniających kryteria.",
              ""]
    MD_FILE.write_text("\n".join(parts), encoding="utf-8")


def write_csv(rows, place_cols):
    columns = [WEEK, *place_cols, "cena [zł]", "czynsz [zł]", "zł/m²", "m²", "pokoje",
               "rok budowy", "nowa", "lokalizacja", "tytuł", "link"]
    # średnik i BOM, żeby polski Excel od razu rozdzielił kolumny i pokazał polskie znaki
    with CSV_FILE.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns, delimiter=";", extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(rows, places, place_cols, summary):
    """Dane dla mapa.py: miejsca i oferty ze współrzędnymi, w kolejności rankingu."""
    data = {
        "generated": datetime.now(WARSAW).strftime("%Y-%m-%d %H:%M"),
        "summary": summary,
        "places": [{"name": place["nazwa"], **place["coords"]} for place in places],
        "offers": [{
            "id": row["id"], "rank": n, "week": row[WEEK], "times": [row[col] for col in place_cols],
            "price": row["cena [zł]"] or None, "rent": row["czynsz [zł]"] or None,
            "pricePerM2": row["zł/m²"] or None,
            "area": row["m²"] or None, "rooms": row["pokoje"] or None, "year": row["rok budowy"] or None,
            "floor": row["piętro"] or None, "photo": row["zdjęcie"], "advertiser": row["ogłoszeniodawca"],
            "listed": row["dodane"] or None, "excerpt": row["opis"] or None, "details": row["details"],
            "routes": row["trasy"],
            "type": row["typ"], "portal": row["portal"], "alsoOn": row.get("alsoOn", []), "isNew": bool(row["nowa"]),
            "approximate": row["lokalizacja"] == "przybliżona",
            "title": row["tytuł"], "link": row["link"], "lat": row["lat"], "lng": row["lng"],
        } for n, row in enumerate(rows, start=1)],
    }
    JSON_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")


def main():
    if not CONFIG_FILE.exists():
        sys.exit("Brak config.toml. Skopiuj config.example.toml do config.toml i uzupełnij go (opis w README.md).")
    config = tomllib.loads(CONFIG_FILE.read_text(encoding="utf-8-sig"))
    api_key = config["google"]["api_key"]
    if not api_key:
        sys.exit("Uzupełnij api_key w sekcji [google] w config.toml.")
    places = [{**place, "coords": parse_coords(place)} for place in config["miejsca"]]
    max_year = config.get("filtry", {}).get("max_rok_budowy")
    siec.configure(config.get("pobieranie", {}).get("limit_minut_na_portal"))

    entries = oferty.search_entries(config)
    selected = sys.argv[1:]  # python dojazdy.py otodom-m olx-m: pobierz tylko te wyszukiwania
    if selected:
        print(f"Odświeżam tylko: {', '.join(selected)}. Pozostałe wyszukiwania biorę z poprzedniego pobrania.")
    ads, problems, search_notes = oferty.collect(entries, selected)
    if not ads:
        sys.exit("Nie pobrano żadnych ofert. " + " ".join(problems) +
                 " Sprawdź adresy w config.toml w przeglądarce albo spróbuj ponownie później.")
    skipped = Counter()
    by_portal = defaultdict(Counter)  # portal -> powód odpadnięcia -> liczba ofert

    def drop(ad, reason, before_commute=True):
        if before_commute:
            skipped[reason] += 1
        by_portal[ad["portal"]][reason] += 1

    candidates = {}
    for ad_id, ad in ads.items():  # odsiew bez pobierania karty ogłoszenia
        reason = oferty.skip_reason(ad, ad["deliveryYear"], max_year)
        if reason:
            drop(ad, reason)
        else:
            candidates[ad_id] = ad

    zones = oferty.load_zones()
    cache = oferty.load_cache()
    new = {ad_id for ad_id in candidates if ad_id not in cache}
    # wpisy bez roku budowy pochodzą z poprzedniej wersji skryptu: ich karty pobieramy jeszcze raz
    oferty.fetch_details([ad_id for ad_id in candidates if "rok" not in cache.get(ad_id, {})],
                         candidates, cache, zones)

    located = {}
    for ad_id, ad in candidates.items():
        if ad_id not in cache:
            drop(ad, "nie udało się pobrać karty")
            continue
        if oferty.in_zone(cache[ad_id]["lat"], cache[ad_id]["lng"], zones):
            drop(ad, "w wykluczonym obszarze")
            continue
        ad["rok"] = cache[ad_id].get("rok") or ad["deliveryYear"]
        reason = oferty.skip_reason(ad, ad["rok"], max_year)
        if reason:
            drop(ad, reason)
        else:
            located[ad_id] = cache[ad_id]
    if not located:
        sys.exit("Brak ofert do policzenia: wszystkie pominięte albo bez lokalizacji.")

    state = (json.loads(TIMES_FILE.read_text(encoding="utf-8")) if TIMES_FILE.exists()
             else {"czasy": {}, "zuzycie": {}})
    migrate_times(state, cache)
    try:
        update_times({point_key(p): p for p in located.values()}, places, api_key, state)
    finally:  # zużycie limitu zostaje zapisane także po przerwaniu
        TIMES_FILE.write_text(json.dumps(state), encoding="utf-8")

    place_cols = [f"{place['nazwa']} [min]" for place in places]
    rows = []
    for ad_id, details in located.items():
        minutes = [state["czasy"].get(time_key(point_key(details), place), [None])[0]
                   for place in places]
        ad = candidates[ad_id]
        if None in minutes:  # brak połączenia, przekroczony limit innego miejsca albo brak czasu
            drop(ad, "poza limitem dojazdu albo bez połączenia", before_commute=False)
            continue
        if any(m > place["max_minut"] for m, place in zip(minutes, places) if "max_minut" in place):
            drop(ad, "poza limitem dojazdu albo bez połączenia", before_commute=False)
            continue
        price, area = ad["price"], ad["area"]
        row = {WEEK: sum(2 * place.get("razy_w_tygodniu", 1) * m for m, place in zip(minutes, places))}
        row.update(zip(place_cols, minutes))
        row.update({
            "id": ad_id, "lat": details["lat"], "lng": details["lng"],
            "typ": ad["type"], "piętro": ad["floor"], "portal": ad["portal"], "zdjęcie": ad["photo"],
            "ogłoszeniodawca": ad["advertiser"], "dodane": ad["listed"], "opis": excerpt(ad["excerpt"]),
            "cena [zł]": price,
            "czynsz [zł]": ad["rent"] or "",
            "zł/m²": ad["pricePerM2"] or (round(price / area) if price and area else ""),
            "m²": round(area) if area else "",
            "pokoje": ad["rooms"] or "",
            "rok budowy": ad["rok"] or "",
            "nowa": "TAK" if ad_id in new else "",
            "lokalizacja": "przybliżona" if details["approximate"] else "dokładna",
            "tytuł": ad["title"],
            "link": ad["link"],
        })
        rows.append(row)
    rows.sort(key=lambda row: row[WEEK])
    rows, merged = merge_duplicates(rows)
    for loser in merged:
        by_portal[loser["portal"]]["scalone z ofertą z innego portalu"] += 1
    # parametry i zdjęcia z karty mają tylko oferty pobrane tą wersją; starsze uzupełniamy, ale tylko z rankingu
    oferty.fetch_details([row["id"] for row in rows
                          if oferty.stale_details(candidates[row["id"]], cache[row["id"]].get("details"))],
                         candidates, cache, zones)
    for row in rows:
        row["details"] = cache[row["id"]].get("details")

    routes_state = (json.loads(ROUTES_FILE.read_text(encoding="utf-8")) if ROUTES_FILE.exists()
                    else {"trasy": {}, "zuzycie": {}})
    try:
        update_routes(rows, places, api_key, routes_state)
    finally:  # zużycie limitu zostaje zapisane także po przerwaniu
        ROUTES_FILE.write_text(json.dumps(routes_state, ensure_ascii=False), encoding="utf-8")
    for row in rows:
        row["trasy"] = [routes_state["trasy"].get(time_key(point_key(row), place), [None])[0]
                        for place in places]

    used = state["zuzycie"].get(billing_month(), 0)
    skipped_text = ", ".join(f"{reason}: {n}" for reason, n in skipped.items()) or "brak"
    notes = [f"Uwaga, wyniki mogą być niepełne: {p}." for p in problems]
    notes += [f"Uwaga, wyniki mogą być niepełne: {p}." for p in siec.problems()
              if not any(p.split(": ", 1)[1] in text for text in problems)]
    in_ranking = Counter(row["portal"] for row in rows)
    portal_lines = []
    for portal, count in Counter(ad["portal"] for ad in ads.values()).most_common():
        gone = ", ".join(f"{reason}: {n}" for reason, n in by_portal[portal].most_common())
        portal_lines.append(f"{portal}: {count} ofert, w rankingu {in_ranking[portal]}"
                            + (f"; odpadły: {gone}" if gone else "") + ".")
    summary = [
        *notes,
        *[f"Wyszukiwanie {note}." for note in search_notes],
        f"Ofert w wyszukiwaniu: {len(ads)}. Pominięte przed liczeniem dojazdów: {skipped_text}.",
        f"W limitach dojazdu: {len(rows)} z {len(located)} (nowych: {sum(1 for r in rows if r['nowa'])})."
        + (f" Scalone duplikaty z różnych portali: {len(merged)}." if merged else ""),
        *portal_lines,
        f"Google w tym miesiącu (licznik skryptu): {thousands(used)} z {thousands(MONTHLY_LIMIT)} par "
        "(darmowo do 10 000).",
        f"Google, trasy w tym miesiącu: {thousands(routes_state['zuzycie'].get(billing_month(), 0))} z "
        f"{thousands(ROUTES_MONTHLY_LIMIT)} zapytań (osobna pula, darmowo do 10 000).",
    ]
    write_csv(rows, place_cols)
    write_markdown(rows, places, place_cols, summary)
    write_json(rows, places, place_cols, summary)

    print("\n" + "\n".join(summary))
    print(f"Ranking: {MD_FILE.name} (do czytania), {CSV_FILE.name} (do Excela), "
          f"mapa: python mapa.py. Najlepsze 10:")
    for row in rows[:10]:
        per_place = ", ".join(f"{place['nazwa']} {row[col]}" for place, col in zip(places, place_cols))
        flag = "NOWA " if row["nowa"] else ""
        print(f"{row[WEEK]:>5} min/tydz. | {per_place} | {row['cena [zł]']} zł | "
              f"{row['m²']} m2 | {flag}{row['link']}")


if __name__ == "__main__":
    main()
