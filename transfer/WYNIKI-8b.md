# Runda 8b: D + porwane linie obecnego rysunku w twarzach

Lokalnie, **0 USD** (bez fal). Na wynikach r8: wariant D (twarz = pusty owal z plamą cienia) połączony z obecnym rysunkiem (r7/r4) tylko w obszarze twarzy, potem C16 jak dotąd.

## Jak
- **Twarze:** Apple Vision (`VNDetectFaceRectanglesRequest`, offline) znalazł je w 10 z 12 dzieł (w „Las Meninas” i u samurajów po dwie). Ręcznie: Cassatt (głowa od tyłu, same włosy) i Homer (profil pod kapeluszem).
- **Twarz:** owal na ramce twarzy, brzeg rozmyty (ok. 25% promienia), więc nie widać szwu. W nim zostaje D, a na nim kładę wąskie ciemne linie obecnego rysunku: black-hat na L (jądro ok. 9% szerokości twarzy, próg), porwane gładką maską szumu. Zostaje **30%** albo **50%** ich długości, w kawałkach kilku kresek, nie w kropkach.
- **Włosy i nakrycie głowy** (owal nad twarzą i wokół niej, bez samej twarzy) są zawsze z obecnego rysunku. U Cassatt cała głowa jest z obecnego rysunku, więc włosy wróciły.
- Łączę przed C16, potem C16 (r6c) na wyniku.

## Mediany (C16 wobec dzieła, 12 dzieł)
| | masy | barwa ° | nasycenie | ciemność | papier % | cieniowanie |
|---|---|---|---|---|---|---|
| obecny | 0,77 | 1,65 | 0,81 | 13,3 | 24,4 | 1,38 |
| D | 0,77 | 1,65 | 0,83 | 14,1 | 26,4 | 1,23 |
| D + linie 30% | 0,77 | 1,65 | 0,83 | 14,1 | 26,5 | 1,25 |
| D + linie 50% | 0,77 | 1,65 | 0,83 | 14,1 | 26,5 | 1,25 |

Twarz to mały kawałek obrazu, więc liczby całego dzieła się nie ruszają. Ocena tylko na oko.

## Na oko (L2-twarze-zblizenia.jpg)
- Twarz przestaje być pustym manekinem: zostaje kawałek brwi, oka, nosa i ust, ale bez portretowego wykończenia. Najlepiej wychodzi u Maneta, w „Żydówce” Gierymskiego, u Boznańskiej, Mleczarki i Delacroix.
- **30%** daje bardzo ogólną twarz, czasem prawie nieczytelną (Delacroix, Homer). **50%** daje szkicową, ale czytelną twarz. Polecam **50%**.
- Słabe strony: plamy różu z D na oczach (Gierymski, Boznańska) zostają i przy porwanych liniach wyglądają jak siniaki. Broda Homera i Maneta jest tylko z linii, bo w D jej nie ma. Wyspiańskiego i Hoppera D prawie nie zmienił, więc nie zmienia się też tu.
- Szwu na brzegu maski nie widać.

Skrypty: `lokalny-model/r8b/` (faces.swift, run8b.py, board8b.py). Kolumny planszy: dzieło | obecny | D | D + linie 30% | D + linie 50%.
