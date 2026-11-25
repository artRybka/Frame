# ArtSR runda 2: STYL2 (2026-11-25)

To jest próba: w aplikacji, na serwerze i na NAS-ie nic się nie zmieniło. Koszt 0 USD. Wszystko liczyłem na Macu (M2 Pro, MPS), z `nice` i `caffeinate`. Były dwie pauzy na prośbę Mateusza, 10:32–14:52 i 16:23–16:37, obie bez straty kroków. Wagi zostały lokalnie w `~/Frame-worktrees/artsr/ckpt/` (STYL2a2, STYL2c, STYL2d).

## Co zrobiłem

- **Dane: 12 000 dzieł** (w nocy było 3590): 4000 obrazów, 4400 grafik i 3600 rysunków i akwarel. Zasady są te same co w nocy: tylko dzieła z muzeów, oryginał co najmniej 2400 px, bez kopii po restauratorze i bez własnych prac. Z 74 tys. kandydatów (głębsze strony katalogu plus zapytania o akwafortę, akwatintę, miedzioryt, mezzotintę, suchą igłę i mistrzów) wziąłem najpierw grafikę gęstą. Wyszło 3,9 tys. akwafort, akwatint i miedziorytów, w tym Goya 109, Rembrandt 100, Piranesi 87 i Dürer ok. 120 (limit na tych mistrzów to 120, na innych 30). Razem 4109 artystów. Ze względu na dysk nowe dzieła mają 2 zepsute kopie × 4 wycinki zamiast 2 × 8, a kopii 2048 px nie trzymam. Wektory to SigLIP 2, jak w nocy. Zbiór testowy jest bez zmian (32 dzieła), a inne kopie testowych dzieł i artyści „nieobecni” są wyłączeni.
- **Losowanie.** Każda kategoria wypada po równo (1/3), a w grafice połowa próbek pochodzi z gęstych technik.
- **Faza 1 (L1 + MS-SSIM) od nocnego STYL.** Trwała 3,5 h, ok. 48 tys. kroków (lr 1e-4, z przerwą) i dała STYL2a2.
- **Faza 2 (tekstura).** LPIPS-VGG 0,1 i PatchGAN 0,003, ale na grafice GAN ×0,3. Do tego nowa **kara gradientowa**: L1 gradientów Sobla jasności. Fałszywa kreska kosztuje w niej tyle samo co brakująca, z wagą 1,0 na grafice i 0,25 na reszcie. Trwała 3 h, ok. 7,5 tys. kroków, i dała **STYL2 (koniec)** = STYL2c.
- **Poprawka STYL2d (45 min).** Po fazie 2 LPIPS utknął na 0,405, bo kara gradientowa tłumiła teksturę także w obrazach i rysunkach. STYL2d to więc STYL2c dotrenowany bez kary poza grafiką, z karą 0,3 na grafice i GAN ×0,5 na grafice.
- **Sterowanie stylem** (punkt opcjonalny): nie robiłem. Czas poszedł na jakość.
- **KH7 na STYL2d.** To ten sam przepis co KH7: gotowy surowy wynik SeedVR2 nałożony na podstawę i wmieszany maską 85–95, ale z podstawą STYL2d zamiast Photo S. Tylko 8 starych dzieł, bez fal.

Miary są te same co w nocy (PSNR, SSIM, LPIPS-alex ↓, detal ↑, ΔE OKLab ×100 ↓), przy 2048 px.

## Wyniki

**Wszystkie 32** (32 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.88 | 0.651 | 0.447 | 0.400 | 3.08 |
| STYL (noc) | 26.77 | 0.645 | 0.351 | 0.389 | 3.19 |
| STYL2 po fazie 1 | 27.09 | 0.668 | 0.523 | 0.436 | 3.00 |
| STYL2 (koniec) | 26.93 | 0.656 | 0.405 | 0.410 | 3.06 |
| STYL2d (poprawka) | 26.86 | 0.654 | 0.374 | 0.399 | 3.10 |

**8 starych** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.81 | 0.629 | 0.483 | 0.422 | 3.20 |
| STYL (noc) | 26.64 | 0.623 | 0.390 | 0.403 | 3.31 |
| STYL2 po fazie 1 | 26.91 | 0.641 | 0.569 | 0.442 | 3.16 |
| STYL2 (koniec) | 26.74 | 0.629 | 0.455 | 0.418 | 3.23 |
| STYL2d (poprawka) | 26.71 | 0.628 | 0.418 | 0.410 | 3.26 |
| restaurator dziś | 25.35 | 0.576 | 0.330 | 0.303 | 3.77 |
| KH7 (podstawa Photo S) | 26.07 | 0.587 | 0.340 | 0.364 | 3.57 |
| KH7 na STYL2 | 26.05 | 0.588 | 0.334 | 0.368 | 3.60 |

**Malarstwo, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 29.57 | 0.690 | 0.457 | 0.335 | 2.52 |
| STYL (noc) | 29.53 | 0.673 | 0.383 | 0.320 | 2.78 |
| STYL2 po fazie 1 | 29.88 | 0.704 | 0.567 | 0.383 | 2.48 |
| STYL2 (koniec) | 29.64 | 0.690 | 0.419 | 0.340 | 2.58 |
| STYL2d (poprawka) | 29.58 | 0.688 | 0.389 | 0.326 | 2.63 |

**Grafika, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 23.04 | 0.583 | 0.458 | 0.374 | 4.27 |
| STYL (noc) | 22.86 | 0.583 | 0.343 | 0.360 | 4.29 |
| STYL2 po fazie 1 | 23.04 | 0.606 | 0.476 | 0.396 | 4.13 |
| STYL2 (koniec) | 23.07 | 0.597 | 0.410 | 0.392 | 4.15 |
| STYL2d (poprawka) | 22.97 | 0.595 | 0.381 | 0.383 | 4.19 |

**Rysunek i akwarela, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 28.10 | 0.702 | 0.389 | 0.467 | 2.35 |
| STYL (noc) | 28.05 | 0.702 | 0.289 | 0.473 | 2.37 |
| STYL2 po fazie 1 | 28.53 | 0.722 | 0.478 | 0.520 | 2.23 |
| STYL2 (koniec) | 28.27 | 0.707 | 0.336 | 0.490 | 2.30 |
| STYL2d (poprawka) | 28.17 | 0.705 | 0.310 | 0.478 | 2.35 |

**Gęste akwaforty i miedzioryty (Dürer ×2, Rembrandt, Goya, Rossi, Bickham)** (6 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 22.49 | 0.548 | 0.484 | 0.341 | 4.63 |
| STYL (noc) | 22.07 | 0.538 | 0.366 | 0.308 | 4.82 |
| STYL2 po fazie 1 | 22.34 | 0.565 | 0.489 | 0.350 | 4.61 |
| STYL2 (koniec) | 22.35 | 0.554 | 0.428 | 0.346 | 4.63 |
| STYL2d (poprawka) | 22.24 | 0.552 | 0.398 | 0.337 | 4.69 |


Punkty kontrolne co godzinę (wszystkie 32 dzieła, PSNR/LPIPS/detal): faza 2 po 30 min 26.98/0.426/0.413, po 1,5 h 26.95/0.409/0.413, po 2,5 h 26.91/0.407/0.409, a na końcu 26.93/0.405/0.410. Od godziny LPIPS prawie stał w miejscu.

## Plansze

- `styl2-1…8.jpg`: wszystkie 32 dzieła z tymi samymi wycinkami 100 % co w nocy. Kolumny: Prawda | Photo S | STYL (noc) | STYL2 (koniec) | STYL2d | restaurator dziś | KH7 na STYL2d. Ostatnie dwie kolumny są tylko przy 8 starych.
- `styl2-akwaforty-1…3.jpg`: 6 gęstych grafik (Dürer: Melancholia I i Chłop z żoną; Rembrandt; Goya; Rossi; Bickham). Każda ma dwa wycinki, nocny i drugi w najgęstszym miejscu.

## Wniosek

1. **Robaczkowa siatka na gęstych akwafortach prawie znikła.** Widać to najlepiej na Goi (20) i Rembrandcie (18). STYL z nocy robił tam drobną sieć oczek, a STYL2 i STYL2d rysują kreskę w kierunku rytu, bliżej prawdy. Kreski nie odtwarzają, bo z wejścia 600 px nie da się jej odzyskać, ale już jej nie podrabiają. Miary na gęstych mówią to samo: PSNR 22.35 i 22.24 wobec 22.07 w nocy, SSIM 0.554 wobec 0.538, detal 0.346 wobec 0.308.
2. **STYL2 (koniec) to wariant „wierny”.** Najwyższy PSNR i detal ze wszystkich modeli po fazie tekstury (26.93 i 0.410 wobec 26.77 i 0.389 w nocy), ale LPIPS 0.405 wobec 0.351, bo obrazy i rysunki są gładsze.
3. **STYL2d to wariant zrównoważony i to on jest moim kandydatem.** Na wszystkich 32 i w każdej kategorii jest lepszy od nocnego STYL w PSNR, SSIM, detalu i ΔE, z czystszą grafiką. Gorszy jest tylko w LPIPS (0.374 wobec 0.351). W rysunku (0.310 wobec 0.289) i malarstwie (0.389 wobec 0.383) różnica jest mała, w grafice większa (0.381 wobec 0.343). Tę różnicę LPIPS liczy po części na korzyść nocnej „siatki”, która dla tej miary wygląda jak faktura.
4. **W restauratorze podstawa STYL2d daje tyle co Photo S.** KH7 na STYL2d ma 26.05 / 0.588 / 0.334 / 0.368, KH7 na Photo S 26.07 / 0.587 / 0.340 / 0.364: odrobinę lepszy LPIPS i detal, PSNR bez zmian. KH7 bierze z podstawy ok. 90 % powierzchni, ale prawie cały LPIPS robi SeedVR2, więc lepsza podstawa niewiele tu zmienia.
5. **Następny krok, jeśli idziemy dalej.** Kara gradientowa tylko na grafice z wagą ok. 0,5 przez całą fazę 2 (bez etapu STYL2c), dłuższa faza 2 (LPIPS w STYL2d jeszcze spadał) i więcej miejsca na dysku na 8 wycinków na dzieło.
