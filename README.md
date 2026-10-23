# Frame

Domowa ramka na sztukę i zdjęcia zbudowana na ekranie **Samsung EM32DX**
(32", kolorowy e-papier E Ink Spectra 6). Wzorem jest ramka InkJoy: biblioteka
obrazów z opisami, udostępniony album iCloud i aplikacja iOS. Wszystko działa
na oryginalnym firmware'rze ekranu, a serwer jest add-onem Home Assistant.

**Status:** Etap 0, czyli rozpoznanie urządzenia. Narzędzia są gotowe, czekamy
na eksperymenty z ekranem. Plan: [docs/PLAN.md](docs/PLAN.md).

| | |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | plan prac, etapy, ryzyka, pytania otwarte |
| [docs/EXPERIMENTS.md](docs/EXPERIMENTS.md) | eksperymenty do wykonania z ekranem |
| [docs/DEVICE_PROTOCOL.md](docs/DEVICE_PROTOCOL.md) | MDC, `content.json`, Wake-on-LAN |
| [docs/IMAGE_PIPELINE.md](docs/IMAGE_PIPELINE.md) | algorytm kolorów, kontrastu i ditheringu |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | komponenty, API, wdrożenie |
| [docs/DECISIONS.md](docs/DECISIONS.md) | rejestr decyzji |

## Szybki start (Mac w tej samej sieci co ekran)

```bash
brew install uv
cd server
uv sync                       # Python + zależności (.venv)
cp .env.example .env          # IP / PIN / MAC ekranu
uv run frame device info      # połączenie z ekranem (E1)
uv run frame push ~/Pictures/obraz.jpg -p painting   # obraz na ekran (E2)
```

Inne przydatne polecenia:

```bash
uv run frame render in.jpg out.png -p photo --preview podglad.png   # bez ekranu
uv run frame testchart passthrough pt.png && uv run frame push pt.png --raw
uv run frame serve            # serwer + API (http://localhost:8099/docs)
uv run pytest                 # testy
```

`frame push` uruchamia na chwilę serwer HTTP na porcie 8099, z którego ekran
pobiera obraz. Przy pierwszym uruchomieniu zezwól w zaporze macOS na
połączenia przychodzące.

## Home Assistant

W *Ustawienia → Dodatki → Sklep z dodatkami → ⋮ → Repozytoria* dodaj
`https://github.com/artRybka/Frame`, zainstaluj add-on **Frame** i uzupełnij
konfigurację (IP, PIN i MAC ekranu, token API). Szczegóły w
[ha-addon/DOCS.md](ha-addon/DOCS.md).

## Aplikacja iOS

```bash
brew install xcodegen
cd ios && xcodegen generate && open Frame.xcodeproj
```

Więcej w [ios/README.md](ios/README.md).

## Struktura

```
server/    serwer i CLI (Python): protokół ekranu, algorytm obrazu, API
ha-addon/  add-on Home Assistant
ios/       aplikacja iOS (SwiftUI)
docs/      dokumentacja projektu
scripts/   skrypty pomocnicze
```
