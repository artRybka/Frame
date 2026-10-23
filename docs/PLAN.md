# Plan prac — Frame

Ramka na obrazy, grafiki i zdjęcia zbudowana na ekranie **Samsung EM32DX**
(32", kolorowy e-papier E Ink Spectra 6, 2560×1440, Tizen 8, Wi-Fi, bateria).
Wzorujemy się na ramce InkJoy: biblioteka obrazów z opisami, udostępniony album
zdjęć iCloud i aplikacja iOS do sterowania.

## 1. Ustalenia

| Temat | Decyzja | Konsekwencje |
|---|---|---|
| Firmware | **Oryginalny**, bez modyfikacji | Sterujemy przez protokół MDC (TCP 1515, TLS, PIN). Ekran sam pobiera manifest `content.json` i obraz z naszego serwera. Gwarancja zostaje, nie ryzykujemy zablokowania urządzenia. |
| Serwer | **Add-on Home Assistant** (Python, FastAPI) | `host_network` (ekran pobiera obrazy z IP Home Assistanta, a Wake-on-LAN wymaga broadcastu). W trakcie prac serwer można uruchamiać na Macu w tej samej sieci. |
| Zasilanie | **Mieszane** (bateria + doładowywanie) | Potrzebna polityka zasilania: przy ładowarce zmiany na żądanie, na baterii rzadkie zmiany i budzenie. Szczegóły zależą od eksperymentów E6–E8. |
| iOS | Mac + Xcode + **płatne konto** (do założenia) | SwiftUI, iOS 17+, dystrybucja przez TestFlight, w przyszłości widget i rozszerzenie „Udostępnij”. |
| iCloud | **Publiczny link albumu** | Serwer sam synchronizuje album. Apple zmniejsza zdjęcia w albumach udostępnionych do ok. 2048 px, więc na ekranie 2560 px trzeba je lekko powiększyć (×1,25), co przy ditheringu jest niewidoczne. |
| Biblioteka | **Muzea z otwartym API + własne prace** | Tylko domena publiczna / CC0. Opisy i notki o autorach pochodzą z API muzeów, a dla autorów z Wikidata/Wikipedii. |
| Orientacja | **Zmieniana** | Każdy obraz renderujemy pod bieżącą orientację; portret obracamy do natywnego bufora 2560×1440. |
| Kalibracja | **Zdjęcie iPhonem** | Plansza testowa na ekranie, zdjęcie z białą kartką obok jako wzorcem, z tego wyliczamy zmierzoną paletę. |

## 2. Dlaczego obrazy z aplikacji Samsunga są za ciemne (hipoteza robocza)

Farby Spectra 6 są dużo ciemniejsze niż ich „nominalne” wartości RGB. Biel
panelu to w praktyce jasnoszary (ok. 190/255), czerwień to ok. (135, 19, 0),
a zieleń jest bardzo ciemna. Algorytm, który dobiera punkty tak, jakby czerwień
była (255, 0, 0), systematycznie zaniża jasność i nasycenie. Nasz model takiego
„naiwnego” ditheringu (`frame render ... --strategy passthrough --preview`)
odtwarza dokładnie ten efekt. Rozwiązanie składa się z czterech kroków:

1. dithering względem **zmierzonych** kolorów farb,
2. mapowanie tonów do rzeczywistego zakresu panelu (podniesienie cieni i półtonów),
3. mapowanie gamutu do bryły kolorów, które da się zmieszać z sześciu farb,
4. wysłanie obrazu złożonego wyłącznie z „czystych” farb, o ile ekran go nie przetworzy ponownie. Rozstrzygnie to eksperyment E5.

Szczegóły: [IMAGE_PIPELINE.md](IMAGE_PIPELINE.md).

## 3. Architektura (skrót)

```
 iPhone (app Frame) ──HTTP/JSON──┐
                                 ▼
             ┌──────────── Home Assistant ─────────────┐
             │  add-on Frame (Python)                  │
             │   • biblioteka (SQLite + pliki)         │
             │   • źródła: muzea, iCloud, upload       │
             │   • pipeline obrazu (numba)             │
             │   • harmonogram rotacji / zasilanie     │
             │   • /panel/content.json + /panel/images │
             └───────┬────────────────────▲────────────┘
          MDC 0xC7   │ TLS :1515           │ HTTP GET (ekran pobiera)
          WoL (UDP)  ▼                     │
                 Samsung EM32DX ───────────┘
```

Więcej: [ARCHITECTURE.md](ARCHITECTURE.md), protokół: [DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md).

## 4. Etapy

### Etap 0 — Rozpoznanie urządzenia ⟵ *jesteśmy tutaj*

Cel: potwierdzić protokół na Twoim egzemplarzu i poznać zachowanie ekranu.

- [x] Klient MDC (TLS, PIN, ramki, bateria, network standby, content download), Wake-on-LAN.
- [x] Serwer treści (`content.json`, obraz, log zapytań ekranu) i CLI `frame`.
- [x] Plansze testowe: `palette`, `passthrough`, `ramps`.
- [ ] Eksperymenty E1–E12 na ekranie ([EXPERIMENTS.md](EXPERIMENTS.md)). **Wymaga Ciebie i ekranu.**
- [ ] Narzędzie do eksperymentu E6 (manifest z kilkoma obrazami), po wynikach E2.
- [ ] Decyzje: strategia obrazu (passthrough / compensate / dither), format pliku (PNG/JPEG), polityka zasilania.

**Gotowe, gdy:** ekran pokazuje obraz z naszego serwera, mamy wyniki E1–E8 i podjęte decyzje.

### Etap 1 — Algorytm obrazu i kalibracja

- [x] Pipeline v0: przestrzeń liniowa i OKLab, mapowanie tonów, mapowanie gamutu do bryły farb, dyfuzja błędu (7 jąder, serpentyna, ograniczanie błędu), presety `photo` / `painting` / `graphic` / `bw`, podgląd wyglądu na ekranie.
- [ ] 1.1 Pomiar palety EM32DX: plansza `palette`, zdjęcie iPhonem i skrypt `frame calibrate photo.jpg`, wynik w `palettes/em32dx.json`.
- [ ] 1.2 Zestaw testowy ok. 20 obrazów (portrety, krajobrazy, olej, akwarela, drzeworyt, plakat, zdjęcia czarno-białe) i procedura porównań A/B: zdjęcia ekranu w tym samym świetle.
- [ ] 1.3 Strojenie presetów na prawdziwym ekranie.
- [ ] 1.4 Ulepszenia algorytmu:
  - szarości bez kolorowego szumu (preferencja osi czarny–biały),
  - kompromis jasność/nasycenie przy mapowaniu gamutu (np. niebo bardziej niebieskie kosztem jasności),
  - dithering uporządkowany / blue-noise dla grafiki płaskiej,
  - automatyczny dobór presetu według treści,
  - inteligentne kadrowanie (twarze i ważne obszary),
  - podpisy i passe-partout bez ditheringu (czysty tekst).
- [ ] 1.5 Obiektywna metryka jakości (ΔE po rozmyciu, w stylu S-CIELAB) do porównywania ustawień.
- [ ] 1.6 Wydajność na sprzęcie Home Assistanta (cel: poniżej 10 s na obraz) i cache renderów.

**Gotowe, gdy:** zdjęcia i obrazy na ramce wyglądają dobrze w ocenie domowników, nie są za ciemne, a kolory mają naturalną tonację.

### Etap 2 — Serwer (add-on Home Assistant)

- [ ] 2.1 Model danych (SQLite): `Item` (dzieło / zdjęcie / własna praca, metadane), `Collection`, `Rotation` (harmonogram), `Render` (cache dla palety i ustawień), `History`.
- [ ] 2.2 Biblioteka: upload własnych prac z opisem, import z muzeów (Art Institute of Chicago, The Met, Cleveland Museum of Art, Rijksmuseum; do weryfikacji: Smithsonian, National Gallery of Art, Wikimedia Commons, Polona), kolekcje kuratorowane, ocena „przydatności dla e-papieru” (pokrycie gamutu, jasność).
- [ ] 2.3 Synchronizacja udostępnionego albumu iCloud z publicznego linku: nowe zdjęcia, usunięcia, metadane (data, autor dodania, podpis), deduplikacja.
- [ ] 2.4 Harmonogram rotacji: interwał, pory dnia, cisza nocna, proporcje źródeł (sztuka / zdjęcia), bez powtórek przez N dni, przypięcie obrazu. Zmiana obrazu co najmniej raz na 3 dni (zalecenie producenta dot. ochrony panelu).
- [ ] 2.5 Polityka zasilania (wg wyników E6–E8): tryb „ładowarka” / „bateria”, monitorowanie baterii, powiadomienia.
- [ ] 2.6 API dla aplikacji: Teraz, Biblioteka, Kolekcje, Harmonogram, Ustawienia obrazu, Podgląd renderu na żywo, Kalibracja. Ogłaszanie przez Bonjour `_frame._tcp`.
- [ ] 2.7 Opisy po polsku: tłumaczenie opisów muzealnych (decyzja: automatyczne czy ręczne), notki o autorach z Wikidata/Wikipedii.
- [ ] 2.8 Wydawanie add-onu: wersje, obrazy multi-arch w GHCR, kopie zapasowe `/data`.

**Gotowe, gdy:** add-on sam zmienia obrazy z biblioteki i albumu iCloud według harmonogramu, a nowe zdjęcie w albumie pojawia się w rotacji.

### Etap 3 — Aplikacja iOS

- [x] Szkielet: połączenie z serwerem (adres i token w Keychain), ekran „Teraz na ramce” (podgląd, opis), wysyłanie zdjęcia z presetem, stan ekranu (bateria, firmware).
- [ ] 3.1 Wykrywanie serwera przez Bonjour i parowanie tokenem (kod QR z panelu add-onu).
- [ ] 3.2 „Teraz”: pełny opis dzieła (tytuł, autor, data, technika, muzeum, notka o autorze) lub zdjęcia (data, miejsce, kto dodał, aparat), przyciski Następny / Poprzedni / Przypnij.
- [ ] 3.3 Biblioteka: kolekcje, wyszukiwanie w muzeach, ulubione, wykluczenia, upload własnych prac z opisem.
- [ ] 3.4 Harmonogram i źródła: interwał, cisza nocna, proporcje, album iCloud.
- [ ] 3.5 Regulacja obrazu: suwaki (jasność, kontrast, nasycenie, cienie) z podglądem renderu na żywo.
- [ ] 3.6 Kreator kalibracji: wyświetl planszę, zrób zdjęcie, wyślij, zobacz wynik.
- [ ] 3.7 Widget (aktualny obraz) i rozszerzenie „Udostępnij → Pokaż na ramce”.
- [ ] 3.8 TestFlight dla domowników.

### Etap 4 — Integracja z Home Assistant

- [ ] Encje: aktualny obraz (`image`), bateria, zasilanie, przyciski następny/poprzedni, wybór kolekcji (MQTT discovery albo mała integracja).
- [ ] Przykładowe automatyzacje: obraz dnia o 7:00, kolekcje sezonowe, pauza, gdy nikogo nie ma w domu.

### Etap 5 — Dopracowanie

- [ ] Dostęp spoza domu (Tailscale albo Nabu Casa + ingress).
- [ ] Testy długoterminowe: zużycie baterii, ghosting, stabilność po aktualizacjach firmware.
- [ ] Dokumentacja użytkownika, kopie zapasowe, ewentualna strona konfiguracji w panelu Home Assistanta (ingress).

## 5. Kamienie milowe

| # | Kamień milowy | Etap |
|---|---|---|
| M0 | Ekran pokazuje obraz wysłany z naszego serwera | 0 |
| M1 | Zmierzona paleta EM32DX, wybrana strategia obrazu | 0–1 |
| M2 | Add-on w Home Assistant rotuje obrazy z biblioteki muzealnej | 2 |
| M3 | Zdjęcia z albumu iCloud na ramce, z datą i opisem | 2 |
| M4 | Aplikacja iOS w TestFlight: Teraz, Biblioteka, Harmonogram | 3 |
| M5 | Encje i automatyzacje w Home Assistant | 4 |

## 6. Ryzyka

| Ryzyko | Wpływ | Co robimy |
|---|---|---|
| Ekran sam przetwarza obraz (dithering nałożony na nasz dithering) | gorsza jakość | Eksperyment E5. Jeśli wzory 1 px nie przetrwają, przechodzimy na strategię `compensate` (wstępna korekta, a dithering zostaje po stronie ekranu). |
| Na baterii ekran nie słucha sieci | brak zmian na żądanie | E6–E8: playlista w manifeście, harmonogram budzenia ekranu, Wake-on-LAN przy network standby. |
| Protokół MDC i manifest są nieoficjalne; aktualizacja firmware może je zmienić | utrata sterowania | Rozważyć wyłączenie automatycznych aktualizacji, testy po każdej aktualizacji, zapisywanie wersji firmware. |
| Publiczne API albumów iCloud jest nieudokumentowane | sync przestaje działać | Izolowany moduł i testy na nagranych odpowiedziach. W zapasie: wysyłanie z aplikacji iOS (PhotoKit). |
| Wydajność na ARM (RPi / HA Green) | wolne renderowanie | numba z cache JIT, renderowanie z wyprzedzeniem, cache wyników. |
| Licencje obrazów | problemy prawne | Tylko domena publiczna / CC0 i pole licencji w bazie. |

## 7. Pytania otwarte

1. Na jakim sprzęcie działa Home Assistant (RPi 4/5, HA Green/Yellow, mini-PC x86)? Od tego zależy wydajność i architektura obrazu Dockera.
2. Czy wyłączamy automatyczne aktualizacje firmware ekranu (stabilność protokołu)?
3. Czy aplikacja ma działać także poza domem?
4. Opisy dzieł po polsku: czy akceptujesz tłumaczenie automatyczne (np. przez API modelu językowego), czy wolisz oryginały po angielsku?
5. Licencja repozytorium (jest publiczne), np. MIT?
6. Jak często zmieniać obraz i czy obowiązują godziny ciszy?
7. Kto będzie używał aplikacji (Ty / rodzina)? Od tego zależą uwierzytelnianie i role.

## 8. Do zrobienia po Twojej stronie (start)

1. **Ekran**: w aplikacji Samsung E-Paper podłącz ekran do Wi-Fi. Zanotuj **IP**, **MAC** i **PIN** (PIN pojawia się na ekranie podczas parowania). W routerze przypisz ekranowi stały adres IP.
2. **Mac**: zainstaluj `uv` (`brew install uv`), sklonuj repozytorium, uruchom `cd server && uv sync`, skopiuj `.env.example` do `.env` i uzupełnij dane ekranu.
3. Wykonaj eksperymenty **E1–E5** z [EXPERIMENTS.md](EXPERIMENTS.md). Zdjęcia ekranu wrzuć do `docs/experiments/` (lub prześlij mi).
4. Załóż konto **Apple Developer Program** (weryfikacja trwa do 48 h).
5. `brew install xcodegen`, następnie `cd ios && xcodegen generate` i otwórz `Frame.xcodeproj`.
6. W albumie iCloud włącz **„Witryna publiczna”** i zachowaj link (przyda się w Etapie 2).
