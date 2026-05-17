"""
Custom Textual widgets and the status-bar renderer.

LoopingListView   — ListView with wrap-around cursor + Home/End keys.
DomainSquare      — clickable domain cell in the picker grid.
ImagoCell         — clickable cell in the Imago tree picker.
ImagoRevealCell   — clickable cell in the Imago reveal picker (cost + eligibility).
StatusPanel       — Static widget that hosts the right-side status bar.
_render_status    — builds the Rich Text rendered into StatusPanel.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListView, Static

from logic.tick_logic import is_in_window
from utilities.imago_registry import get_registry as get_imago_registry

from display import _personality_label

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState
    from utilities.imago_registry import ImagoNode


# ─────────────────────────────────────────
# Looping list view
# ─────────────────────────────────────────

class LoopingListView(ListView):
    """ListView with wrap-around navigation and Home/End key support."""

    def action_cursor_up(self) -> None:
        n = len(self._nodes)
        if n == 0:
            return
        if self.index is None or self.index <= 0:
            self.index = n - 1
        else:
            super().action_cursor_up()

    def action_cursor_down(self) -> None:
        n = len(self._nodes)
        if n == 0:
            return
        if self.index is None or self.index >= n - 1:
            self.index = 0
        else:
            super().action_cursor_down()

    def key_home(self) -> None:
        if self._nodes:
            self.index = 0

    def key_end(self) -> None:
        n = len(self._nodes)
        if n:
            self.index = n - 1


# ─────────────────────────────────────────
# Domain picker grid cell
# ─────────────────────────────────────────

class DomainSquare(Widget):
    """One cell in the domain picker grid."""

    can_focus = True

    class Focused(Message):
        def __init__(self, tag: str) -> None:
            super().__init__()
            self.tag = tag

    class Selected(Message):
        def __init__(self, tag: str) -> None:
            super().__init__()
            self.tag = tag

    def __init__(self, tag: str, icon: str, name: str, affiliated: bool, accessible: bool, eligible_reveal: bool = False) -> None:
        classes = []
        if affiliated and accessible:
            classes.append("affiliated")
        if not accessible:
            classes.append("inactive")
        if eligible_reveal and accessible:
            classes.append("eligible-reveal")
        super().__init__(classes=" ".join(classes), disabled=not accessible)
        self._tag  = tag
        self._icon = icon
        self._name = name

    def render(self) -> Text:
        return Text.from_markup(f"{self._icon or '?'}\n{self._name}", justify="center")

    def on_focus(self) -> None:
        self.post_message(self.Focused(self._tag))

    def on_enter(self) -> None:
        self.post_message(self.Focused(self._tag))

    def on_click(self) -> None:
        if not self.disabled:
            self.post_message(self.Selected(self._tag))

    def key_enter(self) -> None:
        if not self.disabled:
            self.post_message(self.Selected(self._tag))


# ─────────────────────────────────────────
# Imago tree cell
# ─────────────────────────────────────────

class ImagoCell(Widget):
    """One cell in the Imago tree picker."""

    can_focus = True

    class Focused(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    class Selected(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    def __init__(self, node: "ImagoNode", unlocked: bool, approval_class: str) -> None:
        classes = [approval_class] if (unlocked and approval_class) else []
        if not unlocked:
            classes.append("inactive")
        super().__init__(classes=" ".join(classes))
        self._node     = node
        self._unlocked = unlocked

    def render(self) -> Text:
        return Text(self._node.name, justify="center")

    def on_focus(self) -> None:
        self.post_message(self.Focused(self._node.node_id))

    def on_enter(self) -> None:
        self.post_message(self.Focused(self._node.node_id))

    def on_click(self) -> None:
        if self._unlocked:
            self.post_message(self.Selected(self._node.node_id))

    def key_enter(self) -> None:
        if self._unlocked:
            self.post_message(self.Selected(self._node.node_id))


# ─────────────────────────────────────────
# Imago reveal cell
# ─────────────────────────────────────────

class ImagoRevealCell(Widget):
    """One cell in the Imago reveal tree picker."""

    can_focus = True

    class Focused(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    class Selected(Message):
        def __init__(self, node_id: str) -> None:
            super().__init__()
            self.node_id = node_id

    def __init__(self, node: "ImagoNode", state: "SimulationState", cost: int) -> None:
        unlocked = node.node_id in state.demiurge.unlocked_imagines
        pool = state.demiurge.revelation_pools.get(f"domain:{node.tree}", 0.0)
        ireg = get_imago_registry()
        unlocked_set = set(state.demiurge.unlocked_imagines)
        prereqs_met = ireg.is_unlockable(node.node_id, unlocked_set)
        affordable = pool >= cost
        self._unlocked    = unlocked
        self._prereqs_met = prereqs_met
        self._affordable  = affordable
        self._cost        = cost

        if unlocked:
            classes = ["inactive"]          # already revealed
            disabled = True
        elif prereqs_met and affordable:
            classes = ["imago-eligible"]    # can reveal
            disabled = False
        else:
            classes = ["inactive"]          # locked or unaffordable
            disabled = True

        super().__init__(classes=" ".join(classes), disabled=disabled)
        self._node = node

    def render(self) -> "Text":
        name_line = self._node.name
        if self._unlocked:
            cost_line = "✓ Revealed"
        else:
            cost_line = f"{self._cost} Rev"
        return Text.from_markup(f"{name_line}\n[dim]{cost_line}[/]", justify="center")

    def on_focus(self) -> None:
        self.post_message(self.Focused(self._node.node_id))

    def on_enter(self) -> None:
        self.post_message(self.Focused(self._node.node_id))

    def on_click(self) -> None:
        if not self.disabled:
            self.post_message(self.Selected(self._node.node_id))

    def key_enter(self) -> None:
        if not self.disabled:
            self.post_message(self.Selected(self._node.node_id))


# ─────────────────────────────────────────
# Status panel
# ─────────────────────────────────────────

def _render_status(state: "SimulationState") -> Text:
    """Build a Rich Text object for the status panel."""
    lines: list[str] = []
    a = lines.append

    a(f"[bold #4a80b0]━━ STATUS ━━[/]")
    a(f"[#3a6090]{_e(state.universe.name)}[/]")
    a(f"[#2a4a6a]Age {state.universe.current_age:.1f}  ·  Tick {state.tick_number}[/]")
    a("")

    # Essence
    es = state.essence
    fp = state.demiurge.footprint
    ci = es.concealment_integrity
    ci_col = "#50b870" if ci > 0.6 else ("#c09030" if ci > 0.3 else "#b04050")
    a("[bold #4a80b0]ESSENCE[/]")
    a(f"  actual [bold]{es.actual:.2f}[/]  apparent [bold]{es.apparent:.2f}[/]")
    a(f"  concealment [{ci_col}]{ci:.2f}[/]")
    a("")

    # Footprint
    a("[bold #4a80b0]FOOTPRINT[/]")
    a(f"  overt  [#b06050]{fp.overt_miracles:.2f}[/]  "
      f"subtle [#9060a0]{fp.subtle_influence:.2f}[/]")
    a(f"  proxii [#60a070]{fp.proxius_activity:.2f}[/]  "
      f"create [#6080c0]{fp.direct_creation:.2f}[/]")
    a("")

    # Luminaries
    a("[bold #4a80b0]LUMINARIES[/]")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        rc  = "#50b870" if d.results >= 0 else "#b04050"
        mc  = "#50b870" if d.methods  >= 0 else "#b04050"
        ac  = "#c09030" if att > 0.5       else "#2a4a6a"
        a(f"  [bold #c0ccdc]{_e(lum.name)}[/] [#3a5a7a]({_e(_personality_label(lum))})[/]")
        a(f"    R[{rc}]{d.results:+.2f}[/] "
          f"M[{mc}]{d.methods:+.2f}[/] "
          f"att[{ac}]{att:.2f}[/]")
    a("")

    # Worlds
    a("[bold #4a80b0]WORLDS[/]")
    cond_colors = {
        "thriving": "#50b870",
        "stable":   "#3a6a8a",
        "stressed": "#c09030",
        "dying":    "#b04050",
        "barren":   "#604040",
    }
    for wid, world in state.worlds.items():
        if not is_in_window(world):
            continue
        cc = cond_colors.get(world.condition.value, "#707070")
        vis_tag = f" [#5a7090]\\[vis:{world.visibility:.2f}][/]" if not world.pinned else ""
        a(f"  [{cc}]●[/] [bold]{_e(world.name)}[/] [{cc}]{_e(world.condition.value)}[/]{vis_tag}")
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if civ and is_in_window(civ):
                h = civ.health
                a(f"    [#2a4060]└[/] [#8090a0]{_e(civ.name)}[/]")
                a(f"      [#2a4060]S{h.stability:.1f} P{h.prosperity:.1f} C{h.cohesion:.1f}[/]")
    a("")

    # Queue / ongoing
    q_count = len(state.action_queue)
    o_count = len(state.ongoing_actions)
    if q_count or o_count:
        a("[bold #4a80b0]QUEUE[/]")
        if q_count:
            a(f"  [#c09030]{q_count}[/] queued this tick")
        for cat_val, oa in state.ongoing_actions.items():
            label = cat_val.replace("_", " ").title()
            a(f"  [#2a4060]({_e(label)})[/]")
            a(f"  [#3a6a50]{_e(oa.action_key.replace('_',' '))}[/] "
              f"[#2a4060]{oa.executed_ticks}x[/]")

    return Text.from_markup("\n".join(lines))


class StatusPanel(Static):
    def refresh_state(self, state: "SimulationState") -> None:
        self.update(_render_status(state))
