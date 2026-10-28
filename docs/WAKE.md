# Budzenie ekranu na baterii

Problem z Etapu 0 (E8, 2026-10-24, firmware S-RSEDWWC-1130.7): po odpięciu
ładowarki ekran od razu znika z sieci (brak pinga i MDC). Wake-on-LAN przez
Wi-Fi go nie budzi, mimo że network standby (`0xB5`) był włączony. Pomaga
tylko krótkie naciśnięcie przycisku zasilania. Po wybudzeniu ekran nie pobrał
sam ponownie `content.json`.

Ten dokument zbiera, co wiadomo z sieci, możliwe rozwiązania i plan testu
na ekranie (E13).

## Co mówią źródła

1. **Budzik ekranu przez MDC `0x25` (on-timer).** Projekt
   [taylorRichie/node-samsung-emdx](https://github.com/taylorRichie/node-samsung-emdx)
   (EM32DX, firmware 1050.1) używa go produkcyjnie: przed uśpieniem ustawia
   budzik `[en, repeat, hh, mm, 01]`, wyłącza network standby i wyłącza ekran
   (`0x11 00`). Ekran budzi się sam o hh:mm według własnego zegara (`0xA7`).
   Serwer co 30 s próbuje połączyć się przez MDC, a gdy ekran się pojawi,
   wysyła obraz i po kilku minutach znowu go usypia. Budzik ma tylko godzinę
   i minutę, więc działa codziennie (repeat `02`), a dłuższe odstępy obsługują
   „puste” pobudki, po których serwer od razu usypia ekran. Kody repeat:
   `01` raz, `02` codziennie, `03` pn–pt, `04` pn–sb, `05` sb–nd. Zegar
   budzika jest lokalny: serwer musi liczyć w strefie czasowej ekranu.
   W [ha-emdx](https://github.com/johanneswilm/ha-emdx) (`switch.py`) autor
   pisze wprost: z głębokiego uśpienia budzi tylko przycisk „albo on-timer”.
   U nas `0x25` odpowiada `00`, czyli budzik istnieje i jest wyłączony.
2. **Zdalne budzenie wymaga Wi-Fi 2,4 GHz.** Instrukcja Samsunga
   (EM32DX / EM32DX-A, sekcja „Network Settings (Wireless)”): *„EM32DX-A
   models only: To enable remote wake-up via the mobile app, VXT, or a custom
   app, a 2.4GHz Wi-Fi network connection is required.”* Karta katalogowa
   EM32DX-A podaje **dwa moduły Wi-Fi (802.11n i 802.11ac)**. Najpewniej
   w uśpieniu działa tylko oszczędny moduł 2,4 GHz. Jeśli ekran jest
   połączony z siecią 5 GHz, w uśpieniu jest głuchy, niezależnie od network
   standby. Nie wiemy jeszcze, czy nasz egzemplarz to EM32DX czy EM32DX-A
   (etykieta: `LH32EMDIA…` to wersja A, `LH32EMDIB…` zwykła).
3. **Ustawienia w aplikacji Samsung E-Paper** (menu „Power and Energy
   Saving”): tryb uśpienia *Sleep mode / Deep sleep mode / Sleep mode off*
   oraz *Sleep After* (czas bezczynności przed uśpieniem). Instrukcja ostrzega,
   że zmiana zwiększa zużycie baterii, a włączony network standby może
   rozładować baterię bez ostrzeżenia. Samsung podaje do 500 dni pracy przy
   zmianie co 3 dni z network standby **wyłączonym**.
4. **Tryb Auto ekranu**: przytrzymanie przycisku Mode przełącza Manual/Auto.
   W trybie Auto ekran sam zmienia obrazy z pamięci wewnętrznej, domyślnie
   co 4 godziny. Ekran ma więc własny harmonogram, który działa bez sieci
   (sprawdza E6).
5. **API Tizen E-Paper** (`webapis.epaper.setScheduleWakeupTime`,
   `setAutoSleepTime`, `setNetworkStandby`) daje pełną kontrolę z własnej
   aplikacji (Custom App URL), ale wymaga przywileju **Partner**. To ta sama
   funkcja co budzik `0x25`, tylko trudniej dostępna.
6. Nikt nie zgłaszał publicznie (GitHub, fora) problemu „WoL nie działa na
   baterii”. Obie integracje testowano głównie na zasilaczu. W
   node-samsung-emdx zaobserwowano, że po wyłączeniu przez MDC ekran jest
   osiągalny jeszcze ok. 2 minuty.

## Możliwe rozwiązania

| | Rozwiązanie | Wykonalność | Bateria | Zmiana na żądanie | Uwagi |
|---|---|---|---|---|---|
| A | **Budzik `0x25` + spotkanie z serwerem** | wysoka (działa u innych na EM32DX) | najlepsza (network standby wył.) | nie, do najbliższej pobudki albo przycisku | Główna propozycja. Działa także między podsieciami, bo to serwer łączy się z ekranem przez MDC (TCP). |
| B | **Wi-Fi 2,4 GHz + network standby + WoL** | średnia (jeśli to EM32DX-A, Samsung to wspiera) | gorsza | tak | Magic packet z NAS (inna podsieć) nie dotrze broadcastem. Potrzebny nadawca w 192.168.1.x (router, HA, Mac) albo unicast przez router ze stałym wpisem ARP. |
| C | **Przycisk + serwer czekający na ekran** | wysoka | bez wpływu | tak, ręcznie | Uzupełnienie A: krótkie naciśnięcie budzi ekran, serwer to widzi i od razu wysyła zaległy obraz. |
| D | **Playlista w manifeście / tryb Auto** | nieznana (E6) | dobra | nie | Kilka obrazów naraz, ekran zmienia je sam, bez sieci. Uzupełnienie A przy rzadkich pobudkach. |
| E | Własna aplikacja Tizen (`setScheduleWakeupTime`) | **potwierdzona (E16)**, wymaga certyfikatu Samsunga Partner z DUID ramki | dobra | nie | Jedyny działający budzik na 1130.7, patrz [niżej](#aplikacja-custom-budzik-działa-e16-2026-10-28). |
| F | Stałe zasilanie (USB-C albo przejściówka PoE) | pewna | nie dotyczy | tak | Rezygnacja z baterii, kabel do ramki. |

**Rekomendacja:** A jako podstawa polityki zasilania (2.6 w planie), C dla
zmian na żądanie, a B sprawdzić jednym testem, bo jeśli ekran to EM32DX-A
w sieci 5 GHz, przeniesienie go na 2,4 GHz może przywrócić WoL. Polityka:

- na ładowarce: jak dziś, wysyłka od razu;
- na baterii: przed uśpieniem serwer ustawia budzik na najbliższą zmianę
  (np. 07:00), wyłącza network standby i usypia ekran. Zmiany z aplikacji
  czekają w kolejce do pobudki, a aplikacja pokazuje „zmieni się o 07:00
  albo po naciśnięciu przycisku na ramce”.

## Aplikacja Custom: budzik działa (E16, 2026-10-28)

Własna aplikacja Tizen w trybie **Custom** sama budzi ramkę na baterii.
Sprawdzone aplikacją testową WakeProbe ([scripts/wakeprobe](../scripts/wakeprobe/)),
firmware 1130.7, ramka na baterii, network standby wł.

**Instalacja (tryb Custom = SSSP URL Launcher):**

- W aplikacji Samsung E-Paper: Content source → Custom, adres aplikacji
  (np. `http://192.100.3.87:3000/app`), Time Out (sekundy, ustawiliśmy 300),
  przełącznik Developer mode. To samo da się ustawić przez MDC: `0xC7` z
  podkomendą `0x82` + URL (ASCII) i `0x81 01` (tryb Custom). **Zapis
  `0x81 01` od razu wyzwala instalację**; sama zmiana URL nie.
- Zwykła strona nie wystarczy. Ramka pobiera `<url>/sssp_config.xml`
  (`<widget><ver>…</ver><size>bajty wgt</size><widgetname>WakeProbe</widgetname></widget>`),
  a zaraz potem `<url>/<widgetname>.wgt`. Zapytania bez User-Agenta.
- Paczka musi być podpisana **certyfikatem Samsunga**. Podpis własny
  (W3C widget signing z własnym CA), sam podpis autora i paczka bez podpisu
  kończą się czarnym ekranem bez żadnego ruchu z aplikacji. Instalacja przez
  sdb pokazuje przyczynę: `install failed[118, -12], reason: Check
  certificate error : :Invalid certificate chain with certificate in
  signature.`
- Działa certyfikat z Tizen Studio 6.1 + Samsung Certificate Extension:
  Certificate Manager → Samsung → TV, poziom **Partner** (był do wyboru na
  zwykłym koncie Samsung), DUID ramki `RLCDMLZKZTZ5O` (z `sdb shell 0
  getduid`; `webapis.productinfo.getDuid()` zwraca inny, `HQTFRZQO3L36X`).
  Profil `frame` jest na Macu Mateusza (`~/SamsungCertificate/frame`),
  pakowanie: `tizen package -t wgt -s frame -- <katalog>`. Certyfikat
  pasuje tylko do tej ramki.
- `config.xml`: przywilej `http://developer.samsung.com/privilege/systemcontrol`,
  metadane `http://samsung.com/tv/metadata/application/epaper.support` =
  `true`, profil `tv-samsung`. Skrypt `$WEBAPIS/webapis/webapis.js`.
- Developer mode (w aplikacji Samsunga: IP komputera + restart ramki)
  otwiera sdb na `:26101`: `sdb connect`, `tizen install`, `tizen run`.
  Do pracy na co dzień niepotrzebny.

**API (`webapis.epaper.getVersion()` = `"1.0"`), sprawdzone wywołania:**

| Wywołanie | Wynik |
|---|---|
| `setScheduleWakeupTime({year, month, day, hour, minute, second})` | czas lokalny ramki (JS `Date`, strefa CET), zwraca liczbowy id (173, 175, …) |
| `getScheduleWakeupTime(id)` | ten sam obiekt `{day, hour, minute, month, second, year}` |
| `cancelScheduleWakeupTime(id)` | działa dla budzika ustawionego w tym samym okresie czuwania (potem `getScheduleWakeupTime(id)` → `UnknownError` 9999); dla id sprzed ostatniej pobudki zawsze `UnknownError` 9999 |
| `goToSleep()` | usypia ramkę; JS działa jeszcze 20–130 s, potem ramka znika z sieci |
| `isScheduledPlayBootReason()` | liczba: `0` po zwykłym starcie, `1` po pobudce z budzika; wartość „lepka”: zostaje `1` także po pobudce przez WoL i przy starcie aplikacji z sdb |
| `getAutoSleepTime()` | liczba minut (`20` przy „Sleep After” 00:20), nie napis z dokumentacji |
| `getNetworkStandby()` | `"ON"` |
| `getScreenRefreshTime()` | `{"hour": "3", "minute": "0"}` (napisy) |
| `getBatteryWarningIconDisplay()` | `"ON"` |

**Zachowanie:**

- Pobudki w ciągu kilku sekund od zadanej godziny: 00:49:01 (budzik
  00:49:11), 00:56:00 (00:56:02), ok. 00:59:05 (00:59:00), 01:02:01
  (01:02:09). Ramka wraca do sieci sama, bez przycisku i bez WoL.
- Po pobudce aplikacja jest **wznawiana**, a nie uruchamiana od nowa: timery
  JS stoją w czasie snu, `document.visibilityState` jest `visible`. Aplikacja
  musi sama wykryć wznowienie (np. przerwa w liczniku) i wtedy zapytać
  serwer, co pokazać.
- Ekran pokazuje to, co narysuje strona (biała strona z tekstem pojawiła się
  zaraz po starcie). Aplikacja może więc wyświetlać obraz sama.
- Przy usypianiu launcher czasem pobiera `sssp_config.xml` i paczkę
  ponownie, instaluje ją i uruchamia aplikację od nowa zamiast zasnąć
  (00:45:41 i 00:56:31; przy 00:49:00, 00:53:32 i 00:59:39 nie). Aplikacja
  musi to znosić: po starcie zawsze pyta serwer o stan i ustawia budzik od nowa.
- Budziki się sumują, a `cancelScheduleWakeupTime` nie działa: budzik
  ustawiony przed ponownym startem aplikacji nadal obudził ramkę (00:59).
  Aplikacja musi więc znosić pobudki „nie w porę”: zapytać serwer i od razu
  zasnąć.

**Sen płytki i pełny (testy nocne 2026-10-28, WakeProbe 1.3.x):**

- **Płytki sen** (`goToSleep()` przy network standby ON): aplikacja jest
  wznawiana. Pobudki z budzika 0–29 s przed czasem (01:39:00 dla 01:39:29).
  **WoL budzi natychmiast**: pierwsza seria postawiła ramkę po 2 s (w trybie
  Mobile z sieci potrzeba było 60–145 s).
- Budzik, który przypada, zanim ramka naprawdę zaśnie (JS działa jeszcze do
  ok. 130 s po `goToSleep()`), **przepada**: ramka zasypia i już się nie
  budzi. Budzik ustawiać co najmniej 3 min po `goToSleep()`.
- **Pełny sen** (`setNetworkStandby("OFF")`, potem `goToSleep()`): budzik
  budzi ramkę 3 razy na 3 (11–18 s przed czasem), Wi-Fi wraca po kilku
  sekundach. To jednak **zimny start**: aplikacja nie jest wznawiana, tylko
  startuje od nowa (`pageshow`, `focus`). Uruchomiła się sama tylko raz na
  trzy; w pozostałych launcher pobrał `sssp_config.xml` ok. 45 s po pobudce
  i aplikacji nie uruchomił (obserwowane przez 2–7 min). Wtedy MDC odpowiada,
  a `0xC7 81 01` uruchamia aplikację w ok. 10 s. Możliwe, że to skutek
  instalacji przez sdb w Developer mode (`isCustomAppDownloaded()` = `false`),
  do sprawdzenia przy czystej instalacji przez launcher.
- Network standby ustawiony przez aplikację zostaje po pobudce (`OFF`), więc
  po pełnym śnie aplikacja albo serwer (`0xB5 01`) musi go przywrócić.
- Bateria: od 92% (00:09) do 70% (02:18) przy ciągłych testach (ramka
  obudzona większość czasu, wiele odświeżeń ekranu).

**Obraz 1:1 z aplikacji: rozwiązane (wieczór 2026-10-28).** W `config.xml`:

```xml
<tizen:metadata key="http://tizen.org/metadata/app_ui_type/base_screen_resolution" value="always"/>
```

Z tym wpisem strona ma 2560×1440 (`innerWidth`, `screen`, `visualViewport`,
`devicePixelRatio` 1), a PNG 2560×1440 w `<img>` 2560×1440
(`image-rendering: pixelated`) jest pokazywany piksel w piksel: szachownica
1 px wygląda jak równa szarość, paski 1 px w sześciu farbach są ostre
(zdjęcie Mateusza). Wpis podpatrzony w metadanych VXT Playera
(`tizen.application.getAppMetaData("PbHvnmrROv.VXPlayer")`); wartość
`extensive` z dokumentacji Samsunga nic nie zmienia. Odświeżenie po
`img.onload` dalej trzeba wymusić zmianą stylu. Serwer może więc wysyłać
ten sam obraz 2560×1440 co w trybie Mobile (nasz dither albo passthrough).

**Zasady dla aplikacji ramki (wieczór 2026-10-28, Developer mode wył.):**

- Czasy: po jednej zmianie strony (podmiana `src` obrazu już pobranego
  i zdekodowanego) ekran zaczyna mrugać po ok. 10 s i mruga ok. 29 s, czyli
  ok. 40 s razem. Do paska postępu w iOS.
- Pobieranie: Wi-Fi przy ramce słabe (poziom 2, 2,4 GHz, kanał 6), XHR
  60–215 KB/s; `<img>` nałożony na odświeżanie jest 4–10× wolniejszy.
  Najpierw pełne pobranie przez XHR (postęp z `onprogress`), potem
  `FileReader.readAsDataURL` → `img.decode()` → jedna podmiana. Adresy `blob:`
  z pochodzenia `file://` nie działają (błąd obrazka). JPEG q95 4:4:4
  (ok. 1 MB) zamiast PNG 3–4 MB.
- Nie przełączać `visibility`: ekran potrafi zostać w stanie ukrytym.
- **Nie usypiać w trakcie odświeżania:** `goToSleep()` 14 s po zmianie przerwał
  odświeżanie (szaro-brązowy ekran) i budzik przepadł. Usypiać ≥45–60 s po
  ostatniej zmianie ekranu.
- **Pełny sen** (standby OFF) na ładowarce i na baterii: budzik zawsze budzi
  (zimny start), ale **launcher sam aplikacji nie uruchamia** (tylko 2 z 9
  zimnych startów). Także przy czystej instalacji przez launcher, bez
  Developer mode i z `<webtype>tizen</webtype>`: przy tej samej wersji
  launcher pobiera `sssp_config.xml` i stoi, przy 404 też. **Potrzebne:**
  serwer po planowanej pobudce czeka na raport aplikacji i po ok. 60 s ciszy
  wysyła MDC `0xC7 81 01` (start w ok. 10 s, 8 z 8). Aplikacja po starcie
  przywraca `setNetworkStandby("ON")`.
- **Z network standby wył. WoL nie budzi ramki**, tylko budzik albo przycisk.
- Instalacja przez launcher działa bez Developer mode (certyfikat Partner
  z DUID wystarcza); `isCustomAppDownloaded()` zawsze `false`.
  `sssp_config.xml`: `<widget><ver>1.7.1</ver><size>…</size><widgetname>WakeProbe</widgetname><webtype>tizen</webtype></widget>`.
- Aktualizacja bez klikania (sprawdzone 21:00): serwer podnosi `<ver>`
  w `sssp_config.xml` i wystawia nową paczkę, aplikacja woła
  `webapis.systemcontrol.rebootDevice()`, po restarcie launcher instaluje nową
  wersję (ale jej nie uruchamia), serwer wysyła `0xC7 81 01`.
- Po wyłączeniu i włączeniu ramka potrafi połączyć się z inną zapamiętaną
  siecią Wi-Fi (raz „Rocky IoT”, 192.168.3.151): wtedy serwer jej nie widzi.
  Aplikacja powinna raportować SSID i IP.
- Launcher sprawdza wersję także przy części wywołań `goToSleep()`; przy
  niezgodności przeinstalowuje i uruchamia aplikację (ekran instalacji).
  Serwer ma podawać tę wersję, która jest zainstalowana.
- Ramka nie ma czujników (akcelerometr, żyroskop, światło: brak), tylko
  mikrofon. Wi-Fi do odczytu: poziom sygnału, SSID, IP, częstotliwość.

**Wyświetlanie obrazu (rano 2026-10-28, przy ramce):**

- Wbudowanego odtwarzacza (Mobile, 1:1) nie da się łączyć z aplikacją:
  po wysyłce `0xC7 53 80` w trybie Custom na ekranie została strona
  aplikacji; `hide()` nie przerysowuje ekranu; po `exit()` launcher
  uruchamia aplikację ponownie w ok. 10 s, także po przełączeniu `0xC7 81`
  na `02` (Mobile). Wartości `0xC7 81`: `01` Custom, `02` Mobile, `00` czarny
  ekran. `avplay`/`epavplay` odrzucają PNG (`PLAYER_ERROR_NOT_SUPPORTED_FILE`).
- **Działa obraz rysowany przez aplikację:** JPEG 1920×1080 w `<img>` na
  cały ekran; ramka powiększa go do 2560×1440 i sama ditheruje (wygląd jak
  passthrough). Tekst czytelny od ok. 16 px, linie 2–4 px czyste, 1 px
  miękkie. Mateusz: „nie jest źle, ale na drobnych liniach 1px widać brak
  ostrości”.
- E-papier **nie** odświeża się sam po doczytaniu obrazka: po `img.onload`
  trzeba zmienić styl (np. `opacity` 0.99 i z powrotem 1 po 300 ms).
  `screenRefreshNow()` rzuca `UnknownError`.

**Pytania do aplikacji ramki (odpowiedzi):**

1. **Obraz 1:1: tak, z `base_screen_resolution` = `always`** (wyżej). Bez
   tego wpisu strona ma `screen` 1920×1080 i
   `devicePixelRatio` 1 (`tizen.systeminfo` DISPLAY też 1920×1080, a
   capability `screen.height` = 1440), panel ma 2560×1440, więc obraz ze strony
   jest skalowany ×4/3 i nasz dithering się rozjedzie. Strona odświeża ekran
   sama, bez `screenRefreshNow()`.
   `webapis.unipicture` (2.92) **nie działa**: `create()` → stan `INIT`,
   `setScalerType("MAIN"|"SUB")` ok, `setGeometry` zna `"FIT_SCREEN"` i
   `"ZOOM"`, `rotate` zna `"0"/"90"/"180"/"270"`, `setSlideShowEffect`
   `"WIPE"/"SPIRAL"/"CHECKER"/"LINEAR"/"RANDOM"`. `load(ścieżka)` (też
   `file://`) zwraca bez błędu, ale stan zostaje `INIT`, a `show()`,
   `setDisplayRect()` i `useSWDecoder()` dają `PICTURE_ERROR_INVALID_STATE`.
   `loadAsync()` po `create()` **wywraca aplikację** (restart co ok. 30 s),
   z adresem `http://` także (pliku nawet nie pobiera). Pozostaje
   `webapis.epavplay` (odtwarzacz e-papieru, `open(url)`, `setDisplayRect`,
   `setDisplayMethod`) i ustawienie rozdzielczości aplikacji; do sprawdzenia
   przy ekranie. Lokalny zapis pliku działa: `tizen.download.start(new
   tizen.DownloadRequest(url, "downloads", nazwa), {oncompleted})` →
   `/opt/usr/home/owner/content/Downloads/<nazwa>` (przywilej `download`).
2. **Sieć po pobudce:** z płytkiego snu XHR działa od pierwszego taktu po
   wznowieniu; po pełnym śnie raporty startu doszły ok. 20 s po powrocie
   pingu. Ponawiać zapytania.
3. **Wznowienie:** po pobudce z płytkiego snu nie przychodzi żadne zdarzenie
   (`visibilitychange`, `focus`, `pageshow`, `online` milczą); przy zasypianiu
   przychodzą `blur` i `visibilitychange` → `hidden` tylko wtedy, gdy launcher
   przeinstalowuje aplikację. Wznowienie wykrywać przerwą w `setInterval`.
4. **Bateria w aplikacji:** `webapis.deviced.getBatteryCapacity()` → `75`
   (zgodne z MDC `0x1B 73`), `getBatteryPowerSource()` → `"NO_CHARGER"`; są też
   `addBatteryCapacityListener` i `addChargingStatusListener`.
   `tizen.systeminfo.getPropertyValue("BATTERY")` zwraca błąd DBus, a po
   pobudce bywa, że nie odpowiada wcale (zawsze z limitem czasu).
5. **MDC i WoL w trybie Custom:** MDC działa przy działającej aplikacji, po
   płytkim i po pełnym śnie; WoL budzi z płytkiego snu w 2 s. `0xC7 81 01`
   uruchamia zainstalowaną aplikację. **`0xC7 53 80` (content.json) działa
   w trybie Custom** (02:38): ramka pobiera manifest i obraz, raportuje
   `Successful`, tryb zostaje Custom (`C7 81` → `01`), aplikacja działa dalej
   (widoczna, z fokusem, bez zdarzeń), a `goToSleep()` potem usypia ramkę.
   Czy na ekranie zostaje obraz 1:1, czy strona aplikacji: do sprawdzenia
   okiem (to podstawa wariantu hybrydowego: aplikacja budzi i usypia, obraz
   idzie przez MDC).
6. **Kod z serwera: działa.** `<script src="http://<serwer>/remote.js">`
   w podpisanym `index.html` ładuje się przy każdym starcie i ma pełny dostęp
   do `webapis`. Podpisana powłoka może być stała, a logika na serwerze
   (WakeProbe 1.3 ma tak zdalną konsolę JS).

**Inne moduły (odczyty z aplikacji, 2026-10-28):**

- `epaper`: diody `setLEDStateOn` (`LED_GREEN`, `LED_RED`, `LED_BLUE`),
  `setLEDStateBlink` (`LED_250MS`, `LED_500MS`, `LED_1000MS`) i `setLEDStateOff`
  przyjmują wywołania bez błędu (efektu nikt nie widział, w nocy).
  `setBatteryWarningIconDisplay("OFF"/"ON")`, `setAutoSleepTime("30MIN")` →
  `getAutoSleepTime()` = 30 i `setScreenRefreshTime({hour, minute})` działają;
  `resetAutoSleepTime()` nie zmienia wartości.
- `deviced`: bateria (wyżej).
- `productinfo`: `getRealModel()` `EM32DX`, `getModel()` `EMDX`,
  `getModelCode()` `24_ROSEE_LFD`, `getFirmware()`, `getDuid()`,
  `getLocalSet()` `EU`, `isDisplayRotatorSupported()` `true`.
- `systemcontrol` 1.5: `getSerialNumber()`, `getCustomAppInfo()` →
  `{connectionTimeout: "300SEC", downloadServerAddress: "<url>/app/"}`,
  `getButtonLock()` `OFF`, `getOnScreenMenuOrientation()` `LANDSCAPE`,
  `isCustomAppDownloaded()` `false`; są też `setCustomAppInfo`,
  `rebootDevice`, `captureScreen` (bez odpowiedzi w 30 s), `updateFirmware`,
  `setButtonLock`. Nieobsługiwane (`NotSupportedError`): lamp schedule,
  panel mute, safety lock, IR lock, auto power on, MagicInfo.
- `timer`: `getCurrentTime()` (czas lokalny), `getNTP()` →
  `{use: "OFF", timeZone: "Africa/Casablanca"}` (strefa w ustawieniach
  ramki jest dziwna, zegar mimo to pokazuje CET), `getDST()` mode `OFF`,
  `getSystemTimeSyncTimeout()` `30SEC`; on/off timer `NotSupportedError`.
- `remotepower`: wszystko `NotSupportedError`.
- `network`: `getActiveConnectionType()` `1` (Wi-Fi); z przywilejem
  `http://developer.samsung.com/privilege/network.public` także `getIp()`,
  `getMac()`, `getWiFiSignalStrengthLevel()` (3). `tizen.systeminfo`
  WIFI_NETWORK daje SSID, siłę sygnału (0,87) i IP.
- `0xC7 81 01` przy już wybranym Custom tylko uruchamia aplikację od nowa (też
  zawieszoną), nowej wersji nie pobiera, nawet po zmianie adresu `0xC7 82`.
  Launcher pobiera paczkę, gdy aplikacji nie ma, albo sam przy okazji
  (zasypianie, start), co kilkanaście minut.
- `tizen.systeminfo.getCapability("http://tizen.org/feature/screen.width")`
  = 1920, `screen.height` = 1440.
- Bez przywilejów: `avinfo` (jasność itp.), `widgetdata`, `drminfo`, `was`.

## Aplikacja Frame na ramce (2026-10-28)

Na podstawie E16. Ramka w trybie Custom uruchamia naszą aplikację, która sama
pyta serwer o obraz i sama ustawia budzik. Mateusz zdecydował 2026-10-28, że
Frame korzysta z trybu Custom.

**Pętla aplikacji** (`server/src/frame_server/web/panel_app/app.js`): przy
starcie i po każdym wznowieniu (przerwa w takcie 15 s dłuższa niż 45 s)
`GET /panel/next`, do 4 prób co 5 s. Odpowiedź:

- `sleep`: narysuj `image` (jeśli inny niż na ekranie), odczekaj 45 s na
  odświeżenie e-papieru, ustaw `setNetworkStandby(standby)` (tylko gdy inny),
  `setScheduleWakeupTime` na `wake_ms` (przeliczone na czas lokalny ramki
  jej własnym zegarem JS, więc strefa ramki, np. „Africa/Casablanca” z
  `getNTP`, nie przesuwa pobudki w czasie letnim; ten sam moment
  nie jest ustawiany drugi raz, bo budzików nie da się odwołać), zgłoś
  `sleep`, `goToSleep()`;
- `stay` (ładowarka albo „Obudź ramkę”): narysuj i zapytaj znowu za
  `wait_s` (20 s);
- `wait` (zmiana właśnie się przygotowuje, np. ramka obudziła się kilka sekund
  przed godziną zmiany): zapytaj znowu za 15 s, najwyżej 20 razy.

Bez serwera aplikacja śpi i próbuje znowu za 15, 30, 60… minut (najwyżej
6 h), a przy pierwszym starcie pisze na ekranie, z jakim serwerem nie może się
połączyć. Logikę ładuje z serwera (`/panel/app/app.js`) przy każdym starcie,
z kopią w paczce na wypadek braku sieci, więc zmiany w logice nie wymagają
nowego podpisu. Gdy serwer ma inną wersję logiki (`code`), aplikacja
przeładowuje się (najwyżej raz na 10 minut).

**Co odpowiada serwer** (`server/src/frame_server/panel_app.py`):

- pobudka: najbliższa zmiana (z uwzględnieniem przypięcia), w trybie
  Oszczędnym także „Sprawdzaj też co”; w trybie Online na baterii także
  początek ciszy nocnej, żeby wyłączyć Wi-Fi na noc. Najwyżej tydzień naprzód;
- network standby: `OFF` w trybie Oszczędnym i w ciszy nocnej, `ON` w dzień
  w trybie Online (WoL dostarcza wtedy zdjęcia z telefonu od razu);
- ładowarka (`webapis.deviced.getBatteryPowerSource()` inny niż
  `NO_CHARGER`; bez niego bateria z MDC `0x1B 73`, czytana przed odpowiedzią,
  gdy ostatni odczyt ma ponad 10 minut): `stay`;
- pobudka bliżej niż za 5 minut: `wait` aż do niej (budzik ustawiony, zanim
  ramka naprawdę zaśnie, przepada, E16);
- obraz zaległy (`pending_push`) idzie przy pobudce i zostaje do następnej
  zmiany, jak dotąd.

**Po pełnym śnie** (Wi-Fi wył.) ramka startuje na zimno i launcher nie zawsze
uruchamia aplikację (E16): gdy sprawdzi wersję na serwerze i znajdzie tę samą,
zatrzymuje się; gdy nie sprawdza albo znajdzie nowszą, aplikacja startuje
(Developer mode nie ma tu znaczenia). Dlatego `0xC7 81 01` z serwera jest
głównym sposobem, nie zapasowym (5 na 5 startów w 10 s). Gdy aplikacja nie
zapyta w 60 s od budzika, serwer
uruchamia ją przez MDC `0xC7 81 01`, potem co 2 minuty, aż do uznania pobudki
za nieudaną (15 minut). Network standby ustawia aplikacja przed każdym snem.

**Obraz w aplikacji: 1:1, ten sam co w trybie Mobile.** Paczka ma w
`config.xml` `base_screen_resolution` = `always`, więc strona ma 2560×1440
(wieczór 2026-10-28). `/panel/next` podaje ten sam obraz `/panel/images/…`,
który ramka pobiera w trybie Mobile (passthrough z kalibracją, więc ramka
dituje go sama, albo nasz dither, zależnie od ustawień), a aplikacja pokazuje
go w `<img>` 2560×1440 z `image-rendering: pixelated`. Starsza paczka (strona
1920×1080) dostaje ten sam obraz pomniejszony do strony, dopóki z Maca nie
przyjdzie nowa (`pack.sh`; launcher pobiera ją po zimnym starcie). Wcześniej
(add-on 0.24.1) serwer podawał osobną kopię 1920×1080 w pełnym kolorze; 1 px
był miękki. E-papier nie odświeża się sam po wczytaniu obrazka, a
`screenRefreshNow()` rzuca błąd: aplikacja po `onload` zmienia `opacity` na
0,99 i po 300 ms z powrotem na 1.

**Pobieranie i pasek postępu (pomiary wieczorem 2026-10-28).** Wi-Fi ramki
jest słabe (sygnał 2/5, 2,4 GHz, 60–215 KB/s), a `<img>` pobierany w trakcie
odświeżania szedł 4–10× wolniej. Dlatego pełnokolorowy obraz (passthrough)
idzie do aplikacji jako JPEG q95 (`/panel/app-images/<id>.jpg`, ok. 1 MB
zamiast 3–4 MB PNG, różnicy nie widać); obraz z naszym ditheringiem (najwyżej
16 kolorów) zostaje bezstratnym PNG. Aplikacja pobiera cały plik przez XHR,
co 2 s zgłasza postęp (`/panel/report`, `progress`), a dopiero potem podmienia
obraz na stronie i zgłasza `shown`. Pasek w aplikacji iOS liczy z tego czas
pobierania, a odświeżanie (ok. 10 s przygotowania + ok. 30 s zmiany ekranu)
zaczyna od `shown`. Zmiana stylu o jeden piksel niezawodnie wymusza
odświeżenie; ukrycie i pokazanie na 1,5 s raz złapało pusty (biały) ekran.
Launcher po cichu instaluje każdą paczkę wskazaną w `sssp_config.xml` (sprawdza
wersję przy usypianiu, potem przeinstalowuje i przerysowuje ekran), więc
serwer musi zawsze podawać tę zainstalowaną; inną wersję zgłasza w logu.

**Kolejność przed snem.** `goToSleep()` nie czeka na trwające odświeżanie:
sen w jego trakcie zostawił pół narysowany szary ekran i zgubił budzik (E16).
Aplikacja pokazuje obraz, czeka 60 s od ostatniej zmiany ekranu (obraz albo
komunikat), dopiero wtedy ustawia network standby i budzik i zasypia. Gdy
przez długie pobieranie do pobudki zostały mniej niż 2 minuty, pyta serwer
od nowa zamiast zasypiać.

**Instalacja i aktualizacje aplikacji.** Pierwsza instalacja: Konfiguracja →
Aplikacja ramki → „Przełącz na aplikację Frame” (serwer wysyła `0xC7 82
<adres>/panel/app` i `0xC7 81 01`, launcher od razu instaluje). Logika
(`app.js`) przychodzi z serwera przy każdym starcie, więc zwykłe zmiany nie
wymagają nowej paczki. Nowa paczka tylko przy zmianie `config.xml` albo
`index.html`: `scripts/panel-app/pack.sh WERSJA --upload <token>` na Macu
(podpis tylko tam) i dalej samo: serwer podaje nową `<ver>` w
`sssp_config.xml`, a gdy aplikacja zapyta z inną wersją, odpowiada `reboot`.
Aplikacja woła `webapis.systemcontrol.rebootDevice()`, launcher po restarcie
instaluje nową wersję, ale jej nie uruchamia, więc serwer po 60 s ciszy
wysyła `0xC7 81 01` (sprawdzone 2026-10-28 21:00). Restart najwyżej raz na
wersję, żeby paczka, która się nie instaluje, nie restartowała ramki w kółko.

**Wysyłka z aplikacji iOS** w trybie aplikacji: bez `0xC7`. Aplikacja
obudzona (ładowarka) pobiera obraz przy najbliższym pytaniu; uśpiona z Wi-Fi
dostaje serię WoL (do 3 min) i pyta po wznowieniu; w głębokim śnie albo gdy
WoL zawiedzie obraz czeka do pobudki, a „Teraz” pokazuje jej godzinę. Gdy
budzik ramki dzwoni w ciągu 3 minut (zmiana z harmonogramu), serwer nie
budzi jej przez WoL, tylko czeka.

**Instalacja (raz, na Macu z profilem `frame`):**

1. Serwer z tą zmianą na Synology (Projekt → frame → Kompiluj).
2. `scripts/panel-app/pack.sh 1.0.0 --upload <token API>`: buduje, podpisuje
   i wysyła paczkę na serwer (`PUT /api/device/app/package`), adres serwera
   domyślnie `http://192.100.3.185:8099` (`--server` zmienia). Ten adres
   trafia do paczki (`config.js`).
3. W aplikacji: Konfiguracja → Aplikacja ramki → „Przełącz na aplikację
   Frame”. Serwer zapamiętuje dotychczasowe źródło (`0xC7 81`), ustawia
   `0xC7 82 http://192.100.3.185:8099/panel/app` i `0xC7 81 01`; ramka od
   razu instaluje paczkę. „Wróć do zwykłego trybu” ustawia poprzednie źródło
   i wysyła obraz przez `0xC7 53 80`. Pobranie `content.json` przez ramkę
   też oznacza dla serwera, że aplikacja już nie działa.

Gdy ramka działa w aplikacji, w Harmonogramie wraca przełącznik „Tryb pracy”
(Online / Oszczędny), a ostrzeżenie o odrzuconym budziku znika.

**Do sprawdzenia na ramce:** sposób na obraz 1:1 (wyżej), czy logika ładuje się z serwera
(`code` w raportach inny niż `local`), czy budzik budzi przy network standby
`OFF`, czy WoL wznawia aplikację w trybie Custom, jak aplikacja zachowuje się
na ładowarce (czy „Sleep After” jej nie usypia).

## Polityka zasilania (wdrożona, `server/src/frame_server/power.py`)

2026-10-25: ekran był połączony z siecią 5 GHz, co najpewniej tłumaczy wynik
E8. Zakładamy przejście na 2,4 GHz. Mateusz ustalił zasadę:

- **w dzień** zdjęcie z aplikacji trafia na ramkę od razu: ekran śpi
  z włączonym network standby, a serwer budzi go Wake-on-LAN (seria
  pakietów przez 15 s, broadcast i unicast);
- **w ciszy nocnej** ekran na baterii śpi całkowicie: serwer ustawia budzik `0x25`
  na koniec ciszy (codziennie), wyłącza network standby i wyłącza ekran.
  Cisza zaczyna się o godzinie ustawionej w aplikacji i trwa do najbliższej
  godziny zmiany obrazu, więc budzik budzi ekran na poranną zmianę;
- **po pobudce** (budzik albo przycisk) serwer przez 15 minut od porannej
  zmiany co 15 s sprawdza, czy ekran jest w sieci. Gdy go znajdzie, włącza
  z powrotem network standby i wysyła obraz, który czekał;
- obraz, który nie dotarł (ekran śpi albo nie odpowiada), czeka jako
  „zaległy” (`pending_push`). Rotacja wstrzymuje się do jego dostarczenia,
  a po dostarczeniu zostaje do następnej zmiany. Poza oknem pobudki serwer
  co 2 minuty sprawdza, czy ktoś nie obudził ekranu przyciskiem;
- budzik jest ustawiony na stałe (codziennie), także w dzień, więc nawet
  gdy WoL zawiedzie, ekran wróci najpóźniej rano. Bez ciszy nocnej budzik
  dzwoni na pierwszą zmianę dnia;
- **jeden harmonogram przy ładowarce i na baterii** (polecenie Mateusza,
  2026-10-25): te same godziny zmiany. Różni się tylko noc: głęboki sen
  dotyczy wyłącznie baterii, a na ładowarce zdjęcia trafiają na ekran od
  razu także w ciszy nocnej. Zmiana wypadająca dokładnie na początek ciszy
  idzie na ekran, zanim ten zaśnie.

Uwaga sieciowa: serwer na Synology (192.100.3.185) jest w innej podsieci niż
ekran. Broadcast stamtąd do 192.168.1.x nie dotrze, dociera tylko kopia
unicast przez router, a router musi znać adres MAC ekranu (wpis ARP). Jeśli
po przejściu na 2,4 GHz WoL działa z Maca, a z Synology nie, potrzebny jest
stały wpis ARP (albo rezerwacja DHCP z ARP) w routerze dla 192.168.1.152.

Do sprawdzenia w E13: czy budzik budzi ekran przy wyłączonym network
standby, jak długo ekran zostaje w sieci po pobudce, czy WoL na 2,4 GHz
działa na baterii.

## Diagnoza 2026-10-26: budzenie nie działa mimo Wi-Fi 2,4 GHz

Ekran jest już w sieci 2,4 GHz, a „Obudź ramkę” nadal go nie budzi. Trzy
możliwe przyczyny, od najbardziej prawdopodobnej:

1. **Pakiet nie dociera z Synology.** Serwer (192.100.3.185) wysyła magic
   packet trzy razy: na 255.255.255.255 (zostaje w sieci NAS-a), na
   192.168.1.255 (broadcast skierowany: domowe routery zwykle go odrzucają)
   i na 192.168.1.152 (unicast przez router). Unicast dociera tylko wtedy,
   gdy router zna jeszcze adres MAC ekranu. Wpis ARP wygasa po kilku
   minutach od zaśnięcia, a śpiący ekran może nie odpowiadać na zapytania
   ARP. Wtedy router po cichu wyrzuca pakiet. Rozwiązania: stały wpis ARP
   (powiązanie IP–MAC) dla 192.168.1.152 w routerze, funkcja WoL w samym
   routerze, albo serwer z nogą w sieci 192.168.1.x (np. drugi port LAN
   NAS-a; z `network_mode: host` broadcast na 192.168.1.255 wyjdzie wtedy
   prosto do tej sieci, bez zmian w kodzie).
   U nas router to UniFi Dream Machine Pro: nie ma w panelu stałych wpisów
   ARP (przez SSH da się je dodać, ale znikają po restarcie i aktualizacji),
   więc zalecana droga to drugi port LAN Synology RS1619xs+ w sieci
   ekranu (DHCP, brama domyślna zostaje na LAN 1).
   **Wybrane 2026-10-26:** osobny SSID w sieci NAS-a, ekran ma adres
   192.100.3.151, czyli jest w tej samej podsieci co serwer. Do sprawdzenia
   w UniFi: SSID tylko 2,4 GHz, „Multicast and Broadcast Control” wyłączone,
   MAC w aplikacji = MAC, który UniFi pokazuje przy ekranie (moduł 2,4 GHz
   może mieć inny adres).
2. **Network standby został wyłączony na noc i nie wrócił.** Na baterii
   w ciszy nocnej serwer wyłącza network standby (głęboki sen). Włączał go
   z powrotem tylko wtedy, gdy znalazł ekran w oknie porannej pobudki albo
   gdy czekał zaległy obraz. Jeśli budzik `0x25` nie zadziałał (E13 jeszcze
   niezrobione) albo ekran obudzono przyciskiem w innej porze, network
   standby zostawał wyłączony przez cały dzień i WoL nie miał szans.
   **Poprawione:** po nocy (i zawsze, gdy sprawdzenie stanu znajdzie
   network standby wyłączony) serwer co 2 minuty szuka ekranu, aż włączy
   go z powrotem.
3. **Ekran na baterii w ogóle nie słucha WoL**, także na 2,4 GHz (jeśli to
   nie wersja EM32DX-A). To rozstrzyga test z Maca w tej samej sieci
   (E13, krok 5): jeśli z Maca budzi, a z Synology nie, przyczyną jest
   punkt 1.

Do tego „Obudź ramkę” w aplikacji wysyłało tylko trzy pakiety w 0,4 s i od
razu meldowało „wysłano”. Teraz serwer wysyła pakiety przez 15 s, przez
30 s sprawdza, czy ekran odpowiada, i aplikacja pokazuje wynik: obudziła
się, nie odpowiada, albo jest w głębokim śnie do godziny budzika (wtedy
pomaga tylko przycisk). Po udanej pobudce serwer od razu włącza network
standby i wysyła zaległy obraz.

Kiedy serwer usypia ekran (2026-10-26): **w ciszy nocnej na baterii**
głęboki sen (budzik na poranną zmianę, network standby wył., ekran wył.),
a **w dzień na baterii lekki sen po każdym obrazie**: 90 s po pobraniu
(ok. 12 s przygotowania i 31 s odświeżania, E2) network standby wł. i ekran
wył. Kolejny obraz w tym czasie odwołuje usypianie. Przycisk „Uśpij ramkę”
w aplikacji daje ten sam lekki sen.

Poprawki z 2026-10-26 (po 0.12.0):
- Na ładowarce serwer usypia ekran po obrazie tylko wtedy, gdy ekran spał
  przed wysyłką (uśpiony z aplikacji albo obudzony dla tego obrazu). Ekran
  obudzony przez „Sprawdź stan” wraca do lekkiego snu po 60 s także na
  ładowarce. Ekran, który nie spał, na ładowarce zostaje włączony.
- Przed usypianiem po obrazie serwer czyta baterię na nowo. Ekran odpięty od
  ładowarki od razu znika z sieci, więc ostatni odczyt mógł jeszcze mówić
  „zasilacz” i serwer zostawiał wtedy obudzony ekran na baterii.
- Uśpiony przez MDC ekran odpowiada jeszcze przez ok. 2 minuty
  (node-samsung-emdx). Przez 3 minuty po uśpieniu sprawdzanie stanu nie
  łączy się z ekranem (sesja mogłaby go trzymać w gotowości) i pokazuje
  „czuwanie”. Wcześniej pierwsze odświeżenie po „Uśpij ramkę” widziało
  odpowiedź i pokazywało „Online”. Budzenie i wysyłka obrazu łączą się
  normalnie.
- Do sprawdzenia na urządzeniu: czy na ładowarce wyłączony przez MDC ekran
  nadal odpowiada na MDC po tych 3 minutach. Jeśli tak, aplikacja pokaże
  wtedy „Online”, bo ekran faktycznie odpowiada.

„Sprawdź stan” w aplikacji (2026-10-26): gdy ekran nie odpowiada, aplikacja
od razu próbuje go obudzić tak samo jak „Obudź ramkę”. Na baterii ekran
obudzony tylko po to wraca po 60 s do lekkiego snu, chyba że w tym czasie
coś zostanie na niego wysłane. W głębokim śnie nic nie jest wysyłane,
aplikacja tylko mówi, kiedy zadzwoni budzik. Kafelek „Sieć” pokazuje, co
ekran robi według serwera: **online** (odpowiada przez MDC), **czuwanie**
(śpi z network standby, WoL powinien go obudzić), **głęboki sen** (Wi-Fi
wyłączone na noc albo network standby nie wrócił: budzi tylko budzik lub
przycisk), **nie odpowiada** (serwer nigdy go nie widział albo nie wie,
dlaczego milczy). Śpiący ekran nie odpowiada na MDC, więc czuwanie i głęboki
sen serwer wnioskuje z tego, co sam zrobił i co zobaczył przy ostatnim
kontakcie.

## Prawdziwa przyczyna (2026-10-26): serwer w ogóle nie wysyłał pakietów

Ekran na baterii, Wi-Fi 2,4 GHz, ta sama podsieć co serwer: aplikacja WoL
na iPhonie (LAN Broadcast, maska 255.255.255.0, port UDP 7) **budzi ekran**,
a „Obudź ramkę” z serwera nie. Powód: uvicorn uruchamia serwer na pętli
uvloop (instaluje ją `uvicorn[standard]`), a uvloop nie ma
`loop.sock_sendto`, więc każda próba wysłania magic packetu kończyła się
`NotImplementedError` jeszcze przed pierwszym pakietem. Testy tego nie
łapały, bo działają na zwykłej pętli asyncio, a komenda `frame device wake`
też. Poprawka: zwykłe `sendto` (datagram nie czeka) i test na uvloop.

## Tryb Oszczędny

2026-10-27, prośba Mateusza: tryb pracy wybierany w Ramka → Harmonogram,
„Online” (jak dotąd) albo „Oszczędny” (`power_mode: economy`). Cel: dużo
dłuższa praca na baterii przy np. dwóch zmianach dziennie.

Co pozwala ekran (EMDX 224B, firmware 1130.7):

- **Ekran sam nie pyta serwera o nowe obrazy.** Fabryczne oprogramowanie
  pobiera `content.json` tylko na polecenie MDC `0xC7` (E7; projekt
  [samsung-epaper-calendar](https://github.com/Here-Be-Dragons/samsung-epaper-calendar)
  przez 3 h nie widział żadnego zapytania). „Pobieranie przez ramkę” to więc
  budzik `0x25`, a po pobudce serwer zauważa ekran i wysyła obraz. Serwer
  musi działać o godzinie pobudki.
- **Jeden budzik naraz** (godzina i minuta, raz albo codziennie). Serwer
  ustawia go przy każdym usypianiu na następną pobudkę, z powtarzaniem
  codziennym: gdy pobudka się nie uda, ekran wstanie następnego dnia o tej
  samej porze.
- **W głębokim śnie WoL nie działa** (network standby wył.). Wcześniej
  pomaga tylko przycisk na ramce; serwer szuka ekranu co 2 minuty.
- Bateria: samsung-epaper-calendar zmierzył 1,5–2% na godzinę w uśpieniu
  z network standby (ok. 4%/h obudzony). Samsung podaje do ok. 200 dni przy
  jednej zmianie dziennie. Własny pomiar do zrobienia.
- **Budzika nie da się ustawić przez MDC (E13, 2026-10-27, firmware
  1130.7).** Każdy zapis `0x25` w formacie `[en, repeat, hh, mm, 01]` (także
  w innych długościach i z AM/PM) kończy się NAK `01`. `0x25` przyjmuje
  tylko jeden bajt `00–05` i tyle samo zwraca przy odczycie, bez godziny.
  Serwer więc nigdy nie ustawił budzika, także dla ciszy nocnej. Aplikacja
  Samsung E-Paper też nie ma pobudki według zegara (tylko tryb uśpienia,
  „Sleep After” 20 min i „uśpij po aktualizacji treści”). **Ramka nie umie
  więc obudzić się sama**; na baterii budzi ją tylko WoL albo przycisk.
  Przełącznik „Tryb pracy” jest w aplikacji ukryty (kod zostaje). Serwer
  po odmowie (`alarm_refused`) nie wyłącza Wi-Fi: ani w nocy, ani w trybie
  Oszczędnym, który działa wtedy jak Online, a aplikacja to mówi. Próbuje
  ponownie raz na dobę.

Jak działa (`power.py`, `PowerManager.enter_deep` i `_economy_tick`):

- **Pobudki** = godziny zmiany, a z „Sprawdzaj też co” (2, 3, 4 albo 6 h)
  także krótkie pobudki między pierwszą a ostatnią zmianą dnia (przy jednej
  zmianie: przez 12 h po niej), `schedule.check_times`. W nocy nic nie budzi
  ekranu, dlatego w tym trybie nie ma ciszy nocnej.
- **Po każdym obrazie** (90 s na pobranie i odświeżenie) serwer czyta
  baterię, ustawia budzik na najbliższą pobudkę, wyłącza network standby
  i ekran. Na ładowarce nic z tego: działa jak „Online”.
- **Obraz z aplikacji** w czasie snu czeka jako zaległy (`pending_push`),
  a „Teraz” pokazuje „Pojawi się dziś o 19:00 · za 6 h 12 min”
  (`Delivery.asleep_until_at`).
- **Pobudka:** od minuty przed jej godziną przez 15 minut serwer co 15 s
  szuka ekranu. Gdy go znajdzie, wysyła zaległy obraz; zmiana z playlisty
  wypadająca w tej chwili idzie zwykłą drogą; pobudka bez niczego do pokazania
  od razu usypia ekran, bez odświeżania.
- **Pobudka nieudana** (ekran się nie zgłosił w 15 minut): serwer zapisuje
  ją (`missed_wake_at`), „Teraz” mówi „Ramka nie obudziła się o 19:00”
  i czeka na tę samą godzinę następnego dnia (budzik codzienny), a w
  międzyczasie co 2 minuty sprawdza, czy ktoś nie nacisnął przycisku.
- Zalecenie: w aplikacji Samsung E-Paper ustawić „Sleep After” na kilka
  minut, żeby ekran obudzony budzikiem nie został włączony, gdy serwer nie
  odpowie.

Pomiary z 27.10 (E13, Mac w podsieci ekranu, bateria, network standby wł.):
WoL przez Wi-Fi budzi ekran, ale MDC odpowiada dopiero po 60 s do 2,5 min
nadawania pakietu co sekundę. Serwer nadaje więc do 3 minut i przestaje,
gdy ekran odpowie („Obudź ramkę” szuka ekranu 190 s, wysyłka obrazu łączy
się co 5 s w trakcie nadawania). Uśpiony
przez MDC ekran znika z sieci po ok. 20 s, a obudzony przez WoL sam zasypia
po ok. 3 min 10 s.

## E13: plan testu na ekranie

Potrzebny Mac w tej samej sieci co ekran (192.168.1.x) i gałąź z komendą
`frame device timer`. Każdy krok zapisuje godziny i obserwacje.

W osobnym oknie terminala dziennik dostępności ekranu (co 5 s):

```bash
while true; do
  if ping -c1 -t1 192.168.1.152 >/dev/null 2>&1; then s=UP; else s=down; fi
  echo "$(date +%T) $s"; sleep 5
done | tee wake.log
```

0. **Rozpoznanie.** Model z etykiety na tylnej obudowie (`LH32EMDIA…` czy
   `LH32EMDIB…`) i `uv run frame device raw 0x10`. W routerze: z którym
   pasmem (2,4 czy 5 GHz) jest połączony ekran. W aplikacji Samsung E-Paper:
   wartości *Sleep mode* i *Sleep After* (zrzut ekranu).
1. **Budzik, network standby wł.** Na ładowarce:
   `uv run frame device timer HH:MM` (za 5 minut, domyślnie raz). Odczyt
   powinien pokazać `enabled=True` i tę godzinę. Odepnij ładowarkę. Czy o HH:MM
   w `wake.log` pojawia się `UP`? Jak długo ekran zostaje w sieci? Czy pobiera
   sam `content.json` (`data/panel-requests.jsonl`)? Gdy jest w sieci:
   `uv run frame device info` i wysyłka obrazu.
2. **Budzik, network standby wył.** Jak w 1, ale przed odpięciem
   `uv run frame device standby false`. To docelowy, najoszczędniejszy tryb.
3. **Ponowne uśpienie.** Po pobudce z kroku 2: wysyłka obrazu, potem
   `uv run frame device sleep`. Po ilu sekundach ekran znika z sieci?
4. **Budzik codzienny** (w ramach testów 24 h): `--repeat daily` na rano.
   Czy budzi się dwa dni z rzędu bez ponownego ustawiania?
5. **Wi-Fi 2,4 GHz.** Jeśli ekran był w 5 GHz: połącz go z siecią
   2,4 GHz (osobna nazwa sieci albo wyłączony band steering), włącz network
   standby, odepnij ładowarkę, odczekaj 2 minuty i
   `uv run frame device wake --seconds 60` (magic packet co sekundę przez
   minutę, broadcast i unicast). Sprawdź też, czy aplikacja Samsung E-Paper
   potrafi zmienić obraz na uśpionym ekranie na baterii.
6. **Przycisk.** Krótkie naciśnięcie na baterii: po ilu sekundach `UP`,
   jak długo ekran zostaje w sieci?
7. **Ładowarka jako budzik.** Uśpiony ekran na baterii: podłącz ładowarkę.
   Czy wraca do sieci bez przycisku?

Wyniki trafiają do tabeli w [EXPERIMENTS.md](EXPERIMENTS.md) (wiersz E13)
i do tabeli komend w [DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md).

## Wynik E13 (2026-10-27)

- **Budzik `0x25` nie działa** na firmware 1130.7: przyjmuje tylko jeden bajt
  `00`–`05`, a zapis z godziną kończy się NAK. Aplikacja Samsung E-Paper też
  nie ma godziny pobudki. Część polityki „w ciszy nocnej” oparta na budziku
  w tej formie nie zadziała.
- **WoL na baterii działa** przy network standby wł. i Wi-Fi 2,4 GHz, ale
  potrzebuje długiej serii: ekran wstał po ok. 60 s i ok. 145 s nadawania
  co 1 s. Seria 15 s jest za krótka. Na hoście z dwoma interfejsami
  255.255.255.255 wychodzi trasą domyślną, więc ważny jest broadcast
  skierowany na podsieć ekranu.
- **WoL na baterii bywa zawodny:** w trzeciej próbie (E6, 23:3x) 4 minuty
  nadawania nie obudziły ekranu. Aplikacja przy nieudanym budzeniu i przy
  obrazie czekającym na ramkę podpowiada krótkie naciśnięcie przycisku.
- Po pobudce ekran sam zasypia po ok. 3 min bezczynności, po `0x11 00`
  znika z sieci po ok. 20 s.
- E6: wpisy `schedule` / `start_time` w manifeście ekran pobiera z góry
  i po pobudce sam wybiera obowiązujący wpis, ale **nie budzi się** o jego
  godzinie.
- Dokument Samsunga „E-Paper Setup & Web API's Guide” opisuje tryb
  **Custom** (Custom App URL w aplikacji Samsung E-Paper, aplikacja Tizen
  hostowana np. przez nasz serwer) z API `webapis.epaper`:
  `setScheduleWakeupTime({year, month, day, hour, minute, second})` (do
  604800 s naprzód, zwraca id), `getScheduleWakeupTime(id)`,
  `cancelScheduleWakeupTime(id)`, `goToSleep()`, `setAutoSleepTime("30MIN")`,
  `setNetworkStandby("ON")`, `isScheduledPlayBootReason()`. Aplikacja musi
  mieć w `config.xml` metadane
  `http://samsung.com/tv/metadata/application/epaper.support` = `true`
  i `sssp_config.xml` z polem `size`. Wymagane uprawnienia nie są znane;
  sprawdzi to osobny test aplikacji Custom.

## Źródła

- [Instrukcja EM32DX / EM32DX-A / EM13DX (PDF)](https://media.displaynd.de/media/65/77/76/1775570009/Samsung-EM32DX-A-Benutzerhandbuch.pdf?ts=1775570009): Wi-Fi 2,4 GHz do zdalnego budzenia, Power and Energy Saving, tryb Auto.
- [Karta katalogowa EM32DX-A (Bechtle)](https://media.bechtle.com/asrc/180712/1c4b3d4ee288fc9434f5175bf56070570/c3/-/c5e245e44555491b94d7ac1848dd34e3/samsung-em32dx-a-e-paper-display-datenblatt-1): dwa moduły Wi-Fi.
- [taylorRichie/node-samsung-emdx](https://github.com/taylorRichie/node-samsung-emdx): `docs/MDC-COMMANDS.md` (`0x25`), `web/server.mjs` (budzik, poller, ponowne usypianie).
- [johanneswilm/ha-emdx](https://github.com/johanneswilm/ha-emdx): network standby, deep sleep, budzenie.
- [Samsung Epaper API (Tizen)](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/epaper-api.html?device=signage): `setScheduleWakeupTime`, przywilej Partner.
- [Domino Display: konfiguracja E-Paper (PDF)](https://www.dominodisplay.com/media/catalog/attribute-data/Sch_EPaper_SetUp.pdf): Sleep Time, Network Standby, Custom App URL.
