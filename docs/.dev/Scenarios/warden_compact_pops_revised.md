# Warden's Compact — Planned Changes

## Pop Occupation Redesign

Pops gain a canonical **occupation** sub-field within their stratum.

Sizes are logarithmic. Beliefs and cultural values tags use short names (prefix stripped).

---

## Trait Notes

**`relations:commerce` — retained for compatibility.** TODO: Eventually derive "spending attractiveness" and commercial cultural orientation from civilization scale, Gov type, and resource system data, then deprecate.

**Bipolar traits:** 0.0 is neutral. Negative values represent active orientation toward the opposing stance.

---

## Neran Confederacy — Civilization Baseline

**Domain Beliefs:** `order 0.8, mastery 0.5, community 0.3, truth 0.25, growth 0.2, light 0.15`

**Cultural Traits:** `sedentism 0.9, hierarchy 0.85, tenacity 0.8, relations:commerce 0.75, solidarity 0.65, erudition 0.65, luminary_worship 0.6, honor 0.6, ancestor_worship 0.5, pragmatism 0.65, meritocracy 0.5, prowess 0.55, prosperity 0.45`

---

## Neran Surface

| Stratum      | Occupation   | Size | Notable Mortal | Domain Beliefs                                                               | Cultural Traits                                                                                                                                                                                                                                                                        |
| ------------ | ------------ | ---- | -------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Elite        | poli_admin   | 5.0  | Senna Vaur     | order 0.9, mastery 0.55, community 0.3, truth 0.25, light 0.2, secrecy 0.15  | hierarchy 0.9, solidarity 0.75, honor 0.7, sedentism 0.8, prowess 0.65, pragmatism 0.65, meritocracy 0.6, relations:commerce 0.55, luminary_worship 0.5, prosperity 0.4, nontheism 0.35, ancestor_worship 0.2, practice:ritual 0.7, practice:lit 0.5                                   |
| Elite        | noble        | 3.5  |                | order 0.85, mastery 0.6, memory 0.4, light 0.25, secrecy 0.2                 | hierarchy 0.9, honor 0.85, sedentism 0.9, ancestor_worship 0.8, luminary_worship 0.6, folk_wisdom 0.55, prowess 0.65, meritocracy 0.2, practice:lit 0.7, practice:ritual 0.65                                                                                                          |
| Scholar      | scientist    | 6.5  |                | truth 0.7, mastery 0.65, order 0.4, change 0.3, light 0.35                   | erudition 0.95, tenacity 0.6, pragmatism 0.6, nontheism 0.55, prowess 0.55, autonomy 0.6, idealism 0.4, hierarchy 0.2, sedentism 0.65, folk_wisdom -0.3, luminary_worship 0.2, ancestor_worship 0.05, practice:lit 0.75                                                                |
| Scholar      | academic     | 6.2  |                | truth 0.65, mastery 0.5, order 0.45, memory 0.3, light 0.3, water 0.2        | erudition 0.95, idealism 0.6, patience 0.55, solidarity 0.45, pragmatism 0.45, ancestor_worship 0.4, humility 0.4, nontheism 0.4, hierarchy 0.3, sedentism 0.7, luminary_worship 0.3, practice:lit 0.9, practice:theatre 0.35                                                          |
| Scholar      | clergy       | 4.5  | Veth Sarai     | order 0.7, silence 0.55, truth 0.45, memory 0.35, sacrifice 0.3, growth 0.2  | luminary_worship 0.85, ancestor_worship 0.7, sedentism 0.8, humility 0.75, patience 0.65, solidarity 0.65, demiurge_worship 0.5, sincerity 0.5, hierarchy 0.55, folk_wisdom 0.5, indulgence -0.25, practice:ritual 0.9, practice:music 0.6                                             |
| Trader       | merchant     | 6.7  | Durenn Vail    | order 0.65, community 0.6, mastery 0.4, change 0.3, void 0.2                 | relations:commerce 0.9, prosperity 0.8, solidarity 0.65, honor 0.55, pragmatism 0.65, nontheism 0.6, xenophilia 0.6, hierarchy 0.4, sedentism -0.5, indulgence 0.45, adaptability 0.4, prowess 0.35, idealism -0.1, luminary_worship 0.35, ancestor_worship 0.15, practice:revelry 0.7 |
| Trader       | executive    | 6.5  |                | order 0.75, mastery 0.55, community 0.3, change 0.2, light 0.2               | relations:commerce 0.8, hierarchy 0.8, prowess 0.75, pragmatism 0.7, solidarity 0.55, honor 0.6, sedentism 0.75, meritocracy 0.65, prosperity 0.6, autonomy 0.5, nontheism 0.45, luminary_worship 0.4, indulgence 0.35, ancestor_worship 0.25, practice:revelry 0.55                   |
| Trader     | financier    | 6.0  |                | order 0.8, mastery 0.55, community 0.3, truth 0.3, secrecy 0.25              | relations:commerce 0.85, hierarchy 0.85, meritocracy 0.7, prosperity 0.85, pragmatism 0.75, sedentism 0.9, honor 0.65, nontheism 0.5, luminary_worship 0.35, ancestor_worship 0.2, practice:revelry 0.5                                                                                |
| Artisan      | engineer     | 7.5  | Thessal Dour   | mastery 0.75, order 0.5, change 0.4, truth 0.3, growth 0.2                   | erudition 0.8, tenacity 0.85, pragmatism 0.6, prowess 0.65, autonomy 0.5, hierarchy 0.5, sedentism 0.7, nontheism 0.65, luminary_worship 0.25, ancestor_worship 0.2, practice:crafts 0.75                                                                                              |
| Artisan      | technician   | 7.8  | Orryn Vel      | mastery 0.7, change 0.45, order 0.4, conflict 0.25, community 0.3            | tenacity 0.75, erudition 0.6, pragmatism 0.6, adaptability 0.55, solidarity 0.5, honor 0.45, hierarchy 0.35, sedentism 0.7, nontheism 0.5, luminary_worship 0.5, wit 0.35, ancestor_worship 0.3, practice:crafts 0.8                                                                   |
| Artisan    | crafter      | 7.0  |                | mastery 0.8, order 0.5, growth 0.25, truth 0.2                               | tenacity 0.8, prowess 0.75, pragmatism 0.65, erudition 0.65, sedentism 0.75, hierarchy 0.55, luminary_worship 0.4, nontheism 0.45, ancestor_worship 0.35, practice:crafts 0.9                                                                                                          |
| Artisan    | builder      | 6.0  |                | mastery 0.65, order 0.6, growth 0.35, community 0.3                          | tenacity 0.85, pragmatism 0.7, solidarity 0.65, hierarchy 0.6, sedentism 0.8, prowess 0.6, luminary_worship 0.5, ancestor_worship 0.45, practice:crafts 0.65                                                                                                                           |
| Artisan    | healer       | 5.5  |                | mastery 0.7, truth 0.45, growth 0.5, order 0.5, light 0.3                    | erudition 0.8, pragmatism 0.7, solidarity 0.7, hierarchy 0.65, sedentism 0.8, nontheism 0.55, prowess 0.6, luminary_worship 0.3, practice:lit 0.5                                                                                                                                      |
| Artisan    | artist       | 5.5  |                | mastery 0.6, change 0.5, truth 0.35, community 0.35, light 0.35              | autonomy 0.75, wit 0.65, sincerity 0.65, idealism 0.55, erudition 0.7, sedentism 0.55, hierarchy 0.15, prowess 0.65, nontheism 0.5, luminary_worship 0.3, practice:visual 0.8, practice:theatre 0.75, practice:music 0.65, practice:lit 0.7, practice:crafts 0.55                      |
| Common       | professional | 8.2  |                | order 0.75, mastery 0.45, community 0.35, truth 0.2                          | sedentism 0.9, hierarchy 0.75, meritocracy 0.6, relations:commerce 0.65, honor 0.55, erudition 0.55, luminary_worship 0.55, pragmatism 0.65, prosperity 0.5, prowess 0.4, nontheism 0.4, ancestor_worship 0.25, practice:lit 0.4, practice:revelry 0.5                                 |
| Common     | producer     | 7.8  |                | order 0.7, community 0.55, growth 0.5, mastery 0.3                           | sedentism 0.95, solidarity 0.7, folk_wisdom 0.65, luminary_worship 0.7, ancestor_worship 0.7, tenacity 0.75, hierarchy 0.5, nontheism 0.05, practice:ritual 0.55                                                                                                                       |
| Common     | transport    | 7.0  |                | order 0.65, community 0.5, mastery 0.4, change 0.3, void 0.2                 | tenacity 0.75, solidarity 0.65, pragmatism 0.7, sedentism -0.2, xenophilia 0.35, hierarchy 0.55, relations:commerce 0.6, luminary_worship 0.55, ancestor_worship 0.3, practice:revelry 0.65                                                                                            |
| Common       | service      | 9.0  | Maeva Sorn     | order 0.7, community 0.5, silence 0.35, memory 0.3, growth 0.2               | sedentism 0.9, solidarity 0.65, hierarchy 0.6, luminary_worship 0.7, ancestor_worship 0.65, relations:commerce 0.6, pragmatism 0.55, folk_wisdom 0.5, humility 0.4, nontheism 0.05, practice:revelry 0.75, practice:music 0.4, practice:ritual 0.6                                     |
| Common       | labor        | 8.5  |                | order 0.7, community 0.5, mastery 0.4, sacrifice 0.25, growth 0.2, fire 0.15 | sedentism 0.9, tenacity 0.85, solidarity 0.7, luminary_worship 0.75, hierarchy 0.45, folk_wisdom 0.55, ancestor_worship 0.55, pragmatism 0.5, meritocracy -0.15, adaptability -0.1, practice:revelry 0.7, practice:athletics 0.5                                                       |
| Warrior      | officer      | 4.0  |                | order 0.8, mastery 0.55, conflict 0.5, sacrifice 0.25, light 0.2             | hierarchy 0.9, prowess 0.75, tenacity 0.8, honor 0.7, solidarity 0.5, sedentism 0.75, pragmatism 0.65, luminary_worship 0.45, ancestor_worship 0.4, practice:combat 0.8, practice:athletics 0.75                                                                                       |
| Warrior    | guard        | 5.5  |                | order 0.85, mastery 0.5, conflict 0.3, community 0.4, light 0.2              | hierarchy 0.85, honor 0.75, tenacity 0.7, solidarity 0.7, sedentism 0.9, pragmatism 0.65, luminary_worship 0.55, ancestor_worship 0.35, practice:athletics 0.6                                                                                                                         |
| Warrior      | soldier      | 5.5  |                | order 0.75, conflict 0.55, mastery 0.4, sacrifice 0.35, fire 0.2             | hierarchy 0.8, tenacity 0.8, honor 0.65, solidarity 0.6, sedentism 0.8, ancestor_worship 0.6, luminary_worship 0.55, pragmatism 0.5, folk_wisdom 0.4, practice:combat 0.75, practice:athletics 0.7, practice:revelry 0.55                                                              |
| Underclass | dispossessed | 5.5  |                | community 0.5, order 0.5, silence 0.3, sacrifice 0.35, decay 0.2             | solidarity 0.65, folk_wisdom 0.65, luminary_worship 0.75, ancestor_worship 0.65, sedentism 0.75, tenacity 0.6, adaptability 0.45, hierarchy 0.25, meritocracy -0.35, nontheism 0.05, practice:revelry 0.6                                                                              |

---

## Neran Orbital Ring

| Stratum    | Occupation | Size | Notable Mortal | Domain Beliefs                                                                         | Cultural Traits                                                                                                                                                                                                                                                              |
| ---------- | ---------- | ---- | -------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Warrior    | officer    | 4.0  | Karath Omn     | mastery 0.8, conflict 0.65, order 0.55, sacrifice 0.3, void 0.2, light 0.2            | hierarchy 0.9, prowess 0.9, tenacity 0.85, honor 0.75, solidarity 0.55, pragmatism 0.6, sedentism 0.6, nontheism 0.5, ancestor_worship 0.35, luminary_worship 0.4, practice:combat 0.85, practice:athletics 0.7                                                              |
| Warrior    | soldier    | 3.5  |                | order 0.7, conflict 0.5, mastery 0.45, sacrifice 0.35, void 0.2                       | hierarchy 0.8, tenacity 0.85, honor 0.6, solidarity 0.65, sedentism 0.65, pragmatism 0.55, luminary_worship 0.5, ancestor_worship 0.5, folk_wisdom 0.4, nontheism 0.25, practice:combat 0.7, practice:athletics 0.65                                                         |
| Warrior  | guard      | 4.0  |                | order 0.85, mastery 0.5, conflict 0.35, community 0.35, void 0.15                     | hierarchy 0.85, honor 0.75, tenacity 0.75, solidarity 0.65, sedentism 0.8, pragmatism 0.6, luminary_worship 0.5, ancestor_worship 0.3, practice:athletics 0.55                                                                                                               |
| Scholar    | scientist  | 4.2  |                | truth 0.65, mastery 0.75, order 0.5, change 0.35, void 0.3, light 0.35               | erudition 0.95, tenacity 0.7, hierarchy 0.15, nontheism 0.7, prowess 0.7, autonomy 0.65, idealism 0.5, pragmatism 0.55, folk_wisdom -0.4, sedentism 0.5, luminary_worship 0.15, ancestor_worship 0.05, practice:lit 0.8                                                      |
| Artisan    | engineer   | 4.5  |                | mastery 0.8, order 0.55, change 0.4, conflict 0.3, void 0.2                           | tenacity 0.85, erudition 0.65, hierarchy 0.7, prowess 0.7, pragmatism 0.55, nontheism 0.5, solidarity 0.45, sedentism 0.6, luminary_worship 0.4, ancestor_worship 0.1, practice:crafts 0.8                                                                                   |
| Artisan    | technician | 5.2  |                | mastery 0.65, order 0.5, change 0.35, community 0.3, void 0.2                         | tenacity 0.8, erudition 0.55, hierarchy 0.6, sedentism 0.65, solidarity 0.55, pragmatism 0.6, luminary_worship 0.45, folk_wisdom 0.4, nontheism 0.35, ancestor_worship 0.2, practice:crafts 0.7, practice:revelry 0.5                                                        |
| Artisan  | healer     | 3.5  |                | mastery 0.7, truth 0.5, growth 0.45, order 0.5, void 0.2                             | erudition 0.8, pragmatism 0.75, solidarity 0.65, hierarchy 0.6, nontheism 0.6, sedentism 0.65, prowess 0.55, luminary_worship 0.25, practice:lit 0.4                                                                                                                         |
| Common   | transport  | 5.5  |                | order 0.65, community 0.5, mastery 0.4, change 0.35, void 0.35                        | tenacity 0.8, solidarity 0.65, pragmatism 0.7, sedentism -0.3, xenophilia 0.4, hierarchy 0.5, relations:commerce 0.55, luminary_worship 0.5, ancestor_worship 0.25, practice:revelry 0.6                                                                                               |
| Common     | service    | 4.8  |                | order 0.65, community 0.5, mastery 0.35, void 0.15                                   | sedentism 0.7, hierarchy 0.7, tenacity 0.7, solidarity 0.6, luminary_worship 0.6, pragmatism 0.55, ancestor_worship 0.35, folk_wisdom 0.4, nontheism 0.2, practice:revelry 0.6                                                                                               |
| Common     | labor      | 3.8  |                | order 0.65, community 0.45, mastery 0.4, sacrifice 0.3, void 0.2                      | tenacity 0.85, solidarity 0.65, sedentism 0.7, hierarchy 0.5, luminary_worship 0.65, folk_wisdom 0.5, pragmatism 0.5, ancestor_worship 0.4, meritocracy -0.1, nontheism 0.05, practice:revelry 0.5                                                                           |

## Mortals

### Durenn Vail — Trader:merchant

Beliefs: mastery 0.5, community 0.65, order 0.6, change 0.45, void 0.3

Culture: relations:commerce 0.95, prosperity 0.85, sedentism -0.7, xenophilia 0.8, indulgence 0.7, pragmatism 0.75, solidarity 0.7, honor 0.6, adaptability 0.55, nontheism 0.5, practice:revelry 0.85, practice:music 0.75

### Karath Omn — Warrior:officer (Ring)

Beliefs: mastery 0.9, conflict 0.75, order 0.6, sacrifice 0.4, void 0.35, light 0.25

Culture: hierarchy 0.95, prowess 0.95, tenacity 0.9, honor 0.85, pragmatism 0.7, nontheism 0.6, sedentism 0.7, solidarity 0.45, ancestor_worship 0.4, luminary_worship 0.35, practice:combat 0.95, practice:athletics 0.8

### Maeva Sorn — Common:service

Beliefs: order 0.65, silence 0.65, community 0.6, memory 0.5, truth 0.35

Culture: luminary_worship 0.92, ancestor_worship 0.85, sedentism 0.9, humility 0.75, patience 0.65, sincerity 0.55, solidarity 0.65, folk_wisdom 0.55, practice:ritual 0.8, practice:music 0.6

### Orryn Vel — Artisan:technician

Beliefs: change 0.8, conflict 0.65, truth 0.5, community 0.55, order 0.1

Culture: erudition 0.85, adaptability 0.8, autonomy 0.75, solidarity 0.75, wit 0.7, hierarchy -0.4, sedentism 0.55, nontheism 0.6, sincerity 0.6, idealism 0.6, practice:crafts 0.9

### Senna Vaur — Elite:poli_admin

Beliefs: order 0.88, mastery 0.6, community 0.5, truth 0.3, light 0.3, secrecy 0.25

Culture: hierarchy 0.95, solidarity 0.88, honor 0.82, pragmatism 0.78, prowess 0.78, meritocracy 0.72, sedentism 0.85, erudition 0.65, luminary_worship 0.5, nontheism 0.4, practice:ritual 0.75, practice:lit 0.65

### Thessal Dour — Artisan:engineer

Beliefs: secrecy 0.8, silence 0.6, mastery 0.65, order 0.15, truth 0.2, void 0.35

Culture: erudition 0.92, patience 0.75, autonomy 0.75, tenacity 0.8, humility 0.55, hierarchy 0.3, sedentism 0.75, nontheism 0.45, luminary_worship 0.2, practice:crafts 0.88

### Veth Sarai — Scholar:clergy

Beliefs: silence 0.75, order 0.7, truth 0.5, memory 0.45, sacrifice 0.4, growth 0.25

Culture: demiurge_worship 0.92, luminary_worship 0.78, sedentism 0.85, humility 0.82, patience 0.78, sincerity 0.6, solidarity 0.7, folk_wisdom 0.6, moderation 0.55, indulgence -0.4, practice:ritual 0.95, practice:music 0.72
