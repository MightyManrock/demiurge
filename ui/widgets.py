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

from core.universe_core import MortalRole, MortalStatus, PopLocation, is_wild_civ
from logic.tick_logic import is_in_window, ENTITY_VISIBILITY_FLOOR

from ui import display
from ui.display import (
    _personality_label, _format_beliefs, _format_culture, _prominence_label,
    _name_for_id, _short_tag, _trait_color, _pop_stratum_label,
    _format_beliefs_markup, _format_culture_markup, _color_short_tag,
    display_briefing, _lines_to_text,
)
from utilities.imago_registry import get_registry as get_imago_registry

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState
    from utilities.imago_registry import ImagoNode


# Gold highlight for newly-discovered entities. The GameScreen swaps in a
# concrete callable each refresh; default returns False.
_is_unseen: "callable[[str, str], bool]" = lambda kind, eid: False

# When True, `_click_link` emits a navigate-in-place action instead of
# opening a new detail tab. Toggled on by DetailTab._render_body while a
# detail renderer is running; cleared on the way out.
_in_detail_render: bool = False


def set_detail_render(active: bool) -> None:
    """Set whether `_click_link` should emit nav-in-place click actions."""
    global _in_detail_render
    _in_detail_render = bool(active)


def set_unseen_predicate(fn) -> None:
    """Install the predicate used by `_click_link` to gold-highlight new IDs."""
    global _is_unseen
    _is_unseen = fn


def _maybe_gold(kind: str, eid: str, label_markup: str) -> str:
    """Wrap label in gold if this entity ID is currently flagged as unseen."""
    if _is_unseen(kind, eid):
        return f"[#e8c060]{label_markup}[/]"
    return label_markup


# Per-kind colors for clickable entity-name links. Picked to sit outside the
# trait-value gradient (greens/teals/blues/purples ↔ ambers/oranges/reds) so a
# link color cannot be mistaken for a strength signal.
_LINK_COLORS: dict[str, str] = {
    "galaxy":   "#60a070",  # muted green
    "system":   "#9aa870",  # halfway between galaxy and world
    "world":    "#d4b070",  # sandy gold
    "civ":      "#c89050",  # warm bronze
    "mortal":   "#d890a8",  # rose
    "species":  "#b090d0",  # lavender
    "pop":      "#80b8c8",  # pale cyan
    "poploc":   "#3070c0",  # cobalt blue — reserved; not clickable yet
    # luminary: deferred — separate scheme planned
}


def _click_link(kind: str, eid: str, label_markup: str) -> str:
    """
    Wrap `label_markup` in a Textual click-action span that opens a detail tab
    for the given entity.

    Uses the `screen.` namespace so the dispatch goes straight to
    `GameScreen.action_open_detail_by_id` regardless of which widget owns the
    markup. UUIDs and fixed-kind strings are safe to inline (only hex+dashes,
    no quotes).

    Also paints the label in the per-kind link color, unless `_maybe_gold`
    overrides it (unseen-entity highlight).
    """
    if _is_unseen(kind, eid):
        inner = _maybe_gold(kind, eid, label_markup)
    else:
        color = _LINK_COLORS.get(kind)
        inner = f"[{color}]{label_markup}[/]" if color else label_markup
    # Luminaries always route to the Luminaries tab in detail mode.
    # Otherwise: nav-in-place if rendered inside a detail tab; else open new.
    if kind == "luminary":
        action = f"screen.open_luminary('{eid}')"
    elif _in_detail_render:
        action = f"screen.navigate_detail_by_id('{kind}','{eid}')"
    else:
        action = f"screen.open_detail_by_id('{kind}','{eid}')"
    return f"[@click={action}]{inner}[/]"


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

def _committed_essence(state: "SimulationState", loop) -> float:
    """Sum of Essence costs from queued + ongoing actions."""
    if loop is None:
        return 0.0
    library = loop._action_library
    key_by_id = loop._action_key_by_id
    total = 0.0
    for ai in state.action_queue:
        key = key_by_id.get(str(ai.action_definition_id))
        defn = library.get(key) if key else None
        if defn and defn.essence_cost > 0:
            total += defn.essence_cost
    for oa in state.ongoing_actions.values():
        defn = library.get(oa.action_key)
        if defn and defn.essence_cost > 0:
            total += defn.essence_cost
    return total


def _render_status(state: "SimulationState", loop=None) -> Text:
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
    committed = _committed_essence(state, loop)
    a("[bold #4a80b0]ESSENCE[/]")
    a(f"  actual [bold]{es.actual:.2f}[/]  apparent [bold]{es.apparent:.2f}[/]")
    if committed > 0.0:
        free = max(0.0, es.actual - committed)
        a(f"  committed [#c09030]{committed:.2f}[/]  free [bold]{free:.2f}[/]")
    a(f"  concealment [{ci_col}]{ci:.2f}[/]")
    a("")

    # Affiliated domains
    aff = state.demiurge.affiliated_domains
    if aff:
        a("[bold #4a80b0]AFFINITIES[/]")
        show_essence = state.tick_number > 0
        last_tick = state.last_tick_essence_by_domain if show_essence else {}
        for t in aff:
            label = _short_tag(t)
            name = f"[@click=screen.open_divine_wisdom('{t}')][#a0c0e0]{_e(label)}[/][/]"
            if show_essence:
                v = last_tick.get(t, 0.0)
                essence = f"[#c09030]+{v:.2f}[/]" if v > 0.0 else "[dim]—[/]"
                pad = " " * max(1, 14 - len(label))
                a(f"  {name}{pad}{essence}")
            else:
                a(f"  {name}")
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

    # At-a-glance reminder; full list lives on the Actions tab.
    q_count = len(state.action_queue)
    o_count = len(state.ongoing_actions)
    if q_count or o_count:
        a(f"[#5a7090]queue:[/] [#c09030]{q_count}[/]"
          f"  [#5a7090]ongoing:[/] [#60a070]{o_count}[/]")

    return Text.from_markup("\n".join(lines))


class StatusPanel(Static):
    """Like TabBodyStatic, suppresses base link styling so clickable Domain
    tags in the Affinities row aren't underlined or recolored."""

    @property
    def link_style(self):  # type: ignore[override]
        return None

    def refresh_state(self, state: "SimulationState", loop=None) -> None:
        self.update(_render_status(state, loop))


# ─────────────────────────────────────────
# Tab body widgets (Phase 1 of UI overhaul)
# ─────────────────────────────────────────

class TabBodyStatic(Static):
    """Static whose base link styling is suppressed so inner markup colors
    (e.g. the discovery-gold highlight) survive. Textual's default base
    `link_style` would otherwise composite `link-color`/`link-style` on top of
    every `@click=` span, overriding our inner color and forcing an underline.

    `auto_links` stays True so that hover styling (`link-background-hover`
    etc.) is still applied — that path uses `link_style_hover` separately and
    isn't affected by suppressing the base `link_style`."""

    @property
    def link_style(self):  # type: ignore[override]
        return None


class ContentTab(VerticalScroll):
    """Base class for scrollable tab bodies; subclasses implement _render()."""

    def compose(self) -> ComposeResult:
        # `expand=True` makes the Static fill the container's width so Rich's
        # word-wrap calculation matches the visible area instead of the
        # renderable's natural width. Without this, long colored markup lines
        # overshoot the right edge before wrapping.
        yield TabBodyStatic(classes="tab-body", expand=True)

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
            galaxy_md = _click_link("galaxy", str(gid), f"[bold]{_e(galaxy.name)}[/]")
            a(f"{g_style}◇ {galaxy_md}{g_end}")
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
            if is_wild_civ(civ):
                continue  # hidden from player UI
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
            elif dev and m.active_goal.last_action is not None:
                # Dev mode: surface the concrete internal action choice.
                goal = m.active_goal.last_action.value.replace("_", " ")
            elif m.active_goal.label:
                goal = m.active_goal.label
            elif m.active_goal.imago_node_id:
                goal = "preaching"
            elif m.active_goal.research_domain:
                goal = "researching"
            else:
                goal = "on assignment"
            m_link = _click_link("mortal", str(mid), f"[bold]{_e(m.name)}[/]")
            a(f"● {m_link}{tag}")
            a(f"    {_e(loc)}  [#5a7090]{_e(goal)}[/]  "
              f"align:[#a0d080]{m.alignment:.2f}[/]")
        if not any_pr:
            a("[#5a7090](no Proxiī appointed)[/]")
        return Text.from_markup("\n".join(lines))


class ActionsTab(ContentTab):
    """Left-panel tab: queued (this tick) + ongoing actions."""

    _loop = None

    def refresh_state(self, state: "SimulationState", loop=None) -> None:
        self._loop = loop
        self.query_one(Static).update(self._render_body(state))

    def _render_body(self, state: "SimulationState") -> Text:
        loop = self._loop
        library = loop._action_library if loop else {}
        key_by_id = loop._action_key_by_id if loop else {}
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ QUEUED THIS TICK ━━[/]")
        a("")
        if state.action_queue:
            for ai in state.action_queue:
                tgt = ""
                if ai.target_id:
                    tgt = f"  → [#3a6a8a]{_e(_name_for_id(ai.target_id, state))}[/]"
                key = key_by_id.get(str(ai.action_definition_id))
                defn = library.get(key) if key else None
                if defn:
                    label = defn.short_name or defn.name
                else:
                    label = key.replace("_", " ").title() if key else "Action"
                a(f"  • [#a0d080]{_e(label)}[/]{tgt}")
        else:
            a("[#5a7090]  (none queued)[/]")
        a("")
        a("[bold #4a80b0]━━ ONGOING ━━[/]")
        a("")
        if state.ongoing_actions:
            for cat_val, oa in state.ongoing_actions.items():
                cat = cat_val.replace("_", " ").title()
                defn = library.get(oa.action_key)
                if defn:
                    label = defn.short_name or defn.name
                else:
                    label = oa.action_key.replace("_", " ").title()
                tgt = ""
                if oa.target_id:
                    tgt = f"  → [#3a6a8a]{_e(_name_for_id(oa.target_id, state))}[/]"
                a(f"  [#5a7090]({_e(cat)})[/]")
                a(f"    [#60a070]{_e(label)}[/]{tgt}  "
                  f"[#2a4060]{oa.executed_ticks}/{oa.ticks_active} ticks[/]")
        else:
            a("[#5a7090]  (none)[/]")
        return Text.from_markup("\n".join(lines))


class BriefingTab(ContentTab):
    """Right-panel tab: scenario briefing."""

    def _render_body(self, state: "SimulationState") -> Text:
        return _lines_to_text(display_briefing(state, dev_mode=display.DEV_MODE))


def _render_mortal_universe_block(state: "SimulationState", mortal, oow: bool) -> list[str]:
    """Universe-tab-style multi-line block for one notable mortal.

    Returns a list of Rich-markup lines (no surrounding blank lines). When
    `oow` is True, every line is wrapped in `[dim]…[/dim]`. Shared between
    UniverseTab and per-Pop detail renderers so the two stay in lockstep.
    """
    mm = "[dim]" if oow else ""
    me = "[/]" if oow else ""
    lines: list[str] = []
    a = lines.append

    role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
    age_str = f"age:{mortal.chrono_age:.0f}"
    if mortal.bio_age != mortal.chrono_age:
        age_str += f"(bio:{mortal.bio_age:.0f})"
    sp_obj = state.species.get(str(mortal.species_id)) if mortal.species_id else None
    if sp_obj:
        sp_md = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
        sp_str = f"  \\[{sp_md}]"
    else:
        sp_str = ""
    vis_note = f"  vis:{mortal.visibility:.2f}" if not mortal.pinned else ""
    mortal_link = _click_link("mortal", str(mortal.id), f"[bold]{_e(mortal.name)}[/]")
    a(f"{mm}● {mortal_link} \\[{role_str}]  "
      f"align:{mortal.alignment:.2f}  {age_str}{vis_note}{sp_str}{me}")
    a(f"{mm}    {_e(_prominence_label(mortal))}{me}")

    loc_obj = state.locations.get(str(mortal.current_location)) if mortal.current_location else None
    civ_obj = state.civilizations.get(str(mortal.civilization_id)) if mortal.civilization_id else None
    loc_str = ""
    if loc_obj:
        cl_id = str(mortal.current_location)
        if cl_id in state.worlds:
            loc_kind = "world"
        elif cl_id in state.systems:
            loc_kind = "system"
        elif isinstance(loc_obj, PopLocation):
            loc_kind = "poploc"
        else:
            loc_kind = None
        if loc_kind:
            loc_link = _click_link(loc_kind, cl_id, _e(loc_obj.name))
        else:
            loc_link = _e(loc_obj.name)
        loc_str = f"location: {loc_link}"
    civ_str = ""
    if civ_obj:
        civ_link = _click_link("civ", str(civ_obj.id), _e(civ_obj.name))
        civ_str = f"  civ: {civ_link}"
    if loc_str or civ_str:
        a(f"{mm}    {loc_str}{civ_str}{me}")

    if mortal.status_tags:
        stags = sorted(mortal.status_tags)
        shown = stags[:4]
        extra = len(stags) - len(shown)
        suffix = f"  [#5a7090](+{extra} more)[/]" if extra > 0 else ""
        a(f"{mm}    status: {_e(', '.join(_short_tag(t) for t in shown))}{suffix}{me}")
    if mortal.personal_tags:
        ptags = sorted(mortal.personal_tags)
        shown = ptags[:4]
        extra = len(ptags) - len(shown)
        suffix = f"  [#5a7090](+{extra} more)[/]" if extra > 0 else ""
        a(f"{mm}    tags:   {_e(', '.join(_short_tag(t) for t in shown))}{suffix}{me}")
    if mortal.belief_tags:
        a(f"{mm}    beliefs: {_format_beliefs_markup(mortal.belief_tags, top_n=4)}{me}")

    if mortal.role == MortalRole.PROXIUS and mortal.active_goal:
        g = mortal.active_goal
        if g.label:
            dlabel = g.label
        elif g.imago_node_id:
            dlabel = f"preaching [{g.imago_node_id.split(':')[-1]}]"
        elif g.research_domain:
            dlabel = f"researching {_short_tag(g.research_domain)}"
        else:
            dlabel = "on assignment"
        a(f"{mm}    [#c09030]directive:[/] {_e(dlabel)}{me}")
    return lines


class UniverseTab(ContentTab):
    """Right-panel tab: in-Window worlds (with civs/pops) + notable mortals."""

    def _render_body(self, state: "SimulationState") -> Text:
        dev = display.DEV_MODE
        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ WORLDS ━━[/]")
        a("")
        any_w = False

        # Walk galaxies → systems → worlds. Galaxies sit flush at column 0,
        # systems indent +1, worlds indent +2 (so the existing world block —
        # marker, domain line, civ tree — is prefixed with two extra spaces).
        # OOW galaxies/systems are hidden in non-dev mode.
        def _dim(text: str, oow: bool) -> str:
            return f"[dim]{text}[/]" if oow else text

        # Pre-emit base indent prefix used by every line inside a world block.
        IDX = "  "  # two spaces — the "world depth" offset

        for gid, galaxy in state.galaxies.items():
            g_oow = not is_in_window(galaxy)
            if g_oow and not dev:
                continue
            gal_link = _click_link("galaxy", str(gid), _e(galaxy.name))
            a(_dim(gal_link, g_oow))

            for sid in galaxy.child_ids:
                sys_obj = state.systems.get(str(sid))
                if not sys_obj:
                    continue
                s_oow = not is_in_window(sys_obj)
                if s_oow and not dev:
                    continue
                sys_link = _click_link("system", str(sid), _e(sys_obj.name))
                a(_dim(f" {sys_link}", g_oow or s_oow))

                for cid in sys_obj.child_ids:
                    wid = str(cid)
                    world = state.worlds.get(wid)
                    if not world:
                        continue
                    w_oow = not is_in_window(world)
                    if w_oow and not dev:
                        continue
                    any_w = True
                    any_oow_above = g_oow or s_oow or w_oow
                    wm = "[dim]" if any_oow_above else ""
                    we = "[/]" if any_oow_above else ""
                    vis_note = f"  \\[vis:{world.visibility:.2f}]" if not world.pinned else ""
                    domain_str = _format_beliefs_markup(world.domain_expression, top_n=4) or "[#5a7090]none[/]"
                    world_link = _click_link("world", wid, f"[bold]{_e(world.name)}[/]")
                    a(f"{wm}{IDX}● {world_link}  "
                      f"\\[{_e(world.condition.value)}]{vis_note}{we}")
                    a(f"{wm}{IDX}    domain: {domain_str}{we}")

                    # Collect every visible pop on this world, bucketed by
                    # civilization → PopLocation → [pops]. None-keyed bucket
                    # holds wild (no civ or wild-civ) pops.
                    pops_by_civ_loc: dict = {}
                    for _p in state.pops.values():
                        _ploc = state.locations.get(str(_p.current_location)) if _p.current_location else None
                        if not isinstance(_ploc, PopLocation):
                            continue
                        if str(_ploc.parent_id) != wid:
                            continue
                        if not is_in_window(_p) and not dev:
                            continue
                        civ_obj = state.civilizations.get(str(_p.civilization_id)) if _p.civilization_id else None
                        civ_key = str(_p.civilization_id) if (civ_obj and not is_wild_civ(civ_obj)) else None
                        pops_by_civ_loc.setdefault(civ_key, {}).setdefault(str(_ploc.id), []).append(_p)

                    def _render_pop_line(pop, indent: str, civ_oow_local: bool, prefix: str) -> None:
                        p_oow = not is_in_window(pop)
                        if p_oow and not dev:
                            return
                        pm = "[dim]" if (w_oow or civ_oow_local or p_oow) else ""
                        pe = "[/]" if (w_oow or civ_oow_local or p_oow) else ""
                        class_label = _pop_stratum_label(pop)
                        sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                        pop_stratum_md = _click_link("pop", str(pop.id), class_label)
                        if sp_obj:
                            sp_md = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
                            pop_label = f"{pop_stratum_md}  ({sp_md})"
                        else:
                            pop_label = pop_stratum_md
                        belief_str = (
                            _format_beliefs_markup(pop.dominant_beliefs, top_n=4)
                            or "[#5a7090]none[/]"
                        )
                        vn = f"  \\[vis:{pop.visibility:.2f}]" if not pop.pinned else ""
                        a(f"{pm}{indent}{prefix}{pop_label}  sz:{pop.size_magnitude}  "
                          f"{belief_str}{vn}{pe}")

                    def _ploc_sort_key(plid: str):
                        pl = state.locations[plid]
                        return (pl.distance_from_core, pl.name)

                    attached_wild_pop_ids: set[str] = set()

                    for cid_iter in world.civilization_ids:
                        civ = state.civilizations.get(str(cid_iter))
                        if not civ:
                            continue
                        if is_wild_civ(civ):
                            continue
                        c_oow = not is_in_window(civ)
                        if c_oow and not dev:
                            continue
                        cm = "[dim]" if (w_oow or c_oow) else ""
                        ce = "[/]" if (w_oow or c_oow) else ""
                        h = civ.health
                        civ_vis = f"  \\[vis:{civ.visibility:.2f}]" if not civ.pinned else ""
                        civ_link = _click_link("civ", str(cid_iter), f"[bold]{_e(civ.name)}[/]")
                        a(f"{cm}{IDX}    └─ {civ_link} "
                          f"\\[{_e(civ.scale.value)}]{civ_vis}  "
                          f"S{h.stability:.2f} P{h.prosperity:.2f} C{h.cohesion:.2f}{ce}")
                        if civ.dominant_beliefs:
                            a(f"{cm}{IDX}       beliefs: {_format_beliefs_markup(civ.dominant_beliefs, top_n=4)}{ce}")
                        if civ.culture_tags:
                            a(f"{cm}{IDX}       culture: {_format_culture_markup(civ.culture_tags, top_n=4)}{ce}")

                        civ_pops_by_loc = pops_by_civ_loc.get(str(cid_iter), {})
                        wild_by_loc = pops_by_civ_loc.get(None, {})
                        multi_loc = len(civ_pops_by_loc) > 1

                        for ploc_id in sorted(civ_pops_by_loc.keys(), key=_ploc_sort_key):
                            if multi_loc:
                                ploc = state.locations[ploc_id]
                                dist_note = (
                                    f"  [#5a7090](d{ploc.distance_from_core})[/]"
                                    if ploc.distance_from_core > 0 else ""
                                )
                                a(f"{cm}{IDX}       ↳ \\[{_click_link('poploc', str(ploc.id), _e(ploc.name))}]{dist_note}{ce}")
                                pop_indent = f"{IDX}           "
                            else:
                                pop_indent = f"{IDX}       "
                            for pop in civ_pops_by_loc[ploc_id]:
                                _render_pop_line(pop, pop_indent, c_oow, prefix="↳ ")
                            for wpop in wild_by_loc.get(ploc_id, []):
                                if str(wpop.id) in attached_wild_pop_ids:
                                    continue
                                attached_wild_pop_ids.add(str(wpop.id))
                                _render_pop_line(wpop, pop_indent, c_oow, prefix="")

                    # PopLocations containing only wild pops — listed last.
                    wild_by_loc = pops_by_civ_loc.get(None, {})
                    standalone_wild = sorted(
                        [(plid, plops) for plid, plops in wild_by_loc.items()
                         if any(str(p.id) not in attached_wild_pop_ids for p in plops)],
                        key=lambda kv: _ploc_sort_key(kv[0]),
                    )
                    for ploc_id, wild_pops in standalone_wild:
                        ploc = state.locations[ploc_id]
                        dist_note = (
                            f"  [#5a7090](d{ploc.distance_from_core})[/]"
                            if ploc.distance_from_core > 0 else ""
                        )
                        a(f"{wm}{IDX}    \\[{_click_link('poploc', str(ploc.id), _e(ploc.name))}]{dist_note}{we}")
                        for wpop in wild_pops:
                            if str(wpop.id) in attached_wild_pop_ids:
                                continue
                            _render_pop_line(wpop, f"{IDX}        ", False, prefix="")
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
            lines.extend(_render_mortal_universe_block(state, mortal, m_oow))
        if not any_m:
            a("[#5a7090](no notable mortals in Window)[/]")
        return Text.from_markup("\n".join(lines))


class LuminariesTab(ContentTab):
    """Right-panel tab: list of Luminaries + per-Luminary detail view.

    Click a Luminary name (anywhere in the UI) to switch to detail mode in
    this tab; click the breadcrumb "Luminaries" to return to the list.
    Reverts to the list when the simulation tick advances.
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: "SimulationState | None" = None
        self._mode: str = "list"
        self._lum_id: str | None = None
        self._last_tick: int = -1

    # Public navigation methods invoked from GameScreen click handlers.

    def show_list(self) -> None:
        self._mode = "list"
        self._lum_id = None
        self._refresh_self()

    def show_luminary(self, lum_id: str) -> None:
        self._mode = "detail"
        self._lum_id = str(lum_id)
        self._refresh_self()

    def _refresh_self(self) -> None:
        if self._state is not None:
            self.query_one(Static).update(self._render_body(self._state))

    def refresh_state(self, state: "SimulationState") -> None:
        self._state = state
        super().refresh_state(state)

    def _render_body(self, state: "SimulationState") -> Text:
        # Tick advance → revert to list view.
        if state.tick_number != self._last_tick:
            self._last_tick = state.tick_number
            self._mode = "list"
            self._lum_id = None
        if self._mode == "detail" and self._lum_id:
            return self._render_detail(state, self._lum_id)
        return self._render_list(state)

    def _render_detail(self, state: "SimulationState", lum_id: str) -> Text:
        from ui.detail_renderers import render_luminary_detail
        lum = state.luminaries.get(lum_id)
        name = lum.name if lum else "?"
        crumb_home = "[@click=screen.open_luminaries_list][#5a7090]Luminaries[/][/]"
        header = (
            f"{crumb_home}  [#3a4a60]›[/]  [bold #c0ccdc]{_e(name)}[/]\n\n"
        )
        # Navigate-in-place semantics inside the Luminaries detail view too:
        # luminary→luminary clicks switch this tab; other-kind clicks fall
        # through to opening new detail tabs (no detail pane is active).
        set_detail_render(True)
        try:
            body = render_luminary_detail(state, lum_id)
        finally:
            set_detail_render(False)
        return Text.from_markup(header) + body

    def _render_list(self, state: "SimulationState") -> Text:
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
# Divine Wisdom tab — Domain list / Imago tree / Imago node detail
# ─────────────────────────────────────────

class DivineWisdomTab(ContentTab):
    """Right-panel tab. Three navigable views, switched by clicking entries:

        list  — all 16 Domains, with revelation/cap per Domain.
        tree  — one Domain's Imago tree, with cost or ✓ Revealed marker per node.
        node  — full description + mechanics for one Imago node.

    The tab reverts to `list` automatically when the simulation tick advances.
    """

    def __init__(self) -> None:
        super().__init__()
        self._state: "SimulationState | None" = None
        self._mode: str = "list"
        self._domain_tag: str | None = None
        self._node_id: str | None = None
        self._last_tick: int = -1

    # Public navigation methods invoked from GameScreen click handlers.

    def show_list(self) -> None:
        self._mode = "list"
        self._refresh_self()

    def show_domain(self, domain_tag: str) -> None:
        self._mode = "tree"
        self._domain_tag = domain_tag
        self._refresh_self()

    def show_node(self, node_id: str) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(node_id)
        if node is None:
            return
        self._mode = "node"
        self._domain_tag = f"domain:{node.tree}"
        self._node_id = node_id
        self._refresh_self()

    def _refresh_self(self) -> None:
        if self._state is not None:
            self.query_one(Static).update(self._render_body(self._state))

    def refresh_state(self, state: "SimulationState") -> None:
        self._state = state
        super().refresh_state(state)

    def _render_body(self, state: "SimulationState") -> Text:
        # Tick advance → revert to list view.
        if state.tick_number != self._last_tick:
            self._last_tick = state.tick_number
            self._mode = "list"
            self._domain_tag = None
            self._node_id = None
        if self._mode == "tree" and self._domain_tag:
            return self._render_tree(state, self._domain_tag)
        if self._mode == "node" and self._node_id:
            return self._render_node(state, self._node_id)
        return self._render_list(state)

    # ── List view ─────────────────────────────────────────────────

    def _render_list(self, state: "SimulationState") -> Text:
        from logic.tick_logic import _compute_revelation_cap
        from utilities.domain_registry import get_registry as get_domain_registry
        dreg = get_domain_registry()
        ireg = get_imago_registry()
        unlocked = set(state.demiurge.unlocked_imagines)

        lines: list[str] = []
        a = lines.append
        a("[bold #4a80b0]━━ DIVINE WISDOM ━━[/]")
        a("[#5a7090]Conceptual frameworks (Imagines) revealed and yet to be revealed,[/]")
        a("[#5a7090]organized by Domain. Click a Domain to explore its tree.[/]")
        a("")
        a(f"[#5a7090]revealed Imagines:[/] [bold]{len(unlocked)}[/]   "
          f"[#5a7090]affiliated domains:[/] "
          + ", ".join(_short_tag(t) for t in state.demiurge.affiliated_domains))
        a("")

        for tag in dreg.all_tags:
            tree = tag.split(":", 1)[1]
            tree_nodes = ireg.nodes_for_tree(tree)
            n_revealed = sum(1 for n in tree_nodes if n.node_id in unlocked)
            n_total = len(tree_nodes)
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            cap = _compute_revelation_cap(state, tag)
            if cap > 0.0:
                pool_str = f"[#a0c0e0]{pool:.1f}[/] / [#5a7090]{cap:.0f}[/]"
            else:
                pool_str = "[#5a7090](fully revealed)[/]"
            label = _short_tag(tag)
            label_md = f"[@click=screen.open_divine_wisdom('{tag}')][bold #c0ccdc]{_e(label)}[/][/]"
            counts = f"[#5a7090]{n_revealed}/{n_total} revealed[/]"
            a(f"  ● {label_md}  {counts}  {pool_str}")
        return Text.from_markup("\n".join(lines))

    # ── Tree view ─────────────────────────────────────────────────

    def _render_tree(self, state: "SimulationState", domain_tag: str) -> Text:
        from logic.tick_logic import _compute_revelation_cap, _revelation_adjusted_cost
        ireg = get_imago_registry()
        tree = domain_tag.split(":", 1)[1]
        nodes = ireg.nodes_for_tree(tree)
        unlocked = set(state.demiurge.unlocked_imagines)
        rev_count = state.demiurge.revealed_imagines
        pool = state.demiurge.revelation_pools.get(domain_tag, 0.0)
        cap = _compute_revelation_cap(state, domain_tag)

        lines: list[str] = []
        a = lines.append
        crumb_home = "[@click=screen.open_divine_wisdom('')][#5a7090]Divine Wisdom[/][/]"
        a(f"{crumb_home}  [#3a4a60]›[/]  [bold #c0ccdc]{_e(_short_tag(domain_tag))}[/]")
        a("")
        a(f"[bold #4a80b0]━━ {_e(_short_tag(domain_tag).upper())} — IMAGO TREE ━━[/]")
        a("")
        if cap > 0.0:
            a(f"  revelation: [#a0c0e0]{pool:.1f}[/] / [#5a7090]{cap:.0f}[/]  "
              f"[#5a7090]({len(unlocked & {n.node_id for n in nodes})}/{len(nodes)} revealed)[/]")
        else:
            a(f"  [#5a7090](every Imago in this tree is already revealed)[/]")
        a("")

        # Group by tier: T1, T2, T3, T4.
        for tier in (1, 2, 3, 4):
            tier_nodes = [n for n in nodes if n.tier == tier]
            if not tier_nodes:
                continue
            a(f"[#5a7090]── Tier {tier} ──[/]")
            for node in tier_nodes:
                is_unlocked = node.node_id in unlocked
                prereqs_met = ireg.is_unlockable(node.node_id, unlocked)
                cost = _revelation_adjusted_cost(node.tier, rev_count)
                if is_unlocked:
                    status = "[#50b870]✓ revealed[/]"
                elif not prereqs_met:
                    status = "[#5a7090](prereqs unmet)[/]"
                elif pool >= cost:
                    status = f"[#e8c060]{cost} Rev — affordable[/]"
                else:
                    status = f"[#5a7090]{cost} Rev[/]"
                name_md = (
                    f"[@click=screen.open_imago_node('{node.node_id}')]"
                    f"[bold #c0ccdc]{_e(node.name)}[/][/]"
                )
                a(f"  • {name_md}  {status}")
                if node.tooltip_blurb:
                    a(f"      [#7090b0]{_e(node.tooltip_blurb)}[/]")
            a("")
        return Text.from_markup("\n".join(lines))

    # ── Node view ─────────────────────────────────────────────────

    def _render_node(self, state: "SimulationState", node_id: str) -> Text:
        from logic.tick_logic import _revelation_adjusted_cost
        ireg = get_imago_registry()
        node = ireg.get_node(node_id)
        if node is None:
            return Text.from_markup("[#b04050]Imago not found.[/]")
        domain_tag = f"domain:{node.tree}"
        unlocked = set(state.demiurge.unlocked_imagines)
        is_unlocked = node.node_id in unlocked
        prereqs_met = ireg.is_unlockable(node.node_id, unlocked)
        rev_count = state.demiurge.revealed_imagines
        cost = _revelation_adjusted_cost(node.tier, rev_count)
        pool = state.demiurge.revelation_pools.get(domain_tag, 0.0)

        lines: list[str] = []
        a = lines.append
        domain_short = _short_tag(domain_tag)
        crumb_home = "[@click=screen.open_divine_wisdom('')][#5a7090]Divine Wisdom[/][/]"
        crumb_dom = (
            f"[@click=screen.open_divine_wisdom('{domain_tag}')]"
            f"[#5a7090]{_e(domain_short)}[/][/]"
        )
        a(f"{crumb_home}  [#3a4a60]›[/]  {crumb_dom}  [#3a4a60]›[/]  "
          f"[bold #c0ccdc]{_e(node.name)}[/]")
        a("")
        a(f"[bold #4a80b0]IMAGO: {_e(node.name)}[/]")
        a(f"  [#5a7090]Tier {node.tier}[/]  [#3a4a60]·[/]  "
          f"[#5a7090]{_e(domain_short)} tree[/]")
        a("")
        if node.tooltip_blurb:
            a(f"  [#a0b8d0]\"{_e(node.tooltip_blurb)}\"[/]")
            a("")
        if is_unlocked:
            a(f"  [#50b870]✓ Already revealed[/]")
        elif not prereqs_met:
            a(f"  [#5a7090]Prerequisites unmet.[/]")
        elif pool >= cost:
            a(f"  [#e8c060]Affordable:[/] {cost} Rev (pool: {pool:.1f})")
        else:
            a(f"  [#5a7090]Cost:[/] {cost} Rev (pool: {pool:.1f})")
        a("")
        a("[bold #4a80b0]DESCRIPTION[/]")
        a(f"  [#c0ccdc]{_e(node.description)}[/]")
        a("")
        if node.mechanics:
            a("[bold #4a80b0]MECHANICS[/]")
            for tag, mod in sorted(node.mechanics.items(), key=lambda kv: -kv[1]):
                a(f"  {_color_short_tag(tag, mod)}")
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
