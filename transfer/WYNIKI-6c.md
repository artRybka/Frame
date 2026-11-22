# Runda 6c: barwa 1,0 + podbite nasycenie, jasność nietknięta (2026-11-22)

**Koszt: 0 USD**, wszystko lokalnie na LoRA s2 z rundy 4. Skrypty: `r6/restore6c.py`, `measure6b.py`, `apron6b.py`, `board6c.py`; obrazy w `data/r6b/` (`*-C16.png`, `*-C20.png`).

## Werdykt
- **Polecam: barwa 1,0 + nasycenie do ×1,6 (`C16`).**
  - To najbliżej dzieła w barwie i nasyceniu, a kreska, papier i modelunek zostają jak u LoRA.
  - Mediany na 13 dziełach: barwa 1,6° (kolumna 4 z r6: 3,8°), nasycenie 0,82 (0,72), masy 0,76, ciemność +16, papier 24%, modelunek 1,62.
  - W każdej z tych liczb wynik jest bliżej dzieła niż Gemini (10° / 0,72).
- **Limit 2,0 daje praktycznie to samo co 1,6**, na planszy nie widać różnicy. Iloraz chromy dzieła do chromy wyniku w rozmytych masach prawie nigdzie nie przekracza 1,6, więc limit nie jest tu wąskim gardłem. Podbicie o 1,3 z 6b (przy barwie 0,75) dawało już 0,80. Większość zysku daje więc pełne przywrócenie barwy, nie sam limit.
- **Ciemne dzieła zostają za jasne** (ciemność +16). Bez ruszania L tego nie zmienię, bo tak zostało ustalone.

## Fartuch Mleczarki (maska jak w 6b: średnie w masce)

| | L | odcień ° | chroma |
|---|---|---|---|
| dzieło | 0,35 | −108 | 0,085 |
| Gemini | 0,62 | −115 | 0,060 |
| barwa 0,75, jasność 0 (kol. 4 r6) | 0,49 | −97 | 0,042 |
| barwa 0,75 + ×1,3 (6b) | 0,49 | −97 | 0,048 |
| **barwa 1,0 + ×1,6** | 0,49 | **−103** | **0,051** |
| barwa 1,0 + ×2,0 | 0,49 | −103 | 0,052 |

- Na oko fartuch jest wyraźnie bardziej ultramarynowy, mniej szarogranatowy.
- Do dzieła wciąż brakuje: chroma jest o 40% za niska, a odcień o 5° za bardzo w stronę cyjanu.
- Reszty nie naprawi przywrócenie na skali mas (sigma = dłuższy bok/40). LoRA kładzie w fartuchu jaśniejsze, mało nasycone pociągnięcia obok ciemnych, a rozmyta średnia zgadza się już z dziełem.
- Można by przywracać barwę na drobniejszej skali, ale wtedy zacznie zalewać kreskę.

Inne dzieła (nasycenie / barwa, kol. 4 → C16):
- Delft: 0,75 → 0,85 / 4,3° → 4,5°
- Hokusai: 0,52 → 0,62 / 7,8° → 5,7°
- Hopper: 0,49 → 0,67 / 6,0° → 5,1°
- Goya: 0,78 → 0,90 / 4,0° → 1,4°

## Pliki
- `J3-nasycenie.jpg`: 13 dzieł, kolumny: dzieło | Gemini | barwa 0,75 jasność 0 (kol. 4 r6) | barwa 0,75 + ×1,3 | barwa 1,0 + ×1,6 | barwa 1,0 + ×2,0.
- `J3-mleczarka.jpg`: Mleczarka w tych samych kolumnach, w powiększeniu.
