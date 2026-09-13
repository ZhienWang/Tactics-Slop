"""Tests for the Daily Devotion Book system: cycling books in and out of a
unit's 5 slots on the world map, and the battle-side turns-held growth and
reading-level progression. These are pure functions - no pygame event loop
or live battle involved.
"""
from scripts import world_map
from scripts.game_logic import Unit, apply_book_growth, apply_book_bonuses
from scripts.data_editor import reading_level, BOOK_SLOTS


def make_unit(name, **stats):
    data = {
        "name": name,
        "team": "Player",
        "class": "Apostle",
        "x": 0,
        "y": 0,
        "speed": 10,
        "mv": 3,
        "jump": 1,
        "faith": 100,
        "mp": 10,
        "skills": [],
        "color": (255, 255, 255),
        "portrait_path": "",
    }
    data.update(stats)
    return Unit(data)


BOOK_POOL = ["Genesis", "Psalms", "1 Corinthians"]
BOOK_REGISTRY = {
    "Genesis": {"stat": "faith", "description": "Creation and covenant."},
    "Psalms": {"stat": "faith", "description": "Songs of worship."},
    "1 Corinthians": {"stat": "love", "description": "Love is patient."},
}


# --- cycle_book (world map Books screen) ---

def test_cycle_book_from_empty_moves_to_first_book():
    unit = make_unit("Peter")
    world_map.cycle_book(unit, "book_1", 1, BOOK_POOL)
    assert unit.books["book_1"] == "Genesis"


def test_cycle_book_wraps_past_the_end_back_to_empty():
    unit = make_unit("Peter")
    unit.books["book_1"] = "1 Corinthians"  # last item in the pool
    world_map.cycle_book(unit, "book_1", 1, BOOK_POOL)
    assert unit.books["book_1"] is None


def test_cycle_book_only_touches_the_given_slot():
    unit = make_unit("Peter")
    unit.books["book_1"] = "Genesis"
    world_map.cycle_book(unit, "book_2", 1, BOOK_POOL)
    assert unit.books["book_1"] == "Genesis"  # untouched
    assert unit.books["book_2"] == "Genesis"  # any book can go in any slot


def test_cycle_book_swapping_resets_that_slots_progress():
    unit = make_unit("Peter")
    unit.books["book_1"] = "Genesis"
    unit.book_turns["book_1"] = 12
    unit.book_gain["book_1"] = 40
    world_map.cycle_book(unit, "book_1", 1, BOOK_POOL)  # -> Psalms
    assert unit.books["book_1"] == "Psalms"
    assert unit.book_turns["book_1"] == 0
    assert unit.book_gain["book_1"] == 0


def test_book_stat_totals_sums_gain_across_slots_by_stat():
    unit = make_unit("Peter")
    unit.books["book_1"] = "Genesis"
    unit.book_gain["book_1"] = 10
    unit.books["book_2"] = "Psalms"
    unit.book_gain["book_2"] = 5
    unit.books["book_3"] = "1 Corinthians"
    unit.book_gain["book_3"] = 7

    totals = world_map.book_stat_totals(unit, BOOK_REGISTRY)

    assert totals == {"faith": 15, "love": 7}


def test_book_stat_totals_empty_when_nothing_equipped():
    unit = make_unit("Peter")
    assert world_map.book_stat_totals(unit, BOOK_REGISTRY) == {}


# --- reading_level (data_editor) ---

def test_reading_level_thresholds():
    assert reading_level(0) == "Novice"
    assert reading_level(9) == "Novice"
    assert reading_level(10) == "Learned"
    assert reading_level(19) == "Learned"
    assert reading_level(20) == "Devoted"
    assert reading_level(29) == "Devoted"
    assert reading_level(30) == "Mastered"
    assert reading_level(100) == "Mastered"


# --- apply_book_growth / apply_book_bonuses (game_logic, battle-side) ---

def test_apply_book_growth_increments_turns_and_grows_the_books_stat():
    unit = make_unit("Peter", faith=100)
    unit.books["book_1"] = "Genesis"

    apply_book_growth(unit, BOOK_REGISTRY)

    assert unit.book_turns["book_1"] == 1
    assert unit.faith > 100  # Genesis grows faith
    assert unit.book_gain["book_1"] == unit.faith - 100
    # Growth is randomized around 2% but must stay small enough not to
    # break battle balance in a single turn.
    assert 0 < unit.book_gain["book_1"] <= 5


def test_apply_book_growth_ignores_empty_slots():
    unit = make_unit("Peter", faith=100)
    apply_book_growth(unit, BOOK_REGISTRY)
    assert unit.book_turns == {}
    assert unit.faith == 100


def test_apply_book_growth_only_grows_the_stat_its_own_book_targets():
    unit = make_unit("Peter", faith=100, love=50)
    unit.books["book_1"] = "1 Corinthians"  # targets love, not faith

    apply_book_growth(unit, BOOK_REGISTRY)

    assert unit.faith == 100
    assert unit.love > 50


def test_apply_book_bonuses_reapplies_prior_gain_once_onto_a_fresh_unit():
    unit = make_unit("Peter", faith=100)
    unit.books["book_1"] = "Genesis"
    unit.book_gain["book_1"] = 12  # progress carried over from a prior battle

    apply_book_bonuses(unit, BOOK_REGISTRY)

    assert unit.faith == 112


def test_apply_book_bonuses_does_nothing_for_a_book_with_no_gain_yet():
    unit = make_unit("Peter", faith=100)
    unit.books["book_1"] = "Genesis"

    apply_book_bonuses(unit, BOOK_REGISTRY)

    assert unit.faith == 100


def test_all_five_book_slots_exist():
    assert BOOK_SLOTS == ["book_1", "book_2", "book_3", "book_4", "book_5"]
