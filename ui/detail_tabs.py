"""
DetailTab + DetailTabManager.

A DetailTab is one slot in the right panel's TabbedContent dedicated to
inspecting a single entity. The manager owns the set of detail panes,
enforces the cap (6), and handles LRU eviction of unpinned tabs.

Navigation within a single detail tab is supported via a per-tab history
stack: clicking a related entity inside a detail body pushes onto the tab's
history; `back()` pops back to the previous view. (Wiring of in-body clicks
happens in Phase 3; the data structures are ready now.)

Pin state is shown in the tab body header (the strip above the breadcrumb),
while the tab strip label tracks the current entity as the user navigates.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text
from textual.widgets import TabPane

from ui.widgets import ContentTab, set_detail_render
from ui.detail_renderers import RENDERERS

if TYPE_CHECKING:
    from textual.widgets import TabbedContent
    from textual.screen import Screen
    from logic.tick_logic import SimulationState


class DetailTab(ContentTab):
    """One detail-tab body. Holds (kind, id, name) history + pin flag."""

    def __init__(self, kind: str, entity_id: str, name: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._history: list[tuple[str, str, str]] = [(kind, str(entity_id), name)]
        self._pinned: bool = False

    @property
    def current(self) -> tuple[str, str, str]:
        return self._history[-1]

    @property
    def kind(self) -> str:
        return self.current[0]

    @property
    def entity_id(self) -> str:
        return self.current[1]

    @property
    def name(self) -> str:
        return self.current[2]

    @property
    def pinned(self) -> bool:
        return self._pinned

    def toggle_pin(self) -> None:
        self._pinned = not self._pinned

    def navigate_to(self, kind: str, entity_id: str, name: str) -> None:
        """Push a new entity onto this tab's history."""
        self._history.append((kind, str(entity_id), name))

    def back(self) -> bool:
        """Pop the top of history if there's somewhere to go back to."""
        if len(self._history) > 1:
            self._history.pop()
            return True
        return False

    def jump_to_index(self, idx: int) -> bool:
        """Truncate history so that the entry at `idx` becomes current. Returns
        True if the stack actually moved."""
        if idx < 0 or idx >= len(self._history) - 1:
            return False
        del self._history[idx + 1:]
        return True

    def _render_body(self, state: "SimulationState") -> Text:
        kind, eid, _name = self.current
        renderer = RENDERERS.get(kind)
        if renderer is None:
            body = Text.from_markup(f"[#b04050]Unknown entity kind: {_e(kind)}[/]")
        else:
            # While rendering inside a detail tab, entity links navigate the
            # tab's history in place instead of opening new tabs.
            set_detail_render(True)
            try:
                body = renderer(state, eid)
            finally:
                set_detail_render(False)

        # Header strip: pin indicator + breadcrumb (when there's more than one entry).
        header_parts: list[str] = []
        if self._pinned:
            header_parts.append("[#c09030]★ pinned[/]")
        if len(self._history) > 1:
            crumb_pieces: list[str] = []
            last_idx = len(self._history) - 1
            for i, (_k, _eid, n) in enumerate(self._history):
                escaped = _e(n)
                if i == last_idx:
                    # Current view — bold, not a link.
                    crumb_pieces.append(f"[bold #c0ccdc]{escaped}[/]")
                else:
                    crumb_pieces.append(
                        f"[@click=screen.detail_back_to_index({i})]"
                        f"[#5a7090]{escaped}[/][/]"
                    )
            crumbs = "  [#3a4a60]›[/]  ".join(crumb_pieces)
            header_parts.append(crumbs)
        if not header_parts:
            return body
        header_markup = "    ".join(header_parts) + "\n\n"
        return Text.from_markup(header_markup) + body


class DetailTabManager:
    """Owns the dynamic detail panes in the right TabbedContent."""

    CAP = 6
    """Maximum simultaneous detail tabs (independent of Briefing state)."""

    def __init__(self, screen: "Screen", tabs_widget: "TabbedContent") -> None:
        self._screen = screen
        self._tabs = tabs_widget
        self._panes: dict[str, DetailTab] = {}    # pane_id → DetailTab
        self._mru: list[str] = []                 # pane_ids, oldest first
        self._counter = 0

    # ── Public API ────────────────────────────

    def open(
        self,
        kind: str,
        entity_id: str,
        name: str,
        state: "SimulationState",
    ) -> None:
        """Open (or re-focus) a detail tab for the given entity."""
        # If an open tab matches kind+id at its current view, just activate it.
        for pid, dt in self._panes.items():
            if dt.kind == kind and dt.entity_id == str(entity_id):
                self._touch_mru(pid)
                self._activate(pid)
                return

        # Evict if at cap.
        if len(self._panes) >= self.CAP:
            self._evict_lru_unpinned()

        pane_id = self._next_pane_id()
        body = DetailTab(kind, entity_id, name)
        pane = TabPane(name, body, id=pane_id)
        self._tabs.add_pane(pane, before="log")
        self._panes[pane_id] = body
        self._mru.append(pane_id)
        # The new pane mounts asynchronously; defer the initial render.
        self._screen.call_after_refresh(lambda: self._post_open(pane_id, state))

    def refresh_all(self, state: "SimulationState") -> None:
        """Re-render every open detail tab against the current state."""
        for dt in list(self._panes.values()):
            try:
                dt.refresh_state(state)
            except Exception:
                # An entity may have been deleted between ticks; renderer handles
                # the not-found case. Other exceptions are swallowed defensively
                # so a bad tab can't block the rest of the refresh.
                pass

    def close_focused(self) -> bool:
        """Close the currently active detail pane if one is focused."""
        pid = self._active_detail_pane_id()
        if pid is None:
            return False
        self._close_pane(pid)
        return True

    def toggle_pin_focused(self, state: "SimulationState") -> "tuple[bool, str]":
        """Toggle pin on the focused detail tab. Returns (ok, message)."""
        pid = self._active_detail_pane_id()
        if pid is None:
            return False, "No detail tab focused."
        dt = self._panes[pid]
        if not dt.pinned:
            unpinned = sum(1 for d in self._panes.values() if not d.pinned)
            if unpinned <= 1:
                return False, "At least one detail tab must stay unpinned."
        dt.toggle_pin()
        dt.refresh_state(state)
        return True, ("pinned" if dt.pinned else "unpinned")

    def navigate_active(
        self,
        kind: str,
        entity_id: str,
        name: str,
        state: "SimulationState",
    ) -> bool:
        """Push (kind, id) onto the active detail tab's history. False if
        no detail tab is active or kind has no renderer."""
        pid = self._active_detail_pane_id()
        if pid is None:
            return False
        if kind not in RENDERERS:
            return False
        dt = self._panes[pid]
        if dt.kind != kind or dt.entity_id != str(entity_id):
            dt.navigate_to(kind, str(entity_id), name)
            self._update_tab_label(pid)
        dt.refresh_state(state)
        return True

    def jump_active_to_index(self, idx: int, state: "SimulationState") -> bool:
        """Pop the active tab's history back to `idx` (a breadcrumb click)."""
        pid = self._active_detail_pane_id()
        if pid is None:
            return False
        dt = self._panes[pid]
        if dt.jump_to_index(idx):
            self._update_tab_label(pid)
            dt.refresh_state(state)
            return True
        return False

    def _update_tab_label(self, pane_id: str) -> None:
        """Sync the tab strip label with the active DetailTab's current entity."""
        dt = self._panes.get(pane_id)
        if dt is None:
            return
        try:
            self._tabs.get_tab(pane_id).label = dt.name
        except Exception:
            pass

    def back_focused(self, state: "SimulationState") -> bool:
        """Pop the focused detail tab's history. Returns True if moved."""
        pid = self._active_detail_pane_id()
        if pid is None:
            return False
        dt = self._panes[pid]
        if dt.back():
            self._update_tab_label(pid)
            dt.refresh_state(state)
            return True
        return False

    # ── Introspection helpers ─────────────────

    def is_detail_pane_active(self) -> bool:
        return self._active_detail_pane_id() is not None

    def open_count(self) -> int:
        return len(self._panes)

    # ── Internals ─────────────────────────────

    def _next_pane_id(self) -> str:
        self._counter += 1
        return f"detail-{self._counter}"

    def _active_detail_pane_id(self) -> "str | None":
        active = self._tabs.active
        return active if active in self._panes else None

    def _touch_mru(self, pane_id: str) -> None:
        if pane_id in self._mru:
            self._mru.remove(pane_id)
        self._mru.append(pane_id)

    def _activate(self, pane_id: str) -> None:
        self._tabs.active = pane_id

    def _post_open(self, pane_id: str, state: "SimulationState") -> None:
        if pane_id not in self._panes:
            return
        try:
            self._panes[pane_id].refresh_state(state)
        except Exception:
            pass
        self._activate(pane_id)

    def _evict_lru_unpinned(self) -> None:
        for pid in list(self._mru):
            dt = self._panes.get(pid)
            if dt is not None and not dt.pinned:
                self._close_pane(pid)
                return
        # Should not occur — pinning is gated to keep one unpinned. Fall back
        # to oldest pane if every tab is pinned (which would mean someone broke
        # the invariant).
        if self._mru:
            self._close_pane(self._mru[0])

    def _close_pane(self, pane_id: str) -> None:
        try:
            self._tabs.remove_pane(pane_id)
        except Exception:
            pass
        self._panes.pop(pane_id, None)
        if pane_id in self._mru:
            self._mru.remove(pane_id)
