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

Gdy ekran śpi, a mamy jego MAC, serwer wysyła Wake-on-LAN i ponawia połączenie. Na baterii w ciszy nocnej ekran śpi z wyłączonym Wi-Fi i budzi się sam (budzik MDC `0x25`); obraz, który nie dotarł, czeka na pobudkę ([WAKE.md](WAKE.md)).

## Przepływ docelowy: rotacja (Etap 2)

```
harmonogram ─▶ wybór pozycji (kolekcje, iCloud, własne; bez powtórek)
            ─▶ render z cache (paleta + ustawienia + orientacja)
            ─▶ publikacja + MDC / albo tylko podmiana treści, jeśli ekran sam pobiera (E7)
            ─▶ historia, powiadomienie do aplikacji i Home Assistanta
```

## API (stan obecny)

Pełna specyfikacja: `http://<serwer>:8099/docs` (OpenAPI). Endpointy `/api/*`
wymagają nagłówka `Authorization: Bearer <api_token>` (albo `?token=` dla
adresów obrazów), jeśli token jest ustawiony.

| Obszar | Endpointy |
|---|---|
| Ekran (bez autoryzacji) | `GET /panel/content.json`, `GET /panel/images/{name}` |
| Odtwarzacz | `GET /api/player` (co na ramce, następne, historia, przypięcie, następna zmiana), `POST /api/player/next`, `POST /api/player/previous`, `POST/DELETE /api/player/hold` |
| Postęp wyświetlania | `GET /api/progress` (też pole `progress` w `GET /api/player`): etap obrazu w drodze na ramkę (`rendering` → `sending` → [`waking`] → `downloading` → `refreshing` → `done`, albo `waiting` / `failed`), część (`processing` / `loading` / `displaying`, w aplikacji „Przetwarzanie”, „Ładowanie”, „Wyświetlanie”), szacowany ułamek drogi i sekundy do końca. Etapy serwera są mierzone i uczą się czasów z ostatnich obrazów; odświeżanie ekranu po pobraniu jest szacowane na 45 s (E2/E3: ok. 12 s przygotowania i 31–36 s migania), bo ekran nie zgłasza końca. |
| Ustawienia | `GET/PUT /api/settings` (tryb, playlista, interwały przy zasilaczu i na baterii, cisza nocna, prezentacja dla sztuki i zdjęć, orientacja, link do albumu). Zmiana orientacji lub prezentacji od razu przerysowuje bieżący obraz i wysyła go na ramkę, bez przesuwania harmonogramu. |
| Status | `GET /api/status?refresh=` (bateria, ładowanie, połączenie, firmware, serwer), `GET /api/device/status`, `POST /api/device/wake`, `POST /api/device/sleep` |
| Biblioteka | `GET /api/library/items` (filtry: `q`, `artist`, `style`, `subject`, `color`, `kind`, `favorites`, `sort`), `GET /api/library/facets`, `GET/PATCH/DELETE /api/library/items/{id}`, `GET …/{id}/thumb`, `…/image`, `…/preview` (obraz w kadrze i passe-partout, w oryginalnych kolorach; opcjonalnie `?settings=<JSON>` z orientacją i prezentacją oraz `?framing=<JSON>` z kadrami do podglądu przed zapisaniem), `POST …/{id}/show`, `GET/PUT/DELETE …/{id}/framing` (kadr, detale albo kadr w passe-partout z kształtem okienka: odczyt z położeniem okienek na płótnie (`rect`, w passe-partout też `area`), `?automatic=true` pokazuje kadr automatyczny bez zapisu, korekta dla orientacji, powrót do automatu bieżącego trybu), `POST /api/library/upload` (plik i opis; zdjęcia z rolki z datą i miejscem z EXIF) |
| Muzea | `GET /api/museums`, `GET /api/museums/{source}/search`, `POST /api/museums/{source}/import`, `POST /api/museums/{source}/import-search`, `GET /api/jobs[/{id}]` |
| Playlisty | `GET/POST /api/playlists`, `POST /api/playlists/preview`, `GET/PUT/DELETE /api/playlists/{id}`, `POST/DELETE /api/playlists/{id}/items`, `POST /api/playlists/{id}/play` |
| Kalibracja kolorów (bez aplikacji, po E5) | `GET /api/calibration` (paleta w użyciu), `POST …/chart` (plansza na ramkę, 30 min), `POST …/measure` (multipart: `file`, `corners`), `GET …/candidates/{id}/chart.jpg`, `GET …/candidates/{id}/preview/{item}`, `POST …/apply`, `POST …/cancel`, `DELETE /api/calibration` (powrót do domyślnej) |
| Jednorazowe zdjęcie | `POST /api/display` (multipart: `file`, `preset`, `title`, `hold`), `POST /api/device/push`, `GET /api/now`, `GET /api/previews/{id}.png` |
| Diagnostyka | `GET /api/health`, `GET /api/presets`, `GET /api/debug/panel-requests` |

## Rotacja

`player.py`: kolejka z aktywnej playlisty (albo zdjęć w trybie albumu),
tasowana, bez powtórek przez `avoid_repeat_days`. Zmiany są wyrównane do
końca ciszy nocnej (domyślnie codziennie o 07:00); na baterii obowiązuje
osobny interwał. Przypięcie (`hold`) wstrzymuje rotację do określonej chwili
albo na stałe. Stan i historia są w SQLite, więc przetrwają restart.

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
