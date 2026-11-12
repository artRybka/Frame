from __future__ import annotations

import json
import threading
import time

import httpx
import numpy as np
from conftest import jpeg_bytes
from PIL import Image

from frame_server.imaging.color import linear_to_oklab, u8_to_linear
from frame_server.library import (
    Item,
    ItemKind,
    Library,
    Playlist,
    PlaylistKind,
    PlaylistRules,
    colors,
)
from frame_server.library.colors import TONE_GROUPS, TONE_TAG, analyse, family, has_colours
from frame_server.library.models import MINE_FAVORITES, MINE_PLAYLISTS, ColorSwatch
from frame_server.library.museums import (
    MUSEUMS,
    ArtInstituteChicago,
    ClevelandMuseum,
    Discovery,
    MetropolitanMuseum,
    Museum,
    Rijksmuseum,
    WikimediaCommons,
    by_artist,
)
from frame_server.library.seed import PACKS, SEED_QUERIES


def _item(n: int, **kw) -> Item:
    kw.setdefault("title", f"Picture {n}")
    return Item(id=f"test:{n}", source="test", source_id=str(n), **kw)


def test_query_filters_and_facets(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(
        _item(1, artist="Claude Monet", styles=["Impressionism"], color_tags=["blue"], year=1899)
    )
    lib.upsert(_item(2, artist="Katsushika Hokusai", medium="Color woodblock print", year=1831))
    lib.upsert(_item(3, artist="Claude Monet", color_tags=["warm"], year=1891, favorite=True))
    lib.upsert(_item(4, artist="Someone", excluded=True))

    assert lib.query()[0] == 3
    assert {i.id for i in lib.query(PlaylistRules(artists=["claude monet"]))[1]} == {
        "test:1",
        "test:3",
    }
    assert [i.id for i in lib.query(PlaylistRules(query="woodblock"))[1]] == ["test:2"]
    assert [i.id for i in lib.query(PlaylistRules(colors=["blue"]))[1]] == ["test:1"]
    assert [i.id for i in lib.query(PlaylistRules(year_from=1890, year_to=1895))[1]] == ["test:3"]
    assert [i.id for i in lib.query(PlaylistRules(favorites_only=True))[1]] == ["test:3"]
    assert [i.id for i in lib.query(sort="year")[1]] == ["test:2", "test:3", "test:1"]

    facets = lib.facets()
    assert facets.artists[0].value == "Claude Monet" and facets.artists[0].count == 2
    assert all(f.value != "Someone" for f in facets.artists)


def test_lists_survive_works_added_while_they_are_read(tmp_path, monkeypatch) -> None:
    """Playlists and Odkrywaj went 500 ("dictionary changed size during
    iteration") when an import added a work while a list was being read."""
    import threading

    from frame_server.library import repo

    lib = Library(tmp_path / "lib.db")
    for n in range(5):
        lib.upsert(_item(n))
    lib.set_favorite("owner", "test:0", True)
    added = iter(range(100, 200))
    real_matches = repo.matches

    def matches_while_importing(*args, **kwargs):
        # Another thread adds a work and a heart in the middle of the read.
        n = next(added)

        def write() -> None:
            lib.upsert(_item(n))
            lib.set_favorite("owner", f"test:{n}", True)

        writer = threading.Thread(target=write)
        writer.start()
        writer.join()
        return real_matches(*args, **kwargs)

    monkeypatch.setattr(repo, "matches", matches_while_importing)
    assert lib.query()[0] == 5
    liked = lib.save_playlist(
        Playlist(name="Liked", kind=PlaylistKind.SMART, rules=PlaylistRules(favorites_only=True))
    )
    assert "test:0" in {i.id for i in lib.playlist_items(liked)}


def test_upsert_keeps_user_state(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    lib.upsert(_item(1))
    lib.update("test:1", favorite=True)
    lib.upsert(_item(1, title="Renamed"))
    reloaded = Library(tmp_path / "lib.db").get("test:1")
    assert reloaded is not None and reloaded.favorite and reloaded.title == "Renamed"


def test_batch_is_one_transaction(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    with lib.batch():
        for n in range(3):
            lib.upsert(_item(n))
        # Not committed yet: another connection does not see the writes.
        assert Library(tmp_path / "lib.db").count() == 0
    assert Library(tmp_path / "lib.db").count() == 3

    try:
        with lib.batch():
            lib.delete("test:0")
            lib.update("test:1", favorite=True)
            raise RuntimeError("halfway")
    except RuntimeError:
        pass
    # Rolled back on disk and in the cached copy alike.
    assert lib.count() == 3 and not lib.get("test:1").favorite  # type: ignore[union-attr]


def test_state_kept_from_the_loop_never_waits_for_the_lock(tmp_path) -> None:
    """keep_state is read back at once and written by a thread, even while
    another thread holds the library (the frame's question waited 78 s)."""
    lib = Library(tmp_path / "lib.db")
    lib.set_state("app", {"seen": 0})
    assert lib.count() == 0  # the items read once, before the lock is taken
    held, release = threading.Event(), threading.Event()

    def hold() -> None:
        with lib.batch():
            held.set()
            release.wait(5)

    holder = threading.Thread(target=hold)
    holder.start()
    held.wait(5)
    started = time.monotonic()
    lib.keep_state("app", {"seen": 1})
    assert lib.get("nothing") is None
    assert lib.get_state("app") == {"seen": 1}
    assert time.monotonic() - started < 1
    release.set()
    holder.join(5)
    lib.close()  # what is still kept goes to disk
    assert Library(tmp_path / "lib.db").get_state("app") == {"seen": 1}


def test_a_state_set_later_is_not_overwritten_by_one_kept_before(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    with lib.batch():  # the writer waits for this
        lib.keep_state("k", 1)
        lib.set_state("k", 2)
    lib.write_kept()
    assert lib.get_state("k") == 2
    assert Library(tmp_path / "lib.db").get_state("k") == 2


def test_playlists_and_state(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(5):
        lib.upsert(_item(n, artist="A" if n % 2 else "B"))
    smart = lib.save_playlist(Playlist(name="A only", rules=PlaylistRules(artists=["A"])))
    manual = lib.save_playlist(
        Playlist(name="Picks", kind=PlaylistKind.MANUAL, item_ids=["test:4", "test:0", "gone"])
    )
    assert smart.id is not None and manual.id is not None
    assert {i.id for i in lib.playlist_items(smart)} == {"test:1", "test:3"}
    assert [i.id for i in lib.playlist_items(manual)] == ["test:4", "test:0"]
    assert lib.playlist_summary(manual).item_count == 2
    assert [p.name for p in lib.playlists()] == ["A only", "Picks"]
    assert lib.delete_playlist(smart.id) and lib.playlist(smart.id) is None

    lib.set_state("k", {"a": 1})
    assert lib.get_state("k") == {"a": 1}
    lib.record_shown("test:1", "test")
    assert lib.history()[0]["item_id"] == "test:1"
    assert lib.get("test:1").show_count == 1  # type: ignore[union-attr]


def test_a_playlist_sends_the_main_colour_of_each_cover_work(tmp_path) -> None:
    from frame_server.library.models import ColorSwatch

    lib = Library(tmp_path / "lib.db")
    lib.upsert(
        _item(
            1,
            colors=[
                ColorSwatch(hex="#202a60", weight=0.3),
                ColorSwatch(hex="#c8b890", weight=0.6),
                ColorSwatch(hex="#e03020", weight=0.9, accent=True),
            ],
        )
    )
    lib.upsert(_item(2))  # not analysed yet: no colour
    lib.upsert(_item(3, colors=[ColorSwatch(hex="#406030", weight=1.0)]))
    picks = lib.save_playlist(
        Playlist(name="Picks", kind=PlaylistKind.MANUAL, item_ids=["test:3", "test:2", "test:1"])
    )
    summary = lib.playlist_summary(picks)
    assert summary.cover_item_ids == ["test:3", "test:2", "test:1"]
    assert [c.hex for c in summary.cover_colors] == ["#406030", "#c8b890"]


def test_a_smart_playlist_keeps_a_steady_set_within_its_limit(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(30):
        lib.upsert(_item(n, artist="A", title=f"Work {n}"))
    lib.update("test:7", favorite=True)
    lib.update("test:23", favorite=True)
    playlist = lib.save_playlist(Playlist(name="A", rules=PlaylistRules(artists=["A"]), limit=10))

    first = [i.id for i in lib.playlist_items(playlist)]
    assert len(first) == 10 and {"test:7", "test:23"} <= set(first)  # hearts first
    assert lib.playlist_summary(playlist).item_count == 10
    assert lib.playlist_summary(playlist).limit == 10
    # The same works every time, in the order asked for.
    assert [i.id for i in lib.playlist_items(playlist)] == first
    by_title = [i.id for i in lib.playlist_items(playlist, sort="title")]
    assert sorted(by_title) == sorted(first)
    # Another limit draws again; no limit takes all.
    other = lib.save_playlist(playlist.model_copy(update={"limit": 11}))
    assert len(set(i.id for i in lib.playlist_items(other)) - set(first)) >= 1
    assert len(lib.playlist_items(playlist.model_copy(update={"limit": None}))) == 30
    # A work taken out of the playlist makes room for another one.
    out = playlist.rules.model_copy(update={"exclude_ids": [first[0]]})
    fewer = [i.id for i in lib.playlist_items(playlist.model_copy(update={"rules": out}))]
    assert len(fewer) == 10 and first[0] not in fewer and set(first[1:]) <= set(fewer)


def test_mine_finds_favourites_and_works_on_playlists(tmp_path) -> None:
    lib = Library(tmp_path / "lib.db")
    for n in range(6):
        lib.upsert(_item(n, artist="A" if n < 3 else "B", favorite=n in (0, 4)))
    lib.save_playlist(Playlist(name="Ulubione", rules=PlaylistRules(favorites_only=True)))
    lib.save_playlist(Playlist(name="Picks", kind=PlaylistKind.MANUAL, item_ids=["test:1"]))
    lib.save_playlist(Playlist(name="B late", rules=PlaylistRules(artists=["B"], query="5")))
    # Asks for playlisted works itself: not one of the playlists it looks in.
    lib.save_playlist(Playlist(name="Mine", rules=PlaylistRules(terms=[MINE_PLAYLISTS])))

    def ids(*terms: str, **kw) -> set[str]:
        return {i.id for i in lib.query(PlaylistRules(terms=list(terms), **kw))[1]}

    assert ids(MINE_FAVORITES) == {"test:0", "test:4"}
    # Not "Ulubione" (it has its own term): the manual and the smart one.
    assert ids(MINE_PLAYLISTS) == {"test:1", "test:5"}
    # Either of them, and with other rules both.
    assert ids(MINE_FAVORITES, MINE_PLAYLISTS) == {"test:0", "test:1", "test:4", "test:5"}
    assert ids(MINE_FAVORITES, MINE_PLAYLISTS, artists=["A"]) == {"test:0", "test:1"}
    assert PlaylistRules(terms=[MINE_FAVORITES]).asks_mine()
    assert not PlaylistRules(terms=["style:impressionism"]).asks_mine()


def _lab(rgb: tuple[int, int, int]) -> np.ndarray:
    return linear_to_oklab(u8_to_linear(np.array(rgb, dtype=np.uint8)))


def test_colour_families() -> None:
    assert family(_lab((30, 60, 200))) == "blue"
    assert family(_lab((200, 30, 30))) == "red"
    assert family(_lab((240, 200, 40))) == "yellow"
    assert family(_lab((40, 140, 60))) == "green"
    assert family(_lab((120, 80, 50))) == "brown"
    assert family(_lab((235, 230, 215))) == "white"  # aged paper is not "yellow"
    assert family(_lab((15, 15, 18))) == "black"


def test_analyse_blue_picture() -> None:
    import io

    img = Image.open(io.BytesIO(jpeg_bytes((40, 80, 200))))
    swatches, tags, _ = analyse(img)
    assert "blue" in tags and "cool" in tags
    assert swatches[0].hex.startswith("#")


def test_analyse_finds_small_vivid_accents() -> None:
    # A Vermeer-like interior: a pale wall, brown table and dark corners,
    # with a blue apron, a yellow bodice and a red skirt of a few percent.
    rng = np.random.default_rng(3)
    pixels = np.empty((240, 240, 3), np.uint8)
    pixels[:] = (200, 196, 176)
    pixels[120:] = (76, 62, 46)
    pixels[200:, :80] = (30, 28, 26)
    pixels[60:110, 100:130] = (26, 60, 120)  # apron
    pixels[30:60, 100:130] = (180, 150, 80)  # bodice
    pixels[110:150, 100:130] = (120, 32, 28)  # skirt
    noise = rng.integers(-6, 7, pixels.shape)
    img = Image.fromarray(np.clip(pixels.astype(int) + noise, 0, 255).astype(np.uint8))
    swatches, tags, _ = analyse(img)
    dominant = [s for s in swatches if not s.accent]
    accents = [s for s in swatches if s.accent]
    assert 1 <= len(dominant) <= 4 and swatches[: len(dominant)] == dominant  # dominant first
    assert dominant[0].weight >= 0.3
    assert len(accents) == 3 and all(0.01 <= s.weight <= 0.04 for s in accents)
    # Accents are tagged apart: the picture is not "in shades of blue".
    assert {"accent:blue", "accent:yellow", "accent:red"} <= set(tags)
    assert not {"blue", "yellow", "red"} & set(tags)


def test_colour_tags_go_by_area() -> None:
    # A gold altarpiece with a blue robe on a fifth of it is blue; with a
    # robe of a few percent it is warm, with a blue accent.
    def altarpiece(robe_rows: int) -> Image.Image:
        pixels = np.empty((200, 200, 3), np.uint8)
        pixels[:] = (190, 140, 60)
        pixels[100 : 100 + robe_rows, 60:140] = (40, 70, 170)
        return Image.fromarray(pixels)

    _, wide, _ = analyse(altarpiece(100))
    _, narrow, _ = analyse(altarpiece(10))
    assert "blue" in wide and "accent:blue" not in wide
    assert "blue" not in narrow and "accent:blue" in narrow and "warm" in narrow
    assert has_colours(narrow, ["accent:blue"]) and not has_colours(narrow, ["blue"])
    assert not has_colours(wide, ["accent:blue"])  # blue, not a blue accent


def test_colour_and_accent_must_both_fit() -> None:
    blue_with_red = ["blue", "cool", "accent:red"]
    blue_plain = ["blue", "cool"]
    red_on_brown = ["brown", "warm", "accent:red"]
    # Within a group any one will do...
    assert has_colours(blue_plain, ["blue", "green"])
    assert has_colours(blue_with_red, ["accent:red", "accent:yellow"])
    # ...but a colour (or mood) and an accent both have to fit.
    assert has_colours(blue_with_red, ["blue", "accent:red"])
    assert has_colours(blue_with_red, ["cool", "accent:red"])
    assert not has_colours(blue_plain, ["blue", "accent:red"])
    assert not has_colours(red_on_brown, ["blue", "accent:red"])


def test_only_colours_ask_for_pictures_painted_in_them_alone() -> None:
    from frame_server.library.colors import painted_in, shown_tags

    # The fewest families that make 80 % of the coloured pixels.
    assert painted_in({"blue": 0.5, "teal": 0.3, "red": 0.04, "gray": 0.16}) == ["blue", "teal"]
    assert painted_in({"blue": 0.4, "orange": 0.3, "gray": 0.3}) == ["blue", "orange"]
    assert painted_in({"gray": 0.7, "white": 0.3}) == []

    nocturne = ["blue", "gray", "only:blue", "cool"]
    sea = ["blue", "teal", "accent:orange", "only:blue", "only:teal"]
    harbour = ["blue", "orange", "only:blue", "only:orange"]
    grey_sketch = ["gray", "white", "only:blue"]  # a touch of blue, no more
    only_blue = ["only:blue", "only:teal"]
    assert has_colours(nocturne, only_blue) and has_colours(sea, only_blue)
    assert not has_colours(harbour, only_blue)
    assert not has_colours(grey_sketch, only_blue)
    assert not has_colours(sea, ["only:blue"])  # teal too
    # With the other groups: warm and only red or orange.
    assert not has_colours(nocturne, ["warm", "only:blue"])
    # Never shown or counted.
    assert shown_tags(sea) == ["blue", "teal", "accent:orange"]

    # From a picture: blue sea and sky over grey rocks.
    pixels = np.empty((200, 200, 3), np.uint8)
    pixels[:] = (120, 120, 118)
    pixels[:80] = (60, 110, 190)
    pixels[80:150] = (30, 70, 150)
    _, tags, _ = analyse(Image.fromarray(pixels))
    assert "only:blue" in tags and has_colours(tags, ["only:blue", "only:teal"])
    pixels[150:170, :60] = (190, 40, 30)  # a red boat
    _, tags, _ = analyse(Image.fromarray(pixels))
    assert has_colours(tags, ["only:blue", "only:teal", "only:red"])


def test_yellowed_paper_is_not_warm() -> None:
    _, tags, _ = analyse(_etching([(238, 226, 198)]))
    assert "warm" not in tags and not any(t.startswith("accent:") for t in tags)


def test_colourful_needs_several_hues_far_apart() -> None:
    def print_with(*inks: tuple[tuple[int, int, int], int]) -> Image.Image:
        # Ink on old paper, with patches of ``inks`` (colour, rows of 200).
        pixels = np.empty((200, 200, 3), np.uint8)
        pixels[:] = (232, 222, 196)
        pixels[::5] = (40, 34, 30)
        row = 20
        for colour, rows in inks:
            pixels[row : row + rows, 40:160] = colour
            row += rows + 10
        return Image.fromarray(pixels)

    red, blue, green = (170, 40, 35), (40, 70, 160), (60, 120, 60)
    brown = (110, 70, 40)
    # A Madonna's red and blue with green grass: a few percent each will do.
    _, madonna, _ = analyse(print_with((red, 8), (blue, 8), (green, 8)))
    assert "colorful" in madonna and "monochrome" not in madonna
    # Black and white, sepia on old paper and a two-tone print are not.
    _, etching, _ = analyse(_etching([(238, 226, 198)]))
    _, two_tone, _ = analyse(print_with((blue, 40), (brown, 40)))
    _, chalk, _ = analyse(print_with((red, 60)))
    for tags in (etching, two_tone, chalk):
        assert "colorful" not in tags
    assert has_colours(madonna, ["colorful"]) and not has_colours(two_tone, ["colorful"])


def test_colours_at_levels() -> None:
    # A blue sea with a red boat, on grey rocks.
    shares = {"blue": 0.45, "teal": 0.1, "red": 0.04, "gray": 0.35, "white": 0.06}
    tags = ["blue", "accent:red", "cool"]
    assert has_colours(tags, ["blue@much", "red@accent"], shares)
    assert has_colours(tags, ["teal@clear"], shares)
    assert not has_colours(tags, ["blue@clear"], shares)  # more than that
    assert not has_colours(tags, ["red@clear"], shares)  # less than that
    assert not has_colours(tags, ["yellow@accent"], shares)
    assert not has_colours(tags, ["blue@much", "yellow@accent"], shares)  # both must fit
    # Most of its colours (grey and white aside) are blue, and blue and teal.
    assert has_colours(tags, ["blue@most"], shares)
    assert has_colours(tags, ["blue@most", "teal@most"], shares)
    assert not has_colours(tags, ["teal@most"], shares)
    assert not has_colours(tags, ["blue@most", "red@most"], shares)  # red too little
    # A grey drawing with a touch of blue is not "mostly blue".
    assert not has_colours(["gray"], ["blue@most"], {"gray": 0.9, "blue": 0.05})
    # A neutral at "most" counts the whole picture.
    assert has_colours(["white"], ["white@most"], {"white": 0.7, "gray": 0.3})
    assert not has_colours(tags, ["gray@most"], shares)
    # No shares (not analysed yet): no level fits.
    assert not has_colours(tags, ["blue@much"])


def test_tones_must_all_fit() -> None:
    tags = ["blue", "cool", "dark", "muted"]
    assert has_colours(tags, ["tone:cool", "tone:dark"])
    assert not has_colours(tags, ["tone:cool", "tone:light"])
    assert has_colours(tags, ["tone:cool", "blue@much"], {"blue": 0.4})
    # Older rules keep their meaning: one colour or mood of the group will do.
    assert has_colours(tags, ["warm", "blue"])
    assert has_colours(tags, ["light", "dark"])

    # Analysed with the Tonacja sides: those count, the plain moods not.
    sided = [*tags, "tone:cool", "tone:muted", "tone:colorful", "tone:medium"]
    assert has_colours(sided, ["tone:cool", "tone:medium"])
    assert not has_colours(sided, ["tone:cool", "tone:dark"])
    # Two sides of one group: either will do; every group asked must fit.
    assert has_colours(sided, ["tone:dark", "tone:medium"])
    assert has_colours(sided, ["tone:dark", "tone:medium", "tone:cool"])
    assert not has_colours(sided, ["tone:dark", "tone:medium", "tone:warm"])
    assert not has_colours(sided, ["tone:dark", "tone:light"])


def test_every_picture_has_one_side_of_each_tone_group() -> None:
    def tones(pixels: np.ndarray) -> set[str]:
        tags = analyse(Image.fromarray(pixels.astype(np.uint8))).tags
        return {t.removeprefix(TONE_TAG) for t in tags if t.startswith(TONE_TAG)}

    plain = np.full((200, 200, 3), 128)
    grey = tones(plain)
    assert grey == {"neutral", "muted", "monochrome", "medium"}
    for group in TONE_GROUPS:
        assert len(grey & set(group)) == 1
    sunset = plain.copy()
    sunset[:] = (235, 120, 40)
    assert {"warm", "vivid"} <= tones(sunset)
    night = plain.copy()
    night[:] = (25, 40, 90)
    assert {"cool", "dark"} <= tones(night)
    paper = plain.copy()
    paper[:] = (246, 242, 234)
    assert "light" in tones(paper)
    # Kolorowe is everything Mono is not.
    patches = plain.copy()
    for i, colour in enumerate([(200, 40, 40), (40, 80, 200), (40, 160, 60), (230, 200, 40)]):
        patches[i * 50 : (i + 1) * 50] = colour
    assert "colorful" in tones(patches) and "monochrome" not in tones(patches)


def test_monochrome_is_one_tone() -> None:
    def toned(light: tuple[int, int, int], dark: tuple[int, int, int]) -> Image.Image:
        # A photograph in one tone: a gradient from ``light`` to ``dark``.
        ramp = np.linspace(0, 1, 200)[:, None, None]
        pixels = (1 - ramp) * np.array(light) + ramp * np.array(dark)
        return Image.fromarray(np.repeat(pixels, 200, 1).astype(np.uint8))

    sepia = analyse(toned((236, 222, 192), (70, 45, 25))).tags
    cyanotype = analyse(toned((225, 235, 245), (35, 65, 110))).tags
    grey = analyse(toned((240, 240, 240), (20, 20, 20))).tags
    for tags in (sepia, cyanotype, grey):
        assert "monochrome" in tags and "colorful" not in tags
    # A brown picture with a blue sky is two tones, not one.
    pixels = np.asarray(toned((236, 222, 192), (70, 45, 25))).copy()
    pixels[:50] = (90, 140, 200)
    assert "monochrome" not in analyse(Image.fromarray(pixels)).tags


def test_a_faded_colour_print_is_not_monochrome() -> None:
    # A Japanese print gone pale: a pink and a blue-grey robe on yellowed
    # paper, black hair. All of it faint and warm, yet in colours.
    pixels = np.empty((200, 200, 3), np.uint8)
    pixels[:] = (234, 222, 194)
    pixels[20:90, 20:120] = (228, 212, 196)
    pixels[100:180, 60:160] = (192, 194, 190)
    pixels[30:60, 130:180] = (40, 36, 34)
    assert "monochrome" not in analyse(Image.fromarray(pixels)).tags
    # The same print in sepia ink alone stays monochrome.
    pixels[20:90, 20:120] = (200, 184, 156)
    pixels[100:180, 60:160] = (150, 132, 104)
    assert "monochrome" in analyse(Image.fromarray(pixels)).tags


def _street(shutter: bool) -> Image.Image:
    """A brick house front under a pale sky, like Vermeer's Little Street:
    with or without its one red shutter, a five-hundredth of the picture."""
    rng = np.random.default_rng(5)
    pixels = np.empty((400, 320, 3), np.uint8)
    pixels[:] = (125, 84, 62)  # brick
    pixels[:90, :120] = (176, 190, 204)  # sky
    pixels[90:200, :50] = (72, 92, 62)  # a vine
    pixels[300:] = (179, 165, 144)  # cobbles
    pixels[180:300, 40:90] = (84, 65, 51)  # a doorway
    if shutter:
        pixels[220:246, 284:294] = (156, 62, 38)
    noise = rng.integers(-7, 8, pixels.shape)
    return Image.fromarray(np.clip(pixels.astype(int) + noise, 0, 255).astype(np.uint8))


def test_a_small_striking_patch_is_among_the_colours() -> None:
    # Mateusz 2026-11-11 21:24: the red of the shutter belongs on the bar of
    # the Little Street; 21:50: „musi wychodzić także w szukaniu po „akcent:
    # czerwień””. It is of the bricks' own hue and far under an accent's
    # size: a touch among the colours, and a red accent to be found by.
    swatches, tags, shares = analyse(_street(shutter=True))
    plain, plain_tags, _ = analyse(_street(shutter=False))
    assert set(tags) - set(plain_tags) == {"accent:red"} and set(plain_tags) <= set(tags)
    assert has_colours(tags, ["red@accent"], shares) and has_colours(tags, ["accent:red"])
    assert not has_colours(plain_tags, ["red@accent"], shares)
    assert len(swatches) == len(plain) + 1 and swatches[:-1] == plain
    touch = swatches[-1]
    red, green, blue = (int(touch.hex[i : i + 2], 16) for i in (1, 3, 5))
    assert touch.accent and touch.weight <= 0.02
    assert red > 135 and green < 80 and blue < 60
    assert len(swatches) <= 8


def _dark_room(robes: bool) -> Image.Image:
    """Four darks that fill a picture, like Delacroix's two studies of an
    Indian from Calcutta: with or without the greyish white of the robes,
    an eighth of it."""
    rng = np.random.default_rng(11)
    pixels = np.empty((300, 400, 3), np.uint8)
    pixels[:] = (43, 37, 31)
    pixels[:, 130:240] = (66, 55, 44)
    pixels[:, 240:330] = (98, 81, 63)
    pixels[:, 330:] = (27, 22, 19)
    if robes:
        pixels[60:240, 150:230] = (161, 156, 140)
    noise = rng.integers(-5, 6, pixels.shape)
    return Image.fromarray(np.clip(pixels.astype(int) + noise, 0, 255).astype(np.uint8))


def test_a_sizeable_colour_unlike_the_four_largest_is_shown_too() -> None:
    # Mateusz 2026-11-12 12:28, of Delacroix's Indian from Calcutta, whose
    # bar was four darks and a red: „dlaczego np. tu nie ma bieli? … Jest
    # istotnym elementem dzieła.” The four largest colours took every place.
    swatches, tags, _ = analyse(_dark_room(robes=True))
    plain, plain_tags, _ = analyse(_dark_room(robes=False))
    main = [s for s in swatches if not s.accent]
    assert len(main) == 5 and len([s for s in plain if not s.accent]) <= 4
    light = main[-1]
    red, green, blue = (int(light.hex[i : i + 2], 16) for i in (1, 3, 5))
    assert min(red, green, blue) > 125 and 0.08 <= light.weight <= 0.16
    assert all(int(s.hex[1:3], 16) < 110 for s in main[:-1])
    # No tag goes by it, and the eight are still eight at most.
    assert [t for t in tags if t.startswith("accent:")] == [
        t for t in plain_tags if t.startswith("accent:")
    ]
    assert len(swatches) <= 8
    # A fifth colour like the others stays out: the Little Street's walls.
    centres = np.array(
        [[0.3, 0.0, 0.02], [0.4, 0.0, 0.02], [0.5, 0.0, 0.02], [0.6, 0.0, 0.02], [0.72, 0.0, 0.02]]
    )
    weights = np.array([0.3, 0.25, 0.2, 0.15, 0.1])
    merged = colors.merged_colours(centres, weights)
    shown = [c for c, _ in merged[:4]]
    assert colors.passed_over(merged[4:], shown) == []
    centres[4, 0] = 0.85
    assert len(colors.passed_over(colors.merged_colours(centres, weights)[4:], shown)) == 1
    # Nor a small one, however unlike.
    weights = np.array([0.32, 0.26, 0.21, 0.17, 0.04])
    assert colors.passed_over(colors.merged_colours(centres, weights)[4:], shown) == []


def _sheet(
    washes: bool, mount: bool = False, ink: tuple[int, int, int] = (113, 114, 106)
) -> Image.Image:
    """A cream sheet drawn on in pencil, like Cézanne's lithograph of the
    bathers: with or without its pale washes, a green one and a sky that
    is a grey by its numbers; ``mount``: a white mount round it."""
    rng = np.random.default_rng(7)
    pixels = np.empty((300, 400, 3), float)
    pixels[:] = (243, 235, 227)

    def wash(rows: slice, columns: slice, colour: tuple[int, int, int]) -> None:
        # Thin and uneven: more of the paper than of the paint, in patches.
        place = pixels[rows, columns]
        much = np.kron(
            rng.uniform(0.15, 1.0, (place.shape[0] // 10, place.shape[1] // 10)), np.ones((10, 10))
        )
        place += (np.array(colour, float) - place) * much[..., None]

    if washes:
        wash(slice(40, 160), slice(60, 210), (160, 190, 140))
        wash(slice(40, 120), slice(220, 350), (140, 165, 172))
    if mount:
        pixels[:, :60] = (254, 252, 250)
    # The pencil: lines over paper and washes alike, and a shaded place.
    for row in list(range(170, 260, 9)) + list(range(60, 140, 16)):
        pixels[row : row + 3, 40:360] = ink
    pixels[262:290, 250:360] = ink
    pixels[200:250, 250:330] = (176, 174, 166)
    noise = rng.integers(-4, 5, pixels.shape)
    return Image.fromarray(np.clip(pixels + noise, 0, 255).astype(np.uint8))


def _oklab(swatch: ColorSwatch) -> np.ndarray:
    rgb = np.array([int(swatch.hex[i : i + 2], 16) for i in (1, 3, 5)], np.uint8)
    return np.asarray(linear_to_oklab(u8_to_linear(rgb)))


def test_the_tints_of_a_pale_sheet_are_shown(monkeypatch) -> None:
    # Mateusz 2026-11-12 13:46 and 14:28, of Cézanne's lithograph in colours
    # „Kąpiące się”, whose bar was greys and one small green patch:
    # „dlaczego … nie ma zieleni i niebieskiego pod kreską rysunku?”,
    # „zieleni i błękitu powinno być chyba więcej na pasku a nie taki mały
    # kwadracik?” Its sky is a grey by its numbers, blue beside its paper.
    swatches, tags, _ = analyse(_sheet(washes=True))
    plain, plain_tags, _ = analyse(_sheet(washes=False))
    fine = linear_to_oklab(colors._sample(_sheet(washes=True), 128))
    sheet = colors.pale(fine)
    assert sheet is not None
    sides = {sheet.side(_oklab(s), colors.TINT_OFF): s for s in swatches if s.accent}
    green, blue = sides["green"], sides["blue"]
    # As large as the washes are: about an eighth and a twelfth of the sheet.
    assert 0.09 <= green.weight <= 0.17 and 0.05 <= blue.weight <= 0.12
    # The sky's colour: hardly a colour by itself, cooler than the paper.
    lab = _oklab(blue)
    assert float(np.hypot(lab[1], lab[2])) < 0.03 and lab[2] < sheet.paper[2] - 0.01
    assert not any(sheet.side(_oklab(s), colors.TINT_OFF) for s in plain)
    # No tag goes by them, and the eight are still eight at most.
    assert "accent:blue" not in tags and len(swatches) <= 8
    assert "monochrome" in plain_tags
    with monkeypatch.context() as patch:
        patch.setattr(colors, "TINT_SHARE", 9.0)
        before, before_tags, _ = analyse(_sheet(washes=True))
    assert tags == before_tags and len(before) == len(swatches) - 1
    # A white mount round a cream sheet is no tint: a wash darkens its paper.
    mounted, _, _ = analyse(_sheet(washes=False, mount=True))
    assert len(mounted) == len(plain) or not any(s.accent for s in mounted)
    # Nor is a sheet printed in a dark blue one drawn on in pencil, or a dark
    # picture a sheet at all.
    assert colors.pale(linear_to_oklab(colors._sample(_sheet(True, ink=(34, 65, 96)), 128))) is None
    assert colors.pale(linear_to_oklab(colors._sample(_dark_room(robes=True), 128))) is None


def _sea(foam: bool) -> Image.Image:
    """A dark sea under a dark sky, like Turner's Dutch men of war: with or
    without the white of its foam, a twentieth of the picture."""
    rng = np.random.default_rng(7)
    pixels = np.empty((300, 400, 3), np.uint8)
    pixels[:] = (94, 78, 61)  # the sky
    pixels[120:] = (84, 98, 108)  # the sea
    pixels[90:150, 120:300] = (168, 155, 129)  # sails
    pixels[220:, :160] = (50, 58, 66)  # a dark wave
    if foam:
        pixels[200:230, 150:350] = (236, 226, 200)
    noise = rng.integers(-7, 8, pixels.shape)
    return Image.fromarray(np.clip(pixels.astype(int) + noise, 0, 255).astype(np.uint8))


def test_a_white_that_stands_out_is_among_the_colours() -> None:
    # Mateusz 2026-11-12 11:38, of Turner's sea, whose bar had browns and
    # greys only: „biały jest wyraźnie wybijającym się akcentem to trzeba go
    # uwzględnić”. The accents are found by their colour; white has none.
    swatches, tags, _ = analyse(_sea(foam=True))
    plain, plain_tags, _ = analyse(_sea(foam=False))
    assert len(swatches) == len(plain) + 1
    white = swatches[-1]
    red, green, blue = (int(white.hex[i : i + 2], 16) for i in (1, 3, 5))
    assert white.accent and 0.02 <= white.weight <= 0.06
    assert min(red, green, blue) > 185 and all(not s.accent or s == white for s in swatches)
    # No tag goes by it: the picture is found as it was.
    assert [t for t in tags if t.startswith("accent:")] == [
        t for t in plain_tags if t.startswith("accent:")
    ]
    assert len(swatches) <= 8
    # A print's paper, the light of a pale picture: its colours show them.
    pale = np.empty((200, 200, 3), np.uint8)
    pale[:] = (236, 226, 200)
    pale[60:140, 40:160] = (168, 155, 129)
    pale[150:170, 20:180] = (94, 78, 61)
    assert not any(s.accent for s in analyse(Image.fromarray(pale)).swatches)
    # One tint and its paper is one tint: nothing is added to an etching.
    assert not any(s.accent for s in analyse(_etching([(238, 226, 198)])).swatches)


def test_a_stamp_on_an_etching_is_no_accent() -> None:
    # One tint stays one tint: a collector's small red stamp does not make
    # an etching a picture with a red accent, and its bar has no touch.
    plain = _etching([(238, 226, 198)])
    pixels = np.asarray(plain).copy()
    pixels[200:214, 290:304] = (190, 40, 30)
    swatches, tags, _ = analyse(Image.fromarray(pixels))
    assert "monochrome" in tags and "monochrome" in analyse(plain).tags
    assert "accent:red" not in tags and not any(s.accent for s in swatches)


def test_analysis_gives_colour_shares() -> None:
    pixels = np.empty((200, 200, 3), np.uint8)
    pixels[:] = (120, 120, 118)
    pixels[:100] = (40, 80, 170)
    shares = analyse(Image.fromarray(pixels)).shares
    assert 0.45 <= shares["blue"] <= 0.55 and 0.45 <= shares["gray"] <= 0.55
    assert "red" not in shares


def test_monochrome_pictures_have_no_accents() -> None:
    swatches, _, _ = analyse(_etching([(238, 226, 198)]))
    assert swatches and not any(s.accent for s in swatches)


def _client(routes: dict[str, dict], sent: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if sent is not None:
            sent.append(request)
        for prefix, body in routes.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(200, json=body)
        return httpx.Response(404, json={})

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_aic_mapping() -> None:
    body = {
        "pagination": {"total": 1},
        "data": [
            {
                "id": 24645,
                "title": "Under the Wave off Kanagawa",
                "artist_title": "Katsushika Hokusai",
                "artist_display": "Katsushika Hokusai\nJapanese, 1760-1849",
                "date_display": "1830/33",
                "date_start": 1830,
                "medium_display": "Color woodblock print; oban",
                "artwork_type_title": "Print",
                "style_titles": ["Japanese (culture or style)"],
                "subject_titles": ["waves", "Mount Fuji"],
                "place_of_origin": "Japan",
                "description": "<p>Famous &amp; blue.</p>",
                "image_id": "abc",
                "thumbnail": {"width": 6679, "height": 4577},
                "is_public_domain": True,
            },
            {"id": 2, "title": "No image", "is_public_domain": True, "image_id": None},
        ],
    }
    sent: list[httpx.Request] = []
    with _client({"https://api.artic.edu/api/v1/artworks/search": body}, sent) as http:
        total, items = ArtInstituteChicago(http).search("hokusai")
    assert total == 1 and len(items) == 1
    # AIC's bare ``q`` matches everything; the query must also restrict.
    query = json.loads(sent[0].content)["query"]["bool"]
    assert query["must"][0]["simple_query_string"]["query"] == "hokusai"
    assert query["filter"] == [{"term": {"is_public_domain": True}}]
    item = items[0]
    assert item.id == "aic:24645" and item.artist_bio == "Japanese, 1760-1849"
    assert item.description == "Famous & blue." and item.subjects == ["waves", "Mount Fuji"]
    assert item.thumb_url.endswith("/abc/full/843,/0/default.jpg")


def test_aic_asks_for_one_type_with_the_artist() -> None:
    """Malarstwo with Monet: AIC is asked for his paintings by the author
    field, not for every work naming him (his caricatures, Mateusz
    2026-11-10)."""
    sent: list[httpx.Request] = []
    body = {"pagination": {"total": 0}, "data": []}
    with _client({"https://api.artic.edu/api/v1/artworks/search": body}, sent) as http:
        ArtInstituteChicago(http).search_kind(by_artist("Claude Monet"), "painting")
        ArtInstituteChicago(http).search_kind("water lilies", "drawing")
    must = json.loads(sent[0].content)["query"]["bool"]["must"]
    assert {"term": {"artwork_type_title.keyword": "Painting"}} in must
    assert {"match": {"artist_title": {"query": "Claude Monet", "operator": "and"}}} in must
    must = json.loads(sent[1].content)["query"]["bool"]["must"]
    assert {"term": {"artwork_type_title.keyword": "Drawing and Watercolor"}} in must
    assert must[1]["simple_query_string"]["query"] == "water lilies"


def test_cleveland_mapping() -> None:
    record = {
        "id": 111654,
        "title": "South Wind, Clear Sky",
        "creators": [{"description": "Katsushika Hokusai (Japanese, 1760–1849)"}],
        "creation_date": "early 1830s",
        "creation_date_earliest": 1830,
        "technique": "color woodblock print",
        "type": "Print",
        "culture": ["Japan, Edo period (1615–1868)"],
        "share_license_status": "CC0",
        "url": "https://clevelandart.org/art/1930.189",
        "images": {"web": {"url": "https://cdn/x_web.jpg", "width": "900", "height": "617"}},
    }
    with _client(
        {
            "https://openaccess-api.clevelandart.org/api/artworks/": {
                "info": {"total": 1},
                "data": [record],
            }
        }
    ) as http:
        _, items = ClevelandMuseum(http).search("hokusai")
    item = items[0]
    assert item.artist == "Katsushika Hokusai" and item.artist_bio == "Japanese, 1760–1849"
    assert item.width == 900 and item.image_url == "https://cdn/x_web.jpg"


def test_met_mapping() -> None:
    obj = {
        "objectID": 436535,
        "title": "Wheat Field with Cypresses",
        "artistDisplayName": "Vincent van Gogh",
        "objectDate": "1889",
        "objectBeginDate": 1889,
        "isPublicDomain": True,
        "primaryImage": "https://images/original.jpg",
        "primaryImageSmall": "https://images/small.jpg",
        "tags": [{"term": "Landscapes"}],
    }
    routes = {
        "https://collectionapi.metmuseum.org/public/collection/v1.1/search": {
            "total": 1,
            "objectIDs": [436535],
        },
        "https://collectionapi.metmuseum.org/public/collection/v1/objects/436535": obj,
    }
    with _client(routes) as http:
        _, items = MetropolitanMuseum(http).search("van gogh")
    assert items[0].subjects == ["Landscapes"] and items[0].year == 1889


def test_wikimedia_mapping() -> None:
    page = {
        "pageid": 123,
        "title": "File:Chełmoński Babie lato.jpg",
        "imageinfo": [
            {
                "url": "https://upload/full.jpg",
                "thumburl": "https://upload/600px.jpg",
                "descriptionurl": "https://commons/File",
                "width": 3000,
                "height": 2000,
                "extmetadata": {
                    "ObjectName": {"value": "Babie lato"},
                    "DateTimeOriginal": {"value": "1875"},
                    "LicenseShortName": {"value": "Public domain"},
                },
            }
        ],
    }
    body = {"query": {"pages": {"123": page}}}
    with _client({"https://commons.wikimedia.org/w/api.php": body}) as http:
        _, items = WikimediaCommons(http).search("Category:Paintings by Józef Chełmoński")
    item = items[0]
    assert item.artist == "Józef Chełmoński" and item.title == "Babie lato" and item.year == 1875
    assert item.kind == ItemKind.ARTWORK and item.id == "wmc:123"

    page["imageinfo"][0]["extmetadata"]["LicenseShortName"]["value"] = "CC BY-SA 4.0"
    with _client({"https://commons.wikimedia.org/w/api.php": body}) as http:
        assert WikimediaCommons(http).search("Category:X")[1] == []
        _, items = WikimediaCommons(http, private_use=True).search("Category:X")
    assert items[0].license == "CC BY-SA 4.0"


def test_wikimedia_category_pages_by_token() -> None:
    def file(n: int) -> dict:
        info = {"url": f"https://u/{n}.jpg", "extmetadata": {"LicenseShortName": {"value": "CC0"}}}
        return {"pageid": n, "title": f"File:{n}.jpg", "imageinfo": [info]}

    sent: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        start = int(request.url.params.get("gcmcontinue", "0"))
        size = int(request.url.params["gcmlimit"])
        pages = {str(n): file(n) for n in range(start, min(start + size, 5))}
        body: dict = {"query": {"pages": pages}}
        if start + size < 5:
            body["continue"] = {"gcmcontinue": str(start + size), "continue": "gcmcontinue||"}
        return httpx.Response(200, json=body)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        total, items = WikimediaCommons(http).search("Category:X", limit=2, page=2)
        assert [i.source_id for i in items] == ["2", "3"] and total == 6
        total, items = WikimediaCommons(http).search("Category:X", limit=2, page=3)
        assert [i.source_id for i in items] == ["4"] and total == 5


RIJKS_OBJECT = {
    "id": "https://id.rijksmuseum.nl/200108369",
    "type": "HumanMadeObject",
    "classified_as": [
        {
            "notation": [
                {"@language": "nl", "@value": "schilderij"},
                {"@language": "en", "@value": "painting"},
            ]
        }
    ],
    "identified_by": [
        {"type": "Identifier", "content": "SK-A-2344"},
        {
            "type": "Name",
            "content": "Het melkmeisje",
            "language": [{"id": "http://vocab.getty.edu/aat/300388256"}],
        },
        {"type": "Name", "content": "The Milkmaid", "language": [{"id": Rijksmuseum.english}]},
    ],
    "produced_by": {
        "part": [
            {"carried_out_by": [{"notation": [{"@language": "en", "@value": "Johannes Vermeer"}]}]}
        ],
        "timespan": {
            "begin_of_the_begin": "1660-01-01T00:00:00Z",
            "identified_by": [{"content": "c. 1660", "language": [{"id": Rijksmuseum.english}]}],
        },
    },
    "referred_to_by": [
        {
            "classified_as": [{"id": Rijksmuseum.medium_type}],
            "content": "oil on canvas",
            "language": [{"id": Rijksmuseum.english}],
        },
        {"classified_as": [{"id": Rijksmuseum.description_type}], "content": "Een dienstmaagd."},
    ],
    "subject_of": [
        {
            "digitally_carried_by": [
                {
                    "access_point": [{"id": "https://iiif.micr.io/QkOGy/full/max/0/default.jpg"}],
                    "referred_to_by": [
                        {"content": "https://creativecommons.org/publicdomain/mark/1.0/"}
                    ],
                }
            ]
        },
        {
            "digitally_carried_by": [
                {
                    "format": "text/html",
                    "access_point": [
                        {"id": "https://www.rijksmuseum.nl/nl/collectie/object/SK-A-2344"}
                    ],
                }
            ]
        },
    ],
}


def test_rijksmuseum_mapping_and_fallback_to_title() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.startswith(Rijksmuseum.api):
            found = "title" in request.url.params
            items = [{"id": "https://id.rijksmuseum.nl/200108369"}] if found else []
            return httpx.Response(
                200, json={"partOf": {"totalItems": len(items)}, "orderedItems": items}
            )
        if url == "https://id.rijksmuseum.nl/200108369":
            assert request.headers["Accept"] == "application/ld+json"
            return httpx.Response(200, json=RIJKS_OBJECT)
        return httpx.Response(404)

    with httpx.Client(transport=httpx.MockTransport(handler)) as http:
        total, items = Rijksmuseum(http).search("Milkmaid")
    assert total == 1
    item = items[0]
    assert item.id == "rijks:200108369" and item.title == "The Milkmaid"
    assert item.artist == "Johannes Vermeer" and item.year == 1660 and item.date_text == "c. 1660"
    assert item.medium == "oil on canvas" and item.classification == "painting"
    assert item.license == "Public Domain Mark 1.0" and item.description == "Een dienstmaagd."
    assert item.thumb_url == "https://iiif.micr.io/QkOGy/full/600,/0/default.jpg"
    assert item.url.endswith("SK-A-2344")


def test_rijksmuseum_skips_works_without_open_image() -> None:
    closed = {**RIJKS_OBJECT, "subject_of": [RIJKS_OBJECT["subject_of"][1]]}
    assert Rijksmuseum(httpx.Client())._map(closed) is None


def test_rijksmuseum_takes_works_in_copyright_for_private_use() -> None:
    from frame_server.library.museums import PRIVATE_LICENCE

    carrier = RIJKS_OBJECT["subject_of"][0]["digitally_carried_by"][0]
    protected = {
        **RIJKS_OBJECT,
        "subject_of": [
            {
                "digitally_carried_by": [
                    {
                        **carrier,
                        "referred_to_by": [
                            {"content": "https://rightsstatements.org/vocab/InC/1.0/"}
                        ],
                    }
                ]
            }
        ],
    }
    assert Rijksmuseum(httpx.Client())._map(protected) is None
    item = Rijksmuseum(httpx.Client(), private_use=True)._map(protected)
    assert item is not None and item.license == PRIVATE_LICENCE
    assert item.image_url == "https://iiif.micr.io/QkOGy/full/max/0/default.jpg"
    # A public-domain picture keeps its own mark.
    free = Rijksmuseum(httpx.Client(), private_use=True)._map(RIJKS_OBJECT)
    assert free is not None and free.license == "Public Domain Mark 1.0"


def test_search_many_walks_pages(tmp_path) -> None:
    from frame_server.library.importer import Importer

    class Counting(Museum):
        key = "aic"
        name = "Counting"
        page_size = 3

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            start = (page - 1) * limit
            return 7, [self._item(str(n), title="x") for n in range(start, min(start + limit, 7))]

        def fetch(self, source_id: str) -> Item | None:
            return None

    original = MUSEUMS["aic"]
    MUSEUMS["aic"] = Counting
    try:
        importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        assert len(importer.search_many("aic", "x", 5)) == 5
        assert len(importer.search_many("aic", "x", 50)) == 7
    finally:
        MUSEUMS["aic"] = original


def test_packs_use_known_museums() -> None:
    keys = [p.key for p in PACKS]
    assert len(keys) == len(set(keys))
    for _, queries in [("starter", SEED_QUERIES), *[(p.key, p.queries) for p in PACKS]]:
        for source, query, limit in queries:
            assert source in MUSEUMS and query and 0 < limit <= 500


def test_discovery_year_check() -> None:
    spec = Discovery(year_from=1850, year_to=1900)
    assert spec.fits(_item(1, year=1850)) and not spec.fits(_item(2, year=1901))
    assert not spec.fits(_item(3)) and Discovery().fits(_item(3))
    assert Rijksmuseum(httpx.Client())._decades(Discovery(year_from=1855, year_to=1871)) == [
        1850,
        1860,
        1870,
    ]
    # Antiquity (up to 499) asks for its last century, not for nothing.
    assert Rijksmuseum(httpx.Client())._decades(Discovery(year_to=499))[0] == 390
    assert Rijksmuseum(httpx.Client())._decades(Discovery(year_to=1)) == [0]


def test_taking_takes_turns_and_skips_known_or_unfit(tmp_path) -> None:
    import random

    from frame_server.library.importer import Importer, Job

    class Fake(Museum):
        name = "Fake"

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            return 0, []

        def fetch(self, source_id: str) -> Item | None:
            return None

        def discover(self, spec, limit=20, page=1):  # type: ignore[no-untyped-def]
            items = [self._item(str(n), year=1800 + n) for n in range(40)]
            return len(items), items[(page - 1) * limit : page * limit]

    class A(Fake):
        key = "aic"

    class B(Fake):
        key = "cma"

    class Importing(Importer):
        def _analysed(self, item: Item) -> Item:
            # Odd ids do not fit once looked at.
            return item.model_copy(update={"width": 100 if int(item.source_id) % 2 else 3000})

    saved = dict(MUSEUMS)
    MUSEUMS.update(aic=A, cma=B)
    try:
        library = Library(tmp_path / "lib.db")
        library.upsert(A(httpx.Client())._item("10", year=1810))
        importer = Importing(library, None, None)  # type: ignore[arg-type]
        importer.cache = type("Cache", (), {"remove": lambda self, item: None})()
        job = Job(id="j", description="draw")
        spec = Discovery(year_from=1800, year_to=1830)
        rng = random.Random(3)
        streams = [source(httpx.Client()).random_draw(spec, rng) for source in (A, B)]
        importer._take(
            streams, 8, job, before=spec.fits, after=lambda item: (item.width or 0) >= 2000
        )
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    assert job.done == 8 and job.skipped > 0 and len(set(job.item_ids)) == 8
    assert "aic:10" not in job.item_ids
    assert {i.split(":")[0] for i in job.item_ids} == {"aic", "cma"}
    for item_id in job.item_ids:
        n = int(item_id.split(":")[1])
        assert n % 2 == 0 and n <= 30


def test_search_all_interleaves_and_reports_failures(tmp_path) -> None:
    from frame_server.library.importer import Importer

    def fake(source: str, count: int, fails: bool = False) -> type[Museum]:
        class Fake(Museum):
            key = source
            name = source

            def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
                if fails:
                    raise httpx.ConnectError("down")
                return count, [self._item(str(n)) for n in range(min(limit, count))]

            def fetch(self, source_id: str) -> Item | None:
                return None

        return Fake

    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(a=fake("a", 3), b=fake("b", 1), c=fake("c", 0, fails=True))
    try:
        importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        total, items, failed = importer.search_all("x", limit=2)
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    assert total == 4 and failed == ["c"]
    assert [i.id for i in items] == ["a:0", "b:0", "a:1"]


def test_fill_adds_only_what_the_playlist_would_pick(tmp_path) -> None:
    import random

    from frame_server.library.importer import Importer, Job

    class Searching(Museum):
        key = "aic"
        name = "Searching"
        page_size = 3

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            # Results mix the artist's works with works about them.
            items = [
                self._item(str(n), artist=query if n % 3 else "Someone Else", year=1880 + n)
                for n in range(12)
            ]
            return len(items), items[(page - 1) * limit : page * limit]

        def fetch(self, source_id: str) -> Item | None:
            return None

    class Importing(Importer):
        def _analysed(self, item: Item) -> Item:
            tags = ["blue"] if int(item.source_id) % 2 else ["warm"]
            return item.model_copy(update={"color_tags": tags})

    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Searching)
    try:
        importer = Importing(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        importer.cache = type("Cache", (), {"remove": lambda self, item: None})()
        job = Job(id="j", description="fill")
        rules = PlaylistRules(artists=["Claude Monet"], colors=["blue"], year_to=1890)
        importer.fill(rules, 10, job, rng=random.Random(1))
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    # Monet (n % 3), blue (odd), up to 1890 (n <= 10): 1, 5, 7.
    assert sorted(job.item_ids) == ["aic:1", "aic:5", "aic:7"]
    assert job.done == 3 and job.skipped == 4  # Monet, until 1890, but not blue: 2, 4, 8, 10


def test_fill_asks_the_museums_as_discover_search_does(tmp_path) -> None:
    import random

    from frame_server.library.importer import Importer, Job, fill_queries

    asked: list[str] = []

    class Recording(Museum):
        key = "aic"
        name = "Recording"

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            asked.append(query)
            return 0, []

        def fetch(self, source_id: str) -> Item | None:
            return None

    rules = PlaylistRules(artists=["Claude Monet", "Paul Signac"], terms=["subject:sea"])
    assert fill_queries(rules) == ["Claude Monet sea", "Paul Signac sea"]
    assert fill_queries(PlaylistRules(query="harbour", terms=["subject:sea"])) == ["harbour sea"]
    assert fill_queries(PlaylistRules(terms=["subject:sea"])) == ["sea"]
    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Recording)
    try:
        importer = Importer(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        importer.fill(rules, 5, Job(id="j", description="fill"), rng=random.Random(1))
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)
    # What Szukaj shows first, then each artist alone.
    assert sorted(asked) == ["Claude Monet", "Claude Monet sea", "Paul Signac", "Paul Signac sea"]


def test_the_catalogues_searches_go_through_the_kept_pages(tmp_path) -> None:
    """The audit of 2026-11-11: the catalogue and the cards' playlists asked
    the museums themselves, every time from the first page; what a set or
    Szukaj had asked was asked again. One path: ``Importer.search``."""
    from frame_server.library.importer import Importer, Job

    asked: list[tuple[str, int]] = []

    class Paged(Museum):
        key = "aic"
        name = "Paged"
        page_size = 2

        def search(self, query: str, limit: int = 20, page: int = 1) -> tuple[int, list[Item]]:
            asked.append((query, page))
            items = [self._item(f"{query}{n}", artist="Claude Monet") for n in range(4)]
            return len(items), items[(page - 1) * limit : page * limit]

        def fetch(self, source_id: str) -> Item | None:
            return None

    class Importing(Importer):
        def _analysed(self, item: Item) -> Item:
            return item

    saved = dict(MUSEUMS)
    MUSEUMS.clear()
    MUSEUMS.update(aic=Paged)
    try:
        importer = Importing(Library(tmp_path / "lib.db"), None, None)  # type: ignore[arg-type]
        # A set's page, as Odkrywaj asks it ...
        assert importer.search("aic", "sea", limit=2, page=1)[0] == 4
        assert asked == [("sea", 1)]
        # ... is not asked again for the catalogue, which goes on from it.
        job = Job(id="j", description="catalogue")
        importer.collect(3, job, queries=[("aic", "sea")], kinds=())
        assert asked == [("sea", 1), ("sea", 2)]
        assert job.item_ids == ["aic:sea0", "aic:sea1", "aic:sea2"]
        # The next round walks the same pages without a request.
        importer.collect(
            1, Job(id="k", description="catalogue"), queries=[("aic", "sea")], kinds=()
        )
        assert asked == [("sea", 1), ("sea", 2)]
        assert importer.library.get("aic:sea3") is not None
    finally:
        MUSEUMS.clear()
        MUSEUMS.update(saved)


def _gradient(dark: tuple[int, int, int], light: tuple[int, int, int]) -> Image.Image:
    t = np.linspace(0, 1, 200)[None, :, None]
    pixels = (np.array(dark) * (1 - t) + np.array(light) * t) * np.ones((150, 1, 1))
    return Image.fromarray(pixels.astype(np.uint8))


def test_tint_spread_tells_monochrome_from_colour() -> None:
    from frame_server.library.colors import tint_spread
    from frame_server.library.style import MONOCHROME_SPREAD

    grey = _gradient((0, 0, 0), (255, 255, 255))
    sepia = _gradient((40, 25, 10), (235, 215, 180))
    ink_on_old_paper = _gradient((30, 30, 30), (240, 228, 200))
    for img in (grey, sepia, ink_on_old_paper):
        assert tint_spread(img) < MONOCHROME_SPREAD
    red_chalk = _gradient((150, 50, 30), (245, 230, 215))
    cyanotype = _gradient((0, 30, 110), (200, 220, 250))
    sky_and_sand = Image.new("RGB", (200, 150), (70, 120, 200))
    sky_and_sand.paste((220, 170, 90), (0, 75, 200, 150))
    for img in (red_chalk, cyanotype, sky_and_sand):
        assert tint_spread(img) > 2 * MONOCHROME_SPREAD


def test_tint_strength_tells_sepia_from_black_and_white() -> None:
    from frame_server.library.colors import tint_strength
    from frame_server.library.style import NEUTRAL_TINT, preset_for_photo

    grey = _gradient((0, 0, 0), (255, 255, 255))
    faintly_warm = _gradient((20, 20, 20), (250, 247, 240))
    sepia = _gradient((40, 25, 10), (235, 215, 180))
    albumen = _gradient((60, 40, 25), (230, 210, 175))
    assert tint_strength(grey) < NEUTRAL_TINT and tint_strength(faintly_warm) < NEUTRAL_TINT
    assert tint_strength(sepia) > 2 * NEUTRAL_TINT and tint_strength(albumen) > 2 * NEUTRAL_TINT
    assert preset_for_photo(grey) == "bw"
    assert preset_for_photo(sepia) == "photo"


def test_auto_preset_by_kind_metadata_and_colour() -> None:
    from frame_server.library.style import auto_preset

    def item(kind: ItemKind = ItemKind.ARTWORK, spread: float = 0.05, **meta: str) -> Item:
        return Item(id="t:1", kind=kind, source="t", source_id="1", tint_spread=spread, **meta)

    assert auto_preset(item(classification="Painting", medium="Oil on canvas")) == "painting"
    assert auto_preset(item(classification="Print", medium="Color woodblock print")) == "graphic"
    assert auto_preset(item(classification="prent", medium="houtsnede")) == "graphic"
    assert auto_preset(item(classification="Poster")) == "graphic"
    assert auto_preset(item(medium="engraving, hand-colored")) == "graphic"
    assert auto_preset(item(classification="Photograph")) == "photo"
    assert auto_preset(item(ItemKind.PHOTO)) == "photo"
    assert auto_preset(item(ItemKind.OWN)) == "painting"
    # No colour of its own: black and white, whatever it is.
    assert auto_preset(item(spread=0.004, classification="Print", medium="Etching")) == "bw"
    assert auto_preset(item(ItemKind.PHOTO, spread=0.002)) == "bw"
    # A dark, warm oil lies on one brown line like a sepia photo: still colour.
    rembrandt = item(spread=0.011, classification="Painting", medium="oil on panel")
    assert auto_preset(rembrandt) == "painting"
    assert auto_preset(item(spread=0.011, medium="olej na desce")) == "painting"
    # Only a black-and-white copy of a painting goes black and white.
    assert auto_preset(item(spread=0.003, classification="Painting")) == "bw"
    # One tint only: black and white when faint, kept when sepia.
    etching = item(spread=0.004, classification="Print", medium="Etching")
    assert auto_preset(etching, tint=0.01) == "bw"
    assert auto_preset(etching, tint=0.03) == "graphic"
    assert auto_preset(item(spread=0.004, medium="Albumen print"), tint=0.03) == "photo"
    assert auto_preset(item(spread=0.004, medium="pen and brown ink"), tint=0.04) == "painting"
    # Not measured yet: by kind and metadata only.
    assert auto_preset(item(spread=None, medium="Lithograph")) == "graphic"  # type: ignore[arg-type]
    # "Painting" is not a print, "sketch" is not Dutch "ets".
    assert auto_preset(item(classification="Paintings", medium="Oil sketch")) == "painting"


def _etching(colours: list[tuple[int, int, int]]) -> Image.Image:
    """Hatching in dark ink over bands of ``colours``: an etching on old
    paper with one colour, a coloured print with several."""
    import numpy as np

    rng = np.random.default_rng(1)
    pixels = np.zeros((240, 320, 3), dtype=np.uint8)
    for i, colour in enumerate(colours):
        pixels[:, i * 320 // len(colours) : (i + 1) * 320 // len(colours)] = colour
    ink = (rng.random((240, 320)) < 0.35) | (np.arange(320)[None, :] % 7 == 0)
    pixels[ink] = (45, 35, 30)
    return Image.fromarray(pixels)


def test_starter_blues_take_turquoise_once(tmp_path) -> None:
    from frame_server.library.seed import _turquoise_blues

    lib = Library(tmp_path / "lib.db")
    blues = lib.save_playlist(
        Playlist(name="W odcieniach błękitu", rules=PlaylistRules(colors=["blue"]))
    )
    own = lib.save_playlist(Playlist(name="Moje błękity", rules=PlaylistRules(colors=["blue"])))
    _turquoise_blues(lib)
    assert lib.playlist(blues.id).rules.colors == ["blue", "teal"]  # type: ignore[arg-type,union-attr]
    assert lib.playlist(own.id).rules.colors == ["blue"]  # type: ignore[arg-type,union-attr]
    lib.save_playlist(blues.model_copy())  # the owner set it back
    _turquoise_blues(lib)
    assert lib.playlist(blues.id).rules.colors == ["blue"]  # type: ignore[arg-type,union-attr]


def test_playlist_counts_lag_behind_the_catalogue_only(tmp_path) -> None:
    """Playlisty does not wait for every smart playlist to look through the
    catalogue again after the server added works: the last counts, fresh
    ones once a playlist is opened, and all at night. A changed playlist,
    or hearts, are counted at once."""
    lib = Library(tmp_path / "lib.db")
    lib.counts_may_lag = True
    lib.upsert(_item(1, artist="Claude Monet"))
    monet = lib.save_playlist(
        Playlist(
            name="Monet", kind=PlaylistKind.SMART, rules=PlaylistRules(artists=["Claude Monet"])
        )
    )
    liked = lib.save_playlist(
        Playlist(name="Ulubione", kind=PlaylistKind.SMART, rules=PlaylistRules(favorites_only=True))
    )
    assert lib.playlist_summary(monet).item_count == 1
    assert lib.playlist_summary(liked).item_count == 0

    lib.upsert(_item(2, artist="Claude Monet"))
    assert lib.playlist_summary(monet).item_count == 1  # as last counted...
    assert len(lib.playlist_items(monet, sort="artist")) == 2  # ...till opened
    summary = lib.playlist_summary(monet)
    assert summary.item_count == 2 and summary.cover_item_ids == ["test:1", "test:2"]

    lib.upsert(_item(3, artist="Claude Monet"))
    assert lib.playlist_summary(monet).item_count == 2
    lib.recount()  # at night
    assert lib.playlist_summary(monet).item_count == 3

    lib.update("test:2", favorite=True)
    assert lib.playlist_summary(liked).item_count == 1  # hearts: at once
    narrower = lib.save_playlist(
        monet.model_copy(update={"rules": PlaylistRules(artists=["Nobody"])})
    )
    assert lib.playlist_summary(narrower).item_count == 0  # its own change: at once

    lib.counts_may_lag = False  # tests and a server without its background: always fresh
    lib.upsert(_item(4, artist="Nobody"))
    assert lib.playlist_summary(narrower).item_count == 1


def test_state_is_read_while_another_thread_writes(tmp_path) -> None:
    """2026-11-05: the frame's question read the app's state on the event
    loop and waited 6 s for a long write elsewhere. The key/value state is
    read from memory, never waiting for the library's lock; a value written
    inside a batch that fails is forgotten."""
    import threading
    import time

    lib = Library(tmp_path / "lib.db")
    lib.set_state("a", {"n": 1})
    inside, done = threading.Event(), threading.Event()

    def long_write() -> None:
        with lib.batch():
            lib.set_state("b", 2)
            inside.set()
            done.wait(5)

    writer = threading.Thread(target=long_write)
    writer.start()
    assert inside.wait(5)
    try:
        started = time.monotonic()
        assert lib.get_state("a") == {"n": 1}
        assert lib.get_state("b") == 2
        assert time.monotonic() - started < 1  # without waiting for the batch
    finally:
        done.set()
        writer.join()
    assert Library(tmp_path / "lib.db").get_state("b") == 2  # on the disk too

    try:
        with lib.batch():
            lib.set_state("c", 3)
            lib.delete_state("a")
            raise RuntimeError("failed")
    except RuntimeError:
        pass
    assert lib.get_state("c") is None and lib.get_state("a") == {"n": 1}


def test_closing_waits_for_a_write_in_progress(tmp_path) -> None:
    """A write on another thread (a download's note, the night's state)
    holds the connection: closing under it crashed the interpreter (the
    server tests' exit 139)."""
    library = Library(tmp_path / "lib.db")
    inside, leave = threading.Event(), threading.Event()

    def write() -> None:
        with library._db() as db:
            inside.set()
            leave.wait(5)
            db.execute("INSERT OR REPLACE INTO kv (key, value) VALUES ('late', '1')")

    writer = threading.Thread(target=write)
    writer.start()
    assert inside.wait(5)
    closer = threading.Thread(target=library.close)
    closer.start()
    closer.join(0.3)
    assert closer.is_alive()  # waits for the write to end
    leave.set()
    writer.join(5)
    closer.join(5)
    assert not writer.is_alive() and not closer.is_alive()
    assert Library(tmp_path / "lib.db").get_state("late") == 1  # written before the close
