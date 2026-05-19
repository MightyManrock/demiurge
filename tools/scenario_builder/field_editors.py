"""
Generic field editors for the scenario builder. Used by the per-entity
sub-menus (Civilization, Pop, Mortal, World, Species, Universe) to edit
shared field shapes:

  - `dict[str, float]` — beliefs, culture, domain_expression, belief_tags.
    Add/edit/remove sub-menu; tags drawn from a configurable namespace
    (canonical `domain:` list, canonical `culture:` list, or free-form text).
  - `list[str]` — geo/atmo/bio/personal/status tags. Add/remove sub-menu;
    same namespace options.
  - `LocFootprint` — the four-float struct on `SignificantLocation`.

The functions take a `BuilderScreen` so they can drive modal flows
(`screen.app.push_screen_wait`), mark the screen dirty, and refresh after
each mutation. They are coroutine helpers; callers `await` them inside an
existing `@work` flow.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from core.universe_core import CosmicCoordinates, LocFootprint
from ui.constants import BACK
from ui.modals import ErrorModal, PickerModal, TextFormModal
from utilities.culture_registry import ALL_CULTURE_TAGS
from utilities.domain_registry import DOMAIN_TAGS

if TYPE_CHECKING:
    from .screen import BuilderScreen


# ── Tag pickers ────────────────────────────────────────────────────────────

async def _pick_tag(
    screen: "BuilderScreen", namespace: str, exclude: set[str],
) -> Optional[str]:
    """Pick a single tag.

    namespace:
      - "domain" — picker over the 16 canonical `domain:` tags.
      - "culture" — picker over the canonical `culture:` tags.
      - "free" — free-form text input.

    Returns the chosen tag string, or None on cancel.
    """
    if namespace == "domain":
        items = [
            (t, t.removeprefix("domain:").title())
            for t in DOMAIN_TAGS if t not in exclude
        ]
        if not items:
            await screen.app.push_screen_wait(ErrorModal(
                "All canonical domain tags are already assigned."
            ))
            return None
        result = await screen.app.push_screen_wait(PickerModal(
            title="Pick a domain tag", items=items, show_back=True,
        ))
        return None if result in (None, BACK) else result
    if namespace == "culture":
        items = [
            (t, t.removeprefix("culture:").replace("_", " ").title())
            for t in ALL_CULTURE_TAGS if t not in exclude
        ]
        if not items:
            await screen.app.push_screen_wait(ErrorModal(
                "All canonical culture tags are already assigned."
            ))
            return None
        result = await screen.app.push_screen_wait(PickerModal(
            title="Pick a culture tag", items=items, show_back=True,
        ))
        return None if result in (None, BACK) else result
    # Free-form text input
    result = await screen.app.push_screen_wait(TextFormModal(
        title="Add tag (free-form)",
        description=(
            "Enter a tag like `geo:terrestrial` or `bio:bipedal`. The "
            "scenario builder does not constrain the prefix — use whatever "
            "convention your scenario expects."
        ),
        fields=[("Tag", "tag", "")],
        show_back=True,
    ))
    if result in (None, BACK):
        return None
    tag = result["tag"].strip()
    if not tag:
        return None
    if tag in exclude:
        await screen.app.push_screen_wait(ErrorModal(f"Tag {tag!r} already present."))
        return None
    return tag


async def _prompt_weight(
    screen: "BuilderScreen", tag: str, current: Optional[float] = None,
) -> Optional[float]:
    """Prompt the user for a [0.0, 1.0] weight. Returns the validated float
    or None on cancel."""
    result = await screen.app.push_screen_wait(TextFormModal(
        title=f"Weight for {tag}",
        fields=[(
            "Weight (0.0 to 1.0)", "weight",
            f"{current}" if current is not None else "0.5",
        )],
        show_back=True,
    ))
    if result in (None, BACK):
        return None
    try:
        v = float(result["weight"])
    except (KeyError, ValueError):
        await screen.app.push_screen_wait(ErrorModal("Weight must be a number."))
        return None
    if not (0.0 <= v <= 1.0):
        await screen.app.push_screen_wait(ErrorModal(
            "Weight must be between 0.0 and 1.0."
        ))
        return None
    return v


# ── Tag→weight dict editor ─────────────────────────────────────────────────

async def edit_tag_weight_dict(
    screen: "BuilderScreen",
    target: dict[str, float],
    title_prefix: str,
    tag_namespace: str,
) -> None:
    """Loop add/edit/remove on `target` (dict[str, float]). Mutates in place.

    `tag_namespace` controls the picker shown when adding a new key:
    "domain" / "culture" / "free".
    """
    while True:
        n = len(target)
        choice = await screen.app.push_screen_wait(PickerModal(
            title=f"{title_prefix} ({n} entr{'y' if n == 1 else 'ies'})",
            items=[
                ("add",    "+ Add entry"),
                ("edit",   "Edit a weight"),
                ("remove", "Remove an entry"),
                ("done",   "Done"),
            ],
        ))
        if choice in (None, "done"):
            return
        if choice == "add":
            tag = await _pick_tag(screen, tag_namespace, set(target.keys()))
            if tag is None:
                continue
            weight = await _prompt_weight(screen, tag, None)
            if weight is None:
                continue
            target[tag] = weight
            screen.mark_dirty(); screen._refresh_all()
        elif choice == "edit":
            if not target:
                await screen.app.push_screen_wait(ErrorModal("Nothing to edit."))
                continue
            picked = await screen.app.push_screen_wait(PickerModal(
                title="Edit which entry?",
                items=[
                    (t, f"{t}  ({w:.2f})")
                    for t, w in sorted(target.items(), key=lambda kv: -kv[1])
                ],
                show_back=True,
            ))
            if picked in (None, BACK):
                continue
            weight = await _prompt_weight(screen, picked, current=target[picked])
            if weight is None:
                continue
            target[picked] = weight
            screen.mark_dirty(); screen._refresh_all()
        elif choice == "remove":
            if not target:
                await screen.app.push_screen_wait(ErrorModal("Nothing to remove."))
                continue
            picked = await screen.app.push_screen_wait(PickerModal(
                title="Remove which entry?",
                items=[
                    (t, f"{t}  ({w:.2f})")
                    for t, w in sorted(target.items(), key=lambda kv: -kv[1])
                ],
                show_back=True,
            ))
            if picked in (None, BACK):
                continue
            target.pop(picked, None)
            screen.mark_dirty(); screen._refresh_all()


# ── String-list editor ─────────────────────────────────────────────────────

async def edit_string_list(
    screen: "BuilderScreen",
    target: list[str],
    title_prefix: str,
    tag_namespace: str = "free",
    max_items: Optional[int] = None,
) -> None:
    """Loop add/remove on `target` (list[str]). Mutates in place.

    `tag_namespace` controls the picker shown when adding: "domain" /
    "culture" / "free". `max_items`, when set, refuses adds beyond that cap.
    """
    while True:
        n = len(target)
        cap_str = f"/{max_items}" if max_items is not None else ""
        choice = await screen.app.push_screen_wait(PickerModal(
            title=f"{title_prefix} ({n}{cap_str} entr{'y' if n == 1 else 'ies'})",
            items=[
                ("add",    "+ Add entry"),
                ("remove", "Remove an entry"),
                ("done",   "Done"),
            ],
        ))
        if choice in (None, "done"):
            return
        if choice == "add":
            if max_items is not None and len(target) >= max_items:
                await screen.app.push_screen_wait(ErrorModal(
                    f"Already at the {max_items}-entry cap. Remove one before adding another."
                ))
                continue
            tag = await _pick_tag(screen, tag_namespace, set(target))
            if tag is None:
                continue
            target.append(tag)
            screen.mark_dirty(); screen._refresh_all()
        elif choice == "remove":
            if not target:
                await screen.app.push_screen_wait(ErrorModal("Nothing to remove."))
                continue
            picked = await screen.app.push_screen_wait(PickerModal(
                title="Remove which entry?",
                items=[(t, t) for t in target],
                show_back=True,
            ))
            if picked in (None, BACK):
                continue
            try:
                target.remove(picked)
            except ValueError:
                pass
            screen.mark_dirty(); screen._refresh_all()


# ── Enum-list editor ───────────────────────────────────────────────────────

async def edit_enum_list(
    screen: "BuilderScreen",
    target: list,
    enum_items: list[tuple[str, str]],
    enum_class,
    title_prefix: str,
) -> None:
    """Loop add/remove on a `list[EnumValue]`. `enum_items` is the full set
    of (value, display) tuples; `enum_class` coerces the picker's string
    back to a real enum member."""
    while True:
        n = len(target)
        choice = await screen.app.push_screen_wait(PickerModal(
            title=f"{title_prefix} ({n} entr{'y' if n == 1 else 'ies'})",
            items=[
                ("add",    "+ Add entry"),
                ("remove", "Remove an entry"),
                ("done",   "Done"),
            ],
        ))
        if choice in (None, "done"):
            return
        if choice == "add":
            existing = {e.value for e in target}
            candidates = [(v, d) for (v, d) in enum_items if v not in existing]
            if not candidates:
                await screen.app.push_screen_wait(ErrorModal(
                    "Every value is already present."
                ))
                continue
            picked = await screen.app.push_screen_wait(PickerModal(
                title="Pick a value to add", items=candidates, show_back=True,
            ))
            if picked in (None, BACK):
                continue
            target.append(enum_class(picked))
            screen.mark_dirty(); screen._refresh_all()
        elif choice == "remove":
            if not target:
                await screen.app.push_screen_wait(ErrorModal("Nothing to remove."))
                continue
            items = [(e.value, e.value.title()) for e in target]
            picked = await screen.app.push_screen_wait(PickerModal(
                title="Remove which?", items=items, show_back=True,
            ))
            if picked in (None, BACK):
                continue
            target[:] = [e for e in target if e.value != picked]
            screen.mark_dirty(); screen._refresh_all()


# ── CosmicCoordinates editor ───────────────────────────────────────────────

async def edit_coordinates(
    screen: "BuilderScreen",
    target: CosmicCoordinates,
) -> None:
    """One-shot text form for x/y/z. No range constraint — the simulation
    treats coords as relative position; magnitudes scale with the entity's
    place in the hierarchy (galaxy >> system >> world)."""
    result = await screen.app.push_screen_wait(TextFormModal(
        title="Coordinates (x, y, z)",
        description=(
            "Relative position in the universe. Galaxy-level coords sit on "
            "a much larger effective scale than system-level coords — see "
            "`_GALAXY_SCALE` in tick_logic. Any float is acceptable."
        ),
        fields=[
            ("x", "x", f"{target.x}"),
            ("y", "y", f"{target.y}"),
            ("z", "z", f"{target.z}"),
        ],
        show_back=True,
    ))
    if result in (None, BACK):
        return
    try:
        x = float(result["x"])
        y = float(result["y"])
        z = float(result["z"])
    except (KeyError, ValueError):
        await screen.app.push_screen_wait(ErrorModal(
            "All three coordinates must be numbers."
        ))
        return
    target.x = x
    target.y = y
    target.z = z
    screen.mark_dirty(); screen._refresh_all()


# ── LocFootprint editor ────────────────────────────────────────────────────

async def edit_loc_footprint(
    screen: "BuilderScreen",
    target: LocFootprint,
) -> None:
    """One-shot text form for the four LocFootprint floats. Each in [0,1]."""
    result = await screen.app.push_screen_wait(TextFormModal(
        title="Local divine footprint",
        description=(
            "Per-location footprint accumulator. All four floats range "
            "0.0–1.0 and persist across ticks (they decay slowly during "
            "passive simulation phases)."
        ),
        fields=[
            ("Overt miracles",   "overt_miracles",   f"{target.overt_miracles}"),
            ("Subtle influence", "subtle_influence", f"{target.subtle_influence}"),
            ("Proxius activity", "proxius_activity", f"{target.proxius_activity}"),
            ("Direct creation",  "direct_creation",  f"{target.direct_creation}"),
        ],
        show_back=True,
    ))
    if result in (None, BACK):
        return
    try:
        values = {k: float(result[k]) for k in (
            "overt_miracles", "subtle_influence", "proxius_activity", "direct_creation",
        )}
    except (KeyError, ValueError):
        await screen.app.push_screen_wait(ErrorModal("All values must be numbers."))
        return
    for label, v in values.items():
        if not (0.0 <= v <= 1.0):
            await screen.app.push_screen_wait(ErrorModal(
                f"{label} must be between 0.0 and 1.0."
            ))
            return
    target.overt_miracles   = values["overt_miracles"]
    target.subtle_influence = values["subtle_influence"]
    target.proxius_activity = values["proxius_activity"]
    target.direct_creation  = values["direct_creation"]
    screen.mark_dirty(); screen._refresh_all()
