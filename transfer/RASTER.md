# Raster druku a restaurator: sprawdzenie `imaging/descreen.py`

Sprawdzałem kod z gałęzi `claude/project-thread-unv22h` (7231eb23) na Macu, na obrazach z NAS-a. Koszt 0 USD, w repo nic się nie zmieniło.

## Valtat „Bateaux au port” (paris:206689), plansza `valtat.jpg`
- Restaurator rysuje z fotografii muzeum (Paris Musées), która ma **595×485 px**. Karta podaje 300×245, ale to rozmiar miniatury. Kopia po restauracji ma 2061×1680, czyli ×3,46.
- **Raster jest już w źródle**, tylko słaby i prawie na granicy rozdzielczości. To ukośna siatka o okresie **ok. 2,0–2,2 px**: punkty w widmie (0,40; ±0,30) i (0,35; ±0,30) cykli/px. Wystają tylko **1,4–1,6** ponad otoczenie, a próg `STANDS` to 3,0. Część punktów jest też drobniejsza niż `FINEST` = 2,2.
- **`screen()` zwraca 0 punktów, więc `descreened()` nic nie zmienia.** Dla Valtata ta zmiana by nie pomogła. Restaurator powiększa ten ślad do ostrej siatki o okresie ok. 7 px. W kopii wystaje ona 2,3–3,0, więc i tam jest poniżej progu.
- Z luźniejszymi progami (`FINEST` 1,9, `STANDS` 1,5) Valtat jest wykrywany (4 punkty), a drobne ziarno znika (panel 3, obraz robi się lekko miększy). Te same progi łapią jednak **220 z 238** dzieł z próby, więc w tej postaci są bezużyteczne.

## Fałszywe trafienia, plansza `trafienia.jpg` (wycinki 1:1 ×3, przed | po)
- Próba: **238 dzieł zapisanych na NAS-ie** (playlisty i ulubione, z różnych źródeł: wmc 66, wikiart 57, cma 26, met 22, aic 17, europeana 16, własne 15, rijks 6, paris 4 i inne) oraz **13 już restaurowanych**. Losowe dzieła z katalogu pominąłem, bo NAS ściągał każde z muzeum 10–50 s.
- Trafienia przy progach z gałęzi: **18/238 (7,6%)** oraz **1/13** restaurowanych (Hopper „Chair Car”, nie Valtat).
- Na oko:
  - **Prawdziwy druk (raster):** 3 Van Gogh „Three Sunflowers”, 6 „Self Portrait in the Studio”, 7 „Palazzo Da Mula Morosini”, 10 Kahlo „The Wounded Deer”, 12 „Portrait of a man”, 17 Kahlo „The Two Fridas”, prawdopodobnie też 2 „Job” i 4 „Strange travelers”. Wszystkie to reprodukcje z WikiArt/WMC. Po zmianie wyglądają wyraźnie lepiej.
  - **Splot płótna albo faktura:** 11 i 14 to jego własne zdjęcia (upload), 15 MNK „Szermierka”, 19 „Turin Spring”, 8 „Studium postaci w plenerze”. Splot znika, co raczej pomaga.
  - **Bez widocznej zmiany:** 1 Hopper „Chair Car”, 5 „Nymphs”, 9 „The Prodigal Son”, 13 Monet „Val-Saint-Nicolas”, 16 CMA „Hours of Queen Isabella” (pergamin, okres 11,9 px), 18 Cézanne „The Large Bathers”.
- **Gorzej po zmianie:** w środku obrazu nic. Na brzegach tak: filtr działa na FFT, które zawija obraz, więc wzdłuż krawędzi powstaje pasek i ringing. Najmocniej w 17 („Two Fridas”, widoczna ramka) i w 6: średnia różnica na brzegu 14–22 poziomów, w 99. percentylu do 78. Środek obrazu zmienia się mniej. Rada: przed FFT dodać lustrzane odbicie obrazu (`cv2.copyMakeBorder` z `BORDER_REFLECT`) albo przyciemnić brzeg oknem.

## Czas i pamięć `descreened` (Mac, M-series)
- 4096×3338: **4,2 s**, przy tym **ok. 1 GB** RAM ponad sam obraz (complex128 `fft2` na każdy z trzech kanałów).
- Obrazy z trafień (566–4000 px): 0,24–3,8 s. Samo `screen()` trwa poniżej 0,1 s.
- Na NAS-ie będzie to pewnie 2–4× wolniej. Biorąc pod uwagę zawieszenie serwera z 20.11 (brak pamięci), radzę liczyć w float32 (`scipy.fft.rfft2`) albo ograniczyć obraz do ok. 2048 px przed filtrem.

## Wnioski
1. Na tym, co ma łapać, czyli na reprodukcjach druku, detektor działa dobrze i nie zepsuł żadnego środka obrazu. Tyle że **siatki Valtata nie wykrywa**: w źródle 595 px raster jest już prawie na granicy rozdzielczości i bardzo słaby.
2. Samo obniżenie progów odpada, bo łapie prawie wszystko. Żeby wykrywać takie przypadki jak Valtat, potrzeba innego kryterium. Możliwości: (a) szukać siatki w wyniku restauratora (tam ma ok. 7 px i jest wyraźniejsza), ale z próbą fałszywych trafień na kopiach; (b) wymagać, żeby punkty tworzyły siatkę z harmonicznymi, zamiast stosować sam próg wysokości; (c) przy małym źródle, poniżej ok. 800 px, lekko rozmyć wejście restauratora powyżej ok. 0,35 cykla/px.
3. Przed wdrożeniem warto naprawić brzegi (lustrzane odbicie) i pamięć.
