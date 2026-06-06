> [← CLAUDE.md](../../CLAUDE.md)

# Species Biology

## Life basis and solvent

Every `Species` carries two structured biochemistry fields:

```python
class Species(BaseModel):
    ...
    life_basis: LifeBasis = LifeBasis.CARBON
    solvent: Solvent = Solvent.WATER
```

These describe the fundamental biochemistry of the species — what organic compounds form their structural biology (`life_basis`) and what fluid medium their chemistry operates in (`solvent`).

### LifeBasis enum

| Value | Meaning |
|---|---|
| `carbon` | Carbon-based organic chemistry (default; all current human-analogue species) |
| `silicon` | Silicate-based structural chemistry |
| `methane` | Methane-derived structural chemistry |

### Solvent enum

| Value | Meaning |
|---|---|
| `water` | Liquid water (default) |
| `ammonia` | Liquid ammonia |
| `methane` | Liquid methane |
| `sulfuric_acid` | Liquid sulfuric acid |

Methane appears in both enums — a species can be methane-basis/ammonia-solvent, methane-basis/methane-solvent, or any other independent combination.

### Scenario assignments

| Species | Scenario | life_basis | solvent | Notes |
|---|---|---|---|---|
| Naran, Keth, Surathi, Veldan, Vehn, Ultir | Wardens Compact | carbon | water | |
| **Damtal** | Wardens Compact | **silicon** | **sulfuric_acid** | Kiddis is a volcanic sulfurous world |
| Teshari, Ardent, Threshfolk, Varun, Candorans | Ledger & Ash | carbon | water | |
| **Driftfolk** | Ledger & Ash | **methane** | **ammonia** | Rogue planet, geothermal subsurface ocean |

All other species default to carbon/water on load via schema defaults.

---

## Resource biochem tags

`Resource` and `CollectibleResource` both carry:

```python
biochem_tags: list[str] = []
```

Tags follow the `namespace:value` convention used throughout the codebase (`domain:fire`, `values:xenophilia`, etc.):

| Tag | Meaning |
|---|---|
| `basis:carbon` | Carbon-based organic nutrition |
| `basis:silicon` | Silicate-based organic nutrition |
| `basis:methane` | Methane-based organic nutrition |
| `solvent:water` | Potable water (consumable by water-solvent species) |
| `solvent:ammonia` | Liquid ammonia (consumable by ammonia-solvent species) |
| `solvent:sulfuric_acid` | Sulfuric acid (consumable by sulfuric-acid-solvent species) |
| `solvent:methane` | Liquid methane (consumable by methane-solvent species) |

An empty `biochem_tags` list means the resource is inert — not directly consumable by any species (raw ore, currency, unprocessed compounds, etc.).

### Example resource types

| resource_type | biochem_tags | Consumable by |
|---|---|---|
| `organic_flora` | `["basis:carbon", "solvent:water"]` | Carbon/water species only |
| `organic_fauna` | `["basis:carbon", "solvent:water"]` | Carbon/water species only |
| `potable_water` | `["solvent:water"]` | Any water-solvent species |
| `silicate_flora` | `["basis:silicon", "solvent:sulfuric_acid"]` | Silicon/sulfuric-acid species |
| `potable_sulfuric_acid` | `["solvent:sulfuric_acid"]` | Any sulfuric-acid-solvent species |
| `methane_flora` | `["basis:methane", "solvent:ammonia"]` | Methane/ammonia species |
| `potable_ammonia` | `["solvent:ammonia"]` | Any ammonia-solvent species |
| `inert_carbon` | `[]` | Nobody (raw material) |
| `credits` | `[]` | Nobody (currency) |

---

## Compatibility function

`species_can_consume(species, resource) -> bool` in `core/agent_core.py`:

```python
def species_can_consume(species: "Species", resource: Resource) -> bool:
    if not resource.biochem_tags:
        return False
    species_tags = {f"basis:{species.life_basis.value}", f"solvent:{species.solvent.value}"}
    return all(tag in species_tags for tag in resource.biochem_tags)
```

**Rule:** A resource is consumable if all of its `biochem_tags` are satisfied by the species' basis and solvent. Tags not declared on the resource are unconstrained — a resource tagged only `["solvent:water"]` matches any water-solvent species regardless of life basis.

This function is currently infrastructure only — no mortal behavior calls it yet. Future sustenance mechanics will use it to determine whether a collected resource satisfies the `sustenance` need.

---

## World implications

A species' biochemistry constrains its home world:

- **Silicon/sulfuric-acid** (Damtal, Kiddis): high surface temperature (~100–300°C), heavy volcanism, dense sulfurous atmosphere, no free water or oxygen, rich silicate geology.
- **Methane/ammonia** (Driftfolk, rogue planet): extremely cold, subsurface liquid-ammonia ocean warmed by geothermal heat, no sunlight, chemosynthetic energy source.
- **Carbon/water** (most species): Earth-analogue conditions.

Interspecies contact across biochemistry boundaries requires environmental protection. This is the canonical reason the Naran Compact colonized Sethis (carbon/water, Surathi-inhabited) before Kiddis, despite Kiddis being closer.
