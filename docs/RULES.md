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
  więc należała do etapu 4 (4c, 1.145.23: `library/good.py`). Samo pole
  `Item.suitability` i jego liczenie usunęło 1.145.28 (PLAN 3.3zzz174).

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
| 2 | Szybkość bez zmiany wyników: przyrostowe scalanie grup (2a: 1.145.13, PLAN 3.3zzz157); duże obrazy powtórek zostają jako oryginały (2b: 1.145.17, PLAN 3.3zzz161); dalej według pomiarów z nocy | w toku |
| 3 | Sprzątanie resztek: wskaźnik „Na e-papierze”, martwy próg, nieużywane punkty API | 1.145.14 (PLAN 3.3zzz158) |
| 4 | Jeden werdykt pokazywania: lista powodów i tabela „miejsce × powód” (4a, bez zmiany wyników: 1.145.15, PLAN 3.3zzz159); serwer nie proponuje zachowanych detali, kopii i znaczków (4b: 1.145.19, PLAN 3.3zzz163); kolejność „najpierw dobre” w Odkrywaj (4c: 1.145.23, PLAN 3.3zzz168) | 1.145.23 |
| 5 | Jedna tożsamość dzieła i autora, opis rodzaju: przedmioty i książki do „Sztuk innych” (5a: 1.145.26, PLAN 3.3zzz171); „ten sam autor” jedną regułą (5b: 1.145.33, PLAN 3.3zzz179); to samo dzieło i najlepsza kopia według obrazu (5c: 1.145.30, PLAN 3.3zzz176) | w toku |
| 6 | Jedna nocna pętla modeli (6a: 1.145.36, PLAN 3.3zzz182); jedna ścieżka pytań do muzeów | w toku |

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
| `PROPOSED` | to, co serwer proponuje sam: Studium dnia, karty i strony Odkrywaj z katalogu, Propozycje dnia, inne dzieła autora (od 1.145.19; wcześniej `STUDIED`, tylko pula Studium dnia, a zachowane: „Sztuki inne” i czarno-białe kopie) | wszystkie powody | wszystkie powody |
| `MUSEUM` | odpowiedź muzeum przy czytaniu | kopie | kopie |
| `SOUGHT` | Szukaj w muzeach, karty Odkrywaj z muzeów, dobieranie | wszystkie powody | wszystkie powody |
| `TIDIED` | Strażnik, Nocny przegląd | wszystkie powody | wszystkie powody |
| `COMPARED` | powtórki, Sędzia, ostrzejsze kopie | kopie | kopie |

Powód z grupy „Sztuki inne” nie liczy się, gdy pytanie prosi o tę
kategorię (`asked`). Zmiana tego, co widać, to odtąd zmiana komórki tej
tabeli. Zestaw wzorcowy dostał sekcję `kept` (dzieła zachowane przez
właściciela, które mają powód, i czy mogą dziś zostać Studium dnia), z
której powstaje lista do takiej decyzji.

Etap 4b w skrócie (decyzja Mateusza „serwer sam nie proponuje zachowanych
detali, reprodukcji i znaczków”): wiersz `STUDIED` stał się `PROPOSED` i
obejmuje wszystko, co serwer proponuje sam. Kto proponuje, pyta katalog
z `proposing=True` (`Library.query`); reguła, która prosi o własne dzieła
właściciela (Ulubione, „Moje”), wyłącza to sama, więc jego listy, playlisty
i Szukaj zostają przy `LISTED` i `FOUND`. Lista z jego serwera miała 48
dzieł, z czego żadne nie leżało na playliście, a dwa miały serce:
„zachowane” znaczy dziś tylko „nie dobrane przez serwer” (`not pooled`),
co obejmuje importy z pierwszych dni. To do uporządkowania w etapie 5.

Etap 2b w skrócie: pomiar pakietu „Powtórki i jakość” z 2026-11-11 pokazał,
że powtórki to w 80% pobieranie dużych obrazów z muzeów (1403 z 1758 s),
a zadania z modelami to czekanie na paczki (7 do 9 minut każda). Duży obraz
pobrany do porównania zostaje więc jako oryginał dzieła
(`ImageCache.looked_at`), pierwszy do usunięcia przy braku miejsca.

Rozmiar obrazu (znalezisko z całego katalogu, 2026-11-11, PLAN 3.3zzz166):
`Item.width` i `height` to rozmiar oryginału tylko dla źródeł z
`images.SAY_SIZE`; dla pozostałych (Met, Rijksmuseum, MNW, MNK, Luwr, Getty,
Paris Musées, V&A, Europeana, Wellcome, Cleveland) to rozmiar miniatury,
czyli proporcje obrazu i nic więcej. Reguła, która ocenia jakość kopii,
pyta `images.said_side(item)` (None: nie wiadomo), nigdy `item.width`.
Studium dnia przez to nie wybierało z ponad połowy katalogu. Do etapu 5
zostaje ten sam błąd w powtórkach (`twins._surely_whole`) i czytnik
Cleveland.

Etap 4c w skrócie (cel Mateusza: „Dzieła w Odkrywaj mają być po prostu
dobre”; lista różnic pokazana, jego wybór „Wprowadź”): tam, gdzie serwer
proponuje (karty i strony tematów Odkrywaj, Propozycje dnia), o kolejności
decyduje `library/good.py`, nie alfabet autorów i nie ocena e-papieru.
`worth(item)` liczy to, co katalog wie o dziele: arcydzieło muzeum, znany
autor, opis, jakość kopii (tylko tam, gdzie muzeum podaje rozmiar), minus
szkic w tytule i slajd archiwum. `good_first` dodaje losowanie dnia (inne
w każdym temacie) i odsuwa każdą kolejną pracę tej samej osoby i, mniej,
tego samego muzeum. To, jak dzieło pasuje do pytania (autor, miejsce
słowa, tag), dalej idzie przed oceną. Pyta się `Library.query(sort="good",
seed=dzień)`. Szukaj zostaje przy trafności, Studium dnia przy własnej
puli i własnej ocenie. Zmiana wagi w `good.py` to zmiana tego, co widać:
najpierw lista różnic z katalogu (`golden.library_of`).

| Pierwsza strona tematu (71 tematów, 24 dzieła) | Przed | Po |
|---|---|---|
| autorów | 7,9 | 14,5 |
| dzieł bez autora | 6,8 | 2,5 |
| muzeów | 4,3 | 5,6 |
| arcydzieł muzeów | 12,4 | 11,8 |
| najwięcej prac jednej osoby | 13,4 | 5,9 |

Do etapu 5 zostaje z tej listy: „Rembrandt Peale” w malarstwie
holenderskim, dzieła bez tytułu, Straż nocna z dwóch muzeów obok siebie,
statuetki i miecze Met nierozpoznane jako rzeźba i rzemiosło.

Trzy pomyłki opisu z listy etapu 4b (1.145.24, PLAN 3.3zzz169): odwrocie
jest dokumentem tylko dla obrazu, nie dla rysunku ani arkusza nazwanego
obiema stronami (`vocabulary._VERSO`, `_RECTO`, `_SHEET`); dzieło o
malarskiej technice na malarskim podłożu nie jest fotografią, choć muzeum
tak nazwało jego rodzaj (`_PAINTED_ON`). Sprawdzone na całym katalogu:
werdykt zmienia się dla trzech dzieł.

Etap 5a w skrócie (lista różnic pokazana, wybór Mateusza „Przenieś
wszystko”): `vocabulary.object_category` zna teraz rodzaje, którymi muzea
nazywają przedmioty („Metal-Ornaments”, „Aerophone-…”, „Swords”, „Bronzes”,
„Books”). Rodzaj, który nazywa technikę obrazu, dalej rozstrzyga pierwszy
(„Furniture, Drawings” to rysunek). Na katalogu 868 dzieł zmieniło
kategorię (404 rzemiosło, 70 rzeźba, 394 książki do rękopisów), 11 okazów
przyrodniczych stało się dokumentem, 475 dzieł dostało technikę. Udział
kategorii „Sztuk innych” to próg dobierania; przycinanie rusza dopiero
powyżej półtora udziału (`player.OTHER_ART_OVER`), żeby zmiana opisu nie
usuwała dzieł. Nowy rodzaj z muzeum, którego reguły nie znają, zostaje
obrazem: listę takich rodzajów daje katalog (`golden.works`) i
`object_category`.

Pomiary do 5b i 5c (katalog z 2026-11-11): `vocabulary.artist_matches`
(podzbiór słów) i `artists.made_by` (osoby) różnią się na 81 parach nazw
w jedną stronę („Style of…”, „Według…”) i na 1820 w drugą („Edgar Degas”
i „Hilaire Germain Edgar Degas”); `made_by` uznaje „…, After” i „formerly
attributed to” za autora. Grup z więcej niż jedną kopią jest 28 (68
pozycji), bo dobrane kopie z mniej pewnych źródeł serwer usuwa; w 10
najlepsza kopia zmieniłaby się przy kolejności „najpierw obraz”, 4 serca
leżą na kopii, która nie jest najlepsza.

Etap 5c w skrócie (lista różnic pokazana, wybór Mateusza „Wprowadź”):
pierwszą kopię dzieła wybiera `duplicates.preference`: najpierw nie zdjęcie
archiwum sztuki, potem obraz (`duplicates.picture`: wystarcza na ramkę,
zwykły, słaby), potem ranga źródła, a „zachowane” już tylko przy remisie.
Obraz i rysunek albo grafika o tym samym tytule to dwa dzieła
(`duplicates.another_technique`). Serce przechodzi nocą na ściśle lepszą
kopię (`Library.hearts_to_best`), poza kopiami z własnym kadrem. Na
katalogu: pierwsza kopia zmienia się w 3 grupach z 28, jedna grupa się
rozdziela, żadne z 132 serc się nie przenosi.

Etap 5b w skrócie (lista różnic pokazana, wybór Mateusza „Wprowadź”):
o to, czy dwa dzieła są jednego autora, pyta się `artists.same_hand(a, b)`,
a o to, czy dzieło jest szukanego autora, `artists.made_by(artist, wanted)`.
Najpierw rozstrzygają dane o autorach (ta sama osoba albo inna osoba według
Wikidaty), potem zapis: nazwa cofnięta przez muzeum, następca, samo imię
i inicjały nie są autorem. `vocabulary.artist_matches` (podzbiór słów) jest
już tylko wstępnym sitem i nigdzie nie rozstrzyga.

Etap 6a w skrócie: nocna pętla „zamów w Batch API, poczekaj, wstaw
odpowiedzi” jest w `ai/night_order.py` (`NightOrder`, `CheckedNight`);
Sędzia kopii, Strażnik, Nocny przegląd i Kurator ją dziedziczą. Notatki
zamawiane nocą (`AiJobs.order_night`) odbiera pętla tła i zostają osobno.

## Jak sprawdzić zmianę reguł

### 1. Co mówi każde miejsce o każdym rodzaju dzieła

`server/tests/test_rules_matrix.py` trzyma po jednym dziele każdego rodzaju,
który reguły rozróżniają (obraz, detal, reprodukcja, szara kopia, znaczek,
fotografia, rękopis i tak dalej), raz jako dobrane przez serwer i raz jako
zachowane przez właściciela, i pyta o nie dziesięć miejsc: katalog, katalog
szukany słowem, pulę Studium dnia, kartę Odkrywaj z katalogu, odczyt
odpowiedzi muzeum, Szukaj w
muzeach, kartę Odkrywaj z muzeów, Strażnika, Nocny przegląd i powtórki.
Tabela `EXPECTED` to dzisiejsze zachowanie. Zmiana reguły, która przesuwa
choć jeden znak, wychodzi w teście z nazwą rodzaju i miejsca.

Pierwsze cztery kolumny to zbiór, z którego wybierają Studium dnia, karty
Odkrywaj i kurator. „-” w nich zamienia się w „+” tylko za zgodą Mateusza.

Z dwóch znanych niespójności (ustalenie K1 audytu) pierwszą, zachowane
kopie w puli Studium dnia, zamknął etap 4b. Druga jest zapisana wprost, do
decyzji w etapie 4c:

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

Zmianę tego, co widać, próbuje się na całym katalogu poza serwerem (od
1.145.19): `GET /api/debug/catalogue` oddaje każde dzieło sztuki tak, jak ma
je biblioteka (gzip, dzieło w wierszu, same opisy), a `golden.library_of`
robi z pliku bibliotekę, którą pyta się tak jak serwerową. Lista różnic dla
Mateusza to wtedy dwa pytania do tej samej biblioteki: po staremu i po
nowemu.

```bash
curl -s -H "Authorization: Bearer $(cat ~/.config/frame/nas-token)" \
  http://<adres serwera>:8099/api/debug/catalogue > catalogue.jsonl.gz
```

Kto jest kim wśród autorów, serwer wie także od Wikidaty; do prób z
autorami (etap 5b) pobiera się ten stan tak samo z `/api/debug/artists` i
podaje jako trzeci argument `golden.library_of`.

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
