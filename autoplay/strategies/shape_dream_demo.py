"""
autoplay/strategies/shape_dream_demo.py

Diagnostic strategy for Shape Dream:
  - Pick two T1 Imāginēs from different Domain trees.
  - Issue a single Shape Dream on tick 1 targeting Senna Vaur.
  - Otherwise idle-harvest.

Prints, each tick, Senna's domain and culture state across a handful of
tags drawn from both Imagines, so we can watch:
  - which Imago dominated this run (from the action narrative line);
  - how same-tag overlaps combine via the mean-positive / sum-negative rule;
  - how negative-direction riders pass through at full strength.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    ShapeDreamIntent, EssenceHarvestIntent,
    DomainVector, CultureVector, Framing,
)
from logic.tick_logic import TickLoop, SimulationState
from utilities.imago_registry import get_registry as get_imago_registry

from autoplay.strategies._helpers import queue, mortal_named


TARGET_NAME = "Senna Vaur"
IMAGO_A = "change:t1:wheel"   # domain:change +0.35, values:sincerity +0.20,
                              # religion:demiurge_worship +0.10, domain:mastery -0.10, …
IMAGO_B = "order:t1:warden"   # domain:order +0.35, religion:luminary_worship +0.15,
                              # values:tenacity +0.20, domain:change -0.10, …
TRACKED_DOMAINS = ["domain:change", "domain:order", "domain:mastery", "domain:sacrifice"]
TRACKED_CULTURE = ["values:sincerity", "values:tenacity", "religion:demiurge_worship",
                   "religion:luminary_worship"]


def _print_snapshot(state: SimulationState, tick: int, prefix: str) -> None:
    mid, m = mortal_named(state, TARGET_NAME)
    if not m:
        print(f"    [t{tick}] {prefix} — {TARGET_NAME} not found")
        return
    line = f"    [t{tick:>2}] {prefix:<12}"
    for tag in TRACKED_DOMAINS:
        v = m.belief_tags.get(tag, 0.0)
        line += f"  {tag.split(':')[1][:5]}={v:.4f}"
    line += "  ||"
    for tag in TRACKED_CULTURE:
        v = m.culture_tags.get(tag, 0.0)
        short = tag.split(':', 1)[1][:9]
        line += f"  {short}={v:.4f}"
    print(line)


def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:
    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    _print_snapshot(state, tick, "pre-action")

    if tick == 1:
        mid, m = mortal_named(state, TARGET_NAME)
        if mid:
            ireg = get_imago_registry()
            node_a = ireg.get_node(IMAGO_A)
            node_b = ireg.get_node(IMAGO_B)
            dvs_a = [DomainVector(domain_tag=t, direction=v)
                     for t, v in node_a.mechanics.items() if t.startswith("domain:")]
            cvs_a = [CultureVector(culture_tag=t, direction=v)
                     for t, v in node_a.mechanics.items() if not t.startswith("domain:")]
            dvs_b = [DomainVector(domain_tag=t, direction=v)
                     for t, v in node_b.mechanics.items() if t.startswith("domain:")]
            cvs_b = [CultureVector(culture_tag=t, direction=v)
                     for t, v in node_b.mechanics.items() if not t.startswith("domain:")]
            q("shape_dream", TargetType.MORTAL, UUID(mid),
              ShapeDreamIntent(
                  imago_node_id_a=IMAGO_A,
                  imago_node_id_b=IMAGO_B,
                  domain_vectors_a=dvs_a,
                  culture_vectors_a=cvs_a,
                  domain_vectors_b=dvs_b,
                  culture_vectors_b=cvs_b,
                  framing=Framing.AMBIGUOUS,
              ))
            return f"Shape Dream: {IMAGO_A} ⊗ {IMAGO_B} → {TARGET_NAME}"

    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return "Harvest Essence (idle)."
