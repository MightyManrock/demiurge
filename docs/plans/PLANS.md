> Plan files live in `docs/plans/` — one `.md` per plan
> Statuses: `active` · `blocked` · `parked` · `complete`
> TO-DO: [`docs/TO-DO.md`](../TO-DO.md)

## Heartbeat cron

A recurring job runs every 4 hours to check `TO-DO.md` for unplanned items and update this index. Keeping this recurring should be handled by ClaudeClaw.

```
Read /root/demiurge/docs/TO-DO.md and /root/demiurge/docs/plans/PLANS.md. For each item in TO-DO.md that is not already tagged with a plan reference, decide whether it should become a new plan file or be folded into an existing one. If a new plan is warranted, create a file in /root/demiurge/docs/plans/ following the format of claude-md-simplification.md (status/TO-DO ref/last updated header, goal, approach, files affected, notes). Update PLANS.md to add the new entry to the index table. Add the plan tag to the TO-DO item. If an existing plan already covers the item, just add the tag. For any TO-DO item already marked as fully implemented (strikethrough or flagged complete), remove it from TO-DO.md and set the corresponding plan's status to complete in both its own file and the PLANS.md index table. Commit and then contact me over Telegram with a summary of changes. As long as you are only working in this PLANS framework, you can push any changes to origin main without my permission.
```

---

| Plan | Status | Summary |
|------|--------|---------|
| [claude-md-simplification.md](claude-md-simplification.md) | `complete` | Trim CLAUDE.md; extract mechanics into `docs/Mechanics/` |
| [deprecate-core-db-bootstrap.md](deprecate-core-db-bootstrap.md) | `complete` | Stop `core/core.db` unconditional rewrite on every launch |
| [action-success-rework.md](action-success-rework.md) | `complete` | Rework action success/failure math; fold Framing into success likelihood |
| [manifest-omen-recost.md](manifest-omen-recost.md) | `active` | Re-cost Manifest Omen — independent of action success rework |
| [next-big-feature.md](next-big-feature.md) | `active` | Decision: choose next major system (Factions/Agents, Governments, or resources) |
