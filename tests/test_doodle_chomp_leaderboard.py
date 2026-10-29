"""Doodle Chomp's high-score board and groups, against a fake of the Worker API.

Tests that make the fake answer 4xx or 5xx skip the `errors` fixture, because
the browser logs those responses as console errors.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fake_leaderboard import API, FakeLeaderboard
from playwright.sync_api import Page, expect

UNAVAILABLE = "The high-score board is unavailable right now."


def row(initials: str, score: int, scope: str = "*", difficulty: str = "explorer", mode: str = "multiples") -> dict:
    return {"initials": initials, "score": score, "level": 3, "scope": scope, "difficulty": difficulty, "mode": mode}


def open_game(page: Page, site_url: str, fake: FakeLeaderboard | None, query: str = "") -> None:
    if fake:
        page.route(f"{API}/**", fake.handle)
        page.goto(f"{site_url}/doodle-chomp?leaderboard={API}{query}#debug")
    else:
        page.goto(f"{site_url}/doodle-chomp#debug")


def play(page: Page, chomps: int = 2) -> None:
    """Start from the menu, chomp right answers (15 points each on Explorer), then end the game."""
    page.click("#playBtn")
    for _ in range(chomps):
        assert page.evaluate("window.__dc.chompRight()")
    page.evaluate("window.__dc.end()")
    expect(page.locator("#ovTitle")).to_have_text("Game over")


def type_initials(page: Page, letters: str) -> None:
    page.locator("#initial0").press_sequentially(letters)


def expect_letters(page: Page, letters: str) -> None:
    for i, letter in enumerate(letters):
        expect(page.locator(f"#initial{i}")).to_have_value(letter)


def click_action(page: Page, label: str) -> None:
    page.wait_for_timeout(500)  # the card ignores clicks for its first moments
    page.click(f"#ovActions button >> text={label}")


def join_group(page: Page, code: str, name: str) -> None:
    """Join a group from the high-score screen, which is left open."""
    if page.locator("#lbOv").is_hidden():
        page.click("#lbOpenMenu")
    page.fill("#lbJoinCode", code)
    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(f"Joined {name}. Scores you save from now on go to {name} too.")


def stored(page: Page, key: str):
    return page.evaluate("(key) => JSON.parse(localStorage.getItem(key))", key)


def test_board_stays_hidden_until_configured(page: Page, site_url, errors):
    open_game(page, site_url, None)
    expect(page.locator("#menuScoreNote")).to_have_text("Scores are kept in this browser only.")
    expect(page.locator("#lbOpenMenu")).to_be_hidden()
    expect(page.locator("#howtoBoard")).to_have_js_property("hidden", True)  # in How to play
    play(page)
    expect(page.locator(".ov-board")).to_have_count(0)
    expect(page.locator("#ovBody")).to_contain_text("That's a new best score in this browser.")
    assert errors == []


def test_top_ten_score_saves_initials(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245), row("SIS", 400, difficulty="expert")])
    open_game(page, site_url, fake)
    expect(page.locator("#menuWhich")).to_have_text("Multiples · Explorer")
    expect(page.locator("#menuScoreList li")).to_have_text(["1KID300L3", "2MRW245L3"])
    expect(page.locator("#howtoBoard")).to_have_js_property("hidden", False)

    play(page)
    board = page.locator(".ov-board")
    expect(board.locator(".scores-note")).to_have_text("That's #3 on the Multiples · Explorer board.")
    expect(board.locator(".lb-scopes")).to_be_hidden()  # no groups, so no tabs
    expect(board.locator(".lb-public")).to_be_hidden()
    expect(page.locator("#initial0")).to_be_focused()
    type_initials(page, "z3ed")  # letters only, one per slot
    expect_letters(page, "ZED")
    page.click(".save-score button[type=submit]")

    expect(page.locator("#ovTitle")).to_have_text("On the board!")
    expect(board.locator(".scores-note")).to_have_text("Saved! #3 on Everyone.")
    expect(board.locator("li.mine")).to_have_text("3ZED30L1")
    expect(page.locator(".save-score")).to_have_count(0)
    [entry] = fake.posts
    assert entry.pop("seconds") >= 1
    assert entry == {
        "game": "doodle-chomp", "difficulty": "explorer", "mode": "multiples", "initials": "ZED",
        "score": 30, "level": 1, "chomps": 2, "groups": [], "public": True,
    }
    assert stored(page, "games.initials") == "ZED"

    # The menu shows the new entry, and the initials are filled in next time.
    click_action(page, "Change game")
    expect(page.locator("#menuScoreList li.mine")).to_have_text("3ZED30L1")
    play(page)
    expect_letters(page, "ZED")
    assert errors == []


def test_score_below_tenth_place_only_shows_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 500 - i) for i in range(10)])
    open_game(page, site_url, fake)
    play(page)
    expect(page.locator(".ov-board li")).to_have_count(5)
    expect(page.locator(".save-score")).to_have_count(0)
    assert fake.posts == []
    assert errors == []


def test_kindergarten_has_its_own_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 90, difficulty="starter", mode="kinder"), row("MRW", 245)])
    open_game(page, site_url, fake)
    page.click("label:has(#mode-kinder)")
    expect(page.locator("#menuWhich")).to_have_text("Kindergarten")
    expect(page.locator("#menuScoreList li")).to_have_text(["1KID90L3"])
    assert fake.views[-1] == {"game": "doodle-chomp", "scope": "*", "difficulty": "starter", "mode": "kinder"}
    assert errors == []


def test_rejected_save_shows_the_reason(page: Page, site_url):
    fake = FakeLeaderboard(reject_with="pick different initials")
    open_game(page, site_url, fake)
    # Initials saved before the leaderboard moved are still filled in.
    page.evaluate("localStorage.setItem('doodle-chomp:initials', JSON.stringify('WTF'))")
    play(page)
    expect_letters(page, "WTF")
    page.click(".save-score button[type=submit]")
    expect(page.locator(".save-msg")).to_have_text("That didn't save: pick different initials.")
    expect(page.locator(".save-score button[type=submit]")).to_be_enabled()


def test_unavailable_board_does_not_block_the_game(page: Page, site_url):
    fake = FakeLeaderboard(status=500)
    open_game(page, site_url, fake)
    expect(page.locator("#menuScoreNote")).to_have_text(UNAVAILABLE)
    play(page)
    expect(page.locator(".ov-board .scores-note")).to_have_text(UNAVAILABLE)
    expect(page.locator(".save-score")).to_have_count(0)
    click_action(page, "Play again")
    expect(page.locator("#overlay")).to_be_hidden()


def test_high_score_screen_filters_by_game_and_difficulty(page: Page, site_url, errors):
    fake = FakeLeaderboard([
        row("KID", 300),
        row("MRW", 245, difficulty="expert"),
        row("SIS", 120, mode="primes"),
        row("DAD", 90, difficulty="starter", mode="kinder"),
    ])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#lbOv")).to_be_visible()
    expect(page.locator("#lbClose")).to_be_focused()

    # Everything, with each score's board under the initials.
    who = page.locator("#lbList li .who")
    expect(who).to_have_text(["KIDMultiples · Explorer", "MRWMultiples · Expert", "SISPrimes · Explorer", "DADKindergarten"])
    page.select_option("#lbMode", "multiples")
    expect(who).to_have_text(["KIDMultiples · Explorer", "MRWMultiples · Expert"])
    page.select_option("#lbDiff", "expert")
    expect(page.locator("#lbList li")).to_have_text(["1MRW245L3"])  # one board, so no tags
    page.select_option("#lbMode", "primes")
    expect(page.locator("#lbList")).to_be_hidden()
    expect(page.locator("#lbNote")).to_have_text("No scores here yet.")
    assert fake.views[-1] == {"game": "doodle-chomp", "scope": "*", "difficulty": "expert", "mode": "primes"}

    # Game keys wait while the screen is open; Escape closes it.
    page.keyboard.press("Space")
    expect(page.locator("#menu")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("#lbOv")).to_be_hidden()
    expect(page.locator("#lbOpenMenu")).to_be_focused()
    page.reload()
    page.click("#lbOpenMenu")
    expect(page.locator("#lbMode")).to_have_value("primes")
    expect(page.locator("#lbDiff")).to_have_value("expert")
    assert errors == []


def test_start_a_group_and_share_an_invite(page: Page, site_url, errors):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    fake = FakeLeaderboard([row("KID", 300)])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#lbNoGroups")).to_be_visible()

    page.fill("#lbGroupName", "Family")
    page.click("#lbCreateForm button")
    expect(page.locator("#lbGroupNote")).to_have_text("Started Family. Share code K7QP so others can join.")
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    expect(page.locator("#lbScopes button")).to_have_text(["Everyone", "Family"])
    expect(page.locator("#lbScopes button[aria-pressed=true]")).to_have_text("Family")
    expect(page.locator("#lbNote")).to_have_text("No scores in Family yet.")
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "Family"}]

    page.click("#lbGroupList button >> text=Share")
    expect(page.locator("#lbGroupList button").first).to_have_text("Copied")
    text = page.evaluate("navigator.clipboard.readText()")
    assert text.startswith('Join "Family" on the Doodle Chomp high-score board with code K7QP: ')
    link = urlparse(text.rsplit(" ", 1)[-1])
    assert link.path == "/doodle-chomp"
    assert parse_qs(link.query) == {"leaderboard": [API], "join": ["K7QP"]}

    # The menu now shows the group's board.
    page.click("#lbClose")
    expect(page.locator("#menuWhich")).to_have_text("Multiples · Explorer · Family")
    assert errors == []


def test_group_members_save_to_their_groups(page: Page, site_url, errors):
    fake = FakeLeaderboard(
        [row("MOM", 500, scope="K7QP")] + [row(f"A{chr(65 + i)}A", 500 - i) for i in range(10)],
        groups={"K7QP": "Family", "W3XY": "Friends"},
    )
    open_game(page, site_url, fake)
    join_group(page, "k7qp", "Family")  # lower case is fine
    join_group(page, "W3XY", "Friends")
    page.click("#lbScopes button >> text=Family")
    page.click("#lbClose")
    expect(page.locator("#menuScoreList li")).to_have_text(["1MOM500L3"])

    # Not a top-10 public score, but in a group every score can be saved.
    play(page)
    board = page.locator(".ov-board")
    expect(board.locator(".lb-scopes button")).to_have_text(["Everyone", "Family", "Friends"])
    expect(board.locator(".lb-scopes button[aria-pressed=true]")).to_have_text("Family")
    expect(page.locator("#lbPublic")).to_be_visible()
    expect(page.locator("#lbPublic")).to_be_checked()
    page.uncheck("#lbPublic")
    type_initials(page, "DAD")
    page.click(".save-score button[type=submit]")
    expect(board.locator(".scores-note")).to_have_text("Saved! #2 in Family, #1 in Friends.")
    expect(board.locator("li.mine")).to_have_text("2DAD30L1")
    assert fake.posts[0]["groups"] == ["K7QP", "W3XY"]
    assert fake.posts[0]["public"] is False

    board.locator(".lb-scopes button >> text=Friends").click()
    expect(board.locator("li.mine")).to_have_text("1DAD30L1")

    # The public-board choice is remembered for the next game.
    click_action(page, "Play again")
    page.evaluate("window.__dc.chompRight()")
    page.evaluate("window.__dc.end()")
    expect(page.locator("#lbPublic")).not_to_be_checked()
    assert errors == []


def test_joining_from_game_over_offers_to_save(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 500 - i) for i in range(10)], groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    play(page)
    expect(page.locator(".save-score")).to_have_count(0)  # not a top-10 score
    page.click(".ov-board .lb-open")
    join_group(page, "K7QP", "Family")
    page.click("#lbClose")
    expect(page.locator(".save-score")).to_be_visible()
    expect(page.locator(".ov-board .lb-scopes button[aria-pressed=true]")).to_have_text("Family")
    assert errors == []


def test_groups_are_shared_with_other_games(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    join_group(page, "K7QP", "Family")
    page.goto(f"{site_url}/funnels-and-buckets?leaderboard={API}")
    page.click("#lbOpenMenu")
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    assert errors == []


def test_invite_link_opens_the_join_screen(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "The Warkentins"})
    open_game(page, site_url, fake, "&join=k7qp")
    expect(page.locator("#lbOv")).to_be_visible()
    expect(page.locator("#lbJoinCode")).to_have_value("K7QP")
    expect(page.locator("#lbGroupNote")).to_have_text("You’re invited to The Warkentins. Tap Join to add it.")
    assert parse_qs(urlparse(page.url).query) == {"leaderboard": [API]}

    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(
        "Joined The Warkentins. Scores you save from now on go to The Warkentins too."
    )
    assert errors == []


def test_joining_checks_the_code(page: Page, site_url):
    fake = FakeLeaderboard(groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    note = page.locator("#lbGroupNote")
    page.locator("#lbJoinCode").press_sequentially("a-b")
    expect(page.locator("#lbJoinCode")).to_have_value("AB")
    page.click("#lbJoinForm button")
    expect(note).to_have_text("Group codes are four letters and numbers, like K7QP.")
    page.fill("#lbJoinCode", "ZZZZ")
    page.click("#lbJoinForm button")
    expect(note).to_have_text("There’s no group with code ZZZZ.")


def test_leave_a_group(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300)], groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    join_group(page, "K7QP", "Family")
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.click("#lbGroupList button >> text=Leave")
    expect(page.locator("#lbGroupNote")).to_have_text("Left Family.")
    assert dialogs == ["Leave Family? You can rejoin later with code K7QP."]
    expect(page.locator("#lbNoGroups")).to_be_visible()
    expect(page.locator("#lbScopes")).to_be_hidden()
    expect(page.locator("#lbList li .who")).to_have_text(["KIDMultiples · Explorer"])
    assert stored(page, "games.groups") == []
    assert errors == []
