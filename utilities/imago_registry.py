#!/usr/bin/env python3
"""
imago_registry.py
Scenario-agnostic Imago tree definitions for the four implemented trees:
Change, Conflict, Order, and Silence.

Loads from (and bootstraps) core/core.db. Provides:
  - All 28 Imago nodes (7 per tree) with names, descriptions, and mechanics
  - get_node(node_id), nodes_for_tree(tree), prerequisites_for(node_id)
  - is_unlockable(node_id, unlocked_set)  -- prerequisite check
  - is_drawable(node_id)  -- T4 nodes cannot be drawn from the Underreal
"""

from __future__ import annotations
import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

_PROJECT_ROOT = Path(__file__).parent.parent
DEFAULT_CORE_DB = _PROJECT_ROOT / "core" / "core.db"


@dataclass(frozen=True)
class ImagoNode:
    node_id: str            # e.g. "change:t1:wheel"
    tree: str               # e.g. "change"
    tier: int               # 1–4
    name: str
    tooltip_blurb: str      # empty string for T4 apex nodes
    description: str
    mechanics: dict[str, float]  # "domain:xxx" or "culture:xxx" -> modifier
    min_prereqs: int        # how many listed prerequisites must be in unlocked set
    sort_order: int


# ── Canonical Imago node data ─────────────────────────────────────────
# Prerequisite unlock rules (enforced via min_prereqs + imago_prerequisite table):
#   T1: no prerequisites (min_prereqs=0)
#   T2: any 1 of the 2 T1 nodes in the same tree (min_prereqs=1, 2 candidates listed)
#   T3: a specific T2 node (min_prereqs=1, 1 candidate listed)
#   T4: all 6 prior nodes in the tree (min_prereqs=6, 6 candidates listed)
#
# T4 nodes cannot be drawn from the Underreal (is_drawable returns False for tier==4).

_IMAGO_NODES: list[ImagoNode] = [

    # ── CHANGE ──────────────────────────────────────────────────────────

    ImagoNode(
        "change:t1:wheel", "change", 1,
        "The Turning Wheel",
        "What you were must be given up before what you will become can exist.",
        "Every turning of the wheel costs something, for transformation demands sacrifice. "
        "But the wheel also prevents mastery; constant change is the enemy of expertise, "
        "and you never stay anywhere long enough to become truly skilled.",
        {"domain:change": 0.35, "domain:sacrifice": 0.1, "domain:mastery": -0.1,
         "culture:animism": 0.2, "culture:humility": 0.2},
        0, 0,
    ),
    ImagoNode(
        "change:t1:wall", "change", 1,
        "The Crumbling Wall",
        "Change reveals the emptiness that was always hidden inside what was built.",
        "As the wall crumbles, void opens behind it—not emptiness created by loss, but emptiness "
        "that was always there, concealed by structure. Crumbling structures take communities with them.",
        {"domain:change": 0.3, "domain:void": 0.08, "domain:community": -0.1,
         "culture:nomadism": 0.1, "culture:nontheism": 0.1, "culture:pragmatism": 0.15},
        0, 1,
    ),
    ImagoNode(
        "change:t2:dawn", "change", 2,
        "The New Dawn",
        "The dawn doesn't ask permission, and it burns away what was hidden.",
        "The new dawn is revelation, that blinding moment when the new is first fully seen. "
        "Light accompanies change not as warmth but as exposure; the dawn destroys secrecy "
        "as a side effect of simply arriving.",
        {"domain:change": 0.55, "domain:light": 0.15, "domain:secrecy": -0.05,
         "culture:egalitarianism": 0.15, "culture:competition": 0.1,
         "culture:idealism": 0.25, "culture:ambition": 0.15},
        1, 2,
    ),
    ImagoNode(
        "change:t2:shapeshifter", "change", 2,
        "The Shapeshifter's Path",
        "Change is a skill. Impermanence can be mastered.",
        "The shapeshifter masters transformation itself, change as a form of mastery over flux, "
        "a discipline that can be learned and refined. But the shapeshifter moves through "
        "communities without belonging to any of them; adaptability precludes rootedness.",
        {"domain:change": 0.5, "domain:mastery": 0.12, "domain:community": -0.04,
         "culture:nomadism": 0.2, "culture:adaptability": 0.2, "culture:pragmatism": 0.15},
        1, 3,
    ),
    ImagoNode(
        "change:t3:rebel", "change", 3,
        "The Rebel Yell",
        "Revolutions are not made by individuals. They are made by communities that finally see themselves.",
        "The rebel yell is the moment a community recognizes itself as something capable of "
        "collective action. It arises from solidarity, not from lone heroes. But revolution "
        "cannot stay secret; secrecy is its first casualty.",
        {"domain:change": 0.8, "domain:community": 0.45, "domain:secrecy": -0.02,
         "culture:egalitarianism": 0.5, "culture:maltheism": 0.1,
         "culture:idealism": 0.3, "culture:tenacity": 0.2, "culture:sincerity": 0.15},
        1, 4,
    ),
    ImagoNode(
        "change:t3:chrysalis", "change", 3,
        "The Undying Chrysalis",
        "Transformation passes through emptiness. There is a moment when you are nothing.",
        "The chrysalis is void—nothing, waiting to become something. Before new form can emerge, "
        "old form must fully dissolve. The chrysalis is also alone; transformation at this "
        "depth is solitary.",
        {"domain:change": 0.75, "domain:void": 0.4, "domain:community": -0.02,
         "culture:nomadism": 0.45, "culture:animism": 0.2,
         "culture:adaptability": 0.2, "culture:humility": 0.15},
        1, 5,
    ),
    ImagoNode(
        "change:t4:apex", "change", 4,
        "The Great Dissolution",
        "",
        "Pure Change: the force that unmakes and remakes all things, "
        "the end and beginning that are the same moment.",
        {"domain:change": 1.0},
        6, 6,
    ),

    # ── CONFLICT ─────────────────────────────────────────────────────────

    ImagoNode(
        "conflict:t1:banner", "conflict", 1,
        "The Broken Banner",
        "You forget what you've lost so you can keep fighting.",
        "The banner is broken because someone carried it past the point of hope; sacrifice "
        "is the hidden core of defiance. And conflict sustains itself by forgetting; those "
        "who fight on against impossible odds do so by erasing the memory of what the war "
        "has already cost them.",
        {"domain:conflict": 0.35, "domain:sacrifice": 0.1, "domain:memory": -0.1,
         "culture:competition": 0.15, "culture:tenacity": 0.2, "culture:sincerity": 0.1},
        0, 7,
    ),
    ImagoNode(
        "conflict:t1:rival", "conflict", 1,
        "The Rival's Eye",
        "The water finds a way around; the rival breaks through.",
        "Rivalry drives discovery; you learn your own limits by pushing against another's. "
        "But the rival's eye despises yielding; it has no patience for the flowing, "
        "accommodating path that goes around rather than through.",
        {"domain:conflict": 0.3, "domain:mastery": 0.08, "domain:water": -0.1,
         "culture:competition": 0.2, "culture:ambition": 0.2},
        0, 8,
    ),
    ImagoNode(
        "conflict:t2:edge", "conflict", 2,
        "The Sharpened Edge",
        "The fighter carries every wound into the next battle.",
        "Mastery of violence requires memory; technique is encoded experience, and the "
        "trained warrior carries the memory of every mistake into the next engagement. "
        "But the martial life stunts organic development; the blade that is sharpened "
        "cannot also grow.",
        {"domain:conflict": 0.55, "domain:memory": 0.15, "domain:growth": -0.04,
         "culture:conquest": 0.15, "culture:hierarchy": 0.1,
         "culture:tenacity": 0.2, "culture:pragmatism": 0.15},
        1, 9,
    ),
    ImagoNode(
        "conflict:t2:ground", "conflict", 2,
        "The Contested Ground",
        "The emptiness is what makes the ground worth dying for.",
        "The contested ground is defined by what it lacks: the void that power rushes to fill, "
        "the territory that exists as absence until someone dies for it. Strangely, the violence "
        "of contestation preserves what it fights over; the fought-over field resists decay.",
        {"domain:conflict": 0.5, "domain:void": 0.12, "domain:decay": -0.05,
         "culture:nomadism": 0.1, "culture:competition": 0.15,
         "culture:ambition": 0.2, "culture:tenacity": 0.1},
        1, 10,
    ),
    ImagoNode(
        "conflict:t3:eternal", "conflict", 3,
        "The Eternal War",
        "Wars last forever because people remember.",
        "The eternal war is sustained by memory—every grievance, every fallen comrade, every "
        "broken promise—kept alive across generations to fuel the next battle. Memory is the "
        "eternal war's true weapon. But the eternal war has no room for growth; it only has "
        "room for more war.",
        {"domain:conflict": 0.85, "domain:memory": 0.4, "domain:growth": -0.02,
         "culture:conquest": 0.5, "culture:xenophobia": 0.15,
         "culture:tenacity": 0.25, "culture:folk_wisdom": 0.15},
        1, 11,
    ),
    ImagoNode(
        "conflict:t3:crucible", "conflict", 3,
        "The Crucible of Becoming",
        "The sword does not yield; neither does what is made by the sword.",
        "The crucible destroys in order to enable growth, the non-obvious truth that "
        "devastation and flourishing share a root. What survives is genuinely new. The "
        "crucible does not flow around obstacles; it burns through them.",
        {"domain:conflict": 0.75, "domain:growth": 0.45, "domain:water": -0.02,
         "culture:competition": 0.45, "culture:hierarchy": 0.15,
         "culture:ambition": 0.25, "culture:pragmatism": 0.15},
        1, 12,
    ),
    ImagoNode(
        "conflict:t4:apex", "conflict", 4,
        "The Unending Struggle",
        "",
        "Pure Conflict: the primordial striving that preceded the universe and will outlast it.",
        {"domain:conflict": 1.0},
        6, 13,
    ),

    # ── ORDER ────────────────────────────────────────────────────────────

    ImagoNode(
        "order:t1:gauntlet", "order", 1,
        "The Clenched Gauntlet",
        "Authority burns away the contradictions of the past.",
        "Imposed order demands official history over lived memory; the fist that enforces "
        "rewrites what came before it.",
        {"domain:order": 0.35, "domain:fire": 0.08, "domain:memory": -0.1,
         "culture:hierarchy": 0.2, "culture:tenacity": 0.15, "culture:honesty": 0.1},
        0, 14,
    ),
    ImagoNode(
        "order:t1:warden", "order", 1,
        "The Warden's Mark",
        "The price of a stable world is the closing of doors.",
        "Maintaining order costs something—of freedom, of exception, of the individual. "
        "But the warden's jurisdiction also resists what disrupts its categories; the new "
        "finding that overturns established truth is unwelcome here.",
        {"domain:order": 0.3, "domain:sacrifice": 0.1, "domain:truth": -0.1,
         "culture:sedentism": 0.15, "culture:moderation": 0.15},
        0, 15,
    ),
    ImagoNode(
        "order:t2:compact", "order", 2,
        "The Iron Compact",
        "What is remembered cannot be undone.",
        "Binding agreements crystallize into memory, the oath that cannot be forgotten, "
        "the treaty that becomes its own keeper. But compacts resist organic expansion; "
        "the signed border that prevents the natural spread.",
        {"domain:order": 0.55, "domain:memory": 0.15, "domain:growth": -0.05,
         "culture:diplomacy": 0.15, "culture:honesty": 0.2, "culture:patience": 0.1},
        1, 16,
    ),
    ImagoNode(
        "order:t2:path", "order", 2,
        "The Measured Path",
        "The shortcut is always longer.",
        "Patient, ordered process is the only route to true mastery, discipline that "
        "transforms over time into expertise. But the ordered path does not demand sacrifice; "
        "it demands patience. Sacrifice is for those without systems.",
        {"domain:order": 0.5, "domain:mastery": 0.12, "domain:sacrifice": -0.04,
         "culture:cooperation": 0.2, "culture:moderation": 0.2, "culture:pragmatism": 0.15},
        1, 17,
    ),
    ImagoNode(
        "order:t3:throne", "order", 3,
        "The Eternal Throne",
        "Power is proven by what it outlasts.",
        "The throne endures while everything around it decays, but decay is also what "
        "validates the throne's permanence. The institution that outlasts civilizations "
        "proves its own necessity by feeding on their ruin. The still water resists flow.",
        {"domain:order": 0.8, "domain:decay": 0.45, "domain:water": -0.02,
         "culture:hierarchy": 0.5, "culture:luminary_worship": 0.15,
         "culture:ambition": 0.2, "culture:humility": 0.1},
        1, 18,
    ),
    ImagoNode(
        "order:t3:architecture", "order", 3,
        "The Silent Architecture",
        "The cage is most effective when the bars are invisible.",
        "Structures define by what they exclude: walls create emptiness, laws create silence, "
        "categories create void where the uncategorized falls. The architecture of control "
        "does not serve community; it supersedes it.",
        {"domain:order": 0.75, "domain:void": 0.4, "domain:community": -0.02,
         "culture:hierarchy": 0.45, "culture:isolationism": 0.2,
         "culture:pragmatism": 0.2, "culture:patience": 0.15},
        1, 19,
    ),
    ImagoNode(
        "order:t4:apex", "order", 4,
        "The First Axiom",
        "",
        "Pure Order: the foundational principle preceding all written law, all institution, "
        "all hierarchy, the divine grammar underlying reality itself.",
        {"domain:order": 1.0},
        6, 20,
    ),

    # ── SILENCE ──────────────────────────────────────────────────────────

    ImagoNode(
        "silence:t1:veil", "silence", 1,
        "The Veiled Face",
        "The revealed god is already diminished.",
        "Silence is the void between sounds, absence as its own kind of presence. But the "
        "veiled one does not sacrifice themselves; revelation is the deepest sacrifice, "
        "and they refuse it entirely.",
        {"domain:silence": 0.35, "domain:void": 0.1, "domain:sacrifice": -0.1,
         "culture:nontheism": 0.15, "culture:patience": 0.2},
        0, 21,
    ),
    ImagoNode(
        "silence:t1:pool", "silence", 1,
        "The Still Pool",
        "The surface that moves reflects nothing.",
        "Stillness holds reflections; memory lives in silence, the pool that records without "
        "disturbing. But stillness does not grow; the still pool resists the seasonal flood, "
        "the living current.",
        {"domain:silence": 0.3, "domain:memory": 0.08, "domain:growth": -0.1,
         "culture:isolationism": 0.15, "culture:humility": 0.2},
        0, 22,
    ),
    ImagoNode(
        "silence:t2:empty_throne", "silence", 2,
        "The Empty Throne",
        "The throne that is never sat upon is never challenged.",
        "Power preserved in absence also slowly rots—the paradox of ruling by not ruling, "
        "the empty throne that decays precisely because no one maintains it. And yet the "
        "decay validates the absence; power that rots proves it was real.",
        {"domain:silence": 0.55, "domain:decay": 0.15, "domain:community": -0.05,
         "culture:hierarchy": 0.15, "culture:pragmatism": 0.2, "culture:patience": 0.15},
        1, 23,
    ),
    ImagoNode(
        "silence:t2:breath", "silence", 2,
        "The Withheld Breath",
        "The word kept is the word that wins.",
        "The fire never lit—potential energy, a burning that doesn't consume. "
        "The withheld word is a flame kept in the throat. But restraint resists the impulse "
        "to investigate, to reveal, to find out; the withheld breath does not ask questions.",
        {"domain:silence": 0.5, "domain:fire": 0.12, "domain:mastery": -0.1,
         "culture:cooperation": 0.15, "culture:patience": 0.2, "culture:wit": 0.15},
        1, 24,
    ),
    ImagoNode(
        "silence:t3:hand", "silence", 3,
        "The Hidden Hand",
        "The string is only useful if the puppet doesn't know it's there.",
        "The hidden hand requires community to operate; it works through social networks, "
        "through whispers and debts and relationships. Invisible governance runs on connection "
        "while denying connection. But it cannot survive full revelation; truth is its only "
        "vulnerability.",
        {"domain:silence": 0.8, "domain:community": 0.45, "domain:truth": -0.02,
         "culture:hierarchy": 0.4, "culture:nontheism": 0.2,
         "culture:pragmatism": 0.25, "culture:wit": 0.15},
        1, 25,
    ),
    ImagoNode(
        "silence:t3:watcher", "silence", 3,
        "The Patient Watcher",
        "The god who knows everything and says nothing is the most terrible god of all.",
        "The patient observation that eventually reveals truth without acting on it—the watcher "
        "accumulates truth through silence. But the patient watcher gives nothing of themselves; "
        "they do not sacrifice their detachment for the comfort of intervention.",
        {"domain:silence": 0.75, "domain:truth": 0.4, "domain:sacrifice": -0.02,
         "culture:luminary_worship": 0.45, "culture:nontheism": 0.2,
         "culture:patience": 0.3, "culture:humility": 0.15},
        1, 26,
    ),
    ImagoNode(
        "silence:t4:apex", "silence", 4,
        "The Absent God",
        "",
        "Pure Silence: supreme divine withdrawal, the god that is everywhere precisely "
        "because it is nowhere.",
        {"domain:silence": 1.0},
        6, 27,
    ),
]

# ── Prerequisite pairs (node_id, required_node_id) ────────────────────
# T2 nodes list both T1s; is_unlockable counts satisfied prereqs vs min_prereqs.
_PREREQ_DATA: list[tuple[str, str]] = [
    # Change T2 — any 1 T1
    ("change:t2:dawn",          "change:t1:wheel"),
    ("change:t2:dawn",          "change:t1:wall"),
    ("change:t2:shapeshifter",  "change:t1:wheel"),
    ("change:t2:shapeshifter",  "change:t1:wall"),
    # Change T3 — specific T2
    ("change:t3:rebel",         "change:t2:dawn"),
    ("change:t3:chrysalis",     "change:t2:shapeshifter"),
    # Change T4 — all 6 prior
    ("change:t4:apex",          "change:t1:wheel"),
    ("change:t4:apex",          "change:t1:wall"),
    ("change:t4:apex",          "change:t2:dawn"),
    ("change:t4:apex",          "change:t2:shapeshifter"),
    ("change:t4:apex",          "change:t3:rebel"),
    ("change:t4:apex",          "change:t3:chrysalis"),
    # Conflict T2 — any 1 T1
    ("conflict:t2:edge",        "conflict:t1:banner"),
    ("conflict:t2:edge",        "conflict:t1:rival"),
    ("conflict:t2:ground",      "conflict:t1:banner"),
    ("conflict:t2:ground",      "conflict:t1:rival"),
    # Conflict T3 — specific T2
    ("conflict:t3:eternal",     "conflict:t2:edge"),
    ("conflict:t3:crucible",    "conflict:t2:ground"),
    # Conflict T4 — all 6 prior
    ("conflict:t4:apex",        "conflict:t1:banner"),
    ("conflict:t4:apex",        "conflict:t1:rival"),
    ("conflict:t4:apex",        "conflict:t2:edge"),
    ("conflict:t4:apex",        "conflict:t2:ground"),
    ("conflict:t4:apex",        "conflict:t3:eternal"),
    ("conflict:t4:apex",        "conflict:t3:crucible"),
    # Order T2 — any 1 T1
    ("order:t2:compact",        "order:t1:gauntlet"),
    ("order:t2:compact",        "order:t1:warden"),
    ("order:t2:path",           "order:t1:gauntlet"),
    ("order:t2:path",           "order:t1:warden"),
    # Order T3 — specific T2
    ("order:t3:throne",         "order:t2:compact"),
    ("order:t3:architecture",   "order:t2:path"),
    # Order T4 — all 6 prior
    ("order:t4:apex",           "order:t1:gauntlet"),
    ("order:t4:apex",           "order:t1:warden"),
    ("order:t4:apex",           "order:t2:compact"),
    ("order:t4:apex",           "order:t2:path"),
    ("order:t4:apex",           "order:t3:throne"),
    ("order:t4:apex",           "order:t3:architecture"),
    # Silence T2 — any 1 T1
    ("silence:t2:empty_throne", "silence:t1:veil"),
    ("silence:t2:empty_throne", "silence:t1:pool"),
    ("silence:t2:breath",       "silence:t1:veil"),
    ("silence:t2:breath",       "silence:t1:pool"),
    # Silence T3 — specific T2
    ("silence:t3:hand",         "silence:t2:empty_throne"),
    ("silence:t3:watcher",      "silence:t2:breath"),
    # Silence T4 — all 6 prior
    ("silence:t4:apex",         "silence:t1:veil"),
    ("silence:t4:apex",         "silence:t1:pool"),
    ("silence:t4:apex",         "silence:t2:empty_throne"),
    ("silence:t4:apex",         "silence:t2:breath"),
    ("silence:t4:apex",         "silence:t3:hand"),
    ("silence:t4:apex",         "silence:t3:watcher"),
]


class ImagoRegistry:
    """
    Canonical, scenario-agnostic source of truth for Imago tree nodes
    and their prerequisite relationships.

    On first instantiation, bootstraps core/core.db tables if absent.
    """

    def __init__(self, db_path: Path = DEFAULT_CORE_DB) -> None:
        self._db_path = db_path
        self._nodes: dict[str, ImagoNode] = {}
        self._prereqs: dict[str, list[str]] = {}   # node_id -> [required_node_ids]
        self._ensure_db()
        self._load()

    # ── Public interface ───────────────────────────────────────────────

    @property
    def all_node_ids(self) -> list[str]:
        return [n.node_id for n in sorted(self._nodes.values(), key=lambda n: n.sort_order)]

    def is_canonical(self, node_id: str) -> bool:
        return node_id in self._nodes

    def get_node(self, node_id: str) -> Optional[ImagoNode]:
        return self._nodes.get(node_id)

    def nodes_for_tree(self, tree: str) -> list[ImagoNode]:
        """All nodes for the given tree, ordered by tier then sort_order."""
        return sorted(
            (n for n in self._nodes.values() if n.tree == tree),
            key=lambda n: (n.tier, n.sort_order),
        )

    def prerequisites_for(self, node_id: str) -> list[str]:
        """List of node_ids that appear in this node's prerequisite set."""
        return list(self._prereqs.get(node_id, []))

    def is_unlockable(self, node_id: str, unlocked: set[str]) -> bool:
        """
        True if enough prerequisites are satisfied to purchase this node.
        Does not check whether the node is already unlocked.
        """
        node = self._nodes.get(node_id)
        if node is None:
            return False
        if node.min_prereqs == 0:
            return True
        prereqs = self._prereqs.get(node_id, [])
        satisfied = sum(1 for p in prereqs if p in unlocked)
        return satisfied >= node.min_prereqs

    def is_drawable(self, node_id: str) -> bool:
        """T4 apex nodes cannot be drawn from the Underreal."""
        node = self._nodes.get(node_id)
        return node is not None and node.tier < 4

    # ── Internal ───────────────────────────────────────────────────────

    def _ensure_db(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self._db_path)
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS imago_node (
                    node_id        TEXT PRIMARY KEY,
                    tree           TEXT NOT NULL,
                    tier           INTEGER NOT NULL,
                    name           TEXT NOT NULL,
                    tooltip_blurb  TEXT NOT NULL DEFAULT '',
                    description    TEXT NOT NULL,
                    mechanics_json TEXT NOT NULL DEFAULT '{}',
                    min_prereqs    INTEGER NOT NULL DEFAULT 0,
                    sort_order     INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS imago_prerequisite (
                    node_id          TEXT NOT NULL,
                    required_node_id TEXT NOT NULL,
                    PRIMARY KEY (node_id, required_node_id)
                );
            """)

            for node in _IMAGO_NODES:
                conn.execute(
                    "INSERT OR REPLACE INTO imago_node "
                    "(node_id, tree, tier, name, tooltip_blurb, description, "
                    " mechanics_json, min_prereqs, sort_order) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        node.node_id, node.tree, node.tier, node.name,
                        node.tooltip_blurb, node.description,
                        json.dumps(node.mechanics),
                        node.min_prereqs, node.sort_order,
                    ),
                )

            for node_id, required_id in _PREREQ_DATA:
                conn.execute(
                    "INSERT OR IGNORE INTO imago_prerequisite "
                    "(node_id, required_node_id) VALUES (?,?)",
                    (node_id, required_id),
                )

            conn.commit()
        finally:
            conn.close()

    def _load(self) -> None:
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            for row in conn.execute("SELECT * FROM imago_node ORDER BY sort_order"):
                node = ImagoNode(
                    node_id=row["node_id"],
                    tree=row["tree"],
                    tier=row["tier"],
                    name=row["name"],
                    tooltip_blurb=row["tooltip_blurb"],
                    description=row["description"],
                    mechanics=json.loads(row["mechanics_json"]),
                    min_prereqs=row["min_prereqs"],
                    sort_order=row["sort_order"],
                )
                self._nodes[node.node_id] = node

            for row in conn.execute("SELECT node_id, required_node_id FROM imago_prerequisite"):
                self._prereqs.setdefault(row["node_id"], []).append(row["required_node_id"])
        finally:
            conn.close()


# ── Module-level singleton (lazy) ─────────────────────────────────────
_registry: Optional[ImagoRegistry] = None


def get_registry(db_path: Path = DEFAULT_CORE_DB) -> ImagoRegistry:
    """Return the module-level ImagoRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = ImagoRegistry(db_path)
    return _registry
