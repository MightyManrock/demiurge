"""
Presentation layer: formatters and snapshot renderers used by both the TUI
(via ui/) and the plain-text session log (via ui/session_log.py).

Imports only from core/, logic/, utilities/, and rich — never from textual
or ui/. This module is the lower layer; ui/ depends on it, not the reverse.
"""
from __future__ import annotations
import re
from uuid import UUID
from typing import TYPE_CHECKING

from rich.markup import escape as _e
from rich.text import Text

from core.universe_core import MortalRole, MortalStatus, MortalProminence, PopLocation
from logic.tick_logic import is_in_window, ENTITY_VISIBILITY_FLOOR
from utilities.domain_registry import get_registry as get_domain_registry

if TYPE_CHECKING:
    from core.onto_core import Luminary
    from logic.tick_logic import SimulationState, TickResult


# Visual separators used throughout display output.
SEP  = "─" * 60
SEP2 = "═" * 60

# Developer mode: set by main.py at startup from the --dev CLI flag.
# When True, out-of-Window narratives and entities are shown dimmed instead
# of being suppressed. Status bar is unaffected.
DEV_MODE: bool = False

# Sentinel prefixed to display_state/display_briefing lines that describe
# out-of-Window entities. `_lines_to_text` strips it and renders those lines
# dimmed; `_strip_oow` removes it for plain-text file logs.
_OOW = "\x01"


# ─────────────────────────────────────────
# OOW (out-of-window) sentinel handling
# ─────────────────────────────────────────

def _lines_to_text(lines: list[str]) -> Text:
    """Convert a list of lines (some marked with the _OOW sentinel) into a styled Text.

    Lines that start with the _OOW sentinel render in `dim` style; the rest
    render in the default style.
    """
    out = Text()
    for i, line in enumerate(lines):
        suffix = "\n" if i < len(lines) - 1 else ""
        if line.startswith(_OOW):
            out.append(line[len(_OOW):] + suffix, style="dim")
        else:
            out.append(line + suffix)
    return out


def _strip_oow(lines: list[str]) -> str:
    """Plain-text rendering: strip the sentinel for file logs."""
    return "\n".join(l[len(_OOW):] if l.startswith(_OOW) else l for l in lines)


# ─────────────────────────────────────────
# Atomic formatters
# ─────────────────────────────────────────

def _personality_label(lum: "Luminary") -> str:
    """Short personality descriptor derived from domain affinities."""
    dreg = get_domain_registry()
    p = dreg.compute_personality(lum.domains)
    parts = []
    if p.harshness > 0.3:
        parts.append("harsh")
    elif p.harshness < -0.3:
        parts.append("gentle")
    if p.capriciousness > 0.3:
        parts.append("mercurial")
    elif p.capriciousness < -0.3:
        parts.append("stable")
    if p.reactivity > 0.3:
        parts.append("auth.")
    elif p.reactivity < -0.4:
        parts.append("perm.")
    return "/".join(parts) if parts else "neutral"


def _trait_color(value: float, scale: float = 1.0) -> str:
    """
    Map a trait strength (or modifier) to a hex color used for tag rendering.

    Positive scale: mid-gray (~0) → greenish-gray (0.05) → through greens,
    teals, blues, blue-violets → purple (≥0.85). Negative scale runs
    yellowish-gray (~0) → amber → red.

    `scale` divides the input first. Use `1.0` for canonical [0, 1] strengths
    (beliefs, culture, affinities). For signed modifiers whose meaningful
    magnitude is narrower (e.g. Imago mechanics in roughly ±0.3), pass a
    smaller scale so the gradient compresses to that range.
    """
    # v = (value / scale) if scale else value
    # if v >= 0.85:    return "#9040c8"   # purple
    # if v >= 0.70:    return "#6050d0"   # blue-violet
    # if v >= 0.60:    return "#4070d0"   # blue
    # if v >= 0.50:    return "#4090c8"   # teal-blue
    # if v >= 0.40:    return "#40b8c0"   # teal
    # if v >= 0.30:    return "#40c0a0"   # green-teal
    # if v >= 0.20:    return "#50b880"   # green
    # if v >= 0.10:    return "#60a070"   # light green
    # if v >= 0.05:    return "#6a8070"   # greenish-gray
    # if v >= 0.00:    return "#707070"   # mid-gray
    # if v >= -0.05:   return "#807060"   # yellowish-gray
    # if v >= -0.15:   return "#a07050"   # amber
    # if v >= -0.30:   return "#b06040"   # orange
    # if v >= -0.50:   return "#b85040"   # red-orange
    # return "#b04040"                    # red

    v = (value / scale) if scale else value
    if v >= 0.85:    return "#B818B0"   # purple
    if v >= 0.80:    return "#9430A1"   # violet-purple
    if v >= 0.70:    return "#6F23AD"   # blue-violet
    if v >= 0.60:    return "#5040B8"   # blue
    if v >= 0.50:    return "#4949A6"   # teal-blue
    if v >= 0.40:    return "#465B88"   # teal
    if v >= 0.30:    return "#426D6A"   # green-teal
    if v >= 0.20:    return "#577D71"   # green
    if v >= 0.10:    return "#6B8C77"   # light green
    if v >= 0.05:    return "#8FA194"   # greenish-gray
    if v >= 0.00:    return "#8F8F8F"   # mid-gray
    if v >= -0.05:   return "#807060"   # yellowish-gray
    if v >= -0.15:   return "#A17555"   # amber
    if v >= -0.30:   return "#B06040"   # orange
    if v >= -0.50:   return "#b85040"   # red-orange
    return "#D11111"                    # red

def _short_tag(tag: str) -> str:
    """
    Render a tag in its short, human-readable form.

    - `domain:*` → Title-Cased (`'domain:order'` → `'Order'`) — Domains read
      as proper nouns in the UI.
    - everything else (culture tags, personal/status tags, bare strings) →
      lowercase with underscores converted to spaces.
    """
    if tag.startswith("domain:"):
        return tag.split(":", 1)[1].replace("_", " ").title()
    if ":" in tag:
        return tag.split(":", 1)[1].replace("_", " ")
    return tag.replace("_", " ")


def _format_beliefs(beliefs: "dict[str, float]") -> str:
    if not beliefs:
        return ""
    return "  ".join(
        f"{_short_tag(tag)}({v:.0%})"
        for tag, v in sorted(beliefs.items(), key=lambda kv: -kv[1])
    )


def _format_culture(tags: "dict[str, float]") -> str:
    if not tags:
        return ""
    return ", ".join(
        f"{_short_tag(t)}({v:.0%})"
        for t, v in sorted(tags.items(), key=lambda kv: -kv[1])
    )


def _maybe_domain_link(tag: str, markup: str) -> str:
    """If `tag` is a Domain tag, wrap `markup` in a click action that opens the
    Divine Wisdom tab on that Domain's tree. Non-Domain tags pass through."""
    if tag.startswith("domain:"):
        return f"[@click=screen.open_divine_wisdom('{tag}')]{markup}[/]"
    return markup


def _format_beliefs_markup(
    beliefs: "dict[str, float]", scale: float = 1.0, top_n: "int | None" = None,
) -> str:
    """Like `_format_beliefs` but each tag is wrapped in a `[#color]…[/]` span
    keyed off its value. Output is Rich markup; feed through `Text.from_markup`
    and do NOT pass through `_e()` (it would escape the color brackets).

    If `top_n` is set, only the highest-valued entries are rendered and any
    remainder is summarized as `(+N others)`.
    """
    if not beliefs:
        return ""
    sorted_items = sorted(beliefs.items(), key=lambda kv: -kv[1])
    shown = sorted_items if top_n is None else sorted_items[:top_n]
    parts = []
    for tag, v in shown:
        color = _trait_color(v, scale=scale)
        chip = f"[{color}]{_short_tag(tag)}({v:.0%})[/]"
        parts.append(_maybe_domain_link(tag, chip))
    rendered = "  ".join(parts)
    extra = len(sorted_items) - len(shown)
    if extra > 0:
        rendered += f"  [#5a7090](+{extra} others)[/]"
    return rendered


def _format_culture_markup(
    tags: "dict[str, float]", scale: float = 1.0, top_n: "int | None" = None,
) -> str:
    """Markup variant of `_format_culture` — colors per strength, value appended.
    Optional `top_n` truncates with a `(+N others)` summary suffix."""
    if not tags:
        return ""
    sorted_items = sorted(tags.items(), key=lambda kv: -kv[1])
    shown = sorted_items if top_n is None else sorted_items[:top_n]
    parts = []
    for tag, v in shown:
        color = _trait_color(v, scale=scale)
        chip = f"[{color}]{_short_tag(tag)}({v:.0%})[/]"
        parts.append(_maybe_domain_link(tag, chip))
    rendered = ", ".join(parts)
    extra = len(sorted_items) - len(shown)
    if extra > 0:
        rendered += f"  [#5a7090](+{extra} others)[/]"
    return rendered


def _color_short_tag(tag: str, value: float, *, with_value: bool = True, scale: float = 1.0) -> str:
    """Single-tag colored markup. `with_value=True` appends `(0.42)`."""
    color = _trait_color(value, scale=scale)
    label = _short_tag(tag)
    suffix = f"({value:.0%})" if with_value else ""
    return _maybe_domain_link(tag, f"[{color}]{label}{suffix}[/]")


def _pop_stratum_label(pop) -> str:
    """Player-facing single-segment label for a Pop. When `pop.name` is set,
    that authored name takes priority. Otherwise we render the computed
    stratum — Title Case for civilized strata, the literal 'wild' (lowercase)
    only when no wild_stratum is available either."""
    if getattr(pop, "name", None):
        return pop.name
    if not pop.stratum:
        return "Pop"
    if pop.stratum == "wild":
        return "wild"
    return pop.stratum.title()


def _pop_identity_label(state, pop) -> str:
    """Full Pop identity for top-level contexts (detail-tab names, pickers,
    isolated rows): `(name or stratum) (Species)`. Falls back gracefully
    when species or stratum are missing."""
    primary = _pop_stratum_label(pop)
    sp = state.species.get(str(pop.species_id)) if pop.species_id else None
    if sp:
        return f"{primary} ({sp.name})"
    return primary


def _prominence_label(mortal) -> str:
    if not mortal.prominence_roles or mortal.prominence_roles == [MortalProminence.NONE]:
        role_part = "no notable role"
    else:
        role_part = " · ".join(r.value.title() for r in mortal.prominence_roles)
    return f"{role_part}  [prominence:{mortal.prominence:.2f}]"


def _name_for_id(uid: "UUID", state: "SimulationState") -> str:
    sid = str(uid)
    for d in [state.mortals, state.civilizations, state.locations, state.luminaries]:
        if sid in d:
            return getattr(d[sid], "name", sid[:8])
    return sid[:8]


_KIND_FOR_COLLECTION = [
    ("mortals",       "mortal"),
    ("civilizations", "civ"),
    ("species",       "species"),
]

def _name_link_for_id(uid: "UUID", state: "SimulationState") -> str:
    """Like _name_for_id but returns a styled @click link for the entity's detail page."""
    sid = str(uid)
    for attr, kind in _KIND_FOR_COLLECTION:
        col = getattr(state, attr)
        if sid in col:
            name = getattr(col[sid], "name", sid[:8])
            return _entity_link(kind, sid, name)
    if sid in state.locations:
        loc = state.locations[sid]
        name = getattr(loc, "name", sid[:8])
        loc_kind = "poploc" if isinstance(loc, PopLocation) else (
            "world" if hasattr(loc, "child_ids") else "location"
        )
        return _entity_link(loc_kind, sid, name)
    if sid in state.luminaries:
        name = getattr(state.luminaries[sid], "name", sid[:8])
        return _entity_link("luminary", sid, name)
    return _e(sid[:8])


def _wrap_desc(text: str, width: int = 58, indent: str = "  ") -> str:
    """Word-wrap description text, indenting continuation lines."""
    if not text:
        return ""
    words = text.split()
    lines: list[str] = []
    current = indent
    for word in words:
        candidate = current + word if current == indent else current + " " + word
        if len(candidate) <= width:
            current = candidate
        else:
            if current != indent:
                lines.append(current)
            current = indent + word
    if current != indent:
        lines.append(current)
    return "\n".join(lines)


def _get_lum_domain_context(state: "SimulationState"):
    """Returns (lum_info, fellow_tags, all_lum_canonical_tags)."""
    dreg = get_domain_registry()
    lum_info: list[tuple] = []
    per_lum: dict[str, list[str]] = {}
    for lid, lum in state.luminaries.items():
        tags = [t for t in lum.domains.keys() if dreg.is_canonical(t)]
        per_lum[lid] = tags
        lum_info.append((lum, tags))
    fellow_tags: dict[str, set[str]] = {}
    for lid in per_lum:
        fellow_tags[lid] = {
            t for other_lid, other_tags in per_lum.items()
            if other_lid != lid
            for t in other_tags
        }
    seen: set[str] = set()
    all_canonical: list[str] = []
    for tags in per_lum.values():
        for t in tags:
            if t not in seen:
                seen.add(t)
                all_canonical.append(t)
    return lum_info, fellow_tags, all_canonical


# ─────────────────────────────────────────
# Snapshot renderers
# ─────────────────────────────────────────

def display_state(state: "SimulationState", dev_mode: bool = False) -> list[str]:
    """
    Returns lines as a list[str]. Out-of-Window entity lines are prefixed with the
    _OOW sentinel when dev_mode is True; otherwise they are omitted entirely.
    Use _lines_to_text() for RichLog display or _strip_oow() for plain-text logs.
    """
    lines = [
        SEP2,
        f"  UNIVERSE: {state.universe.name}",
        f"  {state.universe.current_age.display()}  |  Tick: {state.tick_number}",
        SEP2,
    ]
    fp = state.demiurge.footprint
    es = state.essence
    lines += [
        "DEMIURGE",
        f"  Footprint — overt:{fp.overt_miracles:.2f}  subtle:{fp.subtle_influence:.2f}  "
        f"proxii:{fp.proxius_activity:.2f}  creation:{fp.direct_creation:.2f}",
        f"  Essence   — actual:{es.actual:.2f}  apparent:{es.apparent:.2f}  "
        f"concealment:{es.concealment_integrity:.2f}",
        f"  Puissance — {state.demiurge.puissance:.2f}",
        SEP,
    ]
    lines.append("LUMINARIES")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        lines.append(
            f"  {lum.name:12s}  results:{d.results:+.0%}  methods:{d.methods:+.0%}  "
            f"attention:{att:.0%}  [{_personality_label(lum)}]"
        )
    lines.append(SEP)
    lines.append("WORLDS")
    for wid, world in state.worlds.items():
        w_oow = not is_in_window(world)
        if w_oow and not dev_mode:
            continue
        wm = _OOW if w_oow else ""
        domain_str = _format_beliefs(world.domain_expression) or "none"
        vis_note = f"  [vis:{world.visibility:.0%}]" if not world.pinned else ""
        lines.append(f"{wm}  {world.name}  [{world.condition.value}]{vis_note}  domain: {domain_str}")
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if not civ:
                continue
            c_oow = not is_in_window(civ)
            if c_oow and not dev_mode:
                continue
            cm = _OOW if (w_oow or c_oow) else ""
            h = civ.health
            civ_vis = f"  [vis:{civ.visibility:.0%}]" if not civ.pinned else ""
            lines.append(
                f"{cm}    └─ {civ.name} [{civ.scale.value}]{civ_vis}  "
                f"stab:{h.stability:.0%} wealth:{h.prosperity:.0%} coh:{h.cohesion:.0%}"
            )
            lines.append(f"{cm}       beliefs: {_format_beliefs(civ.dominant_beliefs) or 'none'}")
            for pid in civ.pop_ids:
                pop = state.pops.get(str(pid))
                if not pop:
                    continue
                p_oow = not is_in_window(pop)
                if p_oow and not dev_mode:
                    continue
                pm = _OOW if (w_oow or c_oow or p_oow) else ""
                class_label = _pop_stratum_label(pop)
                sp_obj = state.species.get(str(pop.species_id)) if pop.species_id else None
                sp_note = f"  ({sp_obj.name})" if sp_obj else ""
                top_beliefs = sorted(pop.dominant_beliefs.items(), key=lambda x: -x[1])[:2]
                belief_str = "  ".join(
                    f"{_short_tag(t)}({v:.0%})" for t, v in top_beliefs
                ) or "none"
                vis_note = f"  [vis:{pop.visibility:.0%}]" if not pop.pinned else ""
                lines.append(
                    f"{pm}       ↳ {class_label}{sp_note}  sz:{pop.size_magnitude}"
                    f"  {belief_str}{vis_note}"
                )
    lines.append(SEP)
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if mortal.status == MortalStatus.DECEASED:
            continue
        m_oow = not mortal.pinned and mortal.visibility <= ENTITY_VISIBILITY_FLOOR
        if m_oow and not dev_mode:
            continue
        mm = _OOW if m_oow else ""
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str  = f"age:{mortal.chrono_age:,.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:,.0f})"
        prom_str = _prominence_label(mortal)
        vis_note = f"  vis:{mortal.visibility:.0%}" if not mortal.pinned else ""
        sp_obj   = state.species.get(str(mortal.species_id)) if mortal.species_id else None
        sp_str   = f"  sp:{sp_obj.name}" if sp_obj else ""
        pop_obj  = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
        pop_str  = f"  pop:{pop_obj.stratum.title()}" if pop_obj else ""
        lines.append(
            f"{mm}  {mortal.name:16s} [{role_str}]  align:{mortal.alignment:.2f}  "
            f"{age_str}{vis_note}{sp_str}{pop_str}  {prom_str}"
        )
    lines.append(SEP)
    lines.append("ONGOING ACTIONS")
    if state.pending_actions:
        for cat_val, oa in state.pending_actions.items():
            cat_label  = cat_val.replace("_", " ").title()
            target_str = f" → {_name_for_id(oa.target_id, state)}" if oa.target_id else ""
            lines.append(
                f"  [{cat_label}] {oa.action_key.replace('_', ' ').title()}"
                f"{target_str}  ({oa.successful_ticks}/{oa.executed_ticks} success)"
            )
    else:
        lines.append("  None")
    lines.append(SEP2)
    return lines


_LOG_LINK_COLORS: dict[str, str] = {
    "galaxy":   "#60a070",
    "system":   "#9aa870",
    "world":    "#d4b070",
    "civ":      "#c89050",
    "mortal":   "#a080c0",
    "species":  "#80a0b0",
    "location": "#80b0a0",
    "poploc":   "#7090a8",
}


def _entity_link(kind: str, eid: str, name: str) -> str:
    color = _LOG_LINK_COLORS.get(kind, "#c0ccdc")
    return (
        f"[@click=screen.open_detail_by_id('{kind}','{eid}')]"
        f"[{color}]{_e(name)}[/][/]"
    )


def _build_name_index(state: "SimulationState") -> dict[str, tuple[str, str]]:
    index: dict[str, tuple[str, str]] = {}
    for eid, e in state.mortals.items():
        if e.name:
            index[e.name] = ("mortal", str(eid))
    for eid, e in state.civilizations.items():
        if e.name:
            index[e.name] = ("civ", str(eid))
    for eid, e in state.species.items():
        if e.name:
            index[e.name] = ("species", str(eid))
    for eid, e in state.worlds.items():
        if e.name:
            index[e.name] = ("world", str(eid))
    for eid, e in state.systems.items():
        if e.name:
            index[e.name] = ("system", str(eid))
    for eid, e in state.galaxies.items():
        if e.name:
            index[e.name] = ("galaxy", str(eid))
    for eid, e in state.locations.items():
        if isinstance(e, PopLocation) and e.name:
            index[e.name] = ("poploc", str(eid))
    return index


def _linkify(text: str, name_index: dict[str, tuple[str, str]]) -> str:
    """Escape plain text for Rich, replacing known entity names with @click links."""
    if not name_index:
        return _e(text)
    pattern = re.compile("|".join(re.escape(n) for n in sorted(name_index, key=len, reverse=True)))
    parts: list[str] = []
    last = 0
    for m in pattern.finditer(text):
        parts.append(_e(text[last:m.start()]))
        kind, eid = name_index[m.group()]
        parts.append(_entity_link(kind, eid, m.group()))
        last = m.end()
    parts.append(_e(text[last:]))
    return "".join(parts)


_ENTITY_SENTINEL_RE = re.compile(r"§(pop|civ)§([^§]+)§([^§]+)§")


def _process_narrative(text: str, name_index: dict[str, tuple[str, str]]) -> str:
    """Resolve §type§uuid§label§ sentinels, then linkify remaining plain text.

    Must split on sentinels BEFORE linkifying: _linkify would otherwise match
    entity names embedded inside sentinel tokens and corrupt the token format.
    """
    parts: list[str] = []
    last = 0
    for m in _ENTITY_SENTINEL_RE.finditer(text):
        if m.start() > last:
            parts.append(_linkify(text[last:m.start()], name_index))
        parts.append(_entity_link(m.group(1), m.group(2), m.group(3)))
        last = m.end()
    if last < len(text):
        parts.append(_linkify(text[last:], name_index))
    return "".join(parts)


# kept for any external callers; internally prefer _process_narrative
_resolve_pop_sentinels = lambda text: _ENTITY_SENTINEL_RE.sub(
    lambda m: _entity_link(m.group(1), m.group(2), m.group(3)), text
)


def display_tick_result_categorized(
    result: "TickResult", dev_mode: bool = False,
    state: "SimulationState | None" = None,
) -> list[tuple[str, str]]:
    """
    Same content as `display_tick_result` but emitted as a list of
    (category, markup-line) tuples for the Log tab's chip filter.

    Categories:
      - 'other'    — headers, separators, terminal scenario-end block
      - 'system'   — passive world events, essence claimed
      - 'actions'  — your queued action results
      - 'proxius'  — agent narratives
      - 'luminary' — disposition changes and dialogue triggers
    """
    out: list[tuple[str, str]] = []
    _nl = _build_name_index(state) if state is not None else {}

    out.append(("other", ""))
    out.append((
        "other",
        f"  TICK {result.tick_number} RESULT  "
        f"({result.universe_age_before.display()} → {result.universe_age_after.display()})",
    ))
    out.append(("other", SEP))

    visible_events = [
        ev for ev in result.passive_result.narrative_events
        if ev.in_window or dev_mode
    ]
    if visible_events:
        out.append(("system", "WORLD EVENTS"))
        for ev in visible_events:
            text = _linkify(ev.text, _nl)
            if not ev.in_window:
                out.append(("system", f"  • [dim]{text}[/dim]"))
            else:
                out.append(("system", f"  • {text}"))
        out.append(("system", ""))

    visible_action_entries = [e for e in result.action_result.entries if e.narrative]
    if visible_action_entries:
        out.append(("actions", "YOUR ACTIONS"))
        for entry in visible_action_entries:
            out.append((
                "actions",
                f"  \\[{entry.outcome.value.upper()}] {_process_narrative(entry.narrative, _nl)}",
            ))
        out.append(("actions", ""))

    if result.agent_narratives:
        out.append(("proxius", "PROXIUS REPORTS"))
        for n in result.agent_narratives:
            out.append(("proxius", f"  • {_linkify(n, _nl)}"))
        out.append(("proxius", ""))

    if result.mortal_narratives:
        out.append(("mortal", "PINNED MORTALS"))
        for n in result.mortal_narratives:
            out.append(("mortal", f"  • {_linkify(n, _nl)}"))
        out.append(("mortal", ""))

    if result.essence_claimed_by_domain:
        total = sum(result.essence_claimed_by_domain.values())
        parts = "  ".join(
            f"{_short_tag(tag)}:{amt:.3f}"
            for tag, amt in sorted(
                result.essence_claimed_by_domain.items(), key=lambda x: -x[1],
            )
        )
        out.append(("system", f"ESSENCE CLAIMED  (+{total:.3f} total)"))
        out.append(("system", f"  {parts}"))
        out.append(("system", ""))

    if result.disposition_changes:
        out.append(("luminary", "LUMINARY REACTIONS"))
        for lid, (r, m) in result.disposition_changes.items():
            ev   = next((e for e in result.evaluations if str(e.luminary_id) == lid), None)
            name = ev.summary_note.split(":")[0] if ev else lid[:8]
            dr   = ev.disposition_delta.results if ev else 0.0
            dm   = ev.disposition_delta.methods if ev else 0.0
            out.append((
                "luminary",
                f"  {name:12s}  results {r:+.2f} ({dr:+.3f})"
                f"  methods {m:+.2f} ({dm:+.3f})",
            ))
        out.append(("luminary", ""))

    if result.dialogue_triggers:
        out.append(("luminary", "DIVINE COMMUNICATIONS"))
        for trig in result.dialogue_triggers:
            out.append((
                "luminary",
                f"  \\[{trig.trigger_type.value.upper()}]  urgency:{trig.urgency:.1f}  "
                f"re: {_e(trig.subject_ref or 'general')}",
            ))
        out.append(("luminary", ""))

    if result.terminal.triggered:
        out.append(("other", SEP2))
        out.append((
            "other",
            f"  SCENARIO END: {result.terminal.condition.value.upper()}",
        ))
        out.append(("other", f"  {result.terminal.note}"))
        out.append(("other", SEP2))

    if not any(cat != "other" for cat, _ in out):
        return []

    return out


def display_tick_result(result: "TickResult", dev_mode: bool = False) -> str:
    """Single markup string (no filtering) — used by the plain-text session log."""
    return "\n".join(line for _, line in display_tick_result_categorized(result, dev_mode))


def display_briefing(state: "SimulationState", dev_mode: bool = False) -> list[str]:
    lines = [SEP2, "  SCENARIO BRIEFING", f"  {state.universe.name}  ({state.universe.current_age.display()})", SEP2, ""]
    pan = state.pantheon
    lines.append(f"PANTHEON: {pan.name}")
    if pan.collective_constraints:
        lines.append("  Collective Constraints:")
        for c in pan.collective_constraints:
            lines.append(f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]")
            lines.append(f"      {c.description}")
    lines.append(SEP)
    lines.append("YOUR LIEGE LUMINARIES")
    for lid in [str(i) for i in state.demiurge.liege_luminary_ids]:
        lum = state.luminaries.get(lid)
        if not lum:
            continue
        lines.append("")
        lines.append(f"  {lum.name.upper()}  [{_personality_label(lum)}]")
        domain_parts = [
            f"{_short_tag(tag)} ({aff:.0%})"
            for tag, aff in sorted(lum.domains.items(), key=lambda x: -x[1])
        ]
        lines.append(f"  Domains: {', '.join(domain_parts)}")
        if lum.constraints:
            lines.append("  Constraints imposed on you:")
            for c in lum.constraints:
                lines.append(f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]")
                lines.append(f"      {c.description}")
        d   = lum.disposition
        att = state.luminary_attention.get(lid, 0.0)
        lines.append(
            f"  Starting disposition:  results{d.results:+.0%}  "
            f"methods{d.methods:+.0%}  attention:{att:.0%}"
        )
    lines += ["", SEP]
    rules   = state.universe.rules
    tol     = rules.footprint_tolerances
    pp      = rules.proxii_policy
    cap_str = f"max {pp.max_per_world} per world" if pp.max_per_world else "no per-world limit"
    lines += [
        "UNIVERSE RULES",
        "  Footprint Tolerances:",
        f"    Overt Miracles:   {tol.overt_miracles:.2f}  |  Subtle Influence: {tol.subtle_influence:.2f}",
        f"    Proxius Activity: {tol.proxius_activity:.2f}  |  Direct Creation:  {tol.direct_creation:.2f}",
        f"  Proxiī Policy: {cap_str}  (slack: {pp.tolerance_for_excess:.2f})",
        f"  Active shaping expected:    {'yes' if rules.active_shaping_expected else 'no'}",
        f"  Mortals perceive divinity:  {'yes' if rules.mortals_can_perceive_divinity else 'no'}",
    ]
    if rules.notes:
        lines.append(f"  Notes: {rules.notes}")
    if rules.special_flags:
        lines.append(f"  Special flags: {', '.join(rules.special_flags)}")
    lines.append(SEP)
    lines.append("YOUR UNIVERSE")
    for gid, galaxy in state.galaxies.items():
        g_oow = not is_in_window(galaxy)
        if g_oow and not dev_mode:
            continue
        gm = _OOW if g_oow else ""
        gal_vis = f"  [vis:{galaxy.visibility:.0%}]" if not galaxy.pinned else ""
        lines += ["", f"{gm}  Galaxy: {galaxy.name}{gal_vis}"]
        for sid in galaxy.child_ids:
            sys_obj  = state.locations.get(str(sid))
            if not sys_obj:
                continue
            s_oow = not is_in_window(sys_obj)
            if s_oow and not dev_mode:
                continue
            sm = _OOW if (g_oow or s_oow) else ""
            star_str = f"  [{sys_obj.star_type.value}]" if hasattr(sys_obj, "star_type") else ""
            sys_vis  = f"  [vis:{sys_obj.visibility:.0%}]" if not sys_obj.pinned else ""
            lines.append(f"{sm}    System: {sys_obj.name}{star_str}{sys_vis}")
            for wid in sys_obj.child_ids:
                world = state.worlds.get(str(wid))
                if not world:
                    continue
                w_oow = not is_in_window(world)
                if w_oow and not dev_mode:
                    continue
                wm = _OOW if (g_oow or s_oow or w_oow) else ""
                n_civs   = len(world.civilization_ids)
                life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
                w_vis    = f"  [vis:{world.visibility:.0%}]" if not world.pinned else ""
                lines.append(
                    f"{wm}      {world.name}  [{world.condition.value}]{w_vis}  age:{world.age:,.0f}  {life_str}"
                )
                if world.domain_expression:
                    lines.append(f"{wm}        domain expression: {_format_beliefs(world.domain_expression)}")
                if world.geo_tags or world.atmo_tags:
                    parts = []
                    if world.geo_tags:
                        parts.append(f"geo: {', '.join(world.geo_tags)}")
                    if world.atmo_tags:
                        parts.append(f"atmo: {', '.join(world.atmo_tags)}")
                    lines.append(f"{wm}        {' · '.join(parts)}")
                for cid in world.civilization_ids:
                    civ = state.civilizations.get(str(cid))
                    if not civ:
                        continue
                    c_oow = not is_in_window(civ)
                    if c_oow and not dev_mode:
                        continue
                    cm = _OOW if (wm or c_oow) else ""
                    h = civ.health
                    civ_vis = f"  [vis:{civ.visibility:.0%}]" if not civ.pinned else ""
                    lines.append(
                        f"{cm}        └─ {civ.name}  [{civ.scale.value}]{civ_vis}  "
                        f"stab:{h.stability:.0%} wealth:{h.prosperity:.0%} coh:{h.cohesion:.0%}"
                    )
                    if civ.dominant_beliefs:
                        lines.append(f"{cm}           beliefs: {_format_beliefs(civ.dominant_beliefs)}")
                    if civ.culture_tags:
                        lines.append(f"{cm}           culture: {_format_culture(civ.culture_tags)}")
                    for pid in civ.pop_ids:
                        pop = state.pops.get(str(pid))
                        if not pop:
                            continue
                        p_oow = not is_in_window(pop)
                        if p_oow and not dev_mode:
                            continue
                        pm = _OOW if (cm or p_oow) else ""
                        class_label = _pop_stratum_label(pop)
                        top_beliefs = sorted(pop.dominant_beliefs.items(), key=lambda x: -x[1])[:2]
                        belief_str = "  ".join(
                            f"{_short_tag(t)}({v:.0%})" for t, v in top_beliefs
                        ) or "none"
                        vis_note = f"  [vis:{pop.visibility:.0%}]" if not pop.pinned else ""
                        lines.append(
                            f"{pm}           ↳ {class_label} (sz {pop.size_magnitude})"
                            f"  {belief_str}{vis_note}"
                        )
    lines += ["", SEP]
    species_view = [
        (sid, sp, not is_in_window(sp))
        for sid, sp in state.species.items()
        if is_in_window(sp) or dev_mode
    ]
    if species_view:
        lines.append("SPECIES")
        for sid, sp, sp_oow in species_view:
            spm = _OOW if sp_oow else ""
            w_obj   = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin  = w_obj.name if w_obj else "unknown"
            sap_str = "sapient" if sp.sapient else "non-sapient"
            xp_str  = "  [transplanted]" if sp.transplanted else ""
            sp_vis  = f"  [vis:{sp.visibility:.0%}]" if not sp.pinned else ""
            lines.append(
                f"{spm}  {sp.name:16s} [{sap_str}]{sp_vis}  origin:{origin}  "
                f"lifespan:{sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}  [{sp.condition.value}]{xp_str}"
            )
            if sp.bio_tags or sp.domain_tags:
                lines.append(f"{spm}    {', '.join(sp.bio_tags + sp.domain_tags)}")
        lines.append(SEP)
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if mortal.status == MortalStatus.DECEASED:
            continue
        m_oow = not mortal.pinned and mortal.visibility <= ENTITY_VISIBILITY_FLOOR
        if m_oow and not dev_mode:
            continue
        mm = _OOW if m_oow else ""
        w_obj    = state.locations.get(str(mortal.current_location))
        c_obj    = state.civilizations.get(str(mortal.civilization_id)) if mortal.civilization_id else None
        loc      = w_obj.name if w_obj else "?"
        if c_obj:
            loc += f" · {c_obj.name}"
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str  = f"age:{mortal.chrono_age:,.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:,.0f})"
        sp_obj   = state.species.get(str(mortal.species_id)) if mortal.species_id else None
        sp_note  = f"  [{sp_obj.name}]" if sp_obj else ""
        prom_str = _prominence_label(mortal)
        vis_note = f"  vis:{mortal.visibility:.0%}" if not mortal.pinned else ""
        lines.append(
            f"{mm}  {mortal.name:16s} [{role_str:7s}]  align:{mortal.alignment:.2f}  "
            f"{age_str}{sp_note}{vis_note}   {loc}"
        )
        lines.append(f"{mm}    {prom_str}")
        if mortal.status_tags:
            lines.append(f"{mm}    Status: {', '.join(_short_tag(t) for t in mortal.status_tags)}")
        if mortal.personal_tags:
            lines.append(f"{mm}    Tags: {', '.join(_short_tag(t) for t in mortal.personal_tags)}")
        if mortal.culture_tags:
            lines.append(f"{mm}    Culture: {_format_culture(mortal.culture_tags)}")
    lines += ["", SEP2]
    return lines
