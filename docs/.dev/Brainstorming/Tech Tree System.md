# Technological Advancement System

## Design Philosophy

The technology system models civilizational capability without micromanaging the specifics of *how* that capability is exercised. The simulation does not track individual farms, factories, or weapons depots. It cares about three things:

1. **How able is the civilization to access materials and resources?**
2. **How able is the civilization to use those materials efficiently?**
3. **What can the civilization do with its surplus beyond basic needs?**

These three questions define the three branches of every tech tree.

---

## The Three-Branch Structure

Every tech tree is divided into three parallel branches, each answering one of the three questions above:

### Access Branch
Improves the raw supply of a resource category. Unlocking techs in this branch increases how much of the relevant resource a civilization can reach, extract, or produce — expanding territory under exploitation, opening new resource types, or enabling access to previously unreachable deposits.

**Mechanical effect**: increases resource supply, contributing positively to the wealth calculation.

### Efficiency Branch
Decreases how much of a resource the civilization's Pops and institutions need to consume to maintain their current scale. The same population can be sustained with less, freeing up more as surplus.

**Mechanical effect**: decreases resource demand, contributing positively to the wealth calculation from the other direction.

### Surplus Exploitation (Applications) Branch
Draws on the civilization's surplus — the gap between supply and demand — and directs it toward something beyond basic wealth maintenance. This is where tech trees generate *capabilities* rather than just resources: medicine extends lifespans, weapons enable conquest, logistics enable coordination at scale.

**Mechanical effect**: requires surplus to function; converts surplus into a specific civilizational capability or modifier.

---

## Wealth as a Derived Stat

Wealth represents **reliable access to resources**, not a stockpile. It is derived from an aggregate of the supply and demand of all the resources needed by the civilization's constituent Pops.

Where:
- **Supply** is determined by Access branch unlocks, resource availability at the civilization's locations, and population size doing the exploiting
- **Demand** is determined by the civilization's current scale, Pop type and size, and Efficiency branch unlocks

High wealth means the civilization reliably has more than it needs. Low wealth means supply and demand are uncomfortably close or inverted. A sudden loss of access to a critical resource is a **wealth shock** — more destabilizing than chronic low wealth, because it disrupts established expectations. This distinction should be modeled explicitly: chronic deficiency produces a stable-if-depressed baseline; sudden disruption produces a stability event.

---

## Surplus Allocation

What a civilization does with its surplus is not determined by the Demiurge directly. **Factions, Govs, and notable mortals** handle resource management and allocation internally. The Demiurge generally lacks the means to micromanage this — their influence is indirect, through Imāginēs, Proxiī directives, and occasional subtle actions.

Cultural traits, domain expression, and Faction pressures shape where surplus flows:
- A civilization with high Conflict expression and a dominant military Faction channels biological surplus toward soldier conditioning and ration hardening
- One with high Community expression and a priestly class channels it toward medicine and population health
- The same tech level and wealth stat can produce very different civilizational characters depending on surplus allocation

This means Imāginēs that promote specific values — tenacity, charity, erudition — indirectly influence surplus allocation without touching the tech tree directly.

---

## Tech Trees and Scale Levels

Each tech tree spans the full range of civilization scales:

| Scale | Description |
|---|---|
| Pre-sapient | Pre-civilizational; drives awakening |
| Nascent | First tools, first culture |
| Tribal | Organized social groups |
| City-State | Settled urban centers |
| Regional | Multi-city political units |
| Continental | Continent-spanning polities |
| Planetary | Full planetary civilization |
| Interplanetary | Multi-world within one system |
| Interstellar | Multi-system civilization |
| Intergalactic | Galaxy-spanning civilization |

Branches **do not need to be equally populated at every scale tier**. At low scales, the Applications branch may be thin or absent — a Nascent civilization is focused on survival, not surplus. Applications branches become prominent at higher scales as specialization and surplus accumulate.

At upper scale levels (Interstellar, Intergalactic), exotic and cosmic materials slot into the Access branch of existing trees rather than requiring separate trees.

---

## Non-Carbon Biology

The tech trees are **biology-neutral** and **environment-neutral by design**. For example, the specific resource targeted by each tech in the Biological Exploitation tree is determined by the dominant species' biology:

- A carbon-based civilization's Biological Exploitation tree defaults to organic resources
- A silicon-based civilization's tree defaults to silicon substrate resources
- An arsenic-based or sulfur-based civilization uses the appropriate default resource

The tree structure, branch logic, and scale progression are identical regardless of biology type. Only the resource label changes.

Multi-biology civilizations (containing Pops of different species with different biological bases) have **compound resource needs** based on the Pops of different species. Before the Xenobiology tech is unlocked (Interstellar tier, Biological Exploitation), a civilization cannot exploit non-dominant biological resource types for food — but a minority Pop whose biology requires a different resource still generates that need and is able to fulfill it if the civilization is able to put Pops toward its extraction (i.e., without needing a "separate tech" for the new resource type/usage). After Xenobiology, all biological resource types become accessible.

---

## Magic and Non-Scientific Universes

In scenarios where magic exists, parallel magical tech trees exist alongside or in place of scientific ones. Some universes are "like ours plus magic" and support both; others follow entirely different physical rules and may have only magical or elemental trees.

In non-scientific universes, the dominant resource types may be **classical elements** (fire, water, earth, air, aether) or analogous cosmological substances rather than material chemistry. The three-branch structure applies identically; only the resource categories and tech names change.

A **Multiversal Adaptation** tech sits at the Intergalactic capstone of relevant trees in appropriate scenarios, representing the ability to access and exploit resources from universes operating under fundamentally different rules.

Imāginēs gain **magical tradition affinities** in applicable scenarios, functioning analogously to their `techno:` promotion fields for scientific advancement.

---

## Imāgō Integration

Each Imāgō promotes advancement in specific tech tree branches through its `techno:` promotion field. The relationship between Imāgō tier and promoted tech scale is intentional:

- **Tier-1 Imāginēs** spread their tech promotions primarily across Pre-sapient, Nascent, and Tribal scale techs
- **Higher-tier Imāginēs** promote higher-scale technologies proportionally

A Tier-1 Imāgō promoting Tribal-era agriculture is essentially inert when preached to a Planetary civilization that mastered those techs millennia ago. This creates natural reasons to use different Imāginēs at different civilization stages.

**Effect intensity scales with Pop specialization**:
- Common Pops receiving an Imāgō produce ambient cultural pressure — slow, diffuse, but real. A civilization where many people hold beliefs adjacent to medicine will gradually produce more healers and value biological knowledge.
- Specialist Pops (scientists, shamans, medicine men, engineers) receiving the same Imāgō produce a salient, direct effect on the relevant research process. The tech specialist who has a revelation about their field *works* differently, not just believes differently.

**Non-obvious tech affinities** are a deliberate design feature. An Imāgō of communal solidarity plausibly promotes Logistics technology — not because solidarity is about logistics, but because communities that deeply value cooperation naturally develop better distribution systems. These indirect connections make Imāgō selection feel like uncovering something true about how belief and material development interact.

---

## Pre-Sapient Tier and the Path to Sapience

### Pre-Sapient Techs

Each tech tree has a pre-sapient tier representing cognitive and behavioral developments that precede organized civilization. These are not "technologies" in the conventional sense — they are the behavioral and social capabilities that make technology possible.

For **Biological Exploitation**:
- *Access*: Deliberate Foraging — actively seeking known food sources rather than opportunistic eating; building a mental map of where food exists
- *Efficiency*: Caching — storing food against future scarcity; the first relationship between present action and future need
- *Applications*: Medicinal Recognition — associating specific plants or materials with healing; proto-biological knowledge

Similar pre-sapient techs exist at the bottom of every tree: proto-language in Communication, fire discovery in Energy, deliberate tool selection in Minerals, path-following and territorial mapping in Transport.

### Critical Mass and the Sapience Threshold

Sapience is not unlocked by a single tech. It emerges when a species accumulates **critical mass across multiple pre-sapient tech trees simultaneously** — cooperative behavior (Biological/Logistics), fire (Energy), tool use (Minerals), and proto-language (Communication) together constitute something that can be called culture.

**Mechanically**: a species crosses into Nascent civilization when its pre-sapient tech development across relevant trees reaches a threshold. The specific combination matters more than any individual unlock. This models sapience as an emergent property of accumulated small developments rather than a discrete event — though the game surfaces it as a discrete event (a civilization spark) for readability.

### Demiurge Role in Pre-Sapient Development

Pre-sapient Pops are reachable by the Demiurge, but the effects are more diffuse than preaching to civilized Pops. Imāginēs with pre-sapient tech affinities can nudge a species toward cooperative behavior, proto-tool development, or early biological knowledge.

This creates a qualitatively distinct style of play: shepherding a species from pre-sapience toward civilization is slower and more indirect than managing existing civilizations, and the outcomes are less predictable — but successfully awakening a new sapient species is among the more powerful long-term investments available to a Demiurge.
