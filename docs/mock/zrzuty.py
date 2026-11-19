#!/usr/bin/env python3
"""
Zrzuty ekranu do README z docs/mock/mapa.html (najpierw: python docs/mock/generuj_mock.py).
Wymaga pakietu playwright: pip install playwright. Używa zainstalowanego Google Chrome, a bez niego
przeglądarki z playwright (playwright install chromium).
Strona jest serwowana przez mapa.py (lokalny serwer na danych przykładowych), żeby można było
naprawdę narysować obszar wykluczony.

Uruchomienie: python docs/mock/zrzuty.py
"""

import sys
import threading
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import mapa  # noqa: E402

OUT = HERE.parent / "img"
PORT = 8799  # inny niż domyślny 8765, żeby nie zderzyć się z działającym mapa.py
URL = f"http://127.0.0.1:{PORT}/"


def settle(page, ms=3500):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)  # kafelki mapy i animacje Leaflet


def start_server():
    """mapa.py na danych przykładowych, z zapisem obszarów do pliku w tym folderze."""
    mapa.DATA_FILE, mapa.NEARBY_FILE = HERE / "wyniki.json", HERE / "okolica.json"
    mapa.MAP_FILE, mapa.ZONES_FILE = HERE / "mapa.html", HERE / "wykluczenia.json"
    mapa.ZONES_FILE.unlink(missing_ok=True)
    mapa.webbrowser.open = lambda *_: None
    threading.Thread(target=mapa.serve, args=(PORT,), daemon=True).start()
    time.sleep(1)


def draw_zone(page, corners):
    """Lasso po czterech rogach (szerokość, długość) obszaru, tak jak rysowałby go użytkownik."""
    page.click("#zone-draw")
    box = page.locator("#map").bounding_box()
    points = page.evaluate("(c) => c.map(([lat, lng]) => { const p = map.latLngToContainerPoint([lat, lng]); return [p.x, p.y]; })", corners)
    xy = [(box["x"] + x, box["y"] + y) for x, y in points]
    page.mouse.move(*xy[0])
    page.mouse.down()
    for target in [*xy[1:], xy[0]]:
        page.mouse.move(*target, steps=18)
    page.mouse.up()


def launch(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:  # bez Google Chrome: przeglądarka dostarczona z playwright
        return p.chromium.launch()


def main():
    OUT.mkdir(exist_ok=True)
    start_server()
    with sync_playwright() as p:
        browser = launch(p)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                color_scheme="light", locale="pl-PL")
        page.goto(URL)
        settle(page)
        page.screenshot(path=OUT / "lista-i-mapa.jpg", quality=85)

        page.locator(".offer .show").first.click()
        settle(page)
        page.screenshot(path=OUT / "szczegoly.jpg", quality=85)

        # Dojazdy i Okolica są domyślnie zwinięte: rozwijamy je (ustawienie zostaje dla kolejnych ofert)
        for name in ("Dojazdy", "Okolica"):
            page.locator(".offer.active .section-head", has_text=name).click()
        variant = page.locator(".offer.active .variant").first
        variant.scroll_into_view_if_needed()
        variant.click()
        settle(page)
        page.locator(".offer.active .section-head", has_text="Dojazdy").evaluate(
            "el => el.scrollIntoView({block: 'start'})")
        page.mouse.move(1000, 450)
        settle(page, 800)
        page.screenshot(path=OUT / "dojazdy.jpg", quality=85)

        variant.click()  # odpina trasę, mapa wraca do okolicy oferty
        page.locator(".offer.active .section-head", has_text="Okolica").evaluate(
            "el => el.scrollIntoView({block: 'start'})")
        settle(page)
        page.screenshot(path=OUT / "okolica.jpg", quality=85)

        # sortowanie po cenie i wspólny znacznik kilku lokali w jednym budynku
        page.reload()
        settle(page, 1500)
        page.select_option("#sort", "price")
        page.evaluate("map.setView([52.1925, 21.0275], 16)")
        settle(page)
        page.locator(".stack").first.click()
        settle(page, 1000)
        page.screenshot(path=OUT / "wspolne-miejsce.jpg", quality=85)

        # obszar wykluczony narysowany lassem: czerwony na mapie, oferty z niego znikają z listy
        page.reload()
        settle(page, 1500)
        page.select_option("#sort", "week")  # sortowanie z poprzedniego zrzutu jest zapamiętane w przeglądarce
        page.evaluate("map.setView([52.225, 21.01], 12)")
        settle(page, 1500)
        draw_zone(page, [[52.226, 21.03], [52.226, 21.075], [52.268, 21.075], [52.268, 21.03]])
        settle(page, 1200)
        page.keyboard.press("Escape")
        page.evaluate("document.activeElement.blur()")  # bez ramki fokusa na przycisku
        page.mouse.move(700, 800)
        page.screenshot(path=OUT / "wykluczanie.jpg", quality=85)

        # motyw nocny (bez obszaru z poprzedniego zrzutu: serwer zapisał go w pliku)
        mapa.ZONES_FILE.unlink(missing_ok=True)
        night = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                    color_scheme="dark", locale="pl-PL").new_page()
        night.goto(URL)
        settle(night)
        night.locator(".offer .show").first.click()
        settle(night)
        night.screenshot(path=OUT / "motyw-nocny.jpg", quality=85)
        browser.close()
    mapa.ZONES_FILE.unlink(missing_ok=True)
    print(f"Zapisano zrzuty w {OUT}")


if __name__ == "__main__":
    main()
