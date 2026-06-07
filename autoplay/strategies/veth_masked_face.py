"""
autoplay/strategies/veth_masked_face.py

Experiment strategy: Veth Sarai preaches *The Masked Face* (silence:t1:veil)
to the Neran Confederacy Elite Pop at Neran Surface.

  Tick 1   — Appoint Veth Sarai as Proxius.
  Tick 2–3 — Direct Veth to preach The Masked Face to NC Elites.
  Otherwise — Harvest Essence; let the Proxius work autonomously.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    EssenceHarvestIntent, ProxiusDirectiveIntent, DomainVector,
)
from core.universe_core import MortalRole, SocialStratum
from logic.tick_logic import TickLoop, SimulationState

from autoplay.strategies._helpers import (
    queue, mortal_named, civ_id, pop_at,
)


MASKED_FACE_IMAGO_ID = "silence:t1:veil"
MASKED_FACE_VECTORS = [
    DomainVector(domain_tag="domain:silence",   direction=0.35),
    DomainVector(domain_tag="domain:void",      direction=0.10),
    DomainVector(domain_tag="domain:sacrifice", direction=-0.10),
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
            target_pop = pop_at(state, "Neran", "Neran Surface", SocialStratum.ELITE)
            if target_pop is None:
                q("harvest_essence", TargetType.UNDERREAL, None,
                  EssenceHarvestIntent(concealment_priority=0.9))
                return f"Tick {tick}: Harvest — NC Elite Pop @ Neran Surface not found."
            target_pop_id = UUID(target_pop[0])
            q("preach_imago", TargetType.MORTAL, UUID(mid_veth),
              ProxiusDirectiveIntent(
                  goal_statement="Teach the Confederacy elites the wisdom of silence and the masked face.",
                  domain_vectors=MASKED_FACE_VECTORS,
                  imago_node_id=MASKED_FACE_IMAGO_ID,
                  target_pop_id=target_pop_id,
                  target_civilization_id=civ_id(state, "Neran"),
                  latitude=0.4,
              ),
              prox=UUID(mid_veth))
            return f"Tick {tick}: Direct Veth Sarai to preach The Masked Face to NC Elites."

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence."
