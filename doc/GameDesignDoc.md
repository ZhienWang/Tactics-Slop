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
| 0 | Road to Damascus | *The Road to Damascus* | The opening (and default) stage, before Paul's conversion: Saul, "breathing threats and murder against the disciples", rides for Damascus with the high priest's letters to bring believers back bound (Acts 9:1–2). You play Saul and 4 Temple Guards, all on horseback (+3 Move); the enemies are 6 disciples - Ananias (Acts 9:10) and the deacons Prochorus, Nicanor, Timon, Parmenas and Nicolas (Acts 6:5). Desert road map, 12×10, sunny. Saul starts at full faith ("extremely zealous", Gal 1:14) and carries Heal. The disciples start in the middle of the map and **run for the road to Damascus**: exit tiles at the far (screen-left) end of the road, listed in the stage's `escape.csv`. Each turn a disciple runs its full Move toward the nearest exit - unless it stands firm and preaches instead (chance = its Bravery / 100, never when an exit is in reach) - and leaves the battle once it reaches one. Saul's band doesn't preach on this stage - **Persecute** replaces Preach for every Player unit here, the hero included (`STAGE_SKILL_SWAPS`): it never misses, takes a fixed 10 faith and slows the target by 1 Move for its next 2 turns (refreshed, not stacked); a disciple whose faith it breaks to 0 is **arrested** and taken off the field. Netting a disciple (snared units can't run), slowing them with Persecute, blocking the road or arresting them stops them; in play-testing 1–4 get away each battle, usually 2. **The light from heaven** (Acts 9:3–8): once only 2 disciples still stand against Saul (the rest arrested, escaped or converted), the battle stops - a blinding flash, then a shaft of sunlight from the sun onto Saul, who is thrown from his horse and lies on the ground beside it - and Jesus asks him why he is persecuting him (dialogue filed under `light` in `dialogues.csv`). The stage then ends with the title *A Light from Heaven*: "Saul rises blind, and his men lead him by the hand into Damascus." Scripted scenes like this are set per stage in `STAGE_SCENES` (game_logic.py) | 6 Disciples (vs. 5 riders) |
| 1 | Jerusalem | *Paul Among the Apostles* | Paul arrives in Jerusalem after his conversion (Acts 9:26–30); the church is wary of him, Barnabas vouches for him | 6 Legionnaires (vs. a 5-unit party) |
| 2 | Antioch | *The First Gentile Church* | The first Gentile congregation forms; Paul and Barnabas are commissioned as missionaries | 3 Legionnaires |
| 3 | Philippi | *The Jailer's Household* | Paul and Silas are imprisoned, an earthquake frees them, the jailer converts (Acts 16) | 3 Legionnaires + 1 Archer |
| 4 | Corinth | *A Fractious Church* | Paul plants a divided but growing church; brought before the proconsul Gallio (Acts 18) | 3 Legionnaires + 1 Archer |
| 5 | Ephesus | *Riot of the Silversmiths* | Demetrius incites a riot in defense of Artemis worship (Acts 19) | 5 Legionnaires + 1 Archer + 1 Sergeant |
| 6 | Rome | *Nero's Persecution* | Climax: Demas deserts the faith for the world; Paul and Peter face Roman persecution under Nero | Demas (Enemy Apostle) + Centurion Marcus + 5 Legionnaires (7 enemies) |

**Mounts**: a `mount` column in `characters.csv` puts a unit on horseback (`horse`), adding +3 Move and drawing a horse (`assets/horse.png`, generated by `assets/horse_art.py`) over the lower half of the unit's token; the profile shows "(Mounted)". An optional `face_portrait` column gives a unit its own HUD portrait - the Damascus disciples borrow apostle map tokens but show public-domain commoner faces from `assets/portraits/converts/`.

Each stage has hand-authored `map_layout.csv`, `terrain_layout.csv`, and `characters.csv` under `data/stages/<name>/`, (terrain cells are single-letter codes - `G` grass, `W` water, ... - resolved to tile art through `data/terrain_types.csv`), plus an optional `props.csv` (`x, y, prop, height`) placing scenery - `tree` or `boulder` - that occupies its tile and stands `height` map height units tall. Heights in `map_layout.csv` are whole numbers, or half steps (0.5, 1.5, ...) which draw as slopes ramping between the lower and higher tile beside them. Difficulty escalates from stage to stage through enemy count, composition, skill kits and level (Jerusalem Lv 1 rising to Rome Lv 7–8; see §13). All Legionnaire-family units share the same base stat template, randomized per row.

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
- **Legionnaires** (Enemy, subclasses Shieldbearer / Archer / Medic, plus Ephesus's Sergeant) — rank-and-file Roman military, the recurring antagonist force across all six stages. Shieldbearers are the tanks, Archers the ranged damage, Medics the healers.

## 4. Combat System

### Turn order
Charge-Time (CT) system: every living unit accrues `CT += Speed` each tick; the first unit to reach CT 100 acts, then resets to 0. An 8-icon turn-order preview is simulated ahead of time for the UI.

### Movement
A*-style flood fill bounded by `mv` (move range) and `jump` (max elevation change crossable); occupied tiles block movement (no stacking), as do tiles holding scenery props. Standing in water reduces effective move range by 1 tile. A slope tile is half a height step, so a 0→0.5→1 ramp is climbable by a unit that could already manage the 0→1 step.

### Hit resolution (Physical skills: Slash, Shoot)
```
hit chance = 0.85 (base)
           + elevation_diff × 0.08        (attacker height − target height)
           + class hit bonus              (Soldier/Sergeant: +0.05)
           + 0.10 if an allied Officer is within 2 tiles of the attacker
           − target.magic_defense × 0.002
clamped to [0.50, 0.98]
```
What a hit does depends on the skill. There's no HP pool anywhere in the game.
- **Slash disarms; it doesn't kill.** The target can't act (no Acts or items) for its next **2 turns**. It can still move or wait. Hitting an already-disarmed unit restarts the count. So the only way to take an enemy out of the fight is conversion (§5).
- **Shoot still kills outright.** Archers are the one lethal threat.
- **Guard:** a `guarded` unit (via the Defend skill) blocks the next incoming Physical hit, consuming the guard.

Heal-family skills (First Aid, Heal) never miss. Preach (a Faith attack) rolls against the preacher's Love: `hit = clamp(0.55 + love × 0.01, 0.5, 0.98)`; on a hit it resolves through the Preach formula (§5).

### Status effects
- **Snared** (Fish net): 2 turns, target can't move (can still act).
- **Stunned** (Shove, 50% base connect chance): 1 turn, target's entire turn is skipped.
- Both are resisted with probability `min(0.6, target.patience × 0.004)` — a high-Patience unit shrugs off crowd control.

### Morale (passive, once per battle, one turn)
- **The roll:** at the start of each of its turns, a unit that hasn't had its surge yet rolls `min(0.35, 0.05 + bravery × 0.004)`. The 5% base is a dice roll everyone gets; Bravery adds to it.
- **The surge:** on a success, the unit gets +5 Faith, +1 Move, +1 Jump and +5 Speed **for that turn only**. The bonus is taken back at the start of its next turn.
- **Limit:** each unit can surge **only once per battle**.

### Faith decay
Every unit loses 1% of its current Faith at the start of its own turn (applies to both sides).

## 5. Faith & the Preach/Conversion Mechanic

This is the game's signature system, standing in for a traditional damage economy.

```
gain = (preacher.faith + preacher.magic_attack) × 0.2 × class multiplier
target.faith = clamp(target.faith + gain, 0, FAITH_CAP=200)
```
Missionary class (Paul) gets ×1.5 on this formula. Preach, First Aid, and Heal all call the *same* function — they differ only in MP cost and range, not in effect. Reviving the fallen is the Ankh item's job — see §7.

**Lead** (Paul, 50 MP): every friendly unit within 2 tiles of Paul, Paul included, gains +50 Love for its next 3 turns, raising their Preach accuracy; the bonus is removed at the start of its 4th turn. Leading an already-led unit refreshes it to 3 turns without stacking the +50.

**Conversion**: if an Enemy unit's Faith reaches the cap (200) from being preached at, it flips to the Player team with a young faith of 100, is recoloured, and **fights for the player under their control** from its next turn (its Stun/Snare/Disarm and guard are cleared). Converted Legionnaires switch to their converted art: on the map, a blue crest and shield with a gold halo (`assets/legionaire_converted.png`, generated by `assets/converted_art.py`); in the HUD, a commoner's face drawn at random from `assets/portraits/converts/` - public-domain 17th-century head studies by Rubens, Rembrandt, Lievens, Jordaens, Hals and Carracci (sources in its `CREDITS.txt`). No two converts share a face in a battle while faces remain, and a unit keeps its face if it's converted again. Conversion isn't final: if enemy preaching shakes a convert's faith to 0, instead of falling into Despair they **turn back** to their original side (faith 100, original art) and can be preached over again - back and forth until every enemy has converted or fled. The preacher whose action completes a conversion earns 45–65 EXP instead of the usual 9–15 (see §10). Converts only last for the battle; they don't join the world-map party.

**Fleeing**: at the start of each of its turns, a Legionnaire still on the enemy side rolls to flee the battle. Nobody runs while the line holds - the chance is `0.6 × pressure × timidity`, where pressure is the share of the original enemy force already converted or fled, and timidity is `1 − (Bravery + Patience) / 150` (never below 0). A fled unit leaves the field for good. Only Legionnaires flee - not Centurion Marcus or Demas. The battle is won when no enemy remains on the field, whether converted or fled.

**Drawing order**: the map draws all terrain first, then props and units back to front on top, so a hill or ridge in front of a unit never covers it; trees and boulders still stand in front of units behind them.

**Paul's faith**: Paul leads the mission - if his faith is ever broken to 0 the battle is lost immediately ("Paul's faith is broken"), even with the rest of the party standing. Anyone else whose faith hits 0 falls into Despair (or, for a convert, turns back) as usual.

## 6. Classes & Passives

| Class | Who | Passive |
|---|---|---|
| Missionary | Paul | ×1.5 Preach/Heal-family effectiveness |
| Apostle | The 11 companions + Demas | No unique passive (baseline) |
| Officer | Centurion Marcus | Grants +0.10 hit chance to allies within 2 tiles |
| Soldier | (unused - superseded by the three Legionnaire subclasses) | +0.05 hit chance |
| Shieldbearer | Legionnaire tanks | Starts each battle guarded; Physical hits against it get −0.15 hit chance |
| Medic | Legionnaire healers | No passive; carries Rally (below) |
| Sergeant | (Ephesus's "Legionnaire Sergeant") | +0.05 hit chance; Shove pushes 3 tiles instead of 2 |
| Archer | Legionnaire archers | Ignores the uphill hit-chance penalty |

**Rally** (Medic, Support, range 2, 0 MP): enemies can't be healed the way the party is - their "wounds" are the faith the party's preaching has built up toward conversion. Rally pulls an ally's faith down by up to 20, never below 100 (where every enemy starts), and clears Stun, Snare and Disarm. The AI rallies whichever ally is closest to converting, and Medics walk toward allies who need it.

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

## 10. Levels & EXP

A Final Fantasy Tactics-style progression: units learn by doing. Every action earns a little EXP, and converting an enemy earns a lot. Each 100 EXP is a level, which brings small, job-flavored stat growth. The same rules apply to both sides.

### Starting level
Every unit, Player and Enemy, starts at **Lv 1 with 0 EXP**. `characters.csv` supports an optional `level` column for a unit that should start higher, such as a veteran enemy officer; none currently use it.

### Earning EXP

**Regular actions: 9–15 EXP**
```
EXP = clamp(11 + (target Lv − actor Lv), 9, 15)
```

| Target's level vs. the actor's | −2 or lower | −1 | equal | +1 | +2 | +3 | +4 or higher |
|---|---|---|---|---|---|---|---|
| **EXP** | 9 | 10 | **11** | 12 | 13 | 14 | 15 |

- **Counts:** every Act or item used on a target, whether it hits, misses or is blocked by a guard, as in FFT. Heals, buffs and Lead count too; the "target" is then the ally, or the caster for self-targeted skills like Lead.
- **Doesn't count:** Move, Wait, and turns lost to Stun or Despair.
- **Why a band:** a higher-level target is always worth more, but the gap is capped both ways. Grinding weak enemies still pays 9, and a far stronger foe pays no more than 15, so pacing stays predictable.

**Conversion: 45–65 EXP**

The one action that fills an enemy's faith to 100%, converting them to the Player side, earns this *instead of* the regular amount. Only the unit whose action converts the enemy gets it; earlier preachers only got their regular EXP.
```
EXP = clamp(55 + 2 × (target Lv − actor Lv), 45, 65)
```

| Target's level vs. the actor's | −5 or lower | −3 | −1 | equal | +1 | +3 | +5 or higher |
|---|---|---|---|---|---|---|---|
| **EXP** | 45 | 49 | 53 | **55** | 57 | 61 | 65 |

### Leveling up
- **100 EXP = 1 level.** The remainder carries over (105 EXP → next level with 5), and a big gain can grant several levels at once.
- **Cap:** Lv **99**. At the cap, EXP stops at 99.
- **Pacing:** between equal-level units, a level takes about 9–10 regular actions, and one conversion is worth about half a level. Example: Paul at Lv 1 preaches three times at a Lv 1 Legionnaire (3 × 11 = 33) and converts them with a fourth Preach (+55), for 88 EXP. One more action reaches Lv 2.

### Stat growth
Fixed per job rather than rolled, so a unit's stats can always be rebuilt exactly from its level:

| Job | MP (max and current) | Speech (magic_attack) | Resist (magic_defense) |
|---|---|---|---|
| Missionary | +5 | +2 | +1 |
| Apostle | +3 | +1 | +1 |
| Soldier / Sergeant | +1 | +1 | +2 |
| Officer | +2 | +1 | +2 |
| Archer | +1 | +1 | +1 |
| Shieldbearer | +1 | +0 | +3 |
| Medic | +2 | +2 | +1 |
| any other | +2 | +1 | +1 |

**Speed** grows slowly: +1 on every 5th level (Lv 5, 10, 15 …). Faith, Bravery, Patience and Love don't grow with level; Books (§9) and Morale cover those.

Example: Paul at Lv 10 has gained +45 MP, +18 Speech, +9 Resist and +2 Speed over his Lv 1 stats.

### Display
- **Popup:** "+N EXP" floats over the actor right after the action's speech bubble or faith popup.
- **Level-up:** "LEVEL UP!" (or "LEVEL UP x2!") appears with the `@level_up` particle effect, a sunburst with rising arrows, bindable in `skill_effects.csv`.
- **Unit profile:** "Lv N  Job" beside the name, plus an EXP bar toward the next level.
- **Elsewhere:** the battle preview cards and the field stats list show each unit's level.

### Persistence
- **Carried between battles:** level and EXP ride along with book progress on the world-map roster.
- **Rebuilt each battle:** units come from base CSV stats, then equipment, book and level growth are re-applied.
- **Current limitation:** the world map is hidden and the game boots straight into Jerusalem, so progress lasts only for the session.

### Tuning
All constants are in `scripts/game_logic.py`:

| Constant | Meaning |
|---|---|
| `EXP_BASE`, `EXP_MIN`, `EXP_MAX` | Regular action EXP (11, clamped to 9–15) |
| `CONVERT_EXP_BASE`, `CONVERT_EXP_PER_LEVEL`, `CONVERT_EXP_MIN`, `CONVERT_EXP_MAX` | Conversion EXP (55, ±2 per level gap, clamped to 45–65) |
| `EXP_PER_LEVEL`, `MAX_LEVEL` | 100 EXP per level, cap 99 |
| `LEVEL_GROWTH`, `DEFAULT_LEVEL_GROWTH`, `SPEED_GROWTH_EVERY` | Per-job growth and speed cadence |

**Code:** `exp_for_action` computes the award, `gain_exp` levels the unit up, and `apply_level_bonuses` rebuilds its stats. Every action goes through `report_action`, which awards EXP and queues the action's effects exactly once.

## 11. World Map

Node-graph overworld (`data/world_map_nodes.csv`): 6 "stage" nodes that launch a battle, 2 "town" nodes (Caesarea, Troas) that are pure waypoints. Travel between connected nodes is an animated lerp; re-entering a stage node replays that battle.

Off-map screens: **Menu** (Unit / Close) → **Unit List** (Player roster) → **Unit Detail** (stat sheet) → **Equipment** and **Books** sub-screens (cycle items/books per slot, see live stat totals).

## 12. Controls

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

## 13. AI Behavior

Enemy ("Enemy"/"Blue" team) units score every affordable skill on every target in range (`score_ai_candidate`) and take the best, breaking ties by distance. Roughly, from most to least wanted:

| Priority | Action | When / whom |
|---|---|---|
| 1 | **Shove** | Only into a cluster: a target with at least one ally standing right next to it. Never on a lone unit. |
| 2 | **Shoot** | Any target in range. |
| 3 | **Preach** | Sowing doubt at the Player team, it targets the **lowest-Faith** unit first, to break them into Despair. Preaching to convert targets whoever is closest to conversion. |
| 4 | **Slash** | Anyone not already disarmed. |
| 5 | **Heals** | The most-hurt ally. |
| 6 | **Fish net** | Only at a target 2+ tiles away and not already snared, and never two turns in a row, so net-throwers still close in. |
| 7 | **Support** | Lead, Command, Defend. |

- **Converted units are off limits:** neither the AI nor the Player can target them. They're skipped by Acts, items and AI movement alike.
- **Disarmed units** can only move.
- **Nothing in range:** the unit advances one tile toward its nearest valid target.

**Enemy kits.** Legionnaires come in three subclasses:
- Shieldbearer: Preach|Slash|Defend (speed 10)
- Archer: Preach|Shoot (speed 10); the original "Legionnaire Archer 1" of Philippi/Corinth/Ephesus keeps Preach|Shoot|Shove
- Medic: Preach|Rally|Shove (speed 11)

Each stage has at most one Archer, since Shoot is the only enemy move that removes a party member.

| Stage | Shieldbearers | Archers | Medics |
|---|---|---|---|
| Jerusalem | 3 | 1 | 2 |
| Antioch | 1 | 1 | 1 |
| Philippi | 2 | 1 | 1 |
| Corinth | 2 | 1 | 1 |
| Ephesus | 3 | 1 | 2 |
| Rome | 2 | 1 | 2 |
 The Sergeant has Slash|Shove|Command, Centurion Marcus has Preach|Command|Defend, and Demas has Preach|Fish net|Slash.

**Enemy levels** rise stage by stage through the `level` column in each stage's `characters.csv`: Jerusalem Lv 1, Antioch 2, Philippi 3, Corinth 4, Ephesus 5, Rome 7 (Centurion Marcus 8). Level growth (§10) makes later enemies sturdier, and they're worth more EXP. The party always starts at Lv 1.

## 14. Art Pipeline

On-map unit tokens are generated from a single master isometric-SVG source (`assets/print_svg.py`, split per character, rasterized via `assets/svg2png.py` using PyMuPDF, gradients flattened to flat colors since the renderer doesn't support live SVG gradients). Three alternate on-map art styles exist behind a `UNIT_ART_STYLE` switch in `game_logic.py`: `"icons"` (each character's own sprite, current default), `"pixel"` (bundled CC0 chibi pack by job class), `"chess"` (Cburnett chess set by job class). A separate, higher-detail painterly portrait set (`assets/portraits/`) backs the character-screen UI (world map roster/equipment/books, turn order strip, unit profile), falling back to the on-map icon for any unit without a dedicated one (currently: Paul).

### Particle effects

Skill and item visuals are data-driven (`scripts/effects.py`). There are no offensive effects: Shoot only shows a defender's block, and Slash (which disarms rather than wounds) shows a sealing X.

- **`data/effects.csv`**: the effect library, 70+ effects in five categories: `buff`, `curse`, `holy`, `first_aid`, `flash`. Each row is one effect:
  - `pattern`: how particles move: rise, fall, burst, fountain, spiral, orbit, converge, vortex, sparkle, drip, miasma, ring, pillar, flash, rays, glyph, halo.
  - `shape`: star, cross, heart, feather, bandage, rune, eye, shield, net, arrow_up/arrow_down and more.
  - `colors`: `|`-separated hex colors.
  - `count`, `duration` (ms), `speed`, `size`, `radius`, `height`, `gravity`, `spin`: pixels at zoom 1.
  - `glow`: 0/1, additive light.
  - `screen_flash`: 0–255, whites out the screen.
  - `layers`: other effects to play at the same time, so composite effects need no code.
- **`data/skill_effects.csv`**: which effects play when. Columns are `skill,effect,anchor,on`:
  - `skill`: a skill or item name, or a game event: `@morale`, `@rekindle`, `@lead_fade`.
  - `anchor`: `target`, `caster`, or `recipients` (every unit an area skill like Lead affected).
  - `on`: `always`, `hit`, `miss`, `convert`, `shaken` (enemy Preach lowered faith) or `despair`.
  - One skill can have several rows, to layer effects or play different ones per outcome.
- **Gallery**: `python -m scripts.effects_gallery` shows every effect looping. Press 0–5 to filter by category, click an effect to enlarge it, and press F5 to reload after editing `effects.csv`.

### Voiced dialogue

Every line in `data/dialogues.csv` is read aloud in its speaker's voice (`scripts/voices.py`); the music dips while someone speaks.

- **Casting:** `data/voices.csv` sets each character's Microsoft neural voice (edge-tts), speaking rate and pitch. The `*` row covers anyone unlisted.
- **Generating:** `python tools/generate_voices.py` (needs internet) writes `assets/voices/<id>.ogg`, with the id taken from the speaker and text. Re-running only generates new or edited lines and removes clips for lines that no longer exist. `--force` regenerates everything, e.g. after recasting.
- **Stage directions:** text in parentheses stays on screen but isn't read aloud.
- A line without a clip plays silently. A test flags missing clips.

## 15. Known Gaps / Not Yet Implemented

- **No save/load system** — everything is in-memory for one session only.
- **No random/wandering battles** — only the 6 fixed stage fights exist.
- **No undo** for moves or attacks.
- **Sergeant and Archer class passives** are implemented in code but not currently assigned to any roster unit outside Ephesus's one Sergeant.
- No HP pool / damage numbers exist anywhere — all combat is binary (hit/miss/kill) or Faith-based; this is a deliberate design choice, not a gap, but worth flagging for anyone expecting a conventional damage system.

## 16. Roadmap (from README's stated goals)

**Near-term**: more AI art, more abilities, attack/move undo, a character roster menu (partially done via Unit List/Detail), random battles, an "Animal Aspect" gem/socket system (Path of Exile 2-style).

**Longer-term**: Itch.io playtest release, a server, web-based multiplayer.

---

## 17. Comments & Input

*Open section — add feedback, questions, and discussion below. Sign entries with your name/date so threads stay easy to follow.*

### New ideas ###
- Focus on the combat system to make it fun first
- Building system where you can build up churches across different locations. The characters can be assigned in positions for the church to scribe books and letters to influence other entities in the game. They can also preach and get tithes from believers. They should also do outreach to heal the sick in the areas, while fighting off or being secretive about what they are preaching to avoid Roman persecutions.
- New books can be researched and developed which unique abilities or contribute to attributes.
- Fellowship can be the core of the adventure party, instead of using the entire roster of people to go into battle.

## Protagonist, the class survey and Paul as advisor

**New Game** (the title screen, `scripts/intro.py`) starts with a survey that decides the player's own character - the hero. Paul, the hero's advisor, introduces it, and the player picks a length: the **long survey (30 questions)**, the **short one (12, marked `short` in `data/survey.csv`)** or the **super short one (4, marked `super_short` - one question deciding each letter)** - or skips the questions and **chooses a class outright** from a grid of all sixteen. Each either/or question leans to one side of a personality pair - E/I, S/N, T/F, J/P - with an odd number per pair (7/7/7/9 long, 3/3/3/3 short, 1/1/1/1 super short) so there are never ties. The result screen can also swap in a hand-picked class (**Choose class**) or retake the survey. The four majorities spell one of the sixteen types, and the player names their character (default *Theophilus*). **Continue** skips all of this once a profile is saved (`~/.road_to_jerusalem/profile.json`; the browser build can't keep it between visits).

The result screen reveals the class, its skills and **Paul's counsel** for that class - Paul is the hero's advisor, not the main character. The hero then joins the party in every battle on the free tile nearest Paul, riding whatever he rides (so on the Road to Damascus, the hero rides with Saul's band). Their map token is Mark's figure with the stand and book in the role's colour (`assets/hero_<role>.png`, generated by `assets/hero_art.py`); their HUD face is a public-domain painting (`assets/portraits/converts/convert_07.png`, kept out of the converts' face pool).

**Classes** (`data/classes.csv`) are named for the 16Personalities archetypes, grouped in four roles. Each has Preach, a role-appropriate existing skill, and a **signature skill** of its own (resolved in `resolve_signature`, game_logic.py):

| Role | Type | Class | Signature skill |
|---|---|---|---|
| Analyst | INTJ | Architect | **Grand Design** - allies within 2 get +1 Move, +5 Speed for 2 turns |
| Analyst | INTP | Logician | **Reason Together** - +25 faith to an enemy; never misses |
| Analyst | ENTJ | Commander | **Marshal** - allies within 2 get +30 CT |
| Analyst | ENTP | Debater | **Disputation** - stun 1 turn and +10 faith (Patience resists) |
| Diplomat | INFJ | Advocate | **Intercession** - an ally is cured of Despair and every status, +30 faith |
| Diplomat | INFP | Mediator | **Peacemaker** - disarm an enemy 2 turns (Patience resists) |
| Diplomat | ENFJ | Protagonist | **Inspire** - +15 faith to allies within 2 |
| Diplomat | ENFP | Campaigner | **Good News** - preaches (at 60% strength) to the target and every enemy beside it |
| Sentinel | ISTJ | Logistician | **Provision** - an ally's MP is refilled, Snare/Stun cured, +10 faith |
| Sentinel | ISFJ | Defender | **Shield of Faith** - an ally is guarded and their faith can't be shaken for 2 turns |
| Sentinel | ESTJ | Executive | **Arrest** - snare 3 turns and disarm 1 (Patience resists) |
| Sentinel | ESFJ | Consul | **Breaking Bread** - allies within 1 get +20 faith and +10 Love for 2 turns |
| Explorer | ISTP | Virtuoso | **Sling** - a Physical disarm from 4 tiles away |
| Explorer | ISFP | Adventurer | **Psalm** - enemies within 2 lose 30 CT, allies within 2 get +10 faith |
| Explorer | ESTP | Entrepreneur | **Bold Venture** - 55%: +60 faith to an enemy; otherwise the caster loses 20 faith |
| Explorer | ESFP | Entertainer | **Parable** - +15 faith and -40 CT to an enemy up to 3 tiles away |

Class stats lean with the type: Extraverts have more Bravery, Introverts more Patience, Feelers more Love, Explorers more Move and Jump. Paul's rule stands - if *his* faith is broken, the battle is lost.
