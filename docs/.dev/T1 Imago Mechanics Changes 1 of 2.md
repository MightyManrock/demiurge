# T1 Imago Mechanics Changes — Eight Domains

Comparison of Tier-1 Imago node mechanics between the hardcoded defaults in `utilities/imago_registry.py` (the **former** values) and the live data in `core/core.db` (the **current** values).

Domain modifiers (`domain:xxx`) are unchanged in all cases and are omitted from the diff rows to keep the focus on culture/practice/religion tag changes.

---

## Change

### change:t1:wheel — *The Turning Wheel*
| Tag | Former | Current |
|---|---|---|
| `domain:change` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:mastery` | −0.10 | −0.10 |
| `religion:animism` | **+0.20** | *(removed)* |
| `values:humility` | **+0.20** | *(removed)* |
| `religion:demiurge_worship` | *(absent)* | **+0.10** |
| `practice:agriculture` | *(absent)* | **+0.06** |
| `values:sincerity` | *(absent)* | **+0.20** |

### change:t1:wall — *The Crumbling Wall*
| Tag | Former | Current |
|---|---|---|
| `domain:change` | +0.30 | +0.30 |
| `domain:void` | +0.08 | +0.08 |
| `domain:community` | −0.10 | −0.10 |
| `practice:nomadism` | +0.10 | +0.10 |
| `religion:nontheism` | +0.10 | +0.10 |
| `values:pragmatism` | **+0.15** | *(removed)* |
| `values:adaptability` | *(absent)* | **+0.15** |

---

## Community

### community:t1:hearth — *The Hearth and Home*
| Tag | Former | Current |
|---|---|---|
| `domain:community` | +0.35 | +0.35 |
| `domain:fire` | +0.10 | +0.10 |
| `domain:decay` | −0.10 | −0.10 |
| `practice:sedentism` | +0.20 | +0.20 |
| `values:patience` | **+0.15** | *(removed)* |
| `values:charity` | *(absent)* | **+0.15** |
| `religion:ancestor_worship` | *(absent)* | **+0.12** |

### community:t1:table — *The Shared Table*
| Tag | Former | Current |
|---|---|---|
| `domain:community` | +0.30 | +0.30 |
| `domain:water` | +0.10 | +0.10 |
| `domain:secrecy` | −0.10 | −0.10 |
| `structure:cooperation` | **+0.15** | *(removed)* |
| `values:humility` | **+0.15** | *(removed)* |
| `values:sincerity` | *(absent)* | **+0.25** |
| `practice:monogamy` | *(absent)* | **+0.10** |
| `religion:demiurge_worship` | *(absent)* | **+0.10** |

---

## Conflict

### conflict:t1:banner — *The Broken Banner*
| Tag | Former | Current |
|---|---|---|
| `domain:conflict` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:memory` | −0.10 | −0.10 |
| `structure:competition` | **+0.15** | *(removed)* |
| `values:tenacity` | +0.20 | +0.20 |
| `values:sincerity` | +0.10 | +0.10 |
| `religion:nontheism` | *(absent)* | **+0.08** |

### conflict:t1:rival — *The Rival's Eye*
| Tag | Former | Current |
|---|---|---|
| `domain:conflict` | +0.30 | +0.30 |
| `domain:mastery` | +0.08 | +0.08 |
| `domain:water` | −0.10 | −0.10 |
| `structure:competition` | **+0.20** | *(removed)* |
| `values:ambition` | +0.20 | +0.20 |
| `religion:nontheism` | *(absent)* | **+0.07** |
| `values:folk_wisdom` | *(absent)* | **+0.08** |

---

## Decay

### decay:t1:leaf — *The Fallen Leaf*
| Tag | Former | Current |
|---|---|---|
| `domain:decay` | +0.35 | +0.35 |
| `domain:silence` | +0.10 | +0.10 |
| `domain:order` | −0.10 | −0.10 |
| `religion:animism` | +0.20 | +0.20 |
| `values:humility` | +0.20 | +0.20 |

*(No changes.)*

### decay:t1:rust — *The Coming Rust*
| Tag | Former | Current |
|---|---|---|
| `domain:decay` | +0.30 | +0.30 |
| `domain:truth` | +0.10 | +0.10 |
| `domain:mastery` | −0.10 | −0.10 |
| `techno:luddism` | **+0.10** | *(removed)* |
| `values:humility` | **+0.15** | *(removed)* |
| `values:folk_wisdom` | +0.15 | +0.15 |
| `practice:foraging` | *(absent)* | **+0.08** |
| `religion:nontheism` | *(absent)* | **+0.12** |

---

## Fire

### fire:t1:flame — *The Holy Flame*
| Tag | Former | Current |
|---|---|---|
| `domain:fire` | +0.35 | +0.35 |
| `domain:light` | +0.10 | +0.10 |
| `domain:memory` | −0.10 | −0.10 |
| `religion:animism` | **+0.20** | *(removed)* |
| `values:idealism` | **+0.15** | *(removed)* |
| `values:prosperity` | *(absent)* | **+0.15** |
| `religion:luminary_worship` | *(absent)* | **+0.20** |
| `practice:sedentism` | *(absent)* | **+0.08** |

### fire:t1:pyre — *The Billowing Pyre*
| Tag | Former | Current |
|---|---|---|
| `domain:fire` | +0.30 | +0.30 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:growth` | −0.10 | −0.10 |
| `religion:animism` | **+0.15** | *(removed)* |
| `values:tenacity` | **+0.10** | *(removed)* |
| `religion:void_worship` | *(absent)* | **+0.15** |
| `values:moderation` | *(absent)* | **+0.15** |

---

## Growth

### growth:t1:seedling — *The Eager Seedling*
| Tag | Former | Current |
|---|---|---|
| `domain:growth` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:memory` | −0.10 | −0.10 |
| `religion:animism` | +0.20 | +0.20 |
| `values:idealism` | **+0.15** | *(removed)* |
| `values:charity` | *(absent)* | **+0.15** |
| `practice:agriculture` | *(absent)* | **+0.08** |

### growth:t1:cycle — *The Cycle of Return*
| Tag | Former | Current |
|---|---|---|
| `domain:growth` | +0.30 | +0.30 |
| `domain:truth` | +0.10 | +0.10 |
| `domain:conflict` | −0.10 | −0.10 |
| `practice:agriculture` | +0.20 | +0.20 |
| `values:humility` | +0.15 | +0.15 |
| `values:prosperity` | *(absent)* | **+0.08** |

---

## Light

### light:t1:rays — *The First Rays*
| Tag | Former | Current |
|---|---|---|
| `domain:light` | +0.35 | +0.35 |
| `domain:water` | +0.10 | +0.10 |
| `domain:decay` | −0.10 | −0.10 |
| `religion:animism` | +0.20 | +0.20 |
| `values:idealism` | +0.15 | +0.15 |
| `practice:foraging` | *(absent)* | **+0.08** |

### light:t1:beacon — *The Beacon*
| Tag | Former | Current |
|---|---|---|
| `domain:light` | +0.30 | +0.30 |
| `domain:community` | +0.10 | +0.10 |
| `domain:silence` | −0.10 | −0.10 |
| `structure:cooperation` | **+0.15** | *(removed)* |
| `values:honesty` | +0.15 | +0.15 |
| `values:charity` | *(absent)* | **+0.12** |
| `religion:luminary_worship` | *(absent)* | **+0.08** |

---

## Mastery

### mastery:t1:anvil — *The Struck Anvil*
| Tag | Former | Current |
|---|---|---|
| `domain:mastery` | +0.35 | +0.35 |
| `domain:memory` | +0.10 | +0.10 |
| `domain:void` | −0.10 | −0.10 |
| `practice:sedentism` | +0.15 | +0.15 |
| `values:tenacity` | **+0.20** | *(removed)* |
| `values:ambition` | *(absent)* | **+0.20** |
| `religion:demiurge_worship` | *(absent)* | **+0.15** |

### mastery:t1:talent — *The Natural Talent*
| Tag | Former | Current |
|---|---|---|
| `domain:mastery` | +0.30 | +0.30 |
| `domain:light` | +0.10 | +0.10 |
| `domain:decay` | −0.10 | −0.10 |
| `structure:competition` | **+0.15** | *(removed)* |
| `values:idealism` | **+0.20** | *(removed)* |
| `values:indulgence` | *(absent)* | **+0.15** |
| `values:erudition` | *(absent)* | **+0.12** |
| `religion:nontheism` | *(absent)* | **+0.10** |

---

## Summary of Patterns

**Tags consistently removed across these changes:**
- `structure:competition` — stripped from Conflict (both), Mastery:talent
- `structure:cooperation` — stripped from Community:table, Light:beacon
- `religion:animism` — stripped from Change:wheel, Fire:flame, Fire:pyre (but retained on Growth:seedling, Decay:leaf, Light:rays)
- `values:idealism` — stripped from Fire:flame, Growth:seedling, Mastery:talent (but retained on Light:rays)
- `values:pragmatism` — stripped from Change:wall
- `values:humility` — stripped from Community:table, Decay:rust (but retained on Decay:leaf, Growth:cycle)
- `techno:luddism` — stripped from Decay:rust

**Tags newly introduced across these changes:**
- `religion:demiurge_worship` — added to Change:wheel, Community:table, Decay:rust, Mastery:anvil
- `religion:luminary_worship` — added to Fire:flame, Light:beacon
- `religion:void_worship` — added to Conflict:rival, Fire:pyre
- `religion:nontheism` — added to Conflict:banner, Mastery:talent
- `religion:ancestor_worship` — added to Community:hearth
- `values:charity` — added to Community:hearth, Growth:seedling, Light:beacon
- `values:sincerity` — added to Change:wheel, Community:table
- `values:adaptability` — added to Change:wall
- `values:ambition` — added to Mastery:anvil
- `values:indulgence` — added to Mastery:talent
- `values:erudition` — added to Mastery:talent
- `values:prosperity` — added to Fire:flame, Growth:cycle
- `values:moderation` — added to Fire:pyre
- `values:folk_wisdom` — added to Conflict:rival
- `practice:agriculture` — added to Change:wheel, Growth:seedling
- `practice:foraging` — added to Decay:rust, Light:rays
- `practice:sedentism` — added to Fire:flame
- `practice:monogamy` — added to Community:table, Fire:pyre
