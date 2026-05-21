# Luminary & Pantheon Constraint Types

## Purpose

This document catalogs constraint types for use in scenario design, with honest notes on current implementability. The goal is to ensure every constraint has concrete mechanical effects — no constraint should be flavor text only.

Constraints are rules placed on the Demiurge (and sometimes their agents) by Luminaries or Pantheons. They define what must exist, what must be suppressed, what actions are forbidden, and what conditions must be maintained. Violations always produce mechanical consequences: satisfaction loss at a minimum, triggered events or sanctions at worst.

---

## Implementability Key

- ✅ **Currently implementable** — all required systems exist
- 🔜 **Near-term** — requires a system currently in development or planned imminently
- 🔮 **Future** — requires systems not yet designed (Factions, Govs, Stronghold, etc.)

---

## Type 1: Expression Floor/Ceiling

The most direct constraint type. A Domain's universal expression must stay above, below, or within a defined range.

- **Floor**: *"Order expression must remain above 0.4"* — protective; demands active maintenance
- **Ceiling**: *"Change expression must never exceed 0.6"* — suppressive; punishes success elsewhere if it bleeds into the wrong Domain
- **Range**: *"Conflict expression must stay between 0.3 and 0.7"* — the most demanding; violations can come from either direction

**Tunables**:
- Threshold value
- Scope: universe-wide, per-galaxy, per-system, per-civilization
- Penalty rate: how fast satisfaction drops per tick of violation
- Visibility: whether the threshold is shown to the player or must be inferred from consequences

**Implementability**: ✅ Universal Domain expression is already tracked. Satisfaction mechanics already exist.

---

## Type 2: Relative/Ordering Expression

Cross-domain relational constraints. More interesting than absolute thresholds because they create dynamic tension that moves with the simulation.

- *"Order expression must always exceed Conflict expression"* — satisfying one makes the other harder
- *"The gap between Growth and Decay must not exceed 0.3"* — forces balance between paired Domains
- *"Truth must be the highest-expressed Domain in the universe"* — creates a full priority ordering

**Tunables**:
- Which Domains are compared
- Whether it is strict inequality or a margin
- Direction of the comparison
- Scope (same as Type 1)

**Implementability**: ✅ Derivable from existing expression tracking. Requires constraint evaluation logic that compares two Domain values rather than one against a constant.

---

## Type 3: Civilization Survival/Status

A specific civilization — or a category of civilization — must exist, thrive, or conversely must not.

- *"The Teshari Hegemony must not be destroyed"*
- *"No civilization may reach Interstellar scale"*
- *"At least one City-State scale civilization must exist somewhere"*
- *"Civilization X must be the dominant power in its system"*

**Tunables**:
- Named civilization vs. category
- Required status: existence, scale tier, dominance, survival of key institutions
- What counts as destruction vs. severe decline

**Implementability**: 🔜 There is currently no mechanical means by which civilizations advance in scale, decline, or cease to exist. These processes — and the events that drive them — are not yet implemented. Civilization survival constraints can be partially set up as framework now, but they cannot fire meaningfully until civilizational change mechanics exist. Dominance metrics similarly require a defined measurement (population, wealth, military) that depends on the resource and wealth system.

---

## Type 4: Cultural/Pop Character

The belief or trait profile of Pops or civilizations must conform to a specified character.

- *"The dominant religion in any civilization must include a Sacrifice Domain trait"* — requires active preaching
- *"No Pop may hold `values:materialism` above 0.7"* — suppression constraint that fights natural cultural drift
- *"At least one Pop of size > 5 must hold `practice:ritual_warfare`"* — specific cultural survival requirement

**Tunables**:
- Trait category and specific trait
- Threshold value
- Scope: specific named civilization, any civilization, all civilizations
- Floor vs. ceiling
- Whether the constraint tracks institutional beliefs, aggregate Pop beliefs, or both

**Implementability**: ✅ Pop and civilization trait tracking already exists. Constraint evaluation against trait thresholds is a natural extension of the existing stability and cohesion mechanics.

---

## Type 5: Action Prohibition/Mandate

Constraints on what the Demiurge themselves may or may not do — or must do at a minimum frequency.

- *"You may not use Manifest Omen in any civilization that has reached Regional scale"*
- *"You must issue at least one Whisper per N ticks"*
- *"No Proxius may be **directed** to operate in this galaxy"*
- *"You may not reveal a Tier-3 or higher Imāgō while a civilization is below Planetary scale"*
- *"A Proxius may not be **directed** to move between civilizations, but may do so autonomously to achieve a mission goal"* — distinguishes player-issued directives from agent autonomy
- *"You may not directly influence any individual mortal other than through Proxiī, which you **are** allowed to appoint"* — silent deity; no Whispers, no Shape Dreams

**Tunables**:
- Which specific action(s) are affected
- Scope of the restriction (universe, galaxy, system, specific civilization)
- Frequency requirement (for mandates) vs. hard prohibition
- Whether the restriction applies only to direct Demiurge actions, to directed Proxius actions, or to all agent actions including autonomous ones

**Implementability**:
- Prohibitions and mandates on **Demiurge direct actions**: ✅
- Prohibitions on **directed Proxius actions**: ✅ The directive system distinguishes player-issued orders from agent behavior
- Constraints distinguishing **directed vs. autonomous** Proxius movement: 🔜 The architectural distinction is meaningful, but autonomous Proxius behavior is currently vestigial. This constraint type can be framed and stored now but will not produce meaningfully different outcomes until Proxius autonomy is more fully developed.

---

## Type 6: Divine Footprint/Secrecy

How visible the Demiurge's work may be, constraining the acceptable level of divine trace.

- *"Divine trace in civilization X must never exceed the 'suspicious' threshold"* — forces subtlety
- *"No civilization may develop a theology that names or describes the Demiurge specifically"* — detects and punishes revealed presence
- *"All Proxiī must be incorporated mortals, not appointed from outside the civilization"* — restricts agent origin

**Tunables**:
- Trace threshold (maps to existing footprint/trace system)
- Which civilizations are covered
- Whether violation triggers a specific sanction or only satisfaction loss
- Whether the constraint is known to the player upfront or revealed upon violation

**Implementability**: ✅ Divine trace and footprint are already tracked. Theology detection — whether a civilization's dominant beliefs reference the Demiurge — is feasible using existing Pop trait evaluation. Proxius origin restriction is implementable given existing appointment mechanics.

---

## Type 7: Temporal/Deadline

A condition must be achieved or avoided within a specific window. Adds urgency without being permanent pressure.

- *"Domain Y expression must not drop below 0.3 for more than 10 consecutive ticks"* — tolerance for brief violations ✅
- *"A named notable mortal must survive until tick N"* — protection with a natural expiry ✅
- *"Civilization X must reach Planetary scale within 50 ticks"* — requires civilizational advancement mechanics 🔜

**Tunables**:
- Deadline tick (fixed) or duration (rolling)
- Grace period: number of consecutive ticks a brief violation is tolerated before it counts
- Whether the deadline is visible to the player
- Consequence on expiry: satisfaction collapse, triggered sanction, narrative event

**Implementability**: ✅/🔜 Deadline constraints tied to expression values or notable mortal status are implementable now — tick tracking and the relevant data all exist. Deadline constraints tied to civilizational advancement, scale changes, or events depend on systems not yet built.

---

## Type 8: Essence Economy

Constraints on the Demiurge's resource generation or spending.

- *"Your Essence stockpile may never exceed N"* — forces active spending, punishes hoarding
- *"You must maintain at least N Essence in reserve at all times"* — restricts aggressive spending
- *"You may not draw Essence from Domain X"* — cuts off a revenue stream, often paired with an expression floor on that Domain for a double bind

**Tunables**:
- Floor vs. ceiling vs. both
- Which Domain sources (if any) are restricted
- Hard cutoff (action blocked) vs. graduated satisfaction penalty
- Whether the constraint applies to apparent Essence, actual Essence, or both (relevant to concealment mechanics)

**Implementability**: ✅ The Essence economy is fully tracked. Stockpile constraints and Domain-source restrictions are straightforward additions to the existing Essence calculation. The apparent/actual Essence distinction is already architecturally present.

---

## Type 9: Conditional/Triggered

Constraints that activate only when a condition is met. These are among the most flavourful constraint types, but their implementability is heavily gated by what conditions the simulation can actually detect.

- *"If Domain X expression crosses threshold Y, constraint Z activates"* — expression-triggered ✅
- *"If Luminary A's satisfaction drops below 0.4, you may not target Luminary B's Domains for 10 ticks"* — satisfaction-triggered ✅
- *"If a civil war begins in civilization X, you must not intervene until it resolves"* — event-triggered 🔮
- *"If any civilization discovers space travel, Order expression must reach 0.5 within 20 ticks"* — advancement-triggered 🔜

**Tunables**:
- Trigger condition type (expression threshold, satisfaction level, tick, notable mortal status, civilizational event)
- What the constraint demands once triggered
- Whether the trigger is one-time or resets when the condition clears
- Whether the trigger is visible to the Demiurge before it fires

**Implementability**: The trigger evaluation framework does not currently exist and needs to be built. Among potential trigger conditions, expression thresholds and satisfaction levels are immediately usable since those values are tracked. Civilizational events (civil wars, invasions, collapses) are not implemented and have no current mechanical representation. Advancement-triggered conditions wait on civilizational change systems.

---

## Type 10: Notable Mortal Survival/Status

A specific notable mortal must live, die, or hold a particular status.

- *"Notable mortal X must survive until tick N"* — protection mandate
- *"A notable mortal with alignment > 0.7 must exist in civilization X"* — character requirement
- *"Notable mortal X must hold a position of civic authority in civilization X"* — role requirement 🔮

**Tunables**:
- Named mortal vs. category (e.g., "any Proxius with alignment > 0.6")
- Survival vs. death vs. status requirement
- Deadline (if any)

**Implementability**: Notable mortal tracking and alignment scores exist. Natural lifespan-based mortality exists for mortals. However, event-driven mortal death (assassination, conflict, disaster) is not mechanically implemented. Role-based constraints (requiring a mortal to hold civic office) wait on the Gov system.

---

## Pantheon-Level Constraints

These encode the *relationship between Luminaries* rather than demands on the Demiurge's behavior directly.

### Satisfaction Parity
*"No Luminary may be more than 0.3 satisfaction above any other."*
Forces the Demiurge to manage the whole Pantheon rather than focusing on the most demanding member.
**Implementability**: ✅

### Priority Ordering
*"Luminary A's primary demands must be met before any action may serve Luminary B's Domains."*
Encodes an explicit hierarchy. The lower-priority Luminary becomes a persistent background dissatisfaction that cannot be addressed until the higher-priority one is satisfied.
**Implementability**: ✅ Requires constraint evaluation ordering logic.

### Mutual Exclusion
*"Satisfying Luminary A's primary Domain beyond 0.7 expression automatically violates Luminary B's ceiling."*
The scenario is structurally unresolvable through direct means. Best used sparingly.
**Implementability**: ✅ Falls out naturally from overlapping Type 1 constraints if designed intentionally.

### Synchronized Deadlines
*"Both Luminaries must be above 0.5 satisfaction simultaneously by tick N."*
Forces parallel progress rather than sequential.
**Implementability**: ✅ Extension of Type 7 with a multi-condition AND requirement.

### Delegated Constraints
A Luminary constrains what other Luminaries may demand.
*"Luminary A may not issue a demand targeting a civilization currently under Luminary B's active Herald."*
**Implementability**: 🔮 Requires Herald agents.

---

## Future Constraint Types (Pending Systems)

### Faction/Gov Constraints 🔮
*"The governing body of civilization X must include a Faction aligned with Domain Y."*
Requires Factions and Govs.

### Technology Constraints 🔜
*"Civilization X must not advance beyond Continental tech scale."*
*"At least one civilization must have unlocked the Energy Access branch at Planetary tier."*
Requires the tech tree system.

### Resource/Wealth Constraints 🔜
*"Civilization X's wealth stat must remain above 'adequate'."*
Requires the resource and wealth system.

### Stronghold Constraints 🔮
*"You may not construct a Stronghold in this scenario."*
Requires Stronghold implementation.

---

## Design Principle

The most mechanically interesting constraints are ones where satisfying Condition A makes Condition B harder — not through scripted conflict but through the underlying simulation. A Growth expression floor and a Conflict expression floor held by different Luminaries will naturally work against each other as peaceful, prosperous civilizations reduce endemic conflict. The constraint system is most powerful when it encodes *genuine cosmological disagreement* between Luminaries rather than arbitrary rules stacked on top of the simulation.

Every constraint should pass this test: **if the constraint were removed, would the player's behavior change?** A constraint the player would satisfy regardless is not a constraint — it is flavor text with extra steps.
