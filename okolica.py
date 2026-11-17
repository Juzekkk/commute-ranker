#!/usr/bin/env python3
"""
Okolica ofert z danych OpenStreetMap, bez pytania żadnego serwera podczas przeglądania.

1. Pobiera wycinek OpenStreetMap dla województwa mazowieckiego z Geofabrik
   (aktualizowany codziennie, kilkaset MB). Wycinek młodszy niż 30 dni zostaje.
2. Wyciąga z niego supermarkety, sklepy spożywcze, stacje metra i kolei, przystanki
   tramwajowe, siłownie, apteki, paczkomaty i parki do okolica.json.

mapa.py wkleja te dane do strony, a strona liczy okolicę każdej oferty u Ciebie.
Uruchomienie: python okolica.py (wystarczy raz na jakiś czas, np. raz w miesiącu)
"""

import json
import math
import sys
import time
from collections import Counter
from datetime import date
from pathlib import Path

import osmium
import requests

HERE = Path(__file__).resolve().parent
EXTRACT_URL = "https://download.geofabrik.de/europe/poland/mazowieckie-latest.osm.pbf"
EXTRACT_FILE = HERE / "mazowieckie-latest.osm.pbf"
NEARBY_FILE = HERE / "okolica.json"
MAX_AGE_DAYS = 30
WANTED = (("shop", "supermarket"), ("shop", "convenience"), ("leisure", "park"), ("leisure", "fitness_centre"),
          ("amenity", "pharmacy"), ("amenity", "parcel_locker"), ("railway", "station"), ("railway", "halt"),
          ("railway", "tram_stop"))


def download():
    """Pobiera wycinek, chyba że lokalny ma mniej niż MAX_AGE_DAYS dni."""
    if EXTRACT_FILE.exists():
        age_days = (time.time() - EXTRACT_FILE.stat().st_mtime) / 86400
        if age_days < MAX_AGE_DAYS:
            print(f"Używam pobranego wcześniej wycinka ({age_days:.0f} dni).")
            return
    print(f"Pobieram {EXTRACT_URL}")
    partial = EXTRACT_FILE.with_name(EXTRACT_FILE.name + ".part")
    try:
        with requests.get(EXTRACT_URL, stream=True, timeout=60,
                          headers={"User-Agent": "mieszkania-dojazdy (prywatny skrypt)"}) as response:
            response.raise_for_status()
            total = int(response.headers.get("Content-Length", 0))
            done = 0
            with partial.open("wb") as f:
                for chunk in response.iter_content(chunk_size=1 << 20):
                    f.write(chunk)
                    done += len(chunk)
                    print(f"  {done / 1e6:.0f}" + (f" z {total / 1e6:.0f} MB" if total else " MB"), end="\r")
    except requests.RequestException as error:
        partial.unlink(missing_ok=True)
        sys.exit(f"\nNie udało się pobrać wycinka OpenStreetMap: {error}")
    partial.replace(EXTRACT_FILE)
    print()


def classify(tags):
    """Rodzaj miejsca według tagów OpenStreetMap albo None."""
    shop, railway, amenity = tags.get("shop"), tags.get("railway"), tags.get("amenity")
    if shop == "supermarket":
        return "supermarket"
    if shop == "convenience":
        return "shop"
    if railway == "station" and (tags.get("station") == "subway" or tags.get("subway") == "yes"):
        return "metro"
    if railway in ("station", "halt"):
        return "train"
    if railway == "tram_stop":
        return "tram"
    if tags.get("leisure") == "fitness_centre":
        return "gym"
    if amenity == "pharmacy":
        return "pharmacy"
    if amenity == "parcel_locker":
        return "parcel"
    return None


def place_name(tags):
    """Nazwa, a gdy jej brak (np. paczkomaty), marka z kodem: "InPost WAW01M"."""
    return tags.get("name") or " ".join(filter(None, (tags.get("brand"), tags.get("ref"))))


def simplify(ring, min_step_m=8):
    """Pomija punkty obrysu bliższe niż ~8 m od poprzedniego: mniejszy plik, ten sam kształt."""
    kept = [ring[0]]
    for lat, lng in ring[1:-1]:
        last_lat, last_lng = kept[-1]
        dx = (lng - last_lng) * 111320 * math.cos(math.radians(lat))
        if math.hypot(dx, (lat - last_lat) * 110540) >= min_step_m:
            kept.append((lat, lng))
    kept.append(ring[-1])
    return kept


def outer_rings(area):
    try:
        return [simplify([(round(p.lat, 5), round(p.lon, 5)) for p in ring]) for ring in area.outer_rings()]
    except osmium.InvalidLocationError:  # obiekt na granicy wycinka, bez części punktów
        return []


def extract():
    """Miejsca jako [rodzaj, nazwa, lat, lng] i parki jako obrysy z wycinka."""
    pois, parks = [], []
    processor = (osmium.FileProcessor(str(EXTRACT_FILE))
                 .with_areas(osmium.filter.TagFilter(*WANTED))
                 .with_filter(osmium.filter.TagFilter(*WANTED)))
    for obj in processor:
        if isinstance(obj, osmium.osm.Node):
            kind = classify(obj.tags)
            if kind and obj.location.valid():
                pois.append([kind, place_name(obj.tags), round(obj.location.lat, 5), round(obj.location.lon, 5)])
        elif isinstance(obj, osmium.osm.Area):  # zamknięte linie i multipoligony, np. sklep jako budynek
            rings = outer_rings(obj)
            if not rings:
                continue
            if obj.tags.get("leisure") == "park":
                parks.append({"name": obj.tags.get("name", ""), "rings": rings})
            elif kind := classify(obj.tags):
                ring = rings[0][:-1]  # bez punktu zamykającego
                pois.append([kind, place_name(obj.tags), round(sum(p[0] for p in ring) / len(ring), 5),
                             round(sum(p[1] for p in ring) / len(ring), 5)])
    return pois, parks


def main():
    download()
    print("Wyciągam sklepy, przystanki i parki (może potrwać kilka minut)...")
    started = time.time()
    pois, parks = extract()
    data_date = date.fromtimestamp(EXTRACT_FILE.stat().st_mtime).isoformat()
    NEARBY_FILE.write_text(json.dumps({"generated": data_date, "pois": pois, "parks": parks},
                                      ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    counts = Counter(kind for kind, *_ in pois)
    print(f"Gotowe w {time.time() - started:.0f} s: {len(pois)} miejsc ({dict(counts)}) i {len(parks)} parków.")
    print(f"Zapisano {NEARBY_FILE.name}. Teraz uruchom: python mapa.py")


if __name__ == "__main__":
    main()
