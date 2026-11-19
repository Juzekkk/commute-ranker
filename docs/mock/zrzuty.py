#!/usr/bin/env python3
"""
Zrzuty ekranu do README z docs/mock/mapa.html (najpierw: python docs/mock/generuj_mock.py).
Wymaga pakietu playwright i zainstalowanego Google Chrome: pip install playwright

Uruchomienie: python docs/mock/zrzuty.py
"""

from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "img"


def settle(page, ms=3500):
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(ms)  # kafelki mapy i animacje Leaflet


def main():
    OUT.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                color_scheme="light", locale="pl-PL")
        page.goto((HERE / "mapa.html").as_uri())
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
        browser.close()
    print(f"Zapisano zrzuty w {OUT}")


if __name__ == "__main__":
    main()
