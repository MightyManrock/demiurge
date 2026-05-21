> Plans index: [`docs/plans/PLANS.md`](plans/PLANS.md)
> Items covered by a plan are tagged `→ plan: filename.md`

---

### CLAUDE.md Simplification
> → plan: [claude-md-simplification.md](plans/claude-md-simplification.md)

CLAUDE.md is currently way too bloated—it is well past time to trim it.

My idea is:

* The codebase structure stays, with simple descriptions, because that is very important for you to know where to look for what.
* Sections on individual mechanics are simplified immensely. Other than a short introduction, these will mostly feature a reference to an `.md` file in `./docs/Mechanics/`.
* Obviously, then, we will create such a folder and populate it with these files. What we add there will contain much more detail, describing exactly how the code works and why.
* Claude Code can then have breadcrumbs directly to only the details that it needs for any particular task.