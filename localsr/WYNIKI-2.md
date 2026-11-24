# Mieszanie LocalSR i SeedVR2 (2026-11-24, ciąg dalszy)

Te same 8 dzieł, wejścia 600 px i prawda 2048 px co w `WYNIKI.md`. Te same miary:
PSNR, SSIM, LPIPS (↓), detal (korelacja górnoprzepustowa z prawdą, ↑) i ΔE OKLab ×100 (↓).
**C** to LocalSR Photo S, **E** to surowy SeedVR2, **F** to dzisiejszy restaurator
(`recoloured(obraz, E, 0,7)`).

Warianty:

- **H**: `recoloured`, w którym podstawą jest Photo S, a nie Lanczos. Barwa i jasność w skali obrazu muzeum pochodzą z Photo S, a z tego, co SeedVR2 dorysował drobniej, zostaje udział 0,7 (H7) albo 0,5 (H5).
- **I**: podział częstotliwości w OKLab. Do skali Gaussa σ biorę Photo S, drobniejsze L biorę z SeedVR2, barwę (a, b) z Photo S. Sprawdziłem σ = 1,5, 2 i 3 px przy 2048.
- **J**: łańcuch. SeedVR2 na fal dostaje Photo S zmniejszone do 1000 px (factor 2,048 do 2048) zamiast surowych 600 px. Sprawdziłem go surowego (J), z `recoloured` 0,7 (Jr7) i z mieszaniem H 0,7 (JH7).
- **K**: maska zmyśleń. Liczę różnicę L między wariantem SeedVR2 a Photo S, uśrednioną Gaussem σ=4 (okno ok. 8 px). Między jej 85. a 95. percentylem maska miękko (smoothstep, potem rozmycie σ=3) przechodzi na Photo S. Photo S trafia tak do ok. 9 % powierzchni. Maskę nałożyłem na surowy E (K90; z progami 70–90: K80), na F (KF90) i na H (KH7, KH5).

## Średnio z 8 dzieł

| Wariant | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| C Photo S | **26.81** | **0.629** | 0.483 | **0.422** | **3.20** |
| E SeedVR2 surowy | 24.05 | 0.529 | **0.307** | 0.271 | 4.44 |
| F restaurator dziś | 25.35 | 0.576 | 0.330 | 0.303 | 3.77 |
| H7 Photo S + SeedVR2 0,7 | 25.36 | 0.576 | 0.321 | 0.318 | 3.76 |
| H5 Photo S + SeedVR2 0,5 | 26.05 | 0.602 | 0.359 | 0.356 | 3.45 |
| I σ1,5 | 24.95 | 0.562 | 0.322 | 0.293 | 4.03 |
| I σ2 | 24.63 | 0.551 | 0.317 | 0.282 | 4.16 |
| I σ3 | 24.37 | 0.541 | 0.318 | 0.275 | 4.26 |
| J łańcuch surowy | 24.50 | 0.560 | 0.355 | 0.309 | 4.17 |
| Jr7 łańcuch + recoloured 0,7 | 25.79 | 0.598 | 0.389 | 0.340 | 3.58 |
| JH7 łańcuch + H 0,7 | 25.75 | 0.597 | 0.381 | 0.353 | 3.58 |
| K90 maska na E | 25.26 | 0.547 | 0.321 | 0.326 | 4.06 |
| K80 maska na E, szersza | 25.69 | 0.560 | 0.337 | 0.347 | 3.85 |
| KF90 maska na F | 26.08 | 0.587 | 0.348 | 0.359 | 3.58 |
| **KH7 maska na H 0,7** | 26.07 | 0.587 | 0.340 | 0.364 | 3.57 |
| KH5 maska na H 0,5 | 26.47 | 0.609 | 0.377 | 0.390 | 3.36 |

## Dzieło po dziele (C | E | F | H7 | H5 | I σ1,5 | JH7 | KH7 | KH5)

| Dzieło | PSNR | LPIPS | detal | ΔE |
|---|---|---|---|---|
| 1. Van Gogh | 21.8 · 19.9 · 20.9 · 21.0 · 21.4 · 20.6 · 21.0 · **21.3** · 21.6 | .61 · .38 · .43 · .42 · .47 · .41 · .47 · **.44** · .49 | .30 · .15 · .18 · .19 · .23 · .17 · .22 · **.22** · .25 | 5.7 · 7.1 · 6.3 · 6.3 · 5.9 · 6.4 · 6.2 · **6.1** · 5.8 |
| 2. Vermeer | 26.7 · 24.7 · 25.8 · 25.8 · 26.3 · 25.5 · 25.8 · **26.5** · 26.6 | .59 · .41 · .47 · .45 · .51 · .40 · .52 · **.47** · .52 | .35 · .19 · .23 · .24 · .28 · .21 · .26 · **.31** · .33 | 2.8 · 3.4 · 3.0 · 3.0 · 2.9 · 3.1 · 3.0 · **2.9** · 2.8 |
| 3. Rembrandt | 33.6 · 31.1 · 32.4 · 32.4 · 33.1 · 32.0 · 33.0 · **33.2** · 33.4 | .51 · .29 · .33 · .32 · .39 · .30 · .41 · **.33** · .40 | .12 · .03 · .05 · .05 · .07 · .04 · .08 · **.08** · .10 | 1.5 · 2.0 · 1.8 · 1.8 · 1.6 · 1.8 · 1.6 · **1.7** · 1.6 |
| 4. Hokusai | 24.9 · 21.8 · 23.3 · 23.2 · 24.0 · 23.0 · 24.7 · **24.5** · 24.9 | .36 · .18 · .19 · .18 · .22 · .19 · .29 · **.21** · .24 | .69 · .57 · .60 · .62 · .65 · .59 · .71 · **.67** · .69 | 3.0 · 3.8 · 3.3 · 3.2 · 3.1 · 3.4 · 2.9 · **3.1** · 3.0 |
| 5. Dürer | 22.4 · 16.4 · 18.6 · 18.6 · 20.1 · 17.1 · 19.3 · **19.4** · 20.7 | .49 · .44 · .38 · .37 · .34 · .46 · .35 · **.38** · .35 | .36 · .13 · .15 · .16 · .20 · .13 · .19 · **.19** · .23 | 5.0 · 9.8 · 7.5 · 7.6 · 6.4 · 9.0 · 6.9 · **6.9** · 6.0 |
| 6. Sargent | 25.8 · 22.8 · 24.3 · 24.3 · 25.0 · 24.0 · 24.2 · **24.9** · 25.4 | .46 · .28 · .29 · .28 · .32 · .29 · .37 · **.30** · .34 | .51 · .32 · .37 · .38 · .43 · .35 · .39 · **.43** · .47 | 3.5 · 4.7 · 4.0 · 4.0 · 3.7 · 4.1 · 4.0 · **3.8** · 3.6 |
| 7. Mondrian | 32.4 · 30.1 · 31.1 · 31.2 · 31.8 · 31.2 · 31.4 · **32.0** · 32.2 | .44 · .22 · .26 · .25 · .30 · .25 · .31 · **.27** · .32 | .59 · .40 · .43 · .47 · .52 · .43 · .51 · **.56** · .58 | 1.3 · 1.5 · 1.4 · 1.4 · 1.3 · 1.4 · 1.3 · **1.3** · 1.3 |
| 8. Holbein | 26.7 · 25.7 · 26.4 · 26.5 · 26.8 · 26.2 · 26.6 · **26.8** · 26.9 | .41 · .26 · .30 · .29 · .33 · .28 · .33 · **.32** · .36 | .46 · .38 · .41 · .43 · .46 · .41 · .46 · **.46** · .47 | 2.8 · 3.1 · 2.9 · 2.8 · 2.7 · 2.9 · 2.8 · **2.8** · 2.7 |

## Plansze

`mix-1.jpg` pokazuje dzieła 1–4, a `mix-2.jpg` dzieła 5–8. Wycinki są w skali 100 %, te same co w poprzedniej próbie. Kolumny: Prawda | C | E | F | H (0,7) | I (σ 1,5) | J (łańcuch + H 0,7) | K (maska na H 0,7). Z każdej rodziny wybrałem najlepszy udział.

## Znane zmyślenia, oglądane w powiększeniu

- **Zapinka Mleczarki.** Wymyślony supeł z rzemykiem jest w E i F, a H, I i J go zostawiają. **K go usuwa:** zostaje bladzy ślad sznurka jak w Photo S.
- **Wąsy Rembrandta.** Włosy dorysowane przez SeedVR2 są w E, F, H i I. **K je wygładza** do Photo S. J jest najgorszy, bo rysuje na skórze łuskowate fałdy, których nigdzie nie było.
- **Nuty Holbeina.** E rysuje pięciolinie z fałszywymi nutami i literą „K”, a H, I i J je zostawiają. K przywraca w tym miejscu miękkie, nieczytelne nuty Photo S. To nieprawda w drugą stronę, ale bez zmyśleń.
- **Kropki piany Hokusaia.** Surowy E je gubi. F, H i K mają je blade, jak w Photo S. J ma ich najwięcej, choć nie zawsze tam, gdzie trzeba.
- **Twarz Melancholii.** Wszystkie warianty z SeedVR2 kładą na twarz gęsty, łuskowaty szraf. Maska K go **nie usuwa**, bo średnia jasność się zgadza, więc różnica L jest mała. J dodaje do tego zawijasy wokół oka.
- **Impast van Gogha.** E i H mają wyraźne pociągnięcia pędzla, które są wymyślone, ale w duchu obrazu. K trochę je łagodzi.

## Wniosek

- **Żaden mix nie daje faktury SeedVR2 całkiem bez zmyśleń.** Faktura SeedVR2 i jego zmyślenia to w dużej części to samo, więc nie da się wziąć jednego bez drugiego.
- **Najlepszy kompromis to K na H 0,7 (KH7).** To dzisiejsze mieszanie z Photo S zamiast Lanczosa oraz maska, która tam, gdzie SeedVR2 najbardziej odbiega od Photo S, wraca do Photo S. Wobec obecnego restauratora (F) KH7 daje +0,7 dB PSNR, wyraźnie więcej prawdziwego detalu (0,364 wobec 0,303), mniejszy błąd barwy (ΔE 3,57 wobec 3,77) i prawie tę samą ostrość w odbiorze (LPIPS 0,340 wobec 0,330). Usuwa przy tym największe miejscowe zmyślenia: zapinkę, wąsy i fałszywe nuty. Szrafu na Melancholii nie usuwa.
- **Chcąc łagodniej, wziąć KH5.** Ma najwięcej prawdziwego detalu ze wszystkich mixów (0,390) i jest najbliżej Photo S w liczbach, ale jest bardziej miękki (LPIPS 0,377).
- **H sam (bez maski)** daje to samo co dziś, tylko trochę lepiej: lepsze są wszystkie miary prócz ΔE, która jest równa. Zmyśla tyle samo co F.
- **I (podział częstotliwości)** nic nie daje. Zostawia drobne zmyślenia L w całości.
- **J (łańcuch)** to ślepa uliczka. SeedVR2 traktuje gładki wynik Photo S jak obraz do „ufakturowania” i zmyśla **więcej**: fałdy na twarzy Rembrandta, zawijasy na Melancholii.

Koszt fal w tej próbie: 0,028 USD (8 obrazów J). Razem z poprzednią próbą wyszło 0,055 USD.
