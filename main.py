#!/usr/bin/env python3
"""
main.py
Interactive CLI for the Demiurge simulation.
"""

from __future__ import annotations
import os
from datetime import datetime
from pathlib import Path
from uuid import UUID

from core.universe_core import MortalRole, MortalStatus, MortalProminence
from core.action_core import (
    ActionCategory, TargetType, ActionDefinition,
    ActionInstance, OngoingAction,
    WhisperIntent, OmenIntent, ProbabilityNudgeIntent,
    DevelopmentIntent, ProxiusDirectiveIntent,
    LuminaryPetitionIntent, EssenceHarvestIntent,
    SalvageIntent, SeedWorldIntent, UpliftSpeciesIntent,
    ExploreBeliefIntent,
    DomainVector,
)
from logic.tick_logic import (
    SimulationState,
    TickLoop, TickResult,
    is_mortal_visible, ALWAYS_VISIBLE_THRESHOLD,
)
from utilities.scenario_loader import load_scenario
from utilities.scenario_exporter import export_scenario
from utilities.domain_registry import get_registry as get_domain_registry
from utilities.imago_registry import get_registry as get_imago_registry

# Actions whose required systems haven't been built yet.
# Listed in the action browser with a note; selecting one shows a message and backs out.
_STUB_ACTIONS: frozenset[str] = frozenset({
    "read_divine_traces",     # needs divine-trace / other-actor footprint system
    "negotiate_herald",       # needs Herald entity class
    "obstruct_herald",        # needs Herald entity class
    "petition_luminary_herald",  # needs Herald entity class
    "investigate_underreal",  # needs Underreal content system
})


# ─────────────────────────────────────────
# DISPLAY
# Compact state summaries for the terminal.
# ─────────────────────────────────────────

SEP  = "─" * 60
SEP2 = "═" * 60

def display_state(state: SimulationState) -> str:
    lines = [
        SEP2,
        f"  UNIVERSE: {state.universe.name}",
        f"  Age: {state.universe.current_age:.1f}  |  Tick: {state.tick_number}",
        SEP2,
    ]

    # ── Demiurge ──────────────────────────────────────
    fp = state.demiurge.footprint
    es = state.essence
    lines += [
        "DEMIURGE",
        f"  Footprint — overt:{fp.overt_miracles:.2f}  "
        f"subtle:{fp.subtle_influence:.2f}  "
        f"proxii:{fp.proxius_activity:.2f}  "
        f"creation:{fp.direct_creation:.2f}",
        f"  Essence   — actual:{es.actual:.2f}  "
        f"apparent:{es.apparent:.2f}  "
        f"concealment:{es.concealment_integrity:.2f}",
        SEP,
    ]

    # ── Luminaries ────────────────────────────────────
    lines.append("LUMINARIES")
    for lid, lum in state.luminaries.items():
        att = state.luminary_attention.get(lid, 0.0)
        d   = lum.disposition
        lines.append(
            f"  {lum.name:12s}  "
            f"results:{d.results:+.2f}  methods:{d.methods:+.2f}  "
            f"attention:{att:.2f}  [{lum.temperament.value}]"
        )
    lines.append(SEP)

    # ── Worlds ────────────────────────────────────────
    lines.append("WORLDS")
    for wid, world in state.worlds.items():  # type: ignore[attr-defined]
        domain_str = _format_beliefs(world.domain_expression) or "none"
        lines.append(
            f"  {world.name}  [{world.condition.value}]  domain: {domain_str}"
        )
        for cid in world.civilization_ids:
            civ = state.civilizations.get(str(cid))
            if civ:
                h = civ.health
                lines.append(
                    f"    └─ {civ.name} [{civ.scale.value}]  "
                    f"stab:{h.stability:.2f} pros:{h.prosperity:.2f} "
                    f"coh:{h.cohesion:.2f}"
                )
                lines.append(
                    f"       beliefs: {_format_beliefs(civ.dominant_beliefs) or 'none'}"
                )
    lines.append(SEP)

    # ── Mortals of note ───────────────────────────────
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if not is_mortal_visible(mortal):
            continue
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str}]  "
            f"align:{mortal.alignment:.2f}  {age_str}{vis_note}  "
            f"{prom_str}"
        )
    lines.append(SEP)

    # ── Ongoing actions ───────────────────────────────
    lines.append("ONGOING ACTIONS")
    if state.ongoing_actions:
        for cat_val, oa in state.ongoing_actions.items():
            cat_label = cat_val.replace("_", " ").title()
            target_str = ""
            if oa.target_id:
                target_str = f" → {_name_for_id(oa.target_id, state)}"
            lines.append(
                f"  [{cat_label}] {oa.action_key.replace('_', ' ').title()}"
                f"{target_str}  ({oa.executed_ticks}/{oa.ticks_active} ticks executed)"
            )
    else:
        lines.append("  None")
    lines.append(SEP2)

    return "\n".join(lines)


def display_tick_result(result: TickResult) -> str:
    lines = [
        "",
        f"  TICK {result.tick_number} RESULT  "
        f"(age {result.universe_age_before:.1f} → {result.universe_age_after:.1f})",
        SEP,
    ]

    # Passive narrative events
    if result.passive_result.narrative_events:
        lines.append("WORLD EVENTS")
        for ev in result.passive_result.narrative_events:
            lines.append(f"  • {ev}")
        lines.append("")

    # Action outcomes
    if result.action_result.entries:
        lines.append("YOUR ACTIONS")
        for entry in result.action_result.entries:
            lines.append(
                f"  [{entry.outcome.value.upper()}] {entry.narrative}"
            )
        lines.append("")

    # Disposition changes
    if result.disposition_changes:
        lines.append("LUMINARY REACTIONS")
        for lid, (r, m) in result.disposition_changes.items():
            # Find luminary name from evaluations
            ev = next(
                (e for e in result.evaluations if str(e.luminary_id) == lid),
                None
            )
            name = ev.summary_note.split(":")[0] if ev else lid[:8]
            lines.append(
                f"  {name:12s}  results→{r:+.2f}  methods→{m:+.2f}"
            )
        lines.append("")

    # Dialogue triggers
    if result.dialogue_triggers:
        lines.append("DIVINE COMMUNICATIONS")
        for trig in result.dialogue_triggers:
            lines.append(
                f"  [{trig.trigger_type.value.upper()}]  "
                f"urgency:{trig.urgency:.1f}  "
                f"re: {trig.subject_ref or 'general'}"
            )
        lines.append("")

    # Terminal condition
    if result.terminal.triggered:
        lines += [
            SEP2,
            f"  SCENARIO END: {result.terminal.condition.value.upper()}",
            f"  {result.terminal.note}",
            SEP2,
        ]

    return "\n".join(lines)


# ─────────────────────────────────────────
# BRIEFING
# Full scenario context for the player.
# ─────────────────────────────────────────

def display_briefing(state: SimulationState) -> str:
    lines = [
        SEP2,
        f"  SCENARIO BRIEFING",
        f"  {state.universe.name}  (Age {state.universe.current_age:.1f})",
        SEP2,
        "",
    ]

    # ── Pantheon ──────────────────────────────────────
    pan = state.pantheon
    lines.append(f"PANTHEON: {pan.name}")
    if pan.collective_constraints:
        lines.append("  Collective Constraints:")
        for c in pan.collective_constraints:
            lines.append(f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]")
            lines.append(f"      {c.description}")
    lines.append(SEP)

    # ── Liege Luminaries ──────────────────────────────
    lines.append("YOUR LIEGE LUMINARIES")
    for lid in [str(i) for i in state.demiurge.liege_luminary_ids]:
        lum = state.luminaries.get(lid)
        if not lum:
            continue
        lines.append("")
        lines.append(f"  {lum.name.upper()}  [{lum.temperament.value}]")

        domain_names = [
            state.domains[str(did)].name
            for did in lum.domains
            if str(did) in state.domains
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
                lines.append(
                    f"    • {c.name}  [enforcement: {c.enforcement_weight:.2f}]"
                )
                lines.append(f"      {c.description}")

        d = lum.disposition
        att = state.luminary_attention.get(lid, 0.0)
        lines.append(
            f"  Starting disposition:  results{d.results:+.2f}  "
            f"methods{d.methods:+.2f}  attention:{att:.2f}"
        )

    lines += ["", SEP]

    # ── Universe Rules ─────────────────────────────────
    rules = state.universe.rules
    tol   = rules.footprint_tolerances
    pp    = rules.proxii_policy
    cap_str = f"max {pp.max_per_world} per world" if pp.max_per_world else "no per-world limit"
    lines += [
        "UNIVERSE RULES",
        "  Footprint Tolerances:",
        f"    Overt Miracles:   {tol.overt_miracles:.2f}  |  "
        f"Subtle Influence: {tol.subtle_influence:.2f}",
        f"    Proxius Activity: {tol.proxius_activity:.2f}  |  "
        f"Direct Creation:  {tol.direct_creation:.2f}",
        f"  Proxii Policy: {cap_str}  (slack: {pp.tolerance_for_excess:.2f})",
        f"  Active shaping expected:    {'yes' if rules.active_shaping_expected else 'no'}",
        f"  Mortals perceive divinity:  {'yes' if rules.mortals_can_perceive_divinity else 'no'}",
    ]
    if rules.notes:
        lines.append(f"  Notes: {rules.notes}")
    if rules.special_flags:
        lines.append(f"  Special flags: {', '.join(rules.special_flags)}")
    lines.append(SEP)

    # ── Spatial hierarchy ─────────────────────────────
    lines.append("YOUR UNIVERSE")
    for gid, galaxy in state.galaxies.items():  # type: ignore[attr-defined]
        lines += ["", f"  Galaxy: {galaxy.name}"]
        for sid in galaxy.child_ids:
            sys_obj = state.locations.get(str(sid))
            if not sys_obj:
                continue
            star_str = f"  [{sys_obj.star_type.value}]" if hasattr(sys_obj, "star_type") else ""
            lines.append(f"    System: {sys_obj.name}{star_str}")
            for wid in sys_obj.child_ids:
                world = state.worlds.get(str(wid))  # type: ignore[attr-defined]
                if not world:
                    continue
                n_civs  = len(world.civilization_ids)
                life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
                lines.append(
                    f"      {world.name}  [{world.condition.value}]"
                    f"  age:{world.age:.0f}  {life_str}"
                )
                if world.domain_expression:
                    lines.append(
                        f"        domain expression: {_format_beliefs(world.domain_expression)}"
                    )
                if world.geo_tags or world.atmo_tags:
                    parts = []
                    if world.geo_tags:
                        parts.append(f"geo: {', '.join(world.geo_tags)}")
                    if world.atmo_tags:
                        parts.append(f"atmo: {', '.join(world.atmo_tags)}")
                    lines.append(f"        {' · '.join(parts)}")
                for cid in world.civilization_ids:
                    civ = state.civilizations.get(str(cid))
                    if civ:
                        h = civ.health
                        lines.append(
                            f"        └─ {civ.name}  [{civ.scale.value}]"
                            f"  stab:{h.stability:.2f} pros:{h.prosperity:.2f}"
                            f" coh:{h.cohesion:.2f}"
                        )
                        if civ.dominant_beliefs:
                            lines.append(
                                f"           beliefs: {_format_beliefs(civ.dominant_beliefs)}"
                            )
                        if civ.culture_tags:
                            lines.append(
                                f"           culture: {_format_culture(civ.culture_tags)}"
                            )
    lines += ["", SEP]

    # ── Species ────────────────────────────────────────
    if state.species:
        lines.append("SPECIES")
        for sid, sp in state.species.items():
            w_obj = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin = w_obj.name if w_obj else "unknown"
            sapient_str = "sapient" if sp.sapient else "non-sapient"
            transplanted_str = "  [transplanted]" if sp.transplanted else ""
            lines.append(
                f"  {sp.name:16s} [{sapient_str}]  "
                f"origin:{origin}  "
                f"lifespan:{sp.lifespan_min:.0f}–{sp.lifespan_max:.0f}  "
                f"[{sp.condition.value}]{transplanted_str}"
            )
            if sp.bio_tags or sp.domain_tags:
                tag_line = ", ".join(sp.bio_tags + sp.domain_tags)
                lines.append(f"    {tag_line}")
        lines.append(SEP)

    # ── Notable Mortals ────────────────────────────────
    lines.append("NOTABLE MORTALS")
    for mid, mortal in state.mortals.items():
        if not is_mortal_visible(mortal):
            continue
        w_obj = state.locations.get(str(mortal.current_location))
        c_obj = (
            state.civilizations.get(str(mortal.civilization_id))
            if mortal.civilization_id else None
        )
        loc      = w_obj.name if w_obj else "?"
        if c_obj:
            loc += f" · {c_obj.name}"
        role_str = mortal.role.value.upper() if mortal.role != MortalRole.OTHER else "mortal"
        age_str = f"age:{mortal.chrono_age:.0f}"
        if mortal.bio_age != mortal.chrono_age:
            age_str += f"(bio:{mortal.bio_age:.0f})"
        sp_obj = state.species.get(str(mortal.species_id)) if mortal.species_id else None
        sp_note = f"  [{sp_obj.name}]" if sp_obj else ""
        prom_str = _prominence_label(mortal)
        vis_note = (
            f"  vis:{mortal.visibility:.2f}"
            if mortal.prominence < ALWAYS_VISIBLE_THRESHOLD else ""
        )
        lines.append(
            f"  {mortal.name:16s} [{role_str:7s}]  "
            f"align:{mortal.alignment:.2f}  {age_str}{sp_note}{vis_note}   {loc}"
        )
        lines.append(f"    {prom_str}")
        if mortal.personal_tags:
            lines.append(f"    Tags: {', '.join(mortal.personal_tags)}")
        if mortal.culture_tags:
            lines.append(f"    Culture: {_format_culture(mortal.culture_tags)}")

    lines += ["", SEP2]
    return "\n".join(lines)


# ─────────────────────────────────────────
# ACTION MENU
# Let the playtester browse and queue actions.
# ─────────────────────────────────────────

def build_intent_interactively(
    action_key: str,
    defn: ActionDefinition,
    state: SimulationState,
) -> tuple[ActionInstance, str] | None:
    """
    Prompt the playtester for intent fields appropriate
    to the chosen action. Returns (ActionInstance, display_summary)
    or None if they cancel.
    """
    print(f"\n  Action: {defn.name}")
    print(f"  {defn.description}")
    print(f"  Footprint cost: {defn.footprint_cost.total():.2f} total")
    if defn.essence_cost != 0.0:
        verb = "yields" if defn.essence_cost < 0 else "costs"
        print(f"  Essence: {verb} {abs(defn.essence_cost):.2f}")
    print()

    # ── issue_directive: target and proxius are the same selection ───────
    if action_key == "issue_directive":
        include_dormant = "include_dormant_proxius" in defn.tags
        already_directed = {
            str(ai.proxius_id)
            for ai in state.action_queue
            if isinstance(ai.intent, ProxiusDirectiveIntent) and ai.proxius_id is not None
        }
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and mid not in already_directed
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            print("  No Proxii available to receive a directive this tick.")
            return None
        print("  Issue directive to which Proxius?")
        for i, (mid, m) in enumerate(proxii):
            w_obj = state.locations.get(str(m.current_location))
            loc = w_obj.name if w_obj else "?"
            dormant_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            print(
                f"    {i+1}. {m.name:<16s}  align:{m.alignment:.2f}   {loc}{dormant_note}"
            )
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(proxii))
        if choice == 0:
            return None
        target_id = UUID(proxii[choice - 1][0])
        intent = _build_intent(action_key, defn, target_id, state)
        summary = f"{defn.name} → {_name_for_id(target_id, state)}"
        instance = ActionInstance(
            action_definition_id=defn.id,
            target_type=TargetType.MORTAL,
            target_id=target_id,
            timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id,
            proxius_id=target_id,
            intent=intent,
        )
        return instance, summary

    # ── Proxius-targeted actions: the Proxius IS the target ──────────────
    # Actions where requires_proxius=True and the Proxius is the sole valid
    # target (not a vehicle acting on something else). issue_directive is
    # handled above; all remaining requires_proxius actions follow this path.
    if defn.requires_proxius:
        include_dormant = "include_dormant_proxius" in defn.tags
        proxii = [
            (mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS
            and (m.status == MortalStatus.ACTIVE
                 or (include_dormant and m.status == MortalStatus.DORMANT))
        ]
        if not proxii:
            status_note = "active or dormant" if include_dormant else "active"
            print(f"  No {status_note} Proxii available for this action.")
            return None
        print("  Select Proxius:")
        for i, (mid, m) in enumerate(proxii):
            w_obj = state.locations.get(str(m.current_location))
            loc = w_obj.name if w_obj else "?"
            dormant_note = "  [DORMANT]" if m.status == MortalStatus.DORMANT else ""
            print(f"    {i+1}. {m.name:<16s}  align:{m.alignment:.2f}   {loc}{dormant_note}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(proxii))
        if choice == 0:
            return None
        proxius_id = UUID(proxii[choice - 1][0])
        intent = _build_intent(action_key, defn, proxius_id, state)
        summary = f"{defn.name} → {_name_for_id(proxius_id, state)}"
        instance = ActionInstance(
            action_definition_id=defn.id,
            target_type=TargetType.MORTAL,
            target_id=proxius_id,
            timestamp=state.universe.current_age,
            demiurge_id=state.demiurge.id,
            proxius_id=proxius_id,
            intent=intent,
        )
        return instance, summary

    # ── Target selection ──────────────────────────────
    target_id = None
    target_type = defn.valid_targets[0]  # Default; refined below

    if TargetType.MORTAL in defn.valid_targets and state.mortals:
        mortals = [
            (mid, m) for mid, m in state.mortals.items()
            if is_mortal_visible(m)
        ]
        if not mortals:
            print("  No mortals are currently within your perception.")
            return None
        print("  Select target mortal:")
        for i, (mid, m) in enumerate(mortals):
            w_obj  = state.locations.get(str(m.current_location))
            c_obj  = state.civilizations.get(str(m.civilization_id)) if m.civilization_id else None
            loc    = w_obj.name if w_obj else "?"
            if c_obj:
                loc += f" · {c_obj.name}"
            role_str = m.role.value if m.role != MortalRole.OTHER else "mortal"
            prom_str = _prominence_label(m)
            print(
                f"    {i+1}. {m.name:<16s} [{role_str}]  "
                f"align:{m.alignment:.2f}   {loc}  {prom_str}"
            )
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(mortals))
        if choice == 0:
            return None
        target_id = UUID(mortals[choice - 1][0])
        target_type = TargetType.MORTAL

    elif TargetType.CIVILIZATION in defn.valid_targets and state.civilizations:
        civs = list(state.civilizations.items())
        print("  Select target civilization:")
        for i, (cid, c) in enumerate(civs):
            w_obj = state.locations.get(str(c.origin_location_id)) if c.origin_location_id else None
            loc   = w_obj.name if w_obj else "?"
            print(f"    {i+1}. {c.name:<30s} [{c.scale.value}]  {loc}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(civs))
        if choice == 0:
            return None
        target_id = UUID(civs[choice - 1][0])
        target_type = TargetType.CIVILIZATION

    elif TargetType.LUMINARY in defn.valid_targets and state.luminaries:
        lums = list(state.luminaries.items())
        print("  Select target Luminary:")
        for i, (lid, l) in enumerate(lums):
            print(f"    {i+1}. {l.name}  [{l.temperament.value}]")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(lums))
        if choice == 0:
            return None
        target_id = UUID(lums[choice - 1][0])
        target_type = TargetType.LUMINARY

    elif TargetType.SPECIES in defn.valid_targets and state.species:
        species_list = list(state.species.items())
        print("  Select target species:")
        for i, (sid, sp) in enumerate(species_list):
            w_obj = state.locations.get(str(sp.origin_world_id)) if sp.origin_world_id else None
            origin = w_obj.name if w_obj else "unknown"
            sapient_str = "sapient" if sp.sapient else "non-sapient"
            print(f"    {i+1}. {sp.name:<16s} [{sapient_str}]  origin: {origin}")
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(species_list))
        if choice == 0:
            return None
        target_id = UUID(species_list[choice - 1][0])
        target_type = TargetType.SPECIES

    elif TargetType.UNDERREAL in defn.valid_targets:
        target_type = TargetType.UNDERREAL
        target_id = None

    elif TargetType.WORLD in defn.valid_targets and state.worlds:  # type: ignore[attr-defined]
        worlds = list(state.worlds.items())  # type: ignore[attr-defined]
        print("  Select target world:")
        for i, (wid, w) in enumerate(worlds):
            sys_obj  = state.locations.get(str(w.parent_id)) if w.parent_id else None
            sys_name = sys_obj.name if sys_obj else "?"
            n_civs   = len(w.civilization_ids)
            life_str = f"{n_civs} civilization(s)" if n_civs else "no life"
            print(
                f"    {i+1}. {w.name:<14s} [{w.condition.value}]  "
                f"{sys_name:<20s}  {life_str}"
            )
        print("    0. Cancel")
        choice = _prompt_int("  > ", 0, len(worlds))
        if choice == 0:
            return None
        target_id = UUID(worlds[choice - 1][0])
        target_type = TargetType.WORLD

    # ── Intent construction ───────────────────────────
    proxius_id = None
    intent = _build_intent(action_key, defn, target_id, state)

    # Actions that build intent interactively may cancel (return None).
    if intent is None and action_key == "explore_beliefs":
        return None

    summary = f"{defn.name}"
    if target_id:
        summary += f" → {_name_for_id(target_id, state)}"
    if isinstance(intent, ExploreBeliefIntent):
        summary += f" → {intent.domain_tag.split(':', 1)[-1]}"

    instance = ActionInstance(
        action_definition_id=defn.id,
        target_type=target_type,
        target_id=target_id,
        timestamp=state.universe.current_age,
        demiurge_id=state.demiurge.id,
        proxius_id=proxius_id,
        intent=intent,
    )
    return instance, summary


def _build_intent(
    action_key: str,
    defn: ActionDefinition,
    target_id,
    state: SimulationState,
):
    """Prompt for intent fields based on action category."""
    cat = defn.category

    if action_key == "explore_beliefs":
        return _build_explore_intent(state)

    if cat == ActionCategory.DIRECT_CREATION:
        if action_key == "seed_world":
            name = input("  Species name: ").strip() or "Life-Form Alpha"
            lifespan_min = _prompt_float("  Lifespan min (time units): ", 1.0, 100000.0, 100.0)
            lifespan_max = _prompt_float("  Lifespan max (time units): ", 1.0, 100000.0, 200.0)
            sapient_raw = input("  Sapient from the start? (y/n) [n]: ").strip().lower()
            sapient = sapient_raw == "y"
            tags_raw = input(
                "  Bio tags (comma-separated, e.g. bio:bipedal — blank to skip): "
            ).strip()
            bio_tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
            return SeedWorldIntent(
                species_name=name,
                lifespan_min=lifespan_min,
                lifespan_max=lifespan_max,
                sapient=sapient,
                bio_tags=bio_tags,
            )
        elif action_key == "uplift_species":
            dvs, imago_id = _prompt_domain_or_imago(state)
            return UpliftSpeciesIntent(
                species_id=target_id,
                domain_vectors=dvs,
                imago_node_id=imago_id,
            )

    elif cat == ActionCategory.SUBTLE_INFLUENCE:
        if action_key in ("whisper", "shape_dream"):
            dvs, imago_id = _prompt_domain_or_imago(state)
            if imago_id:
                concept = get_imago_registry().get_node(imago_id).name
            else:
                concept = input("  Concept to plant: ").strip() or "You could shape the future."
            return WhisperIntent(
                concept=concept,
                domain_vectors=dvs,
                framing=_prompt_framing(),
                imago_node_id=imago_id,
            )
        elif action_key == "nudge_probability":
            event = input("  Event to nudge: ").strip() or "Upcoming succession conflict"
            outcome = input("  Desired outcome: ").strip() or "The reformist faction prevails"
            dvs, imago_id = _prompt_domain_or_imago(state)
            return ProbabilityNudgeIntent(
                event_description=event,
                desired_outcome=outcome,
                domain_vectors=dvs,
                imago_node_id=imago_id,
            )
        elif action_key == "accelerate_development":
            aspect = input("  Which aspect to develop: ").strip() or "military doctrine"
            dvs, imago_id = _prompt_domain_or_imago(state)
            return DevelopmentIntent(
                domain_vectors=dvs,
                target_aspect=aspect,
                imago_node_id=imago_id,
            )

    elif cat == ActionCategory.PROXIUS_DIRECTION:
        if action_key == "issue_directive":
            goal = input("  Directive goal: ").strip() or "Strengthen the reformist faction"
            dvs, imago_id = _prompt_domain_or_imago(state)
            latitude = _prompt_float("  Latitude (0.0 strict – 1.0 open): ", 0.0, 1.0, 0.5)

            # If domain vectors were chosen, pick which civilization to promote them in.
            # Filter to civilizations on the Proxius's current world.
            target_civ_id = None
            if dvs:
                proxius = state.mortals.get(str(target_id)) if target_id else None
                loc_id = str(proxius.current_location) if proxius else None
                civs_here = [
                    (cid, c) for cid, c in state.civilizations.items()
                    if str(c.origin_location_id) == loc_id
                ] if loc_id else []

                if not civs_here:
                    print("  (No civilizations at this Proxius's location — domain vectors discarded.)")
                    dvs = []
                elif len(civs_here) == 1:
                    target_civ_id = UUID(civs_here[0][0])
                    print(f"  Target civilization: {civs_here[0][1].name}")
                else:
                    print("  Promote belief in which civilization?")
                    for i, (cid, c) in enumerate(civs_here):
                        print(f"    {i+1}. {c.name}  [{c.scale.value}]")
                    print("    0. Discard domain vectors")
                    civ_choice = _prompt_int("  > ", 0, len(civs_here))
                    if civ_choice > 0:
                        target_civ_id = UUID(civs_here[civ_choice - 1][0])
                    else:
                        dvs = []

            return ProxiusDirectiveIntent(
                goal_statement=goal,
                domain_vectors=dvs,
                latitude=latitude,
                target_civilization_id=target_civ_id,
                imago_node_id=imago_id,
            )

    elif cat == ActionCategory.UNDERREAL:
        if action_key == "harvest_essence":
            concept_type = input(
                "  Target concept type (enter to skip): "
            ).strip() or None
            concealment = _prompt_float(
                "  Concealment priority (0.0 fast/risky – 1.0 slow/safe): ",
                0.0, 1.0, 0.7
            )
            return EssenceHarvestIntent(
                target_concept_type=concept_type,
                concealment_priority=concealment,
            )
        elif action_key == "salvage_concept":
            desired = input("  What are you hoping to find: ").strip()
            worlds = list(state.worlds.items())  # type: ignore[attr-defined]
            print("  Target world for salvage:")
            for i, (wid, w) in enumerate(worlds):
                print(f"    {i+1}. {w.name}")
            choice = _prompt_int("  > ", 1, len(worlds))
            world_id = UUID(worlds[choice-1][0])
            dvs, imago_id = _prompt_domain_or_imago(state)
            return SalvageIntent(
                desired_concept=desired,
                target_world_id=world_id,
                domain_vectors=dvs,
                imago_node_id=imago_id,
            )

    elif cat == ActionCategory.OVERT_MIRACLE:
        if action_key in ("manifest_omen", "divine_manifestation"):
            sign = input("  Sign description (what occurs): ").strip() or "A celestial anomaly appears"
            interpretation = (
                input("  Intended interpretation: ").strip() or "The gods demand action"
            )
            dvs, imago_id = _prompt_domain_or_imago(state)
            civ_scope = None
            if target_id:
                tid_str = str(target_id)
                if tid_str in state.civilizations:
                    civ_scope = target_id
                elif tid_str in state.mortals:
                    civ_scope = state.mortals[tid_str].civilization_id
            return OmenIntent(
                sign_description=sign,
                intended_interpretation=interpretation,
                domain_vectors=dvs,
                framing=_prompt_framing(),
                civilization_scope=civ_scope,
                imago_node_id=imago_id,
            )

    elif cat == ActionCategory.LUMINARY_RELATIONS:
        subject = input("  Subject of communication: ").strip() or "Current universe state"
        position = input("  Your position / what you want: ").strip() or "Continued patience"
        tone = input("  Tone (deferential/confident/urgent/firm): ").strip() or "deferential"
        return LuminaryPetitionIntent(
            subject=subject,
            your_position=position,
            tone=tone,
        )

    # No structured intent needed (scry, appoint_proxius, etc.)
    return None


def _format_beliefs(beliefs: "dict[str, float]") -> str:
    """Format a weighted belief dict as 'tag(0.73)  tag(0.45)', sorted by strength."""
    if not beliefs:
        return ""
    return "  ".join(
        f"{tag}({v:.2f})"
        for tag, v in sorted(beliefs.items(), key=lambda kv: -kv[1])
    )


def _format_culture(tags: "dict[str, float]") -> str:
    """Format culture tags as a comma-separated list, sorted by strength, prefix stripped."""
    if not tags:
        return ""
    return ", ".join(
        t.split(":", 1)[-1]
        for t, _ in sorted(tags.items(), key=lambda kv: -kv[1])
    )


def _prominence_label(mortal: "NotableMortal") -> str:
    """Short display string showing role(s) and prominence tier."""
    if not mortal.prominence_roles or mortal.prominence_roles == [MortalProminence.NONE]:
        role_part = "no notable role"
    else:
        role_part = " · ".join(r.value.title() for r in mortal.prominence_roles)
    always = mortal.prominence >= ALWAYS_VISIBLE_THRESHOLD
    tier = "always visible" if always else f"prominence:{mortal.prominence:.2f}"
    return f"{role_part}  [{tier}]"


def _build_explore_intent(state: SimulationState) -> ExploreBeliefIntent | None:
    """
    Show explorable domains (accessible but not yet unlocked) and
    return an ExploreBeliefIntent for the chosen one.
    """
    dreg = get_domain_registry()
    lum_info, fellow_tags, all_lum_canonical = _get_lum_domain_context(state)

    accessible = dreg.demiurge_accessible(
        all_lum_canonical,
        state.demiurge.unlocked_domain_tags,
    )
    already_unlocked = set(state.demiurge.unlocked_domain_tags)
    explorable = [t for t in accessible if t not in already_unlocked]

    if not explorable:
        print("  No new domains available for exploration.")
        print("  (All accessible domains are already part of your explored beliefs.)")
        return None

    lum_col_w = 10
    print()
    print(f"  {'Domain':<22}", end="")
    for lum, _ in lum_info:
        print(f"  {lum.name:>{lum_col_w}}", end="")
    print("   (approval if promoted)")
    print("  " + "─" * (24 + len(lum_info) * (lum_col_w + 2)))

    for i, tag in enumerate(explorable):
        short = tag.split(":", 1)[1]
        print(f"  {i+1:3d}.  {short:<18}", end="")
        for lum, lum_tags in lum_info:
            lid = str(lum.id)
            if not lum_tags:
                print(f"  {'·':>{lum_col_w}}", end="")
                continue
            approval = dreg.luminary_approval(
                tag, lum_tags,
                fellow_lum_tags=fellow_tags[lid],
                temperament=lum.temperament.value,
            )
            if abs(approval) < 0.01:
                print(f"  {'·':>{lum_col_w}}", end="")
            else:
                print(f"  {approval:>+{lum_col_w}.2f}", end="")
        print()

    print("    0. Cancel")
    choice = _prompt_int("  > ", 0, len(explorable))
    if choice == 0:
        return None

    tag = explorable[choice - 1]
    return ExploreBeliefIntent(domain_tag=tag)


def _get_lum_domain_context(state: SimulationState):
    """
    Returns (lum_info, fellow_tags, all_lum_canonical_tags) where:
      lum_info  — list of (Luminary, canonical_tag_list) in iteration order
      fellow_tags — dict[lid_str -> set[str]] of other Luminaries' canonical tags
      all_lum_canonical_tags — flat list of all Luminary canonical tags (deduped)
    """
    dreg = get_domain_registry()
    lum_info: list[tuple] = []
    per_lum: dict[str, list[str]] = {}

    for lid, lum in state.luminaries.items():
        tags: list[str] = []
        for did in lum.domains:
            d = state.domains.get(str(did))
            if d:
                tags.extend(t for t in d.tags if dreg.is_canonical(t))
        per_lum[lid] = tags
        lum_info.append((lum, tags))

    fellow_tags: dict[str, set[str]] = {}
    for lid in per_lum:
        fellow_tags[lid] = set(
            t for other_lid, other_tags in per_lum.items()
            if other_lid != lid
            for t in other_tags
        )

    seen: set[str] = set()
    all_canonical: list[str] = []
    for tags in per_lum.values():
        for t in tags:
            if t not in seen:
                seen.add(t)
                all_canonical.append(t)

    return lum_info, fellow_tags, all_canonical


def _prompt_domain_tag(state: SimulationState) -> str | None:
    """
    Numbered selection list of domain tags accessible to the Demiurge,
    annotated with each Luminary's approval/disapproval rating.
    Returns the selected tag or None to skip. Does NOT prompt for direction.
    """
    dreg = get_domain_registry()
    lum_info, fellow_tags, all_lum_canonical = _get_lum_domain_context(state)

    accessible = dreg.demiurge_accessible(
        all_lum_canonical,
        state.demiurge.unlocked_domain_tags,
    )

    if not accessible:
        print("  No domain tags are currently accessible.")
        return None

    lum_col_w = 10
    print()
    print(f"  {'Domain':<22}", end="")
    for lum, _ in lum_info:
        print(f"  {lum.name:>{lum_col_w}}", end="")
    print()
    print("  " + "─" * (24 + len(lum_info) * (lum_col_w + 2)))

    unlocked_set = set(state.demiurge.unlocked_domain_tags)

    for i, tag in enumerate(accessible):
        short = tag.split(":", 1)[1]
        marker = "*" if tag in unlocked_set else " "
        print(f"  {i+1:3d}.{marker}{short:<18}", end="")
        for lum, lum_tags in lum_info:
            lid = str(lum.id)
            if not lum_tags:
                print(f"  {'·':>{lum_col_w}}", end="")
                continue
            approval = dreg.luminary_approval(
                tag, lum_tags,
                fellow_lum_tags=fellow_tags[lid],
                temperament=lum.temperament.value,
            )
            if abs(approval) < 0.01:
                print(f"  {'·':>{lum_col_w}}", end="")
            else:
                print(f"  {approval:>+{lum_col_w}.2f}", end="")
        print()

    if unlocked_set:
        print("  (* = unlocked by you)")
    print(f"    0. No domain influence (skip)")

    choice = _prompt_int("  > ", 0, len(accessible))
    if choice == 0:
        return None
    return accessible[choice - 1]


def _prompt_imago_select(nodes: list) -> object | None:
    """
    Picker for available Imago nodes for the chosen domain tree.
    Shows name, blurb, and mechanics. Returns the chosen ImagoNode or None
    to fall back to manual direction.
    """
    print()
    print("  Frame this action through an Imago:")
    for i, node in enumerate(nodes):
        print(f"    {i+1}. {node.name}")
        if node.tooltip_blurb:
            print(f'         "{node.tooltip_blurb}"')
        domain_parts = [
            (t.split(":", 1)[1], v)
            for t, v in node.mechanics.items()
            if t.startswith("domain:")
        ]
        culture_parts = [
            (t.split(":", 1)[1], v)
            for t, v in node.mechanics.items()
            if t.startswith("culture:")
        ]
        if domain_parts:
            d_str = ", ".join(
                f"{t}:{'+' if v > 0 else ''}{v:.2f}" for t, v in domain_parts
            )
            print(f"         domains: [{d_str}]")
        if culture_parts:
            c_str = ", ".join(
                f"{t}:{'+' if v > 0 else ''}{v:.2f}" for t, v in culture_parts
            )
            print(f"         culture: [{c_str}]")
    print(f"    0. No Imago — set direction manually")

    choice = _prompt_int("  > ", 0, len(nodes))
    if choice == 0:
        return None
    return nodes[choice - 1]


def _prompt_domain_or_imago(
    state: SimulationState,
) -> tuple[list[DomainVector], str | None]:
    """
    Step 1 — domain tag selection (with Luminary approval ratings).
    Step 2 — if the Demiurge has Imagines unlocked for that tree, offer the
              Imago picker; Imago mechanics supply all direction vectors.
              Otherwise fall back to the manual direction prompt.

    Returns (domain_vectors, imago_node_id).
    imago_node_id is non-None only when an Imago was chosen; callers use this
    to suppress free-text prompts (concept, goal) that the Imago answers implicitly.
    """
    tag = _prompt_domain_tag(state)
    if tag is None:
        return [], None

    tree = tag.split(":", 1)[1]  # "domain:order" -> "order"
    ireg = get_imago_registry()

    available = [
        ireg.get_node(nid)
        for nid in state.demiurge.unlocked_imagines
        if ireg.get_node(nid) and ireg.get_node(nid).tree == tree
    ]

    if available:
        node = _prompt_imago_select(available)
        if node is not None:
            dvs = [
                DomainVector(domain_tag=t, direction=v)
                for t, v in node.mechanics.items()
                if t.startswith("domain:")
            ]
            return dvs, node.node_id

    # Fallback: single vector with a manually chosen direction.
    direction = _prompt_float(
        "  Direction  -1.0 (suppress) ──► +1.0 (promote): ", -1.0, 1.0, 0.5
    )
    return [DomainVector(domain_tag=tag, direction=direction)], None


def _prompt_framing():
    from action_core import Framing
    options = [f.value for f in Framing]
    print(f"  Framing: {', '.join(options)}")
    choice = input("  > ").strip().lower()
    return Framing(choice) if choice in options else Framing.INSPIRATIONAL


def _prompt_int(prompt: str, lo: int, hi: int) -> int:
    while True:
        try:
            val = int(input(prompt))
            if lo <= val <= hi:
                return val
        except ValueError:
            pass
        print(f"  Enter a number between {lo} and {hi}.")


def _prompt_float(prompt: str, lo: float, hi: float, default: float) -> float:
    raw = input(f"{prompt}[{default}] ").strip()
    if not raw:
        return default
    try:
        val = float(raw)
        return max(lo, min(hi, val))
    except ValueError:
        return default


def _name_for_id(uid: UUID, state: SimulationState) -> str:
    sid = str(uid)
    for d in [state.mortals, state.civilizations, state.locations,
              state.luminaries]:
        if sid in d:
            obj = d[sid]
            return getattr(obj, "name", sid[:8])
    return sid[:8]


# ─────────────────────────────────────────
# SESSION LOG
# ─────────────────────────────────────────

class SessionLog:
    def __init__(self, path: Path):
        self.path = path
        self.entries: list[str] = []
        self.path.write_text(
            f"DEMIURGE SESSION LOG\n"
            f"Started: {datetime.now().isoformat()}\n"
            f"{'='*60}\n\n"
        )

    def write(self, text: str):
        self.entries.append(text)
        with self.path.open("a") as f:
            f.write(text + "\n")

    def write_state(self, state: SimulationState):
        self.write(display_state(state))

    def write_tick(self, result: TickResult):
        self.write(display_tick_result(result))

    def write_action(self, summary: str):
        self.write(f"  > QUEUED: {summary}")

    def finalize(self, state: SimulationState, result: TickResult | None):
        self.write("\n" + "="*60)
        self.write("SESSION END")
        self.write(f"Final age: {state.universe.current_age:.1f}")
        self.write(f"Final tick: {state.tick_number}")
        if result and result.terminal.triggered:
            self.write(f"Outcome: {result.terminal.condition.value}")
        self.write(f"Ended: {datetime.now().isoformat()}")


# ─────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────

def _peek_db_meta(path: Path) -> dict:
    """Return {name, description, tick_number} from a scenario/save .db file."""
    try:
        import sqlite3 as _sq
        with _sq.connect(path) as _c:
            row = _c.execute(
                "SELECT name, description, tick_number FROM scenario_meta LIMIT 1"
            ).fetchone()
        if row:
            return {
                "name": row[0] or path.stem,
                "description": row[1] or "",
                "tick_number": row[2] if row[2] is not None else 0,
            }
    except Exception:
        pass
    return {"name": path.stem, "description": "", "tick_number": 0}


def _select_scenario() -> SimulationState:
    """
    Startup menu — list saves and scenarios.
    Returns a fully constructed SimulationState.
    """
    saves_dir     = Path(__file__).parent / "saves"
    scenarios_dir = Path(__file__).parent / "scenarios"
    save_files     = sorted(saves_dir.glob("*.db"))     if saves_dir.exists()     else []
    scenario_files = sorted(scenarios_dir.glob("*.db")) if scenarios_dir.exists() else []

    all_files: list[Path] = save_files + scenario_files

    print()
    print("  LOAD GAME")
    print("  ────────────────────────────────────────────────")

    idx = 1
    if save_files:
        print("  Saves:")
        for path in save_files:
            meta = _peek_db_meta(path)
            tick_str = f"  [tick {meta['tick_number']}]" if meta["tick_number"] else ""
            print(f"    [{idx}] {meta['name']}{tick_str}")
            if meta["description"]:
                print(f"         {meta['description']}")
            idx += 1
        print()

    if scenario_files:
        print("  Scenarios:")
        for path in scenario_files:
            meta = _peek_db_meta(path)
            print(f"    [{idx}] {meta['name']}")
            if meta["description"]:
                print(f"         {meta['description']}")
            idx += 1
        print()
    elif not save_files:
        print("  (no saves or scenario files found)")
        print()

    print("  [Q] Quit")
    print()

    max_idx = len(all_files)
    while True:
        raw = input("  > ").strip().upper()

        if raw == "Q":
            raise SystemExit(0)

        if raw.isdigit():
            n = int(raw) - 1
            if 0 <= n < max_idx:
                path = all_files[n]
                print(f"  Loading {path.name}...")
                return load_scenario(path)

        if max_idx:
            print(f"  Invalid choice — enter 1–{max_idx} or Q.")
        else:
            print("  Invalid choice — enter Q.")


def _save_game(state: SimulationState) -> None:
    saves_dir = Path(__file__).parent / "saves"
    saves_dir.mkdir(exist_ok=True)

    default_name = f"save_tick{state.tick_number}"
    raw = input(f"  Save name [{default_name}]: ").strip()
    name = raw if raw else default_name

    db_path = saves_dir / f"{name}.db"
    if db_path.exists():
        confirm = input(f"  '{name}.db' already exists — overwrite? [y/n]: ").strip().lower()
        if confirm != "y":
            print("  Save cancelled.")
            return

    age_str = f"{state.universe.current_age:.1f}"
    description = f"Tick {state.tick_number}  |  Age {age_str}"
    export_scenario(state, db_path, scenario_name=name, description=description)
    print(f"  Saved to saves/{name}.db")


def main():
    print(SEP2)
    print("  DEMIURGE")
    print(SEP2)

    state = _select_scenario()
    print()

    log_path = Path(os.path.join("logs", f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"))
    log = SessionLog(log_path)
    print(f"  Logging to: {log_path}\n")

    loop  = TickLoop()
    library = loop._action_library
    last_result: TickResult | None = None

    # Map action keys to definitions with a stable index
    action_index: list[tuple[str, ActionDefinition]] = list(library.items())

    briefing = display_briefing(state)
    print(briefing)
    log.write(briefing)
    print(display_state(state))
    log.write_state(state)

    while True:
        print()
        print("  ACTIONS")
        print("  ────────────────────────────────────────────────")
        print("  [A] Browse and queue actions")
        print("  [O] Manage ongoing actions")
        print("  [T] Advance time (execute queued actions + tick)")
        print("  [S] Show current state")
        print("  [B] Show scenario briefing")
        print("  [V] Save game")
        print("  [Q] Quit")
        status_parts = []
        if state.action_queue:
            status_parts.append(f"{len(state.action_queue)} queued")
        if state.ongoing_actions:
            status_parts.append(f"{len(state.ongoing_actions)} ongoing")
        if status_parts:
            print(f"\n  {' | '.join(status_parts)}")
        print()

        cmd = input("  > ").strip().upper()

        if cmd == "Q":
            log.finalize(state, last_result)
            print(f"\n  Session saved to {log_path}")
            break

        elif cmd == "S":
            out = display_state(state)
            print(out)
            log.write(out)

        elif cmd == "B":
            out = display_briefing(state)
            print(out)
            log.write(out)

        elif cmd == "A":
            _action_browser(state, library, action_index, log)

        elif cmd == "O":
            _manage_ongoing_actions(state, library)

        elif cmd == "V":
            _save_game(state)

        elif cmd == "T":
            print("\n  Advancing time...")
            state, result = loop.advance(state)
            last_result = result
            out = display_tick_result(result)
            print(out)
            log.write_tick(result)

            if result.terminal.triggered:
                log.finalize(state, result)
                print(f"\n  Session saved to {log_path}")
                break
        else:
            print("  Unknown command.")


def _manage_ongoing_actions(
    state: SimulationState,
    library: dict,
):
    if not state.ongoing_actions:
        print("\n  No ongoing actions.")
        return

    print("\n  ONGOING ACTIONS")
    items = list(state.ongoing_actions.items())
    for i, (cat_val, oa) in enumerate(items):
        cat_label = cat_val.replace("_", " ").title()
        defn = library.get(oa.action_key)
        name = defn.name if defn else oa.action_key
        target_str = ""
        if oa.target_id:
            target_str = f" → {oa.target_id}"
        print(
            f"    {i+1}. [{cat_label}] {name}{target_str}"
            f"  ({oa.executed_ticks}/{oa.ticks_active} ticks executed)"
        )
    print("    0. Back")

    choice = _prompt_int("  Stop which? > ", 0, len(items))
    if choice == 0:
        return
    cat_val, oa = items[choice - 1]
    del state.ongoing_actions[cat_val]
    defn = library.get(oa.action_key)
    name = defn.name if defn else oa.action_key
    print(f"\n  Stopped ongoing: {name}")


def _action_browser(
    state: SimulationState,
    library: dict,
    action_index: list,
    log: SessionLog,
):
    # Group by category for readability
    categories: dict[ActionCategory, list] = {}
    for key, defn in action_index:
        categories.setdefault(defn.category, []).append((key, defn))

    # Build a map of already-queued categories for this tick
    key_by_id = {str(v.id): k for k, v in library.items()}
    queued_cats: dict[str, str] = {}  # category.value -> action name that claimed it
    for ai in state.action_queue:
        k = key_by_id.get(str(ai.action_definition_id))
        if k and k in library:
            dq = library[k]
            queued_cats[dq.category.value] = dq.name

    print("\n  ACTION CATEGORIES")
    cat_list = list(categories.items())
    for i, (cat, _) in enumerate(cat_list):
        used = queued_cats.get(cat.value)
        ongoing = state.ongoing_actions.get(cat.value)
        if used:
            annotation = f"  [used: {used}]"
        elif ongoing:
            od = library.get(ongoing.action_key)
            oname = od.name if od else ongoing.action_key
            annotation = f"  [ongoing: {oname} ({ongoing.executed_ticks}x)]"
        else:
            annotation = ""
        print(f"    {i+1}. {cat.value.replace('_',' ').title()}{annotation}")
    print("    0. Back")

    cat_choice = _prompt_int("  > ", 0, len(cat_list))
    if cat_choice == 0:
        return

    cat, actions = cat_list[cat_choice - 1]

    # If there's an ongoing action in this category, offer management options first
    ongoing = state.ongoing_actions.get(cat.value)
    if ongoing:
        od = library.get(ongoing.action_key)
        oname = od.name if od else ongoing.action_key
        print(
            f"\n  [ONGOING] {oname}  "
            f"({ongoing.executed_ticks}x executed, {ongoing.ticks_active} ticks old)"
        )
        print("    1. Stop ongoing action (then pick a new one)")
        print("    2. Override this tick (pick action; ongoing resumes next tick)")
        print("    0. Leave it running (back)")
        oc = _prompt_int("  > ", 0, 2)
        if oc == 0:
            return
        if oc == 1:
            del state.ongoing_actions[cat.value]
            print(f"  Stopped: {oname}")

    print(f"\n  {cat.value.upper()}")
    for i, (key, defn) in enumerate(actions):
        fp_total = defn.footprint_cost.total()
        essence_str = ""
        if defn.essence_cost != 0:
            verb = "↑" if defn.essence_cost < 0 else "↓"
            essence_str = f"  Ess{verb}{abs(defn.essence_cost):.1f}"
        persist_tag = "  [can persist]" if "can_persist" in defn.tags else ""
        stub_tag    = "  [not yet implemented]" if key in _STUB_ACTIONS else ""
        print(
            f"    {i+1}. {defn.name:35s}"
            f"  FP:{fp_total:.2f}{essence_str}"
            f"  [{defn.reliability.value}]{persist_tag}{stub_tag}"
        )
    print("    0. Back")

    action_choice = _prompt_int("  > ", 0, len(actions))
    if action_choice == 0:
        return

    key, defn = actions[action_choice - 1]

    # Block stub actions before any intent prompting
    if key in _STUB_ACTIONS:
        print(f"\n  {defn.name} is not yet implemented.")
        print(f"  {defn.description}")
        print("  This action requires systems that are planned but not yet built.")
        return

    # Enforce one action per category per tick
    if defn.category.value in queued_cats:
        existing = queued_cats[defn.category.value]
        print(
            f"\n  Blocked: '{existing}' is already queued in this category this tick."
        )
        return

    result = build_intent_interactively(key, defn, state)
    if result is None:
        print("  Cancelled.")
        return

    instance, summary = result

    # For can_persist actions, offer to make it an ongoing action
    if "can_persist" in defn.tags:
        print(f"\n  Make '{defn.name}' persistent? It will auto-execute each tick.")
        persist_choice = input("  [y/n] > ").strip().lower()
        if persist_choice == "y":
            state.ongoing_actions[defn.category.value] = OngoingAction(
                action_key=key,
                action_definition_id=defn.id,
                target_type=instance.target_type,
                target_id=instance.target_id,
                proxius_id=instance.proxius_id,
                intent=instance.intent,
                ticks_active=0,
                started_at_tick=state.tick_number,
            )
            log.write_action(f"[ONGOING SET] {summary}")
            print(f"\n  Ongoing: {summary}")
            return

    state.action_queue.append(instance)
    log.write_action(summary)
    print(f"\n  Queued: {summary}")


if __name__ == "__main__":
    main()
