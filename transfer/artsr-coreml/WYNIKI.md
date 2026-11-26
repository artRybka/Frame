# ArtSR G3 w Core ML: wyniki (2026-11-27, Mac M2 Pro, macOS 27.0.1)

Zdjęć prywatnych nie użyto: wejścia to zdegradowane kopie dwóch dzieł z domeny publicznej z
zestawu testowego treningu (Vermeer, „Mleczarka”; van Gogh, „Gwiaździsta noc”), wektory SigLIP 2
tych samych dzieł z tamtego zestawu. Żadne obrazy nie są w tej gałęzi.

## Skąd model

Prosto z PyTorch (torch 2.7.0, coremltools 9.0), bez ONNX: `StylePULSE` z kodu treningu
(`net.py` + `pulse_arch.py`, poza repo) i wagi G3 `STYL2g_h3.pt`, te same, z których zrobiono
`artsr-g3.onnx`. Gdzie są, mówią zmienne `ARTSR_SRC`, `ARTSR_PULSE`, `ARTSR_CKPT` (`convert.py`).

## Pliki

| plik | co |
|---|---|
| `ArtSR-G3-320.mlpackage` | ML Program, FP16 w środku, wejścia/wyjście fp32, iOS 17+, stały kafelek 320. **5,5 MB** (ONNX fp32: 11,3 MB) |
| `ArtSR-G3-320-576.mlpackage` | ten sam model, kafelek 320 albo 576 (`EnumeratedShapes`, domyślny 320), też 5,5 MB |
| `convert.py` | konwersja: `--sizes 320` (albo `320,576`: jeden pakiet, dwa rozmiary, `EnumeratedShapes`), `--io fp32/fp16` |
| `bench.py` | plan obliczeń, czasy, zgodność z ONNX → `*-results.json`; `bench.py PAKIET 576` dla kafelka 576 |

Wejścia jak w ONNX: `image` (1,3,320,320) RGB 0..1, `look` (1,768) wektor SigLIP 2 po
L2-normalizacji, `kind` (1,3) one-hot obraz / grafika / rysunek; wyjście `out` (1,3,1280,1280),
do przycięcia 0..1. Kafelek 320 = 256 + 2×32 zakładki (jak `TILE`/`OVERLAP` w `artsr.py`).

## Czasy (po rozgrzaniu, mediana z 10)

W czasie pomiarów na Macu chodziły Illustrator (~90% jednego rdzenia) i Time Machine, więc liczby
CPU są raczej trochę zawyżone.

`ArtSR-G3-320.mlpackage` (stały kafelek 320):

| | jeden kafelek 320² | 600×800 (12 kafelków) | 1800×1350 (48 kafelków) | wczytanie modelu |
|---|---|---|---|---|
| **CPU_AND_NE** | **45,9 ms** | **0,60 s** | **2,49 s** | 1,1 s |
| CPU_AND_GPU | 61,0 ms | 0,97 s | 3,52 s | 1,6 s |
| ALL | 82,8 ms | 1,26 s | 4,62 s | 1,9 s |
| CPU_ONLY | 194,5 ms | 2,40 s | 9,56 s | 0,3 s |
| onnxruntime CPU (dla porównania) | – | 7,9 s | 40,9 s | – |

Pakiet z dwoma rozmiarami (`convert.py --sizes 320,576`, `EnumeratedShapes`, też 5,5 MB):

| | kafelek | 600×800 | 1800×1350 |
|---|---|---|---|
| CPU_AND_NE, okna 320 | 47,4 ms | 0,70 s (12) | 2,64 s (48) |
| CPU_AND_NE, okna 576 | 156,2 ms | 0,79 s (4) | **2,22 s** (12) |
| ALL, okna 320 / 576 | 47,1 / 155,2 ms | 0,68 / 0,78 s | 2,63 / 2,29 s |
| CPU_AND_GPU, okna 576 | 198,1 ms | 1,06 s | 2,95 s |
| CPU_ONLY, okna 576 | 574,5 ms | 2,64 s | 8,16 s |

(Osobny pakiet tylko 576, próba wcześniej: 146,6 ms na kafelek na NE, ~1,76 s na 1800×1350.)

- Najszybsze jest **CPU_AND_NE**. W pakiecie ze stałym 320 przy ALL Core ML wysyła na GPU 79 ze
  125 operacji (dodawania, mnożenia i wycinki FiLM, pad, pixel shuffle) i jest prawie 2× wolniej;
  w pakiecie z dwoma rozmiarami ALL zostaje cały na NE. Na telefonie i tak trzeba ustawić
  `MLModelConfiguration.computeUnits = .cpuAndNeuralEngine`.
- Okna 576 opłacają się dopiero przy dużych zdjęciach (1800×1350: −16% w pakiecie z dwoma
  rozmiarami, −30% w osobnym pakiecie 576); przy 600×800 są wolniejsze, bo zakładki ostatnich
  okien liczą się na darmo. 576 działa tylko na obrazach ≥ 576 px na każdym boku.
- Wejścia/wyjście fp16 (`--io fp16`): 48,5 ms na kafelek, czyli bez zysku.
- Na kafelek 320 przypada ~0,42 TFLOP (2,03 M MAC na piksel wejścia), więc NE robi tu ~9 TFLOPS.
- **Na iPhonie nie mierzyłem.** Neural Engine w A17 Pro / A18 jest nowszej generacji niż w M2 Pro,
  więc czas powinien być podobny albo lepszy, ale trzeba to zmierzyć na telefonie.

## Czy wszystko idzie na Neural Engine

`MLComputePlan` (preferowane urządzenie każdej operacji):

- stały 320, CPU_AND_NE: **125 ze 125 operacji na NE**; ALL: 46 na NE, 79 na GPU.
- dwa rozmiary, CPU_AND_NE i ALL: **109 ze 109 na NE**.

## Zgodność z ONNX (te same obrazy i wektory, ONNX fp32 na CPU = wzorzec)

Po zaokrągleniu do 8 bitów, jak przy zapisie (stały 320; pakiet z dwoma rozmiarami daje to samo,
z oknami 576 Mleczarka 600×800 też 56,3 dB, 3):

| obraz | CPU_AND_NE | ALL | CPU_ONLY |
|---|---|---|---|
| Mleczarka 535×600 | 56,4 dB, maks. 5 poziomów | 56,6 dB, 5 | 58,3 dB, 3 |
| Gwiaździsta noc 600×475 | 52,7 dB, 5 | 52,7 dB, 5 | 55,8 dB, 4 |
| Mleczarka 600×800 | 56,3 dB, 3 | 56,5 dB, 3 | 58,1 dB, 3 |

Największa różnica przed zaokrągleniem: 0,017 (NE). To skutek FP16. Dla porównania: kafelki z
zakładką 16 zamiast 32 px zmieniają wynik o ≤ 0,004 (98 dB), a wektor `look` z miniatury zamiast z
pełnego obrazu o 36–45 dB. Różnica Core ML/ONNX jest więc mniejsza niż ta od wektora z miniatury,
ale wyraźnie większa niż od kafelkowania.

Kafelki: każde okno ma pełny rozmiar, a przy krawędzi obrazu jest przesuwane do środka
(`bench.py`, `upscaled`). Zachowany środek ma wtedy zawsze ≥ 32 px prawdziwego kontekstu (pole
widzenia sieci: 26 px), a okno przy krawędzi dopełnia tak samo jak cały obraz, więc wynik jest taki
jak dla całego obrazu, bez dopełniania. Wymaga obrazu nie mniejszego niż okno na każdym boku.

## Co trzeba było zmienić / co warto zmienić w modelu

1. **Konieczne (zrobione w `convert.py`, bez zmiany wag):** `StylePULSE.forward` robi
   `view(-1, n, 2, dim, 1, 1)`, czyli tensor rzędu 6, a Core ML dopuszcza najwyżej 5. W `convert.py`
   ta sama arytmetyka idzie przez `view(-1, 2n, dim, 1, 1)`. Reszta (conv bez biasu, ReLU, pad
   replicate, pixel shuffle, Linear+SiLU) przechodzi wprost.
2. **Obrazy mniejsze niż 320 px na którymś boku** (miniatury, wąskie panoramy): `EnumeratedShapes`
   z drugim rozmiarem 576 tu nie pomaga (jest większy). Potrzebny byłby mniejszy rozmiar w tym
   samym pakiecie (np. 128, 192, 256: każdy kształt musi być wyliczony; `RangeDim` często spada z
   NE na GPU/CPU) i dopełnienie obrazu do niego, z lekką zmianą wyniku tylko przy dopełnionej
   krawędzi. Nie robiłem.
3. **Opcjonalnie: okna 576** dla dużych zdjęć (wyżej), w tym samym pakiecie co 320.
4. **FiLM raz na obraz:** MLP warunkowania liczy się w każdym kafelku, ale jest tyci (0,8 M
   parametrów), więc zysk byłby znikomy. Nie warto.
5. Kwantyzacja wag do 8 bitów zmniejszyłaby pakiet do ~3 MB, ale 5,5 MB to i tak mało, a każdą
   kwantyzację trzeba by sprawdzić na oko. Nie robiłem.
6. Licencja: w opisie pakietu jest atrybucja bazy (LocalSR Photo M, Hermes Reisner, CC BY 4.0,
   zmodyfikowane); w aplikacji musi się ona pojawić tak jak przy serwerze.

Do zrobienia na telefonie poza samym modelem: wektor `look` (SigLIP 2 ViT-B-16-256) — z serwera
(już go trzyma) albo z osobnego modelu SigLIP na telefonie — oraz `recoloured` z
`frame_server.restorer` po skalowaniu do 2048 px.

## Jak powtórzyć

```bash
uv venv -p 3.12 /tmp/artsr-venv && VIRTUAL_ENV=/tmp/artsr-venv uv pip install coremltools "torch==2.7.0" onnxruntime pillow safetensors numpy
/tmp/artsr-venv/bin/python convert.py                     # → ArtSR-G3-320.mlpackage
/tmp/artsr-venv/bin/python convert.py --sizes 320,576     # → ArtSR-G3-320-576.mlpackage
/tmp/artsr-venv/bin/python bench.py ArtSR-G3-320.mlpackage
/tmp/artsr-venv/bin/python bench.py ArtSR-G3-320-576.mlpackage 576
```
