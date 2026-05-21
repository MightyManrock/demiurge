> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

---

### ⭐ TOP PRIORITY — Deprecate `core/core.db` auto-bootstrapping on launch

Every `main.py` launch re-bootstraps `core/core.db` from the hardcoded Python registry data. This re-write produces a git diff on the DB file on *every* game launch, which plays havoc with the repo.

The source data (domain / culture / imago / action registries) is no longer constantly changing, and there are now other means of accessing and editing core DB data (imago editor, rebuild tool, scenario builder, `--inject`). The auto-bootstrap is therefore no longer needed.

Goal: stop the unconditional rewrite. `core/core.db` should be treated as authoritative once it exists — only build it when genuinely absent (true first run), never overwrite it on a normal launch. Explicit rebuilds via `tools/rebuild_databases.py` remain the supported way to regenerate registry data.

---

### ~~CLAUDE.md Simplification~~ ✓
> → plan: [claude-md-simplification.md](plans/claude-md-simplification.md) — **complete**

CLAUDE.md is currently way too bloated—it is well past time to trim it.

My idea is:

* The codebase structure stays, with simple descriptions, because that is very important for you to know where to look for what.
* Sections on individual mechanics are simplified immensely. Other than a short introduction, these will mostly feature a reference to an `.md` file in `./docs/Mechanics/`.
* Obviously, then, we will create such a folder and populate it with these files. What we add there will contain much more detail, describing exactly how the code works and why.
* Claude Code can then have breadcrumbs directly to only the details that it needs for any particular task.

---

### Agent notification system

`ProxiusGoal.petition_pending` is already a clear boolean flag — a natural trigger point for a notification system that surfaces agent state to the player mid-run, without requiring an explicit audit. Flagged as a future priority when the Proxius agent foundation was implemented.

---

### Rework action success/failure math

The roll that determines whether an action succeeds is due for adjustment. Consider folding `Framing` into the success likelihood.

---

### Re-cost Manifest Omen

Manifest Omen is very powerful, especially with skilled `Framing` use — its Essence cost may need to go up. Decide *after* the action success/failure rework: if Framing gates success, a mismatched omen already self-penalizes.

---

### Pick the next big feature

Choose the next major system: Agent expansion, Factions, Governments, or resources↔tech-progress. Note that `Faction` is the data-model prerequisite for expanding the agent phase, so Agent-expansion and Factions are largely the same fork.