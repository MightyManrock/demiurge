> [← CLAUDE.md](../../CLAUDE.md)

# Scry Action

Four scope levels (`ScryScope.WORLD/SYSTEM/GALAXY/UNIVERSE`), each with progressively higher subtle-influence footprint and lower per-entity discovery probability. WORLD/SYSTEM scopes require a target; GALAXY/UNIVERSE do not.

Discovery is probabilistic, gated by **depth delta** (how far the candidate is below the scry's anchor), **container prerequisite** (the entity's spatial container must already be in the Window), **proximity bonus**, and **domain-affinity bonus** with `Demiurge.affiliated_domains`. Civilizations use scale-aware anchor depth (`_CIV_SCALE_DEPTH`). Discovery cascades within a single scry: a system found mid-pass unlocks its worlds in the same pass.

Implementation: `_run_scry_resolver` in `tick_logic.py`.
