"""
Luminary, Constraint, and domain-affinity helpers for Phase 6 of the
scenario builder.

Affinity caps mirror the scenario_loader validator:
  - per-(Luminary, Domain): 0.8
  - sum across one Luminary: 2.0
  - sum across the Pantheon for one Domain: 0.9

The builder warns (does not block) when an edit would violate one of
these — authors may want to play with extreme values, and the loader
will re-check at game launch.
"""
from __future__ import annotations
from typing import Optional
from uuid import UUID

from core.onto_core import Constraint, Disposition, Luminary
from utilities.domain_registry import DOMAIN_TAGS


# Mirrors of scenario_loader.py constants; duplicated here to avoid a
# loader→builder dependency for a constants-only import.
MAX_INDIVIDUAL_AFFINITY = 0.8
MAX_LUMINARY_AFFINITY   = 2.0
MAX_PANTHEON_AFFINITY   = 0.9


# ── Picker label builders ──────────────────────────────────────────────────

def luminary_picker_items(state) -> list[tuple[str, str]]:
    rows = []
    for lid, lum in state.luminaries.items():
        n_domains = len(lum.domains)
        d = lum.disposition
        rows.append((lid, f"{lum.name}  ({n_domains} domain{'s' if n_domains != 1 else ''}, res{d.results:+.2f} meth{d.methods:+.2f})"))
    rows.sort(key=lambda kv: kv[1].lower())
    return rows


def domain_tag_picker_items(exclude: Optional[set[str]] = None) -> list[tuple[str, str]]:
    """Picker over the 16 canonical domain tags. If `exclude` is supplied,
    those tags are omitted (used so '+ Add domain' on a luminary doesn't
    re-offer ones already assigned)."""
    excl = exclude or set()
    return [
        (tag, tag.removeprefix("domain:").title())
        for tag in DOMAIN_TAGS if tag not in excl
    ]


def existing_domain_picker_items(lum: Luminary) -> list[tuple[str, str]]:
    rows = [
        (tag, f"{tag.removeprefix('domain:').title()}  ({aff:.2f})")
        for tag, aff in sorted(lum.domains.items(), key=lambda kv: -kv[1])
    ]
    return rows


def pantheon_sum_for_domain(
    state, tag: str, exclude_luminary_id=None,
) -> float:
    """Sum of `domain[tag]` across every Luminary in the pantheon.
    Optionally exclude one Luminary so the caller can compute "the rest
    of the pantheon's total" without their own contribution."""
    total = 0.0
    for lum in state.luminaries.values():
        if exclude_luminary_id is not None and lum.id == exclude_luminary_id:
            continue
        total += lum.domains.get(tag, 0.0)
    return total


def luminary_total_affinity(lum: Luminary) -> float:
    return sum(lum.domains.values())


def domain_picker_items_with_sums(state, lum: Luminary) -> list[tuple[str, str]]:
    """Like `domain_tag_picker_items` (excludes tags already on `lum`) but
    annotates each row with the pantheon sum so far for that domain — useful
    when adding to spot how much room is left under MAX_PANTHEON_AFFINITY."""
    exclude = set(lum.domains.keys())
    rows = []
    for tag in DOMAIN_TAGS:
        if tag in exclude:
            continue
        pantheon_sum = pantheon_sum_for_domain(state, tag, exclude_luminary_id=lum.id)
        head = MAX_PANTHEON_AFFINITY - pantheon_sum
        cap_note = ""
        if head < 0.05:
            cap_note = "  ⚠ no headroom"
        elif head < 0.2:
            cap_note = f"  (only {head:.2f} headroom)"
        rows.append((
            tag,
            f"{tag.removeprefix('domain:').title()}"
            f"  [pantheon: {pantheon_sum:.2f}/{MAX_PANTHEON_AFFINITY:.1f}]"
            f"{cap_note}",
        ))
    return rows


def affinity_form_description(
    state, lum: Luminary, tag: str, exclude_self: bool = True,
) -> str:
    """Render a multi-line description for the affinity weight form so the
    user sees the per-Luminary and per-domain headroom before committing."""
    cur_self = lum.domains.get(tag, 0.0) if exclude_self else 0.0
    lum_sum_other = luminary_total_affinity(lum) - cur_self
    lum_head = MAX_LUMINARY_AFFINITY - lum_sum_other
    pantheon_other = pantheon_sum_for_domain(
        state, tag, exclude_luminary_id=lum.id,
    )
    pantheon_head = MAX_PANTHEON_AFFINITY - pantheon_other
    return (
        f"Per-(Luminary, Domain) cap: ≤ {MAX_INDIVIDUAL_AFFINITY:.2f}.  "
        f"You can spend up to {min(lum_head, MAX_INDIVIDUAL_AFFINITY):.2f} "
        f"on this domain without exceeding caps:\n"
        f"  • {lum.name}'s remaining per-Luminary budget: "
        f"{lum_head:.2f} (of {MAX_LUMINARY_AFFINITY:.1f})\n"
        f"  • Pantheon headroom on {tag}: "
        f"{pantheon_head:.2f} (others have {pantheon_other:.2f})"
    )


def constraint_picker_items(constraints: list[Constraint]) -> list[tuple[str, str]]:
    return [
        (str(c.id), f"{c.name}  [enforcement {c.enforcement_weight:.2f}]")
        for c in constraints
    ]


# ── Text-field schemas ─────────────────────────────────────────────────────

def basics_fields(lum: Optional[Luminary] = None, attention: float = 0.0) -> list[tuple[str, str, str]]:
    d = lum.disposition if lum else Disposition()
    return [
        ("Name",                  "name",       lum.name if lum else "New Luminary"),
        ("Disposition.results (-1.0 to 1.0)",  "results",  f"{d.results}"),
        ("Disposition.methods (-1.0 to 1.0)",  "methods",  f"{d.methods}"),
        ("Starting attention (0.0 to 1.0)",    "attention", f"{attention}"),
    ]


def constraint_fields(c: Optional[Constraint] = None) -> list[tuple[str, str, str]]:
    return [
        ("Name",        "name",        c.name if c else "New Constraint"),
        ("Description", "description", c.description if c else ""),
        ("Enforcement weight (0.0 to 1.0)", "enforcement_weight",
         f"{c.enforcement_weight}" if c else "0.5"),
    ]


def constraint_domain_tag_items() -> list[tuple[str, str]]:
    """Picker items for the optional `domain_tag` on a Constraint.
    First entry is the '(none)' sentinel that maps to None on the model."""
    items: list[tuple[str, str]] = [("__none__", "(no domain — general expectation)")]
    items.extend(
        (tag, tag.removeprefix("domain:").title()) for tag in DOMAIN_TAGS
    )
    return items


def affinity_field(tag: str, current: Optional[float] = None) -> list[tuple[str, str, str]]:
    label = f"Affinity for {tag.removeprefix('domain:').title()} (0.0 to {MAX_INDIVIDUAL_AFFINITY})"
    return [(label, "affinity", f"{current}" if current is not None else "0.3")]


# ── Validation ─────────────────────────────────────────────────────────────

def validate_basics(result: dict[str, str]) -> Optional[str]:
    if not result.get("name", "").strip():
        return "Name cannot be empty."
    try:
        r = float(result["results"])
        m = float(result["methods"])
        a = float(result["attention"])
    except (KeyError, TypeError, ValueError):
        return "Disposition + attention values must be numbers."
    if not (-1.0 <= r <= 1.0):
        return "Disposition.results must be between -1.0 and 1.0."
    if not (-1.0 <= m <= 1.0):
        return "Disposition.methods must be between -1.0 and 1.0."
    if not (0.0 <= a <= 1.0):
        return "Starting attention must be between 0.0 and 1.0."
    return None


def validate_constraint(result: dict[str, str]) -> Optional[str]:
    if not result.get("name", "").strip():
        return "Constraint name cannot be empty."
    try:
        w = float(result["enforcement_weight"])
    except (KeyError, TypeError, ValueError):
        return "Enforcement weight must be a number."
    if not (0.0 <= w <= 1.0):
        return "Enforcement weight must be between 0.0 and 1.0."
    return None


def validate_affinity(result: dict[str, str]) -> tuple[Optional[float], Optional[str]]:
    try:
        v = float(result["affinity"])
    except (KeyError, TypeError, ValueError):
        return None, "Affinity must be a number."
    if v < 0:
        return None, "Affinity cannot be negative."
    return v, None


def check_affinity_caps(
    state, luminary: Luminary, domain_tag: str, new_value: float,
    exclude_self_from_pantheon: bool = True,
) -> list[str]:
    """Return human-readable warning strings for any of the three caps the
    proposed (luminary, domain_tag, new_value) tuple would violate. Empty
    list means no warnings. The builder surfaces these as a soft warning;
    the loader's `validate_luminary_affinities` is the authoritative check.
    """
    warns: list[str] = []
    if new_value > MAX_INDIVIDUAL_AFFINITY:
        warns.append(
            f"affinity {new_value:.2f} exceeds the per-(Luminary, Domain) "
            f"cap of {MAX_INDIVIDUAL_AFFINITY}"
        )
    # Sum across the luminary if this edit lands.
    other_sum = sum(
        v for tag, v in luminary.domains.items() if tag != domain_tag
    )
    new_sum = other_sum + new_value
    if new_sum > MAX_LUMINARY_AFFINITY:
        warns.append(
            f"total affinity for {luminary.name} would reach {new_sum:.2f}, "
            f"exceeding the per-Luminary cap of {MAX_LUMINARY_AFFINITY}"
        )
    # Pantheon sum for this domain.
    pantheon_sum = 0.0
    for lum in state.luminaries.values():
        if exclude_self_from_pantheon and lum.id == luminary.id:
            continue
        pantheon_sum += lum.domains.get(domain_tag, 0.0)
    pantheon_sum += new_value
    if pantheon_sum > MAX_PANTHEON_AFFINITY:
        warns.append(
            f"pantheon total for {domain_tag} would reach {pantheon_sum:.2f}, "
            f"exceeding the pantheon cap of {MAX_PANTHEON_AFFINITY}"
        )
    return warns


# ── Construction & mutation ────────────────────────────────────────────────

def construct_luminary(fields: dict[str, str], pantheon_id: UUID) -> Luminary:
    """Build a Luminary with empty domains. The caller adds affinities via
    the domain sub-editor after creation."""
    return Luminary(
        name=fields["name"].strip(),
        domains={},
        pantheon_id=pantheon_id,
        disposition=Disposition(
            results=float(fields["results"]),
            methods=float(fields["methods"]),
        ),
    )


def apply_basics(lum: Luminary, fields: dict[str, str]) -> None:
    lum.name = fields["name"].strip()
    lum.disposition.results = float(fields["results"])
    lum.disposition.methods = float(fields["methods"])


def construct_constraint(
    fields: dict[str, str], domain_tag: Optional[str] = None,
) -> Constraint:
    return Constraint(
        name=fields["name"].strip(),
        description=fields["description"],
        enforcement_weight=float(fields["enforcement_weight"]),
        domain_tag=domain_tag,
    )


def apply_constraint_fields(
    c: Constraint, fields: dict[str, str], domain_tag: Optional[str] = None,
) -> None:
    c.name = fields["name"].strip()
    c.description = fields["description"]
    c.enforcement_weight = float(fields["enforcement_weight"])
    c.domain_tag = domain_tag


# ── Back-reference housekeeping ────────────────────────────────────────────

def link_luminary_to_pantheon(state, lum: Luminary) -> None:
    """Register a freshly-created Luminary in the Pantheon's luminary_ids
    list. Caller already set lum.pantheon_id."""
    if lum.id not in state.pantheon.luminary_ids:
        state.pantheon.luminary_ids.append(lum.id)


def unlink_luminary_back_refs(state, lum: Luminary) -> None:
    """Strip a Luminary's id from Pantheon.luminary_ids and Demiurge's
    liege_luminary_ids. Mortals appointed as Heralds by this Luminary
    keep their `appointed_by_luminary` pointer (now dangling) — Phase 5
    backlog will deal with role reassignment more comprehensively."""
    state.pantheon.luminary_ids = [
        x for x in state.pantheon.luminary_ids if x != lum.id
    ]
    state.demiurge.liege_luminary_ids = [
        x for x in state.demiurge.liege_luminary_ids if x != lum.id
    ]
    # Drop the per-luminary state-side maps.
    state.luminary_attention.pop(str(lum.id), None)
    state.ticks_since_evaluation.pop(str(lum.id), None)


def find_luminary_references(state, lum_id: str) -> list[str]:
    """Soft check — list mortals appointed by this Luminary as Heralds.
    Phase 6 still allows delete (the back-ref scrub leaves them dangling
    rather than reassigning), but the user gets a warning first."""
    try:
        lid = UUID(lum_id)
    except (TypeError, ValueError):
        return []
    notes: list[str] = []
    for mid, m in state.mortals.items():
        if m.appointed_by_luminary == lid:
            notes.append(f"herald appointed by this Luminary: {m.name}")
    return notes
