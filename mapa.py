#!/usr/bin/env python3
"""
Mapa ofert: czyta wyniki.json zapisany przez dojazdy.py i tworzy mapa.html,
czyli listę ofert obok mapy z Twoimi miejscami. Niczego nie pobiera.
Jeśli jest okolica.json (z okolica.py), wkleja też sklepy, przystanki i parki
z okolicy ofert, a strona sama liczy, co jest najbliżej wybranej oferty.

Uruchomienie: python mapa.py (otworzy stronę w przeglądarce)
"""

import json
import sys
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "wyniki.json"
NEARBY_FILE = HERE / "okolica.json"
MAP_FILE = HERE / "mapa.html"

TEMPLATE = r"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Mieszkania według dojazdu</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Barlow:wght@400;500;600&display=swap">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"
      integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=" crossorigin="">
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"
        integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=" crossorigin=""></script>
<style>
  :root {
    --variant-bg: #dbe8f4;
    --bg: #f3f5f7;
    --surface: #ffffff;
    --text: #1b2430;
    --muted: #5d6876;
    --rule: #dce1e6;
    --signal: #ffc400;
    --on-signal: #1b2430;
    --active-bg: #eaf2f9;
    --link: #0067b1;
    --focus: #0067b1;
    --new: #c8102e;
    color-scheme: light;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #12161b;
      --surface: #181d24;
      --text: #e6eaef;
      --muted: #9aa5b1;
      --rule: #29313b;
      --on-signal: #12161b;
      --active-bg: #1f2a36;
      --link: #7cc0f5;
      --focus: #7cc0f5;
      --new: #ff7a7a;
      --variant-bg: #26394d;
      color-scheme: dark;
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; margin: 0; }
  body {
    display: flex;
    font: 15px/1.45 "Barlow", "Segoe UI", system-ui, sans-serif;
    font-variant-numeric: tabular-nums;
    color: var(--text);
    background: var(--bg);
  }
  .panel {
    width: 400px;
    flex: none;
    display: flex;
    flex-direction: column;
    background: var(--surface);
    border-right: 1px solid var(--rule);
  }
  #map { flex: 1; }
  header { padding: 16px 18px 14px; border-bottom: 1px solid var(--rule); }
  h1 { margin: 0; font-size: 21px; line-height: 1.2; font-weight: 600; }
  .stamp { margin: 2px 0 12px; font-size: 13px; color: var(--muted); }
  .filters { display: flex; flex-wrap: wrap; gap: 6px; }
  .filters button {
    font: inherit;
    font-size: 14px;
    padding: 4px 11px;
    border-radius: 999px;
    border: 1px solid var(--rule);
    background: transparent;
    color: var(--text);
    cursor: pointer;
  }
  .filters button[aria-pressed="true"] { background: var(--text); border-color: var(--text); color: var(--surface); }
  .filters .count { margin-left: 5px; opacity: .75; }
  .hint { margin: 10px 0 0; font-size: 13px; color: var(--muted); }
  details { margin-top: 8px; font-size: 13px; color: var(--muted); }
  summary { cursor: pointer; }
  details ul { margin: 6px 0 0; padding-left: 18px; }
  .list { flex: 1; min-height: 0; overflow-y: auto; margin: 0; padding: 0; list-style: none; }
  .empty { margin: 0; padding: 18px; color: var(--muted); }
  .offer { position: relative; padding: 12px 16px 12px 12px; border-bottom: 1px solid var(--rule); border-left: 4px solid transparent; }
  .offer.selected { border-left-color: var(--signal); }
  .offer.active { background: var(--active-bg); }
  .show {
    all: unset;
    box-sizing: border-box;
    width: 100%;
    display: grid;
    grid-template-columns: 30px 1fr;
    column-gap: 10px;
    row-gap: 4px;
    cursor: pointer;
  }
  .show > :not(.rank) { grid-column: 2; }
  .show:focus-visible, .filters button:focus-visible, .actions a:focus-visible, .pick input:focus-visible {
    outline: 2px solid var(--focus);
    outline-offset: 3px;
    border-radius: 4px;
  }
  .rank {
    grid-column: 1;
    grid-row: 1 / span 6;
    width: 28px;
    height: 28px;
    border-radius: 50%;
    display: grid;
    place-items: center;
    font-size: 13px;
    font-weight: 600;
    background: var(--text);
    color: var(--surface);
  }
  .selected .rank { background: var(--signal); color: var(--on-signal); }
  .week { padding-right: 84px; font-size: 19px; line-height: 1.25; font-weight: 600; }
  .week .per { margin-left: 6px; font-size: 13px; font-weight: 400; color: var(--muted); }
  .lines { display: flex; flex-wrap: wrap; gap: 4px; }
  .line {
    padding: 1px 7px;
    border-radius: 4px;
    font-size: 12.5px;
    font-weight: 500;
    white-space: nowrap;
    color: #fff;
    background: var(--line);
  }
  .facts { display: flex; flex-wrap: wrap; column-gap: 12px; font-size: 14px; }
  .price { font-weight: 600; }
  .title {
    font-size: 13.5px;
    color: var(--muted);
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }
  .badges { display: flex; flex-wrap: wrap; gap: 6px; }
  .badge { padding: 0 6px; border: 1px solid var(--rule); border-radius: 4px; font-size: 12px; color: var(--muted); }
  .badge.new { border-color: var(--new); color: var(--new); }
  .actions { display: flex; flex-wrap: wrap; align-items: center; gap: 4px 16px; margin: 8px 0 0 40px; font-size: 13.5px; }
  .actions a { color: var(--link); }
  .pick { position: absolute; top: 14px; right: 14px; display: inline-flex; align-items: center; gap: 6px; font-size: 13.5px; cursor: pointer; }
  .pick input { width: 16px; height: 16px; margin: 0; accent-color: var(--signal); }

  .leaflet-container { font: 14px/1.4 "Barlow", "Segoe UI", system-ui, sans-serif; }
  .marker {
    position: relative;
    display: grid;
    place-items: center;
    width: 26px;
    height: 26px;
    border-radius: 50%;
    border: 2px solid #fff;
    background: #1b2430;
    color: #fff;
    font: 600 12px/1 "Barlow", system-ui, sans-serif;
    box-shadow: 0 1px 4px rgb(0 0 0 / .35);
  }
  .marker.selected { background: #ffc400; color: #1b2430; }
  .marker.approximate { box-shadow: 0 0 0 5px rgb(27 36 48 / .22), 0 1px 4px rgb(0 0 0 / .35); }
  .marker.new::after {
    content: "";
    position: absolute;
    top: -4px;
    right: -4px;
    width: 9px;
    height: 9px;
    border-radius: 50%;
    border: 2px solid #fff;
    background: #c8102e;
  }
  .marker.active { transform: scale(1.2); box-shadow: 0 0 0 3px #0067b1, 0 1px 4px rgb(0 0 0 / .35); }
  .station {
    display: block;
    width: 18px;
    height: 18px;
    border-radius: 50%;
    border: 5px solid var(--line);
    background: #fff;
    box-shadow: 0 1px 4px rgb(0 0 0 / .4);
  }
  .leaflet-tooltip.station-label { padding: 0; border: 0; background: none; box-shadow: none; }
  .leaflet-tooltip.station-label::before { display: none; }
  .station-name {
    display: inline-block;
    padding: 3px 7px;
    border-radius: 4px;
    font: 600 13px/1.2 "Barlow", system-ui, sans-serif;
    color: #fff;
    background: var(--line);
    box-shadow: 0 1px 3px rgb(0 0 0 / .3);
  }
  .popup { display: grid; gap: 4px; }
  .popup-title { font-weight: 600; color: #0067b1; }
  .popup .lines { margin: 2px 0; }
  .poi {
    display: grid;
    place-items: center;
    width: 24px;
    height: 24px;
    border-radius: 6px;
    border: 1.5px solid var(--poi);
    background: #fff;
    color: var(--poi);
    font: 700 14px/1 "Barlow", system-ui, sans-serif;
    box-shadow: 0 1px 3px rgb(0 0 0 / .3);
  }
  .poi svg, .near-icon svg { width: 15px; height: 15px; }
  .trips, .details, .nearby { margin: 10px 0 2px 40px; padding-top: 10px; border-top: 1px solid var(--rule); }
  .section-note { margin-left: 6px; font-size: 13px; font-weight: 400; color: var(--muted); }
  .trip + .trip { margin-top: 10px; }
  .trip-place { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin: 0 0 2px; }
  .more {
    padding: 0;
    border: 0;
    background: none;
    color: var(--link);
    font: inherit;
    font-size: 12.5px;
    text-decoration: underline;
    cursor: pointer;
  }
  .more:focus-visible { outline: 2px solid var(--focus); outline-offset: 2px; border-radius: 2px; }
  .trip-empty { margin: 0; font-size: 13px; color: var(--muted); }
  .variants { display: grid; gap: 2px; margin: 0; padding: 0; list-style: none; }
  .variant {
    all: unset;
    box-sizing: border-box;
    width: 100%;
    display: grid;
    grid-template-columns: 54px 1fr auto;
    align-items: center;
    column-gap: 8px;
    padding: 4px 6px;
    border-radius: 4px;
    font-size: 13.5px;
    cursor: pointer;
  }
  .variant:hover, .variant[aria-pressed="true"] { background: var(--variant-bg); }
  .variant:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
  .variant-time { font-weight: 600; }
  .legs { display: flex; flex-wrap: wrap; align-items: center; gap: 3px; min-width: 0; }
  .ride { padding: 0 6px; border-radius: 4px; font-size: 12.5px; font-weight: 600; line-height: 20px; color: var(--ride-text); background: var(--ride); }
  .walk { display: inline-flex; align-items: center; gap: 1px; font-size: 12.5px; color: var(--muted); }
  .walk svg { width: 13px; height: 13px; }
  .sep { color: var(--muted); }
  .variant-clock { font-size: 12.5px; color: var(--muted); white-space: nowrap; }
  .steps { display: grid; gap: 5px; margin: 4px 0 8px; padding: 0 6px; list-style: none; font-size: 13px; }
  .steps[hidden] { display: none; }  /* display: grid wyżej wyłączyłby atrybut hidden */
  .steps li { display: grid; grid-template-columns: 52px 1fr; column-gap: 8px; align-items: start; }
  .step-mark { justify-self: start; }
  .step-detail { display: block; color: var(--muted); }
  .section-title { margin: 0 0 6px; font-size: 14px; font-weight: 600; }
  .photo-link { display: block; margin-bottom: 8px; }
  .photo { display: block; width: 100%; height: 170px; object-fit: cover; border-radius: 6px; background: var(--rule); }
  .facts-list { display: grid; grid-template-columns: max-content 1fr; gap: 2px 12px; margin: 0; font-size: 13.5px; }
  .facts-list dt { color: var(--muted); }
  .facts-list dd { margin: 0; }
  .chips { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 8px; }
  .chip { padding: 1px 7px; border: 1px solid var(--rule); border-radius: 4px; background: var(--surface); font-size: 12.5px; }
  .excerpt { margin: 8px 0 0; font-size: 13px; color: var(--muted); }
  .nearby-status, .nearby-note { margin: 0; font-size: 13px; color: var(--muted); }
  .nearby-note { margin-top: 6px; }
  .nearby-note a { color: var(--link); }
  .near-list { display: grid; gap: 1px; margin: 0; padding: 0; list-style: none; }
  .near-item {
    all: unset;
    box-sizing: border-box;
    width: 100%;
    display: grid;
    grid-template-columns: 22px auto 1fr auto;
    align-items: center;
    column-gap: 8px;
    padding: 3px 4px;
    border-radius: 4px;
    font-size: 13.5px;
    cursor: pointer;
  }
  .near-item:hover { background: var(--active-bg); }
  .near-item:focus-visible { outline: 2px solid var(--focus); outline-offset: 1px; }
  .near-icon {
    width: 22px;
    height: 22px;
    display: grid;
    place-items: center;
    border-radius: 5px;
    border: 1.5px solid var(--poi);
    background: #fff;
    color: var(--poi);
    font-size: 13px;
    font-weight: 700;
  }
  .near-icon svg { width: 14px; height: 14px; }
  .near-label { font-weight: 600; }
  .near-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--muted); }
  .near-distance { white-space: nowrap; }

  @media (max-width: 760px) {
    .leaflet-control-attribution { font-size: 10px; }
    html, body { height: auto; }
    body { flex-direction: column; }
    #map { order: -1; flex: none; height: 55vh; }
    .panel { width: auto; border-right: 0; }
    .list { overflow: visible; }
  }
</style>
</head>
<body>
<aside class="panel">
  <header>
    <h1>Mieszkania według dojazdu</h1>
    <p class="stamp" id="stamp"></p>
    <div class="filters" role="group" aria-label="Pokaż oferty">
      <button type="button" data-filter="all" aria-pressed="true">Wszystkie<span class="count" id="count-all"></span></button>
      <button type="button" data-filter="selected" aria-pressed="false">Zaznaczone<span class="count" id="count-selected"></span></button>
      <button type="button" data-filter="new" aria-pressed="false">Nowe<span class="count" id="count-new"></span></button>
    </div>
    <p class="hint">Kliknij ofertę, żeby pokazać ją na mapie razem z okolicą: sklepami, przystankami, parkami. Niebieski krąg ma promień 500 m, czyli ok. 6 minut pieszo.</p>
    <details>
      <summary>Podsumowanie wyszukiwania</summary>
      <ul id="summary"></ul>
    </details>
  </header>
  <p class="empty" id="empty" hidden></p>
  <ol class="list" id="list"></ol>
</aside>
<main id="map" aria-label="Mapa ofert i Twoich miejsc"></main>

<script id="data" type="application/json">__DATA__</script>
<script id="nearby" type="application/json">__NEARBY__</script>
<script>
const data = JSON.parse(document.getElementById("data").textContent);
const LINE_COLORS = ["#0067b1", "#c8102e", "#007a4d", "#7b3f98", "#b45309", "#00737d"];
const STORAGE_KEY = "mieszkania-wedlug-dojazdu:zaznaczone";
const EMPTY = {
  all: "Brak ofert spełniających kryteria. Zmień wyszukiwanie lub filtry w config.toml i uruchom dojazdy.py ponownie.",
  selected: "Nie zaznaczono jeszcze żadnej oferty. Zaznacz oferty w widoku Wszystkie, a pojawią się tutaj.",
  new: "Od poprzedniego uruchomienia nie pojawiły się nowe oferty.",
};
const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const numbers = new Intl.NumberFormat("pl-PL");
// Ikony: Lucide (https://lucide.dev), licencja ISC, Copyright (c) Lucide Contributors
const ICONS = {"cart": "<path d=\"m2.05 2.05 1.099-.028a1 1 0 0 1 1.008.815l2.69 14.347A1 1 0 0 0 7.83 18H18\" /> <path d=\"M4.563 5h16.435a1 1 0 0 1 .981 1.204l-1.026 6.226A2 2 0 0 1 18.962 14H6.25\" /> <circle cx=\"18\" cy=\"20\" r=\"2\" /> <circle cx=\"8\" cy=\"20\" r=\"2\" />", "store": "<path d=\"M15 21v-5a1 1 0 0 0-1-1h-4a1 1 0 0 0-1 1v5\" /> <path d=\"M17.774 10.31a1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.451 0 1.12 1.12 0 0 0-1.548 0 2.5 2.5 0 0 1-3.452 0 1.12 1.12 0 0 0-1.549 0 2.5 2.5 0 0 1-3.77-3.248l2.889-4.184A2 2 0 0 1 7 2h10a2 2 0 0 1 1.653.873l2.895 4.192a2.5 2.5 0 0 1-3.774 3.244\" /> <path d=\"M4 10.95V19a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-8.05\" />", "dumbbell": "<path d=\"M17.596 12.768a2 2 0 1 0 2.829-2.829l-1.768-1.767a2 2 0 0 0 2.828-2.829l-2.828-2.828a2 2 0 0 0-2.829 2.828l-1.767-1.768a2 2 0 1 0-2.829 2.829z\" /> <path d=\"m2.5 21.5 1.4-1.4\" /> <path d=\"m20.1 3.9 1.4-1.4\" /> <path d=\"M5.343 21.485a2 2 0 1 0 2.829-2.828l1.767 1.768a2 2 0 1 0 2.829-2.829l-6.364-6.364a2 2 0 1 0-2.829 2.829l1.768 1.767a2 2 0 0 0-2.828 2.829z\" /> <path d=\"m9.6 14.4 4.8-4.8\" />", "trees": "<path d=\"M10 10v.2A3 3 0 0 1 8.9 16H5a3 3 0 0 1-1-5.8V10a3 3 0 0 1 6 0Z\" /> <path d=\"M7 16v6\" /> <path d=\"M13 19v3\" /> <path d=\"M12 19h8.3a1 1 0 0 0 .7-1.7L18 14h.3a1 1 0 0 0 .7-1.7L16 9h.2a1 1 0 0 0 .8-1.7L13 3l-1.4 1.5\" />", "train": "<path d=\"M8 3.1V7a4 4 0 0 0 8 0V3.1\" /> <path d=\"m9 15-1-1\" /> <path d=\"m15 15 1-1\" /> <path d=\"M9 19c-2.8 0-5-2.2-5-5v-4a8 8 0 0 1 16 0v4c0 2.8-2.2 5-5 5Z\" /> <path d=\"m8 19-2 3\" /> <path d=\"m16 19 2 3\" />", "tram": "<rect width=\"16\" height=\"16\" x=\"4\" y=\"3\" rx=\"2\" /> <path d=\"M4 11h16\" /> <path d=\"M12 3v8\" /> <path d=\"m8 19-2 3\" /> <path d=\"m18 22-2-3\" /> <path d=\"M8 15h.01\" /> <path d=\"M16 15h.01\" />", "pill": "<path d=\"m10.5 20.5 10-10a4.95 4.95 0 1 0-7-7l-10 10a4.95 4.95 0 1 0 7 7Z\" /> <path d=\"m8.5 8.5 7 7\" />", "package": "<path d=\"M11 21.73a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73z\" /> <path d=\"M12 22V12\" /> <polyline points=\"3.29 7 12 12 20.71 7\" /> <path d=\"m7.5 4.27 9 5.15\" />", "walk": "<path d=\"M4 16v-2.38C4 11.5 2.97 10.5 3 8c.03-2.72 1.49-6 4.5-6C9.37 2 10 3.8 10 5.5c0 3.11-2 5.66-2 8.68V16a2 2 0 1 1-4 0Z\" /> <path d=\"M20 20v-2.38c0-2.12 1.03-3.12 1-5.62-.03-2.72-1.49-6-4.5-6C14.63 6 14 7.8 14 9.5c0 3.11 2 5.66 2 8.68V20a2 2 0 1 0 4 0Z\" /> <path d=\"M16 17h4\" /> <path d=\"M4 13h4\" />"};
const POI_TYPES = [  // rodzaje miejsc z okolica.json (rozpoznaje je okolica.py)
  { key: "supermarket", label: "Supermarket", color: "#c2410c", icon: "cart" },
  { key: "shop", label: "Sklep spożywczy", color: "#9a3412", icon: "store" },
  { key: "metro", label: "Metro", color: "#c8102e", icon: null },
  { key: "train", label: "Kolej", color: "#0067b1", icon: "train" },
  { key: "tram", label: "Tramwaj", color: "#b45309", icon: "tram" },
  { key: "park", label: "Park", color: "#2e7d32", icon: "trees" },
  { key: "gym", label: "Siłownia", color: "#7b3f98", icon: "dumbbell" },
  { key: "pharmacy", label: "Apteka", color: "#00737d", icon: "pill" },
  { key: "parcel", label: "Paczkomat", color: "#5d6876", icon: "package" },
];
const TYPE_BY_KEY = Object.fromEntries(POI_TYPES.map(type => [type.key, type]));
const NEAR_RADIUS = 1000;
const RAIL_RADIUS = 2000;
const nearbyData = JSON.parse(document.getElementById("nearby").textContent);
for (const park of nearbyData?.parks || []) {  // prostokąt otaczający: szybkie pomijanie dalekich parków
  const points = park.rings.flat();
  park.box = [Math.min(...points.map(p => p[0])), Math.max(...points.map(p => p[0])),
              Math.min(...points.map(p => p[1])), Math.max(...points.map(p => p[1]))];
}

data.places.forEach((place, i) => { place.color = LINE_COLORS[i % LINE_COLORS.length]; });
const byId = new Map(data.offers.map(offer => [offer.id, offer]));
const markers = new Map();
const items = new Map();
let selected = loadSelected();
let filter = "all";
let activeId = null;

function loadSelected() {
  try { return new Set(JSON.parse(localStorage.getItem(STORAGE_KEY)) || []); } catch { return new Set(); }
}
function saveSelected() {
  try { localStorage.setItem(STORAGE_KEY, JSON.stringify([...selected])); } catch { /* zapis niedostępny */ }
}
function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}
function duration(minutes) {
  const h = Math.floor(minutes / 60), m = Math.round(minutes % 60);
  return h ? `${h} h ${String(m).padStart(2, "0")} min` : `${m} min`;
}
function roomsText(n) {
  if (typeof n !== "number") return String(n);
  const last = n % 10, lastTwo = n % 100;
  const word = n === 1 ? "pokój" : (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) ? "pokoje" : "pokoi";
  return `${n} ${word}`;
}
function priceText(offer) {
  const price = `${numbers.format(offer.price)} zł`;
  return offer.rent ? `${price}, czynsz ${numbers.format(offer.rent)} zł` : price;
}
function link(text, href) {
  const a = el("a", null, text);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener";
  return a;
}
function linesFor(offer) {
  const lines = el("span", "lines");
  data.places.forEach((place, i) => {
    const line = el("span", "line", `${place.name} ${offer.times[i]} min`);
    line.style.setProperty("--line", place.color);
    lines.append(line);
  });
  return lines;
}

const map = L.map("map");
const streets = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19, maxNativeZoom: 18,
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, DeLorme, NAVTEQ, USGS, Intermap, iPC, NRCAN, Esri Japan, METI, Esri China (Hong Kong), Esri (Thailand), TomTom, 2012" }
).addTo(map);
const imagery = L.tileLayer(
  "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
  { maxZoom: 19,
    attribution: "Tiles &copy; Esri &mdash; Source: Esri, i-cubed, USDA, USGS, AEX, GeoEye, Getmapping, Aerogrid, IGN, IGP, UPR-EGP, and the GIS User Community" }
);
L.control.layers({ "Mapa": streets, "Zdjęcia satelitarne": imagery }).addTo(map);
L.control.scale({ imperial: false }).addTo(map);
const walkCircle = L.circle([0, 0], { radius: 500, color: "#0067b1", weight: 1.5, dashArray: "5 5", fillOpacity: 0.07, interactive: false });

for (const place of data.places) {
  const icon = L.divIcon({ className: "", html: `<span class="station" style="--line:${place.color}"></span>`,
                           iconSize: [18, 18], iconAnchor: [9, 9] });
  const label = el("span", "station-name", place.name);
  label.style.setProperty("--line", place.color);
  L.marker([place.lat, place.lng], { icon, title: place.name, keyboard: false, zIndexOffset: 1000 })
    .bindTooltip(label, { permanent: true, direction: "right", offset: [12, 0], className: "station-label" })
    .addTo(map);
}

const offerLayer = L.layerGroup().addTo(map);
const poiLayer = L.layerGroup().addTo(map);
function markerIcon(offer) {
  const classes = ["marker"];
  if (selected.has(offer.id)) classes.push("selected");
  if (offer.approximate) classes.push("approximate");
  if (offer.isNew) classes.push("new");
  if (offer.id === activeId) classes.push("active");
  return L.divIcon({ className: "", html: `<span class="${classes.join(" ")}">${Number(offer.rank)}</span>`,
                     iconSize: [26, 26], iconAnchor: [13, 13], popupAnchor: [0, -14] });
}
function popupFor(offer) {
  const title = link(offer.title, offer.link);
  title.className = "popup-title";
  const box = el("div", "popup");
  box.append(title, el("span", null, `${duration(offer.week)} w drodze tygodniowo`),
             linesFor(offer), el("span", null, priceText(offer)));
  return box;
}
for (const offer of data.offers) {
  const marker = L.marker([offer.lat, offer.lng], { icon: markerIcon(offer), title: `${offer.rank}. ${offer.title}`, riseOnHover: true });
  marker.bindPopup(() => popupFor(offer), { maxWidth: 280, autoPanPadding: [30, 30] });
  marker.on("click", () => activate(offer.id, { fromMap: true }));
  markers.set(offer.id, marker);
}

const nearbyCache = new Map();  // id oferty -> najbliższe miejsca według rodzaju
let osmCredited = false;

function projector(origin) {  // metry względem oferty; dokładność wystarczy na kilka km
  const kx = 111320 * Math.cos(origin.lat * Math.PI / 180);
  return (lat, lng) => [(lng - origin.lng) * kx, (lat - origin.lat) * 110540];
}
function segmentDistance([ax, ay], [bx, by]) {  // od oferty (0, 0) do odcinka AB
  const dx = bx - ax, dy = by - ay, length = dx * dx + dy * dy;
  const t = length ? Math.max(0, Math.min(1, -(ax * dx + ay * dy) / length)) : 0;
  return Math.hypot(ax + t * dx, ay + t * dy);
}
function containsOrigin(ring) {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i], [xj, yj] = ring[j];
    if ((yi > 0) !== (yj > 0) && 0 < (xj - xi) * (0 - yi) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

function computeNearby(offer) {
  if (nearbyCache.has(offer.id)) return nearbyCache.get(offer.id);
  const project = projector(offer);
  const groups = Object.fromEntries(POI_TYPES.map(type => [type.key, []]));
  for (const [kind, name, lat, lng] of nearbyData.pois) {
    const radius = kind === "metro" || kind === "train" ? RAIL_RADIUS : NEAR_RADIUS;
    if (!groups[kind] || Math.abs(lat - offer.lat) * 110540 > radius) continue;
    const [x, y] = project(lat, lng);
    const distance = Math.hypot(x, y);
    if (distance <= radius) groups[kind].push({ name: name || TYPE_BY_KEY[kind].label, lat, lng, distance });
  }
  const dLat = NEAR_RADIUS / 110540, dLng = NEAR_RADIUS / (111320 * Math.cos(offer.lat * Math.PI / 180));
  for (const park of nearbyData.parks) {
    const [south, north, west, east] = park.box;
    if (offer.lat < south - dLat || offer.lat > north + dLat || offer.lng < west - dLng || offer.lng > east + dLng) continue;
    let distance = Infinity;
    for (const ring of park.rings) {  // do granicy parku, nie do środka; w środku parku: 0
      const xy = ring.map(([lat, lng]) => project(lat, lng));
      for (let i = 1; i < xy.length; i++) distance = Math.min(distance, segmentDistance(xy[i - 1], xy[i]));
      if (containsOrigin(xy)) distance = 0;
    }
    if (distance <= NEAR_RADIUS) groups.park.push({ name: park.name || "Park", distance, shapes: park.rings });
  }
  for (const list of Object.values(groups)) list.sort((a, b) => a.distance - b.distance);
  nearbyCache.set(offer.id, groups);
  return groups;
}

const clock = new Intl.DateTimeFormat("pl-PL", { hour: "2-digit", minute: "2-digit", timeZone: "Europe/Warsaw" });
const VEHICLES = {  // nazwa i kolor zastępczy, gdy Google nie poda koloru linii
  BUS: ["Autobus", "#64748b"], INTERCITY_BUS: ["Autobus", "#64748b"], TROLLEYBUS: ["Trolejbus", "#64748b"],
  TRAM: ["Tramwaj", "#b45309"], SUBWAY: ["Metro", "#0067b1"], METRO_RAIL: ["Metro", "#0067b1"],
  RAIL: ["Pociąg", "#047857"], COMMUTER_TRAIN: ["Pociąg", "#047857"], HEAVY_RAIL: ["Pociąg", "#047857"],
  LONG_DISTANCE_TRAIN: ["Pociąg", "#047857"], HIGH_SPEED_TRAIN: ["Pociąg", "#047857"], FERRY: ["Prom", "#0e7490"],
};
const routeLayer = L.layerGroup().addTo(map);
let pinned = null;  // przypięty wariant: { offerId, place, index }
let previewing = null;  // wariant pokazany po najechaniu kursorem
// po wyborze oferty lista się przewija i wariant może "wjechać" pod nieruchomy kursor:
// takie najechanie bez ruchu myszą nie powinno rysować trasy
let previewBlockedUntil = 0;

function decodePolyline(encoded) {  // format "encoded polyline" Google
  const points = [];
  let index = 0, lat = 0, lng = 0;
  while (index < encoded.length) {
    for (const axis of [0, 1]) {
      let shift = 0, result = 0, byte;
      do {
        byte = encoded.charCodeAt(index++) - 63;
        result |= (byte & 0x1f) << shift;
        shift += 5;
      } while (byte >= 0x20);
      const delta = result & 1 ? ~(result >> 1) : result >> 1;
      if (axis === 0) lat += delta; else lng += delta;
    }
    points.push([lat / 1e5, lng / 1e5]);
  }
  return points;
}
function rideColor(segment) {
  return segment.color || VEHICLES[segment.vehicle]?.[1] || "#1b2430";
}
function stopsText(n) {
  const last = n % 10, lastTwo = n % 100;
  const word = n === 1 ? "przystanek" : (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) ? "przystanki" : "przystanków";
  return `${n} ${word}`;
}
function variantsText(n) {
  const last = n % 10, lastTwo = n % 100;
  const word = n === 1 ? "wariant" : (last >= 2 && last <= 4 && !(lastTwo >= 12 && lastTwo <= 14)) ? "warianty" : "wariantów";
  return `${n} ${word}`;
}
function minutes(seconds) {
  return Math.max(1, Math.round(seconds / 60));
}
function variantClock(route) {  // wyjście z domu i dotarcie na miejsce
  const segments = route.segments;
  const rides = segments.filter(s => s.mode === "transit" && s.depart && s.arrive);
  if (!rides.length) return null;
  const first = segments.indexOf(rides[0]), last = segments.indexOf(rides.at(-1));
  const before = segments.slice(0, first).reduce((sum, s) => sum + s.seconds, 0);
  const after = segments.slice(last + 1).reduce((sum, s) => sum + s.seconds, 0);
  const start = new Date(Date.parse(rides[0].depart) - before * 1000);
  const end = new Date(Date.parse(rides.at(-1).arrive) + after * 1000);
  return `${clock.format(start)}–${clock.format(end)}`;
}
function rideBadge(segment) {
  const badge = el("span", "ride", segment.line || VEHICLES[segment.vehicle]?.[0] || "?");
  badge.style.setProperty("--ride", rideColor(segment));
  badge.style.setProperty("--ride-text", segment.textColor || "#fff");
  return badge;
}
function walkBadge(seconds) {
  const walk = el("span", "walk");
  walk.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
    stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS.walk}</svg>`;
  walk.append(String(minutes(seconds)));
  return walk;
}
function describe(route) {  // dla czytników ekranu
  const parts = route.segments.map(s => s.mode === "walk" ? `pieszo ${minutes(s.seconds)} min`
    : `${(VEHICLES[s.vehicle]?.[0] || "linia").toLowerCase()} ${s.line}`);
  const when = variantClock(route);
  return `${minutes(route.seconds)} min: ${parts.join(", ")}${when ? `, ${when}` : ""}`;
}

function drawRoute(route) {
  routeLayer.clearLayers();
  const points = [];
  for (const segment of route.segments) {
    const lines = segment.polylines.map(decodePolyline);
    for (const line of lines) {
      points.push(...line);
      if (segment.mode === "walk") {
        L.polyline(line, { color: "#5d6876", weight: 4, dashArray: "1 8", lineCap: "round", interactive: false }).addTo(routeLayer);
      } else {
        L.polyline(line, { color: "#1b2430", weight: 9, opacity: 0.35, interactive: false }).addTo(routeLayer);
        L.polyline(line, { color: rideColor(segment), weight: 5, interactive: false }).addTo(routeLayer);
      }
    }
    if (segment.mode === "transit" && lines.length) {
      for (const [point, name] of [[lines[0][0], segment.from], [lines.at(-1).at(-1), segment.to]]) {
        L.circleMarker(point, { radius: 5, color: rideColor(segment), weight: 3, fillColor: "#fff", fillOpacity: 1 })
          .bindTooltip(el("span", null, name || ""), { direction: "top" }).addTo(routeLayer);
      }
    }
  }
  return points;
}
function routeAt(offer, place, index) {
  return offer.routes?.[place]?.[index];
}
function restoreRoute() {  // po zjechaniu kursorem: przypięty wariant albo nic
  previewing = null;
  const offer = pinned && pinned.offerId === activeId ? byId.get(pinned.offerId) : null;
  if (offer) drawRoute(routeAt(offer, pinned.place, pinned.index)); else routeLayer.clearLayers();
}
function updatePins(section) {
  for (const button of section.querySelectorAll(".variant")) {
    const on = Boolean(pinned && pinned.offerId === activeId
      && Number(button.dataset.place) === pinned.place && Number(button.dataset.index) === pinned.index);
    button.setAttribute("aria-pressed", String(on));
    button.nextElementSibling.hidden = !on;
  }
}
function togglePin(offer, place, index, section) {
  const same = pinned && pinned.offerId === offer.id && pinned.place === place && pinned.index === index;
  pinned = same ? null : { offerId: offer.id, place, index };
  updatePins(section);
  if (!pinned) { routeLayer.clearLayers(); return; }
  const points = drawRoute(routeAt(offer, place, index));
  if (points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 16 });
}

function stepsList(route) {
  const list = el("ol", "steps");
  list.hidden = true;
  for (const segment of route.segments) {
    const item = el("li");
    if (segment.mode === "walk") {
      item.append(walkBadge(segment.seconds), el("span", null, `Pieszo ${minutes(segment.seconds)} min`));
    } else {
      const text = el("span", null, [VEHICLES[segment.vehicle]?.[0], segment.line].filter(Boolean).join(" ")
        + (segment.headsign ? `, kierunek ${segment.headsign}` : ""));
      const times = (when, iso) => iso ? `${when} ${clock.format(new Date(iso))}` : when;
      const detail = `${times(segment.from || "?", segment.depart)} → ${times(segment.to || "?", segment.arrive)}`
        + (segment.stops ? `, ${stopsText(segment.stops)}` : "");
      text.append(el("span", "step-detail", detail));
      const mark = rideBadge(segment);
      mark.classList.add("step-mark");
      item.append(mark, text);
    }
    list.append(item);
  }
  return list;
}

function routesSection(offer) {
  const section = el("section", "trips");
  const title = el("p", "section-title", "Dojazdy");
  title.append(el("span", "section-note", "przyjazd we wtorek na 9:00"));
  section.append(title);
  data.places.forEach((place, placeIndex) => {
    const trip = el("div", "trip");
    const name = el("span", "line", place.name);
    name.style.setProperty("--line", place.color);
    const header = el("div", "trip-place");
    header.append(name);
    trip.append(header);
    const routes = offer.routes?.[placeIndex];
    if (!routes || !routes.length) {
      trip.append(el("p", "trip-empty", routes ? "Google nie znalazł połączenia komunikacją."
        : "Tras jeszcze nie pobrano. Uruchom ponownie dojazdy.py."));
      section.append(trip);
      return;
    }
    const list = el("ul", "variants");
    routes.forEach((route, index) => {
      const button = el("button", "variant");
      button.type = "button";
      button.dataset.place = placeIndex;
      button.dataset.index = index;
      button.setAttribute("aria-pressed", "false");
      button.setAttribute("aria-label", describe(route));
      button.title = "Najedź, żeby zobaczyć trasę na mapie. Kliknij, żeby rozpisać przesiadki.";
      const legs = el("span", "legs");
      route.segments.forEach((segment, i) => {
        if (i) legs.append(el("span", "sep", "›"));
        legs.append(segment.mode === "walk" ? walkBadge(segment.seconds) : rideBadge(segment));
      });
      button.append(el("span", "variant-time", `${minutes(route.seconds)} min`), legs,
                    el("span", "variant-clock", variantClock(route) || ""));
      const preview = () => {
        if (previewing === button) return;
        previewing = button;
        drawRoute(route);
      };
      const hoverPreview = () => { if (performance.now() >= previewBlockedUntil) preview(); };
      button.addEventListener("mouseenter", hoverPreview);
      button.addEventListener("mousemove", hoverPreview);
      button.addEventListener("focus", preview);
      button.addEventListener("mouseleave", restoreRoute);
      button.addEventListener("blur", restoreRoute);
      button.addEventListener("click", () => togglePin(offer, placeIndex, index, section));
      const item = el("li");
      item.hidden = index > 0;  // domyślnie tylko najszybszy wariant
      item.append(button, stepsList(route));
      list.append(item);
    });
    if (routes.length > 1) {
      const more = el("button", "more", `+${variantsText(routes.length - 1)}`);
      more.type = "button";
      more.setAttribute("aria-expanded", "false");
      more.addEventListener("click", () => {
        const open = more.getAttribute("aria-expanded") !== "true";
        more.setAttribute("aria-expanded", String(open));
        more.textContent = open ? "zwiń" : `+${variantsText(routes.length - 1)}`;
        [...list.children].slice(1).forEach(item => { item.hidden = !open; });
        if (!open && pinned && pinned.offerId === offer.id && pinned.place === placeIndex && pinned.index > 0) {
          pinned = null;  // przypięty wariant właśnie się schował
          updatePins(section);
          restoreRoute();
        }
      });
      header.append(more);
    }
    trip.append(list);
    section.append(trip);
  });
  updatePins(section);
  return section;
}

function formatDate(isoDate) {
  return /^\d{4}-\d{2}-\d{2}$/.test(isoDate) ? isoDate.split("-").reverse().join(".") : isoDate;
}
function daysAgo(isoDate) {
  const days = Math.floor((Date.now() - new Date(`${isoDate}T00:00:00`)) / 86400000);
  return days <= 0 ? "dziś" : days === 1 ? "wczoraj" : `${days} dni temu`;
}
function floorText(offer, details) {
  if (!offer.floor) return null;
  let text = details.floors ? `${offer.floor}/${details.floors}` : offer.floor;
  if (details.lift === true) text += ", winda";
  if (details.lift === false) text += ", bez windy";
  return text;
}

function detailsSection(offer) {
  const section = el("section", "details");
  section.append(el("p", "section-title", "Szczegóły"));
  if (offer.photo) {
    const photoLink = link("", offer.link);
    photoLink.className = "photo-link";
    photoLink.setAttribute("aria-label", "Zdjęcie, otwórz ogłoszenie");
    const photo = el("img", "photo");
    photo.alt = "";
    photo.loading = "lazy";
    photo.referrerPolicy = "no-referrer";
    photo.addEventListener("error", () => photoLink.remove());  // zdjęcie usunięte z ogłoszenia
    photo.src = offer.photo;
    photoLink.append(photo);
    section.append(photoLink);
  }
  const details = offer.details || {};  // brak, gdy karty ogłoszenia nie udało się pobrać
  const rows = [
    ["Piętro", floorText(offer, details)],
    ["Stan", details.status],
    ["Budynek", [details.building, offer.year].filter(Boolean).join(", ")],
    ["Rynek", details.market],
    ["Ogrzewanie", details.heating],
    ["Własność", details.ownership],
    ["Kaucja", details.deposit],
    ["Dostępne od", details.freeFrom && formatDate(details.freeFrom)],
    ["Ogłoszeniodawca", offer.advertiser],
    ["Dodane", offer.listed && `${formatDate(offer.listed)} (${daysAgo(offer.listed)})`],
    ["Wyposażenie", (details.equipment || []).join(", ")],
  ].filter(([, value]) => value);
  const list = el("dl", "facts-list");
  for (const [label, value] of rows) list.append(el("dt", null, label), el("dd", null, value));
  section.append(list);
  const extras = (details.extras || []).filter(extra => !(extra === "winda" && details.lift != null));
  if (extras.length) {
    const chips = el("div", "chips");
    for (const extra of extras) chips.append(el("span", "chip", extra));
    section.append(chips);
  }
  if (offer.excerpt) section.append(el("p", "excerpt", offer.excerpt));
  return section;
}

function glyph(type, className) {
  const box = el("span", className);
  box.style.setProperty("--poi", type.color);
  if (type.icon) {
    box.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[type.icon]}</svg>`;
  } else {
    box.textContent = "M";
  }
  return box;
}

function walkText(meters) {
  if (meters === 0) return "na miejscu";
  const minutes = Math.max(1, Math.round(meters * 1.25 / 80));  // ok. 5 km/h, ulice nie biegną w linii prostej
  const distance = meters < 1000 ? `${Math.round(meters / 10) * 10} m`
    : `${(meters / 1000).toFixed(1).replace(".", ",")} km`;
  return `${distance}, ok. ${minutes} min`;
}

function focusPlace(place) {
  if (place.shapes) {
    map.fitBounds(place.shapes.flat(), { padding: [40, 40], maxZoom: 17 });
  } else {
    map.setView([place.lat, place.lng], Math.max(map.getZoom(), 17));
  }
}

function nearbySection(offer) {
  const section = el("section", "nearby");
  section.setAttribute("aria-live", "polite");
  section.append(el("p", "section-title", "Okolica"));
  if (!nearbyData) {
    section.append(el("p", "nearby-status",
      "Brak danych o okolicy. Uruchom python okolica.py, a potem python mapa.py."));
    return section;
  }
  const groups = computeNearby(offer);
  const list = el("ul", "near-list");
  const missing = [];
  for (const type of POI_TYPES) {
    const nearest = groups[type.key][0];
    if (!nearest) { missing.push(type.label.toLowerCase()); continue; }
    const row = el("button", "near-item");
    row.type = "button";
    row.append(glyph(type, "near-icon"), el("span", "near-label", type.label),
               el("span", "near-name", nearest.name === type.label ? "" : nearest.name),
               el("span", "near-distance", walkText(nearest.distance)));
    row.addEventListener("click", () => focusPlace(nearest));
    const item = el("li");
    item.append(row);
    list.append(item);
  }
  section.append(list);
  if (missing.length) section.append(el("p", "nearby-note", `Nie znaleziono w okolicy: ${missing.join(", ")}.`));
  const note = el("p", "nearby-note",
    "Promień 1 km, dla metra i kolei 2 km. Odległości w linii prostej, czas pieszo orientacyjny. Dane: ");
  note.append(link("OpenStreetMap", "https://www.openstreetmap.org/copyright"),
              document.createTextNode(`, stan z ${nearbyData.generated.split("-").reverse().join(".")}.`));
  section.append(note);
  return section;
}

function showNearby(offer) {
  poiLayer.clearLayers();
  const item = items.get(offer.id);
  if (item) {
    const section = nearbySection(offer);
    const current = item.querySelector(".nearby");
    if (current) current.replaceWith(section); else item.append(section);
  }
  if (!nearbyData) return;
  if (!osmCredited) {
    map.attributionControl.addAttribution('Okolica &copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>');
    osmCredited = true;
  }
  const groups = computeNearby(offer);
  const style = { color: "#2e7d32", weight: 1.5, fillColor: "#43a047", fillOpacity: 0.18, interactive: false };
  for (const park of groups.park) {
    for (const ring of park.shapes) L.polygon(ring, style).addTo(poiLayer);
  }
  for (const type of POI_TYPES) {
    if (type.key === "park") continue;
    for (const place of groups[type.key].slice(0, 3)) {  // trzy najbliższe z każdego rodzaju
      const icon = L.divIcon({ className: "", html: glyph(type, "poi").outerHTML, iconSize: [24, 24], iconAnchor: [12, 12] });
      L.marker([place.lat, place.lng], { icon, title: `${type.label}: ${place.name}`, keyboard: false, zIndexOffset: -500 })
        .addTo(poiLayer);
    }
  }
}

function refresh(id) {
  const offer = byId.get(id);
  markers.get(id).setIcon(markerIcon(offer)).setZIndexOffset(id === activeId ? 900 : 0);
  const item = items.get(id);
  if (item) {
    item.classList.toggle("active", id === activeId);
    item.classList.toggle("selected", selected.has(id));
  }
}

function activate(id, { fromMap = false } = {}) {
  const previous = activeId;
  activeId = id;
  if (previous && previous !== id) {
    refresh(previous);
    for (const section of items.get(previous)?.querySelectorAll(".trips, .details, .nearby") || []) section.remove();
  }
  refresh(id);
  const offer = byId.get(id);
  const marker = markers.get(id);
  if (previous !== id) {
    pinned = null;
    previewing = null;
    routeLayer.clearLayers();
  }
  previewBlockedUntil = performance.now() + 900;  // czas na przewinięcie listy
  const item = items.get(id);
  if (item && !item.querySelector(".details")) item.append(detailsSection(offer), routesSection(offer));
  showNearby(offer);
  walkCircle.setLatLng([offer.lat, offer.lng]).addTo(map);
  if (!fromMap && offerLayer.hasLayer(marker)) {
    // bez dymka: dane oferty są na karcie, a dymek zasłaniałby okolicę
    map.closePopup();
    const zoom = Math.max(map.getZoom(), 15);  // przy 15 mieści się cały promień okolicy (1 km)
    if (reduceMotion) map.setView([offer.lat, offer.lng], zoom);
    else map.flyTo([offer.lat, offer.lng], zoom, { duration: 0.6 });
  }
  // rozwinięta karta bywa wyższa niż lista: początek karty na górę, szczegóły czyta się w dół
  items.get(id)?.scrollIntoView({ block: "start", behavior: reduceMotion ? "auto" : "smooth" });
}

function toggleSelected(id, on) {
  if (on) selected.add(id); else selected.delete(id);
  saveSelected();
  refresh(id);
  updateCounts();
  if (filter === "selected" && !on) render();
}

function card(offer) {
  const item = el("li", "offer");
  item.classList.toggle("selected", selected.has(offer.id));
  item.classList.toggle("active", offer.id === activeId);

  const show = el("button", "show");
  show.type = "button";
  show.addEventListener("click", () => activate(offer.id));
  const week = el("span", "week", duration(offer.week));
  week.append(el("span", "per", "w drodze tygodniowo"));
  const facts = el("span", "facts");
  facts.append(el("span", "price", priceText(offer)));
  if (offer.pricePerM2) facts.append(el("span", null, `${numbers.format(offer.pricePerM2)} zł/m²`));
  if (offer.area) facts.append(el("span", null, `${offer.area} m²`));
  if (offer.rooms) facts.append(el("span", null, roomsText(offer.rooms)));
  if (offer.year) facts.append(el("span", null, `rok ${offer.year}`));
  show.append(el("span", "rank", String(offer.rank)), week, linesFor(offer), facts, el("span", "title", offer.title));
  if (offer.isNew || offer.approximate) {
    const badges = el("span", "badges");
    if (offer.isNew) badges.append(el("span", "badge new", "Nowa"));
    if (offer.approximate) badges.append(el("span", "badge", "Przybliżona lokalizacja"));
    show.append(badges);
  }

  const actions = el("div", "actions");
  const pick = el("label", "pick");
  const box = el("input");
  box.type = "checkbox";
  box.checked = selected.has(offer.id);
  box.addEventListener("change", () => toggleSelected(offer.id, box.checked));
  pick.append(box, document.createTextNode("Zaznacz"));
  actions.append(link("Otwórz ogłoszenie", offer.link),
                 link("Okolica w Google Maps", `https://www.google.com/maps/search/?api=1&query=${offer.lat},${offer.lng}`));
  item.append(show, pick, actions);
  if (offer.id === activeId) item.append(detailsSection(offer), routesSection(offer), nearbySection(offer));
  items.set(offer.id, item);
  return item;
}

function visibleOffers() {
  if (filter === "selected") return data.offers.filter(offer => selected.has(offer.id));
  if (filter === "new") return data.offers.filter(offer => offer.isNew);
  return data.offers;
}

function updateCounts() {
  document.getElementById("count-all").textContent = data.offers.length;
  document.getElementById("count-selected").textContent = data.offers.filter(offer => selected.has(offer.id)).length;
  document.getElementById("count-new").textContent = data.offers.filter(offer => offer.isNew).length;
}

function fitTo(offers) {
  const points = [...data.places, ...offers].map(p => [p.lat, p.lng]);
  if (points.length > 1) map.fitBounds(points, { padding: [40, 40], maxZoom: 15 });
  else if (points.length === 1) map.setView(points[0], 15);
  else map.setView([52.2297, 21.0122], 11);
}

function render({ fit = false } = {}) {
  const offers = visibleOffers();
  if (activeId && !offers.some(offer => offer.id === activeId)) {
    const hidden = activeId;
    activeId = null;
    refresh(hidden);
    walkCircle.remove();
    poiLayer.clearLayers();
    routeLayer.clearLayers();
    pinned = null;
  }
  items.clear();
  document.getElementById("list").replaceChildren(...offers.map(card));
  offerLayer.clearLayers();
  for (const offer of offers) offerLayer.addLayer(markers.get(offer.id));
  const empty = document.getElementById("empty");
  empty.hidden = offers.length > 0;
  empty.textContent = EMPTY[filter];
  updateCounts();
  if (fit) fitTo(offers);
}

for (const button of document.querySelectorAll("[data-filter]")) {
  button.addEventListener("click", () => {
    filter = button.dataset.filter;
    for (const other of document.querySelectorAll("[data-filter]")) other.setAttribute("aria-pressed", String(other === button));
    render({ fit: true });
  });
}

const [day, time] = data.generated.split(" ");
document.getElementById("stamp").textContent = `Stan na ${day.split("-").reverse().join(".")}, ${time}`;
document.getElementById("summary").replaceChildren(...data.summary.map(line => el("li", null, line)));
render({ fit: true });
</script>
</body>
</html>
"""


def nearby_for(offers):
    """Dane z okolica.json przycięte do obszaru ofert z zapasem ok. 2,5 km, albo None."""
    if not NEARBY_FILE.exists() or not offers:
        return None
    data = json.loads(NEARBY_FILE.read_text(encoding="utf-8"))
    south, north = min(o["lat"] for o in offers) - 0.025, max(o["lat"] for o in offers) + 0.025
    west, east = min(o["lng"] for o in offers) - 0.04, max(o["lng"] for o in offers) + 0.04

    def inside(lat, lng):
        return south <= lat <= north and west <= lng <= east

    data["pois"] = [poi for poi in data["pois"] if inside(poi[2], poi[3])]
    data["parks"] = [park for park in data["parks"]
                     if any(inside(lat, lng) for ring in park["rings"] for lat, lng in ring)]
    return data


def as_script_json(value):
    # "<" jako \u003c: tekst z ogłoszeń nie może zamknąć znacznika <script>
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace("<", "\\u003c")


def main():
    if not DATA_FILE.exists():
        sys.exit("Brak pliku wyniki.json. Najpierw uruchom dojazdy.py.")
    data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
    nearby = nearby_for(data["offers"])
    if nearby is None:
        print("Brak okolica.json: uruchom python okolica.py, żeby strona pokazywała sklepy, przystanki i parki.")
    page = TEMPLATE.replace("__DATA__", as_script_json(data)).replace("__NEARBY__", as_script_json(nearby))
    MAP_FILE.write_text(page, encoding="utf-8")
    print(f"Zapisano {MAP_FILE.name}, otwieram w przeglądarce.")
    webbrowser.open(MAP_FILE.as_uri())


if __name__ == "__main__":
    main()
