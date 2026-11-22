# Kreda 2: kreski lokalnie, poprawione (2026-11-22)

Te same 10 dzieł i ten sam podkład r7+C16 co w kreda-1. Kreski rysuje Python, bez Gemini i fal:
0 USD, ok. 0,5 s na arkusz. Skrypty: `~/Frame-worktrees/lokalny-model/kreda2/`.

## Co zmienione w P2

- **Pętla i kółka echa** to swobodny owal szybkiego zakreślenia. Nie ma już GrabCut ani obrysu kształtu.
  Owal obejmuje całe pudełko z analizy z ok. 12% zapasu. Promień jest lekko nierówny, owal przechylony
  o ±12°. Ręka robi jeden obieg i trochę (1,08–1,22), końce zachodzą na siebie i się rozchodzą, a nacisk
  słabnie pod koniec. Czasem dochodzi drugi, lżejszy obieg tuż obok.
- **Echo** to same kółka, bez żadnych łączników.
- **Groty**: cztery warianty na `groty.jpg`. Wybrałem **B**: jeden ruch ręki zadzior–czubek–zadzior.
  Zadziory mają różną długość (3–4,5% dłuższego boku) i kąt 24–35°, są lekko wygięte i mają to samo
  ziarno co kreska. Koniec linii pod grotem nie blednie już przed czubkiem. A (dwie osobne kreski)
  wygląda podobnie, ale częściej zlewa się w plamę. C (zadziory wciągnięte za czubek) jest żywy, ale
  przy krótkich strzałkach wygląda jak krzyżyk. D (linia przechodzi w zadzior) daje najmniej czytelny
  grot.
- **Linie i boki** trójkątów i pudełek są lekko wygięte jak ruch ręki. Rytm jest nierówny: każda kreska
  ma własną długość, pochylenie i nacisk.

## Liczby

| | kreski / oczekiwane | na miejscu | zgodność (mediana) | napisy |
|---|---|---|---|---|
| G Gemini (odniesienie) | 48/48 | 45/48 | (własny podkład) | nie |
| P z kreda-1 | 48/48 | 48/48 | 0,94 | nie |
| P2 | 48/48 | 48/48 | 0,94 | nie |

Produkcyjny `drawn.split` nadal wyciąga z P2 wszystkie warstwy, więc numery na kreskach działają bez zmian.

## Co jeszcze odstaje

- Rytm u Mondriana: w analizie każda para punktów to cały pas kwadracików, więc P2 rysuje długie pochyłe
  kreski. Gemini rysuje tam krótkie „ptaszki” na kolejnych kwadracikach. Jeśli rytm ma zawsze wyglądać
  jak seria krótkich kresek, trzeba długą parę dzielić na kilka.
- Grot ruchu przy „Biegnącym chłopcu” (Jefferson Park) jest mały przy krótkim, wygiętym łuku. Grot
  można liczyć od długości całego ruchu, a nie od końcówki.
- Boki trójkątów nadal idą od punktu do punktu, a nie po krawędziach podkładu.

Pliki: `kreda-2.jpg` (dzieło | G | P z kreda-1 | P2), `kreda-2-zblizenia.jpg` (wycinki 1:1, te same co
w kreda-1 oraz strzałki, rytm i echo), `groty.jpg` (warianty A–D, powiększone 1,5×).
