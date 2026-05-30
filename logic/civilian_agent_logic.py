from __future__ import annotations
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from core.universe_core import NotableMortal
    from core.agent_core import CivilianAgentState, KnowledgeBase
    from logic.tick_logic import SimulationState

FATIGUE_BLOCK_THRESHOLD = 0.85

LEISURE_BASE_GAIN             = 0.35
SOCIALIZE_BASE_GAIN           = 0.30
LEISURE_SATIATION_HOLD_BASE   = 6
SOCIALIZE_SATIATION_HOLD_BASE = 5

# Score multiplier applied to sell/collect when a commerce directive is active
DIRECTIVE_MULTIPLIER = 2.0


def _need_urgency(need) -> float:
    """Continuous urgency in [0, ~1.5]. Zero when not pressing or held satisfied."""
    if need.satiation_hold > 0 or need.satisfaction >= need.pressing_threshold:
        return 0.0
    base = 1.0 - need.satisfaction / need.pressing_threshold
    if need.is_urgent:
        base = min(1.5, base * 1.5)
    return base


def _pop_practice_quality(mortal_tags: dict[str, float], pop_tags: dict[str, float]) -> float:
    """Weighted leisure quality: mortal preference × pop practice level, normalized to [0, 1]."""
    EXCLUDED = {"practice:ritual", "practice:revelry"}
    total_weight = total = 0.0
    for tag, pop_val in pop_tags.items():
        if not tag.startswith("practice:") or tag in EXCLUDED:
            continue
        mortal_pref = max(0.0, mortal_tags.get(tag, 0.2))
        total_weight += mortal_pref
        total += mortal_pref * pop_val
    if total_weight == 0:
        return 0.3
    return min(1.0, total / total_weight)


def _pop_social_quality(pop_tags: dict[str, float]) -> float:
    """Belonging quality from socializing: driven by pop solidarity + revelry."""
    base = (
        pop_tags.get("values:solidarity", 0.3) * 0.5
        + pop_tags.get("practice:revelry", 0.3) * 0.5
    )
    return min(1.0, max(0.0, base))


def _select_local_pop(mortal, state) -> Optional[str]:
    """Return pop_id of the best pop at mortal's location for pressing social needs,
    or None if no social needs are pressing or no pops are co-located.
    Used by tick_logic for zero-cost milieu switching."""
    cs = mortal.civilian_state
    if cs is None:
        return None
    leisure_pressing  = (n := cs.get_need("leisure"))  is not None and n.is_pressing
    belonging_pressing = (n := cs.get_need("belonging")) is not None and n.is_pressing
    if not leisure_pressing and not belonging_pressing:
        return None
    cur_loc_str = str(mortal.current_location)
    local_pops = [(pid, p) for pid, p in state.pops.items()
                  if str(p.current_location) == cur_loc_str]
    if not local_pops:
        return None
    def _score(item: tuple) -> float:
        _, pop = item
        s = 0.0
        if leisure_pressing:
            s += _pop_practice_quality(mortal.culture_tags, pop.culture_tags)
        if belonging_pressing:
            s += _pop_social_quality(pop.culture_tags)
        return s
    best_pid, _ = max(local_pops, key=_score)
    return best_pid


def _mortal_is_travelling(mortal, state) -> bool:
    if mortal.travel_intent is not None:
        return True
    loc = state.locations.get(str(mortal.current_location))
    return loc is not None and getattr(loc, "location_type", None) == "travel_location"


def _trip_too_long_for_urgent_need(cs, kb, dest_id: str) -> bool:
    """Return True if any urgent need will reach 0 before the trip completes."""
    ticks_cost = kb.route_ticks_to(dest_id)
    if ticks_cost == 0:
        return False
    for need in cs.needs:
        if need.is_urgent and need.decay_rate > 0:
            ticks_until_desperate = need.satisfaction / need.decay_rate
            if ticks_cost > ticks_until_desperate:
                return True
    return False


def evaluate_civilian_action(
    mortal,
    state,
    current_tick: int,
) -> Optional[str]:
    """
    Returns one of: "collect", "sell", "spend", "leisure", "socialize",
    "travel:<location_id>", "idle", None.
    None means the mortal has no civilian_state and should be skipped.

    Actions are scored by Σ(need_urgency × expected_gain). Sell and collect
    carry a "follow-through" component from cargo load fraction: a loaded hold
    creates sell pressure; an empty hold creates collect pressure. Directive-
    aligned actions receive DIRECTIVE_MULTIPLIER. Travel is scored as
    (best_score_at_dest − best_local_score) / ticks_cost, and only beats local
    options when the destination advantage outweighs the journey cost.
    """
    cs = mortal.civilian_state
    kb = mortal.knowledge_base
    if cs is None or kb is None:
        return None

    if _mortal_is_travelling(mortal, state):
        return "idle"

    if mortal.fatigue >= FATIGUE_BLOCK_THRESHOLD:
        return "idle"

    # Sticky collect-then-travel: commit unconditionally on the tick after collecting
    if cs.pending_travel_dest:
        dest = cs.pending_travel_dest
        cs.pending_travel_dest = None
        return f"travel:{dest}"

    if not cs.pressing_needs():
        return "idle"

    current_loc_id = str(mortal.current_location)

    # ── Cargo state ──────────────────────────────────────────────────────────
    _cargo_cap = next(
        (a.cargo_capacity for a in mortal.assets if a.cargo_capacity is not None),
        None,
    )
    _cargo_load = sum(r.quantity for r in cs.inventory if "sell" in r.usable_for)
    _hold_full = _cargo_cap is not None and _cargo_load >= _cargo_cap

    _sell_threshold = _cargo_cap  # None → fall back to Resource.threshold
    _sellable = next(
        (r for r in cs.inventory
         if "sell" in r.usable_for
         and r.quantity >= (_sell_threshold if _sell_threshold is not None else r.threshold)),
        None,
    )
    # Load fraction: ratio when capacity is known; sigmoid (L/(L+1)) otherwise.
    # The sigmoid never reaches 1.0, so uncapped mortals always have some collect score
    # alongside sell pressure — they don't get stuck choosing only one direction.
    _load_fraction = (
        (_cargo_load / _cargo_cap) if _cargo_cap is not None
        else (_cargo_load / (_cargo_load + 1.0))
    )

    _spendable = next(
        (r for r in cs.inventory
         if "spend" in r.usable_for
         and r.quantity >= r.threshold
         and (r.fills_need is None
              or any(n.name == r.fills_need and n.is_pressing for n in cs.needs))),
        None,
    )

    _cur_loc = state.locations.get(current_loc_id)
    _at_resource = (
        _cur_loc is not None
        and getattr(_cur_loc, "collectible_resource", None) is not None
        and current_loc_id in kb.known_resource_locations()
    )

    _local_pop_id = str(mortal.pop_milieu or mortal.pop_id or "")
    _local_pop = state.pops.get(_local_pop_id) if _local_pop_id else None

    # Need urgency map
    urgency = {n.name: _need_urgency(n) for n in cs.needs}

    _directive_active = bool(kb.directive_facts())

    _best_sell_loc  = kb.best_known_sell_location()  if _sellable  else None
    _best_spend_loc = kb.best_known_spend_location() if _spendable else None

    # ── Action scores ─────────────────────────────────────────────────────────

    # Sell: follow-through from loaded hold + purpose + status urgency
    _sell_score = (
        _load_fraction
        + urgency.get("purpose", 0.0) * 1.0
        + urgency.get("status",  0.0) * 0.5
    ) if _sellable else 0.0
    if _directive_active and _sell_score > 0:
        _sell_score *= DIRECTIVE_MULTIPLIER

    # Collect: empty-hold follow-through scaled by purpose urgency
    _collect_score = (
        (1.0 - _load_fraction) * urgency.get("purpose", 0.0)
    ) if not _hold_full else 0.0
    if _directive_active and _collect_score > 0:
        _collect_score *= DIRECTIVE_MULTIPLIER

    # Spend: direct need fill (or generic QoL boost when fills_need is unset)
    if _spendable:
        _spend_score = (
            urgency.get(_spendable.fills_need, 0.0) if _spendable.fills_need
            else sum(urgency.values()) * 0.3
        )
    else:
        _spend_score = 0.0

    # Leisure: leisure urgency × pop practice quality
    _leisure_u = urgency.get("leisure", 0.0)
    if _leisure_u > 0 and _local_pop is not None:
        mortal_tags = getattr(mortal, "culture_tags", {}) or {}
        _leisure_score = _leisure_u * LEISURE_BASE_GAIN * _pop_practice_quality(
            mortal_tags, _local_pop.culture_tags
        )
    else:
        _leisure_score = 0.0

    # Socialize: belonging urgency × pop social quality
    _belonging_u = urgency.get("belonging", 0.0)
    _socialize_score = (
        _belonging_u * SOCIALIZE_BASE_GAIN * _pop_social_quality(_local_pop.culture_tags)
        if _belonging_u > 0 and _local_pop is not None
        else 0.0
    )

    # ── Local candidates ──────────────────────────────────────────────────────
    local_candidates: dict[str, float] = {}
    if _best_sell_loc  and current_loc_id == _best_sell_loc  and _sell_score    > 0:
        local_candidates["sell"]      = _sell_score
    if _at_resource    and not _hold_full                     and _collect_score > 0:
        local_candidates["collect"]   = _collect_score
    if _best_spend_loc and current_loc_id == _best_spend_loc and _spend_score   > 0:
        local_candidates["spend"]     = _spend_score
    if _leisure_score  > 0:
        local_candidates["leisure"]   = _leisure_score
    if _socialize_score > 0:
        local_candidates["socialize"] = _socialize_score

    _best_local = max(local_candidates.values()) if local_candidates else 0.0

    # ── Travel candidates: score = (dest_score − best_local) / ticks_cost ────
    travel_candidates: dict[str, float] = {}

    def _try_travel(dest_id: str, dest_score: float) -> None:
        if dest_id == current_loc_id or dest_score <= _best_local:
            return
        route = kb.route_to(dest_id)
        can_travel = not (route and route.vehicle_type) or any(
            a.asset_type == route.vehicle_type for a in mortal.assets
        )
        if not can_travel or _trip_too_long_for_urgent_need(cs, kb, dest_id):
            return
        ticks = route.ticks_cost if route else 1
        score = (dest_score - _best_local) / max(1, ticks)
        if score > 0:
            travel_candidates[dest_id] = max(travel_candidates.get(dest_id, 0.0), score)

    if _best_sell_loc:
        _try_travel(_best_sell_loc, _sell_score)
    if not _hold_full:
        for res_loc in kb.known_resource_locations():
            _try_travel(res_loc, _collect_score)
    if _best_spend_loc:
        _try_travel(_best_spend_loc, _spend_score)

    # ── Pick best action ──────────────────────────────────────────────────────
    all_candidates: dict[str, float] = dict(local_candidates)
    for dest, score in travel_candidates.items():
        all_candidates[f"travel:{dest}"] = score

    if not all_candidates:
        return "idle"

    best_action = max(all_candidates, key=all_candidates.__getitem__)

    if all_candidates[best_action] <= 0:
        return "idle"

    # Sticky intercept: if travel wins but mortal is at a resource with cargo room,
    # collect first and lock in the destination for next tick.
    if best_action.startswith("travel:") and _at_resource and not _hold_full and _collect_score > 0:
        cs.pending_travel_dest = best_action[len("travel:"):]
        return "collect"

    return best_action
