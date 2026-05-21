# T1 Imago Mechanics Changes — Eight Domains

Comparison of Tier-1 Imago node mechanics between the hardcoded defaults in `utilities/imago_registry.py` (the **former** values) and the live data in `core/core.db` (the **current** values).

Domain modifiers (`domain:xxx`) are unchanged in all cases and are omitted from the diff rows to keep the focus on culture/practice/religion tag changes.

---

## Memory

### memory:t1:tale — *The Elder's Tale*
| Tag | Former | Current |
|---|---|---|
| `domain:memory` | +0.35 | +0.35 |
| `domain:fire` | +0.10 | +0.10 |
| `domain:mastery` | −0.10 | −0.10 |
| `religion:ancestor_worship` | **+0.20** | **+0.15** |
| `values:sincerity` | **+0.15** | **+0.20** |

### memory:t1:scar — *The Old Scar*
| Tag | Former | Current |
|---|---|---|
| `domain:memory` | +0.30 | +0.30 |
| `domain:conflict` | +0.10 | +0.10 |
| `domain:growth` | −0.10 | −0.10 |
| `structure:competition` | **+0.10** | *(removed)* |
| `values:tenacity` | **+0.20** | **+0.10** |
| `values:folk_wisdom` | +0.10 | +0.10 |
| `religion:nontheism` | *(absent)* | **+0.07** |

---

## Order

### order:t1:gauntlet — *The Clenched Gauntlet*
| Tag | Former | Current |
|---|---|---|
| `domain:order` | +0.35 | +0.35 |
| `domain:fire` | +0.08 | +0.08 |
| `domain:memory` | −0.10 | −0.10 |
| `structure:hierarchy` | +0.20 | +0.20 |
| `values:tenacity` | **+0.15** | *(removed)* |
| `values:honesty` | +0.10 | +0.10 |
| `religion:luminary_worship` | *(absent)* | **+0.10** |

### order:t1:warden — *The Warden's Mark*
| Tag | Former | Current |
|---|---|---|
| `domain:order` | +0.30 | +0.30 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:truth` | −0.10 | −0.10 |
| `practice:sedentism` | +0.15 | +0.15 |
| `values:moderation` | **+0.15** | **+0.10** |
| `religion:demiurge_worship` | *(absent)* | **+0.08** |

---

## Sacrifice

### sacrifice:t1:gift — *The Offered Gift*
| Tag | Former | Current |
|---|---|---|
| `domain:sacrifice` | +0.35 | +0.35 |
| `domain:growth` | +0.10 | +0.10 |
| `domain:secrecy` | −0.10 | −0.10 |
| `religion:luminary_worship` | **+0.20** | **+0.10** |
| `values:sincerity` | +0.15 | +0.15 |
| `values:charity` | *(absent)* | **+0.08** |

### sacrifice:t1:fast — *The Pious Fast*
| Tag | Former | Current |
|---|---|---|
| `domain:sacrifice` | +0.30 | +0.30 |
| `domain:void` | +0.10 | +0.10 |
| `domain:growth` | −0.10 | −0.10 |
| `religion:luminary_worship` | +0.10 | +0.10 |
| `values:patience` | **+0.20** | *(removed)* |
| `values:moderation` | **+0.15** | **+0.12** |
| `values:idealism` | *(absent)* | **+0.07** |

---

## Secrecy

### secrecy:t1:confidence — *The Kept Confidence*
| Tag | Former | Current |
|---|---|---|
| `domain:secrecy` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:conflict` | −0.10 | −0.10 |
| `structure:cooperation` | **+0.15** | **+0.08** |
| `values:sincerity` | +0.15 | +0.15 |
| `religion:demiurge_worship` | *(absent)* | **+0.10** |

### secrecy:t1:room — *The Locked Room*
| Tag | Former | Current |
|---|---|---|
| `domain:secrecy` | +0.30 | +0.30 |
| `domain:memory` | +0.10 | +0.10 |
| `domain:order` | −0.10 | −0.10 |
| `relations:isolationism` | **+0.15** | **+0.08** |
| `values:patience` | **+0.20** | *(removed)* |
| `religion:nontheism` | *(absent)* | **+0.07** |
| `values:wit` | *(absent)* | **+0.10** |

---

## Silence

### silence:t1:veil — *The Masked Face*
| Tag | Former | Current |
|---|---|---|
| `domain:silence` | +0.35 | +0.35 |
| `domain:void` | +0.10 | +0.10 |
| `domain:sacrifice` | −0.10 | −0.10 |
| `religion:nontheism` | +0.15 | +0.15 |
| `values:patience` | +0.20 | +0.20 |

*(No changes.)*

### silence:t1:pool — *The Still Pool*
| Tag | Former | Current |
|---|---|---|
| `domain:silence` | +0.30 | +0.30 |
| `domain:memory` | +0.08 | +0.08 |
| `domain:growth` | −0.10 | −0.10 |
| `relations:isolationism` | **+0.15** | **+0.08** |
| `values:humility` | **+0.20** | *(removed)* |
| `values:moderation` | *(absent)* | **+0.10** |
| `religion:void_worship` | *(absent)* | **+0.07** |

---

## Truth

### truth:t1:compass — *The Weathered Compass*
| Tag | Former | Current |
|---|---|---|
| `domain:truth` | +0.35 | +0.35 |
| `domain:water` | +0.10 | +0.10 |
| `domain:void` | −0.10 | −0.10 |
| `values:honesty` | +0.20 | +0.20 |
| `values:patience` | **+0.15** | *(removed)* |
| `practice:nomadism` | *(absent)* | **+0.08** |
| `religion:demiurge_worship` | *(absent)* | **+0.07** |

### truth:t1:glint — *The Glint of Truth*
| Tag | Former | Current |
|---|---|---|
| `domain:truth` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:change` | −0.10 | −0.10 |
| `values:honesty` | **+0.20** | *(removed)* |
| `values:sincerity` | **+0.15** | *(removed)* |
| `values:erudition` | *(absent)* | **+0.15** |
| `values:idealism` | *(absent)* | **+0.12** |
| `religion:luminary_worship` | *(absent)* | **+0.10** |

---

## Void

### void:t1:quarter — *The Empty Quarter*
| Tag | Former | Current |
|---|---|---|
| `domain:void` | +0.35 | +0.35 |
| `domain:truth` | +0.10 | +0.10 |
| `domain:conflict` | −0.10 | −0.10 |
| `religion:nontheism` | +0.15 | +0.15 |
| `values:patience` | +0.20 | +0.20 |

*(No changes.)*

### void:t1:between — *The Nothing in Between*
| Tag | Former | Current |
|---|---|---|
| `domain:void` | +0.30 | +0.30 |
| `domain:change` | +0.10 | +0.10 |
| `domain:order` | −0.10 | −0.10 |
| `religion:animism` | +0.15 | +0.15 |
| `values:adaptability` | **+0.20** | **+0.07** |
| `values:humility` | *(absent)* | **+0.12** |

---

## Water

### water:t1:current — *The Steady Current*
| Tag | Former | Current |
|---|---|---|
| `domain:water` | +0.35 | +0.35 |
| `domain:sacrifice` | +0.10 | +0.10 |
| `domain:order` | −0.10 | −0.10 |
| `practice:nomadism` | +0.10 | +0.10 |
| `values:patience` | +0.20 | +0.20 |
| `values:adaptability` | +0.15 | +0.15 |

*(No changes.)*

### water:t1:depths — *The Still Depths*
| Tag                      | Former     | Current     |
| ------------------------ | ---------- | ----------- |
| `domain:water`           | +0.30      | +0.30       |
| `domain:silence`         | +0.10      | +0.10       |
| `domain:truth`           | −0.10      | −0.10       |
| `relations:isolationism` | **+0.15**  | *(removed)* |
| `values:humility`        | **+0.20**  | **+0.12**   |
| `religion:void_worship`  | *(absent)* | **+0.07**   |
| `values:patience`        | *(absent)* | **+0.08**   |

---

## Summary of Patterns

**Tags consistently removed across these changes:**
- `structure:competition` — stripped from Memory:scar
- `structure:cooperation` — reduced (not removed) on Secrecy:confidence
- `relations:isolationism` — reduced on Secrecy:room, Silence:pool; fully removed from Water:depths
- `values:patience` — stripped from Sacrifice:fast, Secrecy:room, Truth:compass
- `values:humility` — stripped from Silence:pool, reduced on Water:depths
- `values:tenacity` — stripped from Order:gauntlet, reduced on Memory:scar
- `values:honesty` and `values:sincerity` — both stripped from Truth:glint (replaced by erudition/idealism framing)

**Tags newly introduced across these changes:**
- `religion:demiurge_worship` — added to Order:warden, Secrecy:confidence, Truth:compass
- `religion:luminary_worship` — added to Order:gauntlet, Truth:glint
- `religion:void_worship` — added to Silence:pool, Water:depths
- `religion:nontheism` — added to Memory:scar, Secrecy:room
- `values:charity` — added to Sacrifice:gift
- `values:idealism` — added to Sacrifice:fast, Truth:glint
- `values:erudition` — added to Truth:glint
- `values:wit` — added to Secrecy:room
- `values:humility` — added to Void:between
- `values:moderation` — added to Silence:pool
- `practice:nomadism` — added to Truth:compass
