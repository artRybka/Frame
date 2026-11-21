# Changelog

## 1.145.296

- „Szukaj zdjęciem” liczy odcisk zdjęcia na iPhonie: model pobiera się raz
  w tle, potem na serwer idzie tylko odcisk (3 KB) zamiast zdjęcia.
- Przy szukaniu zdjęciem, po dziełach z katalogu, pytane są też muzea:
  o tematy najbliższych dzieł z katalogu, bez Claude. To, co przyniosą,
  zostaje tylko wtedy, gdy wygląda jak zdjęcie.

## 1.145.295

- Szukanie wyglądem gotowe do przesiadki na SigLIP 2: progi bliskości
  ustawione na Twoim katalogu tak, by „Podobne do” pokazywało tyle dzieł co
  Gemini. Przełączenie nastąpi samo, gdy serwer policzy odciski 95% dzieł.

## 1.145.294

- Nowy ekran „Ucz kadrowania” (Konfiguracja → Diagnostyka → Kadrowanie
  zdjęć z muzeów): szybko oceniasz
  zdjęcia z katalogu, osobno malarstwo, rysunki i grafiki. Do wyboru masz
  „bez kadru”, „kadr” albo „kadr z ramą”, a powiększony róg pokazuje, czy
  rama jest. Te oceny będą danymi startowymi do douczenia modelu
  kadrowania.

## 1.145.293

- „Odżółć papier”, „Zdejmij werniks” i „Przywróć…” w menu „…” karty
  zmieniają obraz od razu, bez czekania kilku sekund na serwer.

## 1.145.292

- Menu „…” dzieła krótsze: bez „Przywróć zdjęcie muzeum” (jest na górze
  „Szukaj lepszej kopii”) i bez „Otwórz w muzeum”.
- „Zapisz w Zdjęciach” zapisuje dzieło tak, jak je widzisz: z korektą
  werniksu albo papieru, przycięte. Dzieło w ramie lub passe-partout
  można zapisać samo albo w ramie.
- „Ukryj dzieło” działa dla każdej osoby osobno, także dla Gościa. Na
  ramce nie pojawia się dzieło ukryte przez Ciebie albo Domownika.
- „Szukaj lepszej kopii” tylko dla właściciela. Kopia w pełniejszych
  barwach niż zdjęcie z muzeum nie jest już odrzucana.

## 1.145.291

- Serwer nie zawiesza się już przy otwieraniu dzieła, którego oryginał
  pobiera się długo (np. z Wellcome). Pilne pobranie dla aplikacji omija
  tylko pobieranie w tle, a za innym pilnym czeka.
- Serwer zajmuje mniej pamięci: wspólne pola dzieł w katalogu (ok. 600 MB
  mniej), model SigLIP zwalniany, gdy nie ma nic do liczenia (nigdy w
  trakcie), i oszczędniejszy przydział pamięci (`MALLOC_ARENA_MAX=2`).

## 1.145.290

- Paski barw obrazów pokazują biel: białe kryzy, obrusy i koszule, które
  dotąd wypadały za czterema głównymi barwami albo były za mało jaśniejsze
  od kremowego mazaka. Biel na pasku jest trochę bielsza, niż zmierzona,
  bo w ciemnym, ciepłym obrazie oko bierze ten krem za biel. Serwer po
  aktualizacji przelicza barwy biblioteki (na NAS-ie 1–2 godziny).

## 1.145.289

- Kadrowanie zdjęć z muzeów na iPhonie zostawia ramę tylko wtedy, gdy
  wygląda jak rama: ma wyraźny kolor albo odcina się od tła. Model
  rzadziej dodaje ramę, której nie ma.
- Grafiki są kadrowane do papieru, bez ramy, także te już na liście
  „Kadrowane”. Rysunki zostają jak dotąd.

## 1.145.288

- Wyrażenia w Słowach („parowiec na rzece”) tłumaczy teraz iPhone, więc
  kolejność według wyglądu szybciej jest właściwa. Muzea dalej dostają
  zapytania ułożone przez Haiku.

## 1.145.287

- Tłumaczenie słów w Szukaj na iPhonie naprawdę działa. Telefon szukał
  „angielskiego” ogólnie, a pobrany jest „angielski (USA)”, więc dotąd
  wszystko tłumaczył Haiku.

## 1.145.286

- „Kadrowane”: cienkie linie, rama różowa zamiast przerywanej. Dzieło,
  któremu sam zapisałeś kadr, czeka dalej na „Zatwierdź”, więc możesz
  jeszcze wybrać „Bez ramy”.
- „Do wykadrowania”: przyciski „Kadr dzieła” i „Dodaj ramę”.

## 1.145.285

- Słowa w Szukaj układają się według wyglądu także przy pierwszym
  wyszukiwaniu słowa („pies”: najpierw psy, nie polskie tytuły). Lista
  przestawia się chwilę po pokazaniu, zanim ją przewiniesz.

## 1.145.284

- Korekta barw przełączona na pełnym ekranie od razu widać też na
  miniaturach dzieła i na jego karcie: telefon podaje im obraz, który
  właśnie zrobił, zamiast czekać, aż serwer przerobi swoje pliki.

## 1.145.283

- Odżółcanie papieru na pełnym ekranie liczy telefon, tak jak werniks:
  serwer podaje mały odcisk tonu kartki, a telefon odżółca nim to, co
  widać. Przełączanie jest natychmiastowe i płynne.

## 1.145.282

- Słowa w Szukaj porządkuje teraz po wyglądzie angielskie tłumaczenie
  („koń” jako „horse”), więc na początku są konie, a nie przypadkowe
  grafiki z polskim tytułem.
- Serwer uczy się z katalogu rozróżniać formę i treść w nowych odciskach
  SigLIP. Szukaj przełączy się na nie, kiedy odciski będą gotowe.

## 1.145.281

- Lista „Kadrowane” do sprawdzania dzieło pod dziełem: każde na całą
  szerokość, w trzech widokach, z przyciskami Zatwierdź, Kadr dzieła,
  Kadr ramy i Bez ramy. Zatwierdzić można też kadr, którego model nie
  był pewny.

## 1.145.280

- Playlista z tytułem i artystą (na przykład „Paul Cezanne · Bathers”)
  znajduje też jego dzieła zatytułowane w innym języku, gdy słowo
  kluczowe jest całym tytułem: „Baigneuses” Cézanne’a trafia do
  „Bathers”.

## 1.145.279

- Werniks na pełnym ekranie: kółko korekty barw przełącza obraz od razu i
  płynnie. Werniks zdejmuje teraz telefon z tego, co widać (według liczb
  z serwera), a serwer dostaje zmianę po fakcie. Naprawione: ikona robiła
  się niebieska, a obraz zostawał z werniksem (dzieła z muzeum spoza
  biblioteki).

## 1.145.278

- Kadrowanie zdjęć z muzeów na iPhonie: ramę z modelu zostawiamy tylko
  wtedy, gdy obejmuje całe dzieło (serwer odrzuca ją też z wersji
  1.145.277). W „Popraw kadr” jest „Bez ramy”, a na liście „Kadrowane”
  „Dobrze, bez ramy”. Lista „Kadrowane” odświeża się zaraz po
  wykadrowaniu dzieła w jego karcie.

## 1.145.277

- Zdjęcia dzieł z muzeów kadruje teraz sam iPhone, własnym modelem, bez
  Opusa i Haiku. Kadr powstaje przy otwarciu karty dzieła albo partiami
  w Diagnostyce („Kadrowanie zdjęć z muzeów” → „Kadruj partię”). Gdy
  model nie jest pewny, zdjęcie zostaje całe. Wykadrowane przez model
  i czekające na kadr są w Playlistach, na liście „Kadrowane”
  (przytrzymanie → „Dobrze”). Własne dzieła kadrują się jak dotąd.

## 1.145.276

- Serwer zaczyna liczyć własne odciski wyglądu dzieł modelem SigLIP 2
  (Google, wolna licencja), bez pytania Gemini. Za pierwszym razem pobiera
  model (ok. 950 MB), potem w tle, gdy nie używasz aplikacji, przelicza
  cały katalog. Szukaj i „Podobne do” działają na razie jak dotąd;
  przełączymy je, gdy odciski będą gotowe. („Przesiadamy.”)

## 1.145.275

- Słowa wpisane w Szukaj tłumaczy teraz sam iPhone (systemowe tłumaczenie
  Apple'a, bez sieci), więc muzea za granicą dostają „guitar” za „gitara”
  od razu, bez czekania na Haiku. Haiku tłumaczy już tylko to, czego
  telefon nie umie. Za pierwszym razem Szukaj poprosi o pobranie języków.
  („1 - wdrażamy, bo warto. Przyspieszy.”)

## 1.145.274

- Werniks i odżółcanie przełączają się na pełnym ekranie od razu: druga
  wersja dzieła pobiera się w tle, gdy je oglądasz (tylko przy dziełach z
  kółkiem korekty barw). Serwer odpowiada natychmiast, a pliki dzieła i
  barwy przerabia potem; obie wersje zostają na dysku, więc kolejne
  przełączenia to odczyt pliku.

## 1.145.273

- Szukanie wewnątrz playlisty jest szybsze: podczas pisania szuka tylko
  po tekstach, a szukanie poprzedniej litery jest porzucane, więc litery
  nie stoją w kolejce. Gdy szuka, nad siatką widać kwadraciki i
  „Szukam…”. („Conajmniej trzeba dodać coś co wskazuje na proces
  przeszukiwania”)

## 1.145.272

- Kadrowanie zdjęć dzieł: naddarta albo nierówna krawędź kartki nie
  zatrzymuje już kadrowania (szkic Matejki do „Hołdu pruskiego”, MNW).
  Gdy model nie jest pewny krawędzi samego dzieła, ciemne tło fotografii
  wokół i tak jest odcinane, jeśli pasuje do tego, co widział.
- Dzieła zostawione bez kadru są sprawdzane jeszcze raz przy otwarciu
  karty.

## 1.145.271

- Nowa rola: **Gość**. Przegląda dzieła, szuka, dodaje do Ulubionych,
  tworzy własne playlisty i dodaje własne dzieła, ale nie steruje ramką:
  nie ma zakładek Teraz i Ramka, nie widzi „Pokaż na ramce”, „Do kolejki”
  ani „Prezentuj na ramce” i nie ukrywa dzieł. Jego serca nie wpływają na
  propozycje. Zaprasza się go w Konfiguracja → Domownicy („Jako gościa”).
- Domownik i gość mogą teraz „Popraw kadr”, „Zdejmij werniks”, „Odżółć
  papier”, „Kreatywny restaurator” i dodawać własne dzieła; swoje dzieła
  sami edytują i usuwają (Ty wszystkie).
- Domownik: z menu zasilania zostaje samo „Obudź ramkę”.
- Limit studiów dziennie ustawiasz każdej osobie osobno w Konfiguracja →
  Domownicy (domyślnie 3 dla domownika, 1 dla gościa).
- „Zdejmij werniks” i „Odżółć papier” to teraz ustawienie każdej osoby:
  ktoś inny w domu widzi dzieło tak, jak sam wybrał. Na pełnym ekranie
  kółko korekty barw włącza ją i wyłącza na stałe (nie tylko na podgląd).
  Ramka pokazuje dzieło tak, jak widzi je osoba, która je wysłała; w
  zwykłej rotacji tak, jak Ty.

## 1.145.270

- Szukanie wewnątrz playlisty: lupa obok „…” na stronie playlisty (także
  cudzej i albumu) otwiera pole „Szukaj w tej playliście” od razu
  z klawiaturą. Siatka zawęża się już podczas pisania, nad nią „1 z 6
  dzieł”, a gdy nic nie pasuje: „Nic nie znaleziono”; X wraca do całej
  playlisty. („Zdecydowanie lupa obok”)
- Podpowiedzi te same co w Szukaj (jedno „Słowa”, kolejność A), ale
  policzone w tej playliście: bez muzeów, wiersze bez dzieł znikają.
  Szuka wśród wszystkich dzieł playlisty i pokazuje je w jej porządku.

## 1.145.269

- Własne dzieło, krok „Opis” (i „Edytuj opis” na karcie): długi tytuł
  łamie się na kolejne linie, zamiast przewijać się w prawo i w lewo.
  Tak samo autor i data.
- Autor: po wpisaniu trzech liter pod polem pojawiają się autorzy
  wcześniej dodanych własnych dzieł, których imię albo nazwisko tak się
  zaczyna (wielkość liter i polskie znaki nie mają znaczenia); dotknięcie
  wpisuje całość.
- Rozmiar: bez napisu „Zmierzone LiDAR-em, bez ramy, ±1–2 cm” pod
  zmierzonym wymiarem (ikona linijki zostaje).
- Technika i podłoże to teraz dwa osobne pola, każde z własnym menu.
  „Technika” na karcie dzieła składa się z obu: „olej” i „płótno” dają
  „olej na płótnie”; podłoże, którego odmiany aplikacja nie zna, zapisuje
  się po przecinku, jak w muzeach („akryl, płyta HDF”). Serwer pamięta
  oba pola osobno, więc „Edytuj opis” pokazuje je tak, jak były wpisane;
  dzieła opisane wcześniej dostają oba pola odczytane z dotychczasowej
  linii („olej na płótnie” to „olej” i „płótno”).

## 1.145.268

- Szukaj: „Słowo”, „Słowo kluczowe” i „Szukaj wyglądem” to teraz jedno
  „Słowa”. Najpierw dzieła z tymi słowami w opisie, pod nimi te, które
  wyglądają tak, jak mówią słowa; liczba ma plus („9+”), bo dzieła po
  wyglądzie dochodzą chwilę później, bez skakania listy. („Słowa, słowa
  kluczowe, hasła i słowa o tym co widać - może połączyć w jedno?”)
- Podpowiedzi w kolejności A: wpisane słowa, artyści, dzieła, hasła,
  grupy, artyści z muzeów. Nowe ikony rodzajów z obwódką; „Podobne do”
  pokazuje sam tytuł dzieła, zdjęcie to „Zdjęcie”.
- Artysta z muzeów wygląda jak każdy artysta, a inaczej zapisany artysta
  z podpowiedzi („Van gogh” przy „Vincent van Gogh”) znika.
- Muzeum, które nie odpowie w 8 s, nie wstrzymuje wyników: jest pytane
  w następnej rundzie dociągania, a to, co przyniesie później, czeka
  w katalogu.

## 1.145.267

- Bateria nie liczy już snu bez Wi-Fi za darmo. Po zdjęciu z ładowarki
  ramka przez około dwie i pół doby pokazuje równe 100%, a serwer brał
  te godziny snu za dowód, że sen nic nie kosztuje. Teraz liczy od
  ostatniego odczytu 100%: sen kosztuje ok. 1% na dobę, a dzień z jedną
  zmianą obrazu ok. 2%, tyle ile ramka naprawdę zużyła 18–19 listopada.
  Kafelek pokaże ok. 6 tygodni zamiast prawie 3 miesięcy.
- „Trafność” działa przy jednej pobudce na dobę: odczyty co 24 godziny
  z kilkoma sekundami nie mieściły się w oknie doby.
- Daty pod wykresem baterii nie nachodzą już na siebie.

## 1.145.266

- Skan ekranu, na którym coś się w trakcie zmieniło, nie wychodzi już
  w plamach („Co tu się wydarzyło?”: szara smuga u góry skanu ekranu
  MacBooka, ciemny prostokąt na dole, cienie na tekście). Między
  zdjęciem na wprost a zdjęciem z prawej minęło 13 sekund i rozmowa po
  prawej stronie ekranu przewinęła się o ćwierć jego wysokości. Zdjęcie
  boczne nakładamy na pierwsze według tego, co na obu jest takie samo, a
  tu były dwie odpowiedzi prawie równej siły: nieruchoma lewa połowa i
  przewinięty tekst. Na telefonie wygrał tekst, zdjęcie legło o ćwierć
  ekranu za nisko i jego ciemne miejsca weszły do skanu jako dzieło spod
  „odbić” (zdjęte 24,6% światła).
- Zdjęcie boczne, które da się nałożyć na pierwsze na dwa sprzeczne
  sposoby, nie wchodzi teraz do skanu, tak jak zdjęcie czegoś innego.
  Skan powstaje z pozostałych: ten sam ekran wychodzi czysto.
- W skanach dzieł, które stały w miejscu, nic się nie zmienia: we
  wszystkich 49 zachowanych skanach żadne zdjęcie nie odpada (drugi
  sposób nałożenia trzyma tam najwyżej 27 punktów, 3 na każde 100
  punktów właściwego; w zdjęciu ekranu 158, czyli 57 na 100).
- To nie był skutek poprawki lampy z 1.145.262: poprzednie składanie
  daje przy takim nałożeniu ten sam obraz co do piksela.
- Skany z ostatnich dwóch tygodni zrobią się po aktualizacji serwera od
  nowa, same; zmieni się tylko skan ekranu.

## 1.145.265

- Szukaj: muzea czekają na pociągnięcie końca listy, gdy serwer znalazł
  co najmniej 12 dzieł (dotąd dopiero od 60). Przy mniejszej liczbie
  muzea szukają od razu. („Przy doszukiwaniu w muzeach - do jakiej
  ilości nie ma potrzeby gestu „podciągnięcia”…”, „Albo wiesz co - 12”)

## 1.145.264

- Pociągnięcie końca listy (Szukaj, „Podobne do”) w połowie drogi: komplet
  kwadracików po ok. 70 pt zamiast 80. („Chyba lepiej będzie gdzieś po
  środku - 70 pt”)
- Po pociągnięciu kwadraciki, które czekają na muzea (albo na dalsze
  „Podobne do”), bawią się tam, gdzie stały te zapalone: koniec listy
  zostaje podciągnięty, aż przyjdą nowe dzieła, zamiast opadać na dół
  ekranu. („kwadraciki animowane w miejscu gdzie były te do
  przeciągnięcia (teraz są zbyt nisko)”)

## 1.145.263

- Szukaj: gdy pokazane są już wszystkie dzieła z serwera, a następne
  przyszłyby z muzeów, na końcu listy stoją blade kwadraciki, jak w
  „Podobne do”. Muzea są przeszukiwane dopiero po pociągnięciu końca
  listy (albo stuknięciu w kwadraciki); dalsze strony z muzeów dochodzą
  już same. („Czy ten sam mechanizm możemy dodać do szukania gdy kończą
  się wyniki które mamy na serwerze i trzeba przeszukać muzea?”)
- Pociągnięcie jest odrobinę mocniejsze: wszystkie kwadraciki zapalają
  się po ok. 80 pt za końcem listy zamiast 60. („Może machnięcie powinno
  być odrobinę mocniejsze”)

## 1.145.262

- Skan ramki e-papier nie ma już fioletowej łatki w miejscu lampy
  („zobacz na łatkę w górnej części ekranu po zasłonięciu lampy”). Na
  matowym ekranie lampa miała szeroką poświatę, w barwach karty koloru
  liliową, i to poświata ustalała, czym zdjęcie na wprost różni się od
  bocznych. Gdy w skanie jest lampa, liczymy to teraz jeszcze raz bez
  miejsc, do których sięga jej światło: poświata schodzi razem z lampą,
  a to, co wstawiamy pod lampę ze zdjęć bocznych, ma barwę dzieła.
- Lampa nie jest przy tym szersza niż dotąd. Pierwsza wersja poprawki
  szukała jej od nowa i u Nikifora wstawiała ze zdjęć bocznych także to,
  co pierwsze zdjęcie pokazuje przez poświatę: jasne wcięcie przy
  zielonym pasie i rozmyte „W” przy ramie („Dwa nieidealne miejsca na
  Nikiforze”). Teraz oba miejsca są czyste, blady obłok obok nich
  zniknął, a jasna smuga pod lampą na odbitce też.
- Skany bez lampy wychodzą takie same co do piksela (sprawdzone na
  wszystkich 54 zachowanych skanach). Olejne z połyskiem różnią się o
  kilka poziomów w miejscu połysku.
- Karta koloru działa mocniej: jasność i kontrast idą w 3/4 drogi od
  pomiaru do tego, co zrobił telefon („tak, wolę mocniej - 3/4 w stronę
  telefonu”), dotąd w połowie. Barwy i balans bieli nadal ustala karta.
- Skany z lampą i skany z kartą koloru z ostatnich dwóch tygodni zrobią
  się od nowa po aktualizacji serwera, same.
- Dzieło leżące na stole da się zeskanować tak jak to na ścianie („może
  także gdy poziomo - np. odbitka leżąca na stole”). Gdy telefon patrzy
  w dół, pochylenie mówi czujnik: trzymany poziomo robi zdjęcie mimo
  nierównego obrysu, a gdy jest przechylony, pomocnik prosi „Trzymaj go
  poziomo, nad środkiem dzieła.”
- Aplikacja mówi serwerowi, którą wersją składania zrobiła skan. Skan z
  aplikacji starszej niż serwer zostanie po starcie serwera złożony
  jeszcze raz z zachowanych zdjęć, więc kolejność aktualizacji nie ma
  znaczenia.
- Skan z lampą trwa na telefonie o około sekundę dłużej (szacunek, czas
  odczytam z dziennika po Twoich skanach).

## 1.145.261

- „Podobne do”: pociągnięcie końca listy liczy się wreszcie od miejsca,
  w którym lista naprawdę staje. Zmierzone palcem na symulatorze: iOS
  podaje wysokość widoku już bez pasków u góry i u dołu, a aplikacja
  odejmowała je jeszcze raz, więc koniec wypadał ok. 300 pt za nisko
  (kwadraciki zapalały się przy końcu listy w połowie ekranu). Teraz
  wszystkie pięć zapala się po ok. 60 pt. („Nadal nie działa. Tzn
  zaskakuje dopiero w miejscu jak na zrzucie.”)

## 1.145.260

- „Podobne do”: pociągnięcie końca listy jest krótkie, tak jak miało być
  (ok. 60 pt za końcem, jednym palcem). Aplikacja liczyła koniec listy
  o ok. 200 pt za nisko, więc trzeba było ciągnąć przez dwie trzecie
  ekranu. Teraz uczy się, gdzie lista naprawdę staje, gdy zatrzyma się
  na końcu. („muszę przeciągnąć ekran znacząco ponad połowę ekranu”)

## 1.145.259

- Obiektyw prostuje teraz sam iPhone („prostowanie obiektywu. Czy tego
  także nie lepiej robić na iPhone?”). Serwer mówi telefonowi, czym
  prostować (zmierzona stała albo tabela z aparatu, jak w 1.145.257), a
  telefon prostuje złożony skan, zanim go wyśle. Serwer zapisuje taki
  skan tak, jak przyszedł, więc „Dodaj” nie czeka już na prostowanie
  pełnego zdjęcia na serwerze (w mojej próbie 2 s, na NAS-ie zapewne
  dłużej), a po drodze odpada jedno ponowne zapisanie JPEG.
- W „Kadrze” i na stronie „Skan gotowy” widać już obraz bez wygięcia
  obiektywu i na nim ustawiasz narożniki. Dotąd proste było dopiero
  dzieło w katalogu.
- Prostowanie na telefonie daje ten sam obraz co na serwerze, piksel w
  piksel (sprawdzone na zdjęciu 48 MP, a na mniejszych także w emulacji
  procesora takiego jak w iPhonie). Czas na samym telefonie odczytam z
  dziennika po Twoim pierwszym skanie.
- Serwer zostaje zapasem także tutaj: sam prostuje skan, który sam
  złożył, zdjęcie „Na wprost”, skan ze starszej aplikacji i dzieła
  robione ponownie z zachowanych zdjęć.
- Potrzebna jest nowa aplikacja i aktualizacja serwera. Z jedną ze
  stron starszą wszystko działa jak w 1.145.257.
- Dzieło, które nie jest prostokątem, da się zeskanować („Takiego
  zdjęcia nie mogę zeskanować - nie wykrywa jego krawędzi”, odbitka ze
  ściętymi rogami). Aparat oceniał pochylenie telefonu po kształcie
  obrysu: gdy góra i dół obrysu mają różną szerokość, prosił, żeby
  trzymać telefon prosto. Przy takim dziele obrys zawsze tak wygląda,
  więc zdjęcie nie robiło się nigdy. Teraz liczy się też czujnik
  telefonu: gdy telefon stoi pionowo (do 4°), zdjęcie się robi mimo
  krzywego obrysu. Dla prostokątnych dzieł na ścianie nic się nie
  zmienia.
- Gdy aparat widzi dzieło, a zdjęcie na wprost nie robi się przez 6
  sekund (prosi, żeby stanąć na wprost albo trzymać telefon prosto, i
  to nie pomaga), pojawia się przycisk migawki i zdjęcie można zrobić
  samemu. Dotąd migawka pojawiała się tylko wtedy, gdy aparat nie
  widział krawędzi wcale.

## 1.145.258

- „Podobne do”: pociągnięcie końca listy działa. Kwadraciki zapalają
  się już po krótszym pociągnięciu (ok. 60 pt), a gdy zapalą się
  wszystkie, puszczenie zawsze doczytuje, nawet jeśli lista zdążyła
  odskoczyć. („Działa kliknięcie w kwadraciki, ale nie przeciągnięcie”)
- Każde doczytanie w „Podobne do” jest teraz na żądanie: także kolejne
  porcje tego samego stopnia, nie tylko następny stopień. („Chyba też po
  kolejnych skokach znowu dociąga szybko, bez zatrzymania.”)

## 1.145.257

- Skan z kartą koloru też składa teraz iPhone („Czy iPhone będzie także
  obsługiwać kartę koloru”). Serwer jak dotąd znajduje kartę na pierwszym
  zdjęciu i wylicza z niej korektę barw, a telefon dostaje tę korektę,
  nakłada ją na swoje trzy zdjęcia i dopiero wtedy je składa. Wynik jest
  w barwach karty, tak jak wtedy, gdy składał serwer, tylko po kilku
  sekundach.
- Korekta na telefonie daje te same liczby co na serwerze (różnica o
  jeden poziom w jednej wartości na milion).
- Prostowanie obiektywu danymi Apple'a („a nie ma natywnego rozwiązania
  od Apple w tym zakresie?”). Aparat iPhone'a sam nie prostuje zdjęć
  głównego obiektywu, ale do każdego zdjęcia podaje tabelę, którą można
  je wyprostować. Aplikacja wysyła ją z pierwszym zdjęciem skanu, a
  serwer prostuje nią dzieło, gdy mówi ona o Twoim obiektywie to samo, co
  mój pomiar na ramach Twoich obrazów (z dokładnością do jednej
  trzeciej). Tabela jest z tego właśnie zdjęcia i zna też środek
  obiektywu, więc powinna prostować odrobinę dokładniej niż jedna stała.
  Gdy się z pomiarem nie zgadza, zostaje stała jak dotąd.
- Dla telefonu, którego obiektywu nie mierzyłem (np. inny iPhone w
  domu), tabela jest na razie tylko zapisywana przy skanie. Włączę ją
  dla takich telefonów, gdy Twoje pierwsze skany pokażą w dzienniku
  serwera, że tabela i pomiar mówią to samo. Odczytana na odwrót
  wygięłaby dzieło podwójnie i nic by tego nie wykryło.
- Potrzebna jest nowa aplikacja i aktualizacja serwera. Starsza
  aplikacja albo starszy serwer zostawiają skan z kartą serwerowi, a
  obiektyw prostują stałą, jak dotąd.

## 1.145.256

- „Podobne do”: mniej bliskie dzieła dochodzą teraz tylko na Twoje
  żądanie. Na końcu listy kwadraciki stoją blade; pociągnij koniec listy
  w górę, a zapalają się jeden po drugim (z lekkim stuknięciem), i puść,
  gdy świecą wszystkie: dopiero wtedy dochodzi kolejny stopień. Zwykłe
  machnięcie, które dobija do końca, niczego nie doczytuje. Stuknięcie
  w kwadraciki też doczytuje. („Chciałbym żeby było wrażenie faktycznego
  doczytania na żądanie.”)

## 1.145.255

- Skan własnego dzieła składa teraz iPhone („Tak, składaj na iPhonie”).
  Po trzech zdjęciach telefon łączy je sam w kilka sekund (w próbie
  3,7–5,5 s zamiast ok. 34 s na serwerze) i od razu pokazuje wynik na
  stronie „Skan gotowy”. Gotowy skan idzie na serwer w tle, a „Dalej”
  czeka najwyżej na koniec wysyłki. Kolejność kroków jest ta sama.
- Serwer zostaje jako zapas, z tym samym składaniem co dotąd. Składa
  skan z kartą koloru, skan, w którym nie znalazły się narożniki dzieła,
  i każdy, którego telefon nie dał rady złożyć albo wysłać. Nie składa
  już niczego równolegle i niczego nie porównuje.
- Gdy ustawisz narożniki szerzej, niż sięgało czyszczenie odbić, telefon
  składa skan jeszcze raz w Twoich narożnikach i pokazuje go przed
  „Dalej”. Serwer robił to dopiero przy dodawaniu dzieła.
- Zniknął pasek przy ramie i ciemniejszy brzeg tuż za narożnikami
  dzieła, widoczny w „W ramie”: wokół narożników schodzi teraz najwyżej
  tyle światła, ile przy nich. Twoje skany z ostatnich dwóch tygodni
  złożą się po aktualizacji serwera jeszcze raz.
- Biblioteka obrazu w aplikacji liczy teraz tak samo jak serwer. W
  próbie wynik z telefonu różnił się od serwerowego o jeden poziom w 8%
  wartości; po zmianie, sprawdzone na procesorze takim jak w iPhonie,
  w 0,2%.
- Potrzebna jest nowa aplikacja i aktualizacja serwera. Ze starszym
  serwerem aplikacja składa skan po staremu, na serwerze.

## 1.145.254

- „Podobne do” w Szukaj: po dojściu do końca listy pojawiają się
  kwadraciki i dochodzą dzieła mniej bliskie, za każdym razem o stopień
  dalej: najpierw od 0,50 jak dotąd, potem od 0,45, 0,40 i 0,35 (przy
  samej „Treści” i samej „Formie” odpowiednio od ich progów). („Chyba
  próg bliskości jest zbyt ostry. […] Albo po obecnym limicie dodać
  kwadraciki i doczytanie po kolejnym machnięciu?”) Na górze listy
  zostają najbliższe; playlista z wyszukiwania bierze tylko je.

## 1.145.253

- Próba składania skanu na iPhonie („Najpierw próba na iPhonie”). W
  Konfiguracja → Diagnostyka jest nowa sekcja „Składanie skanu na
  iPhonie” z przyciskiem „Zacznij próbę”. iPhone bierze z serwera Twoje
  trzy ostatnie skany, składa je sam z tych samych zdjęć, z których
  złożył je serwer, i pokazuje, ile trwał każdy i średnio.
- W Twojej kolekcji nic się nie zmienia, a skanowanie działa jak dotąd
  przez serwer. Wynik z telefonu zostaje na serwerze obok zdjęć skanu
  (znika razem z nimi po dwóch tygodniach) i posłuży do porównania
  obrazu z tym, co złożył serwer.
- Próba trwa kilka minut, bo zdjęcia w pełnej wielkości idą z serwera
  na telefon i z powrotem (ok. 220 MB na skan). Najlepiej w domowym
  Wi-Fi, z aplikacją otwartą na ekranie.
- W aplikacji jest do tego to samo składanie co na serwerze, napisane
  drugi raz dla telefonu, na tym samym OpenCV. Na procesorze Maca skan
  48 MP składał się nim w ok. 7 s zamiast 34 s na serwerze; ile zajmie
  na iPhonie, pokaże próba.

## 1.145.252

- Składanie skanu własnego dzieła trochę szybciej, z tym samym obrazem
  („Musimy się teraz zastanowić nad tym jak przyspieszyć składanie
  obrazów - teraz trwa to zdecydowanie za długo […] Nie może odbyć się
  kosztem jakości”). To pierwszy krok próby składania na iPhonie:
  odchudzone samo składanie na serwerze. Zdjęcia czytają się naraz,
  zdjęcia z boku nakładają się obok siebie, a ostatni krok (całe zdjęcie
  w pełnym rozmiarze) idzie dwoma pasami naraz.
- Sprawdzone na Twoich 48 zachowanych skanach: wynik jest ten sam co do
  piksela. W chmurze skan składa się o 2–3 s krócej (ok. 18 s zamiast
  20); ile zyskuje serwer w domu, pokaże Twój następny skan.
- Przy dwóch pasach naraz skan bierze przez chwilę ok. 0,4 GB pamięci
  więcej. Gdy serwer ma mniej niż 3 GB wolnej pamięci, ostatni krok
  idzie po kolei, jak dotąd.
- W logu serwera przy każdym skanie widać teraz, ile trwała każda część
  składania, na ilu rdzeniach i przy ilu GB wolnej pamięci. Z tego
  wyjdzie, co na Twoim serwerze naprawdę trwa najdłużej.

## 1.145.251

- „Podobne do” w Szukaj pokazuje dzieła według bliskości, a nie stałe 120
  („limitem ilości nie powinien być stopień podobieństwa?”). Wybrana
  granica „do żółtego”: przy „Treść i forma” dzieła od 0,50, przy samej
  „Treści” od 0,58, przy samej „Formie” od 0,57 (te dwie dają średnio
  tyle samo dzieł). Ustalone na 20 dziełach z całego katalogu, po 1000
  najbliższych każdego: wychodzi od ok. 18 (Mucha) do ok. 300 (Hiroshige).
- Zawsze co najmniej 8 dzieł („żeby nie pokazywać dzieł niezwiązanych”),
  także przy Twoich własnych dziełach, które na zdjęciu z telefonu leżą
  dalej od skanów muzealnych; najwyżej 1000.
- „Szukaj podobnych” na karcie dzieła i w studium liczy według tej samej
  granicy (dalej „60+” od sześćdziesięciu).

## 1.145.250

- Szukaj: okrągły przycisk „Utwórz playlistę z tego wyszukiwania” w rogu
  paska po przewinięciu listy naprawdę się pokazuje („Nie widzę okrągłego
  przycisku playlisty”). Przy otwartym szukaniu iOS chował cały pasek
  nawigacji, a z nim ten przycisk; teraz pasek zostaje (bez tytułu).

## 1.145.249

- Zakrzywienie obiektywu („Zakrzywienie obiektywu iPhone? Jakieś
  możliwości prostowania czy to bardzo skomplikowane?”). Główny aparat
  iPhone'a rysuje proste linie lekko wygięte na zewnątrz, tym mocniej,
  im bliżej brzegu zdjęcia: bok ramy wychodził wygięty o ok. 0,4% swojej
  długości. Zmierzone na krawędziach Twoich ram, tak samo na zdjęciu na
  wprost, na zdjęciach z boku i na zdjęciach z aparatu iPhone'a.
- Własne dzieło jest teraz zapisywane bez tego zakrzywienia: zdjęcie jest
  prostowane przy dodawaniu dzieła, a kadr i narożniki ramy przechodzą
  razem z nim. W „Kadrze” widzisz jeszcze zdjęcie tak, jak je zrobił
  telefon; proste jest dzieło w katalogu, „Pełny kadr” i „W ramie”.
- Prostowane są tylko zdjęcia z obiektywu, który został zmierzony
  (główny aparat iPhone'a 18 Pro Max, bez zoomu i bez przycięcia).
  Zdjęcia z innych aparatów zostają takie, jak są.
- Twoje skany z ostatnich dwóch tygodni wyprostują się same po
  aktualizacji serwera, także te, przy których wybrałeś „Na wprost”.
  Kadry i ramy zostają tam, gdzie je ustawiłeś.
- Dzieło sfotografowane ponownie jednym zdjęciem nie jest już nigdy
  składane od nowa ze starszego skanu.

## 1.145.248

- Szukaj bez tytułu „Szukaj” (ani na górze, ani w pasku) i bez zdania pod
  „Treść / Forma”. Po przewinięciu wyników w prawym rogu paska jest
  okrągły przycisk „Utwórz playlistę z tego wyszukiwania”.

## 1.145.247

- Duży tytuł „Odkrywaj” zostaje szeryfowy także po wejściu w studium
  dzieła i powrocie (wracał w zwykłym foncie systemowym). Sama aplikacja.

## 1.145.246

- Studium dzieła ma pod „Podobnymi dziełami” ten sam przycisk
  „Szukaj podobnych” co karta dzieła: otwiera Szukaj z dziełami
  podobnymi do studiowanego.
- „Podobne do” w Szukaj ma nagłówek z miniaturą dzieła (albo zdjęcia),
  tytułem i krzyżykiem, a zamiast „Temat i styl / Temat / Styl” dwa
  przełączniki „Treść” i „Forma”, oba włączone na start.

## 1.145.245

- Karta koloru („Dlaczego karta kolorów nie jest tu wykrywana?”,
  „Podobny problem.”). Karta była na Twoich zdjęciach znajdowana, ale
  odrzucana jako nieczytelna. W ciemnym pokoju jej czarne pole wyszło na
  zdjęciu zupełnie czarne (zero), a pod lampą na stole dwa najjaśniejsze
  pola były prześwietlone. Teraz takie pola są pomijane i karta jest
  czytana z pozostałych szarości (co najmniej czterech z sześciu).
- Przy prześwietlonej karcie to, co na zdjęciu jest prześwietlone,
  wychodzi neutralnie białe, a nie kremowe.
- Twoje dzisiejsze skany, w których karta nie została odczytana, zrobią
  się same jeszcze raz z kartą po aktualizacji serwera.
- Gdy serwer widzi kartę, ale jej nie odczyta, zapisuje to w logu
  (wcześniej nie zostawał żaden ślad).
- „W ramie” przy własnym dziele („Podwójny obraz po wyświetleniu ramy”,
  „Out of the box”). Dzieło jest pokazywane w proporcjach z wpisanego
  wymiaru, a zdjęcie ramy pod nim miało proporcje ze zdjęcia, więc przy
  lewej i prawej krawędzi wystawał spod dzieła ten sam obraz ze zdjęcia
  ramy. Teraz zdjęcie ramy dostaje proporcje dzieła i otwór ramy leży
  dokładnie pod nim. Dzieła z ramą poprawią się same po aktualizacji;
  po zmianie wymiaru w opisie rama idzie za dziełem.

## 1.145.244

- Własne dzieła, skan za szybą (Twoje „Test” i „Test 4”). Lampa i Twoja
  sylwetka w szybie na pierwszym zdjęciu myliły serwer co do jasności
  i barw zdjęć z boku: po lampie zostawała blada plama z zielonymi
  kreskami, a sylwetka w ogóle nie schodziła. Teraz jasność zdjęć z boku
  jest liczona z kresek wspólnych z pierwszym zdjęciem.
- Dzieło za szybą, w którym jedno zdjęcie z boku ma w szybie cały jasny
  pokój, nie jest już brane za „niepłaskie”: aplikacja proponuje skan,
  a nie jedno zdjęcie. Kolaż z lustrem i folią zostaje jak był.
- Po zdjętej sylwetce nie zostaje już ostry obrys, a lampa sięgająca
  ramy schodzi do końca (zostawała jej końcówka z prostym cięciem).
- Wklejki pod lampą i w miejscach mocnych odbić mają teraz szczegóły
  w pełnej rozdzielczości zdjęć z boku (12 MP), a nie w zmniejszeniu:
  kreski są wyraźnie ostrzejsze. Nie będą tak ostre jak reszta skanu
  z pierwszego zdjęcia (48 MP).
- Wtapianie („Teraz nadal widać odcięcie”, „tonacja i kolorystyka na
  łączeniu”). Pod półprzezroczystym odbiciem w szybie (jasne drzwi nad
  lewą częścią nieba na „Test 4”) dzieło zostawało bledsze niż obok,
  z krawędzią odbicia pośrodku. Teraz ton i barwa takich miejsc są
  brane ze zdjęć z boku i wyrównane do otoczenia, aż do samej ramy,
  a pod odbiciem tak jasnym jak samo dzieło ze zdjęć z boku jest cały
  obraz (drzewo przecięte krawędzią odbicia jest całe). Oleje pod
  werniksem zostają jak były.
- Karta koloru: skan z kartą wychodził „blado i mdło”, bo wzornik
  ustawiał też jasność i kontrast, a to dawało pomiar, nie obraz. Teraz
  barwy są z wzornika, a jasność i kontrast w połowie drogi między
  wzornikiem a telefonem („Wyważone, pół na pół”). Twój skan z kartą
  zrobi się sam jeszcze raz.
- Aplikacja: zdjęcia z boku dostają balans bieli pierwszego zdjęcia
  (wychodziły chłodniejsze). Do sprawdzenia na Twoim następnym skanie.
- Aplikacja: droga na bok wypełnia się na planie na zielono, w miarę jak
  idziesz, jak przy pierwszym skanie Face ID.
- Twoje skany z ostatnich dwóch tygodni przerobią się same po
  aktualizacji serwera.

## 1.145.243

- „Podobne do” w Szukaj i „Podobne wyglądem” w karcie znów odpowiadają
  od razu: z nowymi odciskami każde pytanie (także przełączenie „Temat” /
  „Styl”) trwało ok. 8 s, bo serwer liczył styl i temat wszystkich dzieł
  od nowa. Teraz liczy je raz, w tle, i trzyma gotowe (pytanie ok. 0,2 s).

## 1.145.242

- Margines kartki działa jak rama. Odbitki, rysunki i ilustracje, które
  muzeum sfotografowało z marginesem kartki, są pokazywane bez niego
  (w karcie, na liście i na ramce), a całą kartkę pokazuje przycisk
  z ikoną passe-partout obok „Oryginał / Na ramce”, ten sam co przy
  obrazach w ramie. Przełącznik „Z marginesem” w „Pełnym kadrze” zniknął.
- „Popraw kadr” przy takiej odbitce ma „Dzieło / Kartka”: drugie
  narożniki ustawiają krawędź kartki pokazywanej przyciskiem.
- Gdy serwer zna tylko kartkę, Opus dopytuje o samą odbitkę: przy
  otwarciu karty od razu, a w nocy do 150 dzieł (ok. 1 centa za dzieło).
  Dzieła z wcześniej wybranym „Z marginesem” przechodzą na widok bez
  marginesu przy pierwszym nocnym przejściu albo przy otwarciu karty.
  Gdy podpis lub tytuł na marginesie jest częścią dzieła, kartka zostaje
  w całości.

## 1.145.241

- Własne dzieła, skan: „jeden łuk”. Po zdjęciu na wprost znaczniki na
  narożnikach dzieła są od razu (bez „Przypinam znaczniki” i stania
  w miejscu), a Ty idziesz łukiem w lewo albo w prawo, w dowolnej
  kolejności. Zdjęcie z boku robi się samo, gdy zwolnisz na jasnym pasie
  planu (22–38° od dzieła, jak dotąd); pas robi się zielony, a aparat
  prowadzi na drugą stronę. Wystarczy, że całe dzieło jest w kadrze, nie
  trzeba już trafiać jego środkiem w celownik. U góry „Krok 1 z 2”
  i „Krok 2 z 2”.
- Haptyka przy skanie: w drodze na bok telefon tyka coraz szybciej
  i mocniej, im bliżej miejsca zdjęcia (zaczyna, gdy ruszysz w dobrą
  stronę, milknie, gdy stoisz albo wracasz), a każdą zrobioną stronę
  potwierdza osobnym sygnałem.
- Po drodze aparat robi po cichu jeszcze jedno zdjęcie z każdej strony,
  z mniejszego kąta. Skan składa się jak dotąd z trzech zdjęć (na wprost
  i z każdej strony to najbliższe 30°), a dodatkowe serwer tylko
  przechowuje ze skanem, żeby sprawdzić na Twoich dziełach, czy mniejszy
  kąt też wystarczy. Aplikacja robi je dopiero przy serwerze w tej wersji.

## 1.145.240

- Własne dzieła, skan z trzech zdjęć: po pierwszym zdjęciu aparat
  przypina znaczniki do narożników dzieła (AR). Idąc w bok widzisz je
  cały czas na dziele, także wtedy, gdy samo wykrywanie krawędzi by je
  zgubiło, a kropka na planie pokazuje dokładne miejsce telefonu
  względem dzieła, nie zliczone obroty. Zdjęcia z boku mają w tym trybie
  12 Mpx (pierwsze, z którego są wszystkie szczegóły, zostaje w pełnej
  jakości). Gdy przypięcie się nie uda, aparat działa jak dotąd.

## 1.145.239

- Szukaj w katalogu: dzieło zatytułowane dokładnie tak, jak wpisane słowo,
  jest pierwsze, a potem dzieła z tym słowem w całości. Dopiero dalej są
  te, w których słowo tylko tak się zaczyna. „Szał” daje najpierw obraz
  Podkowińskiego, a nie ptaki Szalewskiej i damy w szalach. „Czwórka”
  daje obrazy Chełmońskiego przed kartami do gry.

## 1.145.238

- Własne dzieła, aparat: płótno bez ramy jest znajdowane także na
  zdjęciach z boku. Dotąd aparat szukał samych prostokątów i przy takim
  płótnie nie znajdował nic (miękka krawędź na tle ściany, mocne linie
  w samym obrazie), więc zdjęcia z boku trzeba było robić ręcznie.
  Teraz tam, gdzie prostokątów nie ma, dzieło wskazuje drugi sposób
  Apple (ten od skanowania dokumentów). Przy dziełach w ramach bez zmian.

## 1.145.237

- Odkrywaj: kafelki „Studia dzieł” są szersze, 280 pt zamiast 172: na
  ekranie mieści się jedno studium i spora część następnego. Obrazek ma
  tę samą wysokość, a na szerszym kafelku wchodzi ostry oryginał, jak na
  kafelku studium dnia.

## 1.145.236

- Nowe odciski wyglądu (temat i styl) robią się mniej więcej dwa razy
  szybciej: serwer trzyma u Google więcej paczek naraz i zagląda po
  odpowiedzi co pół minuty zamiast co dwie.

## 1.145.235

- Studium dnia to głównie malarstwo: po dniu grafiki lub rysunku przez
  cztery kolejne dni kurator wybiera tylko spośród obrazów. Grafika
  zostaje, ale najwyżej raz na pięć dni.

## 1.145.234

- „W ramie”: samo dzieło jest zawsze tym samym obrazem, w swoich
  proporcjach, a rama to osobna warstwa pod nim. Na pełnym ekranie dzieło
  stoi w miejscu i tylko rama płynnie się pojawia albo znika. Na karcie
  nie ma już przeskoku obrazu na końcu powrotu z ramy.

## 1.145.233

- Szukaj: wyniki z muzeum idą do aplikacji od razu, a dzieła, które nie
  pasują, trafiają do katalogu dopiero potem. Wcześniej odpowiedź czekała,
  aż serwer przejrzy cały katalog, i „Bociany” Chełmońskiego przyszły
  półtorej minuty po odpowiedzi muzeum. Liczenie miejsca na „Sztuki inne”
  robi jeden wątek naraz, nie każde muzeum osobno.
- Polskie muzea dostają słowa i tytuły wpisane w innym języku po polsku
  („The Storks” z podpowiedzi to w Warszawie „Bociany”), a dzieło z
  polskim tytułem pasuje do takiego szukania.
- Log: gdy zapytanie aplikacji czeka dłużej niż 15 s, zapisuje się, co
  robią wtedy wątki serwera.

## 1.145.232

- Pełny ekran: dzieło na cały ekran zostaje takie samo po włączeniu ramy
  (rama jest poza ekranem). Przy wyłączeniu ramy, gdy dzieło w ramie jest
  mniejsze od ekranu, widok najpierw płynnie zbliża się, aż dzieło wypełni
  ekran, i dopiero wtedy rama znika. Przenikanie bez chwilowo
  powiększonego obrazu. Dzieło otwarte „W ramie” wypełnia ekran od
  początku (na pełną wysokość), jak samo dzieło.
- „W ramie” działa też dla dzieła po „Restauracji dzieła”: rama z
  oryginalnego zdjęcia, w środku rysunek restauratora (wcześniej rama
  znikała).

## 1.145.231

- „Podobne do” w Szukaj można zawęzić do tematu albo stylu: pod chipem jest
  przełącznik „Temat i styl | Temat | Styl”, także przy szukaniu zdjęciem.
  Temat łapie to, co przedstawia dzieło (Ukrzyżowanie w temperze, grafice
  i oleju), styl to, jak jest zrobione (technika, pędzel, światło, paleta).
  Serwer robi każdemu dziełu nowe odciski przez Batch (ok. 30 USD za cały
  katalog z limitu Gemini, kilka dni). Do tego czasu wszystko działa jak
  dotąd, a po 95% przełącza się samo; stare odciski zostają na dysku.
  Playlisty z „Szukaj zdjęciem” sprzed przełączenia trzeba wtedy wyszukać
  zdjęciem jeszcze raz.
- Długi tytuł w chipie „Podobne do: …” kończy się wielokropkiem.

## 1.145.230

- Pełny ekran: przycisk ramy przełącza płynnie, a dzieło zostaje w tym
  samym miejscu i powiększeniu. Gdy rama byłaby niewidoczna albo samo
  dzieło za małe, obraz delikatnie dojeżdża do całości.

## 1.145.229

- Skan własnego dzieła z trzech zdjęć: przełącznik „Na wprost /
  Inteligentne” jest teraz po każdym skanie. Gdy dzieło nie wygląda na
  płaskie (płaskorzeźba, kolaż z lustrem), skan i tak jest składany, ale
  domyślnie wybrane jest zdjęcie na wprost. Wcześniej takie dzieło
  zostawało bez wyboru. Wymaga nowej wersji aplikacji.

## 1.145.228

- Zadania ułożone według tego, co robią: Katalog, Obraz, Opisy i fakty,
  Odkrywaj. Prace samego serwera stoją w tych samych grupach (z ostatnim
  przebiegiem i ▶), a to, co robi AI, ma iskierkę. Osobna strona „Prace
  serwera co noc” zniknęła z Zadań; na dole „Cała noc” uruchamia wszystko.
- Przy pozycjach tylko nazwa i koszt z ostatnich dni, bez opisów.
- „Odkrywaj”: dwa przełączniki, „Studium dnia” i „Propozycje kuratora”.
  Fakty z sieci, „Jak powstawał” i „Droga dzieła” są częścią studium i
  działają zawsze.
- „Porządki katalogu” (strażnik i sędzia powtórek): co noc, tylko na
  żądanie albo wyłączone, z „Uruchom teraz”.
- „Kadrowanie” i „Przegląd dzieł” to po jednym zadaniu: porcja co noc i
  więcej z resztki na koniec okresu („Większy nocny przegląd” i „Więcej
  kadrowania” weszły w nie), albo tylko koniec okresu, tylko na żądanie,
  wyłączone. „Przegląd dzieł” ma „Uruchom teraz”.
- „Polskie opisy” obejmują przegląd starszych tłumaczeń (dawny „Przegląd
  zapisanych opisów”). „Uzupełnienie studiów” pokazuje się tylko, gdy
  jakieś studium czeka na fakty z sieci.
- „Odciski wyglądu” (Gemini) jako przełącznik w grupie Obraz.

## 1.145.227

- Suwak balansu bieli przy własnych dziełach wygląda prościej: okrągły
  uchwyt między chmurką (chłodniej) a słońcem (cieplej), bez napisów i bez
  przycisku „Wyzeruj”. Środek, czyli zdjęcie bez zmian, lekko przyciąga
  uchwyt i stuka pod palcem. Sama aplikacja; serwer bez zmian.

## 1.145.226

- W trybie oszczędnym ramka budziła się ok. 10 minut po wieczornej zmianie
  jeszcze raz i rysowała ten sam obraz od nowa. Budził ją dzienny przegląd
  ekranu Samsunga, który przez przesunięty budzik wypadał tego samego
  wieczoru. Serwer rozpoznaje tę pobudkę i nie uruchamia aplikacji ramki,
  więc obraz nie jest rysowany drugi raz, a ramka sama wraca do snu.

## 1.145.225

- „Popraw kadr”: przełącznik „Dzieło / Rama”. W „Rama” ustawiasz narożniki
  zewnętrznej krawędzi ramy albo passe-partout, a „W ramie” w karcie
  pokazuje zdjęcie przycięte tak, jak je ustawiłeś. Twoja rama zostaje
  także po ponownym kadrowaniu dzieła; samo przesunięcie ramy nie zmienia
  obrazu na ramce ani barw.
- Przycisk „W ramie” ma nową ikonę: passe-partout z małym obrazem w środku.

## 1.145.224

- Karta dzieła: obok „Oryginał / Na ramce” okrągły przycisk z ikoną ramy,
  gdy muzeum (albo Ty) sfotografowało dzieło w ramie, w passe-partout,
  albo grafika jest pokazana bez marginesu. Pokazuje zdjęcie przycięte do
  zewnętrznej krawędzi ramy i wyprostowane, z płynnym odjazdem od samego
  dzieła. Na ramkę i do barw idzie nadal samo dzieło. Starsze kadry
  dowiadują się o ramie same, nocą albo przy otwarciu karty.

## 1.145.223

- Inteligentna playlista: szare rysunki z WikiArt (np. „The Mathematicians”
  de Chirico) trafiają już do katalogu. WikiArt każde dzieło nazywa
  obrazem, więc ołówkowy rysunek bez koloru był brany za czarno-białą
  kopię obrazu i odrzucany, choć Szukaj i edycja playlisty go pokazywały.
  Szare dzieło z WikiArt jest kopią tylko wtedy, gdy jego technika mówi o
  farbie.
- „Zapisz” w edycji inteligentnej playlisty od razu bierze do katalogu
  dzieła z muzeów pokazane w niej bladziej, także gdy katalog ma już dość
  dzieł dla tej playlisty. Wcześniej czekały w kolejce tła, które stoi,
  gdy używasz aplikacji, i nie trafiały na playlistę od razu.

## 1.145.222

- Teksty w aplikacji i opis na ramce nie zostawiają już jednoliterowych
  słów (i, w, z, a…) na końcu wiersza; inicjały zostają z nazwiskiem,
  „1868 r.” i „XIX wieku” się nie rozdzielają, a myślnik nie zaczyna
  wiersza. Wymaga nowej wersji aplikacji.

## 1.145.221

- Własne dzieło bez wzornika barw: po kadrowaniu jest teraz strona ze
  zdjęciem i suwakiem „Balans bieli” (chłodniej, cieplej, „Wyzeruj”).
  Obraz zmienia się na żywo, a serwer zapisuje dzieło w ustawionym
  balansie; zostaje on także wtedy, gdy skan jest składany od nowa po
  aktualizacji. Ze wzornikiem barw nic się nie zmienia. Wymaga nowej
  wersji aplikacji.

## 1.145.220

- Skan własnego dzieła: zdjęcia z boku są teraz nakładane na zdjęcie na
  wprost dokładnie, kawałek po kawałku, a nie jednym przekształceniem
  całej płaszczyzny. Na małym obrazie olejnym z grubą farbą leżały obok
  nawet o 22 piksele, przez co kontury wychodziły podwójne, a jasna
  farba szarzała; teraz zostaje około dziesiątej części piksela. Ostrzej
  wychodzą też grafiki za szkłem. Skany z ostatnich 14 dni przerobią się
  same kilka minut po aktualizacji.

## 1.145.219

- Zadania: „Słowa kluczowe i polskie opisy” to teraz dwa osobne zadania,
  „Słowa kluczowe katalogu” i „Polskie opisy katalogu”, każde z własnym
  „kiedy”, liczbą na noc, kwotami, trybem i „Uruchom teraz”. Dotychczasowe
  ustawienia, miejsce na liście i wyłączenie przechodzą na oba.

## 1.145.218

- Ekran poprawiania kadru: tykanie przy wolnym przeciąganiu wreszcie
  działa (wcześniej nie odzywało się wcale), coraz gęstsze, im wolniej
  idzie palec. Pod lupą nie ma już etykietki „na krawędzi”; przyciągnięcie
  do krawędzi czuć samym stuknięciem.

## 1.145.217

- Własne dzieła: po aktualizacji, która zmienia łączenie zdjęć skanu,
  serwer sam składa wcześniejsze skany od nowa z trzech zdjęć, które
  trzyma przez 14 dni, i podmienia obraz dzieła. Kadr i opis zostają.
  Po tej aktualizacji przerobi tak raz wszystkie skany z ostatnich
  14 dni (kilka minut po starcie, w tle).

## 1.145.216

- Skan („Inteligentne”): krawędź fragmentu wstawionego ze zdjęć bocznych
  w miejscu lampy jest wtopiona w otoczenie. Fragment wychodzi trochę na
  zewnątrz i zanika stopniowo, a jego ton przechodzi w ton zdjęcia na
  wprost, więc nie zostaje obrys lampy ani świetlówki. Na dziełach w
  passe-partout fragment nie przechodzi przez krawędź odbitki.

## 1.145.215

- Ekran poprawiania kadru: narożnik zwalnia dopiero przy naprawdę
  wolnym ruchu palca (poniżej ok. 90 pt/s, a do ¼ przy kilku pt/s),
  przejście jest stopniowe i rozłożone w czasie, bez skoku. Zniknęła
  etykietka „wolno: ¼” pod lupą. Stukanie przy zwalnianiu jest teraz
  wyraźnym „tyknięciem” jak przy kółku wyboru, coraz gęstszym, im wolniej
  idzie palec.

## 1.145.214

- Odkrywaj → „Kolor i nastrój”: karty pokazują tylko malarstwo, bez
  rysunków, akwarel, grafiki, kaligrafii, rzeźby i zdjęć. Playlisty
  zrobione wcześniej z tych kart raz tracą rysunki i dopełniają się
  już tylko obrazami.

## 1.145.213

- Konfiguracja → Zadania: jedno miejsce na wszystko, co robią Claude i
  serwer. Na górze pasek okresu: wydane, zamówione, wolne i zapas. Niżej
  zadania według pory: „Od razu” i „Przy studium” (przełączniki opisów,
  słów kluczowych, faktów z sieci…), „Co noc” (strażnik, sędzia
  powtórek, kadrowanie, przegląd), „Z resztki okresu”, „Tylko na
  żądanie”, „Wyłączone” i „Bez Claude” (prace serwera, dawne „Zadania
  nocne”). Przy każdym zadaniu chipy: kiedy, tryb, ile na noc.
- Zadania resztki (opisy katalogu, studia, kadrowanie, uzupełnienie
  studiów, przegląd opisów, większy przegląd) mają własną stronę: kiedy
  (w ostatnich dniach okresu, co noc, tylko na żądanie, wyłączone), ile
  dzieł na noc, kwota na noc i na okres (pierwsze, co się skończy,
  zatrzymuje zadanie), tryb (Batch za pół ceny albo Zwykły, od razu, z
  ceną za dzieło) i „Uruchom teraz za…”. Zadanie ustawione „co noc”
  działa przez cały okres, nie tylko w jego ostatnich dniach; w trybie
  Zwykłym serwer nocą pyta od razu, do kwoty i liczby na noc.
- Strona Claude ma już tylko limit, koszty, okres i zapas.

## 1.145.212

- Skan („Inteligentne”): fragment odzyskany ze zdjęć bocznych w miejscu
  lampy jest dopasowany do otoczenia. Kreski są tak mocne jak wokół (nie
  czarne wśród bladych), papier ma ten sam odcień co obok, a blady rąbek
  lampy też jest brany ze zdjęć bocznych. Na dziełach w passe-partout
  nie zostaje jasne wcięcie przy krawędzi odbitki obok lampy.

## 1.145.211

- Bez akt z archiwów udających dzieła. Pliki Archiwów Narodowych USA,
  które trafiły do Wikimedia Commons jako „obrazy” (puste niemieckie
  kwestionariusze „Fragebogen” z 1943 roku, zdjęcia samolotów
  Departamentu Obrony, poligon w Nevadzie), mają teraz własny powód
  „akta z archiwum państwowego” i nie wchodzą nigdzie: ani do katalogu,
  ani do wyników Szukaj, ani z wybranej kategorii Commons. Zdjęcie albo
  obraz, którego autorem archiwum podaje osobę, a nie urząd, zostaje.
  Listy i wiersze na osobnej kartce (Rijksmuseum „letter”, „poem”) są
  dokumentami jak inne kartki z tekstem. Rękopisy iluminowane, kaligrafia,
  plakaty i listy z rysunkiem zostają.
- Po aktualizacji serwer raz usuwa z katalogu takie akta i dokumenty,
  które sam kiedyś dobrał (na katalogu z 13 listopada 41 pozycji).
  Zachowane przez Ciebie (serce, playlista, ramka) zostają.

## 1.145.210

- Skan („Inteligentne”) dzieła za szybą, trzy poprawki po rysunku w
  szerokim passe-partout: lampa wypalona w zdjęciu na wprost znika cała
  także wtedy, gdy jedno ze zdjęć bocznych ma w tym miejscu odbicie okna
  (zostawała zielonkawa plama); własna sylwetka odbita w szybie nie
  zostaje na papierze jako ciemniejszy kształt z jasnym obrysem; przy
  brzegu dzieła nie zostaje blady pas odbicia, gdy zdjęcie boczne
  pokazuje dzieło aż do brzegu. Pod jasnym odbiciem kreski rysunku są
  brane ze zdjęć bocznych, więc nie bledną.

## 1.145.209

- Konfiguracja → Claude → „Na co, w tej kolejności”: pod „Słowa kluczowe i
  polskie opisy” oraz „Kadrowanie zdjęć dzieł” jest „Uruchom teraz…”.
  Podajesz kwotę (np. 50 USD), a serwer od razu, w trybie zwykłym (bez
  Batch, po pełnej cenie), pyta Claude dzieło po dziele, najpierw o
  Ulubione i playlisty. Działa, aż wyda kwotę albo skończy się kolejka;
  pod pozycją widać pasek, ile dzieł zrobił i ile wydał, i przycisk
  „Zatrzymaj”. Nie przekracza miesięcznego limitu ani zapasu, a noc w tym
  czasie nie zamawia tego samego przez Batch.

## 1.145.208

- Ekran poprawiania kadru: zaraz pod dziełem okrągły przycisk z
  magnesem włącza i wyłącza przyciąganie narożnika do krawędzi zdjęcia
  (domyślnie włączone, aplikacja pamięta wybór). Dokładne, wolne
  celowanie wchodzi i schodzi płynnie, bez przeskoku, a gdy przeciąganie
  zwalnia, telefon lekko stuka, coraz szybciej, im wolniej idzie palec.

## 1.145.207

- Miniatura idzie za obrazem karty. Gdy serwer pobiera oryginał dzieła z
  innego miejsca niż muzeum (na przykład z Wikimedia Commons, kiedy
  muzeum nie odpowiada) i to jest inne zdjęcie niż miniatura (bez ramy,
  inaczej skadrowane), robi miniaturę na nowo z tego oryginału. Aplikacja
  dostaje o tym znać i listy, Odkrywaj oraz playlisty pokazują od razu
  to samo zdjęcie co karta. Tak zostawała stara miniatura w złotej ramie
  przy „Paysage italien au tombeau” Géricaulta. Po aktualizacji serwer
  raz przegląda miniatury dzieł, których oryginał już ma, i poprawia
  takie, które pokazują inne zdjęcie.

## 1.145.206

- Konfiguracja: liczba przy „Do sprawdzenia” zgadza się z listą. Liczyła
  też uwagi o dziełach, których już nie ma w bibliotece (połączone z inną
  kopią albo usunięte), a lista ich nie pokazuje.

## 1.145.205

- Skan („Inteligentne”) dzieła za szybą: miękkie, daleko sięgające
  przejścia przy odbiciach. Wokół miejsca, w którym zdjęcie na wprost
  miało własne odbicie (dłoń, smuga, blask), obraz bierzemy ze zdjęć
  bocznych, a ze zdjęcia na wprost zostaje sam drobny szczegół: na
  gładkim tle szeroko i stopniowo, przy literach i rysunku ciasno. Po
  palcach nie zostają już jasno-ciemne kreski ani ciemne kliny między
  nimi, a na oleju ciemne krążki i blade plamy po blasku.
- „Dodaj własne dzieło”: gdy obok dzieła leży wzornik barw ColorChecker
  (Classic, Classic Mini albo strona „Classic” w Passport), serwer
  ustawia według niego balans bieli, jasność i barwy zdjęcia, także przy
  skanie z trzech zdjęć. Pod kadrem stoi wtedy „Barwy ustawione według
  wzornika.”. Bez wzornika wszystko działa jak dotąd.

## 1.145.204

- Ekran poprawiania kadru (także przy skanie własnego dzieła): zdjęcie
  jest tak duże, jak się mieści, bez czterech lup w rogach. Narożnik
  chwyta się obok niego i idzie za ruchem palca, a przy wolnym ruchu
  przesuwa się o ćwierć, więc łatwo trafić co do piksela. Na czas
  ciągnięcia nad palcem pojawia się lupa. Gdy narożnik trafi na wyraźną
  krawędź (rama, brzeg kartki), telefon stuka i narożnik lekko do niej
  przylega; dalszy ruch go odrywa.

## 1.145.203

- Skan („Inteligentne”) dzieła za szybą: odbicie dłoni i smugi schodzą
  także z rysunku i z ciemnego tła, a nie tylko z gładkich miejsc obok;
  po wyjętej lampie nie zostaje ciemny pierścień. Obrazy olejne bez zmian.

## 1.145.202

- „Skan gotowy” bez pionowego suwaka: przełącznik „Na wprost” |
  „Inteligentne” (domyślnie „Inteligentne”), wybrana wersja płynnie
  zastępuje drugą.
- „Zrób zdjęcie ponownie”: po „Dalej” ekran zamyka się od razu. Serwer
  wycina i zapisuje nowe zdjęcie w tle (około 6 s), karta dzieła pokazuje
  w tym czasie „Zapisuję nowe zdjęcie…” i sama podmienia obraz.
- Skan („Inteligentne”) odrobinę głębszy: z równej poświaty światła na
  dziele zostaje trochę mniej niż dotąd.

## 1.145.201

- „Skan gotowy”: pod porównaniem jest wybór „Jedno zdjęcie” albo „Skan”.
  Po wybraniu „Jedno zdjęcie” dzieło powstaje ze zdjęcia na wprost, bez
  usuwania odbić.
- Skan dzieła za szybą: gdy lampa odbita w szybie wypaliła fragment
  zdjęcia na wprost, serwer bierze ten fragment ze zdjęć bocznych
  (wcześniej zostawała tam kolorowa plama). Odbicia widoczne tylko na
  zdjęciu na wprost (ręka, odblask) są rozpoznawane także wtedy, gdy
  zdjęcia boczne są jaśniejsze.
- Skan obrazu olejnego: połysk na fakturze farby schodzi z wypukłości, a
  nie z każdego punktu po równo, więc nie zostają czarne kropki w
  zagłębieniach; znika też pionowa linia przy krawędzi, gdzie kończyło
  się usuwanie.
- Dzieło, które z każdej strony wygląda inaczej (lustro, folia, relief),
  zostaje jako jedno zdjęcie: serwer niczego w nim nie zmienia.
- Głęboka rama: ciemny, nakrapiany pasek przy krawędzi grafiki za szybą
  nie powstaje.

## 1.145.200

- Skan dzieła z telefonem trzymanym poziomo: żółta ramka wykrytego
  dzieła była o jedną trzecią za długa (wychodziła ponad i pod obraz),
  a celownik przy zdjęciach bocznych stał obok środka. Ramka leży teraz
  dokładnie na dziele, tak jak przy telefonie trzymanym pionowo.

## 1.145.199

- W trybie oszczędnym ramka zmieniała obraz dwa razy: ok. 10 minut przed
  ustawioną godziną i potem o tej godzinie. Zegar ramki spieszy się we
  śnie o ok. 11 minut na dobę, więc budzik dzwonił za wcześnie. Serwer
  przesuwa teraz budzik o tyle, ile zegar ramki zyska do pobudki, i uczy
  się tego tempa przy każdym ustawieniu zegara.
- Gdy ramka mimo to obudzi się do 15 minut przed zmianą, zmiana przychodzi
  od razu, bez drugiej pobudki.
- Obraz wybrany w aplikacji, który czekał na pobudkę ramki, zostaje na
  ramce do następnej zmiany i nie znika po kilku minutach.

## 1.145.198

- Dzieło, którego plik muzeum trzyma obcięty (np. „Zmartwychwstanie
  Jezusa Chrystusa” Podolińskiego z MNW), pokazywało się jako szary
  prostokąt z paskiem obrazu u góry. Serwer rozpoznaje taki obraz i
  traktuje go jak brak obrazu: dzieło znika z list, tak jak dzieła z
  martwym linkiem. Zapisane już takie obrazy są sprawdzane raz po
  aktualizacji.

## 1.145.197

- Restauracja dzieła zachowuje barwy oryginału: z rysunku modelu zostają
  szczegóły, a tony i kolory wracają ze zdjęcia muzeum. Na pięciu pracach
  de Chirico odchylenie barw spadło z 1,6–6,0 do 0,5–0,8.
- Gdy Nano Banana 2.1 dwa razy zawiedzie (odmowa, brak obrazu albo obraz
  w innych proporcjach), restauracja prosi o rysunek droższy Nano Banana
  Pro. Dotyczy karty dzieła i pakietów Google.
- Dzieła odnowione wcześniej dostają barwy oryginału raz, po starcie
  serwera: bez ponownego rysowania i bez kosztu, serwer pobiera jeszcze
  raz zdjęcie z muzeum.

## 1.145.196

- Pasek barw na karcie dzieła i w Propozycjach dnia jest niższy: 18 pt
  zamiast 26, we wszystkich technikach. Pociągnięcia, faktura i kontur
  wyglądają jak dotąd, tylko drobniej. Wąski pasek w zakładce Teraz
  zostaje bez zmian.

## 1.145.195

- Skan własnego dzieła wychodził ciemniejszy i bardziej kontrastowy niż
  zdjęcie na wprost. Teraz z dzieła schodzą tylko odbicia o kształcie
  (lampa, okno, sylwetka), a równy połysk farby i lekka zasłona na szkle
  zostają, więc cienie nie zapadają się w czerń.
- Po trzecim zdjęciu nie trzeba już czekać pół minuty. Każde zdjęcie
  idzie do serwera od razu po zrobieniu, a zaraz po trzecim otwiera się
  kadrowanie. Serwer łączy zdjęcia w tle, strona „Skan gotowy” pokazuje
  się po kadrze. Samo łączenie na serwerze jest też szybsze.
- Aparat: strzałki bez ikonki idącej postaci, obraz na całą szerokość
  ekranu bez zaokrąglonych rogów, bez przycisku zdjęcia podczas wysyłania.
- Żółta ramka przy pierwszym zdjęciu lepiej trafia w dzieło: nie zostaje
  na prostokącie namalowanym w środku obrazu ani na ścianie wokół niego.

## 1.145.194

- Pełny ekran: przyciski korekty barw i restauracji nie są już
  przekreślane. Gdy poprawka jest widoczna, kropla jest błękitna, a iskry
  jasnożółte; gdy wyłączona, ikonka jest przygaszona.
- Pod tytułem i autorem nie ma już dopisku „Przed …”.
- Przełączenie wersji dzieła to szybkie, płynne przejście zamiast skoku.

## 1.145.193

- Aparat własnego dzieła: ikonka z trzema miejscami spod pierwszego
  zdjęcia jest teraz na obrazie aparatu i zostaje na wszystkich trzech
  ekranach. To plan widziany z góry: dzieło u góry, łuk wokół niego,
  kropka idzie po łuku tam, gdzie idziesz z telefonem.
- Zamiast samych strzałek jest idąca postać ze strzałkami i zdanie „Zrób
  krok w lewo, celując w dzieło”. Gdy telefon zostanie obrócony w
  miejscu zamiast przejścia w bok, aparat mówi „Nie obracaj telefonu”.
- Telefon trzymany poziomo: zdania spod obrazu nie leżą już bokiem, są na
  obrazie, obrócone razem z telefonem.
- Miniaturki trzech zdjęć u dołu ekranu zniknęły.

## 1.145.192

- Dzieło, którego oryginału nie da się pobrać (np. martwy odnośnik w
  Europeanie), jest pokazywane z miniatury. Teraz dostaje znaczek niskiej
  rozdzielczości z jej rozmiarem, a w menu „…” pojawia się „Restauracja
  dzieła”, która powiększa tę miniaturę.
- Stan studium sprawdzany w chwili, gdy odpowiedź modelu jest już zapisana,
  ale jeszcze nieoczyszczona, nie kończy się błędem serwera.

## 1.145.191

- W menu „…” dzieła „Kreatywny restaurator” nazywa się teraz
  „Restauracja dzieła” i stoi zaraz pod „Zdejmij werniks” / „Odżółć
  papier”.
- Dzieło po korekcie barw nie ma już pod obrazem opisu ani odnośnika do
  porównania. Wystarczają znaczki przy tytule.
- Na pełnym ekranie pod krzyżykiem są okrągłe przyciski z kroplą (korekta
  barw) i z iskrami (restauracja), tylko gdy dzieło je przeszło.
  Dotknięcie pokazuje dzieło bez tej poprawki, drugie dotknięcie wraca.

## 1.145.190

- Zdjęcia z boku mają celownik: okrąg na środku kadru i znacznik na
  środku dzieła. Zdjęcie robi się, gdy znacznik jest w okręgu, więc
  dzieło zostaje w środku kadru także pod kątem.
- Aparat pokazuje cztery narożniki dzieła i czeka, aż wszystkie będą w
  kadrze. Gdy ich nie znajdzie przez 3 sekundy, pokazuje spust.

## 1.145.189

- Aparat do skanu: zamiast skaczącej ramki jest tor jak w panoramie
  iPhone'a. Idziesz w bok, kropka idzie z Tobą, a zdjęcie robi się, gdy
  dojdzie do kółka. Strzałki pokazują stronę.
- Przed zdjęciem wypełnia się okrąg, więc widać, że aparat pracuje.
- Działa z telefonem trzymanym w poziomie i nad dziełem leżącym na stole.
- Pierwsze zdjęcie też ma teraz 48 MP (miało 12 MP).
- Łączenie trzech zdjęć jest łagodniejsze: nie przyciemnia i nie
  przesyca dzieła, połysk złoceń i werniksu zostaje.
- Gdy serwer nie znajdzie dzieła na zdjęciu, kadr zaczyna się od tego,
  co widział aparat.

## 1.145.188

- Po skanie z trzech zdjęć, gdy udało się zdjąć odbicia, pokazuje się
  strona „Skan gotowy”: przesuwasz uchwyt i porównujesz zdjęcie na wprost
  ze skanem. „Powtórz” wraca do aparatu, „Dalej” idzie do kadru.
- Gdy łączenie nic nie zmieniło, po aparacie jest od razu kadr, jak dotąd.

## 1.145.187

- Nowy aparat do skanu własnego dzieła. Sam znajduje krawędzie dzieła i
  rysuje jego obrys; zdjęcie na wprost robi się samo, gdy obrys zrobi się
  zielony.
- Kolejne dwa zdjęcia robi się pod większym kątem, ok. 30° z lewej i z
  prawej. Na ekranie jest ramka pomocnicza, która pokazuje, gdzie ma się
  znaleźć dzieło, i strzałka, w którą stronę iść. Dawna kropka zniknęła.
- Nie ma guzika robienia zdjęcia. Pojawia się tylko wtedy, gdy aparat
  przez kilka sekund nie widzi krawędzi dzieła.
- Pomocnik podpowiada: „Podejdź bliżej”, „Odsuń się”, „Stań na wprost”,
  „Trzymaj telefon prosto”, a przy słabym świetle uprzedza, że zdjęcie
  może wyjść nieostre.
- Do sprawdzenia na telefonie: czy aparat pewnie łapie krawędzie dzieła
  i czy strzałki prowadzą w dobrą stronę.

## 1.145.186

- Skan z trzech zdjęć łączy się po nowemu. Z dzieła za szybą znika welon
  z całej szyby, odbicie okna i sylwetka fotografującego, a barwy robią
  się głębsze. Każdy szczegół zostaje ze zdjęcia na wprost; zdjęcia z boku
  mówią tylko, co jest odbiciem.
- Dawne łączenie umiało zastąpić tylko małą plamę lampy i przy szybie w
  jasnym pokoju zostawiało zdjęcie bez zmian.
- Serwer szuka dzieła na zdjęciu raz: przy łączeniu, a „Szukam dzieła”
  w aplikacji korzysta potem z tej samej odpowiedzi.

## 1.145.185

- Własne dzieła w pełnej jakości zdjęcia. Telefon wysyła plik aparatu
  taki, jaki powstał (48 MP), a serwer wycina dzieło ze wszystkich jego
  pikseli i trzyma je w całości. Wcześniej dzieło było wycinane ze zdjęcia
  zmniejszonego do 4000 px i zostawało z niego ok. 2800 px.
- Na pełnym ekranie własne dzieło da się przybliżyć dużo głębiej:
  ostrzejsze fragmenty doczytują się same, jak w „Pod lupą”. Karta i
  ramka pracują dalej na wersji 4000 px, więc nic nie zwalnia.
- Dzieła dodane wcześniej zostają w dawnej jakości. Pełną dostaną po
  „Zrób zdjęcie ponownie”.
- Skan z trzech zdjęć nie psuje już dzieł za szybą: gdy odbicia zajmują
  dużą część obrazu, zdjęcie na wprost zostaje nietknięte (lepsze łączenie
  jest w przygotowaniu). Pojedynczy odblask lampy znika jak dotąd.
- Zdjęcia źródłowe skanu z trzech ujęć zostają na serwerze 14 dni, do
  strojenia łączenia zdjęć, potem same znikają.

## 1.145.184

- Konfiguracja → Claude i Gemini: na górze tabela „Koszty”, ile każda
  rzecz kosztowała w ostatnich 7 dniach i w całym okresie, od
  najdroższych, z sumą. Pod każdym przełącznikiem jego koszt z 7 dni.
- Przełączniki Claude w trzech grupach (Opisy i szukanie, Studia i
  Odkrywaj, Nocne porządki), z krótszymi opisami. Postęp słów kluczowych i
  polskich opisów stoi pod ich przełącznikami.
- Znikają jednorazowe przyciski „Uzupełnij wcześniejsze studia”,
  „Przejrzyj zapisane opisy” i „Opisz całą bibliotekę”: tę samą pracę robi
  nocą „Resztka miesiąca”. „Do sprawdzenia” jest na górze Konfiguracji.

## 1.145.183

- „Do sprawdzenia”: uwaga do polskiego opisu (np. „tekst mówi o białych
  literach, a na obrazie są ciemne”) ma przycisk „Popraw opis”. Claude
  poprawia w opisie tylko to, czego dotyczy uwaga, patrząc na obraz, a Ty
  widzisz poprawiony tekst na karcie i na ramce, możesz go jeszcze zmienić
  i zapisujesz. Tak poprawiony opis nie jest potem pisany od nowa.
- „Do sprawdzenia” jest też od razu na górze Konfiguracji (z liczbą
  pozycji), gdy coś na niej czeka.

## 1.145.182

- Aparat przy dodawaniu własnego dzieła robi zdjęcia w pełnej
  rozdzielczości (48 MP na nowszych iPhone'ach), więc dzieło wycięte z
  ramy jest ostrzejsze.
- Po pierwszym zdjęciu aparat prosi o dwa kolejne, krok w lewo i w prawo:
  wystarczy wprowadzić kropkę w kółko, zdjęcie robi się samo. Serwer
  nakłada je na siebie i usuwa odblaski lampy czy okna na szybie i
  werniksie. „Pomiń” zostawia samo pierwsze zdjęcie.
- iPhone z czujnikiem LiDAR (wersje Pro) mierzy wymiar dzieła między
  narożnikami kadru i wpisuje go w puste pole Rozmiar (z ikoną linijki).

## 1.145.181

- Ulubione posortowane „Ostatnio dodane” stawiają na górze dzieła polubione
  ostatnio. Dotąd liczyła się data trafienia dzieła do biblioteki, więc
  serduszko na dziele znanym od dawna zostawiało je daleko w dół listy.
  Serce przeniesione na lepszą kopię dzieła zachowuje swoją datę.
- W playlistach ręcznych „Ostatnio dodane” liczy dodanie dzieła do tej
  playlisty, a nie do biblioteki. W „Historii przesłanych” na górze jest
  ostatnio przesłane zdjęcie także po wybraniu „Ostatnio dodane” (dotąd
  wychodziło odwrotnie).

## 1.145.180

- Kadrowanie grafiki leżącej wśród tablicy barw i linijki (Erichsøe,
  „Selvportræt med Violin”, SMK): pokazuje się sama płyta, a nie kartka
  razem z tablicą. Model nie wątpi już w płytę tylko dlatego, że kartka
  wychodzi poza zdjęcie albo leży pod tablicą barw. Dzieło obejrzane
  wcześniej i zostawione bez kadru jest przy otwarciu karty sprawdzane
  ponownie (dotąd nigdy, bez śladu w logu). Bok kartki leżący na brzegu
  zdjęcia zostaje na brzegu. Log mówi, co kadrowanie postanowiło.

## 1.145.179

- Nowy wygląd kroku Opis przy dodawaniu własnego dzieła i w „Edytuj opis”:
  jak karta dzieła. Tytuł, autor i data dużą szeryfową czcionką, technika,
  rozmiar, miejsce i pochodzenie w jednej karcie, technika z menu. To, co
  udało się odczytać z obrazu, jest od razu wpisane (z iskierką przy polu),
  „Wyczyść” cofa wszystko naraz.

## 1.145.178

- Aparat przy dodawaniu własnego dzieła działa też poziomo: telefon
  trzymany bokiem robi zdjęcie poziome, wygodniej przy szerokich dziełach.
- W kroku Opis nie ma już ramki „Podpowiedzi z obrazu”; podpowiedzi
  zostają przy polach.
- Własne dzieło dostaje notkę kuratora jak każde inne (z tego, co o nim
  wpisałeś, Twój tytuł, data i technika zostają), a Twoja notatka jest pod
  nią. Na karcie pojawia się też „Podobne wyglądem”.

## 1.145.177

- „Moje dzieła” w Playlistach znów pokazuje wszystkie własne dzieła. Od
  1.145.160 aplikacja prosiła serwer o 500 dzieł naraz, serwer daje
  najwyżej 200 i odmawiał, więc lista pokazywała tylko dzieło dodane przed
  chwilą. Teraz lista przychodzi stronami po 200. Dzieła nie zginęły.
- Kafelek własnego dzieła na listach ma proporcje z podanego wymiaru, jak
  karta i sam obraz, a nie z narożników na zdjęciu.

## 1.145.176

- „Dodaj własne dzieło” otwiera od razu aparat: kadr ze znacznikami
  narożników, pod nim „Umieść całe dzieło w kadrze”, obok migawki
  przycisk Zdjęć, w lewym górnym rogu strzałka wstecz. Bez strony
  z opisem i radami przed aparatem.
- Kroki Kadr i Opis mają zwykły pasek nawigacji jak reszta aplikacji:
  strzałka wstecz, tytuł z krokiem („Kadr · 2 z 3”), „Dalej” albo
  „Dodaj” w prawym górnym rogu, zamiast przycisków „Anuluj” i „Wstecz”.

## 1.145.175

- Automatyczne kadrowanie trafniejsze. Przegląd 178 automatycznych kadrów:
  28 złych (16 %). Grafika, której papier wychodzi poza zdjęcie (drzeworyt
  światłocieniowy Jacksona wg Veronesego, litografie Géricaulta), traciła
  margines papieru wzięty za pasek tła: paski z pikseli tnie się teraz
  tylko, gdy kończą się na brzegu kartki wskazanej przez Opusa, a kadry
  zrobione tak dotąd wracają raz do Opusa. Bok kartki nie przeskakuje już
  do wewnątrz na drukowaną linię obwiedni, a bok obrazu na zewnątrz na
  złotą listwę ramy. Romb (obraz postawiony na rogu) nie jest kadrowany.

## 1.145.174

- Szukaj zdjęciem: wyniki pokazują się teraz w zwykłym widoku Szukaj, tak
  jak „Szukaj podobnych” z karty dzieła. W polu jest chip „Podobne do
  zdjęcia” (ikona aparatu), nad wynikami miniatura zdjęcia, a grupy
  (technika, epoka, kolor, muzeum…) zawężają wyniki. Z wyników można
  utworzyć playlistę inteligentną; serwer trzyma liczby zdjęcia (nie samo
  zdjęcie), więc playlista działa dalej. To samo zdjęcie drugi raz nie
  pyta Google. Osobny ekran „Dzieła podobne do tego zdjęcia” zniknął.

## 1.145.173

- Pasek „Kolorystyka” rysunku lawowanego na barwionym papierze albo
  rozjaśnionego bielą (np. Géricault, „Turecki jeździec w walce”): papier
  w kolorze pracy, pod spodem kreski kredy albo piórka, lawowania od
  najjaśniejszego, a biel gwaszem jednym kryjącym pociągnięciem na jasnym
  końcu paska. Serwer zauważa teraz biel położoną na barwionym papierze
  (wcześniej brał ją za papier); po aktualizacji ponownie przelicza barwy
  biblioteki.
- Drzeworyt światłocieniowy (chiaroscuro) ma własny pasek: biel papieru,
  płaskie płyty tonów jednej barwy nadrukowane jedna na drugą i linie
  płyty konturowej, zamiast czarnego klocka zwykłego drzeworytu. Rozpoznaje
  go także opis dzieła, gdy technika mówi tylko „drzeworyt” (np. Jackson
  według Veronese z Europeany: „cu patru plăci”).

## 1.145.172

- Własne dzieło dostaje proporcje z podanego wymiaru: obraz wycięty ze
  zdjęcia jest prostowany do szerokości i wysokości wpisanych w cm, nie do
  tego, co dały narożniki na zdjęciu robionym pod kątem. Zmiana wymiaru w
  „Edytuj opis” wycina dzieło na nowo, a dodane wcześniej poprawiają się
  same po aktualizacji serwera. Wymiar bardzo odbiegający od zdjęcia
  (ponad dwa razy) uznawany jest za pomyłkę i zostają proporcje zdjęcia;
  formularz mówi o tym pod wymiarem, a podgląd u góry od razu pokazuje
  dzieło w nowych proporcjach.

## 1.145.171

- Korekta barw: zdjęty werniks jest teraz widoczny także na obrazach
  ciemnych w całości. Dotąd barwa była oddawana tylko jaśniejszym partiom
  (żeby czernie i ciemne zielenie nie robiły się niebieskie), a w takim
  obrazie prawie wszystko jest ciemne, więc zmiany nie było widać. Próg
  ciemnych partii liczy się teraz względem danego obrazu, czernie dalej
  zostają neutralne. Siła korekty to cała propozycja zamiast trzech
  czwartych, a obraz ciemny w całości wychodzi też jaśniejszy, jak po
  prawdziwym zdjęciu werniksu. Dzieła skorygowane wcześniej serwer
  przelicza sam kilka minut po aktualizacji.
- Kropla „barwy skorygowane” (i znaczek kadru, kopii, restauratora)
  pojawia się na liście od razu po zmianie na karcie, także na stronie
  tematu w Odkrywaj otwartej wcześniej.

## 1.145.170

- Resztka miesiąca Claude: „Słowa kluczowe i polskie opisy” mają limit
  na noc, domyślnie 1000 dzieł (ok. 6,60 USD); pod pozycją menu „do 1000
  na noc” (250–10 000). Dotąd ta pozycja mogła jednej nocy wziąć całą
  wolną resztkę. Wiersz pokazuje teraz, ile pójdzie tej nocy i za ile,
  zamiast kosztu całego zaległego katalogu.

## 1.145.169

- Korekta kadru: narożnik na zdjęciu łapie się teraz w kole o średnicy
  80 pt (było 48 × 48 pt), także poza krawędzią zdjęcia; gdy koła na
  siebie zachodzą, bierze się narożnik bliżej palca. Narożnik nie skacze
  już pod palec, tylko przesuwa się o tyle, o ile palec, więc można go
  chwycić obok i dalej widzieć.

## 1.145.168

- Własne dzieła w katalogu: „+” w Playlistach → „Dodaj własne dzieło”.
  Zdjęcie aparatem albo ze Zdjęć, serwer sam wycina dzieło z ramy,
  passe-partout i ściany (narożniki można poprawić w lupach), potem opis:
  tytuł, autor, data, technika, rozmiar, gdzie wisi, skąd, notatka. Z
  obrazu czytane są podpowiedzi (sygnatura, data, technika, prosty tytuł),
  które wpisuje się jednym dotknięciem. W karcie dzieła „Edytuj opis”,
  „Zrób zdjęcie ponownie”, „Popraw kadr” i „Usuń z katalogu”, w
  Playlistach kafelek „Moje dzieła”. Własne dzieła są na ramce, w
  playlistach, w Szukaj (także zdjęciem) i w studiach jak inne.

## 1.145.167

- „Do sprawdzenia”: miniatury są większe, a dotknięcie miniatury otwiera
  obraz na całym ekranie, w całości, z przybliżaniem palcami (widać
  linijkę, pasek kolorów, uciętą krawędź). Dotknięcie tytułu otwiera kartę
  dzieła.
- Uwagi nocnego przeglądu naprawia się jednym dotknięciem: zły tytuł,
  autor albo data mają przycisk „Popraw na „…”” z gotową propozycją (przy
  tytule także polski tytuł; „Zmień…” pozwala wpisać inaczej), linijka,
  pasek kolorów czy kartka wokół rysunku mają „Przytnij” (Opus szuka
  krawędzi dzieła, wiedząc, co przegląd zauważył) i „Inna kopia”, a każda
  pozycja ma „Ukryj”. Propozycje do starszych uwag dopisuje Haiku przy
  otwarciu listy (ułamek centa za dzieło).
- Opisy strażnika przy odłożonych dziełach są po polsku; starsze
  tłumaczą się same przy otwarciu listy.

## 1.145.166

- Resztka miesiąca: pozycja „Słowa kluczowe i polskie opisy” liczy
  teraz wszystkie dzieła katalogu, którym ich brakuje, i pokazuje
  prawdziwy koszt. Wcześniej liczyła tylko dzieła z Ulubionych,
  playlist i już pokazane, choć noc zamawia opisy dla całego katalogu.

## 1.145.165

- Dzieło w passe-partout i w trybie „Opis” nie jest już lekko powiększane:
  dotąd okno kartonu chowało po 2 % każdej krawędzi (powiększenie o ok.
  4 %), żeby ukryć ramę i tło muzeum. Robi to teraz automatyczne
  kadrowanie, więc na ramce widać dzieło do samych brzegów. Ręczne kadry
  i zbliżenia zostają bez zmian.

## 1.145.164

- Korekta barw zamiast podglądu: „Zdejmij werniks” albo „Odżółć papier”
  w menu „…” karty podmienia dzieło na wersję po korekcie. Widać ją
  wszędzie: na listach, na karcie, na pełnym ekranie i na ramce, a barwy
  dzieła i pasek barw są liczone z wersji po korekcie. To samo miejsce
  w menu cofa zmianę („Przywróć werniks”, „Przywróć ton papieru”).
- Nie ma już suwaka siły: korekta bierze ostrożne trzy czwarte propozycji
  z samego obrazu. Pod obrazem jest jedno zdanie o korekcie i przycisk
  „Porównaj z obrazem przed korektą” (kurtyna: z lewej przed, z prawej po).
- Dzieło po korekcie ma własny znaczek po tytule, w tych samych miejscach
  co znaczki kadru, niskiej rozdzielczości i restauratora.
- Ciemne partie nie niebieszczeją: czernie i ciemne zielenie zachowują
  swój odcień, a czernie są minimalnie głębsze (trochę większy kontrast).
- Inna kopia zdjęcia dzieła nie dostaje korekty sama (nie wiadomo, jakie
  ma barwy). Wersja kreatywnego restauratora dostaje ją, bo powstaje
  z tego samego zdjęcia.

## 1.145.163

- Paski barw rysunków (ołówek, pióro, rysunek z akwarelą), gwaszu
  i lawowania leżą na stronie jak pasek papieru: góra i dół równo cięte,
  końce oddarte, pod spodem delikatny cień. Odbitki (ryciny, drzeworyty,
  litografie, sitodruk, offset) mają papier poszarpany dookoła jak dotąd.

## 1.145.162

- Pasek barw grubo malowanych obrazów olejnych (np. van Gogh, Matisse):
  każdy kolor ma duży, spokojny płat malowany płasko i część z wielu
  krótkich pociągnięć, które leżą na styku z sąsiednim kolorem. Obrazy
  malowane gładko (np. Vermeer) i dzieła bez daty i stylu bez zmian.

## 1.145.161

- Resztka miesiąca Claude idzie na to, co wybierzesz, w Twojej kolejności:
  uzupełnienie wcześniejszych studiów, kadrowanie zdjęć dzieł, przegląd
  zapisanych opisów, nowe studia, słowa kluczowe i polskie opisy oraz
  większy nocny przegląd (domyślnie wyłączony). Noc płaci od góry, póki
  starcza, a przy każdej pozycji widać, ile czeka i ile by to kosztowało.
  Kolejność zmienia się przeciąganiem w Konfiguracji → Claude.

## 1.145.160

- Rysunek kredą, ołówkiem albo węglem na barwionym papierze (niebieskim,
  szarym, brązowym) ma własny pasek barw: papier w swojej barwie, luźne
  kreski rysunku gęstniejące z ciemnymi tonami, światła białą kredą,
  a sangwina czy brązowa kredka kreskami swojej barwy. Tak samo rysunek
  z białymi światłami i kreda trzech kolorów. Dotąd pasek był szarym
  kreskowaniem przez całą szerokość, bez papieru i bez bieli.
- Taki pasek wygląda jak pasek papieru położony na stronie: góra i dół
  równo cięte, końce oddarte, pod spodem delikatny cień.

## 1.145.159

- Rysunek z akwarelą (ołówek, węgiel, kreda albo pióro z akwarelą) ma
  własny pasek barw: tyle paska, ile na dziele zajmuje goły papier, to papier
  z luźnymi kreskami rysunku, reszta barw to laserunki akwareli położone na
  kreskach, a akcenty to krople akwareli na czystym papierze. Dotąd taki
  rysunek dostawał samą akwarelę, a ołówek ginął.
- Biały gwasz, który tylko rozjaśnia rysunek, nie zmienia już paska na
  gwasz; rycina z akwarelą ma pasek ryciny kolorowanej.

## 1.145.158

- Kupowanie kopii w Alamy usunięte: w menu „…” dzieła nie ma już „Kup w
  Alamy” ani „Wczytaj kupioną kopię”, a w Konfiguracji → Źródła dzieł
  przełącznika „Kupowanie w Alamy”. Kopie wczytane wcześniej zostają
  zdjęciem swoich dzieł. „Szukaj lepszej kopii” działa jak dotąd.

## 1.145.157

- Pasek barw farby olejnej jest spokojniejszy i trzyma się prostokąta.
  Każdy kolor jest najpierw położony spokojnym pociągnięciem, a potem
  przejechany kilkoma krótkimi, odrobinę jaśniejszymi lub ciemniejszymi,
  przez część wysokości paska. Nowa farba wchodzi w mokrą bez wypukłej
  obwódki, pasek ma miękki, postrzępiony brzeg i kończy się bez suchego,
  wystrzępionego ogona. Kontur jest cieńszy. Wypukłość farby dalej zależy
  od dzieła.

## 1.145.156

- Akwatinta jednej barwy (także z akwafortą) ma pasek z ziarna zamiast
  kresek rylca, jak litografia: tony to ziarno kalafonii wytrawione w
  płycie, bez śladów kredki, tony stykają się ostrzej (kryte werniksem po
  kolei), a wokół paska jest odcisk płyty. Akwatinta barwna i kolorowana
  ręcznie bez zmian.

## 1.145.155

- Podgląd odzyskania barw na karcie dzieła (menu „…”), sam rachunek, bez
  modelu i bez kosztu. Obrazy olejne i tempery: „Symulacja odzyskania barw”
  pokazuje dzieło bez pożółkłego werniksu; na obrazie jest suwak (po lewej
  „Dziś”, po prawej „Bez werniksu”), pod nim pasek siły z kreską propozycji
  wyliczonej z bieli obrazu i z tego, ile zdejmowały prawdziwe konserwacje.
  Rysunki, grafiki, akwarele i pastele na pożółkłym arkuszu: „Odżółć papier”
  pokazuje arkusz jak dobrze zachowany; kreska i barwy zostają z oryginału,
  papier barwiony celowo nie dostaje propozycji. To tylko podgląd: nie
  zmienia dzieła, paska barw, wyszukiwania ani obrazu na ramce.

## 1.145.154

- Litografia jednej barwy ma własny pasek barw zamiast kreskowania
  ołówkiem: każdy ton to ziarno kamienia, które tłusta kredka chwyta
  mocniej albo słabiej, od rzadkiego pyłu drobnych plamek po aksamitną
  czerń, tony przechodzą miękko jeden w drugi, a ziarno wyłania się
  pociągnięciami od jasnego końca do ciemnego. Litografia barwna i rysunek
  ołówkiem zostają bez zmian.

## 1.145.153

- Dzieła, które nie są prostokątem (wycinanka po konturze rysunku,
  odłamek, talerz, owal, koło, miniatura w okrągłej oprawie, łuk ołtarza,
  przedmiot), nie są już kadrowane automatycznie: zostaje całe zdjęcie
  muzeum. Model kadrujący mówi teraz, jaki kształt ma samo dzieło, i kadruje
  tylko prostokąty; paski tła z pikseli też nie są wtedy wycinane.
- Dzieła wykadrowane wcześniej są sprawdzane jeszcze raz (krótkie pytanie o
  kształt, nocą przez Batch, a od razu przy otwarciu karty) i gdy nie są
  prostokątem, wracają do całego zdjęcia. Twoje własne kadry zostają, a
  kadrowania na ramce pokazują ten sam fragment co wcześniej. Detale
  studium trafiają w to samo miejsce, kolory są liczone od nowa.

## 1.145.152

- Na listach w Odkrywaj (sekcje, „Zobacz wszystkie”, strony motywów i
  grup, karty Studiów) dzieła mają po tytule te same znaczniki co na
  playlistach: przycięte ze zdjęcia muzeum, niska rozdzielczość,
  kreatywny restaurator i Pod lupą. Dzieło z biblioteki pokazuje się tam
  z wybraną kopią i kadrem, także w Szukaj.

## 1.145.151

- Pastel ma własny pasek barw zamiast kreskowania kredki: każda barwa jest
  najpierw roztarta palcem, potem kładziona bokiem kredy w spokojnym skosie
  na całą wysokość paska, a na końcu ma dwie–trzy kreski czubkiem. Akcenty
  to roztarta plamka z pociągnięciami w tym samym skosie. Kredka i kreda
  zostają przy kreskowaniu.

## 1.145.150

- Szkic kompozycji od Gemini jest teraz częścią opracowania studium
  dzieła: krok „Kompozycja” kończy się linią „Rysuję szkic kompozycji”,
  a pasek postępu, „jeszcze ok. X min”, Live Activity i powiadomienie
  „Studium gotowe” liczą go razem ze studium. Detale są wycinane w tym
  samym czasie. Gdy Gemini nie da szkicu (limit, brak środków, odmowa
  albo ok. 5 minut bez odpowiedzi), studium kończy się jak dotąd, z
  zapasowym szkicem serwera.
- Komunikatu „Gemini rysuje szkic kompozycji…” już nie ma.
- Studium otwarte w trakcie opracowania nie pokazuje tekstu, kompozycji
  ani detali, tylko obraz, tytuł i kartę „Studium dzieła w trakcie
  opracowania” z postępem. Gdy studium będzie gotowe, karta gaśnie i w
  jej miejsce wchodzi całe studium.
- „Studia dzieł” pokazują studium dopiero gotowe.
- Po „Wykonaj ponowną analizę” poprzednia analiza zostaje na stronie, aż
  nowa będzie miała swój szkic.

## 1.145.149

- Karta dzieła: „Pełny kadr” to teraz karta z wierszami tuż nad słowami
  kluczowymi i techniką: miniatura zdjęcia muzeum ze zdaniem, co na nim
  było, przełącznik „Z marginesem” przy pracach na papierze i „Popraw
  kadr”.
- Ekran poprawiania kadru ma cztery lupy, po jednej na narożnik, nad
  zdjęciem i pod nim. Krzyżyk w lupie to narożnik: przesuwa się go,
  przesuwając zdjęcie w lupie, więc palec niczego nie zasłania. Narożniki
  na zdjęciu są kątownikami, „Zapisz” jest u góry obok „Anuluj”, pod
  zdjęciem „Cofnij zmiany” i „Całe zdjęcie”.

## 1.145.148

- Błękit pod pożółkłym werniksem: niebo, woda albo szata, które na zdjęciu
  dzieła wyglądają na zielone, a po odjęciu żółci są niebieskie, nocą
  ogląda Haiku. Gdy to błękit, dzieło dostaje akcent błękitu i znajdzie je
  szukanie po barwie (niebo u Cranacha, płaszcz Marii u Boscha, woda u
  Wyczółkowskiego); prawdziwe zielenie zostają zielone. Grosze miesięcznie,
  przełącznik „Błękit pod werniksem” w Konfiguracji. Biblioteka przelicza
  barwy po aktualizacji.

## 1.145.147

- Stonowana barwa, która zajmuje co najmniej 3% obrazu, a pasek pokazuje ją
  jako szarość, dostaje akcent swojej barwy: niebieski papier „Maku”
  Rungego, różowa sukienka u Makowskiego, zielenie u Bouchera. Znajdzie je
  szukanie po akcencie i widać je w barwach na karcie. Na próbce biblioteki
  zmienia się 16 z 530 dzieł. Biblioteka przelicza barwy po aktualizacji.

## 1.145.146

- Detale studium dzieła przyciętego z ramy (lub z kartonu, sztalugi) są
  wycinane z przyciętego zdjęcia, na którym model je zaznaczył. Dotąd
  wycinano je ze zdjęcia muzeum z ramą, więc wychodziły przesunięte o
  szerokość ramy. Studium napisane przed przycięciem dalej wycina detale z
  całego zdjęcia.
- Zanim powstanie studium dzieła (z karty, Studium dnia, studia z zapasu),
  serwer sprawdza zdjęcie i w razie potrzeby wycina ramę, sztalugę czy
  karton. Studium, kompozycja i szkic opisują wtedy samo dzieło, nie ramę.
- Gdy w nocy wejdzie ostrzejsza kopia dzieła, nocne kadrowanie obejrzy ją
  od nowa. Dotąd nowa kopia czekała na kadr do otwarcia karty.
- Poprawienie kadru zdjęcia („Popraw kadr”) albo jego cofnięcie nie kasuje
  już kadrowania na ramce: zbliżenia i kadry pokazują ten sam fragment
  dzieła.

## 1.145.145

- Dzieło z WikiArt nie dostaje już fałszywego znacznika niskiej
  rozdzielczości: WikiArt podaje czasem rozmiar małej wersji (433 × 600
  przy pliku 1441 × 1999), więc liczy się rozmiar pobranego zdjęcia. Karta
  dzieła z wybraną kopią i kafelki w Szukaj liczą znacznik z kopii, nie ze
  zdjęcia muzeum (Wyspiański, „Macierzyństwo”: „600 px” przy kopii
  1920 × 2548).
- Automatyczne kadrowanie wycina ramę także z dzieła, któremu ustawiono
  kadrowanie na ramce (np. zbliżenie twarzy): to kadrowanie przenosi się na
  wycięty obraz i pokazuje ten sam fragment. Dzieła, którym rama została z
  tego powodu, kadrują się przy najbliższym otwarciu karty.
- Technika dzieła z WikiArt bierze się też z rekordu muzeum, którego jest
  kopią (MNW: „pastel, papier żeberkowy”), więc pastel nie dostaje paska
  farby olejnej, gdy WikiArt nie odpowiada. Po wyborze kopii technika jest
  szukana od nowa na jej stronie w Commons.

## 1.145.144

- Parawan malowany tuszem i kolorami na złoconym papierze (Sakai Hōitsu,
  „Paulownie i chryzantemy”, Cleveland) miał płaski pasek barw. Tusz z
  kolorami na dziele wielobarwnym jest teraz gwaszem, a na jedwabiu
  akwarelą; złocony papier daje złoto płatkowe.
- Tak samo obraz w samych kolorach na papierze albo jedwabiu („Color on
  paper”, parawan Kano Hideyoriego „Oglądanie klonów w Takao”, Tokio).
- Blada chłodna barwa na ciepłym tle (złoty papier, werniks) jest akcentem:
  szara woda w Takao jest w pasku i w szukaniu „Błękit · akcent”, tak samo
  niebieskie szaty „Ostatniej Wieczerzy” czy suknia Klio w „Alegorii
  malarstwa”. Na próbce biblioteki zmienia się 7 z 530 dzieł. Biblioteka
  przelicza barwy po aktualizacji.
- Złoto w pasku barw jest jedną z jego farb, nie nakładką: na oleju i
  akwareli ma kształt i wysokość farby, czarny kontur biegnie nad nim, a
  złoto pojawia się dopiero po narysowaniu konturu.

## 1.145.143

- „Podobne wyglądem” na karcie dzieła: szerokie dzieła (parawany,
  panoramy) stoją zaraz pod nagłówkiem, bez dużego pustego miejsca nad
  nimi. Wysokość rzędu dopasowuje się do najwyższego obrazu.

## 1.145.142

- Przygotowywane Studium dzieła nie pokazuje już najpierw arkusza
  kompozycji z plamami, który po minucie czy dwóch znikał pod szkicem
  Gemini. Póki Gemini rysuje, w miejscu arkusza jest napis „Gemini rysuje
  szkic kompozycji…” w ramce kształtu obrazu, a szkic pojawia się w niej,
  gdy przyjdzie. Arkusz z plamami zostaje zapasem: gdy Gemini odmówi
  dzieła, klucz nie działa, skończy się limit albo szkic nie przyjdzie w
  ciągu ok. 7 minut.
- Gemini zabiera się do szkicu od razu, gdy aplikacja czeka na stronę
  (wcześniej do minuty przerwy w tle).
- Serwer nie robi już z wyprzedzeniem arkuszy z plamami (jasnego i
  ciemnego) dla studiów, które mają albo dostaną szkic Gemini. Zrobi go
  dopiero, gdy będzie potrzebny.

## 1.145.141

- Rysunek z marginesem nie traci już marginesu z jednej strony (Beksiński,
  „Kobieta niosąca trumnę…”, MNK: „z marginesem” obcinało prawą stronę do
  samego rysunku). Gdy brzeg kartki leży na brzegu rysunku, a dalej na
  zewnątrz widać pasek tła, brzeg kartki jest przesuwany tam, gdzie pasek
  się kończy. Zapisane już tak kadry serwer poprawia raz w nocy.

## 1.145.140

- Wąskie paski tła są odcinane także wtedy, gdy Opus nie jest pewien brzegu
  kartki (Munch, „Wieczór, melancholia I”, Cleveland). Kartka niemal
  dotyka brzegów zdjęcia, więc Opus odpowiadał „niepewnie” i nic się nie
  działo. Teraz serwer odcina same paski tła, mierząc je na zdjęciu:
  z każdej strony, gdzie biegnie jednolity pasek, do miejsca, w którym się
  kończy. Papier zostaje. Dzieła sprawdzone tak w 1.145.138 i nieprzycięte
  są sprawdzane jeszcze raz.

## 1.145.139

- Praca wydrukowana na cienkim papierze naklejonym na karton (np. litografia
  Wyczółkowskiego na papierze chińskim z „Teki Ukraińskiej”, MNK) nie
  pokazuje już wyboru marginesu, który niczego nie zmienia. Karton jest
  odcinany jak passe-partout, a sama kartka jest odbitką, więc „z
  marginesem” i „bez marginesu” dawały ten sam obraz. Gdy obraz odbitki
  pokrywa się z kartką, serwer zapomina o nim i o „marginesie papieru”, a
  zapisane już takie kadry porządkuje raz w nocy.

## 1.145.138

- Kartka leżąca na białej albo szarej tekturze, z której widać tylko wąski
  pasek, też jest przycinana (Perugino, „Święty Sebastian”, Cleveland).
  Haiku na miniaturze takiego paska nie zauważał, więc nikt nie pytał
  Opusa. Teraz serwer sam sprawdza brzegi miniatury: gdy co najmniej z
  dwóch stron biegnie jednolity pasek innego koloru niż to, co tuż za nim,
  pyta Opusa o kadr, jak przy ramie albo sztaludze. Tak samo fotografuje
  wiele grafik Muzeum Narodowe w Warszawie.
- Dzieła sprawdzone wcześniej są oglądane ponownie przy wejściu w kartę, a
  te z Ulubionych, playlist i Odkrywaj raz w nocy. Pytanie idzie od razu do
  Opusa, bez ponownego pytania Haiku.
- Papier dalej zostaje: gdy Opus wskaże sam obraz odbitki, a kartka
  wypełnia całe zdjęcie, zdjęcie zostaje całe, a „Pokaż bez marginesu”
  przycina do odbitki.

## 1.145.137

- Kadrowanie po wejściu w kartę dzieła przestało działać, gdy przeglądało
  się Odkrywaj: zapytanie o kadr czekało na miniaturę albo zdjęcie muzeum
  jak praca w tle, a ta czeka, dopóki aplikacja jest w użyciu. Oba wątki
  kadrowania stanęły (na NAS od 23:20 UTC 14.11) i każda następna karta
  czekała 60 s bez skutku. Teraz kadrowanie z karty pobiera obrazy od razu,
  jak inne rzeczy, na które karta czeka.

## 1.145.136

- Ponowna analiza kolorów biblioteki (po zmianie sposobu liczenia barw,
  ostatnio w 1.145.128) nie zaczyna się już od zera po każdej aktualizacji
  serwera. Dotąd wyniki czekały w pamięci do ostatniego obrazu, a analiza
  trwa na NAS godziny, więc przy kilku aktualizacjach dziennie mogła się
  nigdy nie skończyć. Teraz wyniki są zapisywane co 5000 obrazów razem z
  miejscem, do którego doszła, i po restarcie idzie dalej od tego miejsca.
- Postęp analizy widać w logu („rescore: … pictures analysed again, … of …
  works looked at, … min”), a nie dopiero jej koniec.
- Analiza ustępuje pytaniom aplikacji: przed każdym obrazem czeka (do 1 s),
  aż serwer skończy odpowiadać. Po starcie 1.145.131 szukanie w jej trakcie
  trwało na NAS 48 s.

## 1.145.135

- „Pełny kadr” prac na papierze wygląda jak przy obrazach: zdjęcie muzeum,
  obok zdanie, co muzeum sfotografowało i co jest pokazywane (np. „Muzeum
  sfotografowało pastel z marginesem kartki. Prezentowany jest pastel bez
  marginesu.”), a pod nim „Pokaż z marginesem” albo „Pokaż bez marginesu”
  i „Popraw kadr”. Zamiast dwóch miniatur „Z papierem” i „Sama odbitka”.
  Pracę nazywa technika: odbitka, pastel, akwarela, gwasz, rysunek, plakat
  albo dzieło.

## 1.145.134

- Schematy, plany, mapy i infografiki znikają z katalogu. Pliki wektorowe
  z Commons, które podawał Openverse (plany, mapy, herby, flagi,
  piktogramy), wypadają od razu i nie są już pobierane. Pozostałe zdjęcia
  ze źródeł zbierających Strażnik w nocy pyta też o to, czy są schematem,
  planem albo mapą; obejrzane wcześniej dostają raz tylko to pytanie.
  Stare mapy i plany z muzeów zostają.

## 1.145.133

- Pod nazwą playlisty inteligentnej widać teraz wszystkie jej reguły, nie
  tylko artystę: także słowa tytułu (np. „Bathers”), wygląd, „Podobne do”,
  style, tematy, epoki i techniki ze słownika, „Moje” oraz rodzaj dzieł.
  Tytuł ma znak cytatu, wygląd oko, jak te same reguły w Szukaj. Reguła,
  która tylko powtarza nazwę playlisty, nadal się nie pokazuje.

## 1.145.132

- Kadrowanie po wejściu w kartę działa też dla dzieła z muzeum, którego
  nie było jeszcze w bibliotece (np. otwartego z wyników muzeum). Wcześniej
  takie dzieło przycinało się dopiero przy drugim wejściu albo w nocy.

## 1.145.131

- „Podobne wyglądem” na karcie dzieła: wszystkie trzy obrazy mają jedną
  wysokość i stały odstęp. Wysoki zwój nie wychodzi już nad nagłówek i
  guzik „Przygotuj studium dzieła”, a długi parawan nie dotyka sąsiada:
  jest dopasowany do swojej kolumny, niższy, na tej samej linii.

## 1.145.130

- Po restarcie serwera zakładka „Teraz” i kolejka ramki nie czekają już na
  indeks szukania. Gdy ramka grała playlistę, pierwsze spojrzenie na
  kolejkę (następny obraz rysowany z wyprzedzeniem, zmiana obrazu
  przypadająca na start) czekało na pogrupowanie dzieł i na indeks w pętli
  zdarzeń, więc serwer mógł przez ten czas nie odpowiadać wcale (na kopii
  katalogu pierwsza odpowiedź po 31 s zamiast po 10 s), a „Teraz” po
  aktualizacji do 1.145.124 czekało na NAS do 48 s. To czekanie idzie
  teraz w wątku, a „Teraz” pokazuje kolejkę sprzed restartu i dobiera nowe
  dzieła przy następnym spojrzeniu albo zmianie obrazu.
- Z logu znikają błędy „No response returned.” (13 w dwie minuty
  przeglądania). Kompresja odpowiedzi z 1.145.118 wstrzymywała nagłówek
  odpowiedzi przychodzących wiersz po wierszu (strona tematu, szukanie w
  muzeach, kopie dzieła) do pierwszego wiersza, więc gdy aplikacja odeszła
  wcześniej, odpowiedź kończyła się bez nagłówka. Nagłówek takich
  odpowiedzi wychodzi znów od razu.

## 1.145.129

- Szkic pod analizą kompozycji (podkład z modelu graficznego) jest ogólniejszy
  i nigdy nie rysuje więcej niż dzieło: mniej kresek, postacie poza tematem
  jako proste sylwetki, bez dorysowanych twarzy, palców i drobiazgów.
  Zapisane arkusze ocenia raz tani model, a te zbyt szczegółowe dostają nowy
  podkład w tle (Batch, ok. 0,04 USD za arkusz); kolorowe kreski analizy
  zostają bez zmian.

## 1.145.128

- Trzy nowe wyglądy paska „Kolorystyka”: rysunek lawowany (tusz lub bister
  rozprowadzony pędzlem) to warstwy laweringu kładzione jedna na drugą z
  kreską piórka na ciemniejszej połowie; gwasz i farby kryjące (także
  „opaque watercolor” i „gum tempera” miniatur) to kryjące, matowe
  pociągnięcia pędzla; grafika kolorowana ręcznie to kreski ryciny z
  luźno położonymi akwarelami jej kolorów.
- Czarno-biały drzeworyt i linoryt mają pasek jak klocek odbity czernią:
  wycięcia dłuta jaśniejszych tonów i dwa większe wybrania papieru, w
  których zostają cienkie grzbiety drewna.
- Złoto, gdy technika je wymienia (tempera i złoto, złota farba), mieni
  się na pasku przy przechylaniu telefonu: płatkowe przesuwa się jednym
  miękkim blaskiem, złota farba dodatkowo błyska drobinkami.
- Pasek „Kolorystyka” idzie za techniką dzieła, a nie za działem muzeum:
  akwarele, rysunki ołówkiem i tuszem z działów „Prints and Drawings” nie
  są już rysowane jak ryciny, a obrazy z działu „Paintings and Sculpture”
  znów mają pasek. Drzeworyt barwny czy litografia barwna dostają farby
  nawet wtedy, gdy kolory na zdjęciu wyszły wyblakłe. Plakat opisany tylko
  jako „druk” ma pasek offsetu.
- Biel, która wybija się w ciemnym dziele jednobarwnym (biała linia na
  czarnym plakacie), jest na pasku jako akcent i daje się znaleźć jako
  „Biel · akcent”. Po aktualizacji serwer raz przelicza kolory biblioteki.

## 1.145.127

- Zdjęcia samych okładek, opraw, grzbietów i pustych kart (szkicowniki,
  sztambuchy, albumy i książki fotografowane przez muzea w całości, głównie
  MNK i MNW) są nocą odsiewane jak inne dzieła odłożone przez Strażnika:
  znikają z Szukaj, „Podobne do”, Odkrywaj, propozycji i studiów. Okładki
  zaprojektowane przez artystów zostają. Te w Ulubionych i na playlistach
  zostają, a odłożone można przywrócić w „Do sprawdzenia”.

## 1.145.126

- Kadrowanie zdjęć dzieł rozpoznaje stronę szkicownika lub albumu: dzieło
  to sama strona, bez grzbietu, okładki i brzegów kartek pod nią
  (np. szkice Bierstadta z Met). Zaokrąglone rogi strony nie są już
  powodem do wątpliwości. Dzieła, których model wcześniej nie był pewien,
  są pytane ponownie, w nocy albo po wejściu w kartę.

## 1.145.125

- Pasek „Kolorystyka” sitodruku to płaskie, kryjące warstwy farby z czystą
  krawędzią szablonu, także dla sitodruku czarno-białego, który dotąd
  dostawał kreskowanie kredką. Offset i plakat bez podanej techniki mają
  płaskie farby, a jasne odcienie z kropek rastra. Litografia bez zmian.

## 1.145.124

- Serwer po restarcie i po aktualizacji szybciej wraca do pracy, a to, co
  pokazuje, zostaje takie samo (listy, szukanie, karty i podpowiedzi
  porównane jeden do jednego). Pełny start na kopii katalogu (116 tys.
  dzieł; NAS liczy mniej więcej dwa razy dłużej), licząc od uruchomienia:
  serwer odpowiada po 10 s zamiast 17 s, ramka, „Teraz” i playlisty
  dostają odpowiedź po 12 s zamiast 19 s, Odkrywaj po 20 s zamiast 103 s,
  Propozycje po 33 s zamiast 54 s, pierwsze szukanie po 38 s zamiast
  48 s, podpowiedzi przy pisaniu w Szukaj po 48 s zamiast 83 s. Późniejsza
  praca serwera jest tak samo szybka jak dotąd.
- Serwer zaczyna odpowiadać, zanim pogrupuje dzieła katalogu w prace.
  Ramka, „Teraz”, ustawienia i playlisty nie czekają już na to
  grupowanie; listy dzieł czekają na nie jak dotąd.
- Odkrywaj otwiera się po restarcie od razu z dzisiejszymi kartami
  zapamiętanymi sprzed restartu. Świeża runda kart dolicza się w tle, w
  swojej kolejce, i podmienia je po chwili. Gdy tego dnia nie było jeszcze
  żadnej rundy, karty liczą się przy pierwszym otwarciu jak dotąd.
- Pytania zadane, zanim powstanie indeks szukania, czekają na niego,
  zamiast przeglądać cały katalog obok wątku, który go buduje. Jedno i
  drugie naraz trwało kilka razy dłużej: indeks był gotowy 66 s po
  uruchomieniu, teraz po ok. 30 s (na NAS po aktualizacji do 1.145.120 po 108 s zamiast 19 s).
- Prace po starcie idą jedna po drugiej w kolejności potrzeb aplikacji:
  grupowanie dzieł, indeks szukania, podpowiedzi, Propozycje, karty
  Odkrywaj, liczniki playlist (dotąd po minucie, obok kart), dobranie
  Propozycji z muzeów, gdy ich brakuje. Runda kart,
  na którą nikt nie czeka, ustępuje pytaniom aplikacji. W logu serwera
  każda z tych prac ma wiersz „start: … in … s”.

## 1.145.123

- „Pełny kadr” na karcie dzieła: każde zdanie zaczyna się od nowego
  wiersza, a „i”, „w”, „z” nie zostają na końcu wiersza ani ostatnie
  słowo samo w wierszu. Tło nie jest wymieniane, gdy dzieło stało na
  sztaludze albo w ramie („na sztaludze”, nie „na sztaludze i na tle”).
  Dotknięcie zdjęcia otwiera poprawianie kadru, tak jak „Popraw kadr”.

## 1.145.122

- Kółko „Łączę z serwerem” w lewym górnym rogu znika, gdy serwer odpowie
  i wczyta się „Teraz”. Dotąd czekało na wszystkie pytania startowe, także
  na playlisty, które po aktualizacji serwera czekały na zbudowanie
  indeksu szukania: kółko kręciło się wtedy przez kilka minut, choć
  aplikacja była już połączona.
- Playlisty po restarcie serwera odpowiadają od razu. Serwer pamięta
  liczby dzieł i okładki playlist inteligentnych także po restarcie i
  pokazuje je, dopóki nie przeliczy ich od nowa (minutę po starcie, przy
  otwarciu playlisty i nocą). Playlista z serc liczy się od nowa po
  zmianie serc, zmieniona playlista od razu, jak dotąd. Po aktualizacji
  do 1.145.120 playlisty odpowiadały po 46–100 s.
- Odkrywaj i Propozycje nie zajmują połączeń, którymi idą „Teraz” i
  playlisty: tematy i propozycje mają własne połączenia i czekają do
  trzech minut. Dotąd po minucie aplikacja pytała od nowa, a serwer
  liczył to samo jeszcze raz.

## 1.145.121

- Konfiguracja → Miejsce na serwerze nie czeka już na dysk także po
  aktualizacji serwera i po nocnym przycięciu biblioteki. Serwer mierzy
  wtedy dysk sam, w tle (po starcie po trzech minutach, gdy nie ma
  zapamiętanego pomiaru; po przycięciu od razu), więc strona otwarta
  później dostaje gotową liczbę. Na NAS pierwszy pomiar zaraz po starcie
  1.145.120 trwał ponad dwie minuty i tyle czekała strona.

## 1.145.120

- Konfiguracja → Miejsce na serwerze pokazuje się od razu. Serwer pamięta
  ostatni pomiar dysku (także po restarcie) i pokazuje go natychmiast, a
  gdy pomiar ma ponad 10 minut, mierzy od nowa w tle; świeży wynik widać
  od razu, jeśli dysk zdąży w sekundę, inaczej przy następnym otwarciu.
  Dotąd strona czekała na obejrzenie każdej miniatury i każdego obrazu,
  na NAS od 3,5 do 45 s. Decyzje serwera (ile miejsca zostało na
  oryginały) biorą świeży pomiar jak dotąd, a po przycięciu biblioteki
  liczba jest mierzona od nowa.
- Miniatury po dobie nie pobierają się od nowa. Telefon trzyma miniaturę
  dobę, a potem pyta, czy się zmieniła; serwer odpowiada teraz krótkim
  „bez zmian” zamiast wysyłać ją całą (kilkadziesiąt KB każda), więc
  siatki otwierane po dniu przerwy i poza domem wypełniają się z pamięci
  telefonu. Zmieniony obraz dzieła (inna kopia) przychodzi cały jak
  dotąd. Czas ważności w telefonie zostaje (doba).
- Nowy odczyt dla właściciela: `GET /api/debug/memory` mówi, ile pamięci
  zajmuje serwer, ile z niej system odłożył na dysk (swap) i ile ma
  jeszcze NAS. Katalog żyje w pamięci (około 2,2 GB); jeśli NAS-owi jej
  brakuje, wszystko zwalnia wielokrotnie, a w logu nic o tym nie ma.
- Sprawdzone i zostawione bez zmian: rozpoznanie telefonu domownika
  kosztuje 0,02 ms na zapytanie, a strona tematu, lista muzeów i
  podpowiedzi z muzeów zatrzymują resztę serwera na 3–5 ms; przeniesienie
  ich do wątków kosztowałoby tyle samo.

## 1.145.119

- Karta dzieła nie blokuje już reszty aplikacji. Jej długie pytania do
  serwera (gdzie jest dzieło, technika, ostrzejsza kopia, opis, polski
  tytuł, fragmenty; każde czeka do pół minuty) idą osobnymi połączeniami.
  Dotąd zajmowały wszystkie cztery połączenia aplikacji z serwerem, więc
  serce, „Pokaż na ramce” i pasek postępu czekały za nimi nawet 15–30 s.
- Seria serc to jedno odświeżenie playlist, ukrytych, Propozycji dnia i
  kolejki, sekundę po ostatnim sercu, zamiast czterech pytań i dwóch
  zapisów po każdym. Strona, na którą patrzysz, odświeża się po każdym
  sercu jak dotąd.
- Konfiguracja: pomiar dysku rusza po wczytaniu reszty strony i idzie
  osobnym połączeniem (serwer ogląda dla niego każdy obraz, na NAS do
  45 s), a sekcje Claude i Gemini nie pytają o to samo równolegle.
- Miniatury z własnego serwera wczytują się po sześć naraz zamiast po
  cztery: siatka wyników wypełnia się szybciej. Limity muzeów pilnuje
  serwer, jak dotąd.
- Zapamiętane ekrany (Odkrywaj, playlisty, ukryte, Propozycje dnia)
  zapisują się poza głównym wątkiem: bez przycięć po wczytaniu Odkrywaj
  i po sercu.

## 1.145.118

- Odkrywaj nie przelicza już wszystkich kart tematów po każdym dziele,
  które doszło do katalogu. Gdy w Szukaj muzea dopisywały dzieła, serwer
  liczył karty bez przerwy (w pomiarze 5 rund w minutę, cała minuta pracy
  procesora), a wszystko inne czekało. Teraz karty liczą się najwyżej co
  10 minut; od razu jak dotąd po zmianie dnia, po nowych kartach kuratora
  i wtedy, gdy okładka straciłaby obraz (dzieło ukryte albo usunięte).
  Nowe dzieło widać więc w liczniku i okładce tematu do 10 minut później;
  w samym temacie po otwarciu jak dotąd.
- Rząd „Pod lupą” nie przegląda już całego katalogu po każdej zmianie
  dzieła (pokazanie na ramce, opis, serce): `/api/suggestions` 1,0 s →
  0,3 s w pomiarze (na NAS było 3–9 s). Te same dzieła w tej samej
  kolejności.
- Po starcie serwera indeks szukania powstaje raz, nie dwa razy pod rząd
  (13.11 na NAS 59 s i zaraz potem 29 s): drugi robił wątek, który czekał
  na pierwszy.
- Większe odpowiedzi dla aplikacji idą skompresowane (gzip): lista
  tematów 670 KB → 119 KB, rzędy Odkrywaj 550 KB → 85 KB, Propozycje dnia
  117 KB → 21 KB, strona wyników 37 KB → 7 KB. Widać to głównie poza
  domem. Obrazy, odpowiedzi dla ramki i wyniki przychodzące po kawałku
  idą jak dotąd.

## 1.145.117

- Podpowiedzi w Szukaj nadążają za pisaniem. Gdy dochodzi kolejna litera,
  serwer od razu przerywa liczenie dla poprzedniej (dotąd liczył do końca,
  a nowe pytanie czekało w kolejce). Przy szybkim wpisaniu słowa ostatnia
  podpowiedź przychodzi 0,2–0,4 s po ostatniej literze zamiast 0,8–4 s.
  Aplikacja przy jednej i dwóch literach czeka z pytaniem 250 ms zamiast
  120 ms; to, co zna sama, pokazuje jak dotąd od razu.
- Przewijanie wyników Szukaj: kolejne strony przychodzą z kolejności
  ustalonej przy pierwszej stronie (7 ms zamiast 0,45 s w pomiarze, na NAS
  było 2–12 s), także wtedy, gdy muzea w tym czasie dopisują dzieła albo
  dajesz serce. Znikają powtórki i dziury między stronami. Dzieło ukryte w
  międzyczasie nie pojawia się, serce jest zawsze aktualne, a nowe
  szukanie i pierwsza strona liczą się od nowa. Kolejność jest pamiętana
  minutę od ostatniej strony, najwyżej 5 minut. Ulubione i „Moje” liczą
  się zawsze od nowa.
- Tytuły dzieł w podpowiedziach szukane przez indeks początków słów
  zamiast przeglądu wszystkich 117 tys. tytułów: średnio 25 ms zamiast
  180 ms na literę, te same tytuły w tej samej kolejności (porównane na
  865 pytaniach).

## 1.145.116

- „Pełny kadr” na karcie dzieła pokazuje zdjęcie muzeum bez przerywanej
  linii („mróweczek”) wokół wykadrowanego dzieła.

## 1.145.115

- Na karcie dzieła „Pełny kadr”, „Fragmenty” i „Detale” stoją pod
  kolorystyką, a nie zaraz pod przyciskami. W „Pełnym kadrze” nie ma już
  dopisku „zdjęcie muzeum”, a zdanie pod miniaturą kończy się słowami
  „Prezentowane jest wykadrowane dzieło”.

## 1.145.114

- Szukanie słowem jest 3 do 4 razy szybsze (pomiar na katalogu z 13.11,
  117 tys. dzieł: „pejzaż” 1,56 s → 0,41 s, „portret kobiety” 0,68 s →
  0,23 s, jedna litera 6,0 s → 1,6 s), a lista bez filtra dwa razy
  szybsza. Serwer pamięta przy każdym dziele, czy jest obrazem do
  pokazania i jak brzmi jego tekst bez akcentów, zamiast liczyć to od
  nowa dla całego katalogu przy każdym zapytaniu. Wyniki i ich kolejność
  są te same co dotąd (porównane 1:1 na całym katalogu). Koszt: około
  125 MB pamięci serwera więcej.
- Miniatury, które serwer już ma, wychodzą szybciej, gdy serwer jest
  zajęty (szukanie, praca nocna): przy jednym zajętym wątku 23 ms → około
  2 ms na miniaturę. Serwer czyta zapisaną miniaturę jednym krokiem poza
  pętlą obsługującą zapytania, a wątki oddają sobie kolej co 1 ms zamiast
  co 5 ms.
- Konfiguracja → Claude otwiera się i odświeża od razu: liczniki „opisane
  / czekają” liczą się raz i są pamiętane, dopóki nie zmieni się dzieło,
  opis albo ustawienie (dotąd każde odświeżenie co 20 s przechodziło cały
  katalog; 0,5 s w pomiarze, na NAS 2–5 s).
- Aplikacja nie wysyła już przy każdym odświeżeniu zapytania o listę
  filtrów biblioteki, której żaden ekran nie czytał (0,7–1 s pracy
  serwera za każdym razem).

## 1.145.113

- Zdjęcia dzieł zrobione z ramą, na sztaludze albo na tle (często Muzeum
  Narodowe w Warszawie i w Krakowie) są przycinane do samego dzieła: na
  ramce, w siatkach i na karcie widać tylko obraz. W nocy Haiku wskazuje
  takie zdjęcia, a Opus ustawia narożniki dzieła, dociągane do krawędzi na
  zdjęciu; to samo dzieje się od razu po wejściu w kartę dzieła, którego
  noc jeszcze nie obejrzała. Przycięte dzieło ma przy dacie znaczek z
  narożnikami kadru.
- Na karcie przyciętego dzieła sekcja „Pełny kadr” pokazuje całe zdjęcie
  z muzeum, z zaznaczonym kadrem; dotknięcie otwiera je w całości. Grafiki
  i rysunki na arkuszu zostają z papierem; obok dwie miniatury „Z
  papierem” i „Sama odbitka” (pierwsze wybranie samej odbitki pyta Opus o
  krawędź druku).
- W menu „…” karty: „Popraw kadr” (albo „Przytnij zdjęcie”) otwiera na
  całym ekranie zdjęcie z muzeum z czterema narożnikami do przeciągania i
  lupą, a „Cofnij kadrowanie” wraca do całego zdjęcia na stałe.
- Konfiguracja → Claude: przełącznik „Kadrowanie zdjęć dzieł”.
- Znaczki niskiej rozdzielczości, iskierek restauratora i kadrowania są
  szare zamiast bursztynowych, a plakietka z samą ikonką stoi w jednej
  linii z plakietką daty.

## 1.145.112

- Konfiguracja → Claude: „Przejrzyj zapisane opisy”. Pokazuje, ile jest
  zapisanych tłumaczeń opisów muzeów i notek w starym stylu, i ile
  kosztuje każdy krok. „Sprawdź tłumaczenia”: Haiku sprawdza, czy tekst
  muzeum mówi o samym dziele; gdzie nie (np. życiorys artysty), Sonnet
  pisze notkę w jego miejsce. „Przepisz notki w nowych stylach”: notki
  sprzed stylów pisze Sonnet od nowa. Oba kroki przez pakiety Anthropic
  (połowa ceny), do czasu wyników zostają dotychczasowe teksty.

## 1.145.111

- Własne notki o dziełach (gdy muzeum nie daje opisu) piszą się w pięciu
  stylach, losowanych po kolei tak, żeby ten sam nie wypadł dwa razy z
  rzędu: opis całości, prowadzenie wzroku po obrazie, jak dzieło jest
  zrobione, temat (co znaczy scena lub motyw) i jeden łatwy do
  przeoczenia szczegół. Notka nie zaczyna się już od „Obraz
  przedstawia…” ani tak jak ostatnie notki, nie pisze, czego dane nie
  mówią, i nie kończy się powtórzeniem autora. Notki zapisane wcześniej
  zostają.
- Gdy muzeum daje jako opis tekst, który nie mówi o dziele (np. krótki
  życiorys artysty), Haiku to rozpoznaje przy tłumaczeniu i zamiast
  tłumaczenia powstaje notka Sonneta.
- Na karcie dzieła pod notką stoi tylko iskierka i „Kurator”, bez listy
  źródeł. „Pokaż oryginał” znika, gdy muzeum nie daje własnego opisu.

## 1.145.110

- Guzik „Szukaj podobnych” pod rzędem „Podobne wyglądem” na karcie dzieła
  jest teraz wypełniony na czarno z jasnym napisem, zamiast obrysu. W
  trybie ciemnym jest jasny z ciemnym napisem, jak pozostałe wypełnione
  guziki, żeby nie zlewał się z czarną stroną.

## 1.145.109

- Strona playlisty (do 160 dzieł) ma od wejścia swoją prawdziwą wysokość:
  nie podskakuje po otwarciu i przewija się do ostatniego rzędu nad
  paskiem kart. Dotąd siatka zgadywała wysokość dzieł, których jeszcze
  nie narysowała, i poprawiała ją w trakcie przewijania. Tak samo w
  Szukaj, tematach i Propozycjach dnia.

## 1.145.108

- Strona playlisty przewija się do końca i nie skacze. Dzieło, którego
  obraz nie wczytał się na ekranie (muzeum chwilowo odmawia), zostaje
  kafelkiem ze strzałką zamiast znikać i przesuwać wszystkie karty za
  nim; szerokie dzieło wchodzi na ekran razem z kartami nad nim. Tak samo
  w Szukaj, tematach i Propozycjach dnia.

## 1.145.107

- Playlista inteligentna nie ma już ustawienia „Ile dzieł”. Bierze
  wszystko, co pasuje, tak jak Szukaj, także playlisty zapisane wcześniej
  z limitem 50–300. Gdy pasuje mniej niż 100 dzieł, pod liczbą stoi jedno
  zdanie: po zapisaniu brakujące dobiorą się z muzeów w tle. Dzieje się to
  po cichu, bez paska „pobieram dzieła z muzeów”. Na ramce playlista dalej
  dobiera nowe dzieła, gdy kończą się niepokazane.

## 1.145.106

- „Podobne wyglądem” na karcie dzieła stoi nad słowami kluczowymi i
  techniką: trzy najbardziej podobne dzieła obok siebie, każde w swoich
  proporcjach, z tytułem i artystą; dotknięcie otwiera dzieło. Przycisk
  „Szukaj podobnych” z liczbą wszystkich znalezionych otwiera Szukaj z
  chipem „Podobne do: …”: wyniki od najbardziej podobnych, grupy zawężają
  je jak zwykle, można z nich zrobić playlistę.

## 1.145.105

- Propozycje dnia pokazują dzieła w całości. Siatka przycinała każde dzieło
  do kwadratu, więc rysunkom i grafikom brakowało brzegów, a obrazom
  stojącym czy leżącym połowy postaci. Teraz każda czwórka stoi w dwóch
  kolumnach jak w playliście: dzieło w swoich proporcjach, z tytułem i
  artystą pod spodem. Kolejność czwórek (karta po karcie, tak jak na
  ramce) bez zmian.

## 1.145.104

- Obraz na karcie dzieła znów wypełnia całą szerokość strony (najwyżej
  460 pt wysokości) i nie kurczy się zaraz po wejściu. Gdy wczytywały się
  kolejne części karty, strona dawała obrazowi coraz mniej wysokości, a on
  jako jedyny ustępował: The Mussel Harvest stał mały pośrodku pola. Teraz
  obraz bierze od strony tylko szerokość. Dotyczy obu widoków: „Oryginał” i
  „Na ramce”.

## 1.145.103

- Usunięte zbędne kopie dzieła nie wracają. Po starcie serwer usuwa kopie,
  które obrazy połączyły z innym dziełem, a dobieranie do playlisty
  pobierało je z muzeów z powrotem jako nowe dzieła, więc w playliście
  „Vincent van Gogh · słoneczniki” powtórki znikały i wracały. Serwer
  pamięta teraz każdą usuniętą kopię razem z kopią, która została.
- Karta playlisty w Playlistach pokazuje tę samą liczbę dzieł co strona
  playlisty: po otwarciu playlisty karta bierze liczbę i okładkę z niej, a
  liczenie po starcie serwera zna już angielskie słowa dzieł (wcześniej
  „słoneczniki” liczyły tylko dzieła opisane po polsku: 9 zamiast 19).
- Wpisane słowa (Szukaj, edycja playlisty, playlisty) szukają w tytule,
  autorze, technice, stylu i hasłach dzieła, a nie w długim opisie z muzeum.
  „Słoneczniki” nie łapią już „La berceuse”, która miała wisieć „między
  dwoma obrazami słoneczników”, a polskie „most” angielskiego „the most”.

## 1.145.102

- Fakty z sieci do studium kosztują o ponad połowę mniej. Claude
  najpierw raz szuka dzieła i szuka dalej tylko wtedy, gdy ktoś o nim
  pisał; wcześniej puszczał od razu sześć wyszukań, często ogólnych. Na
  próbie dziesięciu dzieł: 3,6 centa zamiast 8,8 za dzieło, 40 faktów
  zamiast 43, trzy badania techniczne („Jak powstawał”) zamiast jednego.
  Szacunek przy „Uzupełnij wcześniejsze studia” liczy już nową cenę.
- „Jak powstawał” w studium bez rysunków: kilka zdań (dwa-trzy, najwyżej
  cztery) o tym, jak dzieło powstawało, według badania technicznego
  znalezionego w sieci, zaraz po „Kolor i światło”. Badanie może być
  przywołane („jak pokazało badanie RTG z 1995 roku…”), ale bez linków i
  bez wzmianki o szukaniu. Rysunki modelu Google nie wyglądały dobrze i serwer ich już
  nie zamawia; dzieła, które je dostały, dostaną tekst przy otwarciu
  studium. Przełącznik przeszedł z Google do ustawień Claude.
- Wybór dzieła w podpowiedziach Szukaj („Słoneczniki · Dzieło · Vincent
  van Gogh”) wstawia tytuł razem z artystą, więc pokazuje jego słoneczniki
  zamiast wszystkich dzieł ze słonecznikami w tytule.
- Pod dziełami ze Statens Museum for Kunst przez Europeanę zamiast
  nazwiska stał numer („250_person”). Teraz jest nazwisko, a zapisane
  już dzieła poprawią się w nocy.

## 1.145.101

- Serwer nie zamiera już na pierwsze minuty po starcie. Po aktualizacji
  aplikacja czekała 30–70 s na Teraz, Playlisty i Studia, bo serwer od
  1.145.98 czyta zaraz po starcie polskie tytuły wszystkich dzieł, a to
  czytanie trzymało bazę, na którą czekało też zapytanie o stan ramki,
  i z nim cały serwer. Takie długie odczyty idą teraz osobnym połączeniem
  z bazą, a stan ramki nie czeka na bazę w głównym wątku.
- Podpowiedzi w Szukaj liczą każde hasło raz i najwyżej dwa naraz.
  Przy szybkim pisaniu kilkadziesiąt liczeń całego katalogu szło
  równocześnie i serwer stawał na kilkanaście sekund.
- Liczby wyglądu (Gemini) i dzieła z Szukaj zaległe sprzed restartu
  ruszają dopiero 1,5–3 minuty po starcie.
- Zapis zatrzymania serwera w logu pokazuje dokładne miejsce (krótszy
  stos, osobny wpis dla innych wątków).

## 1.145.100

- Resztka miesiąca na studia (Konfiguracja → Claude, karta „Resztka
  miesiąca”, domyślnie wyłączona). W ostatnich dniach okresu (domyślnie 3)
  to, co zostaje z limitu Claude ponad zapas (domyślnie 10 USD), idzie nocą
  na nowe studia dzieł przez Batch: najpierw dzieła, które kurator Studium
  dnia uznał za dobre, ale wybrał inne, potem nowe listy według tych samych
  reguł i tego samego kuratora, zaczynając od Ulubionych, playlist i
  Odkrywaj. Najwyżej 25 studiów na noc, jedno na artystę, w ostatniej dobie
  okresu już nic. Ok. 0,80 USD za studium, potem według zmierzonego kosztu.
  Te same wyłączenia co dla Studium dnia (szkice, projekty, rękopisy,
  fotografia, rzeźba, ceramika, słabe kopie). Studia przychodzą bez
  powiadomień i są w „Studiach dzieł”.
- Co zostanie po studiach, idzie na słowa kluczowe i polskie opisy dzieł
  katalogu, które ich jeszcze nie mają (Haiku przez Batch, najpierw
  Ulubione i playlisty).
- Dzień odnowienia: limit i wydatki Claude liczą się od wybranego dnia
  miesiąca, tak jak odnawiają się środki na koncie (domyślnie 1.).
- Studium dnia nie wybiera dzieła, które ma już studium.
- Nowe zadanie nocne „Studia z zapasu” w pakiecie „Odkrywaj i ramka”.

## 1.145.99

- Dwa dzieła z tą samą kopią łączą się w jedno od razu. W playliście
  „Vincent van Gogh · słoneczniki” te same obrazy stały po dwa razy pod
  różnymi tytułami („Sunflowers / Vase with Twelve Sunflowers” i „Twelve
  Sunflowers in a Vase”), bo dzieła dodane z Szukaj czekały na porównanie
  obrazów, a to czekało na pobieranie, które wstrzymuje się, gdy używasz
  aplikacji. Teraz serwer porównuje najpierw obrazy, które już ma, i od
  razu zapisuje, które są jednym dziełem. Porównanie rusza też po każdym
  dodaniu dzieł z muzeów i po otwarciu playlisty.

## 1.145.98

- Szukaj po tytule. Podczas pisania pojawiają się wiersze „Dzieło” z
  miniaturą i artystą: do trzech dzieł, których tytuł (polski albo
  oryginalny, z dowolnej kopii) ma wpisane słowa. Dotknięcie wstawia do pola
  znacznik „Tytuł”, który szuka tylko w tytułach, a nie w opisach, i
  znajduje wszystkie wersje dzieła. Muzea są pytane o ten tytuł.
- Lupa wybiera tytuł, gdy wpisane słowa są tytułem dzieła. Kolejność:
  artysta, potem tytuł, potem wygląd, na końcu zwykłe słowa.
- Szukanie wyglądem pyta też muzea. Haiku zamienia opis na dwa lub trzy
  krótkie hasła w języku każdego muzeum. Miniatury tego, co muzea
  przyniosą, dostają na bieżąco liczby Google i zostają tylko dzieła nad
  tym samym progiem co w bazie. To ok. 1 centa za szukanie. Liczby i
  miniatury zostają na serwerze, a odrzucone dzieła trafiają do katalogu
  jako zapasowe.
- Hasła dla muzeów włącza ten sam przełącznik co tłumaczenie słów w Szukaj
  (Konfiguracja → Claude).
- Karta dzieła naprawdę pokazuje rząd „Podobne wyglądem”. Aplikacja w
  ogóle o niego nie pytała, bo zapytanie wisiało na pustym widoku, który
  się nie pojawiał. Rząd pokazuje się też wtedy, gdy liczby ma tylko inna
  kopia tego samego dzieła.
- Miniatury do szukania wyglądem idą do Google w paczkach po 100 zamiast
  300, bo większa paczka raz nie zdążyła się wysłać z NAS.
- Dzieła pokazane w Szukaj, które czekają na przyjęcie do bazy, przetrwają
  restart serwera (np. aktualizację). Wcześniej kolejka była tylko w
  pamięci i znikała.
- Pełny katalog przyjmuje dzieła pokazane w Szukaj. Nocne przycinanie
  usuwa wtedy najpierw dzieła dobrane losowo, a te z Twoich wyszukiwań
  zostawia na koniec. Dzieła przyniesione, ale niepokazane, przy pełnym
  katalogu nadal nie wchodzą.
- Dzieła, które muzeum przyniosło, ale które nie pasowały do wyszukiwania
  (inny artysta, inne lata, inna technika), trafiają do bazy także bez
  miniatury na serwerze. Czekają na końcu kolejki, a miniatury są pobierane
  w tle, w tempie dozwolonym przez każde muzeum.

## 1.145.97

- Poprawka: szukanie wyglądem nie zatrzymuje już serwera. Słowa
  porównywano z całym katalogiem (115 tys. dzieł), co po aktualizacji
  zawiesiło serwer na kilka minut, razem z podglądem w zakładce Teraz. Teraz
  serwer sprawdza tylko kilka tysięcy dzieł najbliższych słowom, a wynik
  jest ten sam.
- Podpowiedzi podczas pisania liczą dzieła najwyżej dwiema naraz i
  porzucają pytania, które aplikacja już zostawiła po kolejnej literze.
- Dzieła znów dostają liczby do szukania wyglądem. Paczki 300 miniatur
  ważyły 30 MB przy limicie Google 19 MB, więc od 16:08 żadna nie
  przeszła. Za ciężka paczka dzieli się teraz na połowy.

## 1.145.96

- Szukaj: szukanie wyglądem jest częścią zwykłego szukania. Gdy wpiszesz
  dwa słowa lub więcej, lupa na klawiaturze szuka dzieł, które tak
  wyglądają. Słowa stają się znacznikiem z okiem w polu, a dzieła trafiają
  do tej samej listy wyników, więc techniki, epoki, kolory, muzea i inne
  grupy je zawężają. Gdy wpiszesz nazwisko artysty, lupa wybiera artystę.
  Wiersz, który wybierze lupa, stoi w podpowiedziach na górze, wyróżniony
  tłem i znakiem ↵.
- Z takiego wyszukiwania można utworzyć playlistę; zachowuje wygląd razem
  z pozostałymi wyborami.
- Z podpowiedzi zniknął podgląd „W muzeach” (powtarzał wpisane słowo i
  pokazywał się także wtedy, gdy baza miała dzieła). Zostali tylko artyści
  z muzeów, których nie ma w bazie, jako zwykłe podpowiedzi.

## 1.145.95

- Aplikacja: arkusz analizy kompozycji w trybie ciemnym leży na pasie
  papieru wydartym u góry i u dołu, od krawędzi do krawędzi ekranu, z
  białym włóknem wzdłuż rozdarcia i ziarnem papieru. Legenda jest jasnym
  pismem na ciemnej stronie, a plama i kreska sięgają krawędzi ekranu jak w
  trybie jasnym.

## 1.145.94

- Szukanie wyglądem przygotowuje dzieła z muzeów przez Batch Google, za
  pół ceny (ok. 6 USD zamiast 12 dla całej biblioteki). Paczki wracają
  zwykle w kilka minut, więc biblioteka będzie gotowa w ciągu doby; na
  bieżąco idą tylko Twoje pytania słowami i zdjęciem.
- Szukaj: zamiast guzika „Szukaj zdjęciem” na prawym końcu pola
  wyszukiwania jest ikonka aparatu, widoczna, gdy nic nie jest wpisane ani
  wybrane. Dotknięcie otwiera aparat, przytrzymanie pozwala wybrać zdjęcie
  z Biblioteki.
- Szukaj wyglądem: dotknięcie dzieła na liście wyników otwiera jego kartę
  i zostaje na niej (wcześniej ekran wracał sam do wyników).
- Konfiguracja → Claude: „Uzupełnij wcześniejsze studia”. Claude szuka w
  sieci faktów, których w napisanych już studiach brakuje (badania,
  losy, wystawy, odbiór), i przepisuje tekst tylko tam, gdzie wiele
  dodają. Analiza kompozycji, detale i Droga dzieła zostają bez zmian.
  W pakietach Anthropic, za pół ceny; przycisk pokazuje liczbę studiów i
  koszt.

## 1.145.93

- WikiArt: serwer nie wyłącza już WikiArt na pół godziny, gdy to on sam
  wstrzymał zapytanie (wyczerpany udział nocnych zadań w godzinowym limicie)
  albo gdy odpowiedź nie doszła. Za przerwę uznaje tylko prawdziwą odmowę
  logowania, a jej powód trafia do logu. Sesja WikiArt przeżywa aktualizację
  serwera (WikiArt daje 10 sesji na godzinę).
- Karta dzieła z muzeum pyta muzeum o pełne dane tylko raz i trzyma je na
  stałe, także po aktualizacji serwera.
- Karta dzieła z muzeum, które chwilowo nie odpowiada, pokazuje dzieło tak,
  jak widziało je wyszukiwanie, zamiast pustej karty. Gdy serwer nie ma nic,
  komunikat mówi po polsku, co się stało, zamiast „Serwer odpowiedział 502”.

## 1.145.92

- Szukanie wyglądem: w Szukaj wystarczy opisać, jak dzieło wygląda
  („mglisty poranek nad wodą”), i wybrać „Szukaj wyglądem”, albo na pustym
  Szukaj dotknąć „Szukaj zdjęciem” i wybrać zdjęcie obrazu (z muzeum,
  pocztówki, książki). Na karcie dzieła na dole jest rząd „Podobne
  wyglądem”. Szuka model Google (Gemini), tylko wśród dzieł z muzeów;
  Twoje zdjęcia nie trafiają do Google. Przełącznik i postęp w
  Konfiguracja → Gemini. Po aktualizacji serwer przygotowuje dzieła w tle
  (najpierw Ulubione, playlisty i Odkrywaj).
- Studium dzieła wybiera „Podobne dzieła” także po wyglądzie.
- Nowe studia są bogatsze: zanim Claude je napisze, szuka w sieci badań
  konserwatorskich, losów dzieła, wystaw i słów artysty, i wplata te
  fakty w tekst, bez linków i bez listy źródeł. Ok. 0,15–0,3 USD za studium,
  przełącznik „Fakty z sieci w studium” w Konfiguracja → Claude.
- „Jak powstawał” w Studium: gdy istnieje badanie techniczne dzieła, model
  Google rysuje jego kolejne etapy według tego badania (ostatni to samo
  dzieło), z opisem z badania. Ok. 0,04 USD za etap, przełącznik w
  Konfiguracja → Gemini.
- „Szukaj zdaniem” zniknęło (zastąpiło je szukanie wyglądem).

## 1.145.91

- Kolorowe kreski na arkuszu kompozycji z Gemini nie rozjeżdżają się.
  Gdy model pominął którąś kreskę, serwer potrafił wziąć za nią fragment
  samego szkicu (szare plamy i czarne smugi na pół obrazu, numery przy
  krawędzi, np. Pissarro „Wzgórze Jalais w Pontoise”). Teraz takiej
  kreski nie ma i model jest pytany o kreski drugi raz. Arkusze już
  zapisane z takim błędem dostają po aktualizacji serwera nowe kreski
  na tym samym szkicu (ok. 0,05 USD za arkusz).

## 1.145.90

- Karta dzieła ma guzik „Dodaj do playlisty” między serduszkiem a „…”
  (także w Studium dnia); z menu „…” ta pozycja zniknęła.
- Nowy arkusz playlist: okładki, liczba dzieł i ptaszek przy
  playlistach, w których dzieło już jest. Dotknięcie dodaje albo
  zabiera od razu, a arkusz zostaje otwarty, więc można zaznaczyć kilka.
  „Nowa playlista…” tworzy playlistę z dziełem w tym samym miejscu.
  Ptaszki działają po aktualizacji serwera.

## 1.145.89

- Studium dzieła tylko dla dzieł, które na nie zasługują: karta kartki ze
  szkicownika, kartki studiów i notatek, prawie pustej kartki z drobnym
  szkicem, projektu, planu, mapy czy rysunku technicznego oraz własnego
  zdjęcia nie ma przycisku „Przygotuj studium dzieła”. O bladych
  rysunkach, których nie rozstrzygają słowa muzeum ani rozkład kreski,
  decyduje raz Haiku z miniaturą. Takie prace nie zostają też Studium dnia.
- Dzieło z małym zdjęciem dostaje studium, a pierwszym jego krokiem jest
  Kreatywny restaurator („Odnawiam zdjęcie dzieła”).
- Rycina na szerokim marginesie (np. mezzotinta Lucasa) jest analizowana
  na samej odbitce, więc arkusz kompozycji wreszcie do niej pasuje.

## 1.145.88

- Kreatywny restaurator nie poddaje się po pierwszej odmowie. Gdy model
  Google uzna obraz za chroniony, restaurator próbuje do pięciu razy
  (odmowa nic nie kosztuje), bo czasem za którymś razem przechodzi. W
  pakietach odrzucone dzieło wraca samo w następnym pakiecie.
- Gdy i tak się nie uda, komunikat podaje dzieło: „Rzeź na Chios
  (studium), Eugène Delacroix” i „Restaurator odmówił pracy, bo to
  dzieło chronione”.

## 1.145.87

- Kreatywny restaurator w playliście. W menu „…” playlisty Właściciel
  ma pozycję „Kreatywny restaurator”: dzieła tej playlisty w niskiej
  rozdzielczości (poniżej 1600 px) idą do modelu graficznego Google w
  pakietach (połowa ceny, ok. 0,03 USD za dzieło) i wracają odnowione w
  ciągu doby. Ulubione odnawia się tak samo, z „…” playlisty Ulubione:
  przycisk „Odnów Ulubione” zniknął z Konfiguracji, gdzie zostało tylko,
  ile czeka w pakietach Google i ile jest odnowionych.
- „Szukaj lepszej kopii” pokazuje miniaturę zdjęcia odnowionego przez
  restauratora (i kopii wczytanej z pliku). Działa po aktualizacji
  serwera.

## 1.145.86

- Pasek barw jednakowy na karcie dzieła i w zakładce Teraz: te same
  barwy są pasmami, a te same plamkami akcentów.
- Wyraźne akcenty nie giną: gdy na pasku brakuje miejsca, wchodzą
  najbardziej wyraziste barwy, nie największe (czerwony płaszcz w
  studium Delacroix „Rzeź na Chios”). Serwer przelicza barwy biblioteki
  raz po aktualizacji.
- Barwna litografia, w której serwer widzi kilka barw (plakat
  Axentowicza „Sztuka”), ma pasek swoich farb zamiast szarej kredki.

## 1.145.85

- Arkusze kompozycji z Gemini narysowane przed nowym poleceniem szkicu są
  rysowane od nowa: z manierą obrazu, akcentami barw i głębszymi ciemnymi
  plamami. Idą przez Batch Google (ok. 0,06 USD za arkusz, w ciągu kilku
  godzin), a do tego czasu widać dotychczasowy arkusz.

## 1.145.84

- Przygotowanie studiów bez płacenia dwa razy: arkusz kompozycji z Gemini
  nie jest rysowany dla analizy, która zaraz zostanie zrobiona od nowa;
  gdy kolorowe kreski się nie udadzą, następna próba nie płaci drugi raz
  za szkic; akt, którego Google nie przyjmuje, jest próbowany 8 razy w
  sumie, a nie 8 razy w każdej z kolejnych prób; ponowna analiza ryciny z
  marginesem rysuje na istniejącym szkicu same kreski.
- Studium dnia pisane dzień wcześniej (Batch Claude) dostaje arkusz z
  Gemini też przez Batch, za połowę ceny; gdy jego dzień przyjdzie, a
  arkusza jeszcze nie ma, rysuje się od razu. Batch pyta drugi raz o
  kreski, gdy model pominął któryś znacznik, tak jak przy rysowaniu od
  razu.
- Dzieło, którego szkicu Google nie narysuje, dostaje nocą kreskę piórka
  na arkuszu serwera zamiast samych plam.

## 1.145.83

- Zmiana zaczęta tuż przed wyjściem z aplikacji kończy się sama. Wybór
  kopii, ostrzejsza kopia, ulubione, playlista czy wysłanie na ramkę nie
  kończą się już komunikatem „Przerwane, gdy aplikacja była w tle”:
  krótkie zmiany dostają od iOS chwilę na dokończenie w tle, a dłuższe
  serwer robi do końca i pamięta wynik, który aplikacja odbiera po
  powrocie. Nic nie dzieje się dwa razy. Działa po aktualizacji serwera.

## 1.145.82

- Delikatniejszy znacznik niskiej rozdzielczości. Zamiast pełnych
  kropek rastra bursztynowe schodki pikseli, jak ząbkowana krawędź
  powiększonego zdjęcia: po tytule na miniaturach i w Szukaj oraz na
  plakietce „950 px” na karcie dzieła.

## 1.145.81

- Arkusze kompozycji z Gemini są o ok. 20% tańsze: 0,12 zamiast 0,15 USD
  od razu i ok. 0,06 przez Batch. Szkic i kolorowe kreski model rysuje
  bez wstępnego „namysłu” (ten sam wygląd, szybciej), a wyjście poza
  kadr robi tańszy Nano Banana 2 Lite.
- Akty, których Google nie chce przyjąć (np. Degas), są próbowane do
  ośmiu razy, bo odmowa nic nie kosztuje i czasem za którymś razem
  przechodzi. Gdy dalej nic, dzieło zostaje z arkuszem serwera.
- Szkic na arkuszu kompozycji trzyma manierę obrazu: nie poprawia
  anatomii ani twarzy (np. Matisse zostaje płaski i w konturze), akcenty
  barw, o których mówi analiza, są na nim wyraźne, a ciemne tło i czerń
  w ciemnych obrazach są naprawdę ciemne.

## 1.145.80

- Pasek barw: kreska konturu. Obraz malowany wyraźnym konturem (Matisse,
  Bernard, Beckmann, Kirchner, „Sypialnia” Van Gogha) ma na pasku
  „Kolorystyka” cienką kreskę w kolorze swoich linii: czarną, granatową
  albo ciemnozieloną. Biegnie wzdłuż górnej krawędzi farby, okrąża jej
  początek i wraca dołem, dalej niż górą; im więcej konturów ma obraz, tym
  dłuższa. Jest płaska, w manierze techniki (smugi pędzla, brzegi
  akwareli, ziarno pastelu). Dawne obrazy o ciemnych cieniach jej nie
  dostają. Kontury dzieł już zapisanych liczą się raz po aktualizacji
  serwera, osobno od analizy barw.

## 1.145.79

- Droga dzieła nadąża za przewijaniem. Przy szybszym przewinięciu nie
  ma już pustej strony z piórem dopiero przy pierwszej kropce: linia
  jest od razu narysowana prawie do dołu ekranu, kropki na niej, a
  przystanki nad środkiem ekranu są już rozlane i podpisane, tym
  dalej, im wyżej. Przy wolnym czytaniu wszystko rysuje się jak dotąd.

## 1.145.78

- Analiza kompozycji (arkusz z modelu graficznego): najpierw widać sam
  szkic z akwarelą. Dotknięcie szkicu pokazuje wszystkie kolorowe linie
  z numerami i siatką, kolejne je chowa. Dotknięcie podpisu pod szkicem
  zostawia tylko jego linię (z siatką), ponowne wraca do samego szkicu.
  Gdy szkic jest na ekranie, a strona chwilę (2 s) stoi, adnotacje
  pojawiają się same.

## 1.145.77

- Serwer nie staje już na koniec przeliczania barw biblioteki. Po
  aktualizacji, która zmienia sposób liczenia barw, wyniki dla ok. 100
  tysięcy dzieł były zapisywane jednym ciągiem i przez ten czas serwer
  nie odpowiadał aplikacji ani ramce (107 sekund 12 listopada). Teraz
  zapisuje je porcjami po 200 dzieł i między porcjami obsługuje
  pozostałych.

## 1.145.76

- Yale: także większe miniatury bardzo długich dzieł (zwoje, fryzy)
  serwer bierze z całego pliku. Po zmianie oryginałów w 1.145.42 odmów
  Yale było w nocy 142 zamiast 524 i wszystkie pochodziły z dwóch
  przerw po takiej miniaturze, na którą Yale nie odpowiedziało na czas.

## 1.145.75

- Playlista: pod nazwą jest porządek. Zostają tam tylko reguły, które
  mówią coś więcej niż nazwa (playlista „Giorgio de Chirico” nie ma już
  pod spodem chipu „Giorgio de Chirico”), i przycisk „Prezentuj na
  ramce”. Liczba dzieł i kolejność stoją teraz nad siatką, jak jej
  nagłówek: „188 dzieł” po lewej, „Artysta, A–Z” po prawej. Stuknięcie
  kolejności otwiera ten sam wybór co „Sortuj” w menu „…”.

## 1.145.74

- Kreatywny restaurator: dzieło o niskiej rozdzielczości można dać do
  przerysowania modelowi graficznemu Google (Nano Banana 2.1), który
  zwraca je w ok. 2000 px, z ostrymi krawędziami, pociągnięciami pędzla
  i fakturą płótna. Szczegóły są dorysowane, nie odzyskane, więc takie
  dzieło ma po tytule bursztynowe iskierki zamiast kropek rastra, a na
  karcie przy „Zdjęcie dzieła” napis „Kreatywny restaurator”. Pojedynczo
  w menu „…” karty (pod „Szukaj lepszej kopii”, ok. pół minuty), a
  wszystkie Ulubione poniżej 1600 px naraz w Konfiguracji → Gemini, w
  pakietach Google za połowę ceny (ok. 0,03 USD za dzieło, do doby).
  Przerysowane zdjęcie zostaje tym samym dziełem i nocne porządki go nie
  podmieniają. „Przywróć zdjęcie muzeum” cofa zmianę. Potrzebny klucz
  Gemini w Kluczach i certyfikatach.
- Długi tytuł ze znacznikiem skraca się w środku, więc znacznik po nim
  nie ginie.

## 1.145.73

- Ponowna analiza kompozycji nie rysuje już podkładu od nowa. Gdy
  dzieło ma szkic z modelu graficznego, „Wykonaj ponowną analizę”
  zamawia u niego tylko kolorowe linie na tym samym szkicu (ok. 0,05 USD
  zamiast 0,15 USD), więc arkusz pod spodem się nie zmienia.
- Gemini ma własną stronę w Konfiguracji, pod „Claude”: osobny
  miesięczny limit (domyślnie 5 USD), wydatki w tym miesiącu i
  przełącznik arkuszy kompozycji ze stanem Batch. Wydatki Gemini i
  Claude liczą się osobno, więc limit jednego nie wstrzymuje drugiego.
  Klucz Google zostaje w Kluczach i certyfikatach.

## 1.145.72

- Studium dzieła, analiza kompozycji: arkusz rysuje teraz model
  graficzny Google (Gemini). Dzieło jest na nim studium piórkiem i
  akwarelą, a linie kompozycji są narysowane kredkami, każdy znacznik
  swoim kolorem, z numerem na samej linii w tym samym kolorze. Szkic i
  akwarela w jednym, dwóch miejscach wychodzą poza pole do krawędzi
  ekranu. Arkusz jest jasną kartką także w trybie ciemnym.
- Dotknięcie arkusza chowa linie kompozycji i zostawia sam szkic,
  dotknięcie notatki zostawia jej linię i przygasza pozostałe.
- Potrzebny jest klucz Google: Konfiguracja → Klucze i certyfikaty →
  „Google (Gemini)”. Bez klucza arkusz wygląda jak dotąd.
- Koszt: nowe studium dostaje arkusz od razu (ok. 0,15 USD, piórko za
  0,18–0,35 USD przestaje być zamawiane). Studia zapisane wcześniej
  serwer przerysowuje sam przez Batch Google'a za połowę ceny (ok.
  0,08 USD za dzieło), po 20 dzieł, w ramach miesięcznego limitu AI.
  „Wykonaj ponowną analizę” daje nowy arkusz od razu. Przełącznik
  „Arkusze kompozycji z modelu graficznego” w Konfiguracji wyłącza
  całość, a pod nim widać, ile studiów czeka i ile to będzie kosztować.

## 1.145.71

- Technika dzieła szukana od razu, gdy otwierasz kartę: dotąd serwer
  czekał z tym, aż przestaniesz korzystać z aplikacji, więc „Widok
  Delftu” i „Polonia” zostawały bez techniki (i z paskiem farby olejnej).

## 1.145.70

- Dzieła o niskiej rozdzielczości mają mały bursztynowy znacznik
  (dziewięć kropek rastra) tuż po tytule na miniaturach playlist, w
  Szukaj i w Odkrywaj, a na karcie dzieła plakietkę z liczbą pikseli
  obok roku i napis
  „Niska rozdzielczość” przy „Zdjęcie dzieła” (dotknięcie, jak dotąd,
  szuka lepszej kopii). Znacznik dostaje zdjęcie, którego dłuższy bok
  ma mniej niż 1600 px, czyli ramka musi je powiększyć co najmniej
  1,6×. Liczy się tylko rozmiar znany na pewno: muzea, które go nie
  podają (Met, Rijksmuseum, Luwr…), dostają znacznik dopiero po
  pobraniu oryginału, a dzieła z playlist i Ulubionych mają go zawsze.

## 1.145.69

- Playlisty: dzieła w playliście można sortować. W menu „…” jest
  „Sortuj”: według artysty, roku powstania, daty dodania, formatu
  (najpierw pionowe albo poziome) albo jakości, czyli rozdzielczości
  zdjęcia dzieła (najpierw największe albo najpierw najsłabsze, żeby
  łatwo znaleźć te, którym przyda się lepsza kopia). Każde kryterium da
  się odwrócić. Wybór jest zapisany przy playliście, a pod liczbą dzieł
  widać, jak są ułożone. Inteligentne playlisty są domyślnie według
  artysty, ręczne w kolejności dodawania.
- Przy wyłączonym „Losowo” ramka pokazuje dzieła playlisty w tej samej
  kolejności co aplikacja (np. po roku, przez kolejne lata).

## 1.145.68

- Inteligentna playlista nie przeskakuje już po powrocie z karty dzieła.
  Dzieła jednego artysty z tego samego roku (u de Chirico jest ich
  wiele) nie miały ustalonej kolejności między sobą: dzieło, któremu
  serwer coś dopisał (technikę i muzeum przy otwarciu karty, przeliczone
  barwy), przesuwało się na koniec swojego roku, a reszta podjeżdżała w
  górę. Teraz takie dzieła stoją według tytułu i zawsze w tej samej
  kolejności; to samo w pozostałych porządkach list i wyników.

## 1.145.67

- Studium dzieła, analiza kompozycji: rysunek piórkiem na arkuszu jest
  teraz dokładnym rysunkiem dzieła, a nie kilkoma zaznaczeniami i obłymi
  bryłami. Rysuje go Opus z obrazu w pełnej wielkości, jaką model
  czyta: nazywa temat, rysuje go forma po formie, a resztę obrazu ledwie
  zaznacza. Żeby kreski trafiały w swoje miejsce, model dostaje obraz
  dwa razy: czysty i z naniesioną siatką współrzędnych co 200 pikseli
  (bez niej Opus potrafił narysować okręt Turnera w niebie). To, co w
  temacie małe albo złożone (twarz, dłonie, łódź, żagle), jest wycinane
  z oryginału, powiększane i rysowane osobno, dlatego twarz jest twarzą,
  a nie trzema kreskami. Rysunek ma zwykle 70–110 kresek zamiast
  dwudziestu. Linie mierzone z kontrastu obrazu nie biorą już w tym
  udziału.
- Kreska piórka jest cieńsza i nierówno dociśnięta: raz jaśniejsza, raz
  ciemniejsza, grubsza tam, gdzie nacisk jest mocniejszy, cienka na
  początku i końcu. Kreski wewnątrz form (rysy twarzy, palce, fałdy) i
  te ze zbliżeń są cieńsze od obrysów. Arkusze, które już są, serwer
  rysuje nową kreską sam po aktualizacji, bez pytania modelu i bez kosztu.
- Aplikacja: kreski analizy kompozycji na arkuszu są rysowane niebieską
  kredką zamiast koloru piórka, także powtórzenia koloru, które były
  czerwone (poznaje się je po kółkach i przerywanej linii). Numery są
  pisane odręcznie tą samą kredką, w niebieskim kółku na kolorze strony,
  na arkuszu i przy podpisach pod nim.
- Koszt: rysunek piórkiem w nowym studium to ok. 0,18–0,35 USD (było
  ok. 0,045 USD), a studium zamówione „na później” ok. połowy tego.
  Nowe studium powstaje o ok. minutę dłużej. Studia, które już są,
  zachowują dotychczasowy rysunek; ich przerysowanie nocą w pakiecie
  jest gotowe, ale wyłączone do decyzji właściciela.

## 1.145.66

- WikiArt: szukanie po nazwisku artysty daje wszystkie jego dzieła, a nie
  tylko pierwsze 60. Wyszukiwarka WikiArt kończyła się na jednej stronie,
  więc z 198 prac Giorgia de Chirico ramka widziała 60. Najpierw idą
  najbardziej znane (te z wyszukiwania), potem reszta. Oryginały w WikiArt
  bywają małe: u de Chirico tylko około 40 ma 1000 px albo więcej.
- Kupowanie w Alamy: nowy przełącznik w Konfiguracji → Źródła dzieł. Gdy
  jest włączony, menu „…” dzieła ma „Kup w Alamy” (szukanie tego dzieła
  w Alamy, licencja osobista od 17 £) i „Wczytaj kupioną kopię”. Kupiony
  plik staje się zdjęciem dzieła, tak jak kopia wybrana w „Szukaj lepszej
  kopii”: serce, playlisty i kadry zostają, a „Przywróć zdjęcie muzeum”
  wraca do poprzedniego. Serwer trzyma ten plik na stałe. Alamy nie daje
  API zwykłym klientom, więc sam zakup odbywa się na ich stronie.

## 1.145.65

- Studium dzieła, analiza kompozycji: rysunek piórkiem na arkuszu znów
  jest rysunkiem modelu, jak w 1.145.60. Rysunek prowadzony po
  krawędziach obrazu z 1.145.62 okazał się gęsty i chaotyczny, więc
  został wycofany. Arkusze wracają same po aktualizacji serwera, bez
  kosztu.

## 1.145.64

- Pasek barw: rysunki i ryciny, które muzeum sfotografowało na szarej
  albo liliowej tekturze, nie mają już szaroliliowej plamki akcentu.
  Reguła z 1.145.59, która mierzy barwy bladej kartki od koloru papieru
  (zieleń i błękit u Cézanne'a), brała pas tektury wokół arkusza za
  błękitne zabarwienie. Teraz serwer rozpoznaje tekturę po tym, że
  skrajne linie zdjęcia z co najmniej dwóch stron są jednej, tej samej
  barwy, i mierzy kartkę bez niej. W próbce 530 dzieł z biblioteki
  zmienia się 13 pasków, wszystkie z takim akcentem; litografie
  Cézanne'a zostają bez zmian.
- Po aktualizacji serwer raz przelicza barwy biblioteki z miniatur
  (razem z przeliczeniem po zmianie barw do szukania, jeśli obie
  wersje przychodzą naraz).

## 1.145.63

- Szukanie po kolorze, po audycie na 530 dziełach z biblioteki. Nowa
  barwa „Beż” w arkuszu Kolor: blady, ciepły ton papieru, kości słoniowej
  i jasnej karnacji. Dotąd liczył się jako żółć albo pomarańcz, przez co
  „Pomarańcz · główny” i „Żółć · główna” znajdowały prawie same rysunki
  i ryciny (41 z 42 w próbce).
- Akcenty i udziały barw nazywa teraz jedna reguła. Ciemny brąz nie jest
  już „czerwonym akcentem”, błękit nieba jest błękitem, a nie turkusem,
  ciemna czerwień szat jest czerwienią, a nie brązem. Akcentem jest też
  barwa, która wyraźnie odstaje od reszty obrazu na co najmniej 1%
  powierzchni, choć nie zmieściła się na pasku.
- „Biel · akcent”: biel, która się wybija (piana ciemnego morza, biała
  szata), ma teraz swój znacznik i można jej szukać.
- Tonacja liczy temperaturę i nasycenie względem bieli samego obrazu.
  Czarna rycina na pożółkłym papierze jest neutralna i stonowana, a nie
  ciepła i żywa. W próbce „Ciepłe” spada z 62% do 43%, „Żywe” z 40% do
  24%, „Chłodne” rośnie z 3% do 5%.
- Poziomy barw znaczą „co najmniej”: „obecny” to co najmniej 6% obrazu,
  „wyraźny” co najmniej 28%. „Czerwień · obecna” znajduje więc także
  obraz w połowie czerwony. „Akcent” i „główny” znaczą to co dotąd.
- Po aktualizacji serwer raz przelicza barwy biblioteki (na NAS 1 do 2
  godzin); do tego czasu wyniki szukania po kolorze są mieszane. Pasek
  barw w studium się nie zmienia.

## 1.145.62

- Studium dzieła, analiza kompozycji: rysunek piórkiem na arkuszu rysuje
  dzieło, a nie kilka zaznaczeń. Serwer bierze kontury z samego obrazu:
  znajduje jego krawędzie i prowadzi po nich linie, więc twarz, dłoń,
  takielunek statku czy poręcz krzesła są dokładnie tam, gdzie są na
  obrazie.
- Rysunek jest szczegółowy przy temacie, a poza nim zostaje kilka długich
  linii albo nic. Krawędź wśród wielu podobnych (fale, deszcz, faktura
  pędzla) liczy się mniej niż samotny kontur, więc rysunek nie obrysowuje
  wszystkiego. Kreski modelu mówią już tylko, gdzie jest temat, i są
  rysowane same wyłącznie wtedy, gdy obraz nie daje prawie żadnych
  konturów. Kreskowanie ciemnych partii zostaje bez zmian.
- Arkusze rysują się na nowo same po aktualizacji serwera, także w gotowych
  studiach, bez modelu i bez kosztu. Aplikacja nie wymaga nowej wersji.

## 1.145.61

- Technika dzieł uzupełniana tam, gdzie źródło jej nie podaje (WikiArt,
  Commons, część Europeany, V&A): serwer szuka jej w rekordzie dzieła,
  na stronie Commons i w Wikidata, gdy otwiera się karta, i nocą
  (zadanie „Technika dzieł”, Ulubione i playlisty najpierw). Pasek
  Kolorystyki maluje się wtedy znalezioną techniką, więc pastel
  Wyspiańskiego „Śpiący Staś” dostaje pastel zamiast farby olejnej,
  a na karcie pojawia się „Technika”.

## 1.145.60

- Studium dzieła, analiza kompozycji: rysunek piórkiem na arkuszu trzyma
  się form obrazu. Serwer mierzy teraz każdą kreskę: dosuwa ją do
  krawędzi obrazu, która biegnie tuż obok (konturu postaci, burty,
  żagla, brzegu chmury), prostą zostawia prostą, końce skraca do miejsca,
  w którym forma się kończy. Kreska, która nie leży na żadnej krawędzi,
  i kreska, która powtarza inną, nie jest rysowana.
- Piórko ma nową instrukcję: najpierw mówi, co jest tematem obrazu
  (postać, grupa, statek, budowla, przedmioty martwej natury, a także
  to, o czym mówi analiza), i rysuje go dokładnie, większością kresek.
  Reszta obrazu dostaje najwyżej kilka długich linii wielkich podziałów
  (horyzont, brzeg ciemnej partii) albo nic; spokojne tło zostaje puste.
  Piórko ogląda też obraz w większym rozmiarze, żeby widzieć małe, ale
  ważne formy (łódź, twarz, dłoń).
- Kreskowanie ciemnych partii zostaje bez zmian.
- Nowy rysunek dostają studia robione od teraz oraz, nocą w pakiecie,
  wszystkie gotowe studia (ok. 2 centów za studium).

## 1.145.59

- Pasek barw farbą olejną dla dzieł malowanych gładko (tempera, gotyk,
  barok, w ogóle przed 1800 rokiem): pociągnięcia są równe, proste i
  jednakowo szerokie, mniej postrzępione, a jedna barwa przechodzi w
  drugą dłużej i miękcej. Dzieła z pierwszej połowy XIX wieku dostają
  to w mniejszym stopniu, późniejsze zostają żywe jak dotąd.
- Akwarela: kropka akcentu zostawia przy sobie mniej czystego papieru,
  a to, co zostaje, ma półton plamy dookoła.
- Barwy bladej kartki: serwer mierzy je teraz od koloru papieru, tak jak
  widzi je oko, więc w litografii „Kąpiące się” Cézanne'a zieleń zajmuje
  na pasku tyle co na kartce (ok. 10%), a niebo, które w liczbach jest
  chłodną szarością, jest pokazane jako osobna barwa (ok. 7%). Aplikacja
  odbija obie jako plamy pod kreską. Po aktualizacji serwer raz
  przelicza barwy biblioteki (na NAS 1 do 2 godzin); znaczniki barw i
  szukanie po kolorze działają bez zmian.

## 1.145.58

- Studium dzieła, analiza kompozycji: akwarela arkusza lepiej oddaje to,
  z czego obraz jest zbudowany. Wielka ciemna plama (burzowe niebo
  Turnera) jest teraz ciemną plamą, a nie pustym papierem ani szarością
  taką jak morze pod nią. Obraz, którego tony przechodzą jeden w drugi,
  nie zlewa się już w jedną plamę od najciemniejszego do
  najjaśniejszego miejsca.
- Miejsce o innej barwie niż otoczenie, choć równie jasne (prześwit
  błękitu w chmurach), jest osobną plamą. W obrazach pod pożółkłym
  werniksem farby jasnych i średnich tonów są mieszane dalej od siebie,
  więc szarobłękit nie ginie w brązie.
- To, co w obrazie białe, zostaje białe jak dotąd, a spokojne tła
  portretów nadal mają niedomalowane brzegi.
- Numerek znaku nie chowa się już pod linią innego znaku: gdy w jego
  miejscu biegnie cudza linia, staje krok obok.
- Arkusze mają nowy wygląd (7), więc serwer maluje je od nowa, każdy
  przy pierwszym otwarciu studium albo z wyprzedzeniem; nie trzeba nic
  robić. Bez pytania modelu, bez kosztu.

## 1.145.57

- Odkrywaj: karty malarzy nie łapią już innych osób o tym samym
  nazwisku. „Romantyzm” i „Pejzaże XIX wieku” pokazywały obok Turnera
  mezzotinty Charlesa Turnera i kilku innych Turnerów (56 dzieł z 356),
  karta z Boschem w jednej trzeciej dzieła Antonia Boscha. Tak samo
  poprawieni: Boucher, Vermeer, Leighton, Mucha, Poynter, Millet
  i Fragonard.
- Szukaj i własne playlisty z barw (np. ciepłe obrazy): serwer ocenia
  barwy tylko u dzieł, które pasują techniką i latami, zamiast pobierać
  miniatury wszystkiego, co muzeum ma na stronie. W próbie 8 dzieł
  w 39 sekund zamiast 2 w 7 minut; wyniki są te same.

## 1.145.56

- Pasek barw farbą olejną: tłusta plama na papierze pod farbą sięga
  mniej więcej o połowę bliżej i jest słabsza.
- Wypukłość farby olejnej jest spokojniejsza i zależy od dzieła: gładka
  dla tempery, gotyku, renesansu, baroku i w ogóle dzieł sprzed 1800
  roku, pośrednia dla pierwszej połowy XIX wieku, wyraźna od
  impresjonistów, a gruba jak dotąd tam, gdzie muzeum podaje styl znany
  z gęstej farby (postimpresjonizm, ekspresjonizm, fowizm). Aplikacja
  czyta to ze stylu, techniki i roku dzieła, nie z samego obrazu.
- Zakładka Teraz: barwy dzieła wracają jako wąski pasek (o połowę
  niższy niż na karcie dzieła), malowany w technice dzieła.
- Grafika i rysunek ze skalą walorów: blada barwa też jest odbijana jako
  plama (zieleń w litografii „Kąpiące się” Cézanne'a była dotąd jednym z
  szarych tonów).
- Tylko aplikacja; serwer bez zmian.

## 1.145.55

- Studium dzieła, analiza kompozycji: znaki analizy wyraźnie odcinają
  się od arkusza. Kreda jest grubsza i mocniej dociśnięta, akwarela pod
  nią jest położona cieniej (w trybie jasnym jaśniejsza, w ciemnym
  ciemniejsza), a szkic piórkiem jeszcze słabszy.
- Dotknięcie podpisu nie podkłada już żółtej poświaty pod znak:
  wskazany znak zostaje, jak był, a pozostałe znaki i podpisy mocniej
  przygasają.
- Tytuł podpisu, który zajmuje dwa wiersze, ma je teraz tak blisko
  siebie jak wiersze notki pod nim (dotąd stały szeroko rozsunięte).
- Tylko aplikacja; serwer bez zmian, arkusze zostają te same.

## 1.145.54

- Karta dzieła i Studium, pasek barw: dzieło, o którego technice muzeum
  nic nie mówi („Widok Delftu” z Mauritshuis), ma teraz pasek malowany
  farbą olejną zamiast płaskiego. Płaski zostaje dla dzieł, których
  technika nazywa coś innego (porcelana, tusz na jedwabiu), dla dzieł
  jednej barwy bez opisu i dla przedmiotów; rzeźba dalej nie ma paska.
- Barwy dzieła: duża barwa niepodobna do czterech głównych jest teraz
  pokazywana razem z nimi. Dotąd w ciemnym obrazie cztery ciemne barwy
  zajmowały wszystkie miejsca i jasne szaty (jedna ósma obrazu u
  Delacroix) znikały z paska. Po aktualizacji serwer raz przelicza barwy
  biblioteki (na NAS 1 do 2 godzin); szukanie po kolorze działa bez zmian.

## 1.145.53

- Studium dzieła, analiza kompozycji: to, co wylewa się poza kadr, jest
  jedną jednolitą plamą w kolorze tej, która w tym miejscu dochodzi do
  ramki. Wcześniej margines dostawał lustrzane odbicie obrazu (drugie
  krzesło obok krzesła).
- Biel na obrazie zostaje bielą na arkuszu: białe tkaniny, piana, obrus
  są czystym papierem (w trybie ciemnym jasną farbą) zamiast kremowej
  plamy jak twarz obok. Zażółcenie starego werniksu nie przeszkadza.
- Znaki analizy są teraz w kolorze rysunku (ciemne na jasnej stronie,
  jasne na ciemnej), trochę mocniejsze i grubsze niż szkic piórkiem, a
  sam szkic pod nimi jest słabszy. Powtórzenia koloru zostają czerwone.
- Dotknięcie podpisu z numerkiem pod arkuszem podświetla jego znak na
  arkuszu, a pozostałe znaki i podpisy przygasają; drugie dotknięcie to
  cofa.
- Numerek znaku nie zakrywa już grotu strzałki: przy strzałce stoi obok
  środka jej drogi, a żaden numerek nie trafia w pobliże grotu.
- Po aktualizacji serwer robi arkusze od nowa, w tle.

## 1.145.52

- Studium i karta dzieła, pasek barw grafiki i rysunku: gdy odbitka albo
  rysunek jednej barwy ma też barwną plamę (łosoś i żółć na japońskim
  drzeworycie, podkolorowany detal ryciny), plama jest teraz na skali
  walorów: odbita płasko własną farbą w swoim miejscu, pod rzadszymi
  kreskami. Dotąd znikała wśród brązów. Grafika, w której barwy jest
  dużo (od ok. jednej trzeciej), ma jak dotąd pasek odbitek farb.

## 1.145.51

- Karta dzieła, „Kolorystyka”: zamiast płaskiego paska z procentami jest
  pasek barw w technice dzieła, ten sam co w Studium („Kolor i światło”):
  olej, akwarela, pastel, kreska ryciny i rysunku, odbitki farb grafiki
  barwnej. Na karcie jest od razu gotowy, bez ruchu, i bez procentów pod
  spodem; jest też wyższy (26 pt zamiast 18).
- Fotografia ma własny pasek: tony od najciemniejszego do najjaśniejszego
  w jednym gradiencie, z lekkim ziarnem (także w Studium).
- Rzeźba nie ma paska barw na karcie (znaczniki barw zostają). Dzieło,
  którego technika nic nie mówi, ma pasek płaski, bez procentów.
- Akwarela i gwasz: małe, wyraźne barwy nie mają już własnego odcinka
  paska. Plama omija kółko czystego papieru, a w nim leży kropla barwy
  akcentu, która z jednej strony zachodzi na plamę i w nią wpływa
  (w Studium widać, jak się rozlewa).
- Pastel, kredka, kreda: akcent to łatka mocno dociśniętych kresek po
  skosie w drugą stronę, nisko na pasku i trochę pod jego linią.
- Zakładka Teraz: cienki pasek barw pod tytułem zniknął.
- Barwy dzieła: biel, która wyraźnie się wybija (piana na ciemnym morzu,
  biały czepek w ciemnym wnętrzu), jest teraz wśród barw obrazu jako
  akcent. Po aktualizacji serwer raz przelicza barwy biblioteki (na NAS
  1 do 2 godzin); szukanie po kolorze działa bez zmian.

## 1.145.50

- Studium dzieła, analiza kompozycji: arkusz nie kończy się równo na
  kadrze. W jednym albo dwóch miejscach plama akwareli wylewa się poza
  kadr i sięga bocznej krawędzi ekranu, a jedna kreska piórka, która
  kończy się przy boku, biegnie dalej poza kadr. Po aktualizacji serwer
  robi arkusze od nowa, w tle.

## 1.145.49

- Studium dzieła, analiza kompozycji: akwarela wchodzi płynnie, po całym
  arkuszu naraz, zamiast rozlewać się z kilku miejsc. Piórko, kreskowanie
  i kreda rysują się jak dotąd.
- Akwarelowy podkład jest znów jaśniejszy, taki jak przed 1.145.47;
  zostaje ogólniejszy (mniej plam, bardziej płaskich). Po aktualizacji
  serwer robi arkusze od nowa, w tle.

## 1.145.48

- Odkrywaj, kafelek studium dnia: obraz jest ostry, bo zamiast małej
  miniatury rozciągniętej na szerokość ekranu wchodzi na nią oryginał
  dzieła (ten sam, który potem otwiera strona studium, więc ta pokazuje
  go od razu). Kafelek ma też efekty kart „Pod lupą”: jaśniejszy obraz
  (HDR) u góry, rozbłysk przesuwający się z obrotem telefonu i całą
  kartę lekko uniesioną nad stronę, z cieniem.

## 1.145.47

- Studium dzieła, analiza kompozycji: arkusz jest gotowy, zanim otworzysz
  studium. Dotąd serwer robił go dopiero przy pierwszym otwarciu, stąd
  czekanie na pustej kartce z siatką. Teraz robi arkusze z góry, w tle,
  zaczynając od najnowszych studiów. Po aktualizacji potrzebuje na to
  trochę czasu, bo wszystkie arkusze robi od nowa.
- Arkusz rysuje się na żywo: najpierw piórko, kreska po kresce, potem
  spod niego rozlewa się akwarela, piórko kreskuje cienie, a na końcu
  po kolei wchodzą znaki kredą. Trwa to niecałe trzy sekundy i zaczyna
  się, gdy arkusz jest na ekranie. Przy włączonym „Ogranicz ruch” arkusz
  pojawia się od razu.
- Akwarelowy podkład jest ciemniejszy na jasnej stronie, żeby biała kreda
  była na nim lepiej widoczna, i jeszcze ogólniejszy: mniej plam, bardziej
  płaskich.
- Piórko rysuje więcej konturów (14–22 zamiast 9–16) i dokładniej, a
  ciemniejsze partie obrazu są gdzieniegdzie kreskowane. Kreskowanie mają
  wszystkie arkusze od razu. Kontury w gotowych studiach serwer rysuje od
  nowa nocą, w pakiecie (zadanie nocne „Słowa kluczowe i polskie
  teksty”), za około 2–3 centy za studium.
- Każdy znak kredą leży na własnej płaszczyźnie nad arkuszem: przy
  przechylaniu telefonu główny znak przesuwa się najbardziej, kolejne
  coraz mniej, więc łatwiej je od siebie odróżnić.

## 1.145.46

- Odkrywaj, okładki kart: ryciny i rysunki na kafelkach są przybliżone
  do samej pracy. Serwer rozpoznaje papier, karton passe-partout albo tło
  fotografa wokół dzieła (jedna jasna, równa barwa przy krawędzi) i
  kafelek pokazuje tylko to, co na nim narysowane lub odbite, z wąskim
  oddechem papieru. Akwaforta Goi na szerokim arkuszu nie wygląda już
  jak błąd. Tak samo okładki playlist (kafelki w Playlistach, nagłówek
  playlisty, „Teraz prezentowane”, „Propozycje dnia”). Karta dzieła,
  przeglądarka i ramka dalej pokazują cały arkusz.
- Odkrywaj, okładki kart: serwer wybiera na okładkę najpierw obrazy
  (malarstwo), nawet gdy w propozycji przeważają ryciny i rysunki; w
  środku propozycji nic się nie zmienia. Karty o grafice lub rysunku
  (grupa „Grafika i plakat”, propozycje z techniką ryciny, rysunku albo
  plakatu bez malarstwa) mają na okładce swoje ryciny i rysunki jak
  dotąd. Tak samo wybierana jest okładka „Motywu dnia”.

## 1.145.45

- Studium dzieła, „Kolor i światło”: ryciny, rysunki, grafiki i plakaty
  mają własny pasek barw zamiast płaskich prostokątów. Dzieło jednej
  barwy (rycina, akwaforta, drzeworyt, rysunek piórkiem, ołówkiem lub
  węglem) dostaje skalę swoich walorów od najjaśniejszego do
  najciemniejszego, zrobioną kreską: rzadką w świetle, krzyżowaną w
  cieniu, rysowaną kreska po kresce na skrawku papieru w barwie tuszu
  dzieła. Rycina ma równą kreskę rylca i odcisk płyty, rysunek piórkiem
  swobodniejszą kreskę w brązie, ołówek miękką kreskę z ziarnem papieru.
  Grafika barwna i plakat dostają odbitki swoich farb: każda barwa jako
  płaska plama na papierze, odbijana po kolei, z lekkim przesunięciem
  pasowania; drzeworyt barwny z usłojeniem deski, litografia i plakat z
  ziarnem kredki i znaczkami pasowania. Próbki farb przy nazwach są
  zrobione tak samo, na skrawkach papieru. Fotografie zostają przy
  płaskim pasku.

## 1.145.44

- Studium dzieła: przerabianie zapisanych analiz kompozycji na arkusze
  idzie teraz pakietem, wolniej, ale taniej. Pytania do Opusa (analiza i
  tekst) serwer zamawia przez Batch API za połowę ceny, więc jedno
  studium kosztuje około 0,10 USD zamiast 0,15, a odpowiedzi przychodzą w
  ciągu minut do godzin. Do tego czasu studium pokazuje dotychczasową
  analizę. „Wykonaj ponowną analizę” i studium bez analizy dalej są
  robione od razu.
- Przerabiane są też studia, w których właściciel sam wybrał jedną z
  wersji analizy: nowa analiza dochodzi jako kolejna wersja i jest
  pokazywana, wcześniejsze zostają do wyboru. Powrót do starszej wersji
  po przerobieniu jest już uszanowany.

## 1.145.43

- Studium dzieła, „Analiza kompozycji”: rysowana jak arkusz studyjny.
  Pod znakami leży arkusz z rysunkiem dzieła piórkiem na podkładzie
  akwarelowym (przełącznikiem można wrócić do samego obrazu). Znaki są
  białą kredą z ziarnem, jest ich 3–5, a powtórzony kolor zaznacza nowy
  znak „echo” czerwienią. Rysunek lekko unosi się przy przechyleniu
  telefonu, z cieniem tylko wtedy. Analizę pisze nowa instrukcja, która
  mówi, czego w obrazie szukać, a sprawdzenie zacieśnia za duże pętle.
  Rysunek piórkiem kosztuje około 0,02–0,03 USD na studium. Zapisane
  studia serwer przerabia sam, w tle, po jednym (około 0,15 USD na
  studium, w ramach miesięcznego limitu); poprzednia analiza zostaje
  zapisana, a analiza wybrana ręcznie spośród wersji zostaje jak jest.

## 1.145.42

- Oryginały z Yale: serwer pobiera cały plik i zmniejsza go u siebie.
  Yale liczy rozmiar 4000 px od kilku do kilkudziesięciu sekund i czasem
  odpowiada błędem, po którym przez jakiś czas nie szły też jego
  miniatury ani nowe dzieła (524 odmowy w nocy 11/12 listopada); cały
  plik oddaje w pół sekundy.

## 1.145.41

- Odkrywaj: karty „Dziś dla Ciebie” zapisane przed 1.145.14 (karty
  kuratora i tygodnia) znowu dają się odczytać. Przez ten błąd karty
  Odkrywaj i Propozycje dnia nie odświeżały się w nocy, a po restarcie
  serwera Odkrywaj mogło się nie ładować.

## 1.145.40

- Playlisty zrobione z kart Odkrywaj (tematy, epoki, pory roku, „Sztuki
  inne”) są dopełniane tak jak Twoje własne playlisty: tym, co na te
  same słowa i lata pokazuje Szukaj. Dotąd serwer losował strony muzeów
  według stylu; w próbie „Morze i statki” przynosiło tak 3 dzieła na 10
  nie o morzu, a „Złoty wiek” osiem rycin jednego autora. Teraz dzieła
  są na temat, autorzy różni, a zapytań do muzeów jest mniej (dla
  morza 13 zamiast 24).
- Bez zmiany zostają karty autorów (np. „Romantyzm”: losowanie lepiej
  miesza autorów), „Arcydzieła muzeów” i karty barw („Kolor i nastrój”):
  dla barw sposób Szukaj okazał się wielokrotnie wolniejszy.

## 1.145.39

- Studium dzieła: gdy studium jest właśnie pisane, a aplikacja ma otwartą
  jego stronę, serwer szuka w muzeach „dzieł późniejszych” raz, nie dwa
  razy. Dotąd strona zaczynała to samo szukanie obok studium: pytania
  do muzeów szły podwójnie, a pasek postępu studium czasem pomijał
  krok szukania dzieł późniejszych. Gotowe studia bez zmian.

## 1.145.38

- Studium dzieła, „Droga dzieła”: rysunków piórkiem przy drodze jest
  więcej. Dotąd najwyżej trzy na drogę i nigdy przy sąsiednich
  przystankach; teraz mniej więcej przy dwóch przystankach z trzech,
  byle nie przy trzech z rzędu. Statek na morzu jest ponad to, a gdy
  dzieło przepłynęło dwa morza, statki są dwa. To, co zdarzyło się
  dwa razy (dwie sprzedaże), może być narysowane dwa razy, daleko od
  siebie; widok miejsca nadal tylko raz. Droga „Wielkiej fali” ma teraz
  Fudżi, statek, monety i zwój z pieczęcią przy spadku z 1913 roku.
- Studium dzieła, „Kolor i światło”: akcenty na pasku barw są większe.
  Na pasku olejnym pacnięcie jest około dwa razy dłuższe (30–42 punkty
  zamiast 17–26) i prawie tak wysokie jak pasek. Na pasku akwarelowym
  i pastelowym, gdzie każda barwa ma swoje miejsce w rzędzie, najmniejsza
  barwa ma co najmniej 20 punktów szerokości zamiast kilku.

## 1.145.37

- Mniej zapytań do muzeów (etap 6b): dobieranie katalogu i dopełnianie
  playlist z kart Odkrywaj korzystają z tych samych zapamiętanych stron
  wyników co Szukaj i zestawy. Strona, o którą serwer pytał niedawno, nie
  jest pytana drugi raz, a kolejne dopełnienie playlisty zaczyna tam,
  gdzie poprzednie skończyło. W tym, co widać, nic się nie zmienia.

## 1.145.36

- Porządki w kodzie nocnych zadań modeli (etap 6a): Sędzia kopii, Strażnik,
  Nocny przegląd i Kurator korzystają z jednej wspólnej pętli zamawiania
  i odbierania odpowiedzi zamiast czterech kopii. W działaniu nic się nie
  zmienia.

## 1.145.35

- Autorzy zapisani z dopiskiem muzeum („Winslow Homer, American”,
  „Juste-François Boucher, French”) są szukani w Wikidacie pod samym
  nazwiskiem. Dotąd serwer pytał o „American Winslow Homer” i nikogo nie
  znajdował: dotyczyło to 527 zapisów, głównie ze Smithsonian. Dzięki temu
  ich dzieła trafiają do właściwej osoby, a syn architekt nie łączy się
  już z ojcem malarzem.
- „Joshua Reynolds” i „Sir Joshua Reynolds” oraz „Palma il Giovane” i
  „Jacopo Palma il Giovane” stają się jednym autorem. Myliły je daty:
  „XVIII wiek” zapisany jako rok 1700 i rysunki datowane rokiem urodzenia
  autora.
- Po aktualizacji serwer pyta Wikidatę ponownie o około 2700 zapisów,
  raz, w tle. Poprawione łączenie autorów widać po tej rundzie.
- Powiadomienie o urodzinach autora nie ma już w tytule dopisku muzeum.

## 1.145.34

- Oryginały dzieł są odtąd przechowywane z dłuższym bokiem do 4000 px
  zamiast 2560. Widać to przy powiększaniu dzieła w aplikacji, w detalach
  studium i przy kadrowaniu. Obraz wysyłany na ramkę ma nadal 2560 px,
  czyli tyle, ile ekran.
- Każde muzeum jest pytane o tyle, ile naprawdę ma. Serwery, które mały
  skan sztucznie powiększały do żądanego rozmiaru (Yale, Wellcome), dają
  teraz plik w jego prawdziwej wielkości. Małe skany Getty, których dotąd
  nie dało się pobrać, wracają w całości. Granice samych muzeów zostają:
  AIC 3000 px, Cleveland 3400, V&A 2500, Wikimedia Commons 3840.
- Oryginały pobrane wcześniej i przycięte do 2560 px serwer pobiera nocą
  ponownie, większe: najpierw Ulubione, potem playlisty, potem dzieła
  ostatnio oglądane, do 300 na noc.
- Większy oryginał zajmuje około 2,4 raza więcej miejsca. W tym samym
  limicie oryginałów (Konfiguracja, domyślnie 3000 MB) zmieści się ich
  więc mniej. Gdy limit jest pełny, większe oryginały przestają dochodzić
  i czekają, aż go podniesiesz; Ulubione nie wypychają się nawzajem.

## 1.145.33

- „Ten sam autor” jest odtąd jedną regułą w całym serwerze. „Inne dzieła
  autora” na karcie, Studium dnia, „Na później” i tematy Odkrywaj pytają
  o autora tak samo jak Szukaj, i tak samo, od którego dzieła zaczniesz.
- Do dzieł autora dochodzą te zapisane inaczej: „Edgar Degas” i „Hilaire
  Germain Edgar Degas”, „Hieronim Bosch” i „Hieronymus Bosch”, „Winslow
  Homer, American” i „Winslow Homer”. W katalogu to około 40 tysięcy
  dzieł, które trafiają do właściwych autorów.
- Spod autora znikają kopie i naśladowcy („Follower of Rembrandt”,
  „Według Albrecht Dürer”), dzieła, których autorstwo muzeum cofnęło
  („formerly attributed to”), następcy o tym samym imieniu (Hiroshige II)
  i imiennicy (Stanisław Witkiewicz i Stanisław Ignacy Witkiewicz,
  Rembrandt i Rembrandt Peale). Około 3,5 tysiąca dzieł.

## 1.145.32

- Studium dzieła, „Droga dzieła”: przy drodze pojawiają się małe rysunki
  piórkiem, kilka kresek tą samą stalówką co kreska drogi. Miejsca:
  wieża Eiffla przy Paryżu (od 1889 roku, wcześniej Notre-Dame), Fudżi
  przy Japonii, Big Ben, Statua Wolności, kamienice Amsterdamu, wiatrak,
  Koloseum, gondola, kolumna Zygmunta, kościół Mariacki i inne. Zdarzenia:
  monety przy sprzedaży, młotek przy aukcji, prezent przy darze, zwój
  z pieczęcią przy spadku, pusta rama przy kradzieży, hełm przy wojnie,
  pędzel przy konserwacji, statek na morzu, które dzieło przepłynęło.
  Razem 33 motywy.
- Rysunki są okazjonalne: najwyżej trzy na drogę, nigdy przy sąsiednich
  przystankach, żaden dwa razy. Rysują się kreska po kresce, gdy pojawi
  się tekst przystanku, w wolnym miejscu obok jego plamy; gdzie miejsca
  nie ma, rysunku nie ma.
- Rysunek dobiera aplikacja z miasta, roku i rodzaju przystanku, które
  serwer podaje od pierwszych dróg. Dlatego drogi opracowane wcześniej
  mają je tak samo jak nowe, bez ponownego opracowania.

## 1.145.31

- Rijksmuseum: 111 dzieł miało w katalogu słowo „@language” zamiast
  rodzaju albo autora (ślad błędu czytania sprzed 10 listopada). Serwer
  odczyta je nocą ponownie z rekordów muzeum, razem z dziełami, których
  rodzaj nic mu nie mówił. Nowe zadanie nocne „Rodzaj i autor czytane
  ponownie” robi to raz, przeważnie bez pytania muzeum.
- Rijksmuseum: serwer czyta wszystkie rodzaje, którymi muzeum opisuje
  dzieło, nie tylko pierwszy. Portrety „grisaille” są przez to obrazami
  (35 w katalogu), projekty rysunkami, a kartki z albumów fotografiami.
- Projekt plakatu, który muzeum nazywa rysunkiem, jest w Rysunku
  i w Plakatach, nie w Grafice. Przedmioty, które Rijksmuseum nazywa
  tylko po niderlandzku (gałki lasek, tkaniny obiciowe, wazy), trafiają
  do „Ceramika i rzemiosło”.

## 1.145.30

- Najlepszą kopię dzieła wybiera teraz obraz, a dopiero potem źródło.
  Gdy katalog ma kilka kopii tego samego dzieła, pokazywana jest ta
  z obrazem wystarczającym na ramkę; dotąd pierwsza była zawsze kopia
  zachowana, nawet mała. Dziewczynę z perłą i Alegorię malarstwa
  pokazywała kopia o boku 400 px, teraz kopie o boku 4548 i 7377 px.
- Obraz olejny i rysunek albo grafika o tym samym tytule i autorze to
  dwa dzieła, nie kopie jednego („Cypresses” van Gogha z Met i rysunek
  z Chicago).
- Serce przechodzi nocą na lepszą kopię tego samego dzieła, jeśli taka
  jest w katalogu. Kopia z własnym kadrem zostaje. Zachowane kopie nie
  znikają z list.

## 1.145.29

- Studium dzieła, „Kolor i światło”: na pasku barw jest także mała, mocna
  plama koloru, która przyciąga wzrok, choć zajmuje ułamek procenta
  obrazu: czerwień okiennicy na „Uliczce” Vermeera, słońce na „Impresji”
  Moneta. Dotąd serwer liczył akcent dopiero od 0,4% obrazu i nie
  odróżniał go od dużej barwy o podobnym odcieniu (czerwień okiennicy
  brał za cegłę). Taka plama pojawia się jako pacnięcie na wierzchu, tak
  jak dotychczasowe akcenty, także na karcie dzieła.
- Po aktualizacji serwer raz przelicza barwy wszystkich dzieł z ich
  miniatur, więc dotyczy to także studiów przygotowanych wcześniej.
- Szukaj, Kolor: taka plama liczy się też jako akcent, więc „Uliczka”
  wychodzi pod „Czerwień · akcent”. Dzieła monochromatyczne (rycina
  z małą pieczątką kolekcjonera) zostają monochromatyczne i akcentu
  nie dostają.

## 1.145.28

- Porządki: serwer nie liczy już i nie trzyma oceny „na e-papierze”, której
  od kilku wydań nikt nie czytał. Nic się nie zmienia w tym, co widać.

## 1.145.27

- Studium dzieła, „Droga dzieła”: kropka przystanku wyrasta z samej
  kreski. Pióro zatrzymuje się w tym miejscu na pół sekundy i dociska,
  a kreska pęcznieje w kroplę: od swojej grubości do pełnej kropki, raz,
  bez powiększania i cofania. Kropla ma szpic leżący wstecz na kresce,
  więc jest jej pogrubieniem, a nie znakiem położonym na wierzchu.
  Dopiero potem kreska rusza dalej. Przy szybkim przewijaniu postój jest
  krótszy.
- Koniec kreski rysuje się wyżej nad paskiem zakładek (64 pt zamiast
  20), żeby powstawanie kropki było dobrze widać.
- Plamy pod tekstami nie mają już zacieku spływającego w dół.

## 1.145.26

- Przedmioty i książki, które uchodziły za obrazy, trafiają do „Sztuk
  innych”: miecze, instrumenty, ubrania, meble, lampy i naczynia do
  „Ceramika i rzemiosło”, brązy, terakoty, maski i kamee do „Rzeźba”,
  książki (głównie z Met) do „Rękopisy i miniatury”. Muzea nazwały je
  inaczej, niż serwer się spodziewał, więc pojawiały się w tematach
  malarskich, także wśród „Arcydzieł muzeów”. W katalogu to około 870
  dzieł. Zostają w swoich grupach, nic nie jest usuwane poza jedenastoma
  okazami przyrodniczymi z Europeany.
- Dobieranie nie bierze już takich przedmiotów jako obrazów.
- Brakujące techniki: ksylografie z kopenhaskiego SMK i ekslibrisy są
  grafiką, odrysy i szkicowniki rysunkiem, greckie plakaty plakatami.
  Filtr techniki w Szukaj znajduje przez to około 470 dzieł więcej.

## 1.145.25

- Studium dzieła, „Kolor i światło”: pasek kolorów obrazu olejnego jest
  malowany jak gradient. Główne kolory leżą jedno na drugim: każde
  pociągnięcie zaczyna się w mokrej farbie poprzedniego i niesie ją
  dalej, więc kolor przechodzi w kolor płynnie, a pociągnięcia nadal
  widać. Tylko ostatnie kończy sucho.
- Małe kolory z końca palety to akcenty: pacnięcia pędzlem położone na
  wierzchu, na samym końcu, z dala od łączeń pociągnięć.
- Pod paskiem papier nasiąka olejem: wokół farby powoli wychodzi tłusta
  plama, taka sama jak wokół pacnięć farb.

## 1.145.24

- Trzy dzieła przestają uchodzić za coś, czym nie są: dwa szkice Cézanne'a
  z Cleveland („Sketch of Madame Cézanne”), które serwer brał za odwrocie
  obrazu, i obraz „Old Woman Plucking a Fowl” z National Gallery of Art,
  który muzeum opisało jako fotografię, choć to olej na płótnie z około
  1650 roku. Odwrocie rysunku i arkusz opisany z obu stron są odtąd
  dziełami, więc serwer nie odrzuca już dwustronnych rysunków z muzeów.

## 1.145.23

- Odkrywaj pokazuje najpierw dobre dzieła. Strona tematu zaczynała się od
  arcydzieł muzeów, a dalej szli autorzy alfabetycznie, z dziełami bez
  autora na początku, codziennie tak samo. „Sztuka polska” otwierała się
  sześcioma obrazami Gierymskiego i siedmioma Malczewskiego i nie dochodziła
  do Matejki, a „Arcydzieła muzeów” 24 anonimowymi starożytnościami. Teraz
  o miejscu decyduje to, czy muzeum uznaje dzieło za ważne, czy znamy
  autora, czy dzieło ma opis i duży, ostry obraz. Kolejne prace tego samego
  autora i z tego samego muzeum stoją dalej, więc na stronie jest około
  dwa razy więcej autorów.
- Strony tematów zmieniają się co dzień: mniej więcej połowa pierwszych
  dzieł jest następnego dnia inna. Propozycje dnia biorą pierwsze dzieła
  każdej karty, więc też są co dzień inne.
- Szukaj układa wyniki jak dotąd, a Studium dnia wybiera według własnych
  kryteriów.
- Stara ocena e-papieru nie ustala już żadnej kolejności. Okładki playlist
  pokazują ich najlepsze dzieła według tej samej oceny co Odkrywaj.

## 1.145.22

- Studium dzieła, „Kolor i światło”: próbki farb malowane w technice
  dzieła są zawsze duże, także przy farbach tylko prawdopodobnych
  (pacnięcie olejne, plama akwareli i kreskowanie pastelą takie same jak
  przy farbach pewnych). O tym, że farba jest tylko prawdopodobna, mówi
  jej opis.
- Próbki pojawiają się wcześniej: pierwsza rusza w połowie malowania
  paska kolorów, a nie po jego końcu, kolejne idą po sobie szybciej, a
  każda zaczyna się już wtedy, gdy wsuwa się na ekran od dołu, więc obok
  nazwy farby jest od razu.

## 1.145.21

- Studium dnia wybiera teraz także spośród dzieł Metropolitan Museum,
  Rijksmuseum, Muzeum Narodowego w Warszawie i w Krakowie, Luwru, Getty,
  Paris Musées i Cleveland. Te muzea nie podają rozmiaru obrazu, serwer
  zapisywał im rozmiar miniatury i odrzucał je jako za małe skany: odpadała
  ponad połowa dzieł, w tym prawie wszystkie, które muzea same oznaczają
  jako najważniejsze. Kryteria wyboru się nie zmieniają, prawdziwie małe
  skany dalej nie zostają Studium dnia.

## 1.145.20

- Studium dzieła, „Droga dzieła”: kropka przystanku pojawia się jako
  kleks w chwili, gdy mija ją kreska, nisko na ekranie. Plama pod tekst
  wylewa się z niej później, gdy przy dalszym przewijaniu kropka dojdzie
  w okolice środka ekranu, i wtedy rusza od razu. Tak samo czerwony kleks
  na końcu drogi i czerwone kleksy przy „Dalszych losach”. Kropka wyprawy
  na wystawę nadal pojawia się na końcu swojej odnogi. Przy cofaniu strony
  kropka znika, gdy kreska cofnie się ponad nią.

## 1.145.19

- Serwer nie proponuje już sam detali, reprodukcji, znaczków, dokumentów,
  czarno-białych kopii ani kopii z Openverse, także wtedy, gdy mają serce
  albo leżą na playliście: nie trafiają do Odkrywaj, Propozycji dnia,
  Studium dnia ani między inne dzieła autora. W Ulubionych, na playlistach
  i w Szukaj zostają jak dotąd. Rzeźba, ceramika, fotografia i rękopisy
  pokazują się w Odkrywaj tylko w swojej grupie „Sztuki inne”.
- Narzędzie do porządków w regułach: cały katalog (same opisy dzieł) można
  pobrać z serwera i wypróbować na nim zmianę, zanim trafi na ramkę.

## 1.145.18

- Karta dzieła pokazuje jego detale, czyli wycinki, które serwer znalazł
  i trzyma osobno jako kopie: pasek „Detale”, a dotknięcie detalu otwiera
  go na całym ekranie. Na karcie detalu jest „Całe dzieło” i pasek „Inne
  detale”.

## 1.145.17

- Duże obrazy, które powtórki pobierają z muzeów, żeby sprawdzić, czy mały
  obraz jest detalem większego dzieła, nie są już wyrzucane po porównaniu.
  Zostają jako oryginały dzieł: karta dzieła otwiera się od razu w pełnej
  jakości, a następne powtórki nie pobierają tego samego drugi raz
  (pobieranie zajmowało 23 z 29 minut powtórek). Mieszczą się w limicie
  miejsca na oryginały i przy braku miejsca znikają pierwsze, przed
  dziełami oglądanymi i Ulubionymi.

## 1.145.16

- Studium dzieła, „Droga dzieła”: przy linii nie ma już białych „korekt”
  ani białych dotknięć na kropelkach tuszu. Kropelek przy zakrętach jest
  tyle samo co dotąd.
- Gdy strona jest przewijana szybko, rysunek za nią nadąża: kreska goni
  dół ekranu wielokrotnie szybciej, a plamy i opisy przystanków, które
  są już wysoko na ekranie, pojawiają się w ułamku sekundy zamiast
  w kilka sekund, nadal jeden po drugim. Przy spokojnym czytaniu tempo
  jest takie jak dotąd. To samo dotyczy „Dalszych losów”.
- Kropka przystanku ląduje jak kleks spod stalówki: w jedną dziesiątą
  sekundy rozpryskuje się ponad swój rozmiar, z poszarpanym brzegiem,
  i zaraz się uspokaja. Zostaje nie całkiem okrągła, każda trochę inna.

## 1.145.15

- Porządki w regułach doboru dzieł, etap 4, pierwszy krok (bez zmiany
  tego, co widać). Serwer ma jedną listę powodów, dla których coś nie jest
  obrazem na ramkę (detal, reprodukcja, znaczek, zdjęcie dzieła w ramie,
  rzeźba i tak dalej), i jedną tabelę, która mówi, co z tego obchodzi
  katalog, Szukaj, Studium dnia, muzea, Strażnika i powtórki. Dwadzieścia
  miejsc, które dotąd składały te reguły każde po swojemu, pyta teraz tę
  tabelę; odpowiedzi są te same co przedtem.
- Zestaw wzorcowy zna teraz Twoje zachowane detale, reprodukcje i znaczki:
  z niego powstanie lista do Twojej decyzji, zanim cokolwiek zmieni się
  w propozycjach.
- Wyłączanie serwera czeka na zapis do bazy, który właśnie trwa w tle.
  Do tej pory zamknięcie bazy w trakcie takiego zapisu potrafiło wywrócić
  proces (rzadko, przy wyłączaniu; częściej w testach przed wydaniem).

## 1.145.14

- Porządki w regułach doboru dzieł, etap 3. Z karty dzieła znika wiersz
  „Na e-papierze”: próg tej oceny nie działa od końca października,
  a wskaźnik sugerował, że serwer coś na jej podstawie odrzuca.
- Usunięte resztki tego progu w regułach playlist i motywów oraz dwa
  punkty API, których aplikacja od dawna nie używa (przeglądanie muzeów
  po epoce i losowe dobieranie dzieł). Kolejność „najlepsze najpierw”
  w Odkrywaj zostaje na razie bez zmian.

## 1.145.13

- Porządki w regułach doboru dzieł, etap 2 (szybkość, bez zmiany tego, co
  widać). Gdy powtórki znajdą kopię albo zmieni się tytuł, autor czy rok
  dzieła, serwer układa od nowa tylko dzieła, których to dotyczy, a nie
  grupy kopii całego katalogu. Do tej pory każda taka zmiana kosztowała
  3 do 6 sekund czekania przy pierwszym pytaniu po niej (lista, Szukaj,
  Odkrywaj), w nocy około trzydziestu razy, a przy powtórkach puszczonych
  w dzień tak samo.

## 1.145.12

- Porządki w regułach doboru dzieł, etap 1: noc najpierw sprząta, potem
  dobiera. Powtórki, Strażnik katalogu, Sędzia powtórek i Nocny przegląd
  idą teraz przed dobieraniem nowych dzieł (ostatnio dobieranie zajęło
  1 h 43 min, powtórki dostały 5 minut, a Strażnik i Przegląd nie ruszyły
  ani razu). Dobieranie dostaje najwyżej 45 minut nocy.
- Zamówienia do Claude dla Strażnika, Sędziego i Przeglądu wychodzą,
  zanim serwer zacznie porównywać obrazy, więc odpowiedzi czekają, gdy
  przychodzi ich kolej. Zadania porządków, do których noc nie doszła,
  następnej nocy idą jako pierwsze.
- Sędzia nie dostaje już par, w których jedno z dzieł Strażnik odłożył
  jako nie-dzieło.

## 1.145.11

- Porządki w regułach doboru dzieł, etap 0 (pomiar, bez zmiany tego, co
  widać). Po audycie reguł z 11 listopada serwer zapisuje, gdzie idzie
  czas: powtórki piszą w logu czas każdego kroku rundy (skróty obrazów,
  punkty, pary, pobrania, zapisy), a każde zadanie nocy dopisuje, ile razy
  przez nie przebudowano grupy kopii i ile to trwało.
- `GET /api/debug/decisions` (tylko właściciel) oddaje to, co do tej pory
  rozstrzygnięto o dziełach: pary uznane za jedno dzieło i przez co, detale
  i zdjęcia sal, pary rozdzielone przez „To nie to samo” i przez Sędziego,
  dzieła odłożone przez Strażnika. Same opisy, bez obrazów i bez własnych
  zdjęć. To zestaw wzorcowy, na którym sprawdzimy każdą późniejszą zmianę
  reguł (`python -m frame_server.golden plik.json`).
- Opis audytu, planu i sposobu sprawdzania: `docs/RULES.md`.

## 1.145.10

- Studium dzieła, „Kolor i światło” przy pastelu, kredce i kredzie: próbka
  farby prawdopodobnej nie jest już rzadką, prawie pojedynczą kreską.
  Jest tak samo gęsto zakreskowana jak próbka farby pewnej, tylko trochę
  węższa i niższa.

## 1.145.9

- Studium dzieła, „Kolor i światło”: malowane próbki prawdopodobnych farb
  nie mają już przerywanego okręgu dookoła. Poznać je po tym, że są
  mniejsze albo cieńsze. Przy płaskiej palecie okrąg zostaje.
- „Kolor i światło” rozpoznaje obraz olejny także wtedy, gdy muzeum nie
  podaje techniki, a jedynie to, że dzieło jest obrazem (tak jest
  w zbiorach Getty), albo gdy w opisie jest samo płótno. Obraz na
  papierze, jedwabiu, tuszem albo fresk zostaje przy płaskiej palecie.
- Farby olejne, akrylowe i tempery nie są już kropkami z tuby, tylko
  pacnięciami pędzla, takimi jak małe kolory na pasku palety, trochę
  większymi od dawnych kropek. Papier wokół pacnięcia powoli nasiąka
  olejem i zostaje na nim delikatna, nierówna obwódka.

## 1.145.8

- Studium dzieła, „Kolor i światło”: paleta i próbki farb są malowane
  techniką, w której powstało dzieło. Olej, akryl i tempera to osobne
  pociągnięcia pędzla, pełne na początku i suche przy końcu, lekko
  nachodzące na siebie i mieszające się w tych miejscach, a przy
  mniejszych kolorach krótkie pacnięcia; farby to kropki wyciśnięte
  z tuby. Akwarela i gwasz rozlewają się na mokrym papierze i wpływają
  jedna w drugą. Pastel, kredka i kreda to kreskowanie, spod którego
  prześwituje papier. Malowanie zaczyna się, gdy sekcja jest na ekranie.
- Technikę aplikacja czyta z opisu dzieła (po polsku, angielsku,
  francusku, niemiecku, niderlandzku, włosku i hiszpańsku). Grafiki,
  fotografie, rysunki tuszem i dzieła bez podanej techniki zostają przy
  płaskiej palecie i okrągłych próbkach.

## 1.145.7

- „Pod lupą”: gdy telefon jest trzymany nieruchomo, cienia pod kafelkami
  nie widać i wyglądają jak zwykłe. Cień pojawia się dopiero przy
  obracaniu telefonu.

## 1.145.6

- Studium dzieła: „Dalsze losy” są teraz dalszym ciągiem „Drogi dzieła”
  i stoją zaraz pod nią. Chwilę po czerwonej plamie na końcu drogi pióro
  zakreśla ją jednym okrągłym ruchem i dopiero z tego zakreślenia kreska
  schodzi niżej, zakreśla nagłówek „Dalsze losy” i biegnie w dół lewą
  stroną, lżejszą ręką i nie całkiem prosto.
- Każde późniejsze dzieło ma na tej kresce małą czerwoną plamę, a z niej
  pod rok i nazwisko wylewa się plama farby w kolorze indygo (w ciemnym
  motywie jasna, z ciemnym tekstem). Czerwień, indygo i czerń kreski
  wpływają w siebie. Cytat, obrazek i opis zostają na papierze, po
  prawej stronie kreski.
- Dzieło bez „Drogi dzieła” ma „Dalsze losy” jak dotąd, tylko wyżej:
  przed „Podobnymi dziełami”.
- „Droga dzieła”: morze, przez które dzieło przepłynęło, jest
  bladoniebieską plamą akwareli. Rozlewa się tuż przed piórem, od
  miejsca, w którym kreska w nią wchodzi, a po wyschnięciu ma
  ciemniejszy brzeg. Kreska jest rysowana w mokrej farbie, więc za
  piórem tusz rozpływa się w niebieskim, miejscami szerzej. Fale i nazwa
  morza zostają, fale są odrobinę ciemniejsze.
- „Droga dzieła”: cienka kreska zaczyna się rysować wcześniej, prawie
  u dołu ekranu, a kropki z plamami pod tekstami pojawiają się trochę
  wcześniej niż dotąd, nieco poniżej środka ekranu.

## 1.145.5

- „Pod lupą” jest teraz na samym końcu Odkrywaj, za „Studiami dzieł”.
  Kafelki ruszają się przy obracaniu telefonu delikatniej, a cień pod
  nimi jest słabszy i mniej rozmyty.

## 1.145.4

- Miniatury bardzo długich dzieł (zwoje, fryzy) są ostre. Serwer szykuje
  je z większego zdjęcia i tak, by krótszy bok miał 320 px, a aplikacja nie
  zmniejsza ich już po dłuższym boku. Stare, zbyt cienkie miniatury serwer
  robi od nowa po aktualizacji; telefon może jeszcze przez dobę pokazywać
  starą.

## 1.145.2

- „Pod lupą”: rozbłysk na kafelkach jest mocniejszy, a całe kafelki są
  lekko uniesione nad stroną. Przy obracaniu telefonu przesuwają się,
  a ich cień na stronie przesuwa się w drugą stronę.

## 1.145.1

- Studium dnia bierze pod uwagę jakość zdjęcia dzieła. Dzieła ze zdjęciem
  co najmniej tak dużym jak ekran ramki idą wyżej, a mniejsze niż 2000 px
  niżej. Czarno-białe zdjęcia obrazów w kolorze i stare slajdy z archiwów
  sztuki nie są proponowane. Kurator widzi rozmiar zdjęcia i odrzuca
  nieostre, wyblakłe albo ze ścianą czy tablicą barw. Takie dzieło wraca,
  gdy znajdzie się jego lepsza kopia.

## 1.145.0

- Zadania nocne → Powtórki i jakość → „Co zmieniła noc”: lista obrazów,
  które noc uznała za kopię innego dzieła, jego detal albo zdjęcie na
  ścianie. Na górze te z wątpliwościami, które rozstrzygnął sędzia: oba
  obrazki oraz to, co powiedzieli sędzia i krytyk. Niżej, zwinięte, te,
  które rozstrzygnął sam obraz. „To nie to samo” rozdziela parę na stałe
  i noc nie połączy jej ponownie. Nic nie jest usuwane: kopia zostaje
  w bibliotece, a pokazuje się najlepsza z nich.
- Przy zadaniach Powtórki i detale, Sędzia powtórek, Strażnik katalogu
  i Nocny przegląd widać, co zrobiły, np. „900 obrazów obejrzanych,
  41 kopii, 14 detali”.
- Zadanie „Kopie razem i podpowiedzi Szukaj” nazywa się teraz
  „Odświeżenie grup kopii i podpowiedzi Szukaj”, bo niczego nie szuka,
  tylko odświeża to, co już wiadomo.

## 1.144.4

- „Pod lupą”: miniatury na kafelkach są kadrowane bliżej i mają błyszczącą
  powłokę, której ukośny błysk przesuwa się przy obracaniu telefonu.
  Cienia za kartą już nie ma, karta wygląda jak inne kafelki.

## 1.144.3

- „Droga dzieła”: na końcu drogi zamiast czerwonej kropki w białym otoku
  jest plama czerwonej akwareli. Rozlewa się od środka, dosycha z
  ciemniejszym brzegiem, a tam, gdzie styka się z kreską i z tuszem pod
  ostatnim podpisem, czerwień i czerń wpływają w siebie.
- Odnoga wystawy rysuje się odręcznymi kreseczkami, jedna po drugiej,
  każda trochę inna. Zakreślenie wokół podpisu powstaje dopiero po
  plamie, jednym ruchem od początku do końca.
- Kiedy ekran się cofa, rysunek zanika tak, jak powstał, tylko wstecz
  i szybciej: podpis, plama, kropka, a kreska wraca w górę.
- Krótka linijka między dwiema długimi nie robi już głębokiego wcięcia
  w plamie pod podpisem.

## 1.144.2

- „Droga dzieła”: kreska biegnie przodem, niżej na ekranie, najpierw
  cienka jak włos, a za nią grubnie; tusz w stalówce jest nierówny.
- Pod każdym podpisem jest ciemna plama tuszu, która wylewa się z kropki
  swojego przystanku: najpierw kropka, po chwili tusz ostrym, mokrym
  brzegiem, potem biały podpis z czerwoną datą. Plama dosycha do
  ciemnoszarej akwareli, a papier przy jej krawędzi nasiąka: miejscami
  wyrasta drugie, jaśniejsze halo. W ciemnym motywie plamy są białe,
  a tekst czarny.
- Drobinki tuszu są tylko przy zakrętach, jak od zbyt szybkiej stalówki,
  i część z nich jest poprawiona białym korektorem; przy kresce doszły
  krótkie białe poprawki.

## 1.144.1

- Studium dnia wybiera kurator. Reguły układają listę dziesięciu dzieł
  dnia, a Sonnet ogląda ich obrazy i odrzuca szkice robocze, kartki ze
  szkicownika, notatki, blade i prawie puste arkusze, fragmenty i
  dokumenty. Z reszty wybiera dzieło, o którym da się najwięcej
  opowiedzieć. Odrzuconych dzieł już nie proponuje. Jedno zapytanie
  dziennie, ok. 2 centów. Bez klucza wybierają reguły, ale szkice i blade
  kartki stawiają na końcu.

## 1.144.0

- Zadania nocne w Konfiguracji są w pakietach: Utrzymanie katalogu,
  Powtórki i jakość, Opisy i fakty, Odkrywaj i ramka oraz Spisy muzeów.
  Każdy pakiet ma jeden guzik, który uruchamia od razu wszystkie jego
  zadania, i krótki opis, co robi. Pojedyncze zadania są nadal pod
  „Zadania”.
- Porządki zaczynają od dzieł, na których Ci zależy: najpierw Ulubione
  i dzieła z Twoich playlist, potem to, co pokazują playlisty
  inteligentne, karty Odkrywaj i Propozycje dnia. Dopiero potem reszta
  katalogu. Dotyczy to powtórek i detali, sędziego powtórek, strażnika
  katalogu, nocnego przeglądu, ostrzejszych kopii i tego, gdzie wiszą
  dzieła.
- Noc najpierw porządkuje, a dopiero na koniec czyta spis Rijksmuseum,
  w czasie, który jej został. Wcześniej spis zajmował 2,5 godziny
  i powtórki dostawały 5 minut, a strażnik katalogu i nocny przegląd nie
  ruszyły ani razu. Strażnik i przegląd czekają na odpowiedź Claude'a
  najwyżej kwadrans, a spóźnioną zbierają następnej nocy.
- Klucze, hasła i tokeny w adresach (np. logowanie do WikiArt) nie
  trafiają już do logu serwera, także przy czytaniu starszych dni.

## 1.143.5

- „Pod lupą”: rozjaśnienie HDR u góry kafelków jest mocniejsze i sięga
  niżej (pełne przez górną trzecią część obrazu), a za górną częścią
  karty jest miękki cień.

## 1.143.4

- Sędzia powtórek pracuje w nocy przed czytaniem spisu Rijksmuseum, a nie
  po nim (wcześniej noc kończyła się, zanim do niego doszła), i czeka na
  odpowiedź najwyżej kwadrans; spóźnioną zbiera następnej nocy.

## 1.143.3

- „Droga dzieła” powstaje przy przewijaniu na wysokości środka ekranu
  i idzie od góry: kreska się rysuje, na niej wyrastają kropki, a podpisy
  wyłaniają się rozmyte i ostrzeją. Niżej nie ma jeszcze nic. Kiedy
  przewijanie staje, zaczęty przystanek rysuje się do końca.
- Białe plamy pod podpisami są jedną plamą: łączą je wąskie zacieki,
  a farba wolno wsiąka w papier od góry i dosycha, zamiast rozlewać się
  osobno pod każdym podpisem, kiedy ten wjeżdżał na ekran od dołu.
- Kreska zaczyna się przy linii pod liczbami, a łuki zwężają się ku
  dołowi: droga zaczyna szeroko i z każdym zakrętem jest bliżej środka
  strony.
- Z „Ogranicz ruch” i z VoiceOver cała droga jest od razu.

## 1.143.2

- „Droga dzieła”: opisy przystanków bez daty czyta się naturalniej.
  Zamiast kilku przystanków „bez daty”, z których każdy kończył się
  słowami „zapis nie podaje daty”, właściciele bez dat stają razem
  w jednym przystanku, a o tym, czego zapis nie mówi, nie ma ani słowa.
  Przystanek bez daty nie ma już czerwonego napisu przy kropce, zdania
  nie zaczynają się raz za razem tak samo i nie powtarzają roku, który
  stoi obok.
- Gotowe drogi są opowiadane od nowa przy najbliższym otwarciu studium.

## 1.143.1

- Ten sam artysta pod innym zapisem imienia jest tym samym artystą:
  „Alphonse Mucha” z V&A i Europeany trafia do Alfonsa Muchy, a muzeum,
  które pod jednym zapisem nic nie znajduje, jest pytane o drugi.
- Rijksmuseum nie podaje już wydawcy ani drukarza jako autora grafiki.
- Europeana: plakaty, których autor jest zapisany tylko jako link albo
  jako „projektant” (np. Kunstbibliothek w Berlinie), mają autora,
  a drukarnia nie jest artystą.

## 1.143.0

- Konfiguracja → Dzieła i biblioteka → „Zadania nocne”: nocną pracę
  serwera można uruchomić o dowolnej porze. Każde zadanie ma własny
  guzik, a „Uruchom wszystkie teraz” puszcza cały pakiet po kolei, tak
  jak w nocy, najwyżej przez 2 godziny. Na żądanie zadania nie czekają,
  aż odłożysz aplikację. Widać, które zadanie trwa i ile zostało, można
  je zatrzymać, a przy każdym zadaniu jest jego ostatni przebieg: kiedy,
  jak długo, ile zrobiło albo że nie miało nic do zrobienia, i czy był
  błąd. Zadania pytające Claude'a mają gwiazdkę. W tym samym czasie
  działa tylko jeden przebieg: noc czeka na ten uruchomiony z aplikacji.
- Konfiguracja → Miejsce na serwerze: „Zebrane dzieła” mówią, ile dzieł
  serwer ma w katalogu (każde raz; obok wszystkie obrazy z kopiami
  i detalami), ile z nich jest na serwerze w dużej rozdzielczości i ile
  z tych ma co najmniej 2560 px, czyli pełny ekran ramki. Twoje prace
  i zdjęcia liczą się osobno. Liczba dzieł stoi też w wierszu tej
  strony na liście Konfiguracji.

## 1.142.12

- „Droga dzieła” w Studium dzieła powstaje dla dużo większej liczby
  dzieł. Dotąd opowiadały ją tylko zapisy Art Institute of Chicago
  i Cleveland Museum of Art (oraz właściciele z Wikidanych). Teraz także
  National Gallery of Art w Waszyngtonie (prawie każdy obraz i rzeźba,
  większość rysunków), Luwr (historia dzieła, dawni właściciele, sposób
  nabycia i wypożyczenia na wystawy) i Rijksmuseum (obrazy opisane
  w katalogu muzeum).
- Dzieło z Wikimediów, Europeany albo innego zbioru, które wisi w jednym
  z tych pięciu muzeów, dostaje drogę z zapisu tego muzeum: serwer
  znajduje je po identyfikatorze muzeum w Wikidanych albo po kopii
  obrazu z samego muzeum. Mona Lisa z Wikimediów ma więc drogę z Luwru.
- Dzieła, dla których wcześniej nie było zapisu, są sprawdzane jeszcze
  raz przy najbliższym otwarciu studium. Gotowe drogi zostają bez zmian.
- Metropolitan Museum, Yale, SMK, Getty i V&A nie podają proweniencji
  w swoich otwartych danych, więc ich dzieła mają drogę tylko wtedy,
  gdy właścicieli zna Wikidata.
- Indeks National Gallery of Art buduje się raz od nowa po aktualizacji
  (kilka minut w tle); do tego czasu wyszukiwanie działa na starym.

## 1.142.11

- Plakaty pokazują tylko plakaty. Po wybraniu artysty (np. Claude
  Monet + Plakaty) muzea oddawały wszystkie jego prace, a serwer
  przepuszczał je bez sprawdzenia, więc wśród plakatów były obrazy
  olejne, rysunki i akwaforty. Teraz o plakacie decyduje to, co
  muzeum pisze o samym dziele: rodzaj i technika. Obraz albo rysunek
  nigdy nie jest plakatem.
- Plakat jest grafiką: pojawia się w Grafice, ale nie w Malarstwie
  ani w Rysunkach.
- Fotografia, Rzeźba, Ceramika i Rękopisy w playlistach i katalogu
  przyjmują tylko dzieła swojego rodzaju, tak jak w Szukaj.
- Europeana: rysunki i ryciny opisane przez muzeum ogólną kategorią
  „malarstwo” nie trafiają już do Malarstwa, a rodzaje zapisane po
  niemiecku, francusku, szwedzku czy rumuńsku są rozpoznawane.
- Art Institute of Chicago i Europeana są pytane wprost o plakaty, więc
  przy Toulouse-Lautrecu czy Musze przychodzą ich prawdziwe plakaty.
- Rijksmuseum: część grafik miała zamiast autora napis „@language”.

## 1.142.10

- Karta nowej playlisty otwarta z Szukaj („Utwórz playlistę z tego
  wyszukiwania”) nie gubi już po chwili guzika „Zapisz” ani „Anuluj”.
  Wybór w grupie (np. Malarstwo) otwierał wyszukiwanie, a ono chowało
  pasek u góry karty. To samo działo się w edytorze playlisty po
  wybraniu czegoś w grupie.

## 1.142.9

- „Droga dzieła”: białe plamy pod tekstami nie leżą już na stronie od
  razu. Kiedy przystanek wjeżdża na ekran przy przewijaniu, jego plama
  rozlewa się od środka jak akwarela w przejściu obrazu na ramce
  w Teraz: poszarpanym frontem gęstszej farby, miejscami miękkim,
  miejscami ostrym, i po chwili zasycha w bladą plamę. Raz rozlana
  zostaje. Przy włączonym „Ogranicz ruch” plama tylko łagodnie się
  pojawia.

## 1.142.8

- „Pod lupą”: rozjaśnienie HDR na kafelkach jest gradientem: pełne
  u góry obrazu, przy linii z podpisem 10%.

## 1.142.7

- Zapamiętane strony wyników z Art Institute of Chicago i strony
  wyszukiwań z wybraną techniką są pobierane z muzeów od nowa. Przy
  Malarstwie i wybranym artyście przyjdą więc od razu jego obrazy,
  a nie stara strona ze wszystkimi pracami.

## 1.142.6

- „Droga dzieła” jest teraz rysunkiem drogi, a nie osią czasu. Jedna
  linia płynie łukami przez całą szerokość, jak pociągnięta szerokim
  piórem do kaligrafii: cienka na długich skosach, gruba na zakrętach.
  Powstaje pierwsza, a kropki przystanków stoją na gotowej linii, więc
  przy żadnej nie ma zakrętu. Tekst każdego przystanku zaczyna się tuż
  pod swoją kropką, w zakolu drogi, i linia nigdzie w niego nie wchodzi.
- Daty przystanków są pisane odręcznie i zawsze stoją przy kropce.
- Droga zaczyna się na pierwszym przystanku i kończy większą czerwoną
  kropką tam, gdzie dzieło jest dziś. Nad morzem wije się swobodnie
  wśród fal.
- Wypad, z którego dzieło wróciło (na przykład wystawa), jest odnogą:
  wychodzi z drogi jak na rozdrożu, tym samym piórem, tylko przerywaną
  kreską, i kończy się pustą kropką na odręcznej pętli, którą tekst
  wypadu jest zakreślony.
- Pod każdym tekstem leży blado-biała podmalówka: nierówna plama
  z ostrzejszą, jaśniejszą krawędzią, jak rozlana i wyschnięta farba.
- Obok czarnej linii w kilku miejscach biegną białe, poszarpane
  pociągnięcia suchym pędzlem, jak korekty kreski, a czerwona kropka na
  końcu ma biały, malowany otok, który nachodzi na czarną linię.
- Teksty przystanków łamią się staranniej: „w”, „z” czy „i” nie zostają
  na końcu wiersza, liczba trzyma się swojego słowa („800 franków”,
  „nr 175”), wyróżniona nazwa nie jest rozrywana, wiersze mają podobną
  długość, a ostatni nie jest jednym słowem.
- Pod rysunkiem nie ma już podpisu o źródle i o tym, kto opowiada.
- Linia z kropkami rysuje się zawsze. Wcześniej czasem zostawały same
  teksty, bez drogi.

## 1.142.5

- Szukaj i playlisty z wybraną techniką (Malarstwo, Grafika, Rysunki
  i akwarele) pokazują tylko dzieła tej techniki także przy wybranym
  artyście albo wpisanych słowach. Wcześniej muzea odsyłały wszystkie
  prace artysty, np. przy Monecie i Malarstwie jego karykatury ołówkiem
  z Art Institute of Chicago. Decyduje rodzaj dzieła w muzeum, potem
  technika („grafit na papierze” to rysunek, „olej na płótnie” obraz).
- Art Institute of Chicago jest pytany wprost o obrazy danego artysty,
  więc przy Malarstwie przychodzi ich więcej.
- Grafika rozpoznaje też monotypie i polskie opisy muzeów (akwaforta,
  litografia, staloryt, sucha igła).

## 1.142.4

- Odkrywaj: „Pod lupą” w kafelkach jak „Studia dzieł”: obraz u góry,
  tytuł i autor na karcie. Każdy obraz trochę jaśniejszy (HDR), jak na
  karcie dzieła. Podpis sekcji: „Dzieła w ogromnej rozdzielczości”.

## 1.142.3

- Serce na miniaturach da się kliknąć także w Odkrywaj (zestawy, „Zobacz
  wszystkie”, rzędy propozycji), w Propozycjach dnia i w playlistach,
  nie tylko w Szukaj.
  W Ulubionych serc dalej nie ma.
- Czerwone serce jest z tego samego przeziernego szkła co puste, tylko
  zabarwionego na czerwono, lekko prześwitującą czerwienią, tą samą
  w jasnym i ciemnym trybie.

## 1.142.2

- „Droga dzieła”: linia biegnie gładko, bez załamań przy kropkach
  i bez zawijasów nad morzem.

## 1.142.1

- „Droga dzieła”: kropki stoją przy swoich przystankach, a linia nie
  przecina już tekstu.

## 1.142.0

- Studium dzieła: nowa sekcja „Droga dzieła”, zaraz po „Rozmiarze
  obrazu”. Pokazuje, jak obraz szedł od pracowni do muzeum: kto go miał,
  gdzie był wystawiany, za ile sprzedany. Rysowana jako płynna linia
  z kropkami, z morzem, gdy dzieło przepłynęło ocean. Wszystko z zapisów
  muzeum (Art Institute of Chicago, Cleveland, a dla innych Wikidata),
  opowiedziane po polsku przez Claude Haiku. Rok albo kwota, której nie
  ma w zapisie, nie trafia na drogę. Do wyłączenia w Konfiguracji → Model
  językowy.

## 1.141.0

- Strażnik katalogu: w nocy Claude Haiku ogląda obrazy z Commons,
  Europeany, Openverse i WikiArt i odkłada te, które nie są dziełem
  (znaczek, strona tekstu, zdjęcie sali, czarno-białe zdjęcie kolorowego
  obrazu). Każde odłożenie najpierw potwierdza krytyk; dzieła muzeów nie
  są ruszane. Odłożone są w Konfiguracji → Model językowy → „Do
  sprawdzenia”, z guzikiem „Przywróć”.
- Nocny przegląd: co noc 30 losowych dzieł sprawdzanych pod kątem tytułu,
  daty, polskiego opisu i obrazu. Nic nie jest zmieniane, znaleziska są na
  tej samej liście „Do sprawdzenia”.
- Szukaj zdaniem: po wpisaniu kilku słów w Szukaj wiersz „Szukaj zdaniem”
  zamienia zdanie na tematy, epoki, kolory, artystów i słowa, każde jako
  żeton do usunięcia.
- Słowa kluczowe i polskie teksty, na które nikt nie czeka, są zamawiane
  w nocy w paczce za pół ceny. Co potrzebne od razu, idzie od razu.

## 1.140.2

- Polskie tytuły z Wikidaty dla większej liczby muzeów. Ustalony polski
  tytuł z Wikidaty i dotąd wygrywał z tytułem od modelu, ale serwer szukał
  go tylko dla Met, AIC, Cleveland, Rijksmuseum, WikiArt i Luwru. Teraz
  także dla NGA, Paris Musées, V&A, Yale, Smithsonian, SMK, Courtauld
  i Muzeów Narodowych w Warszawie i Krakowie (te dwa zachowują własne
  polskie tytuły, Wikidata daje im resztę faktów). Gdzie Wikidata nie ma
  polskiego tytułu, zostaje tytuł od modelu.

## 1.140.1

- „Pod lupą”: znaczek przy roku na karcie dzieła podaje, ile razy naprawdę
  da się przybliżyć to dzieło na tym telefonie (np. 17× zamiast stałego
  „24×”). Pełny ekran przybliża tak głęboko, jak sięgają piksele kafli, do
  48×. Takie dzieła nie mają już sekcji „Fragmenty” na karcie ani w
  studium: kafle ogląda się w pełnym ekranie.

## 1.140.0

- Szukaj: pary dzieł, których obrazy nie rozstrzygnęły (to samo dzieło?
  detal? zdjęcie w ramie?), ocenia w nocy Claude Haiku. Gdy chce połączyć
  dwa obrazy albo schować detal, drugi raz pyta krytyk, który szuka
  dowodów przeciw; zmiana wchodzi tylko po jego zgodzie. Dzieło muzeum
  nigdy nie jest chowane. Koszt to grosze miesięcznie; przełącznik
  „Sędzia powtórek” w Konfiguracji.

## 1.139.4

- Znaczki na miniaturach uporządkowane: na obrazie zostaje tylko to, co
  się klika, i tylko w prawym górnym rogu.
- Serce bez kółka: z przeziernego szkła, przez które widać obraz, gdy
  dzieło nie jest w Ulubionych, czerwone, gdy jest. W Ulubionych serc nie
  ma, bo ulubione jest tam wszystko.
- Usuwanie z playlisty i krzyżyki (edytor, przykładowe zdjęcia) to czarne
  kółko na rogu, jak ptaszek wybranej miniatury w Prezentacji. Plus
  w edytorze też siedzi na rogu: jasne kółko, po dodaniu czarne z ptaszkiem.
- „Pod lupą” to mała lupa zaraz po tytule. Iskierki Propozycji dnia stoją
  przed liczbą dzieł, a zamiast znaczka „gra teraz” pod kartą playlisty
  jest cynobrowe „Na ramce”. Na pasku „Następne” w Teraz podpis
  „Następny w kolejce”.
- Szklany znaczek w kółku zostaje tylko na okładce „Ukrytych”.

## 1.139.3

- Playlisty: kafelek „Propozycje dnia” po uruchomieniu aplikacji od razu
  pokazuje dzieła z ostatniego razu, a nie inne, podmieniane chwilę
  później. Gdy przychodzą nowe (nowy dzień), wchodzą płynnym
  przenikaniem, dopiero gdy ich miniatury są już w telefonie.

## 1.139.2

- „Pod lupą”: kafle z Commons są trzymane w 3840 px zamiast 2560, więc przy
  dużym przybliżeniu są półtora raza ostrzejsze. Kafle zapisane wcześniej
  zostaną raz pobrane od nowa. Aplikacja wczytuje pełny rozmiar kafla tylko
  wtedy, gdy przybliżenie go wymaga.
- „Pod lupą” w Odkrywaj pokazuje każde dzieło raz. Commons trzyma niektóre
  w kilku plikach z kaflami (np. „Księżniczka z krainy porcelany” Whistlera
  trzy razy); zostaje największy.

## 1.139.1

- Próba sędziego powtórek: także Opus, a pytanie osobno o rodzaj pary
  i o to, który obraz jest całym dziełem (Haiku mylił kierunek „detal
  czego”). Nic nie zmienia w katalogu.

## 1.139.0

- Rijksmuseum dostaje własną bazę na serwerze, tak jak AIC, Cleveland,
  Smithsonian i Wellcome. Muzeum nie publikuje pliku z dziełami, więc
  serwer czyta jego katalog (OAI-PMH) po 50 dzieł naraz, najwyżej 2,5
  godziny na noc i tylko gdy nikt nie używa aplikacji. Całość, ok. 737 tys.
  dzieł ze zdjęciem, schodzi w kilka nocy. Do tego czasu Rijksmuseum
  działa jak dotąd, potem Szukaj, Odkrywaj i losowanie biorą je z dysku.
  Co dwa miesiące serwer dociąga tylko zmiany. Baza zajmuje ok. 0,7 GB.

## 1.138.6

- Próba sędziego powtórek: serwer potrafi pokazać parę obrazów modelom
  Haiku, Sonnet i Fable i podać, jak każdy ją ocenia (ta sama praca,
  detal, zdjęcie w ramie, kopia innej ręki, dwa różne dzieła) i ile to
  kosztowało. Używa klucza z Konfiguracji, koszt wlicza się do miesiąca.
  Nic nie zmienia w katalogu.

## 1.138.5

- Mniej powtórek i detali w Szukaj. Wyniki z muzeów nie pokazują już
  kopii dzieła, które jest w katalogu pod innym tytułem (np. „Het meisje
  met de parel” obok „Dziewczyny z perłą”).
- „Johannes Vermeer van Delft” i „Jan Vermeer” to dla porównywania obrazów
  ten sam artysta, więc „Die Malkunst” łączy się z „Alegorią malarstwa”.
  Ten sam skan pod innym zapisem autora też jest rozpoznawany (odcisk
  obrazu).
- Detale z Commons rozpoznawane także po nazwie pliku („…_detail_…”).
- Zdjęcia obrazu w ramie albo na ścianie muzeum są odkładane jak detale.
- Szukanie małych detali w dużym obrazie dokańcza się w kolejnych nocach,
  zamiast przepadać, gdy zabrakło czasu.

## 1.138.4

- Na pełnym ekranie dzieła wraca krzyżyk do zamykania. Słoneczka nadal
  nie ma: przy „Jaśniejszych dziełach” ekran rozjaśnia się sam.

## 1.138.3

- Nazwisko artysty pod tytułem dzieła (na karcie dzieła i w Teraz) nie jest
  już ucinane na „…”, gdy obok jest miejsce; za długie zawija się do
  drugiego wiersza.

## 1.138.2

- Pełny ekran dzieła bez guzików: nie ma już słoneczka ani krzyżyka.
  Gdy w Konfiguracji włączone są „Jaśniejsze dzieła”, ekran rozjaśnia się
  sam po wejściu i ściemnia, gdy zaczynasz go zamykać. Zamykasz
  przesunięciem w dół.

## 1.138.1

- Wszystkie znaczki na miniaturach i kafelkach mają ten sam szklany,
  okrągły wygląd co oko na karcie „Ukryte”: serce ulubionych, lupa
  „Pod lupą”, iskierki Propozycji, „gra teraz” na playliście, kolejka
  w Teraz, plus/ptaszek i krzyżyk w edytorze playlisty, minus przy
  usuwaniu z playlisty i krzyżyk przy przykładowych zdjęciach.

## 1.138.0

- „Pod lupą”: dzieła, które na Commons mają zdjęcie w kaflach ogromnej
  rozdzielczości (np. „Straż nocna”), mają lupę na miniaturze i plakietkę
  „24×” przy tytule. Na pełnym ekranie przybliżysz je do 24 razy.
- W Odkrywaj nowy rząd „Pod lupą”, przed „Studiami dzieł”: najpierw
  dzieła z biblioteki (ulubione na początku), potem pozostałe takie dzieła
  z Commons.

## 1.137.7

- Wycinki dzieł (np. głowy ze „Straży nocnej”) są rozpoznawane po dużym
  zdjęciu całego obrazu i znikają z Szukaj jak kopie. Kopie „przypisywane”
  albo „według” innego malarza łączą się w jedno dzieło.
- Pod wycinkiem lista kopii pokazuje całe dzieło tylko do obejrzenia: nie
  da się nim zastąpić wycinka, bo zmieniłyby się proporcje.
- Druki i kartki z tekstem (maszynopisy, broszury, programy, obwieszczenia,
  odwrocia obrazów) nie trafiają już nigdzie.
- Stare zdjęcia, ceramika i dzwony z Europeany i Paris Musées trafiają do
  Sztuk innych, a nie do obrazów: typ czytany jest w każdym języku.

## 1.137.6

- Szukaj znajduje dzieło po słowach każdej jego kopii (tytuł z jednego
  źródła, słowa kluczowe z innego) i pokazuje je w najlepszej kopii.
- Słowa wpisane po polsku szukają w katalogu także w tłumaczeniu, tak jak
  pytane są muzea: „gitara” znajduje też „Guitar”.
- Ukrycie jednej kopii dzieła nie chowa już kopii, którą masz w ulubionych
  (tak zniknęła „Uliczka” Vermeera z Rijksmuseum).

## 1.137.5

- Szukaj pokazuje ten sam obraz raz, także gdy źródła nazywają go w różnych
  językach („Lekcja muzyki”, „The music lesson”): serwer porównuje
  miniatury dzieł jednego artysty, w tle po każdym wyszukiwaniu i nocą.
- Detale dzieł znikają z katalogu i wyników: po tytule („detail”, „detal”,
  „szczegół”, „Ausschnitt”…) i po obrazie, gdy to tylko część innego
  zdjęcia tego dzieła.
- Kopie z Openverse (rawpixel w 1024 px, strony muzeów, o które serwer
  pyta sam) i zdjęcia fototeki Hertziana w Europeanie nie trafiają już do
  wyników.

## 1.137.4

- Łączenie artystów przez Wikidata nie przerywa się po jednym błędzie
  Wikidaty: zapytanie idzie jeszcze raz po chwili, a paczka nazwisk, która
  dalej nie przechodzi, czeka na następną rundę, zamiast kończyć całą.
  Pierwsza runda zatrzymała się tak po 2200 z 3000 nazwisk.

## 1.137.3

- Szukając artysty, serwer pyta muzea o niego po ich własnym polu autora
  (Art Institute of Chicago, Cleveland, Met, Europeana, SMK, V&A,
  Smithsonian, Wellcome, NGA, Luwr, Courtauld), a nie o dzieła, które
  tylko wymieniają jego nazwisko: mniej zapytań i szybciej jego dzieła.
  Gdy muzeum zapisuje nazwisko inaczej, pyta jak dotąd.

## 1.137.2

- Szukaj i playlisty inteligentne pokazują dzieło znalezione przez muzeum
  tylko wtedy, gdy ma szukane słowa: tak jak je wpisano albo tak, jak
  zapytano muzea (po angielsku, po francusku). Dla „vermeer” znikają
  dzieła ter Borcha, de Hoocha czy owce z Yale, a dla „nocna straż”
  zostaje „The Night Watch” Rembrandta.
- Lepsza kopia zdjęcia dzieła nigdy nie jest zdjęciem z archiwum (Foto
  Marburg, KIK-IRPA), a z kopii, które pasują, serwer bierze największą,
  nie pierwszą. Kopia wciąż za mała dla ramki jest szukana dalej. Dzieła,
  które dostały kopię z archiwum, są sprawdzane od nowa po starcie.
- Zdjęcie z archiwum ustępuje każdej innej kopii tego samego dzieła, także
  wtedy, gdy jest w ulubionych albo na playliście.
- Dzieła, które Wikimedia Commons ma w ultrawysokiej rozdzielczości
  podzielonej na kafle (np. „Straż nocna”, „Ogród rozkoszy ziemskich”),
  same dostają ten plik w miejsce zdjęcia, nawet gdy zdjęcie muzeum jest
  dobre albo wybrane ręcznie; w pełnym ekranie można je przybliżać po
  kaflach. Dzieła z katalogu są sprawdzane raz po starcie.

## 1.137.1

- Szukaj wie, kim są artyści: serwer raz pyta Wikidata o każdego artystę
  katalogu, więc różne zapisy tej samej osoby („Jan Vermeer”, „Johannes
  Vermeer”, „Vermeer, Johannes”) są jednym wierszem podpowiedzi i jednym
  żetonem, a dwie różne osoby o podobnych nazwiskach („Jan Vermeer van
  Haarlem”) się nie mieszają. Pierwsze pytanie rusza 5 minut po starcie
  serwera i trwa kilkanaście–kilkadziesiąt minut w tle (wstrzymuje się,
  gdy korzystasz z aplikacji); nowe nazwiska są dopytywane w nocy.
- Kody z muzealnych baz („MTB-PE-817”) nie są już podpowiadane jako
  artyści, a słowo kluczowe, które jest nazwiskiem artysty, nie powtarza
  jego wiersza.
- Podpowiedź „w muzeach” przy pisaniu odpowiada od razu: korzysta tylko
  z list muzeów trzymanych na serwerze, nie pyta muzeów przy każdej
  literze.
- Muzeum, które w ogóle nie odpowiada (np. wygasły certyfikat), jest na
  chwilę pomijane i wyszukiwanie na nie nie czeka. Druga strona wyników
  z Getty nie kończy się już błędem.

## 1.137.0

- Szukaj w katalogu odpowiada od razu: serwer ma teraz indeks wszystkich
  dzieł i sprawdza tylko te, które mogą pasować (na 78 tysiącach dzieł
  „vermeer” trwa około 0,05 s zamiast kilku sekund), a kolejne strony
  wyników są gotowe od ręki.
- Serwer nie zatrzymuje się już na kilkanaście sekund, gdy Szukaj pyta
  muzea albo w tle porządkuje kopie dzieł: serca, notatki i kopie nie
  blokują reszty serwera, a muzea mają własną pulę wątków.
- Wyniki z katalogu od najlepiej pasujących: najpierw dzieła szukanego
  artysty, potem te z szukanym słowem w tytule, w słowach kluczowych, a na
  końcu w opisie.
- Szukaj pokazuje wszystkie pasujące dzieła z katalogu, nie tylko pierwsze
  60: kolejne dochodzą przy przewijaniu, dzieła z muzeów po nich.
- Słowa szukane są od początku wyrazu, bez względu na polskie znaki: „zolw”
  znajduje „żółw”, a „art” nie znajduje już „Stuttgart”.
- Liczba przy podpowiedzi to dokładnie tyle dzieł, ile pokaże jej wybranie;
  podpowiedź autora, która nic by nie pokazała, znika.

## 1.136.10

- Kopie dzieła znajdują też pliki Commons z kaflami, których wyszukiwanie po
  tytule nie widzi (np. „Nachtwacht” z Google Art Project dla „Nocnej
  straży”): szukane po dziele w Wikidata.

## 1.136.9

- Kafle z Commons w pełnym ekranie leżą na swoich miejscach i mają te same
  barwy co podkład: podkład składa się teraz z miniatur samych kafli, a nie
  z obrazu dzieła, który bywał innym zdjęciem (inna kopia, inny kadr, inne
  barwy). Kafle nie tracą już ciemnych brzegów przy przycinaniu marginesów;
  zapisane wcześniej zostaną raz pobrane od nowa.
- Kopie dzieła: kopia z Commons z zestawem kafli ma znacznik „Kafle przy
  powiększeniu” i jest proponowana na górze listy zamiast obrazu bez kafli
  (np. „Nocna straż”). Po jej wybraniu karta i pełny ekran pokazują jej
  kafle.

## 1.136.8

- Szukaj z frazą („straż nocna”) nie zatrzymuje już serwera. Sprawdzanie
  frazy w katalogu trwało około 12 sekund na zapytanie i w tym czasie
  wszystko inne na serwerze czekało, więc aplikacja przestawała czekać na
  wyniki. Teraz to ułamek sekundy.
- Dzieła z archiwum Foto Marburg, które już są w katalogu, przechodzą na
  dobre kopie (muzeum, Commons, WikiArt) od razu po aktualizacji serwera,
  wszystkie po kolei, bez czekania na kolejne noce.
- Nad tytułem takich dzieł nie ma już nazwy archiwum zdjęć („German
  Documentation Center for Art History…”), tylko muzeum, w którym obraz
  wisi, jeśli da się je ustalić (np. ze strony kopii z Commons).

## 1.136.7

- Europeana nie podaje już zdjęć z archiwum Foto Marburg (małe, czarno-białe
  albo wyblakłe fotografie obrazów). Szukaj, Odkrywaj i dobieranie biorą
  dzieła tylko z innych zbiorów. Dzieła z Marburga, które już są w katalogu,
  zostają i same przechodzą na lepsze kopie.

## 1.136.6

- Dzieła z Europeany w wyblakłych, zimnych kolorach (np. „Gaj oliwny” van
  Gogha): to stare kolorowe przezrocza z archiwum fotografii Foto Marburg,
  którym z latami wyblakł barwnik, a nie błąd przetwarzania. Takie zdjęcie
  przegrywa teraz z każdą inną kopią tego dzieła (muzeum, Commons, WikiArt),
  a dzieło już w katalogu samo bierze kopię we właściwych kolorach, także
  tak samo dużą: przy otwarciu karty albo w nocy (do 40 dzieł na noc).
  W „Kopie dzieła” takie kopie są „Lepsze” bez ostrzeżenia o kolorach.
- „Kopie dzieła”: kopia dużo barwniejsza od obecnej ma teraz znaczek „Inne
  kolory”, a nie „Te kolory”. Wcześniej porównywany był tylko średni kolor
  całego obrazu, który u wyblakłego przezrocza potrafił wyjść podobny.

## 1.136.5

- Playlisty inteligentne: dzieła dociągnięte z muzeów (dodane do biblioteki
  od utworzenia playlisty) są na jej końcu, za dziełami, które biblioteka
  miała wcześniej. Dotyczy listy dzieł w aplikacji i kolejności na ramce
  bez tasowania.

## 1.136.4

- Ramka → Prezentacja → Zdjęcia: Passe-partout i Wypełnij pokazują podgląd
  na pierwszym z przykładowych zdjęć z Konfiguracji, tak jak Multi. Bez
  przykładowych zdjęć podgląd bierze, jak dotąd, zdjęcie z ramki albo
  z biblioteki.
- Konfiguracja → Przykładowe zdjęcia: miniatury to równe kwadraty (zdjęcia
  poziome nachodziły na sąsiednie), a kolejność zmienia się, przytrzymując
  zdjęcie i przesuwając je palcem.
- Playlisty: przytrzymane „Ulubione” (i każda karta prezentowana na ramce)
  mają menu: „Teraz prezentowane” i „Przesuń na koniec”, które jest teraz
  przy każdej karcie poza ostatnią. Dotąd prezentowana pierwsza karta nie
  miała żadnej opcji, więc menu się nie pokazywało.
- Narożniki okładki w przytrzymanej karcie idą równo z narożnikami karty.
- Przesuwana karta nie pokazuje znaku zakazu nad odstępami między kartami.

## 1.136.3

- Szukaj i playlisty z artystą: dopiski muzeów w nawiasie, np. „(signed by
  artist)” albo „(mentioned on object)”, nie sklejają już różnych malarzy w
  jedną osobę. Dla „van Gogh” podpowiedź to znowu Vincent van Gogh (razem z
  „Vincent Van Gogh, The Netherlands” i „(possibly)”), a nie Albrecht Dürer
  z 3000 dzieł, a playlista van Gogha ma tylko jego dzieła, bez Renoira,
  Tiepola czy Abrahama Storcka.

## 1.136.2

- Konfiguracja → Wyświetlanie → Przykładowe zdjęcia: wybrane zdjęcia znowu
  się pojawiają. Wgrywały się na serwer, ale aplikacja nie wysyłała ich
  listy w ustawieniach ani jej nie odczytywała, więc po wgraniu kwadraciki
  zostawały puste, a podgląd układów Multi brał przypadkowe zdjęcia.
  Zdjęcia wgrane przed poprawką zostały na serwerze bez przypisania; trzeba
  je wybrać jeszcze raz.

## 1.136.1

- Playlisty: przytrzymanie karty playlisty albo Propozycji dnia nie wyłącza
  już aplikacji. Podgląd przytrzymanej i przesuwanej karty jest rysowany
  osobno od strony i nie miał dostępu do pobierania obrazów.

## 1.136.0

- „Propozycje” w Playlistach to teraz „Propozycje dnia”: playlista składana
  raz na dzień z kart „Dziś dla Ciebie” (wybór kuratora, Artysta tygodnia,
  Motyw dnia, Ponieważ lubisz, pary tygodnia). Z każdej karty 12 pierwszych
  dzieł, tych, które Odkrywaj pokazuje na początku, ułożonych czwórkami:
  cztery z pierwszej karty, cztery z następnej i tak dalej. Ramka pokazuje
  je w tej kolejności (bez tasowania), a dzieła pokazane w ostatnich dniach
  idą na koniec. Twoje własne zdjęcia już się do nich nie dokładają.
- Po stuknięciu w kafelek: nazwy kart, z których są dzieła, „Prezentuj na
  ramce” i dzieła czwórkami, tak jak pójdą na ramce. Karty „Ponieważ lubisz”
  są tej osoby, która włączyła Propozycje dnia na ramce.

## 1.135.2

- Teraz: gdy ramka rysuje nowe dzieło, maluje się ono na starym akwarelą,
  plama po plamie od środka, w tempie paska. Każda plama zaczyna się od
  rozmytego koloru, który tam będzie, z nierówną, miejscami ciemniejszą
  krawędzią, a potem pojawia się w niej rysunek. Z „Ogranicz ruch” nowe
  dzieło po prostu przenika stare.

## 1.135.1

- Szukaj → Styl: style, których muzea nie znają z nazwy, są szukane także
  po swoich malarzach (najpierw nazwa stylu, potem malarze na zmianę), a ich
  dzieła z lat stylu do niego pasują. Dotyczy Nowej Rzeczowości (dotąd 0
  dzieł), Złotego wieku holenderskiego, Akademizmu, Szkoły znad rzeki
  Hudson, Prerafaelitów, Szkoły monachijskiej, Tonalizmu, Postimpresjonizmu,
  Nabistów, Młodej Polski, Fowizmu, Konstruktywizmu, De Stijl i Shin-hanga.

## 1.135.0

- Playlisty: karty da się ułożyć po swojemu. Przytrzymaj kartę i przesuń
  palcem, pozostałe robią miejsce; w menu przytrzymanej karty jest też
  „Przesuń na początek”. Kolejność zapamiętuje serwer, osobno dla każdego
  domownika (ta sama na każdym jego telefonie). Propozycje zostają pierwsze,
  Ukryte ostatnie, a nowe playlisty stają na końcu.
- Bez kafelka „Nowa playlista” na końcu siatki; nową playlistę tworzy „+” u
  góry ekranu. Przytrzymana karta playlisty (i Propozycji) kładzie się na
  bok: okładka z lewej, nazwa i liczba dzieł z prawej, a menu stoi tuż pod
  nią, nie pod podpisem i nie na sąsiednich kartach.

## 1.134.1

- Szukaj: podpis dzieła wymieniający kilku artystów naraz nie skleja ich już
  w jedną osobę. Przez taki podpis van Gogh, Dürer, Renoir, Tiepolo i
  Toulouse-Lautrec byli w podpowiedziach jednym artystą, a wybranie van
  Gogha pokazywało dzieła ich wszystkich.

## 1.134.0

- Dzieła z Commons, które mają zestaw ostrzejszych kafli (np. „Ogród
  rozkoszy ziemskich” Boscha, „Straż nocna”), w pełnym ekranie doczytują
  kafle przy przybliżaniu: każdy kafel trafia dokładnie na swoje miejsce na
  obrazie, a wczytywane są tylko te, które widać. Przybliżyć można teraz
  mocniej, aż do pikseli kafli.

## 1.133.1

- Dymki z pytaniem („Opisać 19022 obrazy?”, „Usunąć playlistę?” i inne)
  wskazują guzik, który je otworzył. Dotąd potwierdzenie „Opisz całą
  bibliotekę” wisiało u góry strony ze strzałką na „Polskie tytuły i opisy”,
  bo w iOS 26 dymek wskazuje widok, do którego jest przypięty, a był
  przypięty do całej strony. Tak samo przy usuwaniu playlisty, klucza APNs
  i domownika, odłączaniu telefonu, porzucaniu zmian kadru i wgrywaniu
  innego certyfikatu autora.

## 1.133.0

- Szukaj: wpisane razem słowa są frazą. „nocna straż” znajduje dzieła, w
  których te słowa stoją obok siebie (też „nocnej straży” albo „night watch”
  w muzeach zagranicznych), a nie takie, gdzie „night” i „watches” padają w
  różnych zdaniach opisu. Każde kolejne słowo dodane osobno dodatkowo
  zawęża wyniki, nigdy nie wystarcza „dowolne z nich”. Gdy fraza nic nie
  znajdzie, guzik „Szukaj słów osobno” rozbija ją na osobne słowa.
  Zapisane playlisty działają jak dotąd.

## 1.132.1

- Szukaj: z Openverse przychodzą tylko zdigitalizowane dzieła sztuki, bez
  kategorii „illustration”, z której brały się puste kafelki, herby i
  przypadkowe rysunki (np. przy Dadaizmie). Już znalezione ilustracje
  znikają z wyników.

## 1.132.0

- Bardzo wydłużone dzieła, jak zwoje japońskie i chińskie, są zapisywane
  ostrzej. Do proporcji 2:1 nic się nie zmienia. Dłuższe zachowują krótszy
  bok 1280 px, mieszcząc się w 6,5 Mpx, tyle co kwadrat 2560 × 2560.
  Zwój z Yale „Palace Women” miał 2560 × 111 px, teraz ma 12 275 × 534. Muzea,
  które pozwalają wybrać rozmiar (NGA, Yale, SMK, Smithsonian, Courtauld),
  są proszone o większy plik. Wydłużone dzieła, które już leżą na serwerze,
  pobierają się raz ponownie.
- Fragmenty dzieła: zwoje z Cleveland mają na karcie pasek zdjęć kolejnych
  części, każde 3400 px, a wybrane wielkie obrazy z Wikimedia Commons (np.
  „Ogród rozkoszy ziemskich”, „Straż nocna”) swoje kafle. Fragment otwiera
  się jak osobne dzieło: można go pokazać na ramce, dodać do kolejki albo
  playlisty i skadrować. Na jego karcie jest powrót do całości. W studium
  dzieła fragmenty są w sekcji „Fragmenty zwoju”, po „Detalach”.

## 1.131.3

- Library of Congress od dwóch dni odrzuca każde zapytanie z domu. Serwer
  nie pyta jej teraz przez dobę po odmowie, a po każdej następnej dwa razy
  dłużej, do dwóch tygodni. Stara fotografia przychodzi w tym czasie z
  Wikimedia Commons.
- Gdy serwer muzeum psuje się tylko w części (MNK: pełne zdjęcia dzieł od
  trzech dni nie przychodzą, miniatury tak), serwer przestaje pytać o tę
  część coraz dłużej, a miniatury idą dalej.
- WikiArt: po odrzuconym logowaniu serwer czeka pół godziny, zamiast
  logować się przy każdym wyszukiwaniu.

## 1.131.2

- Szukaj → Styl: styl z kilku słów (De Stijl, Art déco, Secesja, Młoda
  Polska…) musi paść w opisie dzieła. Muzea czytały „de stijl” jako dwa
  słowa, więc w wynikach były tablice drogowe i rysunki „w stylu
  romańskim”. Styl z jednego słowa (Impresjonizm, Kubizm) wystarcza też
  przy dziele z datą z lat tego stylu.

## 1.131.1

- Szukaj → Epoka: gdy wybrane okresy nachodzą na siebie (np. Biedermeier
  z Europy i Zabory z Polski), ich kreseczki pod osią leżą jedna pod drugą,
  każda w kolorze swojej grupy, zamiast się zakrywać.

## 1.131.0

- „Zdjęcia do podglądu” przeniesione z Ramki do Konfiguracji →
  Wyświetlanie → „Przykładowe zdjęcia”. Wgrywasz tam z telefonu do ośmiu
  zdjęć, a podgląd układów Multi pokazuje każdy układ na nich, w kolejności
  dodania. Nie trafiają do biblioteki ani na ramkę; krzyżyk je usuwa.

## 1.130.2

- Serwer nie staje już na ponad minutę, gdy ramka pyta o obraz w chwili, gdy
  inna praca zapisuje bibliotekę. 9 listopada przy szukaniu „Edward Munch”
  stał tak 78 s: miniatury zostawały puste, a aplikacja pisała „Serwer nie
  odpowiedział na czas”. Gdyby serwer znów stanął, log pokaże też, która
  praca go trzymała.

## 1.130.1

- Szukaj → Styl: pod obrazkami została sama nazwa stylu, lata są tylko przy
  nagłówkach półek. Obrazki stoją bliżej siebie, więc na ekranie mieści się
  ich więcej.
- Wybrany styl pilnuje swoich lat: dzieło z datą musi powstać mniej więcej
  wtedy, gdy ten styl istniał (z zapasem 15 lat przed i 40 po). Art déco nie
  pokazuje już Rubensa ani Muchy, których muzea znalazły po słowach w opisie.

## 1.130.0

- Szukaj → Temat: zamiast kapsułek spis w dwóch kolumnach, pogrupowany
  (Krajobraz, Przyroda, Ludzie, Życie i miejsca, Opowieści). Przy każdym
  temacie rysunek cienkopisem, a kolor jak akwarela: plama wylewa się poza
  linię, jasna w środku, z ostrym, nierównym brzegiem. Wybrany temat ma
  ptaszek. Kolory są bardziej różne, Ptaki, Muzyka i Mitologia też mają
  swój.

## 1.129.1

- Dzieła bez białej ramki ze skanu. Część muzeów (zwłaszcza starsze skany
  V&A) podaje obraz na płaskim białym lub czarnym arkuszu; serwer obcina teraz
  takie jednolite marginesy przy pobieraniu, a obrazy już zapisane przycina
  raz po aktualizacji i liczy ich kolory od nowa (biel marginesu nie jest już
  „Bielą” w Kolorystyce). Własne zdjęcia zostają bez zmian.

## 1.129.0

- Teraz: zmiana dzieła jest czytelna. Pasek pod ramką od pierwszej sekundy
  pokazuje, co jedzie na ramkę: miniaturę, tytuł i to, co się właśnie dzieje,
  a zamiast jednej belki ma trzy odcinki (Przygotowanie, Wysyłanie,
  Rysowanie), z których każdy wypełnia się osobno. Podgląd ramki trzyma stare
  dzieło, dopóki ramka naprawdę go nie zmienia; gdy zaczyna rysować, nowe
  dzieło pojawia się na nim jako blada odbitka i w tempie paska nabiera koloru
  i ostrości, zamiast rozsypywać stare w kropki farb. Opis pod ramką przechodzi
  na nowe dzieło razem z początkiem rysowania.
- „Ramka odświeża ekran” to teraz „Ramka rysuje obraz” (także na ekranie
  blokady).

## 1.128.0

- Ramka → Zdjęcia → Multi: „Zdjęcia do podglądu”. Wybierasz do ośmiu
  swoich zdjęć, a podgląd pokazuje każdy układ zawsze na nich, w kolejności
  wyboru (przy czterech zdjęciach na planszy cztery pierwsze). Wybór
  zapisuje się z ustawieniami ramki. Ramka dalej bierze zdjęcia z playlisty.

## 1.127.0

- Szukaj → Styl: każdy kierunek to mały obrazek w ramie z jasnego dębu, z
  nazwą i latami pod spodem, zamiast chmury kapsułek. Style leżą na pięciu
  półkach po kolei w czasie (Dawni mistrzowie, Romantyzm i realizm, Przełom
  wieków, Awangarda, Japonia), każdą przewijasz w bok. Wybrany ma otok, a
  pastylka „Styl” pokazuje małe obrazki wybranych stylów.
- Jedenaście nowych stylów: Manieryzm, Szkoła z Barbizonu, Orientalizm,
  Szkoła monachijska, Japonizm, Puentylizm, Futuryzm, Dadaizm, Nowa
  Rzeczowość, Surrealizm i Rinpa. Barbizon i Puentylizm były dotąd w
  Realizmie i Postimpresjonizmie. Dzieła dadaizmu, Nowej Rzeczowości i
  surrealizmu znajdziesz głównie z Użytkiem prywatnym.

## 1.126.0

- Ramka → Zdjęcia → Multi: podgląd układu jest od razu. Aplikacja układa
  planszę sama z miniatur zdjęć, z kadrami takimi jak na ramce, dla każdego
  układu i obu orientacji naraz. Zmiana układu nie czeka więc na serwer,
  a dokładny podgląd z serwera podmienia rysunek po cichu, gdy przyjdzie.
- Serwer nie przegląda już przy każdym podglądzie Multi całej biblioteki
  w głównej pętli (ok. 1 s na NAS, w tym czasie czekało wszystko inne),
  pamięta wybrane zdjęcia planszy i ich kadry, a aplikacja nie zamawia na
  zapas podglądów wszystkich układów naraz. Zapytania aplikacji dłuższe niż
  2 s trafiają do logu serwera.

## 1.125.0

- Szukaj → Temat: każdy temat ma przed nazwą mały rysunek, czarną kreską
  i najwyżej jednym kolorem (pagórki, fale, żaglówka, most, góry, płatek
  śniegu, księżyc, kłos, kurtyna…). Kapsułki są wyśrodkowane na karcie, podpis
  pod nimi też. Na ciemnej kapsułce (wybranej w jasnym trybie, każdej
  w ciemnym) rysunek leży na kremowym kółku, żeby kreska zawsze była czarna.

## 1.124.6

- Szukaj: kafelek Muzeum jest od pierwszej chwili, razem z pozostałymi
  grupami. Przy pierwszym wejściu w Szukaj czekał na listę muzeów
  z serwera i przez moment go brakowało. Tak samo w edytorze playlist.

## 1.124.5

- Szukaj → Muzeum, Styl, Temat: w otwartej grupie szukasz głównym paskiem
  na dole, bez drugiego pola w okienku. Pasek mówi wtedy, czego szuka
  („Muzeum albo miasto”, „Szukaj stylu”, „Szukaj tematu”), a dotknięcie go
  nie zamyka grupy. Po „Gotowe” pasek znowu szuka artystów i słów, z tym,
  co było w nim wpisane wcześniej. Gdy styl albo temat nic nie pasuje,
  „Szukaj „…” jako słowa” przenosi wpisane słowa do wyszukiwania. Tak samo
  w edytorze playlist.
- Szukaj → Epoka: też szukasz głównym paskiem („Okres albo rok”). Na pasach
  zostają nazwane okresy pasujące do wpisanych słów, a wpisany rok, np.
  1890, zostawia okresy, w których ten rok leży. Wybrane okresy zostają
  zawsze, oś czasu też.

## 1.124.4

- Szukaj → Epoka: pod osią czasu jest zawsze miejsce na kreseczkę wybranego
  okresu, więc karta nie podskakuje, gdy go zaznaczysz. Kreseczka ma kolor
  grupy okresu: złoty Starożytność, niebieski Europa, czerwony Polska,
  zielony Japonia i Chiny.

## 1.124.3

- Szukaj → Muzeum: muzeum, które katalog znał tylko z nazwy (np. „Prado”),
  i to samo muzeum podpowiedziane przez Wikidatę są jednym pasem, nie
  dwoma. Serwer od razu zapamiętuje, że ta nazwa to to muzeum, więc jego
  dzieła z katalogu też do niego należą.
- Lista muzeów otwiera się od razu: aplikacja pobiera ją już przy wejściu
  w Szukaj i pokazuje ostatnią, a w tle odświeża. Serwer trzyma policzoną
  listę przez półtorej minuty (do 10 minut, gdy katalog się nie zmienia).
- Wycinki dzieł w pasach muzeów są kadrowane na twarzach albo motywie, jak
  kafelki w Szukaj.

## 1.124.2

- Karteczka z podpisem przy Wypełnij jest zawsze w dwóch liniach: autor
  w pierwszej, tytuł w drugiej, także gdy podpis jest krótki.

## 1.124.1

- Karteczka z podpisem przy Wypełnij jest mniejsza: mniejsze pismo,
  ciaśniejsze marginesy wokół liter i bliżej rogu ekranu.

## 1.124.0

- Szukaj → Muzeum wybiera teraz miejsce, w którym dzieło fizycznie jest,
  a nie źródło zdjęcia. Lista to pasy z wycinkiem dzieła z tego muzeum.
  Muzeum bez dzieła w katalogu dostaje obraz z Wikidaty, a gdy i tego nie
  ma, miękki gradient z ziemistych barw, za każdym razem ten sam. Pole
  „Muzeum albo miasto” od trzech liter podpowiada też muzea spoza katalogu
  (np. Prado). Ich dzieła serwer znajduje przez Wikidatę i Commons oraz
  Europeanę. Wybrane i Wykluczone działają jak dotąd.
- Przytrzymanie nazwy muzeum nad tytułem (w Teraz i na karcie dzieła)
  otwiera Szukaj z dziełami tego muzeum, tak jak przytrzymanie nazwiska
  autora.
- Reprodukcje dawnych obrazów (chromolitografia, oleodruk, fotograwiura,
  fotografia itp. dzieła malarza zmarłego przed wynalezieniem techniki)
  serwer w nocy przypisuje miejscu oryginału. Np. „Adoracja Baranka”
  z Wellcome Collection to Katedra św. Bawona w Gandawie, a wiersz
  „Zdjęcie dzieła” mówi „Chromolitografia, Wellcome Collection”.
- Konfiguracja → Źródła dzieł: przełączniki Wikimedia Commons, Europeana,
  Openverse i WikiArt. Wyłączone nie dokładają dzieł do Szukaj ani do
  playlist; muzeum wybrane w Szukaj i tak znajdzie przez nie swoje dzieła.
- Playlisty z wybranymi lub wykluczonymi muzeami przechodzą na miejsca same.

## 1.123.6

- Stuknięcie w imię i nazwisko autora w Teraz, na karcie dzieła i w studium
  niczego już nie otwiera. Inne dzieła autora w Szukaj pokazuje tylko
  przytrzymanie nazwiska, jak dotąd z narastającym drżeniem i lekkim
  powiększeniem. VoiceOver ma do tego osobną czynność.

## 1.123.5

- Podpis na dziele: obie linie karteczki są wyrównane do prawej
  (chorągiewka), a podpis, na karteczce i pod dziełem, jest bez daty.
  Tryb Opis bez zmian.

## 1.123.4

- Jeden artysta to jeden wiersz w podpowiedziach Szukaj, choć muzea zapisują
  go różnie: „Rembrandt van Rijn”, „Rembrandt”, „Rembrandt (Rembrandt van
  Rijn)” i „Rembrandt Harmensz. van Rijn” to teraz jeden Rembrandt z łączną
  liczbą dzieł, a „Jan van Eyck” i „Jan Van Eyck” jeden van Eyck. Wybrany
  artysta znajduje dzieła pod każdym z tych zapisów, także w playlistach.
  Serwer łączy zapisy o tych samych słowach (bez względu na wielkość liter,
  kolejność i nawiasy), zapis Met „X (Y)” oraz dłuższe imię z patronimikiem
  albo drugim nazwiskiem. Osobno zostają „Starszy/Młodszy”, „II”, warsztat
  i uczniowie, a także inna osoba o tym samym imieniu (Rembrandt Peale).

## 1.123.3

- Diagnostyka dla właściciela: log całego dnia z dysku serwera
  (`/api/debug/log?day=RRRR-MM-DD`), bo bufor w pamięci sięga tylko kilku
  ostatnich godzin i rano nie było już widać nocy. Stan lokalnych baz muzeów
  (`/api/debug/dumps`: kiedy zbudowana, ile dzieł, czy się buduje, czemu się
  nie udało) i ręczne zbudowanie jednej bazy od razu, bez czekania na noc
  (`POST /api/debug/dumps/<klucz>`: aic, cma, si, wellcome).

## 1.123.2

- Podpis na dziele (karteczka przy Wypełnij) nie jest już ucinany
  wielokropkiem: gdy się nie mieści w jednej linii, autor idzie w pierwszej,
  a tytuł z datą w drugiej. Tak samo na ramce i w podglądach aplikacji.

## 1.123.1

- Zapasowy obraz z Wikimedia Commons mają teraz także dzieła z National
  Gallery of Art, Yale, Smithsonian, Paris Musées, SMK, Courtauld i V&A.
  Gdy któreś z tych muzeów nie odpowiada, miniatury, karta i ramka biorą
  ten sam obraz z Commons zamiast zostawiać puste miejsce. Commons ma pliki
  dla ok. 120 tys. ich dzieł. Getty i Wellcome nie mają takiego powiązania.
- Obraz zastępczy zostaje na stałe: serwer nie pyta już w nocy muzeum
  o jego własny obraz. Własny obraz muzeum można przywrócić ręcznie na
  karcie dzieła („Przywróć zdjęcie muzeum”).

## 1.123.0

- Chicago (AIC), Cleveland, Smithsonian i Wellcome mają na serwerze własne
  lokalne bazy, zbudowane z plików, które same publikują. Szukaj, Odkrywaj,
  losowanie, playlisty i kopie nie pytają już tych muzeów o wyniki, tylko
  obrazy dalej przychodzą od nich. Mniej blokad (AIC) i szybsze odpowiedzi.
- Bazy pobierają się nocą raz na dwa miesiące, i to tylko wtedy, gdy muzeum
  zmieniło plik. Pierwsza noc po aktualizacji je zbuduje, a do tego czasu
  wszystko działa jak dotąd.
- Pełny katalog niczego już nie dobiera: serwer nie ściąga nowych dzieł
  z muzeów, żeby zastąpić nimi starsze (ani w dzień, ani w nocy), i nie
  dopisuje tego, co pokazało Szukaj. W Konfiguracji przy limicie katalogu
  pojawia się wtedy komunikat „Katalog jest pełny”; żeby katalog rósł
  dalej, wystarczy zwiększyć limit.
- Gdy muzeum dzieła nie daje obrazu (jak teraz Muzeum Narodowe w Krakowie,
  którego serwer urywa oryginały), karta dzieła sama szuka zastępstwa:
  najpierw w Wikimedia Commons, a gdy znajdzie ten sam obraz, od razu go
  podmienia. Dopiero gdy Commons nic nie ma, pyta pozostałe źródła.
- Dzieła z muzeów narodowych w Krakowie i Warszawie serwer znajduje na
  Commons po numerze inwentarzowym, więc mają tam zapasowy obraz także
  dla miniatur.
- W nocy serwer sprawdza, czy muzeum znowu daje własny obraz; jeśli tak
  i jest co najmniej tak dobry, wraca on na miejsce zastępstwa.
- Zapasowe adresy obrazów (Commons przez Wikidata) są pytane dopiero, gdy
  własny adres muzeum zawiedzie, więc zwykłe pobieranie miniatur nie
  kosztuje już zapytań do Wikidata.

## 1.122.0

- Dzieła, które muzea przyniosły w Szukaj, ale nie pasowały do wyboru
  (inny kolor, inne lata albo epoka, tagi, technika, inny autor), trafiają
  do katalogu, jeśli ich miniatura jest już na serwerze. Nie kosztuje to
  żadnego dodatkowego zapytania do muzeów, a katalog rośnie z tego, o co
  i tak pytaliśmy. Dzieła pokazane w Szukaj idą do katalogu pierwsze.

## 1.121.8

- „Kopie dzieła” znowu pytają wszystkie źródła. Od 1.121.0 szukanie stawało
  na 3/20: muzea w sieci czekały, aż przestaniesz używać aplikacji, a po
  20 s wszystkie zgłaszały brak odpowiedzi.
- Szukaj, Odkrywaj i kopie nie czekają już na tę samą stronę wyników, którą
  akurat pobiera praca w tle.

## 1.121.7

- Fotografia z Wikimedia Commons działa też bez wpisanych słów: serwer
  losuje stare zdjęcia (m.in. z zasobów Library of Congress na Commons),
  bez rycin, plakatów i map.
- Szukanie w Wikimedia Commons pomija skany dokumentów z archiwów
  (formularze, nieśmiertelniki) i diagramy chemiczne.
- Miniatury w Szukaj nie zostają już puste: gdy serwer pobierał tę samą
  miniaturę w tle i czekał, aż przestaniesz korzystać z aplikacji, kafelek
  czekał razem z nim. Teraz po chwili serwer pobiera ją od razu dla
  aplikacji. To samo dotyczy obrazu na karcie dzieła.
- Zdjęcia z Wikimedia Commons bez znanego autora mają podpis „Nieznany”
  zamiast „NieznanyUnknown author”; zapisane wcześniej dzieła są poprawione.

## 1.121.6

- Kadr otwiera się płynniej: okienka kadru są widoczne od początku lotu
  ramki, bez plakietki „Wczytuję podgląd…” w połowie animacji i bez
  mignięcia podglądu w chwili dotknięcia.
- Ekran Kadru nie ma już napisu „Kadr” u góry.

## 1.121.5

- Fotografia w Szukaj sięga też do całej Wikimedia Commons: stare zdjęcia
  w domenie publicznej (sprzed 1930), dość duże dla ramki.
- „Pierwsze kolory” biorą też zdjęcia Prokudina-Gorskiego, fotochromy i
  kolorowe zdjęcia FSA z Commons, więc są pełne, nawet gdy Library of
  Congress odpoczywa.

## 1.121.4

- Serwer pamięta po aktualizacji, które muzeum go zablokowało i na jak
  długo, więc nie puka do niego od nowa po restarcie. Muzeum, które blokuje
  ponownie w ciągu kilku godzin, odpoczywa dwa razy dłużej; Art Institute
  of Chicago odpoczywa od razu pół godziny.
- Źródło, które seryjnie odpowiada błędami serwera, dostaje 10 minut
  przerwy.
- Kolekcje Library of Congress serwer pobiera do siebie tylko w nocy.

## 1.121.3

- Zdjęcia: passe-partout zaczyna się od 10 mm, przy wyborze Passe-partout
  i Multi oraz przy wysyłaniu zdjęcia na ramkę (wcześniej 20 i 30 mm).
  Multi można zwęzić do 10 mm, a ramka pokazuje dokładnie to, co suwak;
  wcześniej poniżej ok. 12 mm nic się nie zmieniało. Suwak w Multi zaczyna
  się od 10 mm, krok zostaje 5 mm.

## 1.121.2

- Opis: passe-partout można zwęzić do 5 mm, a ramka i podgląd pokazują
  dokładnie to, co suwak; wcześniej wszystko poniżej ok. 15 mm wyglądało
  tak samo. Suwak w Opisie zaczyna się od 5 mm.

## 1.121.1

- Szukaj i edytor playlisty pytają muzea dopiero przy przewijaniu, gdy
  serwer sam ma co najmniej 60 pasujących dzieł; przy mniejszej liczbie
  muzea są pytane od razu, jak dotąd.

## 1.121.0

- Serwer pyta muzea rzadziej i łagodniej, żeby nie blokowały domowego
  adresu: przez 10 minut po aktualizacji pracuje tylko na Twoje prośby,
  zapamiętane wyniki wyszukiwań są dobre przez 3 dni i nie znikają przy
  aktualizacji, Met dostaje najwyżej 2 zapytania na sekundę i 1500 na
  godzinę, a po odmowie Met i AIC serwer czeka, zamiast pukać dalej.
- Aplikacja bierze wszystkie miniatury z serwera, który pobiera każdą raz
  i ją zachowuje; telefon w domu nie pyta już muzeów sam. Miniatury z
  Art Institute of Chicago dochodzą przez to po jednej na sekundę, tak jak
  każe AIC.
- Kolekcje Library of Congress, z których są zestawy i losowanie (np.
  „Pierwsze kolory”), serwer trzyma u siebie i odświeża co 3 miesiące
  nocą; LoC jest pytana tylko o to, czego szukasz, i nocą.
- Praca w tle, na którą nikt nie czeka, stoi, gdy używasz aplikacji, i
  idzie wolniej; polskie fakty z Wikidata serwer pamięta po aktualizacji.
- Log serwera jest zapisywany na dysku przez 7 dni, a Konfiguracja →
  Diagnostyka pokazuje przy każdym źródle, kto pytał (Szukaj, Odkrywaj,
  noc, katalog…).

## 1.120.3

- Szukaj po autorze pokazuje tylko jego dzieła: bez prac innych artystów,
  które jedynie o nim wspominają (np. przy Van Goghu autoportret
  Guillaumina czy anonimowe szkice), i bez kopii „według” niego ani prac
  jego warsztatu czy naśladowców. To samo w playlistach inteligentnych z
  artystą. Żeby wyników nie było mniej, serwer zagląda w muzeach o kilka
  stron dalej.

## 1.120.2

- Okładka „Ukryte” nie ma już szronu z ziarnem ani kremowej warstwy: dzieła
  rozmywa zwykła systemowa mgiełka, taka jak w iOS. Ruch zostaje, a odblask
  przy przechyle telefonu jest słabszy.

## 1.120.1

- Jaśniejsze dzieła wchodzą płynnie bez etapu jasnych partii: przez
  chwilę obraz jest zwykły, a potem w około sekundę całe dzieło równo
  dochodzi do siły ustawionej w Konfiguracji.

## 1.120.0

- Karta dzieła: style i tematy z muzeum („18th Century”, „boys”,
  „pilgrimages”) są teraz w ramce z danymi, w wierszu „Słowa kluczowe”
  (dawniej „Na obrazie”), po polsku i bez tych, które tylko powtarzają
  słowa rozpoznane na obrazie. „Rodzaj” i „Pochodzenie” też po polsku
  („obraz”, „Włochy”). Rzadsze etykiety tłumaczy model raz i serwer je
  pamięta.

## 1.119.2

- Biała ramka w podglądach ma grubość w proporcji do obrazu, wszędzie taką
  samą: przy wejściu w „Kadr” i wyjściu z niego (z Teraz, karty dzieła i
  Studium) obwódka już nie przeskakuje.

## 1.119.1

- Jaśniejsze dzieła na karcie dzieła i w studium wchodzą płynnie, w około
  sekundę: najpierw obraz jest zwykły, potem rozjaśniają się jego jasne
  partie, a na końcu całe dzieło równo, z siłą ustawioną w Konfiguracji.

## 1.119.0

- Kafelek „Teraz prezentowane” w Playlistach pokazuje jedno dzieło naraz
  zamiast kolażu czterech. Co kilka sekund następne dzieło okładki powoli
  wyłania się spod poprzedniego, a obraz leży odrobinę głębiej niż karta
  i delikatnie przesuwa się przy obracaniu telefonu i przewijaniu, jak
  w Studium dnia. Poza ekranem animacja stoi.

## 1.118.5

- Okładka „Ukryte” nie ma już jasnych pasów u góry i u dołu, a odblask
  przy przechyle telefonu jest słabszy.

## 1.118.4

- Paralaksa w Studium dnia i na okładce Ukryte jest ok. trzy–cztery
  razy słabsza: obraz przesuwa się tylko odrobinę, gdy obracasz telefon, i
  ledwie zostaje z tyłu przy przewijaniu.

## 1.118.3

- Okładka „Ukryte” w Playlistach ożyła: rozmyte dzieła powoli dryfują za
  szybą, a gdy przechylasz telefon, przesuwają się pod nią i po szkle
  przechodzi odblask. Szron jest cieńszy, więc kolory są żywsze, a treść
  nadal rozmyta. Krawędź daje szkło iOS, z niego jest też plakietka z okiem.
  Z włączonym „Ogranicz ruch” okładka stoi.

## 1.118.2

- Obraz w Studium dnia w Odkrywaj leży odrobinę głębiej niż karta:
  przesuwa się delikatnie, gdy obracasz telefon w dłoni, i zostaje lekko
  z tyłu przy przewijaniu. Przy „Ogranicz ruch” stoi w miejscu.

## 1.118.1

- Konfiguracja → Diagnostyka ma nową sekcję „Zapytania do źródeł”: ile
  zapytań serwer wysłał do każdego muzeum dziś i w ostatnich 7 dniach,
  ile źródło odrzuciło (blokada przed robotami, „za dużo zapytań”, błędy),
  ile serwer sam wstrzymał, bo źródło odpoczywało albo wyczerpał się
  limit, oraz zużycie limitów Paris Musées, Smithsonian, Openverse
  i WikiArt. Liczniki z tygodnia przeżywają aktualizację serwera.

## 1.118.0

- Pisanie studium dzieła ma cztery kroki zamiast trzech: Źródła, Tekst,
  Kompozycja i Detale. Dotąd „Pisanie” trwało prawie cały czas.
- Karta na ekranie blokady, wyspa i karta w aplikacji mówią, co dzieje się
  w danej chwili, w pierwszej osobie: „Piszę studium”, „Analizuję
  kompozycję dzieła”, „Sprawdzam ślady”, „Opisuję kompozycję”, „Wycinam
  detale z oryginału” i tak dalej.
- Pasek postępu płynie sam do przewidywanego końca. Pod nim widać, ile
  minęło i ile studium zwykle trwa, a w aplikacji „jeszcze ok. 1½ min”.
  Serwer liczy czas z ostatnich napisanych studiów. Zwinięta wyspa
  pokazuje kółko postępu.
- Starsza aplikacja z nowym serwerem działa jak dotąd.

## 1.117.0

- Serwer ma jedną tabelę zasad dla wszystkich źródeł dzieł: tempo, ile
  zapytań naraz i limity na godzinę lub dobę, z linkiem do zasad każdego
  muzeum. Liczby dla dotychczasowych źródeł się nie zmieniły.
- Paris Musées, Smithsonian, Openverse i WikiArt mają liczone limity
  dzienne lub godzinowe. Praca w tle zostawia 40% puli dla Szukaj i karty
  dzieła, więc nocne zadania nie wyczerpią limitu.
- Spis Met jest sprawdzany co trzy miesiące i pobierany tylko wtedy, gdy
  się zmienił. Spis NGA jest pobierany raz w miesiącu zamiast co tydzień, a
  Luwr pyta Commons tylko o nowe pliki. Razem ok. 170 MB pobrań miesięcznie
  zamiast ok. 560 MB.
- Serwer pamięta na dysku opisy dzieł z Rijksmuseum i Yale, więc ponowne
  otwarcie wyników to jedno zapytanie zamiast 25 albo 49.
- Strony wyników wyszukiwania są zapisywane na dysku i przeżywają
  aktualizację serwera. Starsze niż 3 godziny pojawiają się od razu, a
  serwer w tle pobiera ich świeżą wersję.
- Raz na dobę log pokazuje, ile zapytań poszło do każdego źródła i ile
  odmówiło.

## 1.116.0

- Szukaj i playlista inteligentna to teraz jedno szukanie. Edytor
  playlisty pokazuje te same dzieła co Szukaj, z tą samą liczbą, i tak
  samo dopytuje muzea o kolejne strony przy przewijaniu. Limit „Ile
  dzieł” zostaje.
- Po zapisaniu playlisty serwer pobiera z muzeów to, co pokazuje Szukaj:
  ze słowami przetłumaczonymi na język muzeum („gitara” w Met to
  „guitar”), a nie losowe dzieła sprawdzane potem słowo w słowo.
- Dzieło znalezione w muzeum pamięta, na jakie szukanie je znaleziono,
  i od tej pory pasuje do tych samych wyborów w Szukaj i w playliście,
  nawet gdy jego opis nie zawiera wpisanego słowa. Epoki są dalej
  sprawdzane na dziele: XVII i XIX wiek nie wciągają już XVIII.

## 1.115.0

- Serwer szuka dzieł Met we własnym katalogu na NAS-ie: raz w miesiącu
  pobiera otwarty spis zbiorów Met (ok. 340 MB, 260 tys. dzieł z domeny
  publicznej) i przeszukuje go w kilka milisekund, zamiast pytać
  wyszukiwarkę Met. Met dostaje już tylko pytania o znalezione dzieła.
- Gdy spis znajduje mało dzieł, serwer pyta wyszukiwarkę Met jak dawniej,
  ale pomija dzieła, które według spisu nie są w domenie publicznej (np.
  dla „Monet” żadne z pierwszych ośmiu wyników nie było).

## 1.114.0

- Analiza kompozycji w studium dzieła jest pisana jednym głosem. Dotąd
  kroki analizy doklejały do tekstu własne zdania („Budowa jest…”, zdanie
  o siatce), a prompt wyliczał zdania po kolei, więc połowa studiów
  zaczynała się od „Najmocniej działa…”. Teraz ślady, siatkę i ruch nadal
  sprawdzają osobne kroki, a na końcu Opus pisze z nich cały tekst. Wie,
  jak zaczynały się ostatnie studia, i nie zaczyna tak samo. Kosztuje to
  ok. 0,015 USD więcej na studium. Studium zamówione na później idzie
  przez jeszcze jeden pakiet (tekst), więc bywa gotowe nieco później.
- Studia napisane wcześniej dostaną w tle nowy tekst kompozycji, z tymi
  samymi śladami na obrazie (ok. 0,65 USD za 42 studia).
- Tło dzieła nie zaczyna się już od „Obraz powstał…”, a „Na ramce” mówi
  konkretnie, co wyjdzie dobrze, a co straci, bez formuły o rastrze.

## 1.113.5

- Serwer pamięta opisy dzieł z Met i pyta o każde dzieło tylko raz na 90
  dni. Ponowne wejście w zestaw nie pyta już Met o te same dzieła.
- Do Met idzie jedno zapytanie naraz, zamiast serii przy otwieraniu kilku
  zestawów. Rano 7 listopada zapora Met zablokowała domowy adres.

## 1.113.4

- Serwer trzyma się aktualnych zasad Library of Congress: najwyżej 17
  zapytań o wyszukiwanie na minutę (wolno 20) i 120 o obrazy (wolno 150),
  większe strony wyników, a po odmowie godzina przerwy bez sprawdzania
  co minutę. Wcześniej pytał nawet 60 razy na minutę.

## 1.113.3

- „Pierwsze kolory” pokazują tylko zdjęcia z prawdziwych procesów
  barwnych (autochromy, fotochromy, kolorowe płyty Prokudina-Gorskiego,
  slajdy). Ręcznie malowane albumy i portrety już tam nie trafiają.
  Doszły fotochromy z Cleveland i autochromy z Art Institute of Chicago.
- Serwer pyta Library of Congress rzadziej, a cienkie karty Sztuk innych
  dopełnia tylko w nocy i po trochu. Rano 7 listopada Library of Congress
  i Met zablokowały domowy adres, najpewniej po zbyt wielu zapytaniach.

## 1.113.2

- Konfiguracja → Serwer: pole z kropkami ma podpis „Token API”. To
  hasło, którym aplikacja przedstawia się serwerowi.
- Adresu serwera spoza domu nie trzeba już wpisywać. Tailscale wbudowany
  w aplikację sam znajduje serwer wśród urządzeń w Tailscale, a serwer
  przekazuje adres każdemu telefonowi, także domownikom i tym z wyłączonym
  Tailscale w aplikacji. W karcie „Dostęp spoza domu” widać „Serwer w
  Tailscale” i „Szukaj ponownie”. Karta „Serwer ramki” ma już tylko adres
  w domu, token i „Połącz”.

## 1.113.1

- W Konfiguracji → Ramka nie ma już pola Adres MAC. Do budzenia serwer
  używa zawsze adresu Wi-Fi, który podaje sama aplikacja ramki.

## 1.113.0

- Konfiguracja to teraz krótka lista jak w Ustawieniach iOS: Na co dzień,
  Dzieła i biblioteka, Ramka i serwer oraz Diagnostyka. Każdy wiersz
  otwiera swoją stronę i podpowiada, co na niej najważniejsze.
- Wszystkie klucze (Claude, APNs, Tailscale, muzea) i certyfikaty Samsunga
  są w jednym miejscu: Klucze i certyfikaty.
- Bez powtórek z zakładki Ramka (Wi-Fi ramki, restart aplikacji, wersja
  serwera) i bez długich opisów.
- Nie ma już przełącznika Tryb demo: przykładowe dzieła są tylko wtedy,
  gdy aplikacja nie ma adresu serwera. Zniknął też przycisk „Przywróć
  wartości z serwera”.

## 1.112.3

- „Popraw detale” i „Wykonaj ponowną analizę” zamówione na kilku
  dziełach naraz nie zostawiają już żadnego z nich w nieskończonym
  „Claude sprawdza…”.

## 1.112.2

- Detale w studiach lepiej trafiają. Claude obwodzi rzecz czterema
  krawędziami, a serwer sam centruje na niej wycinek, dodaje margines
  i dobiera proporcje. Dotąd Claude podawał róg, szerokość i wysokość,
  więc rzecz często lądowała w rogu wycinka albo obok niego.
- Nowe studia znowu same sprawdzają detale tak jak „Popraw detale”:
  Claude widzi każdy wycinek i poprawia ramkę, która chybia (ok. 0,07 USD
  na studium, w zamówieniu na później połowa).

## 1.112.1

- Odkrywaj: okładki kart nie migają już przy przewijaniu. Karta, która
  wraca na ekran, od razu pokazuje swoje obrazy, zamiast za każdym razem
  wyłaniać się z koloru tła.
- Okładki kart nie zmieniają się w ciągu dnia, gdy do katalogu dochodzą
  nowe dzieła. Nowe dzieło zmienia najwyżej jeden obraz okładki, a nie
  wszystkie cztery; nowe okładki są jak dotąd co dzień.
- Rzędy kart sięgają do krawędzi ekranu: karta przesuwana palcem znika
  dopiero za krawędzią, a nie 2 cm przed nią.

## 1.112.0

- Odkrywaj w nowej kolejności: Dziś dla Ciebie, Kierunki i style,
  Sztuka polska, Kolor i nastrój, Epoki, Tematy, Grafika i plakat,
  Sztuki inne, a na końcu Studia dzieł.
- W „Dziś dla Ciebie” najpierw karta Kuratora, Artysta tygodnia, druga
  karta Kuratora i Motyw dnia, potem dwie karty „Ponieważ lubisz” i para
  tygodnia. Karty ulubionych artystów (dawne „Bo lubisz”) liczą się
  tylko z serduszek, jest ich najwyżej dwie, a osobnej grupy już nie ma.
- Grafika i plakat zaczyna się od plakatów, a w Sztukach innych Rzeźba
  jest przed Fotografią.
- Wiersz „Dawno ich nie było” nie jest już pokazywany.

## 1.111.14

- „Pierwsze kolory” w Sztukach innych bierze zdjęcia z całych kolekcji
  Library of Congress: kolorowe zdjęcia Prokudina-Gorskiego, fotochromy,
  autochromy i kolorowe slajdy z lat 40. Dotąd wyszukiwanie słów
  znajdowało tylko kilka, a na karcie były 2.
- Karty Propozycji z mniej niż 4 dziełami nie są pokazywane, zamiast
  szarych pól na okładce. W nocy serwer najpierw dobiera dzieła takich
  kart w Sztukach innych, więc wracają same.
- Wyszukiwanie zdjęć w Library of Congress nie kończy się już po kilku
  stronach.

## 1.111.13

- Konfiguracja → Wyświetlanie dzieł: pod „Jaśniejsze dzieła” suwak
  „Siła rozjaśnienia” (od 1,1× do 3×, domyślnie 1,6×).

## 1.111.12

- Paczka aplikacji ramki wraca do ustawień sprzed testu VXT. Dokładna
  kopia ustawień odtwarzacza VXT (1.111.8) nie usunęła ekranu startu
  Samsunga, a sprawiła, że ramka uruchamiała aplikację przy każdej
  pobudce. Puste sprawdzenia rysowały wtedy ekran startu i ten sam
  obraz jeszcze raz, co kosztowało baterię. Nowa paczka instaluje się
  po przytrzymaniu guzika na ramce.

## 1.111.11

- Sztuczne podbicie HDR usunięte. Słoneczko na pełnym ekranie tylko
  rozjaśnia ekran, a jasność zaczyna wracać od razu, gdy zamykasz pełny
  ekran (krzyżykiem albo przesunięciem w dół), nie dopiero po zamknięciu.
- Na karcie dzieła i w studium obraz i jego detale świecą trochę jaśniej
  niż strona wokół, równo na całej powierzchni (na ekranach z HDR).
  Konfiguracja → Wyświetlanie dzieł → „Jaśniejsze dzieła”, domyślnie
  włączone.

## 1.111.10

- Test: gdy ramka śpi, pobranie obrazu przez wbudowany odtwarzacz
  Samsunga (polecenie MDC z Maca) nie uruchamia już aplikacji ramki,
  więc widać, jak odtwarzacz rysuje obraz sam. Serwer może też podać
  odtwarzaczowi wcześniejszy obraz (`content.json?file=…`), żeby test
  pokazał prawdziwą zmianę.

## 1.111.9

- Oś czasu w Epoce: zakres przy prawym końcu („Po 1945”) nie jest już
  ucinany przy krawędzi arkusza, napis kończy się pod prawym koralikiem.
  Zakres sięgający bieżącego roku pisze się „1945–obecnie” zamiast
  „1945–2026”.

## 1.111.8

- Godzina zmiany dodana w aplikacji tuż po pobudce ramki nie przepada.
  Ramka po starcie czeka do 2,5 minuty, aż ekran się odświeży, i dopiero
  potem zasypia; dotąd zasypiała z planem sprzed tej chwili i nie
  ustawiała budzika na nową godzinę (21:30 dodane o 21:14 zostało
  pominięte). Teraz przed zaśnięciem pyta serwer jeszcze raz o plan.
- Paczka aplikacji ramki (test) ma ustawienia odtwarzacza VXT Samsunga
  przepisane dokładnie tak, jak on je deklaruje; wcześniejsza kopia
  miała jeden klucz pod złym adresem. Sprawdzamy, czy ekran startu
  Samsunga przed obrazem zniknie. Nowa paczka instaluje się po
  przytrzymaniu guzika na ramce.

## 1.111.7

- Sztuczne podbicie HDR jest płynniejsze. Rozjaśnia całe jasne obszary
  obrazu (niebo, okno, twarz) i łagodnie przechodzi w resztę, zamiast
  zapalać pojedyncze małe plamki. Ciemne linie i cienie obok świateł
  nie dostają poświaty, a najmocniejsze podbicie jest niższe (do 2,4×).

## 1.111.6

- Zestawy w Odkrywaj otwierają się szybciej. Każdy zaczyna się od dzieł,
  które ma już katalog na ramce, zanim odpowiedzą muzea, a pierwsza
  strona zestawu jest gotowa od razu (serwer liczy ją razem z kartami
  i przy kolejnym wejściu nie przelicza całego katalogu od nowa).
- Przeszukiwanie katalogu jest ok. dwa razy szybsze, a lista kart
  Odkrywaj jest lżejsza, więc mniej spowalnia zestaw otwierany zaraz po
  wejściu w zakładkę.
- Zestaw otwarty ponownie w ciągu pół godziny od razu pokazuje dzieła,
  które miał, i dociąga dalsze.

## 1.111.5

- Na kafelku Serwer w zakładce Ramka, gdy czeka nowsza wersja, pod
  numerem obecnej jest teraz napis „Dostępna aktualizacja do 1.111.2”
  (z numerem nowej wersji) zamiast krótkiego „jest 1.111.2”.

## 1.111.4

- Fotografie w sepii, stare odbitki i rysunki brązowym tuszem lub na
  kremowym papierze zostają na ramce w swoim ciepłym tonie. Skalę
  szarości dostają tylko naprawdę czarno-białe zdjęcia, ryciny
  i rysunki.

## 1.111.3

- Druga próba zmiany obrazu jednym odświeżeniem. Przezroczysty ekran
  startu z 1.105.0 nic nie zmienił: ramka i tak rysuje swój granatowy
  ekran ładowania przy każdym starcie aplikacji. Nowa paczka aplikacji
  ramki przejmuje ustawienia odtwarzacza VXT Samsunga, który rysuje
  obraz bez tego ekranu, i odczytuje, jak zbudowane są odtwarzacze
  Samsunga na ramce. Paczka instaluje się po włączeniu ramki przyciskiem.

## 1.111.2

- Ciemne, ciepłe obrazy olejne (np. „Studium starca w profilu”
  Rembrandta) nie trafiają już na ramkę w skali szarości. Czarno-białe
  są tylko rysunki, ryciny i fotografie bez własnego koloru, a obraz
  malarski tylko wtedy, gdy samo jego zdjęcie jest czarno-białą kopią.

## 1.111.1

- Sztuczne podbicie HDR dobiera się samo do każdego dzieła. W ciemnym
  obrazie wydobywa jaśniejsze partie (twarz, światło świecy), w jasnym
  podbija tylko same światła i delikatniej, a gdy duża część obrazu
  świeciłaby naraz (niebo, jasne tło), łagodnieje. Barwy i przejścia
  w światłach zostają, równy obraz bez wyraźnych świateł nie zmienia się.

## 1.111.0

- „Użytek prywatny” w Konfiguracji znosi teraz ograniczenia licencji
  wszędzie, gdzie źródło samo publikuje obraz: Europeana daje też prace
  wciąż chronione prawem autorskim (z opisem „Prawa autorskie w mocy
  (użytek prywatny)”), a WikiArt jest zwykłym źródłem w Szukaj,
  playlistach i propozycjach ulubionych autorów.
- Z Konfiguracji znikają przełączniki „WikiArt (tylko testy)” i „Bez
  limitu 70 lat (tylko testy)”: zastępuje je Użytek prywatny. Dzieła,
  które przez nie trafiły do biblioteki, zostają.
- Nowe karty w Odkrywaj przy Użytku prywatnym: „Sztuka współczesna”
  (Picasso, Hopper, Magritte, Rothko, Warhol, Hockney, Richter i inni)
  i „Polska sztuka powojenna” (Wróblewski, Nowosielski, Kantor, Fangor,
  Beksiński, Opałka, Dwurnik i inni).
- Okres „Po 1945” sięga do dziś, a nie tylko do 1955 roku.

## 1.110.6

- Więcej antyku w Odkrywaj → Epoki. Karty starożytności pytają też Getty,
  Yale i V&A, więc we Freskach Rzymu są freski z Pompejów, Boscoreale
  i Dura-Europos, a w Portretach fajumskich portrety z Getty i Yale.
  Wcześniej te dzieła odpadały, bo muzea podają ich datę tylko słowami
  („1st century A.D.”), a Yale zapisywał daty p.n.e. jako naszej ery.
  Ikony z V&A też już się liczą jako malarstwo.

## 1.110.5

- Czytelniejsza oś czasu w Szukaj → Epoka: nazwy okresów spoza wybranych
  lat są ciemniejsze, a paski okresów w wybranym zakresie mają pełny
  kolor. Okresy stoją trochę ciaśniej, a sama karta jest nieco wyższa,
  więc wszystko mieści się na jednym ekranie. Pod kartą Epoka nie ma już dopisku „Wybierz dowolnie wiele…”.
- Serwer odczytuje rok także z dat zapisanych słowami, np. „18th century”,
  „late 16th century”, „ca. 1890s” czy „pierwsza dekada XX wieku”. Około
  200–250 dzieł, głównie z Europeany i Yale, trafi przez to do Epoki.

## 1.110.4

- Nowe karty Epok (Egipt, Fajum, Freski Rzymu, Ikony) i tematy „Sztuk
  innych” nie stoją już puste: zaczynają się od dzieł z katalogu, a to,
  co muzea znajdą, zostaje w katalogu na następny raz. Drugie wejście
  w tę samą kartę przez 3 godziny nie czeka na muzea, a dzieła jednego
  muzeum pojawiają się po 2 sekundach, nie dopiero na końcu.

## 1.110.3

- Konfiguracja → Pełny ekran: pod „Sztuczne „podbicie” w HDR” nowy
  przełącznik „Bez podnoszenia jasności”. Słoneczko tylko podbija obraz
  w HDR, a jasność ekranu zostaje Twoja.

## 1.110.2

- Powiadomienie o nowej wersji serwera mówi prościej: „Nowa wersja
  serwera ramki”, a pod spodem „Wersja 1.110.2 czeka na instalację.
  Stuknij i wybierz „Aktualizuj serwer”.”

## 1.110.1

- Dzieło na cały ekran ma obok krzyżyka słoneczko: rozjaśnia ekran do
  maksimum na czas oglądania, a po zamknięciu wraca Twoja jasność.
  Wybór jest zapamiętany.
- Konfiguracja → Pełny ekran → „Sztuczne „podbicie” w HDR”: słoneczko
  dodatkowo sprawia, że najjaśniejsze miejsca obrazu świecą mocniej niż
  biel ekranu (na telefonach z HDR, poza trybem niskiego zużycia energii).
  Ciemne i średnie tony zostają. Domyślnie wyłączone.

## 1.110.0

- Nowa grupa „Sztuki inne” w Odkrywaj, zaraz po „Grafika i plakat”:
  karty Rękopisy i miniatury, Fotografia, Rzeźba oraz Ceramika i
  rzemiosło, a za nimi 15 propozycji, np. Godzinki i kalendarze,
  Pierwsze kolory, Wit Stwosz i gotyckie drewno, Błękit i biel.
- Katalog na serwerze trzyma teraz trochę dzieł tych czterech technik,
  razem 6% katalogu (fotografia 2%, rękopisy 1,6%, rzeźba i ceramika
  po 1,2%), żeby Szukaj z wybraną techniką miał je od razu. Dobierają się
  stopniowo, głównie nocą.
- Te dzieła żyją „we własnym sosie”: nie mają studium dzieła, nie są
  dziełem dnia i nie trafiają do innych grup Odkrywaj, rotacji ani
  playlist o malarstwie, tylko do swojej grupy, Szukaj z ich techniką i
  playlist z nich zrobionych.

## 1.109.2

- Nowa oś czasu w Szukaj → Epoka. Zamiast rzędu kafelków jest oś
  z podziałką i dwoma koralikami: przeciągnij koralik, żeby zmienić
  początek albo koniec, przesuń palcem po osi, żeby zaznaczyć kilka
  odcinków, stuknij odcinek, żeby wybrać tylko jego. Skrajne lata stoją
  pod koralikami. Nazwane okresy (Starożytność i Bizancjum, Europa,
  Polska, Japonia i Chiny) leżą na torach w tej samej skali, z nazwą obok,
  a jasny pas od osi w dół pokazuje, które z nich mieszczą się w wybranych
  latach; te poza nimi bledną. U góry karty zostaje sam wybór, np.
  „1600–1800” z szarym „XVII i XVIII wiek” obok, bez podpowiedzi.

## 1.109.1

- Pobieranie oryginałów Ulubionych i playlist w tle nie zatrzymuje się
  już na dobre, gdy jedno dzieło nie ma żadnego adresu zdjęcia albo jego
  pobranie kończy się nietypowym błędem. Wcześniej po takim dziele żadne
  kolejne nie było pobierane aż do restartu serwera (nocne pobieranie
  działało dalej).
- Testy serwera nie łączą się już z prawdziwymi muzeami i nie padają
  losowo przez wpisy w logu z innych testów.

## 1.109.0

- Odkrywaj → „Epoki” zaczynają się od starożytności i idą po kolei
  w czasie: Starożytny Egipt (malowidła z grobowców w Tebach), Portrety
  fajumskie, Freski Rzymu i Pompejów, Ikony Bizancjum i Złote tło (Duccio,
  Giotto), a dalej brakujące dotąd XV i XVI wiek, obie połowy XIX wieku
  i Międzywojnie. Strona grupy dzieli karty na „Starożytność i Bizancjum”
  oraz „Średniowiecze i dalej”. Karty antyku biorą tylko malarstwo: wazy,
  rzeźby, emalie i rękopisy zostają w swojej grupie.
- Nowa karta „Antyk oczami malarzy” w Tematach (Alma-Tadema, Gérôme,
  Siemiradzki, Hubert Robert, David). Motyw dnia 7 stycznia, 21 kwietnia
  i 4 listopada sięga po Bizancjum, Rzym i Egipt.
- Kurator Odkrywaj: dwie karty w „Dziś dla Ciebie” układa Claude, z myślą,
  której reguły nie wymyślą (np. portrety przez dwa tysiące lat). Karta
  zmienia się po tygodniu albo następnego dnia po tym, jak ją obejrzysz.
  Zamawiana nocą za pół ceny (ok. 0,40–2,70 USD miesięcznie), wyłączana
  w Konfiguracji → AI. Bez klucza Odkrywaj wygląda jak dotąd.

## 1.108.0

- Nowe źródło: J. Paul Getty Museum (Los Angeles), około 92 000 dzieł
  w domenie publicznej w pełnej rozdzielczości. Najwięcej daje dla
  Fotografii (XIX-wieczni mistrzowie: Talbot, Cameron, Le Gray, Nadar,
  Atget, Watkins; bez stereografii) i dla „Rękopisów i miniatur” (karty
  i miniatury iluminowanych rękopisów, np. Księgi godzinek), a do tego
  słynne obrazy i rysunki (m.in. „Irysy” Van Gogha). Zdjęcia i rękopisy
  nadal nie trafiają do katalogu, są szukane tylko w muzeach. Z „Użytkiem
  prywatnym” także dzieła spoza programu Open Content.

## 1.107.1

- Karta dzieła z muzeum, które nie podaje wymiarów zdjęcia (np. V&A,
  rękopisy i miniatury), nie zmniejsza już obrazu po sekundzie do małego
  znaczka na środku. Karta bierze kształt obrazu z kafelka, z którego ją
  otwarto, albo z pobranego zdjęcia, a gdyby go jeszcze nie znała, obraz
  wypełnia całe dostępne miejsce w swoich proporcjach.

## 1.107.0

- Nowy wygląd karty Szukaj → Technika: zamiast ośmiu kapsułek każda
  technika ma okrągłą miniaturę dzieła i nazwę pod spodem, po cztery
  w rzędzie. U góry Malarstwo, Grafika, Rysunki i akwarele oraz Plakaty,
  niżej pod napisem „Inne · dostępne wyłącznie po wybraniu” Rękopisy
  i miniatury, Fotografia, Rzeźba oraz Ceramika i rzemiosło. Wybrana
  technika ma otok jak kolory w karcie Kolor, a przycisk „Technika” nad
  polem wyszukiwania pokazuje małe kółka z dziełami wybranych technik.

## 1.106.0

- Nowe źródło zdjęć: Library of Congress. Pytamy je tylko wtedy, gdy w
  Szukaj (albo w playliście) wybierzesz Technika → Fotografia, więc nie
  spowalnia innych wyszukiwań i nie zapycha katalogu. Bez wpisanych słów
  losuje ze zbiorów znanych fotografów: kolorowe i czarno-białe zdjęcia
  FSA/OWI (Dorothea Lange, Walker Evans, Jack Delano), kolorowa Rosja
  Prokudina-Gorskiego, fotochromy z lat 1890–1910, szklane negatywy z wojny
  secesyjnej, Frances Benjamin Johnston i Lewis Hine. Wpisane słowa szukają
  we wszystkich jego zdjęciach. Bierzemy tylko zdjęcia bez ograniczeń
  praw („No known restrictions”), w pełnej rozdzielczości skanu, do
  2560 px. Z włączonym „Użytkiem prywatnym” także zdjęcia, których praw
  biblioteka nie sprawdziła albo które mogą być chronione (np. portrety
  Carla Van Vechtena, Edward S. Curtis), jeśli pokazuje je poza swoim
  budynkiem w dużym rozmiarze.

## 1.105.1

- Szukaj → Technika → „Rękopisy i miniatury” znowu coś znajduje. Katalog
  nie trzyma rękopisów, a muzea nie były o nie pytane, więc wynik był
  pusty. Teraz pytamy te, które umieją je wybrać: Met (rękopisy ze
  wszystkich działów, m.in. perskie i indyjskie), Rijksmuseum, V&A
  (wycięte karty i miniatury z kodeksów), Cleveland, Art Institute of
  Chicago i Smithsonian. Znalezione rękopisy nadal nie trafiają do
  katalogu ani do Propozycji.
- Muzea, które nie mają danej techniki (np. Yale czy Paris Musées
  rękopisów), nie podsuwają w jej miejsce malarstwa.

## 1.105.0

- Próba zmiany obrazu jednym odświeżeniem zamiast dwóch. Nowa paczka
  aplikacji ramki ma własny, przezroczysty ekran startu, który znika
  dopiero wtedy, gdy nowy obraz jest gotowy. Jeśli ramka go uwzględni,
  nie narysuje już granatowego ekranu ładowania przed obrazem. Paczka
  instaluje się po włączeniu ramki przyciskiem.
- Grupy w Szukaj wracają tym szybciej, im wolniej przesuwała się lista,
  gdy puszczasz palec: po powolnym przeciągnięciu już po ćwierć sekundy,
  po mocnym pociągnięciu jak dotąd po sekundzie, a pomiędzy płynnie.
  Tak samo w edytorze playlist.
- W Szukaj → Technika (i w edytorze playlist) „Obrazy” nazywają się teraz
  „Malarstwo”. Wybór działa tak samo: dzieła, które muzeum opisuje jako
  malarstwo (olej, tempera i podobne). Zapisane playlisty i wybory zostają.
- „Inni w tym samym czasie” w Studium dzieła pokazuje też dzieła z innych
  kręgów kulturowych: przy Europejczyku np. coś z Japonii, Chin, Indii
  czy Persji. Takie dzieła są dwa z dziesięciu, z dwóch różnych kręgów,
  i drugie w rzędzie widać od razu, bez przewijania. Gdy w katalogu nie
  ma nic z tych samych lat, szukamy do 25 lat obok (rok jest pod
  miniaturą).
- Szukaj → Epoka zaczyna się od starożytności. Na osi czasu przed
  średniowieczem jest odcinek „Starożytność” (do 500 roku), a
  średniowiecze to lata 500–1400. Dotąd dzieła starożytne, np. z Luwru,
  wpadały do średniowiecza.
- Nowa grupa okresów „Starożytność i Bizancjum”: Starożytny Egipt,
  Starożytna Grecja, Starożytny Rzym i Bizancjum. Lata przed naszą erą
  mają dopisek „p.n.e.”.

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
