# Frame — aplikacja iOS

SwiftUI, iOS 17+, interfejs po polsku. Projekt Xcode jest generowany z
`project.yml` przez [XcodeGen](https://github.com/yonaskolb/XcodeGen) i nie
trafia do repozytorium.

```bash
brew install xcodegen
xcodegen generate
open Frame.xcodeproj
```

Przed pierwszym uruchomieniem na iPhonie wybierz w Xcode swój zespół
(*Signing & Capabilities*) albo wpisz `DEVELOPMENT_TEAM` w `project.yml`.

## Tryb demo

Bez serwera aplikacja startuje w **trybie demo**: ok. 40 prawdziwych dzieł
z kolekcji muzeów (`Frame/Resources/DemoLibrary.json`, wygenerowane
importerem serwera), z kolorami i tagami. Obrazy są wbudowane w aplikację
(`Frame/Resources/DemoImages`): oryginał 900 px i podgląd „na ramce”
wyrenderowany pipeline'em serwera (`<id>-frame.jpg`); gdy pliku brak,
aplikacja sięga do CDN muzeum.
Przełącznik jest w zakładce *Ramka → Serwer ramki*.

## Ekrany

- **Teraz**: obraz na ramce w „oprawie”, tło w kolorach dzieła, bateria i połączenie, poprzedni / przypnij / następny, opis jak etykieta w muzeum, dla zdjęć data, miejsce i kto dodał, następne i ostatnie obrazy. Przycisk **+** wysyła zdjęcie z rolki z wyborem, jak długo ma zostać.
- **Odkrywaj**: siatka biblioteki z filtrami (artyści, style, tematy, kolorystyka, ulubione), sortowanie; szczegóły dzieła z przełącznikiem *Oryginał / Na ramce* (symulacja e-papieru), paletą, „Pokaż na ramce”, ulubionymi i playlistami; wyszukiwanie w muzeach z importem.
- **Playlisty**: co gra teraz, kolekcje inteligentne (reguły z podglądem na żywo) i ręczne, odtwarzanie na ramce.
- **Ramka**: bateria, zasilanie i ładowanie, połączenie, czuwanie Wi-Fi, następna zmiana; harmonogram, prezentacja, orientacja ekranu, połączenie z serwerem.

## Zrzuty ekranów

Workflow `ios` w GitHub Actions uruchamia aplikację w trybie demo na
symulatorze i zapisuje zrzuty każdego ekranu (jasny i ciemny motyw) jako
artefakt `screenshots`. Lokalnie: argumenty uruchomienia `-demo YES -screen
discover` (dostępne: `now`, `discover`, `detail`, `museums`, `playlists`,
`playlist`, `editor`, `frame`, `send`).

## TestFlight

Jednorazowo:

1. **Team ID** (`3MQRJF4A9D`) jest już w `project.yml` jako `DEVELOPMENT_TEAM`
   (to nie jest sekret, widać go w każdej podpisanej aplikacji).
2. **Xcode → Settings → Accounts**: dodaj Apple ID konta deweloperskiego.
3. **Bundle ID**: *Certificates, IDs & Profiles → Identifiers → +* →
   *App IDs → App*, *Explicit*: `com.artrybka.frame`. Żadne dodatkowe
   uprawnienia nie są potrzebne.
4. **App Store Connect → Aplikacje → + Nowa aplikacja**: iOS, nazwa musi być
   unikalna w całym App Store („Frame” jest zajęte), np. „Frame – ramka
   e-papier”; na ekranie telefonu i tak będzie „Frame”. Język główny polski,
   Bundle ID jak wyżej, SKU np. `frame-ios`.

Każde wydanie:

1. `cd ios && xcodegen generate && open Frame.xcodeproj`
2. Cel *Any iOS Device (arm64)* → **Product → Archive**.
3. W Organizerze **Distribute App → App Store Connect** (w nowszym Xcode:
   *TestFlight & App Store*) → **Distribute**. Podpis i certyfikaty Xcode
   załatwia sam. Każdy upload potrzebuje wyższego numeru kompilacji; jeśli
   Xcode zgłosi, że taki już był, zwiększ `CURRENT_PROJECT_VERSION`
   w `project.yml`. Workflow `testflight` ustawia go sam na datę i godzinę
   (np. `2610241005`), więc jest zawsze wyższy niż wysłany ręcznie.
4. Po przetworzeniu (kilkanaście minut, przychodzi e-mail) build jest
   w zakładce **TestFlight**.

Bez Maca (np. z telefonu) build zrobi GitHub: workflow `testflight`
archiwizuje aplikację na maszynie macOS i wysyła ją do App Store Connect.
Uruchamia się po każdej zmianie w `ios/` na `main` albo ręcznie
(*Actions → testflight → Run workflow*). Potrzebny jest klucz API:

1. App Store Connect → **Użytkownicy i dostęp → Integracje → App Store
   Connect API** → klucze zespołu → **+**; nazwa „GitHub”, dostęp **Admin**
   (Xcode musi móc sam utworzyć certyfikaty). Za pierwszym razem trzeba
   kliknąć „Poproś o dostęp” i zaakceptować warunki.
2. Pobierz plik `AuthKey_XXXX.p8` (da się to zrobić tylko raz) i zanotuj
   *Key ID* oraz *Issuer ID* (nad listą kluczy).
3. GitHub → repozytorium → **Settings → Secrets and variables → Actions →
   New repository secret**, trzy sekrety: `ASC_KEY_ID`, `ASC_ISSUER_ID`
   i `ASC_KEY_P8` (cała zawartość pliku `.p8`, razem z liniami `BEGIN`/`END`).
   Na iPhonie: zapisz plik w aplikacji Pliki, zmień rozszerzenie na `.txt`,
   otwórz, zaznacz wszystko i skopiuj.

Klucz można w każdej chwili unieważnić w App Store Connect. Bez sekretów
workflow kończy się bez błędu i niczego nie wysyła.

Testerzy:

- **Ty**: *Internal Testing* → dodaj siebie; build jest od razu dostępny
  w aplikacji TestFlight.
- **Rodzina**: *External Testing* → grupa „Rodzina” → adresy e-mail ich Apple ID
  (albo link publiczny). Pierwszy build przechodzi Beta App Review (zwykle
  do doby). W *Test Information* podaj opis i e-mail do opinii, a w notatce
  dla recenzenta np.:

  > Frame controls a Samsung EM32DX colour e-paper display through the
  > user's own home server. Without a server the app starts in demo mode
  > with sample artworks from public museum collections, so every screen can
  > be explored. No sign-in is required.

Buildy w TestFlight wygasają po 90 dniach.

## Struktura

```
Frame/App/          FrameApp, AppModel (@Observable), KeychainStore
Frame/Design/       Theme (kolory, typografia, nazwy), komponenty
Frame/Model/        modele API (zgodne z serwerem)
Frame/Networking/   FrameBackend: LiveBackend (HTTP), DemoBackend, ImageLoader
Frame/Views/        Now, Discover, Playlists, FrameTab, RootView
FrameTests/         dekodowanie, zapytania, tryb demo
```
