# Changelog

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
