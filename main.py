#!/usr/bin/env python3
"""
main.py
Textual TUI for the Demiurge simulation.
Run with: python main.py
"""

from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import UUID

from rich.markup import escape as _e
from rich.text import Text
from textual import on, work
from textual.app import App, ComposeResult
from textual.message import Message
from textual.screen import Screen, ModalScreen
from textual.widget import Widget
from textual.widgets import (
    Button, Footer, Header, Label, ListItem, ListView,
    Input, RichLog, Static,
)
from textual.containers import Grid, Horizontal, Vertical, ScrollableContainer

from core.action_core import (
    ActionCategory, TargetType, ActionDefinition, ActionInstance, OngoingAction,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent, ExploreBeliefIntent,
    ChangeAffiliatedDomainsIntent,
    DomainVector, Framing,
)
from core.universe_core import MortalRole, MortalStatus, MortalProminence, SignificantLocation
from logic.tick_logic import (
    SimulationState, TickLoop, TickResult,
    is_mortal_visible, is_in_window, ALWAYS_VISIBLE_THRESHOLD, ENTITY_VISIBILITY_FLOOR,
)
from core.action_core import ScryScope, ScryIntent
from utilities.scenario_loader import load_scenario, validate_luminary_affinities
from utilities.scenario_exporter import export_scenario
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry, ImagoNode
from utilities.culture_registry import is_culture_tag

SEP  = "─" * 60
SEP2 = "═" * 60

BACK = "__back__"   # sentinel: dismiss with this to go one step back


# ─────────────────────────────────────────
# DISPLAY / FORMATTING HELPERS
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


def _format_beliefs(beliefs: "dict[str, float]") -> str:
    if not beliefs:
        return ""
    return "  ".join(
        f"{tag}({v:.2f})"
        for tag, v in sorted(beliefs.items(), key=lambda kv: -kv[1])
    )


def _format_culture(tags: "dict[str, float]") -> str:
    if not tags:
        return ""
    return ", ".join(
        t.split(":", 1)[-1]
        for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])
    )


def _prominence_label(mortal) -> str:
    if not mortal.prominence_roles or mortal.prominence_roles == [MortalProminence.NONE]:
        role_part = "no notable role"
    else:
        role_part = " · ".join(r.value.title() for r in mortal.prominence_roles)
    always = mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD
    tier = "always visible" if always else f"prominence:{mortal.prominence:.2f}"
    return f"{role_part}  [{tier}]"


def _name_for_id(uid: "UUID", state: "SimulationState") -> str:
    sid = str(uid)
    for d in [state.mortals, state.civilizations, state.locations, state.luminaries]:
        if sid in d:
            return getattr(d[sid], "name", sid[:8])
    return sid[:8]


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


def display_state(state: "SimulationState") -> str:
    lines = [
        SEP2,
        f"  UNIVERSE: {state.universe.name}",
        f"  Age: {state.universe.current_age:.1f}  |  Tick: {state.tick_number}",
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
        SEP,
    ]
    lines.append("LUMINARIES")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        lines.append(
            f"  {lum.name:12s}  results:{d.results:+.2f}  methods:{d.methods:+.2f}  "
            f"attention:{att:.2f}  [{_personality_label(lum)}]"
        )
    lines.append(SEP)
    lines.append("WORLDS")
    for wid, world in state.worlds.items():
        if not is_in_window(world):
            continue
        domain_str = _format_beliefs(world.domain_expression) or "none"
        vis_note = f"  [vis:{world.visibility:.2f}]" if not world.pinned else ""
        lines.append(f"  {world.name}  [{world.condition.value}]{vis_note}  domain: {domain_str}")
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if civ and is_in_window(civ):
                h = civ.health
                civ_vis = f"  [vis:{civ.visibility:.2f}]" if not civ.pinned else ""
                lines.append(
                    f"    └─ {civ.name} [{civ.scale.value}]{civ_vis}  "
                    f"stab:{h.stability:.2f} pros:{h.prosperity:.2f} coh:{h.cohesion:.2f}"
                )
                lines.append(f"       beliefs: {_format_beliefs(civ.dominant_beliefs) or 'none'}")
    lines.append(SEP)
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if not is_mortal_visible(mortal):
            continue
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str  = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD or mortal.pinned == False else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str}]  align:{mortal.alignment:.2f}  "
            f"{age_str}{vis_note}  {prom_str}"
        )
    lines.append(SEP)
    lines.append("ONGOING ACTIONS")
    if state.ongoing_actions:
        for cat_val, oa in state.ongoing_actions.items():
            cat_label  = cat_val.replace("_", " ").title()
            target_str = f" → {_name_for_id(oa.target_id, state)}" if oa.target_id else ""
            lines.append(
                f"  [{cat_label}] {oa.action_key.replace('_', ' ').title()}"
                f"{target_str}  ({oa.executed_ticks}/{oa.ticks_active} ticks executed)"
            )
    else:
        lines.append("  None")
    lines.append(SEP2)
    return "\n".join(lines)


def display_tick_result(result: "TickResult") -> str:
    lines = [
        "",
        f"  TICK {result.tick_number} RESULT  "
        f"(age {result.universe_age_before:.1f} → {result.universe_age_after:.1f})",
        SEP,
    ]
    if result.passive_result.narrative_events:
        lines.append("WORLD EVENTS")
        for ev in result.passive_result.narrative_events:
            lines.append(f"  • {ev}")
        lines.append("")
    if result.action_result.entries:
        lines.append("YOUR ACTIONS")
        for entry in result.action_result.entries:
            lines.append(f"  [{entry.outcome.value.upper()}] {entry.narrative}")
        lines.append("")
    if result.essence_claimed_by_domain:
        total = sum(result.essence_claimed_by_domain.values())
        parts = "  ".join(
            f"{tag.split(':')[1]}:{amt:.3f}"
            for tag, amt in sorted(result.essence_claimed_by_domain.items(), key=lambda x: -x[1])
        )
        lines.append(f"ESSENCE CLAIMED  (+{total:.3f} total)")
        lines.append(f"  {parts}")
        lines.append("")
    if result.disposition_changes:
        lines.append("LUMINARY REACTIONS")
        for lid, (r, m) in result.disposition_changes.items():
            ev   = next((e for e in result.evaluations if str(e.luminary_id) == lid), None)
            name = ev.summary_note.split(":")[0] if ev else lid[:8]
            lines.append(f"  {name:12s}  results→{r:+.2f}  methods→{m:+.2f}")
        lines.append("")
    if result.dialogue_triggers:
        lines.append("DIVINE COMMUNICATIONS")
        for trig in result.dialogue_triggers:
            lines.append(
                f"  [{trig.trigger_type.value.upper()}]  urgency:{trig.urgency:.1f}  "
                f"re: {trig.subject_ref or 'general'}"
            )
        lines.append("")
    if result.terminal.triggered:
        lines += [
            SEP2,
            f"  SCENARIO END: {result.terminal.condition.value.upper()}",
            f"  {result.terminal.note}",
            SEP2,
        ]
    return "\n".join(lines)


def display_briefing(state: "SimulationState") -> str:
    lines = [SEP2, "  SCENARIO BRIEFING", f"  {state.universe.name}  (Age {state.universe.current_age:.1f})", SEP2, ""]
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
        domain_names = [
            state.domains[str(did)].name
            for did in lum.domains if str(did) in state.domains
        ]
        lines.append(f"  Domains: {', '.join(domain_names)}")
        for did in lum.domains:
            d = state.domains.get(str(did))
            if d:
                lines.append(f"    • {d.name}: {d.description}")
                if d.tags:
                    lines.append(f"      Tags: {', '.join(d.tags)}")
        if lum.constraints:
            lines.append("  Constraints imposed on you:")
            for c in lum.constraints:
                lines.append(f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]")
                lines.append(f"      {c.description}")
        d   = lum.disposition
        att = state.luminary_attention.get(lid, 0.0)
        lines.append(
            f"  Starting disposition:  results{d.results:+.2f}  "
            f"methods{d.methods:+.2f}  attention:{att:.2f}"
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
        f"  Proxii Policy: {cap_str}  (slack: {pp.tolerance_for_excess:.2f})",
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
        if not is_in_window(galaxy):
            continue
        gal_vis = f"  [vis:{galaxy.visibility:.2f}]" if not galaxy.pinned else ""
        lines += ["", f"  Galaxy: {galaxy.name}{gal_vis}"]
        for sid in galaxy.child_ids:
            sys_obj  = state.locations.get(str(sid))
            if not sys_obj or not is_in_window(sys_obj):
                continue
            star_str = f"  [{sys_obj.star_type.value}]" if hasattr(sys_obj, "star_type") else ""
            sys_vis  = f"  [vis:{sys_obj.visibility:.2f}]" if not sys_obj.pinned else ""
            lines.append(f"    System: {sys_obj.name}{star_str}{sys_vis}")
            for wid in sys_obj.child_ids:
                world = state.worlds.get(str(wid))
                if not world or not is_in_window(world):
                    continue
                n_civs   = len(world.civilization_ids)
                life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
                w_vis    = f"  [vis:{world.visibility:.2f}]" if not world.pinned else ""
                lines.append(
                    f"      {world.name}  [{world.condition.value}]{w_vis}  age:{world.age:.0f}  {life_str}"
                )
                if world.domain_expression:
                    lines.append(f"        domain expression: {_format_beliefs(world.domain_expression)}")
                if world.geo_tags or world.atmo_tags:
                    parts = []
                    if world.geo_tags:
                        parts.append(f"geo: {', '.join(world.geo_tags)}")
                    if world.atmo_tags:
                        parts.append(f"atmo: {', '.join(world.atmo_tags)}")
                    lines.append(f"        {' · '.join(parts)}")
                for cid in world.civilization_ids:
                    civ = state.civilizations.get(str(cid))
                    if civ and is_in_window(civ):
                        h = civ.health
                        civ_vis = f"  [vis:{civ.visibility:.2f}]" if not civ.pinned else ""
                        lines.append(
                            f"        └─ {civ.name}  [{civ.scale.value}]{civ_vis}  "
                            f"stab:{h.stability:.2f} pros:{h.prosperity:.2f} coh:{h.cohesion:.2f}"
                        )
                        if civ.dominant_beliefs:
                            lines.append(f"           beliefs: {_format_beliefs(civ.dominant_beliefs)}")
                        if civ.culture_tags:
                            lines.append(f"           culture: {_format_culture(civ.culture_tags)}")
    lines += ["", SEP]
    visible_species = [(sid, sp) for sid, sp in state.species.items() if is_in_window(sp)]
    if visible_species:
        lines.append("SPECIES")
        for sid, sp in visible_species:
            w_obj   = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin  = w_obj.name if w_obj else "unknown"
            sap_str = "sapient" if sp.sapient else "non-sapient"
            xp_str  = "  [transplanted]" if sp.transplanted else ""
            sp_vis  = f"  [vis:{sp.visibility:.2f}]" if not sp.pinned else ""
            lines.append(
                f"  {sp.name:16s} [{sap_str}]{sp_vis}  origin:{origin}  "
                f"lifespan:{sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}  [{sp.condition.value}]{xp_str}"
            )
            if sp.bio_tags or sp.domain_tags:
                lines.append(f"    {', '.join(sp.bio_tags + sp.domain_tags)}")
        lines.append(SEP)
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if not is_mortal_visible(mortal):
            continue
        w_obj    = state.locations.get(str(mortal.current_location))
        c_obj    = state.civilizations.get(str(mortal.civilization_id)) if mortal.civilization_id else None
        loc      = w_obj.name if w_obj else "?"
        if c_obj:
            loc += f" · {c_obj.name}"
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str  = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        sp_obj   = state.species.get(str(mortal.species_id)) if mortal.species_id else None
        sp_note  = f"  [{sp_obj.name}]" if sp_obj else ""
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str:7s}]  align:{mortal.alignment:.2f}  "
            f"{age_str}{sp_note}{vis_note}   {loc}"
        )
        lines.append(f"    {prom_str}")
        if mortal.personal_tags:
            lines.append(f"    Tags: {', '.join(mortal.personal_tags)}")
        if mortal.culture_tags:
            lines.append(f"    Culture: {_format_culture(mortal.culture_tags)}")
    lines += ["", SEP2]
    return "\n".join(lines)


# ─────────────────────────────────────────
# SESSION LOG
# ─────────────────────────────────────────

class SessionLog:
    def __init__(self, path: Path):
        self.path = path
        self.path.write_text(
            f"DEMIURGE SESSION LOG\nStarted: {datetime.now().isoformat()}\n{'='*60}\n\n",
            encoding="utf-8",
        )

    def write(self, text: str) -> None:
        with self.path.open("a", encoding="utf-8") as f:
            f.write(text + "\n")

    def write_tick(self, result: "TickResult") -> None:
        self.write(display_tick_result(result))

    def write_action(self, summary: str) -> None:
        self.write(f"  > QUEUED: {summary}")

    def finalize(self, state: "SimulationState", result: "TickResult | None") -> None:
        self.write("\n" + "=" * 60)
        self.write("SESSION END")
        self.write(f"Final age: {state.universe.current_age:.1f}")
        self.write(f"Final tick: {state.tick_number}")
        if result and result.terminal.triggered:
            self.write(f"Outcome: {result.terminal.condition.value}")
        self.write(f"Ended: {datetime.now().isoformat()}")

_SAVES_DIR    = Path(__file__).parent / "saves"
_SCENARIOS_DIR = Path(__file__).parent / "scenarios"
_LOGS_DIR     = Path(__file__).parent / "logs"

_STUB_ACTIONS: frozenset[str] = frozenset({
    "read_divine_traces",
    "negotiate_herald",
    "obstruct_herald",
    "petition_luminary_herald",
    "investigate_underreal",
})

# Canonical 4×4 grid order for the domain picker (row-major).
_DOMAIN_GRID_ORDER: list[str] = [
    "domain:truth",    "domain:light",    "domain:void",      "domain:change",
    "domain:order",    "domain:fire",     "domain:decay",     "domain:conflict",
    "domain:memory",   "domain:growth",   "domain:community", "domain:silence",
    "domain:mastery",  "domain:water",    "domain:sacrifice", "domain:secrecy",
]


# ─────────────────────────────────────────
# CSS  (dark mode)
# ─────────────────────────────────────────

_CSS = """
$bg:        #0c0c1e;
$bg-panel:  #0f1028;
$bg-feed:   #080812;
$bg-modal:  #101026;
$border:    #1e2d50;
$text:      #c0ccdc;
$muted:     #5a7090;
$accent:    #4a80b0;
$good:      #50b870;
$warn:      #b8902a;
$danger:    #b04050;
$highlight: #1a2a50;

Screen {
    background: $bg;
    color: $text;
}

Header {
    background: #0a0a1e;
    color: $muted;
    height: 1;
}

Footer {
    background: #0a0a1e;
    color: $muted;
}

/* ── Layout ─────────────────────────── */

#status-panel {
    width: 36;
    background: $bg-panel;
    border-right: solid $border;
    padding: 0 1 1 1;
    overflow-y: auto;
}

#main-feed {
    background: $bg-feed;
}

/* ── Buttons ─────────────────────────── */

Button {
    background: $highlight;
    color: $accent;
    border: none;
    margin: 0 1;
}

Button:focus {
    background: #24407a;
    color: #c0d8f0;
    border: none;
}

Button:hover {
    background: #24407a;
    color: #c0d8f0;
}

Button.-primary {
    background: #14382a;
    color: $good;
}

Button.-primary:hover {
    background: #1e5040;
    color: #70d890;
}

Button.-danger {
    background: #38101e;
    color: $danger;
}

Button.-danger:hover {
    background: #501828;
    color: #d07080;
}

/* ── Lists ─────────────────────────────── */

ListView {
    background: $bg-panel;
    border: solid $border;
}

ListItem {
    color: $text;
    padding: 0 1;
}

ListItem.--highlight {
    background: $highlight;
    color: #e0eaf8;
}

ListItem > Label {
    color: $text;
    padding: 0 0;
}

/* ── Inputs ──────────────────────────── */

Input {
    background: #07071a;
    color: #e0e8f8;
    border: solid $border;
}

Input:focus {
    border: solid #3a5a9a;
}

/* ── Labels ──────────────────────────── */

Label {
    color: $muted;
}

.field-label {
    color: $muted;
    padding: 1 0 0 0;
}

/* ── Modals ──────────────────────────── */

ModalScreen {
    align: center middle;
    background: rgba(0,0,0,0.6);
}

.modal-box {
    background: $bg-modal;
    border: solid $border;
    width: 74;
    height: auto;
    max-height: 90%;
    padding: 1 2;
}

.modal-box-tall {
    background: $bg-modal;
    border: solid $border;
    width: 74;
    height: 80%;
    padding: 1 2;
}

.modal-title {
    color: $accent;
    text-style: bold;
    padding: 0 0 1 0;
}

.modal-desc {
    color: $muted;
    padding: 0 0 1 0;
}

.btn-row {
    height: 3;
    align: right middle;
    padding: 1 0 0 0;
}

/* ── Domain Picker ───────────────────── */

#domain-grid {
    grid-size: 4;
    height: auto;
    margin: 1 0;
}

DomainSquare {
    border: round $border;
    height: 4;
    content-align: center middle;
    text-align: center;
    padding: 0 1;
    color: $text;
}

DomainSquare:focus {
    border: round $accent;
}

DomainSquare.affiliated {
    border: round $good;
    color: $good;
}

DomainSquare.affiliated:focus {
    border: round #70d890;
}

DomainSquare.inactive {
    border: round $muted;
    color: $muted;
}

#lum-panel {
    height: 3;
    background: $bg-panel;
    border: solid $border;
    padding: 0 1;
    margin: 0 0 1 0;
    content-align: left middle;
}

/* ── Imago Tree Picker ───────────────── */

#imago-grid {
    grid-size: 3;
    height: auto;
    margin: 1 0;
}

ImagoCell {
    border: round $border;
    height: 4;
    content-align: center middle;
    text-align: center;
    padding: 0 1;
    color: $text;
}

ImagoCell:focus {
    border: round $accent;
}

ImagoCell.good {
    border: round $good;
    color: $good;
}

ImagoCell.good:focus {
    border: round #70d890;
}

ImagoCell.danger {
    border: round $danger;
    color: $danger;
}

ImagoCell.danger:focus {
    border: round #d07080;
}

ImagoCell.inactive {
    border: round #2e3d58;
    color: #4a5a72;
}

ImagoCell.inactive:focus {
    border: round #3a4e70;
}

.imago-spacer {
    height: 4;
}

#imago-tooltip {
    height: 5;
    background: $bg-panel;
    border: solid $border;
    padding: 0 1;
    margin: 0 0 1 0;
    content-align: left middle;
}

/* ── LoadScreen ───────────────────────── */

LoadScreen {
    align: center middle;
}

.load-box {
    background: $bg-panel;
    border: solid $border;
    width: 68;
    height: 70%;
    padding: 1 2;
}

.load-title {
    color: $accent;
    text-style: bold;
    text-align: center;
    padding: 1 0;
}

.load-section {
    color: $muted;
    text-style: bold;
    padding: 1 0 0 0;
}
"""


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────

def _peek_db_meta(path: Path) -> dict:
    try:
        with sqlite3.connect(path) as c:
            row = c.execute(
                "SELECT name, description, tick_number FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return {
                "name":        row[0] or path.stem,
                "description": row[1] or "",
                "tick_number": row[2] if row[2] is not None else 0,
            }
    except Exception:
        pass
    return {"name": path.stem, "description": "", "tick_number": 0}


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


def _render_status(state: SimulationState) -> Text:
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


# ─────────────────────────────────────────
# LOOPING LIST VIEW
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
# LOAD SCREEN
# ─────────────────────────────────────────

class LoadScreen(Screen):
    """Startup screen: lists saves and scenarios."""

    BINDINGS = [("q", "quit_app", "Quit")]

    def compose(self) -> ComposeResult:
        saves     = sorted(_SAVES_DIR.glob("*.db"))     if _SAVES_DIR.exists()     else []
        scenarios = sorted(_SCENARIOS_DIR.glob("*.db")) if _SCENARIOS_DIR.exists() else []

        with Vertical(classes="load-box"):
            yield Label("DEMIURGE", classes="load-title")
            with ScrollableContainer():
                with LoopingListView(id="load-list"):
                    if saves:
                        yield ListItem(Label("── SAVES ──", classes="load-section"), disabled=True)
                        for path in saves:
                            meta = _peek_db_meta(path)
                            # description already includes tick number ("Tick N  |  Age X")
                            desc_wrapped = _wrap_desc(meta["description"])
                            label_text   = f"{meta['name']}\n{desc_wrapped}" if desc_wrapped else meta["name"]
                            yield ListItem(
                                Label(label_text),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if scenarios:
                        yield ListItem(Label("── SCENARIOS ──", classes="load-section"), disabled=True)
                        for path in scenarios:
                            meta = _peek_db_meta(path)
                            desc_wrapped = _wrap_desc(meta["description"])
                            label_text   = f"{meta['name']}\n{desc_wrapped}" if desc_wrapped else meta["name"]
                            yield ListItem(
                                Label(label_text),
                                id=f"file-{path.stem}",
                                name=str(path),
                            )
                    if not saves and not scenarios:
                        yield ListItem(Label("(no saves or scenarios found)"), disabled=True)

    def on_mount(self) -> None:
        self.query_one("#load-list", ListView).focus()

    @on(ListView.Selected)
    def _on_selected(self, event: ListView.Selected) -> None:
        path_str = event.item.name
        if not path_str:
            return
        path = Path(path_str)
        state = load_scenario(path)
        violations = validate_luminary_affinities(state)
        if violations:
            msg = "Scenario rejected — Luminary affinity constraints violated:\n\n"
            msg += "\n".join(f"  • {v}" for v in violations)
            self.app.push_screen(ErrorModal(msg))
            return
        self.app.push_screen(GameScreen(state))

    def action_quit_app(self) -> None:
        self.app.exit()


# ─────────────────────────────────────────
# ERROR MODAL
# Displays a blocking error message; dismissed with Enter or Escape.
# ─────────────────────────────────────────

class ErrorModal(ModalScreen):
    BINDINGS = [("escape", "dismiss", "OK"), ("enter", "dismiss", "OK")]

    def __init__(self, message: str) -> None:
        super().__init__()
        self._message = message

    def compose(self) -> ComposeResult:
        with Vertical(classes="picker-box"):
            yield Label("ERROR", classes="picker-title")
            yield Label(self._message)
            yield Button("OK", variant="error", id="ok-btn")

    @on(Button.Pressed, "#ok-btn")
    def _ok(self) -> None:
        self.dismiss()


# ─────────────────────────────────────────
# PICKER MODAL
# Generic: pick one item from a list.
# Dismisses with the selected key (str) or None.
# ─────────────────────────────────────────

class PickerModal(ModalScreen):
    BINDINGS = [
        ("escape",     "go_back",       "Back"),
        ("ctrl+escape","force_cancel",  "Cancel"),
    ]

    def __init__(
        self,
        title: str,
        items: list[tuple[str, str]],  # (key, display_text)
        description: str = "",
        show_back: bool = False,
    ):
        super().__init__()
        self._title       = title
        self._items       = items
        self._description = description
        self._show_back   = show_back

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(_wrap_desc(self._description), classes="modal-desc")
            with ScrollableContainer():
                with LoopingListView(id="picker-list"):
                    for i, (key, text) in enumerate(self._items):
                        yield ListItem(Label(text), id=f"pick-{i}")
            with Horizontal(classes="btn-row"):
                if self._show_back:
                    yield Button("← Back",  id="back-btn")
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#picker-list", ListView).focus()

    @on(ListView.Selected, "#picker-list")
    def _on_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        self.dismiss(self._items[idx][0])

    @on(Button.Pressed, "#back-btn")
    def _on_back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _on_cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_go_back(self) -> None:
        self.dismiss(BACK if self._show_back else None)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# YES / NO MODAL
# ─────────────────────────────────────────

class YesNoModal(ModalScreen):
    BINDINGS = [("escape", "no", "No")]

    def __init__(self, question: str, detail: str = ""):
        super().__init__()
        self._question = question
        self._detail   = detail

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._question, classes="modal-title")
            if self._detail:
                yield Label(self._detail, classes="modal-desc")
            with Horizontal(classes="btn-row"):
                yield Button("Yes", id="yes-btn", classes="-primary")
                yield Button("No",  id="no-btn",  classes="-danger")

    @on(Button.Pressed, "#yes-btn")
    def _yes(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#no-btn")
    def _no(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    def action_no(self) -> None:
        self.dismiss(False)


# ─────────────────────────────────────────
# TEXT FORM MODAL
# fields: list of (label, field_id, default)
# Dismisses with dict[str, str] or None.
# ─────────────────────────────────────────

class TextFormModal(ModalScreen):
    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("ctrl+enter",  "confirm",      "Confirm"),
    ]

    def __init__(
        self,
        title: str,
        fields: list[tuple[str, str, str]],  # (label, id, default)
        description: str = "",
        show_back: bool = False,
    ):
        super().__init__()
        self._title       = title
        self._fields      = fields
        self._description = description
        self._show_back   = show_back

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(self._title, classes="modal-title")
            if self._description:
                yield Label(_wrap_desc(self._description), classes="modal-desc")
            for label, fid, default in self._fields:
                yield Label(label, classes="field-label")
                yield Input(value=default, id=f"field-{fid}")
            with Horizontal(classes="btn-row"):
                if self._show_back:
                    yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn", classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.action_confirm()

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_confirm(self) -> None:
        result = {}
        for _label, fid, _default in self._fields:
            widget = self.query_one(f"#field-{fid}", Input)
            result[fid] = widget.value
        self.dismiss(result)

    def action_go_back(self) -> None:
        self.dismiss(BACK if self._show_back else None)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# DOMAIN PICKER MODAL
# A 4×4 grid of domain squares with color-coded approval borders
# and a per-Luminary focus panel.
# Dismisses with a domain tag (str), "" for skip, or None to cancel.
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

    def __init__(self, tag: str, icon: str, name: str, affiliated: bool, accessible: bool) -> None:
        classes = []
        if affiliated and accessible:
            classes.append("affiliated")
        if not accessible:
            classes.append("inactive")
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


class DomainPickerModal(ModalScreen):
    """4×4 domain grid picker with affiliated domain coloring."""

    BINDINGS = [
        ("escape",      "go_back",      "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("up",          "nav('up')",    ""),
        ("down",        "nav('down')",  ""),
        ("left",        "nav('left')",  ""),
        ("right",       "nav('right')", ""),
    ]

    def __init__(
        self,
        state: SimulationState,
        explore_mode: bool = False,
        exclude_tags: set | None = None,
    ) -> None:
        super().__init__()
        self._state        = state
        self._explore_mode = explore_mode

        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)

        accessible_set = set(dreg.all_tags)
        if explore_mode:
            accessible_set -= set(state.demiurge.unlocked_domain_tags)
        if exclude_tags:
            accessible_set -= exclude_tags

        self._dreg           = dreg
        self._lum_info       = lum_info
        self._fellow_tags    = fellow_tags
        self._accessible_set = accessible_set
        self._affiliated_set = set(state.demiurge.affiliated_domains)

    def compose(self) -> ComposeResult:
        title = "Explore Domain" if self._explore_mode else "Choose Domain"
        with Vertical(classes="modal-box"):
            yield Label(title, classes="modal-title")
            with Grid(id="domain-grid"):
                for tag in _DOMAIN_GRID_ORDER:
                    accessible = tag in self._accessible_set
                    affiliated = tag in self._affiliated_set
                    _dname = tag.split(":", 1)[1].title()
                    if len(_dname) % 2 == 0:
                        _dname = " " + _dname
                    yield DomainSquare(
                        tag=tag,
                        icon=self._dreg.icon(tag),
                        name=_dname,
                        affiliated=affiliated,
                        accessible=accessible,
                    )
            yield Static("", id="lum-panel")
            with Horizontal(classes="btn-row"):
                yield Button("Skip Domain", id="skip-btn")
                yield Button("← Back",      id="back-btn")
                yield Button("Cancel",      id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        for sq in self.query(DomainSquare):
            if not sq.disabled:
                sq.focus()
                break

    def action_nav(self, direction: str) -> None:
        squares = list(self.query(DomainSquare))
        focused_idx = next((i for i, sq in enumerate(squares) if sq.has_focus), -1)
        if focused_idx == -1:
            self.on_mount()
            return
        row, col = divmod(focused_idx, 4)
        dr, dc = {"up": (-1, 0), "down": (1, 0), "left": (0, -1), "right": (0, 1)}[direction]
        r, c = row + dr, col + dc
        while 0 <= r < 4 and 0 <= c < 4:
            candidate = squares[r * 4 + c]
            if not candidate.disabled:
                candidate.focus()
                return
            r, c = r + dr, c + dc

    def on_domain_square_focused(self, event: DomainSquare.Focused) -> None:
        tag   = event.tag
        parts = []
        for lum, lum_tags in self._lum_info:
            if lum_tags:
                lid = str(lum.id)
                v   = self._dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=self._fellow_tags[lid],
                    personality=self._dreg.compute_personality(lum.domains),
                )
                col = "#50b870" if v > 0.15 else ("#b04050" if v < -0.15 else "#5a7090")
                parts.append(f"[{col}]{_e(lum.name[:10])}: {v:+.2f}[/]")
        self.query_one("#lum-panel", Static).update("  ".join(parts))

    def on_domain_square_selected(self, event: DomainSquare.Selected) -> None:
        self.dismiss(event.tag)

    @on(Button.Pressed, "#skip-btn")
    def _skip(self, _: Button.Pressed) -> None:
        self.dismiss("")

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


# ─────────────────────────────────────────
# IMAGO TREE PICKER
# Shows all 7 nodes of one tree in a 3-column pyramid layout.
# Dismisses with a node_id (str), "__manual__" to skip to manual
# direction, or None to cancel.
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

    def __init__(self, node: ImagoNode, unlocked: bool, approval_class: str) -> None:
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


class ImagoTreeModal(ModalScreen):
    """
    Tree-layout Imago picker. Grid is 3 columns × 4 rows (T4 top, T1 bottom).
    T4 is centred; each other tier puts its lower-sort node in col 0, higher in col 2.
    Dismisses with a node_id, '__manual__', or None.
    """

    BINDINGS = [
        ("escape",      "cancel",       "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
        ("up",          "nav('up')",    ""),
        ("down",        "nav('down')",  ""),
        ("left",        "nav('left')",  ""),
        ("right",       "nav('right')", ""),
    ]

    # Cell positions in DOM order → (grid_row, grid_col)
    # Row 0=T4, 1=T3, 2=T2, 3=T1 ; Col 0=left, 1=center, 2=right
    _POSITIONS = [(0, 1), (1, 0), (1, 2), (2, 0), (2, 2), (3, 0), (3, 2)]

    def __init__(self, state: SimulationState, tree: str) -> None:
        super().__init__()
        self._state = state
        self._tree  = tree

        ireg         = get_imago_registry()
        unlocked_set = set(state.demiurge.unlocked_imagines)
        nodes        = ireg.nodes_for_tree(tree)  # sorted by (tier, sort_order)

        by_tier: dict[int, list[ImagoNode]] = {1: [], 2: [], 3: [], 4: []}
        for n in nodes:
            by_tier[n.tier].append(n)

        self._by_tier    = by_tier
        self._unlocked   = unlocked_set
        dreg             = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(state)
        self._dreg        = dreg
        self._lum_info    = lum_info
        self._fellow_tags = fellow_tags

    def _imago_score(self, node: ImagoNode) -> float:
        """Weighted sum of (luminary_approval × mechanic_direction) across all Luminaries."""
        total, count = 0.0, 0
        for lum, lum_tags in self._lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                self._dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=self._fellow_tags[lid],
                    personality=self._dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            total += score
            count += 1
        return total / count if count else 0.0

    def _approval_class(self, node: ImagoNode) -> str:
        s = self._imago_score(node)
        if s > 0.15:
            return "good"
        if s < -0.15:
            return "danger"
        return ""

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box"):
            yield Label(f"{self._tree.title()} — Imagines", classes="modal-title")
            with Grid(id="imago-grid"):
                for tier in (4, 3, 2, 1):
                    nodes = self._by_tier[tier]
                    if tier == 4:
                        yield Static("", classes="imago-spacer")
                        node     = nodes[0]
                        unlocked = node.node_id in self._unlocked
                        yield ImagoCell(node, unlocked, self._approval_class(node) if unlocked else "")
                        yield Static("", classes="imago-spacer")
                    else:
                        left, right = nodes[0], nodes[1]
                        for node in (left, right):
                            unlocked = node.node_id in self._unlocked
                            cell = ImagoCell(node, unlocked, self._approval_class(node) if unlocked else "")
                            if node is left:
                                yield cell
                                yield Static("", classes="imago-spacer")
                            else:
                                yield cell
            yield Static("", id="imago-tooltip")
            with Horizontal(classes="btn-row"):
                yield Button("No Imago",  id="manual-btn")
                yield Button("← Domain",  id="back-btn")
                yield Button("Cancel",    id="cancel-btn",  classes="-danger")

    def on_mount(self) -> None:
        cells = list(self.query(ImagoCell))
        target = next((c for c in cells if c._unlocked), cells[0] if cells else None)
        if target:
            target.focus()

    def action_nav(self, direction: str) -> None:
        cells   = list(self.query(ImagoCell))
        pos_map = {p: i for i, p in enumerate(self._POSITIONS)}
        focused = next((i for i, c in enumerate(cells) if c.has_focus), -1)
        if focused == -1:
            self.on_mount()
            return
        row, col = self._POSITIONS[focused]
        new_pos  = None
        if direction == "up" and row > 0:
            new_pos = (row - 1, 1 if row - 1 == 0 else col)
        elif direction == "down" and row < 3:
            new_pos = (row + 1, 0 if col == 1 else col)
        elif direction == "left" and col == 2:
            new_pos = (row, 0)
        elif direction == "right" and col == 0:
            new_pos = (row, 2)
        if new_pos and new_pos in pos_map:
            cells[pos_map[new_pos]].focus()

    def on_imago_cell_focused(self, event: ImagoCell.Focused) -> None:
        ireg = get_imago_registry()
        node = ireg.get_node(event.node_id)
        tip  = (node.tooltip_blurb or f"Tier {node.tier} apex — cannot be drawn from the Underreal.") if node else ""
        self.query_one("#imago-tooltip", Static).update(tip)

    def on_imago_cell_selected(self, event: ImagoCell.Selected) -> None:
        self.dismiss(event.node_id)

    @on(Button.Pressed, "#manual-btn")
    def _manual(self, _: Button.Pressed) -> None:
        self.dismiss("__manual__")

    @on(Button.Pressed, "#back-btn")
    def _back_btn(self, _: Button.Pressed) -> None:
        self.dismiss(BACK)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(BACK)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


class ImagoDetailModal(ModalScreen):
    """
    Confirmation screen for a chosen Imago node.
    Shows full description, domain/culture effects, and per-Luminary affinity scores.
    Dismisses with True (confirm), False (back one step), or None (cancel entirely).
    """

    BINDINGS = [
        ("escape",      "back",         "Back"),
        ("ctrl+escape", "force_cancel", "Cancel"),
    ]

    def __init__(self, node: ImagoNode, state: SimulationState) -> None:
        super().__init__()
        self._node  = node
        self._state = state

    def _body(self) -> Text:
        node = self._node
        dreg = get_domain_registry()
        lum_info, fellow_tags, _ = _get_lum_domain_context(self._state)

        lines: list[str] = []
        lines.append(f"[bold #c0ccdc]{_e(node.name)}[/]")
        lines.append(f"[#3a5a7a]Tier {node.tier}  ·  {node.tree.title()} tree[/]")
        lines.append("")
        lines.append(f"[#9090a8]{_e(node.description)}[/]")
        lines.append("")

        domain_fx  = [(t, v) for t, v in node.mechanics.items() if t.startswith("domain:")]
        culture_fx = [(t, v) for t, v in node.mechanics.items() if is_culture_tag(t)]

        if domain_fx:
            lines.append("[bold #5a7090]DOMAIN EFFECTS[/]")
            for tag, v in sorted(domain_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        if culture_fx:
            lines.append("[bold #5a7090]CULTURE EFFECTS[/]")
            for tag, v in sorted(culture_fx, key=lambda x: -abs(x[1])):
                short = tag.split(":", 1)[1]
                col   = "#50b870" if v > 0 else "#b04050"
                lines.append(f"  [{col}]{short:<16}  {v:+.2f}[/]")
            lines.append("")

        lines.append("[bold #5a7090]LUMINARY AFFINITIES[/]")
        for lum, lum_tags in lum_info:
            if not lum_tags:
                continue
            lid   = str(lum.id)
            score = sum(
                dreg.luminary_approval(
                    tag, lum_tags,
                    fellow_lum_tags=fellow_tags[lid],
                    personality=dreg.compute_personality(lum.domains),
                ) * direction
                for tag, direction in node.mechanics.items()
                if tag.startswith("domain:")
            )
            col = "#50b870" if score > 0.1 else ("#b04050" if score < -0.1 else "#5a7090")
            lines.append(f"  [{col}]{_e(lum.name):<16}  {score:+.2f}[/]")

        return Text.from_markup("\n".join(lines))

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Imago — Confirm", classes="modal-title")
            with ScrollableContainer():
                yield Static(self._body(), id="imago-detail-body")
            with Horizontal(classes="btn-row"):
                yield Button("← Back",  id="back-btn")
                yield Button("Cancel",  id="cancel-btn",  classes="-danger")
                yield Button("Confirm", id="confirm-btn", classes="-primary")

    def on_mount(self) -> None:
        self.query_one("#confirm-btn", Button).focus()

    @on(Button.Pressed, "#confirm-btn")
    def _confirm(self, _: Button.Pressed) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#back-btn")
    def _back(self, _: Button.Pressed) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#cancel-btn")
    def _cancel_btn(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_back(self) -> None:
        self.dismiss(False)

    def action_force_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# ACTION BROWSER MODAL
# Two-level: category → action.
# Dismisses with (action_key, ActionDefinition) or None.
# ─────────────────────────────────────────

class ActionBrowserModal(ModalScreen):
    BINDINGS = [
        ("escape",      "cancel",       "Cancel"),
        ("ctrl+escape", "cancel",       ""),
    ]

    def __init__(self, state: SimulationState, library: dict):
        super().__init__()
        self._state   = state
        self._library = library

        # Group by category
        self._cat_actions: dict[ActionCategory, list[tuple[str, ActionDefinition]]] = {}
        for key, defn in library.items():
            self._cat_actions.setdefault(defn.category, []).append((key, defn))

        # Currently-queued categories
        key_by_id = {str(v.id): k for k, v in library.items()}
        self._queued_cats: dict[str, str] = {}
        for ai in state.action_queue:
            k = key_by_id.get(str(ai.action_definition_id))
            if k and k in library:
                d = library[k]
                self._queued_cats[d.category.value] = d.name

    def compose(self) -> ComposeResult:
        with Vertical(classes="modal-box-tall"):
            yield Label("Queue Action", classes="modal-title")
            with ScrollableContainer():
                with LoopingListView(id="cat-list"):
                    for i, (cat, _) in enumerate(self._cat_actions.items()):
                        used    = self._queued_cats.get(cat.value)
                        ongoing = self._state.ongoing_actions.get(cat.value)
                        if used:
                            note = f"  [used: {used}]"
                        elif ongoing:
                            note = f"  [ongoing: {ongoing.action_key.replace('_',' ')} ({ongoing.executed_ticks}x)]"
                        else:
                            note = ""
                        yield ListItem(
                            Label(f"{cat.value.replace('_',' ').title()}{note}"),
                            id=f"cat-{i}",
                        )
            with Horizontal(classes="btn-row"):
                yield Button("Cancel", id="cancel-btn", classes="-danger")

    def on_mount(self) -> None:
        self.query_one("#cat-list", ListView).focus()

    @on(ListView.Selected, "#cat-list")
    def _on_cat_selected(self, event: ListView.Selected) -> None:
        self._handle_cat_selected(event)

    @work
    async def _handle_cat_selected(self, event: ListView.Selected) -> None:
        idx = int(event.item.id.split("-", 1)[1])
        cat, actions = list(self._cat_actions.items())[idx]

        # If ongoing action in this category, offer management
        ongoing = self._state.ongoing_actions.get(cat.value)
        if ongoing:
            od    = self._library.get(ongoing.action_key)
            oname = od.name if od else ongoing.action_key
            choice = await self.app.push_screen_wait(
                PickerModal(
                    f"[ONGOING] {oname}",
                    [
                        ("stop",     "Stop ongoing action"),
                        ("override", "Override this tick only"),
                        ("leave",    "Leave it running"),
                    ],
                    description=f"{ongoing.executed_ticks}x executed, {ongoing.ticks_active} ticks old",
                )
            )
            if choice == "leave" or choice is None:
                return
            if choice == "stop":
                del self._state.ongoing_actions[cat.value]

        # If a manually queued action already occupies this category, ask to cancel it
        if cat.value in self._queued_cats:
            existing = self._queued_cats[cat.value]
            cancel_it = await self.app.push_screen_wait(
                YesNoModal(
                    f"'{existing}' already queued",
                    "Cancel it and choose a different action for this category?",
                )
            )
            if not cancel_it:
                return
            # Remove that action instance from the queue
            cat_def_ids = {
                str(defn.id)
                for key, defn in self._library.items()
                if defn.category == cat
            }
            self._state.action_queue = [
                ai for ai in self._state.action_queue
                if str(ai.action_definition_id) not in cat_def_ids
            ]
            del self._queued_cats[cat.value]

        # Show action list
        items = []
        for key, defn in actions:
            fp_total    = defn.footprint_cost.total()
            essence_str = ""
            if defn.essence_cost != 0:
                verb        = "↑" if defn.essence_cost < 0 else "↓"
                essence_str = f"  Ess{verb}{abs(defn.essence_cost):.1f}"
            persist = "  [persist]" if "can_persist" in defn.tags else ""
            stub    = "  [stub]"    if key in _STUB_ACTIONS else ""
            items.append(
                (key, f"{defn.name:<34}  FP:{fp_total:.2f}{essence_str}{persist}{stub}")
            )
        chosen_key = await self.app.push_screen_wait(
            PickerModal(cat.value.replace("_", " ").title(), items, show_back=True)
        )
        if chosen_key is None or chosen_key == BACK:
            return

        if chosen_key in _STUB_ACTIONS:
            defn = self._library[chosen_key]
            await self.app.push_screen_wait(
                YesNoModal(
                    f"{defn.name} — not yet implemented",
                    "This action requires systems that are planned but not yet built.",
                )
            )
            return

        if chosen_key in self._library:
            self.dismiss((chosen_key, self._library[chosen_key]))

    @on(Button.Pressed, "#cancel-btn")
    def _cancel(self, _: Button.Pressed) -> None:
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)


# ─────────────────────────────────────────
# STATUS PANEL  (left sidebar)
# ─────────────────────────────────────────

class StatusPanel(Static):
    def refresh_state(self, state: SimulationState) -> None:
        self.update(_render_status(state))


# ─────────────────────────────────────────
# GAME SCREEN
# ─────────────────────────────────────────

class GameScreen(Screen):
    BINDINGS = [
        ("b",      "briefing",        "Briefing"),
        ("s",      "show_state",      "State"),
        ("a",      "queue_action",    "Queue"),
        ("o",      "manage_ongoing",  "Ongoing"),
        ("t",      "advance_tick",    "Advance"),
        ("ctrl+s", "save_game",       "Save"),
        ("q",      "quit_game",       "Quit"),
    ]

    def __init__(self, state: SimulationState):
        super().__init__()
        self._state = state

    def compose(self) -> ComposeResult:
        yield Header(show_clock=False)
        with Horizontal():
            yield StatusPanel(id="status-panel")
            yield RichLog(id="main-feed", markup=True, highlight=False, wrap=True)
        yield Footer()

    def on_mount(self) -> None:
        self._last_result = None
        _LOGS_DIR.mkdir(exist_ok=True)
        log_path = _LOGS_DIR / f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        self._log = SessionLog(log_path)
        self._refresh_status()
        self._feed_markup(f"[#2a4a6a]Logging to: {log_path}[/]")
        briefing = display_briefing(self._state)
        self._feed(briefing)
        self._log.write(briefing)
        state_str = display_state(self._state)
        self._feed(state_str)
        self._log.write(state_str)

    # ── Display helpers ───────────────────────

    def _feed(self, text: str) -> None:
        self.query_one("#main-feed", RichLog).write(text)

    def _feed_markup(self, markup: str) -> None:
        self.query_one("#main-feed", RichLog).write(Text.from_markup(markup))

    def _refresh_status(self) -> None:
        state = self._state
        self.query_one(StatusPanel).refresh_state(state)
        self.app.sub_title = (
            f"{state.universe.name}  ·  Age {state.universe.current_age:.1f}  ·  Tick {state.tick_number}"
        )

    # ── Actions (keyboard bindings) ───────────

    def action_briefing(self) -> None:
        self._feed(display_briefing(self._state))

    def action_show_state(self) -> None:
        self._feed(display_state(self._state))

    def action_queue_action(self) -> None:
        self._queue_action_flow()

    def action_manage_ongoing(self) -> None:
        self._manage_ongoing_flow()

    @work
    async def _manage_ongoing_flow(self) -> None:
        state   = self._state
        library = self.app.loop._action_library  # type: ignore[attr-defined]
        if not state.ongoing_actions:
            self._feed_markup("[#5a7090]No ongoing actions.[/]")
            return
        items = []
        for cat_val, oa in state.ongoing_actions.items():
            defn  = library.get(oa.action_key)
            name  = defn.name if defn else oa.action_key
            label = cat_val.replace("_", " ").title()
            items.append((cat_val, f"[{label}] {name}  ({oa.executed_ticks}/{oa.ticks_active})"))
        chosen = await self.app.push_screen_wait(PickerModal("Ongoing Actions", items))
        if chosen and chosen in state.ongoing_actions:
            confirmed = await self.app.push_screen_wait(
                YesNoModal(f"Stop this ongoing action?")
            )
            if confirmed:
                oa   = state.ongoing_actions.pop(chosen)
                defn = library.get(oa.action_key)
                name = defn.name if defn else oa.action_key
                # Clear the Proxius's active goal when an issue_directive is stopped
                if oa.action_key == "issue_directive" and oa.proxius_id:
                    proxius = state.mortals.get(str(oa.proxius_id))
                    if proxius:
                        proxius.active_goal = None
                self._feed_markup(f"[#c09030]Stopped ongoing:[/] {name}")
                self._refresh_status()

    def action_advance_tick(self) -> None:
        self._advance_tick_work()

    @work(thread=True)
    def _advance_tick_work(self) -> None:
        state = self._state
        loop  = self.app.loop   # type: ignore[attr-defined]
        self.app.call_from_thread(self._feed_markup, "[#3a6090]Advancing time...[/]")
        new_state, result = loop.advance(state)
        self._state = new_state
        self._last_result = result
        tick_str = display_tick_result(result)
        self._log.write_tick(result)
        self.app.call_from_thread(self._feed, tick_str)
        self.app.call_from_thread(self._refresh_status)
        if result.terminal.triggered:
            self._log.finalize(new_state, result)
            self.app.call_from_thread(
                self._feed_markup,
                f"[bold #b04050]SCENARIO END: {result.terminal.condition.value.upper()}[/]\n"
                f"{result.terminal.note}",
            )

    def action_save_game(self) -> None:
        self._save_game_flow()

    @work
    async def _save_game_flow(self) -> None:
        state = self._state
        _SAVES_DIR.mkdir(exist_ok=True)
        dt      = datetime.now().strftime("%Y%m%d%H%M%S")
        default = f"{state.universe.save_name}_{dt}"
        form = await self.app.push_screen_wait(
            TextFormModal("Save Game", [("Save name", "name", default)])
        )
        if form is None:
            return
        name = form["name"].strip() or default
        db_path = _SAVES_DIR / f"{name}.db"
        if db_path.exists():
            overwrite = await self.app.push_screen_wait(
                YesNoModal(f"'{name}.db' already exists", "Overwrite?")
            )
            if not overwrite:
                self._feed_markup("[#5a7090]Save cancelled.[/]")
                return
        description = f"Tick {state.tick_number}  |  Age {state.universe.current_age:.1f}"
        export_scenario(state, db_path, scenario_name=name, description=description)
        self._feed_markup(f"[#50b870]Saved to saves/{name}.db[/]")

    def action_quit_game(self) -> None:
        self._log.finalize(self._state, self._last_result)
        self.app.exit()

    # ── Action queue flow ─────────────────────

    @work
    async def _queue_action_flow(self) -> None:
        app     = self.app
        state   = self._state
        library = app.loop._action_library  # type: ignore[attr-defined]

        while True:
            # Browse and pick action
            picked = await app.push_screen_wait(ActionBrowserModal(state, library))
            if picked is None:
                return
            action_key, defn = picked

            # Build intent; BACK means "re-show action browser"
            instance = await self._build_intent(action_key, defn)
            if instance is None:
                self._feed_markup("[#5a7090]Cancelled.[/]")
                return
            if instance == BACK:
                continue
            break

        # Offer persistence for eligible actions
        if "can_persist" in defn.tags:
            make_persistent = await app.push_screen_wait(
                YesNoModal(
                    f"Make '{defn.name}' persistent?",
                    "It will auto-execute each tick until you stop it.",
                )
            )
            if make_persistent:
                state.ongoing_actions[defn.category.value] = OngoingAction(
                    action_key=action_key,
                    action_definition_id=defn.id,
                    target_type=instance.target_type,
                    target_id=instance.target_id,
                    proxius_id=instance.proxius_id,
                    intent=instance.intent,
                    ticks_active=0,
                    started_at_tick=state.tick_number,
                )
                self._log.write_action(f"[ONGOING SET] {defn.name}")
                self._feed_markup(f"[#60a870][ONGOING SET][/] {defn.name}")
                self._refresh_status()
                return

        state.action_queue.append(instance)
        summary = defn.name
        if instance.target_id:
            summary += f" → {_name_for_id(instance.target_id, state)}"
        self._log.write_action(summary)
        self._feed_markup(f"[#a0d080]Queued:[/] {summary}")
        self._refresh_status()

    # ── Intent construction ───────────────────

    async def _build_intent(
        self,
        action_key: str,
        defn: ActionDefinition,
    ) -> "ActionInstance | str | None":
        """
        Returns ActionInstance on success, BACK to re-show action browser, or None to cancel.
        """
        app   = self.app
        state = self._state

        target_type = defn.valid_targets[0] if defn.valid_targets else TargetType.WORLD

        # ── issue_directive: full multi-step (proxius → form → domain → civ) ──
        if action_key == "issue_directive":
            already_directed = {
                str(ai.proxius_id)
                for ai in state.action_queue
                if isinstance(ai.intent, ProxiusDirectiveIntent)
                and ai.proxius_id is not None
            }
            step = 0
            pid = None; form_data = None
            dvs: list = []; imago_id = None
            while True:
                if step == 0:
                    result = await self._pick_proxius(
                        state, include_dormant=True, already_directed=already_directed,
                    )
                    if result is None: return None
                    if result == BACK: return BACK
                    pid = result; step = 1
                if step == 1:
                    form = await app.push_screen_wait(
                        TextFormModal(
                            "Directive",
                            [
                                ("Goal statement", "goal", "Strengthen the reformist faction"),
                                ("Latitude  0.0 strict → 1.0 open", "lat", "0.5"),
                            ],
                            description=defn.description,
                            show_back=True,
                        )
                    )
                    if form is None: return None
                    if form == BACK: step = 0; continue
                    form_data = form; step = 2
                if step == 2:
                    domain_result = await self._pick_domain_and_imago(state)
                    if domain_result is None: return None
                    if domain_result == BACK: step = 1; continue
                    dvs, imago_id = domain_result; step = 3
                if step == 3:
                    target_civ_id = None
                    if dvs:
                        proxius_obj = state.mortals.get(pid)
                        loc_id      = str(proxius_obj.current_location) if proxius_obj else None
                        civs_here   = [
                            (cid, c) for cid, c in state.civilizations.items()
                            if str(c.origin_location_id) == loc_id
                        ] if loc_id else []
                        if not civs_here:
                            self._feed_markup(
                                "[#5a7090](No civilizations at Proxius's location — domain vectors discarded.)[/]"
                            )
                            dvs = []
                        elif len(civs_here) == 1:
                            target_civ_id = UUID(civs_here[0][0])
                        else:
                            civ_items = [(cid, f"{c.name}  [{c.scale.value}]") for cid, c in civs_here]
                            civ_items.append(("__discard__", "Discard domain vectors"))
                            chosen_civ = await app.push_screen_wait(
                                PickerModal("Promote belief in which civilization?", civ_items, show_back=True)
                            )
                            if chosen_civ == BACK: step = 2; continue
                            if chosen_civ is None: return None
                            if chosen_civ != "__discard__":
                                target_civ_id = UUID(chosen_civ)
                            else:
                                dvs = []
                    break
            goal = form_data["goal"].strip() or "Strengthen the reformist faction"
            try:
                latitude = max(0.0, min(1.0, float(form_data["lat"])))
            except ValueError:
                latitude = 0.5
            intent = ProxiusDirectiveIntent(
                goal_statement=goal,
                domain_vectors=dvs,
                latitude=latitude,
                target_civilization_id=target_civ_id,
                imago_node_id=imago_id,
            )
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=TargetType.MORTAL,
                target_id=UUID(pid),
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=UUID(pid),
                intent=intent,
            )

        # ── Other proxius-targeted actions (no intent params) ──
        if defn.requires_proxius:
            result = await self._pick_proxius(
                state,
                include_dormant="include_dormant_proxius" in defn.tags,
            )
            if result is None: return None
            if result == BACK: return BACK
            proxius_id = UUID(result)
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=TargetType.MORTAL,
                target_id=proxius_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=proxius_id,
                intent=None,
            )

        # ── Scry: scope → target picker loop ──
        if action_key == "scry":
            scope_items = [
                (ScryScope.WORLD.value,    "World       — deep mortal/civ detail  (0.05 subtle)"),
                (ScryScope.SYSTEM.value,   "System      — reveals worlds & civs   (0.10 subtle)"),
                (ScryScope.GALAXY.value,   "Galaxy      — broad survey            (0.20 subtle)"),
                (ScryScope.UNIVERSE.value, "Universe    — cosmos-wide sweep       (0.35 subtle)"),
            ]
            target_id = None
            while True:
                picked_scope = await app.push_screen_wait(
                    PickerModal("Scry Scope", scope_items, show_back=True)
                )
                if picked_scope is None: return None
                if picked_scope == BACK: return BACK
                chosen_scope = ScryScope(picked_scope)
                if chosen_scope == ScryScope.WORLD:
                    target_id, target_type = await self._pick_world(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                elif chosen_scope == ScryScope.SYSTEM:
                    target_id, target_type = await self._pick_system(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                elif chosen_scope == ScryScope.GALAXY:
                    target_id, target_type = await self._pick_galaxy(state)
                    if target_id is None: return None
                    if target_id == BACK: continue
                else:
                    target_type = TargetType.UNIVERSE
                break
            return ActionInstance(
                action_definition_id=defn.id,
                target_type=target_type,
                target_id=target_id,
                timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id,
                proxius_id=None,
                intent=ScryIntent(scope=chosen_scope),
            )

        # ── Target selection by type, with back-from-params loop ──
        _NO_PARAMS = (
            "appoint_proxius", "empower_proxius", "dismiss_proxius",
            "go_quiet_proxius", "audit_proxius", "maintain_concealment",
        )

        if TargetType.MORTAL in defn.valid_targets:
            _proxius_ids = {str(pid) for pid in state.demiurge.proxius_ids}
            mortals = [
                (mid, m) for mid, m in state.mortals.items()
                if is_mortal_visible(m)
                and m.role not in (MortalRole.PROXIUS, MortalRole.HERALD)
                and mid not in _proxius_ids
            ]
            if not mortals:
                self._feed_markup("[#5a7090]No mortals currently within perception.[/]")
                return None
            mortal_items = []
            for mid, m in mortals:
                w_obj    = state.locations.get(str(m.current_location))
                loc      = w_obj.name if w_obj else "?"
                role_str = m.role.value if m.role != MortalRole.OTHER else "mortal"
                mortal_items.append((mid, f"{m.name:<18} [{role_str}]  align:{m.alignment:.2f}  {loc}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Mortal", mortal_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.MORTAL,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.CIVILIZATION in defn.valid_targets:
            civ_items = []
            for cid, c in state.civilizations.items():
                if not is_in_window(c):
                    continue
                w_obj = state.locations.get(str(c.origin_location_id)) if c.origin_location_id else None
                loc   = w_obj.name if w_obj else "?"
                civ_items.append((cid, f"{c.name:<30} [{c.scale.value}]  {loc}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Civilization", civ_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.CIVILIZATION,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.LUMINARY in defn.valid_targets:
            lum_items = [
                (lid, f"{l.name}  [{_personality_label(l)}]")
                for lid, l in state.luminaries.items()
            ]
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Luminary", lum_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.LUMINARY,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.SPECIES in defn.valid_targets:
            species_items = []
            for sid, sp in state.species.items():
                w_obj  = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
                origin = w_obj.name if w_obj else "unknown"
                sap    = "sapient" if sp.sapient else "non-sapient"
                species_items.append((sid, f"{sp.name:<18} [{sap}]  origin: {origin}"))
            intent = None
            while True:
                picked_id = await app.push_screen_wait(PickerModal("Select Species", species_items, show_back=True))
                if picked_id is None: return None
                if picked_id == BACK: return BACK
                target_id = UUID(picked_id)
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=TargetType.SPECIES,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.WORLD in defn.valid_targets and state.worlds:
            intent = None
            while True:
                target_id, target_type = await self._pick_world(state)
                if target_id is None: return None
                if target_id == BACK: return BACK
                if action_key in _NO_PARAMS:
                    break
                intent = await self._build_intent_params(action_key, defn, target_id, state)
                if intent is None: return None
                if intent == BACK: continue
                break
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=target_id, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None,
                intent=None if action_key in _NO_PARAMS else intent,
            )

        if TargetType.UNDERREAL in defn.valid_targets:
            target_type = TargetType.UNDERREAL
            if action_key in _NO_PARAMS:
                return ActionInstance(
                    action_definition_id=defn.id, target_type=target_type,
                    target_id=None, timestamp=state.universe.current_age,
                    demiurge_id=state.demiurge.id, proxius_id=None, intent=None,
                )
            intent = await self._build_intent_params(action_key, defn, None, state)
            if intent is None: return None
            if intent == BACK: return BACK
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=None, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None, intent=intent,
            )

        # ── No target / self-actions (SELF_REFINEMENT etc.) ──
        if action_key in _NO_PARAMS:
            return ActionInstance(
                action_definition_id=defn.id, target_type=target_type,
                target_id=None, timestamp=state.universe.current_age,
                demiurge_id=state.demiurge.id, proxius_id=None, intent=None,
            )
        intent = await self._build_intent_params(action_key, defn, None, state)
        if intent is None: return None
        if intent == BACK: return BACK
        return ActionInstance(
            action_definition_id=defn.id, target_type=target_type,
            target_id=None, timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id, proxius_id=None, intent=intent,
        )

    async def _build_intent_params(
        self,
        action_key: str,
        defn: "ActionDefinition",
        target_id,
        state: SimulationState,
    ):
        """
        Return the typed intent, BACK (go to previous step), or None (cancel).
        For no-param actions returns None without meaning cancel.
        """
        app = self.app
        cat = defn.category

        # ── DIRECT CREATION ──────────────────────────────
        if cat == ActionCategory.DIRECT_CREATION:
            if action_key == "seed_world":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Seed World — New Species",
                        [
                            ("Species name",          "name",    "Life-Form Alpha"),
                            ("Lifespan min",          "lmin",    "100.0"),
                            ("Lifespan max",          "lmax",    "200.0"),
                            ("Sapient from start? y/n","sapient","n"),
                            ("Bio tags (comma-separated, e.g. bio:bipedal)", "tags", ""),
                        ],
                        description=defn.description,
                        show_back=True,
                    )
                )
                if form is None: return None
                if form == BACK: return BACK
                bio_tags = [t.strip() for t in form["tags"].split(",") if t.strip()]
                return SeedWorldIntent(
                    species_name=form["name"].strip() or "Life-Form Alpha",
                    lifespan_min=float(form["lmin"] or 100.0),
                    lifespan_max=float(form["lmax"] or 200.0),
                    sapient=form["sapient"].strip().lower() == "y",
                    bio_tags=bio_tags,
                )
            if action_key == "uplift_species":
                domain_result = await self._pick_domain_and_imago(state)
                if domain_result is None: return None
                if domain_result == BACK: return BACK
                dvs, imago_id = domain_result
                return UpliftSpeciesIntent(species_id=target_id, domain_vectors=dvs, imago_node_id=imago_id)

        # ── SUBTLE INFLUENCE ─────────────────────────────
        elif cat == ActionCategory.SUBTLE_INFLUENCE:
            if action_key in ("whisper", "shape_dream"):
                ireg = get_imago_registry()
                step = 0
                dvs: list = []; imago_id = None; concept = None
                while True:
                    if step == 0:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: return BACK
                        dvs, imago_id = domain_result
                        concept = ireg.get_node(imago_id).name if imago_id else None
                        step = 1
                    if step == 1:
                        if not imago_id:
                            form = await app.push_screen_wait(
                                TextFormModal(
                                    "Whisper",
                                    [("Concept to plant", "concept", "You could shape the future.")],
                                    show_back=True,
                                )
                            )
                            if form is None: return None
                            if form == BACK: step = 0; continue
                            concept = form["concept"].strip() or "You could shape the future."
                        step = 2
                    if step == 2:
                        framing = await self._pick_framing()
                        if framing is None: return None
                        if framing == BACK:
                            step = 1 if not imago_id else 0
                            continue
                        break
                return WhisperIntent(
                    concept=concept, domain_vectors=dvs, framing=framing, imago_node_id=imago_id,
                )

            if action_key == "nudge_probability":
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Nudge Probability",
                                [
                                    ("Event to nudge",  "event",   "Upcoming succession conflict"),
                                    ("Desired outcome", "outcome", "The reformist faction prevails"),
                                ],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; break
                return ProbabilityNudgeIntent(
                    event_description=form_data["event"].strip() or "Upcoming succession conflict",
                    desired_outcome=form_data["outcome"].strip() or "The reformist faction prevails",
                    domain_vectors=dvs, imago_node_id=imago_id,
                )

            if action_key == "accelerate_development":
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Accelerate Development",
                                [("Aspect to develop", "aspect", "military doctrine")],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; break
                return DevelopmentIntent(
                    domain_vectors=dvs,
                    target_aspect=form_data["aspect"].strip() or "military doctrine",
                    imago_node_id=imago_id,
                )

        # ── OVERT MIRACLE ────────────────────────────────
        elif cat == ActionCategory.OVERT_MIRACLE:
            if action_key in ("manifest_omen", "divine_manifestation"):
                step = 0; form_data = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Manifest Omen",
                                [
                                    ("Sign description",       "sign",   "A celestial anomaly appears"),
                                    ("Intended interpretation","interp", "The gods demand action"),
                                ],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 0; continue
                        dvs, imago_id = domain_result; step = 2
                    if step == 2:
                        framing = await self._pick_framing()
                        if framing is None: return None
                        if framing == BACK: step = 1; continue
                        break
                civ_scope = None
                if target_id:
                    tid_str = str(target_id)
                    if tid_str in state.civilizations:
                        civ_scope = target_id
                    elif tid_str in state.mortals:
                        civ_scope = state.mortals[tid_str].civilization_id
                return OmenIntent(
                    sign_description=form_data["sign"].strip() or "A celestial anomaly appears",
                    intended_interpretation=form_data["interp"].strip() or "The gods demand action",
                    domain_vectors=dvs, framing=framing, civilization_scope=civ_scope,
                    imago_node_id=imago_id,
                )

        # ── UNDERREAL ────────────────────────────────────
        elif cat == ActionCategory.UNDERREAL:
            if action_key == "harvest_essence":
                form = await app.push_screen_wait(
                    TextFormModal(
                        "Harvest Essence",
                        [
                            ("Target concept type (optional)", "concept", ""),
                            ("Concealment priority  0.0 risky → 1.0 safe", "conc", "0.7"),
                        ],
                        show_back=True,
                    )
                )
                if form is None: return None
                if form == BACK: return BACK
                try:
                    conc = max(0.0, min(1.0, float(form["conc"] or 0.7)))
                except ValueError:
                    conc = 0.7
                return EssenceHarvestIntent(
                    target_concept_type=form["concept"].strip() or None,
                    concealment_priority=conc,
                )
            if action_key == "salvage_concept":
                step = 0; form_data = None; world_id = None
                dvs = []; imago_id = None
                while True:
                    if step == 0:
                        form = await app.push_screen_wait(
                            TextFormModal(
                                "Salvage Concept",
                                [("What are you hoping to find?", "desired", "")],
                                show_back=True,
                            )
                        )
                        if form is None: return None
                        if form == BACK: return BACK
                        form_data = form; step = 1
                    if step == 1:
                        world_id, _ = await self._pick_world(state)
                        if world_id is None: return None
                        if world_id == BACK: step = 0; continue
                        step = 2
                    if step == 2:
                        domain_result = await self._pick_domain_and_imago(state)
                        if domain_result is None: return None
                        if domain_result == BACK: step = 1; continue
                        dvs, imago_id = domain_result; break
                return SalvageIntent(
                    desired_concept=form_data["desired"].strip(),
                    target_world_id=world_id,
                    domain_vectors=dvs, imago_node_id=imago_id,
                )

        # ── LUMINARY RELATIONS ───────────────────────────
        elif cat == ActionCategory.LUMINARY_RELATIONS:
            form = await app.push_screen_wait(
                TextFormModal(
                    "Petition Luminary",
                    [
                        ("Subject",           "subject",  "Current universe state"),
                        ("Your position",     "position", "Continued patience"),
                        ("Tone (deferential/confident/urgent/firm)", "tone", "deferential"),
                    ],
                    show_back=True,
                )
            )
            if form is None: return None
            if form == BACK: return BACK
            return LuminaryPetitionIntent(
                subject=form["subject"].strip() or "Current universe state",
                your_position=form["position"].strip() or "Continued patience",
                tone=form["tone"].strip() or "deferential",
            )

        # ── SELF REFINEMENT ──────────────────────────────
        elif cat == ActionCategory.SELF_REFINEMENT:
            if action_key == "explore_beliefs":
                domain_result = await self._pick_domain_and_imago(state, explore_mode=True)
                if domain_result is None: return None
                if domain_result == BACK: return BACK
                dvs, _ = domain_result
                if not dvs:
                    return None
                return ExploreBeliefIntent(domain_tag=dvs[0].domain_tag)

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
                        if not new_tag: step = 0; continue  # skip domain = redo drop picker
                        break
                return ChangeAffiliatedDomainsIntent(old_domain=old_tag, new_domain=new_tag)

        # No intent needed
        return None

    # ── Sub-pickers ───────────────────────────

    async def _pick_domain_and_imago(
        self,
        state: SimulationState,
        explore_mode: bool = False,
    ) -> "tuple[list[DomainVector], str | None] | str | None":
        """
        Show the domain grid picker, then (if applicable) the Imago tree picker.
        Returns (dvs, imago_id), ([], None) for skip, BACK to go one level back, or None to cancel.
        """
        while True:
            tag = await self.app.push_screen_wait(DomainPickerModal(state, explore_mode=explore_mode))

            if tag is None: return None   # Cancel
            if tag == BACK: return BACK   # Back
            if tag == "":   return ([], None)  # Skip Domain

            if explore_mode:
                return ([DomainVector(domain_tag=tag, direction=1.0)], None)

            tree = tag.split(":", 1)[1]
            ireg = get_imago_registry()

            if ireg.nodes_for_tree(tree):
                while True:
                    chosen_id = await self.app.push_screen_wait(ImagoTreeModal(state, tree))
                    if chosen_id == BACK:       # ← Domain: back to domain picker
                        break
                    if chosen_id is None:       # Cancel: propagate up
                        return None
                    if chosen_id == "__manual__":
                        break
                    node      = ireg.get_node(chosen_id)
                    confirmed = await self.app.push_screen_wait(ImagoDetailModal(node, state))
                    if confirmed is None: return None  # Cancel from detail
                    if confirmed:
                        dvs = [
                            DomainVector(domain_tag=t, direction=v)
                            for t, v in node.mechanics.items()
                            if t.startswith("domain:")
                        ]
                        return (dvs, chosen_id)
                    # False = back to tree picker; loop continues
                if chosen_id == BACK:
                    continue  # re-show domain picker
                # fell through with __manual__

            # Manual direction fallback
            form = await self.app.push_screen_wait(
                TextFormModal(
                    "Domain Direction",
                    [("Direction  -1.0 suppress  →  +1.0 promote", "dir", "0.5")],
                    show_back=True,
                )
            )
            if form is None: return None
            if form == BACK: continue   # back to domain picker
            try:
                direction = max(-1.0, min(1.0, float(form["dir"])))
            except ValueError:
                direction = 0.5
            return ([DomainVector(domain_tag=tag, direction=direction)], None)

    async def _pick_proxius(
        self,
        state: SimulationState,
        include_dormant: bool = False,
        already_directed: set | None = None,
    ) -> "str | None":
        already_directed = already_directed or set()
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and mid not in already_directed
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            self._feed_markup("[#5a7090]No Proxii available.[/]")
            return None
        items = []
        for mid, m in proxii:
            w_obj     = state.locations.get(str(m.current_location))
            loc       = w_obj.name if w_obj else "?"
            dorm_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            items.append((mid, f"{m.name:<18}  align:{m.alignment:.2f}  {loc}{dorm_note}"))
        return await self.app.push_screen_wait(PickerModal("Select Proxius", items, show_back=True))

    async def _pick_world(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        worlds = [(wid, w) for wid, w in state.worlds.items() if is_in_window(w)]
        if not worlds:
            self._feed_markup("[#5a7090]No worlds available.[/]")
            return None, TargetType.WORLD
        items = []
        for wid, w in worlds:
            sys_obj  = state.locations.get(str(w.parent_id)) if w.parent_id else None
            sys_name = sys_obj.name if sys_obj else "?"
            n_civs   = sum(1 for cid in w.civilization_ids if str(cid) in state.civilizations and is_in_window(state.civilizations[str(cid)]))
            life_str = f"{n_civs} civilization(s) known" if n_civs else "no life known"
            items.append((wid, f"{w.name:<16} [{w.condition.value}]  {sys_name:<20}  {life_str}"))
        picked = await self.app.push_screen_wait(PickerModal("Select World", items, show_back=True))
        if picked is None:  return None, TargetType.WORLD
        if picked == BACK:  return BACK, TargetType.WORLD
        return UUID(picked), TargetType.WORLD

    async def _pick_system(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        systems = [(sid, s) for sid, s in state.systems.items() if is_in_window(s)]
        if not systems:
            self._feed_markup("[#5a7090]No systems available.[/]")
            return None, TargetType.SYSTEM
        items = []
        for sid, s in systems:
            gal_obj  = state.locations.get(str(s.parent_id)) if s.parent_id else None
            gal_name = gal_obj.name if gal_obj else "?"
            n_worlds = sum(1 for cid in s.child_ids if str(cid) in state.locations and is_in_window(state.locations[str(cid)]))
            items.append((sid, f"{s.name:<22} [{s.star_type.value}]  {gal_name:<20}  {n_worlds} world(s) known"))
        picked = await self.app.push_screen_wait(PickerModal("Select System", items, show_back=True))
        if picked is None:  return None, TargetType.SYSTEM
        if picked == BACK:  return BACK, TargetType.SYSTEM
        return UUID(picked), TargetType.SYSTEM

    async def _pick_galaxy(
        self,
        state: SimulationState,
    ) -> "tuple[UUID | str | None, TargetType]":
        galaxies = [(gid, g) for gid, g in state.galaxies.items() if is_in_window(g)]
        if not galaxies:
            self._feed_markup("[#5a7090]No galaxies available.[/]")
            return None, TargetType.GALAXY
        items = []
        for gid, g in galaxies:
            n_systems = sum(1 for cid in g.child_ids if str(cid) in state.locations and is_in_window(state.locations[str(cid)]))
            items.append((gid, f"{g.name:<26}  {n_systems} system(s) known"))
        picked = await self.app.push_screen_wait(PickerModal("Select Galaxy", items, show_back=True))
        if picked is None:  return None, TargetType.GALAXY
        if picked == BACK:  return BACK, TargetType.GALAXY
        return UUID(picked), TargetType.GALAXY

    async def _pick_framing(self) -> "Framing | str | None":
        """Returns a Framing value, BACK sentinel, or None to cancel."""
        items  = [(f.value, f.value.title()) for f in Framing]
        picked = await self.app.push_screen_wait(PickerModal("Framing", items, show_back=True))
        if picked is None:                          return None
        if picked == BACK:                          return BACK
        if picked not in {f.value for f in Framing}: return Framing.INSPIRATIONAL
        return Framing(picked)


# ─────────────────────────────────────────
# APP
# ─────────────────────────────────────────

class DemiurgeApp(App):
    CSS   = _CSS
    TITLE = "DEMIURGE"

    loop: TickLoop

    def __init__(self):
        super().__init__()
        self.loop = TickLoop()

    def on_mount(self) -> None:
        self.push_screen(LoadScreen())


if __name__ == "__main__":
    DemiurgeApp().run()
