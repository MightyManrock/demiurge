# Mortal Skill System

## Overview

The mortal skill system governs what individual notable mortals can **do** within the simulation. Skills unlock specific action categories and measure a mortal's likelihood of success when using them. Skills are personal to the mortal — independent of their Pop membership, though Pop occupation shapes how certain skills express in practice.

The initial implementation will be tested with **`skill:trade` on Durenn Vail**.

---

## Two-Tier Structure

Each skill has two independent properties:

**1. Presence (binary):** Does the mortal have this skill at all? Presence unlocks the associated actions. A mortal without a skill cannot attempt those actions regardless of circumstances. (The skill simply being in the mortal's list of skills, whatever its value, is enough for this to be true.)

**2. Rating (float, 0.0–1.0):** How capable is the mortal? Rating affects the success probability of skill-gated actions and feeds into the Agent's decision-making about whether to attempt them.

---

## Decision Model: When to Use a Skill

Possessing a skill does not guarantee the mortal will use it. The Agent evaluates several factors before choosing a skill-gated action:

### Estimated success chance
The mortal estimates whether the action is likely to succeed, based on:
- **Base skill rating** — their underlying capability
- **Circumstances modifier** — effective skill = base rating × circumstance. Environmental factors reduce (or occasionally enhance) effective skill regardless of the mortal's actual capability. Examples: hostile trading territory, physical injury, lack of required tools, being observed while attempting a covert action.

### Need and desire urgency as overrides
- If **estimated success is high**, the mortal proceeds normally.
- If **estimated success is low**, the mortal weighs the attempt against the urgency of the need or desire it would fulfill.
- A **pressing need** raises willingness to attempt low-probability actions.
- An **urgent need** overrides hesitation almost entirely — the mortal attempts regardless of odds.
- **Desires** (once implemented) follow the same pattern but at a slightly higher threshold, reflecting that desires are wants rather than requirements.

### Trait modulation of the attempt threshold
Cultural and personal traits shift the minimum estimated success chance the mortal requires before attempting:

| Trait | Effect |
|---|---|
| `values:patience` | Raises threshold — prefers to wait for better circumstances |
| `values:pragmatism` | Raises threshold — avoids low-probability efforts in favor of more reliable paths |
| `values:tenacity` | Lowers threshold — pushes through even bad odds; keeps retrying |
| `values:prowess` | Lowers threshold — sees difficult attempts as worth making regardless of outcome |
| `values:honor` (positive) | Increases drive to fulfil Directives — treats assigned obligations as binding commitments |
| `values:honor` (negative) | Reduces motivation to fulfil Directives — shamelessness means obligations carry less weight |
| `values:adaptability` (positive) | When difficulty is encountered, seeks roundabout or alternative solutions rather than retrying the same approach |
| `values:adaptability` (negative) | When difficulty is encountered, retries the same approach until it works — inflexibility, not necessarily failure |

**Tenacity vs. prowess distinction:** Both lower the attempt threshold, but for different reasons. A tenacious mortal keeps retrying the same action. A prowess-valuing mortal engages with the challenge itself as worthwhile and may still accept failure while seeking another attempt — a subtly different behavioral pattern.

**Tenacity vs. adaptability distinction:** Tenacity determines *whether* a mortal keeps trying when facing difficulty. Adaptability determines *how* they try again. High tenacity with low adaptability produces a mortal who persists at the same failed approach indefinitely. High adaptability with low tenacity finds a clever workaround but abandons the goal if that also fails. High both produces a mortal who is both persistent and creative under pressure.

---

## Canonical Skill List

### Material and Occupational

**`skill:trade`**
Unlocks resource collection, conversion, and sale; asset management; trade route establishment; negotiation. For mortals belonging to Trader-stratum Pops, reflects occupational depth. Durenn Vail's primary skill.

**`skill:craft`**
Unlocks fabrication, repair, construction, and creation of physical objects. Covers artisan production across craftsmanship, visual arts, and culinary dimensions. Reflects occupational depth for Artisan-stratum Pops.

**`skill:labor`**
Unlocks actions tied to the occupation of the mortal's parent Pop. The skill is generic; the Pop's occupation tag shapes what it unlocks in practice. A Common:food_producer mortal's labor skill is agricultural; a Common:service mortal's is service work. Directly relevant to PopAgent behavior in small or isolated groups (e.g., the Keth) where individual mortals materially affect civilizational output.

**`skill:navigation`**
Unlocks travel efficiency bonuses and the ability to operate vehicles and vessels requiring an asset. Also reflects occupational depth for Common:transport Pops — a mortal with high navigation in that Pop is a capable pilot, not merely a passenger.

**`skill:engineering`**
Unlocks large-scale technical construction and maintenance actions. Reflects occupational depth for Artisan:engineer Pops.

**`skill:medicine`**
Unlocks healing and health management actions. Reflects occupational depth for Artisan:healer Pops.

**`skill:combat`**
Unlocks fighting actions, military operations, and performative martial arts. Covers both actual conflict (heavily weighted) and competitive combat arts (lighter weighting). Reflects occupational depth for Warrior-stratum Pops.

### Social — Pop-Facing

These skills target Pops rather than individuals, each affecting a different layer of Pop culture and belief.

**`skill:rhetoric`**
Primarily targets Pop `values:` traits — promotes or shifts what a Pop prizes. The active, argumentative form of cultural influence.

**`skill:ritual`**
Primarily targets Domain beliefs and `religion:` traits — promotes or shifts what a Pop believes about the cosmos and the divine. Distinct from rhetoric in targeting the metaphysical layer rather than the social one.

**`skill:performance`**
Influences Pop `values:` traits as a side effect of meeting leisure needs. Indirect — the performance fulfills the leisure desire first; cultural influence is secondary. Does not directly target belief.

### Social — Faction-Facing

**`skill:leadership`**
Targets the **actions** of Factions — directs groups of mortals and Pops toward specific goals. A mortal does not lead a Pop directly; they lead a Faction that then directs Pops. Kael Ash's primary skill, which makes him notable despite belonging to a Common:producer Pop.

**`skill:diplomacy`**
Targets relations between Factions, potentially across civilizational lines. Formal negotiation, treaty-making, and political representation at the inter-group level.

### Covert

**`skill:stealth`**
Unlocks covert movement and information-gathering. Also unlocks a distinctive *cultural* use: shielding a Pop from civilization conformity pressure. A mortal using stealth can protect a divergent or splinter Pop from being pulled back toward the dominant culture before it has differentiated sufficiently.

**Faction alignment as passive conformity resistance:** A Pop aligned with a divergent Faction receives a built-in resistance to conformity and reabsorption by virtue of that alignment — the Faction provides identity that resists the gravitational pull of the majority. Active `skill:stealth` from a mortal and passive Faction identity resistance can stack, giving revolutionary movements like Orryn Vel's a compounding defensive capability.

### Knowledge

**`skill:scholarship`**
Unlocks information-gathering, analysis, and knowledge synthesis actions. Functions partly as an *input* skill — a mortal with high scholarship who then applies rhetoric, leadership, or diplomacy has better-grounded judgment and improved effectiveness. Also directly unlocks investigation and interpretation actions, and will eventually contribute to technology advancement.

---

## Practice Traits and Skill Correspondence

`practice:` traits on Pops describe cultural availability and quality. `skill:` traits on mortals describe personal capability. A high `practice:music` Pop has rich musical culture; a mortal with `skill:performance` can actively produce that culture rather than merely participate in it.

| Practice Trait(s) | Corresponding Skill |
|---|---|
| `practice:music`, `practice:dance`, `practice:theatre` | `skill:performance` |
| `practice:craftsmanship`, `practice:visual_arts`, `practice:culinary_arts` | `skill:craft` |
| `practice:combat_arts` | `skill:combat` |
| `practice:athletics` | Component of `skill:combat` and `skill:labor` (physical conditioning) |
| `practice:literature`, `practice:poetry` | `skill:rhetoric` |
| `practice:ritual` | `skill:ritual` |
| `practice:revelry` | No corresponding skill — revelry is participatory, not a personal capability |

---

## Initial Implementation: `skill:trade` on Durenn Vail

`skill:trade` is the first skill to be implemented, using Durenn Vail as the test mortal.

**What it unlocks:**
- Collect resource (at a resource node in the mortal's current location)
- Convert resource (exchange one resource type for another, e.g., unobtanium → credits)
- Sell resource (spend resources in exchange for wealth or need satisfaction)
- Eventually: establish trade relationships, negotiate prices, manage assets

**Current behavior to be replaced:** Durenn Vail's resource collection and selling actions are currently arbitrary — he does them because he is scripted to, not because a skill gates them. The skill implementation makes this emergent: Vail collects and sells because he *has* `skill:trade`, the actions require it, and his needs/desires motivate using it.

**Implementation questions to resolve:**
- How is the circumstances modifier calculated and stored? Per-action at evaluation time, or cached on the mortal?
- What is Durenn Vail's initial `skill:trade` rating, and how does it interact with the difficulty of the Sethis resource collection vs. the Neran selling action?
