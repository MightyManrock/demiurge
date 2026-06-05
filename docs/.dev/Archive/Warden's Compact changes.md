# Warden's Compact — Planned Changes

## Pop Occupation Redesign

Pops gain a canonical **occupation** sub-field within their stratum. `priest` stratum is replaced by `scholar`, with `clergy` as one of its occupation types.

Sizes are logarithmic. Beliefs and culture tags use short names (prefix stripped). Civ baseline: beliefs `order 0.8, mastery 0.5`; culture `sedentism 0.9, hierarchy 0.85, industrialism 0.8, commerce 0.75, diplomacy 0.7, science 0.65, luminary_worship 0.6, ancestor_worship 0.5, pragmatism 0.65, ambition 0.55, prosperity 0.45`.

---

### Neran Surface

| Stratum  | Occupation   | Size | Notable Mortal | Domain Beliefs                                         | Cultural Traits                                                                                                                                                                              |
| -------- | ------------ | ---- | -------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Elite    | poli_admin   | 5.0  | Senna Vaur     | order 0.9, mastery 0.55, community 0.3, truth 0.25     | hierarchy 0.9, diplomacy 0.85, sedentism 0.8, ambition 0.7, pragmatism 0.65, commerce 0.55, luminary_worship 0.5, prosperity 0.4, nontheism 0.35, ancestor_worship 0.2                       |
| Scholar  | scientist    | 6.5  |                | truth 0.7, mastery 0.65, order 0.4, change 0.3         | science 0.9, erudition 0.8, sedentism 0.75, industrialism 0.65, pragmatism 0.6, nontheism 0.55, ambition 0.5, luminary_worship 0.2, ancestor_worship 0.05                                    |
| Scholar  | academic     | 6.2  |                | truth 0.65, mastery 0.5, order 0.45, memory 0.3        | erudition 0.9, science 0.85, sedentism 0.8, patience 0.55, pragmatism 0.45, ancestor_worship 0.4, humility 0.4, nontheism 0.4, luminary_worship 0.3                                          |
| Scholar  | clergy       | 4.5  | Veth Sarai     | order 0.7, silence 0.55, truth 0.45, memory 0.35       | luminary_worship 0.85, ancestor_worship 0.7, sedentism 0.8, humility 0.75, patience 0.65, demiurge_worship 0.5, sincerity 0.5, hierarchy 0.55                                                |
| Merchant | trader       | 6.7  | Durenn Vail    | order 0.65, community 0.6, mastery 0.4, change 0.3     | commerce 0.9, prosperity 0.8, diplomacy 0.75, pragmatism 0.65, nontheism 0.6, hierarchy 0.55, sedentism 0.5, indulgence 0.45, adaptability 0.4, luminary_worship 0.35, ancestor_worship 0.15 |
| Merchant | executive    | 6.5  |                | order 0.75, mastery 0.55, community 0.3, change 0.2    | commerce 0.8, hierarchy 0.8, ambition 0.75, pragmatism 0.7, sedentism 0.75, prosperity 0.6, diplomacy 0.6,  nontheism 0.45, luminary_worship 0.4, indulgence 0.35, ancestor_worship 0.25     |
| Artisan  | engineer     | 7.5  | Thessal Dour   | mastery 0.75, order 0.5, change 0.4, truth 0.3         | industrialism 0.9, science 0.85, sedentism 0.8, nontheism 0.65, erudition 0.7, pragmatism 0.6, ambition 0.5, tenacity 0.4, luminary_worship 0.25, ancestor_worship 0.2                       |
| Artisan  | technician   | 7.8  | Orryn Vel      | mastery 0.7, change 0.45, order 0.4, conflict 0.25     | industrialism 0.9, science 0.75, sedentism 0.8, pragmatism 0.6, adaptability 0.55, luminary_worship 0.5, nontheism 0.5, tenacity 0.45, wit 0.35, ancestor_worship 0.3                        |
| Common   | professional | 8.2  |                | order 0.75, mastery 0.45, community 0.35               | sedentism 0.9, hierarchy 0.75, commerce 0.65, science 0.6, luminary_worship 0.55, pragmatism 0.65, prosperity 0.5, ambition 0.4, nontheism 0.4, ancestor_worship 0.25                        |
| Common   | service      | 9.0  | Maeva Sorn     | order 0.7, community 0.5, silence 0.35, memory 0.3     | sedentism 0.9, hierarchy 0.75, luminary_worship 0.7, ancestor_worship 0.65, commerce 0.6, pragmatism 0.55, folk_wisdom 0.5, humility 0.4, nontheism 0.05                                     |
| Common   | labor        | 8.5  |                | order 0.7, community 0.5, mastery 0.4, sacrifice 0.25  | sedentism 0.9, industrialism 0.85, luminary_worship 0.75, hierarchy 0.7, tenacity 0.6, folk_wisdom 0.55, ancestor_worship 0.55, pragmatism 0.5                                               |
| Warrior  | officer      | 4.0  |                | order 0.8, mastery 0.55, conflict 0.5, sacrifice 0.25  | hierarchy 0.9, sedentism 0.75, ambition 0.7, pragmatism 0.65, tenacity 0.6, industrialism 0.65, diplomacy 0.45, luminary_worship 0.45, ancestor_worship 0.4                                  |
| Warrior  | soldier      | 5.5  |                | order 0.75, conflict 0.55, mastery 0.4, sacrifice 0.35 | hierarchy 0.8, sedentism 0.8, industrialism 0.7, tenacity 0.65, ancestor_worship 0.6, luminary_worship 0.55, pragmatism 0.5, folk_wisdom 0.4                                                 |

---

### Neran Orbital Ring

| Stratum | Occupation | Size | Notable Mortal | Domain Beliefs                                         | Cultural Traits                                                                                                                                                            |
| ------- | ---------- | ---- | -------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Warrior | officer    | 4.0  | Karath Omn     | mastery 0.8, conflict 0.65, order 0.55, sacrifice 0.3  | hierarchy 0.9, ambition 0.85, tenacity 0.7, industrialism 0.75, pragmatism 0.6, sedentism 0.75, nontheism 0.5, ancestor_worship 0.35, luminary_worship 0.4                 |
| Warrior | soldier    | 3.5  |                | order 0.7, conflict 0.5, mastery 0.45, sacrifice 0.35  | hierarchy 0.8, industrialism 0.75, sedentism 0.8, tenacity 0.7, pragmatism 0.55, luminary_worship 0.5, ancestor_worship 0.5, folk_wisdom 0.4, nontheism 0.25               |
| Scholar | scientist  | 4.2  |                | truth 0.65, mastery 0.75, order 0.5, change 0.35       | science 0.9, industrialism 0.8, erudition 0.75, hierarchy 0.7, nontheism 0.7, ambition 0.6, pragmatism 0.55, tenacity 0.45, luminary_worship 0.15, ancestor_worship 0.05   |
| Artisan | engineer   | 4.5  |                | mastery 0.8, order 0.55, change 0.4, conflict 0.3      | industrialism 0.9, science 0.8, hierarchy 0.75, tenacity 0.65, ambition 0.65, pragmatism 0.55, nontheism 0.5, erudition 0.5, luminary_worship 0.4, ancestor_worship 0.1    |
| Artisan | technician | 5.2  |                | mastery 0.65, order 0.5, change 0.35, community 0.3    | industrialism 0.85, science 0.7, hierarchy 0.7, sedentism 0.75, tenacity 0.6, pragmatism 0.6, luminary_worship 0.45, folk_wisdom 0.4, nontheism 0.35, ancestor_worship 0.2 |
| Common  | service    | 4.8  |                | order 0.65, community 0.5, mastery 0.35                | sedentism 0.8, hierarchy 0.75, industrialism 0.7, luminary_worship 0.6, tenacity 0.55, pragmatism 0.55, ancestor_worship 0.35, folk_wisdom 0.4, nontheism 0.2              |
| Common  | labor      | 3.8  |                | order 0.65, community 0.45, mastery 0.4, sacrifice 0.3 | industrialism 0.85, sedentism 0.8, hierarchy 0.7, luminary_worship 0.65, tenacity 0.65, folk_wisdom 0.5, pragmatism 0.5, ancestor_worship 0.4, nontheism 0.05              |
