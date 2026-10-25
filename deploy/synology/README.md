# Frame na Synology (obok Home Assistant Container)

Ten sam obraz co add-on HA, uruchamiany jako zwykły kontener.

1. Na NAS-ie utwórz folder, np. `/volume1/docker/frame`, i skopiuj do niego
   `docker-compose.yml` oraz `frame.env.example` jako `frame.env`.
   Uzupełnij `frame.env` (IP, PIN i MAC ekranu, token API).
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
- Aktualizacja: *Container Manager → Projekt → frame → Akcja → Kompiluj*.
  Dzięki `pull_policy: always` w `docker-compose.yml` kompilacja sama pobiera
  nowy `latest`, nie trzeba wcześniej usuwać ani aktualizować obrazu.
  Odpowiednik z wiersza poleceń: `docker compose up -d`.
- Projekt utworzony ze starszej wersji pliku (bez `pull_policy`) trzeba raz
  poprawić: *Projekt → frame → Akcja → Zatrzymaj*, potem w zakładce
  *Konfiguracja YAML* kliknij *Edytuj*, dopisz pod linią `image:`
  wiersz `pull_policy: always` (z tym samym wcięciem), zapisz i kliknij
  *Kompiluj*. Można też podmienić plik w folderze projektu przez File Station.
