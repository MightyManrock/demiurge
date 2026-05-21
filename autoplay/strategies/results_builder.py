"""
autoplay/strategies/results_builder.py

Optimized for Vrath's Results Demand (domain:conflict, domain:change).

Strategy:
  Tick 1:     Appoint Veth Sarai as Proxius.
  Tick 2+:    Direct Veth to preach Broken Banner → Neran Artisan pop.
              Explore Beliefs in conflict; reveal Sharpened Edge at pool≥100.
              Then pivot to explore change; reveal New Dawn at pool≥100.
  Domain swaps (when essence≥1.5):
              order→conflict, then conflict→mastery, then change→growth.
  Whisper:    High-alignment visible mortals every tick, rotating by index.
              Banner until edge unlocked; then edge through tick 30;
              after tick 30 alternate best conflict / best change imago.
  Opportunistic:
              Appoint Urren when Sharpened Edge unlocked; direct to preach it.
              Appoint Deva when New Dawn unlocked; direct to preach it.
  Harvest:    Essence every 5 ticks.

Run with:  python main.py --autoplay results_builder
Watch:     Vrath methods should climb. Cassiel unaffected.
"""
from __future__ import annotations
from uuid import UUID
from typing import Optional, Tuple

from core.action_core import (
    TargetType, WhisperIntent, DomainVector, Framing,
    EssenceHarvestIntent, ScryIntent, ScryScope,
    ProxiusDirectiveIntent, ExploreBeliefIntent, RevealImagoIntent,
    ChangeAffiliatedDomainsIntent, OmenIntent,
)
from core.universe_core import MortalRole, SocialClass, NotableMortal
from logic.tick_logic import TickLoop, SimulationState, is_mortal_visible

from autoplay.strategies._helpers import (
    queue, visible_named, world_id, civ_id, pop_at,
)


def _mortal_pop(
    state: SimulationState, mortal: NotableMortal
) -> Tuple[Optional[str], object]:
    """Return (pop_id_str, pop) for the first pop at the mortal's location and civ."""
    for pid, p in state.pops.items():
        if (p.current_location == mortal.current_location
                and p.civilization_id == mortal.civilization_id):
            return pid, p
    return None, None


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, proxius_id=None):
        queue(loop, state, key, ttype, tid, intent, proxius_id=proxius_id)

    dem        = state.demiurge
    essence    = state.essence.actual
    affiliated = set(dem.affiliated_domains)
    unlocked   = set(dem.unlocked_imagines)
    rev_pools  = dem.revelation_pools

    has_edge = "conflict:t2:edge" in unlocked
    has_dawn = "change:t2:dawn"   in unlocked

    neran = world_id(state, "Neran")
    oros  = world_id(state, "Oros")

    # ── Key mortals ──────────────────────────────────────────────────────
    veth_id,  veth  = visible_named(state, "Veth Sarai")
    urren_id, urren = visible_named(state, "Urren")
    deva_id,  deva  = visible_named(state, "Deva")

    veth_proxius  = bool(veth  and veth.role  == MortalRole.PROXIUS)
    urren_proxius = bool(urren and urren.role == MortalRole.PROXIUS)
    deva_proxius  = bool(deva  and deva.role  == MortalRole.PROXIUS)

    # Artisan pop on Neran Surface — visible from tick 1
    artisan     = pop_at(state, "Neran Confederacy", "Neran Surface", SocialClass.ARTISAN)
    artisan_pid = UUID(artisan[0]) if artisan else None

    best_conflict = "conflict:t2:edge" if has_edge else "conflict:t1:banner"

    actions: list[str] = []

    # ─────────────────────────────────────────────────────────────────────
    # PROXIUS_DIRECTION  (one per tick; priority: Veth > Urren > Deva)
    # ─────────────────────────────────────────────────────────────────────
    if veth_id and not veth_proxius:
        q("appoint_proxius", TargetType.MORTAL, UUID(veth_id))
        actions.append("appoint Veth Sarai as Proxius")

    elif veth_id and veth_proxius:
        current = veth.active_goal.imago_node_id if veth.active_goal else None
        if current != best_conflict:
            q("preach_imago", TargetType.MORTAL, UUID(veth_id),
              ProxiusDirectiveIntent(
                  imago_node_id=best_conflict,
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.7)],
                  target_civilization_id=civ_id(state, "Neran Confederacy"),
                  target_pop_id=artisan_pid,
              ),
              proxius_id=UUID(veth_id))
            actions.append(f"direct Veth → {best_conflict} to Artisan pop")

    elif has_edge and urren_id and not urren_proxius:
        q("appoint_proxius", TargetType.MORTAL, UUID(urren_id))
        actions.append("appoint Urren as Proxius")

    elif has_edge and urren_id and urren_proxius:
        current = urren.active_goal.imago_node_id if urren.active_goal else None
        if current != "conflict:t2:edge":
            pop_id_str, _ = _mortal_pop(state, urren)
            q("preach_imago", TargetType.MORTAL, UUID(urren_id),
              ProxiusDirectiveIntent(
                  imago_node_id="conflict:t2:edge",
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8)],
                  target_civilization_id=urren.civilization_id,
                  target_pop_id=UUID(pop_id_str) if pop_id_str else None,
              ),
              proxius_id=UUID(urren_id))
            actions.append("direct Urren → Sharpened Edge to his pop")

    elif has_dawn and deva_id and not deva_proxius:
        q("appoint_proxius", TargetType.MORTAL, UUID(deva_id))
        actions.append("appoint Deva as Proxius")

    elif has_dawn and deva_id and deva_proxius:
        current = deva.active_goal.imago_node_id if deva.active_goal else None
        if current != "change:t2:dawn":
            pop_id_str, _ = _mortal_pop(state, deva)
            q("preach_imago", TargetType.MORTAL, UUID(deva_id),
              ProxiusDirectiveIntent(
                  imago_node_id="change:t2:dawn",
                  domain_vectors=[DomainVector(domain_tag="domain:change", direction=0.8)],
                  target_civilization_id=deva.civilization_id,
                  target_pop_id=UUID(pop_id_str) if pop_id_str else None,
              ),
              proxius_id=UUID(deva_id))
            actions.append("direct Deva → New Dawn to his pop")

    # ─────────────────────────────────────────────────────────────────────
    # SELF_REFINEMENT  (domain swaps take priority over explore/reveal)
    # Swap sequence: order→conflict, conflict→mastery, change→growth
    # just_revealed_* flags communicate to the OVERT_MIRACLE section below.
    # ─────────────────────────────────────────────────────────────────────
    just_revealed_edge = False
    just_revealed_dawn = False

    if "domain:conflict" not in affiliated and "domain:order" in affiliated and essence >= 15.0:
        q("change_affiliated_domains", TargetType.UNDERREAL, None,
          ChangeAffiliatedDomainsIntent(old_domain="domain:order",
                                        new_domain="domain:conflict"))
        actions.append("swap order → conflict affiliation")

    elif "domain:conflict" in affiliated and "domain:mastery" not in affiliated and essence >= 15.0:
        q("change_affiliated_domains", TargetType.UNDERREAL, None,
          ChangeAffiliatedDomainsIntent(old_domain="domain:conflict",
                                        new_domain="domain:mastery"))
        actions.append("swap conflict → mastery affiliation")

    elif "domain:change" in affiliated and "domain:growth" not in affiliated and essence >= 15.0:
        q("change_affiliated_domains", TargetType.UNDERREAL, None,
          ChangeAffiliatedDomainsIntent(old_domain="domain:change",
                                        new_domain="domain:growth"))
        actions.append("swap change → growth affiliation")

    elif not has_edge:
        pool = rev_pools.get("domain:conflict", 0.0)
        if pool >= 100.0:
            q("reveal_imago", TargetType.UNDERREAL, None,
              RevealImagoIntent(domain_tag="domain:conflict", node_id="conflict:t2:edge"))
            actions.append("reveal Sharpened Edge")
            just_revealed_edge = True
        else:
            q("explore_beliefs", TargetType.UNDERREAL, None,
              ExploreBeliefIntent(domain_tag="domain:conflict"))
            actions.append(f"explore conflict (pool={pool:.0f}/100)")

    elif not has_dawn:
        pool = rev_pools.get("domain:change", 0.0)
        if pool >= 100.0:
            q("reveal_imago", TargetType.UNDERREAL, None,
              RevealImagoIntent(domain_tag="domain:change", node_id="change:t2:dawn"))
            actions.append("reveal New Dawn")
            just_revealed_dawn = True
        else:
            q("explore_beliefs", TargetType.UNDERREAL, None,
              ExploreBeliefIntent(domain_tag="domain:change"))
            actions.append(f"explore change (pool={pool:.0f}/100)")

    # ─────────────────────────────────────────────────────────────────────
    # SUBTLE_INFLUENCE  (whisper to visible mortals, rotate by tick)
    # ─────────────────────────────────────────────────────────────────────
    visible = sorted(
        [(mid, m) for mid, m in state.mortals.items() if is_mortal_visible(m)],
        key=lambda x: -x[1].alignment,
    )
    if visible:
        wmid, wmortal = visible[tick % len(visible)]

        if tick <= 30 or not has_edge:
            whisper_imago = best_conflict
            wvecs    = [DomainVector(domain_tag="domain:conflict", direction=0.6),
                        DomainVector(domain_tag="domain:change",   direction=0.3)]
            wconcept = "Those who clash and endure are reshaping the world."
        elif tick % 2 == 0:
            whisper_imago = best_conflict
            wvecs    = [DomainVector(domain_tag="domain:conflict", direction=0.7)]
            wconcept = "Conflict is the edge that carves meaning from chaos."
        else:
            whisper_imago = "change:t2:dawn" if has_dawn else "change:t1:wheel"
            wvecs    = [DomainVector(domain_tag="domain:change", direction=0.7)]
            wconcept = "The dawn that follows struggle belongs to those who endure."

        q("whisper", TargetType.MORTAL, UUID(wmid),
          WhisperIntent(
              concept=wconcept,
              domain_vectors=wvecs,
              framing=Framing.INSPIRATIONAL,
              imago_node_id=whisper_imago,
          ))
        actions.append(f"whisper to {wmortal.name} [{whisper_imago}]")

    # ─────────────────────────────────────────────────────────────────────
    # OVERT_MIRACLE  (one omen per imago unlock window, world-scale push)
    # Fired on the tick(s) right after a reveal while the pool is near zero.
    # essence_location_weight=3.0 means world domain_expression dominates
    # Essence generation — omens are the highest-leverage conflict/change lever.
    # ─────────────────────────────────────────────────────────────────────
    _sethis_world = next((w for w in state.worlds.values() if w.name == "Sethis"), None)
    sethis = world_id(state, "Sethis") if _sethis_world else None

    if just_revealed_edge:
        q("manifest_omen", TargetType.WORLD, oros,
          OmenIntent(
              sign_description="The sky above Oros tears open — a wound of fire that bleeds conflict into the stars.",
              intended_interpretation="Clash is sacred. To fight is to be alive.",
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8)],
              framing=Framing.PROPHETIC,
              imago_node_id="conflict:t2:edge",
          ))
        actions.append("manifest Sharpened Edge omen on Oros")
    elif just_revealed_dawn and sethis:
        q("manifest_omen", TargetType.WORLD, sethis,
          OmenIntent(
              sign_description="A new sun rises on Sethis — warm, unfamiliar, full of promise and loss.",
              intended_interpretation="Change is not the end. It is the beginning wearing unfamiliar clothes.",
              domain_vectors=[DomainVector(domain_tag="domain:change", direction=0.8)],
              framing=Framing.PROPHETIC,
              imago_node_id="change:t2:dawn",
          ))
        actions.append("manifest New Dawn omen on Sethis")

    # ─────────────────────────────────────────────────────────────────────
    # UNDERREAL  (harvest every 5 ticks to cover appoint + swap costs)
    # ─────────────────────────────────────────────────────────────────────
    if tick % 5 == 0:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=1.0))
        actions.append("harvest essence")

    # ─────────────────────────────────────────────────────────────────────
    # OBSERVATION  (scry world scope; free)
    # ─────────────────────────────────────────────────────────────────────
    target = neran if tick % 2 == 1 else oros
    name   = "Neran" if tick % 2 == 1 else "Oros"
    q("scry", TargetType.WORLD, target, ScryIntent(scope=ScryScope.WORLD))
    actions.append(f"scry {name}")

    return f"Tick {tick}: " + "; ".join(actions)
