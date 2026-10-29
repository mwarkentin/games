"""Air Traffic Controller's leaderboard and groups, against a fake of the Worker API.

A shift's score is aircraft handled × 10000 plus seconds to spare on a clean
shift, and its level is the number handled. Tests that make the fake answer
4xx or 5xx skip the `errors` fixture, because the browser logs those
responses as console errors.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

from fake_leaderboard import API, FakeLeaderboard
from playwright.sync_api import Page, expect

UNAVAILABLE = "The leaderboard is unavailable right now."


def row(initials: str, handled: int, spare: int = 0, scope: str = "*", difficulty: str = "trainee", mode: str = "steady") -> dict:
    score = handled * 10000 + spare
    return {"initials": initials, "score": score, "level": handled, "scope": scope, "difficulty": difficulty, "mode": mode}


def open_game(page: Page, site_url: str, fake: FakeLeaderboard | None, query: str = "") -> None:
    if fake:
        page.route(f"{API}/**", fake.handle)
        page.goto(f"{site_url}/air-traffic-controller?leaderboard={API}{query}#debug")
    else:
        page.goto(f"{site_url}/air-traffic-controller#debug")


def fly_shift(page: Page, handled: int = 8, sweeps: int = 80) -> None:
    """Start a shift from the menu and end it with `handled` aircraft done after `sweeps` sweeps."""
    page.click("#btnStart")
    page.evaluate("([handled, sweeps]) => window.__atc.finish(handled, sweeps)", [handled, sweeps])
    expect(page.locator("#result")).to_be_visible()


def join_group(page: Page, code: str, name: str) -> None:
    """Join a group from the leaderboard card, which is left open."""
    if page.locator("#board").is_hidden():
        page.click("#lbOpenMenu")
    page.fill("#lbJoinCode", code)
    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(f"Joined {name}. Shifts you save from now on go to {name} too.")


def stored(page: Page, key: str):
    return page.evaluate("(key) => JSON.parse(localStorage.getItem(key))", key)


def test_leaderboard_stays_hidden_until_configured(page: Page, site_url, errors):
    open_game(page, site_url, None)
    expect(page.locator("#menuLb")).to_be_hidden()
    fly_shift(page)
    expect(page.locator("#resTitle")).to_have_text("Shift complete")
    expect(page.locator("#resLb")).to_be_hidden()
    assert errors == []


def test_clean_shift_saves_initials(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 8, spare=900), row("MRW", 5)])
    open_game(page, site_url, fake)
    expect(page.locator("#menuLbWhich")).to_have_text("Trainee · Steady")
    expect(page.locator("#menuLbList li")).to_have_text(["1KID8/8+15:00", "2MRW5/8"])

    fly_shift(page, handled=8, sweeps=80)  # 40 sweeps, 10 minutes, to spare
    expect(page.locator("#resLbWhich")).to_have_text("Trainee · Steady")
    expect(page.locator("#lbForm")).to_be_visible()
    expect(page.locator("#lbPublicRow")).to_be_hidden()
    expect(page.locator("#resLbNote")).to_have_text("That’s #2 on the Trainee · Steady board. Add your initials.")
    page.locator("#lbInitials").press_sequentially("z3e d")  # letters only, upper-cased as you type
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    page.click("#lbSave")

    expect(page.locator("#resLbNote")).to_have_text("Saved! #2 on Everyone.")
    expect(page.locator("#resLbList li.mine")).to_have_text("2ZED8/8+10:00")
    expect(page.locator("#lbForm")).to_be_hidden()
    assert fake.posts == [{
        "game": "air-traffic-controller", "difficulty": "trainee", "mode": "steady", "score": 80600, "level": 8,
        "sweeps": 80, "initials": "ZED", "groups": [], "public": True,
    }]

    # The menu shows the new entry, and the initials are remembered for next time.
    page.click("#btnMenu")
    expect(page.locator("#menuLbList li.mine")).to_have_text("2ZED8/8+10:00")
    fly_shift(page)
    expect(page.locator("#lbInitials")).to_have_value("ZED")
    assert stored(page, "games.initials") == "ZED"
    assert errors == []


def test_lost_shift_ranks_by_aircraft_handled(page: Page, site_url, errors):
    fake = FakeLeaderboard([row("KID", 8, spare=900), row("MRW", 5), row("SIS", 3)])
    open_game(page, site_url, fake)
    fly_shift(page, handled=5, sweeps=44)
    expect(page.locator("#resTitle")).to_have_text("Separation lost")
    expect(page.locator("#resLbNote")).to_have_text("That’s #3 on the Trainee · Steady board. Add your initials.")
    page.fill("#lbInitials", "DAD")
    page.click("#lbSave")
    expect(page.locator("#resLbNote")).to_have_text("Saved! #3 on Everyone.")
    expect(page.locator("#resLbList li")).to_have_text(["1KID8/8+15:00", "2MRW5/8", "3DAD5/8", "4SIS3/8"])
    assert fake.posts[0]["score"] == 50000
    assert fake.posts[0]["level"] == 5
    assert errors == []


def test_shift_below_tenth_place_only_shows_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 8, spare=900 - i) for i in range(10)])
    open_game(page, site_url, fake)
    fly_shift(page, handled=7, sweeps=100)
    expect(page.locator("#resLbList li")).to_have_count(5)
    expect(page.locator("#lbForm")).to_be_hidden()
    assert fake.posts == []
    assert errors == []


def test_slowest_sweep_decides_the_board(page: Page, site_url, errors):
    fake = FakeLeaderboard()
    open_game(page, site_url, fake)
    page.click("#speedChips >> text=Rush")
    expect(page.locator("#menuLbWhich")).to_have_text("Trainee · Rush")
    page.click("#btnStart")
    page.click("#btnSpeed")  # rush → calm, mid-shift
    page.click("#btnSpeed")  # calm → steady
    assert page.evaluate("window.__atc.peek().slowest") == "calm"
    page.evaluate("window.__atc.finish(8, 80)")
    expect(page.locator("#resLbWhich")).to_have_text("Trainee · Calm")
    page.fill("#lbInitials", "MRW")
    page.click("#lbSave")
    expect(page.locator("#resLbNote")).to_have_text("Saved! #1 on Everyone.")
    assert fake.posts[0]["mode"] == "calm"
    assert errors == []


def test_rejected_save_shows_the_reason(page: Page, site_url):
    fake = FakeLeaderboard(reject_with="pick different initials")
    open_game(page, site_url, fake)
    fly_shift(page)
    page.fill("#lbInitials", "WTF")
    page.click("#lbSave")
    expect(page.locator("#resLbNote")).to_have_text("Couldn’t save: pick different initials.")
    expect(page.locator("#lbForm")).to_be_visible()


def test_unavailable_leaderboard_does_not_block_the_game(page: Page, site_url):
    fake = FakeLeaderboard(status=500)
    open_game(page, site_url, fake)
    expect(page.locator("#menuLbNote")).to_have_text(UNAVAILABLE)
    fly_shift(page)
    expect(page.locator("#resLbNote")).to_have_text(UNAVAILABLE)
    expect(page.locator("#lbForm")).to_be_hidden()
    page.click("#btnAgain")
    expect(page.locator("#overlay")).to_be_hidden()


def test_leaderboard_card_filters_by_shift_and_sweep(page: Page, site_url, errors):
    fake = FakeLeaderboard([
        row("KID", 8, spare=900),
        row("MRW", 26, spare=60, difficulty="expert", mode="rush"),
        row("SIS", 20, difficulty="easy"),
        row("DAD", 4, mode="calm"),
    ])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#board")).to_be_visible()
    expect(page.locator("#menu")).to_be_hidden()
    expect(page.locator("#lbClose")).to_be_focused()

    who = page.locator("#lbList li .who")
    expect(who).to_have_text(["MRWExpert · Rush", "SISEasy · Steady", "KIDTrainee · Steady", "DADTrainee · Calm"])
    page.select_option("#lbDifficulty", "trainee")
    expect(who).to_have_text(["KIDTrainee · Steady", "DADTrainee · Calm"])
    page.select_option("#lbMode", "calm")
    expect(page.locator("#lbList li")).to_have_text(["1DAD4/8"])  # one board, so no tags
    page.select_option("#lbDifficulty", "hard")
    expect(page.locator("#lbList")).to_be_hidden()
    expect(page.locator("#lbNote")).to_have_text("No shifts here yet.")
    assert fake.views[-1] == {"game": "air-traffic-controller", "scope": "*", "difficulty": "hard", "mode": "calm"}

    # Escape goes back to the menu, and the filters are remembered.
    page.keyboard.press("Escape")
    expect(page.locator("#board")).to_be_hidden()
    expect(page.locator("#menu")).to_be_visible()
    expect(page.locator("#lbOpenMenu")).to_be_focused()
    page.reload()
    page.click("#lbOpenMenu")
    expect(page.locator("#lbDifficulty")).to_have_value("hard")
    expect(page.locator("#lbMode")).to_have_value("calm")
    assert errors == []


def test_start_a_group_and_share_an_invite(page: Page, site_url, errors):
    page.context.grant_permissions(["clipboard-read", "clipboard-write"])
    fake = FakeLeaderboard([row("KID", 8, spare=900)])
    open_game(page, site_url, fake)
    page.click("#lbOpenMenu")
    expect(page.locator("#lbNoGroups")).to_be_visible()

    page.fill("#lbGroupName", "Family")
    page.click("#lbCreateForm button")
    expect(page.locator("#lbGroupNote")).to_have_text("Started Family. Share code K7QP so others can join.")
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    expect(page.locator("#lbScopes button")).to_have_text(["Everyone", "Family"])
    expect(page.locator("#lbScopes button[aria-pressed=true]")).to_have_text("Family")
    expect(page.locator("#lbNote")).to_have_text("No shifts in Family yet.")
    assert stored(page, "games.groups") == [{"code": "K7QP", "name": "Family"}]

    page.click("#lbGroupList button >> text=Share")
    expect(page.locator("#lbGroupList button").first).to_have_text("Copied")
    text = page.evaluate("navigator.clipboard.readText()")
    assert text.startswith('Join "Family" on the Air Traffic Controller leaderboard with code K7QP: ')
    link = urlparse(text.rsplit(" ", 1)[-1])
    assert link.path == "/air-traffic-controller"
    assert parse_qs(link.query) == {"leaderboard": [API], "join": ["K7QP"]}

    page.click("#lbClose")
    expect(page.locator("#menuLbWhich")).to_have_text("Trainee · Steady · Family")
    assert errors == []


def test_group_members_save_to_their_groups(page: Page, site_url, errors):
    fake = FakeLeaderboard(
        [row("MOM", 8, spare=900, scope="K7QP")] + [row(f"A{chr(65 + i)}A", 8, spare=900 - i) for i in range(10)],
        groups={"K7QP": "Family", "W3XY": "Friends"},
    )
    open_game(page, site_url, fake)
    join_group(page, "k7qp", "Family")  # lower case is fine
    join_group(page, "W3XY", "Friends")
    page.click("#lbScopes button >> text=Family")
    page.click("#lbClose")
    expect(page.locator("#menuLbList li")).to_have_text(["1MOM8/8+15:00"])

    # Not a top-10 public shift, but in a group every shift can be saved.
    fly_shift(page, handled=6, sweeps=60)
    expect(page.locator("#resLbScopes button")).to_have_text(["Everyone", "Family", "Friends"])
    expect(page.locator("#lbPublicRow")).to_be_visible()
    expect(page.locator("#lbPublic")).to_be_checked()
    page.uncheck("#lbPublic")
    page.fill("#lbInitials", "DAD")
    page.click("#lbSave")
    expect(page.locator("#resLbNote")).to_have_text("Saved! #2 in Family, #1 in Friends.")
    expect(page.locator("#resLbList li.mine")).to_have_text("2DAD6/8")
    assert fake.posts[0]["groups"] == ["K7QP", "W3XY"]
    assert fake.posts[0]["public"] is False

    # The public-board choice is remembered for the next shift.
    page.click("#btnAgain")
    page.evaluate("window.__atc.finish(2, 20)")
    expect(page.locator("#lbForm")).to_be_visible()
    expect(page.locator("#lbPublic")).not_to_be_checked()
    assert errors == []


def test_joining_from_the_shift_report_offers_to_save(page: Page, site_url, errors):
    fake = FakeLeaderboard([row(f"A{chr(65 + i)}A", 8, spare=900 - i) for i in range(10)], groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    fly_shift(page, handled=3, sweeps=50)
    expect(page.locator("#lbForm")).to_be_hidden()
    page.click("#lbOpenResult")
    join_group(page, "K7QP", "Family")
    page.click("#lbClose")
    expect(page.locator("#result")).to_be_visible()
    expect(page.locator("#lbForm")).to_be_visible()
    expect(page.locator("#resLbScopes button[aria-pressed=true]")).to_have_text("Family")
    assert errors == []


def test_groups_are_shared_with_other_games(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "Family"})
    page.route(f"{API}/**", fake.handle)
    page.goto(f"{site_url}/doodle-chomp?leaderboard={API}")
    page.click("#lbOpenMenu")
    page.fill("#lbJoinCode", "K7QP")
    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    page.goto(f"{site_url}/air-traffic-controller?leaderboard={API}")
    page.click("#lbOpenMenu")
    expect(page.locator("#lbGroupList li code")).to_have_text("K7QP")
    assert errors == []


def test_invite_link_opens_the_join_card(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "The Warkentins"})
    open_game(page, site_url, fake, "&join=k7qp")
    expect(page.locator("#board")).to_be_visible()
    expect(page.locator("#lbJoinCode")).to_have_value("K7QP")
    expect(page.locator("#lbGroupNote")).to_have_text("You’re invited to The Warkentins. Tap Join to add it.")
    assert parse_qs(urlparse(page.url).query) == {"leaderboard": [API]}

    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_have_text(
        "Joined The Warkentins. Shifts you save from now on go to The Warkentins too."
    )
    page.click("#lbClose")
    expect(page.locator("#menu")).to_be_visible()
    assert errors == []


def test_invite_link_over_a_saved_shift_returns_to_it(page: Page, site_url, errors):
    fake = FakeLeaderboard(groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    page.click("#btnStart")
    page.click("#btnAdvance")
    page.goto(f"{site_url}/air-traffic-controller?leaderboard={API}&join=K7QP#debug")
    expect(page.locator("#board")).to_be_visible()
    page.click("#lbJoinForm button")
    expect(page.locator("#lbGroupNote")).to_contain_text("Joined Family.")
    page.click("#lbClose")
    expect(page.locator("#paused")).to_be_visible()
    expect(page.locator("#pauseSummary")).to_contain_text("Picked up where you left off.")
    page.click("#btnResume")
    expect(page.locator("#overlay")).to_be_hidden()
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
    fake = FakeLeaderboard([row("KID", 8, spare=900)], groups={"K7QP": "Family"})
    open_game(page, site_url, fake)
    join_group(page, "K7QP", "Family")
    dialogs: list[str] = []
    page.on("dialog", lambda d: (dialogs.append(d.message), d.accept()))
    page.click("#lbGroupList button >> text=Leave")
    expect(page.locator("#lbGroupNote")).to_have_text("Left Family.")
    assert dialogs == ["Leave Family? You can rejoin later with code K7QP."]
    expect(page.locator("#lbNoGroups")).to_be_visible()
    expect(page.locator("#lbScopes")).to_be_hidden()
    expect(page.locator("#lbList li .who")).to_have_text(["KIDTrainee · Steady"])
    assert stored(page, "games.groups") == []
    assert errors == []
