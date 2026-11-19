"""
Pobieranie stron z portali z ograniczeniami, które pilnują, żeby skrypt nie utknął.

Portale zwracają HTTP 429 („too many requests”) albo 5xx, gdy pytamy za często. Reakcja:
  1. kilka ponowień z rosnącą przerwą (a przy nagłówku Retry-After tyle, ile portal prosi),
  2. po kilku nieudanych zapytaniach z rzędu albo po przekroczeniu limitu czasu portal jest
     w tym uruchomieniu uznany za zablokowany: kolejne zapytania do niego kończą się od razu,
  3. skrypt idzie dalej z tym, co już pobrał, i opisuje w podsumowaniu, co zostało pominięte.
Nie czekamy więc w nieskończoność na komplet ofert.
"""

import random
import time
from email.utils import parsedate_to_datetime
from urllib.parse import urlsplit

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8",
}
MAX_ATTEMPTS = 4          # tyle razy próbujemy jedno zapytanie
BACKOFF_S = 5             # przerwa przed ponowieniem: 5, 10, 20 s
RETRY_AFTER_MAX_S = 60    # dłużej niż minutę na prośbę portalu nie czekamy
MAX_STRIKES = 3           # tyle nieudanych zapytań z rzędu (po wszystkich ponowieniach) blokuje portal
TIME_LIMIT_S = 20 * 60    # tyle czasu na jeden portal w jednym uruchomieniu
EXTRA_DELAY_MAX_S = 6

_hosts = {}               # host -> {"start": czas pierwszego zapytania, "strikes": n, "blocked": powód}
_extra_delay = 0.0        # po 429 zwalniamy tempo zapytań, a po udanych wracamy do normalnego


def configure(time_limit_minutes=None):
    global TIME_LIMIT_S
    if time_limit_minutes:
        TIME_LIMIT_S = float(time_limit_minutes) * 60


def reset():
    """Czyści stan (testy i ponowne uruchomienie w jednym procesie)."""
    global _extra_delay
    _hosts.clear()
    _extra_delay = 0.0


def _host(url):
    """Portal z adresu, bez subdomen (www.otodom.pl i warszawa.nieruchomosci-online.pl to po jednym portalu)."""
    return ".".join((urlsplit(url).hostname or url).split(".")[-2:])


def _state(url):
    return _hosts.setdefault(_host(url), {"start": None, "strikes": 0, "blocked": None, "last": None})


def block(url, reason):
    """Uznaje portal za zablokowany do końca tego uruchomienia."""
    state = _state(url)
    if not state["blocked"]:
        state["blocked"] = reason
        print(f"\n{_host(url)}: {reason}. Przestaję pytać ten portal i idę dalej z tym, co już mam.")


def blocked(url):
    """Powód, dla którego nie pytamy już tego portalu (albo None)."""
    state = _state(url)
    if not state["blocked"] and state["start"] is not None and time.monotonic() - state["start"] > TIME_LIMIT_S:
        block(url, f"przekroczony limit czasu ({round(TIME_LIMIT_S / 60)} min)")
    return state["blocked"]


def last_error(url):
    """Ostatni błąd zapytania do tego portalu, np. „HTTP 429”, albo None."""
    return _state(url)["last"]


def problems():
    """Opisy portali, od których nie udało się pobrać wszystkiego: lista tekstów do podsumowania."""
    return [f"{host}: {state['blocked']}" for host, state in _hosts.items() if state["blocked"]]


def pause():
    """Przerwa między zapytaniami, żeby nie zasypywać portalu; dłuższa po niedawnych błędach 429."""
    time.sleep(random.uniform(1, 2) + _extra_delay)


def _retry_after(response):
    value = response.headers.get("Retry-After") if response is not None else None
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        try:
            return max(0.0, parsedate_to_datetime(value).timestamp() - time.time())
        except (TypeError, ValueError):
            return None


def fetch(url):
    """GET z ponowieniami przy błędach sieci, 429 i 5xx. Zwraca odpowiedź albo None (portal jest
    zablokowany, minął limit czasu, portal odrzuca zapytania HTTP 403 albo ponowienia nic nie dały).
    Odpowiedź z innym błędem, np. 404, jest zwracana: to zwykła informacja, a nie awaria portalu."""
    global _extra_delay
    state = _state(url)
    if blocked(url):
        return None
    if state["start"] is None:
        state["start"] = time.monotonic()
    last = "brak odpowiedzi"
    for attempt in range(MAX_ATTEMPTS):
        response = None
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
        except requests.RequestException as error:
            last = type(error).__name__
        if response is not None:
            code = response.status_code
            if code == 403:  # portal nas odrzuca: ponawianie nic nie da
                last = "HTTP 403"
                break
            if code != 429 and code < 500:
                if response.ok:
                    state["strikes"] = 0
                    _extra_delay = max(0.0, _extra_delay - 0.25)
                return response
            last = f"HTTP {code}"
            if code == 429:
                _extra_delay = min(EXTRA_DELAY_MAX_S, _extra_delay + 1)
        if attempt == MAX_ATTEMPTS - 1:
            break
        wait = _retry_after(response)
        wait = min(wait, RETRY_AFTER_MAX_S) if wait is not None else BACKOFF_S * 2 ** attempt
        if time.monotonic() + wait - state["start"] > TIME_LIMIT_S:
            break  # czekanie przekroczyłoby limit czasu
        time.sleep(wait)
    state["strikes"] += 1
    state["last"] = last
    if state["strikes"] >= MAX_STRIKES:
        block(url, f"{MAX_STRIKES} nieudane zapytania z rzędu (ostatni błąd: {last})")
    else:
        blocked(url)  # sprawdza limit czasu
    return None
