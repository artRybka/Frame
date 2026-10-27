# Protokół ekranu Samsung EM32DX

Stan wiedzy na start projektu. Źródła to projekty społeczności (poniżej)
i dokumentacja Samsunga. Wszystko oznaczone „?” trzeba potwierdzić
eksperymentami ([EXPERIMENTS.md](EXPERIMENTS.md)).

## Urządzenie

| | |
|---|---|
| Panel | E Ink Spectra 6, 32", **2560×1440**, 6 farb: czarna, biała, żółta, czerwona, niebieska, zielona |
| System | Tizen 8.0, 8 GB eMMC |
| Łączność | Wi-Fi 5, Bluetooth 5.0; Ethernet przez przejściówkę USB-C → RJ45 |
| Zasilanie | bateria 4600 mAh, do ~200 dni przy jednej zmianie dziennie; zasilanie USB-C |
| Zalecenie producenta | odświeżać obraz co najmniej raz na 3 dni (ochrona panelu, ghosting) |

## Sterowanie: MDC (Multiple Display Control)

```
klient → TCP :1515
ekran  ← "MDCSTART<<TLS>>"
         TLS na tym samym gnieździe (certyfikat self-signed, bez weryfikacji)
klient → PIN jako ASCII (np. "123456")
ekran  ← "MDCAUTH<<PASS>>"  |  "MDCAUTH<<FAIL:0x01>>" (zły PIN)  |  "...FAIL:0x02>>" (blokada)
```

Ramka komendy: `AA cmd id len data… chk`, gdzie `chk = (cmd+id+len+Σdata) & 0xFF`.
Ramka odpowiedzi: `AA FF id len A|N rcmd data… chk`, gdzie `chk = (FF+id+…) & 0xFF`.
EM32DX bywa niekonsekwentny w bajcie `len` (±1), więc nasz parser
(`device/mdc.py: parse_reply`) akceptuje warianty z poprawną sumą kontrolną.

Ekran obsługuje **jedną sesję naraz** i trzyma martwą sesję zarezerwowaną przez
30–60 s. Dlatego łączymy się na krótko, ponawiamy połączenie z odstępem i nie
wysyłamy komend szybciej niż co ~0,3 s.

| Komenda | Dane | Znaczenie | Status |
|---|---|---|---|
| `0x0B` | – | numer seryjny | potwierdzone (społeczność) |
| `0x0E` | – | wersja oprogramowania | potwierdzone |
| `0x10` | – | model: kod `02 7a 01`, nie tekst | odczytane (E1) |
| `0x11` | `00`/`01` | zasilanie wył./wł. (odczyt NAK) | potwierdzone |
| `0x1B` | `73` | stan baterii: `payload[4]` = poziom %, `payload[6]` = zasilanie USB-C (`02` podłączone, `00` odłączone); reszta (`00 01 01`, `02`) bez zmian | częściowo (E1) |
| `0x25` | `en repeat hh mm 01` | on-timer według społeczności (firmware 1050.1). **U nas (1130.7) zapis z godziną: NAK `01`**; przyjmuje tylko jeden bajt `00–05` i tyle zwraca odczyt. Godziny budzika przez MDC nie znamy, patrz [WAKE.md](WAKE.md#tryb-oszczędny) | E13: odrzucone |
| `0x67` | – | nazwa urządzenia | potwierdzone |
| `0xA7` | – | zegar: dzień, godzina 1–12, minuta, miesiąc, rok (2 bajty), `01` = AM (np. `19 0c 00 0a 07 ea 01` = 25.10.2026 00:00) | odczytane (E1) |
| `0xB5` | `00`/`01` | network standby (nasłuch Wi-Fi w uśpieniu, potrzebny do WoL) | potwierdzone |
| `0xC7` | `53 80 len url` | **content download**: ekran pobiera manifest z `url` | potwierdzone |

Wake-on-LAN: standardowy magic packet (UDP :9 i :7). Wysyłamy na 255.255.255.255,
na broadcast podsieci /24 i unicastem na adres ekranu. Działa tylko przy włączonym
network standby, a według instrukcji Samsunga (EM32DX-A) tylko w sieci Wi-Fi 2,4 GHz.
**E8: przez Wi-Fi nie obudził ekranu uśpionego na baterii** (firmware 1130.7); budzi go
krótkie naciśnięcie przycisku. Więcej w [WAKE.md](WAKE.md).

Obecność w sieci bez budzenia: uśpiony ekran nie odpowiada na MDC (TCP :1515
milczy, połączenie kończy się timeoutem). Gdy MDC milczy, serwer sprawdza tablicę
sąsiadów jądra (rtnetlink, bez uprawnień; kontener działa w sieci hosta): po
próbie połączenia wpis ekranu kończy jako REACHABLE (moduł Wi-Fi odpowiedział na
ARP, czyli ekran śpi w sieci) albo FAILED (brak odpowiedzi; `connect` zwraca
wtedy od razu „No route to host”). Za routerem wpisu nie ma i nic nie wiadomo.
Czy EM32DX odpowiada na ARP w uśpieniu: E15.

## Treść: manifest `content.json`

Po `0xC7` ekran pobiera (HTTP GET) manifest, a potem obraz z `image_url`.
Format naśladuje to, co publikuje aplikacja Samsung E-Paper na iOS
(`deploy_type: MOBILE`):

```json
{
  "schedule": [{
    "start_date": "1970-01-01", "stop_date": "2999-12-31", "start_time": "00:00:00",
    "contents": [{
      "image_url": "http://192.168.1.10:8099/panel/images/ABCD.png",
      "file_id": "ABCD",
      "file_path": "/home/owner/content/Downloads/vxtplayer/epaper/mobile/contents/ABCD/ABCD.png",
      "duration": 91326,
      "file_size": "612345",
      "file_name": "ABCD.png"
    }]
  }],
  "name": "frame", "version": 1, "create_time": "2026-10-23 20:00:00", "id": "ABCD",
  "program_id": "com.samsung.ios.ePaper", "content_type": "ImageContent", "deploy_type": "MOBILE"
}
```

Uwagi:

- Zapytania ekranu (E2): brak User-Agenta, tylko `Accept: */*`, bez `Range` i `If-Modified-Since`. Pobiera `content.json` ok. 0,25 s po `0xC7`, obraz zaraz po nim.
- Obraz (E3): PNG i JPEG działają, także JPEG 13 MB. Inna rozdzielczość jest wpasowywana w 2560×1440 z zachowaniem proporcji (pion 1440×2560 = wąski pas z szarymi bokami, bez obracania). Piksele 2560×1440 są pokazywane 1:1 (E5). Obraz spoza 6 farb ekran sam ditheruje szumem w stylu dyfuzji błędu.

- Ukośniki są escapowane (`\/`), tak jak robi to aplikacja Samsunga. Robimy to samo na wszelki wypadek.
- Znaczenie `duration` i to, czy kilka pozycji lub wpisów `schedule` tworzy playlistę, sprawdza **E6**.
- Ekran **zapamiętuje URL** i pobiera go ponownie później. Odpowiedź 404 kończy się komunikatem „Configuration error” na ekranie, dlatego nasz serwer zawsze serwuje bieżącą treść (także po restarcie) i ma treść zastępczą od pierwszego uruchomienia.
- Do URL dodajemy `?v=<file_id>`, żeby każda wysyłka miała inny adres. Serwer ignoruje ten parametr.
- Ekran raportuje postęp pobierania zapytaniami `POST /content-transfer-progress` na **główny** adres serwera (nie pod `/panel/`). Zaobserwowane 2026-10-24 przy błędnym `image_url`: kilka raportów w ciągu minuty, obrazu nie pobrał. Treść raportu nie jest jeszcze znana; serwer zapisuje ją w logu (`panel progress report: …`) i odpowiada 200.

## Tizen / VXT (na później)

- **Custom App URL** w aplikacji Samsung E-Paper pozwala uruchomić własną aplikację webową Tizen. Pozwoliłoby to sterować budzeniem (`setScheduleWakeupTime`), usypianiem i diodami LED (Epaper API, Tizen 8.0). Ograniczenie: API wymaga przywileju **Partner** (`http://developer.samsung.com/privilege/systemcontrol`), więc może być niedostępne bez certyfikatu partnerskiego.
- **Samsung VXT** to chmurowy CMS Samsunga. Nie korzystamy z niego.

## Źródła

- [johanneswilm/ha-emdx](https://github.com/johanneswilm/ha-emdx): integracja HA, zweryfikowana na EM32DX z firmware S-RSEDWWC-1050.1.
- [WeeJeWel/node-samsung-emdx](https://github.com/WeeJeWel/node-samsung-emdx) i [node-samsung-mdc](https://github.com/WeeJeWel/node-samsung-mdc): pierwsze publiczne odtworzenie przepływu content download.
- [Samsung Epaper API (Tizen)](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/epaper-api.html?device=signage)
- [CNX Software: EMDX, Tizen 8, 2560×1440](https://www.cnx-software.com/2025/04/09/samsung-32-emdx-color-e-paper-display-runs-tizen-8-0-offers-2560x1440-resolution-up-to-200-days-of-battery-life/)
- [Samsung: 32" Color E-paper EM32DX](https://www.samsung.com/hk_en/business/smart-signage/e-paper/color-e-paper-emdx-a-lh32emdiagbxxk/)
