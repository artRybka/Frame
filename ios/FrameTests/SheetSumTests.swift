import XCTest
@testable import Frame

/// The sheet de-yellowed on the phone as on the server (Mateusz 2026-11-20:
/// "A może warto jednak się pokłonić nad papierem?"): a made-up drawing of
/// 40 × 30 on a yellowed sheet, a field of the sheet's tone of 5 × 4 and
/// what `recovery.sheet_applied` makes of it, plain and for pastel
/// (`opaque`). `server/tests/test_cleaning.py` holds the fixture to the
/// server's sum.
final class SheetSumTests: XCTestCase {
    static let width = 40, height = 30

    static let picture = """
        y7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQzLmQzLmQzLmQzLmRzLmRzLmQzLmQzLmQ
        y7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQ
        y7iQy7iQy7iQy7iQzLmQzbmRzbqRzruRzruSz7uSz7ySz7ySz7ySz7ySz7uSzruSzruSzbqRzbqRzLmQy7iQy7iQy7iQy7iQ
        y7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQzLmQzLmRzrqRzruSz7yT0L2T0b2U
        0b6U0b6U0r6U0r6U0r6U0r6U0b6U0b6U0b2U0L2T0LyTz7uSzruRzbqRzLmQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQ
        y7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQzLmQzrqRz7uS0L2T0b2U0r6U0r+V07+V08CV08CW1MCW1MCW1MCW1MCW1MCW08CV
        07+V0r+V0r6U0b2U0L2Tz7ySzruRzbmRy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQv62Hwa6Jwa6Iwa6Iwa6Iwa6Iwa+Jw7CK
        xLKLxbOLxrSMx7WNyLWOybaOybePyrePyriPy7iPy7iQy7iQy7iQy7iQy7iQyrePyrePybePybaOyLaOx7WNxrSMxbOMxLKL
        w7GKwa+Jwa+Iwa6Iwa6Iwa6IwK6Iw7GLvauGv62Iv62Hv62Hv62HwK6Hwa+Jw7CKxLKLxbOLxrSMx7WNyLWNybaOybaOyreP
        yrePy7iPy7iQy7iQy7iQy7iQy7iPyrePyrePybePybaOyLWNx7WNxrSMxbOLxLKLw7GKwa+JwK6Iv62Hv62Hv62HvqyHwrCK
        vauGv62Iv62Hv62HwK6IwrCJw7GKxbKLxrSMx7WNyLWOybeOyrePy7iPzLiQzLmQzLmRzbqRzbqRzbqRzbqRzbqRzbqRzLmR
        zLmQzLiQy7iQyrePybeOyLaOx7WNxrSMxbOLxLGKwrCJwK+Iv62Hv62HvqyHwrCKvauGv62Iv62HwK6IwrCJw7GKxbKLxrSM
        x7WNybaOyrePy7iPy7mQzLmQzbqRzrqRzruSzruSz7uSz7uSz7uSz7uSzruSzruSzrqRzbqRzLmRzLmQy7iPyrePybaOyLWN
        xrSMxbOLxLGKwrCJwK6Iv62HvqyHwrCKvauGv62Iv62Hwa+Jw7GKxbKLxrSMx7WNybaOyrePy7iQzLmQzbqRzrqRzruSz7yT
        z7yT0LyT0LyT0L2T0L2T0L2T0LyTz7yTz7ySzruSzruRzbqRzLmQy7iQyrePybaOyLWNxrSMxbOLw7GKwrCJwK6IvqyHwrCK
        vauGv66IwK+IwrCKxLKLxrOMx7WNyLaOyrePy7iQzLmQzbqRzruSz7ySz7yT0L2T0L2U0b2U0b2U0b6U0b6U0b6U0b2U0b2U
        0L2T0LyTz7ySzruSzbqRzLmRy7iQyrePybaOyLWNxrSMxbKLw7GKwa+Jvq2HwrCKvauGwK6IwbCJw7GKxbOLxrSNyLWOyreO
        y7iPzLmQzbqRzruSz7yS0LyT0L2U0b6U0r6U0r6U0r6U0r+U0r+U0r+U0r6U0r6U0b6U0b2U0LyTz7yTzruSzbqRzLmRy7iQ
        yrePyLaOx7WNxbOMxLKKwrCJv62HwrCJvauGwa+IwrCJxLKLxrOMx7WNybaOyriPzLmQzbqRzruSz7yS0LyT0L2U0b6U0r6U
        0r+V07+V07+V07+V07+V07+V07+V0r+V0r6U0b6U0b2U0L2Tz7ySzruSzbqRzLmQy7iPybeOyLWNxrSMxbKLw7GKwK6IwrCK
        vauGwq+Jw7GKxbKLxrSMyLWOybePy7iPzLmQzbqRzruSz7yT0L2T0b2U0r6U0r+V07+V07+V08CV08CV08CV08CV07+V07+V
        07+V0r6U0b6U0L2T0LyTz7uSzrqRzbmQy7iQyrePyLaOx7SNxbOLw7GKwa+Iw7CKvayGwrCJw7GKxbOLx7SNyLaOyrePy7iQ
        zLqRzruRz7yS0LyT0b2U0b6U0r+U07+V07+V08CV08CV08CV1MCV08CV08CV08CV07+V0r+V0b6U0b2U0LyTz7ySzruSzbqR
        y7iQyrePybaOx7WNxbOMxLGLwa+Iw7GKvayGwrCJxLGKxbOMx7SNybaOyrePzLmQzbqRzruSz7yS0L2T0b2U0r6U0r+V07+V
        08CV08CV1MCV1MCV1MCV1MCV08CV08CV07+V0r+V0r6U0b2U0L2Tz7yTzruSzbqRzLmQyriPybaOx7WNxrOMxLKLwa+Jw7GK
        vayGwrCJxLGKxbOMx7SNybaOyrePzLmQzbqRzruSz7yS0L2T0b2U0r6U0r+V07+V08CV08CV1MCV1MCV1MCV1MCV08CV08CV
        07+V0r+V0r6U0b2U0L2Tz7yTzruSzbqRzLmQyriPybaOx7WNxrOMxLKLwa+Jw7GKvayGwrCJw7GKxbOLx7SNyLaOyrePy7iQ
        zLqRzruSz7yS0LyT0b2U0b6U0r+U07+V07+V08CV08CV1MCV1MCV08CV08CV08CV07+V0r+V0r6U0b2U0LyTz7ySzruSzbqR
        y7mQyrePybaOx7WNxrOMxLGLwa+Iw7GKvauGwq+Jw7GKxbKLxrSMyLWOybePy7iQzLmQzbqRz7uS0LyT0L2T0b6U0r6U0r+V
        07+V08CV08CV08CV08CV08CV08CV07+V07+V0r6V0b6U0L2U0LyTz7ySzrqSzbmRy7iQyrePyLaOx7SNxbOLw7GKwa+Iw7CK
        vauGwa+IwrCJxLKLxrOMx7WNybaOyriPzLmQzbqRzruSz7uS0LyT0L2U0b6U0r6U0r+V0r+V07+V07+V07+V07+V0r+V0r+V
        0r6U0b6U0L2U0LyTz7ySzruSzbqRzLmQy7iPybeOyLWNxrSMxLKLw7GKwK6IwrCKvqyHwa+IwrCJxLKLxrSMx7WNybaOyriP
        zLmQzbqRzruSz7yT0L2U0b6U0b6V0r+V07+V07+V08CW08CW07+V07+V07+V07+V0r6V0b6U0b2U0L2Tz7yTzruSzbqRzLmQ
        y7iPybeOyLWOxrSMxbKLw7GKwK6Iw7GJyrePyrePzLmQzruS0L2T0r6U08CV1cGW1sKX18OY2MOY2cSY2sWZ28aZ28ea3Mea
        3Meb3cib3cib3cib3smd3smd3cmc3cic3cic3Mib28eb28aa2sWa2cSZ2MOY1sKX1cGW08CV0r6V0L2Tz7uSzbqRyriPyreQ
        y7iQy7iQzLmQzruS0LyT0r6U07+V1cGW1sKX18OZ2sif3Mmg3cqh3cqh3sui3sui38yi38yj38yj38yi3smd3cmc3cmd3cic
        3Mic3Mec28eb2sab2cWa2MSZ18OY1sKX1cGX08CV0r6U0L2TzruSzLmQy7iQy7iQy7iQy7iQy7iQzLmQzruS0LyT0b6U07+W
        1MCV2MWd9vLr+Pfz+Pbx+Pbx+Pbx+Pbx+Pbx+Pbx+ffz9vTs3sqh28aa3Meb28eb28ab2saa2sWa2cSZ2MSZ18OY1sKX1MGW
        07+V0r6U0L2TzruSzbqRy7iQy7iQy7iQy7iQy7iQy7iQy7iQzbmRzruS0L2T0r6U0r6T18Sd+fj1/P39+/z7+/z7+/z7+/z7
        +/z7+/z7/P39+fj13Mmh2sWY2saa2sWa2cWa2cSZ2MSZ18OY1sOY1cGX1MCW07+V0r6U0L2Tz7uSzbqRy7iQy7iQy7iQy7iQ
        y7iQy7iQy7iQy7iQy7iQzLmQzruS0LyT0LyS1cKb9PLq+Pfz9/bx9/bx9/bx+Pbx+Pbx+Pbx+ffz9vLs2sif2MOX2MSZ2MSZ
        18OY18OY1sKY1cKX1MGW1MCW0r+V0b6U0L2TzruSzbqRy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQy7iQzLmQzruR
        z7yS0L2U1MGa1cOc1sSc18Sd18Wd2MWd2Mae2cae2cae2cae18OY1sKX1sKY1sKX1cKX1cGX1MGW08CW0r+V0b6U0b2Tz7yT
        zruSzLmQy7iQy7iQy7iQy7iQy7iQy7iQyLWOyLWOyLWOyLWOyLWOyLWOyLWOyLWOybeOy7iPy7iPzLmPzbqQzrqRz7uRz7yR
        0LyS0LyS0LyS0L2S0b2U0b2U0b2U0L2T0L2Tz7yTz7ySzruSzbqRzLmQy7iPyrePyLaOyLWOyLWOyLWOyLWOyLWOyLWOyLWO
        2sab2sab2sab2sab2sab2sab2sab2sab2sab28ab3Mic3cmd3sqd38qe4Mue4Muf4cyf4cyf4c2g4s2g4syf4cyf4cyf4cyf
        4Mue4Mue38qe3smd3cic3Mib28eb2sab2sab2sab2sab2sab2sab2sab2sab2sabaF5LaF5LaF5LaF5LaF5LaF5LaF5LaF9L
        aF5LaF5LaF5LaF9LaV9LaWBLaWBMamBMamBMamFMamFMamFMamFMamFMamFMamBMamBMaWBMaWBMaV9LaF9LaF5LaF5LaF5L
        aF9LaF5LaF5LaF5LaF5LaF5LaF5LaF5LAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        """

    static let numbers = #"{"kind": "paper", "on": false, "field": "+DnKOIE1uzmZOEk1fjloOBA1QDk3ONg0AzkGOKA0yjmlOFc1jTl0OB41UDlDOOY0EzkSOK401jjCN3U0nDmAOCw1XzlPOPQ0IjkeOLw05TjbN4M0qDh4N0s0bjlcOAI1MTkrOMo09DjzN5E0tziRN1k0ejgvNyE0", "width": 5, "height": 4, "fresh": [0.7397, 0.6918, 0.598], "opaque": false}"#

    static let deyellowed = """
        ysS4ysS4ysS4ysS5ysS5ysW5y8W5y8W6zMa6zMa7zce7zce8zsi8z8i9z8m9z8m+0cu+0cu+0sy/0szB083B1M3B1M7B1M7B
        1M7C1M7C1c7D1c/D1tDE19HF2NHF2NLG2dLG2dPH2tPH2tTH2tTI29TI29TI29TIysS4ysS4ysS4ysS5ysS5ysW5y8W5y8W6
        zMa6zMa7zce7zce8z8m80cq+0cu/0s2/083B1M3B1c/B1c/C1tDD19HD19DE1tDE19HE1tDD19HE1tDD1tDE19HF2NHF2NLG
        2dLG2dPH2tPH2tTH2tTI29TI29TI29TIysS4ysS4ysS4ysS5ysS5y8W5y8W6y8W6zMa6zce7zsi80Mm90cu/083B1M7B1s/D
        1tDD1tHE2NHE2NLF2dLF2tPG2dPG2tTH2tPH2dTG2tPH2tLG2dPF2dPG2dLF2NLG2dLG2dPH2tPH2tTH2tTI29TI29TI29TI
        ysS5ysS5ysS5ysS5ysS5y8W5y8W6y8W6zce6z8m80cq+083A1M7C1s/C1tHE2NHE2NPF2dPG2tPH29TH29XI3NXJ3dbJ3NbI
        3NbJ3NbJ3NXI3NXJ3NbI29XH29XH29PH2dPG2dPH2tPH2tTI29TI29TI29XI29TIvritwLmwwLqvwLqvwbqvwbqwwbyxxL2z
        xcC0x8G1yMO3ysW4y8W6zce7zci9z8m9z8q90cu+0cu/0szA0szB083B1M3C083B083B083B083A083B083A0s3A0szA0czA
        0cu/z8m+z8q90Mm90Mm90Mm+z8m+083CvLesvrmvvrmuv7muv7muwLuuwryxxL2zxcC1x8K1yMO3ysW5zMW5zce7zsi7z8m9
        0Mm90cu+0cvA0szA083B083B1M7B083B1M3B087C1M3B083A083B083A0sy/0szA0cu/z8m+z8m9zsi8zsi8z8m9zse90szB
        vbetv7mvv7muv7muwLuww72xxL6zxsC0yMK2ycS4y8W6zMe6zsi80Mq90cq+0sy/0szA083B1M7B1M7C1c/C1tDD1tDD1tDE
        1tDD18/D1tDE1s/D1dDC1dDD1c/C1M/B1M7B08zA0cu/0Mu+z8m9z8m9zsi90szBvbetv7mvv7muwLuwwr2xxL6zxsC0yMK2
        ycS4zMW5zce7z8m8z8q+0cu+083A1M3A1M7C1c/C1s/D19DD2NHE2NHF2NLF2NLF2dHF2NLF19HF2NLF2NHE19HF19HE19DD
        1c/C1M/B1M3A0szA0Mq/z8m9zsi9083Bvbetv7qwv7qvwryxxL6zxsC0yMK2ycS4y8W5zce7zsi90Mq90sy/083A1M7C1dDD
        1tDE19DE2NHF2NPF2dPG2tTG2tPH2tTH2tTG2dPH2tTG2tPG2dPG2dPG2dLG2NLF2NHE1tDD1dDC1M7B083A0cu/z8m+083C
        vriuwLuwwbyww72zxcC0yMG2ycS4ysW5zce7zsi90Mq90sy/083B1c/C1dDD19HE19HF2dLG2dLG2tTH29XI29XI3NXJ3NXJ
        3NbI3NXI29bI29XI29XI29TI2tTI2tPH2dPG2dLF19HE1s/D1M/C083Bz8q+1M7Cvriuwbuxwr6yxL+zx8G1yMO4ysS5zce6
        zsi70Mq90cy/083B1c/C19DD19HF2NPG2tPG2tTG29TH29bH3NbI3dfJ3dfJ3tfJ3dfK3tfK3dbJ3dfK3NbJ3NbJ3NbJ29XJ
        29TI2dTH2dPG19HF1tDD1M7C0cu/1M7Cv7muw72xxL6yxsG1yMK3ysS4zMa6zci80Mq90cy/083B1c/B19DD19HF2dPG2tPG
        2tXI3NXI3NbJ3dbJ3tfK39jL39jL3tnL39jK3tjL39jL3tjL3tjK3tjL3tfK3dfJ3dbI29bI2tTH2dPG2NHF1tDE083B1c/E
        v7mvxL2zxcC0x8G1ycO3y8W6zce8z8m80Mq+0sy/1M7B1c/D19HE2dLG2tPG29XI3NXI3NbJ3dfJ3tjK3tnK39nL4NnM4NnM
        4NrM4NnL39nM39nL4NnM4NjL39jL39fK3dfK3dbJ29XJ2tTI2NPF19HE1M7B19DEv7uvxL+zxcC0yMK2ysS5y8a6zsi8z8m+
        0cy/083A1c/C19DE2NLG2dPG29XH3NXI3NbJ3dfJ3djK3tjK4NnL4NrL4NrM4dvM4drN4NrN4NrM4NnN4NnM4NrM4NnM39nM
        3tfL3dfK3NbJ29XI2dPH2NHG1c/C19HFwLuvxb+zx8C1yMO3ysS5zce7zsi80cu+0szA1M7B1c/C19HE2dLG2tTG29XI3NbJ
        3dfJ3djJ39jK39nK4NrL4drM4NvM4dvN4drN4dvN4drN4drN4dvN4NrN4NrN4NnM39nL3djK3dbJ29bI2tTH2NPG1c/E19LF
        wLuwxb+0x8G1yMO4y8S5zce7zsi90cu+0s3A1M7C1tDC19LE2dLG29TH29bI3dbJ3djJ3tjK39jK4NnL4drL4dvM4dvN4dvN
        4tvN4dvO4tvN4drN4dvN4drN4NrN4NrM39nM3tjL3dfK29bJ29TI2dPH1tDE2NLFwLuwxcC0xsG1ycO3y8W6zMe7z8m90Mq+
        0s3A1M7C1tDD2NHE2dPG2tTH3NbH3dbJ3tfK3tjK3tnK4NnL4drM4dvM4dvN4tzN4tvO4dzO4tvN4trO4drN4dvN4drN4NrN
        39nM3tjL3tfK3NbJ29TI2dLH1tDD2NLGwbuwxr+0x8G2ycO3ysW5zce8zsm90cu/0sy/1M7B1s/D2NHF2dPG2tXH3NXI3NfK
        3tfK3tnK39nL4NrL4NvM4dvN4tzN4tvO49zO4tvO4dvO4dvO4tvO4tvN4drN4dnN39nM39jL3dfK3NbK29XH2dPG1tDD2dLG
        wbuxxb+zxsG1yMO3y8S5zMe7z8i80Mu+083A1M7C1tDD2NHE2dLG2tTI3NbI3dbJ3djK3tjL39nL4NnM4drN4tvN4dvO4tzO
        4tvN4dvO4dvO4trN4dvN4dvO4drN4NrM4NnM3tnL3tfK3NbJ2tTI2dPH1tDE2NLHw72zxsC0x8G1ycS4y8a6zci7z8m90cy/
        083A1c/C1tDE2NLG2tTI3NbI3NbK3tjL39jL4NnL4NrN4dvO4tvN4tvO49zP49zP49vP4tzO49vP4tzO4tzP4tzO4tvO4dvN
        4drM39nL3tjM3dfJ3NXI2tTH19HE2tTGz8m9z8m90cu/1M7B1tDD2dLF2tTG3dbI3tjK4NnM4drM49zN5d7P59/Q5+HR6eHS
        6eLU6+TU6+TV7OXV7ufZ7+fZ7ujZ7+fZ7+jZ7+jZ7ujZ7+fY7+fZ7+fZ7ubY7ebX7OXX6+XW6uPW6OLU6ODT5t/S4t3P4tvP
        0cu/0cu/0sy/1M7C19DE2dLF29TH3dbJ39jK4NrN493P5d7Q5t/Q5+DR6eHT6eLU7Oba6+TX7OXY7und7+fZ7ujZ7+na7+ja
        7+ja7+ja7+ja7uja7uja7ufZ7ufZ7ebY7ebY6+XW6+PV6ePU5+HT5d/R5N7R5N7R0cu/0cu/0cu/08zA1c/D19HE2dPG29XJ
        3dbI4drP9vLr+Pfz+Pbx+Pbx+Pbx+Pbx+Pbx+Pbx+ffz9vTs7uba7eXW7ufY7ufZ7ufZ7ufY7ubZ7ubY7ufZ7efY7ebY7ObX
        6+TW6+PV6ePU5+HT5+DS5d7R5d7R5d7R0svA0svA0svA0szA1M3C1tDD2NLF29TH29TG4NnP+fj1/P39+/z7+/z7+/z7+/z7
        +/z7+/z7/P39+fj16uLU7OTU7ebX7eXY7ObY7eXX7ObY7OXX7ObY7OXX6+TX6+TW6+PV6ePU6OHT5+DS5d7R5d7S5d/S5d7S
        0szA0szA0szA0szA08zB1M7B19DE2dLG2tPF39nQ9PLq+Pfz9/bx9/bx9/bx+Pbx+Pbx+Pbx+ffz9vLs6eTX6uLT6+TW6+XX
        6+TW6+TW6+TX6uXW6uTW6+TW6uTW6ePV6ePU5+HT5+DS5d7R5d/S5t/S5t/S5t/S0szA0szA0szA08zB083B083B1c/C19HD
        2dPF2tTI39nQ4NrO4dvO4trN49zO5N3P5N3O5t7P5t7Q59/R6eLU6OLT6eLV6uPU6ePV6eLV6ePU6ePV6OLV6OLU6eLT5+HU
        5+HT5d/R5d7R5d/S5t/S5t/S5t/T5t/Sz8m+z8m+z8m+0Mm+0Mq/0Mq/0cq/0cvA087A1c/C1tDD2NLD2tTF29TH3dbI3dfI
        39jK39jK4NnL4dvL49vP49zP5N3Q493P5N7Q493Q5N7P493Q493P493P49zO4tvP4dvO4drO4drO4tvO4tvP49vP49zP49vP
        4tzP4tzP4tzP49zP493Q493Q5N3R5N7R5d7S5t/S6OLU6uTW7ObX7ubZ7+jZ8Onb8erc8uvc8u3e9O3f9e3e9e7f9u7f9u/g
        9e7f9u/f9u7g9e7f9e7f9e7e9e7f9O7g9e7g9u/h9u/h9/Di9/Di9/Hj+PHj+PHja2Zea2Zea2Zea2Zea2Zfa2Zfa2ZfbGhg
        bGdgbGdgbGdhbWlibmpjb2tkb2xlcGxmcWxmcW5ncW9ocm9ocnBpc3Bpc3Bqc29qc3Bqc3Bqc3Brc29pc3Bqc29qc29rdHBr
        dHJsdHFsdXFtdXFtdXJtdnJudnJudnJuAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        """

    static let opaque = """
        ysO4ysO4ysO4ysS4ysS4ysS5y8W5y8W5zMW6zMa6zca7zce7zsi8zsi8z8m9z8m90cu+0cu+0su/0szA083B083A1M7B1M7B
        1M3B1M7C1c7C1c/D1tDE19DE19HF2NLF2dLG2dPG2tPH2tTH2tTI29TI29TI29TIysO4ysO4ysO4ysS4ysS4ysS5y8W5y8W5
        zMW6zMa6zca7zce7z8m80Mm+0cu+0sy/083A1M3B1c/B1c/C1tDD19HD19DD1tDE19HE1tDD19HE1tDD1tDE19DE19HF2NLF
        2dLG2dPG2tPH2tPH2tTI29TI29TI29TIysO4ysO4ysS4ysS4ysS4y8S5y8W5y8W5zMa6zce6zsi80Mm90cu/083B1M7B1c/D
        1tDD1tHD2NHE2NLF2dLF2tPG2dPG2tTH2tPH2dTG2tPG2tLG2dPF2dPG2dLF2NLG2dLG2dPH2tPH2tTH2tTI29TI29TI29TI
        ysS4ysS4ysS4ysS4ysS4y8W5y8W5y8W6zce6z8i80cq+083A1M3B1s/C1tHE2NHE2NPF2dPG2tPH29TH29XI3NXJ3dbJ3NbI
        3NbJ3NbJ3NXI3NXJ3NbI29XH29XH2tPH2dLG2dPH2tPH2tTI29TI29TI29TI29TIvriswLmuwLmuwLmuwbquwbquwbuwxL2y
        xb+0x8G0yMO2ysS4y8W6zce6zci8z8m8z8q90cq90cu/0svA0szA083B083B083A083B083B083A083B0s3A0s3A0szA0cu/
        0cu+z8m9z8m90Mm90Mm90Mm9z8m9083BvLarvritvritv7mtv7mtwLquwrywxL2yxcC0x8G1yMO2ysW4zMW5zce7zse7z8m9
        z8m90cu+0cu/0szA08zB083B1M7A083B1M3B087B083B083A083B0s3A0sy/0szA0cu/z8m+z8i9zsi8zsi8z8i8zce80szA
        vbarv7iuv7mtv7mtwLqvw72wxL6yxsC0yMK2ycS3y8S5zMe6zsi80Mq80cq+0su/0szA083B1M7B1M7C1c/C1tDD1tDD1s/E
        1tDD1s/D1tDE1s/D1dDC1c/D1c/C1M7B087A08zA0cu/z8q9z8i8z8m9zse80szBvbesv7muv7mtwLqvwr2wxL6yxsC0yMK2
        ycS3zMW5zce7z8m8z8q90cu+0szA1M3A1M7C1c/C1s/D19DD2NHE2NHF2NLF2NLF2dHE2NLF19HF2NLF2NHE19HF19HE19DD
        1c/C1M/B1M3A0sy/0Mq+z8m9zsi9083Bvbesv7muv7muwrywxL6yxsC0yMK1ycS3y8W5zce7zsi80Mq90sy/08zA1M7B1c/D
        1tDE19DE2NHE2NPF2dPG2tTG2tPH2tTH2tTG2dPH2tTG2tPG2dPG2dPG2dLG2NLF2NHE1tDD1dDC087B083A0cu/z8i9083C
        vreswLuvwbyvw72yxcC0yMG1ycS3ysW5zce7zsi80Mq90sy/083B1c/C1dDD19HE19HF2dLG2dLG2tTH29XI29XI3NXJ3NXJ
        3NbI3NXI29XI29XI29XI29TI2tTH2tPH2dPG2dLF19HE1s/D1M7C0szBz8q+1M3Cvritwbuvwr2xxL+zx8G0yMO3ysS5zce6
        zsi70Mq90cu/083B1c/C1tDD19HF2NPF2tPG2tTG29TH29bH3NbI3dfJ3dbJ3tfJ3dfK3tfK3dbJ3dfK3NbJ3NbJ3NXJ29XJ
        29TI2dTH2dPG19HF1tDD1M7B0cu/1M7Bv7itw72wxL6yxsC0yMK2ysS4zMa5zci70Mq90cu/083B1c/B1tDD19HF2dPG2tPG
        2tXI3NXI3NbJ3dbJ3tfK39jL39jL3tnL39jK3tjL39jL3tjL3tjK3tjL3tfK3dfJ3dbI29XI2tTH2dPG2NHF1tDD08zB1c/D
        v7muxL2yxb+zx8G1ycO3y8W5zMe7z8m80Mq90sy/1M7B1c/D19HE2dLG2tPG29XI3NXI3NbJ3dfJ3tjK3tnK39nL4NnM4NnM
        4NrM4NnL39nM39nL4NnM4NjL39jL39fK3dfK3dbJ29XI2tPH2NPF1tHE1M7B1s/Ev7quxL+yxcC0yMK1ysS4y8a6zsi8z8m9
        0cy/083A1c/C19DD2NLF2dPG29XH3NXI3NbJ3dfJ3djJ3tjK4NnL4NrL4NrM4NvM4drN4NrN4NrM4NnN4NnM4NrM4NnM39nM
        3tfL3dfK3NbJ29XI2dPH2NHG1c/C19HEwLquxb+zx8C0yMK3ysS4zca6zsi80cu+0sy/1M7B1c/C19HE2dLG2tTG29XI3NbJ
        3dfJ3djJ39jK39nK4NrL4drM4NvM4dvN4drN4dvN4drN4drN4dvN4NrN4NrN4NnM39nL3djK3dbJ29XI2tTH2NPG1c/D19HF
        wLuvxb+zx8C0yMO3y8S5zce6zsi80cu+0szA1M7C1tDC19LE2dLG29TH29bI3dbJ3dfJ3tjK39jK4NnL4drL4dvM4dvN4dvN
        4tvN4dvO4tvN4drN4dvN4drN4NrN4NrM39nM3tjL3dfK29bJ29TI2dPG1c/E2NLFwLuvxb+zxsG1ycO2y8S5zMe7z8m80Mq+
        0s3A1M7C1tDC2NHE2dPG2tTH3NbH3dbJ3dfK3tjK3tnK4NnL4drM4dvM4dvN4tzN4tvO4dzO4tvN4trO4drN4dvN4drN4NrN
        39nM3tjL3tfK3NbJ29TI2dLH1tDD2NLFwLqvxr+zx8G1ycK2ysW4zca7zsm90cq+0sy/1M7B1s/D2NHF2dPG2tXH3NXI3NfK
        3tfK3tnK39nL4NrL4NvM4dvN4tzN4tvO49zO4tvO4dvO4dvO4tvO4tvN4drN4dnN39nM39jL3dfK3NXJ29XH2dPG1tDD2dHG
        wbuwxb+zxsC0yMO3y8S4zMe6z8i80Mu+083A1M7B1tDD2NHE2dLG2tTI3NbI3dbJ3djK3tjL39nL4NnM4drN4tvN4dvO4tzO
        4tvN4dvO4dvO4trN4dvN4dvO4drN4NrM4NnM3tnL3tfK3NbJ2tTI2dPG1tDE2NLGwryxxsCzx8G1ycO3y8a5zce7z8m90cu+
        083A1c/C1tDE2NLG2tTI3NbI3NbK3tjL39jL4NnL4NrN4dvO4tvN4tvO49zP49zP49vP4tzO49vP4tzO4tzP4tzO4tvO4dvN
        4drM39nL3tjM3dfJ3NXI2tTH19DE2tTGz8m9z8m90cu+1M7B1tDD2dLF2tTG3dbI3tjK4NnM4drM49zN5d7P59/P5+HR6eHS
        6eLT6+PU6+TU7OXV7ufZ7+fZ7ujY7+fZ7+jZ7ujY7ujZ7+fY7+fZ7ufZ7ubY7ebX7OXW6+XV6uPW6OLU6ODT5t/S4t3P4tvP
        0cu/0cu/0sy/1M7C19DD2dLF29TH3dbJ39jK4NrN4tzP5d7Q5t/Q59/R6eHT6eLU7Oba6+TX7OXX7ujd7ufZ7ujY7+ja7+jZ
        7+ja7+ja7+jZ7uja7uja7ufZ7ufY7ebY7ebY6+XW6+PV6ePU5+HT5d/R5N7R5N3R0cu/0cu/0cu/08y/1c/C19DE2dPG29XJ
        3dbI4drO9vLr+Pfz+Pbx+Pbx+Pbx+Pbx+Pbx+Pbx+ffz9vTs7eba7OXW7ufY7ufY7ubZ7efY7ubZ7ubY7ufZ7efY7ebX7ObX
        6+TW6+PV6ePU5+HT5+DS5d7R5d7R5d7R0su/0su/0su/0szA1M3B1tDD2NLF29TH29TG4NnO+fj1/P39+/z7+/z7+/z7+/z7
        +/z7+/z7/P39+fj16uLU7OTT7ObX7eXY7ObY7eXX7ObY7OXX7ObY7OXX6+TX6+TW6+PV6ePU6OHT5+DS5d7R5d7S5d/S5d7S
        0szA0szA0szA0szA08zA1M7B1tDE2dLG2tPF39nP9PLq+Pfz9/bx9/bx9/bx+Pbx+Pbx+Pbx+ffz9vLs6eTW6uLT6+TW6+XX
        6+TW6+TW6+TX6uXW6uTV6+TW6uTW6ePV6eLU5+HT5+DS5d7R5d/S5t/S5t/S5t/S0szA0szA0szA0szA083B083B1c/C19HD
        2dPF2tTI39nP39nO4dvO4trN49zO5NzP5N3O5d3P5t7P59/R6eLU6OLT6eLV6ePU6ePV6eLV6ePU6ePV6OLV6OLU6eLT5+HU
        5+HT5d/R5d7R5d/S5t/S5t/S5t/T5t/Sz8m9z8m9z8m+0Mm+0Mm+0Mq+0cq/0cu/083A1c/C1tDC2NLD2tTF29TH3dbI3dfI
        39jK39jK4NnL4dvL49vP49zP5N3Q493P5N7Q493Q5N7P493Q493P493P49zO4tvP4dvO4drO4drO4tvO4tvP4tvP49vP49vP
        4tzP4tzP4tzP49zP493Q493Q5N3R5N7R5d7S5t/S6OLU6uTW7ObX7ubZ7+jZ8Onb8erb8uvc8uze9O3e9e3e9e3e9e7f9u7f
        9e7e9u7f9e7g9e3f9e3e9e7e9O7f9O3f9e7g9e/h9u/h9/Di9/Di9/Di9/Di9/DiamNXamNXamNXamNXamNYamNYamNYamVZ
        amRZa2RZa2RZa2ZbbWZbbWhdbWhebmheb2leb2pgb2tgb2tgcGthcGxicGxicGthcWticGticGticGthb2tib2phcGpicGpi
        cWxkcWtjcWtkcWxkcWxkcmxkcmxlcmxlAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA
        """

    private func bytes(_ text: String) -> [UInt8] {
        [UInt8](Data(base64Encoded: text.filter { !$0.isWhitespace }) ?? Data())
    }

    private func check(opaque: Bool, expected text: String) throws {
        var view = try JSONDecoder().decode(ColoursView.self, from: Data(Self.numbers.utf8))
        view.opaque = opaque
        let sum = try XCTUnwrap(SheetSum(view))
        let rgb = bytes(Self.picture), expected = bytes(text)
        let count = Self.width * Self.height
        XCTAssertEqual(rgb.count, count * 3)
        XCTAssertEqual(expected.count, count * 3)
        var rgba = [UInt8](repeating: 255, count: count * 4)
        for at in 0 ..< count {
            for c in 0 ..< 3 { rgba[at * 4 + c] = rgb[at * 3 + c] }
        }
        rgba.withUnsafeMutableBufferPointer {
            sum.apply(to: $0.baseAddress!, width: Self.width, height: Self.height)
        }
        var apart = 0, most = 0
        for at in 0 ..< count {
            for c in 0 ..< 3 {
                let d = abs(Int(rgba[at * 4 + c]) - Int(expected[at * 3 + c]))
                most = max(most, d)
                if d > 0 { apart += 1 }
            }
            XCTAssertEqual(rgba[at * 4 + 3], 255)
        }
        XCTAssertLessThanOrEqual(most, 1)
        XCTAssertLessThan(Double(apart) / Double(count * 3), 0.02)
        // The yellow did come off: the sheet is bluer than it was.
        let blue = (0 ..< count).map { Int(rgba[$0 * 4 + 2]) - Int(rgb[$0 * 3 + 2]) }.reduce(0, +)
        XCTAssertGreaterThan(blue, count * 10)
    }

    func testTheSheetIsDeyellowedAsOnTheServer() throws {
        try check(opaque: false, expected: Self.deyellowed)
    }

    func testPastelIsLeftWhereItCoversTheSheet() throws {
        try check(opaque: true, expected: Self.opaque)
    }

    func testHalfFloats() {
        XCTAssertEqual(SheetSum.half(0x3C00), 1)
        XCTAssertEqual(SheetSum.half(0x3800), 0.5)
        XCTAssertEqual(SheetSum.half(0xC000), -2)
        XCTAssertEqual(SheetSum.half(0x0001), powf(2, -24))
    }

    func testAServerWithoutTheSheetsNumbersLeavesItToTheServer() throws {
        let view = try JSONDecoder().decode(ColoursView.self, from: Data(#"{"kind": "paper", "on": true}"#.utf8))
        XCTAssertTrue(view.on)
        XCTAssertNil(SheetSum(view))
    }

    func testAPictureKeepsItsSizeAndComesBackWhole() throws {
        let view = try JSONDecoder().decode(ColoursView.self, from: Data(Self.numbers.utf8))
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 64, height: 48))
        let picture = renderer.image { context in
            UIColor(red: 0.89, green: 0.8, blue: 0.63, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: 64, height: 48))
        }
        let made = try XCTUnwrap(SheetSum(view)?.apply(to: picture))
        XCTAssertEqual(made.size, picture.size)
        XCTAssertEqual(made.cgImage?.width, picture.cgImage?.width)
    }
}
