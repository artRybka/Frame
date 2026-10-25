# Changelog

## Niewydane

- Harmonogram: zamiast interwałów osobno dla zasilacza i baterii godziny
  zmiany obrazu (`change_times`, jedna lub kilka dziennie) i co ile dni
  (`change_every_days`, 1–3). Cisza nocna trwa od `quiet_start` do
  porannej zmiany; `quiet_end`, `interval_minutes` i
  `interval_minutes_battery` znikają, a stare ustawienia zamieniają się
  same. Harmonogram jest ten sam przy ładowarce i na baterii; głęboki sen
  w nocy tylko na baterii, na ładowarce zdjęcia idą od razu.

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
