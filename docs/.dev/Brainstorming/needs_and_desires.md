# Mortal Needs & Desires

## Overview

Every mortal has a set of **needs** and **desires** that drive their Agent's decision-making. These are tracked as satisfaction floats (0.0–1.0). Satisfaction decays over time; when it drops below a threshold, the Agent begins prioritizing actions to restore it.

**Needs** are universal or near-universal. When unsatisfied, they create urgency that overrides other goals. The Agent always addresses pressing or urgent needs before pursuing desires.

**Desires** are variable and culturally shaped. They represent enrichment rather than deficiency. When all needs are adequately met, the Agent pursues desires. Desires have no hard urgency floor — an unsatisfied desire makes a mortal restless and directs their choices, but does not dominate their behavior the way an urgent need does.

There are some notes on how these needs and desire might apply differently to Proxiī, but we will integrate all of this into Proxiī behavior at a later date.

### Thresholds

Each need and desire has two configurable thresholds:

- **Pressing** — satisfaction has dropped enough that the Agent begins weighting this need/desire more heavily in decisions. Other goals are not abandoned but this one competes more actively.
- **Urgent** — satisfaction is critically low. The Agent deprioritizes other goals until this need is addressed. Only needs, not desires, typically produce urgent states.

Cultural (and, later, personal) traits modify both thresholds and the base decay rate per tick. A mortal whose traits make a need more central to their identity will notice its absence sooner (higher pressing threshold) and feel its absence more acutely (higher urgent threshold relative to pressing). The listed trait influences below are not exhaustive but some illustrative starting examples.

---

## Universal Needs

These needs are present in all mortals. Their decay rates are relatively fixed, though traits can modulate them.

---

### Sustenance

**What it is:** Access to appropriate food and water (or species-equivalent). The most basic survival need.

**What satisfies it:** Consuming personal resources tagged as food/water equivalents; being in a location with sufficient supply.

**In practice:** Within the bounds of a stable, functional civilization, sustenance is typically auto-satisfied from the mortal's resource base and does not enter the Agent's active decision loop. It becomes a genuine constraint during resource scarcity, travel through hostile environments, or scenarios involving resource collapse.

**Trait influences:**

| Trait               | Effect                                                                                                                                  |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `values:indulgence` | Decay is slightly faster — the indulgent mortal wants *good* food, not merely sufficient food; their sustenance bar is partly aesthetic |
| `values:moderation` | Slightly slower decay; reduced urgency threshold — content with less                                                                    |
| `values:pragmatism` | Lower urgency threshold — food is fuel; adequate is adequate                                                                            |
| `practice:culinary` | Values quality and variety of foods — mortals with this trait like being among Pops with this trait                                     |

---

### Safety

**What it is:** Freedom from immediate physical threat, persecution, or extreme environmental hazard.

**What satisfies it:** Being in a location without active danger; having adequate protection (bodyguards, shelter, political status).

**In practice:** Usually auto-satisfied under normal conditions. Becomes active in conflict zones, hostile environments, or when the mortal is a target of violence or persecution.

**Trait influences:**

| Trait               | Effect                                                                                                                                       |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| `values:tenacity`   | Reduced urgency threshold — the tenacious mortal tolerates more danger before it dominates their decisions                                   |
| `values:idealism`   | May override safety need — a highly idealistic mortal can deprioritize safety in service of principle                                        |
| `values:pragmatism` | Safety need is weighted more heavily in decision trade-offs                                                                                  |
| `values:sedentism`  | Locations outside of home/origin deemed more dangerous than usual                                                                            |
| `values:xenophilia` | **Negative** values lead the mortal to see areas with Pops of different species or of other civilizations as being more dangerous than usual |

---

### Rest

**What it is:** Recovery from accumulated fatigue. Addressed through the fatigue system rather than as a standalone need.

**Implementation note:** Rest is not tracked as a separate satisfaction float. Instead, the mortal's fatigue level rises as actions are taken (each action costs fatigue in proportion to its intensity). When fatigue exceeds a threshold, the Agent adds rest as a high-priority option, and rest actions reduce fatigue. This is mechanically cleaner than a parallel need tracker.

**Trait influences on fatigue tolerance:**

| Trait               | Effect                                                                    |
| ------------------- | ------------------------------------------------------------------------- |
| `values:tenacity`   | Reduced threshold before fatigue triggers rest priority                   |
| `values:moderation` | Heightened threshold — the moderate mortal rests before they're exhausted |
| `values:indulgence` | Heightened threshold — comfort-seeking mortals dislike being tired        |

---

## Socially-Derived Needs

These needs are present in all mortals but their strength, decay rate, and thresholds are significantly shaped by cultural traits. The values below describe which traits most influence each need.

---

### Belonging

**What it is:** Social connection, acceptance, and a sense of membership in a community or relationship network.

**What satisfies it:** Social interactions with others (conversation, shared activities, time spent with people the mortal knows); being embedded in a stable community.

**Trait influences:**

| Trait                          | Effect                                                                                                                         |
| ------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| `values:solidarity`            | Significantly faster decay; higher thresholds — solidarity-oriented mortals feel isolation acutely and need regular connection |
| `values:autonomy`              | Significantly slower decay; lower thresholds — autonomous mortals are comfortable with more alone time                         |
| `practice:revelry` (Pop-level) | High local revelry culture provides passive belonging satisfaction through ambient social density                              |
| `values:xenophilia`            | A xenophilic mortal can satisfy belonging with unfamiliar people; a xenophobic mortal requires familiar community              |

---

### Status

**What it is:** Recognition, esteem, and acknowledgment of one's worth from peers and community.

**What satisfies it:** Achieving visible goals; being praised or rewarded; advancement in occupation or social position; successful completion of directives (for Proxiī, also includes Demiurge recognition).

**Trait influences:**

| Trait                | Effect                                                                                                                      |
| -------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| `values:prowess`     | Faster decay; significantly higher thresholds — ambitious mortals feel underrecognized quickly and crave more               |
| `values:humility`    | Slower decay; lower thresholds — humble mortals need less external validation                                               |
| `values:hierarchy`   | High hierarchy increases urgency threshold — in a hierarchy-valuing culture, status matters more acutely                    |
| `values:meritocracy` | Positive meritocracy: status need is satisfied specifically by earned recognition; title or birth alone does not restore it |

---

### Purpose

**What it is:** The sense that one's activities are meaningful and directed toward something that matters. This can also include spiritual fulfillment.

**What satisfies it:** Completing significant goals; achieving outcomes aligned with personal values or occupational duties; being part of something larger than oneself (a cause, a community, a mission). For Proxiī, purpose is strongly tied to fulfilling the Demiurge's directives when alignment is high.

**Trait influences:**

| Trait               | Effect                                                                                                                     |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `values:idealism`   | Faster decay; higher thresholds — idealistic mortals feel purposeless acutely when not working toward meaningful goals     |
| `values:pragmatism` | Slower decay; lower thresholds — pragmatic mortals find purpose in functional outcomes rather than grand meaning           |
| `values:prowess`    | Amplifies purpose need — ambition and purpose decay together when goals are absent                                         |
| `religion:` traits  | High religious trait values tie purpose to spiritual/divine activity; purpose is partially satisfied by religious practice |

---

### Leisure

**What it is:** Time for enjoyment, rest from purposeful activity, and cultural participation for its own sake. Distinct from rest (which addresses fatigue) — leisure is about enrichment, not recovery.

**What satisfies it:** Engaging in `practice:` activities (music, dance, athletics, revelry, etc.) aligned with personal preferences; spending resources on pleasurable experiences; social leisure (`practice:revelry`). Satisfaction efficiency is determined by both the mortal's personal practice preferences and the quality available locally (local Pop `practice:` trait values).

**Trait influences:**

| Trait                  | Effect                                                                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `values:indulgence`    | Significantly faster decay; higher thresholds — indulgent mortals feel the absence of leisure quickly and require richer satisfaction |
| `values:moderation`    | Slower decay; lower thresholds — moderate mortals are content with less leisure and more easily satisfied                             |
| `values:pragmatism`    | Suppresses leisure urgency — pragmatic mortals are more willing to defer leisure for other goals                                      |
| `values:idealism`      | Can suppress or redirect leisure — idealistic mortals may feel guilt about leisure that doesn't serve a purpose                       |
| `practice:` (personal) | Specific practice preferences determine which activities satisfy most efficiently                                                     |
| `skill:` (personal)    | Having a skill creates an additional satisfaction bonus from practicing it                                                            |

**Quality multiplier:** Leisure satisfaction gained from a `practice:` activity scales with the local Pop's trait value in that practice. Durenn Vail listening to Surathi music gains more leisure satisfaction from their high `practice:music` Pop than he would from a low-practice:music community, even if he prefers music equally in both cases. (This is a test case that we will engineer later.)

---

## Desires

Desires are individually variable and represent enrichment goals rather than deficiency states. The Agent pursues desires when needs are adequately met. No desire has a hard urgency floor, but persistent unsatisfied desire shifts the mortal's priority weighting over time.

---

### Accumulation

**What it is:** The drive to acquire more resources beyond what current needs require.

**What generates it:** Present when `values:prosperity` is elevated; amplified by `values:prowess`; especially elevated by negative `values:moderation`.

**What satisfies it:** Increasing personal resources; completing profitable trade; advancing occupation in ways that increase resource access.

---

### Knowledge

**What it is:** The drive to learn and understand — both new information and deeper mastery.

**What generates it:** `values:erudition` (formal/theoretical knowledge); `values:folk_wisdom` (traditional and practical knowledge). These can generate distinct flavors of the desire — the scholarly mortal wants to read and discuss; the folk-wisdom mortal wants to observe, listen to elders, and practice traditional skills.

**What satisfies it:** Information-gathering actions; time with Scholar-stratum contacts; travel that reveals new locations or cultures; completing research-type activities.

---

### Exploration

**What it is:** The drive to experience new places, cultures, and situations.

**What generates it:** Negative `values:sedentism` (values movement and new places); high `values:xenophilia` (finds the unfamiliar appealing); amplified when either is combined with positive `values:ambition` or `values:tenacity`.

**What satisfies it:** Travel to new locations; encountering unfamiliar Pops; sightseeing actions; spending time in locations significantly different from home.

**Note:** This is the desire that drives Durenn Vail to the Surathi village rather than returning immediately to Neran. Combined with his high `values:indulgence` (urgent leisure need), his moderate `values:xenophilia`, and his awareness that a Surathi Pop offers higher-quality music, the Agent chooses the culturally distant but qualitatively richer option.

---

### Expression

**What it is:** The drive to engage with specific cultural practices — both as participant and, for skilled mortals, as producer.

**What generates it:** Personal `practice:` preferences (developed from the mortal's Pop culture) outside of `practice:ritual` and `practice:revelery`. High `skill:` in a creative domain creates a secondary production desire — a skilled musician doesn't just want to listen, they want to play.

**What satisfies it:** Attending or participating in the relevant practice; for high-skill mortals, performing or creating.

**Note:** This is distinct from the Leisure need. A mortal with low leisure satisfaction will seek *any* satisfying leisure. The cultural expression desire is specifically about *particular* practices.

---

### Influence

**What it is:** The drive to have meaningful control over events, people, and situations.

**What generates it:** `values:prowess` (wanting to achieve more broadly); `values:hierarchy` (caring about one's position in power structures). High `values:meritocracy` channels this into earned advancement rather than raw power-seeking.

**What satisfies it:** Taking actions that visibly affect outcomes; advancement in social or occupational position; directing others successfully; for Proxiī, having their directives produce observable results.

---

## Interactions and Notes

### Conflicting needs

Some needs work against each other in specific mortal profiles. A mortal with high `values:solidarity` and high `values:autonomy` simultaneously will have both a strong belonging need and a strong drive for independence — they need connection but also need freedom from it. The Agent manages this through sequencing rather than resolving the tension, which produces a characteristically restless social pattern.

### Trait pairs that suppress needs

- High `values:idealism` + high `values:pragmatism` simultaneously: purpose need is very strong but very easily satisfied (idealistic about goals, pragmatic about outcomes)
- `religion:nontheism` fully suppresses spiritual aspect of the need for purpose — this mortal simply does not have it
- Very high `values:moderation` suppresses leisure urgency almost entirely — this mortal is difficult to satisfy through luxury or pleasure-seeking

### Pops

At the Pop level, aggregate needs function as demographic pressure rather than individual Agent inputs. A Pop with high aggregate leisure need and insufficient local `practice:` quality will generate events — unrest, cultural drift toward the nearest satisfying source, migration toward higher-quality communities. A Pop with high spiritual need and declining religious institutions will experience stability effects. Pop-level needs are outputs of the trait distribution rather than direct Agent drivers. These Pop-level implementations will follow later.

### Proxius modifiers

For Proxiī specifically, the Demiurge relationship creates additional modifiers:
- High alignment amplifies purpose satisfaction from directive completion
- High loyalty causes belonging satisfaction to partially derive from Demiurge contact
- Neglect (long gaps without directive or acknowledgment) accelerates belonging and purpose decay
