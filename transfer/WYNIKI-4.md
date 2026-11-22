# Runda 4: druga LoRA dla FLUX.2 [klein] 9B i „więcej plamy” (2026-11-22)

**Koszt rundy 4: 8,38 USD** (limit 10). Trening kosztował 7,17, testy 1,21 (39 obrazów). Spłaszczanie robione lokalnie, więc 0 USD. Każde wywołanie jest w `data/fal-runs.jsonl` (`"round": 4`).

## Werdykt w skrócie
- **Nowa LoRA w skali 1 = LoRA z rundy 3.** Obrazy są prawie identyczne (ΔE mas, mediana 34 wobec 34). Więcej par (86 zamiast 59) i wyższe lr nic nie zmieniły.
- **Skala 2 jako pierwsza robi coś w stronę Gemini: zostawia więcej gołego papieru.** Najwyraźniej u Moneta, w Mleczarce, Żniwach i Delft. Płaci za to geometrią: przesunięcie rośnie z 0,2–0,9% do 0,6–5,4% (Hopper 5,4%, tuż pod progiem 6%). Do tego psuje szczegóły: w Nocnych markach oświetlone okno baru robi się ciemne, w Wenus twarz w lustrze ciemnieje, a u Goi spodnie zmieniają kolor na żółty.
- **Straż nocna: nie poprawiła się.** We wszystkich wariantach nadal jest jasny tłum i pomiar „nie nakłada się”. W skali 2 ciemna góra jest bliżej Gemini, ale postaci zostają jasne i dopowiedziane.
- **Żebrak: trochę lepiej, ale nie dobrze.** W skali 2 tło jest głęboko ciemne jak u Gemini, a płaszcz szaro-oliwkowy zamiast brązowego z rundy 3. Zielony jak u Gemini nadal nie jest. Pomiar w skali 2 „nie nakłada się” (na oko się nakłada; ciemny obraz myli pomiar), polecenie „płasko” daje 2,6%.
- **Barwy Matisse'a: bez postępu.** Skala 2 jest bladsza, ale bez żółci i turkusu Gemini.

## „Więcej plamy, mniej światłocienia w plamie”
Pod obrazami na planszy jest nowa liczba **modelunek**: średni spadek jasności wewnątrz plam (gradient L poniżej krawędzi, 512 px). Im mniej, tym płaściej. Mediany z 13 dzieł:

| wariant | modelunek | ΔE mas | uwagi |
|---|---|---|---|
| Gemini | 1,55 | 36 | punkt odniesienia |
| nowa LoRA skala 1 | 1,89 | 34 | najbardziej „cieniowana” |
| nowa LoRA skala 2 | 1,62 | 36 | |
| nowa LoRA skala 2 + polecenie „płasko” | 1,50 | 35 | ledwo widać; klein prawie nie słucha tego dopisku |
| **Gemini spłaszczony lokalnie** | **0,96** | 35 | barwy i położenie bez zmian (przesunięcie 0,0–0,6%) |
| **nowa LoRA s2 spłaszczona lokalnie** | **0,94** | 36 | j.w. |

**Najlepiej „więcej plamy” daje lokalna obróbka końcowa, nie polecenie.** Modelunek spada o ok. 40% i nic nie kosztuje: kilka sekund na Macu, bez modelu. Przesunięcie i barwy dużych plam się nie zmieniają. Kontury i linie piórka zostają, bo sąsiednie piksele o podobnym kolorze stają się jedną plamą w średnim kolorze, a cienkie ciemne kreski są przenoszone z oryginału. Na oko: gorset Mleczarki, ściana, niebo w Delft i tło portretów to teraz jednolite plamy. Mniejsze plamy zostają osobno, więc obraz nie zmienia się w plakat. Dopisek do polecenia klein prawie ignoruje.

Obróbka: `r4/flatten.py` (OpenCV: mean shift w Lab, `sp=12`, `sr=24`, potem łączenie sąsiadów w zasięgu 12, średni kolor plamy, czarny kapelusz morfologiczny 7 px na linie). Łatwo ją przenieść na serwer, np. jako krok po podkładzie Gemini. Siłę reguluje jeden parametr (zasięg plamy 8–14).

## Rekomendacja
1. **Nie wpinać nowej LoRA.** Skala 1 nic nie daje, a skala 2 przesuwa obraz i psuje szczegóły (okno u Hoppera, lustro u Velázqueza). Zysk w „mniej niż obraz” jest za mały na takie ryzyko.
2. **Jeśli „więcej plamy” ma trafić do ramy, to jako lokalne spłaszczanie podkładu Gemini.** To najtańszy i najpewniejszy krok: działa na każdym podkładzie i nie rusza geometrii. Warto obejrzeć kolumnę „Gemini spłaszczony” na ramie i dobrać siłę.
3. Dalsze LoRA tylko lokalnie (Mac Studio, ai-toolkit): trener fal nie daje rank ani checkpointów, a dwie próby za 11,4 USD pokazały, że sama skala danych i lr niewiele zmieniają.

## Co zrobiłem
- **Pary:** 86 = 59 z rundy 3 + 27 nowych z NAS-a (124 studia, wszystkie z muzeów). Poza treningiem zostało 13 dzieł testowych. Odrzucone: 5 bez podkładu, 2 z przesunięciem ponad 1,5% (Cassatt, Pissarro), 7 po obejrzeniu: 2 zwoje (Gendżi, kwiaty i owady), 4 rysunki i szkice, do których Gemini dorysował treść, 1 akwarela (Morze w Bognor). Skrypt `r4/fetch4.py`, pliki w `data/r4/pairs/`.
- **Trening:** `fal-ai/flux-2-klein-9b-base-trainer/edit`, **1700 kroków**, lr 1e-4, ten sam podpis ze słowem `frmstudy`, 32 min, 7,17 USD. Trener nie ma rank ani zapisu checkpointów, a kroki muszą być wielokrotnością 100. 2000 kroków kosztowałoby 8,44 USD, a na testy zostałoby mniej niż 2 USD.
- **Testy:** `fal-ai/flux-2/klein/9b/edit/lora`, polecenie jak w rundzie 3 (krótkie D ze słowem `frmstudy`), skala 1 i 2, oraz skala 2 z dopiskiem „płasko”: *„Every patch of colour is flat and even, one tone from edge to edge: no shading, no modelling, no light and shade inside a patch.”* Jedno losowanie na dzieło, ziarna jak w rundzie 3. Czas 3–27 s, 0,030–0,045 USD za obraz.

## Plansza
`H-lora2.jpg`, 13 dzieł, numerowane. Kolumny: dzieło | Gemini | LoRA runda 3, skala 2 | nowa LoRA, skala 1 | skala 2 | Gemini spłaszczony | nowa LoRA s2 + „płasko” | nowa LoRA s2 spłaszczona. Pod obrazem: przesunięcie, ΔE mas, modelunek, czas, koszt.

## Pliki
- Wagi: `~/Frame-worktrees/lokalny-model/lora/frmstudy-2.safetensors` (127 MB) i `frmstudy-2-config.json`. Słowo wyzwalające: `frmstudy`.
- Skrypty: `~/Frame-worktrees/lokalny-model/r4/` (`fetch4.py`, `train.py`, `test4.py`, `flatten.py`, `board4.py`, `caption.txt`). Wyniki i pomiary: `data/r4/` (`measure.json`).
