# Kreda 3: groty, kółka, rytm, ruch (2026-11-22)

Te same 10 dzieł i ten sam podkład r7+C16. Kreski rysuje Python, 0 USD.
Skrypty: `~/Frame-worktrees/lokalny-model/kreda3/`.

## Zmiany w P3

- **Groty**: na każdą strzałkę losowany jest jeden z wariantów A, B, C, D. Losowanie jest powtarzalne,
  bo ziarno bierze się z dzieła. Wielkość grotu jest stała względem arkusza, niezależnie od długości
  strzałki: zadziory mają 3,5–5,8% dłuższego boku, czyli ok. 5–7 grubości kreski. Na wycinkach
  w 1/3 (`ruch.jpg`, jak na telefonie) groty są czytelne.
- **Kółka powtórzeń**: wielkość bierze się z rzeczy. GrabCut w oknie wokół miejsca daje tylko rozmiar
  i środek, kształt nadal jest swobodnym owalem. Promień mieści się między 3% a 7% dłuższego boku.
  Wada: przy rzeczy wielobarwnej na ruchliwym tle (parasole w Jefferson Park) GrabCut bierze tylko
  część, więc jeden parasol dostał małe kółko, a drugi wąski, wysoki owal. Duże zwykle wychodzą
  dobrze, np. czerwona suknia i dziewczynka na Grande Jatte.
- **Rytm**: przyczyna rozjazdu leżała po mojej stronie, nie w analizie. Pary punktów są dobre
  (u Mondriana każda para to cały poziomy pas kwadracików, u Seurata pień, u Rousseau kiść). To w P2
  każdą kreskę losowo obracałem o ±14° i przesuwałem. Na długich pasach 14° to już ukos przez pół
  obrazu. W P3 kreska leży wzdłuż swojego elementu: obrót najwyżej ±1,2°, długość 95–103%, bez
  przesunięcia, z lekkim łukiem ręki.
- **Ruch**: pięć wariantów na `ruch.jpg`. Do planszy głównej wybrałem **d**: podwójny łuk, drugi
  krótszy obok pierwszego, jeden grot. Najbardziej „mówi ruch”, a nie zwykła strzałka, i pozostaje
  czytelny w 1/3. **b** (jeden zamaszysty łuk, nacisk w środku) jest najczystszy, ale wygląda jak
  zwykła strzałka. **e** (łuk zawija się w grot jednym ruchem) jest żywy, za to grot wychodzi
  cięższy. **c** (smugi za startem) jest komiksowy i przy krótkim łuku smugi wiszą osobno.
  Łuk ruchu jest teraz wyraźniej wygięty niż w analizie, co najmniej o 10% cięciwy.

## Liczby

| | kreski / oczekiwane | na miejscu | zgodność (mediana) | napisy |
|---|---|---|---|---|
| G Gemini (odniesienie) | 48/48 | 45/48 | (własny podkład) | nie |
| P2 | 48/48 | 48/48 | 0,94 | nie |
| P3 | 48/48 | 48/48 | 0,93 | nie |

Pliki: `kreda-3.jpg` (dzieło | G | P2 | P3), `kreda-3-zblizenia.jpg` (echo parasoli i pomarańczy,
rytm Mondriana i pni, groty, ruch) oraz `ruch.jpg` (warianty a–e, wycinki 1:1 i w 1/3).
