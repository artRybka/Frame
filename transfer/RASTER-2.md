# Raster 2: SeedVR2 z `descreened` i bez (acaeb638)

Przepuściłem 8 dzieł przez prawdziwy restaurator: fal SeedVR2 do `LONGEST` 2048, potem `fit` i `recoloured`, tak samo jak serwer. Każde dzieło raz z obrazem jak dotąd, raz po `descreened`. Wszystko na Macu. **Koszt 0,051 USD** (16 wywołań), limit 0,20 USD.
Plansza `restaurator.jpg` ma kolumny: podgląd wyniku | wycinek 1:1 jak dotąd | wycinek 1:1 po descreened | lewy górny róg 1:1 (brzeg) jak dotąd | po descreened.

Dzieła:
- 1–6: małe źródła (≤ 1000 px). Valtat, Verdilhan, strona tytułowa „Jan Vermeer” (druk i pismo odręczne), „Ships moored” (300 px, cienkie liny), Monet „Michel au bonnet”, Met „Gloves” (drobny wzór).
- 7–8: druki z rastrem, „Portrait of a man” (566×800) i Mucha „Job” (1500×2005).
- Kahlo „Two Fridas” (2206 px) i Van Gogh „Sunflowers” (2526 px) mają ≥ 2048 px, więc restaurator ich nie bierze (`check`: „large”). Wziąłem zamiast nich te dwa.

## Valtat
- **Siatka znikła.** W kopii jak dotąd ukośna siatka o okresie ok. 7 px wystaje w kafelkach 256 px 10–234 razy ponad tło widma (mediana 53). Po descreened jest to 5–20 (mediana 6), czyli tyle co szum. Na wycinku 1:1 wyraźną kratkę zastępuje gładka farba.
- `screen()` dalej znajduje 0 punktów. Pomaga tylko łagodne zdjęcie ziarna drobniejszego niż 3 px (`SOFT`). Źródło zmienia się średnio o 1,9 poziomu.

## Rysunki i drobna kreska (3, 4, 6, także 2 i 5)
- **Ostrość kreski bez zmian.** Litery „VERMEER”, pismo odręczne, liny statków i wzór rękawiczek wyglądają na wycinkach 1:1 tak samo. SeedVR2 i tak rysuje kreskę na nowo, a 3 px przy ×3,5 to poniżej tego, co widać jako krawędź. Różnic między kolumnami prawie nie widać.

## Druki 7 i 8
- 7 („Portrait of a man”, wykryto 4 punkty): po descreened restauracja jest **lepsza**. Bez tego SeedVR2 robi z rastra przerysowane, „rzeźbione” zmarszczki, a po descreened skóra jest naturalna.
- 8 (Mucha „Job”, 8 punktów): podobnie jak dotąd. Kropkowanie dymu z oryginału zostaje, bo to wzór z samego plakatu.

## Brzegi
- Lustrzane odbicie działa. W żadnym rogu nie ma paska ani ringingu.

## Czas i pamięć `descreened` (Mac)
| obraz | nowe (acaeb638) | stare (7231eb23) |
|---|---|---|
| 4000×2714 (MNK „Szermierka”, 6 pkt) | 2,9 s, szczyt +630 MB | 2,6 s, +585 MB |
| 1500×2005 (Mucha „Job”, 8 pkt) | **3,2 s**, +420 MB | 1,6 s, +360 MB |
| małe ≤ 1000 px | 0,02–0,5 s | — |

- **Pamięci nie ubyło.** float32 oszczędza, ale padding (+8%), osobna maska `both` (2 kanały), wynik mnożenia `spectrum * both` i kopia `big` zjadają tę oszczędność.
- **Na krzywych rozmiarach jest 2× wolniej.** 2005 + 2·80 = 2165 = 5·433, a cv2.dft na rozmiarach z dużym czynnikiem pierwszym jest wolne. Rada: dopełnić do `cv2.getOptimalDFTSize` (2187 i 1728). Do tego mnożyć w miejscu (`cv2.mulSpectrums` albo `spectrum *= both`) i nie trzymać `both`.
- Restaurator bierze tylko obrazy poniżej 2048 px, więc 4000 px w praktyce się nie zdarzy. Najgorszy realny przypadek to ok. 2047×2047, czyli ok. 3 s i ok. 0,5 GB.

## Wniosek
Wersja acaeb638 robi to, o co chodziło: **siatka Valtata znika**, rysunki i pismo nie tracą ostrości, brzegi są czyste, a druk 7 wychodzi nawet lepiej. Przed wdrożeniem zostaje szybkość i pamięć (rozmiar DFT, mnożenie w miejscu).
