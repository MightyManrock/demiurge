"""
Custom Textual widgets, the status-bar renderer, and tab body widgets.

LoopingListView   — ListView with wrap-around cursor + Home/End keys.
DomainSquare      — clickable domain cell in the picker grid.
ImagoCell         — clickable cell in the Imago tree picker.
ImagoRevealCell   — clickable cell in the Imago reveal picker (cost + eligibility).
StatusPanel       — Static widget that hosts the Status tab body.
_render_status    — builds the Rich Text rendered into StatusPanel.

Tab body widgets (Phase 1):
    LocationsTab, EntitiesTab, ActionsTab — left panel tabs.
    BriefingTab, UniverseTab, LuminariesTab — right panel tabs.
Each has refresh_state(state) which redraws from the current SimulationState.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text
from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll, Vertical
from textual.message import Message
from textual.widget import Widget
from textual.widgets import ListView, RichLog, Static

from core.universe_core import MortalRole, MortalStatus
from logic.tick_logic import is_in_window, ENTITY_VISIBILITY_FLOOR

import display
from display import (
    _personality_label, _format_beliefs, _format_culture, _prominence_label,
    _name_for_id, _short_tag, _trait_color,
    _format_beliefs_markup, _format_culture_markup, _color_short_tag,
    display_briefing, _lines_to_text,
)
from utilities.imago_registry import get_registry as get_imago_registry

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState
    from utilities.imago_registry import ImagoNode


def _click_link(kind: str, eid: str, label_markup: str) -> str:
    """
    Wrap `label_markup` in a Textual click-action span that opens a detail tab
    for the given entity.

    Uses the `screen.` namespace so the dispatch goes straight to
    `GameScreen.action_open_detail_by_id` regardless of which widget owns the
    markup. UUIDs and fixed-kind strings are safe to inline (only hex+dashes,
    no quotes).
    """
    return f"[@click=screen.open_detail_by_id('{kind}','{eid}')]{label_markup}[/]"


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

    # At-a-glance reminder; full list lives on the Actions tab.
    q_count = len(state.action_queue)
    o_count = len(state.ongoing_actions)
    if q_count or o_count:
        a(f"[#5a7090]queue:[/] [#c09030]{q_count}[/]"
          f"  [#5a7090]ongoing:[/] [#60a070]{o_count}[/]")

    return Text.from_markup("\n".join(lines))


class StatusPanel(Static):
    def refresh_state(self, state: "SimulationState") -> None:
        self.update(_render_status(state))


# ─────────────────────────────────────────
# Tab body widgets (Phase 1 of UI overhaul)
# ─────────────────────────────────────────

class ContentTab(VerticalScroll):
    """Base class for scrollable tab bodies; subclasses implement _render()."""

    def compose(self) -> ComposeResult:
        # `expand=True` makes the Static fill the container's width so Rich's
        # word-wrap calculation matches the visible area instead of the
        # renderable's natural width. Without this, long colored markup lines
        # overshoot the right edge before wrapping.
        yield Static(classes="tab-body", expand=True)

    def _render_body(self, state: "SimulationState") -> "Text | str":
        raise NotImplementedError

    def refresh_state(self, state: "SimulationState") -> None:
        self.query_one(Static).update(self._render_body(state))


class LocationsTab(ContentTab):
    """Left-panel tab: tree of in-Window Galaxy → System → World."""

    def _render_body(self, state: "SimulationState") -> Text:
        dev = display.DEV_MODE
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ LOCATIONS ━━[/]")
        a("")
        any_shown = False
        for gid, galaxy in state.galaxies.items():
            g_oow = not is_in_window(galaxy)
            if g_oow and not dev:
                continue
            any_shown = True
            g_style = "[dim]" if g_oow else ""
            g_end = "[/]" if g_oow else ""
            a(f"{g_style}◇ [bold]{_e(galaxy.name)}[/]{g_end}")
            for sid in galaxy.child_ids:
                sys_obj = state.locations.get(str(sid))
                if not sys_obj:
                    continue
                s_oow = not is_in_window(sys_obj)
                if s_oow and not dev:
                    continue
                s_style = "[dim]" if (g_oow or s_oow) else ""
                s_end = "[/]" if (g_oow or s_oow) else ""
                star = getattr(sys_obj, "star_type", None)
                star_str = f" \\[{_e(star.value)}]" if star is not None else ""
                sys_link = _click_link("system", str(sid), _e(sys_obj.name))
                a(f"{s_style}  ◆ {sys_link}{star_str}{s_end}")
                for wid in getattr(sys_obj, "child_ids", []):
                    world = state.worlds.get(str(wid))
                    if not world:
                        continue
                    w_oow = not is_in_window(world)
                    if w_oow and not dev:
                        continue
                    w_style = "[dim]" if (g_oow or s_oow or w_oow) else ""
                    w_end = "[/]" if (g_oow or s_oow or w_oow) else ""
                    world_link = _click_link("world", str(wid), _e(world.name))
                    a(f"{w_style}    • {world_link} "
                      f"[#5a7090]{_e(world.condition.value)}[/]{w_end}")
        if not any_shown:
            a("[#5a7090](nothing within the Window)[/]")
        return Text.from_markup("\n".join(lines))


class EntitiesTab(ContentTab):
    """Left-panel tab: in-Window civilizations and currently-appointed Proxiī."""

    def _render_body(self, state: "SimulationState") -> Text:
        dev = display.DEV_MODE
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ CIVILIZATIONS ━━[/]")
        a("")
        any_civ = False
        for cid, civ in state.civilizations.items():
            c_oow = not is_in_window(civ)
            if c_oow and not dev:
                continue
            any_civ = True
            h = civ.health
            origin = state.locations.get(str(civ.origin_location_id)) if civ.origin_location_id else None
            origin_name = origin.name if origin else "?"
            style = "[dim]" if c_oow else ""
            end = "[/]" if c_oow else ""
            civ_link = _click_link("civ", str(cid), f"[bold]{_e(civ.name)}[/]")
            a(f"{style}● {civ_link} "
              f"[#5a7090]\\[{_e(civ.scale.value)}][/] "
              f"[#3a6a8a]{_e(origin_name)}[/]{end}")
            a(f"{style}    S{h.stability:.1f} P{h.prosperity:.1f} C{h.cohesion:.1f}{end}")
        if not any_civ:
            a("[#5a7090](none in Window)[/]")
        a("")
        a("[bold #4a80b0]━━ PROXIĪ ━━[/]")
        a("")
        any_pr = False
        for mid, m in state.mortals.items():
            if m.role != MortalRole.PROXIUS or m.status == MortalStatus.DECEASED:
                continue
            any_pr = True
            w_obj = state.locations.get(str(m.current_location)) if m.current_location else None
            loc = w_obj.name if w_obj else "?"
            tag = " \\[DORMANT]" if m.status == MortalStatus.DORMANT else ""
            if m.active_goal is None:
                goal = "idle"
            elif m.active_goal.last_action is not None:
                goal = m.active_goal.last_action.value.replace("_", " ")
            else:
                goal = "directed"
            m_link = _click_link("mortal", str(mid), f"[bold]{_e(m.name)}[/]")
            a(f"● {m_link}{tag}")
            a(f"    [#3a6a8a]{_e(loc)}[/]  [#5a7090]{_e(goal)}[/]  "
              f"align:[#a0d080]{m.alignment:.2f}[/]")
        if not any_pr:
            a("[#5a7090](no Proxiī appointed)[/]")
        return Text.from_markup("\n".join(lines))


class ActionsTab(ContentTab):
    """Left-panel tab: queued (this tick) + ongoing actions."""

    def _render_body(self, state: "SimulationState") -> Text:
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ QUEUED THIS TICK ━━[/]")
        a("")
        if state.action_queue:
            for ai in state.action_queue:
                tgt = ""
                if ai.target_id:
                    tgt = f"  → [#3a6a8a]{_e(_name_for_id(ai.target_id, state))}[/]"
                a(f"  • [#a0d080]{_e(ai.intent.__class__.__name__ if ai.intent else 'Action')}[/]"
                  f"{tgt}")
        else:
            a("[#5a7090]  (none queued)[/]")
        a("")
        a("[bold #4a80b0]━━ ONGOING ━━[/]")
        a("")
        if state.ongoing_actions:
            for cat_val, oa in state.ongoing_actions.items():
                cat = cat_val.replace("_", " ").title()
                key = oa.action_key.replace("_", " ").title()
                tgt = ""
                if oa.target_id:
                    tgt = f"  → [#3a6a8a]{_e(_name_for_id(oa.target_id, state))}[/]"
                a(f"  [#5a7090]({_e(cat)})[/]")
                a(f"    [#60a070]{_e(key)}[/]{tgt}  "
                  f"[#2a4060]{oa.executed_ticks}/{oa.ticks_active} ticks[/]")
        else:
            a("[#5a7090]  (none)[/]")
        return Text.from_markup("\n".join(lines))


class BriefingTab(ContentTab):
    """Right-panel tab: scenario briefing."""

    def _render_body(self, state: "SimulationState") -> Text:
        return _lines_to_text(display_briefing(state, dev_mode=display.DEV_MODE))


class UniverseTab(ContentTab):
    """Right-panel tab: in-Window worlds (with civs/pops) + notable mortals."""

    def _render_body(self, state: "SimulationState") -> Text:
        dev = display.DEV_MODE
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ WORLDS ━━[/]")
        a("")
        any_w = False
        for wid, world in state.worlds.items():
            w_oow = not is_in_window(world)
            if w_oow and not dev:
                continue
            any_w = True
            wm = "[dim]" if w_oow else ""
            we = "[/]" if w_oow else ""
            vis_note = f"  \\[vis:{world.visibility:.2f}]" if not world.pinned else ""
            domain_str = _format_beliefs_markup(world.domain_expression) or "[#5a7090]none[/]"
            world_link = _click_link("world", str(wid), f"[bold]{_e(world.name)}[/]")
            a(f"{wm}● {world_link}  "
              f"\\[{_e(world.condition.value)}]{vis_note}{we}")
            a(f"{wm}    domain: {domain_str}{we}")
            for cid in world.civilization_ids:
                civ = state.civilizations.get(str(cid))
                if not civ:
                    continue
                c_oow = not is_in_window(civ)
                if c_oow and not dev:
                    continue
                cm = "[dim]" if (w_oow or c_oow) else ""
                ce = "[/]" if (w_oow or c_oow) else ""
                h = civ.health
                civ_vis = f"  \\[vis:{civ.visibility:.2f}]" if not civ.pinned else ""
                civ_link = _click_link("civ", str(cid), f"[bold]{_e(civ.name)}[/]")
                a(f"{cm}    └─ {civ_link} "
                  f"\\[{_e(civ.scale.value)}]{civ_vis}  "
                  f"S{h.stability:.2f} P{h.prosperity:.2f} C{h.cohesion:.2f}{ce}")
                if civ.dominant_beliefs:
                    a(f"{cm}       beliefs: {_format_beliefs_markup(civ.dominant_beliefs)}{ce}")
                if civ.culture_tags:
                    a(f"{cm}       culture: {_format_culture_markup(civ.culture_tags)}{ce}")
                for pid in civ.pop_ids:
                    pop = state.pops.get(str(pid))
                    if not pop:
                        continue
                    p_oow = not is_in_window(pop)
                    if p_oow and not dev:
                        continue
                    pm = "[dim]" if (w_oow or c_oow or p_oow) else ""
                    pe = "[/]" if (w_oow or c_oow or p_oow) else ""
                    class_label = pop.stratum.title() if pop.stratum else "Pop"
                    sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                    sp_note = f"  ({sp_obj.name})" if sp_obj else ""
                    top_beliefs = sorted(pop.dominant_beliefs.items(), key=lambda x: -x[1])[:2]
                    belief_str = "  ".join(
                        _color_short_tag(t, v) for t, v in top_beliefs
                    ) or "[#5a7090]none[/]"
                    vn = f"  \\[vis:{pop.visibility:.2f}]" if not pop.pinned else ""
                    a(f"{pm}       ↳ {class_label}{_e(sp_note)}  sz:{pop.size_magnitude}  "
                      f"{belief_str}{vn}{pe}")
        if not any_w:
            a("[#5a7090](no worlds in Window)[/]")
        a("")
        a("[bold #4a80b0]━━ NOTABLE MORTALS ━━[/]")
        a("")
        any_m = False
        for mid, mortal in state.mortals.items():
            if mortal.status == MortalStatus.DECEASED:
                continue
            m_oow = not mortal.pinned and mortal.visibility <= ENTITY_VISIBILITY_FLOOR
            if m_oow and not dev:
                continue
            any_m = True
            mm = "[dim]" if m_oow else ""
            me = "[/]" if m_oow else ""
            role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
            age_str = f"age:{mortal.chrono_age:.0f}"
            if mortal.bio_age != mortal.chrono_age:
                age_str += f"(bio:{mortal.bio_age:.0f})"
            sp_obj = state.species.get(str(mortal.species_id)) if mortal.species_id else None
            sp_str = f"  \\[{_e(sp_obj.name)}]" if sp_obj else ""
            vis_note = f"  vis:{mortal.visibility:.2f}" if not mortal.pinned else ""
            mortal_link = _click_link("mortal", str(mid), f"[bold]{_e(mortal.name)}[/]")
            a(f"{mm}● {mortal_link} \\[{role_str}]  "
              f"align:{mortal.alignment:.2f}  {age_str}{vis_note}{sp_str}{me}")
            a(f"{mm}    {_e(_prominence_label(mortal))}{me}")
        if not any_m:
            a("[#5a7090](no notable mortals in Window)[/]")
        return Text.from_markup("\n".join(lines))


class LuminariesTab(ContentTab):
    """Right-panel tab: full Luminary detail (domains, constraints, disposition)."""

    def _render_body(self, state: "SimulationState") -> Text:
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ LUMINARIES ━━[/]")
        a("")
        liege_ids = {str(i) for i in state.demiurge.liege_luminary_ids}
        for lid, lum in state.luminaries.items():
            att = state.luminary_attention.get(lid, 0.0)
            d = lum.disposition
            is_liege = lid in liege_ids
            tag = " [#c09030]\\[LIEGE][/]" if is_liege else ""
            lum_link = _click_link("luminary", str(lid), f"[bold]{_e(lum.name)}[/]")
            a(f"● {lum_link}{tag} "
              f"[#3a5a7a]({_e(_personality_label(lum))})[/]")
            domain_parts = [
                _color_short_tag(tag2, aff)
                for tag2, aff in sorted(lum.domains.items(), key=lambda x: -x[1])
            ]
            a(f"    domains: {', '.join(domain_parts)}")
            rc = "#50b870" if d.results >= 0 else "#b04050"
            mc = "#50b870" if d.methods >= 0 else "#b04050"
            ac = "#c09030" if att > 0.5 else "#2a4a6a"
            a(f"    disposition: "
              f"R[{rc}]{d.results:+.2f}[/]  "
              f"M[{mc}]{d.methods:+.2f}[/]  "
              f"att[{ac}]{att:.2f}[/]")
            if lum.constraints:
                a(f"    [#5a7090]constraints imposed:[/]")
                for c in lum.constraints:
                    a(f"      • {_e(c.name)}  [#5a7090]\\[enf {c.enforcement_weight:.2f}][/]")
                    a(f"        [#7090b0]{_e(c.description)}[/]")
            a("")

        pan = state.pantheon
        a(f"[bold #4a80b0]━━ {_e(pan.name.upper())} — COLLECTIVE CONSTRAINTS ━━[/]")
        a("")
        if pan.collective_constraints:
            for c in pan.collective_constraints:
                a(f"  • {_e(c.name)}  [#5a7090]\\[enf {c.enforcement_weight:.2f}][/]")
                a(f"    [#7090b0]{_e(c.description)}[/]")
        else:
            a("  [#5a7090](none)[/]")

        return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# Log tab: chip filter row + filtered RichLog
# ─────────────────────────────────────────

class LogChip(Static):
    """One filter chip in the Log tab. Click (or Enter) toggles its category."""

    can_focus = True

    class Toggled(Message):
        def __init__(self, category: str, active: bool) -> None:
            super().__init__()
            self.category = category
            self.active = active

    def __init__(self, category: str, active: bool = True) -> None:
        super().__init__(
            category.title(),
            classes="log-chip" + (" active" if active else ""),
        )
        self._category = category
        self._active = active

    def _toggle(self) -> None:
        self._active = not self._active
        if self._active:
            self.add_class("active")
        else:
            self.remove_class("active")
        self.post_message(self.Toggled(self._category, self._active))

    def on_click(self) -> None:
        self._toggle()

    def key_enter(self) -> None:
        self._toggle()


class LogTab(Vertical):
    """Composite tab body: chip row on top, filtered RichLog beneath.

    Tick-result lines (and ad-hoc status messages) come in via `append(category, markup)`.
    The full history is retained; chip toggles re-render the visible portion.
    """

    CATEGORIES = ("actions", "proxius", "luminary", "system", "other")

    def __init__(self) -> None:
        super().__init__()
        self._active: set[str] = set(self.CATEGORIES)
        self._entries: list[tuple[str, str]] = []

    def compose(self) -> ComposeResult:
        with Horizontal(id="log-chips"):
            for cat in self.CATEGORIES:
                yield LogChip(cat, active=True)
        yield RichLog(id="main-feed", markup=True, highlight=False, wrap=True)

    def append(self, category: str, markup: str) -> None:
        """Record an entry and write it to the log if its category is active."""
        if category not in self.CATEGORIES:
            category = "other"
        self._entries.append((category, markup))
        if category in self._active:
            self.query_one("#main-feed", RichLog).write(Text.from_markup(markup))

    def clear(self) -> None:
        self._entries.clear()
        self.query_one("#main-feed", RichLog).clear()

    def _rerender(self) -> None:
        log = self.query_one("#main-feed", RichLog)
        log.clear()
        for cat, mk in self._entries:
            if cat in self._active:
                log.write(Text.from_markup(mk))

    def on_log_chip_toggled(self, event: LogChip.Toggled) -> None:
        if event.active:
            self._active.add(event.category)
        else:
            self._active.discard(event.category)
        self._rerender()
