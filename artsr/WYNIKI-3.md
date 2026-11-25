# ArtSR: własny model powiększania na dziełach sztuki (2026-11-24/25, noc)

Próba, nic w aplikacji ani na serwerze nie zmienione. Koszt 0 USD (bez fal).
Wszystko liczone na Macu (M2 Pro, MPS). Wagi zostały lokalnie w `~/Frame-worktrees/artsr/ckpt/`.

## Co zrobiłem

- **Dane: 3590 dzieł z katalogu na NAS-ie** (1530 obrazów olejnych i tempera, 1030 grafik, 1030 rysunków i akwarel), tylko pozycje muzealne, bez własnych prac i FrameCam, bez dzieł już „odrestaurowanych” i z lepszą kopią. Pobierałem zdjęcie muzeum (`/full?side=2400`, po 3 naraz), a brałem tylko te, które miały co najmniej 2400 px dłuższego boku. Zdjęcia zmniejszyłem do 2048 px. Kategoria pochodzi z techniki na serwerze (`technique:*`), sprawdzonej jeszcze z techniką i klasyfikacją muzeum. Najwięcej dzieł dały NGA (1088), SMK (830), AIC (662), Smithsonian (619) i Yale (385). Na artystę przypada najwyżej 18 dzieł, razem 1839 artystów. Otwartych API muzeów nie trzeba było używać. Metadane są w `manifest.jsonl` (lokalnie). Pobieranie trwało ok. 2 h.
- **Pary.** HR to wycinki 256 px z dzieła w 2048 px. LR to to samo dzieło zmniejszone ×4 (losowo area, bicubic albo lanczos), czasem lekko rozmyte (30 %), czasem z rastrem druku 2–4 px (25 %), czasem z szumem (50 %), z JPEG q55–95, a potem przepuszczone przez `descreened` jak w produkcji. Na każde dzieło przypadają 2 zepsute kopie × 8 wycinków, w większości z miejsc z fakturą.
- **Modele.** Wszystkie mają budowę Photo M (PULSE 96×12, 2 mln parametrów) i startują z jego wag.
  - **ART** to model wspólny. Faza 1 (L1 + MS-SSIM) trwała 85 min i 20 556 kroków. Faza 2 (+ LPIPS-VGG 0,1 + PatchGAN 0,003) trwała 40 min i 2150 kroków.
  - **MAL, GRAF i RYS** to ART douczony przez 30 min (ok. 1600 kroków) tylko na swojej kategorii.
  - **STYL** to ART z FiLM na każdym bloku. Wektor to SigLIP 2 (te same wagi co serwerowe „looks”), liczony z całego zepsutego wejścia, plus kategoria. Trenował 60 min i 3002 kroki, ale część tego czasu dzielił procesor z oceną.
  - **Kontrola: ART + 30 min**, ta sama dawka douczania co u specjalistów, ale na wszystkich dziełach. Sprawdza, czy zysk specjalistów to podział, czy tylko dłuższy trening.
- **Test.** 8 starych dzieł (wejścia 600 px, prawda 2048, jak w `localsr/WYNIKI*.md`) i 24 nowe, po 8 na kategorię. Nowe zepsułem tak samo jak stare (600 px, JPEG 80, `descreened`). Wszystkie testowe dzieła i ich kopie z innych muzeów są wyjęte z treningu, tak samo wszystkie dzieła 12 artystów „nieobecnych”.
  - **Uwaga do grupy „obecni”.** Wybrałem ją przed końcem pobierania i wyszła słabo. W treningu są Hiroshige (18), Homer (17), Dürer (9), Rembrandt (7) i Goya (3), ale van Gogh tylko raz, a Ruisdaela i Halsa nie ma wcale.

Miary: PSNR, SSIM, LPIPS (alex, ↓), detal (korelacja górnoprzepustowa z prawdą, ↑) i ΔE OKLab ×100 (↓), wszystko przy 2048 px.

## Wyniki

**Wszystkie 32** (32 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.88 | 0.651 | 0.447 | 0.400 | 3.08 |
| Photo M (start) | 26.33 | 0.644 | 0.439 | 0.390 | 3.22 |
| ART po fazie 1 (L1+MS-SSIM) | 27.12 | 0.662 | 0.531 | 0.437 | 3.02 |
| ART | 26.82 | 0.647 | 0.366 | 0.393 | 3.14 |
| specjalista | 26.84 | 0.648 | 0.362 | 0.392 | 3.15 |
| STYL | 26.77 | 0.645 | 0.351 | 0.389 | 3.19 |
| ART+30 min (kontrola) | 26.83 | 0.647 | 0.367 | 0.393 | 3.14 |

**8 starych** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.81 | 0.629 | 0.483 | 0.422 | 3.20 |
| Photo M (start) | 26.52 | 0.624 | 0.477 | 0.412 | 3.32 |
| ART po fazie 1 (L1+MS-SSIM) | 26.99 | 0.639 | 0.573 | 0.450 | 3.11 |
| ART | 26.74 | 0.624 | 0.395 | 0.408 | 3.24 |
| specjalista | 26.74 | 0.624 | 0.386 | 0.408 | 3.25 |
| STYL | 26.64 | 0.623 | 0.390 | 0.403 | 3.31 |
| ART+30 min (kontrola) | 26.75 | 0.625 | 0.396 | 0.409 | 3.24 |
| SeedVR2 surowy | 24.05 | 0.529 | 0.307 | 0.271 | 4.44 |
| restaurator dziś | 25.35 | 0.576 | 0.330 | 0.303 | 3.77 |
| KH7 | 26.07 | 0.587 | 0.340 | 0.364 | 3.57 |

**24 nowe** (24 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.90 | 0.659 | 0.435 | 0.392 | 3.04 |
| Photo M (start) | 26.26 | 0.650 | 0.426 | 0.383 | 3.19 |
| ART po fazie 1 (L1+MS-SSIM) | 27.16 | 0.670 | 0.517 | 0.433 | 2.99 |
| ART | 26.85 | 0.655 | 0.357 | 0.388 | 3.11 |
| specjalista | 26.87 | 0.655 | 0.354 | 0.387 | 3.11 |
| STYL | 26.82 | 0.653 | 0.338 | 0.384 | 3.15 |
| ART+30 min (kontrola) | 26.86 | 0.655 | 0.357 | 0.388 | 3.11 |

**Malarstwo, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 29.57 | 0.690 | 0.457 | 0.335 | 2.52 |
| Photo M (start) | 29.13 | 0.681 | 0.452 | 0.326 | 2.62 |
| ART po fazie 1 (L1+MS-SSIM) | 29.84 | 0.693 | 0.564 | 0.378 | 2.62 |
| ART | 29.55 | 0.680 | 0.390 | 0.319 | 2.70 |
| specjalista | 29.56 | 0.680 | 0.385 | 0.318 | 2.70 |
| STYL | 29.53 | 0.673 | 0.383 | 0.320 | 2.78 |
| ART+30 min (kontrola) | 29.55 | 0.679 | 0.390 | 0.318 | 2.71 |

**Grafika, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 23.04 | 0.583 | 0.458 | 0.374 | 4.27 |
| Photo M (start) | 22.67 | 0.579 | 0.449 | 0.370 | 4.40 |
| ART po fazie 1 (L1+MS-SSIM) | 23.19 | 0.599 | 0.511 | 0.403 | 4.11 |
| ART | 22.97 | 0.585 | 0.369 | 0.372 | 4.25 |
| specjalista | 22.90 | 0.585 | 0.368 | 0.367 | 4.28 |
| STYL | 22.86 | 0.583 | 0.343 | 0.360 | 4.29 |
| ART+30 min (kontrola) | 22.98 | 0.586 | 0.371 | 0.373 | 4.25 |

**Rysunek i akwarela, nowe** (8 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 28.10 | 0.702 | 0.389 | 0.467 | 2.35 |
| Photo M (start) | 27.00 | 0.690 | 0.378 | 0.451 | 2.56 |
| ART po fazie 1 (L1+MS-SSIM) | 28.46 | 0.717 | 0.477 | 0.517 | 2.24 |
| ART | 28.03 | 0.700 | 0.310 | 0.473 | 2.37 |
| specjalista | 28.15 | 0.702 | 0.309 | 0.477 | 2.36 |
| STYL | 28.05 | 0.702 | 0.289 | 0.473 | 2.37 |
| ART+30 min (kontrola) | 28.05 | 0.700 | 0.310 | 0.473 | 2.37 |

**Artyści obecni w treningu** (12 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 27.60 | 0.661 | 0.426 | 0.402 | 2.87 |
| Photo M (start) | 26.82 | 0.650 | 0.417 | 0.391 | 3.05 |
| ART po fazie 1 (L1+MS-SSIM) | 27.82 | 0.670 | 0.513 | 0.443 | 2.91 |
| ART | 27.47 | 0.655 | 0.347 | 0.396 | 3.02 |
| specjalista | 27.49 | 0.656 | 0.347 | 0.396 | 3.02 |
| STYL | 27.43 | 0.651 | 0.330 | 0.395 | 3.09 |
| ART+30 min (kontrola) | 27.49 | 0.655 | 0.348 | 0.396 | 3.02 |

**Artyści nieobecni** (12 dzieł)

| Model | PSNR dB ↑ | SSIM ↑ | LPIPS ↓ | detal ↑ | ΔE OKLab ↓ |
|---|---|---|---|---|---|
| Photo S | 26.19 | 0.656 | 0.444 | 0.382 | 3.22 |
| Photo M (start) | 25.71 | 0.650 | 0.435 | 0.374 | 3.33 |
| ART po fazie 1 (L1+MS-SSIM) | 26.51 | 0.669 | 0.522 | 0.423 | 3.08 |
| ART | 26.23 | 0.655 | 0.366 | 0.380 | 3.20 |
| specjalista | 26.25 | 0.655 | 0.361 | 0.378 | 3.20 |
| STYL | 26.20 | 0.655 | 0.347 | 0.374 | 3.20 |
| ART+30 min (kontrola) | 26.24 | 0.655 | 0.366 | 0.380 | 3.20 |


## Czasy (wejście ok. 600 px, wynik ×4)

| Model | MPS, s/obraz | CPU, s/obraz | MPS, s/MP wejścia | CPU, s/MP wejścia |
|---|---|---|---|---|
| Photo S | 0,19 | 1,5 | 0,67 | 5,2 |
| ART / specjaliści (budowa Photo M) | 0,34 | 3,3 | 1,2 | 11,6 |
| STYL (+ SigLIP ok. 0,05 s na MPS) | 0,46 | 3,5 | 1,6 | 12,1 |

Czas treningu: ART 125 min, każdy specjalista 30 min, STYL 60 min (wektory SigLIP 7178 kopii ok. 3 min), kontrola 30 min. Razem ok. 5 h GPU.

## Plansze

- **`art-1.jpg` … `art-8.jpg`** pokazują po 4 dzieła, razem 32 ponumerowane, w kolejności z tabel: 1–8 stare, 9–16 obrazy, 17–24 grafiki, 25–32 rysunki. Kolumny: Prawda | Photo S | ART | specjalista swojej kategorii | STYL | restaurator dziś (tylko stare). Wycinki są w 100 %, a czerwona ramka na miniaturze pokazuje, skąd pochodzą.
- **`styl-sterowanie.jpg`** pokazuje to samo wejście przepuszczone przez STYL z własnym wektorem i z wektorem innego dzieła: Dürer z van Goghiem i odwrotnie, Hokusai z Rembrandtem i odwrotnie, Sargent z Holbeinem. Jest tam też różnica ×4 i dzieło, z którego wzięto wektor.

## Wniosek

- **Trening na sztuce działa.** ART wobec Photo M, od którego startował, ma +0,5 dB PSNR i LPIPS 0,366 zamiast 0,439. Wobec Photo S jest wyraźnie ostrzejszy (LPIPS 0,366 zamiast 0,447, lepszy na 32 z 32 dzieł) przy tym samym PSNR (−0,06 dB), detalu i barwie. Kreska rycin, szraf i twarze są czystsze. Faza 1 sama daje najwyższą wierność (27,12 dB, detal 0,437), ale jest miękka (LPIPS 0,531). Dopiero faza tekstury robi z niej ostrość.
- **Wobec dzisiejszego restauratora** (8 starych dzieł) ART jest wierniejszy we wszystkim prócz wrażenia ostrości. Ma +1,4 dB PSNR, detal 0,408 zamiast 0,303 i ΔE 3,24 zamiast 3,77, a ostrość w LPIPS 0,395 zamiast 0,330. Faktury SeedVR2 nie dorysowuje, ale też nie zmyśla: nie ma fałszywych nut, supłów ani szrafu na twarzy Melancholii. Na MPS działa w 0,3 s, na CPU w 3 s.
- **Specjaliści (MAL, GRAF, RYS) prawie nic nie dają.** Mają LPIPS 0,362 wobec 0,366 (lepiej na 24 z 32 dzieł), a PSNR i detal są równe. Kontrola ART + 30 min nie zmienia nic (0,367), więc ten drobny zysk to rzeczywiście podział, ale jest mały. Najwięcej daje w rysunku (+0,1 dB), w grafice nic. Przy tej ilości danych i tak krótkim douczaniu nie warto trzymać trzech modeli.
- **STYL jest najostrzejszy:** LPIPS 0,351, lepszy niż ART na 27 z 32 dzieł, najwięcej w grafice (0,343 wobec 0,369) i rysunku (0,289 wobec 0,310). Płaci za to 0,05 dB i trochę barwy (ΔE +0,05). Kontrola pokazuje, że to nie sam dłuższy trening. Wektor SigLIP mówi modelowi, jaki to rodzaj dzieła (kreska ryciny, akwarela, impast), i model dobiera ostrość do rodzaju.
- **„W jakim kierunku odtwarzać” jeszcze nie steruje.** Podmiana wektora (Dürer z wektorem van Gogha i odwrotnie) zmienia wynik o średnio 1–4 poziomy na 255. Widać to w różnicy ×4 jako trochę inną ostrość kresek, ale na oko obraz jest ten sam. Nic „van Goghowego” nie pojawia się w Dürerze. Model nauczył się używać wektora jako wskazówki o rodzaju dzieła, a nie stylu do naśladowania. Żeby sterował stylem, trzeba go uczyć na parach, w których styl zmienia wynik (np. różne wektory tego samego artysty kontra innych), i dłużej.
- **Wada:** na gęstych akwafortach i akwatintach (Goya 20, Rembrandt 18) ART i STYL zamieniają drobną siatkę kresek w „robaczkową” siatkę. To typowe zmyślenie fazy GAN przy małym wejściu. Jest dużo łagodniejsze niż u SeedVR2, ale widoczne.
- **Artyści obecni i nieobecni:** zysk ART nad Photo S jest podobny w obu grupach (LPIPS −0,079 i −0,078). Model uogólnia rodzaj techniki, a nie konkretnych artystów. Przy kilku dziełach na artystę trudno oczekiwać więcej.

## Co dalej

1. **ART lub STYL zamiast Photo S w restauratorze**, na próbę jako baza mieszania KH7 (dziś Photo S plus maska zmyśleń SeedVR2). ART jest równie wierny i wyraźnie ostrzejszy, więc maska miałaby mniej do łatania. Mieści się w CPU NAS-a (ok. 3 s na dzieło na M2 Pro, na NAS-ie może być 3–5× wolniej).
2. **Więcej danych i dłużej.** Trening był krótki (2 h na ART), a dane mają po 16 wycinków z dzieła. Rozsądny kolejny krok to 10–20 tys. dzieł z katalogu, wycinki brane na nowo przy każdym przejściu i faza tekstury 2–3 h. Dobrze byłoby też wyważyć kopie fotograficzne, bo ich część ma ramy i tablice barw.
3. **Artyści:** świadomie dobrać po 50–200 dzieł mistrzów, których Mateusz ogląda najczęściej (Rembrandt, Dürer, van Gogh, Holendrzy, Hiroshige), i wtedy sprawdzić STYL z wektorem artysty, a nie dzieła. Wektor średni z dzieł artysty dawałby kierunek „jak u tego artysty”.
4. **Przeciw „robaczkom” w akwafortach:** mniejsza waga GAN dla grafiki albo specjalista GRAF tylko z fazą L1 + LPIPS, bez GAN.
