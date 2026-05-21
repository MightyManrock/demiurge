> Plan files live in `docs/plans/` — one `.md` per plan
> Statuses: `active` · `blocked` · `parked` · `complete`
> TO-DO: [`docs/TO-DO.md`](../TO-DO.md)

## Heartbeat cron

A recurring job runs every 4 hours to check `TO-DO.md` for unplanned items and update this index. To restore it after a session restart, run the following prompt via CronCreate (`17 */4 * * *`, durable, recurring):

```
Read /root/demiurge/docs/TO-DO.md and /root/demiurge/docs/plans/PLANS.md. For each item in TO-DO.md that is not already tagged with a plan reference, decide whether it should become a new plan file or be folded into an existing one. If a new plan is warranted, create a file in /root/demiurge/docs/plans/ following the format of claude-md-simplification.md (status/TO-DO ref/last updated header, goal, approach, files affected, notes). Update PLANS.md to add the new entry to the index table. Add the plan tag to the TO-DO item. If an existing plan already covers the item, just add the tag. For any TO-DO item already marked as fully implemented (strikethrough or flagged complete), remove it from TO-DO.md and set the corresponding plan's status to complete in both its own file and the PLANS.md index table. Commit and push any changes to origin main.
```

---

| Plan | Status | Summary |
|------|--------|---------|
| [claude-md-simplification.md](claude-md-simplification.md) | `complete` | Trim CLAUDE.md; extract mechanics into `docs/Mechanics/` |
