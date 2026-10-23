# Algorytm obrazu

Kod: `server/src/frame_server/imaging/`. Eksperymenty z poziomu CLI:

```bash
uv run frame render obraz.jpg out.png -p painting --preview podglad.png
uv run frame render obraz.jpg out.png -p photo --set tone.gamma=1.25 --set dither.method='"atkinson"'
```

`out.png` to plik dla ekranu (tylko czyste kolory farb), a `podglad.png` to
symulacja wyglądu na ekranie z uwzględnieniem adaptacji oka do „bieli” papieru.

![Porównanie](img/pipeline-compare.jpg)

*Van Gogh, „Pole pszenicy z cyprysami” (The Met, domena publiczna). Od lewej:
oryginał, model naiwnego ditheringu (tak przypuszczalnie działa ścieżka
Samsunga), nasz preset `painting`. Symulacja używa palety referencyjnej
Spectra 6; po kalibracji EM32DX (Etap 1) wartości się zmienią.*

## Problem

Spectra 6 ma tylko 6 farb, a te są ciemne i mało nasycone:

| farba | wartość nominalna | wygląd (pomiar ref.) |
|---|---|---|
| czarna | 0, 0, 0 | 2, 2, 2 |
| biała | 255, 255, 255 | **190, 190, 190** |
| żółta | 255, 255, 0 | 205, 202, 0 *(jaśniejsza niż biel!)* |
| czerwona | 255, 0, 0 | **135, 19, 0** |
| niebieska | 0, 0, 255 | **5, 64, 158** |
| zielona | 0, 255, 0 | **39, 102, 60** |

Dithering liczony na wartościach nominalnych jest przekonany, że miesza jasne
kolory, a w rzeczywistości miesza ciemne. Efekt: obraz za ciemny i zgaszony.

## Etapy przetwarzania

1. **Wczytanie**: orientacja z EXIF, konwersja profilu ICC do sRGB (zdjęcia z iPhone'a są w Display P3), spłaszczenie przezroczystości na białe tło.
2. **Kompozycja** (`layout.py`): płótno 2560×1440 albo 1440×2560. Tryb `fill` kadruje z punktem ciężkości `focus_x/y`, tryb `fit` zostawia passe-partout (`margin`, kolor `white` / `black` / `edge`), tryb `auto` wybiera `fill`, gdy kadrowanie zabiera mniej niż ~12%. Skalowanie odbywa się w świetle liniowym (Lanczos).
3. **Wyostrzenie** (`filters.py`): unsharp mask na jasności OKLab, więc bez kolorowych obwódek. Dithering rozmywa drobne detale, a lekkie wyostrzenie je odzyskuje.
4. **Mapowanie tonów** (`tone.py`) na jasności OKLab L: ekspozycja, `gamma` (półtony), `shadows` (podniesienie cieni), `highlights`, `contrast` (krzywa S). Na koniec `compress_range` mapuje czerń–biel źródła na **czerń–biel panelu** (a nie na najjaśniejszą farbę, czyli żółtą).
5. **Mapowanie gamutu** (`gamut.py`): kolory osiągalne przez mieszanie farb tworzą bryłę wypukłą w liniowym RGB. Dla każdej pary (L, odcień) wyznaczamy maksymalne nasycenie i miękko kompresujemy nasycenie powyżej progu `gamut_knee`. Bez tego ditherer goni kolory, których nie da się uzyskać, i daje szum.
6. **Dithering** (`dither.py`, numba): dyfuzja błędu w świetle liniowym, wybór farby w OKLab. Jądra: Floyd–Steinberg, Atkinson, Jarvis, Stucki, Burkes, Sierra, Sierra Lite. Do tego skanowanie serpentynowe i ograniczanie błędu (`error_clamp`).
7. **Zapis**: indeksy farb zamieniamy na wartości **nominalne** (dla firmware'u). Wynik to PNG, ewentualnie JPEG 4:4:4 q95.
8. **Podgląd**: indeksy farb zamieniamy na kolory **zmierzone** i normalizujemy do bieli papieru. Ten obraz trafia do aplikacji iOS.

## Strategie (wybór po eksperymencie E5)

| strategia | co wysyłamy | kiedy |
|---|---|---|
| `passthrough` | tylko przeskalowany obraz; całą resztę robi ekran | punkt odniesienia (tak robi aplikacja Samsunga) |
| `compensate` | obraz po naszym mapowaniu tonów i gamutu, wstępnie skorygowany macierzą afiniczną (farby nominalne → zmierzone), tak żeby dithering ekranu trafił w nasz cel | gdy ekran przetwarza każdy obraz po swojemu |
| `dither` | gotowy obraz z samych czystych farb | gdy ekran pokazuje czyste farby 1:1 (najlepsza kontrola) |

## Presety

| preset | dla | najważniejsze ustawienia |
|---|---|---|
| `photo` | zdjęcia | gamma 1.15, cienie +0.35, nasycenie 1.2, wyostrzenie 0.6 |
| `painting` | obrazy olejne, akwarele | passe-partout 5%, gamma 1.1, nasycenie 1.15 |
| `graphic` | plakaty, ilustracje, drzeworyty | Atkinson, kontrast 1.2, nasycenie 1.3 |
| `bw` | rysunki, grafiki, zdjęcia czarno-białe | tylko czarna i biała farba, Jarvis |

Pełna lista parametrów: `GET /api/presets` albo modele `RenderSettings`,
`ToneSettings`, `DitherSettings` i `LayoutSettings` w kodzie.

## Kalibracja (Etap 1)

1. `uv run frame testchart palette p.png && uv run frame push p.png --raw`
2. Zdjęcie iPhonem według zasad z [EXPERIMENTS.md](EXPERIMENTS.md), z białą kartką w kadrze.
3. *(do napisania)* `frame calibrate zdjecie.jpg`: wykrywa znaczniki w rogach, uśrednia pola, normalizuje względem kartki i zapisuje `palettes/em32dx.json`.
4. W add-onie ustawiamy `palette: /data/palette.json` (albo przez aplikację).

Paletę można też poprawiać ręcznie: `uv run frame palette --export p.json`,
edycja pól `perceived`, a potem `--palette p.json` w `frame render`.

## Pomysły na dalsze ulepszenia

- Szarości bez kolorowego szumu: neutralne tony mieszane z czerni i bieli zamiast z R+G+B.
- Kompromis jasność/nasycenie przy mapowaniu gamutu (cusp mapping), np. bardziej niebieskie niebo kosztem jasności.
- Dithering uporządkowany / blue-noise dla grafik z płaskimi plamami koloru (mniej „robaczków”).
- Automatyczny wybór presetu (fotografia vs. obraz vs. grafika) oraz ocena, czy dany obraz w ogóle nadaje się na e-papier.
- Metryka jakości: ΔE2000 między rozmytym podglądem a rozmytym oryginałem (S-CIELAB), do automatycznego strojenia.
- Podpisy i karty informacyjne renderowane bez ditheringu (czysta czerń na bieli).
