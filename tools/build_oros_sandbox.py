#!/usr/bin/env python3
"""
Rebuild oros_test_sandbox.db with the full Oros scenario:
  - 9 PopLocations (Plains of Kir'an replaces Oros Surface, + 8 new)
  - 3 Factions (Asha Dunewalker Clan, The Hiparunites, The Stonecallers)
  - 24 Pops distributed across locations with faction affiliations
  - 3 reassigned mortals (incl. Kael Ash → Kael Osh)
  - 3 TravelNetworks enforcing access restrictions
"""
import sqlite3, json, uuid

DB = "scenarios/oros_test_sandbox.db"
con = sqlite3.connect(DB)
con.row_factory = sqlite3.Row

# ── Existing IDs we keep ─────────────────────────────────────────────────────
OROS_PLANET   = "e3f92fd2-3501-40b4-957f-95d65dc4b51e"
OROS_SYSTEM   = "bb1031ee-e15f-49dc-9ea4-83cb7d424b0c"
GALAXY        = "f6661f3d-edb2-41be-9015-46b8742ca7e0"
CIV_ID        = "744556e5-ce52-49a4-94b6-e5a3e390f6c0"
SPECIES_ID    = "2433c35f-6a41-4529-af95-92d9c1f1c4dc"

M_ASHA   = "f7597f6d-44e3-41f0-bdc4-a58370396b93"
M_KAEL   = "306f22fc-7fba-411f-81ee-defe83d711d7"
M_URREN  = "5cff7f1d-4603-44a7-a42a-3db2ebb35d77"

# Cosmetic age fields copied from existing locations
AGE  = dict(age_billions=13, age_millions=675, age_thousands=482, age_years=90, age_month=5, age_day=13)
FORM = dict(formation_billions=10, formation_millions=684, formation_thousands=52,
            formation_year=521, formation_month=9, formation_day=4)

def uid(): return str(uuid.uuid4())

def jdump(v): return json.dumps(v)

# ── Generate new UUIDs ───────────────────────────────────────────────────────
L = {
    "plains":    uid(),   # Plains of Kir'an  dfc 0
    "asvelim":   uid(),   # Asvelim Savannah   dfc 0
    "qaebdol":   uid(),   # Qaebdol Cave Village dfc 0
    "dunes":     uid(),   # Dunes of Tor       dfc 1
    "stones":    uid(),   # The Ancestor Stones dfc 2
    "oasis":     uid(),   # Taem's Oasis       dfc 2
    "ulum":      uid(),   # Ulum Highlands     dfc 2
    "hiparun":   uid(),   # Hiparun's Rift     dfc 3
    "saltflats": uid(),   # The Salt Flats     dfc 4
}

F = {
    "asha":       uid(),   # Asha Dunewalker Clan
    "hiparunite": uid(),   # The Hiparunites
    "stone":      uid(),   # The Stonecallers
}

TN = {
    "general":    uid(),   # Plains, Asvelim, Qaebdol, Dunes, Stones, Ulum
    "stone_fast": uid(),   # Qaebdol <-> Ancestor Stones (Stonecallers privilege)
    "hipa_deep":  uid(),   # Ulum <-> Hiparun's Rift (Hiparunite privilege)
    "asha_fast":  uid(),   # Dunes <-> Taem's Oasis (Asha Dunewalker privilege)
    "asha_deep":  uid(),   # Dunes, Taem's Oasis, Salt Flats (Asha Dunewalker privilege)
}

# Pops keyed by (location_key, social_class, occupation)
P = {}
def pop(loc, sc, occ): P[(loc, sc, occ)] = uid(); return P[(loc, sc, occ)]

# Plains of Kir'an
plains_common   = pop("plains",   "common",     "producer")
plains_warrior  = pop("plains",   "warrior",    "militia")
# Asvelim Savannah
asvelim_common  = pop("asvelim",  "common",     "producer")
asvelim_warrior = pop("asvelim",  "warrior",    "militia")
# Qaebdol Cave Village
qaeb_laborer    = pop("qaebdol",  "common",     "laborer")
qaeb_producer   = pop("qaebdol",  "common",     "producer")
qaeb_clergy     = pop("qaebdol",  "scholar",    "clergy")
qaeb_merchant   = pop("qaebdol",  "trader",     "merchant")
qaeb_warrior    = pop("qaebdol",  "warrior",    "militia")
# Dunes of Tor
dunes_producer  = pop("dunes",    "common",     "producer")
dunes_bonded    = pop("dunes",    "underclass", "bonded")
dunes_warrior   = pop("dunes",    "warrior",    "militia")   # Asha Keln
# The Ancestor Stones
stones_clergy   = pop("stones",   "scholar",    "clergy")    # Urren
# Taem's Oasis
oasis_producer  = pop("oasis",    "common",     "producer")
oasis_clergy    = pop("oasis",    "scholar",    "clergy")
oasis_merchant  = pop("oasis",    "trader",     "merchant")
oasis_bonded    = pop("oasis",    "underclass", "bonded")
oasis_warrior   = pop("oasis",    "warrior",    "militia")
# Ulum Highlands
ulum_producer   = pop("ulum",     "common",     "producer")
ulum_warrior    = pop("ulum",     "warrior",    "militia")
# Hiparun's Rift
hipa_laborer    = pop("hiparun",  "common",     "laborer")
hipa_producer   = pop("hiparun",  "common",     "producer")  # Kael Osh
hipa_clergy     = pop("hiparun",  "scholar",    "clergy")
hipa_merchant   = pop("hiparun",  "trader",     "merchant")
hipa_bonded     = pop("hiparun",  "underclass", "bonded")
hipa_warrior    = pop("hiparun",  "warrior",    "militia")

# ── Pop definitions ──────────────────────────────────────────────────────────
# Each entry: (id, name, social_class, occupation, size, location_id, faction_id|None,
#              dominant_beliefs, culture_tags, notable_mortal_ids)

CIV_CULTURE_BASE = {
    "values:sedentism": -0.9, "religion:ancestor_worship": 0.85,
    "religion:animism": 0.8,  "practice:foraging": 0.7,
    "relations:conquest": 0.6,"values:hierarchy": -0.5,
    "values:tenacity": 0.7,   "values:folk_wisdom": 0.55,
    "values:prowess": 0.45,
}

POPS = [
    # ── Plains of Kir'an (no faction) ─────────────────────────────────────
    dict(
        id=plains_common, social_class="common", occupation="producer", size=3.12,
        loc=L["plains"], faction=None, notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.6, "domain:memory": 0.55, "domain:growth": 0.25},
        culture={
            "values:sedentism": -0.8, "religion:ancestor_worship": 0.75,
            "religion:animism": 0.7,  "practice:foraging": 0.65,
            "relations:conquest": 0.45,"values:tenacity": 0.6,
            "values:folk_wisdom": 0.6, "values:hierarchy": -0.5,
        },
    ),
    dict(
        id=plains_warrior, social_class="warrior", occupation="militia", size=2.48,
        loc=L["plains"], faction=None, notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.75, "domain:change": 0.3, "domain:memory": 0.35},
        culture={
            "values:sedentism": -0.9, "relations:conquest": 0.65,
            "religion:ancestor_worship": 0.7, "religion:animism": 0.65,
            "values:tenacity": 0.7,   "values:prowess": 0.55,
            "practice:foraging": 0.5, "values:hierarchy": -0.45,
        },
    ),
    # ── Asvelim Savannah (no faction) ─────────────────────────────────────
    dict(
        id=asvelim_common, social_class="common", occupation="producer", size=1.85,
        loc=L["asvelim"], faction=None, notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.55, "domain:memory": 0.6, "domain:growth": 0.3},
        culture={
            "values:sedentism": -0.85, "religion:ancestor_worship": 0.8,
            "religion:animism": 0.8,   "practice:foraging": 0.7,
            "relations:conquest": 0.4, "values:tenacity": 0.55,
            "values:folk_wisdom": 0.65,"values:hierarchy": -0.5,
        },
    ),
    dict(
        id=asvelim_warrior, social_class="warrior", occupation="militia", size=2.26,
        loc=L["asvelim"], faction=None, notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.7, "domain:memory": 0.4, "domain:change": 0.25},
        culture={
            "values:sedentism": -0.85, "relations:conquest": 0.55,
            "religion:ancestor_worship": 0.7, "religion:animism": 0.65,
            "values:tenacity": 0.65,   "values:prowess": 0.5,
            "practice:foraging": 0.55, "values:hierarchy": -0.45,
        },
    ),
    # ── Qaebdol Cave Village (Stonecallers) ───────────────────────────────
    dict(
        id=qaeb_laborer, social_class="common", occupation="laborer", size=2.12,
        loc=L["qaebdol"], faction=F["stone"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.4, "domain:memory": 0.7, "domain:community": 0.3},
        culture={
            "values:sedentism": -0.6, "religion:ancestor_worship": 0.9,
            "religion:animism": 0.85, "practice:foraging": 0.6,
            "values:tenacity": 0.65,  "values:charity": 0.6,
            "values:pragmatism": 0.5, "values:folk_wisdom": 0.65,
            "relations:conquest": 0.2,"values:hierarchy": -0.5,
        },
    ),
    dict(
        id=qaeb_producer, social_class="common", occupation="producer", size=2.91,
        loc=L["qaebdol"], faction=F["stone"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.45, "domain:memory": 0.7, "domain:growth": 0.3},
        culture={
            "values:sedentism": -0.7, "religion:ancestor_worship": 0.9,
            "religion:animism": 0.85, "practice:foraging": 0.65,
            "values:tenacity": 0.6,   "values:folk_wisdom": 0.65,
            "values:charity": 0.5,    "values:pragmatism": 0.45,
            "relations:conquest": 0.2,"values:hierarchy": -0.5,
        },
    ),
    dict(
        id=qaeb_clergy, social_class="scholar", occupation="clergy", size=1.82,
        loc=L["qaebdol"], faction=F["stone"], notable_mortal_ids=[],
        beliefs={"domain:memory": 0.8, "domain:growth": 0.4, "domain:sacrifice": 0.35, "domain:conflict": 0.2},
        culture={
            "religion:ancestor_worship": 0.95, "religion:animism": 0.9,
            "values:folk_wisdom": 0.8,          "values:charity": 0.7,
            "values:pragmatism": 0.6,           "values:erudition": 0.5,
            "practice:ritual": 0.65,            "values:sedentism": -0.5,
            "relations:conquest": 0.1,          "values:hierarchy": -0.45,
        },
    ),
    dict(
        id=qaeb_merchant, social_class="trader", occupation="merchant", size=1.35,
        loc=L["qaebdol"], faction=F["stone"], notable_mortal_ids=[],
        beliefs={"domain:memory": 0.55, "domain:change": 0.4, "domain:conflict": 0.3},
        culture={
            "religion:ancestor_worship": 0.8, "religion:animism": 0.75,
            "practice:trade": 0.6,            "values:pragmatism": 0.65,
            "values:folk_wisdom": 0.6,         "values:charity": 0.5,
            "values:sedentism": -0.6,          "relations:conquest": 0.15,
            "values:hierarchy": -0.45,
        },
    ),
    dict(
        id=qaeb_warrior, social_class="warrior", occupation="militia", size=1.5,
        loc=L["qaebdol"], faction=F["stone"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.6, "domain:memory": 0.5, "domain:sacrifice": 0.3},
        culture={
            "religion:ancestor_worship": 0.85, "religion:animism": 0.75,
            "values:charity": 0.55,            "values:tenacity": 0.7,
            "values:prowess": 0.5,             "values:folk_wisdom": 0.55,
            "values:sedentism": -0.7,          "relations:conquest": 0.3,
            "values:hierarchy": -0.45,
        },
    ),
    # ── Dunes of Tor (Asha Dunewalker Clan) ───────────────────────────────
    dict(
        id=dunes_producer, social_class="common", occupation="producer", size=1.75,
        loc=L["dunes"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.75, "domain:change": 0.45, "domain:memory": 0.3},
        culture={
            "values:sedentism": -0.95, "relations:conquest": 0.7,
            "religion:ancestor_worship": 0.75, "religion:animism": 0.7,
            "practice:foraging": 0.65, "values:tenacity": 0.8,
            "values:adaptability": 0.5,"values:prowess": 0.4,
            "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=dunes_bonded, social_class="underclass", occupation="bonded", size=1.42,
        loc=L["dunes"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.5, "domain:memory": 0.45, "domain:change": 0.3},
        culture={
            "values:sedentism": -0.9, "religion:ancestor_worship": 0.7,
            "religion:animism": 0.65, "practice:foraging": 0.6,
            "values:tenacity": 0.6,   "values:folk_wisdom": 0.5,
            "values:hierarchy": -0.3, "relations:conquest": 0.3,
        },
    ),
    dict(
        id=dunes_warrior, social_class="warrior", occupation="militia", size=1.26,
        loc=L["dunes"], faction=F["asha"], notable_mortal_ids=[M_ASHA],
        beliefs={"domain:conflict": 0.9, "domain:change": 0.5, "domain:memory": 0.2},
        culture={
            "values:sedentism": -0.95, "relations:conquest": 0.85,
            "values:tenacity": 0.85,   "values:prowess": 0.7,
            "values:adaptability": 0.55,"religion:ancestor_worship": 0.7,
            "religion:animism": 0.6,   "practice:foraging": 0.5,
            "values:hierarchy": -0.35,
        },
    ),
    # ── The Ancestor Stones (Stonecallers) ────────────────────────────────
    dict(
        id=stones_clergy, social_class="scholar", occupation="clergy", size=1.4,
        loc=L["stones"], faction=F["stone"], notable_mortal_ids=[M_URREN],
        beliefs={"domain:memory": 0.85, "domain:sacrifice": 0.45, "domain:growth": 0.35, "domain:conflict": 0.15},
        culture={
            "religion:ancestor_worship": 0.95, "religion:animism": 0.9,
            "values:folk_wisdom": 0.85,         "values:charity": 0.7,
            "values:erudition": 0.6,            "values:pragmatism": 0.55,
            "practice:ritual": 0.7,             "values:sedentism": -0.4,
            "relations:conquest": 0.05,         "values:hierarchy": -0.45,
        },
    ),
    # ── Taem's Oasis (Asha Dunewalker Clan) ───────────────────────────────
    dict(
        id=oasis_producer, social_class="common", occupation="producer", size=1.35,
        loc=L["oasis"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.65, "domain:change": 0.5, "domain:memory": 0.3},
        culture={
            "values:sedentism": -0.8, "relations:conquest": 0.65,
            "religion:ancestor_worship": 0.7, "religion:animism": 0.65,
            "practice:foraging": 0.55,"values:tenacity": 0.75,
            "values:adaptability": 0.5,"values:hierarchy": -0.4,
        },
    ),
    dict(
        id=oasis_clergy, social_class="scholar", occupation="clergy", size=1.08,
        loc=L["oasis"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.7, "domain:memory": 0.5, "domain:change": 0.4, "domain:sacrifice": 0.3},
        culture={
            "religion:ancestor_worship": 0.8, "religion:animism": 0.75,
            "relations:conquest": 0.55,        "values:tenacity": 0.7,
            "values:folk_wisdom": 0.6,         "values:sedentism": -0.85,
            "values:prowess": 0.4,             "values:hierarchy": -0.35,
        },
    ),
    dict(
        id=oasis_merchant, social_class="trader", occupation="merchant", size=1.05,
        loc=L["oasis"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:change": 0.6, "domain:conflict": 0.5, "domain:memory": 0.3},
        culture={
            "values:sedentism": -0.8, "practice:trade": 0.7,
            "relations:conquest": 0.55,"values:adaptability": 0.65,
            "values:tenacity": 0.65,  "religion:ancestor_worship": 0.65,
            "religion:animism": 0.6,  "values:prosperity": 0.4,
            "values:hierarchy": -0.35,
        },
    ),
    dict(
        id=oasis_bonded, social_class="underclass", occupation="bonded", size=1.31,
        loc=L["oasis"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.45, "domain:memory": 0.5, "domain:change": 0.35},
        culture={
            "values:sedentism": -0.85, "religion:ancestor_worship": 0.7,
            "religion:animism": 0.65,  "practice:foraging": 0.55,
            "values:tenacity": 0.55,   "values:folk_wisdom": 0.45,
            "values:hierarchy": -0.3,  "relations:conquest": 0.3,
        },
    ),
    dict(
        id=oasis_warrior, social_class="warrior", occupation="militia", size=1.15,
        loc=L["oasis"], faction=F["asha"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.85, "domain:change": 0.45, "domain:memory": 0.25},
        culture={
            "values:sedentism": -0.95, "relations:conquest": 0.8,
            "values:tenacity": 0.8,    "values:prowess": 0.65,
            "religion:ancestor_worship": 0.65, "religion:animism": 0.55,
            "values:adaptability": 0.5,"values:hierarchy": -0.35,
        },
    ),
    # ── Ulum Highlands (The Hiparunites) ──────────────────────────────────
    dict(
        id=ulum_producer, social_class="common", occupation="producer", size=2.21,
        loc=L["ulum"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.6, "domain:memory": 0.65, "domain:change": 0.2},
        culture={
            "values:sedentism": -0.7, "religion:ancestor_worship": 0.85,
            "religion:animism": 0.75, "practice:foraging": 0.6,
            "values:tenacity": 0.75,  "relations:isolationism": 0.65,
            "relations:xenophobia": 0.5,"values:folk_wisdom": 0.6,
            "values:autonomy": 0.5,   "relations:conquest": 0.3,
            "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=ulum_warrior, social_class="warrior", occupation="militia", size=2.39,
        loc=L["ulum"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.75, "domain:memory": 0.55, "domain:mastery": 0.3},
        culture={
            "values:sedentism": -0.75, "relations:conquest": 0.5,
            "religion:ancestor_worship": 0.8, "religion:animism": 0.7,
            "values:tenacity": 0.8,    "values:prowess": 0.65,
            "relations:isolationism": 0.7,"relations:xenophobia": 0.55,
            "values:autonomy": 0.5,    "values:hierarchy": -0.35,
        },
    ),
    # ── Hiparun's Rift (The Hiparunites) ──────────────────────────────────
    dict(
        id=hipa_laborer, social_class="common", occupation="laborer", size=2.5,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.5, "domain:memory": 0.7, "domain:change": 0.2},
        culture={
            "values:sedentism": -0.65, "religion:ancestor_worship": 0.9,
            "religion:animism": 0.8,   "practice:foraging": 0.65,
            "values:tenacity": 0.8,    "relations:isolationism": 0.7,
            "relations:xenophobia": 0.5,"values:folk_wisdom": 0.65,
            "values:autonomy": 0.55,   "relations:conquest": 0.25,
            "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=hipa_producer, social_class="common", occupation="producer", size=2.82,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[M_KAEL],
        beliefs={"domain:conflict": 0.55, "domain:memory": 0.75, "domain:mastery": 0.3, "domain:change": 0.2},
        culture={
            "values:sedentism": -0.65, "religion:ancestor_worship": 0.9,
            "religion:animism": 0.8,   "practice:foraging": 0.65,
            "values:tenacity": 0.75,   "relations:isolationism": 0.65,
            "relations:xenophobia": 0.5,"values:folk_wisdom": 0.7,
            "values:autonomy": 0.55,   "relations:conquest": 0.2,
            "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=hipa_clergy, social_class="scholar", occupation="clergy", size=1.61,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:memory": 0.8, "domain:conflict": 0.4, "domain:mastery": 0.35, "domain:decay": 0.25},
        culture={
            "religion:ancestor_worship": 0.95, "religion:animism": 0.85,
            "values:folk_wisdom": 0.8,          "values:erudition": 0.55,
            "relations:isolationism": 0.7,      "values:autonomy": 0.6,
            "values:tenacity": 0.7,             "values:sedentism": -0.6,
            "relations:conquest": 0.15,         "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=hipa_merchant, social_class="trader", occupation="merchant", size=1.3,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:memory": 0.6, "domain:conflict": 0.45, "domain:change": 0.35, "domain:mastery": 0.3},
        culture={
            "religion:ancestor_worship": 0.8, "religion:animism": 0.7,
            "practice:trade": 0.5,            "relations:isolationism": 0.7,
            "relations:xenophobia": 0.55,      "relations:protectionism": 0.5,
            "values:folk_wisdom": 0.65,        "values:tenacity": 0.65,
            "values:autonomy": 0.5,            "relations:conquest": 0.2,
            "values:hierarchy": -0.4,
        },
    ),
    dict(
        id=hipa_bonded, social_class="underclass", occupation="bonded", size=1.58,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.5, "domain:memory": 0.55, "domain:change": 0.3},
        culture={
            "religion:ancestor_worship": 0.75, "religion:animism": 0.65,
            "practice:foraging": 0.55,          "values:tenacity": 0.6,
            "values:folk_wisdom": 0.5,          "values:hierarchy": -0.3,
            "relations:isolationism": 0.5,      "relations:conquest": 0.2,
        },
    ),
    dict(
        id=hipa_warrior, social_class="warrior", occupation="militia", size=2.2,
        loc=L["hiparun"], faction=F["hiparunite"], notable_mortal_ids=[],
        beliefs={"domain:conflict": 0.8, "domain:memory": 0.5, "domain:mastery": 0.35, "domain:change": 0.2},
        culture={
            "values:sedentism": -0.8, "relations:conquest": 0.45,
            "religion:ancestor_worship": 0.85, "religion:animism": 0.7,
            "values:tenacity": 0.85,   "values:prowess": 0.7,
            "relations:isolationism": 0.75,"relations:xenophobia": 0.6,
            "values:autonomy": 0.55,   "values:hierarchy": -0.4,
        },
    ),
]

# Gather pop IDs per location and per faction
pops_by_loc = {}
pops_by_faction = {}
for pd in POPS:
    pops_by_loc.setdefault(pd["loc"], []).append(pd["id"])
    if pd["faction"]:
        pops_by_faction.setdefault(pd["faction"], []).append(pd["id"])

all_pop_ids = [pd["id"] for pd in POPS]

# ── Apply changes ────────────────────────────────────────────────────────────

# 1. Remove the old Oros Surface pop location
con.execute("DELETE FROM locations WHERE id = 'a8fdbeb7-c782-443e-a25c-2eb54539e0ea'")

# 2. Remove old pops
con.execute("DELETE FROM pops")

# 3. Insert new PopLocations
try:
    con.execute("ALTER TABLE locations ADD COLUMN danger REAL NOT NULL DEFAULT 0.0")
except Exception:
    pass  # column already exists

def insert_poploc(lid, name, dfc, pop_ids, tn_ids, domain_expr=None, danger=0.0):
    con.execute("""
        INSERT INTO locations (
            id, name, description, location_type, subclass,
            parent_id, child_ids, traits, condition,
            coordinates_x, coordinates_y, coordinates_z, star_type,
            domain_expression, lf_overt_miracles, lf_subtle_influence,
            lf_proxius_activity, lf_direct_creation,
            civilization_ids, species_ids, proxius_ids, herald_ids_loc,
            geo_tags, atmo_tags,
            age_billions, age_millions, age_thousands, age_years, age_month, age_day,
            formation_billions, formation_millions, formation_thousands,
            formation_year, formation_month, formation_day,
            pop_ids, distance_from_core,
            legs, travel_current_wp, travel_ticks_rem,
            travel_occupants, travel_pop_ids, travel_network_ids,
            commerce_quality, collectible_resource, wealth, danger,
            visibility, pinned, visibility_stall_remaining
        ) VALUES (
            ?,?,?,?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,?,?,  ?,?,?,?,  ?,?,
            ?,?,?,?,?,?,  ?,?,?,?,?,?,  ?,?,  ?,?,?,?,?,?,  ?,?,?,?,  ?,?,?
        )
    """, (
        lid, name, "", "pop_location", "pop_location",
        OROS_PLANET, jdump([]), jdump([]), "stable",
        0.0, 0.0, 0.0, "main_sequence",
        jdump(domain_expr or {}), 0.0, 0.0, 0.0, 0.0,
        jdump([]), jdump([]), jdump([]), jdump([]),
        jdump([]), jdump([]),
        AGE["age_billions"], AGE["age_millions"], AGE["age_thousands"],
        AGE["age_years"], AGE["age_month"], AGE["age_day"],
        FORM["formation_billions"], FORM["formation_millions"], FORM["formation_thousands"],
        FORM["formation_year"], FORM["formation_month"], FORM["formation_day"],
        jdump(pop_ids), dfc,
        jdump({}), "", 0, jdump([]), jdump([]), jdump(tn_ids),
        0.5, None, 0.5, danger,
        1.0, 0, 360,
    ))

# General network membership
gen        = [L["plains"], L["asvelim"], L["qaebdol"], L["dunes"], L["stones"], L["ulum"]]
stone_fast = [L["qaebdol"], L["stones"]]
hipa_deep  = [L["ulum"], L["hiparun"]]
asha_fast  = [L["dunes"], L["oasis"]]
asha_deep  = [L["dunes"], L["oasis"], L["saltflats"]]

def tn_ids_for(lid):
    ids = []
    if lid in gen:        ids.append(TN["general"])
    if lid in stone_fast: ids.append(TN["stone_fast"])
    if lid in hipa_deep:  ids.append(TN["hipa_deep"])
    if lid in asha_fast:  ids.append(TN["asha_fast"])
    if lid in asha_deep:  ids.append(TN["asha_deep"])
    return ids

insert_poploc(L["plains"],    "Plains of Kir'an",      0, pops_by_loc.get(L["plains"],   []), tn_ids_for(L["plains"]),   danger=0.0)
insert_poploc(L["asvelim"],   "Asvelim Savannah",       0, pops_by_loc.get(L["asvelim"],  []), tn_ids_for(L["asvelim"]),  danger=0.05)
insert_poploc(L["qaebdol"],   "Qaebdol Cave Village",   0, pops_by_loc.get(L["qaebdol"],  []), tn_ids_for(L["qaebdol"]),  danger=0.0)
insert_poploc(L["dunes"],     "Dunes of Tor",           1, pops_by_loc.get(L["dunes"],    []), tn_ids_for(L["dunes"]),    danger=0.35)
insert_poploc(L["stones"],    "The Ancestor Stones",    2, pops_by_loc.get(L["stones"],   []), tn_ids_for(L["stones"]),   danger=0.1)
insert_poploc(L["oasis"],     "Taem's Oasis",           2, pops_by_loc.get(L["oasis"],    []), tn_ids_for(L["oasis"]),    danger=0.0)
insert_poploc(L["ulum"],      "Ulum Highlands",         2, pops_by_loc.get(L["ulum"],     []), tn_ids_for(L["ulum"]),     danger=0.15)
insert_poploc(L["hiparun"],   "Hiparun's Rift",         3, pops_by_loc.get(L["hiparun"],  []), tn_ids_for(L["hiparun"]),  danger=0.25)
insert_poploc(L["saltflats"], "The Salt Flats",         4, [],                                 tn_ids_for(L["saltflats"]), danger=0.45)

# 4. Update Oros planet's child_ids
con.execute(
    "UPDATE locations SET child_ids = ? WHERE id = ?",
    (jdump(list(L.values())), OROS_PLANET)
)

# 5. Insert TravelNetworks
for col, default in [("edges", "[]"), ("conditions", "[]")]:
    try:
        con.execute(f"ALTER TABLE travel_networks ADD COLUMN {col} TEXT NOT NULL DEFAULT '{default}'")
    except Exception:
        pass  # column already exists

def cond(faction_id, danger_mod=0.0):
    return jdump([{"faction_ids": [faction_id], "hard_gate": False, "danger_modifier": danger_mod}])
def edge(a, b, cost): return {"node_a": a, "node_b": b, "privileged_cost": cost}

con.execute("DELETE FROM travel_networks")
for tn_key, tn_name, members, edges, conditions in [
    ("general",    "Oros Open Routes",               gen,        [],  "[]"),
    ("stone_fast", "Stonecallers Paths",              stone_fast, [edge(L["qaebdol"], L["stones"], 1)],                                             cond(F["stone"])),
    ("hipa_deep",  "Hiparunite Highlands",            hipa_deep,  [edge(L["ulum"],    L["hiparun"], 2)],                                            cond(F["hiparunite"])),
    ("asha_fast",  "Asha Dunewalker Fast Route",      asha_fast,  [edge(L["dunes"],   L["oasis"],  1)],                                             cond(F["asha"])),
    ("asha_deep",  "Asha Dunewalker Territory",       asha_deep,  [edge(L["dunes"],   L["saltflats"], 3), edge(L["oasis"], L["saltflats"], 3)],     cond(F["asha"], danger_mod=-0.5)),
]:
    con.execute(
        "INSERT INTO travel_networks (id, name, member_ids, edges, conditions) VALUES (?, ?, ?, ?, ?)",
        (TN[tn_key], tn_name, jdump(members), jdump(edges), conditions)
    )

# 6. Insert Pops
for pd in POPS:
    con.execute("""
        INSERT INTO pops (
            id, name, demiurge_authored, civilization_id, species_id,
            social_class, wild_stratum, current_location, size_fractional,
            dominant_beliefs, culture_tags, rider_traits, notable_mortal_ids,
            parent_pop_id, child_pop_ids, splinter_cooldown, identity_anchor,
            visibility, pinned, visibility_stall_remaining,
            preaching_imago_id, preaching_goal_cooldown_until,
            occupation, linked_pop_ids, active_directives, asset_crew_for, faction_ids
        ) VALUES (
            ?,?,?,?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,?,  ?,?,?,  ?,?,  ?,?,?,?,?
        )
    """, (
        pd["id"], None, 0, CIV_ID, SPECIES_ID,
        pd["social_class"], None, pd["loc"], pd["size"],
        jdump(pd["beliefs"]), jdump(pd["culture"]), jdump({}), jdump(pd["notable_mortal_ids"]),
        None, jdump([]), 0, None,
        1.0, 0, 360,
        None, 0,
        pd["occupation"], jdump({}), jdump([]), None,
        jdump([pd["faction"]] if pd["faction"] else [])
    ))

# 7. Factions
con.execute("DELETE FROM factions")

faction_defs = [
    (F["asha"], "Asha Dunewalker Clan",
     "Wide-faring martial clan led by warchief Asha Keln. Controls the Dunes of Tor, Taem's Oasis, and the Salt Flats; raids the Plains and Savannah.",
     pops_by_faction.get(F["asha"], [])),
    (F["hiparunite"], "The Hiparunites",
     "Highland and canyon-dwelling folk led by an elder council unofficially headed by Kael Osh. Deeply isolationist; control Hiparun's Rift and guard the Ulum Highlands from outsiders.",
     pops_by_faction.get(F["hiparunite"], [])),
    (F["stone"], "The Stonecallers",
     "Religious tradition venerating the Ancestor Stones, led by the prophet Urren. Based at Qaebdol Cave Village and the Ancestor Stones; prioritize tradition and protecting plainsfolk from raids.",
     pops_by_faction.get(F["stone"], [])),
]

for fid, fname, fdesc, fmembers in faction_defs:
    con.execute("""
        INSERT INTO factions (id, name, description, civilization_id, member_pop_ids,
                              active_directives, visibility, pinned)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (fid, fname, fdesc, CIV_ID, jdump(fmembers), jdump([]), 1.0, 0))

# 8. Update mortals
# Asha Keln → Dunes warrior pop, at Dunes of Tor
con.execute("""
    UPDATE mortals SET
        pop_id = ?, pop_milieu = ?,
        current_location = ?,
        home_location = ?
    WHERE id = ?
""", (dunes_warrior, dunes_warrior, L["dunes"], OROS_PLANET, M_ASHA))

# Kael Ash → Kael Osh, Hiparunite producer pop, Hiparun's Rift
# Update beliefs/culture to match Hiparunite flavor (he was already ambitious/suspicious)
con.execute("""
    UPDATE mortals SET
        name = 'Kael Osh',
        pop_id = ?, pop_milieu = ?,
        current_location = ?,
        home_location = ?,
        belief_tags = ?,
        culture_tags = ?
    WHERE id = ?
""", (
    hipa_producer, hipa_producer, L["hiparun"], OROS_PLANET,
    jdump({"domain:conflict": 0.55, "domain:memory": 0.75, "domain:mastery": 0.4, "domain:decay": 0.35}),
    jdump({
        "values:sedentism": -0.7, "religion:ancestor_worship": 0.85,
        "religion:animism": 0.75, "values:tenacity": 0.65,
        "relations:isolationism": 0.7, "relations:xenophobia": 0.55,
        "values:autonomy": 0.6, "values:wit": 0.45,
        "values:prowess": 0.55,
    }),
    M_KAEL
))

# Urren → Ancestor Stones clergy pop
con.execute("""
    UPDATE mortals SET
        pop_id = ?, pop_milieu = ?,
        current_location = ?,
        home_location = ?
    WHERE id = ?
""", (stones_clergy, stones_clergy, L["stones"], OROS_PLANET, M_URREN))

# 9. Update civilization pop_ids
con.execute("UPDATE civilizations SET pop_ids = ? WHERE id = ?",
            (jdump(all_pop_ids), CIV_ID))

con.commit()
con.close()
print("Done.")
print(f"  {len(POPS)} pops, 9 PopLocations, 3 factions, 5 travel networks")
print(f"  Asha Keln → {L['dunes']} (Dunes of Tor warrior)")
print(f"  Kael Osh  → {L['hiparun']} (Hiparun's Rift producer)")
print(f"  Urren     → {L['stones']} (Ancestor Stones clergy)")
