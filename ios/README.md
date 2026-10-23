# Frame — aplikacja iOS

SwiftUI, iOS 17+. Projekt Xcode jest generowany z `project.yml` przez
[XcodeGen](https://github.com/yonaskolb/XcodeGen) i nie trafia do repozytorium.

```bash
brew install xcodegen
xcodegen generate
open Frame.xcodeproj
```

Przed pierwszym uruchomieniem na iPhonie wybierz w Xcode swój zespół
(*Signing & Capabilities*) albo wpisz `DEVELOPMENT_TEAM` w `project.yml`.
Zmień też `PRODUCT_BUNDLE_IDENTIFIER`, jeśli chcesz użyć własnego.

## Co już jest

- **Teraz**: podgląd tego, co jest na ramce (symulacja wyglądu na e-papierze), tytuł, opis, źródło; „Wyślij ponownie”.
- **Wyślij**: wybór zdjęcia z biblioteki, styl (Zdjęcie / Obraz / Grafika / Czarno-białe), wysyłka na ramkę.
- **Ustawienia**: adres serwera (np. `http://homeassistant.local:8099`), token API (w Keychain), stan ekranu (bateria, firmware).

Kolejne funkcje opisuje Etap 3 w [../docs/PLAN.md](../docs/PLAN.md).

## Struktura

```
Frame/App/          FrameApp, AppModel (@Observable), KeychainStore
Frame/Model/        modele odpowiedzi API
Frame/Networking/   FrameAPI (URLSession, multipart)
Frame/Views/        RootView, NowPlayingView, SendView, SettingsView
FrameTests/         testy dekodowania i zapytań
```
