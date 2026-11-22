# Runda 6: LoRA s2 + przywrócenie barw dzieła (2026-11-22)

**Koszt rundy 6: 0 USD.** Wszystko liczyłem lokalnie na gotowych wynikach z rundy 4 (LoRA w skali 2, `data/r4/*-frmstudy-2-s2.png`). fal nie był wołany. Gemini służy tylko do porównania.

## Werdykt w skrócie
- **Polecam: barwa 0,75, jasność 0,5 (`R75L50`).** Na 13 dziełach masy rosną z 0,75 (surowa LoRA) do 0,87, różnica barwy spada z 14° do 4°, nasycenie rośnie z 0,57 do 0,73, a ciemność spada z +16 do +10. W każdej z tych liczb wynik jest bliżej dzieła niż Gemini (0,80 / 10° / 0,72 / +15). Kreska, zalewy i papier zostają jak u LoRA, a modelunek się nie spłaszcza (1,65 wobec 1,62 u surowej).
- **Barwa 1,0 (`R100L50`)** daje to samo, tylko trochę mocniej nasycone (0,80). Na planszy różnica jest ledwo widoczna. To dobra druga opcja, jeśli na ramie 0,75 wyjdzie za blado.
- **Bez jasności (`L0`)** naprawia barwę, ale nie masy ani ciemność (masy zostają na 0,75, ciemność +16). Ciemne dzieła (Straż nocna, Manet, Żniwa) zostają za jasne. Zostaje tylko jako ostrożny wariant, jeśli L 0,5 gdzieś brudzi.
- **Hopper się nie poprawia.** LoRA namalowała wnętrze baru ciemnogranatowe, a ulicę zostawiła jako papier, czyli odwrotnie niż w dziele. Przywrócenie na skali mas poprawia odcień (z 68° do 6°), ale nie odwróci jasności: bar zostaje ciemny, a ulica biała. Tego nie naprawi żadna obróbka po rysowaniu. Pomogłoby tylko inne wejście albo inny model (w rundzie 5 to samo było przy klein).
- **Vermeer:** błękit wraca.
  - Delft: niebo między chmurami jest znów niebieskie, chmury i woda ciemnieją jak u Vermeera. Najjaśniejsze partie nieba zostają gołą kartką (papier 35%), więc niebo jest mniej błękitne niż u Gemini.
  - Mleczarka: fartuch i obrus wracają do granatu. Przy L 0,5 ściana za nią dostaje szare, nierówne zacieki, bo dzieło jest tam ciemniejsze niż kartka LoRA. To jedyne miejsce, gdzie L 0,5 widać jako „brud”.

## Jak liczę przywrócenie (`r6/restore.py`)
W OKLab: `wynik += s · (rozmyte dzieło − rozmyty wynik) · pomalowane`, sigma = dłuższy bok/40 (skala mas), jak `restorer.recoloured` na serwerze.
- **s osobno dla barwy i jasności:** a,b ∈ {0,5; 0,75; 1,0}, L ∈ {0,5; 0}. To 6 wariantów, nazwy `R{ab}L{L}`.
- **Papier zostaje papierem.** Maska „pomalowane” to odległość od #F5F1EA > 0,03 (miękko między 0,02 a 0,04, rozmyta o 2 px). Goła kartka się nie barwi.
- **Rozmyty wynik liczę tylko z pomalowanych pikseli** (średnia ważona maską). Bez tego papier wokół plamy zaniżałby barwę wyniku i plama dostawałaby za dużo koloru.
- Bez sprowadzania do mas i bez spłaszczania, więc nie ma pop-artu jak w DM z rundy 5. Czas: ok. 0,7 s na wariant na Macu (Python, lokalnie).

## Pomiary (`r5/impression.py`, wobec dzieła)
Opis miar jak w WYNIKI-5. Mediany na 13 dziełach testowych (Wenus też jest, bo LoRA z r4 jej nie zaczerniła):

| wariant | masy | barwa ° | nasycenie | ciemność | papier % | modelunek |
|---|---|---|---|---|---|---|
| Gemini (odniesienie) | 0,80 | 10,4 | 0,72 | +15 | 23 | 1,55 |
| LoRA s2 surowa (r4) | 0,75 | 14,3 | 0,57 | +16 | 26 | 1,62 |
| barwa 0,5, jasność 0 | 0,75 | 6,3 | 0,68 | +16 | 26 | 1,62 |
| barwa 0,75, jasność 0 | 0,75 | 3,8 | 0,72 | +16 | 25 | 1,62 |
| barwa 1,0, jasność 0 | 0,75 | 1,6 | 0,78 | +16 | 25 | 1,62 |
| barwa 0,5, jasność 0,5 | 0,87 | 6,3 | 0,68 | +10 | 19 | 1,65 |
| **barwa 0,75, jasność 0,5 (polecam)** | **0,87** | **3,7** | **0,73** | **+10** | **19** | **1,65** |
| barwa 1,0, jasność 0,5 | 0,87 | 1,5 | 0,80 | +10 | 19 | 1,65 |
| dla porównania r5: B2 + DM (klein) | 0,92 | 4,6 | 0,94 | +2 | 5 | 0,68 |

Uwaga do „barwy”: przywrócenie i pomiar działają na tej samej skali rozmycia, więc przy s = 1 różnica odcienia spada prawie do zera z definicji. Niska liczba nie znaczy, że kolor „wygląda” dokładnie jak w dziele, tylko że masy mają ten sam odcień. Lepiej rozstrzyga nasycenie i oko.

Wybrane dzieła (masy · barwa · nasycenie · ciemność · papier):

| dzieło | Gemini | LoRA s2 | 0,75 / 0,5 |
|---|---|---|---|
| Vermeer, Widok Delftu | 0,95 · 10° · 0,65 · +15 · 24% | 0,88 · 12° · 0,50 · +30 · 44% | 0,94 · 3° · 0,75 · +16 · 35% |
| Vermeer, Mleczarka | 0,87 · 9° · 0,65 · +31 · 29% | 0,76 · 17° · 0,48 · +25 · 41% | 0,93 · 7° · 0,68 · +13 · 35% |
| Hopper, Nocne marki | 0,71 · 32° · 0,59 · +11 · 9% | 0,67 · 68° · 0,19 · +13 · 28% | 0,87 · 6° · 0,49 · +6 · 24% |
| Rembrandt, Straż nocna | 0,41 · 4° · 1,00 · +15 · 6% | 0,35 · 4° · 0,65 · +27 · 14% | 0,55 · 2° · 0,66 · +11 · 9% |
| Hokusai, Wielka fala | 0,91 · 4° · 0,31 · −4 · 23% | 0,76 · 15° · 0,41 · +10 · 53% | 0,84 · 8° · 0,52 · +10 · 37% |

Hopper w liczbach wygląda nieźle (masy 0,87), ale na oko jest źle: rozmyta jasność zgadza się z grubsza, a jasny i ciepły bar wciąż jest ciemny. To przykład, że miary mas nie łapią odwróconego światła w małym fragmencie.

## Porównanie z rundą 5
B2 + DM (klein) jest bliżej w liczbach (ciemność +2, nasycenie 0,94), ale płaci za to płaskimi, plakatowymi plamami (modelunek 0,68) i prawie bez papieru (5%). LoRA + przywrócenie 0,75/0,5 zostaje akwarelą: modelunek 1,65, papier 19%. Z ciemnych dzieł nie zrobi jednak tak głębokich, jak są w oryginale.

## Co dalej (propozycja)
1. Obejrzeć na ramie `R75L50` obok Gemini i surowej LoRA, głównie Mleczarkę (zacieki na ścianie) i Delft.
2. Jeśli L 0,5 brudzi jasne ściany, ograniczyć przywrócenie jasności do ściemniania tam, gdzie wynik jest jaśniej niż dzieło o więcej niż próg. Albo dać L 0,35.
3. Hopper i podobne (jasne okno w ciemnym obrazie) wymagają innego rysunku, nie obróbki.

## Plansza
`J-przywrocenie.jpg`: 13 dzieł testowych. Kolumny: dzieło | Gemini | LoRA s2 surowa | barwa 0,75 + jasność 0 | barwa 0,75 + jasność 0,5 | barwa 1,0 + jasność 0,5. Pod obrazem pomiary.

## Pliki
Skrypty są w `~/Frame-worktrees/lokalny-model/r6/`:
- `restore.py`: przywrócenie;
- `measure6.py`: pomiary;
- `board6.py`: plansza.

Wyniki i `measure.json`: `data/r6/`.
