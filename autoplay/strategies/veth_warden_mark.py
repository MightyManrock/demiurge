"""
autoplay/strategies/veth_warden_mark.py

Experiment strategy: Veth Sarai preaches *The Warden's Mark* (order:t1:warden)
to the Neran Confederacy Common Pop at Neran Surface.

  Tick 1   — Appoint Veth Sarai as Proxius.
  Tick 2–3 — Direct Veth to preach The Warden's Mark to NC Commoners.
  Otherwise — Harvest Essence; let the Proxius work autonomously.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    EssenceHarvestIntent, ProxiusDirectiveIntent, DomainVector,
)
from core.universe_core import MortalRole, SocialClass
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import (
    queue, mortal_named, civ_id, pop_at,
)


WARDEN_MARK_IMAGO_ID = "order:t1:warden"
WARDEN_MARK_VECTORS = [
    DomainVector(domain_tag="domain:order",     direction=0.30),
    DomainVector(domain_tag="domain:sacrifice", direction=0.10),
    DomainVector(domain_tag="domain:truth",     direction=-0.10),
]


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    mid_veth, veth = mortal_named(state, "Veth Sarai")

    if tick == 1:
        if mid_veth:
            q("appoint_proxius", TargetType.MORTAL, UUID(mid_veth))
            return "Appoint Veth Sarai as Proxius."

    if tick in (2, 3):
        if mid_veth and veth and veth.role == MortalRole.PROXIUS and veth.active_goal is None:
            target_pop = pop_at(state, "Neran", "Neran Surface", SocialClass.COMMON)
            if target_pop is None:
                q("harvest_essence", TargetType.UNDERREAL, None,
                  EssenceHarvestIntent(concealment_priority=0.9))
                return f"Tick {tick}: Harvest — NC Common Pop @ Neran Surface not found."
            target_pop_id = UUID(target_pop[0])
            q("preach_imago", TargetType.MORTAL, UUID(mid_veth),
              ProxiusDirectiveIntent(
                  goal_statement="Teach the Confederacy commons the duty of order and the warden's mark.",
                  domain_vectors=WARDEN_MARK_VECTORS,
                  imago_node_id=WARDEN_MARK_IMAGO_ID,
                  target_pop_id=target_pop_id,
                  target_civilization_id=civ_id(state, "Neran"),
                  latitude=0.4,
              ),
              prox=UUID(mid_veth))
            return f"Tick {tick}: Direct Veth Sarai to preach The Warden's Mark to NC Commoners."

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence."
