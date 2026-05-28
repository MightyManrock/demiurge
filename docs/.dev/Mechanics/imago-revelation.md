> [← CLAUDE.md](../../CLAUDE.md)

# Imago Revelation System

Three actions:
- **`explore_beliefs`** (`SELF_REFINEMENT`, `can_persist`) — accumulates Revelation in a targeted Domain pool each tick.
- **`reveal_imago`** (`SELF_REFINEMENT`) — spends accumulated Revelation to add a node to `unlocked_imagines`.
- **`commission_inquiry`** (`PROXIUS_DIRECTION`) — directs a Proxius to conduct slower Domain research.

Per-domain Revelation accumulates in `Demiurge.revelation_pools`; cumulative reveals in `Demiurge.revealed_imagines` drive a small cost malus. Rate/cost formulas live in `tick_logic.py` (`_compute_universal_expression`, `_revelation_adjusted_cost`, `_compute_revelation_cap`). Explore Beliefs auto-stops when its pool ≥ the tree's cap.

Mutation types: `REVELATION_GAINED`, `IMAGO_REVEALED`.

UI: `ImagoRevealModal` (tree view with costs/pool header) and `ImagoRevealDetailModal` (confirm + cost) in `ui/modals.py`. `eligible-reveal` CSS class highlights domains with affordable Imagines in the domain picker.

See also: [imago-system.md](imago-system.md)
