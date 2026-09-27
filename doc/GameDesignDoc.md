# The Road to Rome — Game Design Document

*Status: living document, reflects the codebase as of 2026-09-16.*

## 1. Overview

| | |
|---|---|
| **Working title** | The Road to Rome |
| **Genre** | Grid-based isometric tactics RPG (Final Fantasy Tactics / Tactics Ogre lineage) |
| **Engine** | Python + pygame (pygame-ce) |
| **Platform** | Desktop (Windows dev target), single-player, local only |
| **Entry point** | `python fftr.py` |
| **Setting** | The early Christian Church, ~AD 35–64 — after the Gospels, during the Acts-of-the-Apostles era, ending with Nero's persecution in Rome |
| **Session shape** | World map (node-graph overworld) → battle (tactics grid) → back to world map, roster/loadout persists in-memory for the session. *Currently the world map is hidden: both entrypoints boot straight into the Jerusalem battle (`run_first_stage` in `game_logic.py`), and `world_map.py` is unchanged and still runnable on its own.* |

The player leads a fixed party of the early Church's apostles and missionaries — led by **Paul** — across six cities of the Roman Empire, preaching, converting, and surviving armed persecution, ending at Paul and Peter's martyrdom under Nero in Rome.

There is intentionally no divine/miracle-working lead character (no Jesus unit). Paul is written and drawn as human: a former persecutor turned missionary, not a messianic figure.

## 2. Narrative & Campaign Structure

Six battle stages, visited in a fixed order on the world map, connected by two non-battle waypoint towns:

```
Jerusalem → Caesarea (town) → Antioch → Philippi ⟍
                                            Troas (town) → Ephesus → Rome
                                Corinth ⟋
```

| # | Stage | Title | Narrative beat | Difficulty (enemy count) |
|---|---|---|---|---|
| 1 | Jerusalem | *Paul Among the Apostles* | Paul arrives in Jerusalem after his conversion (Acts 9:26–30); the church is wary of him, Barnabas vouches for him | 6 Legionnaires (vs. a 5-unit party) |
| 2 | Antioch | *The First Gentile Church* | The first Gentile congregation forms; Paul and Barnabas are commissioned as missionaries | 3 Legionnaires |
| 3 | Philippi | *The Jailer's Household* | Paul and Silas are imprisoned, an earthquake frees them, the jailer converts (Acts 16) | 3 Legionnaires + 1 Archer |
| 4 | Corinth | *A Fractious Church* | Paul plants a divided but growing church; brought before the proconsul Gallio (Acts 18) | 3 Legionnaires + 1 Archer |
| 5 | Ephesus | *Riot of the Silversmiths* | Demetrius incites a riot in defense of Artemis worship (Acts 19) | 5 Legionnaires + 1 Archer + 1 Sergeant |
| 6 | Rome | *Nero's Persecution* | Climax: Demas deserts the faith for the world; Paul and Peter face Roman persecution under Nero | Demas (Enemy Apostle) + Centurion Marcus + 20 Legionnaires |

Each stage has hand-authored `map_layout.csv`, `terrain_layout.csv`, and `characters.csv` under `data/stages/<name>/`, (terrain cells are single-letter codes - `G` grass, `W` water, ... - resolved to tile art through `data/terrain_types.csv`), plus an optional `props.csv` (`x, y, prop, height`) placing scenery - `tree` or `boulder` - that occupies its tile and stands `height` map height units tall. Heights in `map_layout.csv` are whole numbers, or half steps (0.5, 1.5, ...) which draw as slopes ramping between the lower and higher tile beside them. Difficulty escalates from stage to stage purely through enemy count/composition (all Legionnaire-family units share the same base stat template, randomized per row).

Dialogue is scripted per stage/turn in `data/dialogues.csv` (`map, turn, character, text`) and fires mid-battle at specific turn counts. Non-climax stages get 4 lines (opening exchange at turn 1, a reaction beat at turn 8–9); Rome, the climax, gets 8 lines including Demas's desertion and Paul's final "I have fought the good fight" speech at turn 11. Dialogue only plays if Paul is present in the stage's roster (which is every stage).

## 3. The Party

12 fixed player units, drawn on per stage (position/stat values vary slightly per stage file). Jerusalem currently fields 5 of them - Paul, Peter, Barnabas, Mark and John, the units its narrative beat turns on:

| Unit | Class | Role/flavor |
|---|---|---|
| **Paul** | Missionary | Party leader. 1.5× Preach/Heal effectiveness. Highest Faith stat. |
| Peter | Apostle | The Rock; carries over from the Gospels era |
| Barnabas | Apostle | Paul's early missionary companion, "son of encouragement" |
| Mark (John Mark) | Apostle | Gospel author, companion of Peter and Paul |
| John | Apostle | The Beloved Disciple, later elder of Ephesus |
| Philip | Apostle | Philip the Evangelist (Acts 8/21) |
| Timothy | Apostle | Paul's protégé |
| Luke | Apostle | Physician and historian, author of Luke–Acts |
| Titus | Apostle | Paul's delegate, active at Corinth |
| Silas | Apostle | Imprisoned with Paul at Philippi |
| Priscilla | Apostle | Teacher, met Paul at Corinth |
| Aquila | Apostle | Priscilla's husband and ministry partner |

**Antagonists**:
- **Demas** (Enemy, class Apostle) — a former companion who deserts "having loved this present world" (2 Tim 4:10). Appears only in the Rome stage. Being an `Apostle`-class Enemy, he is theoretically preachable back to the Player side via the Faith/conversion mechanic (see §5), same as the original design's Judas.
- **Centurion Marcus** (Enemy, class Officer) — Roman officer, grants a hit-chance aura to nearby Legionnaires.
- **Legionnaires** (Enemy, classes Soldier / Archer / Sergeant) — rank-and-file Roman military, the recurring antagonist force across all six stages.

## 4. Combat System

### Turn order
Charge-Time (CT) system: every living unit accrues `CT += Speed` each tick; the first unit to reach CT 100 acts, then resets to 0. An 8-icon turn-order preview is simulated ahead of time for the UI.

### Movement
A*-style flood fill bounded by `mv` (move range) and `jump` (max elevation change crossable); occupied tiles block movement (no stacking), as do tiles holding scenery props. Standing in water reduces effective move range by 1 tile. A slope tile is half a height step, so a 0→0.5→1 ramp is climbable by a unit that could already manage the 0→1 step.

### Hit resolution (Physical skills only — Slash, Shoot)
```
hit chance = 0.85 (base)
           + elevation_diff × 0.08        (attacker height − target height)
           + class hit bonus              (Soldier/Sergeant: +0.05)
           + 0.10 if an allied Officer is within 2 tiles of the attacker
           − target.magic_defense × 0.002
clamped to [0.50, 0.98]
```
A hit kills outright (no HP pool anywhere in the game — combat is binary hit/miss/one-shot-kill). A `guarded` unit (via the Defend skill) blocks the next incoming Physical hit instead of dying, consuming the guard.

Faith/Heal-family skills (Preach, First Aid, Heal, Resurrection) never miss — they resolve deterministically through the Preach formula (§5), not a hit roll.

### Status effects
- **Snared** (Fish net): 2 turns, target can't move (can still act).
- **Stunned** (Shove, 50% base connect chance): 1 turn, target's entire turn is skipped.
- Both are resisted with probability `min(0.6, target.patience × 0.004)` — a high-Patience unit shrugs off crowd control.

### Morale (passive, every unit's own turn)
`min(0.3, bravery × 0.004)` chance per turn to permanently gain +5 Faith, +1 Move, +1 Jump, +5 Speed for the rest of the battle.

### Faith decay
Every unit loses 1% of its current Faith at the start of its own turn (applies to both sides).

## 5. Faith & the Preach/Conversion Mechanic

This is the game's signature system, standing in for a traditional damage economy.

```
gain = (preacher.faith + preacher.magic_attack) × 0.2 × class multiplier
target.faith = clamp(target.faith + gain, 0, FAITH_CAP=200)
```
Missionary class (Paul) gets ×1.5 on this formula. Preach, First Aid, Heal, and Resurrection all call the *same* function — they differ only in MP cost and range, not in effect. ("Resurrection" does not revive dead units; that's the Ankh item's job — see §7.)

**Conversion**: if an Enemy unit's Faith reaches the cap (200) from being preached at, it flips to the Player team, is recolored, and is `disabled` for the remainder of the battle (stands there as a converted body, takes no further turns that fight). This is how the game handles "defeating" an enemy without ever dealing damage — you talk them out of the fight rather than killing them (killing is reserved for the binary Physical-skill hit resolution above).

## 6. Classes & Passives

| Class | Who | Passive |
|---|---|---|
| Missionary | Paul | ×1.5 Preach/Heal-family effectiveness |
| Apostle | The 11 companions + Demas | No unique passive (baseline) |
| Officer | Centurion Marcus | Grants +0.10 hit chance to allies within 2 tiles |
| Soldier | Legionnaires | +0.05 hit chance |
| Sergeant | (Ephesus's "Legionnaire Sergeant") | +0.05 hit chance; Shove pushes 3 tiles instead of 2 |
| Archer | (defined, currently unassigned in the roster — reserved) | Ignores the uphill hit-chance penalty |

## 7. Items (shared Player-team pool, not per-character)

| Item | Uses | Effect |
|---|---|---|
| Healing Salve | 3 | Clears Snared/Stunned status on an ally (range 1) |
| Ankh | 2 | Revives a fallen ally; new Faith = half the reviver's own Faith + the reviver's full Love stat (min 10) |
| Myrrh | 2 | Fully restores an ally's MP (range 1) |
| Frankincense | 2 | Buffs an ally's Magic Attack by 30% of the *user's own* Magic Attack |
| Mustard Seed | 3 | Grants +20 Faith (+ user's Love if targeting another unit), range 2 |

## 8. Equipment

9 slots: `helmet, armor, pants, sandals, left_hand, right_hand, necklace, ring_1, ring_2` (both rings draw from one shared "ring" catalog). 24 catalog items (`data/equipment.csv`), each granting 1–2 flat stat bonuses, themed around Ephesians 6's "armor of God" (Helmet of Salvation, Shield of Faith, Sword of the Spirit, Belt of Truth, Breastplate of Righteousness, Shoes of the Gospel of Peace). Equipped bonuses apply once at battle start and hold for the whole fight. Equipping only happens on the world map, not mid-battle.

## 9. Books — the "Daily Devotion" Growth System

5 book slots per unit, freely interchangeable (any of the 66 books of the Bible fits any slot — unlike equipment, no slot restriction). Each book is tied to one growable stat (`data/books.csv`).

- Holding a book across turns slowly grows its stat: roughly 1.5–2.5% of the current value per own-turn held (min +1), tracked cumulatively per book.
- Growth persists on the world-map roster across the whole play session (units are rebuilt from base CSV stats each battle, then the accrued book bonus is re-applied).
- Swapping a book resets that slot's progress.
- A flavor "reading level" label (Novice / Learned / Devoted / Mastered) reflects turns held (10/20/30 thresholds).

## 10. World Map

Node-graph overworld (`data/world_map_nodes.csv`): 6 "stage" nodes that launch a battle, 2 "town" nodes (Caesarea, Troas) that are pure waypoints. Travel between connected nodes is an animated lerp; re-entering a stage node replays that battle.

Off-map screens: **Menu** (Unit / Close) → **Unit List** (Player roster) → **Unit Detail** (stat sheet) → **Equipment** and **Books** sub-screens (cycle items/books per slot, see live stat totals).

## 11. Controls

| Input | Action |
|---|---|
| A / S / D / W | Pan camera |
| Q / E | Rotate isometric view |
| Z / X | Zoom out / in |
| H | Toggle HUD |
| Arrow keys | Move tile cursor / navigate menus; on the world map, picks the best-aligned connected node |
| Space / Enter | Confirm selection / start battle on a stage node |
| Escape | Back out a menu level / quit |
| Mouse | Full support — click/drag to move, click menu rows, right-click to cancel a selection, wheel to scroll |

## 12. AI Behavior

Enemy ("Enemy"/"Blue" team) units evaluate each affordable skill in range and pick by priority: Heal-family skills target the lowest-Faith living ally; Support skills target the lowest-CT ally; offensive skills target the lowest-Faith enemy, tiebroken by the skill's raw power stat then distance. If nothing is in range, the unit advances one reachable tile toward its nearest valid target (or ends its turn if none exists).

## 13. Art Pipeline

On-map unit tokens are generated from a single master isometric-SVG source (`assets/print_svg.py`, split per character, rasterized via `assets/svg2png.py` using PyMuPDF, gradients flattened to flat colors since the renderer doesn't support live SVG gradients). Three alternate on-map art styles exist behind a `UNIT_ART_STYLE` switch in `game_logic.py`: `"icons"` (each character's own sprite, current default), `"pixel"` (bundled CC0 chibi pack by job class), `"chess"` (Cburnett chess set by job class). A separate, higher-detail painterly portrait set (`assets/portraits/`) backs the character-screen UI (world map roster/equipment/books, turn order strip, unit profile), falling back to the on-map icon for any unit without a dedicated one (currently: Paul).

## 14. Known Gaps / Not Yet Implemented

- **No save/load system** — everything is in-memory for one session only.
- **No random/wandering battles** — only the 6 fixed stage fights exist.
- **No undo** for moves or attacks.
- **Sergeant and Archer class passives** are implemented in code but not currently assigned to any roster unit outside Ephesus's one Sergeant.
- No HP pool / damage numbers exist anywhere — all combat is binary (hit/miss/kill) or Faith-based; this is a deliberate design choice, not a gap, but worth flagging for anyone expecting a conventional damage system.

## 15. Roadmap (from README's stated goals)

**Near-term**: more AI art, more abilities, attack/move undo, a character roster menu (partially done via Unit List/Detail), random battles, an "Animal Aspect" gem/socket system (Path of Exile 2-style).

**Longer-term**: Itch.io playtest release, a server, web-based multiplayer.

---

## 16. Comments & Input

*Open section — add feedback, questions, and discussion below. Sign entries with your name/date so threads stay easy to follow.*

### New ideas ###
- Focus on the combat system to make it fun first
- Building system where you can build up churches across different locations. The characters can be assigned in positions for the church to scribe books and letters to influence other entities in the game. They can also preach and get tithes from believers. They should also do outreach to heal the sick in the areas, while fighting off or being secretive about what they are preaching to avoid Roman persecutions.
- New books can be researched and developed which unique abilities or contribute to attributes.
- Fellowship can be the core of the adventure party, instead of using the entire roster of people to go into battle.
