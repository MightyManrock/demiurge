# Mortal Skill System — Initial Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `skill_tags` field to `NotableMortal`, gate civilian collect/sell actions on `skill:trade` presence, scale action scores by skill rating, and seed Durenn Vail with `skill:trade: 0.8`.

**Architecture:** Skills are stored as `dict[str, float]` on `NotableMortal`, parallel to the existing `culture_tags` and `belief_tags` fields. Civilian action evaluation checks skill presence before scoring collect/sell candidates, and multiplies scores by skill rating. Empty `skill_tags` (`{}`) means the skill system is not engaged for this mortal — all actions remain ungated (legacy compatibility). Non-empty `skill_tags` means the mortal is in the skill system: only actions matching held skills are available.

**Tech Stack:** Python/Pydantic, SQLite, pytest/MagicMock

---

## File Map

| File | Change |
|------|--------|
| `core/universe_core.py` | Add `skill_tags: dict[str, float]` field to `NotableMortal` |
| `core/scenario_schema.sql` | Add `skill_tags TEXT NOT NULL DEFAULT '{}'` to mortals table |
| `utilities/scenario_loader.py` | Load `skill_tags` from DB row in `_load_mortals()` |
| `utilities/scenario_exporter.py` | Export `skill_tags` in mortal INSERT |
| `logic/civilian_agent_logic.py` | Add `_has_skill()` / `_skill_rating()` helpers; gate and scale collect/sell scores |
| `tests/test_civilian_logic.py` | Update `_mortal()` helper; add skill gating tests |
| `scenarios/wardens_compact.db` | Seed Durenn Vail with `{"skill:trade": 0.8}` |

---

### Task 1: Add `skill_tags` to the data model, schema, loader, and exporter

**Files:**
- Modify: `core/universe_core.py` (~line 674)
- Modify: `core/scenario_schema.sql` (~line 280, mortals table)
- Modify: `utilities/scenario_loader.py` (~line 802)
- Modify: `utilities/scenario_exporter.py` (~line 522)

- [ ] **Step 1: Add field to `NotableMortal`**

In `core/universe_core.py`, after line 674 (`culture_tags: dict[str, float]...`), add:

```python
    skill_tags: dict[str, float] = Field(default_factory=dict)
```

- [ ] **Step 2: Add column to schema**

In `core/scenario_schema.sql`, find the `mortals` table. After the `culture_tags TEXT` column line, add:

```sql
    skill_tags          TEXT    NOT NULL DEFAULT '{}',
```

- [ ] **Step 3: Load from DB**

In `utilities/scenario_loader.py` `_load_mortals()`, after line 802 (`culture_tags=_jd(...)`), add:

```python
            skill_tags=_jd(row.get("skill_tags", "{}")),
```

- [ ] **Step 4: Export to DB**

In `utilities/scenario_exporter.py` `_write_mortals()`, the INSERT at line 522 currently has 43 columns and 43 values.

Add `skill_tags` to the column list after `culture_tags`:
```python
               (id, name, description, civilization_id, role, status,
                species_id, prominence_roles, prominence, visibility,
                belief_tags, personal_tags, status_tags, culture_tags, skill_tags,
                ...
```

Add the value after `_j(m.culture_tags)` in the values tuple:
```python
                _j(m.skill_tags),
```

- [ ] **Step 5: Write a round-trip test**

In `tests/test_civilian_logic.py`, add after the existing imports:

```python
from core.universe_core import NotableMortal
```

Add this test at the end of the file:

```python
def test_notable_mortal_skill_tags_default_empty():
    m = NotableMortal(name="Test", home_location="00000000-0000-0000-0000-000000000001",
                      current_location="00000000-0000-0000-0000-000000000001")
    assert m.skill_tags == {}


def test_notable_mortal_skill_tags_roundtrip():
    m = NotableMortal(name="Test", home_location="00000000-0000-0000-0000-000000000001",
                      current_location="00000000-0000-0000-0000-000000000001",
                      skill_tags={"skill:trade": 0.8, "skill:craft": 0.4})
    dumped = m.model_dump()
    restored = NotableMortal(**dumped)
    assert restored.skill_tags == {"skill:trade": 0.8, "skill:craft": 0.4}
```

- [ ] **Step 6: Run tests**

```bash
pytest tests/test_civilian_logic.py -v -k "skill_tags"
```

Expected: 2 new tests PASS.

- [ ] **Step 7: Run full suite**

```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 8: Commit**

```bash
git add core/universe_core.py core/scenario_schema.sql utilities/scenario_loader.py utilities/scenario_exporter.py tests/test_civilian_logic.py
git commit -m "feat(skills): add skill_tags field to NotableMortal with schema, loader, exporter"
```

---

### Task 2: Add `_has_skill` and `_skill_rating` helpers + update test fixture

**Files:**
- Modify: `logic/civilian_agent_logic.py` (add two module-level helpers near the top)
- Modify: `tests/test_civilian_logic.py` (update `_mortal()` helper; add helper tests)

- [ ] **Step 1: Write failing tests for the helpers**

Add these tests at the end of `tests/test_civilian_logic.py`:

```python
# ── Skill helpers ─────────────────────────────────────────────────────────────

from logic.civilian_agent_logic import _has_skill, _skill_rating


def test_has_skill_legacy_empty_dict():
    """Empty skill_tags → legacy mode → all actions ungated."""
    m = MagicMock()
    m.skill_tags = {}
    assert _has_skill(m, "skill:trade") is True


def test_has_skill_present():
    m = MagicMock()
    m.skill_tags = {"skill:trade": 0.8}
    assert _has_skill(m, "skill:trade") is True


def test_has_skill_absent_when_skill_system_engaged():
    """Mortal has skills but not this one → blocked."""
    m = MagicMock()
    m.skill_tags = {"skill:craft": 0.7}
    assert _has_skill(m, "skill:trade") is False


def test_skill_rating_legacy():
    m = MagicMock()
    m.skill_tags = {}
    assert _skill_rating(m, "skill:trade") == 1.0


def test_skill_rating_returns_value():
    m = MagicMock()
    m.skill_tags = {"skill:trade": 0.8}
    assert _skill_rating(m, "skill:trade") == pytest.approx(0.8)


def test_skill_rating_zero_for_absent_skill():
    m = MagicMock()
    m.skill_tags = {"skill:craft": 0.7}
    assert _skill_rating(m, "skill:trade") == 0.0
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_civilian_logic.py -v -k "_has_skill or _skill_rating"
```

Expected: ImportError or AttributeError (helpers don't exist yet).

- [ ] **Step 3: Implement helpers in `civilian_agent_logic.py`**

Near the top of `logic/civilian_agent_logic.py`, after the module-level constants but before `evaluate_civilian_action`, add:

```python
def _has_skill(mortal: Any, skill_name: str) -> bool:
    """True if mortal can attempt skill-gated actions for `skill_name`.

    Empty skill_tags means the skill system isn't engaged for this mortal
    (legacy / pre-skill entities). Non-empty skill_tags means the mortal is
    in the skill system and must hold the skill explicitly.
    """
    tags = getattr(mortal, "skill_tags", {}) or {}
    if not tags:
        return True  # legacy: ungated
    return skill_name in tags


def _skill_rating(mortal: Any, skill_name: str) -> float:
    """Skill rating in [0, 1]. Returns 1.0 for legacy (empty skill_tags) mortals.
    Returns 0.0 if skill system is engaged but the skill is absent.
    """
    tags = getattr(mortal, "skill_tags", {}) or {}
    if not tags:
        return 1.0  # legacy: full effectiveness
    return tags.get(skill_name, 0.0)
```

If `Any` is not already imported in that file, add `from typing import Any` (or it may already be present — check imports first).

- [ ] **Step 4: Update the `_mortal()` test fixture**

The existing `_mortal()` helper uses `MagicMock()`, so `m.skill_tags` defaults to a MagicMock object (truthy, `__contains__` returns False). This would break the `_has_skill` legacy check. Fix by setting `skill_tags = {}` explicitly.

In `tests/test_civilian_logic.py`, update `_mortal()` at line 10:

```python
def _mortal(cs, kb=None, fatigue=0.0, assets=None, travel_intent=None, loc_id="loc-A", skill_tags=None):
    m = MagicMock()
    m.civilian_state = cs
    m.knowledge_base = kb or KnowledgeBase()
    m.fatigue = fatigue
    m.assets = assets or []
    m.travel_intent = travel_intent
    m.current_location = loc_id
    m.skill_tags = skill_tags if skill_tags is not None else {}
    return m
```

- [ ] **Step 5: Run helper tests**

```bash
pytest tests/test_civilian_logic.py -v -k "_has_skill or _skill_rating"
```

Expected: all 6 new tests PASS.

- [ ] **Step 6: Run full suite to check no regressions**

```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add logic/civilian_agent_logic.py tests/test_civilian_logic.py
git commit -m "feat(skills): add _has_skill/_skill_rating helpers; update _mortal() fixture"
```

---

### Task 3: Gate collect/sell scores on `skill:trade`; scale by rating

**Files:**
- Modify: `logic/civilian_agent_logic.py` (~lines 384–399)
- Modify: `tests/test_civilian_logic.py` (add gating and scaling tests)

- [ ] **Step 1: Write failing tests**

Add these tests to `tests/test_civilian_logic.py`:

```python
# ── Skill gating: collect and sell ────────────────────────────────────────────

def _kb_with_resource_and_sell(resource_loc_id, sell_loc_id):
    """KnowledgeBase that reports a resource location and a sell location."""
    kb = KnowledgeBase()
    kb.facts.append(ResourceFact(location_id=resource_loc_id, resource_type="ore", yield_per_tick=5))
    kb.facts.append(LocationQualityFact(location_id=sell_loc_id, quality_type="sell", score=0.8))
    return kb


def test_collect_blocked_when_skill_system_engaged_without_trade():
    """Mortal has skills but not skill:trade → collect score = 0 → idle."""
    resource_loc = "loc-A"
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=0.1, pressing_threshold=0.6)],
        inventory=[Resource(resource_type="ore", quantity=0, base_value=10,
                            converts_to="wealth", threshold=1, usable_for=["sell", "collect"])],
    )
    kb = _kb_with_resource_and_sell(resource_loc, "sell-loc")
    mortal = _mortal(cs, kb, loc_id=resource_loc, skill_tags={"skill:craft": 0.9})
    loc = MagicMock()
    loc.collectible_resource = "ore"
    result = evaluate_civilian_action(mortal, _state({resource_loc: loc}), 0)
    assert result != "collect"


def test_collect_allowed_when_skill_trade_present():
    """Mortal with skill:trade → collect proceeds normally."""
    resource_loc = "loc-A"
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=0.1, pressing_threshold=0.6)],
        inventory=[Resource(resource_type="ore", quantity=0, base_value=10,
                            converts_to="wealth", threshold=1, usable_for=["sell", "collect"])],
    )
    kb = _kb_with_resource_and_sell(resource_loc, "sell-loc")
    mortal = _mortal(cs, kb, loc_id=resource_loc, skill_tags={"skill:trade": 0.8})
    loc = MagicMock()
    loc.collectible_resource = "ore"
    result = evaluate_civilian_action(mortal, _state({resource_loc: loc}), 0)
    assert result == "collect"


def test_collect_allowed_legacy_no_skill_tags():
    """Empty skill_tags (legacy) → collect ungated."""
    resource_loc = "loc-A"
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=0.1, pressing_threshold=0.6)],
        inventory=[Resource(resource_type="ore", quantity=0, base_value=10,
                            converts_to="wealth", threshold=1, usable_for=["sell", "collect"])],
    )
    kb = _kb_with_resource_and_sell(resource_loc, "sell-loc")
    mortal = _mortal(cs, kb, loc_id=resource_loc, skill_tags={})
    loc = MagicMock()
    loc.collectible_resource = "ore"
    result = evaluate_civilian_action(mortal, _state({resource_loc: loc}), 0)
    assert result == "collect"


def test_sell_blocked_when_skill_system_engaged_without_trade():
    """Mortal with skill:craft but not skill:trade at a sell location → cannot sell."""
    sell_loc = "loc-sell"
    cs = CivilianAgentState(
        needs=[MortalNeed(name="purpose", satisfaction=0.1, pressing_threshold=0.6)],
        inventory=[Resource(resource_type="ore", quantity=10, base_value=10,
                            converts_to="wealth", threshold=5, usable_for=["sell"])],
    )
    kb = KnowledgeBase()
    kb.facts.append(LocationQualityFact(location_id=sell_loc, quality_type="sell", score=0.8))
    mortal = _mortal(cs, kb, loc_id=sell_loc, skill_tags={"skill:craft": 0.9})
    result = evaluate_civilian_action(mortal, _state(), 0)
    assert result != "sell"
```

- [ ] **Step 2: Run to confirm they fail**

```bash
pytest tests/test_civilian_logic.py -v -k "skill_trade or trade_present or legacy_no_skill or sell_blocked"
```

Expected: 3–4 failures (gating not yet implemented).

- [ ] **Step 3: Apply gating + rating scaling in `evaluate_civilian_action()`**

In `logic/civilian_agent_logic.py`, find the scoring block (~lines 384–399):

```python
    # Sell: follow-through from loaded hold + purpose + status urgency
    _sell_score = (
        _load_fraction
        + urgency.get("purpose", 0.0) * 1.0
        + urgency.get("status",  0.0) * 0.5
    ) if _sellable else 0.0
    if _directive_active and _sell_score > 0:
        _sell_score *= DIRECTIVE_MULTIPLIER

    # Collect: purpose urgency drives it; a small baseline fires on a "might as well" roll.
    _directive_base = MIGHT_AS_WELL_COLLECT_BASE if _might_as_well else 0.0
    _collect_score = (
        (1.0 - _load_fraction) * max(urgency.get("purpose", 0.0), _directive_base)
    ) if not _hold_full else 0.0
    if _directive_active and _collect_score > 0:
        _collect_score *= DIRECTIVE_MULTIPLIER
```

Replace it with:

```python
    # Sell: follow-through from loaded hold + purpose + status urgency
    _sell_score = (
        _load_fraction
        + urgency.get("purpose", 0.0) * 1.0
        + urgency.get("status",  0.0) * 0.5
    ) if _sellable else 0.0
    if _directive_active and _sell_score > 0:
        _sell_score *= DIRECTIVE_MULTIPLIER
    # Skill gate: zero score if trade skill is absent (non-legacy mortals only)
    if _sell_score > 0:
        _sell_score *= _skill_rating(mortal, "skill:trade") if _has_skill(mortal, "skill:trade") else 0.0

    # Collect: purpose urgency drives it; a small baseline fires on a "might as well" roll.
    _directive_base = MIGHT_AS_WELL_COLLECT_BASE if _might_as_well else 0.0
    _collect_score = (
        (1.0 - _load_fraction) * max(urgency.get("purpose", 0.0), _directive_base)
    ) if not _hold_full else 0.0
    if _directive_active and _collect_score > 0:
        _collect_score *= DIRECTIVE_MULTIPLIER
    # Skill gate: zero score if trade skill is absent (non-legacy mortals only)
    if _collect_score > 0:
        _collect_score *= _skill_rating(mortal, "skill:trade") if _has_skill(mortal, "skill:trade") else 0.0
```

- [ ] **Step 4: Run the new skill gating tests**

```bash
pytest tests/test_civilian_logic.py -v -k "skill_trade or trade_present or legacy_no_skill or sell_blocked"
```

Expected: all new tests PASS.

- [ ] **Step 5: Run full suite**

```bash
pytest
```

Expected: all tests pass.

- [ ] **Step 6: Commit**

```bash
git add logic/civilian_agent_logic.py tests/test_civilian_logic.py
git commit -m "feat(skills): gate collect/sell on skill:trade presence; scale scores by rating"
```

---

### Task 4: Migrate the scenario DB and seed Vail's `skill:trade`

**Files:**
- `scenarios/wardens_compact.db` (modified by migration + seeding)

The new `skill_tags` column must be added to the DB before Vail can have skills. The scenario migrator does a load → re-export round-trip, which will automatically write the new column (with default `{}`). Then a short seeding snippet sets Vail's skills.

- [ ] **Step 1: Migrate the scenario DB**

```bash
python main.py --rebuild --scenario
```

Expected: migrator runs without errors. `wardens_compact.db` (and any other scenario DBs) now have a `skill_tags` column defaulting to `{}`.

- [ ] **Step 2: Seed Vail's `skill:trade`**

From the repo root (with virtualenv active), run:

```bash
python - <<'EOF'
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario

state = load_scenario("scenarios/wardens_compact.db")
vail = next(m for m in state.mortals.values() if m.name == "Durenn Vail")
vail.skill_tags = {"skill:trade": 0.8}
export_scenario(state, "scenarios/wardens_compact.db")
print(f"Seeded skill:trade = {vail.skill_tags['skill:trade']} on {vail.name}")
EOF
```

Expected output:
```
Seeded skill:trade = 0.8 on Durenn Vail
```

- [ ] **Step 3: Verify Vail's skills in the DB**

```bash
python -c "
import sqlite3, json
conn = sqlite3.connect('scenarios/wardens_compact.db')
row = conn.execute(\"SELECT skill_tags FROM mortals WHERE name='Durenn Vail'\").fetchone()
print('Vail skill_tags:', json.loads(row[0]))
conn.close()
"
```

Expected:
```
Vail skill_tags: {'skill:trade': 0.8}
```

- [ ] **Step 4: Commit**

```bash
git add scenarios/wardens_compact.db
git commit -m "data: seed Durenn Vail with skill:trade 0.8 in wardens_compact scenario"
```

---

### Task 5: End-to-end verification

- [ ] **Step 1: Run autoplay**

```bash
python main.py --autoplay
```

Watch for:
- Vail collecting and selling resources as normal (skill:trade present → ungated at 0.8 rating)
- No Python errors or exceptions
- Trade narrative events appearing in the log

- [ ] **Step 2: Sanity-check a hypothetical no-skill mortal (optional smoke test)**

Only if there are other civilian mortals in the scenario: confirm they still function (they should, via the legacy `{}` bypass).

- [ ] **Step 3: Run full test suite one final time**

```bash
pytest -v
```

Expected: all tests pass.

---

## Out of Scope (follow-up work)

- **Circumstances modifier** (`effective_skill = rating × circumstances`): deferred. Circumstances = 1.0 for now.
- **Trait modulation** (`values:pragmatism` raises threshold, `values:tenacity` lowers it): deferred. Currently skill rating directly scales scores without trait adjustment.
- **Sell quality contribution**: deferred. Skill rating currently affects willingness (score) only, not execution quality (credits per unit).
- **`skill:craft`, `skill:labor`, etc.**: other skills remain unimplemented until needed.
- **`skill:trade` on additional mortals**: Vail is the test case. Other mortals get skills when their civilian_state is wired up.

---

## Verification Checklist

- [ ] `pytest` — all tests green
- [ ] `python main.py --autoplay` — runs 50 ticks without errors; Vail trades
- [ ] `python main.py` — TUI launches; Vail's detail tab shows skill_tags if rendered (no crash)
