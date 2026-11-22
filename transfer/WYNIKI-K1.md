# Kreda 1: kreski kredą nad lokalnym podkładem (2026-11-22)

Podkład wszędzie ten sam: runda 7 (FLUX.2 klein 9B edit + LoRA frmstudy-2 w skali 2, potem lokalnie C16).
10 dzieł z rundy 7, każde z 4 do 6 kresek z nazwą. Warstwy wyciągnięte produkcyjnym `drawn.split`
z kolorami z `pencils`, liczone jak `marks_there`, zgodność z podkładem z `drawn.over` (poniżej 0,5 to odrzut).
„Na miejscu”: warstwa leży co najmniej w 60% w pudełku swojej kreski (z zapasem 8%). Ta miara jest moja,
nie produkcyjna: sprawdza, czy kolor trafił w swoje miejsce, a nie tylko czy w ogóle jest.

| wariant | kreski / oczekiwane | na miejscu | zgodność (mediana) | odrzuty | napisy | USD / arkusz | czas |
|---|---|---|---|---|---|---|---|
| G Gemini (produkcja, z NAS-a) | 48/48 | 45/48 | (własny podkład) | 0/10 | nie | ok. 0,12 (cały arkusz) | — |
| K klein 9B, polecenie produkcyjne | 3/48 | 1/48 | 0,31 | 9/10 | 2/10 | 0,025 | 4 s |
| K, drugie ziarno (9 odrzuconych) | 0/44 | 0/44 | 0,38 | 9/9 | — | 0,024 | 4 s |
| K2 klein 9B, ok. 120 słów | 46/48 | 15/48 | 0,84 | 0/10 | 3/10 | 0,025 | 3 s |
| Q Qwen-Image-Edit-2511 (5 dzieł) | 13/24 | 2/24 | 0,56 | 2/5 | 3/5 | 0,072 | 35 s |
| P lokalnie w Pythonie | 48/48 | 48/48 | 0,94 | 0/10 | nie | 0 | ok. 1 s |

Koszt rundy: 1,09 USD z 3 USD (`fal-runs.jsonl`, `"round": "kreda1"`).

## Gdzie co zawodzi

- **K (klein, długie polecenie, ok. 900 słów):** nie dodaje kresek. Przerysowuje cały podkład jako rysunek
  kredkami. Czasem dorysowuje dłoń z kredką (Las Meninas, Morze w Bognor) i podpisy („Ogon i grzbiet”
  przy Rousseau). Drugie ziarno daje to samo. Polecenie jest za długie i klein nie ma go jak utrzymać.
- **K2 (klein, krótkie polecenie):** podkład zostaje (zgodność 0,63–0,90), ale kreski to bazgroły w złych
  miejscach. Jedna kreska bywa kilkoma kolorami, a jeden kolor jest użyty do kilku kresek. Po
  `split` liczba „kresek” wychodzi dobrze (46/48), ale na miejscu leży tylko 15/48. Na 3 z 10 arkuszy coś
  napisał: kody kolorów przy Las Meninas, „Nie…pal” przy Czerwonym domu, podpis przy Rousseau. Raz
  przemalował szlafrok w paski (Kobieta myjąca się).
- **Q (Qwen 2511):** rysuje kredki jako przedmioty (leżące na arkuszu albo wbite w obraz), pisze
  etykiety i liczby (3 z 5) i przemalowuje podkład. Dwa arkusze odrzucone (Starzec 0,18, Boogie Woogie 0,16).
  Do tego jest najdroższy i najwolniejszy.
- **P (lokalnie):** każda kreska jest na miejscu i we własnym kolorze, napisów nie ma. `split` wyciąga
  z P wszystkie warstwy (48/48), więc produkcyjne numery i warstwy działają bez zmian. Wygląd:
  ziarno papieru z nierównym brzegiem, nacisk słabnie ku końcowi, drżenie ręki, część kresek
  pociągnięta dwa razy, boki trójkątów i pudełek wychodzą za narożniki, strzałki mają otwarty grot,
  echo to kółka z kropkowanym łukiem. Pętla idzie po sylwetce rzeczy (GrabCut w pudełku, kontur
  ściągnięty w połowie do otoczki). Gdy sylwetki nie da się znaleźć, pętla jest nieregularnym jajem.
  Słabsze strony: kreski są bardziej „wiedzące” niż u Gemini, a proste boki trójkątów i promienie nie
  przylegają do prawdziwych krawędzi (idą od punktu do punktu). Echo na dużych odległościach wygląda
  jak sznur kropek. Rytm przy Boogie Woogie wygląda jak linijka kresek.
- **G (Gemini):** najbardziej „nauczycielski” wygląd, linie przylegają do krawędzi. Rysuje jednak nad
  własnym podkładem, a nie nad r7+C16. Nad lokalnym podkładem musiałby dostać ten podkład w drugim
  wywołaniu, tak jak dziś (ok. 0,04 USD za kreski).

## Polecenie

Nad lokalnym podkładem kreski rysować **lokalnie (P)**: 0 USD, wszystkie na miejscu, nic napisanego,
podkład nietknięty. Klein i Qwen odpadają: bez LoRA nie umieją „tylko dodać” kresek, a długiego
polecenia klein nie trzyma. Jeśli liczy się wygląd ręki nauczyciela, druga droga to zostawić Gemini
tylko do kresek, nad podkładem r7+C16 (polecenie `LINES` bez zmian, ok. 0,04 USD za arkusz). Wtedy
warto porównać G i P nad tym samym podkładem. Dalsze kroki dla P: boki trójkątów, pudełek i promienie
dociągać do najbliższej krawędzi podkładu, echo rysować łukiem z przerwami zamiast kropkami, a rytm
krótszymi, nierównymi kreseczkami.

Pliki: `kreda-1.jpg` (dzieło | G | K | K2 | Q | P; K, K2 i Q pokazane tak, jak przyszły z modelu,
G jako strona z warstwami, P jak narysowane) oraz `kreda-1-zblizenia.jpg` (wycinki 1:1).
Skrypty: `~/Frame-worktrees/lokalny-model/kreda1/` (`prep`, `run_fal`, `chalk`, `run_p`, `measure`, `board`).
