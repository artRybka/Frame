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
importerem serwera), z kolorami i tagami. Obrazy ładują się z CDN muzeów.
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

## Struktura

```
Frame/App/          FrameApp, AppModel (@Observable), KeychainStore
Frame/Design/       Theme (kolory, typografia, nazwy), komponenty
Frame/Model/        modele API (zgodne z serwerem)
Frame/Networking/   FrameBackend: LiveBackend (HTTP), DemoBackend, ImageLoader
Frame/Views/        Now, Discover, Playlists, FrameTab, RootView
FrameTests/         dekodowanie, zapytania, tryb demo
```
