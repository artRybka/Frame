# Changelog

## 1.104.9

- Dzieło wysłane na ramkę z aplikacji nie wraca już z harmonogramem
  tego samego dnia. Dotąd czekało dalej w kolejce i mogło pojawić się
  znowu po kilku godzinach, mimo ustawienia „bez powtórek przez 14 dni”.
  Teraz idzie na koniec kolejki.
- Samousypianie po 3 minutach ramka odrzuca za każdym razem, więc
  zostaje 5 minut (sprawdzone trzy razy z rzędu).

## 1.104.8

- Ramka obudzona na zmianę obrazu dostaje nowy obraz od razu, a nie
  dopiero o równej godzinie. Wcześniej, budząc się ok. 1,5 minuty przed
  czasem, najpierw rysowała jeszcze raz stary obraz, a dopiero potem nowy.
  Teraz zmiana to jedno odświeżenie mniej i ok. minuty krócej z Wi-Fi.
- Aplikacja ramki próbuje jeszcze raz ustawić samousypianie po 3 minutach
  (dwa razy przed każdym snem). Jeśli ramka znów odmówi, zostaje 5 minut.

## 1.104.7

- Daty dzieł starożytnych z Luwru też są cyframi: „Ie s. ap. J.-C.” to
  teraz „1–100 n.e.”, a „Ier s. av. J.-C.” to „100–1 p.n.e.”.
- Dzieła z Luwru bez znanego autora mają w miejscu autora „Anonim”, a nie
  „Luwr”. Gdy Luwr podaje autora, a Wikidane go nie znają, pokazujemy
  nazwisko z Luwru także wtedy, gdy autor nie ma wpisu w Wikidanych.
  Nazwa szkoły, np. „Allemagne Rhin”, nie udaje autora.
- Tytuły z Luwru zaczynają się wielką literą („Peinture murale”).
- Dzieła już zapisane w bibliotece poprawiają się same. Spis Luwru
  pobiera się raz jeszcze w tle (ok. godziny).

## 1.104.6

- Grupy w Szukaj wracają sekundę po puszczeniu palca (dotąd pół
  sekundy), także gdy lista jeszcze się przewija.
- Szybko przewijana lista nie trzyma już grup schowanych dłużej. Grupy
  chowają się tylko wtedy, gdy palec przesuwa wyniki. Tak samo
  w edytorze playlist.

## 1.104.5

- Serwer znowu nie usypia pustego sprawdzenia przez MDC. W nocy 6 listopada
  o 2:00 obraz zatrzymał się w połowie odświeżania. Kamera pokazała, że
  ramka po każdej pobudce sama dwa razy odświeża ekran (ekran ładowania
  Samsunga, potem znowu obraz), a uśpienie ok. 35 s po budziku przerywa to
  drugie odświeżenie. Puste sprawdzenie znowu trwa ok. 5 minut.
- Grupy w Szukaj chowają się też przy przesuwaniu wyników w górę, nie
  tylko w dół.
- Po puszczeniu palca grupy wracają po pół sekundy, a nie od razu.
- Kiedy wyniki po mocnym pociągnięciu pędzą bardzo szybko, grupy zostają
  schowane i wracają dopiero, gdy lista zwolni albo stanie. Tak samo
  w edytorze playlist.
- Karta „Ukryte” na końcu Playlist pokazuje ukryte dzieła i ich liczbę od
  razu po otwarciu aplikacji, a nie „brak”. Dotąd odświeżała się dopiero po
  wejściu w nią i powrocie. Przy następnym uruchomieniu okładka jest gotowa
  od razu, zanim serwer odpowie.

## 1.104.3

- Pierścień wybranego „Żywe” w karcie Tonacja nie jest już ucięty w rogach.
- Środkowe kropki Tonacji stoją tam, gdzie kółka Kolorystyki, więc przy
  przełączaniu kart nie skaczą: Neutralne tam, gdzie Pomarańcz,
  Umiarkowane na Turkusie, Średnie na Szarościach.
- Nowa karta „Teraz prezentowane” na górze Playlist: niski pas na całą
  szerokość. Z lewej cztery dzieła okładki jako kwadrat 2×2 od krawędzi
  karty, z prawej napis „Teraz prezentowane”, nazwa playlisty, liczba dzieł
  i strzałka. Długa nazwa dostaje trochę mniejsze litery, a karta zostaje
  tej samej wysokości.
- Dzieła na okładkach playlist, Propozycji i kart propozycji w Odkrywaj są
  lekko przybliżone, więc ramki i marginesy ze skanów muzeów nie wchodzą
  w małe kwadraty.

## 1.104.2

- Grupy w Szukaj (Technika, Epoka, Styl, Kolor, Temat, Muzeum) wracają
  w chwili, gdy palec puszcza ekran, a wyniki jeszcze suną siłą rozpędu.
  Dotąd czekały, aż przewijanie całkiem stanie. Chowają się jak dotąd przy
  przesuwaniu wyników palcem w dół. Tak samo w edytorze playlist.
- Nowa karta Bateria (po dotknięciu kafelka). Na górze ile dni zostało
  i do kiedy mniej więcej starczy, z rozsądnym zakresem. Pod spodem wykres
  odczytów z ostatniego tygodnia na baterii z przewidywanym spadkiem do
  zera.
- „Dzień ramki” to jedna lista: puste kontrole, zmiany obrazu, obrazy
  wysłane z aplikacji, czuwanie i sen, przy każdej ile razy na dobę, ile
  kosztuje raz i ile razem, najdroższe na górze, z dopiskiem „zmierzone”
  albo „założenie”.
- „Trafność”: ostatnia doba na baterii, ile ramka naprawdę zużyła, a ile
  wynikało z wyliczeń.
- Bateria liczy pustą kontrolę tak długo, jak naprawdę trwa: gdy serwer
  usypia ją przez MDC, to ok. minuty (mediana z ostatnich kontroli), a nie
  5,5 minuty Wi-Fi. Gdy przestaje usypiać albo nie usypiał od dwóch dni,
  wraca do czasu samousypiania ramki.
- Dzieła z Luwru nie pokazują już adresu „wikidata.org/.well-known/genid/…”
  zamiast autora. Gdy Wikidane nie znają autora, bierzemy nazwisko z Luwru
  („Hals, Frans” → „Frans Hals”). Nazwa szkoły, np. „France”, nie
  udaje autora.
- Daty dzieł z Luwru są cyframi, np. „1450–1499” zamiast „2e moitié du XVe
  siècle”, więc działa z nimi wyszukiwanie po latach. Dzieła już zapisane
  w bibliotece poprawiają się same po aktualizacji. Spis obrazów Luwru
  pobiera się raz jeszcze w tle (ok. godziny).

## 1.104.1

- Ramka nie przyjmuje samousypiania po 3 minutach (odrzuca też 2), więc
  aplikacja od razu ustawia 5 minut, najkrótszy czas, jaki ta ramka bierze.
  Szacunek pod harmonogramem liczy puste sprawdzenie jako ok. 5,5 minuty
  Wi-Fi.
- Codzienne odświeżanie ekranu Samsunga ramka robi teraz przy pobudce ze
  zmianą obrazu, a nie przy pierwszym sprawdzeniu po niej. Puste
  sprawdzenie nie odświeża już ekranu.
- Serwer znowu usypia puste sprawdzenie przez MDC zaraz po pobudce, zamiast
  czekać 5 minut z Wi-Fi. Żółty ekran 5 listopada o 21:00 wypadł właśnie w
  czasie przeniesionego na takie sprawdzenie odświeżania. Teraz serwer usypia
  tylko sprawdzenie, o którym ramka powiedziała przed snem, że nie ma na nim
  odświeżania; po starej aplikacji ramki zostawia je w spokoju.

## 1.104.0

- Dzieła z Art Institute of Chicago przychodzą w większym rozmiarze, takim
  jak z przycisku „Pobierz” na stronie muzeum (do 3000 px zamiast 1686 px).
  Najwięcej zyskują detale w studium dzieła, ale ramka też dostaje
  ostrzejszy obraz. Gdyby muzeum odmówiło większego rozmiaru, serwer bierze
  jak dotąd 1686 px.
- Zdjęcia, które serwer już ma, zostają w starym rozmiarze, ale „Szukaj
  lepszej kopii” w menu „…” karty dzieła pokazuje dla nich „Większe zdjęcie
  muzeum” wśród lepszych kopii. Można je porównać jak każdą kopię
  i pobrać przyciskiem „Pobierz większe zdjęcie”.
- Nowe źródło dzieł: Luwr, tylko z „Użytkiem prywatnym”. Uzupełnia
  Commons: bierze ok. 7500 obrazów z Luwru, których na Commons nie ma albo
  są tam mniejsze niż zdjęcia Luwru (1500 px), np. szkice olejne
  Valenciennes’a, Oudry, Prud’hon, Hubert Robert. Słynne obrazy w lepszej
  jakości zostają z Commons.
- Pierwsze spisanie obrazów trwa ok. godziny w tle, potem serwer sprawdza
  nowe raz w miesiącu w nocy. Pomija zdjęcia innych instytucji (warunki
  Luwru wymagają na nie ich zgody).
- Karta dzieła z Luwru pokazuje prawdziwy rozmiar z wymiarów Luwru.

## 1.103.1

- Po powrocie do aplikacji z tła Teraz od razu pokazuje obraz, który
  jest na ramce. Dotąd po zmianie z harmonogramu, np. w trybie
  Oszczędnym, przez półtorej minuty (czasem dłużej) widać było poprzednie
  dzieło.
- Kafelek Bateria pokazuje realny czas pracy dla każdego harmonogramu, od
  obecnego poziomu baterii. Wcześniej serwer brał każdą pobudkę za ok. pół
  godziny przytomności, bo liczył też godziny na zasilaczu, i np. przy
  harmonogramie testowym wychodziło 1,3 dnia zamiast ok. 4. Teraz czas
  pobudki to mediana z ostatnich pobudek na baterii, pusta kontrola liczy
  się tak długo, jak ustawiła ją aplikacja ramki (3 albo 5 min), a obrazy
  wysłane z aplikacji jako średnia z ostatnich dwóch tygodni. Założenia
  startowe pochodzą z testów tej ramki.
- Ramka nie przyjęła samousypiania po 2 minutach (Samsung pozwala tylko na
  3, 5, 10, 20, 30 albo 60 minut) i przy pustej kontroli dalej czekała 5
  minut. Teraz zasypia po 3 minutach, najkrótszym możliwym czasie, co
  oszczędza ok. 2 minuty Wi-Fi na każdej kontroli bez nowego obrazu.
  Szacunek pobudek w Ramce liczy kontrolę jako ok. 3,5 minuty.

## 1.103.0

- Karta Tonacja w Szukaj → Kolor nie ma już grupy „pomiędzy”. Każde
  dzieło jest w każdej grupie dokładnie w jednym kółku, więc kółka razem
  dają całą bibliotekę. Temperatura, Nasycenie i Jasność mają trzecie,
  środkowe kółko: Ciepłe · Neutralne · Chłodne, Żywe · Umiarkowane ·
  Stonowane, Ciemne · Średnie · Jasne. Barwność zostaje na dwa: Kolorowe
  to wszystko poza Mono. Grupy stoją po dwie w rzędzie.
- W grupie można wybrać dwa sąsiednie kółka, np. Ciemne i Średnie: obejmuje
  je jeden pierścień, a nad wynikami stoi żeton „Ciemne albo średnie”.
- Kropki Nasycenia wyraźniej się różnią: Żywe w czystych barwach,
  Stonowane prawie szare. Neutralne to płaska szarość.
- „Żywe” znów coś znajduje: liczy się najbarwniejsza część obrazu, a nie
  średnia z całego (dotąd prawie nigdy nie wypadało).
- Po aktualizacji serwer raz przelicza kolory całej biblioteki. Do końca
  przeliczenia Tonacja działa po staremu.
- Harmonogram: nagłówek godzin to „Godzina zmiany obrazu” (przy kilku
  „Godziny zmiany obrazu”) w obu trybach, zamiast „Pobudki i zmiany”
  w Oszczędnym i „Godzina zmiany” w Online.
- Kontrola w trybie Oszczędnym, która nie przynosi nic nowego, kosztuje
  mniej baterii. Ramka po takiej pobudce zasypia sama po 2 minutach
  bezczynności zamiast po 5. Gdyby ramka nie przyjęła 2 minut, zostaje
  przy 5. Przy kontroli z nowym obrazem aplikacja wstaje wcześniej, więc
  to jej nie przeszkadza.
- Podsumowanie pod paskiem pobudek (Ramka → Harmonogram) liczy czas Wi-Fi
  według pomiarów: ok. 3,5 min na zmianę i 2,5 min na kontrolę.

## 1.102.6

- Zmiana harmonogramu w czasie snu ramki w trybie Oszczędnym (dodana albo
  przesunięta zmiana, inne godziny sprawdzeń) dociera do ramki przy
  najbliższej kontroli. Budziki ustawia sobie sama aplikacja ramki przed
  zaśnięciem, więc serwer uruchamia ją wtedy, a ona ustawia budziki według
  nowego planu. Wcześniej, np. zmiana dodana na 22:10, czekała do
  następnej zmiany z dawnego planu.

## 1.102.5

- Serwer znowu nie usypia ramki przez MDC przy pustej kontroli w trybie
  Oszczędnym (wycofane z 1.102.3). Kamera pokazała, że po takim uśpieniu
  obraz znikał, a ekran zostawał jednolicie żółty. Ramka po pustej
  kontroli sama zasypia po ok. 5 minutach, jak wcześniej.

## 1.102.4

- Gdy po pustej kontroli, przy której serwer uśpił ramkę, wyślesz nowy
  obraz, aplikacja nie pisze już „Ramka nie obudziła się o …”. Ramka
  wstała o czasie, a obraz czeka na najbliższą pobudkę, jak w trybie
  Oszczędnym. Serwer nie próbuje też co 5 minut uruchamiać śpiącej ramki.

## 1.102.3

- Kontrola w trybie Oszczędnym, która nie przynosi nic nowego, kosztuje mniej
  baterii. Ramka stała wtedy ok. 5 minut z włączonym Wi-Fi, zanim sama
  zasnęła; teraz serwer usypia ją przez MDC kilkanaście sekund po tym, jak
  się zgłosi. Obraz na ekranie się nie zmienia. Na zasilaczu ramka zostaje
  obudzona jak dotąd. Gdyby ramka po takim uśpieniu nie obudziła się na
  następną kontrolę, serwer to zauważy i wróci do starego sposobu.

## 1.102.2

- Zamówiony zrzut ekranu ramki pokazuje obraz, a nie ekran startowy
  Samsunga „Custom App”. Aplikacja robiła go za wcześnie: przy pobudce,
  która przynosi nowy obraz, zanim go narysowała, a po starcie, zanim
  ramka pokazała stronę. Teraz robi go minutę po narysowaniu obrazu tej
  pobudki i nie wcześniej niż 100 s po starcie; ramka czuwa na baterii do
  4 minut dłużej (było 3).

## 1.102.1

- Teraz po zmianie orientacji ramki (np. z poziomej na pionową) znowu
  pokazuje duży podgląd ramki. Dopóki ramka ma na ekranie obraz
  przygotowany dla starej orientacji (w trybie Oszczędnym nawet do
  najbliższej pobudki), podgląd nie kurczył się już do malutkiej
  miniatury: ramka ma kształt nowej orientacji, a stary obraz stoi w niej
  z białym marginesem.

## 1.102.0

- Zrzut ekranu ramki można zamówić także wtedy, gdy ramka śpi na baterii
  (Konfiguracja → Aplikacja ramki → „Pokaż ekran ramki” → „Zamów zrzut przy
  następnej pobudce”). Ramka robi go przy najbliższej pobudce i czuwa wtedy
  do 3 minut dłużej. Zamówienie przetrwa restart serwera.

## 1.101.4

- Mono w Szukaj → Kolor → Tonacja to naprawdę skala szarości, sepia albo
  duotone. Serwer patrzy na kolory tak, jak oko widzi je na papierze:
  wyblakłe japońskie drzeworyty, portrety z różową szarfą czy czerwoną
  różą i inne stonowane, ale wielobarwne dzieła nie są już Mono. Po
  aktualizacji serwer raz przelicza kolory całej biblioteki (w logu
  „rescore: … pictures analysed again”).
- Wyszukiwanie, któremu nic nie odpowiada, nie kręci się bez końca. Gdy
  biblioteka nic nie ma, a pierwsza runda muzeów też nic nie przyniosła,
  od razu pokazuje się „Brak dzieł spełniających kryteria” z pastylkami.
  Muzea przestają też dociągać kolejne strony po trzech pustych rundach z
  rzędu.
- Grupy w Szukaj znowu chowają się przy przewijaniu wyników, ale wracają
  od razu, gdy wyniki się zatrzymają (wcześniej po 1,2 s). Tak samo
  w edytorze playlist.

## 1.101.3

- Menu po przytrzymaniu kafelka Studium dnia i karty Artysty tygodnia ma
  sam guzik „Wylosuj inne” / „Wylosuj innego”, bez dopisku nad nim.
  Losowanie Studium dnia nie pyta już o koszt.

## 1.101.2

- Grupy w Szukaj (Technika, Epoka, Styl, Kolor, Temat, Muzeum) są zawsze
  widoczne, także przy przewijaniu wyników. Tak samo w edytorze playlist.

## 1.101.1

- Obraz wysłany do ramki śpiącej w trybie oszczędnym nie jest już
  „błędem wysyłki”. Zamiast czerwonej karty „Nie udało się wysłać obrazu”
  pasek wysyłki kończy się zegarem i napisem „Pojawi się dziś o 10:00”,
  a guzik „Pokaż na ramce” na karcie dzieła i w Studium dnia pokazuje
  „Pojawi się o 10:00”, dopóki ramka nie wyświetli obrazu. Serwer nie
  pokazuje kroku „Łączę się z ramką”, gdy ramka śpi bez Wi-Fi.
- Pod czekającym obrazem w Teraz są dwie linie: kiedy się pojawi i „Aby
  pokazać obraz wcześniej, naciśnij przycisk na ramce.”. Znikają
  powtórzona „Pobudka ramki” i „Następna zmiana”. Karta ramki śpiącej w
  Oszczędnym nazywa się „Ramka w trybie oszczędnym”.
- „Prezentuj” playlistę przy śpiącej ramce mówi, kiedy pojawi się pierwszy
  obraz. Ekran blokady: „Pojawi się dziś o 10:00”.
- W całej aplikacji „przycisk na ramce” zamiast „guzik” i „przycisk z
  tyłu ramki”, „pobudka” zamiast „budzik”.
- Komunikaty serwera przy wysyłce obrazu są po polsku, także o braku
  certyfikatów Samsunga i o ramce bez ustawionego adresu.

## 1.101.0

- Nowy panel Szukaj → Kolor z dwiema kartami. W Kolorystyce wybierasz do
  trzech kolorów, a każde kolejne stuknięcie w próbkę mówi, ile go ma być:
  akcent, obecny, wyraźny albo główny (pierścień wokół próbki rośnie).
  Dwa kolory jako „główny” to obrazy malowane głównie nimi
  razem. W Tonacji są cztery przełączniki: Temperatura (ciepłe albo
  chłodne), Nasycenie (żywe albo stonowane), Barwność (kolorowe albo mono)
  i Jasność (ciemne albo jasne). Wszystko, co wybrane, musi
  pasować naraz. Gdy nic się nie znajdzie,
  Szukaj pisze „Brak dzieł spełniających kryteria” i pokazuje pastylki
  wyborów, bez których coś się znajdzie (z liczbą dzieł); stuknięcie
  usuwa taki wybór. Komunikat pojawia się dopiero po zakończonym
  wyszukiwaniu.
- „Mono” (wcześniej „Monochromia”) znajduje naprawdę obrazy jednym tonem:
  czarno-białe, sepię, cyjanotypie i sangwinę, a nie ciemne obrazy olejne.
  Serwer raz po aktualizacji przelicza kolory całej biblioteki.
- Gdy przy kontroli w trybie Oszczędnym czeka nowy obraz, serwer uruchamia
  aplikację ramki od razu, gdy ramka zgłosi się po pobudce, a nie minutę
  później. Tak samo po włączeniu ramki guzikiem.
- Przy zmianie obrazu serwer nie wtrąca się: aplikacja wstaje wtedy sama
  ze swojego budzika, a serwer uruchamia ją tylko, gdy milczy.
- Konfiguracja → Aplikacja ramki: gdy na serwerze czeka nowa wersja
  aplikacji, a ramka ma starszą, pojawia się prośba o wyłączenie
  i włączenie ramki guzikiem. Tylko wtedy ramka ją instaluje.

## 1.100.8

- „Wylosuj inne” Studium dnia i „Wylosuj innego” Artystę tygodnia
  przeniesione z Konfiguracji do menu po przytrzymaniu kafelka Studium
  dnia i karty Artysty tygodnia w Odkrywaj. Menu ma tylko właściciel.

## 1.100.7

- Obrazy z Courtauld Gallery nie są już białe. Część skanów galerii jest
  zapisana w CMYK i jej serwer obrazów oddaje je jako białe pola. Kafelki
  biorą teraz obraz ze strony dzieła, a oryginał serwer pobiera jako PNG i
  sam przelicza kolory. Białe obrazy zapisane wcześniej pobierają się na
  nowo.
- Oryginały mniejszych obrazów z Courtauld pobierają się w pełnym
  rozmiarze, a nie jako rozmyta miniatura.

## 1.100.6

- Ekran ramki nie robi się biały w nocy na baterii. Aplikacja ramki
  uruchamiała się sama także przy kontrolach bez nowego obrazu. Jej świeża
  strona była biała, a obrazu, który pamiętała, nie rysowała drugi raz.
  Teraz przy każdym starcie aplikacji serwer każe narysować obraz od nowa.
- Budzik, który sam uruchamia aplikację, jest ustawiany tylko na pobudkę,
  przy której aplikacja i tak musi działać (zmiana obrazu). Przy zwykłej
  kontroli ramka znowu zasypia sama, bez odświeżania ekranu.

## 1.100.5

- Ramka nie czeka na odpowiedź serwera, gdy ten zapisuje coś dłużej w
  tle. Po wydaniu 1.100.4 zdarzyła się jeszcze jedna 6-sekundowa przerwa
  zaraz po aktualizacji.
- Zaraz po restarcie serwer nie uruchamia aplikacji ramki na nowo, tylko
  czeka półtorej minuty, aż sama się odezwie.

## 1.100.4

- Serwer odpowiada od razu po starcie. Dotąd przez ok. 1,5 minuty po
  uruchomieniu kontenera stał: liczył rozmiar miniatur katalogu na dysku
  NAS i sprawdzał albumy iCloud w głównej pętli, więc ramka i aplikacja
  czekały, a serwer uznawał, że zegar ramki się spóźnia. Ta praca idzie
  teraz w tle, a liczenie miniatur jest kilka razy szybsze. Gdyby serwer
  znów stanął na dłużej niż 5 s, w logu pojawi się, gdzie.

## 1.100.3

- Próba samodzielnego startu aplikacji ramki po głębokim śnie. Launcher
  Samsunga sam jej nie uruchamia, więc aplikacja przed snem bez Wi-Fi
  zostawia budzik systemu Tizen, który ma ją uruchomić. Ramka dostaje przy
  tym nową wersję aplikacji (zainstaluje się sama). Do sprawdzenia w nocy
  na baterii.

## 1.100.2

- Po wyłączeniu i włączeniu ramki przyciskiem (i po każdym innym zimnym
  starcie) ekran nie zostaje już biały. Ekran startu Samsunga zamazywał
  obraz, a serwer nie wiedział, który obraz aplikacja pamięta, więc nie
  kazał jej narysować go ponownie.

## 1.100.1

- Ramka nie zasypia, gdy restartuje się, żeby zainstalować nową wersję
  aplikacji. Wcześniej w zatorze zapytań po aktualizacji serwera zasnęła
  na zasilaczu bez budzika i obudził ją dopiero guzik. Gdy restart do
  instalacji nie dojdzie do skutku, serwer prosi o niego ponownie po
  10 minutach, najwyżej trzy razy.
- W trybie oszczędnym ramka na zasilaczu ma zawsze ustawiony budzik na
  najbliższą zmianę. Po odpięciu Samsung usypia ją od razu, zanim zdąży
  zapytać serwer, więc bez tego budziła się dopiero po naciśnięciu przycisku.

## 1.100.0

- Nowe źródło dzieł: Courtauld Gallery z Londynu, ok. 580 obrazów w
  pełnej rozdzielczości, m.in. „Bar w Folies-Bergère” Maneta, „Gracze w
  karty” Cézanne'a i „Autoportret z zabandażowanym uchem” Van Gogha.
  Tylko z „Użytkiem prywatnym” (licencja CC BY-NC). Courtauld nie ma API,
  więc serwer po włączeniu raz powoli spisuje ich obrazy (poniżej
  godziny) i raz w miesiącu sprawdza, czy doszły nowe.

## 1.99.1

- Wellcome Collection pomija ilustracje medyczne: akwarele chorób skóry,
  anatomię, rany, sekcje i narzędzia chirurgiczne. Sceny z lekarzami
  i portrety zostają.

## 1.99.0

- Zestawy w Odkrywaj (np. „Polskie międzywojnie”) są wymieszane: obok
  siebie nie stoją dwa dzieła jednego autora ani jednego muzeum, o ile
  jest czym je przedzielić, a rodzaje (obrazy, grafiki, rysunki) też się
  przeplatają. U każdego autora dzieła idą od najwcześniejszego, więc
  całość lekko płynie w czasie. Pierwsza porcja zestawu przynosi od razu
  kilku różnych autorów, a pokazane dzieła nie przeskakują.
- Wiersze „Motyw dnia” i „Dawno ich nie było” są wymieszane tak samo.
- Konfiguracja → Aplikacja ramki → „Pokaż ekran ramki”: zrzut ekranu ramki
  (pomniejszony, tak jak aplikacja go narysowała). Tylko gdy ramka jest na
  zasilaczu; ramka robi go co najmniej minutę po zmianie obrazu.
- Aplikacja na ramce sama ustawia jej zegar, gdy ten się rozjedzie (stał na
  1 stycznia 2024). Ramka raz zainstaluje nową wersję aplikacji (ekran
  instalatora). Budziki przeliczane na zegar ramki zostają jako
  zabezpieczenie.
- Nowe źródło dzieł: Wellcome Collection z Londynu, bez klucza. Daje
  pełnowymiarowe obrazy z domeny publicznej: indyjskie gwasze, japońskie
  drzeworyty (Hokusai, Kuniyoshi, Hiroshige, Utamaro), ryciny Dürera,
  Rembrandta i Goi oraz angielską satyrę Hogartha, Gillraya i
  Rowlandsona. Z „Użytkiem prywatnym” także dzieła na licencjach CC BY i
  CC BY-NC. Pojawia się w Szukaj, przy artystach, motywach i playlistach,
  ale nie w losowych obrazach, bo wiele prac dotyczy medycyny.

## 1.98.0

- Zdjęcia z albumów iCloud nie są już „Bez tytułu / Album iCloud”. Claude,
  który i tak ogląda każde zdjęcie przy słowach kluczowych, nadaje mu
  krótki polski tytuł, np. „Montaż drewnianej ścianki”, a pod nim widać
  dzień i miejsce: „29 października 2026 · Kraków”. Podpis dodany
  w Zdjęciach zawsze wygrywa, także dopisany później. Bez Claude tytułem
  jest dzień zrobienia zdjęcia.
- Nazwę miejscowości serwer bierze ze współrzędnych zdjęcia
  (OpenStreetMap, współrzędne zaokrąglone do ok. 1 km), po każdej
  synchronizacji albumu i w nocy. Ten sam tytuł i miejsce pokazują
  kafelki, karta zdjęcia, Teraz i ramka w trybie Opis. Zdjęcia, które
  już są w bibliotece, dostają tytuły w tle.

## 1.97.2

- Po wybraniu lepszej kopii dzieła (Kopie dzieła → „Użyj tej kopii”) jego
  miniatura w listach, siatkach i na Teraz od razu pokazuje nowe zdjęcie,
  w jego tonacji i kolorach, z ramą, jeśli kopia ją obejmuje. Wcześniej
  zostawała stara. Tak samo po „Przywróć zdjęcie muzeum” i po ostrzejszej
  kopii znalezionej przez serwer. Kropki kolorów dzieła i tagi kolorów
  liczą się na nowo z nowego zdjęcia.
- Dzieła, którym kopię wybrano wcześniej, raz po aktualizacji serwera
  dostają miniatury z kopii. Inny telefon domownika pobiera nową miniaturę,
  gdy pierwszy raz pokaże to dzieło.

## 1.97.1

- Teraz: nad tytułem dzieła nazwa muzeum, w którym wisi, zamiast „Dzieło”;
  muzeum, tytuł i autor bliżej siebie, narodowość i lata życia tuż pod
  nazwiskiem, bez linijki z techniką. Rok powstania na małym szarym
  znaczku na końcu tytułu, w Teraz i na karcie dzieła.
- Szukaj → Kolor ma zakładki Kolorystyka, Dominuje i Akcent.
  Kolorystyka to kolor na co najmniej 15% obrazu, razem z nastrojami.
  Dominuje (wcześniej „Wyłącznie”) to obrazy malowane głównie wybranymi
  kolorami: dają one 80% barw obrazu, a biel, szarość i czerń się nie
  liczą.

## 1.97.0

- Odkrywaj → Kolor i nastrój pokazuje tylko obrazy, rysunki i akwarele,
  bez plakatów, grafiki i zdjęć. Playlisty zrobione z tych kart (także
  „W odcieniach błękitu” i „Ciepłe barwy”) też trzymają się teraz tych
  technik.
- Karty Kolor i nastrój zmieniają się co poniedziałek: cztery z 22
  kolorystyk, tonacji i akcentów, każda z własną nazwą i opisem, np. „Sam
  błękit”, „Barwy ziemi”, „Czerwień w zieleni”, „Światło w mroku”. Karta
  pojawia się tylko wtedy, gdy w katalogu jest co najmniej 12 pasujących
  dzieł, i nie wraca przez cztery tygodnie.
- Szukaj → Kolor ma trzecią zakładkę „Wyłącznie”: obrazy malowane tylko
  wybranymi kolorami (biel, szarość i czerń się nie liczą), np. wyłącznie
  błękitem i turkusem. „Tylko akcent” nazywa się teraz „Akcent”. Serwer
  raz przelicza kolory całej biblioteki.

## 1.96.2

- Guziki studium na karcie dzieła („Przygotuj studium dzieła”, „Otwórz
  studium”, „Zamówione na później”) mają białe tło, w ciemnym trybie
  czarne, żeby wyróżniały się na stronie.
- Dzieła duńskiego SMK, których numer ma ukośnik (np. „KKS1984-23/366”),
  znowu mają miniatury, kartę, podgląd na ramce i dają się wysłać. Serwer
  nie rozpoznawał takiego adresu i odpowiadał „nie znaleziono”, więc
  kafelki zostawały puste ze strzałką odświeżenia.

## 1.96.1

- Przytrzymane guziki z obwódką („Przygotuj studium dzieła”, „Otwórz
  studium”) mają w uniesionym podglądzie tło strony, a nie prześwitujące
  przyciemnione tło za nimi.

## 1.96.0

- Studium dnia za pół ceny: serwer w nocy wybiera dzieło na jutro i zamawia
  jego studium w pakiecie Anthropic (Batch API), który kosztuje połowę i
  odpowiada zwykle w ciągu kilku godzin. Rano studium jest gotowe; gdy pakiet
  się spóźni, serwer dopytuje o resztę od razu i nie płaci drugi raz za to,
  co już przyszło. Jutrzejsze dzieło nie pojawia się wcześniej w „Studia
  dzieł”.
- Przytrzymanie „Przygotuj studium dzieła” na karcie dzieła daje menu:
  „Przygotuj na już” (jak dotąd, 1–3 minuty) i „Przygotuj na później” (za pół
  ceny, zwykle w ciągu kilku godzin). Gotowe studium przychodzi jako
  powiadomienie „Studium gotowe”. Zamówione na później można przytrzymać
  jeszcze raz i przygotować na już, bez ponownej opłaty za to, co pakiet już
  zrobił.
## 1.95.6

- Serwer pyta źródła dzieł tak, jak proszą ich zasady dla programów, żeby
  nie dostać blokady jak w AIC: do Wikimedia Commons, Wikidanych i Wikipedii
  razem jedno zapytanie naraz i najwyżej cztery na sekundę, do Art Institute
  of Chicago jedno naraz, a gdy serwis odpowie „za dużo zapytań” i powie, ile
  czekać, serwer czeka tyle, zamiast ponawiać po kilku sekundach.
- Klucze Europeany i Smithsonian idą w nagłówku zapytania, a nie w adresie,
  więc nie trafiają już do logu serwera.

## 1.95.5

- Obrazy z Art Institute of Chicago pobierane tak, jak prosi ich
  dokumentacja: tylko w dozwolonych szerokościach (miniatury 843 px,
  oryginały do 1686 px), jeden naraz i co sekundę. Serwer prosił dotąd
  o pełny rozmiar mniejszych grafik, a na takie pytanie muzeum odpowiadało
  blokadą, przez którą znikały miniatury. Adresy zapisanych dzieł AIC
  poprawiają się same.

## 1.95.4

- Pasek wysyłki na ekranie blokady dochodzi do końca także przy uśpionej
  aplikacji: serwer sam przesuwa go przez kolejne etapy, na koniec pokazuje
  zielone „Obraz jest na ramce” i po 15 sekundach pasek znika. Dotąd
  zatrzymywał się na „Ramka odświeża ekran” do otwarcia aplikacji.
- Potrzebny klucz APNs, jak przy powiadomieniach. Bez niego pasek działa
  jak dotąd.
- Mniej pustych kafelków ze strzałką odświeżenia w Odkrywaj i Szukaj. Gdy
  Art Institute of Chicago (albo inne muzeum za ścianą anty-botową)
  chwilowo odmawia serwerowi, lista pomija jego dzieła, których miniatury
  serwer jeszcze nie ma, a kafelek, który już jest, znika z siatki na
  kilka minut, zamiast pokazywać strzałkę.
- Serwer w czasie takiej przerwy raz na minutę sprawdza, czy muzeum już
  odpowiada, i wraca do niego od razu, bez czekania pełnych 15 minut.
  Do obrazów AIC pyta też spokojniej.
- Log serwera zachowuje koniec długich błędów, gdzie widać ich przyczynę.

## 1.95.3

- Po aktualizacji serwera ekran ramki nie zostaje biały także wtedy, gdy
  serwer uruchamia aplikację na ramce od nowa (z ekranem instalatora):
  aplikacja rysuje wtedy obraz jeszcze raz, choć pamięta go na ekranie.

## 1.95.2

- Pasek wysyłki na ekranie blokady sam znika: po „Obraz jest na ramce”
  po 15 sekundach, po błędzie po 5 minutach. Dotąd zostawał długo.
- Karta studium po „Gotowe” znika po 2 minutach (była godzina), po błędzie
  po 5 minutach. Powiadomienie „Studium gotowe” zostaje jak dotąd.
- Po otwarciu aplikacji znikają od razu zakończone karty, także te, które
  zostały po czasie albo po wcześniejszym uruchomieniu aplikacji.
- Live Activity na ekranie blokady i w Dynamic Island: pasek wysyłki na
  ramkę i studium dzieła są białe (na jasnym ekranie blokady czarne)
  zamiast czerwonych, a po sukcesie zielone.

## 1.95.1

- Budziki ramki znowu się ustawiają: zegar systemowy ramki stał na
  1 stycznia 2024 i ramka odrzucała każdy budzik ustawiony według
  prawdziwej godziny, więc na baterii sama by się nie obudziła. Aplikacja
  przelicza teraz godzinę budzika na zegar ramki. Ustawień ramki nie zmienia.
- Po aktualizacji serwera ekran ramki nie zostaje biały: aplikacja po
  przeładowaniu rysuje obraz jeszcze raz.
- Serwer nie ostrzega o rozjechanym zegarze ramki z powodu jednego
  spóźnionego zapytania.
- Guzik „następny” na ramce przełącza na następne dzieło, tak jak strzałka
  w aplikacji (gdy ramka nie śpi; na zasilaczu zawsze). Naciśnięcia w
  odstępie krótszym niż 15 s liczą się jako jedno.

## 1.95.0

- Pasek wysyłki na ekranie blokady i w wyspie pokazuje małą miniaturę
  dzieła, które jedzie na ramkę, ze znaczkiem stanu na rogu (ptaszek,
  krzyżyk, księżyc). Tak samo karta studium, które się pisze.
- Powiadomienie „Błąd wysyłki” też ma miniaturę dzieła.
- Gdy miniatura nie zdąży się pobrać, karta wygląda jak dotąd.
- Druga sonda ramki (na zasilaczu, raz): sprawdza, według którego zegara
  ramka liczy budziki (jej zegar systemowy stoi na 1 stycznia 2024, a
  zapasowe budziki na zasilaczu się nie ustawiają), odczytuje stan zasilania
  z modułu `remotepower` i zapisuje pełną listę funkcji ekranu w logu.
- Zrzut ekranu na żądanie próbuje odczytać plik inną drogą, bo ramka nie
  pozwalała aplikacji go otworzyć.
- „Prezentuj na ramce” działa dla Ulubionych, z przytrzymania okładki
  i z przycisku na stronie playlisty. Dotąd serwer odpowiadał
  „Ulubione zostają zawsze”, jakby chodziło o usuwanie.
- Gdy muzeum podaje tylko jednozdaniową adnotację (tytuł, autor,
  technika, data, np. „obraz olejny Paula Cézanne'a, 1888–1890; skan
  w wysokiej rozdzielczości”), „O dziele” nie pokazuje już jej
  tłumaczenia, tylko notkę napisaną z obrazu i danych, jak przy dziele
  bez opisu. Opis musi mieć co najmniej 120 znaków i 10 słów, które
  mówią coś więcej niż tytuł, autor i data. Takie dzieła dostają nową
  notkę same, w tle.
- Miniatury w Teraz („Następne” i „Ostatnio na ramce”) są kadrowane
  wokół twarzy albo tego, co przyciąga wzrok, tak jak kafelki Odkrywaj,
  zamiast przez środek. Portret nie traci już głowy.

## 1.94.1

- Nowe studia i Studium dnia nie sprawdzają już osobno kadrów detali,
  bo zwykle trafiają. Każde studium kosztuje przez to około 7 centów
  mniej. Kadr, który chybił, nadal poprawisz przytrzymaniem nagłówka
  „Detale” i „Popraw detale”.

## 1.94.0

- Powiadomienia o dziele pokazują jego miniaturę: zmiana dzieła na
  ramce, Studium dnia, Studium gotowe, Artysta tygodnia i Rocznica
  urodzin (przy dwóch ostatnich jedno z ulubionych dzieł artysty).
  W domu obrazek przychodzi z serwera, poza domem z muzeum; zdjęcie
  z rolki poza domem przychodzi bez miniatury. Gdy obrazek nie zdąży
  się pobrać, powiadomienie przychodzi jak dotąd, bez niego.
- „Studium gotowe” przy karcie na ekranie blokady jest osobnym
  powiadomieniem z miniaturą, a karta tylko się rozświetla.
- Po zapisaniu nowego kadru podgląd „Na Twojej ramce” w Studium dzieła
  (a także na karcie dzieła i przy przeglądaniu w Teraz) pokazuje nowy
  kadr, a nie stary sprzed zmiany. Aplikacja nie bierze już tego podglądu
  ze swojej pamięci, tylko prosi serwer o nowy.
- Kadr przy zamykaniu po „Zapisz kadr” chwilę czeka na podgląd z nowym
  kadrem, żeby ramka wróciła na miejsce już z nim.
- Wymaga nowej aplikacji z TestFlight i nowej wersji serwera.

## 1.93.0

- Analiza kompozycji kosztuje około jednej trzeciej tego, co dotąd.
  Opus patrzy na sam obraz, bez tekstów muzeum i Wikipedii, i wskazuje
  miejsca, na których opiera się kompozycja. Haiku sprawdza, czy każdy
  ślad trafia tam, gdzie mówi jego opis. Siatkę (połowy, trójpodział,
  złoty podział) serwer wybiera sam, mierząc linie w obrazie, a Haiku
  dopisuje o niej jedno zdanie. O tym, czy kompozycja jest spokojna czy
  pełna ruchu, i o śladach ruchu decyduje Sonnet.
- Dotychczasowe analizy zostają, jakie były. Nowe studia i „Wykonaj
  ponowną analizę” idą już nową drogą.
- Ramka na zasilaczu raz sprawdza, co jeszcze potrafi powiedzieć o sobie
  (zegar i jego strefa, pamięć, wolne miejsce, sieć, czujniki, ustawienia),
  i zapisuje to w logu serwera. Same odczyty, bez zmian w ustawieniach.
- Serwer wie, o ile zegar ramki rozjeżdża się z jego zegarem, i pisze o tym
  w logu przy różnicy ponad minutę: od zegara ramki zależą jej budziki.
- Gdy w Konfiguracji nie ma adresu MAC ramki, serwer bierze go od samej
  ramki i budzi ją nim przez sieć.
- Nowe powiadomienie „Nowy firmware ramki”, gdy Samsung zaktualizuje
  oprogramowanie ekranu (tylko właściciel).
- Na próbę: zrzut ekranu ramki na żądanie z serwera, naciśnięcia przycisku
  i zmiany baterii na żywo trafiają do logu.

## 1.92.1

- Studium dzieła: podpis pod obrazem to same litery, bez czarnego pasa
  (i kremowego w ciemnym trybie), jak etykieta w muzeum. Tytuł zostaje
  wielkimi literami jak na przyciskach, ale mniejszy i w kolorze tekstu,
  a pod nim szarym, cienkim pismem autor i data.
- Studium dzieła: w górnym pasku nie ma już napisu „Studium dzieła”,
  zostały same przyciski (wstecz, serce, „…”) nad stroną.
- Aktualizacja serwera nie usypia już ramki na ładowarce. Aplikacja na
  ramce, która przez chwilę nie dosięgnie serwera, na ładowarce czeka
  przytomna i pyta znowu po minucie, dwóch, najwyżej pięciu; na baterii
  zasypia jak dotąd.
- Ramka, która ucichła tuż przed restartem serwera, nie jest już
  pokazywana jako „Na baterii”, bo nikt jej nie odpiął. Serwer próbuje
  ją wtedy obudzić przez sieć.

## 1.92.0

- Studium dzieła: tytuł jest na karteczce tuż pod obrazem, na jego
  szerokość. Karteczka jest czarna z białym pismem (w ciemnym trybie
  kremowa), tytuł wielkimi literami jak na przyciskach, a pod nim
  cieńszym pismem imię i nazwisko autora oraz data powstania (po polsku,
  gdy dzieło ma polskie opisy). Długi tytuł z muzeum, pokazany po
  przytrzymaniu, jest pisany zwykłymi literami. Przytrzymanie autora
  otwiera Szukaj. Od karteczki do pierwszej sekcji jest trochę bliżej.
- „Rozmiar obrazu”: mężczyzna jest albo cały, od stóp, albo jako popiersie
  ucięte tuż pod marynarką, bez wersji pośrednich. Popiersie stoi na
  kresce przez całą szerokość ekranu, a jego wzrost, 180 cm, jest
  podpisany przy krótkiej kreseczce na wysokości czubka głowy.
- Studium dzieła, „Detale”: studium zapamiętuje, na której kopii zdjęcia
  Claude zaznaczał fragmenty. Gdy dzieło ma potem inną, ostrzejszą kopię,
  serwer dopasowuje do siebie obie kopie i wycina detale z tej lepszej,
  trafiając w to samo miejsce obrazu.
- Nowe studia: Claude sprawdza swoje detale na wyciętych fragmentach
  i poprawia ramkę, która nie pokazuje tego, o czym mówi (np. tło nad
  kapeluszem zamiast twarzy w „Automacie” Hoppera).
- Studia napisane wcześniej: właściciel przytrzymuje nagłówek „Detale”
  i wybiera „Popraw detale”. Claude sprawdza wtedy każdy detal na jego
  wycinku i poprawia ramki, które chybiają; aplikacja mówi na koniec,
  ile detali poprawiono.

## 1.91.0

- Oryginały dzieł z Ulubionych (każdego domownika) oraz z ręcznych
  i albumowych playlist są zawsze na serwerze. Serwer pobiera oryginał
  w tle zaraz po dodaniu serca albo dzieła do playlisty, a te, których
  brakuje (dodane wcześniej, muzeum nie odpowiadało), w nocy jako
  ostatnie zadanie: najwyżej 300 na noc, jedno po drugim z przerwą,
  muzeum, które odmawia albo każe zwolnić, zostaje na następną noc,
  a dzieło, którego oryginału muzeum nie daje, nie jest pytane przez
  30 dni. Pobiera tylko do 90% limitu „Oryginały dzieł”, żeby porządki
  od razu ich nie usuwały. Nowy podpis pod tym limitem w Konfiguracji.

## 1.90.1

- „Rozmiar obrazu”: małe dzieła są przybliżone. Dłuższy bok dzieła ma co
  najmniej około 1/3 szerokości ekranu (o ile mieści się obok mężczyzna);
  mężczyzna widoczny jest wtedy od głowy co najmniej do pasa, ucięty równo
  na krótkiej kresce ołówkiem, która zanika na końcach. Przy dziełach od
  około metra widać go całego, jak dotąd. Pod rysunkiem nie ma już pustego miejsca.
- Gdy wymiary dzieła przychodzą dopiero po otwarciu studium (raz, przy
  dziełach ze studium sprzed szukania wymiarów), sekcja pojawia się
  płynnie zamiast wskakiwać.

## 1.90.0

- Studium dzieła, tylko dla właściciela: przytrzymanie nagłówka „Analiza
  kompozycji” otwiera menu z „Wykonaj ponowną analizę”. Claude analizuje
  kompozycję od nowa (to trwa kilka minut, pod nagłówkiem widać, że
  pracuje), a nowa analiza zastępuje pokazywaną. Poprzednie zostają: gdy
  jest ich kilka, to samo menu pozwala wybrać, którą pokazywać. Domownicy
  widzą zwykły nagłówek.

## 1.89.0

- Tailscale wbudowany w aplikację: spoza domu Frame łączy się z serwerem
  własnym połączeniem Tailscale, bez aplikacji Tailscale i bez VPN na
  iPhonie, więc działa obok innego VPN. Klucz Tailscale wkleja się raz
  w Konfiguracja → Dostęp spoza domu („Zapisz i połącz”); serwer oddaje
  go każdemu telefonowi domu, także domownikom bez konta Tailscale.
  Tam też stan połączenia, przełącznik „Tailscale w aplikacji”,
  „Połącz ponownie” i dziennik. Przez Tailscale idzie tylko adres
  „Spoza domu”, gdy to adres Tailscale. Instrukcja (tag i klucz
  w panelu Tailscale): deploy/synology/README.md.

## 1.88.0

- Konfiguracja → Aplikacja ramki: „Wgraj nowe certyfikaty”. Odnowione
  w Tizen Studio `author.p12` i `distributor.p12` wybiera się w Plikach
  (z Maca przez AirDrop), wpisuje hasło i wysyła na serwer, jak klucz
  APNs. Serwer sprawdza hasło i daty, trzyma pliki tylko u siebie i od
  razu podpisuje nimi aplikację ramki. Skrypt na Macu i File Station
  działają dalej.
- Serwer nie przyjmuje certyfikatu autora z innym kluczem niż dotąd
  (ramka wzięłaby aplikację za inną; w arkuszu można go wgrać mimo to)
  ani certyfikatu, który już wygasł. Błędy po polsku.
- Ważność certyfikatów liczona z całego łańcucha w pliku `.p12`, nie
  tylko z samego certyfikatu, więc ostrzeżenie zdąży także wtedy, gdy
  pierwszy wygaśnie certyfikat pośredni Samsunga.

## 1.87.0

- „Rozmiar obrazu”: obok dzieła dla skali zawsze stoi ciemna sylwetka
  mężczyzny, 180 cm (od czubka głowy do podeszwy stopy z tyłu), z wzrostem
  dopisanym ołówkiem obok. Mniejsze dzieła wiszą jak w muzeum: linia jego
  wzroku przecina je na 2/3 wysokości; większe stoją na podłodze, na linii
  jego prawej stopy. Bez linii podłogi i linii wzroku; dzieło bez cienkiej
  obwódki. Sekcja stoi teraz zaraz po „Detale”.
- Rysunek z wymiarami nie znika już na chwilę przy przełączaniu zakładek:
  wymiary przychodzą razem z tekstem studium.
- Studium dzieła: przy farbach niepewnych na zmianę „Najpewniej”,
  „Prawdopodobnie”, „Zapewne”, „Przypuszczalnie” (także w studiach
  napisanych wcześniej); większy odstęp po każdej sekcji; „Inni w tym
  samym czasie” pokazuje do 10 dzieł w jednym wierszu przewijanym w bok;
  czerwona kropka dzieła na linii życia jest wielkości kółek z numerkami.

## 1.86.2

- Karta dzieła: gdy otwiera się od razu z polskim tytułem, po sekundzie
  przez tytuł raz przechodzi od lewej do prawej delikatny, jaśniejszy
  pas. To podpowiedź, że tytuł można przytrzymać i zobaczyć tytuł
  z muzeum. Gdy polski tytuł dochodzi później, nic nie przechodzi
  (wtedy tytuł i tak się przenika). Przy włączonym „Ogranicz ruch”
  bez efektu.

## 1.86.1

- Kadrowanie: lot ramki z podglądu i z powrotem już nie podskakuje.
  Ramka nie przeskakuje za cel i nie odbija, a przy zamykaniu ląduje
  do końca, zanim pojawi się podgląd. Kadrowanie otwarte
  przytrzymaniem startuje z podglądu tak powiększonego, jakim go widać
  pod palcem. Okna kadru znikają w locie, więc ramka ląduje dokładnie
  jako podgląd.

## 1.86.0

- Ramka → Prezentacja: bez nagłówka „Kadrowanie”. Kolor i szerokość
  passe-partout pokazują się tylko tam, gdzie jest karton (Sztuka:
  Passe-partout i Opis, Zdjęcia: Passe-partout i Multi), jako „Kolor”
  i „Szerokość”, a w Opisie „Kolor passe-partout” i „Szerokość
  passe-partout”.
- Podpis: przy Passe-partout nazywa się „Podpis pod dziełem”, przy
  Wypełnij „Podpis na dziele”, w Opisie go nie ma. Podpis na dziele to
  teraz biała karteczka w prawym dolnym rogu, położona na obrazie, z
  miękkim cieniem rzucanym głównie w dół. Obraz wypełnia cały ekran, bez paska na dole.
- Miniatury kadrowania i siatek Multi mają większy cień, a wybraną
  wyróżnia okrągły znaczek z ptaszkiem w rogu zamiast obwódki wokół ramki.
- Multi przy czarnym passe-partout: okienka zdjęć w miniaturach siatek są
  jasne, wcześniej było czarne na czarnym.

## 1.85.5

- Kadrowanie (karta dzieła, Teraz i Studium): po powrocie ramki na
  podgląd ekran Kadru znika od razu. Wcześniej system jeszcze go
  zsuwał jako kremową kartę z ramką w środku, więc przez ułamek sekundy
  było widać dwie ramki.

## 1.85.4

- Studium dzieła, „Na Twojej ramce”: podgląd ramki otwiera kadrowanie
  tak jak w Teraz i na karcie dzieła. Działa stuknięcie albo przytrzymanie
  z postukiwaniem, ramka wychodzi z podglądu i po zamknięciu wraca na
  niego. Zapisany kadr od razu widać w podglądzie, a gdy dzieło jest
  właśnie na ramce, ramka przerysowuje je z nowym kadrem.

## 1.85.3

- Oryginały dzieł: serwer już zachowywał oryginał każdego dzieła, które
  oglądasz (karta, cały ekran, studium) albo pokazujesz na ramce, nie tylko
  z Ulubionych i playlist. Te ostatnie znikają tylko na samym końcu, gdy
  pamięć przekroczy limit. Jedna luka: przycinanie katalogu usuwało dzieło
  dobrane przez serwer razem z jego oryginałem, nawet obejrzane chwilę
  wcześniej. Teraz obejrzane dzieła odchodzą z katalogu na samym końcu, od
  najdawniej oglądanych. Opisy obu limitów w Konfiguracji mówią to wprost
  (katalog przycina się od najdawniej dodanych, nie od najsłabszych na
  e-papierze).
- Kadrowanie (karta dzieła i Teraz): przy zamykaniu ramka po obrocie
  szybko i płynnie wraca dokładnie na miejsce podglądu, a reszta ekranu
  w tym czasie znika, więc na końcu nic nie miga. Wcześniej systemowe
  przejście zmniejszało cały ekran i dopiero na końcu podmieniało go na
  podgląd. Otwieranie wygląda tak samo: ramka wychodzi z podglądu
  i obraca się, a strona pojawia się wokół niej. Po „Zapisz kadr” ramka
  wraca już z nowym kadrem.
- Tłumaczenie słów w Szukaj: odpowiedź modelu, która przyszła w trakcie
  kolejnego wyszukiwania, nie wywołuje już drugiego, takiego samego pytania.

## 1.85.2

- Karty na dole ekranu łatwiej przeczytać nad kolorowymi obrazami: większy
  tytuł, większy i ciemniejszy drugi wiersz, rodzaj karty w małym kółku w
  stonowanym kolorze, jasna krawędź i miękki cień. Matowe szkło bez zmian.
- Kręciołek, pasek postępu i ikonka telefonu przy wysyłce są czarne (w
  ciemnym trybie jasne) zamiast czerwonych.
- Krótsze tytuły kart: kroki studium z licznikiem „2 z 3”, „Ramka nie
  reaguje na budzenie”, „Szukam nowszej wersji serwera”.

## 1.85.1

- Studium dzieła: gwiazdka oznaczająca tekst Claude'a jest już tylko raz,
  na samym końcu karty, a nie przy każdej sekcji. Stopka nie powtarza
  daty, techniki i muzeum.
- Linia życia: wszystkie chwile z życia i wydarzenia historyczne mają
  numerki w jednej numeracji według lat (historyczne na szaro), znaczniki
  zbyt blisko siebie rozsuwają się, żeby się nie nakładały, a kreska osi
  biegnie za urodzeniem i śmiercią do krawędzi ekranu. W legendzie tytuł
  dzieła tym samym pismem co pozostałe pozycje, tylko na czerwono.
- „Rozmiar obrazu” pojawia się częściej. Wymiary pochodziły tylko z Met,
  Cleveland, SMK i z Wikidanych dla dzieł z kilku muzeów. Teraz serwer
  pyta też Art Institute of Chicago, V&A, Muzeum Narodowe w Warszawie i w
  Krakowie, czyta wymiary ze strony dzieła na Wikimedia Commons, a w
  Wikidanych szuka dzieła także po stronie Commons, po zdjęciu i na końcu po
  tytule (obraz, którego opis wymienia autora, z tego samego roku).
  Dzieła, dla których wcześniej nic nie znaleziono, są sprawdzane ponownie
  przy otwarciu karty.

## 1.85.0

- Studium dzieła, Detale: wycinki trafiają teraz w to, o czym jest opis.
  Duże obrazy model oglądał pomniejszone, a serwer liczył ramki wycinków
  względem obrazu wysłanego, więc wycinek wypadał za mały i przesunięty w
  górę i w lewo. Obraz idzie teraz w rozmiarze, w jakim model go czyta, a
  wycinki studiów napisanych wcześniej są poprawiane przy otwarciu.
- „O autorze”: imię i nazwisko pismem odręcznym większe. Linia życia jest
  po notce o autorze i czytelniejsza: na końcach „ur.” i „zm.” z rokiem,
  ważne chwile z życia jako kółka z numerami, jedno lub dwa wydarzenia
  historyczne z czasu artysty jako kwadraciki z literami, to dzieło jako
  czerwona kropka. Pod linią legenda w kolejności lat z tymi samymi
  znaczkami (dzieło z tytułem). Studia napisane wcześniej serwer uzupełnia
  o wydarzenia w tle.
- Zamiast notki „Tekst napisał Claude…” na końcu, małe gwiazdki przy
  tytułach sekcji, które napisał Claude. W stopce zostaje data, technika i
  muzeum.
- „W tym samym czasie” nazywa się teraz „Inni w tym samym czasie”.
- „Prawdziwy rozmiar” to teraz „Rozmiar obrazu”: obok dzieła dla skali
  kartka A4 z jasnoszarym napisem „A4”. Wymiary są pokazywane także wtedy,
  gdy proporcje różnią się od zdjęcia do 15%.
- Farby w „Kolor i światło” pojawiają się częściej: gdy źródła ich nie
  wymieniają, Claude podaje farby, którymi w tamtym czasie i miejscu
  najpewniej uzyskiwano główne kolory obrazu (oznaczone kółkiem z
  przerywaną obwódką i słowem „Najpewniej”), nigdy młodsze niż dzieło.
  Studia bez farb serwer uzupełnia w tle.

## 1.84.2

- Kadrowanie: pozioma ramka obraca się na bok przy wejściu dużo szybciej
  (ok. 0,3 s zamiast 0,6 s). Pod ramką nie ma już dopisku „Ramka leży
  bokiem, żeby była większa”, zostaje zwykła podpowiedź.
- Kafelek Bateria: gdy ramka śpi, pasek kończy się prosto na szacowanym
  poziomie, a cienka szczelina oddziela go od jaśniejszej części zużytej od
  ostatniego odczytu. Wcześniej przy kilku procentach różnicy jaśniejszy
  kawałek chował się pod zaokrąglonym końcem paska.

## 1.84.1

- Tytuły dzieł nie zaczynają się już od imienia i nazwiska autora
  („Tadeusz Makowski Szewc” → „Szewc”). Brało się to z Wikimedia Commons:
  gdy opis pliku nie ma tytułu, serwer brał nazwę pliku, a ta zaczyna się
  od autora i czasem kończy rokiem. Dotyczy też polskiego tytułu i dzieł
  już zapisanych w bibliotece (poprawiane raz po aktualizacji serwera).

## 1.84.0

- Studium dzieła, nowa sekcja „W tym samym czasie”: trzy dzieła z katalogu
  powstałe kilka lat przed nim lub po nim, u innych artystów i najlepiej w
  innych krajach.
- „O autorze”: pod nazwiskiem linia życia artysty. Na niej to dzieło (na
  czerwono), inne jego prace ze strony i dwie, trzy ważne chwile z życia,
  wypisane pod linią z rokiem.
- „Kolor i światło”: farby, z których dzieło namalowano (z kółkiem barwy,
  miejscem na obrazie i zdaniem o farbie), gdy wymieniają je źródła.
  Studia napisane wcześniej serwer uzupełnia o linię życia i farby w tle.
- Pod tytułem studium jest teraz sam tytuł. Imię i nazwisko twórcy jest w
  „O autorze”, pismem odręcznym jak uwagi do kompozycji, a data, technika i
  muzeum w stopce, obok informacji, kto napisał tekst.
- Nowa sekcja „Prawdziwy rozmiar” tuż przed „Na Twojej ramce”: rysunek
  dzieła w prawdziwych wymiarach (ołówkiem) obok pustej ramki dla skali.
  Wymiary pochodzą z muzeum albo z Wikidaty i są pokazywane tylko wtedy,
  gdy ich proporcje zgadzają się ze zdjęciem.

## 1.83.1

- Szukaj, arkusz „Kolor”: na karcie „Tylko akcent” nie ma już sekcji
  Nastrój, bo nastrój dotyczy całego dzieła, nie akcentu. Nastroje są
  pod „Dominuje”.

## 1.83.0

- Karta dzieła: czerwony napis nad tytułem i wiersz „Kolekcja” podają
  muzeum, w którym dzieło naprawdę jest, a nie źródło zdjęcia. Np.
  „Skąpiec” Makowskiego z Wikimedia Commons pokazuje „Muzeum Narodowe w
  Warszawie”. Skąd jest samo zdjęcie, mówi dalej wiersz „Zdjęcie dzieła”.
- Dla dzieł z Wikimedia Commons, Openverse i WikiArt serwer szuka muzeum
  przy otwarciu karty i w nocy: w Wikidata (kolekcja dzieła), na stronie
  pliku w Commons (instytucja) albo w kopii tego samego dzieła z muzeum.
  Europeana podaje muzeum sama. Gdy nikt nie wie, napisu nad tytułem nie
  ma (zamiast „Wikimedia Commons”).
- To samo muzeum widać w Teraz i w nagłówku Studium dnia.
- Karta dzieła: etykiety pod Kolorystyką idą w trzech wierszach: kolory,
  akcenty, nastroje.

## 1.82.1

- Kopie dzieła: kopii z „Nie pasują” (z marginesem, sam fragment, inne
  dzieło o podobnym tytule) też można użyć. Po stuknięciu widać porównanie
  z obecnym zdjęciem, krótkie wyjaśnienie, czemu kopia nie pasuje,
  i przycisk „Użyj mimo to”. Kopię z marginesem przytniesz potem
  w Kadrowaniu.

## 1.82.0

- Studium dzieła, „O autorze”: nad notką jest teraz wyraźnie imię i
  nazwisko twórcy (imię pierwsze, także gdy muzeum zapisuje „Gogh, Vincent
  van”), a pod nim lata życia, gdy muzeum je podaje. Przytrzymanie nazwiska
  otwiera jego dzieła w Szukaj.
- Analiza kompozycji: kreski, które biegną dalej niż obraz (wierzchołek
  trójkąta, punkt zbiegu), nie są już ucinane na krawędzi obrazu, tylko
  przechodzą na tło strony.
- Podobne dzieła nie pokazują już prac tego samego artysty; te są w „Inne
  prace artysty”.
- Inne prace artysty: cztery prace, po dwie w rzędzie jak w Podobnych
  dziełach. W obu siatkach miniatury są kadrowane wokół twarzy, nie przez
  środek.
- Szukaj, arkusz „Kolor”: nowy nastrój „Kolorowe” dla dzieł w barwach,
  bez czarno-białych, monochromatycznych i dwutonowych. Dzieło jest
  kolorowe, gdy widać na nim co najmniej trzy odległe barwy (z czerwieni,
  żółci, zieleni, błękitu i fioletu), każdą choćby wielkości akcentu.
  Serwer po aktualizacji raz przelicza kolory biblioteki.
- Przygaszone, ale barwne obrazy (np. El Greco) nie dostają już tagu
  „Monochromia”.
- Kropki nastroju są czytelniejsze: Ciepłe to gradient od morelowego do
  ceglastej czerwieni, Chłodne od bladego błękitu do niebieskiego, Żywe
  świecąca czerwień, Stonowane szarawy beż w szarą zieleń, Kolorowe koło
  barw. Nastroje stoją parami, para w wierszu: Ciepłe i Chłodne, Żywe i
  Stonowane, Kolorowe i Monochromia, Ciemne i Jasne. Te same kropki są przy kolorach na karcie dzieła, w polu
  wyszukiwania, w regułach playlist i na pastylce „Kolor” po wyborze
  nastroju.

## 1.81.0

- Szukaj: polskie słowa trafiają do muzeów zagranicznych po angielsku.
  „gitara” idzie do Met, Rijksmuseum, NGA i reszty jako „guitar”, do Paris
  Musées jako „guitare”, a do muzeów w Warszawie i Krakowie dalej po
  polsku. Nazwiska, tytuły i słowa wpisane po angielsku zostają bez zmian.
- Tłumaczenie bierze najpierw to, co serwer już zna (polskie nazwy stylów i
  tematów, słowa kluczowe opisanych dzieł), a nowe słowa raz tłumaczy Haiku
  i je zapamiętuje. Pierwsze wyszukanie nowego słowa może potrwać sekundę
  dłużej.
- Konfiguracja → Model językowy: nowy przełącznik „Tłumaczenie słów w
  Szukaj” (domyślnie włączony).

## 1.80.0

- Szukaj lepszej kopii: arkusz „Kopie dzieła” pokazuje wszystko, co
  znalazły źródła. Dotąd biała pastylka (np. „Wikimedia Commons · 6”)
  mówiła, że coś się znalazło, ale znalezione dzieła o podobnym tytule,
  które okazywały się innym obrazem, znikały bez śladu. Teraz są w „Nie
  pasują” z oznaczeniem „Inne dzieło”, a stuknięcie otwiera ich stronę
  w źródle. Kopie, których nie dało się pobrać do porównania, mają
  oznaczenie „Nie udało się porównać”.
- „Nie pasują” rozwija się samo, gdy nic lepszego się nie znalazło.
- Szukaj w Paris Musées: każde wpisane słowo może pasować do tytułu albo
  do autora, więc „Monet” czy „Nymphéas Monet” znajdują dzieła Moneta.
  Dotąd Paris szukał wpisanego tekstu tylko w tytułach.
- Konfiguracja → Źródła dzieł: pole na klucze WikiArt (Access code i Secret
  code połączone dwukropkiem). Bez nich WikiArt korzysta ze wspólnego
  darmowego limitu i często odmawia.

## 1.79.9

- Teraz: kadrowanie otwiera się z podglądu ramki tak jak na karcie dzieła.
  Przy przytrzymaniu telefon postukuje coraz szybciej, a podgląd lekko
  rośnie; kadrowanie rozwija się z podglądu („pop”) i zamyka się z
  powrotem do niego. Zwykłe stuknięcie dalej działa.
- Kadrowanie: pozioma ramka obraca się na bok już w trakcie otwierania,
  bez czekania. Przy zamykaniu („Zapisz kadr”, „Anuluj”) najpierw płynnie
  wraca do poziomu, a dopiero potem kadrowanie chowa się do podglądu.

## 1.79.8

- Szukaj lepszej kopii: arkusz „Kopie dzieła” nie czeka już w nieskończoność
  na Paris Musées i Openverse. Ich wyszukiwarki odpowiadają czasem dopiero
  po minucie, więc po 20 s takie źródło jest oznaczone jako bez odpowiedzi,
  a lista się kończy. Serwer czeka na nie dalej w tle i zapamiętuje
  odpowiedź, więc przy następnym otwarciu ich kopie są od razu.
- Paris Musées szuka kopii po samym tytule dzieła. Wcześniej szukał tytułu
  razem z nazwiskiem artysty, czego w tytułach nie ma, więc nigdy nic nie
  znajdował.

## 1.79.7

- Szukaj: menu po przytrzymaniu kafelka wyniku ma obok „Dodaj do kolejki”
  także „Ukryj dzieło”. Ukryte dzieło od razu znika z wyników (razem z
  kopiami z innych muzeów) i trafia do karty „Ukryte” w Playlistach.
- Kopie dzieła: po wyborze innej kopii komunikat „Zdjęcie podmienione”
  jest samą informacją, bez guzika „Cofnij”, i znika po chwili.
- Karta dzieła, widok „Na ramce”: podgląd reaguje jak obraz w „Oryginał”.
  Przy przytrzymaniu telefon postukuje coraz szybciej, a podgląd lekko
  rośnie; kadrowanie rozwija się z podglądu („pop”) zamiast wjeżdżać od
  dołu. Zwykłe stuknięcie dalej działa. Kadrowania nie zamyka już
  przeciągnięcie w dół, tylko „Anuluj” albo „Zapisz kadr”.
- Kadrowanie (karta dzieła i Teraz): gdy ramka wisi w poziomie, jej
  podgląd po otwarciu obraca się o 90° i leży bokiem na całej wysokości
  ekranu, więc jest dużo większy. Przeciąganie obrazu działa w osiach
  obróconej ramki.

## 1.79.6

- Obraz na karcie dzieła i w studium: przy przytrzymaniu rośnie wyraźniej,
  a widok na całym ekranie rozwija się z miniatury („pop”) zamiast
  wjeżdżać od dołu; zamyka się z powrotem do miniatury.

## 1.79.5

- Passe-partout (zakładka Ramka i wysyłanie zdjęcia): kolory kartonu to
  teraz okrągłe próbki zamiast zaokrąglonych prostokątów. Jasne i Ciemne,
  które biorą odcień z obrazu, mają zamiast tęczy trzy kropki farb, jak
  pastylka Kolor w Szukaj. Wybrany kolor otacza obwódka, a podpisy są
  wszystkie w kolorze tekstu, jak w Kadrowaniu.

## 1.79.4

- Przytrzymanie tytułu, nazwiska autora i obrazu (karta dzieła, studium,
  tytuł i autor także w Teraz): telefon postukuje coraz szybciej aż do
  zamiany zamiast jednego stuknięcia, a tekst powiększa się mniej.
  Przytrzymanie obrazu otwiera go na całym ekranie; zwykłe stuknięcie
  dalej działa.
- Zakładka Ramka: przy nazwie ramki nie ma już ołówka. Nazwę zmieniasz,
  przytrzymując ją, tak jak tytuł dzieła: telefon postukuje, nazwa
  delikatnie rośnie, a po chwili otwiera się okienko „Nazwa ramki”.

## 1.79.3

- Przełączniki w ciemnym trybie: włączony przełącznik ma ciepły, szary
  tor zamiast kremowego, więc biała gałka znowu się od niego odcina. W
  jasnym trybie bez zmian.
- Playlisty, karta „Ukryte”: ukryte dzieła leżą teraz za szronionym
  szkłem z drobnym ziarnem, rozmyte mocniej i jako całość. Dotąd każdy
  obraz rozmywał się osobno, więc szwy między nimi zostawały ostre; teraz
  widać same kolory, bez kształtów.

## 1.79.2

- Tytuł w oryginale: bez dopisku „Tytuł z muzeum”, także w studium dzieła.
  Gdy zaczynasz naciskać tytuł, telefon lekko stuka, a tytuł delikatnie
  się powiększa; po przytrzymaniu przełącza się z mocniejszym stuknięciem.
- Nazwisko autora (karta dzieła, Teraz, studium) odpowiada na nacisk tak
  samo; dociśnięcie, jak stuknięcie, otwiera Szukaj z jego dziełami.

## 1.79.1

- Playlisty: nowa okładka karty „Ukryte”. Zamiast wyszarzonego kolażu
  ukryte dzieła leżą pod kremową bibułą, jak grafika w teczce: kolory
  prześwitują, szczegółów nie widać. W rogu naklejka z przekreślonym okiem.

## 1.79.0

- Nocna kolejka prac serwera: to, co zmienia katalog albo przegląda go w
  całości, serwer robi nocą (1:30–6:00 wg strefy ramki), po jednym
  zadaniu, czekając, gdy ktoś używa aplikacji albo ramka dostaje obraz.
  W nocy: porządki pamięci (dotąd po każdej zmianie obrazu), wymiana
  dzieł pełnego katalogu (dotąd co 6 h) i arcydzieła muzeów, grupowanie
  kopii i podpowiedzi wyszukiwania, indeks NGA, urodziny ulubionych
  artystów, Dzieło dnia z listami, liczby playlist, nowe dzieła w
  kolejce ramki, ostrzejsze kopie dla 20 następnych obrazów, karty
  motywów i wiersze Odkrywaj. Noc opuszczona (NAS wyłączony) nadrabia
  się kilka minut po starcie. Log mówi, ile trwało każde zadanie
  (`/api/debug/log?grep=night`).
- W dzień: Teraz nie przegląda całej playlisty przy każdym otwarciu,
  karty motywów Odkrywaj są ważne do zmiany katalogu (nie 10 minut),
  Propozycje do zmiany biblioteki, a przegląd notatek AI w tle odbywa się
  po zmianach, nie co minutę. Szukanie w muzeach, opisy otwieranych dzieł,
  ostrzejsza kopia przy otwarciu karty, studia i Analiza kompozycji
  działają jak dotąd. Katalog, który jeszcze się zapełnia, rośnie też
  w dzień.

## 1.78.1

- Tytuł w oryginale: przytrzymanie polskiego tytułu przełącza go na tytuł
  z muzeum, który zostaje po puszczeniu palca (wcześniej palec zasłaniał
  go przez cały czas, gdy był widoczny). Kolejne przytrzymanie wraca do
  polskiego; nowy obraz albo karta zaczyna po polsku.

## 1.78.0

- Wskaźnik połączenia z serwerem jest teraz w lewym górnym rogu każdej
  zakładki, nie tylko w „Teraz”. Podczas łączenia to samo kręcące się
  kółko, bez napisu „Odświeżam”; „Bez połączenia” pojawia się dopiero,
  gdy serwer naprawdę nie odpowiada, a stuknięcie próbuje ponownie.
- „Bez połączenia” nie miga już przy łączeniu przez Tailscale: aplikacja
  próbuje przez 20 sekund (od razu ponownie, gdy zmieni się sieć, np. gdy
  Tailscale wstanie), zamiast poddawać się po pierwszej próbie, i nie
  pokazuje go, gdy serwer już odpowiedział, a „Teraz” jeszcze się wczytuje.
  Tylko aplikacja, serwer bez zmian.

## 1.77.1

- Playlisty widać od razu po uruchomieniu aplikacji (z poprzedniego razu,
  potem świeże). Serwer nie przelicza już przy każdym otwarciu każdej
  inteligentnej playlisty przez cały katalog (na NAS po sekundzie lub
  więcej na playlistę): liczby dzieł i okładki pamięta, a gdy w tle
  przybywają dzieła, przelicza playlistę, gdy ktoś ją otwiera, i wszystkie
  w nocy. Zmieniona playlista albo serduszko liczą się od razu.
  Wymaga zaktualizowanego serwera.

## 1.77.0

- „Szukaj lepszej kopii” w menu „…” karty dzieła i w wierszu „Zdjęcie
  dzieła” (teraz widocznym zawsze, z rozmiarem zdjęcia): arkusz „Kopie
  dzieła” pyta wszystkie źródła naraz i pokazuje kopie, gdy tylko
  przychodzą. Na górze obecne zdjęcie z paskiem, ile z 2560 px ramki daje,
  pod nim „Lepsze” od najostrzejszej na ramce, „Inne kopie” i zwinięte „Nie
  pasują” (fragment, czarno-biała plansza, reprodukcja). Dotknięcie kopii
  pokazuje ten sam fragment obu zdjęć w skali ramki z suwakiem „przed / po”
  i „Użyj tej kopii”. Dzieło zostaje tym samym dziełem (serduszko,
  playlisty, kolejka, kadr), zmienia się tylko zdjęcie; automat w tle nie
  nadpisuje wyboru. „Przywróć zdjęcie muzeum” w menu i w arkuszu. Serwer:
  `GET /api/library/items/<id>/copies` (strumień), `…/copies/<kopia>/spot`,
  `PUT`/`DELETE …/copy`. Wymaga zaktualizowanego serwera.
- Tytuł w oryginale: przytrzymaj polski tytuł na karcie dzieła albo w
  „Teraz”, a po chwili (z lekką wibracją) przeniknie w tytuł podany przez
  muzeum, z dopiskiem „Tytuł z muzeum”. Po puszczeniu wraca polski. Długi
  tytuł muzeum pokazuje się na ten czas cały; stuknięcie tytułu w „Teraz”
  dalej otwiera kartę.

## 1.76.0

- „Nie pokazuj na ramce” nazywa się teraz „Ukryj dzieło” (z powrotem
  „Przywróć dzieło”). Ukryte dzieło znika zewsząd: z ramki, playlist,
  kolejki, Propozycji, Odkrywaj, Dzieła dnia i wyszukiwania, także w
  muzeach, razem z jego kopiami z innych muzeów. „Pokaż na ramce” wprost
  dalej działa.
- Na końcu Playlist nowa karta „Ukryte”: ukryte dzieła, ostatnio ukryte
  pierwsze. Przytrzymaj dzieło (albo otwórz jego kartę), by je przywrócić.
  Wymaga zaktualizowanego serwera.
- Odkrywaj: Studium dnia i Studia dzieł widać od razu po uruchomieniu
  aplikacji (z poprzedniego razu, potem świeże). Kafelek dnia prosi serwer
  tylko o tekst (dotąd serwer za każdym razem przeszukiwał cały katalog dla
  list pod stroną, ok. 6 s na NAS, a przy starcie wstrzymywało to też inne
  zapytania). Listy pod stroną (podobne dzieła, co z niego wyrosło, inne
  prace artysty) serwer pamięta przez godzinę i liczy zawczasu dla dzieła
  dnia, więc strona też otwiera się szybciej. Wymaga zaktualizowanego
  serwera.

## 1.75.6

- Analiza kompozycji: główny układ zawsze ma swój ślad. Klin, którego punkt
  zbiegu leży daleko poza obrazem (bar w „Nocnych markach”), rysuje się
  dwiema prostymi po zbiegających się krawędziach; w 1.75.4 porządkowanie
  czytelności usuwało go zamiast tego, co go dublowało. Runda 7.

## 1.75.5

- Ramka: znaczek na kafelku Sieć mówi, co zrobi stuknięcie: odśwież przy
  Online, słońce przy Czuwaniu (stuknięcie budzi), „i” przy głębokim śnie
  i poza Wi-Fi.

## 1.75.4

- Podgląd na „Teraz” i inne obrazy nie wiszą już poza domem (Tailscale):
  zapytania w toku przechodzą na drugi adres serwera, a aplikacja startuje
  z ostatnio działającym. Podgląd ramki przychodzi jako JPEG, ok. 5× mniejszy.
  Wymaga zaktualizowanego serwera.
- Analiza kompozycji czytelniejsza: łamana linia (klin, zygzak) rysuje się
  w aplikacji z ostrymi narożnikami zamiast łuku, zbiegające się krawędzie
  model rysuje jako linie perspektywy do punktu zbiegu, dwa ślady nie
  biegną po tej samej krawędzi, jedna rzecz ma jeden ślad (nie kółko wokół
  łodzi i linia po jej maszcie), klin to trzy punkty zamiast zygzaka, a
  strzałka otwartej kompozycji jest długa i ma własną drogę (uwagi Mateusza
  do Nocnych marków, to samo w Trouville). Runda 6.

## 1.75.3

- Analiza kompozycji: praca, przy której odpowiedź modelu nie dała ujęcia,
  nie czeka już w nieskończoność. Odpowiedź zostaje zapisana do wglądu,
  `GET /api/ai/composition` pokazuje takie prace w `failed`, a ponowne
  wskazanie ich w `PUT` pyta jeszcze raz. Ujęcie podpisane inaczej niż
  „Analiza kompozycji” też się liczy.
- Bez rytmu sprzętów (stołki, krzesła, butelki): model może o nim napisać,
  ale go nie rysuje. Runda 5: strony z pierwszej próby można przerobić
  jeszcze raz.

## 1.75.2

- Ramka: gdy serwer wie, że ramka śpi (Czuwanie), zakładka Ramka nie pyta
  jej od nowa, więc kółko na kafelku Sieć nie kręci się kilkadziesiąt sekund.

## 1.75.1

- Karta dzieła i studium: obraz na całym ekranie otwiera się powiększony,
  wypełniając ekran; podwójne stuknięcie pokazuje całe dzieło.

## 1.75.0

- Studium dzieła: nowa „Analiza kompozycji”, jedno ujęcie zamiast „Geometrii”
  i „Geometrii detali”. Claude pisze ją osobnym, dokładniejszym pytaniem:
  masy i równowaga, podziały, jeden główny układ, duże wyraźne rytmy, czy
  kompozycja jest otwarta czy zamknięta i co układ robi dla tematu; siatki
  tylko jako pomiar. Tekst ma 4–6 zdań.
- Nowe ślady na obrazie: rytm jako równoległe kreski przy każdej powtarzanej
  formie (bez łączącej linii), linie zbiegu perspektywy i ruch jako
  zamaszysta strzałka ze smugami.
- Zapisane studia dostają nową analizę w tle, gdy właściciel na to pozwoli
  (`PUT /api/ai/composition`); poprzednia zostaje zachowana w stronie.

## 1.74.0

- Szukaj: w grupie Muzeum przełącznik „Wybrane / Wykluczone” pozwala
  przeszukać wszystkie muzea oprócz wybranych (np. bez Yale). Playlista
  utworzona z takiego wyszukiwania też pomija te muzea, a muzea dodane później
  same do niej wejdą. Wymaga zaktualizowanego serwera.
- Serwer po starcie nie przelicza w kółko całej biblioteki przy synchronizacji
  albumu iCloud: aplikacja nie czeka już na niego kilkudziesięciu sekund po
  aktualizacji.

## 1.73.4

- Studium dzieła: podgląd „Na Twojej ramce” znów pokazuje całą ramkę w jej
  kształcie, a nie biały pasek z małym obrazkiem.
- Playlisty: karta „Teraz prezentowane” ma w prawym dolnym rogu tę samą
  strzałkę w czarnym kwadracie co studium dnia w Odkrywaj; cudza playlista,
  której nie da się otworzyć, nie ma strzałki.
- Przytrzymany przycisk „Pokaż na ramce” (i „Otwórz studium”) zachowuje
  kształt etykiety, bez zaokrąglonych rogów.

## 1.73.3

- Harmonogram: godziny ciszy nocnej mają ten sam obwiedziony wygląd co
  godziny zmiany.

## 1.73.2

- Studium: dopiski przy „Podobnych dziełach” to cicha kursywa z cienką kreską
  z lewej zamiast cynobrowej plakietki.
- Teraz: zwinięty opis na karcie „Dzieło” kończy się na pełnym zdaniu, a nie
  na urwanym słowie z „…”.
- Ramka nie przesypia zmiany obrazu, gdy zgubi budzik: aplikacja ustawia
  budziki od nowa po każdym śnie, a gdy ramka i tak nie wstanie, serwer minutę
  później budzi ją przez sieć. Nowa paczka aplikacji instaluje się na ramce
  sama.

## 1.73.1

- Ramka: orientacja to sam przełącznik z ikonkami poziomej i pionowej ramki,
  bez napisu i karty.

## 1.73.0

- Bateria we śnie: kafelek pokazuje szacowany poziom (jaśniejszy łuk, szara
  liczba) zamiast ostatniego odczytu, a w okienku Bateria jest linia „Teraz ok.
  X%”. Dni do rozładowania liczą się od tego szacunku.
- Uśpienie ramki widać od razu na kafelku Sieć w zakładce Ramka: aplikacja
  najpierw pokazuje stan znany serwerowi, potem pyta ramkę i odświeża go co
  10 s. Serwer uznaje ramkę za śpiącą także wtedy, gdy nie dotarł jej
  meldunek o zaśnięciu.
- Studium dnia nie zostaje w połowie puste: gdy Claude odda opis bez analizy
  kompozycji, koloru, detali albo oceny na ramce, serwer pyta drugi raz.
  Zapisane wcześniej takie studium uzupełnia się samo.

## 1.72.0

- Nowy wygląd przycisków w całej aplikacji: jak etykiety muzealne
  (prostokątne, wersaliki, atrament albo kontur). Niebieski akcent zniknął.
- Zestawy z Odkrywaj nie czekają już w kolejce do muzeów za importem w tle;
  serwer zapisuje w logu czasy każdej rundy zestawu.
- Miniatury w Szukaj i Odkrywaj w swoich proporcjach, także z muzeów, które
  nie podają wymiarów.
- Nowa ikonka „Teraz” i „na ramce”: pełny obraz zamiast obrazu w ramce, w
  zakładce, przyciskach „Pokaż na ramce” i „Prezentuj na ramce” oraz w Live
  Activity.
- Strona pod szklanym okienkiem podpowiedzi nie jest już rozbielona.

## 1.71.1

- Okienko podpowiedzi w Szukaj jest szklane, jak otwarta grupa.
- Aplikacja na przytomnej ramce pyta serwer co 10 s zamiast co 20 s, więc
  wysłany obraz dociera szybciej.
- Po „Sprawdź stan” ramka nie zasypia od razu, tylko czeka jeszcze 2 minuty.
  Obraz wysłany w tym czasie dociera od razu, bez budzenia.

## 1.71.0

- Odkrywaj: propozycja (motyw) zamiast „Wczytuję…” pokazuje kwadraciki i
  wczytuje dzieła stopniowo, w miarę jak odpowiadają muzea; kolejne dochodzą
  przy przewijaniu.
- Playlisty i Odkrywaj nie kończą się błędem, gdy w tle dochodzą nowe dzieła.
- Ramka budzi się dla obrazu wysłanego tuż po „Sprawdź stan”: serwer
  czeka z sygnałem budzenia, aż ramka naprawdę zaśnie, a aplikacja na
  ramce sama pyta o obraz, gdy kilka minut po uśpieniu dalej działa.
- Serwer: ostatnie wpisy logu pod `/api/debug/log` (tylko z tokenem
  właściciela), do diagnozy bez otwierania Container Managera.

## 1.70.0

- Studium dzieła: gotowe studium otwiera się od tekstu, a listy (Podobne,
  Dalsze losy, Inne prace artysty) dochodzą chwilę później; studium obejrzane
  raz otwiera się od razu. Poświata u góry karty i studium jest od pierwszej
  klatki, z kolorów miniatury.
- Karta dzieła: polski tytuł pojawia się od razu, opis dochodzi chwilę później.
- Szukaj i edytor playlisty: podpowiedzi podczas pisania w okienku nad polem,
  a wyniki pod nim stoją w miejscu; nowe wyszukiwanie przewija wyniki na górę.

## 1.69.8

- Wyszukiwanie: animowane kwadraciki to znak czekania (wyniki, podpowiedzi,
  edytor playlisty); znikają dopiero, gdy nic więcej nie przyjdzie.

## 1.69.7

- Studium dzieła: obraz nie miga przy wejściu; najpierw miniatura, na nią
  płynnie wchodzi pełny obraz.

## 1.69.6

- Karta dzieła i „Teraz”: bez ikony lupy przy autorze; stuknięcie w imię i
  nazwisko dalej otwiera Szukaj z jego dziełami.

## 1.69.5

- Szukaj: kolejne wyniki doczytują się same podczas przewijania, bez
  przeciągania; w trakcie na dole bawią się kwadraciki, nad grupami.

## 1.69.4

- Karta dzieła: polski tytuł i opis od razu, gdy już były po polsku; z
  oryginału łagodne przenikanie zamiast nagłej podmiany.

## 1.69.3

- Karta dzieła: gdy studium jest gotowe, „Otwórz studium” stoi na całą
  szerokość pod „Pokaż na ramce” i „Dodaj do kolejki”.

## 1.69.2

- Aktualizacja serwera z aplikacji: chwilowa utrata połączenia przy restarcie
  jest pokazywana jako etap aktualizacji, a nie błąd.

## 1.69.1

- Playlisty: przy wspólnych playlistach sama ikona dwóch osób, bez napisu
  „Wspólna”.

## 1.69.0

- Przy użytku prywatnym Rijksmuseum i SMK w Kopenhadze także pokazują dzieła
  wciąż chronione prawem autorskim (np. Karel Appel, Picasso, Asger Jorn).
- Europeana nie pokazuje już starych czarno-białych zdjęć obrazów z kartą
  katalogową (Bildarchiv Foto Marburg, KIK-IRPA); kolorowe zdjęcia tych archiwów
  i czarno-białe grafiki z muzeów zostają.
- Playlisty: wszystkie kafelki mają równą wysokość (nic nie skacze przy
  przewijaniu), „Wspólna” po prawej w wierszu z liczbą dzieł, bez nagłówka
  „Kolekcje”.

## 1.68.0

- Słabe obrazy dzieł (mała rozdzielczość, mocno ściśnięty plik) podmieniane
  w tle na ostrzejszą kopię tego samego obrazu z innego źródła (Commons,
  muzea), na karcie dzieła i przy Studium dnia; nigdy detal, strona albumu
  ani czarno-biała reprodukcja.

## 1.67.4

- Playlisty: kafelki w siatce wyrównane do góry (bez wiersza „Wspólna” nie
  opadają), a moje „Ulubione” zawsze pierwsze, obok „Propozycje”.
- Szukaj i edytor playlisty: stuknięcie poza otwartym okienkiem grupy działa
  jak „Gotowe”.

## 1.67.3

- Ikony grup (Epoka, Styl, Temat, Muzeum) prostsze, jedną kreską jak Technika,
  w całej aplikacji.

## 1.67.2

- Szukaj: pole nie podskakuje, gdy po wyborze z grupy pojawia się X.

## 1.67.1

- Szukaj: ikona Tematu jak na szkicu (szczyt i słońce), w tej samej wielkości
  co pozostałe.

## 1.67.0

- Szukaj: ikony przy grupach; po wyborze pastylka pokazuje ikonę i wybraną
  wartość w jednej linii. Temat ma pejzaż także w podpowiedziach.
- Szukaj: X obok pola czyści też wybory z grup (zamiast „Wyczyść wybory”),
  także w edytorze playlisty.

## 1.66.0

- Przy „Użytku prywatnym” Muzea Narodowe w Warszawie i Krakowie pokazują też
  dzieła wciąż chronione prawem autorskim (np. Andrzej Wróblewski); puste
  wyniki z tych muzeów nie są już błędem.
- Klucz Smithsonian w Konfiguracja → Źródła dzieł znowu się zapisuje (zamiast
  „Smithsonian teraz nie odpowiada”); to samo sprawdzanie poprawione dla
  Europeany.
- Podgląd „Na ramce” i pełny ekran wczytują się także dla bardzo dużych
  skanów z Wikimedia Commons (serwer bierze kopię 3840 px).

## 1.65.0

- Klucze źródeł dzieł wpisuje się w aplikacji: Konfiguracja → Źródła dzieł
  (Smithsonian, Paris Musées, Europeana). Serwer sprawdza klucz w źródle,
  zanim go zapisze. Opcja dodatku `smithsonian_key` i zmienna
  `FRAME_SMITHSONIAN_KEY` z 1.64.0 znikają.
- Nowe źródło: Paris Musées (z kluczem).
- Polskie imiona artystów także u domowników (Mój dostęp → Dla zabawy).

## 1.64.0

- Nowe źródła dzieł: Muzeum Narodowe w Warszawie i w Krakowie, National
  Gallery of Art, Yale, Smithsonian (z kluczem API w opcji
  `smithsonian_key`, inaczej ukryte) i V&A (tylko przy „Użytek prywatny”).
  Polskie motywy najpierw pytają muzea narodowe. NGA przy pierwszym użyciu
  pobiera lokalny indeks (~230 MB, odświeżany co tydzień).

## 1.63.0

- Konfiguracja → Odkrywaj: „Wylosuj inne” zmienia Studium dnia, a
  „Wylosuj innego” Artystę tygodnia (tylko właściciel).
- Polskie imiona artystów dla zabawy (Konfiguracja → Dla zabawy): Paweł
  Cézanne, Wincenty van Gogh, Hieronim Bosch; nazwiska i wyszukiwanie bez
  zmian.

## 1.62.0

- Szukaj: podpowiedzi obejmują też słowa kluczowe i tematy dzieł (np.
  „wielka fala”, „góra Fuji”), oznaczone w aplikacji jako „Słowo kluczowe”.
- Ponowne stuknięcie w „Teraz” na pasku wraca do obrazu, który jest na
  ramce, i przewija stronę na górę.
- Poświata kolorów jest krótsza (zostaje u góry strony), a do tego pojawia
  się też na ekranie playlisty, na karcie dzieła i w studium.
- Puste obrazy dzieł: gdy muzeum odmawia, serwer bierze kopię z Wikimedia
  Commons; obrazy same ponawiają wczytywanie, dotknięcie wczytuje je od
  razu, a dzieła bez obrazu znikają z list.
- „Inne prace artysty” w studium bez powtórzeń: ta sama praca z innego
  źródła (także pod tytułem w innym języku) i kopie studiowanego dzieła są
  pomijane.

## 1.61.1

- Szukaj: okienka grup są ze szkła, które płynnie rozciąga się z przycisku
  w okienko i chowa się z powrotem do przycisku.

## 1.61.0

- Ta sama, spokojniejsza poświata kolorów na Teraz, w Odkrywaj i w
  Playlistach (z okładki aktywnej playlisty).

## 1.60.0

- Szukaj: podpowiedzi pojawiają się od razu przy każdej literze, a serwer
  liczy je w ułamku sekundy (indeks haseł zamiast przeglądania całej
  biblioteki); lista nie znika już na chwilę do „Szukam…”.

## 1.59.0

- Serce i menu „…” w prawym górnym rogu studium dzieła, jak na karcie
  dzieła (Dodaj do playlisty, Nie pokazuj na ramce, Otwórz w muzeum, Zapisz
  w Zdjęciach).

## 1.58.2

- Poświata w Odkrywaj bez ostrej krawędzi, sięga dalej i ma mocniejsze
  kolory.

## 1.58.1

- Miniatury w studium (Inne prace artysty, Podobne dzieła, Dalsze losy)
  otwierają wskazane dzieło, a nie studiowane; ikona studium to gwiazdki AI.
- Tytuły dzieł bez przedrostka języka (np. „en:Night Windows”); zapisane
  dzieła poprawiane raz przy starcie.

## 1.58.0

- Domownicy: właściciel zaprasza osobę w Konfiguracja → Domownicy (kod QR
  albo link, jednorazowy, 30 min); jej telefon dostaje własny dostęp.
  Domownik ma własne Ulubione, playlisty (przełącznik „Wspólna”, nowe
  prywatne, dotychczasowe wspólne), Historię przesłanych i powiadomienia;
  zmienia Harmonogram i Prezentację, budzi i usypia ramkę, zamawia studia
  (limit dzienny u właściciela, domyślnie 5). Konfiguracja, nazwa ramki,
  usuwanie dzieł i aktualizacja serwera tylko dla właściciela. Wymaga
  FRAME_API_TOKEN na serwerze.
- Szukaj: okienko grupy naprawdę wyrasta ze swojego przycisku i do niego
  wraca (poprawka z 1.57.0 nie działała). Opis „Tylko akcent” krótszy.

## 1.57.0

- Inteligentne playlisty: zamiast przełącznika „Pobieraj pasujące z muzeów”
  wybór „Ile dzieł” (50, 100, 200, 300 albo Wszystkie). Brakujące dzieła
  dobierają się z muzeów w tle, a gdy pasuje więcej, playlista bierze stały
  zestaw, najpierw ulubione. Starsze playlisty zachowują wszystkie dzieła.
- Sprawdzanie wersji serwera w aplikacji trwa około sekundy: serwer pyta
  rejestr obrazów zamiast pobierać cały obraz. Aktualizacje serwera pobierają
  kilka MB zamiast ~200 MB (od następnej wersji po tej).
- Szukaj: okienko grupy zamyka się z powrotem do swojego przycisku (a nie do
  „Techniki”) i może być wyższe, więc Epoka mieści więcej okresów bez
  przewijania.
- Szukaj: muzeum, które nie odpowiada (np. The Met), jest pomijane po cichu,
  bez napisu „Nie odpowiedziało”; siatka dzieł z mniejszymi dziurami między
  kolumnami.
- Grupa „Na ten tydzień” w Odkrywaj i Propozycjach nazywa się teraz
  „Dziś dla Ciebie”.
- Ramka nie budzi się już o 03:00 na kilka minut: przed każdym snem
  z pobudką aplikacja ramki przesuwa dzienne odświeżanie ekranu Samsunga na
  godzinę tej pobudki.
- Na górze Odkrywaj kolory Studium dnia lekko przenikają w tło, jak na
  karcie Teraz.

## 1.56.0

- Dzieło dnia jest teraz Studium dnia: codziennie na górze Odkrywaj nowe
  studium dzieła, a dawne Dzieła dnia stają się zwykłymi studiami bez nowego
  kosztu. Na karcie dzieła pojawia się wtedy „Otwórz studium”.
- Na stronie studium obraz ma zawsze pełną szerokość i otwiera się na całym
  ekranie z powiększaniem. Obraz w Analizie kompozycji ma szerokość tekstu
  w obu ujęciach.
- „Dlaczego dziś” pojawia się tylko w dniu studium, na białej albo czarnej
  karteczce. Nie ma już „Poprzednich dzieł dnia”.
- Nowa sekcja „Inne prace artysty”: 6 prac z katalogu, a gdy jest ich za
  mało, serwer raz szuka w muzeach.
- Przełącznik i powiadomienie nazywają się „Studium dnia”.

## 1.55.1

- Szukaj: siatka dzieł nie znika i nie skacze przy przewijaniu.
- Szukaj i ręczne playlisty: jedna lista dzieł bez podziału na katalog
  i muzea; teksty Odkrywaj bez słowa „katalog”.

## 1.55.0

- Przygotowanie studium dzieła na ekranie blokady i w Dynamic Island (Live
  Activity): trzy kroki, serwer przesuwa kartę pushem także przy zamkniętej
  aplikacji, na koniec stuknięcie otwiera studium. „Studium gotowe”
  przychodzi po wycięciu detali.
- Analiza kompozycji: tylko Geometria i Geometria detali (bez Spojrzenia),
  złota spirala rysowana dokładnie, siatki 3×2 i 2×3 obok złotego podziału,
  3×3 i 2×2, złote trójkąty; zapisane studia i Dzieła dnia poprawione raz
  w tle (ok. 0,10 USD za stronę).
- Notka „O dziele” i „Czytaj więcej” na Teraz pokazują się w całości, bez
  urwania wielokropkiem; tekst da się zaznaczyć.
- Wyszukiwanie i katalog nie pokazują już znaczków, monet ani rzeczy
  pocztowych z Europeany (np. arkusz Ateny 2004 jako martwa natura).
- Szukaj: przy otwartej klawiaturze grupy stoją wyżej, z wyraźnym odstępem
  od pola szukania.

## 1.54.0

- Teraz startuje tak, jak go zostawiono: ostatni obraz od razu, z pigułką
  „Odświeżam…” (albo „Bez połączenia”, by spróbować ponownie), dopóki serwer
  nie odpowie; nowszy obraz pojawia się płynnie. Przy pierwszym uruchomieniu
  w pustej ramce grają kwadraty z ikony aplikacji z powitaniem pod spodem.

## 1.53.0

- Odkrywaj: Motyw dnia jako pierwszy kafelek w „Na ten tydzień”; zamiast
  rzędów „Bo lubisz: …” grupa „Bo lubisz” z kafelkiem na każdego ulubionego
  artystę i pokrewnymi artystami w środku; „Studia dzieł” na końcu ekranu.
- Poprawki szklanego Szukaj: grupy przy klawiaturze stoją nad polem, a nie
  za nim; znowu wyższe grupy na całą szerokość 3 × 2 z nazwą nad wyborem;
  grupa otwiera się jako szklane okienko nad polem zamiast arkusza;
  „Wyczyść wybory” nad grupami; schowane grupy wracają chwilę po zatrzymaniu
  przewijania; Epoka pobiera okresy od nowa po aktualizacji serwera; koniec
  białego ekranu z wąskim paskiem podczas pisania.
- Dzieło dnia otwiera się od razu na całą szerokość z obrazem, zanim
  wczyta się reszta strony.
- Ekrany w trakcie wczytywania lub puste (m.in. Odkrywaj przy pierwszym
  uruchomieniu) mają od razu pełną szerokość: koniec białej strony z wąskim
  beżowym paskiem w całej aplikacji.
- Kafelek Zasilanie pokazuje błyskawicę przez całe ładowanie (zasilacz
  wpięty i bateria poniżej 95%), a wtyczkę dopiero przy prawie pełnej
  baterii; wcześniej błyskawica migała i zmieniała się we wtyczkę.

## 1.52.0

- Szklane Szukaj (iOS 26): systemowa karta wyszukiwania z polem na dole; nad
  polem sześć grup w cienkich szklanych kapsułach (bez „Moje” i strzałek),
  które chowają się przy przewijaniu wyników i wracają po stuknięciu pola;
  nad wynikami linijka z tym, czego szukasz. To samo w edytorze playlist
  (pole na dole arkusza, w ręcznej „Wybrane · N”).
- Epoka: 20 nazwanych okresów w grupach Europa, Polska oraz Japonia i Chiny,
  z klamrą lat pod osią; okresy polskie i azjatyckie sprawdzają też
  pochodzenie dzieła.
- Analiza kompozycji: Geometria pierwsza i z wielkimi liniami całego obrazu
  (piramida, X, klin, koła i owale, linie mogą wychodzić poza obraz), siatka
  2×2 obok złotego podziału i 3×3, nowe ujęcie Geometria detali zamiast
  Rytmu; zapisane studia i Dzieła dnia poprawione raz w tle (ok. 0,10 USD
  za stronę).
- Aplikacja wymaga teraz iOS 26.

## 1.51.0

- Trzy nowe powiadomienia, każde z własnym przełącznikiem: „Studium gotowe”
  (dotknięcie otwiera studium), „Artysta tygodnia” w poniedziałek o 9:00
  (otwiera jego temat w Odkrywaj) i „Rocznica urodzin” o 10:00 dla artystów
  Twoich ulubionych dzieł (data urodzenia z Wikidata; otwiera Szukaj na
  artyście). Telefony zapisane wcześniej mają je od razu włączone.

## 1.50.0

- Analiza kompozycji trafniejsza: Claude dostaje większy obraz i podaje
  ślady w pikselach, nowy opis zadania (siatka do ok. 5%, otwarte trójkąty,
  rytm od trzech powtórzeń), a drugie pytanie sprawdza ślady narysowane na
  obrazie i je poprawia albo usuwa. Zapisane studia sprawdzane są raz
  w tle. Studium kosztuje teraz ok. 0,24 USD zamiast 0,14.
- Tytuły ekranów w aplikacji pisane szeryfowym krojem, półgrubym,
  z Dynamic Type.

## 1.49.1

- Szukaj i edytor playlist: przyciski grup zawijają się do drugiej linii
  zamiast przewijać się w bok.
- Kolory: kolory i nastroje to jedna grupa „lub”, akcenty druga, a obie
  muszą pasować (np. Błękit + Akcent: czerwień to niebieskie dzieła
  z czerwonym akcentem). Dotyczy playlist i wyników z muzeów.

## 1.49.0

- Powiadomienia na telefonie (Konfiguracja → Powiadomienia): bateria poniżej
  20%, błąd wysyłki, zmiana dzieła na ramce, nowa wersja serwera i Dzieło
  dnia o 8:30, każde do włączenia osobno. Serwer wysyła je przez Apple, więc
  przychodzą też poza domem. Raz trzeba dodać klucz APNs (AuthKey_….p8)
  z konta Apple Developer; „Wyślij próbne powiadomienie” pokazuje odpowiedź
  Apple.
- „Studia dzieł” w Odkrywaj mają też każde Dzieło dnia z napisaną stroną;
  dotknięcie otwiera stronę z jego dnia, a strzałka przy tytule otwiera
  pełne zestawienie.
- Rytm także w starych studiach: strony napisane przed „Rytmem” nie
  pokazują już trzeciego ujęcia innego rodzaju (np. „Światło”), a serwer
  w tle dopisuje do nich same rytmy.
- Legenda analizy kompozycji: dopiski pod tytułami bez podwójnych odstępów,
  a numery w takich samych kółkach ołówkiem jak na obrazie.
- Po aktualizacji aplikacji, gdy serwer jest starszy i jest dla niego nowa
  wersja, na dole pojawia się raz karta z „Aktualizuj”.

## 1.48.0

- Szukaj: pod polem pasek grup (Technika, Epoka, Styl, Kolor, Temat,
  Muzeum, Moje) zamiast „+” i jednego długiego arkusza. Każdy przycisk
  otwiera mały arkusz tylko ze swoją grupą i pokazuje, co wybrano. Epoka to
  oś czasu do stuknięcia albo przeciągnięcia, Kolor to paleta
  z przełącznikiem „Dominuje / Tylko akcent” i nastrojami, Styl i Temat
  mają pole do zawężenia listy. Ten sam pasek jest w edytorze playlist.

## 1.47.0

- Napisane studia dzieł i strony Dzieła dnia zostają na stałe: porządki
  w katalogu nie usuwają już ich dzieł, a zmiana w sposobie pisania nie
  każe Claude'owi pisać ich od nowa (ponawiane są tylko nieudane). Dzieło
  dnia i studium tego samego dzieła mają wspólną stronę.
- Analiza kompozycji: trzecie ujęcie „Rytm”, gdy obraz ma powtarzające się
  motywy; linia prowadzi przez powtórzenia z akcentem przy każdym
  i krótkim podpisem.
- Numeracja wersji od teraz 1.x (po 0.46.1 jest 1.47.0), bo TestFlight
  uznawał wersje 0.x za starsze niż dawne 1.0.

## 0.46.1

- Artysta tygodnia i inne miejsca grupujące po artyście pomijają autorów
  nieznanych i anonimowych (np. „Desconegut”).
- Z Europeany znikają zdjęcia z archiwum miasta Girona opisane jako obrazy
  i plakaty; katalog usuwa je raz po aktualizacji.
- TestFlight pokazuje numer wydania zamiast 1.0, a w „Co testować” tę listę
  zmian.

## 0.46.0

- Odkrywaj: przed „Bo lubisz” rząd „Studia dzieł” ze wszystkimi gotowymi
  studiami dzieł (ostatnio zamówione pierwsze), z dopiskiem
  „Dotychczas przyszykowane studia dzieł”.
- Karta dzieła: „Przygotuj studium dzieła” z gwiazdkami AI, bez opisu pod
  spodem. Kafelek Dzieła dnia ma strzałkę w rogu zamiast „Czytaj dalej”.
- Studium, sekcja „Dalsze losy” (dawniej „Co z niego wyrosło”): późniejsze
  dzieła z miniaturą z muzeum albo z katalogu; dotknięcie otwiera kartę
  dzieła.
- Analiza kompozycji na obrazie w pełnych kolorach, ślady ołówka z jasną
  obwódką, dopisek tuż pod tytułem uwagi; stuknięcie w obraz chowa ślady.
- Szukaj: serce na każdym kafelku zamiast „+ Zapisz”, dodaje dzieło do
  Ulubionych i od razu się zapala. Serce na karcie dzieła też zapala się
  od razu.
- Dzieła z muzeów, które pokazało Szukaj, serwer w tle dokłada do katalogu
  zamiast losowych. Artyści, których szukasz, lekko podbijają „Bo lubisz”.
- Koniec progu „przydatności na e-papier” w całej aplikacji: Propozycje,
  dobór do katalogu, Dzieło dnia, motywy tygodnia i starsze playlisty biorą
  też dzieła, które ocena wcześniej odrzucała (np. autoportret Rembrandta,
  „Straż nocna”). Ocena zostaje na karcie dzieła i do kolejności. Katalog
  przycina od najdłużej trzymanych dzieł.

## 0.45.0

- Dzieło dnia, analiza kompozycji: przełącznik ujęć bez numerów, wszystkie
  punkty pod obrazem w dwóch kolumnach, dopiski pisane odręcznie, a zdanie
  podsumowania ujęcia zwykłym pismem. Obraz pod śladami jest mniej
  rozjaśniony (w trybie ciemnym mniej przyciemniony). Ujęcie „Droga oka”
  nazywa się teraz „Spojrzenie”.
- Nowa sekcja „Detale” po „Kolor i światło”: dwa, trzy zbliżenia wycięte
  z pełnego pliku muzeum, w karuzeli do przesuwania w bok, każde z tytułem
  i krótkim opisem.
- „Przygotuj studium dzieła” na karcie każdego dzieła, pod „O dziele”:
  Claude pisze dla niego taką samą stronę jak dla Dzieła dnia. Postęp widać
  w dymku na dole, a gotowy dymek otwiera studium po dotknięciu. Studia
  zostają na serwerze, więc przycisk potem brzmi „Otwórz studium”
  (przytrzymanie: „Przygotuj od nowa”).
- Ramka → Źródła dzieł: przełącznik „Bez limitu 70 lat (tylko testy)”,
  wyłącznie do sprawdzenia, jak aplikacja będzie działać za kilka lat.
  Europeana daje wtedy także dzieła twórców zmarłych mniej niż 70 lat temu,
  opisane „Tylko do testów” z rokiem, od którego będą wolne; po wyłączeniu
  przełącznika znikają z biblioteki.
- Po aktualizacji serwer napisze tekst dzieła dnia od nowa w nowym układzie.

## 0.44.0

- Dzieło dnia, kafelek: kadr wokół twarzy albo głównego motywu dzieła,
  zajawka to jedno zdanie, które mieści się w dwóch linijkach, a „Czytaj
  dalej” stoi w wierszu autora.
- Dzieło dnia, strona: bez „O dziele” i „W skrócie”, zamiast „Kontekst”
  własny tytuł tekstu, nowa krótka notka „O autorze”, a „Na Twojej ramce”
  na samym końcu z przyciskami „Pokaż na ramce” i „Dodaj do kolejki”.
- Analiza kompozycji w nowej odsłonie: jedno do trzech ujęć (droga oka,
  geometria: złoty podział, trójpodział, trójkąty, koła) rysowanych ołówkiem
  na rozbielonym obrazie, z odręcznymi strzałkami, pętlami i numerami;
  podpisy nad i pod obrazem, tytuł pismem odręcznym. W trybie ciemnym
  białe ślady na przyciemnionym obrazie.
- Karta dzieła otwiera się od razu na całą szerokość z miniaturą, tytułem
  i autorem z kafelka zamiast czarnego ekranu z wąskim paskiem; oryginał
  doczytuje się na miniaturze, a nieudane wczytanie można ponowić.
- Po aktualizacji serwer napisze tekst dzieła dnia od nowa w nowym układzie;
  starsze teksty aplikacja nadal pokaże.

## 0.43.0

- Nowa karta Szukaj między Odkrywaj a Playlistami. Odkrywaj pokazuje już
  tylko Propozycje, bez przełącznika Propozycje/Szukaj; dotknięcie nazwiska
  artysty otwiera kartę Szukaj.
- Propozycje: kafelki motywów bez liczby dzieł i „+N”, bez rzędów „Dla
  Ciebie” i „Nowe w katalogu”, a Motyw dnia stoi zaraz pod Dziełem dnia,
  nad „Na ten tydzień”. Motyw „Arcydzieła muzeów” nie jest już pusty:
  katalog raz dziennie dociąga wyróżnione dzieła Met i Cleveland do 40.
- Kafelek Serwer w czasie aktualizacji pokazuje, z której wersji na którą
  przechodzi serwer, zamiast „0.42.0 → 0.42.0”.
- Po powrocie do aplikacji nie wyskakuje już fałszywy błąd „Serwer nie
  odpowiedział na czas”: zapytanie przerwane uśpieniem w tle idzie
  ponownie.

## 0.42.0

- Dzieło dnia: na samej górze Odkrywaj → Propozycje niski kafelek z
  obrazem, tytułem, autorem i dwiema linijkami zachęty. Po dotknięciu strona
  dzieła: „Pokaż na ramce”, dlaczego dziś, kontekst, fakty w skrócie, analiza
  kompozycji z liniami na obrazie, kolor i światło, jak wypadnie na ramce,
  podobne dzieła z katalogu, „Co z niego wyrosło” i poprzednie dzieła dnia.
  Serwer codziennie wybiera dzieło z katalogu (dobrze wypada na e-papierze,
  bez powtórek artysty przez 30 dni i dzieła przez rok), a tekst raz pisze
  Claude z obrazu, opisu muzeum, Wikidanych i Wikipedii. Przełącznik „Dzieło
  dnia” w Konfiguracji, ok. 0,10 USD dziennie we wspólnym limicie; bez klucza
  zostaje opis muzeum i podobne dzieła tego samego autora.
- Odkrywaj → Propozycje są codziennie świeże: okładki motywów losują się
  każdego dnia z 40 najlepszych dzieł motywu, a kafelek pokazuje „+N”, gdy
  w tym tygodniu doszły do niego nowe dzieła. Nowe rzędy „Nowe w katalogu”
  (najlepsze z tygodniowych nabytków) i „Dawno ich nie było” (zachowane
  dzieła niepokazywane od pół roku).
- Motyw dnia nie powtarza się przez 30 dni, motywy sezonowe wypadają
  częściej (i nigdy poza sezonem), a polskie święta i Wielkanoc mają własny
  motyw z uzasadnieniem. Nowe motywy: Jesień, Wiosna, Lato i Arcydzieła
  muzeów (wyróżnione dzieła Met i Cleveland).
- „Na ten tydzień”: co tydzień artysta tygodnia i trzy pary tematów z tego,
  co jest w katalogu, bez powtórek przez 12 tygodni.
- Nowe źródło: Statens Museum for Kunst (SMK, Kopenhaga), domena publiczna.
  Pełny katalog nadal przyjmuje 60 dzieł co 6 godzin, a przy przycinaniu
  pierwsze odchodzą starsze, niezachowane dzieła.
- Strzałka przy każdym nagłówku w Propozycjach otwiera całość jako siatkę
  w dwóch kolumnach: grupa motywów pokazuje wszystkie swoje motywy, rząd
  otwiera swój motyw albo swoje dzieła („Dla Ciebie”). Zastępuje link
  „Więcej”.
- Obrazy w kolażach pojawiają się od razu w kadrze na twarz, bez
  przesuwania po wyświetleniu. Okładki motywów w Propozycjach też kadrują
  się wokół postaci.

## 0.41.2

- Ustawienia → Prezentacja: przyciski Orientacji są teraz na górze, nad
  podglądem ramki, a Sztuka/Zdjęcia pod nim, potem Kadrowanie. Podgląd ma
  tylko taką wysokość, jakiej potrzebuje ramka, więc w poziomie nie ma pustego
  pasa, a wysokość zmienia się płynnie razem z obrotem. Zmiana tylko w
  aplikacji iOS.

## 0.41.1

- Poprawka: w 0.41.0 obrazy w całej aplikacji zostawały szare. Szukanie
  twarzy do kolaży zajmowało wszystkie wspólne wątki i pobieranie obrazów
  czekało. Teraz Vision działa po jednym obrazie we własnej kolejce, a obraz
  w kolażu pojawia się od razu i dopiero potem płynnie przesuwa kadr na
  twarz. Zmiana tylko w aplikacji iOS.
- Kafelki komunikatów na dole: czynność o nieznanej długości pokazuje tylko
  tekst i kręcące się kółko, bez biegającego paska i licznika sekund. Pasek
  zostaje tam, gdzie postęp jest znany. Zmiana tylko w aplikacji iOS.

## 0.41.0

- Podgląd w Ustawieniach → Prezentacja działa płynniej: ma stałą wysokość,
  więc przyciski Orientacji nie skaczą, a ich zaznaczenie przesuwa się.
  Zmiana orientacji obraca ramkę jak tę na ścianie. Zanim podgląd się
  wyrenderuje, widać pulsujący szkic passe-partout, opisu albo siatki Multi.
  Druga orientacja i pozostałe układy Multi wczytują się z wyprzedzeniem.
  Serwer: podgląd planszy Multi z dużych zdjęć JPEG liczy się ok. 2,7×
  szybciej.
- Widać, kto zmienił obraz na ramce: pasek wysyłania ma ikonę zegara
  (harmonogram) albo telefonu (aplikacja), a zmiana z harmonogramu przy
  otwartej aplikacji sama pokazuje pasek i podmianę. „Ostatnio na ramce”
  i „Poprzednio na ramce” mówią, kto i kiedy postawił każdy obraz. Serwer:
  `origin` w postępie, `history_marks` i `last_change_origin` w
  `/api/player`.

- Kolaże playlist (nagłówek playlisty i kafelki na Playlistach) kadrują
  obrazy wokół twarzy, a bez twarzy wokół tego, co przyciąga wzrok, zamiast
  ciąć przez środek. Każdy obraz w kolażu nagłówka otwiera swoje dzieło.
  Zmiana tylko w aplikacji iOS.

- Szacowanie baterii: serwer śledzi, co robi ramka (czuwanie, głęboki sen,
  wybudzenia, rysowanie obrazów), i z odczytów na baterii uczy się, ile
  kosztuje każda z tych rzeczy, zaczynając od pomiarów z innych ramek
  EM32DX. Kafelek Bateria pokazuje, na ile dni starczy przy obecnym
  harmonogramie (z zakresem, który zawęża się z kolejnymi odczytami), i
  otwiera rozbicie. Serwer: pole `battery` w statusie.

## 0.40.0

- Wysyłanie obrazu na ramkę widać też poza aplikacją: pasek na ekranie
  blokady i w Dynamic Island (Live Activity) z etapem, trzema częściami i
  czasem do końca; przy czekaniu na ramkę pokazuje, kiedy się obudzi. Po
  wyjściu z aplikacji pasek sam dochodzi do końca, który przewiduje serwer,
  a wynik pojawia się po powrocie do aplikacji. Nowe rozszerzenie
  FrameWidgets. Zmiana tylko w aplikacji iOS, serwer bez zmian.

## 0.39.0

- Komunikaty w aplikacji wyglądają jak pasek wysyłania: zamiast ciemnych
  dymków u góry na 2,6 s pojawiają się kafelki na dole nad zakładkami, też
  nad otwartymi arkuszami. Czynność w toku (budzenie, restart, aktualizacja
  serwera, zdjęcia i dzieła z muzeów w tle) trzyma kafelek do końca, a wynik
  pojawia się w tym samym miejscu. Potwierdzenie znika po 2,5–5 s,
  ostrzeżenie i błąd zostają do zamknięcia; wibracja i VoiceOver. Teksty są
  krótsze, z wyjaśnieniem w drugiej linii, błędy serwera po polsku. Zmiana
  tylko w aplikacji iOS, serwer bez zmian.

## 0.38.2

- Podgląd układu Multi w Ustawieniach → Prezentacja pokazuje pełną planszę
  także wtedy, gdy ramka gra playlistę dzieł sztuki. Brakujące zdjęcia
  podgląd bierze z biblioteki i z „Historii przesłanych”, za każdym razem
  te same dla danego zdjęcia. Zmiana tylko w serwerze.

## 0.38.1

- Zakładka Ramka: kafelki same są przyciskami, bez rzędu przycisków pod
  nimi. Stuknięcie w Zasilanie otwiera menu zasilania, w Sieć sprawdza stan
  ramki (kafelek pokazuje „Sprawdzam…” albo „Budzę ramkę…”), w Serwer
  aktualizuje albo sprawdza wersję; kółko w rogu kafelka mówi, co zrobi
  stuknięcie. Każda informacja pada raz: nagłówek jednym zdaniem mówi, co
  ramka robi i jak ją obudzić („Śpi w sieci · wysyłka ją obudzi”), Sieć
  podaje stan i nazwę sieci, Zasilanie źródło prądu i tryb. Zmiana tylko w
  aplikacji iOS, serwer bez zmian.

## 0.38.0

- Podgląd w Ustawieniach → Prezentacja nie znika po przełączeniu Sztuka ↔
  Zdjęcia. Gdy ramka pokazuje coś innego, podgląd bierze ostatni obraz tego
  rodzaju z historii ramki, a jeśli takiego nie było, losowy z biblioteki.
  Wysłane raz zdjęcie pokazuje się w podglądzie z ustawieniami dla zdjęć
  (nowy parametr `own_look=false` podglądu w API).
- Serwer nie bierze już pobrania `content.json` z innego komputera (np.
  przeglądarki sprawdzającej serwer) za ramkę, która opuściła aplikację.
  Liczy się tylko adres ramki; wcześniej taki odczyt gubił stan snu ramki.

## 0.37.2

- Obraz wysłany do ramki obudzonej budzikiem albo przyciskiem (na baterii)
  rysuje się do końca: aplikacja ramki zasypia najwcześniej 2,5 minuty po
  starcie, bo ramka najpierw rysuje ekran instalatora Samsunga. Wcześniej sen
  przerywał odświeżanie i obraz zostawał fioletowy.
- Koniec błędów 403 z muzeów: Art Institute of Chicago nie dostaje już próśb
  o podgląd szerszy niż sam obraz (wąskie obrazy pobieramy w pełnym
  rozmiarze), zapytania do AIC i Met idą w odstępach (API AIC raz na
  sekundę), a po odmowie ochrony przed botami serwer daje muzeum spokój na
  15 minut, za każdym kolejnym razem dwa razy dłużej, do 4 godzin.

## 0.37.1

- Ramka, której aplikacja przestała odpowiadać, nie jest już na baterii
  budzona co kilka minut przez całą noc: kolejne próby uruchomienia
  aplikacji idą coraz rzadziej (do raz na godzinę), żeby ramka mogła zasnąć.
- Gdy aplikacja milczy także 10 minut po ponownej instalacji, serwer usypia
  ramkę głęboko; przy najbliższym budziku albo po przycisku startuje ona od
  nowa i serwer uruchamia aplikację (restartu przez MDC ramka nie przyjmuje).
- Kafelek „Serwer”: „sprawdzono …” w osobnej linii, a serwer przebudowany
  w Container Manager między sprawdzeniami pomocnika nie proponuje już
  aktualizacji do wersji, która właśnie działa.
- „Uruchom ramkę ponownie” jest wyszarzone, gdy aplikacja ramki milczy
  (restart robi aplikacja, więc zamrożona by go nie wykonała); zostaje
  „Uruchom aplikację ponownie”.

## 0.37.0

- Playlista otwiera się płynnie: od razu z nagłówkiem z kafelka i dziełami
  z poprzedniego otwarcia (albo spokojnie pulsującymi kartami, gdy jeszcze
  ich nie ma), a świeże dzieła pojawiają się łagodnie. Zniknął szary pas
  wokół kółka wczytywania.
- Kafelek „Propozycje” w Playlistach otwiera stronę jak zwykła playlista,
  zamiast przeskakiwać do Odkrywaj („Otwórz w Odkrywaj” zostaje w menu).
- Zakładka Ramka mówi, gdy ekran odpowiada, a aplikacja ramki od ponad
  3 minut nie pytała o obraz: „Ekran odpowiada · aplikacja milczy od …”
  z podpowiedzią, zamiast „Połączona”.
- Kafelek „Serwer” zamiast „Obraz”: wersja serwera, a gdy jest nowsza,
  „jest X · stuknij, by zaktualizować” (sprawdza pomocnik aktualizacji).
- W menu Zasilanie „Uruchom aplikację ponownie” obok „Uruchom ramkę
  ponownie” (dawne „Uruchom ponownie”).
- Synology: pomocnik aktualizacji (`frame-updater`) montuje cały folder
  `data` zamiast `data/update`, bo Docker na Synology nie tworzy brakującego
  folderu („Bind mount failed: … does not exist”).

## 0.36.2

- Aplikacja na ramce na baterii przestawała działać: ramka odpowiadała
  („Połączona”), a wysyłka wisiała na „Budzę ramkę”. Serwer uruchamiał ją
  przez MDC w tej samej chwili, w której zasypiała, i od tego czasu żaden
  start jej nie ruszał. Serwer nie uruchamia już aplikacji, która właśnie
  zapytała albo zasypia, a gdy dwa starty z rzędu nie pomogą, instaluje
  aplikację od nowa (następna wersja paczki), co uruchamia ją na czysto.
- Nowa paczka aplikacji ramki z `background-support="enable"` (jak w
  testowej aplikacji, na której pobudki działały): Tizen nie zatrzymuje już
  aplikacji w tle. Ramka zainstaluje ją sama przy najbliższej pobudce
  (krótki restart, ok. 40 s mrugania).
- Więcej śladów w logu do dalszych testów (źródło treści przy każdym
  starcie, widoczność strony aplikacji, długość snu przy pobudce).

## 0.36.1

- Ramka odpięta od zasilacza bywa po kilkunastu sekundach znów widoczna w
  sieci (UniFi: „Ch. 0”), ale sygnał budzenia jej nie budzi. Ramka, która
  zasnęła sama zaraz po zdjęciu z zasilacza, jest więc zawsze w głębokim
  śnie, bez względu na odpowiedź ARP, i odpowiedź ARP nie zmienia już
  głębokiego snu w „Czuwanie”. Aplikacja pisze „Śpi głęboko, obudzi ją
  przycisk” zamiast „Śpi bez Wi-Fi”.

## 0.36.0

- Ramka odpięta od zasilacza zasypia od razu i bez Wi-Fi: serwer nie bierze
  jej już za śpiącą w sieci (w sieci tylko, gdy odpowiada na ARP), kafelki
  i komunikaty mówią „Śpi bez Wi-Fi, obudzi ją przycisk”, bez „Obudź ramkę”
  dla obrazu czekającego na przycisk. W takim śnie serwer co minutę szuka
  ramki przez MDC i po naciśnięciu przycisku sam uruchamia aplikację.
- Koniec ciągłego „Budzę ramkę”: wysyłka i „Sprawdź stan” uruchamiają przez
  MDC aplikację na ramce, która odpowiada, ale nie ma jej uruchomionej.
- „Teraz” odświeża się samo co 8 s, gdy obraz czeka na ramkę; pasek postępu
  rusza od pobierania przez obudzoną aplikację.
- Tryb Online na zasilaczu: aplikacja ramki trzyma zapasowe budziki na dwa
  najbliższe pełne pół godziny (np. 14:00 i 14:30), więc ramka odpięta od
  zasilacza budzi się sama, a serwer ją uruchamia i odsyła do zwykłego snu
  w sieci. Kafelki
  i „Teraz” mówią, kiedy się obudzi. Nie dotyczy trybu Oszczędnego.
- Aktualizacja serwera z aplikacji (Synology): Konfiguracja → Serwer ramki
  pokazuje wersję serwera, „Sprawdź aktualizacje” i „Aktualizuj serwer”.
  Robi to nowy kontener `frame-updater` (ten sam obraz, gniazdo Dockera,
  bez sieci): co 6 h pobiera nowy obraz, na prośbę tworzy `frame` na nowo
  z tymi samymi ustawieniami i wraca do poprzedniego, gdy nowy nie wstanie.
  Wymaga jednorazowo nowego `deploy/synology/docker-compose.yml`.
- Serwer podaje wersję dodatku (`/etc/frame-release` z budowy obrazu);
  obraz ghcr ma etykiety wersji i rewizji oraz tag z wersją dodatku.

## 0.35.0

- Prezentacja uporządkowana: dzieła sztuki bez kadru „Auto” (zapisany
  przechodzi na passe-partout), styl obrazu zawsze automatyczny (bez
  przełącznika), zdjęcia bez podpisu, szerokość passe-partout w milimetrach
  (co 5 mm), sześć kolorów passe-partout w jednym rzędzie, kwadratowe ikony
  kadrowania i siatek z zaznaczeniem wybranej, bez objaśnień trybów.
- Multi: siatki zawsze wypełniają całą ramkę (zdjęcia przycinane do okien),
  po dwie na liczbę zdjęć: „Para” i „Duży i mały”, 2×2 i „Duży i pięć”,
  nowe „Duży i cztery” i „Duży i sześć”, „Cztery nad trzema” z pierwszym
  z trzech na dwa; bez „Pion i dwa poziomy” i „Rząd pionów”.
- „Ekran” → „Orientacja”: dwie pastylki z miniaturą ramki; pion to zawsze
  ekran obrócony o 90° w prawo (zapisane 270° serwer czyta jako 90°).
- „Źródła dzieł” przeniesione pod trybik do Konfiguracji, zapisują się od
  razu po przełączeniu.

## 0.34.0

- Szukaj → „+”: sekcje w kolejności Technika, Epoka, Styl, Kolorystyka,
  Akcenty, Tematy, Muzea i nowa „Moje”: dzieła z serduszkiem
  (`mine:favorites`) albo z dowolnej innej playlisty (`mine:playlists`);
  z nimi muzea nie są pytane.
- Fotografia, Rzeźba oraz Ceramika i rzemiosło jako osobne techniki: muzea
  pytane o nie wprost, a bez ich wybrania wyszukiwanie i inteligentne
  playlisty pokazują tylko obrazy, rysunki, grafiki i plakaty.
- „Pokaż na ramce” i „Dodaj do kolejki” na karcie dzieła reagują na
  dotknięcie (wciśnięcie, wibracja, „Wysyłam…”, potem „Wysłano”), opcje
  pod przytrzymaniem; wskaźnik i wibracja także w motywach i przy
  „Prezentuj na ramce”. Nieudana wysyłka nie pokazuje już dymka sukcesu.
- Szerokie dzieła (od 2:1) zajmują w siatce cały wiersz, a panoramy nie
  wychodzą poza swoją kartę.

## 0.33.0

- Ramka → Harmonogram (Online i Oszczędny) uporządkowany: bez podtytułu
  i wiersza „Playlista” (playlistę wybiera „Prezentuj”), godziny zmian obok
  siebie jako żetony z (+), dotknięcie godziny otwiera kółko z „Usuń
  godzinę”; „Losowo” i „Cisza nocna” jako dwie pigułki w jednym wierszu
  (godziny ciszy pod nimi, też w zapisie 12-godzinnym w jednej linii),
  „Sprawdzenia” (wyłączone / co N godzin).
- Playlisty: pierwszy kafelek „Propozycje” (okładka z czterech kolejnych dzieł
  rotacji) przywraca Propozycje na ramce (`POST /api/suggestions/play`) albo
  otwiera Odkrywaj.
- Filtr techniki patrzy na rodzaj i materiał dzieła według muzeum, a nie na
  cały opis i słowa kluczowe (rysunek Moneta nie jest już „Obrazem”).
- Europeana: wyszukiwanie obejmuje tylko obrazy, rysunki, grafiki i plakaty
  (bez uprzęży, medali, znaczków czy zdjęć budynków) i pomija fotografie
  botaniczne OpenUp!.

## 0.32.1

- „Sprawdź stan” budzi śpiącą w sieci ramkę jednym naciśnięciem: gdy serwer
  wie, że ramka śpi, aplikacja od razu ją budzi (`POST /api/device/wake`), a gdy
  nie jest pewien, najpierw ją sprawdza i budzi, jeśli nie odpowiada. W głębokim
  śnie i po „Wyłącz ramkę” tylko mówi, kiedy zadzwoni budzik i że budzi
  przycisk. Przeciągnięcie w dół i wejście w zakładkę dalej tylko patrzą.
  Tylko aplikacja iOS; serwer i paczka aplikacji ramki bez zmian.

## 0.32.0

- Ramka, która zasnęła sama (np. po odłączeniu zasilacza), nie jest już brana
  za obudzoną: obudzona jest tylko aplikacja, która odezwała się w ciągu 90 s.
  „Obudź ramkę” i wysyłka obrazu budzą milczącą ramkę WoL zamiast od razu
  meldować „Ramka się obudziła”; gdy ramka odpowiada przez MDC, a aplikacja
  milczy, serwer uruchamia ją `0xC7 81 01`. Milcząca ramka bez MDC to sen
  w sieci, odczyt „zasilacz” zmienia się na „bateria”.
- Menu „Zasilanie”: „Uruchom ponownie” (`POST /api/device/restart`):
  aplikacja przy najbliższym pytaniu restartuje ramkę (`rebootDevice`),
  śpiącą w sieci serwer najpierw budzi, po starcie uruchamia aplikację przez
  MDC. Paczka aplikacji ramki bez zmian.

## 0.31.0

- Zakładka Ramka: siłę sygnału pokazują łuki ikonki Wi-Fi (żółte przy słabym
  sygnale), pod spodem nazwa sieci, tytuł „Online” zostaje; tak samo
  w Konfiguracji.
- Bateria: na zasilaczu „na zasilaczu”, na baterii liczba dni z faktycznego
  spadku (serwer zapisuje poziom co pół godziny przez 3 dni) zamiast stałych
  200 dni.
- Dopiski kafelka Zasilanie zależą od trybu pracy, kafelek Obraz mówi, kiedy
  pojawi się czekający obraz. „Sprawdź stan” budzi ramkę śpiącą w sieci
  dopiero za drugim naciśnięciem.
- Menu „Zasilanie”: „Głęboki sen” na 6 h, 12 h, 1, 2 albo 3 dni oraz „Wyłącz
  ramkę” z ostrzeżeniem (`POST /api/device/sleep?hours=N` / `?off=true`).
  Ramka śpi bez Wi-Fi, zmiany czekają do końca snu, wcześniej budzi ją tylko
  przycisk; serwer co 2 minuty szuka obudzonej ramki przez MDC. Paczka
  aplikacji ramki bez zmian (nowy `app.js` serwer podaje sam).

## 0.30.0

- Osobny limit oryginałów dzieł: Konfiguracja ma dwa wybory, „Katalog
  (miniatury)” i „Oryginały dzieł” (domyślnie 3 GB, około 2000 dzieł,
  zamiast 500 MB dzielonych 2:1). Przesłane zdjęcia i prace mają własny
  wiersz, nie liczą się do limitu i nigdy nie są usuwane. Przy przycinaniu
  oryginały z Ulubionych i playlist idą na samym końcu. Dawny jeden limit
  ustawiony w aplikacji przelicza się raz. Uwaga: `FRAME_IMAGE_CACHE_MB=500`
  w frame.env nadal ustawia domyślnie 500 MB.

## 0.29.0

- Czarne passe-partout: fazowanie ma ciemnoszary rdzeń ze światłem i cieniem,
  więc cięcie widać na ramce (`mat.BLACK_CORE`, także w trybie demo).
- „Prezentuj na ramce” od razu pokazuje pierwsze dzieło playlisty, a nie
  czekające w kolejce (np. przesłane zdjęcie); kolejka przychodzi przy
  następnej zmianie. Zapis zakładki Ramka (np. nowe passe-partout) nie
  przywraca już poprzedniej playlisty.
- „Teraz”: podczas wysyłki widać, co ramka jeszcze ma, a w czasie
  przerysowania stary obraz przechodzi w nowy kwadrat po kwadracie w sześciu
  tuszach Spectra 6, w rytm paska postępu. Ikony „Teraz” i „Pomiń” obok
  „Pokaż na ramce”; „Pomiń” cofa wybór z kolejki albo przesuwa dzieło na
  koniec rundy (`POST /api/player/skip/{id}`).
- Brakujące podglądy: oryginały odrzucane programom (Mauritshuis, Belvedere,
  Dropbox) idą przez proxy Europeany; gdy i to zawiedzie, `/image` i
  `/preview` podają miniaturę, a odtwarzacz pomija takie dzieło. Wyniki
  z hostów odrzucających nawet proxy są pomijane. Podgląd czeka do 20 s na
  polskie teksty; opis muzeum po niderlandzku, niemiecku, francusku, włosku
  czy hiszpańsku liczy się jako nieprzetłumaczony.
- Zdjęcia przesłane przez „Zdjęcie na ramkę” dostają słowa kluczowe z modelu
  (od razu przy pokazaniu lub dodaniu do kolejki, wcześniejsze w tle).
- Playlisty kolorów: kolor liczy się, gdy pokrywa co najmniej 15 % obrazu;
  mniejsze barwy to akcenty (`accent:<rodzina>`, nowy rząd „Akcenty”).
  Ciepłe/zimne według powierzchni. „W odcieniach błękitu” obejmuje turkus.
  `SCORE_VERSION` 4: biblioteka przelicza się raz w tle.
- Tryb Opis: na ramce samo nazwisko autora (bez narodowości i lat życia),
  pod spodem data · technika; bez daty powstania lata życia autora.
- CI szybciej: obrazy arm64 na natywnych maszynach z cache warstw, bez
  podwójnych przebiegów dla PR, zrzuty ekranów iOS tylko na żądanie
  (`ios-screenshots.yml`).

## 0.28.0

- Najpierw to, na co patrzysz: podgląd w „Teraz”, oryginał na karcie i
  podglądy mają własne wątki i pierwszeństwo przy pobieraniu z muzeów (dwa
  dodatkowe miejsca na hosta); miniatury siatki nie blokują już `/player`
  ani ustawień. iOS: obraz oglądany ładuje się z wysokim priorytetem we
  własnej sesji, porzucone pobrania wychodzą z kolejki, sąsiednie dzieła
  dopiero po głównym obrazie; karta pokazuje miniaturę, gdy oryginał zawiedzie.
- Model językowy odpowiada na to, czego aplikacja lub ramka potrzebuje teraz,
  na osobnym wątku, nigdy za pytaniami w tle.
- Polskie tytuły i opisy także w „Teraz” i na paskach kolejki (`/player`
  podaje `title_pl` i polskie teksty bieżącego dzieła). Angielska kopia opisu
  z muzeum nie udaje tłumaczenia: zastępuje ją tekst na ramkę, a takie
  teksty są raz odpytywane ponownie.
- „Prezentuj na ramce” szybciej widać w „Teraz”: odtwarzacz jest zajęty już
  od pobierania oryginału i od tego momentu biegnie pasek postępu.
- Tryb Oszczędny: „Sprawdzaj też co” liczy od północy (co 4 h: 0, 4, 8, 12,
  16, 20), pomija godziny zmian i nową własną „Ciszę nocną” od–do
  (`check_quiet_start`/`check_quiet_end`, domyślnie 22:00–07:00; zmiany
  nadal budzą ramkę). Nowa opcja: co godzinę. Pasek pobudek w iOS czytelny
  (cisza nocna w paski, etykiety godzin bez nakładania, zawijana legenda).
- Puste sprawdzenie nie miga ramką: aplikacja ustawia od razu budziki
  wszystkich sprawdzeń do następnej zmiany (`wakes_ms`), pamięta obraz na
  ekranie (`localStorage`) i nie rysuje go ponownie; serwer uruchamia ją przez
  MDC tylko, gdy jest coś nowego, albo przy ostatnim budziku.
- Bez podwójnego odświeżenia po wysyłce: aplikacja ramki zmienia stronę raz
  na obraz (bez „szturchnięcia” przezroczystością 0.99 → 1).
- Paczka aplikacji ramki bez zmian; nowa logika (`app.js`) wczytuje się sama.

## 0.27.0

- Ramka działa wyłącznie przez aplikację Frame (źródło Custom): serwer nie
  wysyła już obrazów przez `content.json` (tryb Mobile, MDC `0xC7 53 80`) ani
  nie usypia ramki przez MDC (budzik `0x25`, cisza nocna, lekki sen); budzi
  i usypia ją aplikacja.
- Serwer sam buduje i podpisuje paczkę aplikacji (`panel_package.py`, nowa
  zależność `cryptography`), wersje 2.0.x. Certyfikaty Samsung wgrywa się raz:
  przez File Station do `data/panel-app/certs` (`author.p12`,
  `distributor.p12`, `password.txt`) albo `scripts/panel-app/upload-certs.sh
  --server <adres>`. `pack.sh` i `PUT /api/device/app/package` usunięte.
- Ramka bez aplikacji albo wskazująca inny serwer jest kierowana z powrotem
  przez MDC (`0xC7 82 <adres>`, potem `81 01`) co 5 minut, przed wysyłką
  obrazu i przy „Obudź ramkę”; milcząca aplikacja jest uruchamiana ponownie
  do trzech razy.
- Ostrzeżenie 60 dni przed wygaśnięciem certyfikatów (27.10.2027), w zakładce
  Ramka i w Konfiguracji → Aplikacja ramki, która ma teraz „Uruchom aplikację
  ponownie”. Wybór trybu Online/Oszczędny znów widoczny.
- „Teraz”: karta „Ramka śpi” krótsza (tylko podpowiedź o przycisku), pobudka
  ramki jako „Pobudka ramki” pod „Następna zmiana”; zmiana trybu w czasie snu
  ramki pokazuje, że zadziała przy następnej pobudce (`mode_pending`).
- Kafelek „Sieć” z ikoną Wi-Fi zamiast kresek.
- Adresy domowej sieci, MAC i DUID ramki zastąpione w testach, demo,
  dokumentacji i skryptach przykładowymi.

## 0.26.0

- „Teraz”: gdy ramka śpi bez Wi-Fi (głęboki sen), karta „Ramka śpi” pokazuje,
  o której się obudzi, z odliczaniem, i że wcześniej obudzi ją krótkie
  naciśnięcie przycisku; status ramki ma `wake_at`.
- Aplikacja Frame na ramce aktualizuje się sama: gdy pyta z inną wersją niż
  wgrana paczka, `/panel/next` odpowiada `reboot` (raz na wersję), aplikacja
  restartuje ramkę (`rebootDevice`), launcher instaluje nową paczkę, a serwer
  po minucie uruchamia ją przez MDC. Paczka wgrana na obudzoną ramkę idzie
  na nią od razu.
- Wi-Fi ramki w aplikacji iOS: kafelek „Sieć” pokazuje kreski sygnału, SSID
  i pasmo, a Konfiguracja → „Połączenie z ekranem” sieć, adres i siłę
  sygnału, z ostrzeżeniem „Obca sieć”, gdy ramka weszła do innej sieci albo
  ma inny adres. Aplikacja ramki zgłasza odczyt przy każdym starcie
  i pobudce (zdarzenie `wifi` w `/panel/report`). Pełne dane wymagają paczki
  1.2.0 z uprawnieniem `network.public` (`pack.sh 1.2.0 --upload`).

## 0.25.2

- Aplikacja Frame na ramce: `sssp_config.xml` podaje `<webtype>tizen</webtype>`,
  jak oczekuje launcher Samsunga.
- Dokumentacja E16: końcowe wyniki testu aplikacji Custom. Po pełnym śnie
  launcher prawie nigdy sam nie uruchamia aplikacji (2 z 9), więc „kopnięcie”
  serwera MDC `0xC7 81 01` ok. 60 s po pobudce jest konieczne (8 z 8); przy
  wyłączonym czuwaniu sieci WoL nie budzi ramki; instalacja przez launcher
  działa bez Developer mode; po wyłączeniu zasilania ramka może wejść do innej
  zapamiętanej sieci Wi-Fi.

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
