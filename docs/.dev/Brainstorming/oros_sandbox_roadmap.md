# Oros Sandbox Roadmap

Goal: a fully functional tribal-scale, single-planet simulation. The sandbox has 9 PopLocations, 3 factions (Asha Dunewalker Clan, The Hiparunites, The Stonecallers), 3 NotableMortals (Asha Keln, Kael Osh, Urren), and 5 TravelNetworks (general + 4 faction-gated fast routes).

The end-state milestone: introduce a fourth NotableMortal with no faction affiliation and see if they can earn TravelNetwork privileges or faction membership through play.

---

## ~~1. Travel routing condition evaluation~~ ✅ Complete

Wire up condition and edge evaluation in the routing layer. ~~Currently TravelNetwork has `edges` and `conditions` fields but nothing reads them.~~

- Router filters hard-gated networks the traveler can't access
- `leg_cost` gains a traveler parameter and returns `privileged_cost` when conditions are met
- Agent route selection: given multiple viable routes to the same destination, pick based on active directives, known costs, and current assets

Also delivered: `ResourceCost` model, `PopLocation.danger`, `TravelRoute` dataclass with tick-weighted danger metrics, direct `mortal.faction_ids` / `faction.member_mortal_ids` fields, and cleanup of all pop-indirection callsites in the engine and UI.

---

## 2. Generalized MortalAgent

Extend `initialize_mortal_state` so it works for tribal mortals, not just Durenn's trade-focused setup. The three Oros NotableMortals currently have no `mortal_state`.

- Needs and desires calibrated to tribal context (survival, belonging, purpose, status)
- Depends loosely on #3 — need to know what resources exist before mortals can want them
- Eventually: a general lazy-init pass on scenario load for any mortal that should have one

---

## 3. Resource system

Concrete resources that Pops and mortals need and compete over. Currently resources exist in agent_core (for Durenn's unobtanium trade loop) but aren't generalized to tribal contexts.

- Define what resources exist in the Oros world (food, water, raw materials, crafted goods, territory?)
- Attach collectible resources to relevant PopLocations (Salt Flats, Ancestor Stones, etc.)
- Pops have resource needs; scarcity creates pressure that motivates faction behavior

*Foundational for #4–7. The most important item to get right before building on top of it.*

---

## 4. PopAgent mechanics

Pops currently have no autonomous behavior. This is the largest single item on the list.

- Migration: Pops move toward better conditions (resources, safety, belonging)
- Resource gathering: Pops collect and consume resources at their location
- Faction affiliation shifts based on which faction best serves Pop needs
- Depends on #3

---

## 5. Faction goals → Directives

Factions have goals that cascade down to NotableMortals and Pops as Directives.

- Faction object gains a goal structure (raid, expand, defend, trade, proselytize, etc.)
- Goals translate to DirectiveFacts pushed to affiliated mortals and pops
- Faction goals respond to world state (resource scarcity, threat level, territory control)
- Tightly coupled with #6 — develop together

---

## 6. NotableMortal influence on factions and Pops

Mortals affect their faction's direction and Pop behavior, not just the other way around.

- A mortal's actions (raids, speeches, negotiations) shift faction goals and Pop loyalty
- Prominent mortals can sway faction policy or defect and take followers
- Depends on #2 (MortalAgent) and #5 (faction goals)

---

## 7. Combat, raiding, fleeing, territory

- Raiding: one faction's mortals/pops attack another's locations for resources
- Fleeing: pops and mortals retreat from dangerous locations via available TravelNetworks
- Territory: factions claim and contest PopLocations; control affects resource access
- Danger as a PopLocation property (referenced in TravelNetwork design)
- Depends on #3 (resources to fight over), #4 (pops that can act), #5 (faction goals)

---

## 8. Diplomacy and mortal-to-mortal interaction

- NotableMortals negotiate with each other: truces, trade agreements, permission grants
- Faction relationship model (hostile, neutral, wary, allied)
- Permission grants enable TravelNetwork privileges without full faction membership
- Depends on #5, #6, and a mortal interaction channel that doesn't yet exist

---

## Dependency order

```
1 (routing) ──┐
2 (mortal agent) ──┐
3 (resources) ──────┤
                    ├── 4 (pop agent) ──┐
                    └── 5 (faction goals) ──┬── 6 (mortal influence) ──┐
                                            │                           ├── 7 (combat)
                                            └───────────────────────────┴── 8 (diplomacy)
```

Items 1 and 2 are independent starting points. Everything from 4 onward builds on 3.
