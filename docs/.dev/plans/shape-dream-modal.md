# Shape Dream Config Modal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the multi-step Shape Dream menu flow with a single `ShapeDreamConfigModal` that lets the player pick a mortal + two distinct domain/imago pairs in one screen.

**Architecture:** Mirror `WhisperConfigModal`'s layout (mortal list on left, selection UI on right) but replace the right panel with a `TabbedContent` (two tabs, one per imago slot) plus a shared button row below the tabs. Each tab hosts the same domain-grid + imago-tree combo used in `WhisperConfigModal`. Selecting a domain in one tab disables that domain in the other. Modal dismisses with `(mortal_id, imago_node_id_a, imago_node_id_b)`. Remove the now-unused `concept` field from `ShapeDreamIntent`.

**Tech Stack:** Python 3.11, Textual (TabbedContent, TabPane, Vertical, Horizontal, ListView, Grid, ScrollableContainer, Button, Label), Pydantic, sqlite3

---

## Files affected

| File | Change |
|---|---|
| `core/action_core.py` | Remove `concept: str` from `ShapeDreamIntent` |
| `logic/tick_logic.py` | Replace `concept=intent.concept` → `concept=""` in Shape Dream Event |
| `autoplay/strategies/shape_dream_demo.py` | Remove `concept=` kwarg from `ShapeDreamIntent(...)` |
| `ui/styles.tcss` | Add CSS for `ShapeDreamConfigModal` layout |
| `ui/modals.py` | Add `ShapeDreamConfigModal` class |
| `ui/ui.py` | Replace multi-step shape_dream flow with modal push; add import |

---

## ✅ Task 1: Remove `concept` from `ShapeDreamIntent` and fix all references

**Files:**
- Modify: `core/action_core.py:256` (remove `concept: str`)
- Modify: `logic/tick_logic.py:3654` (`concept=intent.concept` → `concept=""`)
- Modify: `autoplay/strategies/shape_dream_demo.py:78` (remove `concept=` kwarg)
- Modify: `ui/ui.py:1558-1566` (remove `concept=concept` from `ShapeDreamIntent(...)` and all `concept` variable references in the shape_dream block)

- [ ] **Step 1: Remove `concept` field from `ShapeDreamIntent`**

In `core/action_core.py`, remove these lines (currently around line 256-259):
```python
    concept: str
    # Plain statement of the dream the player is shaping. The narrative line
    # generated at resolution time will report which Imago turned out to be
    # the dominant interpretation.
```

- [ ] **Step 2: Fix tick_logic Event construction**

In `logic/tick_logic.py` around line 3654, change:
```python
                    concept=intent.concept,
```
to:
```python
                    concept="",
```

- [ ] **Step 3: Fix shape_dream_demo autoplay strategy**

In `autoplay/strategies/shape_dream_demo.py`, remove the `concept=` line from `ShapeDreamIntent(...)`:
```python
            q("shape_dream", TargetType.MORTAL, UUID(mid),
              ShapeDreamIntent(
                  imago_node_id_a=IMAGO_A,
                  imago_node_id_b=IMAGO_B,
                  domain_vectors_a=cvs_a,   # intentional: mechanics are culture-heavy
                  culture_vectors_a=cvs_a,
                  domain_vectors_b=cvs_b,
                  culture_vectors_b=cvs_b,
              ))
```
(i.e., delete the `concept=f"{node_a.name} ⊗ {node_b.name}",` line only)

- [ ] **Step 4: Verify no remaining `concept` references on `ShapeDreamIntent`**

```bash
grep -n "ShapeDreamIntent\|shape_dream" /root/demiurge/core/action_core.py \
     /root/demiurge/logic/tick_logic.py \
     /root/demiurge/autoplay/strategies/shape_dream_demo.py \
     /root/demiurge/ui/ui.py | grep -v "^Binary\|#"
```

None of the lines should reference `.concept` on a `ShapeDreamIntent`. If any do, fix them.

- [ ] **Step 5: Smoke-test with autoplay**

```bash
cd /root/demiurge && python3 main.py --autoplay shape_dream_demo 2>&1 | tail -10
```

Expected: run completes without `TypeError` or `ValidationError`.

- [ ] **Step 6: Commit**

```bash
git add core/action_core.py logic/tick_logic.py \
        autoplay/strategies/shape_dream_demo.py ui/ui.py
git commit -m "refactor: remove unused concept field from ShapeDreamIntent"
```

---

## ✅ Task 2: Add CSS for `ShapeDreamConfigModal`

**Files:**
- Modify: `ui/styles.tcss` (append after the whisper-config-modal block, around line 611)

The layout differs from `WhisperConfigModal` in one key way: the right side uses Textual's `TabbedContent` widget, and the button row lives *below* the tab pane (not inside it). The modal needs to be slightly taller (83% vs 78%) to accommodate the tab bar.

- [ ] **Step 1: Append CSS block to `ui/styles.tcss`**

Add after the existing `Button.continue-ready` rule (around line 611):

```css
/* ── Shape Dream Config Modal ──────────────── */

.shape-dream-modal {
    background: $bg-modal;
    border: solid $border;
    width: 95%;
    height: 83%;
    padding: 1 2;
}

.shape-dream-panels {
    height: 1fr;
}

.shape-dream-left {
    width: 40%;
    border-right: solid $border;
    padding: 0 1 0 0;
}

.shape-dream-right {
    width: 60%;
    padding: 0 0 0 1;
}

.shape-dream-tabs {
    height: 1fr;
}

#shape-dream-domain-grid-a,
#shape-dream-domain-grid-b {
    grid-size: 8;
    height: auto;
    margin: 0 0 1 0;
}

#shape-dream-tree-container-a,
#shape-dream-tree-container-b {
    height: 16;
    border: solid $border;
    padding: 0 1;
}
```

- [ ] **Step 2: Commit**

```bash
git add ui/styles.tcss
git commit -m "ui: add CSS for ShapeDreamConfigModal"
```

---

## ✅ Task 3: Build `ShapeDreamConfigModal`

**Files:**
- Modify: `ui/modals.py` (add class after `WhisperConfigModal`, around line 1456)

The modal dismisses with `tuple[str, str, str]` = `(mortal_id, imago_node_id_a, imago_node_id_b)`, or `None` (cancel), or `BACK`.

Key design details:
- Tab labels start as `"Domain 1: Imāgō 1"` / `"Domain 2: Imāgō 2"` and update to e.g. `"Fire: The Wheel"` → strip a leading `"The "` → `"Fire: Wheel"`.
- When domain X is selected in tab A, find that `DomainSquare` in tab B's grid and set `widget.disabled = True` + `add_class("inactive")`; if a previously excluded domain is deselected (tab A switches domains), re-enable it in tab B.
- `ImagoCell.Selected` events bubble from inside the tab panes; distinguish which tab the event came from by inspecting `event.node._dom_ready` ancestry or by checking `self._active_tab`.
- Use Textual's `TabbedContent.TabActivated` to track which tab is active if needed, but simpler is to store selections per slot (slot A vs slot B) and key event handling on *which domain grid / tree container* fired the event.
- The two domain grids and two tree containers each have unique IDs (`#shape-dream-domain-grid-a` / `-b`, `#shape-dream-tree-container-a` / `-b`), so `event.control` ancestry can identify which tab the event originated from.

- [ ] **Step 1: Add import for `TabbedContent` and `TabPane` at top of `modals.py`**

Find the existing Textual import block near the top of `ui/modals.py` and add `TabbedContent, Tab, TabPane` to it. Currently it should look something like:
```python
from textual.widgets import (
    Button, Label, ListView, ListItem, ...
)
```
Add `TabbedContent, Tab, TabPane` to that list.

- [ ] **Step 2: Add the `ShapeDreamConfigModal` class**

After the closing of `WhisperConfigModal` (around line 1455), insert:

```python
class ShapeDreamConfigModal(ModalScreen):
    """
    Single-screen Shape Dream configuration. Left panel: mortal list.
    Right panel: two tabs (one per Imāgō slot) each with a domain grid +
    imago tree. Buttons live below the tabs. Dismisses with
    (mortal_id, imago_node_id_a, imago_node_id_b).
    """

    BINDINGS = [
        ("escape",    "cancel", "Cancel"),
        ("backspace", "back",   "Back"),
    ]

    def __init__(self, state: SimulationState) -> None:
        super().__init__()
        self._state          = state
        self._mortal_id:     str | None = None
        self._imago_a:       str | None = None   # node_id for slot A
        self._imago_b:       str | None = None   # node_id for slot B
        self._domain_a:      str | None = None   # domain tag chosen in tab A
        self._domain_b:      str | None = None   # domain tag chosen in tab B

        dreg = get_domain_registry()
        _proxius_ids = {str(pid) for pid in state.demiurge.proxius_ids}
        self._mortals = [
            (mid, m) for mid, m in state.mortals.items()
            if m.status != MortalStatus.DECEASED
            and (m.pinned or m.visibility > ENTITY_VISIBILITY_FLOOR)
            and m.role not in (MortalRole.PROXIUS, MortalRole.HERALD)
            and mid not in _proxius_ids
        ]
        self._mortal_ids  = [mid for mid, _ in self._mortals]
        self._dreg        = dreg
        ireg              = get_imago_registry()
        unlocked_set      = set(state.demiurge.unlocked_imagines)
        self._eligible_tags = {
            tag for tag in _DOMAIN_GRID_ORDER
            if any(n.node_id in unlocked_set for n in ireg.nodes_for_tree(tag.split(":", 1)[1]))
        }

    def compose(self) -> ComposeResult:
        with Vertical(classes="shape-dream-modal"):
            yield Label("Shape Dream", classes="modal-title")
            with Horizontal(classes="shape-dream-panels"):
                with Vertical(classes="shape-dream-left"):
                    yield Label("Mortal: —", id="sd-mortal-label")
                    with ListView(id="sd-mortal-list"):
                        for i, (mid, m) in enumerate(self._mortals):
                            pop_obj  = self._state.pops.get(str(m.pop_id)) if m.pop_id else None
                            pop_name = _pop_stratum_label(pop_obj) if pop_obj else "?"
                            loc_obj  = self._state.locations.get(str(m.current_location))
                            loc      = (loc_obj.name or "?") if loc_obj else "?"
                            name     = m.name or "?"
                            align    = m.alignment if m.alignment is not None else 0.0
                            yield ListItem(
                                Label(f"{name:<18}  {align*100:>4.0f}%  {pop_name:<14}  {loc}"),
                                id=f"sd-mortal-{i}",
                            )
                with Vertical(classes="shape-dream-right"):
                    with TabbedContent(
                        id="sd-tabs",
                        classes="shape-dream-tabs",
                        initial="sd-tab-a",
                    ):
                        with TabPane("Domain 1: Imāgō 1", id="sd-tab-a"):
                            yield Label("Domain: —", id="sd-domain-label-a")
                            with Grid(id="shape-dream-domain-grid-a"):
                                for tag in _DOMAIN_GRID_ORDER:
                                    eligible = tag in self._eligible_tags
                                    yield DomainSquare(
                                        tag=tag,
                                        icon=self._dreg.icon(tag),
                                        name="",
                                        affiliated=tag in self._state.demiurge.affiliated_domains,
                                        accessible=eligible,
                                    )
                            yield Label("Imāgō: —", id="sd-imago-label-a")
                            with ScrollableContainer(id="shape-dream-tree-container-a"):
                                pass
                        with TabPane("Domain 2: Imāgō 2", id="sd-tab-b"):
                            yield Label("Domain: —", id="sd-domain-label-b")
                            with Grid(id="shape-dream-domain-grid-b"):
                                for tag in _DOMAIN_GRID_ORDER:
                                    eligible = tag in self._eligible_tags
                                    yield DomainSquare(
                                        tag=tag,
                                        icon=self._dreg.icon(tag),
                                        name="",
                                        affiliated=tag in self._state.demiurge.affiliated_domains,
                                        accessible=eligible,
                                    )
                            yield Label("Imāgō: —", id="sd-imago-label-b")
                            with ScrollableContainer(id="shape-dream-tree-container-b"):
                                pass
                    with Horizontal(classes="btn-row"):
                        yield Button("← Back",     id="sd-back-btn")
                        yield Button("Cancel",     id="sd-cancel-btn",   classes="-danger")
                        yield Button("Continue →", id="sd-continue-btn", disabled=True)

    def on_mount(self) -> None:
        if self._mortal_ids:
            self._mortal_id = self._mortal_ids[0]
            m = self._state.mortals.get(self._mortal_id)
            if m:
                self.query_one("#sd-mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def _check_continue(self) -> None:
        ready = bool(self._mortal_id and self._imago_a and self._imago_b)
        btn   = self.query_one("#sd-continue-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    def _tab_label(self, slot: str, domain_tag: str | None, imago_node_id: str | None) -> str:
        """Build a tab label like 'Fire: Wheel' from current slot state."""
        if domain_tag is None:
            return f"Domain {slot}: Imāgō {slot}"
        domain_name = domain_tag.split(":", 1)[1].title()
        if imago_node_id is None:
            return f"{domain_name}: Imāgō {slot}"
        ireg = get_imago_registry()
        node = ireg.get_node(imago_node_id)
        raw_name = node.name if node else imago_node_id
        # Strip leading "The " from imago names for tab brevity.
        imago_name = raw_name.removeprefix("The ")
        return f"{domain_name}: {imago_name}"

    def _update_tab_label(self, tab_id: str, label: str) -> None:
        tab = self.query_one(f"#{tab_id}", TabPane)
        tab.label = label  # type: ignore[assignment]

    def _set_domain_excluded(self, grid_id: str, excluded_tag: str | None, prev_excluded_tag: str | None) -> None:
        """
        In the given domain grid, disable the square for `excluded_tag` and
        re-enable the square for `prev_excluded_tag` (if any, and if eligible).
        """
        grid = self.query_one(f"#{grid_id}", Grid)
        for sq in grid.query(DomainSquare):
            if sq._tag == excluded_tag:
                sq.disabled = True
                sq.add_class("inactive")
            elif sq._tag == prev_excluded_tag and sq._tag in self._eligible_tags:
                sq.disabled = False
                sq.remove_class("inactive")

    @on(ListView.Highlighted, "#sd-mortal-list")
    def _on_mortal_highlighted(self, event: ListView.Highlighted) -> None:
        if event.item is None:
            return
        idx = int(event.item.id.split("-", 2)[2])
        self._mortal_id = self._mortal_ids[idx]
        m = self._state.mortals.get(self._mortal_id)
        if m:
            self.query_one("#sd-mortal-label", Label).update(f"Mortal: {m.name}")
        self._check_continue()

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        # Determine which tab (A or B) the event came from.
        grid_a = self.query_one("#shape-dream-domain-grid-a", Grid)
        in_tab_a = grid_a in event.control.ancestors_with_self

        if in_tab_a:
            prev = self._domain_a
            self._domain_a  = event.tag
            self._imago_a   = None
            self.query_one("#sd-domain-label-a", Label).update(
                f"Domain: {event.tag.split(':', 1)[1].title()}"
            )
            self.query_one("#sd-imago-label-a", Label).update("Imāgō: —")
            self._update_tab_label("sd-tab-a", self._tab_label("1", self._domain_a, None))
            # Exclude this domain in tab B; re-enable the previously excluded one.
            self._set_domain_excluded("shape-dream-domain-grid-b", event.tag, prev)
            self._swap_tree("shape-dream-tree-container-a", event.tag)
        else:
            prev = self._domain_b
            self._domain_b  = event.tag
            self._imago_b   = None
            self.query_one("#sd-domain-label-b", Label).update(
                f"Domain: {event.tag.split(':', 1)[1].title()}"
            )
            self.query_one("#sd-imago-label-b", Label).update("Imāgō: —")
            self._update_tab_label("sd-tab-b", self._tab_label("2", self._domain_b, None))
            self._set_domain_excluded("shape-dream-domain-grid-a", event.tag, prev)
            self._swap_tree("shape-dream-tree-container-b", event.tag)

        self._check_continue()

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        # Determine which tab the cell came from.
        container_a = self.query_one("#shape-dream-tree-container-a", ScrollableContainer)
        in_tab_a = container_a in event.control.ancestors_with_self

        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id

        if in_tab_a:
            self._imago_a = event.node_id
            self.query_one("#sd-imago-label-a", Label).update(f"Imāgō: {name}")
            self._update_tab_label("sd-tab-a", self._tab_label("1", self._domain_a, self._imago_a))
        else:
            self._imago_b = event.node_id
            self.query_one("#sd-imago-label-b", Label).update(f"Imāgō: {name}")
            self._update_tab_label("sd-tab-b", self._tab_label("2", self._domain_b, self._imago_b))

        self._check_continue()

    @work
    async def _swap_tree(self, container_id: str, tag: str) -> None:
        tree      = tag.split(":", 1)[1]
        container = self.query_one(f"#{container_id}", ScrollableContainer)
        await container.remove_children()
        await container.mount(ImagoTreeGrid(self._state, tree))

    @on(Button.Pressed, "#sd-continue-btn")
    def _on_continue(self, _: Button.Pressed) -> None:
        if self._mortal_id and self._imago_a and self._imago_b:
            self.dismiss((self._mortal_id, self._imago_a, self._imago_b))

    @on(Button.Pressed, "#sd-back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#sd-cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(BACK)
```

- [ ] **Step 3: Verify the file parses**

```bash
python3 -c "import ui.modals" 2>&1
```

Expected: no output (clean import).

- [ ] **Step 4: Commit**

```bash
git add ui/modals.py
git commit -m "feat: add ShapeDreamConfigModal"
```

---

## ✅ Task 4: Wire `shape_dream` in `ui.py`

**Files:**
- Modify: `ui/ui.py:73` (add `ShapeDreamConfigModal` to import)
- Modify: `ui/ui.py:1497-1567` (replace multi-step shape_dream flow)

- [ ] **Step 1: Add `ShapeDreamConfigModal` to the import from `ui.modals`**

Find the `from ui.modals import (...)` block (around line 68-74) and add `ShapeDreamConfigModal` to the list.

- [ ] **Step 2: Replace the shape_dream multi-step flow**

Find the block starting at `if action_key == "shape_dream":` (around line 1497) and replace the entire block (through the closing `return ShapeDreamIntent(...)` at line 1567) with:

```python
            if action_key == "shape_dream":
                ireg = get_imago_registry()
                while True:
                    result = await app.push_screen_wait(ShapeDreamConfigModal(state))
                    if result is None: return None
                    if result == BACK: return BACK
                    mortal_id_str, imago_node_id_a, imago_node_id_b = result
                    node_a = ireg.get_node(imago_node_id_a)
                    node_b = ireg.get_node(imago_node_id_b)
                    dvs_a = [
                        DomainVector(domain_tag=t, direction=v)
                        for t, v in node_a.mechanics.items()
                        if t.startswith("domain:")
                    ]
                    cvs_a = [
                        CultureVector(culture_tag=t, direction=v)
                        for t, v in node_a.mechanics.items()
                        if not t.startswith("domain:")
                    ]
                    dvs_b = [
                        DomainVector(domain_tag=t, direction=v)
                        for t, v in node_b.mechanics.items()
                        if t.startswith("domain:")
                    ]
                    cvs_b = [
                        CultureVector(culture_tag=t, direction=v)
                        for t, v in node_b.mechanics.items()
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
                        intent=ShapeDreamIntent(
                            imago_node_id_a=imago_node_id_a,
                            imago_node_id_b=imago_node_id_b,
                            domain_vectors_a=dvs_a,
                            culture_vectors_a=cvs_a,
                            domain_vectors_b=dvs_b,
                            culture_vectors_b=cvs_b,
                            framing=framing,
                        ),
                    )
```

Note: the old flow also had a `while True` that let the player go "Back" to re-pick. The new modal handles its own Back internally; the outer `while True` here handles the case where the player hits Back from the framing picker and needs to re-enter the modal.

- [ ] **Step 3: Smoke-test**

```bash
python3 -c "import ui.ui" 2>&1
```

Expected: no output (clean import).

- [ ] **Step 4: Commit**

```bash
git add ui/ui.py
git commit -m "feat: wire shape_dream to ShapeDreamConfigModal"
```

---

## ✅ Task 5: Manual smoke-test and push

- [ ] **Step 1: Run autoplay to confirm no regressions**

```bash
cd /root/demiurge && python3 main.py --autoplay wardens_default 2>&1 | tail -5
```

Expected: completes without error.

- [ ] **Step 2: Run shape_dream_demo strategy**

```bash
python3 main.py --autoplay shape_dream_demo 2>&1 | tail -10
```

Expected: completes without `ValidationError` or `TypeError`.

- [ ] **Step 3: Push**

```bash
git push origin action-redesign
```

---

## Notes

- `_update_tab_label` sets `tab.label` — in Textual, `TabPane.label` is a reactive `str | Text` property. If this doesn't cause the tab bar to re-render in the Textual version in use, an alternative is to call `self.query_one(TabbedContent).get_tab("sd-tab-a").label = label` instead. Either will need testing at runtime.
- `event.control.ancestors_with_self` is used to determine which tab a bubbled event came from. If `ancestors_with_self` is not available in the installed Textual version, use `event.control.ancestors` and check `container_a in event.control.ancestors`.
- The existing shape_dream multi-step flow in `_build_intent_params` (around line 1497) that doesn't go through `_build_action_intent` (the early-return block) does NOT need to be touched — only the early-return block handles whisper/shape_dream specially. Confirm by checking that the `if action_key == "shape_dream":` block is inside the early-return section before the `_NO_PARAMS` block.
