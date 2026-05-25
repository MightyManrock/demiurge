"""
autoplay/strategies/wardens_default.py

The default 50-tick autoplay strategy for the Warden's Compact scenario.
Exports `decide(loop, state, tick) -> str` which the autoplay runner calls
once per tick. Modifies state.action_queue as a side effect and returns
a one-line narrative description of the tick's chosen action.

Strategy: maximise Essence stockpile while keeping both Luminaries appeased.
  - Cassiel (Order/Silence, patient): low footprint, push domain:order on Neran.
  - Vrath (Conflict/Change, wrathful): push domain:conflict/change on both worlds.
  - Harvest Essence regularly with high concealment priority.
  - Appoint Senna Vaur (Neran) as Proxius early; seek Urren on Oros later.
  - Scry both worlds to discover hidden mortals; whisper conflict to Orryn/Kael.
"""
from __future__ import annotations
from uuid import UUID

from core.action_core import (
    TargetType,
    WhisperIntent, EssenceHarvestIntent, DevelopmentIntent,
    ProxiusDirectiveIntent, LuminaryPetitionIntent, ProbabilityNudgeIntent,
    DomainVector, ScryIntent, ScryScope,
)
from logic.tick_logic import TickLoop, SimulationState
from core.universe_core import MortalRole

from autoplay.strategies._helpers import (
    queue, mortal_named, visible_named, world_id, civ_id, lum_id,
)


# ── Decision logic ─────────────────────────────────────────────────────────

def decide(loop: TickLoop, state: SimulationState, tick: int) -> str:

    def q(key, ttype, tid, intent=None, prox=None):
        queue(loop, state, key, ttype, tid, intent, prox)

    # ── Ticks 1–2: Scry both worlds ────────────────────────────────────────
    if tick == 1:
        q("scry", TargetType.WORLD, world_id(state, "Neran"), ScryIntent(scope=ScryScope.WORLD))
        return "Scry Neran — open the board, search for hidden mortals."

    if tick == 2:
        q("scry", TargetType.WORLD, world_id(state, "Oros"), ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros — reveal hidden tribal mortals."

    # ── Tick 3: Appoint Senna as Proxius ──────────────────────────────────
    if tick == 3:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna.role != MortalRole.PROXIUS:
            q("appoint_proxius", TargetType.MORTAL, UUID(mid))
            return "Appoint Senna Vaur as Proxius on Neran — order anchor for Cassiel."

    # ── Tick 4: First Essence harvest ─────────────────────────────────────
    if tick == 4:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(target_concept_type="failed civilisations",
                               concealment_priority=0.9))
        return "Harvest Essence (concealment 0.9) — building stockpile quietly."

    # ── Tick 5: Whisper to Orryn if visible, else re-scry Neran ───────────
    if tick == 5:
        mid, _ = visible_named(state, "Orryn Vel")
        if mid:
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8),
                                  DomainVector(domain_tag="domain:change",   direction=0.7)],
              ))
            return "Whisper to Orryn Vel — plant seeds of conflict/change."
        else:
            q("scry", TargetType.WORLD, world_id(state, "Neran"), ScryIntent(scope=ScryScope.WORLD))
            return "Re-scry Neran — Orryn not yet visible."

    # ── Tick 6: First directive to Senna ──────────────────────────────────
    if tick == 6:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Consolidate institutional authority in the Confederacy.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.8),
                                  DomainVector(domain_tag="domain:law",   direction=0.6)],
                  latitude=0.3,
              ), prox=UUID(mid))
            return "Directive to Senna: consolidate order on Neran."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna not yet Proxius."

    # ── Tick 7: Whisper to Kael or re-scry Oros ───────────────────────────
    if tick == 7:
        mid, _ = visible_named(state, "Kael Ash")
        if mid:
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9)],
              ))
            return "Whisper to Kael Ash — push conflict on Oros for Vrath."
        q("scry", TargetType.WORLD, world_id(state, "Oros"), ScryIntent(scope=ScryScope.WORLD))
        return "Re-scry Oros — seeking Kael Ash."

    # ── Tick 8: Harvest ────────────────────────────────────────────────────
    if tick == 8:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 9: Accelerate Keth toward conflict ────────────────────────────
    if tick == 9:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Keth Wanderers"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8)],
              target_aspect="inter-band raiding culture",
          ))
        return "Accelerate Keth toward conflict — Vrath's agenda."

    # ── Tick 10: Report to Vrath ───────────────────────────────────────────
    if tick == 10:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Vrath"),
          LuminaryPetitionIntent(
              subject="Conflict domain is spreading across both worlds.",
              your_position="Oros is stirring; the Keth grow aggressive.",
              tone="confident",
          ))
        return "Report to Vrath — demonstrate early conflict results."

    # ── Tick 11: Appoint Urren if visible, else re-scry Oros ──────────────
    if tick == 11:
        mid, urren = visible_named(state, "Urren")
        if mid and urren.role != MortalRole.PROXIUS:
            q("appoint_proxius", TargetType.MORTAL, UUID(mid))
            return "Appoint Urren as Proxius on Oros — spiritual conduit."
        q("scry", TargetType.WORLD, world_id(state, "Oros"), ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros — seeking Urren for Proxius appointment."

    # ── Tick 12: Harvest ───────────────────────────────────────────────────
    if tick == 12:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.85))
        return "Harvest Essence."

    # ── Tick 13: Nudge Oros toward conflict ────────────────────────────────
    if tick == 13:
        q("nudge_probability", TargetType.WORLD, world_id(state, "Oros"),
          ProbabilityNudgeIntent(
              event_description="Keth band rivalry over winter grazing grounds",
              desired_outcome="Open warfare that forges a dominant war-leader",
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9)],
              nudge_strength=0.6,
          ))
        return "Nudge probability on Oros — drive Keth toward open conflict."

    # ── Tick 14: Directive to Senna ────────────────────────────────────────
    if tick == 14:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Establish a stronger legal code rooted in institutional hierarchy.",
                  domain_vectors=[DomainVector(domain_tag="domain:order",     direction=0.9),
                                  DomainVector(domain_tag="domain:hierarchy", direction=0.7)],
                  latitude=0.25,
              ), prox=UUID(mid))
            return "Directive to Senna: legal code push — deepens domain:order."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna unavailable."

    # ── Tick 15: Report to Cassiel ─────────────────────────────────────────
    if tick == 15:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Cassiel"),
          LuminaryPetitionIntent(
              subject="Neran's institutional stability is deepening quietly.",
              your_position="My Proxius works through legitimate channels; no visible footprint.",
              tone="deferential",
          ))
        return "Report to Cassiel — reassure with evidence of subtlety."

    # ── Tick 16: Whisper to Maeva if visible ──────────────────────────────
    if tick == 16:
        mid, _ = visible_named(state, "Maeva Sorn")
        if mid:
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  domain_vectors=[DomainVector(domain_tag="domain:silence", direction=0.7),
                                  DomainVector(domain_tag="domain:order",   direction=0.6)],
              ))
            return "Whisper to Maeva Sorn — deepen silence/order for Cassiel."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Maeva not visible."

    # ── Tick 17: Harvest ───────────────────────────────────────────────────
    if tick == 17:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 18: Directive to Urren if appointed ──────────────────────────
    if tick == 18:
        mid, urren = mortal_named(state, "Urren")
        if mid and urren and urren.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Spread the ancestral teaching that conflict is sacred — the spirits demand it.",
                  domain_vectors=[DomainVector(domain_tag="domain:conflict",         direction=0.7),
                                  DomainVector(domain_tag="domain:ancestor_worship", direction=0.5)],
                  latitude=0.5,
              ), prox=UUID(mid))
            return "Directive to Urren: sacred conflict doctrine on Oros."
        q("scry", TargetType.WORLD, world_id(state, "Oros"), ScryIntent(scope=ScryScope.WORLD))
        return "Scry Oros — Urren not yet appointed."

    # ── Tick 19: Accelerate Neran toward order/law ────────────────────────
    if tick == 19:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Neran Confederacy"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.8),
                              DomainVector(domain_tag="domain:law",   direction=0.6)],
              target_aspect="bureaucratic and judicial institutions",
          ))
        return "Accelerate Neran toward order/law — Cassiel's agenda compounds."

    # ── Tick 20: Harvest ───────────────────────────────────────────────────
    if tick == 20:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.85))
        return "Harvest Essence — midpoint stockpile check."

    # ── Tick 21: Directive to Senna: counter Orryn ────────────────────────
    if tick == 21:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Counter the rebel faction quietly — discredit, not suppress.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.8)],
                  latitude=0.4,
              ), prox=UUID(mid))
            return "Directive to Senna: quietly neutralise Orryn's faction."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna not available."

    # ── Tick 22: Whisper to Kael or harvest ───────────────────────────────
    if tick == 22:
        mid, _ = visible_named(state, "Kael Ash")
        if mid:
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=1.0)],
              ))
            return "Whisper to Kael: escalate aggression — pure conflict signal for Vrath."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Kael not visible."

    # ── Tick 23: Harvest ───────────────────────────────────────────────────
    if tick == 23:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 24: Accelerate Keth succession customs ───────────────────────
    if tick == 24:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Keth Wanderers"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.7),
                              DomainVector(domain_tag="domain:change",   direction=0.6)],
              target_aspect="war-leadership succession customs",
          ))
        return "Accelerate Keth: conflict/change in succession customs."

    # ── Tick 25: Report to Cassiel ─────────────────────────────────────────
    if tick == 25:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Cassiel"),
          LuminaryPetitionIntent(
              subject="Neran's order institutions are strengthening through internal channels.",
              your_position="My methods remain deniable; the Confederacy is self-governing toward order.",
              tone="deferential",
          ))
        return "Report to Cassiel — midpoint diplomatic check-in."

    # ── Tick 26: Directive to Urren or harvest ────────────────────────────
    if tick == 26:
        mid, urren = mortal_named(state, "Urren")
        if mid and urren and urren.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Preach that the old ways demand blood-offerings through war.",
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8)],
                  latitude=0.6,
              ), prox=UUID(mid))
            return "Directive to Urren: escalate war-theology on Oros."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Urren not yet Proxius."

    # ── Tick 27: Harvest ───────────────────────────────────────────────────
    if tick == 27:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 28: Nudge Oros toward unifying battle ────────────────────────
    if tick == 28:
        q("nudge_probability", TargetType.WORLD, world_id(state, "Oros"),
          ProbabilityNudgeIntent(
              event_description="Season of raids between Keth bands",
              desired_outcome="A decisive battle producing a unified Keth war-confederacy",
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9),
                              DomainVector(domain_tag="domain:change",   direction=0.7)],
              nudge_strength=0.65,
          ))
        return "Nudge probability: push Keth toward unifying battle."

    # ── Tick 29: Directive to Senna: constitutional charter ───────────────
    if tick == 29:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Propose a new constitutional charter — codify the Confederacy's laws permanently.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.9),
                                  DomainVector(domain_tag="domain:law",   direction=0.8)],
                  latitude=0.2,
              ), prox=UUID(mid))
            return "Directive to Senna: constitutional charter — peak order push."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna unavailable."

    # ── Tick 30: Report to Vrath ───────────────────────────────────────────
    if tick == 30:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Vrath"),
          LuminaryPetitionIntent(
              subject="The Keth Wanderers are becoming a war-culture; Oros burns with conflict.",
              your_position="Vrath's domain is manifesting. Both worlds are changing.",
              tone="confident",
          ))
        return "Report to Vrath — show Oros conflict results at tick 30."

    # ── Tick 31: Harvest ───────────────────────────────────────────────────
    if tick == 31:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 32: Nudge Neran judicial reform ──────────────────────────────
    if tick == 32:
        q("nudge_probability", TargetType.CIVILIZATION,
          civ_id(state, "The Neran Confederacy"),
          ProbabilityNudgeIntent(
              event_description="Neran Confederacy judicial reform debate",
              desired_outcome="The reformist legal faction passes the new charter",
              domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.9),
                              DomainVector(domain_tag="domain:law",   direction=0.7)],
              nudge_strength=0.5,
          ))
        return "Nudge Neran judicial reform toward order/law outcome."

    # ── Tick 33: Whisper to Kael or harvest ───────────────────────────────
    if tick == 33:
        mid, _ = visible_named(state, "Kael Ash")
        if mid:
            q("whisper", TargetType.MORTAL, UUID(mid),
              WhisperIntent(
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9),
                                  DomainVector(domain_tag="domain:change",   direction=0.8)],
              ))
            return "Whisper to Kael (prophetic) — escalate unification drive."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Kael not visible."

    # ── Tick 34: Harvest ───────────────────────────────────────────────────
    if tick == 34:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 35: Directive to Urren or Keth acceleration ──────────────────
    if tick == 35:
        mid, urren = mortal_named(state, "Urren")
        if mid and urren and urren.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Anoint a war-chieftain as the chosen of the ancestor-spirits.",
                  domain_vectors=[DomainVector(domain_tag="domain:conflict",         direction=0.9),
                                  DomainVector(domain_tag="domain:ancestor_worship", direction=0.6)],
                  latitude=0.5,
              ), prox=UUID(mid))
            return "Directive to Urren: anoint war-chieftain — faith + conflict."
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Keth Wanderers"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.8)],
              target_aspect="warrior priest tradition",
          ))
        return "Accelerate Keth warrior-priest tradition."

    # ── Tick 36: Directive to Senna: suppress dissent legally ────────────
    if tick == 36:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Suppress dissent through legal process, not force.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=0.8)],
                  latitude=0.3,
              ), prox=UUID(mid))
            return "Directive to Senna: legal suppression of dissent."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna unavailable."

    # ── Tick 37: Harvest ───────────────────────────────────────────────────
    if tick == 37:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 38: Report to Cassiel ─────────────────────────────────────────
    if tick == 38:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Cassiel"),
          LuminaryPetitionIntent(
              subject="Neran's constitutional charter is taking shape through internal deliberation.",
              your_position="I have been a silent hand only. Cassiel's domains are expressed.",
              tone="deferential",
          ))
        return "Report to Cassiel — show restraint and order results."

    # ── Tick 39: Accelerate Keth toward war-state ─────────────────────────
    if tick == 39:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Keth Wanderers"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9),
                              DomainVector(domain_tag="domain:change",   direction=0.7)],
              target_aspect="unified Keth war-state emerging from band confederation",
          ))
        return "Accelerate Keth: final push toward unified conflict-state."

    # ── Tick 40: Harvest ───────────────────────────────────────────────────
    if tick == 40:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.85))
        return "Harvest Essence — approaching final stretch."

    # ── Tick 41: Final directive to Senna ─────────────────────────────────
    if tick == 41:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Finalise the constitutional charter and present it to the Council.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=1.0)],
                  latitude=0.1,
              ), prox=UUID(mid))
            return "Directive to Senna: finalise charter — maximum order signal."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Senna unavailable."

    # ── Tick 42: Directive to Urren: proclaim Kael ────────────────────────
    if tick == 42:
        mid, urren = mortal_named(state, "Urren")
        if mid and urren and urren.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Declare Kael Ash the war-blessed chieftain of all Keth.",
                  domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=1.0)],
                  latitude=0.4,
              ), prox=UUID(mid))
            return "Directive to Urren: proclaim Kael — peak conflict on Oros."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence — Urren unavailable."

    # ── Tick 43: Harvest ───────────────────────────────────────────────────
    if tick == 43:
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    # ── Tick 44: Final report to Vrath ────────────────────────────────────
    if tick == 44:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Vrath"),
          LuminaryPetitionIntent(
              subject="Conflict and change are in full expression across the universe.",
              your_position="Oros wages war; Neran fractures but holds. Both serve your domain.",
              tone="confident",
          ))
        return "Final report to Vrath — confident display of conflict results."

    # ── Tick 45: Final report to Cassiel ──────────────────────────────────
    if tick == 45:
        q("report_to_luminary", TargetType.LUMINARY, lum_id(state, "Cassiel"),
          LuminaryPetitionIntent(
              subject="Neran's order is self-sustaining; my methods left no trace.",
              your_position="Silence and order both thrive. I have been a careful hand.",
              tone="deferential",
          ))
        return "Final report to Cassiel — underscore subtlety and silence."

    # ── Ticks 46–50: Harvest into the end ─────────────────────────────────
    if tick in (46, 49, 50):
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return f"Harvest Essence — tick {tick}."

    if tick == 47:
        mid, senna = mortal_named(state, "Senna Vaur")
        if mid and senna and senna.role == MortalRole.PROXIUS:
            q("preach_imago", TargetType.MORTAL, UUID(mid),
              ProxiusDirectiveIntent(
                  goal_statement="Ensure the Confederacy's charter enshrines order as the founding law.",
                  domain_vectors=[DomainVector(domain_tag="domain:order", direction=1.0),
                                  DomainVector(domain_tag="domain:law",   direction=0.9)],
                  latitude=0.1,
              ), prox=UUID(mid))
            return "Final directive to Senna: enshrine order in Confederacy law."
        q("harvest_essence", TargetType.UNDERREAL, None,
          EssenceHarvestIntent(concealment_priority=0.9))
        return "Harvest Essence."

    if tick == 48:
        q("accelerate_development", TargetType.CIVILIZATION,
          civ_id(state, "The Keth Wanderers"),
          DevelopmentIntent(
              domain_vectors=[DomainVector(domain_tag="domain:conflict", direction=0.9)],
              target_aspect="conquering Keth confederation emerging as dominant force",
          ))
        return "Final Keth acceleration — conflict at maximum expression."

    # Fallback
    q("harvest_essence", TargetType.UNDERREAL, None,
      EssenceHarvestIntent(concealment_priority=0.9))
    return f"Fallback tick {tick}: Harvest Essence."
