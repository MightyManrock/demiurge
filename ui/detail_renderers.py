"""
Per-entity detail-tab renderers. Each function takes (state, entity_id) and
returns a Rich Text. Renderers are pure read-only views — they make no
assumptions about clickability (that's the manager's job in Phase 3).

Naming: render_<kind>_detail. The DetailTabManager dispatches by kind string.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text

from core.universe_core import MortalRole, MortalStatus
from logic.tick_logic import is_in_window, is_mortal_visible, ENTITY_VISIBILITY_FLOOR
import display
from display import (
    _personality_label, _format_beliefs, _format_culture, _prominence_label,
    _short_tag, _trait_color, _format_beliefs_markup, _format_culture_markup,
    _color_short_tag,
)
from ui.widgets import _click_link

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


def _not_found(label: str) -> Text:
    return Text.from_markup(f"[#b04050]{_e(label)} not found in current state.[/]")


def _location_kind(state: "SimulationState", location_id) -> "str | None":
    """Return 'world' / 'system' / None depending on which dict holds the id."""
    lid = str(location_id)
    if lid in state.worlds:   return "world"
    if lid in state.systems:  return "system"
    return None


def _location_link(state: "SimulationState", location_id, label_markup: str) -> str:
    """Wrap label as a click-link if the location has a detail renderer; else return as-is."""
    kind = _location_kind(state, location_id)
    if kind is None:
        return label_markup
    return _click_link(kind, str(location_id), label_markup)


# ─────────────────────────────────────────
# WORLD
# ─────────────────────────────────────────

def render_world_detail(state: "SimulationState", world_id: str) -> Text:
    world = state.worlds.get(str(world_id))
    if not world:
        return _not_found(f"World {world_id}")

    lines: list[str] = []
    a = lines.append

    a(f"[bold #4a80b0]WORLD: {_e(world.name)}[/]")
    a("")
    a(f"  condition: \\[{_e(world.condition.value)}]   age: {world.age:.0f}")
    if world.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {world.visibility:.2f}")

    if world.geo_tags:
        a(f"  geography: {_e(', '.join(world.geo_tags))}")
    if world.atmo_tags:
        a(f"  atmosphere: {_e(', '.join(world.atmo_tags))}")
    if world.domain_expression:
        a(f"  domain expression: {_format_beliefs_markup(world.domain_expression)}")

    sys_obj = state.locations.get(str(world.parent_id)) if world.parent_id else None
    if sys_obj:
        sys_link = _location_link(state, world.parent_id, f"[#3a6a8a]{_e(sys_obj.name)}[/]")
        a(f"  in system: {sys_link}")

    fp = getattr(world, "local_footprint", None)
    if fp is not None:
        a("")
        a("[bold #4a80b0]LOCAL FOOTPRINT[/]")
        a(f"  overt:{fp.overt_miracles:.2f}  subtle:{fp.subtle_influence:.2f}  "
          f"proxii:{fp.proxius_activity:.2f}  create:{fp.direct_creation:.2f}")

    dev = display.DEV_MODE

    a("")
    a("[bold #4a80b0]CIVILIZATIONS[/]")
    any_civ = False
    for cid in world.civilization_ids:
        civ = state.civilizations.get(str(cid))
        if not civ:
            continue
        c_oow = not is_in_window(civ)
        if c_oow and not dev:
            continue
        any_civ = True
        cm = "[dim]" if c_oow else ""
        ce = "[/]" if c_oow else ""
        h = civ.health
        civ_link = _click_link("civ", str(cid), f"[bold]{_e(civ.name)}[/]")
        a(f"  {cm}● {civ_link}  \\[{_e(civ.scale.value)}]  "
          f"S{h.stability:.2f} P{h.prosperity:.2f} C{h.cohesion:.2f}{ce}")
    if not any_civ:
        a("  [#5a7090](none in Window)[/]")

    a("")
    a("[bold #4a80b0]NOTABLE MORTALS HERE[/]")
    any_m = False
    for mid, m in state.mortals.items():
        if str(m.current_location) != str(world_id):
            continue
        if m.status == MortalStatus.DECEASED:
            continue
        m_oow = not is_mortal_visible(m)
        if m_oow and not dev:
            continue
        any_m = True
        mm = "[dim]" if m_oow else ""
        me = "[/]" if m_oow else ""
        role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
        m_link = _click_link("mortal", str(mid), f"[bold]{_e(m.name)}[/]")
        a(f"  {mm}● {m_link} \\[{role_str}]  align:{m.alignment:.2f}{me}")
    if not any_m:
        a("  [#5a7090](none in Window)[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# SYSTEM
# ─────────────────────────────────────────

def render_system_detail(state: "SimulationState", system_id: str) -> Text:
    sys_obj = state.systems.get(str(system_id))
    if not sys_obj:
        return _not_found(f"System {system_id}")

    lines: list[str] = []
    a = lines.append

    star_str = sys_obj.star_type.value if hasattr(sys_obj, "star_type") else "?"
    a(f"[bold #4a80b0]SYSTEM: {_e(sys_obj.name)}[/]")
    a("")
    a(f"  star type: \\[{_e(star_str)}]")
    if sys_obj.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {sys_obj.visibility:.2f}")

    parent = state.locations.get(str(sys_obj.parent_id)) if sys_obj.parent_id else None
    if parent:
        a(f"  in galaxy: [#3a6a8a]{_e(parent.name)}[/]")

    a("")
    a("[bold #4a80b0]WORLDS[/]")
    dev = display.DEV_MODE
    any_w = False
    for cid in sys_obj.child_ids:
        world = state.worlds.get(str(cid))
        if not world:
            continue
        w_oow = not is_in_window(world)
        if w_oow and not dev:
            continue
        any_w = True
        marker = "●" if not w_oow else "○"
        style = "[dim]" if w_oow else ""
        end = "[/]" if w_oow else ""
        n_civs = sum(
            1 for x in world.civilization_ids
            if str(x) in state.civilizations and is_in_window(state.civilizations[str(x)])
        )
        life = f"{n_civs} civ(s) known" if n_civs else "no life known"
        world_link = _click_link("world", str(cid), f"[bold]{_e(world.name)}[/]")
        a(f"  {style}{marker} {world_link}  "
          f"\\[{_e(world.condition.value)}]  {life}{end}")

    if not any_w:
        a("  [#5a7090](no worlds known in this system)[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# CIVILIZATION
# ─────────────────────────────────────────

def render_civ_detail(state: "SimulationState", civ_id: str) -> Text:
    civ = state.civilizations.get(str(civ_id))
    if not civ:
        return _not_found(f"Civilization {civ_id}")

    lines: list[str] = []
    a = lines.append
    h = civ.health

    a(f"[bold #4a80b0]CIVILIZATION: {_e(civ.name)}[/]")
    a("")
    a(f"  scale: \\[{_e(civ.scale.value)}]   divine awareness: {civ.divine_awareness:.2f}")
    if civ.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {civ.visibility:.2f}")

    a("")
    a("[bold #4a80b0]HEALTH[/]")
    a(f"  stability:  {h.stability:+.2f}")
    a(f"  prosperity: {h.prosperity:+.2f}")
    a(f"  cohesion:   {h.cohesion:+.2f}")

    origin = state.locations.get(str(civ.origin_location_id)) if civ.origin_location_id else None
    if origin:
        a("")
        origin_link = _location_link(state, civ.origin_location_id, f"[#3a6a8a]{_e(origin.name)}[/]")
        a(f"  origin: {origin_link}")

    if civ.dominant_beliefs:
        a("")
        a("[bold #4a80b0]DOMINANT BELIEFS[/]")
        for tag, val in sorted(civ.dominant_beliefs.items(), key=lambda kv: -kv[1]):
            a(f"  {_color_short_tag(tag, val, with_value=False)}: {val:.2f}")

    if civ.culture_tags:
        a("")
        a("[bold #4a80b0]CULTURE[/]")
        a(f"  {_format_culture_markup(civ.culture_tags)}")

    dev = display.DEV_MODE

    a("")
    a("[bold #4a80b0]POPS[/]")
    any_p = False
    for pid in civ.pop_ids:
        pop = state.pops.get(str(pid))
        if not pop:
            continue
        p_oow = not is_in_window(pop)
        if p_oow and not dev:
            continue
        any_p = True
        pm = "[dim]" if p_oow else ""
        pe = "[/]" if p_oow else ""
        class_label = pop.stratum.title() if pop.stratum else "Pop"
        sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
        sp_note = f"  ({sp_obj.name})" if sp_obj else ""
        top = sorted(pop.dominant_beliefs.items(), key=lambda kv: -kv[1])[:3]
        belief_str = "  ".join(
            _color_short_tag(t, v) for t, v in top
        ) or "[#5a7090]none[/]"
        vis = f"  \\[vis:{pop.visibility:.2f}]" if not pop.pinned else ""
        a(f"  {pm}↳ {class_label}{_e(sp_note)}  sz:{pop.size_magnitude}{vis}{pe}")
        a(f"      {pm}{belief_str}{pe}")
    if not any_p:
        a("  [#5a7090](no pops visible in Window)[/]")

    a("")
    a("[bold #4a80b0]NOTABLE MORTALS[/]")
    any_m = False
    for mid, m in state.mortals.items():
        if str(m.civilization_id) != str(civ_id):
            continue
        if m.status == MortalStatus.DECEASED:
            continue
        m_oow = not is_mortal_visible(m)
        if m_oow and not dev:
            continue
        any_m = True
        mm = "[dim]" if m_oow else ""
        me = "[/]" if m_oow else ""
        role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
        m_link = _click_link("mortal", str(mid), f"[bold]{_e(m.name)}[/]")
        a(f"  {mm}● {m_link} \\[{role_str}]  align:{m.alignment:.2f}{me}")
    if not any_m:
        a("  [#5a7090](none in Window)[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# MORTAL  (works for both notable mortals and Proxiī)
# ─────────────────────────────────────────

def render_mortal_detail(state: "SimulationState", mortal_id: str) -> Text:
    m = state.mortals.get(str(mortal_id))
    if not m:
        return _not_found(f"Mortal {mortal_id}")

    lines: list[str] = []
    a = lines.append

    role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
    status_str = m.status.value.upper()

    a(f"[bold #4a80b0]MORTAL: {_e(m.name)}[/]")
    a("")
    a(f"  \\[{role_str}]   status: \\[{status_str}]")
    a(f"  alignment: {m.alignment:+.2f}")
    age_str = f"age:{m.chrono_age:.0f}"
    if m.bio_age != m.chrono_age:
        age_str += f"  (bio:{m.bio_age:.0f})"
    a(f"  {age_str}")
    if m.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {m.visibility:.2f}")
    a(f"  {_e(_prominence_label(m))}")

    sp_obj = state.species.get(str(m.species_id)) if m.species_id else None
    if sp_obj:
        a(f"  species: [#3a6a8a]{_e(sp_obj.name)}[/]")

    loc = state.locations.get(str(m.current_location)) if m.current_location else None
    if loc:
        loc_link = _location_link(state, m.current_location, f"[#3a6a8a]{_e(loc.name)}[/]")
        a(f"  location: {loc_link}")

    home = state.locations.get(str(m.home_location)) if m.home_location else None
    if home and (not loc or home.id != loc.id):
        home_link = _location_link(state, m.home_location, f"[#3a6a8a]{_e(home.name)}[/]")
        a(f"  home: {home_link}")

    civ = state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
    if civ:
        civ_link = _click_link("civ", str(m.civilization_id), f"[#3a6a8a]{_e(civ.name)}[/]")
        a(f"  civilization: {civ_link}")

    if m.status_tags or m.personal_tags or m.culture_tags:
        a("")
    if m.status_tags:
        a(f"  status: {_e(', '.join(_short_tag(t) for t in m.status_tags))}")
    if m.personal_tags:
        a(f"  tags:   {_e(', '.join(_short_tag(t) for t in m.personal_tags))}")
    if m.culture_tags:
        a(f"  culture: {_format_culture_markup(m.culture_tags)}")

    if m.role == MortalRole.PROXIUS:
        a("")
        a("[bold #4a80b0]PROXIUS GOAL[/]")
        if m.active_goal:
            g = m.active_goal
            a(f"  current: [#a0d080]{_e(g.choice.value)}[/]")
            if g.goal_pop_id:
                pop = state.pops.get(str(g.goal_pop_id))
                if pop:
                    a(f"  target pop: {_e(pop.stratum.title())}")
            if g.imago_node_id:
                a(f"  imago: {_e(g.imago_node_id)}")
        else:
            a("  [#5a7090](idle — no active directive)[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# LUMINARY
# ─────────────────────────────────────────

def render_luminary_detail(state: "SimulationState", lum_id: str) -> Text:
    lum = state.luminaries.get(str(lum_id))
    if not lum:
        return _not_found(f"Luminary {lum_id}")

    lines: list[str] = []
    a = lines.append
    d = lum.disposition
    att = state.luminary_attention.get(str(lum_id), 0.0)
    liege = str(lum_id) in {str(i) for i in state.demiurge.liege_luminary_ids}

    a(f"[bold #4a80b0]LUMINARY: {_e(lum.name)}[/]")
    a("")
    suffix = "  [#c09030]\\[LIEGE][/]" if liege else ""
    a(f"  personality: [#3a5a7a]({_e(_personality_label(lum))})[/]{suffix}")
    rc = "#50b870" if d.results >= 0 else "#b04050"
    mc = "#50b870" if d.methods >= 0 else "#b04050"
    ac = "#c09030" if att > 0.5 else "#2a4a6a"
    a(f"  disposition: "
      f"R[{rc}]{d.results:+.2f}[/]  "
      f"M[{mc}]{d.methods:+.2f}[/]  "
      f"att[{ac}]{att:.2f}[/]")

    a("")
    a("[bold #4a80b0]DOMAIN AFFINITIES[/]")
    for tag, aff in sorted(lum.domains.items(), key=lambda kv: -kv[1]):
        chip = _color_short_tag(tag, aff, with_value=False)
        # Pad inside the color span so column alignment is preserved.
        a(f"  {chip}{' ' * max(0, 16 - len(_short_tag(tag)))}  {aff:+.2f}")

    if lum.constraints:
        a("")
        a("[bold #4a80b0]CONSTRAINTS IMPOSED[/]")
        for c in lum.constraints:
            a(f"  • {_e(c.name)}  [#5a7090]\\[enf {c.enforcement_weight:.2f}][/]")
            a(f"    [#7090b0]{_e(c.description)}[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# Dispatch table
# ─────────────────────────────────────────

RENDERERS = {
    "world":     render_world_detail,
    "system":    render_system_detail,
    "civ":       render_civ_detail,
    "mortal":    render_mortal_detail,
    "luminary":  render_luminary_detail,
}
