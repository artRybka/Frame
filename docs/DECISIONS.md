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
**Zmiana 2026-10-31.** Cel podniesiony do iOS 26 (decyzja Mateusza przy
szklanym Szukaj): systemowa karta wyszukiwania (`Tab(role: .search)`),
pole Szukaj na dole i szklane przyciski grup (`glassEffect`). Aplikacji
używa tylko rodzina na iPhone'ach z iOS 26; CI wybiera symulator z
najnowszym iOS.

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

## D6. Serwer: jeden obraz, add-on (HA Green) albo kontener (Synology) — 2026-10-23

**Kontekst.** Są dwie maszyny: HA Green (HA OS, aarch64) oraz Synology
RS1619xs+ z Home Assistantem w kontenerze (HA Container, bez sklepu z
dodatkami, amd64).
**Decyzja.** Budujemy jeden obraz multi-arch. Uruchamiamy go jako add-on na
HA Green albo jako kontener `docker-compose` na Synology (sieć hosta, wolumen
`/data`). Wybór zapadnie później, po pomiarze czasu renderowania na ARM.
Uzupełnia D2.

## D7. Oprogramowanie ekranu aktualizowane ręcznie — 2026-10-23

**Decyzja.** Automatyczne aktualizacje firmware wyłączone. Aktualizujemy
dopiero po sprawdzeniu, że MDC i `content.json` nadal działają.

## D8. Rodzina z rolami, dostęp spoza domu przez Tailscale / VPN — 2026-10-23

**Decyzja.** Role: *administrator* (wszystko, w tym ustawienia ekranu,
kalibracja, użytkownicy) i *domownik* (wysyłanie zdjęć z rolki,
następny/poprzedni/przypnij, tryb i harmonogram, ulubione i wykluczenia).
Każde urządzenie ma własny token, parowany kodem QR. Serwer nie jest
wystawiony do internetu; poza domem działa przez Tailscale / VPN.
Aplikacja: TestFlight dla rodziny, nazwa „Frame”, interfejs po polsku.

## D9. Tryb ramki: album iCloud albo obrazy; zdjęcie z rolki z czasem wyświetlania — 2026-10-23

*Tryb zastąpiony przez D12: album iCloud jest teraz playlistą.*

**Decyzja.** Źródeł nie mieszamy: w aplikacji wybiera się album iCloud albo
obrazy (kolekcje). Pojedyncze zdjęcie z rolki aparatu wysyła się z wyborem,
jak długo ma zostać (do następnej zmiany / X godzin lub dni / na stałe).
Częstotliwość zmian, godziny ciszy, kadrowanie i etykieta na ramce są
ustawiane w aplikacji (kadrowanie i etykieta osobno dla sztuki i zdjęć).

## D10. Treści: opisy w oryginale, priorytety źródeł — 2026-10-23

**Decyzja.** Opisy dzieł i notki o autorach w oryginale (angielskim), bez
tłumaczenia. Priorytety źródeł: wielkie muzea światowe, sztuka polska
(Polona, muzea narodowe — do weryfikacji API i licencji), drzeworyt
japoński, plakaty i ilustracje. Szczegóły zdjęć: data i godzina, miejsce,
kto dodał, podpis.

## D11. Licencja MIT — 2026-10-23

**Decyzja.** Repozytorium jest publiczne, kod udostępniamy na licencji MIT (`LICENSE`).

## D12. Albumy iCloud jako playlisty — 2026-10-25

**Kontekst.** Album iCloud był trybem ramki w ustawieniach (jeden link).
**Decyzja.** Album to rodzaj playlisty: przy tworzeniu podaje się link i
kolejność (losowo, najnowsze, najstarsze, ostatnio dodane); albumów może
być wiele. Harmonogram wybiera tylko playlistę. Synchronizacja pobiera
miniatury, a oryginały przez świeży link przed pokazaniem (pamięć podręczna
z limitem). Prezentacja zostaje osobno dla sztuki (playlisty dzieł,
Propozycje) i zdjęć (albumy, zdjęcia z rolki).
**Konsekwencje.** Starsze ustawienia (`mode`, `album_url`) zamieniają się
same w playlistę-album, odtwarzaną, jeśli był włączony tryb albumu.

## D13. Dostęp spoza domu: dwa adresy serwera i Tailscale — 2026-10-26

**Decyzja.** Serwer nie jest wystawiany do internetu. Poza domem aplikacja
łączy się przez Tailscale (pakiet na NAS-ie, aplikacja na iPhonie). W
ustawieniach są dwa adresy: „W domu” i opcjonalny „Spoza domu”. Aplikacja
pyta oba o `/api/health` naraz (bez tokenu, bo domowy adres nie jest
prywatny i poza domem może należeć do kogoś innego) i wybiera domowy, jeśli
odpowie w 2 s, inaczej zdalny. Sprawdza to przy starcie, przeciągnięciu w
dół, powrocie do aplikacji, zmianie sieci (także włączeniu VPN) i gdy
zapytanie nie dojdzie; zapytanie powtarza na drugim adresie tylko wtedy,
gdy nie mogło niczego zrobić dwa razy (GET albo brak połączenia).
**Konsekwencje.** Serwer bez zmian: ekran dalej pobiera obrazy z adresu
lokalnego (`public_host`), a aplikacja używa ścieżek względnych. Odrzucone:
publiczny adres HTTPS przez reverse proxy (serwer chroniony tylko tokenem)
oraz sam VPN z jednym adresem (trzeba pamiętać o włączaniu go także w domu
albo routować podsieć).

## D14. Aktualizacja serwera z aplikacji: pomocnik obok kontenera — 2026-10-29

**Kontekst.** Na Synology każda wersja wymagała ręcznego *Projekt → frame →
Kompiluj* w Container Managerze.
**Decyzja.** W projekcie `frame` działa drugi kontener z tego samego obrazu,
`frame-updater` (`frame updater`), z gniazdem Dockera i bez sieci
(`network_mode: none`). Co 6 godzin i na prośbę aplikacji pobiera obraz,
z którego powstał kontener `frame`, a na polecenie tworzy ten kontener na
nowo z tymi samymi ustawieniami (bez ENV/CMD/etykiet starego obrazu); gdy
nowy nie działa po 20 s, wraca poprzedni. Na koniec podmienia też siebie
przez krótkotrwały kontener. Serwer nie ma dostępu do Dockera: zostawia
prośbę w `data/update/request.json` (API `/api/server/update` z tokenem),
pomocnik odpowiada w `status.json`. Wersję obrazu podaje etykieta
`org.opencontainers.image.version` i plik `/etc/frame-release` (wersja
add-onu).
**Konsekwencje.** Raz trzeba wkleić nowy `docker-compose.yml` w projekcie.
Odrzucone: Watchtower (obcy obraz z pełnym dostępem do Dockera i otwarty
port API) i API Synology (hasło administratora DSM na serwerze).
