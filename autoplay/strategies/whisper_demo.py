"""
autoplay/strategies/whisper_demo.py

Diagnostic strategy: whisper once to Senna Vaur (Neran) on tick 1, then
idle-harvest. Each tick, print the target mortal's `belief_tags` and the
target Pop's `dominant_beliefs` for the whispered domain, so we can verify
that MORTAL_BELIEF_SHIFT fires immediately, the RAMP_FADE echo continues
to shift the mortal's beliefs over the following ticks, and the Pop splash
(with own-pop bonus) lands on the mortal's own Pop.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    WhisperIntent, EssenceHarvestIntent,
    DomainVector, CultureVector, Framing,
)
from logic.tick_logic import TickLoop, SimulationState
from utilities.imago_registry import get_registry as get_imago_registry

from autoplay.strategies._helpers import queue, mortal_named


TARGET_NAME = "Senna Vaur"
# Frame the whisper with a real T1 Imago so we can see whether mortal-side
# lever C lets sub-floor T1 contributions accumulate. change:t1:wheel carries
# both domain and culture mechanics.
WHISPER_IMAGO = "change:t1:wheel"
WHISPER_DOMAIN = "domain:change"            # peak +0.35 in change:t1:wheel
WHISPER_CULTURE = "values:sincerity"        # +0.20 in change:t1:wheel (values:* — stubborn)


def _print_snapshot(state: SimulationState, tick: int, prefix: str) -> None:
    from logic.tick_logic import _resolve_world_id_for
    from core.universe_core import PopLocation
    mid, m = mortal_named(state, TARGET_NAME)
    if not m:
        print(f"    [t{tick}] {prefix} — {TARGET_NAME} not found")
        return
    m_dom = m.belief_tags.get(WHISPER_DOMAIN, 0.0)
    m_cult = m.culture_tags.get(WHISPER_CULTURE, 0.0)
    line = (f"    [t{tick:>2}] {prefix:<14} "
            f"{TARGET_NAME}[{WHISPER_DOMAIN.split(':')[1]}]={m_dom:.4f} "
            f"[{WHISPER_CULTURE.split(':',1)[1]}]={m_cult:.4f}")
    # All Pops on the mortal's world.
    wid = _resolve_world_id_for(state, m.current_location)
    pops_on_world = []
    if wid:
        for pop in state.pops.values():
            ploc = state.locations.get(str(pop.current_location)) if pop.current_location else None
            if isinstance(ploc, PopLocation) and str(ploc.parent_id) == wid:
                pops_on_world.append(pop)
    for pop in pops_on_world:
        label = (pop.name or pop.stratum)
        own = "*" if str(pop.id) == str(m.pop_id) else " "
        d = pop.dominant_beliefs.get(WHISPER_DOMAIN, 0.0)
        c = pop.culture_tags.get(WHISPER_CULTURE, 0.0)
        line += f"  {own}{label} d={d:.4f}/c={c:.4f}"
    print(line)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    _print_snapshot(state, tick, "pre-action")

    if tick == 1:
        mid, m = mortal_named(state, TARGET_NAME)
        if mid:
            node = get_imago_registry().get_node(WHISPER_IMAGO)
            dvs = [DomainVector(domain_tag=t, direction=v)
                   for t, v in node.mechanics.items() if t.startswith("domain:")]
            cvs = [CultureVector(culture_tag=t, direction=v)
                   for t, v in node.mechanics.items() if not t.startswith("domain:")]
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  concept="The wheel turns; the Confederacy must learn to bend with it.",
                  domain_vectors=dvs,
                  culture_vectors=cvs,
                  framing=Framing.INSPIRATIONAL,
                  imago_node_id=WHISPER_IMAGO,
              ))
            return f"Whisper framed by '{WHISPER_IMAGO}' to {TARGET_NAME}."

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence (idle)."
