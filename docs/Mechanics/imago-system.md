> [← CLAUDE.md](../../CLAUDE.md)

# Imago System

**Imagines** are the Demiurge's internalized conceptual frameworks. 16 trees (one per Domain), 7 nodes per tree (2 T1, 2 T2, 2 T3, 1 T4 apex). T4 nodes cannot be drawn from the Underreal (`is_drawable()`).

Each node carries `mechanics: dict[str, float]` mapping `domain:...` / `culture:...` tags to signed modifiers. When an Imago frames an influence action, `domain:...` mechanics become `DomainVector` objects.

**Demiurge state**: `Demiurge.unlocked_imagines: list[str]`. Warden's Compact starts with 4 Tier-1 Imagines (one per liege domain).

**Influence-action integration** (in `GameScreen._build_intent` / `_pick_domain_and_imago`): domain selection routes through the domain picker, then offers an Imago picker for the chosen tree. Selecting an Imago auto-derives both `domain_vectors` (from `domain:*` mechanics) and `culture_vectors` (from `culture:*` mechanics). All `domain_vectors`-carrying intents include an optional `imago_node_id`.

See also: [imago-revelation.md](imago-revelation.md)
