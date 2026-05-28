# RTwP Action System — Brainstorming & Implementation Approach

## Concept Summary

The current turn-based system (one action per category per tick, advance manually) is replaced with a **Real-Time with Pause** model. Time advances continuously; the player intervenes when action categories become available and the moment is right.

The core constraint shifts from "one action per category per tick" to **per-category cooldowns**: each action category has its own independent cooldown timer that counts down as ticks advance. The player can act in a category the moment its cooldown reaches zero, regardless of what other categories are doing.

This is an extension of the existing design rather than a replacement. The "one action per category" rule already exists; this stretches the interval from exactly one tick to a variable number of ticks determined by the category and context.

---

## Time Advancement

| Input | Behavior |
|---|---|
| `t` | Advance exactly one tick (existing behavior, preserved) |
| `spacebar` (main game screen) | Toggle continuous auto-advance |

During auto-advance, ticks process continuously. The player can stop advancement at any time. Configurable auto-pause conditions (see below) can interrupt advancement automatically.

### Tick Scale

With this system, ticks can now represent **days** rather than the current ~six months. The per-tick magnitude of belief shifts, cultural trait changes, Essence generation, and Revelation accumulation is recalibrated accordingly — floors are dropped very low, and fractional accumulation handles precision rather than per-tick minimums.

Universe age and civilization ages are stored and displayed in actual years, months, and days.

Because universe age can be billions of years and gameplay will almost never have to account for anywhere near that much time, year counts in the billions, millions, and thousands are each stored as separate values that can be overflowed into as necessary—but generally don't change. The year number that "matters" will be between 0 and 999.

A year will be divided into twelve months where every month has 30 days for simplicity. Months will simply be shown as numbers and not given names.

One design goal is to have an impressive top bar label showing something like "Day 13 of Month 5, Year 13,675,482,090"—that mechanically doesn't mean a whole lot.

The tick-to-time correspondence is a scenario parameter, but for scenarios like "The Warden's Compact" and "The Ash and the Ledger," this will be one day. We may expand this later to have "compacted time" in young universe where very little is happening, but we will keep it standard at one day for now.

---

## Action Category Cooldowns

Each action category has:
- A **base cooldown** (number of ticks before it can be used again), determined by the category's inherent weight
- A **current cooldown counter** that decrements each tick
- A **ready state** (counter = 0) when actions in that category can be queued

### Cooldown Modifiers

**Individual actions** within categories may or may not have cooldown modifiers, increasing the actual cooldown timer of their parent action category when used. For example, Shape Dream will cause the Subtle Interaction category to cool down for longer after its use than Whisper to Mortal does, and Appoint Proxius will make the Proxius Direction action category take longer to cool down than Preach Imāgō (or other Proxius directives) does.

**Puissance** provides a slight reduction to all cooldown durations — a more capable Demiurge acts more fluidly. The exact formula defers to the existing `puissance` implementation.

**Ongoing actions** in a category: a category with an active ongoing action (e.g., Explore Beliefs running) could optionally reduce the cooldown for related actions (e.g., any action that involves the use of Imāginēs), since divine attention is already partly engaged in a similar area. Exact interactions TBD per category.

### Stopping or Replacing Ongoing Actions

Stopping an ongoing action is treated as **an action in that category** — it triggers a cooldown, as well, meant to discourage the player from toggling ongoing actions on and off unnecessarily.

---

## Auto-Pause Configuration

Certain events interrupt auto-advance automatically. The player can configure which event types trigger a pause.

### Suggested Default Tiers

**Always pause (not configurable):**
- A Luminary, Herald, Proxius, or other entity initiates contact/dialogue
- A Luminary issues an ultimatum

**Default pause (player can disable):**
- Luminary evaluation completes
- A Revelation threshold is reached (new Imāgō affordable)
- A queued action completes
- A pinned notable mortal dies or reaches a critical state

**Default silent (player can enable):**
- Pop splinter created
- Domain expression crosses a threshold
- A mortal's travel completes
- Minor agent status updates

---

## Dialogue as Auto-Pause

When an entity contacts the Demiurge — a Luminary issuing orders, a Herald delivering a message, a Proxius reporting, or eventually a mortal petitioner — tick advancement halts unconditionally regardless of player auto-pause settings. The contact demands presence.

This is the natural future home for a dialogue system or 4X-style diplomacy equivalent. The contact interrupts the flow of time and requires a response (or a deliberate choice not to respond).

---

## UI: Action Category Panel

A new **far right-hand vertical panel** displays all action categories as interactive symbols with cooldown indicators.

### Cooldown Visualization

The ideal design is that each category symbol is accompanied by a **clock-style circular fill meter** rendered using Unicode block and arc characters, consistent with the game's text-based aesthetic. As ticks advance, the meter fills clockwise. When full, the category is ready.

Alternatively, the symbol could be displayed with a short, horizontal progress bar beneath it, which is something that Textual is more capable of handling without fancy formatting. As such, we will go with this option, and we will consider ways that we might replace it with a clock-style look later.

The goal is a readable at-a-glance state for each category without requiring the player to read numbers.

The symbol for each category is:

| Category           | Symbol |
| ------------------ | ------ |
| Direct Creation    | ✦      |
| Overt Miracle      | ✺      |
| Subtle Influence   | ≃      |
| Proxius Direction  | ▻      |
| Observation        | ⊚      |
| Herald Interaction | ⚜      |
| Luminary Relations | ↑      |
| Underreal          | ∇      |
| Self-Refinement    | ⟡      |

### Interaction

The category symbol in this panel acts as a **third method** to queue an action in that category, alongside:
1. The `a` key (existing)
2. The "queue action" button in the Actions tab (very new but existing)
3. Clicking the symbol in the new panel (to be implemented)

Clicking a symbol whose cooldown has not yet expired shows a "not ready" toast modal.

---

## Implementation Approach

### Phase 1: Core Loop Refactor
- Replace manual tick advancement with continuous auto-advance toggle (`spacebar`)
- Preserve `t` for single-tick advancement
- Confirm the game loop is stable under continuous advancement without player input

### Phase 2: Per-Category Cooldowns
- Add a cooldown counter to each action category
- Define base cooldown values per category (start with placeholder values, tune during playtesting)
- Gate action availability on cooldown state rather than tick boundary
- Implement the longer cooldown for stopping ongoing actions

### Phase 3: Auto-Pause System
- Implement the event-type pause framework
- Wire up the default tier events
- Add player configuration for the configurable tiers

### Phase 4: Category Panel UI
- Build the right-hand vertical panel in Textual
- Implement cooldown meters
- Wire up click-to-queue on ready symbols

### Phase 5: Tick Scale Recalibration
- Change tick to represent days
- Recalibrate all per-tick rates (Essence, Revelation, cultural drift, etc.)
- Update universe age and civilization age display to actual years
- Drop floors and rely on fractional accumulation throughout

*Note: Phase 5 touches many systems and should be done as a single coordinated pass rather than incrementally.*

---

## Open Questions

- **Base cooldown values**: What are the right base cooldowns per category? These will need significant playtesting to feel right. A useful starting heuristic: categories involving direct divine action (Manifest Omen, Appoint Proxius) have longer cooldowns than subtle or delegated actions (Whisper, Proxius directive) or than "internal" actions (Reveal Imāgō, Change Domain Affiliation).
- **Cooldown display during ongoing actions**: Should a category with a running ongoing action show its cooldown differently from one that is simply waiting? (Perhaps the progress bar is a mid-gray blue rather than the typical color?)
- **Tick recalibration scope**: Phase 5 will require auditing every system with a per-tick rate. A full list should be assembled before that pass begins.
