from __future__ import annotations
import math
import random
from uuid import UUID
from typing import TYPE_CHECKING

from core.action_core import StateMutation, MutationType
from core.agent_core import AgentActionChoice
from core.universe_core import MortalRole, MortalStatus
from logic.belief_propagation import emit_lineage_bleed, BELIEF_CAP
from logic.sim_utils import pop_domain_receptivity, resolve_world_id_for as _resolve_world_id_for
from utilities.imago_registry import get_registry as get_imago_registry

if TYPE_CHECKING:
    from logic.tick_logic import SimulationState, TickConfig


def resolve_proxius_agents(
    state: "SimulationState",
    phase_rng: random.Random,
    cfg: "TickConfig",
) -> tuple[list[StateMutation], list[str]]:
    """
    Phase 2.5 — autonomous Proxius agent actions.
    Each active Proxius with an active_goal chooses and executes one
    action per tick, weighted by dedication (alignment × leeway).
    Generates StateMutations directly; does not go through ActionInstance machinery.
    Returns (mutations, agent_narratives) where agent_narratives are REPORT_TO_DEMIURGE
    entries that should be surfaced in the tick log.
    """
    mutations: list[StateMutation] = []
    agent_narratives: list[str] = []

    for mortal in state.mortals.values():
        if mortal.role != MortalRole.PROXIUS:
            continue
        if mortal.status != MortalStatus.ACTIVE:
            continue
        goal = mortal.active_goal
        if goal is None:
            continue

        # ── Milestone checks (run every tick before the frequency gate) ──────
        # Individual flags fire once; combined-success fires and clears the goal.
        # Ordering: individual checks first (may reset petition clock), then
        # combined check, then petition abandonment — so a same-tick double
        # completion fires combined success before abandonment can fire.

        _pop_a_ms = state.pops.get(str(goal.source_pop_id)) if goal.source_pop_id else None
        _pop_b_ms = state.pops.get(str(goal.goal_pop_id))   if goal.goal_pop_id   else None
        if goal.imago_node_id:
            _ms_node = get_imago_registry().get_node(goal.imago_node_id)
            _ms_name = _ms_node.name if _ms_node else goal.imago_node_id
            _imago_ref_ms = f"§imago§{goal.imago_node_id}§{_ms_name}§"
        else:
            _imago_ref_ms = "their directive"

        # (A) Belief cap milestone
        if not goal.pop_b_belief_cap_reached and _pop_b_ms is not None and goal.domain_vectors:
            core_dv = max(
                (dv for dv in goal.domain_vectors if dv.direction > 0),
                key=lambda dv: dv.direction,
                default=None,
            )
            # Threshold slightly below BELIEF_CAP: Phase 1 decay runs before
            # Phase 2.5, so the reading can sit ~0.01–0.02 below 0.9 even when
            # the cap was hit last tick.
            if core_dv and _pop_b_ms.dominant_beliefs.get(core_dv.domain_tag, 0.0) >= BELIEF_CAP - 0.02:
                goal.pop_b_belief_cap_reached = True
                goal.petition_pending         = True
                goal.petition_pending_ticks   = 0
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=+0.05,
                    note=f"{mortal.name} — Pop B core domain at belief cap",
                ))
                domain_short = core_dv.domain_tag.split(":", 1)[1]
                agent_narratives.append(
                    f"[Tick {state.tick_number + 1}] {mortal.name}: "
                    f"The splinter community has fully embraced {domain_short} "
                    f"under {_imago_ref_ms}. Still growing their numbers. "
                    f"Awaiting guidance."
                )

        # (B) Size goal milestone — Pop B >= 55% of Pop A's current size
        if (
            not goal.pop_b_size_goal_reached
            and _pop_a_ms is not None
            and _pop_b_ms is not None
            and _pop_b_ms.size_fractional >= 0.55 * _pop_a_ms.size_fractional
        ):
            goal.pop_b_size_goal_reached  = True
            goal.petition_pending         = True
            goal.petition_pending_ticks   = 0
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=mortal.id,
                field="alignment",
                delta=+0.05,
                note=f"{mortal.name} — Pop B has reached 55% of Pop A's size",
            ))
            agent_narratives.append(
                f"[Tick {state.tick_number + 1}] {mortal.name}: "
                f"The {_imago_ref_ms} community has grown to a self-sustaining size. "
                f"Awaiting new orders."
            )

        # (C) Combined success — both milestones met: immediate clearance
        if goal.pop_b_belief_cap_reached and goal.pop_b_size_goal_reached:
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=mortal.id,
                field="alignment",
                delta=+0.08,
                note=f"{mortal.name} — full mission success",
            ))
            mutations.append(StateMutation(
                mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                target_id=mortal.id,
                field="active_goal",
                note=f"{mortal.name} mission complete — goal cleared",
            ))
            agent_narratives.append(
                f"[Tick {state.tick_number + 1}] {mortal.name} reports: "
                f"The {_imago_ref_ms} directive is fulfilled — "
                f"the community is established and their convictions run deep. "
                f"Standing by for a new purpose."
            )
            continue

        # Petition abandonment: after milestones so a same-tick completion
        # fires combined success before the 5-tick clock can trigger.
        if goal.petition_pending:
            goal.petition_pending_ticks += 1
            if goal.petition_pending_ticks >= 5:
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                    target_id=mortal.id,
                    field="active_goal",
                    note=f"{mortal.name} abandoned goal after petition ignored for 5 ticks",
                ))
                agent_narratives.append(
                    f"[Tick {state.tick_number + 1}] {mortal.name} has abandoned their directive — "
                    f"no response to petition for {goal.petition_pending_ticks} ticks."
                )
                continue

        # Dedication: high alignment + low latitude → near-certain, frequent action
        dedication = mortal.alignment * (1.0 - goal.latitude * 0.3)
        dedication = max(0.0, min(1.0, dedication))

        # Frequency gate — probabilistic skip
        if phase_rng.random() > dedication:
            goal.last_action = AgentActionChoice.NOTHING
            goal.last_action_tick = state.tick_number
            goal.consecutive_promote_count = 0
            goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)
            continue

        # ── Research goal branch (Commission Inquiry) ──
        if goal.research_domain:
            tag = goal.research_domain
            cap = _compute_revelation_cap(state, tag)
            pool = state.demiurge.revelation_pools.get(tag, 0.0)
            if cap == 0.0 or pool >= cap:
                # Tree complete or pool full — clear goal
                mutations.append(StateMutation(
                    mutation_type=MutationType.PROXIUS_GOAL_CLEARED,
                    target_id=mortal.id,
                    field="active_goal",
                    note=f"{mortal.name} completed Domain research on {tag}",
                ))
                short = tag.split(":", 1)[1].title() if ":" in tag else tag.title()
                goal.report_log = (goal.report_log + [
                    f"[Tick {state.tick_number + 1}] {mortal.name}: Research on {short} is complete. Awaiting a new directive."
                ])[-5:]
                goal.last_action = AgentActionChoice.RESEARCH_DOMAIN
                goal.last_action_tick = state.tick_number
            else:
                base_rev = 2.0
                expr = _compute_local_expression(state, tag, mortal.current_location)
                loc_bonus = round(expr * 2.0, 2)
                belief_bonus = 1.0 if mortal.belief_tags.get(tag, 0.0) >= 0.4 else 0.0
                delta = round(min(base_rev + loc_bonus + belief_bonus, cap - pool), 2)
                mutations.append(StateMutation(
                    mutation_type=MutationType.REVELATION_GAINED,
                    target_id=state.demiurge.id,
                    field=tag,
                    delta=delta,
                    note=f"{mortal.name} research on {tag}: +{delta} Revelation",
                ))
                goal.last_action = AgentActionChoice.RESEARCH_DOMAIN
                goal.last_action_tick = state.tick_number
            continue

        # Action weight table
        already_audited = str(mortal.id) in state.proxii_audited_this_tick
        has_goal_pop    = goal.goal_pop_id is not None
        if has_goal_pop:
            _bcr = goal.pop_b_belief_cap_reached
            _sgr = goal.pop_b_size_goal_reached
            if _bcr and not _sgr:
                # Beliefs at cap but still growing: shift weight toward size drain
                promote_w = 0.50
                bolster_w = 0.15
            elif _sgr and not _bcr:
                # Size met but beliefs still building: shift weight toward bolstering
                promote_w = 0.15
                bolster_w = 0.50
            elif _bcr and _sgr:
                # Both met — combined-success should have fired; defensive fallback
                promote_w = 0.10
                bolster_w = 0.10
            else:
                # Normal: balanced between deepening beliefs and growing size
                promote_w = 0.30
                bolster_w = 0.40
            take_stock_w = 0.08
            report_w     = 0.0 if already_audited else (0.08 + (1.0 - goal.latitude) * 0.10)
            petition_w   = (
                min(0.25, 0.03 + goal.stagnation_counter * 0.03)
                if not goal.petition_pending else 0.0
            )
            nothing_w    = max(0.0, 0.09 - dedication * 0.06)
        else:
            # No splinter yet: laser-focused on creating the first split
            promote_w    = 0.75
            bolster_w    = 0.0
            take_stock_w = 0.06
            report_w     = 0.0 if already_audited else (0.06 + (1.0 - goal.latitude) * 0.08)
            petition_w   = 0.03 if not goal.petition_pending else 0.0
            nothing_w    = max(0.0, 0.10 - dedication * 0.08)

        weights = [promote_w, bolster_w, take_stock_w, report_w, petition_w, nothing_w]
        choices = [
            AgentActionChoice.PROMOTE_DOMAIN,
            AgentActionChoice.BOLSTER_BELIEFS,
            AgentActionChoice.TAKE_STOCK,
            AgentActionChoice.REPORT_TO_DEMIURGE,
            AgentActionChoice.PETITION_FOR_RELIEF,
            AgentActionChoice.NOTHING,
        ]
        chosen = phase_rng.choices(choices, weights=weights, k=1)[0]
        goal.last_action = chosen
        goal.last_action_tick = state.tick_number

        if chosen == AgentActionChoice.PROMOTE_DOMAIN and goal.domain_vectors:
            goal.consecutive_promote_count += 1
            goal.effectiveness_bonus = min(0.30, goal.consecutive_promote_count * 0.05)
            base_rate = 0.06

            if goal.source_pop_id:
                # ── Pop-level preaching path ──────────────────────────
                pop_a = state.pops.get(str(goal.source_pop_id))
                # Cross-civ preaching: half effectiveness when Proxius preaches to a
                # community outside their own civilization.
                _proxius_origin_pop = state.pops.get(str(mortal.pop_id)) if mortal.pop_id else None
                _proxius_civ = str(_proxius_origin_pop.civilization_id) if _proxius_origin_pop and _proxius_origin_pop.civilization_id else None
                if pop_a and _proxius_civ and str(pop_a.civilization_id) != _proxius_civ:
                    base_rate *= 0.5
                if pop_a is None:
                    # Source Pop gone — force petition
                    goal.petition_pending = True
                    goal.consecutive_promote_count = 0
                    goal.effectiveness_bonus = 0.0
                elif goal.goal_pop_id is None:
                    # ── First success: create Pop B ───────────────────
                    # 5-tick escalating pre-shift applied to Pop A's beliefs
                    # plus culture synergy bonus from Imāgō node mechanics
                    ireg = get_imago_registry()
                    imago_node = ireg.get_node(goal.imago_node_id) if goal.imago_node_id else None
                    culture_mechanics = {}
                    if imago_node:
                        culture_mechanics = {
                            k: v for k, v in imago_node.mechanics.items()
                            if k.startswith("culture:")
                        }

                    new_beliefs = dict(pop_a.dominant_beliefs)
                    for dv in goal.domain_vectors:
                        belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                        # Culture synergy bonus: sum strength × pop A's culture level
                        culture_bonus = sum(
                            c_strength * pop_a.culture_tags.get(c_tag, 0.0)
                            for c_tag, c_strength in culture_mechanics.items()
                            if dv.direction > 0
                        )
                        # Apply 2 escalating tick-steps with inertia at each step
                        # so the initial state respects the same resistance as live bolstering.
                        current = new_beliefs.get(dv.domain_tag, 0.0)
                        for i in range(1, 3):
                            tick_rate = base_rate * (1.0 + i * 0.05) + belief_affinity * 0.02
                            raw_delta = (tick_rate + culture_bonus / 5) * dv.direction
                            raw_delta *= belief_inertia(current, raw_delta)
                            cap = BELIEF_CAP if raw_delta > 0 else 1.0
                            current = max(0.0, min(cap, current + raw_delta))
                        new_beliefs[dv.domain_tag] = current

                    # Prune sub-floor entries
                    new_beliefs = {
                        k: v for k, v in new_beliefs.items() if v > BELIEF_FLOOR
                    }

                    # Apply the Imago's culture-tag riders to the splinter's
                    # starting culture_tags — same 2-step escalating pre-shift
                    # pattern as the belief pre-shift above, respecting inertia
                    # and the values:* stubbornness multiplier.
                    new_culture = dict(pop_a.culture_tags)
                    _stub_mult = max(0.05, 1.0 - state.config.values_stubbornness_factor)
                    for cv in goal.culture_vectors:
                        current = new_culture.get(cv.culture_tag, 0.0)
                        for i in range(1, 3):
                            tick_rate = base_rate * (1.0 + i * 0.05)
                            raw_delta = tick_rate * cv.direction
                            _s = cv.culture_tag.startswith(("values:", "practice:"))
                            if cv.culture_tag.startswith("values:"):
                                raw_delta *= _stub_mult
                            raw_delta *= belief_inertia(abs(current) if _s else current, raw_delta)
                            if _s:
                                current = max(-1.0, min(1.0, current + raw_delta))
                            else:
                                cap = BELIEF_CAP if raw_delta > 0 else 1.0
                                current = max(0.0, min(cap, current + raw_delta))
                        new_culture[cv.culture_tag] = current
                    new_culture = {
                        k: v for k, v in new_culture.items() if abs(v) > CULTURE_FLOOR
                    }

                    pop_b = Pop(
                        id=uuid4(),
                        name=goal.goal_pop_name,
                        # Splinters formed via Proxius preaching are
                        # Demiurge-authored — grants the player naming
                        # rights via the in-game [ Rename ] button.
                        demiurge_authored=True,
                        civilization_id=pop_a.civilization_id,
                        species_id=pop_a.species_id,
                        social_class=pop_a.social_class,
                        wild_stratum=pop_a.wild_stratum,
                        current_location=pop_a.current_location,
                        size_fractional=1.0,
                        dominant_beliefs=new_beliefs,
                        culture_tags=new_culture,
                        rider_traits={
                            dv.domain_tag: 0.30
                            for dv in goal.domain_vectors
                            if dv.direction > 0
                        },
                        parent_pop_id=pop_a.id,
                        preaching_imago_id=goal.imago_node_id,
                        pinned=False,
                        visibility=pop_a.visibility * 0.75,
                    )
                    # Wire goal_pop_id now so next tick uses the ongoing path.
                    # Also clear goal_pop_name — the name has been applied; if
                    # the goal continues, we don't want to re-apply it.
                    goal.goal_pop_id = pop_b.id
                    goal.goal_pop_last_size = pop_b.size_fractional
                    goal.goal_pop_name = None
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_SPLINTER,
                        target_id=pop_a.id,
                        field="",
                        new_value=pop_b,
                        note=f"Directed Preach Imāgō splinter by {mortal.name}",
                    ))
                    if goal.imago_node_id:
                        _ireg = get_imago_registry()
                        _inode = _ireg.get_node(goal.imago_node_id)
                        _imago_ref = f"§imago§{goal.imago_node_id}§{_inode.name if _inode else goal.imago_node_id}§"
                    else:
                        _imago_ref = "their directive"
                    agent_narratives.append(
                        f"[Tick {state.tick_number + 1}] {mortal.name}'s preaching of "
                        f"{_imago_ref} has drawn "
                        f"§pop§{str(pop_b.id)}§a new group§ "
                        f"apart from §pop§{str(pop_a.id)}§their parent community§."
                    )
                else:
                    # ── Ongoing: drain Pop A into Pop B (beliefs unchanged here;
                    # Pop A only shifts via splash during BOLSTER_BELIEFS) ──
                    pop_b = state.pops.get(str(goal.goal_pop_id))
                    if pop_b is None:
                        goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
                    else:
                        # Clear petition once Proxius achieves a streak of 2+
                        if goal.petition_pending and goal.consecutive_promote_count >= 2:
                            goal.petition_pending = False
                            goal.petition_pending_ticks = 0

                        peel_fraction = 0.05 * (1.0 + goal.effectiveness_bonus)
                        # Log-space delta for A: A loses peel_fraction of its actual population.
                        a_delta = math.log10(1.0 - peel_fraction)  # negative
                        if pop_a.size_fractional + a_delta <= 0.0:
                            # Pop A fully absorbed
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_ABSORBED,
                                target_id=pop_a.id,
                                field="",
                                new_value=str(pop_b.id),
                                note=f"Pop A absorbed into goal Pop by {mortal.name}",
                            ))
                            goal.petition_pending = True
                            agent_narratives.append(
                                f"[Tick {state.tick_number + 1}] {mortal.name} reports: "
                                f"the source community has been fully drawn into the new group. "
                                f"Directive complete — awaiting new orders."
                            )
                        else:
                            # B gains the actual people leaving A — conserves population.
                            people_transferred = (10 ** pop_a.size_fractional) * peel_fraction
                            b_delta = math.log10(10 ** pop_b.size_fractional + people_transferred) - pop_b.size_fractional
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_SIZE_CHANGE,
                                target_id=pop_a.id,
                                field="",
                                delta=round(a_delta, 6),
                                note=f"Members leaving for goal Pop (Proxius {mortal.name})",
                            ))
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_SIZE_CHANGE,
                                target_id=pop_b.id,
                                field="",
                                delta=round(b_delta, 6),
                                note=f"Members joining goal Pop (Proxius {mortal.name})",
                            ))
                            # Stagnation tracking against last known size
                            if pop_b.size_fractional + b_delta <= goal.goal_pop_last_size:
                                goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
                            else:
                                goal.stagnation_counter = max(0, goal.stagnation_counter - 1)
                            goal.goal_pop_last_size = pop_b.size_fractional + b_delta
            else:
                # ── Legacy civ-level path (goals without source_pop_id) ──
                target_civ_ids: list[str] = []
                if goal.target_civilization_id:
                    cid = str(goal.target_civilization_id)
                    if cid in state.civilizations:
                        target_civ_ids.append(cid)
                else:
                    # goal.target_location_id may be a PopLocation; resolve
                    # to its parent world so it matches civ.origin_location_id.
                    loc_id = (
                        _resolve_world_id_for(state, goal.target_location_id)
                        or str(goal.target_location_id)
                    )
                    target_civ_ids = [
                        cid for cid, civ in state.civilizations.items()
                        if str(civ.origin_location_id) == loc_id
                    ]
                for cid in target_civ_ids:
                    for dv in goal.domain_vectors:
                        belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                        rate = base_rate * (1.0 + goal.effectiveness_bonus) + belief_affinity * 0.02
                        mutations.append(StateMutation(
                            mutation_type=MutationType.BELIEF_SHIFT,
                            target_id=UUID(cid),
                            field="dominant_beliefs",
                            delta=dv.direction * rate,
                            new_value=dv.domain_tag,
                            note=f"Proxius {mortal.name} promoting {dv.domain_tag} (streak {goal.consecutive_promote_count})",
                        ))

            # Footprint regardless of path
            mutations.append(StateMutation(
                mutation_type=MutationType.FOOTPRINT_CHANGE,
                target_id=state.demiurge.id,
                field="proxius_activity",
                delta=0.02,
                note=f"Proxius {mortal.name} promoting domain",
            ))

        elif chosen == AgentActionChoice.BOLSTER_BELIEFS and goal.domain_vectors:
            # Strengthen Pop B's distinctive beliefs directly
            pop_a = state.pops.get(str(goal.source_pop_id)) if goal.source_pop_id else None
            pop_b = state.pops.get(str(goal.goal_pop_id)) if goal.goal_pop_id else None
            if pop_b is None:
                goal.stagnation_counter = min(10, goal.stagnation_counter + 1)
            else:
                goal.consecutive_promote_count += 1
                goal.effectiveness_bonus = min(0.30, goal.consecutive_promote_count * 0.05)
                base_rate = 0.12
                # Clear petition once Proxius achieves a streak of 2+
                if goal.petition_pending and goal.consecutive_promote_count >= 2:
                    goal.petition_pending = False
                    goal.petition_pending_ticks = 0
                for dv in goal.domain_vectors:
                    belief_affinity = mortal.belief_tags.get(dv.domain_tag, 0.0)
                    rate = base_rate * (1.0 + goal.effectiveness_bonus) + belief_affinity * 0.02
                    receptivity = _pop_domain_receptivity(pop_b, dv.domain_tag)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_BELIEF_SHIFT,
                        target_id=pop_b.id,
                        field=dv.domain_tag,
                        delta=dv.direction * rate * receptivity,
                        note=f"Proxius {mortal.name} bolstering goal Pop beliefs",
                    ))
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_RIDER_TRAIT,
                        target_id=pop_b.id,
                        field=dv.domain_tag,
                        delta=dv.direction * rate * 0.5,
                        note=f"Rider trait from {goal.imago_node_id or 'directive'}",
                    ))
                for cv in goal.culture_vectors:
                    rate = base_rate * (1.0 + goal.effectiveness_bonus)
                    mutations.append(StateMutation(
                        mutation_type=MutationType.POP_CULTURE_SHIFT,
                        target_id=pop_b.id,
                        field=cv.culture_tag,
                        delta=cv.direction * rate,
                        note=f"Proxius {mortal.name} preaching culture rider",
                    ))
                # Splash: Proxius actively bridges Pop B's new beliefs back to Pop A.
                # No size dampening here — this is directed preaching, not passive contact.
                if pop_a is not None:
                    for dv in goal.domain_vectors:
                        if dv.direction > 0:
                            _pop_a_receptivity = _pop_domain_receptivity(pop_a, dv.domain_tag)
                            splash_delta = dv.direction * base_rate * 0.6 * _pop_a_receptivity
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_BELIEF_SHIFT,
                                target_id=pop_a.id,
                                field=dv.domain_tag,
                                delta=splash_delta,
                                note=f"Belief splash to Pop A from {mortal.name} bolstering goal Pop",
                            ))
                    for cv in goal.culture_vectors:
                        if cv.direction > 0:
                            splash_delta = cv.direction * base_rate * 0.6
                            mutations.append(StateMutation(
                                mutation_type=MutationType.POP_CULTURE_SHIFT,
                                target_id=pop_a.id,
                                field=cv.culture_tag,
                                delta=splash_delta,
                                note=f"Culture splash to Pop A from {mortal.name} preaching",
                            ))
                mutations.append(StateMutation(
                    mutation_type=MutationType.FOOTPRINT_CHANGE,
                    target_id=state.demiurge.id,
                    field="proxius_activity",
                    delta=0.02,
                    note=f"Proxius {mortal.name} bolstering goal Pop",
                ))

        elif chosen == AgentActionChoice.TAKE_STOCK:
            goal.consecutive_promote_count = 0
            goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.02)
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=mortal.id,
                field="alignment",
                delta=0.01,
                note=f"{mortal.name} taking stock of their work",
            ))

        elif chosen == AgentActionChoice.REPORT_TO_DEMIURGE:
            tick = state.tick_number + 1  # tick_number increments after Phase 2.5
            streak = goal.consecutive_promote_count
            ticks_active = state.tick_number + 1 - goal.started_at_tick
            if goal.imago_node_id:
                _r_node = get_imago_registry().get_node(goal.imago_node_id)
                _r_name = _r_node.name if _r_node else goal.imago_node_id
                _r_ref = f"§imago§{goal.imago_node_id}§{_r_name}§"
            else:
                _r_ref = "directive"
            if streak >= 3:
                progress = f"momentum is building — {streak} consecutive pushes of {_r_ref}"
            elif streak > 0:
                progress = f"work on {_r_ref} is underway, {streak} push(es) this stretch"
            elif goal.effectiveness_bonus > 0:
                progress = f"{_r_ref} work has stalled momentarily; prior gains hold"
            else:
                progress = f"no meaningful progress on {_r_ref} yet"
            entry = (
                f"[Tick {tick}] {mortal.name} reports after {ticks_active} tick(s): "
                + progress
                + (f"; effectiveness at +{goal.effectiveness_bonus:.0%}" if goal.effectiveness_bonus > 0 else "")
                + "."
            )
            goal.report_log = (goal.report_log + [entry])[-5:]
            agent_narratives.append(entry)

        elif chosen == AgentActionChoice.PETITION_FOR_RELIEF:
            goal.petition_pending = True
            goal.petition_pending_ticks = 0  # 5-tick abandonment clock starts now
            goal.consecutive_promote_count = 0
            goal.effectiveness_bonus = 0.0
            goal.stagnation_counter = 0  # fresh start after petition
            tick = state.tick_number + 1
            ticks_active = state.tick_number + 1 - goal.started_at_tick
            if goal.imago_node_id:
                _p_node = get_imago_registry().get_node(goal.imago_node_id)
                _p_name = _p_node.name if _p_node else goal.imago_node_id
                _p_ref = f"§imago§{goal.imago_node_id}§{_p_name}§"
            else:
                _p_ref = "directive"
            if goal.goal_pop_id is not None:
                reason = "the splinter population has stalled — they may be losing ground."
            else:
                reason = "directive yields diminishing returns."
            entry = (
                f"[Tick {tick}] {mortal.name} petitions after {ticks_active} tick(s): "
                f"{_p_ref} — {reason} Requesting new orders."
            )
            goal.report_log = (goal.report_log + [entry])[-5:]
            if not (goal.pop_b_belief_cap_reached or goal.pop_b_size_goal_reached):
                mutations.append(StateMutation(
                    mutation_type=MutationType.MORTAL_ALIGNMENT,
                    target_id=mortal.id,
                    field="alignment",
                    delta=-0.02,
                    note=f"{mortal.name} frustrated with current directive",
                ))

        elif chosen == AgentActionChoice.NOTHING:
            goal.consecutive_promote_count = 0
            goal.effectiveness_bonus = max(0.0, goal.effectiveness_bonus - 0.05)
            mutations.append(StateMutation(
                mutation_type=MutationType.MORTAL_ALIGNMENT,
                target_id=mortal.id,
                field="alignment",
                delta=+0.01,
                note=f"{mortal.name} idle recovery",
            ))

    return mutations, agent_narratives

