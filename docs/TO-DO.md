> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

---

## Tick and time standardization with RTwP
> → plan: [rtwp-action-system.md](plans/rtwp-action-system.md)

So far, one tick has been half a universe age unit. How long is a universe age unit? I don't know, maybe a year. So a tick is six months... maybe.

After adding the travel system, it has become clear that we need to track time on a much smaller scale than 6-month periods. But that naturally brings up a concern: if we want a mortal's travel time to make sense in the setting, if we changed nothing else but say "ticks are days now," we would have a massive problem justifying the sorts of belief and culture shifts that can take place. If, however, we reduce the latter proportionally, then we're spending every turn doing things with extremely little ROI.

I have a proposal to resolve this: simply, ticks are not turns. When you act, it can take longer than a tick to even "fire off," much less resolve, and the passing of ticks is not as crucial. This puts us in the territory of real-time with pause.

For more details, read the brainstorming document [[rtwp_action_system|here]]. This will be a **massive** refactor, with a lot of moving parts, and it will fundamentally break the game until we get it right, so any work we plan to do **must** be done in a fork.

---

### Human-readable Documentation
> → plan: [human-readable-docs.md](plans/human-readable-docs.md)

Especially since I have started sharing my game with friends, it is **very** clear that the only guide to how to play this game exists in my head. And now that my docs are moving with the repo, that is one area to address this.

I would like to start putting together a source about how the game works and how to go about playing it. This will include an introduction/tutorial as well as "non-codey" descriptions of the game's systems. Players who read this should come away with a good idea of what they can expect to see and how to interact with it.

In the future, we will fold a lot of this information into a redesign of the Divine Wisdom tab in-game. Ideally, that will become a definitive encyclopedia on Demiurge, with a navigable interface of its own—and possibly a search function, if possible.

---

### Pick the next big feature
> → plan: [next-big-feature.md](plans/next-big-feature.md)

Choose the next major system: Agent expansion, Factions, Governments, or resources↔tech-progress. Note that `Faction` is the data-model prerequisite for expanding the agent phase, so Agent-expansion and Factions are largely the same fork.

---

