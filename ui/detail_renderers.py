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

from core.universe_core import MortalRole, MortalStatus, PopLocation, is_wild_civ
from logic.tick_logic import is_in_window, is_mortal_visible, ENTITY_VISIBILITY_FLOOR
from ui import display
from ui.display import (
    _personality_label, _format_beliefs, _format_culture, _prominence_label,
    _short_tag, _trait_color, _format_beliefs_markup, _format_culture_markup,
    _color_short_tag, _pop_stratum_label,
)
from ui.widgets import _click_link, _maybe_gold

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState


def _format_calendar_date(date_tuple: tuple) -> str:
    """Format a (billions, millions, thousands, years, month, day) tuple as a calendar string."""
    bi, mi, th, yr, mo, dy = date_tuple
    full_year = bi * 1_000_000_000 + mi * 1_000_000 + th * 1_000 + yr
    return f"Day {dy} of Month {mo}, Year {full_year:,}"


def _not_found(label: str) -> Text:
    return Text.from_markup(f"[#b04050]{_e(label)} not found in current state.[/]")


_SIZE_MAGNITUDE_WORDS = {
    0: "ones", 1: "dozens", 2: "hundreds",
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
    """Return the click-link kind for a Location id, or None if it has no
    detail renderer."""
    lid = str(location_id)
    if lid in state.worlds:    return "world"
    if lid in state.systems:   return "system"
    if lid in state.galaxies:  return "galaxy"
    loc = state.locations.get(lid)
    from core.universe_core import PopLocation
    if isinstance(loc, PopLocation):
        return "poploc"
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
    # PopLocation: render parent world (linked) with PopLocation name (linked) in parens.
    parent = state.locations.get(str(loc.parent_id)) if loc.parent_id else None
    poploc_link = _location_link(state, loc.id, _e(loc.name))
    if parent is not None:
        parent_link = _location_link(state, parent.id, _e(parent.name))
        return f"{parent_link} ({poploc_link})"
    return poploc_link


# ─────────────────────────────────────────
# Species-presence helpers
# ─────────────────────────────────────────

def _species_in_civ(state: "SimulationState", civ) -> list[tuple[str, str]]:
    """Distinct species among this civ's pops; returns [(species_id, name)] sorted by name.

    Species not currently in the Window are excluded (or dimmed under dev mode via the
    OOW flag injected at render time)."""
    dev = display.DEV_MODE
    seen: dict[str, str] = {}
    for pid in civ.pop_ids:
        pop = state.pops.get(str(pid))
        if not pop or not pop.species_id:
            continue
        sp = state.species.get(str(pop.species_id))
        if not sp:
            continue
        if not is_in_window(sp) and not dev:
            continue
        seen[str(sp.id)] = sp.name
    return sorted(seen.items(), key=lambda kv: kv[1])


def _species_at_location(state: "SimulationState", loc_id) -> list[tuple[str, str, bool]]:
    """Distinct species at a SignificantLocation or PopLocation.

    SigLoc: Pops at child PopLocs + mortals at the SigLoc or any child PopLoc.
    PopLoc: Pops at this PopLoc + mortals at this PopLoc.

    A species is 'foreign' if represented only by a notable mortal (no Pop has it).
    Returns [(species_id, name, foreign)] with natives first (by name), foreigners last.
    """
    lid = str(loc_id)
    loc = state.locations.get(lid)
    if loc is None:
        return []

    dev = display.DEV_MODE

    if isinstance(loc, PopLocation):
        ploc_ids: set[str] = {lid}
        relevant_loc_ids: set[str] = {lid}
    else:
        ploc_ids = set()
        for cid in getattr(loc, "child_ids", []):
            child = state.locations.get(str(cid))
            if isinstance(child, PopLocation):
                ploc_ids.add(str(cid))
        relevant_loc_ids = ploc_ids | {lid}

    native: dict[str, str] = {}
    for pop in state.pops.values():
        if str(pop.current_location) not in ploc_ids:
            continue
        if not pop.species_id:
            continue
        sp = state.species.get(str(pop.species_id))
        if not sp:
            continue
        if not is_in_window(sp) and not dev:
            continue
        native[str(sp.id)] = sp.name

    foreign: dict[str, str] = {}
    for m in state.mortals.values():
        if m.status == MortalStatus.DECEASED:
            continue
        if str(m.current_location) not in relevant_loc_ids:
            continue
        if not m.species_id:
            continue
        sid = str(m.species_id)
        if sid in native:
            continue
        sp = state.species.get(sid)
        if not sp:
            continue
        if not is_in_window(sp) and not dev:
            continue
        foreign[sid] = sp.name

    natives = [(sid, name, False) for sid, name in sorted(native.items(), key=lambda kv: kv[1])]
    foreigners = [(sid, name, True) for sid, name in sorted(foreign.items(), key=lambda kv: kv[1])]
    return natives + foreigners


def _render_species_section(items: list[tuple[str, str, bool]], heading: str) -> list[str]:
    out: list[str] = ["", f"[bold #4a80b0]{heading}[/]"]
    if not items:
        out.append("  [#5a7090](none in Window)[/]")
        return out
    parts = []
    for sid, name, foreign in items:
        link = _click_link("species", sid, _e(name))
        parts.append(f"{link} (foreign)" if foreign else link)
    out.append("  " + ", ".join(parts))
    return out


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
    a(f"  condition: \\[{_e(world.condition.value)}]   age: {world.age:,.0f}")
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

    # Collect in-Window PopLocations that are children of this world, sorted
    # by (distance_from_core, name) so the planet's core surface comes first.
    visible_plocs: list = []
    for cid in world.child_ids:
        ploc = state.locations.get(str(cid))
        if not isinstance(ploc, PopLocation):
            continue
        if not is_in_window(ploc) and not dev:
            continue
        visible_plocs.append(ploc)
    visible_plocs.sort(key=lambda p: (p.distance_from_core, p.name))

    a("")
    a("[bold #4a80b0]SUB-LOCATIONS[/]")
    if not visible_plocs:
        a("  [#5a7090](none in Window)[/]")
    else:
        for ploc in visible_plocs:
            pl_oow = not is_in_window(ploc)
            plm = "[dim]" if pl_oow else ""
            ple = "[/]" if pl_oow else ""
            pl_link = _click_link("poploc", str(ploc.id), f"[bold]{_e(ploc.name)}[/]")
            dist_note = (
                f"  [#5a7090](d{ploc.distance_from_core})[/]"
                if ploc.distance_from_core > 0 else ""
            )
            a(f"  {plm}● {pl_link}{dist_note}{ple}")

    a("")
    a("[bold #4a80b0]CIVILIZATIONS[/]")
    any_civ = False
    for cid in world.civilization_ids:
        civ = state.civilizations.get(str(cid))
        if not civ or is_wild_civ(civ):
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
          f"S{h.stability:.0%} W{h.prosperity:.0%} C{h.cohesion:.0%}{ce}")
    if not any_civ:
        a("  [#5a7090](none in Window)[/]")

    # Helpers: group an iterable of items by their PopLocation id, filtered
    # to visible (or dev) and parented to this world.
    def _bucket_by_ploc(items_and_oow):
        buckets: dict = {}
        for item, oow in items_and_oow:
            ploc = state.locations.get(str(item.current_location)) if item.current_location else None
            if not isinstance(ploc, PopLocation):
                continue
            if str(ploc.parent_id) != str(world_id):
                continue
            buckets.setdefault(str(ploc.id), []).append((item, oow))
        return buckets

    def _ploc_header(ploc_id: str, *, dim: bool) -> str:
        pl = state.locations[ploc_id]
        link = _click_link("poploc", str(pl.id), _e(pl.name))
        dist_note = (
            f"  [#5a7090](d{pl.distance_from_core})[/]"
            if pl.distance_from_core > 0 else ""
        )
        wrap = ("[dim]", "[/]") if dim else ("", "")
        return f"  {wrap[0]}↳ \\[{link}]{dist_note}{wrap[1]}"

    # ── Species here ─────────────────────────────────────────
    lines.extend(_render_species_section(_species_at_location(state, world_id), "SPECIES HERE"))

    # ── Pops here ────────────────────────────────────────────
    pop_buckets = _bucket_by_ploc(
        (p, not is_in_window(p))
        for p in state.pops.values()
        if (is_in_window(p) or dev)
    )
    a("")
    a("[bold #4a80b0]POPS HERE[/]")
    if not pop_buckets:
        a("  [#5a7090](none in Window)[/]")
    else:
        multi = len(pop_buckets) > 1
        for ploc_id in sorted(pop_buckets.keys(),
                              key=lambda k: (state.locations[k].distance_from_core,
                                             state.locations[k].name)):
            if multi:
                a(_ploc_header(ploc_id, dim=False))
                pop_indent = "      "
            else:
                pop_indent = "  "
            for pop, p_oow in pop_buckets[ploc_id]:
                pm = "[dim]" if p_oow else ""
                pe = "[/]" if p_oow else ""
                is_wild = pop.is_wild
                class_label = _pop_stratum_label(pop)
                sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                pop_stratum_md = _click_link("pop", str(pop.id), class_label)
                if sp_obj:
                    sp_md = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
                    pop_label = f"{pop_stratum_md}  ({sp_md})"
                else:
                    pop_label = pop_stratum_md
                # Wild pops: label conveys it; skip both ↳ marker and civ suffix.
                marker = "" if is_wild else "↳ "
                if is_wild:
                    civ_suffix = ""
                else:
                    civ_obj = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
                    if civ_obj and not is_wild_civ(civ_obj):
                        civ_link = _click_link("civ", str(civ_obj.id), _e(civ_obj.name))
                        civ_suffix = f"  in {civ_link}"
                    else:
                        civ_suffix = ""
                a(f"{pop_indent}{pm}{marker}{pop_label}  sz:{pop.size_magnitude}{civ_suffix}{pe}")

    # ── Notable mortals here ─────────────────────────────────
    mortal_buckets = _bucket_by_ploc(
        (m, not is_mortal_visible(m))
        for m in state.mortals.values()
        if m.status != MortalStatus.DECEASED and (is_mortal_visible(m) or dev)
    )
    a("")
    a("[bold #4a80b0]NOTABLE MORTALS HERE[/]")
    if not mortal_buckets:
        a("  [#5a7090](none in Window)[/]")
    else:
        multi = len(mortal_buckets) > 1
        for ploc_id in sorted(mortal_buckets.keys(),
                              key=lambda k: (state.locations[k].distance_from_core,
                                             state.locations[k].name)):
            if multi:
                a(_ploc_header(ploc_id, dim=False))
                mortal_indent = "      "
            else:
                mortal_indent = "  "
            for m, m_oow in mortal_buckets[ploc_id]:
                mm = "[dim]" if m_oow else ""
                me = "[/]" if m_oow else ""
                role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
                m_link = _click_link("mortal", str(m.id), f"[bold]{_e(m.name)}[/]")
                a(f"{mortal_indent}{mm}● {m_link} \\[{role_str}]  align:{m.alignment:.2f}{me}")

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
        gal_link = _location_link(state, parent.id, f"{_e(parent.name)}")
        a(f"  in galaxy: {gal_link}")

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
    if is_wild_civ(civ):
        # Wild "civilizations" exist for bookkeeping only — they have no
        # player-facing info page. Reachable in theory via stale link.
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
    a(f"  stability:  {h.stability:+.0%}")
    a(f"  wealth:     {h.prosperity:+.0%}")
    a(f"  cohesion:   {h.cohesion:+.0%}")

    if display.DEV_MODE:
        a(f"  [#5a7090]age: {civ.age:,.0f} years  |  founded: {_format_calendar_date(civ.founding_date)}[/]")

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
            a(f"  {_color_short_tag(tag, val, with_value=False)}: {val:.0%}")

    if civ.culture_tags:
        a("")
        a("[bold #4a80b0]CULTURE[/]")
        a(f"  {_format_culture_markup(civ.culture_tags)}")

    dev = display.DEV_MODE

    # ── Constituent species ──────────────────────────────────
    species_items = _species_in_civ(state, civ)
    if species_items:
        a("")
        a("[bold #4a80b0]CONSTITUENT SPECIES[/]")
        parts = [_click_link("species", sid, _e(name)) for sid, name in species_items]
        a("  " + ", ".join(parts))

    # ── Pops, grouped by World → (PopLocation if >1) → Pops ──
    pops_by_world: dict = {}
    for pid in civ.pop_ids:
        pop = state.pops.get(str(pid))
        if not pop:
            continue
        if not is_in_window(pop) and not dev:
            continue
        ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
        if not isinstance(ploc, PopLocation):
            continue
        world_id = str(ploc.parent_id) if ploc.parent_id else None
        pops_by_world.setdefault(world_id, {}).setdefault(str(ploc.id), []).append(pop)

    a("")
    a("[bold #4a80b0]POPS[/]")
    if not pops_by_world:
        a("  [#5a7090](no pops visible in Window)[/]")
    else:
        world_keys = sorted(
            pops_by_world.keys(),
            key=lambda wid: state.worlds[wid].name if (wid and wid in state.worlds) else "~",
        )
        for wid in world_keys:
            ploc_buckets = pops_by_world[wid]
            world = state.worlds.get(wid) if wid else None
            if world:
                w_oow = not is_in_window(world)
                if w_oow and not dev:
                    continue
                wm = "[dim]" if w_oow else ""
                we = "[/]" if w_oow else ""
                world_link = _click_link("world", wid, f"[bold]{_e(world.name)}[/]")
                a(f"  {wm}● {world_link}{we}")
            else:
                a("  ● [#5a7090](unknown world)[/]")
            multi = len(ploc_buckets) > 1
            ploc_keys = sorted(
                ploc_buckets.keys(),
                key=lambda k: (state.locations[k].distance_from_core, state.locations[k].name),
            )
            for ploc_id in ploc_keys:
                if multi:
                    ploc = state.locations[ploc_id]
                    ploc_link = _click_link("poploc", ploc_id, _e(ploc.name))
                    dist_note = (
                        f"  [#5a7090](d{ploc.distance_from_core})[/]"
                        if ploc.distance_from_core > 0 else ""
                    )
                    a(f"      ↳ \\[{ploc_link}]{dist_note}")
                    pop_indent = "          "
                else:
                    pop_indent = "      "
                for pop in ploc_buckets[ploc_id]:
                    p_oow = not is_in_window(pop)
                    pm = "[dim]" if p_oow else ""
                    pe = "[/]" if p_oow else ""
                    class_label = _pop_stratum_label(pop)
                    sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                    pop_stratum_md = _click_link("pop", str(pop.id), class_label)
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
                    a(f"{pop_indent}{pm}↳ {pop_label}  sz:{pop.size_magnitude}{vis}{pe}")
                    a(f"{pop_indent}    {pm}{belief_str}{pe}")

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
    age_str = f"age:{m.chrono_age:,.0f}"
    if m.bio_age != m.chrono_age:
        age_str += f"  (bio:{m.bio_age:,.0f})"
    a(f"  {age_str}")
    _manually_pinned = (
        m.pinned
        and str(m.id) not in state.starting_pinned_ids
        and m.role not in (MortalRole.PROXIUS, MortalRole.HERALD)
    )
    if display.DEV_MODE or _manually_pinned:
        a(f"  [#5a7090]born: {_format_calendar_date(m.birthday)}[/]")
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
    if civ and not is_wild_civ(civ):
        civ_link = _click_link("civ", str(m.civilization_id), f"{_e(civ.name)}")
        _gated(civ, f"civilization: {civ_link}")

    pop = state.pops.get(str(m.pop_id)) if m.pop_id else None
    if pop:
        stratum = _pop_stratum_label(pop)
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
            if dev:
                # ── Verbose dev view: full ProxiusGoal state. ──
                if g.label:
                    a(f"  directive: {_e(g.label)}")
                if g.last_action is not None:
                    a(f"  last action: [#a0d080]{_e(g.last_action.value.replace('_', ' '))}[/]")
                else:
                    a(f"  last action: [#5a7090](not yet acted)[/]")
                if g.imago_node_id:
                    from utilities.imago_registry import get_registry as get_imago_registry
                    ireg = get_imago_registry()
                    node = ireg.get_node(g.imago_node_id)
                    imago_label = node.name if node else g.imago_node_id
                    a(f"  imago: [#a0b8d0]{_e(imago_label)}[/]")
                if g.target_civilization_id:
                    civ = state.civilizations.get(str(g.target_civilization_id))
                    if civ:
                        civ_link = _click_link(
                            "civ", str(g.target_civilization_id), f"{_e(civ.name)}",
                        )
                        a(f"  target civilization: {civ_link}")
                if g.target_location_id:
                    loc = state.locations.get(str(g.target_location_id))
                    if loc:
                        loc_link = _location_link(state, g.target_location_id, f"{_e(loc.name)}")
                        a(f"  target location: {loc_link}")
                if g.source_pop_id:
                    src = state.pops.get(str(g.source_pop_id))
                    if src:
                        slabel = _pop_stratum_label(src)
                        src_link = _click_link("pop", str(g.source_pop_id), f"{_e(slabel)}")
                        a(f"  source pop: {src_link}  sz:{src.size_magnitude}")
                if g.goal_pop_id:
                    gp = state.pops.get(str(g.goal_pop_id))
                    if gp:
                        glabel = _pop_stratum_label(gp)
                        gp_link = _click_link("pop", str(g.goal_pop_id), f"{_e(glabel)}")
                        a(f"  goal pop:   {gp_link}  sz:{gp.size_magnitude}")
                if g.research_domain:
                    a(f"  researching: {_e(_short_tag(g.research_domain))}")
                ticks_active = state.tick_number - g.started_at_tick
                a(f"  ticks at task: {ticks_active}")
                if g.petition_pending:
                    a(f"  [#c09030]petition pending ({g.petition_pending_ticks}/5 ticks)[/]")
            else:
                # ── Compact player view. ──
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

    if m.travel_intent and dev:
        ti = m.travel_intent
        tl = state.locations.get(str(ti.travel_location_id))
        if tl is not None:
            # Destination is the last key in legs (value == 0)
            dest_id = list(tl.legs.keys())[-1] if tl.legs else None
            dest_loc = state.locations.get(dest_id) if dest_id else None
            dest_name = dest_loc.name if dest_loc else (dest_id or "unknown")
            ticks_remaining = getattr(tl, "ticks_remaining", 0)
            a("")
            a("[bold #4a80b0]TRAVEL[/]")
            ticks_word = "tick" if ticks_remaining == 1 else "ticks"
            a(f"  Traveling → {_e(dest_name)} | {ticks_remaining} {ticks_word} remaining")

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
      f"R[{rc}]{d.results:+.0%}[/]  "
      f"M[{mc}]{d.methods:+.0%}[/]  "
      f"att[{ac}]{att:.0%}[/]")

    a("")
    a("[bold #4a80b0]DOMAIN AFFINITIES[/]")
    for tag, aff in sorted(lum.domains.items(), key=lambda kv: -kv[1]):
        chip = _color_short_tag(tag, aff, with_value=False)
        # Pad inside the color span so column alignment is preserved.
        a(f"  {chip}{' ' * max(0, 16 - len(_short_tag(tag)))}  {aff:+.0%}")

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

    stratum = _pop_stratum_label(pop)
    sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
    # Header uses Title Case even for the "wild" no-stratum fallback.
    if pop.is_wild and stratum == "wild":
        header = "Wild"
    else:
        header = stratum
    if sp_obj:
        header += f" ({_e(sp_obj.name)})"
    a(f"[bold #4a80b0]POP: {header}[/]")
    a("")

    if pop.is_wild and not pop.wild_stratum:
        stratum_text = "wild"
    else:
        stratum_text = pop.stratum.title() if pop.stratum else "—"
    a(f"  stratum: {stratum_text}")
    a(f"  size: {pop.size_magnitude} ({_size_magnitude_word(pop.size_magnitude)})")
    if pop.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {pop.visibility:.2f}")

    if sp_obj:
        sp_link = _click_link("species", str(sp_obj.id), f"{_e(sp_obj.name)}")
        a(f"  species: {sp_link}")

    civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
    if civ and not is_wild_civ(civ):
        civ_link = _click_link("civ", str(civ.id), f"{_e(civ.name)}")
        a(f"  civilization: {civ_link}")
    elif (civ and is_wild_civ(civ)) or not pop.civilization_id:
        a(f"  civilization: [#5a7090](wild)[/]")

    loc = state.locations.get(str(pop.current_location)) if pop.current_location else None
    if loc:
        loc_str = _format_location_chain(state, pop.current_location)
        a(f"  location: {loc_str}")

    if pop.dominant_beliefs:
        a("")
        a("[bold #4a80b0]BELIEFS[/]")
        for tag, weight in sorted(pop.dominant_beliefs.items(), key=lambda kv: -kv[1]):
            chip = _color_short_tag(tag, weight, with_value=False)
            a(f"  {chip}  {weight:.0%}")

    if pop.culture_tags:
        a("")
        a("[bold #4a80b0]CULTURE[/]")
        for tag, weight in sorted(pop.culture_tags.items(), key=lambda kv: -kv[1]):
            chip = _color_short_tag(tag, weight, with_value=False)
            a(f"  {chip}  {weight:.0%}")

    if pop.rider_traits:
        a("")
        a("[bold #4a80b0]RIDER TRAITS (from Preaching)[/]")
        for tag, weight in sorted(pop.rider_traits.items(), key=lambda kv: -kv[1]):
            chip = _color_short_tag(tag, weight, with_value=False)
            a(f"  {chip}  {weight:.0%}")

    if pop.preaching_imago_id:
        from utilities.imago_registry import get_registry as get_imago_registry
        ireg = get_imago_registry()
        node = ireg.get_node(pop.preaching_imago_id)
        imago_label = node.name if node else pop.preaching_imago_id
        a("")
        a(f"  [#c09030]goal target of Preach Imāgō: {_e(imago_label)}[/]")

    dev = display.DEV_MODE
    a("")
    a("[bold #4a80b0]NOTABLE MORTALS[/]")
    any_m = False
    for mid in pop.notable_mortal_ids:
        m = state.mortals.get(str(mid))
        if not m or m.status == MortalStatus.DECEASED:
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
            stratum = _pop_stratum_label(pop)
            pop_link = _click_link("pop", str(pop.id), f"{_e(stratum)}")
            civ = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
            if civ and not is_wild_civ(civ):
                civ_link = _click_link("civ", str(civ.id), f"{_e(civ.name)}")
                civ_str = f"  in {civ_link}"
            else:
                civ_str = "  [#5a7090](wild)[/]"
            a(f"  {pm}↳ {pop_link}  sz:{pop.size_magnitude}{civ_str}{pe}")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# GALAXY
# ─────────────────────────────────────────

def render_galaxy_detail(state: "SimulationState", galaxy_id: str) -> Text:
    galaxy = state.galaxies.get(str(galaxy_id))
    if not galaxy:
        return _not_found(f"Galaxy {galaxy_id}")

    lines: list[str] = []
    a = lines.append
    dev = display.DEV_MODE

    a(f"[bold #4a80b0]GALAXY: {_e(galaxy.name)}[/]")
    a("")
    if galaxy.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {galaxy.visibility:.2f}")
    if galaxy.description:
        a("")
        a(f"  [#7090b0]{_e(galaxy.description)}[/]")

    a("")
    a("[bold #4a80b0]SYSTEMS[/]")
    any_s = False
    for sid in galaxy.child_ids:
        sys_obj = state.systems.get(str(sid))
        if not sys_obj:
            continue
        s_oow = not is_in_window(sys_obj)
        if s_oow and not dev:
            continue
        any_s = True
        marker = "●" if not s_oow else "○"
        style = "[dim]" if s_oow else ""
        end = "[/]" if s_oow else ""
        star_str = sys_obj.star_type.value if hasattr(sys_obj, "star_type") else "?"
        n_worlds = sum(
            1 for x in sys_obj.child_ids
            if str(x) in state.worlds and is_in_window(state.worlds[str(x)])
        )
        worlds_str = f"{n_worlds} world(s) known" if n_worlds else "no worlds known"
        sys_link = _click_link("system", str(sid), f"[bold]{_e(sys_obj.name)}[/]")
        a(f"  {style}{marker} {sys_link}  \\[{_e(star_str)}]  {worlds_str}{end}")
    if not any_s:
        a("  [#5a7090](no systems known in this galaxy)[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# POPLOCATION
# ─────────────────────────────────────────

def render_poploc_detail(state: "SimulationState", poploc_id: str) -> Text:
    from core.universe_core import PopLocation
    loc = state.locations.get(str(poploc_id))
    if not isinstance(loc, PopLocation):
        return _not_found(f"PopLocation {poploc_id}")

    lines: list[str] = []
    a = lines.append
    dev = display.DEV_MODE

    a(f"[bold #4a80b0]POPULATED LOCATION: {_e(loc.name)}[/]")
    a("")
    if loc.pinned:
        a(f"  [#5a7090]pinned (always in Window)[/]")
    else:
        a(f"  visibility: {loc.visibility:.2f}")
    a(f"  distance from core: [#a0c0e0]{loc.distance_from_core}[/]")
    if loc.description:
        a("")
        a(f"  [#7090b0]{_e(loc.description)}[/]")

    parent = state.locations.get(str(loc.parent_id)) if loc.parent_id else None
    if parent is not None:
        parent_link = _location_link(state, parent.id, f"{_e(parent.name)}")
        a(f"  on world: {parent_link}")

    if loc.traits:
        a(f"  traits: {_e(', '.join(_short_tag(t) for t in loc.traits))}")

    # Pops here — bucketed by civilization (None last for wild).
    civ_buckets: dict = {}
    for pop in state.pops.values():
        if str(pop.current_location) != str(loc.id):
            continue
        p_oow = not is_in_window(pop)
        if p_oow and not dev:
            continue
        civ_obj = state.civilizations.get(str(pop.civilization_id)) if pop.civilization_id else None
        civ_key = str(pop.civilization_id) if (civ_obj and not is_wild_civ(civ_obj)) else None
        civ_buckets.setdefault(civ_key, []).append((pop, p_oow))

    lines.extend(_render_species_section(_species_at_location(state, loc.id), "SPECIES HERE"))

    a("")
    a("[bold #4a80b0]POPS HERE[/]")
    if not civ_buckets:
        a("  [#5a7090](none in Window)[/]")
    else:
        # Sort: civs first (by name), wild last.
        ordered_keys = sorted(
            [k for k in civ_buckets.keys() if k is not None],
            key=lambda k: state.civilizations[k].name if k in state.civilizations else "",
        )
        if None in civ_buckets:
            ordered_keys.append(None)
        for civ_key in ordered_keys:
            # Wild bucket has no header — the per-pop "wild" label conveys it.
            if civ_key is not None:
                civ = state.civilizations.get(civ_key)
                if civ and not is_wild_civ(civ):
                    civ_link = _click_link("civ", str(civ_key), f"[bold]{_e(civ.name)}[/]")
                    a(f"  {civ_link}:")
            for pop, p_oow in civ_buckets[civ_key]:
                pm = "[dim]" if p_oow else ""
                pe = "[/]" if p_oow else ""
                class_label = _pop_stratum_label(pop)
                pop_link = _click_link("pop", str(pop.id), class_label)
                sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                sp_str = ""
                if sp_obj:
                    sp_link = _click_link("species", str(sp_obj.id), _e(sp_obj.name))
                    sp_str = f"  ({sp_link})"
                a(f"    {pm}↳ {pop_link}{sp_str}  sz:{pop.size_magnitude}{pe}")

    a("")
    a("[bold #4a80b0]NOTABLE MORTALS HERE[/]")
    any_m = False
    for mid, m in state.mortals.items():
        if str(m.current_location) != str(loc.id):
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


def render_travel_location_detail(state: "SimulationState", tl_id: str) -> Text:
    from core.universe_core import TravelLocation
    tl = state.locations.get(str(tl_id))
    if not isinstance(tl, TravelLocation):
        return _not_found(f"TravelLocation {tl_id}")

    lines: list[str] = []
    a = lines.append

    # Destination is the last key in legs (value == 0).
    dest_id = next((k for k, v in tl.legs.items() if v == 0), None)
    dest_loc = state.locations.get(str(dest_id)) if dest_id else None
    dest_label = _e(dest_loc.name) if dest_loc else (str(dest_id) if dest_id else "?")
    if dest_loc:
        dest_str = _location_link(state, dest_loc.id, dest_label)
    else:
        dest_str = dest_label

    a(f"[bold #4a80b0]IN TRANSIT → {dest_str}[/]")
    a("")

    # Current leg
    wp_loc = state.locations.get(str(tl.current_waypoint)) if tl.current_waypoint else None
    wp_name = _e(wp_loc.name) if wp_loc else (str(tl.current_waypoint) or "?")
    if wp_loc:
        wp_str = _location_link(state, wp_loc.id, wp_name)
    else:
        wp_str = wp_name
    a(f"  current leg: {wp_str}")
    a(f"  ticks remaining: [#a0c0e0]{tl.ticks_remaining}[/]")

    # Full itinerary
    a("")
    a("[bold #4a80b0]ITINERARY[/]")
    for loc_id_str, cost in tl.legs.items():
        leg_loc = state.locations.get(loc_id_str)
        leg_name = _e(leg_loc.name) if leg_loc else loc_id_str
        if leg_loc:
            leg_link = _location_link(state, leg_loc.id, leg_name)
        else:
            leg_link = leg_name
        if cost == 0:
            a(f"  ► {leg_link}  [#5a9060](destination)[/]")
        elif loc_id_str == str(tl.current_waypoint):
            a(f"  ◉ {leg_link}  [#a0c0e0]{tl.ticks_remaining}/{cost} tick(s) left[/]")
        else:
            a(f"  ○ {leg_link}  [#7090b0]{cost} tick(s)[/]")

    # Occupants
    a("")
    a("[bold #4a80b0]TRAVELERS[/]")
    if not tl.occupants:
        a("  [#5a7090](none)[/]")
    else:
        for occ_id in tl.occupants:
            m = state.mortals.get(str(occ_id))
            if m:
                m_link = _click_link("mortal", str(occ_id), f"[bold]{_e(m.name)}[/]")
                role_str = m.role.value.upper() if m.role != MortalRole.OTHER else "mortal"
                a(f"  ● {m_link} [{role_str}]")
            else:
                a(f"  ● [#7090b0]{str(occ_id)}[/]")

    return Text.from_markup("\n".join(lines))


# ─────────────────────────────────────────
# Dispatch table
# ─────────────────────────────────────────

RENDERERS = {
    "world":           render_world_detail,
    "system":          render_system_detail,
    "galaxy":          render_galaxy_detail,
    "poploc":          render_poploc_detail,
    "travel_location": render_travel_location_detail,
    "civ":             render_civ_detail,
    "mortal":          render_mortal_detail,
    "luminary":        render_luminary_detail,
    "pop":             render_pop_detail,
    "species":         render_species_detail,
}
