# The Road to Jerusalem - Game Plan

*The plan for getting this game to as many players as possible. Set September 2026; revisit it whenever an episode ships.*

## The end goal

**A free, single-player tactics RPG that walks through the New Testament - from the Gospels to Revelation - played in the browser on any device - phone, tablet or computer - and released in short episodes that a community of players and churches follows and shares.**

| Decision | Choice | Why it matters |
|---|---|---|
| Audience | Tactics/RPG fans, Christian players and churches, casual/mobile players | The tactics are the draw; the faith setting is the hook; phones are where most of them are |
| Platform | Web browser first (itch.io), playable on phones and tablets | A link anyone can open - no install, works on school and church computers |
| Price | Free | Removes every barrier to playing and sharing |
| Scope | Ongoing / episodic | Small releases fit a few hours a week, and each one is a reason to come back and share |
| Multiplayer | None - single-player | No servers, nothing to pay for or maintain |
| Story | The New Testament, Gospels to Revelation | Biblical events as the backbone, told visual-novel style between battles, with an invented protagonist and battles |
| Pace | A few hours a week | About one episode every 6-8 weeks |
| Success | Number of players, spiritual impact, community | Each episode should be easy to share, point players to Scripture, and give followers something to come back for |

## Principles

1. **Reach beats polish.** Every choice should make the game easier to open, play and share. A link that works on a phone matters more than a new feature.
2. **Finish small things.** One short, complete episode beats a big unfinished one. Keep each episode to 1-2 stages, 20-40 minutes.
3. **Point to Scripture.** Every episode ends by sending players to the passage it's drawn from - that serves the impact goal and gives churches a reason to share it.
4. **Stay on the current engine.** pygame + pygbag already runs in the browser. A Godot rewrite would cost months of episodes; reconsider only if app-store releases become essential. The same goes for story: the visual-novel scenes are built in pygame (`scripts/story.py`) rather than a separate engine like Ren'Py, which can't run inside the pygbag build.

## Story roadmap

Five stories to start, in Bible order, from the Gospels to Revelation. Each is one world map node: a visual-novel scene, a battle, and a closing scene that ends on the passage and discussion questions.

**The thread:** the hero (the player's own character) begins as a young student of Saul the Pharisee and walks, over sixty years, from Saul's side to Christ's. They are sent to spy on Jesus, stand guard at the empty tomb and are paid to keep quiet about it, then ride to Damascus to arrest believers. On that road the hero is converted alongside Saul, becomes a missionary, and finally tells the truth about the tomb on Patmos, beside the aged John. This matches the playable demo, where the hero already rides in Saul's band, and keeps Paul as the hero's advisor.

| # | Story | Passage | The hero's part | Battle | Status |
|---|---|---|---|---|---|
| 1 | Fishers of Men | Luke 5:1-26 | Saul sends the hero to Galilee to watch the new rabbi; the miraculous catch, the paralytic through the roof | A short tutorial skirmish among the temple guard recruits (new stage, teaches the controls) | Story written; battle to build |
| 2 | The Sealed Tomb | Matthew 26:47-56; 27:62-28:15 | On the temple guard at Gethsemane (Malchus's ear), then at the sealed tomb; offered silver to say "his disciples stole him" | The arrest in the garden - disciples scatter toward the exits (reuses the Damascus escape mechanics); ends when Jesus says "put your sword away" | Story written; battle to build (can reuse the Jerusalem map) |
| 3 | The Road to Damascus | Acts 7:54-8:3; 9:1-19 | Stephen's stoning, riding with Saul, the light from heaven; Ananias, and the hero's baptism | Saul's band hunts the disciples (exists) | **Playable** - story and Scripture ending added |
| 4 | The Jailer's Household | Acts 16:16-34 | Stays outside the prison for Paul and Silas; the earthquake; the jailer (who mirrors the hero's own past) believes | Philippi (stage exists) | Story written; balance the stage |
| 5 | The Revelation on Patmos | Revelation 1:9-19; 12:11; 21:1-5 | Old and exiled with John; the vision; finally gives testimony about the tomb | War in heaven in John's vision, won by faith and testimony (Preach/conversion) rather than strikes (new stage + win condition) | Story written; battle to build |

**Release order:** 3 first (it's the current demo, now with its story and Scripture ending), then 1, 2, 4, 5, one every 6-8 weeks. Stories 1, 2 and 5 are already playable as story-only nodes on the world map; their battles are the main work left.

**Later stories:** the remaining Acts stages slot in between 4 and 5 as more episodes - Paul Among the Apostles (Acts 9:20-30, Jerusalem), The First Gentile Church (Acts 11-13, Antioch), A Fractious Church (Acts 18, Corinth), Riot of the Silversmiths (Acts 19, Ephesus), Nero's Persecution (Acts 28 and 2 Timothy, Rome). Each stage exists and needs only its scenes and balance. Pentecost (Acts 2) is a strong candidate for its own story too.

**Writing a story:** add rows to `data/story.csv` as `<node>_intro` and `<node>_outro`. Each row is a `bg`, `show`, `hide`, `say`, `narrate`, `title`, `scripture`, `reflect` or `choice` command, and the format is documented at the top of `scripts/story.py`. Add the chapter to `data/story_chapters.csv`, and a world map node of type `story` until its battle exists, then `stage`. `python -m pytest scripts/test_story.py` checks the script, including that every story ends on its `reflect` card.

**Open decisions:**
- Jesus and angels appear as a figure of light, not a face. Keep this, or commission art?
- Scripture is quoted from the World English Bible (public domain). Check each quote against the WEB text before release.
- Art: the painted portraits are 200x100 crops, and named people without one (Cleopas, Ananias, Lydia, the jailer) borrow a convert's face. Patmos has no island on the map art yet.
- Voices: the story's lines will play voice clips the same way battle dialogue does, once `tools/generate_voices.py` is pointed at `data/story.csv`.

## Critical issues (fix before growing the audience)

1. ~~**Saves in the browser.**~~ **Done** - the web build keeps the player's profile in the browser's localStorage, so Continue survives a reload.
2. ~~**Phones and touch.**~~ **Done** - on-screen Back, Zoom -/+ and drag-to-pan; tapping the name box opens the phone's text prompt; phones held upright are asked to turn sideways. Tested touch-only in a phone-sized browser. *Still to improve:* text is small on a phone screen - a larger UI scale for small screens is the next mobile step.
3. ~~**One main branch.**~~ **Done** - `main` now holds the current game (fast-forwarded from `deviate-from-Jesus's-line-of-story`). Work on `main` from here.

## Next steps, in order

1. ~~Fix the three critical issues above.~~ Done.
2. ~~Episode 1 ending: "Read Acts 9:1-19" plus 2-3 discussion questions on the end screen.~~ **Done** - the Damascus closing scene ends on a Read Acts 9:1-19 card with three questions; every story now does the same.
3. Polish the itch.io page - screenshots, a short trailer GIF, tags (tactics, RPG, Christian, Bible), embed size 1280x720 - and set it to **Public**.
4. Playtest with one real youth group; fix what confuses them.
5. Start Story 1's tutorial battle (see the story roadmap).

## Growing the community

- Post a short **devlog on itch.io** with every episode (what's new, a screenshot, what's next).
- Write a **one-page youth-group guide** per episode: the passage, a summary, discussion questions, a link to play. Put it on the itch.io page.
- Later: a simple Discord or email list for followers, once there are players asking for one.
- Track itch.io's views/plays per episode to see what grows reach.

## Release checklist (every episode)

- [ ] All tests pass (`python -m pytest scripts`)
- [ ] Play it through once in the browser on a computer **and on a phone**
- [ ] Scripture reference and discussion questions on the ending screen
- [ ] `python tools/build_web.py`, then `butler push build/web azurestudio808/road-to-jerusalem:html5`
- [ ] Devlog post on itch.io
- [ ] Commit and push to GitHub
