> Plan files live in `docs/.dev/plans/` — one `.md` per plan
> Statuses: `active` · `blocked` · `parked` · `complete`
> TO-PLAN: [`docs/.dev/TO-PLAN.md`](../TO-PLAN.md)

## Heartbeat cron

A recurring job runs every 4 hours to check `TO-PLAN.md` for unplanned items and update this index. Keeping this recurring should be handled by ClaudeClaw.

```
Read /root/demiurge/docs/.dev/TO-PLAN.md and /root/demiurge/docs/.dev/plans/PLANS.md. For each item in TO-PLAN.md that is not already tagged with a plan reference, decide whether it should become a new plan file or be folded into an existing one. If a new plan is warranted, create a file in /root/demiurge/docs/.dev/plans/ following the format of existing plan files (status/TO-PLAN ref/last updated header, goal, approach, files affected, notes). Update PLANS.md to add the new entry to the index table. Add the plan tag to the TO-PLAN item. If an existing plan already covers the item, just add the tag. For any TO-PLAN item already marked as fully implemented (strikethrough or flagged complete), remove it from TO-PLAN.md and set the corresponding plan's status to complete in both its own file and the PLANS.md index table. Commit and then contact me over Telegram with a summary of changes. As long as you are only working in this PLANS framework, you can push any changes to origin main without my permission.
```

---

| Plan | Status | Summary |
|------|--------|---------|
| [next-big-feature.md](next-big-feature.md) | `active` | Decision: choose next major system (Factions/Agents, Governments, or resources) |
| [human-readable-docs.md](human-readable-docs.md) | `active` | Player-facing guide and system overviews; future Divine Wisdom tab |
| [actions-redesign-master-plan.md](actions-redesign-master-plan.md) | `active` | Systematic mechanic + UI + DB-prep pass over every action |
| [belief-propagation.md](belief-propagation.md) | `active` | Extract belief/culture propagation to logic/belief_propagation.py + add strides and stratum weighting |
| [narrative-formatters.md](narrative-formatters.md) | `parked` | Extract all narrative string-building from tick_logic + civilian_agent_logic into logic/narrative_formatters.py |
| [pop-splinter-redesign.md](pop-splinter-redesign.md) | `complete` | Probabilistic stride-gated splinter check, divergence-scaled fraction, post-split belief nudge, civ-scale threshold modifier |
