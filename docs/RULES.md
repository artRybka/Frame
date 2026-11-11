# Reguły doboru i deduplikacji dzieł: audyt i plan porządków

Audyt z 2026-11-11 (prośba Mateusza: „kompletny audyt i przygotowanie planu
zmian, celem jest jakość i szybkość działania”). Pełny dokument z mapą reguł
jest w bibliotece projektu („Audyt reguł doboru i deduplikacji dzieł”). Tutaj
to, czego potrzebuje kolejna osoba przy kodzie: co ustalono, w jakiej
kolejności to porządkujemy i jak sprawdzić, że zmiana niczego nie zepsuła.

Mateusz 2026-11-11 14:16: wdrażamy cały plan, etapy 0 do 6. Zastrzeżenie
z 14:17 i 14:19: wspólne reguły nie mogą obniżyć jakości doboru Studium dnia
ani dziennych propozycji kuratora („droga doboru może być inna, ale nie
chciałbym żeby spadła jakość doboru tych propozycji”).

## Ustalenia

- **„Czy to dzieło pokazać”** rozstrzyga dwanaście reguł z
  `library/vocabulary.py` (`is_copy`, `set_aside`, `other_art` i inne),
  składanych na nowo w ok. 60 miejscach w 15 plikach, w różnych zestawach.
- **„Czy to to samo dzieło”** ma dziewięć odpowiedzi: opis (`same_work`,
  rok ±2), numer inwentarza (tylko Rijksmuseum), skrót obrazu, punkty ORB,
  `twins._fit` z własną klasą `Fit` (rok ±10), Sędzia, identyfikator Wikidata
  (tylko „Pod lupą”), `isSameWork` w aplikacji, doraźne porównania tytułów.
- **„Ten sam autor”** ma sześć odpowiedzi, **„Twoje dzieło”** osiem.
- **Muzea są pytane czterema ścieżkami**: `MuseumSearch.pages` (Szukaj,
  własne playlisty), `themes.search_page` (karty, tylko AIC, Cleveland, Met),
  `Importer.fill` (playlisty z kart), `Importer.collect` i `_take`
  (dobieranie katalogu).
- **Nocna pętla modeli** istnieje w czterech kopiach (`CriticNight`,
  `NightJudge`, `Curator`, studium).
- **Resztki**: ocena e-papieru (suitability) w 12 plikach i wskaźnik
  „Na e-papierze” w aplikacji, jednorazowe migracje, punkty `/api/browse`
  i `/api/library/draw`, których aplikacja nie woła. Wskaźnik, próg
  i oba punkty usunął etap 3. Sama ocena została jako kolejność „najlepsze
  najpierw” (karty i strony Odkrywaj, pula Propozycji dnia, wiersz dla
  modelu wybierającego Studium dnia): jej wymiana zmienia to, co widać,
  więc należy do etapu 4.

## Liczby bazowe (NAS, 1.143.2, logi z 10 i 11 listopada 2026, ok. 91 tys. dzieł)

| Pomiar | Wartość |
|---|---|
| Noc 11.11, cały budżet | 4 h 30 min |
| dobieranie katalogu | 1 h 43 min (6 partii po ok. 318 dzieł) |
| spis Rijksmuseum | 2 h 30 min (od 1.144.0 na końcu nocy) |
| powtórki i detale | 5 min 11 s, potem koniec nocy |
| Strażnik, Nocny przegląd | nie ruszyły ani razu do rana 11.11 |
| Powtórki na żądanie | 32 min 45 s dla 38 538 obrazów 835 autorów (41 kopii, 14 detali) |
| Przebudowa grup kopii | 30 razy w 3 h 47 min, 3,3 do 6,4 s każda, razem 126 s |
| Powolne odpowiedzi | `/api/suggestions` 3,2 i 4,8 s, `/api/themes` 2,2 i 2,7 s |
| Sędzia powtórek 10.11 | 74 pary, 68 rozdzielonych, 2 zapisane |

## Plan

| Etap | Co | Stan |
|---|---|---|
| 0 | Zestaw wzorcowy i pomiary | 1.145.11 (PLAN 3.3zzz155) |
| 1 | Noc: porządki przed dobieraniem, budżety czasu | 1.145.12 (PLAN 3.3zzz156) |
| 2 | Szybkość bez zmiany wyników: przyrostowe scalanie grup (2a: 1.145.13, PLAN 3.3zzz157); duże obrazy powtórek zostają jako oryginały (2b: 1.145.16, PLAN 3.3zzz160); dalej według pomiarów z nocy | w toku |
| 3 | Sprzątanie resztek: wskaźnik „Na e-papierze”, martwy próg, nieużywane punkty API | 1.145.14 (PLAN 3.3zzz158) |
| 4 | Jeden werdykt pokazywania: lista powodów i tabela „miejsce × powód” (4a, bez zmiany wyników: 1.145.15, PLAN 3.3zzz159), potem zmiany widoczne z listą różnic | w toku |
| 5 | Jedna tożsamość dzieła i autora | |
| 6 | Jedna ścieżka pytań do muzeów i jedna nocna pętla modeli | |

Etapy 0 do 3 nie zmieniają tego, co widać. Przed każdą zmianą widocznych
wyników w etapach 4 do 6 Mateusz dostaje listę różnic do decyzji.

Etap 1 w skrócie: pakiet „Powtórki i jakość” (powtórki, Strażnik, Sędzia,
Nocny przegląd) idzie przed dobieraniem katalogu, dobieranie dostaje
najwyżej 45 minut (`night.CATALOGUE_FOR`), zamówienia do Claude wychodzą
przed pierwszym zadaniem pakietu (`NightTask.ahead`), a zadania, do których
noc nie doszła, następnej idą pierwsze (`NightQueue.in_turn`).

Etap 2a w skrócie: zmiana jednego dzieła (nazwana kopia, tytuł, autor,
rok, usunięcie) grupuje od nowa tylko dzieła osiągalne od niego przez
`same_work` (`Works.regroup`), z tym samym wynikiem co grupowanie całego
katalogu; całość od nowa tylko wtedy, gdy takich dzieł jest za dużo
(`REGROUP_LOOKS`) albo zapis został wycofany.

Etap 4a w skrócie: `library/verdict.py` zna każdy powód, dla którego coś
nie jest obrazem na ramkę, pod jedną nazwą (`Why`), i pyta o nie reguły ze
`vocabulary` raz, w jednej kolejności (`whys(item)`). Tabela `MINDS` mówi,
które powody obchodzą które miejsce (`Place`), osobno dla dzieł dobranych
przez serwer i dla zachowanych przez właściciela; `against(item, place,
asked)` oddaje powody, które dane miejsce ma przeciw dziełu (żadnego: dzieło
jest tam pokazywane albo brane). Miejsca w kodzie nie składają już reguł
same, tylko nazywają miejsce:

| Miejsce (`Place`) | Kto pyta | Dobrane przez serwer | Zachowane przez właściciela |
|---|---|---|---|
| `LISTED` | katalog przeglądany (Ulubione, playlisty, wszystko), słowa kluczowe, polskie teksty | wszystkie powody | nic |
| `FOUND` | katalog pytany słowem, autorem albo filtrem | wszystkie powody | „Sztuki inne”, znaczek, dokument, szare zdjęcie z archiwum sztuki |
| `STUDIED` | pula Studium dnia | wszystkie powody | „Sztuki inne”, czarno-białe kopie |
| `MUSEUM` | odpowiedź muzeum przy czytaniu | kopie | kopie |
| `SOUGHT` | Szukaj w muzeach, karty Odkrywaj z muzeów, dobieranie | wszystkie powody | wszystkie powody |
| `TIDIED` | Strażnik, Nocny przegląd | wszystkie powody | wszystkie powody |
| `COMPARED` | powtórki, Sędzia, ostrzejsze kopie | kopie | kopie |

Powód z grupy „Sztuki inne” nie liczy się, gdy pytanie prosi o tę
kategorię (`asked`). Zmiana tego, co widać, to odtąd zmiana komórki tej
tabeli: decyzja Mateusza „serwer sam nie proponuje zachowanych detali,
reprodukcji i znaczków” zmieni wiersz `STUDIED` i doda miejsce dla kart
Odkrywaj z katalogu. Zestaw wzorcowy dostał sekcję `kept` (dzieła zachowane
przez właściciela, które mają powód, i czy mogą dziś zostać Studium dnia),
z której powstaje lista do tej decyzji.

Etap 2b w skrócie: pomiar pakietu „Powtórki i jakość” z 2026-11-11 pokazał,
że powtórki to w 80% pobieranie dużych obrazów z muzeów (1403 z 1758 s),
a zadania z modelami to czekanie na paczki (7 do 9 minut każda). Duży obraz
pobrany do porównania zostaje więc jako oryginał dzieła
(`ImageCache.looked_at`), pierwszy do usunięcia przy braku miejsca.

## Jak sprawdzić zmianę reguł

### 1. Co mówi każde miejsce o każdym rodzaju dzieła

`server/tests/test_rules_matrix.py` trzyma po jednym dziele każdego rodzaju,
który reguły rozróżniają (obraz, detal, reprodukcja, szara kopia, znaczek,
fotografia, rękopis i tak dalej), raz jako dobrane przez serwer i raz jako
zachowane przez właściciela, i pyta o nie dziewięć miejsc: katalog, katalog
szukany słowem, pulę Studium dnia, odczyt odpowiedzi muzeum, Szukaj w
muzeach, kartę Odkrywaj z muzeów, Strażnika, Nocny przegląd i powtórki.
Tabela `EXPECTED` to dzisiejsze zachowanie. Zmiana reguły, która przesuwa
choć jeden znak, wychodzi w teście z nazwą rodzaju i miejsca.

Pierwsze trzy kolumny to zbiór, z którego wybierają Studium dnia i karty
kuratora. „-” w nich zamienia się w „+” tylko za zgodą Mateusza.

Dwie znane niespójności (ustalenie K1 audytu) są zapisane wprost, do decyzji
w etapie 4:

- `KEPT_COPIES_STUDIED`: detal, reprodukcja, znaczek, dokument, zdjęcie sali,
  zdjęcie archiwum i kopia z Openverse, które właściciel zachował, mogą
  zostać Studium dnia, choć zachowana szara kopia już nie.
- `BROWSED_NOT_FOUND`: zachowane dzieła, które katalog pokazuje przy
  przeglądaniu, a pomija po wpisaniu słowa.

### 2. Zestaw wzorcowy z prawdziwego katalogu

`GET /api/debug/decisions` (tylko właściciel) oddaje to, co do tej pory
rozstrzygnięto o dziełach: pary uznane za jedno dzieło i przez co (opis,
skrót obrazu, obrazy, Sędzia), detale i zdjęcia sal, pary rozdzielone przez
właściciela („To nie to samo”) i przez Sędziego, dzieła odłożone przez
Strażnika. Od 1.145.15 także dzieła zachowane przez właściciela, które
mają powód „to nie obraz na ramkę” (`kept`). Same opisy, bez obrazów i bez zdjęć właściciela. Plik zostaje
poza repozytorium (obok logów nocy na Macu).

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/frame/nas-token)" \
  http://<adres serwera>:8099/api/debug/decisions > decisions.json
cd server && uv run python -m frame_server.golden ../decisions.json
```

Polecenie wypisuje, jak dzisiejsza reguła „to samo dzieło” (`same_work`)
radzi sobie na tych decyzjach: ile par trzyma razem, ile gubi, ile par
rozdzielonych błędnie łączy. `golden.measure(data, reguła)` liczy to samo dla
dowolnej nowej reguły, więc etap 5 ma liczbę przed i po.

### 3. Czas

- Powtórki piszą po każdej rundzie, gdzie poszedł czas:
  `twins: time: keypoints 310.2 s (5210), pairs 88.0 s (41200), …`
  (kroki: candidates, hashes, hash distances, keypoints, pairs, thumbnails,
  large pictures, large keypoints, large pairs, writes, grouping; w nawiasie
  liczba obrazów, par albo pobrań).
- Każde zadanie nocy dopisuje, ile razy przez nie przebudowano grupy kopii
  w całości (na to czekały pytania aplikacji) i ile zmian ułożono tylko
  w części (od 1.145.13, nikt nie czeka):
  `night: twins in 310.9 s, the works regrouped 1 time(s) in 3.4 s, 41 change(s) regrouped in part in 0.1 s`.
