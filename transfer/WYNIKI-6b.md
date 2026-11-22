# Runda 6b: barwa 0,75 + jasność tylko w górę albo nasycenie (2026-11-22)

**Koszt: 0 USD.** Wszystko liczyłem lokalnie na wynikach LoRA s2 z rundy 4. Skrypty są w `r6/restore6b.py`, `measure6b.py`, `apron6b.py` i `board6b.py`, wyniki w `data/r6b/`.

## Werdykt
- **Jasność „tylko w górę” (×0,5 i ×0,75) prawie nic nie zmienia.** Obie kolumny wyglądają jak kolumna 4 z rundy 6. LoRA wychodzi niemal wszędzie jaśniejsza od dzieła (mediana ciemności +16), więc rozjaśniać nie ma czego. Ruch widać tylko w paru drobnych miejscach: w Hokusaiu ciemność rośnie z +10 do +11/+12 (piana), w Matissie o 0,3. Mediany zostają co do setnej takie same jak w kolumnie 4: masy 0,75, barwa 4°, nasycenie 0,72, ciemność +16. Cała poprawa mas w R75L50 z rundy 6 brała się z przyciemniania.
- **Nasycenie (×do 1,3, bez L)** daje małą, ale widoczną poprawę: mediana nasycenia rośnie z 0,72 do 0,80, odcień zostaje (3,9°), papier i modelunek bez zmian. Najwięcej zyskują Delft (0,75 → 0,84), Mleczarka (0,68 → 0,78), Goya i Hopper.
- **Mleczarka: fartuch nadal kłamie.** Problemem nie jest sam odcień, tylko to, że fartuch jest za jasny i za mało nasycony. Bez przyciemniania tego nie naprawię (liczby niżej).
- Delft i Hokusai: warianty „w górę” wyglądają jak kolumna 4. Przy nasyceniu niebo w Delfcie jest trochę bardziej niebieskie, a Hokusai nieco bardziej granatowy (nasycenie 0,52 → 0,58).

## Fartuch Mleczarki
Maska fartucha to niebieskie piksele dzieła (OKLab b < −0,06, chroma > 0,07) w prostokącie fartucha, razem 23 tys. px. Liczę średnie w tej masce.

| | jasność L | odcień ° | chroma |
|---|---|---|---|
| dzieło | 0,35 | −108 | 0,085 |
| Gemini | 0,62 | −115 | 0,060 |
| LoRA s2 surowa | 0,49 | −79 | 0,040 |
| barwa 0,75, jasność 0 (kol. 4) | 0,49 | −97 | 0,042 |
| w górę ×0,5 / ×0,75 | 0,49 | −97 | 0,042 |
| nasycenie | 0,49 | −97 | 0,048 |
| dla porównania: barwa 1,0, jasność 0 (r6) | 0,49 | −102 | 0,044 |
| dla porównania: barwa 0,75, jasność 0,5 (r6) | 0,40 | −97 | 0,042 |

Co z tego wynika:
- Odcień przesuwa się z −79° (granat wpadający w zieleń i szarość) do −97°. To wciąż 11° od ultramaryny Vermeera, w stronę cyjanu.
- Chroma jest o połowę za niska (0,042–0,048 wobec 0,085). Limit 1,3 ją przycina, bo dzieło ma tu dwa razy więcej chromy niż wynik.
- Fartuch jest jaśniejszy od dzieła (0,49 wobec 0,35), a i tak wygląda na brudny granat. LoRA kładzie tam ciemnoszare, mało nasycone pociągnięcia.

Gemini ma lepszy odcień (−115°), ale robi fartuch dużo jaśniejszy (0,62).

Ściana za Mleczarką jest we wszystkich wariantach gołym papierem: L 0,945, odchylenie 0,004. Szare zacieki z L 0,5 leżały więc nie na ścianie, tylko w pomalowanych miejscach przy niej.

## Co dalej (propozycja)
- Najprostsza poprawa błękitu to barwa 1,0 z limitem nasycenia około 2 zamiast 1,3, dalej bez ruszania L. Wtedy chroma fartucha powinna zbliżyć się do dzieła, a odcień do około −102°. To jedna lokalna przeróbka, mogę ją zrobić od razu.

## Pliki
- `J2-przywrocenie.jpg`: 13 dzieł, kolumny: dzieło | Gemini | barwa 0,75 jasność 0 | w górę 0,5 | w górę 0,75 | nasycenie.
- `J2-mleczarka.jpg`: Mleczarka w tych samych kolumnach, w powiększeniu.
