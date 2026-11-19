#!/usr/bin/env python3
"""
Fikcyjne dane do zrzutów ekranu w README: wyniki.json i okolica.json w tym folderze
oraz mapa.html złożona przez mapa.py. Oferty, ogłoszeniodawcy i zdjęcia są
wymyślone; współrzędne miejsc są w Warszawie, a trasy to uproszczone linie.

Uruchomienie: python docs/mock/generuj_mock.py
"""

import base64
import json
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import mapa  # noqa: E402

random.seed(7)

PLACES = [
    {"name": "Praca", "lat": 52.2302, "lng": 20.9836, "times_week": 5},
    {"name": "Rodzice", "lat": 52.1311, "lng": 21.0657, "times_week": 1},
    {"name": "Siłownia", "lat": 52.2196, "lng": 21.0147, "times_week": 2},
]

# (tytuł, lat, lng, cena, czynsz, m², pokoje, rok, piętro, przybliżona, nowa)
OFFERS = [
    ("Jasne 2 pokoje przy metrze Politechnika", 52.2188, 21.0098, 4200, 650, 46, 2, 1965, "3", False, False),
    ("Kawalerka z balkonem, Muranów", 52.2441, 20.9935, 3300, 520, 31, 1, 1958, "4", False, True),
    ("Przestronne 3 pokoje, Stary Mokotów", 52.2034, 21.0172, 4900, 780, 64, 3, 1937, "2", False, False),
    ("2 pokoje w kamienicy, Powiśle", 52.2365, 21.0272, 4500, 600, 49, 2, 1912, "3", True, False),
    ("Nowoczesne mieszkanie, Wola, blisko Ronda Daszyńskiego", 52.2297, 20.9792, 4800, 900, 44, 2, 2019, "11", False, True),
    ("Cicha kawalerka na Ochocie", 52.2121, 20.9783, 2900, 450, 29, 1, 1972, "5", False, False),
    ("3 pokoje z widokiem na park, Mokotów", 52.1925, 21.0275, 4700, 820, 61, 3, 1978, "8", False, False),
    ("Mieszkanie 2-pokojowe, Ursynów, metro Imielin", 52.1494, 21.0451, 3600, 700, 48, 2, 1986, "6", False, True),
    ("Nowe 2 pokoje, Służewiec", 52.1801, 21.0049, 3800, 750, 42, 2, 2021, "7", False, False),
    ("Klimatyczna kawalerka, Saska Kępa", 52.2329, 21.0539, 3100, 480, 33, 1, 1960, "parter", True, False),
    ("2 pokoje przy Polu Mokotowskim", 52.2139, 20.9997, 4300, 690, 45, 2, 1968, "4", False, False),
    ("Mieszkanie z ogródkiem, Wilanów", 52.1633, 21.0832, 4600, 850, 57, 3, 2016, "parter", False, False),
    ("3 pokoje na Bielanach, metro Słodowiec", 52.2765, 20.9629, 4100, 720, 58, 3, 1981, "3", False, True),
    ("Kawalerka w apartamentowcu, Praga Północ", 52.2533, 21.0353, 3400, 600, 30, 1, 2018, "9", False, False),
    # kilka lokali w jednym budynku: na mapie wspólny znacznik
    ("2 pokoje w tym samym budynku, Mokotów", 52.1925, 21.0275, 5200, 950, 51, 2, 2019, "6", False, True),
    ("Kawalerka z widokiem na Morskie Oko", 52.1925, 21.0275, 3900, 800, 32, 1, 2019, "3", False, False),
    ("3 pokoje z tarasem, Mokotów", 52.1925, 21.0275, 6100, 1100, 66, 3, 2019, "12", False, False),
    ("Mieszkanie na wysokim piętrze, Mokotów", 52.1926, 21.0276, 4600, 880, 43, 2, 2019, "10", False, False),
    ("2 pokoje w kamienicy obok, Powiśle", 52.2365, 21.0272, 4400, 580, 47, 2, 1912, "2", True, False),
]

ADVERTISERS = ["osoba prywatna", "Biuro Nieruchomości Przykładowe", "Agencja Mieszkań Testowych",
               "osoba prywatna", "Lokale Wzorcowe sp. z o.o."]
WALL_COLORS = [("#e9e2d6", "#b9a68a"), ("#dfe6ea", "#9aa9b3"), ("#efe7dc", "#a88f6e"),
               ("#e4e9e0", "#8f9c86"), ("#f1ece4", "#c2a27c"), ("#e6e1ea", "#a397ab")]


def encode_polyline(points):
    """Format "encoded polyline" Google, taki jak w odpowiedziach Routes API."""
    out, last = [], (0, 0)
    for lat, lng in points:
        cur = (round(lat * 1e5), round(lng * 1e5))
        for delta in (cur[0] - last[0], cur[1] - last[1]):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        last = cur
    return "".join(out)


def distance_km(a, b):
    dx = (a[1] - b[1]) * 111.32 * math.cos(math.radians(a[0]))
    return math.hypot(dx, (a[0] - b[0]) * 110.54)


def wiggle(a, b, n=6, amount=0.0025):
    """Linia z a do b z lekkim zakrzywieniem, żeby trasa nie wyglądała jak od linijki."""
    sign = random.choice((-1, 1))
    pts = []
    for i in range(n + 1):
        t = i / n
        bend = math.sin(math.pi * t) * amount * sign
        pts.append((a[0] + (b[0] - a[0]) * t + bend, a[1] + (b[1] - a[1]) * t - bend))
    return pts


def toward(a, b, meters):
    d = distance_km(a, b) * 1000 or 1
    t = min(1, meters / d)
    return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t)


LINES = [("M1", "SUBWAY", "#0067b1", "#ffffff", ("Kabaty", "Młociny")),
         ("M2", "SUBWAY", "#c8102e", "#ffffff", ("Bemowo", "Bródno")),
         ("17", "TRAM", "#b45309", "#ffffff", ("Tarchomin Kościelny", "Woronicza")),
         ("15", "TRAM", "#b45309", "#ffffff", ("Marymont-Potok", "P+R Al. Krakowska")),
         ("523", "BUS", "#64748b", "#ffffff", ("PKP Olszynka Grochowska", "Bemowo-Ratusz")),
         ("128", "BUS", "#64748b", "#ffffff", ("Dworzec Zachodni", "Gocław")),
         ("S2", "COMMUTER_TRAIN", "#047857", "#ffffff", ("Warszawa Lotnisko Chopina", "Sulejówek Miłosna"))]
STOPS = ["Centrum", "Politechnika", "Rondo ONZ", "Plac Unii Lubelskiej", "Metro Wilanowska",
         "Dworzec Gdański", "Plac Zbawiciela", "Rondo Daszyńskiego", "Pole Mokotowskie", "Kabaty",
         "Stadion Narodowy", "Świętokrzyska", "Ratusz Arsenał", "Most Poniatowskiego"]


def route(origin, place, total_min, clock):
    """Wariant: pieszo, 1-2 przejazdy, pieszo; czasy sumują się do total_min."""
    rides = 1 if total_min < 22 else 2
    walk1, walk2 = random.randint(3, 7), random.randint(2, 6)
    ride_total = max(4, total_min - walk1 - walk2 - (3 if rides == 2 else 0))
    start = toward(origin, (place["lat"], place["lng"]), 350)
    end = toward((place["lat"], place["lng"]), origin, 300)
    mid = ((start[0] + end[0]) / 2 + random.uniform(-0.006, 0.006),
           (start[1] + end[1]) / 2 + random.uniform(-0.006, 0.006))
    hops = [start, end] if rides == 1 else [start, mid, end]
    segments = [{"mode": "walk", "seconds": walk1 * 60, "polylines": [encode_polyline(wiggle(origin, start, 3, 0.0004))]}]
    lines = random.sample(LINES, rides)
    names = random.sample(STOPS, rides + 1)
    h, m = 8, 60 - total_min - clock
    for i, (line, vehicle, color, text, ends) in enumerate(lines):
        minutes = ride_total // rides
        dep = f"{h + (m // 60):02d}:{m % 60:02d}"
        m += minutes
        arr = f"{h + (m // 60):02d}:{m % 60:02d}"
        segments.append({
            "mode": "transit", "seconds": minutes * 60, "line": line, "vehicle": vehicle,
            "color": color, "textColor": text, "headsign": random.choice(ends),
            "stops": max(1, minutes // 2), "from": names[i], "to": names[i + 1],
            "depart": f"2026-11-24T{dep}:00+01:00", "arrive": f"2026-11-24T{arr}:00+01:00",
            "polylines": [encode_polyline(wiggle(hops[i], hops[i + 1]))]})
        if i < rides - 1:
            segments.append({"mode": "walk", "seconds": 180, "polylines": []})
            m += 3
    segments.append({"mode": "walk", "seconds": walk2 * 60,
                     "polylines": [encode_polyline(wiggle(end, (place["lat"], place["lng"]), 3, 0.0004))]})
    return {"seconds": sum(s["seconds"] for s in segments), "segments": segments}


def svg_uri(svg):
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def room_photo(seed, variant):
    """Stylizowane wnętrze: ściana, podłoga, okno, sofa albo łóżko i roślina."""
    rnd = random.Random(seed * 10 + variant)
    wall, wood = WALL_COLORS[(seed + variant) % len(WALL_COLORS)]
    sofa = rnd.choice(["#5b6b7a", "#7a5b5b", "#4f6b58", "#8a7a5c", "#3f4a5a"])
    wx = rnd.randint(60, 360)
    furniture = (
        f'<rect x="{rnd.randint(60, 300)}" y="290" width="260" height="70" rx="14" fill="{sofa}"/>'
        f'<rect x="{rnd.randint(60, 300)}" y="255" width="260" height="45" rx="12" fill="{sofa}" opacity=".85"/>'
        if variant % 2 == 0 else
        f'<rect x="120" y="280" width="380" height="80" rx="8" fill="#f7f4ef"/>'
        f'<rect x="120" y="250" width="380" height="40" rx="8" fill="{sofa}"/>')
    return svg_uri(f"""<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480">
<rect width="640" height="480" fill="{wall}"/>
<rect y="360" width="640" height="120" fill="{wood}"/>
<g stroke="#00000014">{''.join(f'<line x1="0" y1="{360 + i * 24}" x2="640" y2="{360 + i * 24}"/>' for i in range(1, 5))}</g>
<rect x="{wx}" y="60" width="200" height="170" fill="#cfe3f1" stroke="#ffffff" stroke-width="10"/>
<line x1="{wx + 100}" y1="60" x2="{wx + 100}" y2="230" stroke="#ffffff" stroke-width="6"/>
<rect x="{wx - 20}" y="235" width="240" height="8" fill="#ffffff"/>
{furniture}
<rect x="540" y="300" width="40" height="60" fill="#b07b4f"/>
<circle cx="560" cy="275" r="38" fill="#4f7d4a"/><circle cx="545" cy="250" r="24" fill="#5f8f58"/>
</svg>""")


def offers():
    result = []
    for i, (title, lat, lng, price, rent, area, rooms, year, floor, approx, new) in enumerate(OFFERS):
        times = [max(9, round(distance_km((lat, lng), (p["lat"], p["lng"])) * 3.1 + random.randint(6, 12)))
                 for p in PLACES]
        photos = [room_photo(i, v) for v in range(4)]
        variants = []
        for place, minutes in zip(PLACES, times):
            options = sorted({minutes, minutes + random.randint(2, 6), minutes + random.randint(7, 12)})
            variants.append([route((lat, lng), place, t, random.randint(0, 6)) for t in options])
        times = [round(v[0]["seconds"] / 60) for v in variants]
        result.append({
            "routes": variants,
            "id": str(66000000 + i * 137), "times": times,
            "week": sum(2 * p["times_week"] * t for p, t in zip(PLACES, times)),
            "price": price, "rent": rent, "pricePerM2": round(price / area), "area": area, "rooms": rooms,
            "year": year, "floor": floor, "photo": photos[0], "advertiser": ADVERTISERS[i % len(ADVERTISERS)],
            "listed": f"2026-11-{random.randint(1, 17):02d}",
            "excerpt": "Fikcyjna oferta do zrzutu ekranu. Mieszkanie po remoncie, jasne, z dobrym dojazdem "
                       "do centrum. Blisko sklepy, przystanki i zieleń.",
            "details": {
                "floors": str(max(int(floor) if floor.isdigit() else 1, random.choice([4, 5, 10, 12]))),
                "status": random.choice(["do zamieszkania", "do odświeżenia"]),
                "market": "wtórny" if year < 2015 else "pierwotny",
                "building": random.choice(["blok", "kamienica", "apartamentowiec"]),
                "heating": random.choice(["miejskie", "gazowe"]), "ownership": None,
                "deposit": f"{price} zł", "freeFrom": "2026-12-01",
                "lift": int(floor) > 3 if floor.isdigit() else None,
                "extras": random.sample(["balkon", "piwnica", "oddzielna kuchnia", "garaż/miejsce parkingowe"], 2),
                "equipment": random.sample(["lodówka", "pralka", "zmywarka", "kuchenka", "meble", "telewizor"], 4),
                "photos": photos,
            },
            "isNew": new, "approximate": approx, "title": title,
            "link": f"https://example.com/oferta/{66000000 + i * 137}", "lat": lat, "lng": lng,
        })
    result.sort(key=lambda o: o["week"])
    for rank, offer in enumerate(result, start=1):
        offer["rank"] = rank
    return result


def nearby(all_offers):
    kinds = [("supermarket", "Supermarket Osiedlowy", 3), ("shop", "Sklep Spożywczy", 4),
             ("tram", "Przystanek", 3), ("gym", "Klub Fitness", 1), ("pharmacy", "Apteka", 2),
             ("parcel", "Paczkomat WAW", 3)]
    pois = []
    for offer in all_offers:
        for kind, name, count in kinds:
            for n in range(count):
                pois.append([kind, f"{name} {random.choice(STOPS)}" if kind != "parcel" else f"{name}{random.randint(10, 999):03d}M",
                             round(offer["lat"] + random.uniform(-0.007, 0.007), 5),
                             round(offer["lng"] + random.uniform(-0.011, 0.011), 5)])
    for name, lat, lng in [("Politechnika", 52.2190, 21.0158), ("Centrum", 52.2318, 21.0115),
                           ("Rondo Daszyńskiego", 52.2300, 20.9840), ("Imielin", 52.1494, 21.0456),
                           ("Słodowiec", 52.2766, 20.9606), ("Dworzec Wileński", 52.2547, 21.0349),
                           ("Pole Mokotowskie", 52.2085, 21.0080), ("Wilanowska", 52.1806, 21.0237)]:
        pois.append(["metro", name, lat, lng])
    for name, lat, lng in [("Warszawa Powiśle", 52.2398, 21.0322), ("Warszawa Stadion", 52.2443, 21.0473),
                           ("Warszawa Ochota", 52.2234, 20.9877)]:
        pois.append(["train", name, lat, lng])
    parks = []
    for name, lat, lng, r in [("Pole Mokotowskie", 52.2105, 20.9985, 0.006), ("Park Morskie Oko", 52.1960, 21.0255, 0.003),
                              ("Park Skaryszewski", 52.2415, 21.0545, 0.005), ("Ogród Krasińskich", 52.2470, 21.0020, 0.0025),
                              ("Park Kępa Potocka", 52.2740, 20.9755, 0.003)]:
        ring = [(round(lat + r * math.sin(a) * 0.62, 5), round(lng + r * math.cos(a), 5))
                for a in [k * math.pi / 8 for k in range(17)]]
        parks.append({"name": name, "rings": [ring]})
    return {"generated": "2026-11-10", "pois": pois, "parks": parks}


def main():
    all_offers = offers()
    data = {
        "generated": "2026-11-18 08:30",
        "summary": [
            "Ofert w wyszukiwaniu: 212. Pominięte przed liczeniem dojazdów: bez ceny: 6, rok budowy po 2027: 11.",
            f"W limitach dojazdu: {len(all_offers)} z 195 (nowych: {sum(o['isNew'] for o in all_offers)}).",
            "Google w tym miesiącu (licznik skryptu): 1 240 z 9 000 par (darmowo do 10 000).",
            "Google, trasy w tym miesiącu: 186 z 9 000 zapytań (osobna pula, darmowo do 10 000).",
        ],
        "places": [{"name": p["name"], "lat": p["lat"], "lng": p["lng"]} for p in PLACES],
        "offers": all_offers,
    }
    (HERE / "wyniki.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    (HERE / "okolica.json").write_text(json.dumps(nearby(all_offers), ensure_ascii=False), encoding="utf-8")
    mapa.DATA_FILE, mapa.NEARBY_FILE, mapa.MAP_FILE = HERE / "wyniki.json", HERE / "okolica.json", HERE / "mapa.html"
    mapa.webbrowser.open = lambda *_: None
    mapa.ZONES_FILE = HERE / "wykluczenia.json"
    mapa.main(serve_page=False)


if __name__ == "__main__":
    main()
