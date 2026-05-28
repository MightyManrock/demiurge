"""Occupation alias registry.

Maps `(occupation, CivilizationScale)` → display alias, supporting the Pop
display-name fallback chain (explicit name → occupation alias → stratum).

Encoding inside the per-occupation row:
    None  — the (occupation, scale) combination is non-meaningful (N/A).
            Callers fall back to the stratum label.
    ""    — "use the per-occupation default" (the "—" rows in the design doc).
            Defaults are the occupation key Title-Cased, or an entry in
            `_OCCUPATION_DEFAULTS` when something nicer is available.
    "Xxx" — explicit alias used verbatim.

Authored from `docs/.dev/Brainstorming/occupation_list.md`.
"""

from __future__ import annotations

from typing import Optional

from core.universe_core import CivilizationScale


# Scale order matches the design doc rows (≤ Pre-sapient collapses both
# NON_SENTIENT and PRE_SAPIENT into one entry via `_row`).
_SCALE_ORDER: tuple[CivilizationScale, ...] = (
    CivilizationScale.NASCENT,
    CivilizationScale.TRIBAL,
    CivilizationScale.CITY_STATE,
    CivilizationScale.REGIONAL,
    CivilizationScale.CONTINENTAL,
    CivilizationScale.PLANETARY,
    CivilizationScale.INTERPLANETARY,
    CivilizationScale.INTERSTELLAR,
    CivilizationScale.INTERGALACTIC,
)


def _row(le_presap: Optional[str], *rest: Optional[str]) -> dict[CivilizationScale, Optional[str]]:
    """Build one occupation row. First arg covers ≤ Pre-sapient (both NON_SENTIENT
    and PRE_SAPIENT); the remaining 9 args follow `_SCALE_ORDER`."""
    if len(rest) != len(_SCALE_ORDER):
        raise ValueError(f"_row expects {len(_SCALE_ORDER) + 1} values, got {len(rest) + 1}")
    out: dict[CivilizationScale, Optional[str]] = {
        CivilizationScale.NON_SENTIENT: le_presap,
        CivilizationScale.PRE_SAPIENT: le_presap,
    }
    for scale, val in zip(_SCALE_ORDER, rest):
        out[scale] = val
    return out


# Per-occupation override for the "—" / `""` case. When absent, the default is
# the occupation key Title-Cased.
_OCCUPATION_DEFAULTS: dict[str, str] = {
    "poli_admin": "Administrator",
}


# Columns: ≤Pre-sap | Nascent | Tribal | City-State | Regional | Continental | Planetary | Interplanetary | Interstellar | Intergalactic
OCCUPATION_ALIASES: dict[str, dict[CivilizationScale, Optional[str]]] = {
    # --- Wild ---
    "forager":      _row("Grazer",   "Scraper", "Nomad",  "Barbarian", "Wildfolk", "Wildfolk",   "Uncontacted", "Uncontacted", "Uncontacted", "Uncontacted"),
    "raider":       _row("Predator", "",        "",       "Brigand",   "Brigand",  "Outlaw",     "Outlaw",      "Pirate",      "Pirate",      "Pirate"),

    # --- Feral ---
    "outcast":      _row(None, "",     "",       "Vagabond", "Vagabond", "Vagabond", "Displaced", "Stateless", "Stateless", "Stateless"),
    "criminal":     _row(None, None,   "Bandit", "Bandit",   "Bandit",   "",         "",          "",          "",          ""),

    # --- Underclass ---
    "bonded":       _row(None, None, "Thrall", "Slave",  "Serf",   "Slave",     "Servant",   "",          "",          ""),
    "dispossessed": _row(None, None, None,     "Beggar", "Beggar", "Destitute", "Destitute", "",          "",          ""),

    # --- Common ---
    "producer":     _row(None, "Hunter-Gatherer", "Farmer", "Peasant", "Peasant", "Farmer", "Farmer", "Farmer", "Agrispecialist", "Nutrispecialist"),
    "laborer":      _row(None, "Porter",          "Worker", "Worker",  "Worker",  "",       "",       "",       "",               ""),
    "service":      _row(None, None,              None,     "Seller",  "Seller",  "Vendor", "",       "",       "",               ""),
    "transport":    _row(None, None,              None,     "Carter",  "Teamster","Driver", "Freight","Freight","Freight",        "Freight"),
    "professional": _row(None, None,              None,     None,      "Clerk",   "Clerk",  "",       "",       "",               ""),

    # --- Artisan ---
    "crafter":      _row(None, "", "",     "Guild",     "Guild",   "",           "",           "",           "Fabricator", "Fabricator"),
    "builder":      _row(None, None, "",   "Mason",     "Mason",   "Construction","Construction","Construction","Construction","Construction"),
    "engineer":     _row(None, None, None, "Architect", "Meister", "Machinist",  "",           "",           "",           ""),
    "technician":   _row(None, None, None, None,        None,      "Mechanic",   "",           "",           "",           ""),
    "healer":       _row(None, None, None, None,        "",        "Doctor",     "Physician",  "Physician",  "Biomed",     "Biomed"),
    "artist":       _row(None, "",   "",   "",          "",        "",           "",           "",           "",           ""),

    # --- Trader ---
    "merchant":     _row(None, None, "Peddler", "Peddler",      "",       "",       "",          "",          "",          ""),
    "financier":    _row(None, None, None,      "Moneylender",  "Banker", "Banker", "",          "",          "",          ""),
    "executive":    _row(None, None, None,      None,           None,     "",       "Corporate", "Corporate", "Corporate", "Corporate"),

    # --- Warrior ---
    "soldier":      _row(None, None,    None,    "",      "",      "",       "",         "",         "",         ""),
    "officer":      _row(None, None,    None,    None,    "Knight","",       "",         "",         "",         ""),
    "guard":        _row(None, None,    None,    "Watch", "",      "Police", "Police",   "Security", "Security", "Security"),
    "mercenary":    _row(None, None,    None,    "Sellsword", "Sellsword", "", "",       "",         "",         ""),
    "militia":      _row(None, "Brave", "Brave", "Fighter",   "Levy",      "Levy", "",  "",         "",         ""),

    # --- Scholar ---
    "clergy":       _row(None, None, "Shaman", "Priest", "Priest", "", "", "", "", ""),
    "scientist":    _row(None, None, None,     None,     None,     "", "", "", "", ""),
    "academic":     _row(None, None, None,     "Scribe", "Philosopher", "", "", "", "", ""),

    # --- Elite ---
    "poli_admin":   _row(None, None, None, "Council",    "Minister", "Minister", "Senate", "Senate", "Administrator", "Administrator"),
    "noble":        _row(None, None, None, "Aristocrat", "",         "",         "",       "",       "",              ""),
}


def _default_for(occupation: str) -> str:
    """Per-occupation default used when an alias cell is `""` (the doc's '—')."""
    if occupation in _OCCUPATION_DEFAULTS:
        return _OCCUPATION_DEFAULTS[occupation]
    return occupation.replace("_", " ").title()


def occupation_alias(occupation: str, scale: Optional[CivilizationScale]) -> Optional[str]:
    """Resolve `(occupation, scale)` to a display alias.

    Returns:
        - The explicit alias string when one is authored.
        - The per-occupation default (or Title-Cased key) when the cell is `""`.
        - `None` when the cell is N/A, the occupation is unknown, or scale is None.
          Callers should fall back to the stratum label in that case.
    """
    if not occupation or scale is None:
        return None
    row = OCCUPATION_ALIASES.get(occupation)
    if row is None:
        return None
    cell = row.get(scale)
    if cell is None:
        return None
    if cell == "":
        return _default_for(occupation)
    return cell


def pop_display_name(pop, civ) -> str:
    """Three-step Pop name resolution:
        1. `pop.name` if set,
        2. occupation alias resolved against `civ.scale` if both present,
        3. stratum label (e.g. "Common", or "wild"/wild_stratum for wild pops).

    `civ` may be None (e.g. wild pops with no civilization attached); the
    occupation-alias step is then skipped.
    """
    if getattr(pop, "name", None):
        return pop.name

    occupation = getattr(pop, "occupation", "") or ""
    scale = getattr(civ, "scale", None) if civ is not None else None
    alias = occupation_alias(occupation, scale)
    if alias is not None:
        return alias

    stratum = getattr(pop, "stratum", None)
    if not stratum:
        return "Pop"
    if stratum == "wild":
        return "wild"
    return stratum.title()
