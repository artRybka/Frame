# Runda 7: 20 dzieł ze studiów — wybrany model

Model: FLUX.2 klein 9B edit + LoRA `frmstudy-2` w skali 2 (fal `flux-2/klein/9b/edit/lora`, polecenie z rundy 4),
jedno losowanie na dzieło, potem lokalnie C16 z rundy 6c (barwa a,b 1,0, nasycenie do ×1,6, L bez zmian, papier chroniony).
Plansza: `K-20.jpg` (dzieło | model).

**Dobór dzieł.** Na NAS-ie jest 124 studiów; każde było już w treningu, w testach albo w walidacji, poza 19 parami
odrzuconymi na oko z treningu w rundach 3/4. Z nich 6 to grafiki i rysunki jednobarwne (pominięte), zostało **13 dzieł
nigdy niewidzianych przez model (1–13)**. Studium dnia nie daje nic nowego (wszystkie dni z /api/daily są wśród tych 124).
Brakujące **7 (14–20) to dzieła z treningu LoRA** (portret, ciemne wnętrze, dżungla, płaski Hopper, szeroki pejzaż,
wielopostaciowe), oznaczone na planszy „w treningu”.

**Koszt:** 0,615 USD (21 wywołań: 20 + 1 powtórka; Sando Hyosho za pierwszym razem wrócił czarny — fałszywy alarm NSFW,
drugie ziarno w porządku).

**Mediany** (wobec dzieła; masy 1 = ten sam układ jasności, barwa w °, nasycenie 1 = jak dzieło, ciemność + = jaśniej, papier %):

| | masy | barwa | nasycenie | ciemność | papier |
|---|---|---|---|---|---|
| 20 dzieł, LoRA s2 sama | 0,75 | 11,9° | 0,56 | +11,6 | 28 % |
| **20 dzieł, LoRA s2 + C16** | **0,75** | **2,0°** | **0,83** | **+11,6** | **26 %** |
| 13 nowych, + C16 | 0,83 | 2,0° | 0,80 | +11,4 | 28 % |
| 7 z treningu, + C16 | 0,71 | 1,9° | 0,89 | +20,5 | 17 % |

**Gdzie słabo.** Dzieła z gęstym, drobnym wzorem na ciemnym tle tracą układ mas: tanka tybetańska (masy 0,14 — ciemna
czerwień tła rozpada się w jasne plamki), Gendżi na złotym tle (0,26) i tłum na targu Myersa (0,48) stają się jasnym,
rozbitym szkicem. Ciemne obrazy wychodzą wyraźnie jaśniej, bo C16 nie rusza jasności (Las Meninas +37, Rousseau +25,
Myers +26), a płaskie, jasne dzieła mają za dużo gołego papieru (Mondrian 70 %, akwarela Hoppera 51 %, Chełmoński 47 %).
