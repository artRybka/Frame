# Frame — add-on

Serwer ramki dla ekranu Samsung EM32DX. Przygotowuje obrazy pod e-papier
Spectra 6, serwuje je ekranowi i steruje nim po sieci lokalnej (protokół
MDC). Z serwerem łączy się aplikacja iOS.

## Konfiguracja

| Opcja | Opis |
|---|---|
| `device_host` | Adres IP ekranu (warto ustawić stały adres w routerze) |
| `device_pin` | PIN do MDC, wyświetlany na ekranie podczas parowania w aplikacji Samsung E-Paper |
| `device_mac` | MAC ekranu, potrzebny do budzenia (Wake-on-LAN) |
| `port` | Port HTTP, z którego ekran pobiera obrazy (domyślnie 8099) |
| `public_host` | Adres, pod którym ekran widzi Home Assistanta; wykrywany automatycznie, gdy puste |
| `api_token` | Token dla aplikacji iOS i narzędzi (zalecany) |
| `palette` | Nazwa wbudowanej palety albo ścieżka do skalibrowanej palety JSON (np. `/data/palette.json`) |

Adres IP, PIN i MAC ekranu można też ustawić w aplikacji (Ramka → trybik →
Połączenie z ekranem). Zapisane tam mają pierwszeństwo przed opcjami
add-onu i przetrwają restart; „Przywróć wartości z serwera” wraca do opcji.

Dane (aktualny obraz, podglądy, log zapytań ekranu) trafiają do `/data`
add-onu, więc przetrwają restart. Ekran zapamiętuje adres
`http://<HA>:8099/panel/content.json` i pobiera go ponownie, np. po
wybudzeniu. Dlatego add-on powinien działać stale.

## API

Dokumentacja OpenAPI: `http://<HA>:8099/docs`.
