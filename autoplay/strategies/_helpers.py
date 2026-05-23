"""
autoplay/strategies/_helpers.py — shared lookup utilities for strategy modules.

All lookups are by name (or by predicate), so strategies remain stable across
database rebuilds. Strategy modules should never hold scenario UUIDs as
constants.
"""
from __future__ import annotations
from uuid import UUID
from typing import Optional, Tuple

from core.action_core import ActionInstance, TargetType
from core.universe_core import MortalRole, MortalStatus, SocialClass
from logic.tick_logic import TickLoop, SimulationState, is_mortal_visible


def queue(loop: TickLoop, state: SimulationState, key: str,
          target_type: TargetType, target_id, intent=None, proxius_id=None):
    defn = loop._action_library[key]
    inst = ActionInstance(
        action_definition_id=defn.id,
        target_type=target_type,
        target_id=target_id,
        timestamp=state.universe.current_age.to_float_years(),
        demiurge_id=state.demiurge.id,
        proxius_id=proxius_id,
        intent=intent,
    )
    state.action_queue.append(inst)
    return inst


def mortal_named(state: SimulationState, name: str):
    for mid, m in state.mortals.items():
        if m.name == name:
            return mid, m
    return None, None


def visible_named(state: SimulationState, name: str):
    mid, m = mortal_named(state, name)
    if mid and is_mortal_visible(m):
        return mid, m
    return None, None


def active_proxii(state: SimulationState):
    return [(mid, m) for mid, m in state.mortals.items()
            if m.role == MortalRole.PROXIUS and m.status == MortalStatus.ACTIVE]


def world_id(state: SimulationState, name: str) -> UUID:
    return UUID(next(wid for wid, w in state.worlds.items() if w.name == name))


def civ_id(state: SimulationState, name_substring: str) -> UUID:
    """Return the first civilization whose name contains `name_substring`."""
    return UUID(next(cid for cid, c in state.civilizations.items()
                     if name_substring in c.name))


def lum_id(state: SimulationState, name: str) -> UUID:
    return UUID(next(lid for lid, l in state.luminaries.items() if l.name == name))


def location_id(state: SimulationState, name: str) -> UUID:
    return UUID(next(lid for lid, l in state.locations.items() if l.name == name))


def pop_at(
    state: SimulationState,
    civ_name_substring: str,
    location_name: str,
    social_class: SocialClass,
) -> Optional[Tuple[str, object]]:
    """Find the pop matching (civilization name fragment, location name, class)."""
    for pid, p in state.pops.items():
        civ = state.civilizations.get(str(p.civilization_id))
        if not (civ and civ_name_substring in civ.name):
            continue
        if p.social_class != social_class:
            continue
        loc = state.locations.get(str(p.current_location))
        if not (loc and loc.name == location_name):
            continue
        return pid, p
    return None
