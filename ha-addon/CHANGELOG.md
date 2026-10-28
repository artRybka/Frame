# Changelog

## 0.25.1

- Aplikacja Frame na ramce dostaje obraz passthrough jako JPEG q95 4:4:4
  (`/panel/app-images/`, ok. 1 MB zamiast 3–4 MB PNG); obraz z ditheringiem
  zostaje w PNG. Aplikacja pobiera cały plik (XHR, jako data URL, bo `blob:`
  nie działa z `file://`) i podmienia obraz dopiero po pobraniu; pasek
  postępu w aplikacji iOS śledzi pobieranie.
- Ramka zasypia najwcześniej 60 s po ostatnim odświeżeniu ekranu (uśpienie
  w trakcie odświeżania zostawiało szary ekran i gubiło budzik). Po budziku
  serwer uruchamia milczącą aplikację po 60 s (było 90 s) i zapisuje w logu,
  gdy ramka ma inną wersję aplikacji niż serwer.
- Po starcie lub obudzeniu aplikacja włącza z powrotem czuwanie sieci,
  jeśli ostatni sen je wyłączył, żeby Wake-on-LAN znów docierał.
- Nie trzeba nowej paczki: logika aplikacji ładuje się z serwera.
- Dokumentacja E16: wieczorne zasady dla aplikacji ramki.

## 0.25.0

- Aplikacja Frame na ramce pokazuje obraz 1:1: paczka ma
  `base_screen_resolution` = `always`, więc strona ma 2560×1440,
  a `/panel/next` podaje ten sam obraz z `/panel/images/` co tryb Mobile
  (domyślnie passthrough, ramka dituje sama). Osobna kopia 1920×1080
  (`/panel/app-images/`) znika.
- Wymaga nowej paczki z Maca (`scripts/panel-app/pack.sh 1.1.0 --upload
  <token>`) i zimnego startu ramki; stara paczka do tego czasu zmniejsza
  obraz do swojej strony 1920×1080.
- Dokumentacja E16: wieczorne wyniki z `base_screen_resolution`.

## 0.24.1

- Aplikacja Frame na ramce pokazuje obraz bez rozjechanego ditheringu:
  serwer podaje jej pełnokolorowy JPEG 1920×1080 (`/panel/app-images/`),
  a ramka sama powiększa go do 2560×1440 i dituje, jak w trybie
  passthrough. Drobne linie 1 px są trochę miękkie, 2–4 px czyste.
- Po wczytaniu obrazu aplikacja szturcha styl strony, żeby e-papier się
  odświeżył. Logika aplikacji ładuje się z serwera, więc paczki na ramce
  nie trzeba podpisywać od nowa.
- Dokumentacja E16: wyniki z ramki (odtwarzacz 1:1 nie łączy się
  z aplikacją, `0xC7 81` `02` = Mobile, `00` = czarny ekran).

## 0.24.0

- Tryb „Oszczędny” działa przez aplikację Frame na ramce (aplikacja
  Custom podpisana certyfikatem Samsung): ramka sama budzi się o swoim
  czasie, pobiera następny obraz z serwera (`/panel/next`), melduje się
  (`/panel/report`) i znów zasypia. Wybór trybu w Harmonogramie pojawia
  się, gdy ramka działa w tej aplikacji.
- Konfiguracja → Aplikacja ramki: stan aplikacji na ramce i „Przełącz na
  aplikację Frame” (albo powrót do zwykłego trybu). Paczkę aplikacji
  podpisuje i wgrywa na serwer `scripts/panel-app/pack.sh` z Maca.
- Aplikacja czyta baterię i ładowarkę z systemu ramki (zapasowo serwer przez
  MDC), więc ramka na ładowarce nie zasypia. Ramka śpi co najmniej 5 min,
  a gdy po pobudce nie poprosi o obraz w 90 s, serwer uruchamia aplikację
  przez MDC.
- Uwaga: strona aplikacji ma 1920×1080, więc obraz jest powiększany ×4/3,
  a nie 1:1. Do codziennego użytku lepiej zostać przy zwykłym trybie, dopóki
  to nie jest rozwiązane.
- Gdy Wake-on-LAN nie obudzi ramki, aplikacja podpowiada naciśnięcie
  przycisku na ramce (na baterii budzenie przez sieć bywa zawodne).

## 0.23.0

- Otwarta karta dzieła lub zdjęcia prosi model o słowa kluczowe i polskie
  teksty od razu, poza kolejnością w tle; karta pokazuje „Na obrazie”
  albo „Na zdjęciu”, gdy model już popatrzył. Miesięczny limit modelu
  do wyboru aż do 200 USD.
- Budzenie ramki na baterii: serwer wysyła Wake-on-LAN do 3 minut i
  przestaje, gdy ramka odpowie (na baterii budzi się po 1–2,5 min).
- Ramka (firmware 1130.7) odrzuca budzik 0x25, więc serwer nie wyłącza jej
  Wi-Fi w nocy: cisza nocna to lekki sen, zdjęcia wysłane w nocy trafiają
  na ramkę od razu, a stan nie pokazuje już fałszywego „Głęboki sen”.
- Tryb „Oszczędny” jest gotowy, ale ukryty, dopóki ramka nie umie obudzić
  się sama.

## 0.22.0

- Model językowy (Claude): nowa sekcja w Konfiguracji (Ramka → trybik)
  z kluczem API Anthropic (serwer go sprawdza i pokazuje tylko końcówkę),
  przełącznikami polskich opisów oraz słów kluczowych dzieł i zdjęć,
  miesięcznym limitem (domyślnie 5 USD) z bieżącymi wydatkami, postępem
  i „Opisz całą bibliotekę” z szacowanym kosztem przed startem. Klucz
  można też podać w opcji dodatku `anthropic_api_key`.
- Słowa kluczowe z modelu (Haiku) dla dzieł i zdjęć: co przedstawia
  obraz, po polsku i angielsku, pora roku i dnia, nastrój. Znajdują je
  Szukaj, inteligentne playlisty i wyszukiwanie w bibliotece.
- Tryb Opis i podpis na ramce po polsku: tłumaczenie opisu z muzeum
  (Haiku), a dla dzieł bez opisu notka z obrazu (Sonnet). Ramka czeka na
  tekst najwyżej 25 s, a dla następnego obrazu prosi z wyprzedzeniem.
- Karta dzieła po polsku: tytuł, notka o autorze, data, technika i tekst
  z oznaczeniem „Tłumaczenie maszynowe” albo notki modelu oraz „Pokaż
  oryginał”. Narodowość autora jako osoba („Holender, 1853–1890”), polskie
  tytuły z Wikidata, gdy istnieją.

## 0.21.0

- Kolorystyka: barwy dominujące bez powtórek (podobne odcienie łączą się
  w jedną, najwyżej cztery) i akcenty, czyli małe, żywe plamy koloru
  (np. błękit, żółć i czerwień w „Mleczarce”). Akcenty trafiają też do
  tagów kolorów w Szukaj. Analiza uwzględnia profile ICC skanów.
- Karta dzieła pokazuje kolorystykę jako wyższy pasek jak w „Teraz”,
  z udziałami pod szerszymi częściami; pasek w „Teraz” dokłada akcenty
  po barwach dominujących.
- Biblioteka przelicza kolory raz, w tle, po aktualizacji serwera.

## 0.20.0

- Szukaj: każde dzieło raz także w katalogu (z kilku kopii tego samego
  dzieła widać najlepszą) i wśród plików z Wikimedia Commons, gdzie wiele
  obrazów ma kilka skanów; pliki jednej kolekcji porównują się po tytule,
  autorze, roku i proporcjach. Nazwy plików z Commons tracą dopiski typu
  „Jan Vermeer van Delft”, „WGA24652” czy nazwę muzeum.
- Szukaj: przeciągnięcie za koniec wyników naprawdę doczytuje kolejne
  strony z muzeów (wcześniej działało tylko stuknięcie w kwadraciki).
- Playlisty: „Zapisz” od razu zamyka edytor, a wysyłanie zdjęć, zapis,
  synchronizacja albumu i pobieranie z muzeów idą w tle z komunikatami.
- Inteligentna playlista bez żadnej reguły (cały katalog) nie da się
  zapisać: edytor mówi, czego brakuje, serwer odpowiada 422. Karta
  inteligentnej playlisty pokazuje najwyżej 400 dzieł, więc zapisana
  wcześniej taka playlista znowu się otwiera i można ją usunąć.
- Przytrzymanie okładki playlisty: „Prezentuj na ramce” i „Usuń
  playlistę”. „Usuń” w menu karty jest też, zanim karta się wczyta.

## 0.19.0

- Playlisty: ręczna playlista ma to samo wyszukiwanie co inteligentna;
  przy każdym znalezionym dziele jest „+” (po dodaniu ptaszek), dzieła z
  muzeów najpierw trafiają do biblioteki, a dodane widać w pasku
  „W playliście”. W inteligentnej z włączonym pobieraniem z muzeów dzieła
  z muzeów są pierwsze. „Zapisz” bez nazwy przewija do pola nazwy.
- Ulubionych nie da się usunąć ani zmienić w inny rodzaj playlisty
  (serwer odpowiada 409); biblioteka, która ich nie ma, dostaje je z
  powrotem przy starcie. Bez „Zapisane dzieła” (powtarzały Ulubione i
  playlisty).
- „Teraz”: tytuł otwiera kartę dzieła; „Zapisz w Zdjęciach” jest ostatnie
  w menu dzieła.
- Szukaj: każde dzieło raz, także gdy muzea odpowiadają po kolei i na
  dalszych stronach; lepsza kopia zastępuje gorszą (`replaces`).
  Openverse i Europeana liczą się według kolekcji (np. rekord Met i plik z
  Commons tego samego obrazu, Rijksmuseum po numerze inwentarza).
- Szukaj: zamiast „Więcej z muzeów” na dole kwadraciki i „Przeciągnij po
  więcej”; przeciągnięcie za koniec listy (albo stuknięcie) doczytuje
  kolejne strony z muzeów.

## 0.18.0

- Dzieła zapisane jako SVG (np. z Wikimedia Commons przez Openverse) mają
  znowu podgląd: serwer bierze gotowe obrazki PNG/JPEG z Commons, a SVG
  spoza Commons pomija. Pliki TIFF/PDF/DjVu z Commons tak samo.
- Tytuły i autorzy bez resztek HTML (np. „<span class=” w tytułach z
  Commons); zapisane już dzieła są poprawiane raz przy starcie.
- „Zdjęcie na ramkę” zaczyna od pustej ramki w jej proporcjach z napisem
  „Wybierz zdjęcie z rolki” i od razu pokazuje opcje; wybrany wcześniej
  wygląd idzie razem ze zdjęciem.
- Nowa inteligentna playlista jak Szukaj: od razu pole wyszukiwania,
  przełącznik pobierania z muzeów pod nim, kwadraciki do czasu
  wyszukania i podgląd dzieł w kafelkach; bez „Tylko ulubione”.

## 0.17.0

- Szukaj: wyniki zostają po powrocie z dzieła; dzieła z muzeów pojawiają
  się, gdy każde muzeum odpowie (`/api/discover/search/stream`), a przy
  kolorach każde muzeum jest przeglądane głębiej (do sześciu stron, 15 s).
  Dziwna odpowiedź jednego muzeum nie psuje już całego wyszukiwania.
  Kwadraciki na pustym ekranie są o połowę mniejsze, w środku wolnego
  miejsca i z przerwą po każdej rundzie; Kolory są ostatnie w „+”.
- Edytor inteligentnej playlisty działa jak Szukaj: jedno pole z
  etykietkami (muzea, kolory, style, tematy, epoki, techniki pod „+”),
  „Tylko ulubione” i „Pobierz pasujące dzieła z muzeów”; podgląd pokazuje
  też to, co mają muzea.
- „Zdjęcie na ramkę” od nowa: podgląd w proporcjach ramki, „Wypełnij” albo
  „Passe-partout”, kadrowanie od razu na podglądzie, „Pokaż na ramce” obok
  „Dodaj do kolejki”. Zdjęcie wysłane raz nie trafia do list ani
  Propozycji; pokazane lub dodane do kolejki idzie na początek playlisty
  „Historia przesłanych”, a niewysłane znika z serwera.
- Pasek wysyłania bez licznika sekund i bez skoku na końcu; czasy etapów
  są pamiętane po restarcie, a każde wysłanie zapisuje w logu czasy etapów.
- Epoki po 1930 według zasady 70 lat od śmierci autora: międzywojnie,
  1930–1945 i po 1945; style abstrakcja, konstruktywizm, De Stijl, Bauhaus;
  motywy awangarda i „Polskie międzywojnie”.
- Ramka → trybik („Konfiguracja”) → „Biblioteka na serwerze”: rozmiar
  katalogu, oryginałów, obrazów ramki i bazy, wolne miejsce i limit
  rozmiaru. Niższy limit przycina w tle (nigdy ulubionych, playlist,
  kolejki, Propozycji, pokazanych ani własnych zdjęć), wyższy powiększa
  katalog.

## 0.16.1

- Kolejka Ulubionych (i innych playlist) nie kurczy się już do kilku świeżo
  polubionych prac: obejmuje całą playlistę, najpierw prace niepokazywane
  ostatnio, potem resztę. Gdy w międzyczasie dojdą nowe prace (np. z
  muzeów), kolejka losuje się od nowa, żeby poszły pierwsze.

## 0.16.0

- Szukaj: pod „+” na górze są Muzea i Kolory; można wybrać kilka muzeów
  naraz, a każde muzeum i kolor jest etykietką w polu. Kolory działają też
  dla wyników z muzeów i WikiArt (serwer ocenia miniatury). WikiArt bez
  „(test)”, bez filtrów pod polem. Pusty ekran ma zabawę z kwadracików.
- Odkrywaj: „Pokaż na ramce” na stronie motywu; bez wiersza i motywu
  „Najlepiej na e-papierze”.
- Playlisty: bez „Tylko najlepsze na e-papier” (nowa instalacja nie tworzy
  już tej playlisty); muzea wybiera się pod „+”, a playlista i pobieranie w
  tle biorą wtedy tylko z nich.
- Ulubione: po kliknięciu serca lub „Nie pokazuj na ramce” aplikacja od razu
  odświeża playlisty i kolejkę. Gdy ramka gra Ulubione (lub inną
  inteligentną playlistę), nowa praca wchodzi do kolejki zaraz po
  najbliższym obrazie, a usunięta z niej znika.

## 0.15.1

- Nowa ikona aplikacji z napisem „Frame”, z osobnym wariantem dla trybu
  ciemnego. Serwer bez zmian.

## 0.15.0

- Ramka: uśpiona ramka, która nie odpowiada, ale jest w sieci Wi-Fi
  (odpowiada na ARP), pokazuje się jako „Czuwanie”, a nie „Nie odpowiada”.
  Aplikacja sprawdza stan bez budzenia przy wejściu na kartę Ramka (najwyżej
  co 30 s) i przy pociągnięciu w dół. Ostatni odczyt ekranu przeżywa
  restart serwera; `frame device presence` sprawdza obecność z terminala.
- Serwer ramki: drugi, opcjonalny adres „Spoza domu” (np. Tailscale).
  Aplikacja sama wybiera adres, który odpowiada (domowy ma pierwszeństwo),
  i pokazuje, którędy jest połączona.
- Odkrywaj → Propozycje: strona motywu nie zostaje pusta z „Wczytuję…”.
  Motywy polskie (np. Młoda Polska) są przeglądane w kategoriach Commons,
  puste wyniki są pomijane (`next_page`), a przy błędzie można spróbować
  ponownie.
- Bez czarno-białych reprodukcji: plansze z albumów i książek (Polona,
  Biblioteka Narodowa), przezrocza, pocztówki i obrazy bez własnego koloru
  są odrzucane z Commons i Europeany; katalog jest raz jeszcze czyszczony.
- „Teraz”: po zmianie Prezentacji plansze z kolejki od razu pokazują się w
  nowym wyglądzie; podgląd bez ustawień w adresie nie jest zapamiętywany.
- „Teraz”: krótsze podpisy pod ramką (tylko kiedy nastąpi następna zmiana,
  bez „Teraz na ramce” i wskazówki kadrowania); następny w kolejce mówi,
  kiedy ramka się zmieni. Powrót do „Teraz” jest przyciskiem po lewej od
  „Pokaż na ramce”.

## 0.14.0

- Odkrywaj → Propozycje wczytują się szybciej: serwer liczy motywy w tle
  (po starcie i co 10 minut, w międzyczasie oddaje poprzednie), Motyw dnia
  bierze z katalogu, gdy ma co najmniej 8 dzieł, a na muzeum czeka
  najwyżej 3 s; rozpoznawanie fotografii i rękopisów jest zapamiętywane,
  rzędy i okładki idą bez długich opisów. Aplikacja od razu pokazuje
  ostatnie Propozycje, wczytuje je już przy starcie, miniatury pobiera
  tylko dla widocznych kart i trzyma je na dysku; pociągnięcie w dół
  odświeża.
- „Szukaj” bez dymków stylów, kierunków, tematów, epok i technik (zostają
  pod „+”); zostają Muzea, a wybrane muzeum jest żetonem w polu
  wyszukiwania. Autor w „Teraz” też otwiera wyszukiwanie jego prac.
- Ramka: „Połączenie z ekranem” i „Serwer ramki” są w osobnym arkuszu pod
  trybikiem w prawym górnym rogu. Kafelek Zasilanie pokazuje baterię na
  baterii, wtyczkę przy zasilaczu i błyskawicę przy ładowaniu.
- Oryginał dzieła bez ikonki powiększenia; klikalny jest cały obraz.
- „Zapisz w Zdjęciach” znowu działa (Zdjęcia odrzucały pobrany plik bez
  rozszerzenia); przy błędzie komunikat podaje powód.

## 0.13.0

- Passe-partout „z obrazu” nazywa się teraz „Jasne”, a nowe „Ciemne”
  (`picture_dark`) to głęboki, przygaszony karton w odcieniu obrazu z
  białym rdzeniem fazy.
- Ekran kadrowania: „Kadr automatyczny” stoi na stałe obok „Zapisz kadr”
  (wygaszony, gdy nie ma czego przywracać), więc podgląd już się nie
  zmniejsza w trakcie przeciągania. Podglądy ramki nie mają już ikonki
  kadrowania.
- Dotknięcie artysty przy dziele otwiera wyszukiwanie jego prac; zakładka
  „Muzea” w Odkrywaj nazywa się „Szukaj”.
- Menu „…” dzieła → „Zapisz w Zdjęciach”: obraz w największej dostępnej
  rozdzielczości (plik z muzeum, a gdy się nie da, kopia z serwera).
- „Uśpij ramkę” pokazuje faktyczny stan: przez 3 minuty po uśpieniu
  serwer nie otwiera sesji MDC przy sprawdzaniu stanu i zgłasza czuwanie.
  Po wysłaniu obrazu i po „Sprawdź stan” ramka wraca do snu także na
  ładowarce, jeśli wcześniej spała; bateria jest czytana ponownie przed
  decyzją.
- Odświeżanie przeciągnięciem w dół nie pokazuje już dymka „anulowane”.

## 0.12.0

- Tryb „Opis”: pierwszeństwo ma obraz. W okienku passe-partout zajmuje
  tyle miejsca, ile pozwalają marginesy (karton po bokach taki jak u
  góry), a detal i tekst dostają pod nim co najmniej 20% krótszego boku
  (40% w kolumnie obok) zamiast stałej jednej trzeciej.
- Kremowe passe-partout jest wyraźniej kremowe: 30% żółtej farby zamiast
  10%; podgląd w aplikacji pokazuje je jak ekran.
- „Sprawdź stan” budzi ramkę, gdy nie odpowiada (i nie śpi głęboko); na
  baterii po minucie wraca do lekkiego snu
  (`POST /api/device/wake?sleep_after=true`). Serwer podaje
  `power_state` (online, czuwanie, głęboki sen, nie odpowiada), a kafelek
  Sieć i nagłówek zakładki Ramka go pokazują.
- Zakładka Ramka: wizualizacja w proporcjach ekranu (9:16 / 16:9) i
  własna nazwa ramki w aplikacji (pole `name` w ustawieniach, puste wraca
  do nazwy z ekranu).
- Zmiana Prezentacji nie wysyła już obrazu ponownie: nowy wygląd dostaje
  następny obraz na ramce; tylko obrót ekranu przerysowuje obecny.
- Kadrowanie na całym ekranie: dotknięcie podglądu w „Teraz” albo w
  „Na ramce” przy dziele otwiera ramkę tak dużą, jak się mieści, z
  okienkami kadru, kształtem okienka, „Kadr automatyczny” i „Zapisz kadr”;
  nic się tam nie przewija. Oryginał dzieła otwiera się na całym ekranie
  z przybliżaniem palcami i podwójnym stuknięciem.
- „Najlepiej na e-papierze” stawia na kolorowe dzieła: ocena waży
  najbardziej barwność (0,5), potem kontrast, średnią jasność i pokrycie
  gamy; obrazy bez własnego koloru (rysunki, ryciny, zdjęcia cz-b, sepia)
  mają najwyżej 0,5. Biblioteka jest raz oceniana od nowa w tle po
  starcie.
- „Teraz” pokazuje stan faktyczny: serwer zapamiętuje, który obraz ekran
  naprawdę pobrał (`delivery.json`), a `GET /api/player` zwraca
  `delivery`. Obraz, który nie dotarł, ma „Nie dotarł na ramkę” albo
  „Czeka na ramkę” z powodem, kartę „Na ramce nadal” z tym, co ekran
  wyświetla, i przycisk „Wyślij ponownie” (`POST /api/device/push`) albo
  „Obudź ramkę”.

## 0.11.1

- Wake-on-LAN z serwera naprawdę wychodzi: uvicorn działa na uvloop, a
  uvloop nie ma `loop.sock_sendto`, więc każde budzenie kończyło się
  błędem przed pierwszym pakietem. Teraz zwykły `sendto` (porty 9 i 7),
  w logu liczba wysłanych pakietów i nieudane adresy; test pod uvloop.
- „Obudź ramkę” przywraca network standby także wtedy, gdy ekran sam
  zgłasza je jako wyłączone.
- Polecenia CLI dla ekranu używają adresu, PIN-u i MAC-a zapisanych w
  aplikacji.

## 0.11.0

- Tryb „Opis”: sam obraz w oknie też można przesunąć i przybliżyć
  (`Framing.picture`, `LayoutSettings.picture_crop`); widok kadrowania
  pokazuje go przed detalem, a `PUT` przyjmuje [obraz, detal] albo, ze
  starszych aplikacji, sam detal. Nieruszony obraz zostaje automatyczny.
- Automatyczny detal jest co najmniej 1,8× bliżej niż obraz obok, nawet
  ponad limit pikseli źródła.
- Tytuł na kartonie jest mniejszy (3% krótszego boku) i zawija się do
  trzech linii, zanim dostanie wielokropek.
- Tryb „Detale” (dwa detale) usunięty: zapisane ustawienia z nim ładują
  się jako „Opis”, AUTO wybiera „Opis”, a z zapisanej pary detali zostaje
  bliższy jako detal opisu.
- Budzenie ramki: po nocy na baterii serwer szuka ekranu co 2 min, aż
  przywróci network standby (wcześniej przegapiony alarm albo przycisk
  zostawiały go wyłączonym na cały dzień i Wake-on-LAN nie działał).
  „Obudź ramkę” wysyła pakiety przez 15 s, szuka ekranu przez 30 s, a
  aplikacja pokazuje, czy się obudził, nie odpowiada, czy śpi głęboko do
  alarmu (`/api/device/wake` zwraca wynik).
- Na baterii ekran przechodzi w lekki sen 90 s po pobraniu obrazu (z
  network standby, więc WoL nadal działa); nowy obraz w tym czasie to
  anuluje, na ładowarce bez zmian.
- Aplikacja: w „Teraz” przycisk „Wróć do obrazu na ramce” po
  przeglądaniu strzałkami; w szczegółach dzieła „Pokaż na ramce” i „Dodaj
  do kolejki” w jednym rzędzie, serce i menu „⋯” u góry, narzędzia kadru
  z „Zapisz kadr” w jednym rzędzie; poprawiony opis zasilania na
  baterii; „Użytek prywatny” przeniesiony do Ramka → Źródła dzieł.

## 0.10.0

- Jedno dzieło z kilku źródeł pokazuje się raz. Agregatory (Openverse,
  Europeana, Commons) mają te same obrazy co muzea, więc wyszukiwanie,
  Propozycje, katalog i playlisty pokazywały jeden obraz dwa albo trzy
  razy. Serwer łączy kopie po tytule i autorze (z rokiem ±2 i proporcjami
  obrazu ±15% jako sprawdzeniem, ten sam adres strony lub pliku zawsze)
  i zostawia kopię, którą właściciel trzyma, a w innym razie tę z
  najpewniejszego źródła: muzeum, Europeana, Commons, Openverse, WikiArt.
  Zbędne kopie w puli są usuwane przy starcie i przy porządkach (ulubione,
  kadrowane, z playlist i z kolejki zostają). Ręczne playlisty nie biorą
  dzieła dwa razy.
- „Dodaj do kolejki”: dzieło wybrane przez właściciela pokazuje się przy
  następnej zmianie, przed resztą kolejki, i przetrwa zmianę playlisty.
  Nowe `POST /api/library/items/{id}/queue` (dzieła z muzeów trafiają do
  biblioteki), `DELETE /api/player/queue/{id}` i pole `queued` w stanie
  odtwarzacza. `/api/player/next` i `/previous` są teraz asynchroniczne.
- Aplikacja: kadrowanie bezpośrednio na podglądzie „Na ramce” w
  szczegółach dzieła (jak w „Teraz”), „Zapisz kadr”; „Pokaż na ramce”,
  „Dodaj do kolejki” i dodanie do playlisty najpierw zapisują nowy kadr.

## 0.9.1

- Naprawiona wysyłka na ekran na Synology („[Errno 21] Is a directory:
  '/data/images/@eaDir'”): porządkowanie starych obrazów próbowało usunąć
  katalog miniatur, który DSM zakłada w zamontowanych folderach. Serwer
  pomija teraz katalogi oraz wpisy `@eaDir`, `#recycle` i `.DS_Store`
  wszędzie, gdzie listuje lub sprząta pliki w `/data`.

## 0.9.0

- Presety dobrane na oko na prawdziwym ekranie (E14, piętnaście plansz
  porównawczych): wszystkie na `passthrough`, czyli dithering robi ekran,
  a serwer tylko poprawia obraz pod jego mapowanie. Jasne partie
  przesunięte do bieli papieru i odbarwione (ekran sypał w nich
  niebieskie i zielone kropki), szarości odsunięte od zieleni. Nowe pola
  `ToneSettings`: `white_point`, `highlight_chroma`, `tint`,
  `temperature`, `tint_region`.
- Kropkowana linia dookoła okna passe-partout, tam gdzie faza styka się
  z kartonem: czarna, a na ciemnym kartonie na przemian biała i
  niebieska. Bez niej na białym kartonie cięcie znikało.
- Karton, fazy i podpisy przy `passthrough` w czystych farbach (nasz
  dithering tylko na kartonie), ekran ditheruje sam obraz; karton
  nadal rzuca cień na obraz.
- Podgląd w aplikacji pokazuje karton i linię dookoła okna tak jak
  ramka, także w szybkim podglądzie.

## 0.8.0

- Muzea → samo źródło (bez frazy) pokazuje dzieła tego źródła, a nie
  „Nic tu nie ma”: Openverse dzieła w domenie publicznej (z „Użytkiem
  prywatnym” także CC), WikiArt najczęściej oglądane obrazy, Europeana
  dzieła na wolnych licencjach. Wcześniej serwer w ogóle nie pytał
  źródła, więc Openverse i WikiArt, których nie ma w katalogu, były puste.
- WikiArt: kolejne strony wyników działają (token stronicowania był
  kodowany dwa razy i WikiArt odpowiadał błędem).
- Szybsze przygotowanie obrazu dla ekranu, z wynikiem identycznym bit
  w bit: PNG zapisywany bez `optimize` (~5 s mniej), sRGB → światło
  liniowe z tablicy, mapowanie tonów i kolorów liczone pasami na
  wszystkich rdzeniach, szybszy karton. Na 2 rdzeniach obraz
  z passe-partout ok. 10 s → 2 s.
- Następny obraz z kolejki rysowany z wyprzedzeniem, zaraz po zmianie
  (i po restarcie serwera), więc zmiana o czasie tylko publikuje gotowy
  plik.
- Pobieranie obrazów z muzeów ponawiane przy 408/429/5xx i błędach
  sieci (do 3 prób, przerwa wg `Retry-After`), najwyżej kilka pobrań
  naraz z jednego hosta. W aplikacji miniatury w Odkrywaj ponawiane tak
  samo, a ta, która nie przyszła z muzeum, jest brana z serwera
  (`/api/library/items/<id>/thumb`).
- Aplikacja: obrys i wewnętrzny cień na styku ramki i ekranu w
  wizualizacji ramki.

## 0.7.0

- Adres IP, PIN i MAC ekranu ustawiane w aplikacji (Ramka → Połączenie
  z ekranem). Serwer trzyma je w bazie (kv `panel_config`), mają
  pierwszeństwo przed `frame.env` i opcjami add-onu i przetrwają restart.
  Nowe `GET`/`PUT`/`DELETE /api/device/config`; PIN nigdy nie wraca do
  aplikacji, tylko `pin_set`. Po zapisie aplikacja od razu sprawdza, czy
  ekran odpowiada (albo odrzuca PIN).

- Muzea bez zwykłych zdjęć. Wikimedia Commons szuka tylko plików
  opisanych jako dzieła sztuki i pomija pliki z kategorii zdjęć
  użytkowników; fotografie z muzeów (odbitki żelatynowo-srebrowe,
  albuminy, dagerotypy…) nie trafiają do wyszukiwania, losowania ani
  katalogu, a już pobrane znikają jednorazowo razem z rękopisami.
  Openverse szuka tylko w kategoriach dzieł i ilustracji.

- „+” przy wyszukiwaniu (Muzea i edytor playlisty) otwiera style,
  tematy, okresy i techniki do zaznaczenia, więc do stylu można dodać
  temat.

## 0.6.0

- Nowsze dzieła legalnie. Domena publiczna liczona także według prawa UE
  (70 lat po śmierci twórcy; daty z Europeany i Wikidata), co otwiera
  m.in. Kandinsky'ego, Mondriana, Klee, Matisse'a i Légera. Nowe źródła:
  Europeana (także w Propozycjach; dzieła „in copyright” przyjmowane, gdy
  twórca zmarł ponad 70 lat temu) i Openverse (Creative Commons; bez
  „Użytku prywatnego” tylko CC0). Opcjonalne klucze: `europeana_key`,
  `openverse_client_id`, `openverse_client_secret`.

- WikiArt tylko do testów panelu: nowe ustawienie `wikiart` (przełącznik
  w aplikacji). Bez niego WikiArt nie pojawia się w `GET /api/museums`
  ani w wyszukiwaniu; nigdy nie trafia do Propozycji; po wyłączeniu jego
  dzieła znikają z biblioteki.

## 0.5.0

- Nowe Odkrywaj. Słownik stylów, tematów, okresów i technik po polsku ze
  słowami, których używają muzea (`PlaylistRules.terms`, artyści
  dopasowywani po słowach: „Hokusai” pasuje do „Katsushika Hokusai”).
  36 tematów w grupach z okładkami i liczbą dzieł z katalogu
  (`GET /api/themes`, `GET /api/themes/{key}`,
  `POST /api/themes/{key}/playlist`), nowe `GET /api/vocabulary`,
  `/api/terms`, `/api/terms/museums` i `/api/discover/search`;
  `/api/library/items` przyjmuje `terms` i lata. Rękopisy nie trafiają do
  katalogu i są ukryte, chyba że ktoś o nie zapyta
  (`technique:manuscripts`); już pobrane znikają z katalogu jednorazowo.

- Podgląd z passe-partout dla aplikacji 5–8× szybciej: składa tylko
  układ, karton i opis (bez mapowania tonów i ditheringu) i idzie jako
  JPEG. Serwer pobiera z wyprzedzeniem oryginały wszystkich 8 obrazów
  z „Następne” (było 3).

- Gładsza faktura kartonu (0,3% w miękkich plamach zamiast 1,2% w drobnym
  ziarnie). Mniejszy tekst opisu (treść ok. 60% dawnej wielkości, wiersze
  do połowy krótszego boku); tytuł i autor prawie jak dotąd.

- Nowe linki do albumów udostępnionych z iOS 26 do albumów udostępnionych z iOS 26
  (`https://photos.icloud.com/shared/album/<token>`) działają. To albumy
  w nowym API iCloud (CloudKit, „shared collections”), a serwer znał tylko
  stary format `www.icloud.com/sharedalbum/#<token>`. Z nowych albumów
  przychodzą pełne oryginały (zamiast ok. 2048 px), także HEIC (nowa
  zależność `pillow-heif`), do tego data i miejsce zdjęcia od razu przy
  synchronizacji. Stare linki działają jak dotąd.

- Synology: `pull_policy: always` w `deploy/synology/docker-compose.yml`,
  więc Projekt → frame → Kompiluj sam pobiera nowy obraz (bez usuwania
  starego).

## 0.4.1

- Serwer znów startuje w kilka sekund po aktualizacji z 0.3.0. Jednorazowe
  porządki w bibliotece (czyszczenie opisów z Commons, czysty start
  katalogu) robiły tysiące zapisów do SQLite, każdy z kilkoma
  synchronizacjami dysku; na dysku NAS start trwał wiele minut, a port
  8099 był w tym czasie zamknięty („Nie można połączyć się z serwerem”).
  Biblioteka trzyma teraz jedno połączenie z bazą (`synchronous=NORMAL`
  w trybie WAL), a porządki idą w jednej transakcji.

## 0.4.0

- Albumy iCloud jako playlisty (`kind: "album"` z `album: {url, order}`):
  wiele albumów, każdy z kolejnością zdjęć (losowo, najnowsze, najstarsze,
  ostatnio dodane). Synchronizacja co 30 min pobiera tylko miniatury, a
  oryginał przez świeży link przed pokazaniem. Nowe endpointy
  `POST/GET /api/playlists/{id}/sync` i `POST /api/albums/check`; znikają
  `/api/album`, `/api/album/sync` oraz `mode` i `album_url` w ustawieniach
  (stary album zamienia się sam w playlistę).

- Harmonogram: zamiast interwałów osobno dla zasilacza i baterii godziny
  zmiany obrazu (`change_times`, jedna lub kilka dziennie) i co ile dni
  (`change_every_days`, 1–3). Cisza nocna trwa od `quiet_start` do
  porannej zmiany; `quiet_end`, `interval_minutes` i
  `interval_minutes_battery` znikają, a stare ustawienia zamieniają się
  same. Harmonogram jest ten sam przy ładowarce i na baterii; głęboki sen
  w nocy tylko na baterii, na ładowarce zdjęcia idą od razu.

- „Styl obrazu” dobierany automatycznie do każdego obrazu (domyślnie):
  bez koloru czarno-biały, zdjęcia jako zdjęcia, drzeworyty, litografie
  i plakaty jako grafika, reszta jako obraz. Ręczny wybór dalej możliwy.

- Dzieła z internetu zamiast importowanej biblioteki: serwer trzyma katalog
  miniatur (do `FRAME_CATALOGUE_MB`, domyślnie 1000 MB, dorasta co godzinę)
  i pamięć podręczną oryginałów (`FRAME_IMAGE_CACHE_MB`, 500 MB). Domyślna
  rotacja to Propozycje; nowe `/api/suggestions`, `/api/themes`,
  `/api/browse`. Dzieła zaimportowane wcześniej z muzeów są jednorazowo
  usuwane (własne prace i zdjęcia zostają).

- Pojedyncze dzieła można usuwać z playlist; z inteligentnej trafiają do
  wyjątków (`rules.exclude_ids`).

- Postęp obrazu w drodze na ramkę: `GET /api/progress` (też `progress` w
  `GET /api/player`), etapy przetwarzania, ładowania i wyświetlania z
  szacowanym czasem. Podgląd kadru przed zapisem (`?framing=` w
  `…/preview`, `?automatic=true` w `…/framing`).

- Tytuły, daty i opisy z Wikimedia Commons bez znaczników wikitekstu;
  istniejące pozycje poprawiane przy starcie.

## 0.3.0

- Zasilanie na baterii: w godzinach ciszy ekran dostaje budzik (MDC `0x25`)
  na koniec ciszy i zasypia głęboko; w dzień WoL przed wysyłką. Obraz,
  którego ekran nie odebrał, czeka i idzie, gdy ekran się pojawi
  (`pending_push`, `wakes_at` w statusie).
- Podglądy w aplikacji pokazują kadr, passe-partout i napisy w oryginalnych
  kolorach; korekta kolorów i dithering trafiają tylko do obrazu dla ekranu.
- „Pobierz pasujące dzieła z muzeów” w edytorze inteligentnej playlisty
  (`POST /api/library/fill`).

## 0.2.0

- Wyniki Etapu 0: zmierzona paleta EM32DX jest domyślna, preset `photo`
  używa `passthrough`, zasilanie USB-C odczytywane z bajtu stanu baterii.
- Biblioteka: Rijksmuseum, wyszukiwanie we wszystkich muzeach naraz,
  dodawanie wielu prac, pakiety tematyczne, „Losuj do biblioteki”,
  przełącznik „Użytek prywatny” (wolne licencje z Commons).
- Kadrowanie: passe-partout z fazą i kolorem z obrazu, tryb „Detale”
  i „Opis”, automatyczny kadr; zdjęcia mają własne tryby (Passe-partout,
  Wypełnij, Multi z kilkoma zdjęciami na jednej planszy).
- Budzenie na baterii: on-timer ekranu (MDC `0x25`), dłuższe serie WoL,
  także unicastem na adres ekranu.
- Kalibracja kolorów ze zdjęcia (`/api/calibration`); kreator w aplikacji
  usunięty.
- Poprawki: `public_host` może zawierać `http://`, raporty
  `/content-transfer-progress` są logowane, brak konfiguracji ekranu
  pokazuje błąd zamiast cichego pominięcia.

## 0.1.0

- Pierwsza wersja: serwowanie treści dla ekranu (`content.json` i obraz),
  wysyłanie przez MDC, Wake-on-LAN, renderowanie obrazów z presetami
  `photo`, `painting`, `graphic` i `bw`, API dla aplikacji iOS.
