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
| E | Własna aplikacja Tizen (`setScheduleWakeupTime`) | niska (przywilej Partner) | dobra | nie | Daje to samo co A. |
| F | Stałe zasilanie (USB-C albo przejściówka PoE) | pewna | nie dotyczy | tak | Rezygnacja z baterii, kabel do ramki. |

**Rekomendacja:** A jako podstawa polityki zasilania (2.6 w planie), C dla
zmian na żądanie, a B sprawdzić jednym testem, bo jeśli ekran to EM32DX-A
w sieci 5 GHz, przeniesienie go na 2,4 GHz może przywrócić WoL. Polityka:

- na ładowarce: jak dziś, wysyłka od razu;
- na baterii: przed uśpieniem serwer ustawia budzik na najbliższą zmianę
  (np. 07:00), wyłącza network standby i usypia ekran. Zmiany z aplikacji
  czekają w kolejce do pobudki, a aplikacja pokazuje „zmieni się o 07:00
  albo po naciśnięciu przycisku na ramce”.

## Polityka zasilania (wdrożona, `server/src/frame_server/power.py`)

2026-10-25: ekran był połączony z siecią 5 GHz, co najpewniej tłumaczy wynik
E8. Zakładamy przejście na 2,4 GHz. Mateusz ustalił zasadę:

- **w dzień** zdjęcie z aplikacji trafia na ramkę od razu: ekran śpi
  z włączonym network standby, a serwer budzi go Wake-on-LAN (seria
  pakietów przez 15 s, broadcast i unicast);
- **w ciszy nocnej** ekran śpi całkowicie: serwer ustawia budzik `0x25`
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
- **ta sama polityka przy ładowarce i na baterii** (polecenie Mateusza,
  2026-10-25): jeden zestaw ustawień, a w nocy także ekran na ładowarce
  śpi do porannej zmiany. Zmiana wypadająca dokładnie na początek ciszy
  idzie na ekran, zanim ten zaśnie.

Uwaga sieciowa: serwer na Synology (192.100.3.185) jest w innej podsieci niż
ekran. Broadcast stamtąd do 192.168.1.x nie dotrze, dociera tylko kopia
unicast przez router, a router musi znać adres MAC ekranu (wpis ARP). Jeśli
po przejściu na 2,4 GHz WoL działa z Maca, a z Synology nie, potrzebny jest
stały wpis ARP (albo rezerwacja DHCP z ARP) w routerze dla 192.168.1.152.

Do sprawdzenia w E13: czy budzik budzi ekran przy wyłączonym network
standby, jak długo ekran zostaje w sieci po pobudce, czy WoL na 2,4 GHz
działa na baterii.

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

## Źródła

- [Instrukcja EM32DX / EM32DX-A / EM13DX (PDF)](https://media.displaynd.de/media/65/77/76/1775570009/Samsung-EM32DX-A-Benutzerhandbuch.pdf?ts=1775570009): Wi-Fi 2,4 GHz do zdalnego budzenia, Power and Energy Saving, tryb Auto.
- [Karta katalogowa EM32DX-A (Bechtle)](https://media.bechtle.com/asrc/180712/1c4b3d4ee288fc9434f5175bf56070570/c3/-/c5e245e44555491b94d7ac1848dd34e3/samsung-em32dx-a-e-paper-display-datenblatt-1): dwa moduły Wi-Fi.
- [taylorRichie/node-samsung-emdx](https://github.com/taylorRichie/node-samsung-emdx): `docs/MDC-COMMANDS.md` (`0x25`), `web/server.mjs` (budzik, poller, ponowne usypianie).
- [johanneswilm/ha-emdx](https://github.com/johanneswilm/ha-emdx): network standby, deep sleep, budzenie.
- [Samsung Epaper API (Tizen)](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/epaper-api.html?device=signage): `setScheduleWakeupTime`, przywilej Partner.
- [Domino Display: konfiguracja E-Paper (PDF)](https://www.dominodisplay.com/media/catalog/attribute-data/Sch_EPaper_SetUp.pdf): Sleep Time, Network Standby, Custom App URL.
