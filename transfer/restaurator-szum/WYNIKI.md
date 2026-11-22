# Restaurator: mniej zmyślania i ostrość Valtata (2026-11-22)

Kod: origin/main 1.145.320. SeedVR2 na fal (`fal-ai/seedvr/upscale/image`), seed 1234. Wynik zrobiony tak jak na serwerze: `descreened` → `fit` → `recoloured`. 52 wywołania, **0,162 USD** (limit 0,40).
Dzieła: 1 Janinet, 2 Valtat, 3 Hopper, 4 Kahlo, 5 Herod, 6 Ender (akwarela), 7 Barocci (rysunek), 8 Cézanne. Ender i Barocci mają duże oryginały, więc do próby zmniejszyłem je do 720 i 640 px.

Pomiar wierności: wariant i źródło zmniejszone do 50% źródła, liczę ΔE w OKLab ×100. „Dodane” to szczegół drobniejszy, niż źródło może pomieścić (L ×100).

## szum.jpg: średnia z 8 dzieł

| wariant | ΔE do źródła | dodane |
|---|---|---|
| Lanczos | 0,11 | 0,42 |
| 1 obecny (szum 0,1) | 1,38 | 2,16 |
| 2 szum 0,03 | 1,31 | 2,20 |
| 3 szum 0 | 1,31 | 2,23 |
| 4 szum 0, czynnik ≤ 2 | 1,51 | 1,99 |
| 5 pół na pół z Lanczosem (OKLab) | **0,75** | **1,10** |

- **Szum prawie nic nie zmienia.** 0,03 i 0 obniżają ΔE o ok. 5%, ale szczegółu jest tyle samo. Gruby kontur Janineta (dziecko, fałdy) i „kreskówkowe” oczy Hoppera i Endera wyglądają tak samo w 1, 2 i 3. To robi sam model, a nie szum.
- **Czynnik ×2 jest gorszy.** ΔE rośnie. U Kahlo wychodzi wyraźna siatka, a Valtat jest bardziej poszarpany.
- **Pół na pół (5) wygląda najnaturalniej.** Kontur jest cieńszy, faktura i włosy zostają, ale nie są wymyślone na nowo. ΔE i dodany szczegół spadają mniej więcej o połowę, a obraz jest wciąż ostrzejszy niż sam Lanczos. Kosztuje 0 USD.

**Polecenie:** w `restorer._keep` po `recoloured` mieszać w OKLab: wynik = 0,5·Lanczos(obraz) + 0,5·rysunek. Waga może być stałą (`DRAWN = 0.5`). `noise_scale` zostawić jak jest albo dać 0,03, to bez znaczenia.

## valtat-ostrosc.jpg: wejście do SeedVR2 dla małych źródeł

| | a bez descreen | b SOFT 0,3 (teraz) | c 0,38 | d 0,42 | e tylko punkty | f = b, szum 0,2 |
|---|---|---|---|---|---|---|
| Valtat: siatka | **10,2** | 4,6 | 4,4 | 4,5 | 4,8 | 4,5 |
| Valtat: ostrość | 17,5 | 12,7 | 13,8 | **14,3** | 13,5 | 12,8 |

Siatka to średnie wystawanie punktów siatki z (a) nad widmo, mediana z kafli 256 px. Bez siatki jest ok. 4,5, a Lanczos ze źródła daje 5,8. Ostrość to energia L powyżej 0,1 cykla/px ×1000.

- **SOFT 0,42 (d)**: siatki nie ma, tak samo jak w (b), a ostrość wraca do połowy drogi do (a). Na wycinku deski i liny są wyraźniejsze niż w (b).
- **(e) wąskie wycięcia** daje mniej niż (d). Do tego próg 1,3 jest za niski: „siatkę” znalazł w każdym z 4 dzieł (Kahlo, Herod, Cézanne też), więc warunek nie odróżnia rastra.
- **(f) szum 0,2** ostrości nie dodaje.
- U Herodu i Cézanne’a od a do f prawie nic się nie zmienia.
- **Kahlo** ma własny raster (okres ok. 3,3 px, stoi ok. 2 < STANDS 3). Siatka zostaje we wszystkich wariantach a–f i nic z tego jej nie zdejmuje. To osobna sprawa.

**Polecenie:** `descreen.SOFT = 0.42`.
