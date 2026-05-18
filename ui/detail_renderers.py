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
from ui.widgets import _click_link, _maybe_gold

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


def _not_found(label: str) -> Text:
    return Text.from_markup(f"[#b04050]{_e(label)} not found in current state.[/]")


_SIZE_MAGNITUDE_WORDS = {
    0: "ones", 1: "tens", 2: "hundreds",
    3: "thousands", 4: "tens of thousands", 5: "hundreds of thousands",
    6: "millions", 7: "tens of millions", 8: "hundreds of millions",
    9: "billions", 10: "tens of billions", 11: "hundreds of billions",
    12: "trillions", 13: "tens of trillions", 14: "hundreds of trillions",
    15: "quadrillions",
}


def _size_magnitude_word(mag: int) -> str:
    if mag in _SIZE_MAGNITUDE_WORDS:
        return _SIZE_MAGNITUDE_WORDS[mag]
    if mag < 0:
        return "fewer than 1"
    return f"~10^{mag}"


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


def _format_location_chain(state: "SimulationState", location_id) -> "str | None":
    """
    Render a Mortal/Pop location reference. If the id resolves to a PopLocation,
    returns 'WorldLink (poploc_name)'; otherwise returns the link for whatever
    Location it is (world/system). Returns None if the id can't be resolved.
    """
    loc = state.locations.get(str(location_id)) if location_id else None
    if loc is None:
        return None
    kind = _location_kind(state, location_id)
    if kind is not None:
        return _location_link(state, location_id, _e(loc.name))
    # PopLocation: render parent world (linked) with PopLocation name in parens.
    parent = state.locations.get(str(loc.parent_id)) if loc.parent_id else None
    if parent is not None:
        parent_link = _location_link(state, parent.id, _e(parent.name))
        return f"{parent_link} ({_e(loc.name)})"
    return _e(loc.name)


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
        a(f"  geography:  {_e(', '.join(_short_tag(t) for t in world.geo_tags))}")
    if world.atmo_tags:
        a(f"  atmosphere: {_e(', '.join(_short_tag(t) for t in world.atmo_tags))}")
    if world.domain_expression:
        a(f"  domain expression: {_format_beliefs_markup(world.domain_expression)}")

    sys_obj = state.locations.get(str(world.parent_id)) if world.parent_id else None
    if sys_obj:
        sys_link = _location_link(state, world.parent_id, f"{_e(sys_obj.name)}")
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
        oow = not is_in_window(origin)
        if not oow or display.DEV_MODE:
            origin_link = _location_link(state, civ.origin_location_id, f"{_e(origin.name)}")
            line = f"origin: {origin_link}"
            a("")
            a(f"  [dim]{line}[/dim]" if oow else f"  {line}")

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
        pop_stratum_md = _click_link("pop", str(pid), class_label)
        if sp_obj:
            sp_md = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
            pop_label = f"{pop_stratum_md}  ({sp_md})"
        else:
            pop_label = pop_stratum_md
        top = sorted(pop.dominant_beliefs.items(), key=lambda kv: -kv[1])[:3]
        belief_str = "  ".join(
            _color_short_tag(t, v) for t, v in top
        ) or "[#5a7090]none[/]"
        vis = f"  \\[vis:{pop.visibility:.2f}]" if not pop.pinned else ""
        a(f"  {pm}↳ {pop_label}  sz:{pop.size_magnitude}{vis}{pe}")
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
        sp_md = _click_link("species", str(sp_obj.id), f"{_e(sp_obj.name)}")
        a(f"  species: {sp_md}")

    dev = display.DEV_MODE

    def _gated(entity, line_markup: str) -> None:
        """Emit a line only if the referenced entity is in the Window
        (or always, when running with --dev — dimmed if OOW)."""
        if entity is None:
            return
        oow = not is_in_window(entity)
        if oow and not dev:
            return
        if oow:
            a(f"  [dim]{line_markup}[/dim]")
        else:
            a(f"  {line_markup}")

    loc = state.locations.get(str(m.current_location)) if m.current_location else None
    if loc:
        loc_str = _format_location_chain(state, m.current_location)
        _gated(loc, f"location: {loc_str}")

    home = state.locations.get(str(m.home_location)) if m.home_location else None
    if home and (not loc or str(home.id) != str(loc.id)):
        home_str = _format_location_chain(state, m.home_location)
        _gated(home, f"origin:   {home_str}")

    civ = state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
    if civ:
        civ_link = _click_link("civ", str(m.civilization_id), f"{_e(civ.name)}")
        _gated(civ, f"civilization: {civ_link}")

    pop = state.pops.get(str(m.pop_id)) if m.pop_id else None
    if pop:
        stratum = pop.stratum.title() if pop.stratum else "Pop"
        sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
        pop_md = _click_link("pop", str(pop.id), f"{_e(stratum)}")
        if sp_obj:
            sp_md = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
            _gated(pop, f"pop:      {pop_md} ({sp_md})  sz:{pop.size_magnitude}")
        else:
            _gated(pop, f"pop:      {pop_md}  sz:{pop.size_magnitude}")

    if m.status_tags or m.personal_tags or m.belief_tags or m.culture_tags:
        a("")
    if m.status_tags:
        a(f"  status:  {_e(', '.join(_short_tag(t) for t in m.status_tags))}")
    if m.personal_tags:
        a(f"  tags:    {_e(', '.join(_short_tag(t) for t in m.personal_tags))}")
    if m.belief_tags:
        a(f"  beliefs: {_format_beliefs_markup(m.belief_tags)}")
    if m.culture_tags:
        a(f"  culture: {_format_culture_markup(m.culture_tags)}")

    if m.role == MortalRole.PROXIUS:
        a("")
        a("[bold #4a80b0]PROXIUS GOAL[/]")
        if m.active_goal:
            g = m.active_goal
            # Directive label — derived from the imago the player chose.
            if g.label:
                a(f"  directive: {_e(g.label)}")
            elif g.imago_node_id:
                from utilities.imago_registry import get_registry as get_imago_registry
                ireg = get_imago_registry()
                node = ireg.get_node(g.imago_node_id)
                imago_label = node.name if node else g.imago_node_id
                a(f"  directive: preaching [#a0b8d0]{_e(imago_label)}[/]")
            elif g.research_domain:
                a(f"  directive: researching {_e(_short_tag(g.research_domain))}")
            # Targets — only what the player explicitly set.
            if g.target_civilization_id:
                civ = state.civilizations.get(str(g.target_civilization_id))
                if civ:
                    civ_link = _click_link(
                        "civ", str(g.target_civilization_id),
                        f"{_e(civ.name)}",
                    )
                    a(f"  target: {civ_link}")
            if g.target_location_id:
                loc = state.locations.get(str(g.target_location_id))
                if loc:
                    loc_link = _location_link(state, g.target_location_id, f"{_e(loc.name)}")
                    a(f"  location: {loc_link}")
            ticks_active = state.tick_number - g.started_at_tick
            a(f"  ticks at task: {ticks_active}")
            if g.petition_pending:
                a(f"  [#c09030]petition pending — awaiting new orders[/]")
        else:
            a("  [#5a7090](idle — no active directive)[/]")

        # Last report from the Proxius (Phase 2.5 REPORT_TO_DEMIURGE action).
        if m.active_goal and m.active_goal.report_log:
            a("")
            a("[bold #4a80b0]LAST REPORT[/]")
            last = m.active_goal.report_log[-1]
            for raw_line in str(last).splitlines():
                a(f"  [#7090b0]{_e(raw_line)}[/]")

        # Last audit text (from Audit Proxius action).
        if m.last_audit_text:
            tick_str = f" (tick {m.last_audit_tick})" if m.last_audit_tick is not None else ""
            a("")
            a(f"[bold #4a80b0]LAST AUDIT{tick_str}[/]")
            for raw_line in m.last_audit_text.splitlines():
                a(f"  [#7090b0]{_e(raw_line)}[/]")

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

    # Last evaluation (with delta vs. prior cycle)
    if lum.last_evaluation:
        ev = lum.last_evaluation
        prev = lum.previous_evaluation or {}
        tick_str = f" (tick {lum.last_evaluation_tick})" if lum.last_evaluation_tick is not None else ""
        a("")
        a(f"[bold #4a80b0]LAST EVALUATION{tick_str}[/]")

        def _delta_str(cur: float, prev_v) -> str:
            if prev_v is None:
                return ""
            d = cur - float(prev_v)
            color = "#50b870" if d > 0 else ("#b04050" if d < 0 else "#5a7090")
            return f"  [{color}]({d:+.2f})[/]"

        # Overall alignment
        cur_align = float(ev.get("overall_domain_alignment", 0.0))
        prev_align = prev.get("overall_domain_alignment")
        a(f"  overall alignment: {cur_align:+.2f}{_delta_str(cur_align, prev_align)}")

        # Attention level (enum string)
        att_lvl = ev.get("attention_level", "—")
        a(f"  attention level:   {_e(str(att_lvl).upper())}")

        # Disposition delta this cycle
        dd = ev.get("disposition_delta") or {}
        dd_prev = prev.get("disposition_delta") or {}
        dd_r = float(dd.get("results", 0.0))
        dd_m = float(dd.get("methods", 0.0))
        r_color = "#50b870" if dd_r >= 0 else "#b04050"
        m_color = "#50b870" if dd_m >= 0 else "#b04050"
        prev_note = ""
        if dd_prev:
            pr = float(dd_prev.get("results", 0.0))
            pm = float(dd_prev.get("methods", 0.0))
            prev_note = f"   [#5a7090](prev R:{pr:+.2f} M:{pm:+.2f})[/]"
        a(f"  disposition delta: "
          f"R[{r_color}]{dd_r:+.2f}[/]  M[{m_color}]{dd_m:+.2f}[/]{prev_note}")

        # Summary note
        summary = ev.get("summary_note", "")
        if summary:
            a(f"  [#7090b0]{_e(summary)}[/]")

        # Top reasons from the disposition delta
        reasons = dd.get("reasons") or []
        if reasons:
            a("  reasons:")
            for r in reasons[:5]:
                if isinstance(r, dict):
                    note = r.get("note") or r.get("reason") or ""
                else:
                    note = str(r)
                if note:
                    a(f"    · [#7090b0]{_e(str(note))}[/]")

    # Last orders response
    if lum.last_orders_response:
        tick_str = f" (tick {lum.last_orders_response_tick})" if lum.last_orders_response_tick is not None else ""
        a("")
        a(f"[bold #4a80b0]LAST ORDERS RESPONSE{tick_str}[/]")
        for raw_line in lum.last_orders_response.splitlines():
            a(f"  [#7090b0]{_e(raw_line)}[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# POP
# ─────────────────────────────────────────

def render_pop_detail(state: "SimulationState", pop_id: str) -> Text:
    pop = state.pops.get(str(pop_id))
    if not pop:
        return _not_found(f"Pop {pop_id}")

    lines: list[str] = []
    a = lines.append

    stratum = pop.stratum.title() if pop.stratum else "Pop"
    sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
    header = f"{stratum} Pop"
    if sp_obj:
        header += f" ({_e(sp_obj.name)})"
    a(f"[bold #4a80b0]POP: {header}[/]")
    a("")

    a(f"  size: {pop.size_magnitude} ({_size_magnitude_word(pop.size_magnitude)})")
    if pop.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {pop.visibility:.2f}")

    if sp_obj:
        sp_link = _click_link("species", str(sp_obj.id), f"{_e(sp_obj.name)}")
        a(f"  species: {sp_link}")

    civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
    if civ:
        civ_link = _click_link("civ", str(civ.id), f"{_e(civ.name)}")
        a(f"  civilization: {civ_link}")

    loc = state.locations.get(str(pop.current_location)) if pop.current_location else None
    if loc:
        loc_str = _format_location_chain(state, pop.current_location)
        a(f"  location: {loc_str}")

    if pop.dominant_beliefs:
        a("")
        a("[bold #4a80b0]BELIEFS[/]")
        for tag, weight in sorted(pop.dominant_beliefs.items(), key=lambda kv: -kv[1]):
            chip = _color_short_tag(tag, weight, with_value=False)
            a(f"  {chip}  {weight:.2f}")

    if pop.culture_tags:
        a("")
        a("[bold #4a80b0]CULTURE[/]")
        for tag, weight in sorted(pop.culture_tags.items(), key=lambda kv: -kv[1]):
            a(f"  {_e(_short_tag(tag))}  {weight:.2f}")

    if pop.rider_traits:
        a("")
        a("[bold #4a80b0]RIDER TRAITS (from Preaching)[/]")
        for tag, weight in sorted(pop.rider_traits.items(), key=lambda kv: -kv[1]):
            a(f"  {_e(_short_tag(tag))}  {weight:.2f}")

    if pop.preaching_imago_id:
        from utilities.imago_registry import get_registry as get_imago_registry
        ireg = get_imago_registry()
        node = ireg.get_node(pop.preaching_imago_id)
        imago_label = node.name if node else pop.preaching_imago_id
        a("")
        a(f"  [#c09030]goal target of Preach Imāgō: {_e(imago_label)}[/]")

    if pop.notable_mortal_ids:
        a("")
        a("[bold #4a80b0]NOTABLE MORTALS[/]")
        for mid in pop.notable_mortal_ids:
            m = state.mortals.get(str(mid))
            if not m:
                continue
            m_link = _click_link("mortal", str(mid), f"[bold]{_e(m.name)}[/]")
            role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
            a(f"  ● {m_link} \\[{role_str}]  align:{m.alignment:+.2f}")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# SPECIES
# ─────────────────────────────────────────

def render_species_detail(state: "SimulationState", species_id: str) -> Text:
    sp = state.species.get(str(species_id))
    if not sp:
        return _not_found(f"Species {species_id}")

    lines: list[str] = []
    a = lines.append

    a(f"[bold #4a80b0]SPECIES: {_e(sp.name)}[/]")
    a("")
    if sp.description:
        a(f"  [#7090b0]{_e(sp.description)}[/]")
        a("")

    sapient_str = "sapient" if sp.sapient else "non-sapient"
    a(f"  \\[{sapient_str}]   condition: \\[{_e(sp.condition.value)}]")
    if sp.transplanted:
        a(f"  [#c09030](transplanted from origin world)[/]")
    a(f"  lifespan: {sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}")
    if sp.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {sp.visibility:.2f}")

    origin = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
    if origin:
        origin_link = _location_link(state, sp.origin_world_id, f"{_e(origin.name)}")
        a(f"  origin world: {origin_link}")

    if sp.domain_tags:
        a("")
        a("[bold #4a80b0]DOMAIN AFFINITIES[/]")
        for t in sp.domain_tags:
            a(f"  {_e(_short_tag(t))}")

    if sp.bio_tags:
        a("")
        a("[bold #4a80b0]BIOLOGY[/]")
        for t in sp.bio_tags:
            a(f"  {_e(_short_tag(t))}")

    # List Pops belonging to this species (Window-gated; dimmed in dev mode)
    dev = display.DEV_MODE
    pops_of_species = [p for p in state.pops.values() if str(p.species_id) == str(sp.id)]
    visible_pops = [p for p in pops_of_species if is_in_window(p) or dev]
    if visible_pops:
        a("")
        a(f"[bold #4a80b0]POPS ({len(visible_pops)})[/]")
        for pop in visible_pops:
            p_oow = not is_in_window(pop)
            pm = "[dim]" if p_oow else ""
            pe = "[/]" if p_oow else ""
            stratum = pop.stratum.title() if pop.stratum else "Pop"
            pop_link = _click_link("pop", str(pop.id), f"{_e(stratum)}")
            civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            civ_str = ""
            if civ:
                civ_link = _click_link("civ", str(civ.id), f"{_e(civ.name)}")
                civ_str = f"  in {civ_link}"
            a(f"  {pm}↳ {pop_link}  sz:{pop.size_magnitude}{civ_str}{pe}")

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
    "pop":       render_pop_detail,
    "species":   render_species_detail,
}
