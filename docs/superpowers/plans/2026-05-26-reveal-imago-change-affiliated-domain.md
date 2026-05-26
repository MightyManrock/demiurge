# Reveal Imāgō + Change Affiliated Domain Modal Redesign

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the 3-step Reveal Imāgō flow and 2-step Change Affiliated Domain flow each into a single modal, and add a gate modal when no unlockable Imāgō nodes exist.

**Architecture:** Three new `ModalScreen` subclasses added to `ui/modals.py`; two existing modals (`ImagoRevealModal`, `ImagoRevealDetailModal`) deleted; wiring in `ui/ui.py` updated. No changes to `ImagoTreeGrid`, `ImagoRevealCell`, or any logic layer. CSS added to `ui/styles.tcss`.

**Tech Stack:** Textual (`ModalScreen`, `Grid`, `ScrollableContainer`, `Button`, `Label`, `Static`, `Horizontal`, `Vertical`, `@work`), Pydantic models from `core/`, registry helpers from `utilities/`.

---

## No test suite

This project has no pytest suite. The regression test is:

```bash
source bin/activate
python main.py --autoplay
```

Expected: completes 50 ticks with no Python exceptions. Run this after every commit.

---

## File map

| File | Change |
|------|--------|
| `ui/modals.py` | Add `NoUnlockableModal`, `RevealImagoConfigModal`, `ChangeAffiliatedDomainModal`; add `_eligible_reveal_domain_tags`, `_has_any_unlockable` helpers; delete `ImagoRevealModal` and `ImagoRevealDetailModal` |
| `ui/styles.tcss` | Add CSS for `.reveal-imago-modal`, `#reveal-domain-grid`, `#reveal-tree-container`, `.change-affiliated-modal`, `.affiliated-domain-row`, `.affiliated-placeholder`, `#new-domain-grid` |
| `ui/ui.py` | Replace `_build_reveal_imago_intent` and the `change_affiliated_domains` block; update imports |

---

## Task 1: Add two module-level helper functions to `ui/modals.py`

These go right after `_eligible_domain_tags` (currently around line 1653 in `ui/modals.py`).

**Files:**
- Modify: `ui/modals.py` (insert after `_eligible_domain_tags`)

- [x] **Step 1: Add `_has_any_unlockable`**

Find the line that reads `def _compose_entity_list(` and insert both new helpers **before** it (they go after `_eligible_domain_tags`):

```python
def _has_any_unlockable(state: SimulationState) -> bool:
    """Return True if any Imago node has prereqs met and is not yet unlocked."""
    ireg    = get_imago_registry()
    dreg    = get_domain_registry()
    unlocked = set(state.demiurge.unlocked_imagines)
    return any(
        ireg.is_unlockable(n.node_id, unlocked)
        for tag in dreg.all_tags
        for n in ireg.nodes_for_tree(tag.split(":", 1)[1])
    )


def _eligible_reveal_domain_tags(state: SimulationState) -> set[str]:
    """
    Return domain tags where the revelation pool can afford at least one
    unlockable node — used for 'eligible-reveal' styling in the domain grid.
    """
    ireg     = get_imago_registry()
    dreg     = get_domain_registry()
    unlocked = set(state.demiurge.unlocked_imagines)
    rev      = state.demiurge.revealed_imagines

    def _min_cost(tag: str) -> int:
        tree = tag.split(":", 1)[1]
        return min(
            (
                _revelation_adjusted_cost(n.tier, rev)
                for n in ireg.nodes_for_tree(tree)
                if n.node_id not in unlocked and ireg.is_unlockable(n.node_id, unlocked)
            ),
            default=9999,
        )

    return {
        tag for tag in dreg.all_tags
        if state.demiurge.revelation_pools.get(tag, 0.0) >= _min_cost(tag)
    }
```

- [x] **Step 2: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 2: Add `NoUnlockableModal` to `ui/modals.py`

This is a simple gate modal shown when no Imāgō nodes are unlockable at all. It offers routing to Explore Beliefs or going back to the action picker.

Dismisses with: `"explore_beliefs"` (→ route to Explore Beliefs), `BACK` (→ action picker), `None` (→ cancel everything).

**Files:**
- Modify: `ui/modals.py` (insert before `ImagoRevealModal`, around line 1002)

- [x] **Step 1: Insert `NoUnlockableModal` before `ImagoRevealModal`**

Find the line `class ImagoRevealModal(ModalScreen):` and insert this class immediately before it:

```python
class NoUnlockableModal(ModalScreen):
    """
    Shown when the player selects Reveal Imāgō but no nodes are currently unlockable.
    Dismisses with "explore_beliefs" (route to Explore Beliefs), BACK, or None (cancel).
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
    ]

    def compose(self) -> "ComposeResult":
        with Vertical(classes="modal-box"):
            yield Label("No Unlockable Imāgō", classes="modal-title")
            yield Static(
                "There are no Imāgō nodes available to reveal right now.\n"
                "You may not have met the prerequisites, or your Revelation pools\n"
                "may be empty. Explore Beliefs to build up Revelation.",
                id="no-unlock-body",
            )
            with Horizontal(classes="btn-row"):
                yield Button("← Back",          id="back-btn")
                yield Button("Cancel",           id="cancel-btn",   classes="-danger")
                yield Button("Explore Beliefs",  id="explore-btn",  classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#explore-btn", Button).focus()

    @on(Button.Pressed, "#explore-btn")
    def _explore(self, _: Button.Pressed) -> None:
        self.dismiss("explore_beliefs")

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)
```

- [x] **Step 2: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 3: Add CSS for `RevealImagoConfigModal` to `ui/styles.tcss`

**Files:**
- Modify: `ui/styles.tcss` (insert after the Whisper CSS block, after line ~683)

- [x] **Step 1: Insert CSS block after the Whisper block**

Find the comment `/* ── Shape Dream Confirm Modal` and insert this block immediately before it:

```css
/* ── Reveal Imāgō Config Modal ─────────── */

.reveal-imago-modal {
    background: $bg-modal;
    border: solid $border;
    width: 60%;
    height: 85%;
    padding: 1 2;
}

#reveal-domain-grid {
    grid-size: 8;
    height: auto;
    margin: 0 0 1 0;
}

#reveal-tree-container {
    height: 1fr;
    border: solid $border;
    padding: 0 1;
    margin: 0 0 1 0;
}

/* ── Change Affiliated Domain Modal ──────── */

.change-affiliated-modal {
    background: $bg-modal;
    border: solid $border;
    width: 55%;
    height: 75%;
    padding: 1 2;
}

.affiliated-domain-row {
    height: auto;
    margin: 0 0 1 0;
}

.affiliated-placeholder {
    height: 4;
    border: round $border;
    width: 1fr;
    color: $muted;
    content-align: center middle;
    text-align: center;
}

#new-domain-grid {
    grid-size: 4;
    height: auto;
    margin: 0 0 1 0;
}
```

- [x] **Step 2: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 4: Add `RevealImagoConfigModal` to `ui/modals.py`

Single-screen modal replacing the 3-step Reveal Imāgō flow. Layout (top to bottom): title → "Domain: —" label → 2×8 symbol-only domain grid → "Imāgō: —" label → scrollable ImagoRevealCell tree → buttons.

Dismisses with: `RevealImagoIntent` (confirmed), `BACK`, or `None` (cancel).

**Files:**
- Modify: `ui/modals.py` (insert after `NoUnlockableModal`, before `ImagoRevealModal`)

**Imports needed** (verify these are already at the top of `modals.py`; add if missing):
- `from core.action_core import RevealImagoIntent`
- `ImagoRevealCell` (from `ui/widgets.py`, already imported)
- `_revelation_adjusted_cost`, `_compute_revelation_cap` (from `logic/tick_logic.py`, already imported)

- [x] **Step 1: Insert `RevealImagoConfigModal` before `ImagoRevealModal`**

Find the line `class ImagoRevealModal(ModalScreen):` and insert this class immediately before it (after `NoUnlockableModal`):

```python
class RevealImagoConfigModal(ModalScreen):
    """
    Single-screen Reveal Imāgō configuration.
    Domain grid (2×8, symbol-only) → ImagoRevealCell tree → confirm.
    Dismisses with RevealImagoIntent, BACK, or None.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
    ]

    # Positional map for the 7 ImagoRevealCell slots in the 3-column tree grid.
    # (row, col) where col 0=left, 1=middle, 2=right.
    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: "SimulationState") -> None:
        super().__init__()
        self._state       = state
        self._dreg        = get_domain_registry()
        self._domain_tag: str | None = None
        self._node_id:    str | None = None

        # Domains not capped (revelation_cap > 0) → accessible in the grid
        self._accessible_tags: set[str] = {
            tag for tag in self._dreg.all_tags
            if _compute_revelation_cap(state, tag) > 0.0
        }
        # Domains where pool can afford ≥1 unlockable node → eligible-reveal styling
        self._eligible_reveal_tags = _eligible_reveal_domain_tags(state)

    def compose(self) -> "ComposeResult":
        with Vertical(classes="reveal-imago-modal"):
            yield Label("Reveal Imāgō", classes="modal-title")
            yield Label("Domain: —", id="domain-label")
            with Grid(id="reveal-domain-grid"):
                yield from _domain_grid_squares(
                    self._state, self._dreg, self._accessible_tags,
                    eligible_reveal_tags=self._eligible_reveal_tags,
                )
            yield Label("Imāgō: —", id="imago-label")
            with ScrollableContainer(id="reveal-tree-container"):
                pass
            with Horizontal(classes="btn-row"):
                yield Button("← Back",   id="back-btn")
                yield Button("Cancel",   id="cancel-btn",   classes="-danger")
                yield Button("Confirm",  id="confirm-btn",  classes="-primary", disabled=True)

    def on_mount(self) -> None:
        for sq in self.query(DomainSquare):
            if not sq.disabled:
                sq.focus()
                break

    # ── Arrow key routing: domain grid or imago tree ────

    def _nav_imago_tree(self, direction: str) -> None:
        cells = list(self.query(ImagoRevealCell))
        if not cells:
            return
        focused_idx = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused_idx == -1:
            return
        pos_map = {i: p for i, p in enumerate(self._POSITIONS)}
        cur_pos = pos_map.get(focused_idx, (0, 1))
        dr, dc  = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
        r, c    = cur_pos[0] + dr, cur_pos[1] + dc
        while 0 <= r <= 3 and 0 <= c <= 2:
            for i, p in pos_map.items():
                if p == (r, c) and not cells[i].disabled:
                    cells[i].focus()
                    return
            r, c = r + dr, c + dc

    # ── Tab / Shift+Tab section cycling + arrow routing ─

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key in ("up", "down", "left", "right"):
            if isinstance(focused, DomainSquare):
                squares = list(self.query(DomainSquare))
                _nav_domain_grid(squares, event.key)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell):
                self._nav_imago_tree(event.key)
                event.prevent_default(); event.stop()
            return
        if event.key == "tab":
            if isinstance(focused, DomainSquare):
                tag = focused._tag
                self._domain_tag = tag
                self._node_id    = None
                self.query_one("#domain-label", Label).update(
                    f"Domain: {_domain_display_name(tag)}"
                )
                self.query_one("#imago-label", Label).update("Imāgō: —")
                self._check_confirm()
                self._load_reveal_tree(tag, focus_first=True)
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell):
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "confirm-btn":
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, DomainSquare):
                self.query_one("#confirm-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "back-btn":
                cells  = [c for c in self.query(ImagoRevealCell) if not c.disabled]
                if cells:
                    cells[0].focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, ImagoRevealCell):
                squares = list(self.query(DomainSquare))
                target  = next((sq for sq in squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()

    # ── Domain selected (click or Enter on a DomainSquare) ──

    def on_domain_square_focused(self, event: "DomainSquare.Focused") -> None:
        self.query_one("#domain-label", Label).update(
            f"Domain: {_domain_display_name(event.tag)}"
        )

    def on_domain_square_selected(self, event: "DomainSquare.Selected") -> None:
        tag              = event.tag
        self._domain_tag = tag
        self._node_id    = None
        self.query_one("#domain-label", Label).update(
            f"Domain: {_domain_display_name(tag)}"
        )
        self.query_one("#imago-label", Label).update("Imāgō: —")
        self._check_confirm()
        self._load_reveal_tree(tag)

    # ── ImagoRevealCell events ───────────────────────────

    def on_imago_reveal_cell_focused(self, event: "ImagoRevealCell.Focused") -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")

    def on_imago_reveal_cell_selected(self, event: "ImagoRevealCell.Selected") -> None:
        self._node_id = event.node_id
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        name = node.name if node else event.node_id
        self.query_one("#imago-label", Label).update(f"Imāgō: {name}")
        self._check_confirm()

    # ── Confirm gate ─────────────────────────────────────

    def _check_confirm(self) -> None:
        ready = bool(self._domain_tag and self._node_id)
        btn   = self.query_one("#confirm-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    # ── Tree loader ──────────────────────────────────────

    @work
    async def _load_reveal_tree(self, tag: str, *, focus_first: bool = False) -> None:
        tree      = tag.split(":", 1)[1]
        ireg      = get_imago_registry()
        nodes     = ireg.nodes_for_tree(tree)
        rev_count = self._state.demiurge.revealed_imagines

        by_tier: dict[int, list] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)

        container = self.query_one("#reveal-tree-container", ScrollableContainer)
        await container.remove_children()

        cells_and_spacers: list = []
        for tier in (4, 3, 2, 1):
            tnodes = by_tier[tier]
            if tier == 4:
                cells_and_spacers.append(Static("", classes="imago-spacer"))
                node = tnodes[0]
                cells_and_spacers.append(
                    ImagoRevealCell(node, self._state, _revelation_adjusted_cost(node.tier, rev_count))
                )
                cells_and_spacers.append(Static("", classes="imago-spacer"))
            else:
                left, right = tnodes[0], tnodes[1]
                cells_and_spacers.append(
                    ImagoRevealCell(left, self._state, _revelation_adjusted_cost(left.tier, rev_count))
                )
                cells_and_spacers.append(Static("", classes="imago-spacer"))
                cells_and_spacers.append(
                    ImagoRevealCell(right, self._state, _revelation_adjusted_cost(right.tier, rev_count))
                )

        grid = Grid(classes="imago-tree-inner-grid")
        await container.mount(grid)
        await grid.mount(*cells_and_spacers)

        if focus_first:
            cells = [c for c in self.query(ImagoRevealCell) if not c.disabled]
            if cells:
                cells[0].focus()

    # ── Buttons ──────────────────────────────────────────

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        if self._domain_tag and self._node_id:
            self.dismiss(RevealImagoIntent(domain_tag=self._domain_tag, node_id=self._node_id))

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)
```

- [x] **Step 2: Verify `RevealImagoIntent` is imported in `modals.py`**

Search for `RevealImagoIntent` in the imports at the top of `ui/modals.py`. If it's missing, add it to the `from core.action_core import ...` line.

- [x] **Step 3: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 5: Add `ChangeAffiliatedDomainModal` to `ui/modals.py`

Single-screen modal replacing the 2-step Change Affiliated Domain flow. Layout: title → "Domain to Replace: —" label → row of 3 affiliated `DomainSquare` cells + one static placeholder → "New Domain: —" label → 4×4 domain grid (all affiliated domains shown as inaccessible) → buttons.

Pre-selects the first affiliated domain on mount. Dismisses with `(old_tag, new_tag)` tuple, `BACK`, or `None`.

**Files:**
- Modify: `ui/modals.py` (insert after `RevealImagoConfigModal`, before `ImagoRevealModal`)

**Imports needed** (verify at top of `modals.py`; add if missing):
- `ChangeAffiliatedDomainsIntent` from `core.action_core`

- [x] **Step 1: Insert `ChangeAffiliatedDomainModal`**

Find the line `class ImagoRevealModal(ModalScreen):` and insert this class immediately before it (after `RevealImagoConfigModal`):

```python
class ChangeAffiliatedDomainModal(ModalScreen):
    """
    Single-screen Change Affiliated Domain configuration.
    Affiliated row (3 selectable DomainSquares + placeholder) → 4×4 new domain grid → confirm.
    First affiliated domain is pre-selected on mount.
    Dismisses with (old_tag, new_tag) tuple, BACK, or None.
    """

    BINDINGS = [
        ("escape",    "force_cancel", "Cancel"),
        ("backspace", "go_back",      "Back"),
        ("up",        "nav_new('up')",    ""),
        ("down",      "nav_new('down')",  ""),
        ("left",      "nav_new('left')",  ""),
        ("right",     "nav_new('right')", ""),
    ]

    def __init__(self, state: "SimulationState") -> None:
        super().__init__()
        self._state        = state
        self._dreg         = get_domain_registry()
        self._affiliated   = list(state.demiurge.affiliated_domains)  # stable order
        self._old_tag: str | None = self._affiliated[0] if self._affiliated else None
        self._new_tag: str | None = None

        # New domain grid: accessible = all tags not currently affiliated
        affiliated_set = set(self._affiliated)
        self._accessible_new: set[str] = set(self._dreg.all_tags) - affiliated_set

    def compose(self) -> "ComposeResult":
        with Vertical(classes="change-affiliated-modal"):
            yield Label("Change Affiliated Domain", classes="modal-title")
            yield Label(
                f"Domain to Replace: {_domain_display_name(self._old_tag)}" if self._old_tag else "Domain to Replace: —",
                id="old-label",
            )
            with Horizontal(classes="affiliated-domain-row"):
                for tag in self._affiliated:
                    yield DomainSquare(
                        tag=tag,
                        icon=self._dreg.icon(tag),
                        name="",
                        affiliated=True,
                        accessible=True,
                    )
                yield Static("", classes="affiliated-placeholder")
            yield Label("New Domain: —", id="new-label")
            with Grid(id="new-domain-grid"):
                yield from _domain_grid_squares(
                    self._state, self._dreg, self._accessible_new, show_names=True,
                )
            with Horizontal(classes="btn-row"):
                yield Button("← Back",   id="back-btn")
                yield Button("Cancel",   id="cancel-btn",   classes="-danger")
                yield Button("Confirm",  id="confirm-btn",  classes="-primary", disabled=True)

    def on_mount(self) -> None:
        # Pre-select first affiliated domain
        if self._old_tag:
            for sq in self.query(DomainSquare):
                if sq._tag == self._old_tag and sq.has_class("affiliated"):
                    sq.focus()
                    break

    # ── Navigation ───────────────────────────────────────

    def action_nav_new(self, direction: str) -> None:
        squares = [sq for sq in self.query(DomainSquare) if not sq.has_class("affiliated")]
        if any(sq.has_focus for sq in squares):
            _nav_domain_grid(squares, direction, cols=4)

    def on_key(self, event) -> None:
        focused = self.focused
        if event.key == "tab":
            if isinstance(focused, DomainSquare) and focused.has_class("affiliated"):
                new_squares = [sq for sq in self.query(DomainSquare) if not sq.has_class("affiliated")]
                target = next((sq for sq in new_squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare):
                self.query_one("#back-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "confirm-btn":
                aff_squares = [sq for sq in self.query(DomainSquare) if sq.has_class("affiliated")]
                if aff_squares:
                    aff_squares[0].focus()
                event.prevent_default(); event.stop()
        elif event.key == "shift+tab":
            if isinstance(focused, DomainSquare) and focused.has_class("affiliated"):
                self.query_one("#confirm-btn", Button).focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, Button) and focused.id == "back-btn":
                new_squares = [sq for sq in self.query(DomainSquare) if not sq.has_class("affiliated")]
                target = next((sq for sq in new_squares if not sq.disabled), None)
                if target:
                    target.focus()
                event.prevent_default(); event.stop()
            elif isinstance(focused, DomainSquare):
                aff_squares = [sq for sq in self.query(DomainSquare) if sq.has_class("affiliated")]
                if aff_squares:
                    aff_squares[0].focus()
                event.prevent_default(); event.stop()

    # ── Affiliated row selection ─────────────────────────

    def on_domain_square_focused(self, event: "DomainSquare.Focused") -> None:
        sq = event.control if hasattr(event, "control") else None
        # Only update old-label when an affiliated square is focused
        tag = event.tag
        if tag in set(self._affiliated):
            self._old_tag = tag
            self.query_one("#old-label", Label).update(
                f"Domain to Replace: {_domain_display_name(tag)}"
            )
        else:
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(tag)}"
            )

    def on_domain_square_selected(self, event: "DomainSquare.Selected") -> None:
        tag = event.tag
        if tag in set(self._affiliated):
            self._old_tag = tag
            self.query_one("#old-label", Label).update(
                f"Domain to Replace: {_domain_display_name(tag)}"
            )
        else:
            self._new_tag = tag
            self.query_one("#new-label", Label).update(
                f"New Domain: {_domain_display_name(tag)}"
            )
            self._check_confirm()

    def _check_confirm(self) -> None:
        ready = bool(self._old_tag and self._new_tag)
        btn   = self.query_one("#confirm-btn", Button)
        btn.disabled = not ready
        if ready:
            btn.add_class("continue-ready")
        else:
            btn.remove_class("continue-ready")

    # ── Buttons ──────────────────────────────────────────

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        if self._old_tag and self._new_tag:
            self.dismiss((self._old_tag, self._new_tag))

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)
```

- [x] **Step 2: Verify `ChangeAffiliatedDomainsIntent` is imported in `modals.py`**

Check the `from core.action_core import ...` line at the top of `ui/modals.py`. Add `ChangeAffiliatedDomainsIntent` if missing. (Note: the intent is used in `ui.py` wiring, but verifying now is cheap.)

- [x] **Step 3: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 6: Wire new modals in `ui/ui.py`

Replace `_build_reveal_imago_intent` and the `change_affiliated_domains` block with the new single-modal flows.

**Files:**
- Modify: `ui/ui.py`

### Step 1: Add imports at the top of `ui/ui.py`

- [x] Find the import block that imports modal classes from `ui/modals.py`. Add `NoUnlockableModal`, `RevealImagoConfigModal`, `ChangeAffiliatedDomainModal` to it. Remove `ImagoRevealModal` and `ImagoRevealDetailModal` from the same import line (they will be deleted in Task 7).

Also check the `from core.action_core import` line — ensure `ExploreBeliefIntent` is present (needed for the Explore Beliefs routing from `NoUnlockableModal`).

### Step 2: Replace the `reveal_imago` block

- [x] Find this block in `ui/ui.py` (currently around line 1768):

```python
            if action_key == "reveal_imago":
                return await self._build_reveal_imago_intent(state)
```

Replace it with:

```python
            if action_key == "reveal_imago":
                _ireg     = get_imago_registry()
                _unlocked = set(state.demiurge.unlocked_imagines)
                _has_unlockable = any(
                    _ireg.is_unlockable(n.node_id, _unlocked)
                    for _tag in get_domain_registry().all_tags
                    for n in _ireg.nodes_for_tree(_tag.split(":", 1)[1])
                )
                if not _has_unlockable:
                    gate_result = await self.app.push_screen_wait(NoUnlockableModal())
                    if gate_result is None:
                        return None
                    if gate_result == BACK:
                        return BACK
                    # gate_result == "explore_beliefs" — route to Explore Beliefs
                    dreg  = get_domain_registry()
                    capped = {
                        tag for tag in dreg.all_tags
                        if _compute_revelation_cap(state, tag) == 0.0
                        or state.demiurge.revelation_pools.get(tag, 0.0)
                            >= _compute_revelation_cap(state, tag)
                    }
                    eb_result = await self.app.push_screen_wait(
                        ExploreBeliefsModal(state, capped_domains=capped)
                    )
                    if eb_result is None:
                        return None
                    if eb_result == BACK:
                        return BACK
                    tag, t1_one, t1_both, t2_one, t2_both, t3_one, t3_both = eb_result
                    return ExploreBeliefIntent(
                        domain_tag=tag,
                        stop_on_t1_one=t1_one,   stop_on_t1_both=t1_both,
                        stop_on_t2_one=t2_one,   stop_on_t2_both=t2_both,
                        stop_on_t3_one=t3_one,   stop_on_t3_both=t3_both,
                    )
                result = await self.app.push_screen_wait(RevealImagoConfigModal(state))
                if result is None:
                    return None
                if result == BACK:
                    return BACK
                return result  # RevealImagoIntent
```

Note: The unlockable check is inlined directly using `get_imago_registry()` and `get_domain_registry()`, which are already imported in `ui/ui.py`. No new imports needed for the check itself.

### Step 3: Replace the `change_affiliated_domains` block

- [x] Find this block in `ui/ui.py` (currently around line 1771–1797):

```python
            if action_key == "change_affiliated_domains":
                if not state.demiurge.affiliated_domains:
                    self.app.notify("No affiliated domains to swap.", severity="warning")
                    return None
                step = 0; old_tag = None
                while True:
                    if step == 0:
                        result = await self.app.push_screen_wait(
                            PickerModal(
                                title="Drop which affiliated domain?",
                                items=[(t, t.split(":", 1)[1].title()) for t in state.demiurge.affiliated_domains],
                                show_back=True,
                            )
                        )
                        if result is None: return None
                        if result == BACK: return BACK
                        old_tag = result; step = 1
                    if step == 1:
                        exclude = set(state.demiurge.affiliated_domains)
                        new_tag = await self.app.push_screen_wait(
                            DomainPickerModal(state, exclude_tags=exclude)
                        )
                        if new_tag is None: return None
                        if new_tag == BACK: step = 0; continue
                        if not new_tag: step = 0; continue
                        break
                return ChangeAffiliatedDomainsIntent(old_domain=old_tag, new_domain=new_tag)
```

Replace the entire block with:

```python
            if action_key == "change_affiliated_domains":
                if not state.demiurge.affiliated_domains:
                    self.app.notify("No affiliated domains to swap.", severity="warning")
                    return None
                result = await self.app.push_screen_wait(ChangeAffiliatedDomainModal(state))
                if result is None:
                    return None
                if result == BACK:
                    return BACK
                old_tag, new_tag = result
                return ChangeAffiliatedDomainsIntent(old_domain=old_tag, new_domain=new_tag)
```

### Step 4: Delete `_build_reveal_imago_intent`

- [x] Find and delete the entire `_build_reveal_imago_intent` method (currently lines ~1859–1927 in `ui/ui.py`). It's no longer called.

- [x] **Step 5: Verify autoplay**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

---

## Task 7: Delete `ImagoRevealModal` and `ImagoRevealDetailModal` from `ui/modals.py`

These two classes are fully replaced by `RevealImagoConfigModal`. They must be deleted cleanly.

**Files:**
- Modify: `ui/modals.py`

- [ ] **Step 1: Delete `ImagoRevealModal`**

Find and delete the entire `ImagoRevealModal` class (currently lines ~1002–1107 in `ui/modals.py`). It starts at `class ImagoRevealModal(ModalScreen):` and ends before `class ImagoRevealDetailModal(ModalScreen):`.

- [ ] **Step 2: Delete `ImagoRevealDetailModal`**

Find and delete the entire `ImagoRevealDetailModal` class (currently lines ~1109–1228 in `ui/modals.py`). It ends before the `# ─────────────────────────────────────────\n# MORTAL DETAIL MODAL` comment block.

- [ ] **Step 3: Check for any remaining references**

```bash
grep -n "ImagoRevealModal\|ImagoRevealDetailModal" /root/demiurge/ui/modals.py /root/demiurge/ui/ui.py
```

Expected: no output. If any references remain, remove them.

- [ ] **Step 4: Final autoplay run**

```bash
cd /root/demiurge && source bin/activate && python main.py --autoplay
```
Expected: 50 ticks, no exceptions.

- [ ] **Step 5: Commit**

```bash
cd /root/demiurge && git add ui/modals.py ui/styles.tcss ui/ui.py && git commit -m "feat: collapse Reveal Imāgō and Change Affiliated Domain into single modals

- Add NoUnlockableModal gate for Reveal Imāgō when no nodes are unlockable
- Add RevealImagoConfigModal (domain grid + ImagoRevealCell tree + confirm)
- Add ChangeAffiliatedDomainModal (affiliated row + new domain grid + confirm)
- Delete ImagoRevealModal and ImagoRevealDetailModal
- Add _has_any_unlockable and _eligible_reveal_domain_tags helpers"
```

---

## Known edge cases to check manually after execution

- **`on_domain_square_focused` in `ChangeAffiliatedDomainModal`**: `DomainSquare.Focused` events bubble up from both affiliated cells and new-domain cells. The handler distinguishes by checking `tag in set(self._affiliated)`. Verify this works correctly with both rows in the same modal.
- **`_load_reveal_tree` async timing**: If the user tabs quickly before the `@work` finishes mounting the tree, focus on the first reveal cell may fail silently. This is acceptable — same behavior as Whisper's `_swap_imago_tree`.
