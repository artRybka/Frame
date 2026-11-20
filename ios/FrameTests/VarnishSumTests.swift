import XCTest
@testable import Frame

/// The varnish taken off on the phone as on the server (Mateusz 2026-11-20:
/// "korekta może dotyczyć tylko tego co widać"): a made-up picture of 40 × 30
/// under an aged varnish, the numbers the server reads on it at 0.69
/// (`recovery.varnish_sum`) and what `recovery.unvarnished` makes of it.
/// `server/tests/test_cleaning.py` holds the fixture to the server's sum.
final class VarnishSumTests: XCTestCase {
    static let width = 40, height = 30

    static let picture = """
        i5aOi5aOi5aOi5aOi5aOipWNi5aNipWNipWNi5aNi5aNi5aOipWNi5aNi5aOi5aOi5aNi5aOi5aOi5aOipaNipWNi5aOi5aO
        ipWOipaNi5aOi5aOi5aOipaNipaNipWNi5aOi5aOi5aOi5aOi5aOipWNi5aOi5aOi5aNi5aOi5aOi5aOipWNipaNipaNipWN
        i5aOi5aOi5aNi5aOi5aNipWNi5aOi5aOipWNipWNipWNipWNipWNipWNi5aOi5aOi5aOi5aOi5aOi5aOipaNi5aOipWNipaN
        i5aOi5WNi5WNi5aOipWNipWNi5aOi5aOipWNi5aOi5WNi5aOi5eOi5aOipaNipWNi5aOi5aOipWNipaOi5aOi5aOi5aOipWN
        ipaNi5aNi5aOipWNi5aOi5aOi5aOi5aOi5aOi5WNi5aOipaNi5aOipWNipWNi5aOi5aOi5aOi5aOi5aOipaOi5aOi5aOi5aO
        i5aOi5aOi5aOi5eOi5aNi5aOi5aOi5aNi5aOi5aOipWNipWNi5aOi5aOi5aOi5aOipWNipWNi5aOi5aOipaNipWOi5aOi5aO
        i5aOi5aOi5aOi5aOi5aOipWNi5aNi5aOi5aOi5aOipaNi5aOi5aOipaOi5aNi5aOi5aOi5aOi5aOi5aOi5aOi5aOi5aOi5aO
        ipWNipWNi5aOi5aOi5aOi5aOi5aOipWNi5aOipWNipWNi5aOi5aOi5aOipWNipWNipaNipaNi5aOi5aOi5aOipWNi5aOi5eO
        i5aOipWNipWNi5aOipWNi5aNi5aOipWNi5eOi5aOi5aOipWNi5aOi5aOi5aOi5WOipWNipWNi5aOipWNi5aOi5aOipWNi5aO
        i5aOi5aOipWNipaNi5aOi5aOipWNi5aOi5aOipaNi5aOi5aOipWNipaNipaNipWNipWNipWNi5aNi5aOi5aOi5aOipWNi5aO
        ipaNi5WOi5aOipaNipWNipWNipWNi5aOipWNipaNipWNi5aOipWNipWNi5aNipaNi5aOipaNi5aOipaNipWNipWNipWNipaN
        i5aOi5aOipaNipWNipaNipWNi5aOi5aOipaNi5aNi5eOipWNipWNi5aOi5aOipaNipaNipWNipWNipWNi5aOi5aOi5aOipWN
        i5aNi5aNi5WNi5aOi5aOi5aNi5aOjJaOi5aOipWNi5aOipWNipWNi5aOipaNi5aOipWNipaNi5aOipWNi5aOi5aOi5aOi5aO
        jJePi5aOi5aOi5aOipWNi5aOi5aOipWNi5aOipWNipaOi5aOi5aOi5aOi5aNipWNipaOipaPipaPipWOiZWOipaOipaPipaP
        ipaPipaOi5WNipWNipWNi5aNi5aOi5aOipWNipWNi5aOipWMi5aOi5aOi5aOi5aOipWNipWNjJePi5aOi5aOi5aOipWNipWN
        i5aOi5aOi5aOi5aOipWNi5aOipWNjJaMjpWLjpaLj5aMjpaLjZWKjpaMjpWLjpaLj5aMjJaMipaOipaNipaNi5aNi5aOi5aO
        i5aOi5aOi5aOi5aOi5aOi5aOi5aNi5aOi5aOi5aOi5aOi5aOi5aOi5aOipWNipWNi5aNipWNi5WNi5aOipWNjJaNiJaRpJV8
        wZZpvJZtvZZsvZZsvZZsvZZsvpdtvJZtwZZqpJZ9h5aQjJaNi5aOi5aOi5aOi5aOjJaNjJeOjJeOjJePjJeOi5aNjJaOjJaO
        jJeOjZePjJeOi5aNi5aOi5aOi5aOi5aOipaNipWNi5aOipWNi5aOi5WNh5aRppZ8xZVmwJZqwZVpwpZpwpZpwZZpwpZpwJZq
        xZZmppV7hpWQjJaNi5aNi5aOi5aOiZWNhZKMhZKMhpONhZKMhZKMhZKMhJGMhZKMhZKMhZKMhpKNipaNi5aOi5aOipaNipaN
        i5aNipWNipWNipWNipWNjJaNh5aQppZ8xJZnv5ZqwZZqwJZqwJZqwZZqwZZqv5VqxZZnppZ8hpWPi5WNipWNi5aNiJSMlJyQ
        s7CWsK6Wsa+Wsa+XsrCXsa+Wsa+Wsa+Wsa+Wsq+WsK6WjZeNipWNi5aOi5aNi5aOjJiQjJiQi5ePi5ePjJePjZePiJiTppZ8
        xJVnwJZqwZZqwZZqwJZqwZdqwZZqv5ZqxZZnppZ8h5eSjJeOjJiQjZiPhpSOoaWU4c6h3cyg3cyg3cyg3syg3s2h3syh3syh
        3cyg3syg2MifkJqQi5aPjJePjJeQjJePh5CHh5CHiJGIhpCHh5CGiJGHgo+JpJN4xZZnwJZqwZZqwZZqwZVpwZZqwZZqwJZq
        xZZnpJN4go+JiJGHiJGIh5CHg42GnJ+O2sqg1cae1sef18if1sef18if1cae1sef18if18ie0cOdjJSJho+Hh5CHh5CHh5CH
        V0UvVkUvVkUvVkUvVkUvWEcwTj8rjG1MyZxuvpRowJZqwJZpwZZqwZZpwZZqv5VpyJxujG5MTj8rWEcwVkUvWEcwTz4peGdM
        3c6k1see2Mmf2Mmf18ef18if18if2Mmg2Mie2suhz8CYX042VEMtVkUvVkUvVkUvUj8nUj8nUj4nUj4nUT4nVEAoSTgiiWpI
        yp1vvpRowZZpwJZpwJVpwZZqwZdqv5VpyZ1viWpISTgiU0AoUj4nU0AoSzcgdGJG3s+l18ee18ie2Mif2Mmg2Mmf18ef2Mif
        18ee2cqhz7+XWkcvTzwlUj8nUj4nUT4nU0ApU0ApU0ApU0ApU0ApVUEqSzkkimtJyZxuvpRowZZqwZZqwJZpwJVpwJVpv5Ro
        yZxvimtJSzkkVUEqU0ApVEEqSzgidWNH3c6k1sad18ie18ee18ie2Mif18ef18ee1sad2cqgz7+XW0gwUT4nVEApU0ApU0Ap
        U0ApU0ApU0ApU0ApU0ApVEEqSzkkimpJyJxuvpRowZZqwZZqwZZqwZZqwZZpv5RoyJxuiWtJSjkjVUEqU0ApVEEqSzgidWNH
        4dGn2Mif2cqh2sqh28uh2sqh2sqh2sqh2cmg3M2j0cKZW0kxUT0nVEEpUkApUj8oU0ApU0ApUz8oU0ApU0ApVEEpSjkkimtJ
        yZ1vvpRowJZqwJZpwJVpwJZpwJVpv5RoyZxuimtJSzkkVEEqUj8oVEEqTDkic2FF1cWdzr6Wz7+Xz8CXz7+Xz7+Xz7+Xzr+X
        z7+X0sKZx7eQW0gwUT4nU0ApU0ApUj8pU0AoU0ApU0ApU0ApU0ApVUEqSjkkiWpJyJtuvZNnv5RovpRov5RovpRov5RovZNo
        xpptiWpJSjkkVEEpUj8oU0ApUj8oVEIqW0kwW0gwW0kwW0gwW0kwW0kwW0gwW0kwWkgwW0kwWkgvU0AqU0ApU0AoU0ApUj8o
        U0AoUj8oU0ApUkAoUj8oVEEqSjkjjW5L0qNzxpptyZxvyZxvyZxvyZxuyJxux5tt0qN0jm5MSjgjVUEqU0AoU0ApU0ApUj8o
        UD0mUT4nUD0mUT4nUT4nUT0nUT0nUT0mUD0mUT4nUD0nUj8oU0ApU0ApUj8oU0ApUj8oUkAoU0AoUj8oU0ApU0ApTjwmblU5
        jm5MiWpJimtJiWtJiWpJimtKimtJiWpJjm5LblU4Tz0nVEEpUkAoU0ApU0ApU0ApU0ApU0EpU0ApU0ApU0EpU0ApU0ApU0Ap
        U0ApU0ApU0ApU0ApU0ApU0ApU0AoU0AoUj8oUkAoU0AoUkAoU0AoUkApVEEpTz0mSjkjSzokSjkjSjkjSzkkSzkkSjkkSzkk
        STgjTz0mU0ApU0ApU0ApUkApU0AoUj8oUj8pU0ApUj8oU0AoUz8pUj8oU0AoUj8oU0ApUj8pUj8oU0ApU0ApUkAoUj8oUz8o
        U0ApU0ApU0ApU0ApUkApUj8oUkAoVEEpVUEqVEEpVEEqVUEqVEEqVEEpVUEqVEEqVUEqVEApUj8oU0ApU0AoUj8oUj8oUj8o
        U0ApU0ApU0AoUj8oU0AoUz8oU0AoUj8oUj8oU0AoU0AoU0ApUj8oUkAoU0ApUz8oUj8oU0ApU0ApU0ApU0ApU0ApU0ApU0Ao
        U0ApUkAoU0ApUj8oUkAoUz8oU0ApU0ApUj8oUj8oU0ApU0ApUj8oU0ApUkApU0ApU0AoU0AoU0ApUj8pUj8oUj8oU0AoUz8o
        UkAoU0AoU0ApU0ApUj8oU0ApU0ApU0AoUj8oU0AoUj8oUj8oU0ApU0ApU0ApUj8oU0AoU0ApU0ApU0ApUj8oUkApUkApU0Ap
        Uj8oUkAoUz8oUj8oUj8oU0AoU0ApU0ApU0ApUkApU0AoU0ApU0ApUkAoUj8oUkApUj8oU0AoU0ApU0ApUz8oU0AoUj8oUj8o
        Uz8oU0ApUkAoUkAoU0AoU0ApUz8oUj8oU0ApU0ApUj8oU0ApU0ApUkAoU0ApU0AoUkApUj8oU0AoU0ApU0ApUj8oU0ApU0Ao
        U0ApU0ApUj8oUj8oUkAoU0AoU0ApUj8oU0ApUz8oU0AoU0ApU0ApU0ApU0AoU0ApU0AoUz8oUkAoU0AoUj8oUkApUkAoU0Ap
        UkApU0ApU0AoU0ApUkAoU0ApUkAoU0AoU0ApU0ApU0ApUj8oUj8oU0ApUj8pU0ApU0ApU0ApU0ApU0ApUj8oU0ApU0AoUj8o
        U0ApU0ApU0ApU0ApUj8oU0ApUj8oUkAoU0ApUkAoUkAoUj8oU0ApU0ApUj8oU0ApUkAoU0AoU0ApUj8oU0ApU0ApU0ApU0Ao
        Uj8oUz8oUj8oUj8oUj8oUz8oUkAoUj8oU0ApU0ApU0ApU0ApUj8oU0ApUj8oU0ApU0ApU0ApUj8oU0ApU0ApU0ApU0ApUkAo
        """

    static let numbers = #"{"kind": "varnish", "on": false, "haze": 0.01035, "colour": [1.1090458631515503, 1.2819725275039673, 1.993715524673462], "even": 1.2965961694717407, "dark": 0.15, "scale": 1.0963576019858532, "luma": [0.2126, 0.7152, 0.0722]}"#

    static let cleaned = """
        lq3Ilq3Ilq3Ilq3Ilq3IlazGlq3GlazGlazGlq3Glq3Glq3IlazGlq3Glq3Ilq3Ilq3Glq3Ilq3Ilq3Ila3GlazGlq3Ilq3I
        lazIla3Glq3Ilq3Ilq3Ila3Gla3GlazGlq3Ilq3Ilq3Ilq3Ilq3IlazGlq3Ilq3Ilq3Glq3Ilq3Ilq3IlazGla3Gla3GlazG
        lq3Ilq3Ilq3Glq3Ilq3GlazGlq3Ilq3IlazGlazGlazGlazGlazGlazGlq3Ilq3Ilq3Ilq3Ilq3Ilq3Ila3Glq3IlazGla3G
        lq3IlqzGlqzGlq3IlazGlazGlq3Ilq3IlazGlq3IlqzGlq3Ilq7Ilq3Ila3GlazGlq3Ilq3IlazGla3Ilq3Ilq3Ilq3IlazG
        la3Glq3Glq3IlazGlq3Ilq3Ilq3Ilq3Ilq3IlqzGlq3Ila3Glq3IlazGlazGlq3Ilq3Ilq3Ilq3Ilq3Ila3Ilq3Ilq3Ilq3I
        lq3Ilq3Ilq3Ilq7Ilq3Glq3Ilq3Ilq3Glq3Ilq3IlazGlazGlq3Ilq3Ilq3Ilq3IlazGlazGlq3Ilq3Ila3GlazIlq3Ilq3I
        lq3Ilq3Ilq3Ilq3Ilq3IlazGlq3Glq3Ilq3Ilq3Ila3Glq3Ilq3Ila3Ilq3Glq3Ilq3Ilq3Ilq3Ilq3Ilq3Ilq3Ilq3Ilq3I
        lazGlazGlq3Ilq3Ilq3Ilq3Ilq3IlazGlq3IlazGlazGlq3Ilq3Ilq3IlazGlazGla3Gla3Glq3Ilq3Ilq3IlazGlq3Ilq7I
        lq3IlazGlazGlq3IlazGlq3Glq3IlazGlq7Ilq3Ilq3IlazGlq3Ilq3Ilq3IlqzIlazGlazGlq3IlazGlq3Ilq3IlazGlq3I
        lq3Ilq3IlazGla3Glq3Ilq3IlazGlq3Ilq3Ila3Glq3Ilq3IlazGla3Gla3GlazGlazGlazGlq3Glq3Ilq3Ilq3IlazGlq3I
        la3GlqzIlq3Ila3GlazGlazGlazGlq3IlazGla3GlazGlq3IlazGlazGlq3Gla3Glq3Ila3Glq3Ila3GlazGlazGlazGla3G
        lq3Ilq3Ila3GlazGla3GlazGlq3Ilq3Ila3Glq3Glq7IlazGlazGlq3Ilq3Ila3Gla3GlazGlazGlazGlq3Ilq3Ilq3IlazG
        lq3Glq3GlqzGlq3Ilq3Ilq3Glq3Il63Ilq3IlazGlq3IlazGlazGlq3Ila3Glq3IlazGla3Glq3IlazGlq3Ilq3Ilq3Ilq3I
        l67Jlq3Ilq3Ilq3IlazGlq3Ilq3IlazGlq3IlazGla3Ilq3Ilq3Ilq3Ilq3GlazGla3Ila3Jla3JlazIlKzIla3Ila3Jla3J
        la3Jla3IlqzGlazGlazGlq3Glq3Ilq3IlazGlazGlq3IlazFlq3Ilq3Ilq3Ilq3IlazGlazGl67Jlq3Ilq3Ilq3IlazGlazG
        lq3Ilq3Ilq3Ilq3IlazGlq3IlazGl63FmazDma3Dmq3Fma3DmKzCma3FmazDma3Dmq3Fl63Fla3Ila3Gla3Glq3Glq3Ilq3I
        lq3Ilq3Ilq3Ilq3Ilq3Ilq3Ilq3Glq3Ilq3Ilq3Ilq3Ilq3Ilq3Ilq3IlazGlazGlq3GlazGlqzGlq3IlazGl63Gk63Msqyu
        0q2SzK2Yza2Xza2Xza2Xza2Xzq6YzK2Y0q2Usq2vka3Kl63Glq3Ilq3Ilq3Ilq3Il63Gl67Il67Il67Jl67Ilq3Gl63Il63I
        l67ImK7Jl67Ilq3Glq3Ilq3Ilq3Ilq3Ila3GlazGlq3IlazGlq3IlqzGka3MtK2u1qyO0a2U0qyS062S062S0q2S062S0a2U
        1q2OtKyskKzKl63Glq3Glq3Ilq3IlKzGj6jFj6jFkKrGj6jFj6jFj6jFjqfFj6jFj6jFj6jFkKjGla3Glq3Ilq3Ila3Gla3G
        lq3GlazGlazGlazGlazGl63Gka3KtK2u1a2P0K2U0q2U0a2U0a2U0q2U0q2U0KyU1q2PtK2ukKzJlqzGlazGlq3Gk6vFoLTK
        wszTv8nTwMvTwMvUwczUwMvTwMvTwMvTwMvTwcvTv8nTmK7GlazGlq3Ilq3Glq3Il6/Kl6/Klq7Jlq7Jl67JmK7Jk6/PtK2u
        1ayP0a2U0q2U0q2U0a2U0q6U0q2U0K2U1q2PtK2uka7Nl67Il6/KmK/JkKvIrr/Q9e/i8e3h8e3h8e3h8u3h8u7i8u3i8u3i
        8e3h8u3h6+jgm7LKlq3Jl67Jl67Kl67Jkaa+kaa+k6e/kKa+kaa8k6e+jKXAsqqo1q2P0a2U0q2U0q2U0qyS0q2U0q2U0a2U
        1q2PsqqojKXAk6e+k6e/kaa+jaK8qbjI7erh6OXe6efg6ujg6efg6ujg6OXe6efg6ujg6uje4+Ldl6vAkKW+kaa+kaa+kaa+
        YEsxX0sxX0sxX0sxX0sxYU4zVUMpl3xn27SazquR0a2U0a2S0q2U0q2S0q2U0KyS2bSal31nVUMpYU4zX0sxYU4zV0IlgXVn
        8e/n6efe6+ng6+ng6ufg6ujg6ujg6+nh6+je7evi4d7WaFY+XEgtX0sxX0sxX0sxWkMiWkMiWkIiWkIiWUIiXUQkUDoXlHlh
        3LWbzquR0q2S0a2S0ayS0q2U0q6U0KyS27WblHlhUDoXW0QkWkIiW0QkUjgTfW9d8vDo6ufe6uje6+jg6+nh6+ng6ufg6+jg
        6ufe7Ori4d3UY04xVz8eWkMiWkIiWUIiW0QmW0QmW0QmW0QmW0QmXkYoUjsblXpj27SazquR0q2U0q2U0a2S0ayS0ayS0KuR
        27SblXpjUjsbXkYoW0QmXUYoUjoXfnBe8e/n6eXd6uje6ufe6uje6+jg6ufg6ufe6eXd7Orh4d3UZE8zWUIiXUQmW0QmW0Qm
        W0QmW0QmW0QmW0QmW0QmXUYoUjsblXlj2bSazquR0q2U0q2U0q2U0q2U0q2S0KuR2bSalHpjUTsZXkYoW0QmXUYoUjoXfnBe
        9fLr6+jg7Ori7eri7uvi7eri7eri7eri7Onh7+7l4+HXZFA1WUAiXUYmWkQmWkMkW0QmW0QmXEMkW0QmW0QmXUYmUTsblXpj
        27WbzquR0a2U0a2S0ayS0a2S0ayS0KuR27SalXpjUjsbXUYoWkMkXUYoUzsXfG5b6OTd4NzT4d3U4d7U4d3U4d3U4d3U4N3U
        4d3U5OHX2NTKZE8zWUIiW0QmW0QmWkMmW0QkW0QmW0QmW0QmW0QmXkYoUTsblHlj2bOazaqP0KuRzquR0KuRzquR0KuRzaqR
        17KYlHljUTsbXUYmWkMkW0QmWkMkXUcoZFAzZE8zZFAzZE8zZFAzZFAzZE8zZFAzY08zZFAzY08xW0QnW0QmW0QkW0QmWkMk
        W0QkWkMkW0QmWkQkWkMkXUYoUTsZmH1m5Lyh17KY27Sb27Sb27Sb27Sa2bSa2LOY5LyimX1nUToZXkYoW0QkW0QmW0QmWkMk
        WEAgWUIiWEAgWUIiWUIiWUAiWUAiWUAgWEAgWUIiWEAiWkMkW0QmW0QmWkMkW0QmWkMkWkQkW0QkWkMkW0QmW0QmVj8geF9F
        mX1nlHljlXpjlHpjlHljlXpklXpjlHljmX1meF9DV0AiXUYmWkQkW0QmW0QmW0QmW0QmW0YmW0QmW0QmW0YmW0QmW0QmW0Qm
        W0QmW0QmW0QmW0QmW0QmW0QmW0QkW0QkWkMkWkQkW0QkWkQkW0QkWkQmXUYmV0AgUTsZUjwcUTsZUTsZUjsbUjsbUTsbUjsb
        UDoZV0AgW0QmW0QmW0QmWkQmW0QkWkMkWkMmW0QmWkMkW0QkXEMmWkMkW0QkWkMkW0QmWkMmWkMkW0QmW0QmWkQkWkMkXEMk
        W0QmW0QmW0QmW0QmWkQmWkMkWkQkXUYmXkYoXUYmXUYoXkYoXUYoXUYmXkYoXUYoXkYoXUQmWkMkW0QmW0QkWkMkWkMkWkMk
        W0QmW0QmW0QkWkMkW0QkXEMkW0QkWkMkWkMkW0QkW0QkW0QmWkMkWkQkW0QmXEMkWkMkW0QmW0QmW0QmW0QmW0QmW0QmW0Qk
        W0QmWkQkW0QmWkMkWkQkXEMkW0QmW0QmWkMkWkMkW0QmW0QmWkMkW0QmWkQmW0QmW0QkW0QkW0QmWkMmWkMkWkMkW0QkXEMk
        WkQkW0QkW0QmW0QmWkMkW0QmW0QmW0QkWkMkW0QkWkMkWkMkW0QmW0QmW0QmWkMkW0QkW0QmW0QmW0QmWkMkWkQmWkQmW0Qm
        WkMkWkQkXEMkWkMkWkMkW0QkW0QmW0QmW0QmWkQmW0QkW0QmW0QmWkQkWkMkWkQmWkMkW0QkW0QmW0QmXEMkW0QkWkMkWkMk
        XEMkW0QmWkQkWkQkW0QkW0QmXEMkWkMkW0QmW0QmWkMkW0QmW0QmWkQkW0QmW0QkWkQmWkMkW0QkW0QmW0QmWkMkW0QmW0Qk
        W0QmW0QmWkMkWkMkWkQkW0QkW0QmWkMkW0QmXEMkW0QkW0QmW0QmW0QmW0QkW0QmW0QkXEMkWkQkW0QkWkMkWkQmWkQkW0Qm
        WkQmW0QmW0QkW0QmWkQkW0QmWkQkW0QkW0QmW0QmW0QmWkMkWkMkW0QmWkMmW0QmW0QmW0QmW0QmW0QmWkMkW0QmW0QkWkMk
        W0QmW0QmW0QmW0QmWkMkW0QmWkMkWkQkW0QmWkQkWkQkWkMkW0QmW0QmWkMkW0QmWkQkW0QkW0QmWkMkW0QmW0QmW0QmW0Qk
        WkMkXEMkWkMkWkMkWkMkXEMkWkQkWkMkW0QmW0QmW0QmW0QmWkMkW0QmWkMkW0QmW0QmW0QmWkMkW0QmW0QmW0QmW0QmWkQk
        """

    private func bytes(_ text: String) -> [UInt8] {
        [UInt8](Data(base64Encoded: text.filter { !$0.isWhitespace }) ?? Data())
    }

    func testTheVarnishComesOffAsOnTheServer() throws {
        let view = try JSONDecoder().decode(ColoursView.self, from: Data(Self.numbers.utf8))
        let sum = VarnishSum(view)
        let rgb = bytes(Self.picture), expected = bytes(Self.cleaned)
        let count = Self.width * Self.height
        XCTAssertEqual(rgb.count, count * 3)
        XCTAssertEqual(expected.count, count * 3)
        var rgba = [UInt8](repeating: 255, count: count * 4)
        for at in 0 ..< count {
            for c in 0 ..< 3 { rgba[at * 4 + c] = rgb[at * 3 + c] }
        }
        rgba.withUnsafeMutableBufferPointer { sum.apply(to: $0.baseAddress!, count: count) }
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
        // The varnish did come off: the picture is bluer than it was.
        let blue = (0 ..< count).map { Int(rgba[$0 * 4 + 2]) - Int(rgb[$0 * 3 + 2]) }.reduce(0, +)
        XCTAssertGreaterThan(blue, count * 10)
    }

    func testAPictureKeepsItsSizeAndComesBackWhole() throws {
        let view = try JSONDecoder().decode(ColoursView.self, from: Data(Self.numbers.utf8))
        let renderer = UIGraphicsImageRenderer(size: CGSize(width: 64, height: 48))
        let picture = renderer.image { context in
            UIColor(red: 0.6, green: 0.45, blue: 0.2, alpha: 1).setFill()
            context.fill(CGRect(x: 0, y: 0, width: 64, height: 48))
        }
        let made = try XCTUnwrap(VarnishSum(view).apply(to: picture))
        XCTAssertEqual(made.size, picture.size)
        XCTAssertEqual(made.cgImage?.width, picture.cgImage?.width)
    }
}
