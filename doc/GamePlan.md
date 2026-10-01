# The Road to Jerusalem - Game Plan

*The plan for getting this game to as many players as possible. Set September 2026; revisit it whenever an episode ships.*

## The end goal

**A free, single-player tactics RPG inspired by the Book of Acts, played in the browser on any device - phone, tablet or computer - and released in short episodes that a community of players and churches follows and shares.**

| Decision | Choice | Why it matters |
|---|---|---|
| Audience | Tactics/RPG fans, Christian players and churches, casual/mobile players | The tactics are the draw; the faith setting is the hook; phones are where most of them are |
| Platform | Web browser first (itch.io), playable on phones and tablets | A link anyone can open - no install, works on school and church computers |
| Price | Free | Removes every barrier to playing and sharing |
| Scope | Ongoing / episodic | Small releases fit a few hours a week, and each one is a reason to come back and share |
| Multiplayer | None - single-player | No servers, nothing to pay for or maintain |
| Story | Inspired by Acts | Biblical events as the backbone, with invented characters (the protagonist) and battles |
| Pace | A few hours a week | About one episode every 6-8 weeks |
| Success | Number of players, spiritual impact, community | Each episode should be easy to share, point players to Scripture, and give followers something to come back for |

## Principles

1. **Reach beats polish.** Every choice should make the game easier to open, play and share. A link that works on a phone matters more than a new feature.
2. **Finish small things.** One short, complete episode beats a big unfinished one. Keep each episode to 1-2 stages, 20-40 minutes.
3. **Point to Scripture.** Every episode ends by sending players to the passage it's drawn from - that serves the impact goal and gives churches a reason to share it.
4. **Stay on the current engine.** pygame + pygbag already runs in the browser. A Godot rewrite would cost months of episodes; reconsider only if app-store releases become essential.

## Episode roadmap

| Episode | Passage | Content | Status |
|---|---|---|---|
| 1. The Road to Damascus | Acts 9:1-19 | Saul's band hunts the disciples; the light from heaven | Playable demo |
| 2. Paul Among the Apostles | Acts 9:20-30 | Damascus to Jerusalem - the church fears Paul; Barnabas vouches for him | Stage exists (Jerusalem) |
| 3. The First Gentile Church | Acts 11:19-26, 13:1-3 | Antioch - Paul and Barnabas are sent out | Stage exists (Antioch) |
| 4. The Jailer's Household | Acts 16 | Philippi - prison, earthquake, the jailer converts | Stage exists |
| 5. A Fractious Church | Acts 18 | Corinth - before Gallio | Stage exists |
| 6. Riot of the Silversmiths | Acts 19 | Ephesus | Stage exists |
| 7. Nero's Persecution | Acts 28, 2 Timothy | Rome | Stage exists |

Most stages are already built - each episode is mostly story, dialogue, balance (see `doc/Road_to_Jerusalem_Balance_Sheet.xlsx`) and an ending that points to its passage.

## Critical issues (fix before growing the audience)

1. ~~**Saves in the browser.**~~ **Done** - the web build keeps the player's profile in the browser's localStorage, so Continue survives a reload.
2. ~~**Phones and touch.**~~ **Done** - on-screen Back, Zoom -/+ and drag-to-pan; tapping the name box opens the phone's text prompt; phones held upright are asked to turn sideways. Tested touch-only in a phone-sized browser. *Still to improve:* text is small on a phone screen - a larger UI scale for small screens is the next mobile step.
3. ~~**One main branch.**~~ **Done** - `main` now holds the current game (fast-forwarded from `deviate-from-Jesus's-line-of-story`). Work on `main` from here.

## Next steps, in order

1. ~~Fix the three critical issues above.~~ Done.
2. Episode 1 ending: "Read Acts 9:1-19" plus 2-3 discussion questions on the end screen.
3. Polish the itch.io page - screenshots, a short trailer GIF, tags (tactics, RPG, Christian, Bible), embed size 1280x720 - and set it to **Public**.
4. Playtest with one real youth group; fix what confuses them.
5. Start Episode 2.

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
