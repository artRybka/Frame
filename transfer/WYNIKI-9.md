# Runda 9: mniej szczegółów w całym rysunku

Model jak w r7 i r8: FLUX.2 klein 9B + LoRA frmstudy-2 w skali 2 (fal `flux-2/klein/9b/edit/lora`), potem lokalnie C16.
To samo 12 dzieł co w r8, to samo ziarno i ten sam rozmiar wyniku co obecny rysunek. Polecenie jak w r7, bez dopisków o twarzach.

**Koszt:** 1,13 USD (36 wywołań po 0,015–0,045 USD), limit 2 USD. C liczy się lokalnie, 0 USD.

## Warianty
- **A:** dzieło wysłane po zmniejszeniu do 512 px dłuższego boku (Lanczos), wynik w obecnym rozmiarze.
- **B:** to samo przy 384 px.
- **C:** lokalnie na obecnym rysunku: black-hat na L, z kresek piórka usunięte składowe krótsze niż 2,5% dłuższego boku albo cieńsze niż ok. 1,5 px. W ich miejsce wchodzi plama spod spodu (inpaint Telea). Długie kontury i plamy zostają.
- **D:** na samym początku polecenia: „Draw it general and simplified, the way a painter's quick study is: only the big shapes and their main contour lines, no small details anywhere, no texture, no individual strands, folds, leaves or features drawn one by one.”, dalej polecenie r7. Wejście w pełnej rozdzielczości.

## Mediany (C16 wobec dzieła, impression.py r5; kreska = piksele kresek piórka wobec obecnego rysunku)
| | masy | barwa ° | nasycenie | ciemność | papier % | cieniowanie | kreska |
|---|---|---|---|---|---|---|---|
| obecny | 0,77 | 1,65 | 0,81 | 13,3 | 24,4 | 1,38 | 1,00 |
| A 512 | 0,77 | 1,60 | 0,83 | 13,5 | 24,8 | 1,38 | 1,02 |
| B 384 | 0,77 | 1,60 | 0,85 | 13,5 | 24,3 | 1,39 | 1,01 |
| C bez drobnych kresek | 0,77 | 1,65 | 0,81 | 14,3 | 24,9 | 1,25 | 0,74 |
| D zdanie | 0,72 | 1,45 | 0,83 | 16,5 | 28,3 | 1,10 | 0,76 |

## Na oko (M-mniej.jpg, M-mniej-zblizenia.jpg)
- **A i B nie zmieniają prawie nic.** Model sam rysuje szczegóły w rozmiarze wyjścia, więc mniejsze wejście nie daje mniej kresek (kreska 1,01–1,02). Rysunki są niemal takie same jak obecne, z drobnymi różnicami w twarzach. Niczego nie zmyślił, ale też nic nie zyskujemy.
- **C usuwa kreski mechanicznie i trafia w to, co ważne.** Znikają zmarszczki, pojedyncze włosy i ziarno akwareli (Rembrandt, Homer i Wyspiański wyglądają spokojniej), ale znikają też **oczy i usta** (u Hoppera i Boznańskiej twarz jest pusta), kaligrafia na portretach samurajów (kreska 0,25) i ucho u Cassatt, gdzie zostaje przy tym jasna łata. Ten wariant odradzam, chyba że z ochroną twarzy i pisma.
- **D faktycznie uogólnia cały rysunek:** mniej pasm włosów i brody (Rembrandt, Homer, Manet), prostsze fałdy, jaśniej, więcej papieru, mniej cieniowania. Twarze zachowują oczy i usta, tylko prostsze. Wady:
  - Kilka rzeczy model pomija albo zmienia. Kaligrafii u samurajów nie ma wcale. W „Las Meninas” ciemne masy postaci i ścian są dużo jaśniejsze (masy 0,60 → 0,43), a postać po prawej wygląda inaczej. U Boznańskiej tło za oknem jest bledsze. Twarz Delacroix i Mleczarki ma trochę inny wyraz.
  - Wymyślonych przedmiotów ani postaci nie widzę. Ryzyko polega na opuszczaniu (pismo, ciemne tło), nie na dodawaniu.

## Co polecam
Z tych wariantów do celu „mniej szczegółów” najbliżej jest **D**. Jest tani (tyle co obecny rysunek), ale potrafi zgubić ważny drobny element (pismo) i rozjaśnia ciemne obrazy. Do sprawdzenia w następnej rundzie:
1. **D przy skali LoRA 1,5** albo z łagodniejszym zdaniem: czy zachowa ciemne masy.
2. **D z dopiskiem** „inscriptions and calligraphy stay as written”.
3. **C z ochroną:** bez usuwania w twarzach (Apple Vision, jak w r8b) i w polach z pismem. Koszt 0 USD.

Skrypty: `lokalny-model/r9/` (run9.py, measure9.py, board9.py). Kolumny plansz: dzieło | obecny | A 512 | B 384 | C | D.
