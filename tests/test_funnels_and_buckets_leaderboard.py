"""Funnels & Buckets' leaderboard and groups, against a fake of the Worker API.

Tests that make the fake answer 4xx or 5xx skip the `errors` fixture, because
the browser logs those responses as console errors.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fake_leaderboard import API, FakeLeaderboard
from playwright.sync_api import Page, expect

SINGLE_TABLE_NOTE = "Games with one times table are practice and don’t go on the leaderboard."
UNAVAILABLE = "The leaderboard is unavailable right now."


def row(initials: str, score: int, scope: str = "*", difficulty: str = "classic", mode: str = "normal") -> dict:
    return {"initials": initials, "score": score, "level": 3, "scope": scope, "difficulty": difficulty, "mode": mode}


def open_game(page: Page, site_url: str, fake: FakeLeaderboard | None, query: str = "") -> None:
    if fake:
        page.route(f"{API}/**", fake.handle)
        page.goto(f"{site_url}/funnels-and-buckets?leaderboard={API}{query}#debug")
    else:
        page.goto(f"{site_url}/funnels-and-buckets#debug")


def play_one_bubble(page: Page) -> None:
    """Pop one divide bubble (20 points), then end the game."""
    page.click("#startBtn")
    page.evaluate("window.__fb.queue([['div', 20, 4]])")
    page.wait_for_function("() => window.__fb.peek().bubbles.some((b) => b.ans === 5)", timeout=15000)
    page.keyboard.type("5")
    page.keyboard.press("Enter")
    page.wait_for_function("() => window.__fb.peek().popped === 1")
    page.wait_for_timeout(1100)  # at least a second of play, which the API checks
    page.evaluate("window.__fb.end()")
    expect(page.locator("#overOv")).to_be_visible()


def join_group(page: Page, code: str, name: str) -> None:
    """Join a group from the leaderboard screen, which is left open."""
    if page.locator("#lbOv").is_hidden():
        page.click("#lbOpenMenu")
    page.fill("#lbJoinCode", code)
    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(f"Joined {name}. Scores you save from now on go to {name} too.")


def stored(page: Page, key: str):
    return page.evaluate("(key) => JSON.parse(localStorage.getItem(key))", key)


def test_leaderboard_stays_hidden_until_configured(page: Page, site_url, errors):
    open_game(page, site_url, None)
    expect(page.locator("#menuLb")).to_be_hidden()
    play_one_bubble(page)
    expect(page.locator("#overLb")).to_be_hidden()
    assert errors == []


def test_top_ten_score_saves_initials(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300), row("MRW", 245), row("SIS", 400, difficulty="starter")])
    open_game(page, site_url, fake)
    expect(page.locator("#menuLbWhich")).to_have_text("Classic")
    expect(page.locator("#menuLbList li")).to_have_count(2)
    expect(page.locator("#lbPublicRow")).to_be_hidden()

    play_one_bubble(page)
    expect(page.locator("#lbForm")).to_be_visible()
    expect(page.locator("#overLbScopes")).to_be_hidden()  # no groups, so no tabs
    page.locator("#lbInitials").press_sequentially("z3e d")  # letters only, upper-cased as you type
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    page.click("#lbSave")

    expect(page.locator("#overLbNote")).to_have_text("Saved! #3 on Everyone.")
    expect(page.locator("#overLbList li.mine")).to_have_text("3ZED20")
    expect(page.locator("#lbForm")).to_be_hidden()
    [entry] = fake.posts
    assert entry.pop("seconds") >= 1
    assert entry == {
        "game": "funnels-and-buckets", "difficulty": "classic", "mode": "normal", "initials": "ZED",
        "score": 20, "level": 1, "popped": 1, "groups": [], "public": True,
    }

    # The menu shows the new entry, and the initials are remembered for next time.
    page.click("#settingsBtn")
    expect(page.locator("#menuLbList li")).to_have_count(3)
    play_one_bubble(page)
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    assert stored(page, "games.initials") == "ZED"
    assert errors == []


def test_score_below_tenth_place_only_shows_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 500 - i) for i in range(10)])
    open_game(page, site_url, fake)
    play_one_bubble(page)
    expect(page.locator("#overLbList li")).to_have_count(10)
    expect(page.locator("#lbForm")).to_be_hidden()
    assert fake.posts == []
    assert errors == []


def test_single_table_games_stay_off_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard()
    open_game(page, site_url, fake)
    page.select_option("#table", "7")
    expect(page.locator("#menuLbNote")).to_have_text(SINGLE_TABLE_NOTE)
    play_one_bubble(page)
    expect(page.locator("#overLbNote")).to_have_text(SINGLE_TABLE_NOTE)
    expect(page.locator("#lbForm")).to_be_hidden()
    assert errors == []


def test_rejected_initials_show_the_reason(page: Page, site_url):
    fake = FakeLeaderboard(reject_with="pick different initials")
    open_game(page, site_url, fake)
    play_one_bubble(page)
    page.fill("#lbInitials", "WTF")
    page.click("#lbSave")
    expect(page.locator("#overLbNote")).to_have_text("Couldn’t save: pick different initials.")
    expect(page.locator("#lbForm")).to_be_visible()


def test_unavailable_leaderboard_does_not_block_the_game(page: Page, site_url):
    fake = FakeLeaderboard(status=500)
    open_game(page, site_url, fake)
    expect(page.locator("#menuLbNote")).to_have_text(UNAVAILABLE)
    play_one_bubble(page)
    expect(page.locator("#overLbNote")).to_have_text(UNAVAILABLE)
    expect(page.locator("#againBtn")).to_be_enabled()


def test_leaderboard_screen_filters_by_difficulty_and_mode(page: Page, site_url, errors):
    fake = FakeLeaderboard([
        row("KID", 300),
        row("MRW", 245, difficulty="challenge"),
        row("SIS", 120, difficulty="starter", mode="easy"),
        row("DAD", 90, difficulty="classic", mode="easy"),
    ])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#lbOv")).to_be_visible()
    expect(page.locator("#lbScopes")).to_be_hidden()

    # Everything, with each score's board beside it.
    who = page.locator("#lbList li .who")
    expect(who).to_have_text(["KIDClassic", "MRWChallenge", "SISStarter · Extra easy", "DADClassic · Extra easy"])

    page.select_option("#lbDifficulty", "classic")
    expect(who).to_have_text(["KIDClassic", "DADClassic · Extra easy"])
    page.select_option("#lbMode", "easy")
    expect(page.locator("#lbList li")).to_have_count(1)
    expect(page.locator("#lbList li")).to_have_text("1DAD90")  # one board, so no tags
    page.select_option("#lbDifficulty", "challenge")
    expect(page.locator("#lbList")).to_be_hidden()
    expect(page.locator("#lbNote")).to_have_text("No scores here yet.")
    assert fake.views[-1] == {"game": "funnels-and-buckets", "scope": "*", "difficulty": "challenge", "mode": "easy"}

    # The filters are remembered, and Escape closes the screen.
    page.keyboard.press("Escape")
    expect(page.locator("#lbOv")).to_be_hidden()
    page.reload()
    page.click("#lbOpenMenu")
    expect(page.locator("#lbDifficulty")).to_have_value("challenge")
    expect(page.locator("#lbMode")).to_have_value("easy")
    assert errors == []


def test_start_a_group_and_share_an_invite(page: Page, site_url, errors):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    fake = FakeLeaderboard([row("KID", 300)])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#lbNoGroups")).to_be_visible()

    page.fill("#lbGroupName", "  The   Warkentins ")
    page.click("#lbCreateForm button")
    expect(page.locator("#lbGroupNote")).to_have_text("Started The Warkentins. Share code K7QP so others can join.")
    expect(page.locator("#lbGroupList li")).to_have_count(1)
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    expect(page.locator("#lbNoGroups")).to_be_hidden()
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "The Warkentins"}]

    # The new group's board opens, empty for now, beside the Everyone tab.
    expect(page.locator("#lbScopes button")).to_have_text(["Everyone", "The Warkentins"])
    expect(page.locator("#lbScopes button[aria-pressed=true]")).to_have_text("The Warkentins")
    expect(page.locator("#lbNote")).to_have_text("No scores in The Warkentins yet.")
    page.click("#lbScopes button >> text=Everyone")
    expect(page.locator("#lbList li")).to_have_count(1)

    # Share copies an invite link that keeps the leaderboard override.
    page.click("#lbGroupList button >> text=Share")
    expect(page.locator("#lbGroupList button").first).to_have_text("Copied")
    text = page.evaluate("navigator.clipboard.readText()")
    assert text.startswith('Join "The Warkentins" on the Funnels & Buckets leaderboard with code K7QP: ')
    link = urlparse(text.rsplit(" ", 1)[-1])
    assert link.path == "/funnels-and-buckets"
    assert parse_qs(link.query) == {"leaderboard": [API], "join": ["K7QP"]}
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
    expect(page.locator("#menuLbWhich")).to_have_text("Classic · Family")
    expect(page.locator("#menuLbList li")).to_have_text(["1MOM500"])

    # Not a top-10 public score, but in a group every score can be saved.
    play_one_bubble(page)
    expect(page.locator("#overLbScopes button")).to_have_text(["Everyone", "Family", "Friends"])
    expect(page.locator("#lbForm")).to_be_visible()
    expect(page.locator("#lbPublicRow")).to_be_visible()
    expect(page.locator("#lbPublic")).to_be_checked()
    page.uncheck("#lbPublic")
    page.fill("#lbInitials", "DAD")
    page.click("#lbSave")
    expect(page.locator("#overLbNote")).to_have_text("Saved! #2 in Family, #1 in Friends.")
    expect(page.locator("#overLbList li.mine")).to_have_text("2DAD20")
    assert fake.posts[0]["groups"] == ["K7QP", "W3XY"]
    assert fake.posts[0]["public"] is False

    page.click("#overLbScopes button >> text=Everyone")
    expect(page.locator("#overLbList li.mine")).to_have_count(0)
    page.click("#overLbScopes button >> text=Friends")
    expect(page.locator("#overLbList li.mine")).to_have_text("1DAD20")

    # The public choice is remembered, and every board gets the next score.
    page.click("#settingsBtn")
    play_one_bubble(page)
    expect(page.locator("#lbPublic")).not_to_be_checked()
    page.check("#lbPublic")
    page.click("#lbSave")
    expect(page.locator("#overLbNote")).to_have_text("Saved! #11 on Everyone, #3 in Family, #2 in Friends.")
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
    expect(page.locator("#lbGroupList")).to_be_hidden()

    join_group(page, "K7QP", "Family")
    page.fill("#lbJoinCode", "K7QP")
    page.click("#lbJoinForm button")
    expect(note).to_have_text("You’re already in Family.")


def test_invite_link_opens_the_join_screen(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "The Warkentins"})
    open_game(page, site_url, fake, "&join=K7QP")
    expect(page.locator("#lbOv")).to_be_visible()
    expect(page.locator("#lbJoinCode")).to_have_value("K7QP")
    expect(page.locator("#lbGroupNote")).to_have_text("You’re invited to The Warkentins. Tap Join to add it.")
    # The code leaves the URL, so a reload or bookmark doesn't ask again.
    assert parse_qs(urlparse(page.url).query) == {"leaderboard": [API]}

    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(
        "Joined The Warkentins. Scores you save from now on go to The Warkentins too."
    )
    expect(page.locator("#lbScopes button[aria-pressed=true]")).to_have_text("The Warkentins")
    assert errors == []


def test_leave_a_group(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 300)], groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    join_group(page, "K7QP", "Family")

    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.click("#lbGroupList button >> text=Leave")
    expect(page.locator("#lbGroupNote")).to_have_text("Left Family.")
    assert dialogs == ["Leave Family? You can rejoin later with code K7QP."]
    expect(page.locator("#lbGroupList")).to_be_hidden()
    expect(page.locator("#lbNoGroups")).to_be_visible()
    expect(page.locator("#lbScopes")).to_be_hidden()
    expect(page.locator("#lbList li .who")).to_have_text(["KIDClassic"])  # back to Everyone
    assert stored(page, "games.groups") == []
    assert errors == []
