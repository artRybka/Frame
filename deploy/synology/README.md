# Frame na Synology (obok Home Assistant Container)

Ten sam obraz co add-on HA, uruchamiany jako zwykły kontener.

1. Na NAS-ie utwórz folder, np. `/volume1/docker/frame`, i skopiuj do niego
   `docker-compose.yml` oraz `frame.env.example` jako `frame.env`.
   Uzupełnij `frame.env` (token API; IP, PIN i MAC ekranu można wpisać tu
   albo później w aplikacji: Ramka → trybik → Połączenie z ekranem).
2. *Container Manager → Projekt → Utwórz*, wskaż ten folder i
   `docker-compose.yml`, a następnie uruchom.
3. Sprawdź `http://<IP NAS>:8099/api/health`.

Uwagi:

- Kontener działa w sieci hosta (`network_mode: host`), bo ekran pobiera
  obrazy z adresu NAS-a, a Wake-on-LAN wymaga broadcastu w sieci lokalnej.
  Port 8099 nie może być zajęty przez inną usługę.
- Dane (biblioteka, bieżący obraz, podglądy, log zapytań ekranu)
  trafiają do `./data`. Warto objąć ten folder kopią zapasową (Hyper Backup).
- Obraz `ghcr.io/artrybka/frame` publikuje GitHub Actions po każdym scaleniu
  do `main` (`.github/workflows/publish.yml`). Pakiet jest publiczny, więc NAS
  pobiera go bez logowania.
- Aktualizacja z aplikacji: *Ramka → trybik → Konfiguracja → Serwer ramki →
  Aktualizuj serwer*. Robi to kontener `frame-updater` z tego samego pliku
  (sekcja `updater`): co 6 godzin (i po *Sprawdź*) pobiera nowy obraz,
  a na prośbę aplikacji tworzy kontener `frame` na nowo z tymi samymi
  ustawieniami. Jeśli nowy nie wystartuje, wraca poprzedni. Na koniec
  podmienia też sam siebie.
- Pomocnik ma dostęp do Dockera (`/var/run/docker.sock`), ale nie ma sieci
  (`network_mode: none`) ani portu: obraz pobiera sam Docker, a polecenie
  dostaje tylko od serwera Frame (plik w `data/update`, zlecany przez API
  z tokenem). Zmienia wyłącznie kontener `frame`. Montuje cały folder
  `data`, bo Docker na Synology nie tworzy brakującego folderu do
  zamontowania (błąd „Bind mount failed: … does not exist”).
- *Kompiluj* (*Container Manager → Projekt → frame → Akcja → Kompiluj*)
  potrzebne jest już tylko po zmianie `docker-compose.yml` lub `frame.env`.
  Dzięki `pull_policy: always` sama pobiera nowy `latest`. Odpowiednik
  z wiersza poleceń: `docker compose up -d`.
- Projekt utworzony ze starszej wersji pliku (bez sekcji `updater`) trzeba
  raz poprawić: *Projekt → frame → Akcja → Zatrzymaj*, potem w zakładce
  *Konfiguracja YAML* kliknij *Edytuj*, wklej cały aktualny
  `docker-compose.yml`, zapisz i kliknij *Kompiluj*. W kontenerach projektu
  pojawi się `frame-updater`, a w aplikacji przycisk *Aktualizuj serwer*.

## Dostęp spoza domu (Tailscale)

Serwer nie powinien być wystawiony do internetu. Aplikacja łączy się z nim
spoza domu przez Tailscale:

1. Na NAS-ie zainstaluj pakiet *Tailscale* z Centrum pakietów i zaloguj go
   na swoje konto. Kontener działa w sieci hosta, więc serwer od razu
   odpowiada pod adresem Tailscale NAS-a (`100.x.y.z`, widocznym w panelu
   Tailscale) na porcie 8099.
2. Na iPhonie zainstaluj aplikację Tailscale na to samo konto.
3. W aplikacji Frame: *Ramka → trybik → Serwer ramki*, w polu *Spoza domu*
   wpisz `http://100.x.y.z:8099` (albo nazwę MagicDNS, np.
   `http://nas.tailXXXX.ts.net:8099`) i stuknij *Połącz*.

Aplikacja sama wybiera adres, który odpowiada; domowy ma pierwszeństwo. Pod
przyciskiem *Połącz* widać, którędy jest połączona („w domu” albo „spoza
domu”). Poza domem Tailscale na iPhonie musi być włączony.

## Powiadomienia na telefonie

Serwer wysyła powiadomienia sam, przez Apple (APNs, `api.push.apple.com`,
port 443), więc NAS potrzebuje tylko zwykłego wyjścia do internetu. Raz:

1. developer.apple.com → Certificates, IDs & Profiles → Keys → „+”, zaznacz
   **Apple Push Notifications service (APNs)**, środowisko **Sandbox &
   Production**, zakres **Team Scoped**; pobierz `AuthKey_XXXXXXXXXX.p8`
   (da się tylko raz).
2. W aplikacji: Ramka → trybik → Konfiguracja → Powiadomienia → „Włącz
   powiadomienia”, potem „Dodaj klucz z Plików”. Serwer trzyma go w
   `data/push/` (nie w repozytorium).
3. „Wyślij próbne powiadomienie”: przy błędzie widać odpowiedź Apple.
