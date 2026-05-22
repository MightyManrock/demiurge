> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

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

### TravelNetwork refactor
> → plan: [travel-network-refactor.md](plans/travel-network-refactor.md)

Replace implicit `travel_features` string-intersection routing with explicit `TravelNetwork` objects. Same semantics, explicit topology — eliminates the BFS shortcut bug class.

---

### Warp gate world expansion
> → plan: [warp-gate-expansion.md](plans/warp-gate-expansion.md)

Add Warp Gate / Hyperlane `SignificantLocation` entries to the Neran and Sethis systems, extending the Vail travel route through real FTL infrastructure. Depends on TravelNetwork refactor.

---

