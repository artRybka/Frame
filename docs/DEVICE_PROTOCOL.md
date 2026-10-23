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
| `0x10` | – | model | ? |
| `0x11` | `00`/`01` | zasilanie wył./wł. (odczyt NAK) | potwierdzone |
| `0x1B` | `73` | stan baterii: `payload[4]` = poziom %, reszta bajtów sporna | częściowo (E1) |
| `0x25` | ? | on timer | ? (E9) |
| `0x67` | – | nazwa urządzenia | potwierdzone |
| `0xA7` | ? | zegar | ? |
| `0xB5` | `00`/`01` | network standby (nasłuch Wi-Fi w uśpieniu, potrzebny do WoL) | potwierdzone |
| `0xC7` | `53 80 len url` | **content download**: ekran pobiera manifest z `url` | potwierdzone |

Wake-on-LAN: standardowy magic packet (UDP :9). Wysyłamy na 255.255.255.255
i na broadcast podsieci /24. Działa tylko przy włączonym network standby.

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

- Ukośniki są escapowane (`\/`), tak jak robi to aplikacja Samsunga. Robimy to samo na wszelki wypadek.
- Znaczenie `duration` i to, czy kilka pozycji lub wpisów `schedule` tworzy playlistę, sprawdza **E6**.
- Ekran **zapamiętuje URL** i pobiera go ponownie później. Odpowiedź 404 kończy się komunikatem „Configuration error” na ekranie, dlatego nasz serwer zawsze serwuje bieżącą treść (także po restarcie) i ma treść zastępczą od pierwszego uruchomienia.
- Do URL dodajemy `?v=<file_id>`, żeby każda wysyłka miała inny adres. Serwer ignoruje ten parametr.

## Tizen / VXT (na później)

- **Custom App URL** w aplikacji Samsung E-Paper pozwala uruchomić własną aplikację webową Tizen. Pozwoliłoby to sterować budzeniem (`setScheduleWakeupTime`), usypianiem i diodami LED (Epaper API, Tizen 8.0). Ograniczenie: API wymaga przywileju **Partner** (`http://developer.samsung.com/privilege/systemcontrol`), więc może być niedostępne bez certyfikatu partnerskiego.
- **Samsung VXT** to chmurowy CMS Samsunga. Nie korzystamy z niego.

## Źródła

- [johanneswilm/ha-emdx](https://github.com/johanneswilm/ha-emdx): integracja HA, zweryfikowana na EM32DX z firmware S-RSEDWWC-1050.1.
- [WeeJeWel/node-samsung-emdx](https://github.com/WeeJeWel/node-samsung-emdx) i [node-samsung-mdc](https://github.com/WeeJeWel/node-samsung-mdc): pierwsze publiczne odtworzenie przepływu content download.
- [Samsung Epaper API (Tizen)](https://developer.samsung.com/smarttv/develop/api-references/samsung-product-api-references/epaper-api.html?device=signage)
- [CNX Software: EMDX, Tizen 8, 2560×1440](https://www.cnx-software.com/2025/04/09/samsung-32-emdx-color-e-paper-display-runs-tizen-8-0-offers-2560x1440-resolution-up-to-200-days-of-battery-life/)
- [Samsung: 32" Color E-paper EM32DX](https://www.samsung.com/hk_en/business/smart-signage/e-paper/color-e-paper-emdx-a-lh32emdiagbxxk/)
