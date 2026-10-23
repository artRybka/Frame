# Architektura

## Komponenty

| Komponent | Technologia | Katalog |
|---|---|---|
| Serwer ramki | Python 3.12+, FastAPI, numpy, numba, Pillow | `server/` |
| Add-on Home Assistant | Docker (Debian slim), `host_network` | `ha-addon/` |
| Aplikacja iOS | SwiftUI, iOS 17+, XcodeGen | `ios/` |
| Ekran | Samsung EM32DX, oryginalny firmware | — |

## Przepływ: wysłanie obrazu

```
App/CLI ──POST /api/display──▶ serwer
                                │ 1. render (pipeline) → PNG + podgląd
                                │ 2. zapis do /data (current.json, images/, previews/)
                                │ 3. MDC: TLS :1515, PIN, 0xC7 "http://<serwer>/panel/content.json?v=<id>"
                                ▼
                              ekran ──GET /panel/content.json──▶ serwer
                              ekran ──GET /panel/images/<id>.png─▶ serwer
                                │ 4. serwer widzi pobranie → odpowiedź "fetched: true"
                                ▼
                              odświeżenie panelu (kilkanaście sekund)
```

Gdy ekran śpi, a mamy jego MAC, serwer wysyła Wake-on-LAN i ponawia połączenie.

## Przepływ docelowy: rotacja (Etap 2)

```
harmonogram ─▶ wybór pozycji (kolekcje, iCloud, własne; bez powtórek)
            ─▶ render z cache (paleta + ustawienia + orientacja)
            ─▶ publikacja + MDC / albo tylko podmiana treści, jeśli ekran sam pobiera (E7)
            ─▶ historia, powiadomienie do aplikacji i Home Assistanta
```

## API (stan obecny)

| Metoda | Ścieżka | Opis |
|---|---|---|
| GET | `/panel/content.json` | manifest dla ekranu (bez autoryzacji) |
| GET | `/panel/images/{name}` | obraz dla ekranu (bez autoryzacji) |
| GET | `/api/health` | wersja, paleta |
| GET | `/api/now` | co jest na ekranie (tytuł, opis, źródło, URL podglądu) |
| GET | `/api/previews/{id}.png` | podgląd wyglądu na ekranie |
| GET | `/api/presets` | presety renderowania |
| POST | `/api/display` | multipart: `file`, `preset` / `settings_json`, `strategy`, `raw`, `title`, `description`, `push`, `wait` |
| POST | `/api/device/push` | ponowne wysłanie bieżącej treści |
| GET | `/api/device/status` | numer seryjny, firmware, bateria, network standby |
| POST | `/api/device/wake`, `/api/device/sleep` | Wake-on-LAN / uśpienie |
| GET | `/api/debug/panel-requests` | ostatnie zapytania ekranu |

Endpointy `/api/*` wymagają nagłówka `Authorization: Bearer <api_token>`, jeśli
token jest ustawiony. Pełna specyfikacja: `http://<serwer>:8099/docs` (OpenAPI).

## Wdrożenie

- **W trakcie prac**: `uv run frame serve` na Macu w tej samej sieci co ekran. Port 8099 musi być osiągalny dla ekranu; zezwól na połączenia przychodzące w zaporze macOS.
- **Docelowo**: add-on w Home Assistant. Repozytorium dodajesz w *Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria* (`https://github.com/artRybka/Frame`), a add-on instaluje kod z gałęzi `main`. Do testów niewydanych zmian: `scripts/bundle-addon.sh` i skopiowanie wyniku do `/addons` (add-on „Frame (local)”).
- Dane add-onu znajdują się w `/data` (kopie zapasowe Home Assistanta je obejmują).

## Struktura repozytorium

```
docs/        plan, protokół, algorytm, eksperymenty, decyzje
server/      frame_server: device/ (MDC, manifest, WoL), imaging/ (pipeline),
             web/ (FastAPI), service.py, store.py, cli.py; tests/
ha-addon/    config.yaml, build.yaml, Dockerfile, DOCS.md, translations/
ios/         project.yml (XcodeGen), Frame/ (SwiftUI), FrameTests/
scripts/     bundle-addon.sh
```
