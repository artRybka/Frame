# Eksperymenty z ekranem (Etap 0)

Protokół ekranu jest nieoficjalny. Opisały go projekty społeczności (patrz
[DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md)), ale wiele szczegółów trzeba
sprawdzić na Twoim egzemplarzu. Wyniki zapisuj w tabeli na dole albo w
`docs/experiments/EXX-*.md`. **Zdjęć nie dodajemy do repo**: zostają u Ciebie, a w tabeli opisujemy, co na nich widać.

## Przygotowanie

```bash
cd server
uv sync
cp .env.example .env      # uzupełnij FRAME_DEVICE_HOST / PIN / MAC
uv run frame device info  # E1
```

Zasady robienia zdjęć ekranu (E5, kalibracja):

- światło dzienne rozproszone (nie bezpośrednie słońce, bez lamp), zawsze to samo miejsce;
- iPhone na wprost ekranu, bez lampy błyskowej, ekspozycja zablokowana (przytrzymaj palec na kadrze);
- obok ekranu, w kadrze, kartka białego papieru do drukarki (wzorzec bieli);
- do zbliżeń teleobiektyw albo makro, z odległości 10–20 cm.

Każde zapytanie ekranu do serwera trafia do `data/panel-requests.jsonl`
(czas, adres, ścieżka, User-Agent, nagłówki).

---

### E1 — Połączenie i informacje o urządzeniu

- `uv run frame device info`. Zapisz model, numer seryjny, wersję firmware i surowe bajty baterii.
- Powtórz przy podłączonej i odłączonej ładowarce oraz przy różnych poziomach baterii. Cel: rozszyfrować bajty statusu baterii (dwie implementacje referencyjne interpretują je różnie).
- Sprawdź, co zwracają komendy, których nie znamy: `uv run frame device raw 0x25` (timer), `raw 0xA7` (zegar), `raw 0x10` (model).

### E2 — Pierwszy obraz z naszego serwera (kamień milowy M0)

- `uv run frame push zdjecie.jpg`. Polecenie uruchamia serwer, wysyła MDC 0xC7, czeka na pobranie i serwuje dalej.
- Zmierz czasy: wysłanie komendy → GET `content.json` → GET obrazu → początek odświeżania → koniec odświeżania.
- Zapisz z logu User-Agent i nagłówki zapytań (np. `Range`, `If-Modified-Since`).

### E3 — Formaty i rozdzielczości

- `--format png` i `--format jpeg` dla tego samego obrazu. Czy oba działają?
- Plik w innej rozdzielczości niż 2560×1440, wysłany bez renderowania (`--raw`), np. 1920×1080 albo 1440×2560. Czy ekran skaluje, kadruje, odrzuca?
- Rozmiar pliku: od jakiego rozmiaru pojawiają się problemy (sprawdzić np. JPEG 10 MB)?

### E4 — Orientacja

- Czy aplikacja Samsunga ma ustawienie orientacji? Czy ekran ma czujnik położenia?
- `uv run frame push obraz.jpg --set layout.orientation='"portrait"'`, a następnie wariant z `--set layout.rotation=270`. Który wariant jest prawidłowy przy Twoim sposobie powieszenia?

### E5 — Czy ekran przetwarza obraz po swojemu? (kluczowy)

1. `uv run frame testchart passthrough pt.png && uv run frame push pt.png --raw`.
   Zrób zbliżenia szachownic 1 px. **Pytanie:** czy wzór jest odtworzony 1:1 (każdy piksel dokładnie jedną farbą), czy jest rozmyty lub zdithowany ponownie?
2. `uv run frame testchart ramps r.png && uv run frame push r.png --raw`.
   Zdjęcie całości i zbliżenia. Jak ekran sam ditheruje gradienty? Jaki ma wzór (szum, raster)?
3. To samo zdjęcie testowe w trzech strategiach, każda z osobnym zdjęciem ekranu w identycznym świetle:
   ```bash
   uv run frame push foto.jpg -s passthrough   # jak aplikacja Samsunga
   uv run frame push foto.jpg -s compensate    # nasza korekta, dithering po stronie ekranu
   uv run frame push foto.jpg -s dither        # pełny pipeline, czyste farby
   ```
   Dla porównania wyślij to samo zdjęcie aplikacją Samsung E-Paper.

**Decyzja:** jeśli punkt 1 jest 1:1, używamy strategii `dither`. W przeciwnym razie `compensate`.

### E6 — Playlista w manifeście

*(Narzędzie przygotujemy po E2.)* Manifest z 2–3 pozycjami w `contents` i różnymi
wartościami `duration`, a także kilka wpisów `schedule` z różnymi `start_time`.
Czy ekran sam zmienia obrazy? W jakich jednostkach jest `duration`? Czy działa
to na baterii, gdy ekran śpi?

### E7 — Kiedy ekran sam pobiera `content.json` ponownie?

- Po wysłaniu obrazu zmień treść na serwerze bez MDC: `POST /api/display` z `push=false`.
- Zostaw ekran na 24 h i przejrzyj `panel-requests.jsonl`. Czy i kiedy ekran pyta ponownie (po wybudzeniu, o stałej godzinie, co N godzin)? Czy pokazuje nową treść?
- To samo po naciśnięciu przycisku zasilania i po restarcie ekranu.

### E8 — Zasilanie, usypianie, budzenie

- Zużycie baterii przez 24 h: network standby **wł.** vs **wył.** (`uv run frame device standby true|false`).
- `uv run frame device sleep`, a następnie `uv run frame device wake`. Po ilu sekundach MDC odpowiada?
- Czy na baterii ekran sam przechodzi w uśpienie? Po jakim czasie? Czy budzi się na WoL?

### E9 — Odświeżanie panelu

- Czas pełnego odświeżenia, ghosting po wielu zmianach, zachowanie „odświeżania co 3 dni” (ochrona panelu).
- Odczytaj `raw 0x25` (on timer). Czy da się ustawić codzienne budzenie lub odświeżanie przez MDC?

### E10 — Błędy i odporność

- Zatrzymaj serwer i wybudź ekran. Co pokazuje: stary obraz czy „Configuration error”?
- Odpowiedź 404 albo 500 dla `content.json` lub obrazu.

### E11 — Limity

- Długość URL (limit 252 znaki wynika z ramki MDC), adres `https://` w `image_url`, wolny serwer (timeouty).

### E12 — Współistnienie z aplikacją Samsung E-Paper

- Czy wysłanie czegoś z aplikacji Samsunga nadpisuje nasz URL? Czy aplikacja zmienia PIN?

### E13 — Budzenie na baterii

Budzik ekranu (`uv run frame device timer HH:MM`), Wi-Fi 2,4 GHz i WoL, przycisk,
ładowarka. Plan krok po kroku w [WAKE.md](WAKE.md#e13-plan-testu-na-ekranie).

### E14 — Strojenie na oko (plansze porównawcze)

- Jedna plansza 2560×1440 = sześć kafelków 3×2, każdy to inny wariant tych samych kadrów (dwa obrazy obok siebie), podpisany literą. Wysyłana `--raw`, więc kafelki passthrough ditheruje ekran, a kafelki `dither` zostają w czystych farbach 1:1 (E5). Obok, na ekranie telefonu, wzorzec: te same kadry bez obróbki.
- Ocena subiektywna w świetle pokoju: najlepszy wariant, ewentualnie „za mało / za dużo”, i kolejna plansza wokół zwycięzcy. Obrazy z AIC i Wikimedia Commons, różne style: zdjęcia (portrety, góry), olej, drzeworyt, plakat, miedzioryt, zdjęcie cz-b.

---

## Wyniki

| Eksp. | Data | Firmware | Wynik / obserwacje | Zdjęcia |
|---|---|---|---|---|
| E1 | 2026-10-25 | 1130.7 | Połączenie z PIN-em działa (otwarcie sesji TLS ok. 5 s). Samsung EMDX 224B, SN `0WMUHNPY900224B`. Bateria `73 00 01 01 64 02 02` z ładowarką, `… 64 02 00` bez: ostatni bajt = zasilanie USB-C, `payload[4]` = %. Przy 100% `payload[1]` = `00` także z ładowarką (ładowania poniżej 100% jeszcze nie sprawdzono). `0x25` → `00`, `0xA7` → zegar (format w DEVICE_PROTOCOL), `0x10` → `02 7a 01`. | – |
| E2 | 2026-10-25 | 1130.7 | **M0 osiągnięty.** `0xC7` → GET `content.json` po 0,25 s → GET obrazu zaraz potem. Odświeżanie (JPEG): pobranie 00:11:56, miganie 00:12:08–00:12:39, czyli ok. 12 s przygotowania i 31 s odświeżania. Brak User-Agenta, tylko `Accept: */*`, bez `Range` / `If-Modified-Since`. | – |
| E3 | 2026-10-25 | 1130.7 | PNG i JPEG działają. JPEG 13 MB działa (miganie od 11 s po pobraniu, 36 s). 1920×1080 `--raw`: skalowany na cały ekran. 1440×2560 `--raw`: wpasowany z zachowaniem proporcji, wąski pas z szarymi bokami, bez obracania. | – |
| E4 | 2026-10-25 | 1130.7 | Ekran nie obraca obrazu sam (E3). Docelowo raczej pion, z przełącznikiem orientacji w aplikacji. Wariantów `orientation` / `rotation` jeszcze nie testowano. | – |
| E5 | 2026-10-25 | 1130.7 | **1. Szachownice 1 px odtworzone 1:1, czyste farby.** 2. Gradienty: ekran sam ditheruje szumem (dyfuzja błędu), mocno przycina kolory spoza farb (cyjan → biały, magenta → czerwień, średnia szarość z fioletowym odcieniem). Kalibracja palety lampą światła dziennego: wbudowana paleta `em32dx` w `server/src/frame_server/imaging/palette.py`, teraz domyślna (czerń granatowa, żółta ciemniejsza, niebieska jaśniejsza niż w palecie domyślnej). 3. Zdjęcie (dziecko w lesie, preset `photo`): `passthrough` wygląda najlepiej; `compensate` odpada (przesycony, twarz czerwona); `dither` ma czystszy raster, ale jest wyprany; `dither` z `saturation=1.7 contrast=1.3 shadows=0.15 gamma=1.0` lepiej, nadal słabiej niż `passthrough`. **Decyzja techniczna: `dither` (piksele 1:1), ale strojenie mapowania tonów i gamutu (1.3/1.4) musi dogonić `passthrough`; do tego czasu `passthrough` jest bezpiecznym domyślnym.** | – |
| E6 | | | | |
| E7 | 2026-10-25 | 1130.7 | Wstępnie: po wybudzeniu przyciskiem ekran **nie** pobrał ponownie `content.json`. Test 24 h do zrobienia. | – |
| E8 | 2026-10-25 | 1130.7 | Po odłączeniu ładowarki ekran od razu zniknął z sieci (ping i MDC). WoL (network standby wł.) przez Wi-Fi nie obudził go przez 2 min; krótkie naciśnięcie przycisku budzi (miga zielona dioda z tyłu, obraz bez zmian), MDC wraca po kilku sekundach. Pomiar 24 h do zrobienia. | – |
| E9 | | | | |
| E10 | | | | |
| E11 | | | | |
| E12 | | | | |
| E13 | 2026-10-26 | 1130.7 | Krok 5 (WoL na 2,4 GHz): ekran **na baterii**, uśpiony, z network standby wł., zostaje połączony z Wi-Fi (UniFi go widzi). Aplikacja WoL na iPhonie w tej samej podsieci (broadcast, port 7) go budzi. Serwer nie budził przez błąd w kodzie (uvloop bez `sock_sendto`, zob. WAKE.md). Budzik `0x25` jeszcze niesprawdzony. | – |
| E14 | 2026-10-25 | 1130.7 | 12 plansz. **Passthrough z korektą wygrał z naszym ditherem w każdym stylu.** Wyjściowy problem: za dużo niebieskiego i zieleni w jasnych partiach. 1. Jasne partie: odbarwienie do 0.55 (rampa L 0.55–0.9) i punkt bieli 0.93 (L ≥ 0.93 → biel papieru); same ocieplenie pomagało mniej. 2. Zdjęcia: nasycenie i kontrast +5% (+10% już za dużo). 3. Malarstwo: passthrough lepszy niż nasz dither (także z poprawką jasnych), ale bez korekty za ciemny; γ 1.1 i podniesione jasne partie (`highlights` −0.15). 4. Grafika (Hokusai, Toulouse-Lautrec): jak malarstwo, plus nasycenie i kontrast +10%; nasz dither Atkinson/F-S słabszy. 5. Cz-b: nasz dither z czerni i bieli ma dobrą szarość, ale passthrough w szarościach płynniejsze przejścia i głębię; wygrał passthrough, kontrast +10%, wyostrzenie 0.9, szarość przesunięta od zieleni (OKLab a +0.012) i odrobinę chłodniej (b −0.006). 6. Ta sama korekta w kolorze: najlepiej połowa, tylko w szarych miejscach (chroma < 0.06). 7. Białe passe-partout: dolna i prawa faza zlewała się z kartonem; z sześciu linii załamania (plansza 13, wycinki 1:1) wygrała 1 px z co drugim pikselem czarnym, dookoła całego okna i na każdym kartonie. Na czarnym kartonie białe kropki były za mocne; wygrały na przemian biała i niebieska co drugi piksel (plansze 14–15, Vermeer). Wartości są w presetach (`pipeline.py`) i w `mat.py`. | – |
