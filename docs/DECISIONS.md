# Decyzje projektowe

Krótki rejestr decyzji (ADR). Nowe wpisy dopisujemy na końcu.

## D1. Oryginalny firmware, sterowanie przez MDC — 2026-10-23

**Kontekst.** Ekran działa na Tizen 8 z zamkniętym firmware'em. Społeczność
odtworzyła protokół MDC i przepływ „content download” (ekran sam pobiera
`content.json` i obraz z podanego URL); działa to na EM32DX z firmware 1050.1.
**Decyzja.** Nie modyfikujemy firmware'u. Jeśli okaże się to konieczne,
wrócimy do tematu (np. aplikacja Tizen przez Custom App URL).
**Konsekwencje.** Brak ryzyka zablokowania urządzenia i zachowana gwarancja.
Jesteśmy jednak zależni od nieoficjalnego protokołu, który aktualizacja
firmware może zmienić. Odpowiedź: testy po aktualizacjach, logowanie wersji.

## D2. Serwer jako add-on Home Assistant, w Pythonie — 2026-10-23

**Kontekst.** Home Assistant działa w domu przez całą dobę i jest w tej samej
sieci co ekran (MDC i WoL działają tylko w LAN).
**Decyzja.** Python 3.12+, FastAPI. Obliczenia obrazu w numpy, dithering w
numba. Add-on oparty na Debian slim (numba nie ma wheeli dla musl/Alpine),
z `host_network`.
**Konsekwencje.** Jeden język dla protokołu, obrazu i API. Kod uruchamia się
też poza Home Assistantem (`frame serve` na Macu), co przyspiesza pracę.

## D3. Aplikacja iOS w SwiftUI, projekt generowany XcodeGenem — 2026-10-23

**Decyzja.** iOS 17+ (Observation, PhotosPicker), definicja projektu w
`ios/project.yml`; `Frame.xcodeproj` nie trafia do repozytorium. Token API
trzymamy w Keychain. CI buduje aplikację i uruchamia testy na macOS.
**Konsekwencje.** Brak konfliktów w pliku projektu. Trzeba zainstalować
`xcodegen` (`brew install xcodegen`).

## D4. Algorytm obrazu na zmierzonej palecie — 2026-10-23

**Decyzja.** Dithering i mapowanie gamutu liczymy względem kolorów farb
zmierzonych na ekranie, a do pliku zapisujemy wartości nominalne. Strategię
wysyłki (`dither` / `compensate`) wybierzemy po eksperymencie E5.

## D5. iCloud przez publiczny link albumu — 2026-10-23

**Decyzja.** Serwer synchronizuje udostępniony album z publicznego linku
(nieudokumentowane API `sharedstreams`). W rezerwie zostaje wysyłanie z
aplikacji iOS (PhotoKit).
**Konsekwencje.** Zdjęcia mają maksymalnie ok. 2048 px na dłuższym boku, co
dla tego ekranu jest akceptowalne. API może się zmienić bez ostrzeżenia.
