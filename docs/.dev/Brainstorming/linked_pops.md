# Linked Pops

## Concept

Two Pops can be **linked** when they represent the same demographic in different circumstances — the same stratum and often the same occupation, but separated by location or political affiliation. Linked Pops see each other as "us, but elsewhere." This is the foundation for future mechanics including Pop migration, cross-location cultural influence, and event propagation between connected communities.

The most common cases:
- **Same civilization, different locations**: surface engineers and orbital ring engineers under the Neran Confederacy
- **Different civilizations**: a native labor Pop and a colonizer labor Pop occupying the same world, subject to different governing entities — same economic position, different political circumstances

---

## Data Structure

Each Pop has a `linked_pop_ids` dict:

```python
linked_pop_ids: dict[pop_id, float]  # {other_pop_id: base_link_factor}
```

The base link factor is stored independently on each Pop, allowing **asymmetric links**: Pop A may have Pop B at 0.8 while Pop B has Pop A at 0.5. This naturally handles cases where identification is not mutual — a colonized Pop may not identify with its colonizer counterpart even if the colonizer Pop views them as "the same kind of people."

---

## Computed Link Factor

The base link factor is a seed. The **computed link factor** used in mechanics is derived as:

```
computed_link_factor = clamp(
    base_link_factor
    + (STRATUM_BONUS if same stratum)
    + (OCCUPATION_BONUS if same occupation)
    + COSINE_WEIGHT * cosine_similarity(a.beliefs + a.traits, b.beliefs + b.traits),
    0.0, 1.0
)
```

- **Base link factor**: authored at instantiation; captures contextual reasons not derivable from the formula (functional operational connection, shared historical origin, explicit political confederation)
- **Stratum bonus**: flat addition for shared class identity
- **Occupation bonus**: larger flat addition for the same occupation — the strongest structural basis for identification
- **Cosine similarity**: computed against a combined vector of both Domain beliefs and cultural traits, weighted to scale but not dominate

The cosine similarity component ensures cultural divergence reduces the link even when structural factors remain constant. A colonizer/native pair with the same stratum and occupation will still show a lower computed link factor if their belief and trait profiles have diverged significantly.

---

## Base Factor Drift

The base link factor is not static. It **lerps toward the cosine similarity** of the two Pops' current belief and trait profiles over time — the same pattern already used elsewhere in the simulation:

- Civilization `established_beliefs` and `established_culture_tags` lerp toward the aggregate of all Pop values; Pops lerp back toward the civilization's established values
- Base link factor lerps toward the cosine similarity of the two linked Pops

As Pops converge culturally, the base rises. As they diverge, it falls. The lerp rate can be tuned per link — a functional connection (transport workers sharing a route) might lerp slowly, resisting cultural drift; a purely categorical link between Pops with no direct contact would lerp quickly toward whatever the cosine similarity reflects.

---

## Link Breaking

Link dissolution uses logic parallel to the existing Pop splinter mechanic:

- **Pop splinter**: watches *internal* coherence — when a Pop accumulates too many strong contradictory traits, internal cosine similarity between trait clusters drops below threshold and the Pop splits
- **Link breaking**: watches *external* coherence — when the computed link factor between two Pops drops below threshold, the link dissolves and the entry is removed from `linked_pop_ids`

No special trigger event is needed. The base lerps downward as Pops diverge; when the computed link factor falls below the threshold, the link fades out naturally.

---

## Neran Confederacy — Initial Link Pairs

Links between **Neran Surface** and **Neran Orbital Ring** Pops, with initial base link factors:

| Surface Pop | Ring Pop | Base Link Factor | Notes |
|---|---|---|---|
| Common:transport | Common:transport | 0.90 | Operationally inseparable; work the same route |
| Warrior:officer | Warrior:officer | 0.80 | Same institution; rotation between postings |
| Scholar:scientist | Scholar:scientist | 0.75 | Shared professional identity; collaboration |
| Artisan:engineer | Artisan:engineer | 0.70 | Same firms and projects spanning both locations |
| Warrior:soldier | Warrior:soldier | 0.70 | Same class; garrison rotation |
| Warrior:guard | Warrior:guard | 0.65 | Same function in different environments |
| Artisan:technician | Artisan:technician | 0.65 | Same skills; different posting |
| Artisan:healer | Artisan:healer | 0.60 | Same medical system |
| Common:service | Common:service | 0.55 | Similar work; less direct contact |
| Common:labor | Common:labor | 0.55 | Same working class; less direct contact |

All Neran surface/ring links are initialized as symmetric. These are same-civilization links; the asymmetric link pattern is more relevant to the colonizer/native case, which we won't account for yet (but will eventually with the Pops on Sethis).
