# Runda 8: ogólniejsze twarze

Model jak w r7: FLUX.2 klein 9B + LoRA frmstudy-2 (fal, `fal-ai/flux-2/klein/9b/edit/lora`), potem C16 (r6c) lokalnie.
12 dzieł z twarzami (9 z r7, 3 z testów r4: Boznańska, Manet „Żebrak”, Vermeer „Mleczarka”).
Każdy wariant ma to samo ziarno i rozmiar co obecny rysunek, więc różnice biorą się tylko z polecenia (albo skali LoRA).

**Koszt:** 2,25 USD (75 wywołań po 0,015–0,045 USD), limit 2,5 USD.

## Warianty
- **A:** dopisek na końcu: „Faces and hands are only suggested … no eyes, lips or nostrils drawn in detail …”.
- **B:** A + „A quick, loose sketch: broken, searching pen lines …”.
- **C:** B przy skali LoRA 1,5.
- **D:** na *początku* polecenia: „Every face is a blank oval of pale skin wash with one soft shadow patch, featureless like a mannequin; hands are simple mitten shapes. Loose, broken, unfinished pen lines, open edges.”
- E (D przy skali 1,0) i F (łagodniejsze D: „jedna kreska brwi i nosa, bez oczu i ust”) poszły tylko do sprawdzenia, nie ma ich na planszach.

## Mediany (C16 wobec dzieła, impression.py r5, 12 dzieł)
| | masy | barwa ° | nasycenie | ciemność | papier % | cieniowanie |
|---|---|---|---|---|---|---|
| obecny | 0,77 | 1,65 | 0,81 | 13,3 | 24,4 | 1,38 |
| A | 0,77 | 1,60 | 0,82 | 13,4 | 26,3 | 1,36 |
| B | 0,75 | 1,60 | 0,81 | 14,1 | 26,4 | 1,33 |
| C | 0,78 | 1,35 | 0,84 | 13,6 | 23,5 | 1,46 |
| D | 0,77 | 1,65 | 0,83 | 14,1 | 26,4 | 1,23 |
| E | 0,82 | 1,55 | 0,88 | 11,4 | 16,8 | 1,60 |
| F | 0,77 | 1,60 | 0,85 | 14,9 | 26,2 | 1,19 |

W żadnym wariancie układ mas ani barwa się nie zmieniają: A, B, C, D, F trzymają się obecnego.
E (skala 1,0) daje mniej papieru i więcej cieniowania, czyli mniej „studium”.

## Ocena na oko (L-twarze-zblizenia.jpg)
- **A, B, C:** prawie takie same jak obecny rysunek. Przy skali 2 LoRA zagłusza dopisek na końcu polecenia, a na 1,5 też niewiele to zmienia. Twarze dalej mają oczy, usta i podobieństwo. „Luźniej” z B nie widać.
- **D** to jedyny wariant, który faktycznie upraszcza twarze: zostaje owal z plamą różu i cienia (Gierymski, Boznańska, Manet, Homer, Delacroix, Mleczarka), a reszta obrazu się nie zmienia. Wad jest kilka. Wychodzi na to manekin, a nie szkic, czasem jest pustawo. U Cassatt znikły włosy (wyszła łysa głowa). Wyspiańskiego i Hoppera prawie nie ruszyło.
- **F** (łagodniej niż D) wrócił do pełnych twarzy. Polecenie działa więc tylko wtedy, gdy mówi stanowczo „pusty owal”.

## Co polecam
Z tych wariantów najbliżej celu jest **D**, ale to rozwiązanie zero-jedynkowe: albo pełna twarz, albo pusty owal, „kilku luźnych kresek” model nie robi. Żeby dostać naprawdę szkicową twarz, polecam jedną z dwóch dróg:
1. **D + kilka kresek lokalnie:** w miejscu twarzy (wykrytej w dziele) wziąć z obecnego rysunku jego linie piórka, rozjaśnione i porwane, i nałożyć je na D. Koszt 0 USD, wynik powtarzalny.
2. **Nowa LoRA:** pary treningowe z uogólnionymi twarzami (kilka USD). Najpewniejsza droga do „ogólniejszego rysunku” w całym obrazie, nie tylko w twarzach.

Pliki: L-twarze.jpg (całe dzieła), L-twarze-zblizenia.jpg (twarze). Kolumny: dzieło | obecny | A | B | C | D.
