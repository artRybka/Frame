# Architektura

## Komponenty

| Komponent | Technologia | Katalog |
|---|---|---|
| Serwer ramki | Python 3.12+, FastAPI, numpy, numba, Pillow | `server/` |
| Add-on Home Assistant (HA Green) | Docker (Debian slim), `host_network` | `ha-addon/` |
| Kontener (Synology) | ten sam obraz, `docker-compose`, sieć hosta | `deploy/synology/` |
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
- **Docelowo, wariant A — HA Green**: add-on w Home Assistant. Repozytorium dodajesz w *Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria* (`https://github.com/artRybka/Frame`), a add-on instaluje kod z gałęzi `main`. Do testów niewydanych zmian: `scripts/bundle-addon.sh` i skopiowanie wyniku do `/addons` (add-on „Frame (local)”).
- **Docelowo, wariant B — Synology** (HA Container, bez add-onów): kontener `ghcr.io/artrybka/frame` z `deploy/synology/docker-compose.yml`, sieć hosta, dane w `./data`. Obraz publikuje `.github/workflows/publish.yml` po scaleniu do `main`.
- Dane serwera znajdują się w `/data` (add-on: kopie zapasowe Home Assistanta; Synology: Hyper Backup).
- Dostęp spoza domu: Tailscale / VPN (serwer nie jest wystawiony do internetu).

## Struktura repozytorium

```
docs/        plan, protokół, algorytm, eksperymenty, decyzje
server/      frame_server: device/ (MDC, manifest, WoL), imaging/ (pipeline),
             web/ (FastAPI), service.py, store.py, cli.py; tests/
ha-addon/    config.yaml, build.yaml, Dockerfile, DOCS.md, translations/
deploy/      synology/ (docker-compose dla kontenera obok HA Container)
ios/         project.yml (XcodeGen), Frame/ (SwiftUI), FrameTests/
scripts/     bundle-addon.sh
```
