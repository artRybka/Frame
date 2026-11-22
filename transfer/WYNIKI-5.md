# Runda 5: otwarty model bliżej wrażenia dzieła (2026-11-22)

**Koszt rundy 5: ok. 4,97 USD** (limit 25). 214 wywołań fal: klein 9B 1,88, Qwen-Image img2img 1,34, Qwen-Image-Edit-2511 0,75, FLUX.2 dev 0,71, klein 4B 0,27, opisy z VLM 0,02 USD. Koszt liczę z cennika fal (cena za MP, MP w górę). Każde wywołanie jest w `data/fal-runs.jsonl` (`"round": 5`). Gemini nie był wołany; jego podkłady służą tylko do porównania.

## Werdykt w skrócie
- **Polecenie samo nie wystarcza.** klein „rozjaśnia ciemne i gasi barwy” niezależnie od tego, jak go poprosić. Ani opis obrazu z VLM, ani zdanie „czarne zostaje czarne” nie uratowały Straży nocnej, Maneta, Rembrandta ani okna Hoppera.
- **Najwięcej daje para „przed i po”:** dzieło uproszczone lokalnie do mas przed modelem (B) i lokalna obróbka po modelu (D), która ustawia ciemności i barwę mas według dzieła.
- **Zwycięzca: B2 + DM na FLUX.2 [klein] 9B.** Na 12 dziełach testowych masy rosną z 0,80 (Gemini) do 0,92, różnica barwy spada z 10° do 5°, nasycenie z 0,70 do 0,94, a ciemność z +15 do +2. Walidacja (6 nowych dzieł) to potwierdza: masy 0,98, barwa 5°, nasycenie 0,95, ciemność 0.
- **Cena: mniej akwareli.** DM przybliża wrażenie, ale arkusz robi się bardziej „malarski”: ciemne zalewy są płaskie i cięższe, a przy papierze bywają twarde brzegi (Mleczarka, Delft). W najgorszych przypadkach wychodzi plakat (Seurat, Straż nocna). Surowe B2 wygląda bardziej jak studium, ale jest za jasne. Rozstrzygnąć to trzeba na oko i na ramie.
- **Okno Hoppera nie świeci w żadnym wariancie.** klein zawsze maluje wnętrze baru ciemnoszaro-niebiesko. DM przywraca zieleń ulicy, ale nie żółte światło.

## Pomiary (r5/impression.py, wobec dzieła)
Dzieło i wynik w tym samym rozmiarze (512 px), OKLab, rozmycie sigma = dłuższy bok/40. **masy** = korelacja rozmytej jasności (1 = ten sam układ), **barwa** = mediana różnicy odcienia, gdzie chroma dzieła > 0,03, **nasycenie** = chroma wyniku / dzieła, **ciemność** = 5. percentyl L wyniku minus dzieła ×100 (0 = tak głęboko jak dzieło), **papier** = % pikseli w ΔOKLab < 0,03 od #F5F1EA, **modelunek** jak w r4, **przesunięcie** = drawn.measure.

Mediany na 12 dziełach testowych (bez Wenus z lustrem, którą fal zaczernia u klein; patrz niżej):

| wariant | masy | barwa ° | nasycenie | ciemność | papier % | modelunek | przesunięcie % | nie nakłada się |
|---|---|---|---|---|---|---|---|---|
| Gemini (odniesienie) | 0,80 | 9,8 | 0,70 | +15 | 21 | 1,56 | 0,0 | 0 |
| r4: LoRA s2 | 0,75 | 14,5 | 0,56 | +17 | 26 | 1,62 | 1,5 | 2 |
| r4: LoRA s2 spłaszczona | 0,74 | 11,9 | 0,51 | +16 | 16 | 0,89 | 1,6 | 1 |
| A0: szablon opisowy, bez opisu | 0,81 | 9,7 | 0,99 | +22 | 20 | 1,45 | 0,5 | 1 |
| A: szablon + opis z VLM | 0,67 | 8,6 | 0,84 | +15 | 13 | 1,31 | 0,5 | 1 |
| B: dzieło uproszczone do mas | 0,86 | 10,9 | 0,88 | +15 | 26 | 1,44 | 0,6 | 0 |
| BD: B + opis z VLM | 0,77 | 10,8 | 0,84 | +10 | 17 | 1,67 | 0,7 | 0 |
| B2: B, „ciemne zostaje ciemne” | 0,83 | 11,5 | 0,93 | +11 | 25 | 1,44 | 0,6 | 1 |
| C: Qwen-Image img2img 0,6 z dzieła* | 0,97 | 4,7 | 0,96 | 0 | 0 | 1,43 | 0,7 | 2 |
| C: to samo, siła 0,8* | 0,86 | 8,4 | 0,92 | −2 | 0 | 1,42 | 2,6 | 6 |
| E: klein 4B, polecenie B | 0,77 | 10,7 | 0,36 | +21 | 35 | 1,24 | 0,8 | 0 |
| E: FLUX.2 dev, polecenie B (10 dzieł) | 0,87 | 11,3 | 1,11 | +4 | 8 | 1,34 | 0,4 | 0 |
| E: Qwen-Image-Edit-2511, polecenie B | 0,68 | 8,4 | 0,86 | +2 | 17 | 1,05 | **6,0** | 1 |
| D (DM) na r4 | 0,92 | 4,8 | 0,79 | +4 | 5 | 0,72 | 1,7 | 0 |
| D (DM) na A0 | 0,93 | 4,7 | 0,99 | +7 | 5 | 0,69 | 0,6 | 0 |
| D (DM) na FLUX.2 dev B (10 dzieł) | 0,93 | 5,5 | 0,97 | 0 | 7 | 0,75 | 0,3 | 0 |
| **B2 + DM (zwycięzca)** | **0,92** | **4,6** | **0,94** | **+2** | 5 | 0,68 | 0,5 | 0 |

\* C to nie jest studium, tylko prawie kopia obrazu: 0% papieru, a przy sile 0,8 model zmyśla (bazgroły u Matisse'a, przy Żniwach zgubione postaci).

Walidacja, 6 dzieł (Lucas, Seurat, Pissarro, Hollar, Syberg, Munch; trzy z nich to grafiki i rysunki prawie bez barwy):

| wariant | masy | barwa ° | nasycenie | ciemność | papier % | modelunek | nie nakłada się |
|---|---|---|---|---|---|---|---|
| A0 + nic | 0,87 | 8,8 | 1,22 | +23 | 17 | 1,38 | 1 |
| B2 | 0,93 | 11,3 | 1,08 | +5 | 32 | 1,86 | 0 |
| A0 + DM | 0,96 | 4,8 | 0,94 | +6 | 17 | 0,71 | 2 |
| **B2 + DM** | **0,98** | **5,0** | **0,95** | **0** | **20** | 0,92 | 0 |
| FLUX.2 dev B + DM (4 dzieła) | 0,98 | 5,6 | 1,03 | 0 | 21 | 0,73 | 0 |

**Papier:** w testach mediana po DM to tylko 5%, bo DM zostawia papier tylko tam, gdzie dzieło jest jasne i prawie bez barwy. W ciemnych dziełach (Straż nocna, Manet, Rembrandt, Wenus) papieru prawie nie ma, czyli zgodnie z zasadą „ciemności jak w dziele”. W walidacji jest 20%. Jeśli 10–20% ma obowiązywać zawsze, kłóci się to z ciemnością dzieła. Trzeba wybrać, co ważniejsze.

## Co działa, a co nie
- **A, polecenie opisowe.** Sam szablon opisowy (A0, bez opisu) podnosi nasycenie z 0,56 (r4) do 0,99, czyli klein lepiej słucha opisu wyglądu niż rozkazów. Opis konkretnego dzieła z otwartego VLM (Qwen3-VL-30B-A3B, 60–150 słów, cięty do ≤75) **psuje masy** (0,81 → 0,67): klein rysuje według słów i przesuwa duże plamy (niebo Delft, Wenus). Pierwsza wersja polecenia dla VLM miała przykłady barw, a VLM je papugował („saturated vermilion dress” u Hokusaia), więc przykłady trzeba było usunąć. Opis nie jest potrzebny w zwycięskim potoku.
- **B, uproszczenie do mas** (r5/simplify.py: mean shift + plamy w średnim kolorze, 0,4 s): najlepsze masy bez obróbki (0,86) i nic nie dorysowuje. Słabość: w bardzo ciemnych dziełach klein robi z ciemności papier (Straż nocna: 78% papieru, Manet i Rembrandt jasne). Zdanie o ciemnościach w B2 tego nie zmienia.
- **C, img2img z siłą:** nie nadaje się. Sprawdziłem siłę 0,6 (z dzieła i z B) oraz 0,8. Przy 0,6 zostaje obraz, przy 0,8 model zmyśla i przestaje się nakładać.
- **D, obróbka końcowa** (r5/post.py `toward2`, wersja DM, 3 s lokalnie): krzywa jasności przez dopasowanie kwantyli do dzieła (0,7), barwa mas przez lokalne przesunięcie a,b (0,7, jak `restorer.recoloured`), papier tylko w jasnych i bezbarwnych miejscach dzieła (miękki brzeg), na koniec spłaszczanie z r4. Działa na każdym modelu i daje największą zmianę w liczbach. Ma też wady:
  - twarde brzegi przy papierze;
  - gdzie model zostawił papier w ciemnym miejscu, wychodzi płaska szara plama (Straż nocna);
  - przy dziełach prawie bez barwy wychodzi plakat (Seurat).
  Wersja D (pełne przesunięcie mas) robiła z arkusza przemalowany obraz, a D2 zjadała papier, dlatego zostało DM.
- **E, inne modele:**
  - **FLUX.2 dev** daje najbogatsze barwy i ciemności nawet bez obróbki (ciemność +4), ale jest 4–5× wolniejszy, a filtr fal odrzucił mu 5 z 19 dzieł.
  - **klein 4B** jest blady (nasycenie 0,36, papier 35%).
  - **Qwen-Image-Edit-2511** dorysowuje brzeg kartki i ramkę (przesunięcie 6%, porażka).
- **Filtry fal.** Wenus z lustrem jest zaczerniona przez oba endpointy klein (także `/edit/lora`), FLUX.2 dev odrzuca Wenus, Straż nocną, Goyę, Muncha i Hollara (szkielet), a Qwen-Image i Qwen-Edit odrzucają Wenus i część losowań Goi. To cecha fal, nie modeli: lokalnie tego filtra nie będzie, więc wynik tych dzieł trzeba sprawdzić na Macu.

## Rekomendacja potoku dla Mac Studio
1. **Uproszczenie do mas** (OpenCV, `r5/simplify.py`): mean shift w Lab na 768 px, plamy w średnim kolorze, mediana 5. Ok. 0,5 s.
2. **FLUX.2 [klein] 9B edit, 4 kroki,** obraz z kroku 1 jako wejście, polecenie B2 (`r5/prompts.py`), rozmiar dzieła ≤1536 px. Bez VLM i bez LoRA.
3. **Obróbka DM** (`r5/post.py toward2(kl=0.7, kab=0.7, pale_c=0.07, paper_top=0.25, feather=5)`): ok. 3 s w Pythonie.
4. Opcjonalnie zamiast 2: FLUX.2 dev, jeśli liczy się barwa, a czas nie.

**Szacowany czas na Mac Studio** (to szacunek, nie pomiar: na fal klein 9B liczy 1,4 s na H100, FLUX.2 dev 11 s):
- klein 9B, 4 kroki, ok. 2 MP: **20–40 s** na M3 Ultra / M4 Max (MLX lub diffusers + MPS, bf16, ok. 20 GB pamięci);
- z krokami 1 i 3 całość to **ok. 25–45 s na podkład**;
- FLUX.2 dev (32B, 28 kroków): **4–8 min**, ok. 64 GB w bf16 lub 35 GB w 8 bitach;
- gdyby jednak użyć opisu z VLM: Qwen3-VL-30B-A3B w MLX (4 bity, ok. 18 GB) to ok. 5–10 s na opis.

**Co dalej (moja propozycja):**
1. Uruchomić klein 9B lokalnie i zmierzyć prawdziwy czas.
2. Obejrzeć na ramie B2 + DM obok surowego B2 i Gemini.
3. Dobrać siłę DM (kl 0,5–0,8) na oko, bo tu liczby i „akwarelowość” idą w przeciwne strony.
4. Na ciemne dzieła rozważyć wejście B bez rozjaśnienia albo DM z mniejszym spłaszczaniem.

## Plansze
- `I-runda5.jpg`: 13 dzieł testowych. Kolumny: dzieło | Gemini | najlepszy r4 (LoRA s2) | A (opis z VLM) | B (B2) | C (img2img 0,6) | D (DM na r4) | E (FLUX.2 dev) | zwycięzca (B2 + DM). Pod obrazem: masy, barwa, nasycenie, ciemność, papier, modelunek, przesunięcie, czas, koszt.
- `I-walidacja.jpg`: 6 dzieł spoza treningu i testów (5 nowych na NAS-ie bez podkładu Gemini + Pissarro odrzucony z treningu w r3). Kolumny: dzieło | Gemini | B2 | B2 + DM | FLUX.2 dev + DM | A0 + DM.

## Pliki
Skrypty są w `~/Frame-worktrees/lokalny-model/r5/`:
- `impression.py`: pomiary;
- `fal5.py`: wywołania i log;
- `prompts.py`: polecenia;
- `describe.py`: opisy z VLM;
- `simplify.py`: B;
- `runA.py`, `runB.py`, `runC.py`: wywołania modeli;
- `post.py`: D;
- `measure5.py`, `table.py`, `board5.py`, `fetch5.py`: pomiary zbiorcze, tabele, plansze, pobranie dzieł walidacyjnych.

Wyniki, opisy i pomiary: `data/r5/` (`measure.json`, `desc/`).
