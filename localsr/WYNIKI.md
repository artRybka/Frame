# Próba LocalSR jako restauratora dzieł (2026-11-24)

Osiem dzieł w domenie publicznej z Wikimedia Commons, oryginały od 3143 do 44 567 px na dłuższym boku.
**Prawda** to oryginał zmniejszony Lanczosem do 2048 px. **Wejście** to oryginał zmniejszony do 600 px,
zapisany jako JPEG q80 i przepuszczony przez `descreened`, czyli tak jak w `restorer._picture`.
Każdy wariant doprowadzono do rozmiaru prawdy i porównano z nią.

- **A**: Lanczos.
- **B**: LocalSR Photo M (`4xLocalSRPhoto_PULSE-96x12`), 4×, potem Lanczos do 2048 px.
- **C**: LocalSR Photo S (`-64x8`), tak samo.
- **D**: Real-ESRGAN x4plus (spandrel).
- **E**: SeedVR2 na fal, wynik surowy (prawdziwy `fal.Upscaler` serwera, factor 3,413, safety off), po `fit`.
- **F**: to, co dziś widzi Mateusz: `recoloured(picture, fit(E), 0.7)`.
- **G**: to samo mieszanie dla LocalSR: `recoloured(picture, B, 0.7)`.

Miary: PSNR i SSIM (RGB), LPIPS (alex, im niżej, tym bliżej w odbiorze),
**detal** (korelacja górnoprzepustowa: obraz minus rozmycie Gaussa σ=2, im wyżej, tym więcej
*prawdziwych* drobnych szczegółów), ΔE w OKLab ×100 (średnio na piksel).
Sprawdziłem też położenie wyników: każdy wariant leży na prawdzie z dokładnością do 0,3 px,
więc niskie liczby SeedVR2 wynikają z tego, co model rysuje, a nie z przesunięcia.

Plansze: `plansza-1.jpg` (dzieła 1–4) i `plansza-2.jpg` (5–8). Wycinki są w skali 100 % z prawdy 2048 px.

## Średnio z 8 dzieł

| Wariant | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| A Lanczos | 26.34 | 0.620 | 0.697 | 0.363 | 3.35 |
| B Photo M | 26.52 | 0.624 | 0.477 | 0.412 | 3.32 |
| C Photo S | **26.81** | 0.629 | 0.483 | **0.422** | **3.20** |
| D Real-ESRGAN | 25.61 | 0.607 | 0.437 | 0.384 | 3.62 |
| E SeedVR2 surowy | 24.05 | 0.529 | **0.307** | 0.271 | 4.44 |
| F SeedVR2 + miesz. 0,7 (dziś) | 25.35 | 0.576 | 0.330 | 0.303 | 3.77 |
| G Photo M + miesz. 0,7 | 26.67 | **0.630** | 0.531 | 0.417 | 3.27 |

## Dzieło po dziele

**PSNR dB**

| Dzieło | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| 1. Van Gogh, Gwiaździsta noc | 21.73 | 21.42 | 21.81 | 20.79 | 19.94 | 20.94 | 21.67 |
| 2. Vermeer, Mleczarka | 26.61 | 26.58 | 26.73 | 25.74 | 24.71 | 25.76 | 26.73 |
| 3. Rembrandt, Autoportret | 33.72 | 33.10 | 33.64 | 33.08 | 31.13 | 32.42 | 33.44 |
| 4. Hokusai, Wielka fala | 23.54 | 24.86 | 24.95 | 24.06 | 21.76 | 23.29 | 24.67 |
| 5. Dürer, Melancholia I | 22.41 | 21.93 | 22.39 | 20.90 | 16.42 | 18.59 | 22.29 |
| 6. Sargent, Górski strumień | 25.33 | 25.53 | 25.78 | 24.97 | 22.75 | 24.26 | 25.69 |
| 7. Mondrian, Kompozycja II | 31.18 | 32.25 | 32.43 | 29.26 | 30.05 | 31.08 | 32.32 |
| 8. Holbein, Ambasadorowie | 26.23 | 26.53 | 26.73 | 26.10 | 25.69 | 26.42 | 26.58 |

**LPIPS**

| Dzieło | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| 1. Van Gogh | 0.883 | 0.621 | 0.613 | 0.487 | 0.380 | 0.432 | 0.674 |
| 2. Vermeer | 0.787 | 0.568 | 0.586 | 0.562 | 0.410 | 0.469 | 0.625 |
| 3. Rembrandt | 0.718 | 0.473 | 0.512 | 0.537 | 0.288 | 0.327 | 0.546 |
| 4. Hokusai | 0.600 | 0.359 | 0.355 | 0.358 | 0.178 | 0.187 | 0.427 |
| 5. Dürer | 0.644 | 0.472 | 0.492 | 0.386 | 0.438 | 0.375 | 0.489 |
| 6. Sargent | 0.760 | 0.474 | 0.458 | 0.389 | 0.284 | 0.288 | 0.546 |
| 7. Mondrian | 0.545 | 0.423 | 0.442 | 0.397 | 0.221 | 0.257 | 0.467 |
| 8. Holbein | 0.639 | 0.423 | 0.405 | 0.378 | 0.259 | 0.303 | 0.476 |

**Detal (korelacja górnoprzepustowa z prawdą)**

| Dzieło | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| 1. Van Gogh | 0.291 | 0.287 | 0.301 | 0.241 | 0.151 | 0.184 | 0.298 |
| 2. Vermeer | 0.323 | 0.340 | 0.347 | 0.302 | 0.188 | 0.226 | 0.350 |
| 3. Rembrandt | 0.152 | 0.117 | 0.119 | 0.111 | 0.033 | 0.047 | 0.129 |
| 4. Hokusai | 0.557 | 0.688 | 0.694 | 0.708 | 0.568 | 0.602 | 0.675 |
| 5. Dürer | 0.343 | 0.341 | 0.355 | 0.293 | 0.129 | 0.153 | 0.354 |
| 6. Sargent | 0.444 | 0.500 | 0.512 | 0.471 | 0.315 | 0.365 | 0.505 |
| 7. Mondrian | 0.418 | 0.586 | 0.592 | 0.478 | 0.402 | 0.432 | 0.584 |
| 8. Holbein | 0.380 | 0.437 | 0.456 | 0.469 | 0.383 | 0.414 | 0.439 |

**ΔE OKLab (×100)**

| Dzieło | A | B | C | D | E | F | G |
|---|---|---|---|---|---|---|---|
| 1. Van Gogh | 5.79 | 5.98 | 5.69 | 6.43 | 7.08 | 6.30 | 5.82 |
| 2. Vermeer | 2.82 | 2.83 | 2.77 | 3.05 | 3.40 | 3.04 | 2.79 |
| 3. Rembrandt | 1.52 | 1.61 | 1.54 | 1.66 | 2.01 | 1.75 | 1.56 |
| 4. Hokusai | 3.57 | 3.05 | 2.99 | 3.22 | 3.79 | 3.27 | 3.13 |
| 5. Dürer | 5.08 | 5.32 | 5.02 | 5.89 | 9.82 | 7.55 | 5.10 |
| 6. Sargent | 3.68 | 3.61 | 3.50 | 3.73 | 4.72 | 4.00 | 3.55 |
| 7. Mondrian | 1.35 | 1.28 | 1.26 | 1.80 | 1.54 | 1.39 | 1.27 |
| 8. Holbein | 3.00 | 2.92 | 2.83 | 3.13 | 3.12 | 2.87 | 2.89 |

## Czas na obraz (Mac z M2 Pro, wejście ~600×450 → ~2400×1800, mediana z 3 prób)

| Model | MPS (GPU) | CPU |
|---|---|---|
| LocalSR Photo S | 0,12–0,18 s (śr. 0,14) | 1,6–3,1 s (śr. 2,3) |
| LocalSR Photo M | 0,30–0,47 s (śr. 0,38) | 3,8–6,2 s (śr. 4,7) |
| Real-ESRGAN x4plus | 3–45 s (śr. 18; skakało, pamięć GPU) | nie mierzyłem |
| SeedVR2 na fal | ok. 10–20 s z kolejką, 0,003–0,004 USD | — |

## Wniosek

- **LocalSR niczego nie zmyśla.** Na każdej planszy Photo M i Photo S mają to, co jest w obrazie
  600 px, tylko ostrzej: czystsze krawędzie (Hokusai, Mondrian), wyraźniejszą kreskę Dürera i nuty
  w śpiewniku Holbeina. Pod względem wierności wygrywają ze wszystkimi wariantami: najwyższy PSNR,
  „detal” i najniższe ΔE, wyraźnie lepsze od Lanczosa (LPIPS 0,48 zamiast 0,70).
  Photo S wypada tu minimalnie lepiej od Photo M. Kopie z muzeów są rozmyte przez JPEG, a nie
  przez aparat, a M uczył się głównie rozmycia aparatu.
- **SeedVR2 zmyśla wyraźnie.** Ma najlepsze LPIPS (0,31): wygląda jak prawdziwe malarstwo, z fakturą
  i pociągnięciami pędzla. Rysuje jednak rzeczy, których nie ma. Twarz Melancholii u Dürera jest inna
  (inne oko, inny nos; PSNR 16,4, ΔE 9,8). Mleczarka dostała zapinkę na kołnierzu, Rembrandt wąsy
  i zarost, a Hokusai białe kropki piany. Mieszanie 0,7 (F) łagodzi to tylko trochę.
  „Detal” SeedVR2 (0,27–0,30) jest gorszy nawet od Lanczosa (0,36): drobne szczegóły są gęste,
  ale nie te.
- **Gdzie LocalSR przegrywa.** Nie odtwarza faktury, której w 600 px już nie ma. Impasty van Gogha
  i Rembrandta zostają gładkie i lekko „plastikowe”, kreska miedziorytu jest grubsza niż w oryginale,
  a ziarno płótna u Mondriana i papieru w akwareli znika. Obraz jest ostry, ale ubogi: nie da efektu
  „jak w muzeum”, który dziś daje SeedVR2.
- **Real-ESRGAN się nie nadaje.** Wybiela papier Hokusaia, wygładza płótno, zmienia kolory (najwyższe
  ΔE z modeli lokalnych) i jest 50–100 razy wolniejszy od LocalSR.
- **Mieszanie 0,7 jest LocalSR niepotrzebne.** G tylko go zmiękcza (LPIPS 0,48 → 0,53) przy
  podobnych PSNR i ΔE. Wystarczy samo przeniesienie barw albo udział 1,0.
- **Jako darmowy zapas zamiast Gemini: tak, w roli uczciwego wyostrzenia, nie restauracji.**
  Kosztuje 0 USD, model waży 2,5 MB (S) lub 8 MB (M), potrzebuje tylko torch i liczy na samym CPU:
  na Macu 2–5 s na dzieło, na NAS/HA Green pewnie kilka razy dłużej, ale do przyjęcia w tle.
  Nigdy nie odmawia i nigdy niczego nie dorysowuje. Twórczej restauracji SeedVR2 nie zastąpi,
  ale jest lepszy od Lanczosa wszędzie tam, gdzie dziś nie ma nic (brak klucza, brak kredytu,
  awaria fal).

Koszt fal w tej próbie: **0,028 USD** (8 obrazów SeedVR2).
Modele: LocalSR (H. Reisner, kod MIT, wagi CC BY 4.0), Real-ESRGAN (BSD-3).
Dzieła (Wikimedia Commons, domena publiczna): 

- 1. Van Gogh, Gwiaździsta noc: `File:Van Gogh - Starry Night - Google Art Project.jpg` (44567×35291)
- 2. Vermeer, Mleczarka: `File:Johannes Vermeer - Het melkmeisje - Google Art Project.jpg` (4000×4485)
- 3. Rembrandt, Autoportret (Kenwood): `File:Rembrandt van Rijn - Self-Portrait - Google Art Project.jpg` (12243×15859)
- 4. Hokusai, Wielka fala: `File:Tsunami by hokusai 19th century.jpg` (3859×2594)
- 5. Dürer, Melancholia I: `File:Melencolia I MET MM13762.jpg` (3143×4000)
- 6. Sargent, Górski strumień (akwarela): `File:Mountain Stream MET DT1544.jpg` (3811×2502)
- 7. Mondrian, Kompozycja II: `File:Piet Mondriaan, 1930 - Mondrian Composition II in Red, Blue, and Yellow.jpg` (5918×6000)
- 8. Holbein, Ambasadorowie: `File:Hans Holbein the Younger - The Ambassadors - Google Art Project.jpg` (30000×29560)
