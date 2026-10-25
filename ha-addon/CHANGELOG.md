# Changelog

## Następna wersja

- „Styl obrazu” dobierany automatycznie do każdego obrazu (domyślnie):
  bez koloru czarno-biały, zdjęcia jako zdjęcia, drzeworyty, litografie
  i plakaty jako grafika, reszta jako obraz. Ręczny wybór dalej możliwy.

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
