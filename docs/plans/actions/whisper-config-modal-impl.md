# WhisperConfigModal Implementation Plan

> **STATUS: COMPLETE** — All tasks implemented and pushed to `action-redesign` branch (2026-05-25).

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-step whisper wizard (mortal → domain → imago) with a single unified `WhisperConfigModal` that shows all three panels at once.

**Architecture:** Extract a reusable `ImagoTreeGrid` widget from `ImagoTreeModal`, build `WhisperConfigModal` using that widget plus a mortal `ListView` and a 2×8 domain grid, then wire up an early-return whisper block in `_build_intent`. Existing modals stay untouched; the old whisper flow in `_build_intent_params` is left in place until the full cleanup pass.

**Tech Stack:** Python 3, Pydantic v2, Textual 8.2.7. No tests — `python main.py --autoplay` is the regression check.

---

## File Map

| File | Change |
|---|---|
| `ui/widgets.py` | Add `ImagoTreeGrid` widget class |
| `ui/modals.py` | Update `ImagoTreeModal` to use `ImagoTreeGrid`; add `WhisperConfigModal` |
| `ui/styles.tcss` | Rename `#imago-grid` → `.imago-tree-inner-grid`; add `WhisperConfigModal` styles; add `.continue-ready` |
| `ui/ui.py` | Add whisper early-return block in `_build_intent`; add `WhisperConfigModal` to imports |

---

## Task 1: Add `ImagoTreeGrid` to `ui/widgets.py`

**Files:**
- Modify: `ui/widgets.py` (after `ImagoCell` class, ~line 295)

This widget encapsulates all tree-rendering logic so `WhisperConfigModal` can embed it inline and call `load_tree()` to swap domains dynamically.

- [ ] **Step 1: Add imports to `widgets.py`**

The new widget needs `Grid` from `textual.containers`, `_get_lum_domain_context` from `ui.display`, and `get_registry as get_domain_registry` from `utilities.domain_registry`. Add these to the existing import blocks:

In the `from textual.containers import` line (currently `Horizontal, VerticalScroll, Vertical`), add `Grid`:
```python
from textual.containers import Grid, Horizontal, VerticalScroll, Vertical
```

In the `from ui.display import (...)` block, add `_get_lum_domain_context`:
```python
from ui.display import (
    _personality_label, _format_beliefs, _format_culture, _prominence_label,
    _name_for_id, _name_link_for_id, _short_tag, _trait_color, _pop_stratum_label,
    _format_beliefs_markup, _format_culture_markup, _color_short_tag,
    display_briefing, _lines_to_text, _get_lum_domain_context,
)
```

Add after `from utilities.imago_registry import get_registry as get_imago_registry`:
```python
from utilities.domain_registry import get_registry as get_domain_registry
```

- [ ] **Step 2: Add `ImagoTreeGrid` class after `ImagoCell` (~line 295)**

```python
# ─────────────────────────────────────────
# Imago tree grid widget (reusable)
# ─────────────────────────────────────────

class ImagoTreeGrid(Widget):
    """
    Embeddable 3×4 imago tree grid for one domain's imagoes.
    Arrow-key navigation built in. ImagoCell.Selected and ImagoCell.Focused
    bubble up to the host screen.
    Call load_tree(tag) to swap to a different domain at runtime.
    """

    BINDINGS = [
        ("up",    "nav('up')",    ""),
        ("down",  "nav('down')",  ""),
        ("left",  "nav('left')",  ""),
        ("right", "nav('right')", ""),
    ]

    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: "SimulationState", tree: str) -> None:
        super().__init__()
        self._state = state
        self._tree  = tree
        self._setup(tree)

    def _setup(self, tree: str) -> None:
        ireg         = get_imago_registry()
        unlocked_set = set(self._state.demiurge.unlocked_imagines)
        nodes        = ireg.nodes_for_tree(tree)
        by_tier: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)
        self._by_tier  = by_tier
        self._unlocked = unlocked_set
        dreg           = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(self._state)
        self._dreg        = dreg
        self._lum_info    = lum_info
        self._fellow_tags = fellow_tags

    def _imago_score(self, node: "ImagoNode") -> float:
        total, count = 0.0, 0
        for lum, lum_tags in self._lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                self._dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=self._fellow_tags[lid],
                    personality=self._dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            total += score
            count += 1
        return total / count if count else 0.0

    def _approval_class(self, node: "ImagoNode") -> str:
        s = self._imago_score(node)
        if s > 0.15:  return "good"
        if s < -0.15: return "danger"
        return ""

    def _build_cells(self) -> list:
        children = []
        for tier in (4, 3, 2, 1):
            nodes = self._by_tier[tier]
            if tier == 4:
                children.append(Static("", classes="imago-spacer"))
                node     = nodes[0]
                unlocked = node.node_id in self._unlocked
                children.append(ImagoCell(node, unlocked, self._approval_class(node) if unlocked else ""))
                children.append(Static("", classes="imago-spacer"))
            else:
                left, right = nodes[0], nodes[1]
                for node in (left, right):
                    unlocked = node.node_id in self._unlocked
                    cell = ImagoCell(node, unlocked, self._approval_class(node) if unlocked else "")
                    if node is left:
                        children.append(cell)
                        children.append(Static("", classes="imago-spacer"))
                    else:
                        children.append(cell)
        return children

    def compose(self) -> ComposeResult:
        with Grid(classes="imago-tree-inner-grid"):
            yield from self._build_cells()

    def on_mount(self) -> None:
        cells  = list(self.query(ImagoCell))
        target = next((c for c in cells if c._unlocked), cells[0] if cells else None)
        if target:
            target.focus()

    @work
    async def load_tree(self, tree: str) -> None:
        """Swap to a different domain tree in place."""
        self._tree = tree
        self._setup(tree)
        grid = self.query_one(Grid)
        await grid.remove_children()
        await grid.mount(*self._build_cells())
        self.on_mount()

    def action_nav(self, direction: str) -> None:
        cells   = list(self.query(ImagoCell))
        pos_map = {p: i for i, p in enumerate(self._POSITIONS)}
        focused = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused == -1:
            self.on_mount()
            return
        row, col = self._POSITIONS[focused]
        new_pos  = None
        if direction == "up" and row > 0:
            new_pos = (row - 1, 1 if row - 1 == 0 else col)
        elif direction == "down" and row < 3:
            new_pos = (row + 1, 0 if col == 1 else col)
        elif direction == "left" and col == 2:
            new_pos = (row, 0)
        elif direction == "right" and col == 0:
            new_pos = (row, 2)
        if new_pos and new_pos in pos_map:
            cells[pos_map[new_pos]].focus()
```

- [ ] **Step 3: Verify syntax**

```bash
cd /root/demiurge && source bin/activate && python -c "from ui.widgets import ImagoTreeGrid; print('ok')"
```
Expected: `ok`

---

## Task 2: Refactor `ImagoTreeModal` to use `ImagoTreeGrid`

**Files:**
- Modify: `ui/modals.py` — `ImagoTreeModal` class (~line 505)

`ImagoTreeModal` drops its inline grid-building and delegates to `ImagoTreeGrid`. All external behaviour (dismisses node_id/BACK/None, tooltip on focus, keyboard bindings for escape/backspace) stays identical.

- [ ] **Step 1: Add `ImagoTreeGrid` to the widgets import in `modals.py`**

Find line:
```python
from ui.widgets import DomainSquare, ImagoCell, ImagoRevealCell, LoopingListView
```
Change to:
```python
from ui.widgets import DomainSquare, ImagoCell, ImagoRevealCell, ImagoTreeGrid, LoopingListView
```

- [ ] **Step 2: Replace `ImagoTreeModal` body**

Replace the entire `ImagoTreeModal` class (lines 505–649) with:

```python
class ImagoTreeModal(ModalScreen):
    """
    Tree-layout Imago picker. Dismisses with a node_id, BACK, or None.
    Rendering and keyboard nav are handled by the embedded ImagoTreeGrid widget.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "cancel",       "Back"),
    ]

    def __init__(self, state: SimulationState, tree: str) -> None:
        super().__init__()
        self._state = state
        self._tree  = tree

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Imāginēs", classes="modal-title")
            yield ImagoTreeGrid(self._state, self._tree)
            yield Static("", id="imago-tooltip")
            with Horizontal(classes="btn-row"):
                yield Button("← Domain",  id="back-btn")
                yield Button("Cancel",    id="cancel-btn",  classes="-danger")

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        tip  = (node.tooltip_blurb or f"Tier {node.tier} apex — cannot be drawn from the Underreal.") if node else ""
        self.query_one("#imago-tooltip", Static).update(tip)

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self.dismiss(event.node_id)

    @on(Button.Pressed, "#back-btn")
    def _back_btn(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)
```

- [ ] **Step 3: Update `#imago-grid` CSS in `ui/styles.tcss`**

The inner grid now uses class `imago-tree-inner-grid` instead of id `imago-grid`. In `styles.tcss` find:
```css
#imago-grid {
    grid-size: 3;
    height: auto;
    margin: 1 0;
}
```
Replace with:
```css
.imago-tree-inner-grid {
    grid-size: 3;
    height: auto;
    margin: 1 0;
}
```

- [ ] **Step 4: Smoke test — ImagoTreeModal still works**

Launch the TUI, trigger any action that opens the imago tree (e.g. Uplift Species → choose a domain → see imago tree):
```bash
cd /root/demiurge && source bin/activate && python main.py
```
Verify:
- Imago tree renders (3-column pyramid with 7 nodes)
- Arrow keys navigate between cells
- Clicking or pressing Enter on an unlocked node selects it
- ← Domain button returns to domain picker
- Tooltip updates on focus

---

**Heartbeat:** ImagoTreeModal working? Proceed to Task 3. Any crash or rendering difference — debug before continuing. The most likely failure modes are: (1) `Grid` not imported in `widgets.py` — check the import in Task 1 Step 1; (2) `#imago-tooltip` not found — `ImagoTreeModal.compose()` still yields it so this shouldn't happen; (3) cells don't focus — `ImagoTreeGrid.on_mount()` calls `target.focus()`.

---

## Task 3: Add CSS for `WhisperConfigModal`

**Files:**
- Modify: `ui/styles.tcss` — append after the existing Imago Tree Picker section

- [ ] **Step 1: Append WhisperConfigModal CSS**

Append to the end of `ui/styles.tcss`:

```css
/* ── Whisper Config Modal ──────────────── */

.whisper-config-modal {
    background: $bg-modal;
    border: solid $border;
    width: 90%;
    height: 85%;
    padding: 1 2;
}

.whisper-panels {
    height: 1fr;
}

.whisper-left {
    width: 35%;
    border-right: solid $border;
    padding: 0 1 0 0;
}

.whisper-right {
    width: 65%;
    padding: 0 0 0 1;
}

.whisper-right-labels {
    height: auto;
    padding: 0 0 1 0;
}

#whisper-domain-grid {
    grid-size: 8;
    height: auto;
    margin: 0 0 1 0;
}

#whisper-tree-container {
    height: 1fr;
    border: solid $border;
    padding: 0 1;
}

Button.continue-ready {
    background: $good;
    color: $bg;
    text-style: bold;
}
```

- [ ] **Step 2: Verify CSS loads**

```bash
cd /root/demiurge && source bin/activate && python main.py
```
Expected: app starts without CSS parse errors (errors would appear as a traceback or blank screen).

---

**Heartbeat:** App starts cleanly? Proceed to Task 4.

---

## Task 4: Build `WhisperConfigModal` in `ui/modals.py`

**Files:**
- Modify: `ui/modals.py` — add imports; append class before the final closing section

- [ ] **Step 1: Add runtime imports for `MortalRole`, `MortalStatus`, `ENTITY_VISIBILITY_FLOOR`**

In `modals.py`, find the existing `from logic.tick_logic import (...)` block:
```python
from logic.tick_logic import (
    SimulationState,
    _compute_revelation_cap, _revelation_adjusted_cost,
)
```
Add `ENTITY_VISIBILITY_FLOOR`:
```python
from logic.tick_logic import (
    SimulationState,
    _compute_revelation_cap, _revelation_adjusted_cost,
    ENTITY_VISIBILITY_FLOOR,
)
```

The `if TYPE_CHECKING:` block currently has:
```python
if TYPE_CHECKING:
    from core.universe_core import NotableMortal
```
Change to a runtime import (needed for `isinstance` checks at runtime):
```python
from core.universe_core import MortalRole, MortalStatus

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
```

- [ ] **Step 2: Append `WhisperConfigModal` class to `modals.py`**

Add this class at the end of `modals.py` (before any final blank lines):

```python
# ─────────────────────────────────────────
# WHISPER CONFIG MODAL
# Unified mortal + domain + imago picker for the Whisper action.
# Replaces the 3-step wizard. Dismisses with (mortal_id_str, domain_tag,
# imago_node_id) on Continue, BACK, or None on cancel.
# ─────────────────────────────────────────

class WhisperConfigModal(ModalScreen):
    """
    Single-screen Whisper configuration. Left panel: mortal list.
    Right panel: 2×8 domain grid + dynamic imago tree.
    Continue is gated until mortal, domain, and imago are all selected.
    """

    BINDINGS = [
        ("escape",    "cancel", "Cancel"),
        ("backspace", "back",   "Back"),
    ]

    def __init__(self, state: SimulationState) -> None:
        super().__init__()
        self._state         = state
        self._mortal_id:    str | None = None
        self._domain_tag:   str | None = None
        self._imago_node_id: str | None = None

        dreg = get_domain_registry()
        _proxius_ids = {str(pid) for pid in state.demiurge.proxius_ids}
        self._mortals = [
            (mid, m) for mid, m in state.mortals.items()
            if m.status != MortalStatus.DECEASED
            and (m.pinned or m.visibility > ENTITY_VISIBILITY_FLOOR)
            and m.role not in (MortalRole.PROXIUS, MortalRole.HERALD)
            and mid not in _proxius_ids
        ]
        self._mortal_ids = [mid for mid, _ in self._mortals]
        self._dreg       = dreg

    def compose(self) -> ComposeResult:
        with Vertical(classes="whisper-config-modal"):
            yield Label("Whisper to Mortal", classes="modal-title")
            with Horizontal(classes="whisper-panels"):
                # ── Left: mortal list ──────────────────────
                with Vertical(classes="whisper-left"):
                    yield Label("Mortal: —", id="mortal-label")
                    with ListView(id="mortal-list"):
                        for i, (mid, m) in enumerate(self._mortals):
                            pop_obj  = self._state.pops.get(str(m.pop_id)) if m.pop_id else None
                            pop_name = pop_obj.name if pop_obj else "?"
                            loc_obj  = self._state.locations.get(str(m.current_location))
                            loc      = loc_obj.name if loc_obj else "?"
                            yield ListItem(
                                Label(f"{m.name:<18}  align:{m.alignment:.2f}  {pop_name:<14}  {loc}"),
                                id=f"mortal-{i}",
                            )
                # ── Right: domain grid + imago tree ────────
                with Vertical(classes="whisper-right"):
                    with Horizontal(classes="whisper-right-labels"):
                        yield Label("Domain: —", id="domain-label")
                        yield Label("Imāgō: —",  id="imago-label")
                    with Grid(id="whisper-domain-grid"):
                        for tag in _DOMAIN_GRID_ORDER:
                            eligible = self._state.demiurge.revelation_pools.get(tag, 0.0) > 0
                            yield DomainSquare(
                                tag=tag,
                                icon=self._dreg.icon(tag),
                                name="",
                                affiliated=tag in self._state.demiurge.affiliated_domains,
                                accessible=eligible,
                            )
                    with ScrollableContainer(id="whisper-tree-container"):
                        pass
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",     id="back-btn")
                        yield Button("Cancel",     id="cancel-btn",   classes="-danger")
                        yield Button("Continue →", id="continue-btn", disabled=True)

    def on_mount(self) -> None:
        if self._mortal_ids:
            self._mortal_id = self._mortal_ids[0]
            m = self._state.mortals.get(self._mortal_id)
            if m:
                self.query_one("#mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def _check_continue(self) -> None:
        ready = bool(self._mortal_id and self._domain_tag and self._imago_node_id)
        btn   = self.query_one("#continue-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    @on(ListView.Highlighted, "#mortal-list")
    def _on_mortal_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        idx = int(event.item.id.split("-", 1)[1])
        self._mortal_id = self._mortal_ids[idx]
        m = self._state.mortals.get(self._mortal_id)
        if m:
            self.query_one("#mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        self._domain_tag    = event.tag
        self._imago_node_id = None
        name = event.tag.split(":", 1)[1].title()
        self.query_one("#domain-label", Label).update(f"Domain: {name}")
        self.query_one("#imago-label",  Label).update("Imāgō: —")
        self._check_continue()
        self._swap_tree(event.tag)

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self._imago_node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        self._check_continue()

    @work
    async def _swap_tree(self, tag: str) -> None:
        tree      = tag.split(":", 1)[1]
        container = self.query_one("#whisper-tree-container", ScrollableContainer)
        await container.remove_children()
        await container.mount(ImagoTreeGrid(self._state, tree))

    @on(Button.Pressed, "#continue-btn")
    def _on_continue(self, _: Button.Pressed) -> None:
        if self._mortal_id and self._domain_tag and self._imago_node_id:
            self.dismiss((self._mortal_id, self._domain_tag, self._imago_node_id))

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(BACK)
```

- [ ] **Step 3: Verify syntax**

```bash
cd /root/demiurge && source bin/activate && python -c "from ui.modals import WhisperConfigModal; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: Smoke test — open the modal**

Launch the TUI and trigger Whisper to Mortal from the Actions tab. Verify:
- `WhisperConfigModal` opens (wide two-column layout)
- Mortal list populates on the left; "Mortal: [Name]" label updates as you move through the list
- Domain grid shows 16 icon-only buttons in 2 rows; eligible domains are interactive, ineligible are greyed
- Clicking an eligible domain renders the imago tree on the right; "Domain: [Name]" label updates; "Imāgō: —" resets
- Arrow keys navigate the imago tree; clicking or Enter selects a node; "Imāgō: [Name]" label updates
- Continue button stays grey until all three are selected; turns green once all three are set
- Back → dismisses with BACK; Cancel → dismisses with None; Escape → same as Cancel

---

**Heartbeat:** All three panels interactive and Continue gating correct? Proceed to Task 5. Common failure modes: (1) `ScrollableContainer` not in `modals.py` imports — check `from textual.containers import ...`; (2) domain buttons all greyed — check `revelation_pools`; for a fresh game state where no imagoes are unlocked yet, ALL domains will be greyed (correct behaviour — whisper requires at least one unlocked imago). Try after unlocking an imago via Reveal Imago first.

---

## Task 5: Wire up `_build_intent` in `ui/ui.py`

**Files:**
- Modify: `ui/ui.py` — add `WhisperConfigModal` to imports; add whisper early-return block in `_build_intent`

- [ ] **Step 1: Add `WhisperConfigModal` to the modals import**

Find:
```python
from ui.modals import (
    ErrorModal, ToastModal, PickerModal, PopLatitudePickerModal, YesNoModal,
    QuitConfirmModal,
    TextFormModal, DomainPickerModal, ImagoTreeModal, ImagoDetailModal,
    ImagoRevealModal, ImagoRevealDetailModal, MortalDetailModal,
    ActionBrowserModal, CategoryPendingModal,
)
```
Add `WhisperConfigModal` on the `ImagoDetailModal` line:
```python
from ui.modals import (
    ErrorModal, ToastModal, PickerModal, PopLatitudePickerModal, YesNoModal,
    QuitConfirmModal,
    TextFormModal, DomainPickerModal, ImagoTreeModal, ImagoDetailModal,
    ImagoRevealModal, ImagoRevealDetailModal, MortalDetailModal,
    ActionBrowserModal, CategoryPendingModal, WhisperConfigModal,
)
```

- [ ] **Step 2: Insert whisper early-return block in `_build_intent`**

Find the comment `# ── Target selection by type, with back-from-params loop ──` (around line 1187). Insert the following block immediately before it:

```python
        # ── whisper: unified config modal ──
        if action_key == "whisper":
            ireg = get_imago_registry()
            while True:
                result = await app.push_screen_wait(WhisperConfigModal(state))
                if result is None: return None
                if result == BACK: return BACK
                mortal_id_str, domain_tag, imago_node_id = result
                node      = ireg.get_node(imago_node_id)
                confirmed = await app.push_screen_wait(ImagoDetailModal(node, state))
                if confirmed is None: return None
                if not confirmed:     continue
                dvs = [
                    DomainVector(domain_tag=t, direction=v)
                    for t, v in node.mechanics.items()
                    if t.startswith("domain:")
                ]
                cvs = [
                    CultureVector(culture_tag=t, direction=v)
                    for t, v in node.mechanics.items()
                    if not t.startswith("domain:")
                ]
                framing = await self._pick_framing()
                if framing is None: return None
                if framing == BACK: continue
                return ActionInstance(
                    action_definition_id=defn.id,
                    target_type=TargetType.MORTAL,
                    target_id=UUID(mortal_id_str),
                    timestamp=state.universe.current_age.to_float_years(),
                    demiurge_id=state.demiurge.id,
                    proxius_id=None,
                    intent=WhisperIntent(
                        concept=node.name,
                        domain_vectors=dvs,
                        culture_vectors=cvs,
                        framing=framing,
                        imago_node_id=imago_node_id,
                    ),
                )

```

- [ ] **Step 3: Verify syntax**

```bash
cd /root/demiurge && source bin/activate && python -c "from ui.ui import DemiurgeApp; print('ok')"
```
Expected: `ok`

- [ ] **Step 4: End-to-end test**

Launch the TUI and run through the full whisper flow:
```bash
cd /root/demiurge && source bin/activate && python main.py
```
1. Open Actions → Subtle Influence → Whisper to Mortal
2. `WhisperConfigModal` opens
3. Select a mortal, a domain, and an imago node; click Continue
4. `ImagoDetailModal` opens — confirm or go back
5. Framing picker opens — select a framing
6. Action appears as QUEUED in the Actions tab
7. Advance a tick — whisper resolves with a narrative line

Also test Back at each step:
- Back in framing → returns to `WhisperConfigModal`
- Back in `ImagoDetailModal` (unconfirm) → returns to `WhisperConfigModal`
- Back in `WhisperConfigModal` → returns to action browser

- [ ] **Step 5: Regression check**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50-tick run completes without exceptions. The autoplay strategy doesn't use `WhisperConfigModal` (headless), so this verifies the old whisper path in `_build_intent_params` still compiles and the rest of the codebase is intact.

---

**Heartbeat:** Full flow works and autoplay clean? Proceed to Task 6.

---

## Task 6: Commit

- [ ] **Step 1: Stage and commit**

```bash
cd /root/demiurge && git add ui/widgets.py ui/modals.py ui/styles.tcss ui/ui.py
git commit -m "$(cat <<'EOF'
feat: WhisperConfigModal — unified config modal for Whisper to Mortal

Extracts ImagoTreeGrid as a reusable widget (with load_tree() for
dynamic domain swapping), refactors ImagoTreeModal to delegate to it,
and adds WhisperConfigModal: a single-screen two-column picker that
replaces the 3-step mortal → domain → imago wizard.

Old wizard flow preserved in _build_intent_params for cleanup pass.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

- [ ] **Step 2: Push to origin main**

```bash
git push origin main
```
