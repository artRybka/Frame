# Plan prac — Frame

Ramka na obrazy, grafiki i zdjęcia zbudowana na ekranie **Samsung EM32DX**
(32", kolorowy e-papier E Ink Spectra 6, 2560×1440, Tizen 8, Wi-Fi, bateria).
Wzorujemy się na ramce InkJoy: biblioteka obrazów z opisami, udostępniony album
zdjęć iCloud i aplikacja iOS do sterowania.

## 1. Ustalenia

| Temat | Decyzja | Konsekwencje |
|---|---|---|
| Firmware | **Oryginalny**, bez modyfikacji; **automatyczne aktualizacje wyłączone** | Sterujemy przez protokół MDC (TCP 1515, TLS, PIN). Ekran sam pobiera manifest `content.json` i obraz z naszego serwera. Gwarancja zostaje, nie ryzykujemy zablokowania urządzenia. Firmware aktualizujemy ręcznie, gdy wiemy, że protokół dalej działa. |
| Serwer | **Jeden obraz Dockera, dwa sposoby uruchomienia** | (a) add-on na **HA Green** (aarch64), (b) kontener na **Synology RS1619xs+** obok HA Container (amd64, `docker-compose`). Wybór później. Wymagana sieć hosta: ekran pobiera obrazy z IP serwera, a Wake-on-LAN wymaga broadcastu. W trakcie prac serwer można też uruchamiać na Macu. |
| Zasilanie | **Mieszane** (bateria + doładowywanie) | Jeden harmonogram przy ładowarce i na baterii (2026-10-25). W dzień zmiany na żądanie (WoL); w ciszy nocnej na baterii pełny sen z budzikiem na poranną zmianę, na ładowarce wysyłka od razu. |
| iOS | **TestFlight dla rodziny**, nazwa „Frame”, interfejs **po polsku** | SwiftUI, iOS 17+, płatne konto Apple Developer, w przyszłości widget i rozszerzenie „Udostępnij”. |
| Użytkownicy | **Rodzina z rolami** | Administrator: wszystko (ustawienia ekranu, użytkownicy). Domownik: wysyłanie zdjęć z rolki, następny/poprzedni/przypnij, tryb i harmonogram, ulubione i wykluczenia. Każdy ma własny token, więc wiadomo, kto co wysłał. |
| Dostęp spoza domu | **Tailscale / VPN** | Serwer nie jest wystawiony do internetu. |
| Tryb ramki | **Playlista: dzieła albo album iCloud** (bez mieszania) | Wybór playlisty w aplikacji; każdy album iCloud to osobna playlista (zmiana z 2026-10-25, D12). Do tego jednorazowe **zdjęcie z rolki aparatu**: przy wysyłce wybierasz, jak długo zostaje (do następnej zmiany, na X godzin/dni, na stałe). |
| Częstotliwość | **Ustawiana w aplikacji** | Godziny zmiany (jedna lub kilka dziennie, domyślnie 07:00), codziennie albo co 2–3 dni, tak samo przy ładowarce i na baterii. Cisza nocna od wybranej godziny do porannej zmiany. Zmiana co najmniej raz na 3 dni (ochrona panelu). |
| iCloud | **Publiczny link albumu** | Serwer sam synchronizuje album. Dwa rodzaje linków: stare albumy (`www.icloud.com/sharedalbum/#…`), gdzie Apple zmniejsza zdjęcia do ok. 2048 px (na ekranie 2560 px lekkie powiększenie ×1,25, przy ditheringu niewidoczne), i albumy z iOS 26 (`photos.icloud.com/shared/album/…`, CloudKit) z pełnymi oryginałami, także HEIC. Szczegóły zdjęcia: data i godzina, miejsce, kto dodał i podpis. |
| Biblioteka | **Muzea z otwartym API + własne prace** | Priorytety: wielkie muzea światowe, sztuka polska, drzeworyt japoński (ukiyo-e), plakaty i ilustracje. Domena publiczna (także według prawa UE) i CC0; licencje CC przy „Użytku prywatnym”. Opisy **w oryginale (angielskim)**, bez tłumaczenia. |
| Prezentacja | **Do wyboru w aplikacji** | Kadrowanie i etykieta na ramce (tytuł, autor, rok albo data zdjęcia), osobno dla sztuki i dla zdjęć. Sztuka: passe-partout / wypełnienie / opis / automatycznie. Zdjęcia: passe-partout / wypełnienie / multi (2–8 zdjęć albo losowo na jednej planszy). |
| Orientacja | **Zmieniana** | Każdy obraz renderujemy pod bieżącą orientację; portret obracamy do natywnego bufora 2560×1440. |
| Kalibracja | **Zdjęcie iPhonem** | Plansza testowa na ekranie, zdjęcie z białą kartką obok jako wzorcem, z tego wyliczamy zmierzoną paletę. Ramka wisi w jasnym pomieszczeniu z dużą ilością dziennego światła, więc kalibrujemy w świetle dziennym. |
| Licencja | **MIT** | Repozytorium jest publiczne. |

## 2. Dlaczego obrazy z aplikacji Samsunga są za ciemne (hipoteza robocza)

Farby Spectra 6 są dużo ciemniejsze niż ich „nominalne” wartości RGB. Biel
panelu to w praktyce jasnoszary (ok. 190/255), czerwień to ok. (135, 19, 0),
a zieleń jest bardzo ciemna. Algorytm, który dobiera punkty tak, jakby czerwień
była (255, 0, 0), systematycznie zaniża jasność i nasycenie. Nasz model takiego
„naiwnego” ditheringu (`frame render ... --strategy passthrough --preview`)
odtwarza dokładnie ten efekt. Rozwiązanie składa się z czterech kroków:

1. dithering względem **zmierzonych** kolorów farb,
2. mapowanie tonów do rzeczywistego zakresu panelu (podniesienie cieni i półtonów),
3. mapowanie gamutu do bryły kolorów, które da się zmieszać z sześciu farb,
4. wysłanie obrazu złożonego wyłącznie z „czystych” farb, o ile ekran go nie przetworzy ponownie. Rozstrzygnie to eksperyment E5.

Szczegóły: [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md).

## 3. Architektura (skrót)

```
 iPhone (app Frame) ──HTTP/JSON──┐
                                 ▼
             ┌──────────── Home Assistant ─────────────┐
             │  add-on Frame (Python)                  │
             │   • biblioteka (SQLite + pliki)         │
             │   • źródła: muzea, iCloud, upload       │
             │   • pipeline obrazu (numba)             │
             │   • harmonogram rotacji / zasilanie     │
             │   • /panel/content.json + /panel/images │
             └───────┬────────────────────▲────────────┘
          MDC 0xC7   │ TLS :1515           │ HTTP GET (ekran pobiera)
          WoL (UDP)  ▼                     │
                 Samsung EM32DX ───────────┘
```

Więcej: [ARCHITECTURE.md](ARCHITECTURE.md), protokół: [DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md).

## 4. Etapy

### Etap 0 — Rozpoznanie urządzenia ⟵ *jesteśmy tutaj*

Cel: potwierdzić protokół na Twoim egzemplarzu i poznać zachowanie ekranu.

- [x] Klient MDC (TLS, PIN, ramki, bateria, network standby, content download), Wake-on-LAN.
- [x] Serwer treści (`content.json`, obraz, log zapytań ekranu) i CLI `frame`.
- [x] Plansze testowe: `palette`, `passthrough`, `ramps`.
- [ ] Eksperymenty E1–E12 na ekranie ([EXPERIMENTS.md](EXPERIMENTS.md)). **Wymaga Ciebie i ekranu.** Zrobione 2026-10-25: E1–E5, częściowo E7 i E8; zostały testy 24 h (E7, E8), E6, E9–E12.
- [ ] Narzędzie do eksperymentu E6 (manifest z kilkoma obrazami), po wynikach E2.
- [ ] Decyzje: strategia obrazu (passthrough / compensate / dither), format pliku (PNG/JPEG), polityka zasilania. *Stan po E5: piksele są 1:1, więc docelowo `dither` + PNG (JPEG psułby czyste farby); `compensate` odpada. Strojenie na oko (E14): `passthrough` z korektą wygrał we wszystkich presetach, więc jest domyślny; `dither` zostaje do porównań i dla podpisów i passe-partout. Polityka zasilania czeka na E8 (WoL przez Wi-Fi nie budzi ekranu na baterii).*

**Gotowe, gdy:** ekran pokazuje obraz z naszego serwera, mamy wyniki E1–E8 i podjęte decyzje.

### Etap 1 — Algorytm obrazu i kalibracja

- [x] Pipeline v0: przestrzeń liniowa i OKLab, mapowanie tonów, mapowanie gamutu do bryły farb, dyfuzja błędu (7 jąder, serpentyna, ograniczanie błędu), presety `photo` / `painting` / `graphic` / `bw`, podgląd wyglądu na ekranie.
- [x] 1.1 Pomiar palety EM32DX: plansza `palette` i zdjęcie iPhonem, pomiar przez `/api/calibration`. Pomiar 2026-10-25 (lampa światła dziennego): wbudowana paleta `em32dx` w `server/src/frame_server/imaging/palette.py`, teraz domyślna.
- [ ] 1.2 Zestaw testowy ok. 20 obrazów (portrety, krajobrazy, olej, akwarela, drzeworyt, plakat, zdjęcia czarno-białe) i procedura porównań A/B: zdjęcia ekranu w tym samym świetle.
- [ ] 1.3 Strojenie presetów na prawdziwym ekranie. *Pierwsza runda (E14, 12 plansz po 6 wariantów): wszystkie presety na `passthrough` z korektą jasnych partii i szarości. Do zrobienia: potwierdzenie na zdjęciach z rolki i na dłuższej playliście.*
- [ ] 1.4 Ulepszenia algorytmu:
  - szarości bez kolorowego szumu (preferencja osi czarny–biały),
  - kompromis jasność/nasycenie przy mapowaniu gamutu (np. niebo bardziej niebieskie kosztem jasności),
  - dithering uporządkowany / blue-noise dla grafiki płaskiej,
  - [x] automatyczny dobór presetu według treści: „Styl obrazu automatycznie” (domyślnie włączony, `preset: "auto"`). Obraz bez własnego koloru (rysunek, rycina, fotografia czarno-biała lub w sepii, mierzone jako rozrzut barwy wokół jednego odcienia, `tint_spread`) idzie jako `bw`; zdjęcia i fotografie z muzeów jako `photo`; drzeworyty, litografie, ryciny, plakaty i ilustracje (po klasyfikacji i technice, także po niderlandzku i polsku) jako `graphic`; reszta jako `painting`. Dotychczasowe domyślne style przełączone raz na automatyczne, wybrane ręcznie zostają. Do sprawdzenia na ekranie w 1.3.
  - inteligentne kadrowanie (twarze i ważne obszary),
  - podpisy i passe-partout bez ditheringu (czysty tekst).
- [ ] 1.5 Obiektywna metryka jakości (ΔE po rozmyciu, w stylu S-CIELAB) do porównywania ustawień.
- [x] 1.6 Wydajność na sprzęcie Home Assistanta (cel: poniżej 10 s na obraz) i cache renderów: render kilka razy szybszy bez zmiany wyniku (PNG bez `optimize`, tablica sRGB, liczenie pasami na wszystkich rdzeniach), następny obraz rysowany z wyprzedzeniem, więc zmiana o czasie tylko publikuje gotowy plik ([IMAGE_PIPELINE.md](IMAGE_PIPELINE.md#wydajność)). *(Do potwierdzenia czas na Synology: pasek postępu uczy się czasu etapu „przetwarzanie”.)*

**Gotowe, gdy:** zdjęcia i obrazy na ramce wyglądają dobrze w ocenie domowników, nie są za ciemne, a kolory mają naturalną tonację.

### Etap 2 — Serwer (add-on Home Assistant / kontener na Synology)

- [x] 2.1 Model danych (SQLite): `Item` (dzieło / zdjęcie / własna praca, metadane, licencja, paleta, tagi kolorów, ocena dla e-papieru), playlisty, ustawienia i stan odtwarzacza, historia; cache podglądów. *(`User` w 2.7.)*
- [x] 2.2 Biblioteka: upload własnych prac z opisem, import z muzeów (Art Institute of Chicago, Cleveland, The Met, Rijksmuseum, Wikimedia Commons), biblioteka startowa i domyślne playlisty przy pierwszym uruchomieniu, ocena „przydatności dla e-papieru”. *(Do zrobienia: Polona i muzea narodowe — MNW ma tylko wewnętrzne API strony, NGA tylko zrzuty CSV bez wyszukiwania, Europeana zwraca dużo słabych skanów (przeźrocza, pocztówki), więc na razie bez nich. Sztuka polska jest na razie tylko z Wikimedia Commons, bo AIC, Cleveland i The Met jej prawie nie mają; Commons ogranicza zapytania z serwerowni, z sieci domowej działa.)* Źródła według priorytetów:
  - wielkie muzea: The Met, Art Institute of Chicago, Rijksmuseum, Cleveland Museum of Art;
  - sztuka polska: Polona (grafiki, plakaty, ilustracje), muzea narodowe (do sprawdzenia, czy mają API i licencje);
  - drzeworyt japoński (ukiyo-e) z kolekcji powyższych muzeów;
  - plakaty i ilustracje (polska szkoła plakatu, ilustracje botaniczne, mapy).
- [x] 2.2a Większy katalog: w zakładce „Muzea” wyszukiwanie domyślnie we wszystkich muzeach naraz (równolegle, wyniki na przemian), kolejne strony wyników i „Dodaj wiele” (do 500 naraz, w tle), oraz pakiety tematyczne „Rozszerz bibliotekę” (impresjonizm, ukiyo-e, malarstwo holenderskie, sztuka polska, plakaty, botanika, pejzaże; łącznie do ok. 1460 dzieł). Import zapisuje tylko miniatury (ok. 60 KB), pełne obrazy pobierane są przy pierwszym wyświetleniu. Przy zapisie inteligentnej playlisty można pobrać do biblioteki 50–300 pasujących dzieł ze wszystkich muzeów (`POST /api/library/fill`; artyści i słowa kluczowe przez wyszukiwarki muzeów, style i epoki przez losowanie, kolorystyka i jakość sprawdzane po pobraniu miniatury). Kreator „Losuj do biblioteki”: okres, styl, rodzaj i liczba (do 500), losowo na zmianę z AIC, Cleveland, Met i Rijksmuseum, z pominięciem dzieł słabo wyglądających na e-papierze (`POST /api/library/draw`). Przełącznik „Użytek prywatny” (ustawienie `private_use`, w aplikacji Ramka → Źródła dzieł) dopuszcza z Wikimedia Commons, Europeany i Openverse także wolne licencje (np. CC BY-SA); muzea dalej tylko domena publiczna, bo dzieł chronionych i tak nie udostępniają w dużej rozdzielczości.
- [ ] 2.2b Dzieła z internetu zamiast biblioteki ([plan](https://claude.ai/artifact/5qFAV39oGVhKmNJf9LjZ4d)): serwer trzyma katalog dzieł z miniaturami i kolorami (do 1 GB) oraz dzieła zatrzymane przez Ciebie, a pełne obrazy tylko jako pamięć podręczną; Odkrywaj = propozycje, katalog miniatur z filtrami (także po kolorach), motywy i wyszukiwarka w muzeach; playlisty inteligentne dobierają dzieła z muzeów w tle.
  - [x] Oryginały muzealne jako pamięć podręczna z limitem (`FRAME_IMAGE_CACHE_MB`, domyślnie 500 MB; najdawniej używane usuwane pierwsze, własne prace i zdjęcia zawsze zostają), pobieranie oryginałów 3 następnych obrazów zaraz po zmianie, a bez internetu zmiana na następny obraz, który już jest na serwerze (albo ponowna próba za 15 min). Miniatury z Commons w standardowej szerokości 500 px.
  - [x] Pokaż, podgląd, kadr, ulubione i playlisty dla dzieł spoza biblioteki: endpointy `/api/library/items/{id}` przyjmują też dowolne `<muzeum>:<id>`; przeglądanie niczego nie zapisuje, a serce, kadr, „Pokaż” lub playlista dodają dzieło do biblioteki. Miniatury przeglądanych dzieł: najnowsze 500, reszta usuwana.
  - [x] Czysty start (prośba Mateusza z 2026-10-25): przy pierwszym uruchomieniu nowej wersji serwer raz usuwa dzieła z muzeów zaimportowane wcześniej (z miniaturami, oryginałami, miejscami w playlistach i kolejce); własne prace i zdjęcia zostają.
  - [x] Katalog: serwer sam dobiera dzieła z muzeów (motywy pakietów i losowanie obrazów, grafik, rysunków i plakatów, po 300 co godzinę) aż miniatury zajmą `FRAME_CATALOGUE_MB` (domyślnie 1000 MB, ok. 10–15 tys. dzieł), do przeglądania i filtrowania po kolorach w aplikacji. Ponad limit znikają dzieła dodane przez serwer, których nikt nie zatrzymał, od najsłabszych na e-papierze. Pole `pooled` odróżnia dodane przez serwer od zatrzymanych (`kept=true` w `/api/library/items`).
  - [x] Propozycje jako domyślna rotacja (wybór Mateusza z 2026-10-25): 24 dzieła z katalogu, połowa według ulubionych artystów, a gdy katalogu brakuje, dobierane z muzeów (motyw dnia, artyści, losowe obrazy); do tego własne prace. Inteligentne playlisty dobierają w tle do 24 pasujących dzieł, gdy zostaje mniej niż 8 niepokazanych.
  - [x] API Odkrywaj: `/api/suggestions` (Dla Ciebie, Motyw dnia, Najlepiej na e-papierze), `/api/themes` i `/api/themes/{key}?page=` (motywy stronami, na żywo), `/api/browse` (okres, styl, rodzaj ze wszystkich muzeów).
  - [x] Aplikacja: Odkrywaj = Propozycje (rzędy i motywy przeglądane stronami), Katalog (filtry, kolory, „Moje” = zatrzymane) i Muzea (wyszukiwanie, karta dzieła bez importu, „Zapisz”); bez pakietów i losowania do biblioteki; rotacja bez playlisty nazywa się „Propozycje”.
- [x] 2.2c Nowe Odkrywaj ([propozycja](https://claude.ai/artifact/Pc7LzAJ3GUYExHt5wY14KJ), zaakceptowana przez Mateusza 2026-10-25): dwie zakładki, Propozycje i Muzea.
  - [x] Słownik (`library/vocabulary.py`): style, tematy, epoki i techniki po polsku z angielskimi słowami muzeów; reguły `terms` w playlistach (np. `subject:sea`, `years:1880-1914`; ten sam rodzaj = alternatywy, różne rodzaje razem); artyści dopasowywani po słowach („Hokusai” = „Katsushika Hokusai”). API: `/api/vocabulary`, `/api/terms?q=` (artyści z bazy, terminy, słowa, z liczbą dzieł), `/api/terms/museums?q=` (co mają muzea, gdy baza nie wie), `/api/discover/search` (muzea dla słów, artystów, terminów i lat).
  - [x] Rękopisy (karty kodeksów, Księgi godzin, strony Koranu i Szahname) nie trafiają do katalogu, propozycji ani wyników; jednorazowo usunięte z katalogu. Można je wybrać techniką „Rękopisy i miniatury”.
  - [x] Propozycje: 36 motywów w grupach (kierunki, grafika, tematy, sztuka polska, kolor, epoki) jako karty z okładką z katalogu, „+ Playlista” i „Graj na ramce” (`POST /api/themes/{key}/playlist`, playlista dociąga dzieła z muzeów); rzędy „Bo lubisz…”.
  - [x] Muzea: jedno pole z chipami i podpowiedziami; wyniki z katalogu od razu, z muzeów doczytywane; filtry techniki, koloru i muzeum; „Utwórz playlistę z tego wyszukiwania”. Zakładka Katalog zniknęła, „Zapisane dzieła” są w Playlistach.
  - [x] Edytor playlisty: to samo wyszukiwanie zamiast list faset; gdy w bazie nic nie ma, podpowiada z muzeów i włącza pobieranie.
  - [x] Bez zwykłych fotografii (zgłoszenie Mateusza z 2026-10-25): z Wikimedia Commons tylko pliki opisane jako dzieła sztuki (szablon `{{Artwork}}`/`{{Painting}}`), bez plików z kategoriami zdjęć („Photographs taken on…”, „Taken with…”, „Self-published work”); z muzeów bez fotografii (działy i techniki: gelatin silver, albumen, dagerotypy…). Fotografie i rękopisy zebrane wcześniej usuwane raz z katalogu.
  - [x] Łączenie filtrów: przycisk „+” w polu wyszukiwania otwiera style, tematy, epoki i techniki do zaznaczenia (np. Impresjonizm + Morze + 1850–1900), w Muzeach i w edytorze playlisty.
  - [x] Zakładka „Muzea” nazywa się „Szukaj” (prośba Mateusza z 2026-10-26). Dotknięcie autora w szczegółach dzieła (z „Teraz”, Odkrywaj i playlist) przenosi do Odkrywaj → Szukaj z żetonem tego artysty, czyli z jego pracami z katalogu i muzeów.
  - [x] Prostsze „Szukaj” (prośba Mateusza z 2026-10-26): bez dymków stylów, kierunków, tematów, epok i technik na ekranie (zostają pod „+” w polu wyszukiwania), zostają Muzea; wybrane muzeum to żeton w polu wyszukiwania, jak temat czy epoka. W wynikach zostają filtry muzeum i koloru. Autor w karcie dzieła na ekranie „Teraz” też otwiera wyszukiwanie jego prac.
  - [x] Szybsze Propozycje (zgłoszenie Mateusza z 2026-10-26). Pomiar na katalogu 5000 dzieł: okładki i liczby 36 motywów to 2,5 s liczenia co 10 minut (na NAS-ie kilka razy dłużej), Motyw dnia czekał na odpowiedź muzeum (a gdy nie odpowiadało, przy każdym otwarciu), aplikacja czekała na oba zapytania naraz i od razu pobierała ~140 miniatur okładek. Teraz: serwer liczy motywy w tle (po starcie i co 10 min, w międzyczasie oddaje poprzednie), Motyw dnia bierze z katalogu, gdy ma co najmniej 8 dzieł, a muzeum czeka najwyżej 3 s (spóźniona odpowiedź jest na następny raz); zapamiętane rozpoznawanie fotografii i rękopisów (zapytania katalogu ~2× szybsze), rzędy i okładki bez długich opisów. Aplikacja pokazuje od razu ostatnie Propozycje (także po ponownym uruchomieniu), wczytuje je już przy starcie, motywy i rzędy wyświetla osobno, gdy tylko przyjdą, pobiera miniatury tylko widocznych kart, trzyma miniatury na dysku (do 300 MB) i odświeża się pociągnięciem w dół.
- [x] 2.2d Nowsze dzieła legalnie ([rozeznanie](https://claude.ai/artifact/3dqPMdWdG3cz9D5u7tMg6i), Mateusz wybrał punkty 1 i 2 oraz WikiArt do testów, 2026-10-25):
  - [x] Domena publiczna według prawa UE (`library/lifespan.py`): dzieło jest wolne 70 lat po śmierci twórcy (w 2026 r. zmarli do 1955). Daty śmierci z bazy osób Europeany (zbudowanej z Wikidata) i z Wikidata, trzymane w pamięci.
  - [x] Europeana jako źródło (`europeana`, także w Propozycjach i katalogu): dzieła oznaczone jako wolne, a oznaczone „in copyright” wtedy, gdy wszyscy twórcy zmarli ponad 70 lat temu (licencja „Domena publiczna w UE (twórca zm. …)”); z „Użytkiem prywatnym” także CC. Bez obrazów poniżej 0,42 Mpx. Klucz `FRAME_EUROPEANA_KEY` (domyślnie wspólny klucz demo). *(Polskich muzeów jest tam mało, MNW prawie wcale.)*
  - [x] Openverse (`openverse`): Flickr, Commons i muzea na CC; bez „Użytku prywatnego” tylko CC0 i domena publiczna, z nim wszystkie licencje CC, z podpisem autora w opisie. Anonimowo 200 zapytań dziennie, więcej z `FRAME_OPENVERSE_CLIENT_ID`/`_SECRET`. Nie zasila katalogu.
  - [x] WikiArt (`wikiart`) tylko do testów panelu, za przełącznikiem w aplikacji (Ramka → Źródła dzieł, ustawienie `wikiart`): widoczny w wyszukiwaniu tylko po włączeniu, nigdy w Propozycjach ani w playlistach bez wskazania źródła; po wyłączeniu jego dzieła znikają z biblioteki.
  - [x] Bez powtórek z kilku źródeł (prośba Mateusza z 2026-10-25, `library/duplicates.py`): to samo dzieło z muzeum, Europeany, Commons, Openverse czy WikiArt rozpoznawane po tytule (bez przedimków, dat, nawiasów i nazwiska w nazwach plików Commons) i artyście, z kontrolą roku (±2) i proporcji (±15%); tytuły typu „Pejzaż”, „Autoportret” tylko z rokiem; ten sam adres strony lub obrazu też łączy. Zostaje kopia zachowana przez właściciela, a z dodanych przez serwer ta z pewniejszego źródła: muzeum → Europeana → Commons → Openverse → WikiArt. Dotyczy wyszukiwania we wszystkich źródłach, Odkrywaj, motywów, uzupełniania Propozycji, katalogu i playlist inteligentnych, dodawania do playlist ręcznych; zapasowe kopie w katalogu serwer usuwa przy starcie i porządkach. W aplikacji „Więcej z muzeów” i kolejne strony motywu pomijają kopie z poprzednich stron (pole `work`). Wyszukiwanie w jednym wybranym źródle pokazuje je bez zmian. *(Tytuły w różnych językach, np. „De Nachtwacht” i „The Night Watch”, nie są łączone.)*
- [x] 2.3 Synchronizacja udostępnionego albumu iCloud z publicznego linku: nowe zdjęcia, usunięcia, metadane (data i godzina, miejsce, kto dodał, podpis), deduplikacja. *(Do sprawdzenia na prawdziwym albumie: API jest nieudokumentowane.)*
  - [x] Nowe linki z iOS 26 (`photos.icloud.com/shared/album/…`, 2026-10-25): album to strefa CloudKit odczytywana anonimowym dostępem z publicznego linku; oryginały w pełnej rozdzielczości (HEIC przez `pillow-heif`), miejsce i data z rekordów. Sprawdzone na prawdziwym albumie Mateusza.
  - [x] Albumy jako playlisty (prośba Mateusza z 2026-10-25): playlista rodzaju „Album iCloud” z linkiem i kolejnością (losowo, najnowsze, najstarsze, ostatnio dodane); albumów może być wiele. Synchronizacja co 30 min pobiera tylko miniatury, a oryginał zdjęcia przez świeży link tuż przed pokazaniem (pamięć podręczna jak dla muzeów); zdjęcia usunięte z albumu znikają z playlisty, a usunięcie playlisty usuwa jej zdjęcia. Stary tryb „Album iCloud” w ustawieniach zamienia się sam w playlistę.
- [x] 2.4 Harmonogram: **playlista** (Propozycje, playlista dzieł albo album iCloud), godziny zmiany (jedna lub kilka dziennie, codziennie albo co 2–3 dni; domyślnie 07:00), cisza nocna do porannej zmiany, bez powtórek przez N dni, ulubione i wykluczenia, przypięcie. Zmiana obrazu co najmniej raz na 3 dni (ochrona panelu).
- [x] 2.5 Zdjęcie z rolki: wysyłka z czasem wyświetlania (do następnej zmiany / X godzin lub dni / na stałe), po czym wraca harmonogram.
- [ ] 2.6 Polityka zasilania (wg wyników E6–E8 i E13), harmonogram ten sam przy ładowarce i na baterii: w dzień WoL (Wi-Fi 2,4 GHz), w ciszy nocnej na baterii pełny sen z budzikiem `0x25` na poranną zmianę, zaległy obraz po pobudce *(zrobione w serwerze, [WAKE.md](WAKE.md); czeka na potwierdzenie w E13)*; po nocy serwer szuka ekranu, aż włączy z powrotem network standby; „Obudź ramkę” melduje, czy ekran się obudził *(2026-10-26; WoL z Synology do 192.168.1.x wymaga stałego wpisu ARP w routerze albo nogi NAS-a w tej sieci, zob. diagnozę w WAKE.md)*; monitorowanie baterii, powiadomienia.
- [ ] 2.7 Użytkownicy i role: administrator i domownik, osobne tokeny, parowanie urządzenia kodem QR, „kto wysłał” w historii.
- [x] 2.8 API dla aplikacji: Teraz, Następny/Poprzedni/Przypnij, Biblioteka z filtrami i facetami, wyszukiwanie i import z muzeów, Playlisty (inteligentne i ręczne, podgląd reguł), Harmonogram i Prezentacja, podgląd „na ramce”, Status (bateria, ładowanie, połączenie). *(Do zrobienia: Kalibracja, Użytkownicy, Bonjour `_frame._tcp`.)*
- [x] 2.9 Etykieta na ramce (opcjonalna): tytuł, autor, rok albo data zdjęcia, wypisane czystą czernią na passe-partout, bez ditheringu.
- [x] 2.10 Opisy w oryginale (angielskim) z API muzeów. Tytuły, daty i opisy z Wikimedia Commons są czyszczone z ukrytych znaczników QuickStatements (`title QS:P1476,…`) i etykiet języka („Polish: ”); z wielojęzycznych pól brany jest polski, potem angielski. Wpisy zapisane przez starsze wersje serwer poprawia raz, przy starcie. *(Do zrobienia: notki o autorach z Wikidata/Wikipedii.)*
- [x] 2.11 Wydawanie: obraz multi-arch w GHCR (`ghcr.io/artrybka/frame`), add-on (HA Green) i `docker-compose` (Synology). *(Do zrobienia: numeracja wersji, kopie zapasowe `/data`.)*

**Gotowe, gdy:** serwer sam zmienia obrazy z biblioteki albo albumu iCloud według harmonogramu, a nowe zdjęcie w albumie pojawia się w rotacji.

### Etap 3 — Aplikacja iOS (po polsku, TestFlight)

- [x] Szkielet: połączenie z serwerem (adres i token w Keychain), ekran „Teraz na ramce” (podgląd, opis), wysyłanie zdjęcia z presetem, stan ekranu (bateria, firmware).
- [x] Projekt graficzny „galeryjny” (papier, szeryfowe tytuły, oprawione dzieło, tło w kolorach obrazu, tryb ciemny), ikona; tryb demo z prawdziwymi dziełami bez serwera (obrazy i podglądy „na ramce” wbudowane w aplikację); zrzuty ekranów w CI.
- [x] Playlisty: inteligentne (artyści, style, tematy, kolorystyka, epoka, słowa kluczowe, ulubione, „najlepsze na e-papier”) z podglądem na żywo i ręczne; odtwarzanie na ramce; usuwanie pojedynczych dzieł z playlisty (menu „…” → „Usuń dzieła z playlisty” albo przytrzymanie dzieła). Z inteligentnej dzieło znika jako wyjątek od reguł (`rules.exclude_ids`) i można je przywrócić.
- [x] Ramka: bateria, zasilanie/ładowanie, połączenie, czuwanie Wi-Fi, następna zmiana; budzenie i usypianie. „Sprawdź stan” budzi śpiącą ramkę (na baterii po minucie wraca do lekkiego snu), a kafelek Sieć pokazuje stan: online, czuwanie, głęboki sen albo „nie odpowiada” *(2026-10-26)*. Wejście w zakładkę Ramka i przeciągnięcie w dół sprawdzają ramkę bez budzenia: gdy MDC milczy, serwer patrzy, czy ekran odpowiada na ARP, i pokazuje „Czuwanie, śpi, ale jest w sieci Wi-Fi” zamiast „nie odpowiada”; ostatni odczyt (m.in. network standby) przetrwa restart serwera *(2026-10-26, czeka na E15)*. Kafelek Zasilanie ma ikonę błyskawicy przy ładowaniu, wtyczki przy zasilaczu i baterii (z poziomem naładowania) na baterii.
- [x] Ramka → trybik w prawym górnym rogu → „Połączenie z ekranem” i „Serwer ramki” (osobny arkusz, poza główną listą ustawień): adres IP, PIN (MDC) i MAC (Wake-on-LAN) ustawiane w aplikacji i zapisywane na serwerze; mają pierwszeństwo przed `frame.env` / opcjami add-onu, „Przywróć wartości z serwera” wraca do nich. Po zapisie aplikacja od razu sprawdza, czy ekran odpowiada.
- [ ] 3.1 Wykrywanie serwera przez Bonjour i parowanie kodem QR (token użytkownika), działanie przez Tailscale / VPN poza domem.
- [x] 3.2 „Teraz”: opis dzieła (tytuł, autor, data, technika, muzeum, notka o autorze; po angielsku) lub zdjęcia (data i godzina, miejsce z GPS przez CLGeocoder, kto dodał, podpis). Bez nagłówka i stanu baterii, ramka w podglądzie biała jak prawdziwa. Strzałki po bokach przeglądają poprzednie i następne obrazy bez wysyłania, a „Wróć do obrazu na ramce” wraca z nich do tego, który jest teraz na ramce; dotknięcie obrazu otwiera kadrowanie na całym ekranie: wizualizacja ramki tak duża, jak się mieści, okienka kadru na podglądzie w swoich miejscach (przesuwanie i przybliżanie palcami, bez przypadkowego przewijania strony), w passe-partout także kształt okienka, „Kadr automatyczny” obok „Zapisz kadr”, zawsze na swoim miejscu i przygaszony, gdy kadr już jest automatyczny, więc podgląd nie zmienia rozmiaru („Anuluj” pyta o odrzucenie zmian); podgląd ramki nie ma ikonki kadrowania, kadrowanie otwiera samo dotknięcie. Zapisany kadr obrazu, który jest na ramce, ramka pokazuje od razu; „Pokaż na ramce” wysyła obraz, do którego doszły strzałki. Sąsiednie obrazy idą jak „następny”/„poprzedni”, żeby playlista zachowała kolejność. Dopóki podgląd z serwera się nie wygeneruje i nie doczyta, okienka kadru czekają, a na obrazie kręci się „Wczytuję podgląd…” (bez niepełnego podglądu przy przewijaniu). Podgląd liczy się szybką ścieżką (`render_original`: sam układ, karton i napisy, bez tonowania i ditheringu panelu, JPEG), 5–8× szybciej niż pełny render; aplikacja zamawia z wyprzedzeniem podgląd poprzedniego i następnego, a serwer pobiera oryginały wszystkich 8 „Następnych”. „Teraz” pokazuje stan faktyczny: serwer zapamiętuje, który obraz ekran naprawdę pobrał (`delivery.json`, z dziennika żądań panelu), a `GET /api/player` zwraca `delivery` (na ramce, w drodze, czeka na pobudkę, nie dotarł). Obraz, który nie dotarł, ma nad przyciskiem „Nie dotarł na ramkę” albo „Czeka na ramkę” z powodem, kartę „Na ramce nadal” z tym, co ekran faktycznie wyświetla, i przycisk „Wyślij ponownie” (albo „Obudź ramkę”, gdy czeka w lekkim śnie).
- [x] 3.3 Wysyłanie z rolki: wybór czasu wyświetlania (do następnej zmiany / X godzin lub dni / na stałe).
- [x] 3.3a Pasek postępu obrazu w drodze na ramkę: przetwarzanie (render), ładowanie (połączenie, budzenie, pobranie przez ekran) i wyświetlanie (odświeżanie e-papieru, szacowane), z szacowanym czasem do końca; pod obrazem w „Teraz”, przy wysyłaniu z rolki i jako mały pasek w pozostałych zakładkach (`GET /api/progress`). *(Do sprawdzenia na ekranie: czy treść raportów `POST /content-transfer-progress` pozwala zastąpić szacunek prawdziwym postępem.)*
- [x] 3.4 Harmonogram: playlista (Propozycje, dzieła albo album iCloud), godziny zmiany i co ile dni, cisza nocna. Album iCloud dodaje się jako playlistę (link sprawdzany od razu, nazwa albumu podpowiada nazwę playlisty, kolejność zdjęć), w szczegółach widać ostatnią synchronizację i przycisk „Synchronizuj”. „Dodaj do kolejki” przy dziele (szczegóły, długie przytrzymanie w Odkrywaj, playlistach i Zapisanych) wstawia je jako następne na ramce; w „Teraz” takie dzieła mają znaczek, a długie przytrzymanie pozwala je wycofać.
- [x] 3.5 Biblioteka: przeglądanie (siatka, filtry: artyści, style, tematy, kolorystyka, ulubione), szczegóły dzieła: dotknięcie oryginału otwiera go na całym ekranie (bez ikonki powiększenia, klikalny jest cały obraz; czarne tło, przybliżanie palcami i podwójnym stuknięciem, przesuwanie, stuknięcie chowa podpis), a dotknięcie widoku „Na ramce” otwiera to samo pełnoekranowe kadrowanie co w „Teraz”, wyszukiwanie i import z muzeów, ulubione, wykluczenia; ręczna playlista ze zdjęć z rolki (wiele naraz, z datą i miejscem z EXIF); menu „…” dzieła → „Zapisz w Zdjęciach” zapisuje obraz w rolce w największej dostępnej rozdzielczości (dzieło prosto z muzeum, a gdy się nie da, kopia z serwera do 2560 px; uprawnienie tylko do dodawania) *(2026-10-26)*. *(Do zrobienia: upload własnych prac z opisem.)*
- [x] 3.6 Prezentacja: kadrowanie i etykieta na ramce, osobno dla sztuki i dla zdjęć. Tryby: passe-partout (biały, kremowy, szary, czarny, jasne albo ciemne w odcieniu obrazu; faza 45° w kolorze kartonu, w ciemnym biały rdzeń; obraz chowa brzegi pod kartonem; kadr i kształt okienka do wyboru), wypełnienie z kadrem dobranym automatycznie (twarze, szczegóły), opis (detal co najmniej 1,8× większy niż obraz i tekst o dziele nadrukowany na kartonie, tytuł do trzech linii; kadr obrazu i detalu do poprawienia) i automatyczny; opis działa przy każdych proporcjach; tryb „Detale” (dwa fragmenty) wycofany, zapisane ustawienia przechodzą na opis; korekta kadru palcami na pełnoekranowym podglądzie ramki, otwieranym z „Teraz” i ze szczegółów dzieła („Na ramce”); „Styl obrazu” z objaśnieniem. Zdjęcia mają własne tryby: passe-partout, wypełnienie i multi: od 2 do 8 zdjęć (albo losowa liczba) na jednej planszy, każde w okienku passe-partout; 16 siatek (po 2–3 na liczbę zdjęć), wybór siatki albo „Auto”, które kieruje pionowe zdjęcia do pionowych okienek. Zapisana zmiana Prezentacji nie wysyła obrazu ponownie: nowy wygląd dostaje następny obraz na ramce (tylko obrót ekranu przerysowuje obecny od razu).
- [x] 3.6a Zakładka Ramka: wizualizacja w proporcjach ekranu (9:16 w pionie, 16:9 w poziomie), własna nazwa ramki w aplikacji (dotknięcie nazwy; pole `name` w ustawieniach, puste wraca do nazwy z ekranu).
- [ ] 3.7 Regulacja obrazu (administrator): suwaki (jasność, kontrast, nasycenie, cienie) z podglądem renderu na żywo.
- [x] ~~3.8 Kreator kalibracji~~ usunięty z aplikacji po E5: paleta EM32DX jest zmierzona i wbudowana w serwer; ponowny pomiar przez API serwera ([IMAGE_PIPELINE.md](IMAGE_PIPELINE.md#kalibracja-etap-1)).
- [ ] 3.9 Użytkownicy (administrator): zaproszenie domownika (kod QR), role, odebranie dostępu.
- [ ] 3.10 Widget (aktualny obraz) i rozszerzenie „Udostępnij → Pokaż na ramce”.
- [ ] 3.11 TestFlight dla domowników. *(Build trafia do TestFlight automatycznie z GitHuba, workflow `testflight` na Xcode 26; do zrobienia: grupy testerów i przegląd Apple dla testów zewnętrznych.)*

### Etap 4 — Integracja z Home Assistant

- [ ] Encje: aktualny obraz (`image`), bateria, zasilanie, przyciski następny/poprzedni, wybór kolekcji (MQTT discovery albo mała integracja).
- [ ] Przykładowe automatyzacje: obraz dnia o 7:00, kolekcje sezonowe, pauza, gdy nikogo nie ma w domu.

### Etap 5 — Dopracowanie

- [ ] Dostęp spoza domu przez Tailscale / VPN (instrukcja konfiguracji).
- [ ] Testy długoterminowe: zużycie baterii, ghosting, stabilność po aktualizacjach firmware.
- [ ] Dokumentacja użytkownika, kopie zapasowe, ewentualna strona konfiguracji w panelu Home Assistanta (ingress).

## 5. Kamienie milowe

| # | Kamień milowy | Etap |
|---|---|---|
| M0 | Ekran pokazuje obraz wysłany z naszego serwera | 0 |
| M1 | Zmierzona paleta EM32DX, wybrana strategia obrazu | 0–1 |
| M2 | Serwer (add-on lub kontener) rotuje obrazy z biblioteki muzealnej | 2 |
| M3 | Zdjęcia z albumu iCloud na ramce, z datą i opisem | 2 |
| M4 | Aplikacja iOS w TestFlight: Teraz, Biblioteka, Harmonogram | 3 |
| M5 | Encje i automatyzacje w Home Assistant | 4 |

## 6. Ryzyka

| Ryzyko | Wpływ | Co robimy |
|---|---|---|
| Ekran sam przetwarza obraz (dithering nałożony na nasz dithering) | gorsza jakość | Eksperyment E5. Jeśli wzory 1 px nie przetrwają, przechodzimy na strategię `compensate` (wstępna korekta, a dithering zostaje po stronie ekranu). |
| Na baterii ekran nie słucha sieci (potwierdzone w E8: WoL nie budzi) | brak zmian na żądanie | [WAKE.md](WAKE.md): budzik ekranu `0x25` i serwer czekający na pobudkę, przycisk, Wi-Fi 2,4 GHz dla WoL, playlista w manifeście (E6). Test E13. |
| Protokół MDC i manifest są nieoficjalne; aktualizacja firmware może je zmienić | utrata sterowania | Automatyczne aktualizacje wyłączone; aktualizacja ręczna po sprawdzeniu; serwer zapisuje wersję firmware. |
| Publiczne API albumów iCloud jest nieudokumentowane | sync przestaje działać | Izolowany moduł i testy na nagranych odpowiedziach. W zapasie: wysyłanie z aplikacji iOS (PhotoKit). |
| Wydajność na ARM (HA Green) | wolne renderowanie | numba z cache JIT, renderowanie z wyprzedzeniem, cache wyników. Alternatywnie kontener na Synology (x86). |
| API polskich instytucji (Polona, muzea narodowe) | brak API lub niejasne licencje | Weryfikacja na początku Etapu 2; ewentualnie ręcznie kuratorowane kolekcje z plików. |
| Licencje obrazów | problemy prawne | Domena publiczna (także według prawa UE: 70 lat po śmierci twórcy), CC0, a przy „Użytku prywatnym” licencje CC; pole licencji w bazie. WikiArt wyłącznie do testów, za przełącznikiem. |

## 7. Pytania otwarte

Wszystkie pytania z 2026-10-23 mają odpowiedzi (sekcja 1 i [DECISIONS.md](DECISIONS.md)). Do rozstrzygnięcia później:

1. Gdzie ostatecznie działa serwer: HA Green (add-on) czy Synology (kontener)? Decyzja po Etapie 1, gdy znamy czas renderowania na ARM.
2. Strategia obrazu (`dither` / `compensate`) i polityka zasilania: po eksperymentach E5–E8.

## 8. Do zrobienia po Twojej stronie (start)

1. **Ekran**: w aplikacji Samsung E-Paper podłącz ekran do Wi-Fi. Zanotuj **IP**, **MAC** i **PIN** (PIN pojawia się na ekranie podczas parowania). W routerze przypisz ekranowi stały adres IP. **Wyłącz automatyczne aktualizacje firmware** (jeśli aplikacja na to pozwala) i zanotuj obecną wersję.
2. **Mac**: zainstaluj `uv` (`brew install uv`), sklonuj repozytorium, uruchom `cd server && uv sync`, skopiuj `.env.example` do `.env` i uzupełnij dane ekranu.
3. Wykonaj eksperymenty **E1–E5** z [EXPERIMENTS.md](EXPERIMENTS.md). Zdjęcia ekranu wrzuć do `docs/experiments/` (lub prześlij mi).
4. Załóż konto **Apple Developer Program** (weryfikacja trwa do 48 h).
5. `brew install xcodegen`, następnie `cd ios && xcodegen generate` i otwórz `Frame.xcodeproj`.
6. W albumie iCloud włącz **„Witryna publiczna”** i zachowaj link (przyda się w Etapie 2).
7. Jeśli jeszcze go nie masz: **Tailscale** na iPhonie i na serwerze (HA Green: add-on Tailscale; Synology: pakiet Tailscale) — dostęp do ramki spoza domu.
