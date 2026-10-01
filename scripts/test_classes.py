"""The new-game survey, the sixteen classes it chooses between, and their
signature skills."""
import itertools

import pytest

from scripts import game_logic, hero
from scripts.data_editor import load_skill_effects_from_csv, load_skills_from_csv


def make_unit(name, team="Player", x=0, y=0, faith=100, skills=None, char_class="Apostle"):
    return game_logic.Unit({
        "name": name, "team": team, "class": char_class, "x": x, "y": y, "speed": 10, "mv": 3, "jump": 1,
        "faith": faith, "mp": 20, "skills": skills or [], "color": (255, 255, 255), "portrait_path": "",
    })


@pytest.fixture
def board():
    game_logic.MAP_DATA = [[0] * 8 for _ in range(8)]
    game_logic.MAP_ROWS = game_logic.MAP_COLS = 8
    game_logic.SKILL_REGISTRY = load_skills_from_csv()
    game_logic.EFFECT_EVENTS.clear()


# --- survey ---

def test_the_survey_has_thirty_questions_and_no_pair_can_tie():
    questions = hero.load_survey_from_csv()
    assert len(questions) == 30
    for a, b in hero.PAIRS:
        in_pair = [q for q in questions if {q["answers"][0][1], q["answers"][1][1]} == {a, b}]
        assert len(in_pair) % 2 == 1, (a, b)
    assert all({q["answers"][0][1], q["answers"][1][1]} in [set(p) for p in hero.PAIRS] for q in questions)


def test_every_answer_pattern_scores_to_a_real_class():
    questions = hero.load_survey_from_csv()
    classes = hero.load_classes_from_csv()
    for want in itertools.product(*hero.PAIRS):
        answers = [0 if q["answers"][0][1] in want else 1 for q in questions]
        assert hero.score_survey(questions, answers) == "".join(want) in classes


def test_the_majority_wins_each_pair():
    questions = hero.load_survey_from_csv()
    ei = [i for i, q in enumerate(questions) if q["answers"][0][1] in "EI"]
    answers = [0 if q["answers"][0][1] in "INFJ" else 1 for q in questions]
    # Flip all but three E/I answers back to E - the E majority wins.
    for i in ei[:len(ei) - 3]:
        answers[i] = 0 if questions[i]["answers"][0][1] == "E" else 1
    assert hero.score_survey(questions, answers)[0] == "E"


# --- classes ---

def test_sixteen_classes_in_four_roles_each_with_its_own_signature_skill():
    classes = hero.load_classes_from_csv()
    skills = load_skills_from_csv()
    assert len(classes) == 16
    assert {c["role"] for c in classes.values()} == set(hero.ROLE_COLORS)
    signatures = [c["signature"] for c in classes.values()]
    assert len(set(signatures)) == 16
    for cls in classes.values():
        assert cls["signature"] in cls["skills"]
        assert all(skill in skills for skill in cls["skills"]), cls["class"]
        assert cls["blurb"] and cls["advice"]


def test_every_signature_skill_has_effects_and_a_resolver():
    bindings = load_skill_effects_from_csv()
    for cls in hero.load_classes_from_csv().values():
        signature = cls["signature"]
        assert signature in bindings, signature
        assert signature in game_logic.SIGNATURE_SKILLS or signature in game_logic.DISARM_SKILLS


def test_the_hero_joins_beside_paul_riding_what_he_rides():
    roster = [
        {"name": "Paul", "team": "Player", "x": 2, "y": 2, "mount": "horse"},
        {"name": "Guard", "team": "Player", "x": 3, "y": 2, "mount": "horse"},
    ]
    entry = hero.hero_character({"name": "Lydia", "type": "ENFJ"}, roster, [[0] * 6 for _ in range(6)], {(2, 3)})
    assert entry["name"] == "Lydia" and entry["class"] == "Protagonist" and entry["hero"]
    assert (entry["x"], entry["y"]) not in {(2, 2), (3, 2), (2, 3)}
    assert abs(entry["x"] - 2) + abs(entry["y"] - 2) == 1
    assert entry["mount"] == "horse"
    unit = game_logic.Unit(entry)
    assert unit.is_hero and "Inspire" in unit.skills


def test_profiles_round_trip_and_bad_ones_are_ignored(tmp_path):
    path = tmp_path / "profile.json"
    hero.save_profile({"name": "Lydia", "type": "ENFJ"}, path=str(path))
    assert hero.load_profile(path=str(path)) == {"name": "Lydia", "type": "ENFJ"}
    hero.save_profile({"name": "Lydia", "type": "XXXX"}, path=str(path))
    assert hero.load_profile(path=str(path)) is None
    assert hero.load_profile(path=str(tmp_path / "missing.json")) is None


# --- signature skills ---

def test_grand_design_buffs_nearby_allies_for_two_turns(board):
    caster = make_unit("Hero")
    near, far = make_unit("Near", x=1), make_unit("Far", x=5)
    units = [caster, near, far]
    game_logic.apply_skill_status("Grand Design", caster, caster, units)
    assert near.mv == 4 and near.speed == 15 and far.mv == 3
    game_logic.tick_buffs(near)
    game_logic.tick_buffs(near)
    assert near.mv == 4  # still up through its next two turns
    game_logic.tick_buffs(near)
    assert near.mv == 3 and near.speed == 10 and not near.buffs


def test_reason_together_never_misses(board, monkeypatch):
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.999)
    caster, target = make_unit("Hero"), make_unit("Judas", "Enemy", 0, 1)
    game_logic.apply_skill_status("Reason Together", caster, target, [caster, target])
    assert target.faith == 100 + game_logic.REASON_TOGETHER_FAITH


def test_shield_of_faith_wards_off_enemy_preaching(board):
    caster, ally = make_unit("Hero"), make_unit("Peter", x=1)
    enemy = make_unit("Legionnaire 1", "Enemy", 2, 0)
    game_logic.apply_skill_status("Shield of Faith", caster, ally, [caster, ally, enemy])
    assert ally.guarded
    game_logic.apply_preach(enemy, ally)
    assert ally.faith == 100
    for _ in range(game_logic.SHIELD_OF_FAITH_TURNS):
        game_logic.begin_turn(ally)
    faith = ally.faith
    game_logic.apply_preach(enemy, ally)
    assert ally.faith < faith  # the ward has worn off


def test_arrest_binds_and_disarms_unless_resisted(board, monkeypatch):
    caster, target = make_unit("Hero"), make_unit("Timon", "Enemy", 0, 1)
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.999)  # never resisted
    game_logic.apply_skill_status("Arrest", caster, target, [caster, target])
    assert target.snared_turns == game_logic.ARREST_SNARE_TURNS and target.disarmed_turns == 1


def test_marshal_and_psalm_move_the_turn_order(board):
    caster = make_unit("Hero")
    ally, foe = make_unit("Peter", x=1), make_unit("Timon", "Enemy", 0, 2)
    ally.ct, foe.ct = 50, 50
    units = [caster, ally, foe]
    game_logic.apply_skill_status("Marshal", caster, caster, units)
    game_logic.apply_skill_status("Psalm", caster, caster, units)
    assert ally.ct == 50 + game_logic.MARSHAL_CT
    assert foe.ct == 50 - game_logic.PSALM_CT


def test_bold_venture_can_backfire_on_the_caster(board, monkeypatch):
    caster, target = make_unit("Hero", faith=100), make_unit("Timon", "Enemy", 0, 1)
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.99)  # the gamble fails
    game_logic.apply_skill_status("Bold Venture", caster, target, [caster, target])
    assert caster.faith == 100 - game_logic.BOLD_VENTURE_BACKFIRE and target.faith == 100
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)  # and pays off
    game_logic.apply_skill_status("Bold Venture", caster, target, [caster, target])
    assert target.faith == 100 + game_logic.BOLD_VENTURE_FAITH


def test_self_centred_skills_target_the_casters_own_tile(board):
    caster = make_unit("Hero", x=3, y=3, skills=["Inspire"])
    assert (3, 3) in game_logic.get_skill_targets(caster, "Inspire", [caster])


def test_sling_is_a_ranged_disarm(board, monkeypatch):
    monkeypatch.setattr(game_logic.random, "random", lambda: 0.0)
    caster, target = make_unit("Hero"), make_unit("Timon", "Enemy", 0, 4)
    killed, _ = game_logic.resolve_physical_hit(caster, target, "Sling", [caster, target])
    assert not killed and target.disarmed_turns == game_logic.DISARM_TURNS and target.is_alive()


def test_the_short_survey_has_twelve_questions_three_per_pair():
    short = hero.load_survey_from_csv(version="short")
    assert len(short) == 12
    for a, b in hero.PAIRS:
        assert sum(1 for q in short if {q["answers"][0][1], q["answers"][1][1]} == {a, b}) == 3, (a, b)


def test_every_type_is_reachable_from_the_short_survey():
    short = hero.load_survey_from_csv(version="short")
    for want in itertools.product(*hero.PAIRS):
        answers = [0 if q["answers"][0][1] in want else 1 for q in short]
        assert hero.score_survey(short, answers) == "".join(want)


def test_a_tied_pair_goes_to_its_first_answer():
    questions = [{"answers": [("a", "T"), ("b", "F")]}, {"answers": [("a", "T"), ("b", "F")]}]
    assert hero.score_survey(questions, [1, 0])[2] == "F"
    assert hero.score_survey(questions, [0, 1])[2] == "T"


def test_the_super_short_survey_asks_one_question_per_letter():
    four = hero.load_survey_from_csv(version="super_short")
    assert len(four) == 4
    assert [{q["answers"][0][1], q["answers"][1][1]} for q in four] == [set(p) for p in hero.PAIRS]
    for want in itertools.product(*hero.PAIRS):
        answers = [0 if q["answers"][0][1] in want else 1 for q in four]
        assert hero.score_survey(four, answers) == "".join(want)


def test_the_web_build_keeps_the_profile_in_browser_storage(tmp_path):
    class FakeLocalStorage:
        def __init__(self):
            self.items = {}

        def setItem(self, key, value):
            self.items[key] = value

        def getItem(self, key):
            return self.items.get(key)

    storage = FakeLocalStorage()
    assert hero.load_profile(storage=storage) is None  # nothing saved yet
    hero.save_profile({"name": "Lydia", "type": "ENFJ"}, storage=storage)
    assert hero.BROWSER_PROFILE_KEY in storage.items
    assert not (tmp_path / "profile.json").exists()
    assert hero.load_profile(storage=storage) == {"name": "Lydia", "type": "ENFJ"}
    storage.items[hero.BROWSER_PROFILE_KEY] = "not json"
    assert hero.load_profile(storage=storage) is None
