# frame-server

Serwer ramki: sterowanie ekranem Samsung EM32DX (MDC), serwowanie treści
(`content.json` + obraz), algorytm przygotowania obrazu dla e-papieru
Spectra 6 oraz CLI do eksperymentów. Szczegóły: `../docs/`.

```bash
uv sync                 # środowisko + zależności
uv run pytest           # testy
uv run frame --help     # CLI
```

Na Macu z katalogiem `Documents` w iCloud Drive iCloud oznacza pliki w `.venv`
jako ukryte, a Python 3.13 pomija ukryte pliki `.pth`, więc znika pakiet
`frame_server` (`ModuleNotFoundError`). Trzymaj środowisko poza iCloud, np.
`export UV_PROJECT_ENVIRONMENT=~/.venvs/frame`, albo doraźnie
`chflags nohidden .venv/lib/python3.13/site-packages/*.pth`.
