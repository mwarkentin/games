"""Doodle Chomp's high-score board and groups, against a fake of the Worker API.

Tests that make the fake answer 4xx or 5xx skip the `errors` fixture, because
the browser logs those responses as console errors.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fake_leaderboard import API, FakeLeaderboard, Held, without_worker
from playwright.sync_api import Page, expect

UNAVAILABLE = "The high-score board is unavailable right now."
# Local midnight on Monday, as the page works it out.
START_OF_WEEK = "() => { const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() - (d.getDay() + 6) % 7); return d.getTime(); }"


def row(initials: str, score: int, scope: str = "*", difficulty: str = "explorer", mode: str = "multiples", **extra) -> dict:
    return {"initials": initials, "score": score, "level": 3, "scope": scope, "difficulty": difficulty, "mode": mode, **extra}


def open_game(page: Page, site_url: str, fake: FakeLeaderboard | Held | None, query: str = "") -> None:
    if fake:
        page.route(f"{API}/**", fake.handle)
        page.goto(f"{site_url}/doodle-chomp?leaderboard={API}{query}#debug")
    else:
        without_worker(page, site_url, "doodle-chomp")
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
    expect(page.locator("#menuWhich")).to_have_text("Multiples · Explorer · This week")
    expect(page.locator("#menuScoreList li")).to_have_text(["1KID300L3", "2MRW245L3"])
    expect(page.locator("#menuScopes")).to_be_hidden()  # no groups, so no tabs
    expect(page.locator("#howtoBoard")).to_have_js_property("hidden", False)

    play(page)
    board = page.locator(".ov-board")
    expect(board.locator(".scores-note")).to_have_text("That's #3 this week on the Multiples · Explorer board.")
    expect(board.locator(".lb-scopes")).to_be_hidden()  # no groups, so no tabs
    expect(board.locator(".lb-public")).to_be_hidden()
    expect(page.locator("#initial0")).to_be_focused()
    type_initials(page, "z3ed")  # letters only, one per slot
    expect_letters(page, "ZED")
    page.click(".save-score button[type=submit]")

    expect(page.locator("#ovTitle")).to_have_text("On the board!")
    expect(board.locator(".scores-note")).to_have_text("Saved! #3 this week on Everyone.")
    expect(board.locator("li.mine")).to_have_text("3ZED30L1")
    expect(page.locator(".save-score")).to_have_count(0)
    [entry] = fake.posts
    assert entry.pop("seconds") >= 1
    assert entry.pop("since") == page.evaluate(START_OF_WEEK)
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


def test_initials_get_focus_even_if_focus_was_left_outside_the_card(page: Page, site_url, errors):
    # In CI the Play button can still hold focus when a quick game ends,
    # because the browser hasn't yet noticed it was hidden. If the scores then
    # arrived before the card's own focus timer, the initials were skipped and
    # Play again got focus instead. A focused button outside the card stands
    # in for it here, and makes the race happen every time.
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    open_game(page, site_url, fake)
    expect(page.locator("#menuScoreList li")).to_have_count(2)
    page.click("#playBtn")
    page.evaluate("window.__dc.chompRight(); window.__dc.chompRight()")
    page.evaluate("""() => {
        const outside = document.createElement('button');
        outside.textContent = 'Outside the card';
        document.body.appendChild(outside);
        outside.focus();
        window.__dc.end();
    }""")
    expect(page.locator("#ovTitle")).to_have_text("Game over")
    expect(page.locator("#initial0")).to_be_focused()
    page.wait_for_timeout(100)  # past the card's 30 ms focus timer
    expect(page.locator("#initial0")).to_be_focused()
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
    expect(page.locator("#menuWhich")).to_have_text("Kindergarten · This week")
    expect(page.locator("#menuScoreList li")).to_have_text(["1KID90L3"])
    assert fake.views[-1] == {
        "game": "doodle-chomp", "scope": "*", "difficulty": "starter", "mode": "kinder", "since": str(page.evaluate(START_OF_WEEK)),
    }
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
    expect(page.locator("#lbNote")).to_have_text("No scores here this week yet.")
    assert fake.views[-1] == {
        "game": "doodle-chomp", "scope": "*", "difficulty": "expert", "mode": "primes", "since": str(page.evaluate(START_OF_WEEK)),
    }

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


def test_periods_narrow_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245), row("OLD", 900, days_ago=40)])
    open_game(page, site_url, fake)
    expect(page.locator("#menuScoreList li .who")).to_have_text(["KID", "MRW"])  # this week, by default

    play(page)
    expect(page.locator(".ov-board .scores-which")).to_have_text("Multiples · Explorer · This week")
    type_initials(page, "ZED")
    page.click(".save-score button[type=submit]")
    expect(page.locator(".ov-board .scores-note")).to_have_text("Saved! #3 this week on Everyone (#4 all time).")

    page.click(".ov-board .lb-open")
    expect(page.locator("#lbPeriods button")).to_have_text(["Today", "This week", "This month", "All time"])
    page.click("#lbPeriods >> text=All time")
    expect(page.locator("#lbList li .who")).to_have_text(
        ["OLDMultiples · Explorer", "KIDMultiples · Explorer", "MRWMultiples · Explorer", "ZEDMultiples · Explorer"]
    )
    assert "since" not in fake.views[-1]
    page.click("#lbClose")
    expect(page.locator(".ov-board .scores-which")).to_have_text("Multiples · Explorer · All time")
    expect(page.locator(".ov-board li .who")).to_have_text(["OLD", "KID", "MRW", "ZED"])
    expect(page.locator(".ov-board .scores-note")).to_have_text("Saved! #3 this week on Everyone (#4 all time).")
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
    expect(page.locator("#lbNote")).to_have_text("No scores in Family this week yet.")
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "Family"}]

    page.click("#lbGroupList button >> text=Share")
    expect(page.locator("#lbGroupList button").first).to_have_text("Copied")
    text = page.evaluate("navigator.clipboard.readText()")
    assert text.startswith('Join "Family" on the Doodle Chomp high-score board with code K7QP: ')
    link = urlparse(text.rsplit(" ", 1)[-1])
    assert link.path == "/doodle-chomp"
    assert parse_qs(link.query) == {"leaderboard": [API], "join": ["K7QP"]}

    # The menu now shows the group's board, with tabs to switch.
    page.click("#lbClose")
    expect(page.locator("#menuWhich")).to_have_text("Multiples · Explorer · This week")
    expect(page.locator("#menuScopes button")).to_have_text(["Everyone", "Family"])
    expect(page.locator("#menuScopes button[aria-pressed=true]")).to_have_text("Family")
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
    expect(page.locator("#sideWhich")).to_have_text("Multiples · Explorer · This week · Family")  # the margin has no tabs

    # The menu's tabs switch its list, and the margin's, too.
    page.click("#menuScopes >> text=Everyone")
    expect(page.locator("#menuScoreList li")).to_have_count(5)
    expect(page.locator("#sideWhich")).to_have_text("Multiples · Explorer · This week")
    page.click("#menuScopes >> text=Family")
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
    expect(board.locator(".scores-note")).to_have_text("Saved! #2 this week in Family, #1 this week in Friends.")
    expect(board.locator("li.mine")).to_have_text("2DAD30L1")
    assert fake.posts[0]["groups"] == ["K7QP", "W3XY"]
    assert fake.posts[0]["public"] is False

    board.locator(".lb-scopes button >> text=Friends").click()
    expect(board.locator("li.mine")).to_have_text("1DAD30L1")
    expect(board.locator(".scores-note")).to_have_text("Saved! #2 this week in Family, #1 this week in Friends.")

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


SCORES_GET = lambda r: r.method == "GET" and "/v1/scores" in r.url  # noqa: E731
SCORES_POST = lambda r: r.method == "POST" and r.url.endswith("/v1/scores")  # noqa: E731


def test_closing_the_high_score_screen_while_saving_saves_once(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    held = Held(fake, SCORES_POST)
    open_game(page, site_url, held)
    play(page)
    type_initials(page, "ZED")
    page.click(".save-score button[type=submit]")
    held.wait_for(page)  # the score is out
    page.click(".ov-board .lb-open")
    page.click("#lbClose")
    # Still the one form, still saving: no second Save to tap.
    expect(page.locator(".save-score")).to_have_count(1)
    expect(page.locator(".save-score button[type=submit]")).to_be_disabled()
    expect_letters(page, "ZED")
    held.release()
    expect(page.locator("#ovTitle")).to_have_text("On the board!")
    expect(page.locator(".ov-board .scores-note")).to_have_text("Saved! #3 this week on Everyone.")
    expect(page.locator(".save-score")).to_have_count(0)
    assert [p["initials"] for p in fake.posts] == ["ZED"]
    assert errors == []


def test_a_save_that_lands_while_the_card_reloads_says_its_saved(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    held = Held(fake, SCORES_POST)
    open_game(page, site_url, held)
    play(page)
    type_initials(page, "ZED")
    page.click(".save-score button[type=submit]")
    held.wait_for(page)
    page.click(".ov-board .lb-open")
    page.click("#lbPeriods >> text=All time")  # a board the card hasn't loaded yet
    expect(page.locator("#lbList li")).to_have_count(2)
    held.match = lambda r: SCORES_POST(r) or SCORES_GET(r)
    page.click("#lbClose")
    held.wait_for(page, 2)  # the score, and the card's list for All time
    held.answer(0)  # the score lands first
    expect(page.locator("#ovTitle")).to_have_text("On the board!")
    held.release()
    expect(page.locator(".ov-board li.mine")).to_have_text("3ZED30L1")
    expect(page.locator(".ov-board .scores-note")).to_have_text("Saved! #3 this week on Everyone.")
    assert errors == []


def test_a_tab_tapped_while_the_card_loads_keeps_the_offer_to_save(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 500 - i) for i in range(10)], groups={"K7QP": "Family"})
    # Every list stays out until release(), so none is answered from the page's cache.
    held = Held(fake, SCORES_GET)
    open_game(page, site_url, held)
    join_group(page, "K7QP", "Family")
    page.click("#lbClose")
    before = len(held.routes)
    play(page)
    held.wait_for(page, before + 1)  # the card's list
    page.click(".ov-board .lb-scopes button >> text=Everyone")  # before it arrives
    held.wait_for(page, before + 2)
    held.release()
    expect(page.locator(".ov-board li")).to_have_count(5)
    expect(page.locator(".save-score")).to_be_visible()
    expect(page.locator("html")).to_have_attribute("data-save", "offered")
    assert errors == []


def test_opening_the_high_score_screen_keeps_typed_initials(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    open_game(page, site_url, fake)
    play(page)
    type_initials(page, "ZED")
    page.click(".ov-board .lb-open")
    page.click("#lbClose")
    expect_letters(page, "ZED")
    expect(page.locator("html")).to_have_attribute("data-save", "offered")
    assert errors == []


def test_the_high_score_screen_keeps_the_card_below_out_of_reach(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300)])
    open_game(page, site_url, fake)
    play(page)
    page.click(".ov-board .lb-open")
    # However far you tab, focus stays on the high-score screen, so Enter
    # can't start a game behind it.
    for _ in range(25):
        page.keyboard.press("Shift+Tab")
        assert page.evaluate("!document.activeElement.closest('#overlay, #menu, #hud, #rule, #stage, #side, #pad')")
    expect(page.locator("html")).to_have_attribute("data-board", "open")
    expect(page.locator("#overlay")).to_have_attribute("inert", "")
    page.keyboard.press("Escape")
    expect(page.locator("html")).to_have_attribute("data-board", "closed")
    expect(page.locator("#overlay")).not_to_have_attribute("inert", "")
    expect(page.locator("html")).to_have_attribute("data-screen", "over")
    assert errors == []


def test_a_save_that_lands_while_the_screen_is_open_leaves_focus_there(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    held = Held(fake, SCORES_POST)
    open_game(page, site_url, held)
    play(page)
    type_initials(page, "ZED")
    page.click(".save-score button[type=submit]")
    held.wait_for(page)
    page.click(".ov-board .lb-open")
    all_time = page.locator("#lbPeriods button >> text=All time")
    all_time.focus()
    held.release()
    expect(page.locator("#ovTitle")).to_have_text("On the board!")
    expect(all_time).to_be_focused()
    page.keyboard.press("Enter")  # for All time, not for Play again behind the screen
    expect(page.locator("#lbPeriods button[aria-pressed=true]")).to_have_text("All time")
    assert page.evaluate("window.__dc.peek().phase") == "over"
    assert errors == []


def test_a_list_that_lands_while_the_screen_is_open_leaves_focus_there(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245)])
    held = Held(fake, SCORES_GET)
    open_game(page, site_url, held)
    page.evaluate("localStorage.setItem('games.initials', JSON.stringify('MOM'))")
    play(page)
    page.click(".ov-board .lb-open")
    page.click("#lbJoinCode")  # about to type a group's code
    held.release()  # the card's list comes back and offers to save
    expect(page.locator(".save-score")).to_have_count(1)
    expect(page.locator("#lbJoinCode")).to_be_focused()
    page.keyboard.press("Enter")
    expect(page.locator("#lbGroupNote")).to_have_text("Group codes are four letters and numbers, like K7QP.")
    assert fake.posts == [], "no score saved from behind the screen"
    assert errors == []


def test_a_second_tap_doesnt_start_a_second_group(page: Page, site_url, errors):
    fake = FakeLeaderboard()
    held = Held(fake, lambda r: r.method == "POST" and r.url.endswith("/v1/groups"))
    open_game(page, site_url, held)
    page.click("#lbOpenMenu")
    page.fill("#lbGroupName", "Family")
    page.evaluate("() => { const b = document.querySelector('#lbCreateForm button'); b.click(); b.click(); }")
    held.wait_for(page)
    page.wait_for_timeout(200)
    assert len(held.routes) == 1, "one group asked for"
    expect(page.locator("#lbCreateForm button")).to_be_disabled()
    page.evaluate("document.querySelector('#lbCreateForm').requestSubmit()")  # Enter in the name field
    page.wait_for_timeout(200)
    assert len(held.routes) == 1, "still one"
    held.release()
    expect(page.locator("#lbGroupNote")).to_have_text("Started Family. Share code K7QP so others can join.")
    expect(page.locator("#lbCreateForm button")).to_be_enabled()
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "Family"}]
    assert errors == []


def test_a_slow_invite_lookup_doesnt_undo_joining(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "The Warkentins"})
    held = Held(fake, lambda r: "/v1/groups/" in r.url)
    open_game(page, site_url, held, "&join=K7QP")
    held.wait_for(page)  # the invite's lookup, still out
    held.holding = False
    page.click("#lbJoinForm button")
    joined = "Joined The Warkentins. Scores you save from now on go to The Warkentins too."
    expect(page.locator("#lbGroupNote")).to_have_text(joined)
    held.release()
    page.wait_for_timeout(300)
    expect(page.locator("#lbGroupNote")).to_have_text(joined)
    assert errors == []


def test_a_group_joined_after_the_screen_closed_shows_on_the_menu(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("MOM", 500, scope="K7QP")], groups={"K7QP": "Family"})
    held = Held(fake, lambda r: "/v1/groups/" in r.url)
    open_game(page, site_url, held)
    page.click("#lbOpenMenu")
    page.fill("#lbJoinCode", "K7QP")
    page.click("#lbJoinForm button")
    held.wait_for(page)
    page.keyboard.press("Escape")  # closed before the Worker answers
    held.release()
    expect(page.locator("#menuScopes button")).to_have_text(["Everyone", "Family"])
    expect(page.locator("#menuScoreList li")).to_have_text(["1MOM500L3"])
    page.click("#lbOpenMenu")
    expect(page.locator("#lbGroupNote")).to_have_text("")  # no news from a screen that had closed
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "Family"}]
    assert errors == []


def test_an_invite_when_youre_in_five_groups_says_so(page: Page, site_url, errors):
    groups = [{"code": c, "name": f"Group {c}"} for c in ("AAAA", "BBBB", "CCCC", "DDDD", "EEEE")]
    fake = FakeLeaderboard(groups={"K7QP": "The Warkentins", **{g["code"]: g["name"] for g in groups}})
    page.route(f"{API}/**", fake.handle)
    page.goto(f"{site_url}/doodle-chomp?leaderboard={API}#debug")
    page.evaluate("(g) => localStorage.setItem('games.groups', JSON.stringify(g))", groups)
    page.goto(f"{site_url}/doodle-chomp?leaderboard={API}&join=K7QP#debug")
    expect(page.locator("#lbJoinForm")).to_be_hidden()
    expect(page.locator("#lbGroupNote")).to_have_text(
        "You’re in 5 groups already, the most there can be. Leave one to join another."
    )
    assert errors == []
