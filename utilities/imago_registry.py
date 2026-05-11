#!/usr/bin/env python3
"""
imago_registry.py
Scenario-agnostic Imago tree definitions for sixteen implemented trees:
Change, Conflict, Order, Silence, Community, Fire, Light, Truth, Water, Decay, Growth, Void,
Mastery, Memory, Sacrifice, and Secrecy.

Loads from (and bootstraps) core/core.db. Provides:
  - All 112 Imago nodes (7 per tree) with names, descriptions, and mechanics
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
        "The Great Tremor",
        "Change is the force that unmakes and remakes all things, "
        "the end and beginning that are the same moment.",
        "The divine concept of Change itself.",
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
        "Conflict is the primordial striving that preceded the universe and will outlast it.",
        "The divine concept of Conflict itself.",
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
        "Order is the foundational principle preceding all written law, all institution, "
        "all hierarchy, the divine grammar underlying reality itself.",
        "The divine concept of Order itself.",
        {"domain:order": 1.0},
        6, 20,
    ),

    # ── SILENCE ──────────────────────────────────────────────────────────

    ImagoNode(
        "silence:t1:veil", "silence", 1,
        "The Masked Face",
        "The revealed god is already diminished.",
        "Silence is the void between sounds, absence as its own kind of presence. But the "
        "masked one does not sacrifice themselves; revelation is the deepest sacrifice, "
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
        "Silence is supreme divine withdrawal, the god that is everywhere precisely "
        "because it is nowhere.",
        "The divine concept of Silence itself.",
        {"domain:silence": 1.0},
        6, 27,
    ),

    # ── COMMUNITY ────────────────────────────────────────────────────────

    ImagoNode(
        "community:t1:hearth", "community", 1,
        "The Hearth and Home",
        "The fire at the center belongs to everyone in the room. That is what makes it a hearth "
        "rather than just a fire.",
        "Domestic belonging, the family unit, the shared warmth, the first and smallest "
        "community—the fire that is everyone's and therefore no one's to take.",
        {"domain:community": 0.35, "domain:fire": 0.1, "domain:decay": -0.1,
         "culture:sedentism": 0.2, "culture:patience": 0.15},
        0, 28,
    ),
    ImagoNode(
        "community:t1:table", "community", 1,
        "The Shared Table",
        "Eating together is not incidental to community. It is community, stated plainly.",
        "The communal meal, the ritual of shared food, is the most fundamental expression of "
        "collective belonging. What is given to the table is given to all.",
        {"domain:community": 0.3, "domain:water": 0.1, "domain:secrecy": -0.1,
         "culture:cooperation": 0.15, "culture:humility": 0.15},
        0, 29,
    ),
    ImagoNode(
        "community:t2:council", "community", 2,
        "The Village Council",
        "The decision that everyone has argued about is the decision everyone will live with.",
        "Community as collective governance—the group deliberates and decides together. "
        "Belonging is expressed through shared responsibility.",
        {"domain:community": 0.55, "domain:truth": 0.15, "domain:conflict": -0.05,
         "culture:cooperation": 0.15, "culture:honesty": 0.2, "culture:patience": 0.15},
        1, 30,
    ),
    ImagoNode(
        "community:t2:festival", "community", 2,
        "The Festival of Remembrance",
        "The celebration is not about what happened. It is about the fact that it happened "
        "to all of us.",
        "Bound by shared history, collective rituals keep common memory alive, reminding "
        "people they have a story together.",
        {"domain:community": 0.5, "domain:light": 0.12, "domain:change": -0.04,
         "culture:ancestor_worship": 0.2, "culture:sincerity": 0.15,
         "culture:humility": 0.1, "culture:cooperation": 0.1},
        1, 31,
    ),
    ImagoNode(
        "community:t3:chain", "community", 3,
        "The Unbroken Chain",
        "Each generation inherits a debt it did not agree to and passes on a gift it will "
        "not see received.",
        "Civilization is the multigenerational project of building something that outlasts "
        "every individual within it; it is belonging as obligation across time.",
        {"domain:community": 0.8, "domain:mastery": 0.45, "domain:void": -0.02,
         "culture:cooperation": 0.5, "culture:erudition": 0.2,
         "culture:tenacity": 0.2, "culture:idealism": 0.1},
        1, 32,
    ),
    ImagoNode(
        "community:t3:migration", "community", 3,
        "The Great Migration",
        "They carried everything that mattered. Some of it was portable.",
        "The people carry their identity through displacement, remaining themselves across "
        "distances that should have dissolved them. Belonging is something you hold rather "
        "than somewhere you live.",
        {"domain:community": 0.75, "domain:change": 0.4, "domain:order": -0.02,
         "culture:nomadism": 0.45, "culture:cooperation": 0.2,
         "culture:tenacity": 0.2, "culture:folk_wisdom": 0.15},
        1, 33,
    ),
    ImagoNode(
        "community:t4:apex", "community", 4,
        "The One Body",
        "Community is the fundamental condition of belonging, the irreducible fact of "
        "togetherness that precedes every specific form it takes.",
        "The divine concept of Community itself.",
        {"domain:community": 1.0},
        6, 34,
    ),

    # ── FIRE ─────────────────────────────────────────────────────────────

    ImagoNode(
        "fire:t1:flame", "fire", 1,
        "The Holy Flame",
        "The flame on the altar is not warming anything. It is a message, whether the gods "
        "receive it or not.",
        "The altar flame, the vestal fire, the burning that reaches upward—sacred fire is "
        "the most ancient form of divine communication.",
        {"domain:fire": 0.35, "domain:light": 0.1, "domain:memory": -0.1,
         "culture:animism": 0.2, "culture:idealism": 0.15},
        0, 35,
    ),
    ImagoNode(
        "fire:t1:pyre", "fire", 1,
        "The Billowing Pyre",
        "What is given to the fire is given completely. This is what makes it a gift.",
        "The sacrificial pyre is the great burning that gives everything and asks for the "
        "same. It is destruction as the highest form of devotion.",
        {"domain:fire": 0.3, "domain:sacrifice": 0.1, "domain:growth": -0.1,
         "culture:animism": 0.15, "culture:tenacity": 0.1},
        0, 36,
    ),
    ImagoNode(
        "fire:t2:forge", "fire", 2,
        "The Heat of the Forge",
        "The sword does not emerge from the fire unchanged, and neither does the smith.",
        "The kiln, the furnace, the productive use of heat—as a disciplined craft, fire "
        "makes things rather than consuming them.",
        {"domain:fire": 0.55, "domain:mastery": 0.15, "domain:change": -0.04,
         "culture:sedentism": 0.15, "culture:tenacity": 0.2, "culture:pragmatism": 0.15},
        1, 37,
    ),
    ImagoNode(
        "fire:t2:coals", "fire", 2,
        "The Warming Coals",
        "The fire at the center of the room is the room. Everything else is just walls.",
        "Domestic warmth, the hearth around which people gather, is the flame that defines "
        "home by defining where home is.",
        {"domain:fire": 0.5, "domain:community": 0.15, "domain:silence": -0.04,
         "culture:sedentism": 0.2, "culture:patience": 0.15, "culture:moderation": 0.1},
        1, 38,
    ),
    ImagoNode(
        "fire:t3:entwined", "fire", 3,
        "The Hearts Entwined",
        "The fire that commits does not burn less brightly. It burns more precisely.",
        "Passionate, devoted love is intensity through fidelity, the fire that chooses one "
        "thing and gives itself to that thing entirely.",
        {"domain:fire": 0.8, "domain:truth": 0.45, "domain:change": -0.02,
         "culture:monogamy": 0.5, "culture:sincerity": 0.2,
         "culture:patience": 0.15, "culture:idealism": 0.1},
        1, 39,
    ),
    ImagoNode(
        "fire:t3:errant", "fire", 3,
        "The Errant Lover",
        "The fire that spreads is not less fire. It is simply honest about its nature.",
        "This is fire as abundance, love that does not believe limitation is the same as "
        "devotion. Passion moves freely, finding no contradiction in warmth given to many.",
        {"domain:fire": 0.75, "domain:growth": 0.4, "domain:order": -0.02,
         "culture:polygamy": 0.45, "culture:adaptability": 0.2,
         "culture:wit": 0.2, "culture:indulgence": 0.1},
        1, 40,
    ),
    ImagoNode(
        "fire:t4:apex", "fire", 4,
        "The Eternal Flame",
        "Fire is the heat of raw passion that precedes and outlasts every individual burning.",
        "The divine concept of Fire itself.",
        {"domain:fire": 1.0},
        6, 41,
    ),

    # ── LIGHT ────────────────────────────────────────────────────────────

    ImagoNode(
        "light:t1:rays", "light", 1,
        "The First Rays",
        "Darkness does not end dramatically. It simply stops being true.",
        "Light is natural rhythm, the dawn that arrives regardless of whether anyone was "
        "waiting for it, the cycle that asks nothing.",
        {"domain:light": 0.35, "domain:water": 0.1, "domain:decay": -0.1,
         "culture:animism": 0.2, "culture:idealism": 0.15},
        0, 42,
    ),
    ImagoNode(
        "light:t1:beacon", "light", 1,
        "The Beacon",
        "A beacon is not for the one who lit it. That is the whole point.",
        "Light is guidance: the lighthouse, the signal fire, the flame made specifically to "
        "be seen by someone who needs it—illumination in service of others.",
        {"domain:light": 0.3, "domain:community": 0.1, "domain:silence": -0.1,
         "culture:cooperation": 0.15, "culture:honesty": 0.15},
        0, 43,
    ),
    ImagoNode(
        "light:t2:eye", "light", 2,
        "The Opened Eye",
        "The moment of understanding does not feel like gaining something. It feels like "
        "losing the option of not knowing.",
        "Light enables comprehension, through revelation that creates the condition of "
        "understanding where ignorance was before. But there is a cost to seeing clearly.",
        {"domain:light": 0.55, "domain:sacrifice": 0.15, "domain:void": -0.05,
         "culture:erudition": 0.2, "culture:honesty": 0.15, "culture:idealism": 0.15},
        1, 44,
    ),
    ImagoNode(
        "light:t2:mirror", "light", 2,
        "The Mirror",
        "The mirror is the most honest thing in the room. This is why people avoid it.",
        "Light reflects the true image returned unchanged, the self made visible to itself. "
        "It can be the instrument of self-knowledge rather than knowledge of the world.",
        {"domain:light": 0.5, "domain:memory": 0.12, "domain:change": -0.04,
         "culture:honesty": 0.2, "culture:humility": 0.2, "culture:sincerity": 0.15},
        1, 45,
    ),
    ImagoNode(
        "light:t3:radiance", "light", 3,
        "The Blinding Radiance",
        "There is a point past which revelation is no longer useful. This has never stopped "
        "revelation.",
        "Light may be weaponized as illumination so total it destroys rather than reveals. "
        "Becoming truth at an intensity that cannot be survived, the god shows itself fully "
        "to a mortal who asked.",
        {"domain:light": 0.8, "domain:conflict": 0.45, "domain:void": -0.02,
         "culture:honesty": 0.4, "culture:tenacity": 0.2,
         "culture:idealism": 0.2, "culture:competition": 0.1},
        1, 46,
    ),
    ImagoNode(
        "light:t3:procession", "light", 3,
        "The Lantern Procession",
        "The light that is passed from hand to hand arrives somewhere that no single lamp "
        "could reach.",
        "Light carried and shared, a ritual of passing illumination through a community, is "
        "the procession in which each person is briefly the source—and everyone gets a turn.",
        {"domain:light": 0.75, "domain:community": 0.4, "domain:secrecy": -0.02,
         "culture:cooperation": 0.45, "culture:luminary_worship": 0.2,
         "culture:humility": 0.2, "culture:patience": 0.1},
        1, 47,
    ),
    ImagoNode(
        "light:t4:apex", "light", 4,
        "The Undimmed",
        "Light is the condition of complete illumination, the state in which nothing remains "
        "unseen and nothing is hidden.",
        "The divine concept of Light itself.",
        {"domain:light": 1.0},
        6, 48,
    ),

    # ── TRUTH ────────────────────────────────────────────────────────────

    ImagoNode(
        "truth:t1:compass", "truth", 1,
        "The Weathered Compass",
        "The compass that has survived everything still points true. That is not a small thing.",
        "Truth is the basis of reliable navigation—practical, hard-won, earned through use "
        "rather than revelation. The instrument endures.",
        {"domain:truth": 0.35, "domain:water": 0.1, "domain:void": -0.1,
         "culture:honesty": 0.2, "culture:patience": 0.15},
        0, 49,
    ),
    ImagoNode(
        "truth:t1:glint", "truth", 1,
        "The Glint of Truth",
        "You cannot unknow what you have seen. This is both the gift and the cost.",
        "Revelation is the blinding moment when something is fully and finally known. Truth "
        "as exposure is not concerned with comfort.",
        {"domain:truth": 0.35, "domain:sacrifice": 0.1, "domain:change": -0.1,
         "culture:honesty": 0.2, "culture:sincerity": 0.15},
        0, 50,
    ),
    ImagoNode(
        "truth:t2:sage", "truth", 2,
        "The Haggard Sage",
        "Wisdom is not given. It is what remains after everything else has been taken.",
        "Devoted totally to truth-seeking, the philosopher has surrendered comfort, community, "
        "and certainty in pursuit of understanding, earning wisdom through loss.",
        {"domain:truth": 0.55, "domain:decay": 0.15, "domain:community": -0.05,
         "culture:erudition": 0.2, "culture:patience": 0.2, "culture:humility": 0.1},
        1, 51,
    ),
    ImagoNode(
        "truth:t2:witness", "truth", 2,
        "The Sworn Witness",
        "The witness who tells the truth when it costs them nothing is not a witness but a "
        "bystander who happened to speak.",
        "The social contract, the testimony, the record, the oath that binds—truth is what "
        "makes collective life possible.",
        {"domain:truth": 0.5, "domain:community": 0.12, "domain:secrecy": -0.04,
         "culture:honesty": 0.2, "culture:sincerity": 0.15, "culture:cooperation": 0.15},
        1, 52,
    ),
    ImagoNode(
        "truth:t3:reckoning", "truth", 3,
        "The Brutal Reckoning",
        "The account does not care whether you are ready for it.",
        "Truth as a weapon is the tribunal, the exposure, the verdict that cannot be appealed. "
        "This is truth in service of judgment rather than understanding, the revelation that "
        "destroys what it illuminates.",
        {"domain:truth": 0.8, "domain:conflict": 0.45, "domain:silence": -0.02,
         "culture:honesty": 0.4, "culture:tenacity": 0.2,
         "culture:pragmatism": 0.15, "culture:competition": 0.1},
        1, 53,
    ),
    ImagoNode(
        "truth:t3:covenant", "truth", 3,
        "The Covenant of Light",
        "The civilization that knows what it is can become something else. The one that "
        "doesn't is already finished.",
        "Truth is the foundation of social order: the transparent city, the civilization "
        "that governs through shared knowledge rather than managed perception.",
        {"domain:truth": 0.75, "domain:growth": 0.4, "domain:secrecy": -0.02,
         "culture:honesty": 0.45, "culture:cooperation": 0.2,
         "culture:idealism": 0.2, "culture:erudition": 0.1},
        1, 54,
    ),
    ImagoNode(
        "truth:t4:apex", "truth", 4,
        "The Undivided Truth",
        "Truth is the fundamental consistency of reality underlying all observation, all "
        "testimony, all knowledge.",
        "The divine concept of Truth itself.",
        {"domain:truth": 1.0},
        6, 55,
    ),

    # ── WATER ────────────────────────────────────────────────────────────

    ImagoNode(
        "water:t1:current", "water", 1,
        "The Steady Current",
        "The current doesn't stop because there is something in the way.",
        "Water is ceaseless, incorporating any obstacles into itself and becoming something "
        "other than what it was in the process. This compromise is inherent in the river.",
        {"domain:water": 0.35, "domain:sacrifice": 0.1, "domain:order": -0.1,
         "culture:nomadism": 0.1, "culture:patience": 0.2, "culture:adaptability": 0.15},
        0, 56,
    ),
    ImagoNode(
        "water:t1:depths", "water", 1,
        "The Still Depths",
        "There is more below the surface than the surface suggests—and always has been.",
        "Water in its calmest state has nothing to say, no truth to reveal. In the deepest "
        "of depths lies the most humbling solitude; in bearing the weight of itself there "
        "is little meaning.",
        {"domain:water": 0.3, "domain:silence": 0.1, "domain:truth": -0.1,
         "culture:isolationism": 0.15, "culture:humility": 0.2},
        0, 57,
    ),
    ImagoNode(
        "water:t2:river", "water", 2,
        "The Patient River",
        "The stone does not break because the water is angry but because it arrived every "
        "day for millennia.",
        "The river does not merely pass through the landscape but writes itself into the "
        "landscape, and what it writes cannot be unwritten. What the river keeps is not the "
        "memory of struggle but the shape of where it has been, carved into the stone like "
        "a record that cannot be disputed.",
        {"domain:water": 0.55, "domain:memory": 0.15, "domain:conflict": -0.05,
         "culture:conservationism": 0.15, "culture:patience": 0.2, "culture:tenacity": 0.15},
        1, 58,
    ),
    ImagoNode(
        "water:t2:rain", "water", 2,
        "The Fostering Rain",
        "The rain does not ask whose land it falls on but simply falls.",
        "The rain falls on every surface equally—on the wicked and the righteous, the "
        "prepared and the unprepared. Whether it is divine justice or divine indifference, "
        "nourishment freely given asks nothing in return and means nothing beyond itself, "
        "and that is the truest generosity.",
        {"domain:water": 0.5, "domain:community": 0.12, "domain:secrecy": -0.04,
         "culture:cooperation": 0.15, "culture:egalitarianism": 0.2, "culture:adaptability": 0.15},
        1, 59,
    ),
    ImagoNode(
        "water:t3:flood", "water", 3,
        "The Great Flood",
        "What the flood leaves behind is richer than what it found, though this may be "
        "little comfort.",
        "The flood does not distinguish between what deserves to be destroyed and what does "
        "not. What remains after may be richer for the destruction, but those who suffered "
        "it remember what the gods were doing while the water rose.",
        {"domain:water": 0.8, "domain:decay": 0.45, "domain:order": -0.02,
         "culture:maltheism": 0.1, "culture:adaptability": 0.3,
         "culture:tenacity": 0.2, "culture:folk_wisdom": 0.15},
        1, 60,
    ),
    ImagoNode(
        "water:t3:archive", "water", 3,
        "The Sunken Archive",
        "The sea keeps what the land cannot, including what may have been better lost.",
        "The sea preserves without curation, holding the record of what was built and what "
        "was lost with equal fidelity. What lies at the bottom has been kept from decay not "
        "out of mercy but because water, in sufficient depth, is indifferent to time.",
        {"domain:water": 0.75, "domain:truth": 0.4, "domain:fire": -0.02,
         "culture:conservationism": 0.2, "culture:erudition": 0.2,
         "culture:patience": 0.2, "culture:humility": 0.1},
        1, 61,
    ),
    ImagoNode(
        "water:t4:apex", "water", 4,
        "The Primordial Sea",
        "Water is the source from which all flow originates and to which all flow returns.",
        "The divine concept of Water itself.",
        {"domain:water": 1.0},
        6, 62,
    ),

    # ── DECAY ────────────────────────────────────────────────────────────

    ImagoNode(
        "decay:t1:leaf", "decay", 1,
        "The Fallen Leaf",
        "The leaf does not resist, because it was always going to fall; the tree does not "
        "mourn it, because it was always going to let go.",
        "The cycle of growth and release is the oldest truth in the natural world, predating "
        "every civilization that has tried to name it. To accept what was living as something "
        "that will cease, and finding in this neither grief nor celebration, is the beginning "
        "of genuine humility.",
        {"domain:decay": 0.35, "domain:silence": 0.1, "domain:order": -0.1,
         "culture:animism": 0.2, "culture:humility": 0.2},
        0, 63,
    ),
    ImagoNode(
        "decay:t1:rust", "decay", 1,
        "The Coming Rust",
        "The rust is not the weapon's enemy but the weapon's inevitable future.",
        "Everything made by hands carries within it the seed of its own undoing, a fact the "
        "maker rarely considers at the moment of craft. The rust arrives not as punishment "
        "but as conclusion, for it was always written into the work.",
        {"domain:decay": 0.3, "domain:truth": 0.1, "domain:mastery": -0.1,
         "culture:luddism": 0.1, "culture:folk_wisdom": 0.15, "culture:humility": 0.15},
        0, 64,
    ),
    ImagoNode(
        "decay:t2:ruin", "decay", 2,
        "The Unclaimed Ruin",
        "The ruin says that something was here. It says that it is not here anymore. "
        "This is everything it has to teach.",
        "What was built here is gone, and nothing about its absence has been resolved—no "
        "mourning, no reclamation, no name attached to what it once was. The ruin, "
        "illuminated and abandoned, teaches more about impermanence than any monument could.",
        {"domain:decay": 0.55, "domain:light": 0.15, "domain:conflict": -0.05,
         "culture:ancestor_worship": 0.15, "culture:erudition": 0.2,
         "culture:pragmatism": 0.15, "culture:humility": 0.1},
        1, 65,
    ),
    ImagoNode(
        "decay:t2:compost", "decay", 2,
        "The Rich Compost",
        "The heap does not care from whence it came—only what it is becoming.",
        "What decays is not lost but converted, and the heap is indifferent to the "
        "distinction. The richness of what it becomes knows nothing of what it once was.",
        {"domain:decay": 0.5, "domain:fire": 0.12, "domain:truth": -0.04,
         "culture:agriculture": 0.15, "culture:patience": 0.2,
         "culture:pragmatism": 0.15, "culture:folk_wisdom": 0.15},
        1, 66,
    ),
    ImagoNode(
        "decay:t3:plague", "decay", 3,
        "The Terrible Plague",
        "The plague does not choose, no matter how much intent its survivors see in it.",
        "The plague finds no distinction between the devout and the faithless, the guilty "
        "and the blameless. What survives has not been chosen; it has simply not yet been "
        "reached.",
        {"domain:decay": 0.8, "domain:conflict": 0.45, "domain:order": -0.02,
         "culture:maltheism": 0.1, "culture:tenacity": 0.2,
         "culture:pragmatism": 0.2, "culture:folk_wisdom": 0.2},
        1, 67,
    ),
    ImagoNode(
        "decay:t3:rot", "decay", 3,
        "The Sacred Rot",
        "What fades was not defeated. It was completed.",
        "To call decay sacred is to accept that completion and dissolution are the same "
        "word. The cultures that learn this do not fear endings; they recognize them.",
        {"domain:decay": 0.75, "domain:water": 0.4, "domain:community": -0.02,
         "culture:animism": 0.45, "culture:void_worship": 0.2,
         "culture:humility": 0.25, "culture:patience": 0.1},
        1, 68,
    ),
    ImagoNode(
        "decay:t4:apex", "decay", 4,
        "The Final Dissolution",
        "Decay is the active process of dissolution that returns all forms to the "
        "formlessness from which they came.",
        "The divine concept of Decay itself.",
        {"domain:decay": 1.0},
        6, 69,
    ),

    # ── GROWTH ───────────────────────────────────────────────────────────

    ImagoNode(
        "growth:t1:seedling", "growth", 1,
        "The Eager Seedling",
        "The seed knows what it is going to become and surrenders its current form "
        "without hesitation.",
        "Growth begins with what looks like self-destruction: the seed cracks open, "
        "surrendering the only form it has ever known in exchange for the form it will "
        "become. Nothing in the seedling hesitates; it has no attachment to what it is "
        "giving up.",
        {"domain:growth": 0.35, "domain:sacrifice": 0.1, "domain:memory": -0.1,
         "culture:animism": 0.2, "culture:idealism": 0.15},
        0, 70,
    ),
    ImagoNode(
        "growth:t1:cycle", "growth", 1,
        "The Cycle of Return",
        "The spring does not remember the winter was difficult, but it returns anyway.",
        "The seasons do not require memory or intention to keep their promise; spring "
        "arrives because that is what spring does. The world that expects the return and "
        "plants accordingly is practicing the oldest and most reliable form of faith.",
        {"domain:growth": 0.3, "domain:truth": 0.1, "domain:conflict": -0.1,
         "culture:agriculture": 0.2, "culture:humility": 0.15},
        0, 71,
    ),
    ImagoNode(
        "growth:t2:garden", "growth", 2,
        "The Wild Garden",
        "The garden that tends itself does not require permission, whether to persist or "
        "to be built over.",
        "Life reclaims what was taken from it with patience and without malice; the garden "
        "built over will simply wait. What grows without direction tends to be harder to "
        "remove than what was planted with it.",
        {"domain:growth": 0.55, "domain:fire": 0.15, "domain:order": -0.05,
         "culture:animism": 0.2, "culture:adaptability": 0.2, "culture:folk_wisdom": 0.15},
        1, 72,
    ),
    ImagoNode(
        "growth:t2:field", "growth", 2,
        "The Cultivated Field",
        "The field that yields abundantly is not generous; it is the farmer who is generous "
        "with what he has learned to ask of it.",
        "Agriculture is the long negotiation between the will of sapient mortals and the "
        "stubbornness of living things, requiring more tenacity than strength and more "
        "observation than command. The farmer who has learned what the soil asks of them "
        "understands growth more honestly than any doctrine can.",
        {"domain:growth": 0.5, "domain:mastery": 0.12, "domain:silence": -0.04,
         "culture:agriculture": 0.15, "culture:sedentism": 0.1,
         "culture:tenacity": 0.2, "culture:pragmatism": 0.15},
        1, 73,
    ),
    ImagoNode(
        "growth:t3:forest", "growth", 3,
        "The Ancient Forest",
        "The forest was here before the town walls and will be here after.",
        "The forest operates on a timescale that makes mortal history look like a brief "
        "disturbance in the canopy. To walk beneath trees older than your civilization's "
        "name is a specific kind of instruction in humility.",
        {"domain:growth": 0.8, "domain:memory": 0.45, "domain:mastery": -0.02,
         "culture:animism": 0.5, "culture:conservationism": 0.2,
         "culture:humility": 0.2, "culture:patience": 0.1},
        1, 74,
    ),
    ImagoNode(
        "growth:t3:city", "growth", 3,
        "The Living City",
        "The city grows the way living things grow: by consuming, by competing, by making "
        "room for what is next.",
        "The city that stops consuming, competing, and making room is no longer a city but "
        "a ruin that has not yet fallen. Every generation of inhabitants inherits a place "
        "shaped by those before them and reshapes it for those who come after, whether they "
        "intend to or not.",
        {"domain:growth": 0.75, "domain:conflict": 0.4, "domain:secrecy": -0.02,
         "culture:sedentism": 0.2, "culture:commerce": 0.15,
         "culture:ambition": 0.2, "culture:tenacity": 0.2, "culture:pragmatism": 0.1},
        1, 75,
    ),
    ImagoNode(
        "growth:t4:apex", "growth", 4,
        "The Verdant Absolute",
        "Growth is the fundamental condition of flourishing, the irreducible vitality "
        "underlying all living things.",
        "The divine concept of Growth itself.",
        {"domain:growth": 1.0},
        6, 76,
    ),

    # ── VOID ─────────────────────────────────────────────────────────────

    ImagoNode(
        "void:t1:quarter", "void", 1,
        "The Empty Quarter",
        "The emptiness is not a lack of something. The emptiness is the thing.",
        "Most things that are empty are waiting to be filled, yet some are not waiting for "
        "anything. To sit with emptiness that has no use and no intention is the beginning "
        "of a rare form of patience.",
        {"domain:void": 0.35, "domain:truth": 0.1, "domain:conflict": -0.1,
         "culture:nontheism": 0.15, "culture:patience": 0.2},
        0, 77,
    ),
    ImagoNode(
        "void:t1:between", "void", 1,
        "The Nothing in Between",
        "There is a moment between one thing and the next that belongs to neither.",
        "Every transition passes through a moment that belongs to neither what came before "
        "nor what comes after, a gap most minds hurry across without looking down. The "
        "cultures that learn to treat the threshold as a place rather than a passage find "
        "in it something more solid ground cannot offer.",
        {"domain:void": 0.3, "domain:change": 0.1, "domain:order": -0.1,
         "culture:animism": 0.15, "culture:adaptability": 0.2},
        0, 78,
    ),
    ImagoNode(
        "void:t2:abyss", "void", 2,
        "The Boundless Abyss",
        "The abyss does not look back at you, for it cares not for anything.",
        "The abyss does not require anything from those who face it, which is what makes "
        "it so difficult to face. What returns from the encounter is not the abyss's gift; "
        "it is whatever was in the person all along, reflected from a very great depth.",
        {"domain:void": 0.55, "domain:sacrifice": 0.15, "domain:mastery": -0.05,
         "culture:void_worship": 0.2, "culture:humility": 0.2, "culture:patience": 0.15},
        1, 79,
    ),
    ImagoNode(
        "void:t2:hollow", "void", 2,
        "The Hollow Space",
        "The space inside the bell is not separate from the bell but its most crucial part.",
        "Function depends on absence as much as presence: the bowl that cannot hold, the "
        "bell that cannot ring. Emptiness is not the failure of the form but the condition "
        "of its purpose.",
        {"domain:void": 0.5, "domain:water": 0.12, "domain:truth": -0.04,
         "culture:nontheism": 0.15, "culture:humility": 0.2, "culture:adaptability": 0.15},
        1, 80,
    ),
    ImagoNode(
        "void:t3:dark", "void", 3,
        "The Devouring Dark",
        "The dark does not hate what it consumes, but that too is reason to fear it.",
        "The dark that consumes does not hate what it takes, and this is the most terrible "
        "thing about it. Hatred would at least imply a relationship, something to appeal "
        "to, and yet it is not to be found.",
        {"domain:void": 0.8, "domain:conflict": 0.45, "domain:light": -0.02,
         "culture:void_worship": 0.5, "culture:maltheism": 0.1,
         "culture:tenacity": 0.2, "culture:pragmatism": 0.15},
        1, 81,
    ),
    ImagoNode(
        "void:t3:womb", "void", 3,
        "The Vacant Womb",
        "Nothing is not the absence of possibility but what possibility is made from.",
        "The womb before conception holds nothing and is therefore capable of holding "
        "everything; the canvas before the first mark contains all possible paintings. "
        "An absence is a readiness.",
        {"domain:void": 0.75, "domain:mastery": 0.4, "domain:conflict": -0.02,
         "culture:nontheism": 0.2, "culture:idealism": 0.3,
         "culture:patience": 0.2, "culture:humility": 0.1},
        1, 82,
    ),
    ImagoNode(
        "void:t4:apex", "void", 4,
        "The Null",
        "Void is the fundamental condition of absence from which all presence is "
        "distinguished.",
        "The divine concept of Void itself.",
        {"domain:void": 1.0},
        6, 83,
    ),

    # ── MASTERY ──────────────────────────────────────────────────────────

    ImagoNode(
        "mastery:t1:anvil", "mastery", 1,
        "The Struck Anvil",
        "The first blow on the metal is not the important one—but neither is the last.",
        "Every minute act of creation is of equal importance, made with the same attention "
        "as the first and the last. This is what mastery asks of people and why most do "
        "not achieve it.",
        {"domain:mastery": 0.35, "domain:memory": 0.1, "domain:void": -0.1,
         "culture:sedentism": 0.15, "culture:tenacity": 0.2},
        0, 84,
    ),
    ImagoNode(
        "mastery:t1:talent", "mastery", 1,
        "The Natural Talent",
        "The gift arrives without asking, but what is done with it afterwards is still "
        "an answer.",
        "Mastery either begins or ends somewhere beyond mere talent. The gift is the "
        "precondition—not the achievement.",
        {"domain:mastery": 0.3, "domain:light": 0.1, "domain:decay": -0.1,
         "culture:competition": 0.15, "culture:idealism": 0.2},
        0, 85,
    ),
    ImagoNode(
        "mastery:t2:oath", "mastery", 2,
        "The Apprentice's Oath",
        "To commit to a craft is to accept that you will be wrong, slow, and clumsy for "
        "longer than seems reasonable.",
        "The oath to become a creator does not make the years shorter; it makes them "
        "possible. What is promised is not success but continuation.",
        {"domain:mastery": 0.55, "domain:sacrifice": 0.15, "domain:change": -0.05,
         "culture:hierarchy": 0.15, "culture:patience": 0.2, "culture:tenacity": 0.15},
        1, 86,
    ),
    ImagoNode(
        "mastery:t2:score", "mastery", 2,
        "The Musician's Score",
        "The score is what remains of the music when the sound is gone.",
        "The composer writes for an audience they will never meet, leaving instructions for "
        "how the thing they made can be made again. This is a faith that has nothing to do "
        "with gods.",
        {"domain:mastery": 0.5, "domain:memory": 0.12, "domain:silence": -0.04,
         "culture:ancestor_worship": 0.1, "culture:erudition": 0.15,
         "culture:idealism": 0.15, "culture:patience": 0.15},
        1, 87,
    ),
    ImagoNode(
        "mastery:t3:machine", "mastery", 3,
        "The Flying Machine",
        "The machine that should not fly and does anyway is the record of someone who "
        "refused to accept current possibility as a fixed limit.",
        "The wings are the argument; the flight is the proof. What follows after is a world "
        "in which the impossible thing is simply a fact, and everyone else has to adjust "
        "their sense of what is possible accordingly.",
        {"domain:mastery": 0.8, "domain:change": 0.45, "domain:decay": -0.02,
         "culture:science": 0.15, "culture:ambition": 0.4,
         "culture:tenacity": 0.2, "culture:idealism": 0.2},
        1, 88,
    ),
    ImagoNode(
        "mastery:t3:composition", "mastery", 3,
        "The Grand Composition",
        "The life's work is the thing that could only have been made by the person who "
        "lived that life.",
        "Everything learned and survived and practiced arrives at a single act of complete "
        "expression. It cannot be improved; it can only be finished.",
        {"domain:mastery": 0.75, "domain:community": 0.4, "domain:silence": -0.02,
         "culture:sedentism": 0.15, "culture:erudition": 0.2,
         "culture:ambition": 0.15, "culture:patience": 0.2, "culture:humility": 0.1},
        1, 89,
    ),
    ImagoNode(
        "mastery:t4:apex", "mastery", 4,
        "The Perfected Form",
        "Mastery is the refinement that builds on accumulated experience until the work "
        "and the worker cannot be separated.",
        "The divine concept of Mastery itself.",
        {"domain:mastery": 1.0},
        6, 90,
    ),

    # ── MEMORY ───────────────────────────────────────────────────────────

    ImagoNode(
        "memory:t1:tale", "memory", 1,
        "The Elder's Tale",
        "The oldest stories were never written down, which is why they survive.",
        "What lives in the mouth and passes to another mouth carries something the "
        "inscription loses: the weight of the person who chose to remember it. The story "
        "told by a living voice is not the same as the story carved in stone.",
        {"domain:memory": 0.35, "domain:fire": 0.1, "domain:mastery": -0.1,
         "culture:ancestor_worship": 0.2, "culture:sincerity": 0.15},
        0, 91,
    ),
    ImagoNode(
        "memory:t1:scar", "memory", 1,
        "The Old Scar",
        "The body keeps its own records, written in the language of damage and healing.",
        "What the mind prefers to forget, the scar refuses to. Memory that lives in the "
        "body does not require consent.",
        {"domain:memory": 0.3, "domain:conflict": 0.1, "domain:growth": -0.1,
         "culture:competition": 0.1, "culture:tenacity": 0.2, "culture:folk_wisdom": 0.1},
        0, 92,
    ),
    ImagoNode(
        "memory:t2:tablet", "memory", 2,
        "The Stone Tablet",
        "What is carved in stone resists the forgetting that takes everything else.",
        "The record that outlasts the civilization that made it is the most honest thing "
        "that civilization ever produced. It does not know what was forgotten alongside it.",
        {"domain:memory": 0.55, "domain:mastery": 0.15, "domain:fire": -0.05,
         "culture:sedentism": 0.15, "culture:erudition": 0.2, "culture:patience": 0.15},
        1, 93,
    ),
    ImagoNode(
        "memory:t2:ghost", "memory", 2,
        "The Restless Ghost",
        "The ghost does not haunt because it wishes to; it haunts because it does not "
        "know how to stop.",
        "What refuses to leave the present was not finished with it, or the present was "
        "not finished with what refuses to leave. The distinction rarely matters to either "
        "party.",
        {"domain:memory": 0.5, "domain:void": 0.12, "domain:growth": -0.04,
         "culture:ancestor_worship": 0.15, "culture:sincerity": 0.15, "culture:patience": 0.1},
        1, 94,
    ),
    ImagoNode(
        "memory:t3:hall", "memory", 3,
        "The Hall of Ancestors",
        "As you walk through where the dead sleep, remember that the dead once walked "
        "where you do elsewhere.",
        "A civilization that consults its dead before making decisions has decided the "
        "accumulated weight of those who came before outweighs the freedom of those here "
        "now. It is sometimes correct to heed the dead, and sometimes the dead are simply "
        "preventing the living from making the necessary mistakes.",
        {"domain:memory": 0.8, "domain:order": 0.45, "domain:conflict": -0.02,
         "culture:ancestor_worship": 0.5, "culture:hierarchy": 0.2,
         "culture:patience": 0.2, "culture:humility": 0.1},
        1, 95,
    ),
    ImagoNode(
        "memory:t3:wound", "memory", 3,
        "The Wound That Festers",
        "The wound that was not allowed to heal becomes the wound that defines everything.",
        "What a people have suffered becomes, in time, what they believe they are. Whether "
        "this is cause for mourning or solidarity depends entirely on who is asking.",
        {"domain:memory": 0.75, "domain:water": 0.4, "domain:growth": -0.02,
         "culture:xenophobia": 0.15, "culture:tenacity": 0.3,
         "culture:sincerity": 0.2, "culture:idealism": 0.1},
        1, 96,
    ),
    ImagoNode(
        "memory:t4:apex", "memory", 4,
        "The Eternal Record",
        "Memory is the accumulated record of what persists and endures, true or not.",
        "The divine concept of Memory itself.",
        {"domain:memory": 1.0},
        6, 97,
    ),

    # ── SACRIFICE ────────────────────────────────────────────────────────

    ImagoNode(
        "sacrifice:t1:gift", "sacrifice", 1,
        "The Offered Gift",
        "The act of giving itself is the first reward.",
        "The first offering asks a question, and the answer shapes every act of worship "
        "that follows: if I give this up, will something be given back?",
        {"domain:sacrifice": 0.35, "domain:growth": 0.1, "domain:secrecy": -0.1,
         "culture:luminary_worship": 0.2, "culture:sincerity": 0.15},
        0, 98,
    ),
    ImagoNode(
        "sacrifice:t1:fast", "sacrifice", 1,
        "The Pious Fast",
        "To deny the body what it wants is to rehearse for every larger sacrifice that "
        "may be required.",
        "What is given up without being taken is the most honest gift. The fast is the "
        "offering no one witnesses, which is part of what makes it costly.",
        {"domain:sacrifice": 0.3, "domain:void": 0.1, "domain:growth": -0.1,
         "culture:luminary_worship": 0.1, "culture:patience": 0.2, "culture:moderation": 0.15},
        0, 99,
    ),
    ImagoNode(
        "sacrifice:t2:price", "sacrifice", 2,
        "The Blood Price",
        "Some costs are fixed; they do not negotiate and they do not accept substitutes.",
        "The blood price is the teaching that the universe keeps accounts. Whether this is "
        "cosmically true or simply a story someone found useful is a question that risks "
        "the covenant.",
        {"domain:sacrifice": 0.55, "domain:order": 0.15, "domain:change": -0.05,
         "culture:luminary_worship": 0.2, "culture:honesty": 0.15, "culture:pragmatism": 0.15},
        1, 100,
    ),
    ImagoNode(
        "sacrifice:t2:life", "sacrifice", 2,
        "The Given Life",
        "To give one's life is to make the final statement about what one believed was "
        "worth more than living.",
        "The martyr does not merely die; they insist on something. The insistence outlives "
        "them, which is either the point or the tragedy.",
        {"domain:sacrifice": 0.5, "domain:truth": 0.12, "domain:secrecy": -0.04,
         "culture:cooperation": 0.1, "culture:idealism": 0.2, "culture:sincerity": 0.2},
        1, 101,
    ),
    ImagoNode(
        "sacrifice:t3:slaughter", "sacrifice", 3,
        "The Ritual Slaughter",
        "The formalization of violence into ritual is what separates sacrifice from murder "
        "in the minds of the practitioners.",
        "From the perspective of what is killed, this distinction is academic. What the "
        "altar demands, it receives, and the civilization organized around the altar tends "
        "to become very good at demanding.",
        {"domain:sacrifice": 0.8, "domain:mastery": 0.45, "domain:change": -0.02,
         "culture:hierarchy": 0.2, "culture:luminary_worship": 0.5,
         "culture:pragmatism": 0.15, "culture:patience": 0.1},
        1, 102,
    ),
    ImagoNode(
        "sacrifice:t3:martyr", "sacrifice", 3,
        "The Willing Martyr",
        "The willing sacrifice is an argument that cannot be answered.",
        "The martyr who chooses their death gives everyone who survives a problem: they "
        "cannot pretend the cause was not worth dying for. Whether the cause deserved it "
        "is a different question that the martyr has made very difficult to raise.",
        {"domain:sacrifice": 0.75, "domain:growth": 0.4, "domain:secrecy": -0.02,
         "culture:luminary_worship": 0.2, "culture:idealism": 0.5,
         "culture:sincerity": 0.2, "culture:tenacity": 0.1},
        1, 103,
    ),
    ImagoNode(
        "sacrifice:t4:apex", "sacrifice", 4,
        "The Ultimate Offering",
        "Sacrifice is the active giving up of something real in exchange for something "
        "believed.",
        "The divine concept of Sacrifice itself.",
        {"domain:sacrifice": 1.0},
        6, 104,
    ),

    # ── SECRECY ──────────────────────────────────────────────────────────

    ImagoNode(
        "secrecy:t1:confidence", "secrecy", 1,
        "The Kept Confidence",
        "The secret held for someone else is not yours to do anything with.",
        "What is both the simplest and the most difficult thing about bearing the secrets "
        "of others is that what is given in trust must be given back in kind, or the next "
        "secret will not be given at all.",
        {"domain:secrecy": 0.35, "domain:sacrifice": 0.1, "domain:conflict": -0.1,
         "culture:cooperation": 0.15, "culture:sincerity": 0.15},
        0, 105,
    ),
    ImagoNode(
        "secrecy:t1:room", "secrecy", 1,
        "The Locked Room",
        "The room no one else can enter is the room that belongs entirely to you.",
        "Your own is the only space in which you are not shaped by being observed. What "
        "happens there is no one's business but yours, which is a rarer condition than "
        "it sounds.",
        {"domain:secrecy": 0.3, "domain:memory": 0.1, "domain:order": -0.1,
         "culture:isolationism": 0.15, "culture:patience": 0.2},
        0, 106,
    ),
    ImagoNode(
        "secrecy:t2:double", "secrecy", 2,
        "The Double Life",
        "To live two lives simultaneously is to become expert in the gap between them.",
        "The slight adjustment of word and posture and emphasis that is the difference "
        "between what others see and what is true is exhausting but, for some, the only "
        "way they know how to be safe.",
        {"domain:secrecy": 0.55, "domain:mastery": 0.15, "domain:growth": -0.05,
         "culture:competition": 0.1, "culture:adaptability": 0.2,
         "culture:wit": 0.2, "culture:pragmatism": 0.1},
        1, 107,
    ),
    ImagoNode(
        "secrecy:t2:vault", "secrecy", 2,
        "The Sealed Vault",
        "The formal protection of a secret is an acknowledgment that it has value.",
        "What is locked away is worth the cost of locking it. The vault makes explicit "
        "what the locked room leaves implicit: some things are not for everyone.",
        {"domain:secrecy": 0.5, "domain:decay": 0.12, "domain:mastery": -0.04,
         "culture:hierarchy": 0.15, "culture:patience": 0.2, "culture:pragmatism": 0.15},
        1, 108,
    ),
    ImagoNode(
        "secrecy:t3:circle", "secrecy", 3,
        "The Inner Circle",
        "The group that knows becomes, through the knowing, something more cohesive than "
        "groups formed by geography or blood.",
        "Shared secrets are among the strongest bonds there are, which is why they are so "
        "frequently exploited. The inner circle is a community built on exclusion, which "
        "is a different thing from a community built on belonging—though from inside, it "
        "is hard to tell.",
        {"domain:secrecy": 0.8, "domain:community": 0.45, "domain:truth": -0.02,
         "culture:hierarchy": 0.5, "culture:ambition": 0.2,
         "culture:pragmatism": 0.15, "culture:wit": 0.1},
        1, 109,
    ),
    ImagoNode(
        "secrecy:t3:mystery", "secrecy", 3,
        "The Ancient Mystery",
        "What has been deliberately hidden for long enough begins to feel like it was "
        "always meant to be hidden.",
        "The tradition so old that its origins are lost, the knowledge only initiates "
        "understand—whether the secret is still worth keeping rarely gets asked, because "
        "asking would mean someone already knew the answer.",
        {"domain:secrecy": 0.75, "domain:memory": 0.4, "domain:light": -0.02,
         "culture:ancestor_worship": 0.2, "culture:erudition": 0.3,
         "culture:patience": 0.2, "culture:humility": 0.1},
        1, 110,
    ),
    ImagoNode(
        "secrecy:t4:apex", "secrecy", 4,
        "The Impenetrable Veil",
        "Secrecy is the active maintenance of concealment, the work of keeping what is "
        "hidden from becoming known.",
        "The divine concept of Secrecy itself.",
        {"domain:secrecy": 1.0},
        6, 111,
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
    ("silence:t4:apex",              "silence:t1:veil"),
    ("silence:t4:apex",              "silence:t1:pool"),
    ("silence:t4:apex",              "silence:t2:empty_throne"),
    ("silence:t4:apex",              "silence:t2:breath"),
    ("silence:t4:apex",              "silence:t3:hand"),
    ("silence:t4:apex",              "silence:t3:watcher"),
    # Community T2 — any 1 T1
    ("community:t2:council",         "community:t1:hearth"),
    ("community:t2:council",         "community:t1:table"),
    ("community:t2:festival",        "community:t1:hearth"),
    ("community:t2:festival",        "community:t1:table"),
    # Community T3 — specific T2
    ("community:t3:chain",           "community:t2:council"),
    ("community:t3:migration",       "community:t2:festival"),
    # Community T4 — all 6 prior
    ("community:t4:apex",            "community:t1:hearth"),
    ("community:t4:apex",            "community:t1:table"),
    ("community:t4:apex",            "community:t2:council"),
    ("community:t4:apex",            "community:t2:festival"),
    ("community:t4:apex",            "community:t3:chain"),
    ("community:t4:apex",            "community:t3:migration"),
    # Fire T2 — any 1 T1
    ("fire:t2:forge",                "fire:t1:flame"),
    ("fire:t2:forge",                "fire:t1:pyre"),
    ("fire:t2:coals",                "fire:t1:flame"),
    ("fire:t2:coals",                "fire:t1:pyre"),
    # Fire T3 — specific T2
    ("fire:t3:entwined",             "fire:t2:forge"),
    ("fire:t3:errant",               "fire:t2:coals"),
    # Fire T4 — all 6 prior
    ("fire:t4:apex",                 "fire:t1:flame"),
    ("fire:t4:apex",                 "fire:t1:pyre"),
    ("fire:t4:apex",                 "fire:t2:forge"),
    ("fire:t4:apex",                 "fire:t2:coals"),
    ("fire:t4:apex",                 "fire:t3:entwined"),
    ("fire:t4:apex",                 "fire:t3:errant"),
    # Light T2 — any 1 T1
    ("light:t2:eye",                 "light:t1:rays"),
    ("light:t2:eye",                 "light:t1:beacon"),
    ("light:t2:mirror",              "light:t1:rays"),
    ("light:t2:mirror",              "light:t1:beacon"),
    # Light T3 — specific T2
    ("light:t3:radiance",            "light:t2:eye"),
    ("light:t3:procession",          "light:t2:mirror"),
    # Light T4 — all 6 prior
    ("light:t4:apex",                "light:t1:rays"),
    ("light:t4:apex",                "light:t1:beacon"),
    ("light:t4:apex",                "light:t2:eye"),
    ("light:t4:apex",                "light:t2:mirror"),
    ("light:t4:apex",                "light:t3:radiance"),
    ("light:t4:apex",                "light:t3:procession"),
    # Truth T2 — any 1 T1
    ("truth:t2:sage",                "truth:t1:compass"),
    ("truth:t2:sage",                "truth:t1:glint"),
    ("truth:t2:witness",             "truth:t1:compass"),
    ("truth:t2:witness",             "truth:t1:glint"),
    # Truth T3 — specific T2
    ("truth:t3:reckoning",           "truth:t2:sage"),
    ("truth:t3:covenant",            "truth:t2:witness"),
    # Truth T4 — all 6 prior
    ("truth:t4:apex",                "truth:t1:compass"),
    ("truth:t4:apex",                "truth:t1:glint"),
    ("truth:t4:apex",                "truth:t2:sage"),
    ("truth:t4:apex",                "truth:t2:witness"),
    ("truth:t4:apex",                "truth:t3:reckoning"),
    ("truth:t4:apex",                "truth:t3:covenant"),
    # Water T2 — any 1 T1
    ("water:t2:river",               "water:t1:current"),
    ("water:t2:river",               "water:t1:depths"),
    ("water:t2:rain",                "water:t1:current"),
    ("water:t2:rain",                "water:t1:depths"),
    # Water T3 — specific T2
    ("water:t3:flood",               "water:t2:river"),
    ("water:t3:archive",             "water:t2:rain"),
    # Water T4 — all 6 prior
    ("water:t4:apex",                "water:t1:current"),
    ("water:t4:apex",                "water:t1:depths"),
    ("water:t4:apex",                "water:t2:river"),
    ("water:t4:apex",                "water:t2:rain"),
    ("water:t4:apex",                "water:t3:flood"),
    ("water:t4:apex",                "water:t3:archive"),
    # Decay T2 — any 1 T1
    ("decay:t2:ruin",                "decay:t1:leaf"),
    ("decay:t2:ruin",                "decay:t1:rust"),
    ("decay:t2:compost",             "decay:t1:leaf"),
    ("decay:t2:compost",             "decay:t1:rust"),
    # Decay T3 — specific T2
    ("decay:t3:plague",              "decay:t2:ruin"),
    ("decay:t3:rot",                 "decay:t2:compost"),
    # Decay T4 — all 6 prior
    ("decay:t4:apex",                "decay:t1:leaf"),
    ("decay:t4:apex",                "decay:t1:rust"),
    ("decay:t4:apex",                "decay:t2:ruin"),
    ("decay:t4:apex",                "decay:t2:compost"),
    ("decay:t4:apex",                "decay:t3:plague"),
    ("decay:t4:apex",                "decay:t3:rot"),
    # Growth T2 — any 1 T1
    ("growth:t2:garden",             "growth:t1:seedling"),
    ("growth:t2:garden",             "growth:t1:cycle"),
    ("growth:t2:field",              "growth:t1:seedling"),
    ("growth:t2:field",              "growth:t1:cycle"),
    # Growth T3 — specific T2
    ("growth:t3:forest",             "growth:t2:garden"),
    ("growth:t3:city",               "growth:t2:field"),
    # Growth T4 — all 6 prior
    ("growth:t4:apex",               "growth:t1:seedling"),
    ("growth:t4:apex",               "growth:t1:cycle"),
    ("growth:t4:apex",               "growth:t2:garden"),
    ("growth:t4:apex",               "growth:t2:field"),
    ("growth:t4:apex",               "growth:t3:forest"),
    ("growth:t4:apex",               "growth:t3:city"),
    # Void T2 — any 1 T1
    ("void:t2:abyss",                "void:t1:quarter"),
    ("void:t2:abyss",                "void:t1:between"),
    ("void:t2:hollow",               "void:t1:quarter"),
    ("void:t2:hollow",               "void:t1:between"),
    # Void T3 — specific T2
    ("void:t3:dark",                 "void:t2:abyss"),
    ("void:t3:womb",                 "void:t2:hollow"),
    # Void T4 — all 6 prior
    ("void:t4:apex",                 "void:t1:quarter"),
    ("void:t4:apex",                 "void:t1:between"),
    ("void:t4:apex",                 "void:t2:abyss"),
    ("void:t4:apex",                 "void:t2:hollow"),
    ("void:t4:apex",                 "void:t3:dark"),
    ("void:t4:apex",                 "void:t3:womb"),
    # Mastery T2 — any 1 T1
    ("mastery:t2:oath",              "mastery:t1:anvil"),
    ("mastery:t2:oath",              "mastery:t1:talent"),
    ("mastery:t2:score",             "mastery:t1:anvil"),
    ("mastery:t2:score",             "mastery:t1:talent"),
    # Mastery T3 — specific T2
    ("mastery:t3:machine",           "mastery:t2:oath"),
    ("mastery:t3:composition",       "mastery:t2:score"),
    # Mastery T4 — all 6 prior
    ("mastery:t4:apex",              "mastery:t1:anvil"),
    ("mastery:t4:apex",              "mastery:t1:talent"),
    ("mastery:t4:apex",              "mastery:t2:oath"),
    ("mastery:t4:apex",              "mastery:t2:score"),
    ("mastery:t4:apex",              "mastery:t3:machine"),
    ("mastery:t4:apex",              "mastery:t3:composition"),
    # Memory T2 — any 1 T1
    ("memory:t2:tablet",             "memory:t1:tale"),
    ("memory:t2:tablet",             "memory:t1:scar"),
    ("memory:t2:ghost",              "memory:t1:tale"),
    ("memory:t2:ghost",              "memory:t1:scar"),
    # Memory T3 — specific T2
    ("memory:t3:hall",               "memory:t2:tablet"),
    ("memory:t3:wound",              "memory:t2:ghost"),
    # Memory T4 — all 6 prior
    ("memory:t4:apex",               "memory:t1:tale"),
    ("memory:t4:apex",               "memory:t1:scar"),
    ("memory:t4:apex",               "memory:t2:tablet"),
    ("memory:t4:apex",               "memory:t2:ghost"),
    ("memory:t4:apex",               "memory:t3:hall"),
    ("memory:t4:apex",               "memory:t3:wound"),
    # Sacrifice T2 — any 1 T1
    ("sacrifice:t2:price",           "sacrifice:t1:gift"),
    ("sacrifice:t2:price",           "sacrifice:t1:fast"),
    ("sacrifice:t2:life",            "sacrifice:t1:gift"),
    ("sacrifice:t2:life",            "sacrifice:t1:fast"),
    # Sacrifice T3 — specific T2
    ("sacrifice:t3:slaughter",       "sacrifice:t2:price"),
    ("sacrifice:t3:martyr",          "sacrifice:t2:life"),
    # Sacrifice T4 — all 6 prior
    ("sacrifice:t4:apex",            "sacrifice:t1:gift"),
    ("sacrifice:t4:apex",            "sacrifice:t1:fast"),
    ("sacrifice:t4:apex",            "sacrifice:t2:price"),
    ("sacrifice:t4:apex",            "sacrifice:t2:life"),
    ("sacrifice:t4:apex",            "sacrifice:t3:slaughter"),
    ("sacrifice:t4:apex",            "sacrifice:t3:martyr"),
    # Secrecy T2 — any 1 T1
    ("secrecy:t2:double",            "secrecy:t1:confidence"),
    ("secrecy:t2:double",            "secrecy:t1:room"),
    ("secrecy:t2:vault",             "secrecy:t1:confidence"),
    ("secrecy:t2:vault",             "secrecy:t1:room"),
    # Secrecy T3 — specific T2
    ("secrecy:t3:circle",            "secrecy:t2:double"),
    ("secrecy:t3:mystery",           "secrecy:t2:vault"),
    # Secrecy T4 — all 6 prior
    ("secrecy:t4:apex",              "secrecy:t1:confidence"),
    ("secrecy:t4:apex",              "secrecy:t1:room"),
    ("secrecy:t4:apex",              "secrecy:t2:double"),
    ("secrecy:t4:apex",              "secrecy:t2:vault"),
    ("secrecy:t4:apex",              "secrecy:t3:circle"),
    ("secrecy:t4:apex",              "secrecy:t3:mystery"),
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
                    "INSERT OR IGNORE INTO imago_node "
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


def reinstate(db_path: Path = DEFAULT_CORE_DB) -> ImagoRegistry:
    """Drop and recreate imago tables from Python source data, then reload the singleton."""
    global _registry
    _registry = None
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript("""
            DROP TABLE IF EXISTS imago_prerequisite;
            DROP TABLE IF EXISTS imago_node;
        """)
        conn.commit()
    finally:
        conn.close()
    return get_registry(db_path)
