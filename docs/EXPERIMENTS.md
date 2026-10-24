# Eksperymenty z ekranem (Etap 0)

Protokół ekranu jest nieoficjalny. Opisały go projekty społeczności (patrz
[DEVICE_PROTOCOL.md](DEVICE_PROTOCOL.md)), ale wiele szczegółów trzeba
sprawdzić na Twoim egzemplarzu. Wyniki zapisuj w tabeli na dole albo w
`docs/experiments/EXX-*.md`, a zdjęcia ekranu wrzucaj do `docs/experiments/`.

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

---

## Wyniki

| Eksp. | Data | Firmware | Wynik / obserwacje | Zdjęcia |
|---|---|---|---|---|
| E1 | | | | |
| E2 | | | | |
| E3 | | | | |
| E4 | | | | |
| E5 | | | | |
| E6 | | | | |
| E7 | | | | |
| E8 | | | | |
| E9 | | | | |
| E10 | | | | |
| E11 | | | | |
| E12 | | | | |
| E13 | | | | |
