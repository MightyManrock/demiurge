> [← CLAUDE.md](../../CLAUDE.md)

# Domain System

16 canonical tags defined in `utilities/domain_registry.py`: order, silence, truth, conflict, change, fire, water, void, growth, decay, memory, sacrifice, light, mastery, secrecy, community.

**Pairwise similarity** is stored in `core/core.db` and seeded from `_SIMILARITY_DATA` in the registry source. Used by `luminary_approval()`, alignment computation, pop receptivity, and the scry resolver.

**`luminary_approval()`** applies internal-contradiction bypass (a Luminary holding opposing domains ignores the negative similarity between them) and a realpolitik damping factor mapped from personality.harshness.

**`Demiurge.affiliated_domains`** represents the Demiurge's conceptual focus; the Demiurge claims Essence only from these Domains. Its length is capped by **`Demiurge.max_affiliated_domains`** (default 3 — a future Stronghold building slot can raise it). When a scenario `.db` leaves `affiliated_domains` empty, `scenario_loader` derives it as the top-`max_affiliated_domains` domains by aggregate liege-Luminary affinity (alphabetical tiebreak). Used by Essence claiming, alignment computation, scry domain-affinity bonuses, and the `eligible-reveal` highlight in the domain picker. Both shipped scenarios author 3 affiliations explicitly while keeping a 4th Tier-1 Imago unlocked in a Pantheon-covered Domain they don't claim Essence from.
