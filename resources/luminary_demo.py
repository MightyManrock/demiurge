#!/usr/bin/env python3
"""
Luminary Presence Visualizer — Textual port of luminary_demo_most_recent.jsx

Run from the project root:
    source bin/activate && python resources/luminary_demo.py

What translates from the JSX:
  - 15×19 virtual cell grid, 7×9 viewport window
  - Domain-weighted symbol pool; random cell replacement each tick
  - All cell effects: memory row-shift, decay/sacrifice column fall/rise,
    growth column scroll, truth freeze, void split, silence wipe,
    light bloom, secrecy dim
  - All viewport movement patterns: water scroll up, fire scroll down,
    change dart, conflict shake, order circular walk, random pan

What doesn't translate:
  - Smooth CSS transform pan → discrete step-by-step cell swaps
  - text-shadow glow → bright/dim color blending only
"""
from __future__ import annotations

import random
import time
from typing import Optional

from textual.app import App, ComposeResult
from textual import on
from textual.widget import Widget
from textual.widgets import Button, Static
from textual.containers import Horizontal, Vertical, Center
from rich.text import Text
from rich.color import Color
from rich.style import Style

# ── Grid constants ─────────────────────────────────────────────────────────────
FULL_W, FULL_H = 15, 19
VIEW_W, VIEW_H = 7, 9
FULL_SIZE = FULL_W * FULL_H

BLANK: dict = {"char": " ", "rgb": (0x11, 0x11, 0x11), "bright": False, "dim": False}

# ── Domain definitions ─────────────────────────────────────────────────────────
DOMAINS: dict[str, dict] = {
    "order":     {"label": "Order",     "symbol": "⬡", "color": (0x90, 0xb4, 0xf0),
                  "symbols": ["═","║","╔","╗","╚","╝","┼","─","┤","├","╠","╣","╦","╩"],
                  "speed": "slow"},
    "silence":   {"label": "Silence",   "symbol": "◯", "color": (0x7a, 0x8f, 0xa6),
                  "symbols": ["◯","·","∘","○","◌","⊹","‥","∙","⋯","⊸"],
                  "speed": "slow"},
    "truth":     {"label": "Truth",     "symbol": "◈", "color": (0xb8, 0xb8, 0xcc),
                  "symbols": ["◈","✦","⊕","✧","⊗","⋄","⟐","◇","◆","⊞"],
                  "speed": "medium"},
    "conflict":  {"label": "Conflict",  "symbol": "✖", "color": (0xff, 0x6b, 0x6b),
                  "symbols": ["✖","╳","✕","×","▲","⚡","▶","◀","▼","⟆"],
                  "speed": "fast"},
    "change":    {"label": "Change",    "symbol": "⬍", "color": (0x5f, 0xcc, 0xa8),
                  "symbols": ["↺","↻","⟳","≈","~","⌀","⇌","⇄","↯","⇅"],
                  "speed": "fast"},
    "fire":      {"label": "Fire",      "symbol": "🜂", "color": (0xff, 0x9f, 0x40),
                  "symbols": ["▲","△","▴","∧","^","⟨","▵","⋀","∆","ʌ"],
                  "speed": "fast"},
    "water":     {"label": "Water",     "symbol": "≋", "color": (0x4e, 0xcd, 0xc4),
                  "symbols": ["≋","≈","∿","~","⌇","⌊","∼","⌣","⏜","⌢"],
                  "speed": "medium"},
    "void":      {"label": "Void",      "symbol": "∅", "color": (0x9b, 0x72, 0xcf),
                  "symbols": ["∅","◌","□","░","▫","⊡","▭","◽","▪","◾"],
                  "speed": "slow"},
    "growth":    {"label": "Growth",    "symbol": "✿", "color": (0x7b, 0xc6, 0x7e),
                  "symbols": ["✿","❀","✾","⁂","∗","⊛","❋","✳","⊕","✢"],
                  "speed": "medium"},
    "decay":     {"label": "Decay",     "symbol": "☋", "color": (0xc4, 0x95, 0x6a),
                  "symbols": ["☋","⁂","∴","∵","¨","⌀","∾","⁖","⁘","⁙"],
                  "speed": "medium"},
    "memory":    {"label": "Memory",    "symbol": "◉", "color": (0xe8, 0xc9, 0x6a),
                  "symbols": ["◉","◎","⊙","○","●","⊚","⊛","◌","⊜","◍"],
                  "speed": "slow"},
    "sacrifice": {"label": "Sacrifice", "symbol": "⚱", "color": (0xe0, 0x5c, 0x6c),
                  "symbols": ["⚱","☽","⋆","*","✦","⛤","✵","⊶","⊷","∗"],
                  "speed": "medium"},
    "light":     {"label": "Light",     "symbol": "☼", "color": (0xff, 0xf4, 0xa0),
                  "symbols": ["☼","✴","★","✦","⟡","⊹","✧","✯","✬","✭"],
                  "speed": "medium"},
    "mastery":   {"label": "Mastery",   "symbol": "⚙", "color": (0xb0, 0xbe, 0xc5),
                  "symbols": ["⚙","⬡","⊞","◧","⊡","⊟","⊠","⊝","◫","◪"],
                  "speed": "medium"},
    "secrecy":   {"label": "Secrecy",   "symbol": "⛉", "color": (0x26, 0xc6, 0xda),
                  "symbols": ["⛉","⊘","▣","▪","◾","⊡","▩","◼","▬","⊏"],
                  "speed": "slow"},
    "community": {"label": "Community", "symbol": "♾", "color": (0xf4, 0x8f, 0xb1),
                  "symbols": ["♾","∞","⊕","⊞","⊛","⊗","⊎","⋈","⊍","∪"],
                  "speed": "medium"},
}
DOMAIN_KEYS: list[str] = list(DOMAINS.keys())

SPEED_PARAMS: dict[str, dict] = {
    "fast":   {"interval": 100,  "rate": 0.32},
    "medium": {"interval": 210,  "rate": 0.22},
    "slow":   {"interval": 420,  "rate": 0.11},
}

# ── Presets ────────────────────────────────────────────────────────────────────
PRESETS: list[dict] = [
    {"name": "The Lawgiver",   "affs": {"order": 0.80, "truth": 0.55, "light": 0.30}},
    {"name": "The Wrathful",   "affs": {"conflict": 0.80, "fire": 0.55, "change": 0.35}},
    {"name": "The Watcher",    "affs": {"silence": 0.75, "memory": 0.60, "void": 0.25}},
    {"name": "The Verdant",    "affs": {"growth": 0.75, "water": 0.55, "community": 0.40}},
    {"name": "The Sacrificer", "affs": {"sacrifice": 0.80, "void": 0.45, "decay": 0.30}},
]

# ── Viewport movement step factories ──────────────────────────────────────────
def _steps_water() -> list[dict]:
    return [{"dx": 0, "dy": -1, "ms": 150} for _ in range(random.randint(3, 5))]

def _steps_fire() -> list[dict]:
    return [{"dx": 0, "dy": 1, "ms": 150} for _ in range(random.randint(3, 5))]

def _steps_change() -> list[dict]:
    dx = random.choice([-1, 1])
    dy = random.choice([-1, 1])
    return [{"dx": dx, "dy": dy, "ms": 90} for _ in range(random.randint(2, 5))]

def _steps_conflict() -> list[dict]:
    seq = [1, -2, 2, -2, 1]
    if random.random() < 0.5:
        return [{"dx": s, "dy": 0, "ms": 80} for s in seq]
    return [{"dx": 0, "dy": s, "ms": 80} for s in seq]

def _steps_order() -> list[dict]:
    cw = [
        {"dx": 1, "dy": 0}, {"dx": 1, "dy": 1}, {"dx": 0, "dy": 1}, {"dx": -1, "dy": 1},
        {"dx": -1, "dy": 0}, {"dx": -1, "dy": -1}, {"dx": 0, "dy": -1}, {"dx": 1, "dy": -1},
    ]
    steps = cw if random.random() < 0.5 else list(reversed(cw))
    start = random.randint(0, 7)
    rotated = steps[start:] + steps[:start]
    return [{**s, "ms": 750} for s in rotated]

VP_PATTERNS: dict[str, dict] = {
    "water":    {"prob": 0.14, "make": _steps_water},
    "fire":     {"prob": 0.14, "make": _steps_fire},
    "change":   {"prob": 0.12, "make": _steps_change},
    "conflict": {"prob": 0.13, "make": _steps_conflict},
    "order":    {"prob": 0.07, "make": _steps_order},
}

BASE_PAN: dict[str, float] = {
    "conflict": 0.18, "fire": 0.18, "change": 0.16, "light": 0.07, "water": 0.06,
    "growth": 0.06, "truth": 0.03, "mastery": 0.03, "sacrifice": 0.03,
    "community": 0.03, "decay": 0.03, "memory": 0.02, "order": 0.01,
    "silence": 0.01, "void": 0.01, "secrecy": 0.01,
}
PAN_DIRS: list[dict] = [
    {"dx": 1, "dy": 0, "ms": 500}, {"dx": -1, "dy": 0, "ms": 500},
    {"dx": 0, "dy": 1, "ms": 500}, {"dx": 0, "dy": -1, "ms": 500},
]

# ── Pure helpers ───────────────────────────────────────────────────────────────
def build_pool(affs: dict) -> list[dict]:
    pool: list[dict] = []
    for k in DOMAIN_KEYS:
        a = affs.get(k, 0.0)
        if a < 0.05:
            continue
        d = DOMAINS[k]
        for _ in range(max(1, round(a * 14))):
            pool.append({"symbols": d["symbols"], "rgb": d["color"]})
    return pool or [{"symbols": [" "], "rgb": (0x11, 0x11, 0x11)}]


def pick_cell(pool: list[dict], prev: Optional[dict] = None) -> dict:
    e = random.choice(pool)
    cell: dict = {
        "char": random.choice(e["symbols"]),
        "rgb": e["rgb"],
        "bright": prev.get("bright", False) if prev else False,
        "dim":    prev.get("dim",    False) if prev else False,
    }
    return cell


def get_speed(affs: dict) -> dict:
    top = max(DOMAIN_KEYS, key=lambda k: affs.get(k, 0.0))
    return SPEED_PARAMS[DOMAINS[top]["speed"]]


def get_aura_rgb(affs: dict) -> tuple[int, int, int]:
    r = g = b = t = 0.0
    for k in DOMAIN_KEYS:
        a = affs.get(k, 0.0)
        if a < 0.05:
            continue
        cr, cg, cb = DOMAINS[k]["color"]
        r += cr * a; g += cg * a; b += cb * a; t += a
    return (int(r / t), int(g / t), int(b / t)) if t else (0x33, 0x33, 0x33)


def blend(rgb: tuple, target: tuple, f: float) -> tuple:
    return tuple(int(c + (t - c) * f) for c, t in zip(rgb, target))


def cell_rich_color(cell: dict) -> Color:
    rgb = cell["rgb"]
    if cell.get("bright"):
        rgb = blend(rgb, (255, 255, 255), 0.7)
    elif cell.get("dim"):
        rgb = blend(rgb, (0x1e, 0x1e, 0x2a), 0.85)
    return Color.from_rgb(*rgb)


def domain_legend(affs: dict) -> Text:
    active = sorted(
        [(k, v) for k in DOMAIN_KEYS if (v := affs.get(k, 0.0)) >= 0.1],
        key=lambda x: -x[1],
    )
    text = Text()
    for k, v in active:
        d = DOMAINS[k]
        c = Color.from_rgb(*d["color"])
        text.append(f" {d['symbol']} ", style=Style(color=c, bold=True))
        text.append(f"{d['label']:<10} {int(v * 100):2}%\n", style=Style(color=c))
    if not active:
        text.append(" no domain affinity\n", style=Style(color=Color.from_rgb(0x33, 0x33, 0x33)))
    return text


# ── LuminaryDisplay widget ─────────────────────────────────────────────────────
class LuminaryDisplay(Widget):
    DEFAULT_CSS = f"""
    LuminaryDisplay {{
        width: {VIEW_W + 2};
        height: {VIEW_H + 2};
        border: round white;
        background: #07090e;
    }}
    """

    def __init__(self, affs: dict, **kwargs) -> None:
        super().__init__(**kwargs)
        self._affs: dict = dict(affs)
        self._cells: list[dict] = [dict(BLANK) for _ in range(FULL_SIZE)]
        self._vx: int = FULL_W       # viewport origin x in virtual space
        self._vy: int = FULL_H       # viewport origin y in virtual space
        self._lock: bytearray = bytearray(FULL_SIZE)   # 1 = cell immune to random replacement
        self._frozen: bool = False      # truth effect: halt all animation
        self._vp_running: bool = False  # viewport sequence in progress
        self._last_fx: float = 0.0     # epoch time of last cell effect
        self._pool: list[dict] = []
        self._speed: dict = SPEED_PARAMS["medium"]

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def on_mount(self) -> None:
        self._rebuild(init=True)
        self._schedule_anim()
        self.set_interval(0.5, self._vp_trigger)
        self.set_interval(0.6, self._fx_trigger)

    def _rebuild(self, init: bool = False) -> None:
        self._pool = build_pool(self._affs)
        self._speed = get_speed(self._affs)
        ar, ag, ab = get_aura_rgb(self._affs)
        aura_hex = f"#{ar:02x}{ag:02x}{ab:02x}"
        self.styles.border = ("round", aura_hex)
        if init:
            self._cells = [pick_cell(self._pool) for _ in range(FULL_SIZE)]

    def set_affs(self, affs: dict) -> None:
        self._affs = dict(affs)
        self._rebuild()
        self.refresh()

    # ── Animation tick ─────────────────────────────────────────────────────────

    def _schedule_anim(self) -> None:
        self.set_timer(self._speed["interval"] / 1000.0, self._anim_tick)

    def _anim_tick(self) -> None:
        if not self._frozen:
            count = max(1, round(FULL_SIZE * self._speed["rate"]))
            lock = self._lock
            pool = self._pool
            cells = self._cells
            for _ in range(count):
                idx = random.randrange(FULL_SIZE)
                if not lock[idx]:
                    cells[idx] = pick_cell(pool, cells[idx])
            self.refresh()
        self._schedule_anim()

    # ── Viewport helpers ───────────────────────────────────────────────────────

    def _vvr(self, r: int) -> int:
        return (self._vy + r) % FULL_H

    def _vvc(self, c: int) -> int:
        return (self._vx + c) % FULL_W

    def _vwrap(self) -> None:
        if self._vx < FULL_W * 0.5:
            self._vx += FULL_W
        elif self._vx >= FULL_W * 2.5:
            self._vx -= FULL_W
        if self._vy < FULL_H * 0.5:
            self._vy += FULL_H
        elif self._vy >= FULL_H * 2.5:
            self._vy -= FULL_H

    def _vp_trigger(self) -> None:
        if self._vp_running:
            return
        for k in DOMAIN_KEYS:
            aff = self._affs.get(k, 0.0)
            if aff < 0.1:
                continue
            sp = VP_PATTERNS.get(k)
            if sp and random.random() < sp["prob"] * (aff / 0.8):
                self._run_seq(sp["make"]())
                return
        top = max(DOMAIN_KEYS, key=lambda k: self._affs.get(k, 0.0))
        if random.random() < BASE_PAN.get(top, 0.02):
            self._run_seq([random.choice(PAN_DIRS)])

    def _run_seq(self, steps: list[dict]) -> None:
        self._vp_running = True
        self._do_step(steps, 0)

    def _do_step(self, steps: list[dict], idx: int) -> None:
        if idx >= len(steps):
            self._vwrap()
            self._vp_running = False
            return
        step = steps[idx]
        self._vx += step["dx"]
        self._vy += step["dy"]
        self.refresh()
        ms = step.get("ms", 150)
        self.set_timer(ms / 1000.0, lambda s=steps, i=idx + 1: self._do_step(s, i))

    # ── Cell effects ───────────────────────────────────────────────────────────

    _CELL_FX_PROBS: dict[str, float] = {
        "memory": 0.10, "decay": 0.10, "sacrifice": 0.10,
        "growth": 0.09, "truth": 0.08, "void": 0.08,
        "silence": 0.09, "light": 0.09, "secrecy": 0.09,
    }

    def _fx_trigger(self) -> None:
        if self._vp_running:
            return
        if time.time() - self._last_fx < 4.2:
            return
        dispatch = {
            "memory": self._fx_memory, "decay": self._fx_decay,
            "sacrifice": self._fx_sacrifice, "growth": self._fx_growth,
            "truth": self._fx_truth, "void": self._fx_void,
            "silence": self._fx_silence, "light": self._fx_light,
            "secrecy": self._fx_secrecy,
        }
        for k in DOMAIN_KEYS:
            aff = self._affs.get(k, 0.0)
            if aff < 0.1:
                continue
            prob = self._CELL_FX_PROBS.get(k, 0.0)
            if prob and random.random() < prob * (aff / 0.8):
                self._last_fx = time.time()
                dispatch[k]()
                return

    def _fx_memory(self) -> None:
        """Alternating rows shift left/right in steps."""
        vy0 = self._vy
        steps = 4 + random.randint(0, 2)

        def do_step(s: int) -> None:
            shift_even = (s % 2 == 0)
            for vr in range(VIEW_H):
                if (vr % 2 == 0) != shift_even:
                    continue
                row = (vy0 + vr) % FULL_H
                base = row * FULL_W
                if shift_even:
                    last = self._cells[base + FULL_W - 1]
                    for c in range(FULL_W - 1, 0, -1):
                        self._cells[base + c] = self._cells[base + c - 1]
                    self._cells[base] = last
                else:
                    first = self._cells[base]
                    for c in range(FULL_W - 1):
                        self._cells[base + c] = self._cells[base + c + 1]
                    self._cells[base + FULL_W - 1] = first
            self.refresh()
            if s + 1 < steps:
                self.set_timer(0.36, lambda s2=s + 1: do_step(s2))

        do_step(0)

    def _fx_decay(self) -> None:
        """Column falls away: symbols cascade downward, blanks enter from top."""
        vx0, vy0 = self._vx, self._vy
        col = (vx0 + random.randrange(VIEW_W)) % FULL_W
        vrows = [(vy0 + r) % FULL_H for r in range(VIEW_H)]

        def do_step(step: int) -> None:
            for i in range(VIEW_H - 1, 0, -1):
                self._cells[vrows[i] * FULL_W + col] = self._cells[vrows[i - 1] * FULL_W + col]
            top_idx = vrows[0] * FULL_W + col
            self._cells[top_idx] = dict(BLANK)
            self._lock[top_idx] = 1
            self.refresh()
            if step + 1 < VIEW_H:
                self.set_timer(0.2, lambda s=step + 1: do_step(s))
            else:
                for r in range(VIEW_H):
                    self._lock[vrows[r] * FULL_W + col] = 1
                def unlock(rows=vrows, c=col):
                    for r in range(VIEW_H):
                        self._lock[rows[r] * FULL_W + c] = 0
                self.set_timer(3.2, unlock)

        do_step(0)

    def _fx_sacrifice(self) -> None:
        """Column rises away: symbols cascade upward, blanks enter from bottom."""
        vx0, vy0 = self._vx, self._vy
        col = (vx0 + random.randrange(VIEW_W)) % FULL_W
        vrows = [(vy0 + r) % FULL_H for r in range(VIEW_H)]

        def do_step(step: int) -> None:
            for i in range(VIEW_H - 1):
                self._cells[vrows[i] * FULL_W + col] = self._cells[vrows[i + 1] * FULL_W + col]
            bot_idx = vrows[VIEW_H - 1] * FULL_W + col
            self._cells[bot_idx] = dict(BLANK)
            self._lock[bot_idx] = 1
            self.refresh()
            if step + 1 < VIEW_H:
                self.set_timer(0.2, lambda s=step + 1: do_step(s))
            else:
                for r in range(VIEW_H):
                    self._lock[vrows[r] * FULL_W + col] = 1
                def unlock(rows=vrows, c=col):
                    for r in range(VIEW_H):
                        self._lock[rows[r] * FULL_W + c] = 0
                self.set_timer(3.2, unlock)

        do_step(0)

    def _fx_growth(self) -> None:
        """Column scrolls upward, new symbols growing from the bottom."""
        vx0, vy0 = self._vx, self._vy
        col = (vx0 + random.randrange(VIEW_W)) % FULL_W
        vrows = [(vy0 + r) % FULL_H for r in range(VIEW_H)]
        pool = list(self._pool)

        def do_step(step: int) -> None:
            for i in range(VIEW_H - 1):
                self._cells[vrows[i] * FULL_W + col] = self._cells[vrows[i + 1] * FULL_W + col]
            self._cells[vrows[VIEW_H - 1] * FULL_W + col] = pick_cell(pool)
            self.refresh()
            if step + 1 < VIEW_H:
                self.set_timer(0.15, lambda s=step + 1: do_step(s))

        do_step(0)

    def _fx_truth(self) -> None:
        """All animation pauses briefly, the field frozen and clear."""
        self._frozen = True
        duration = 2.0 + random.random() * 2.0
        self.set_timer(duration, lambda: setattr(self, "_frozen", False))

    def _fx_void(self) -> None:
        """The field splits apart — either horizontally or vertically — leaving a blank seam."""
        vx0, vy0 = self._vx, self._vy
        vcols = [(vx0 + c) % FULL_W for c in range(VIEW_W)]
        vrows = [(vy0 + r) % FULL_H for r in range(VIEW_H)]
        horiz = random.random() < 0.5

        if not horiz:
            half = VIEW_H // 2  # = 4
            # top half shifts up (each row i gets row i+1)
            for i in range(half - 1):
                for c in range(VIEW_W):
                    self._cells[vrows[i] * FULL_W + vcols[c]] = self._cells[vrows[i + 1] * FULL_W + vcols[c]]
            # blank the seam rows
            for c in range(VIEW_W):
                idx = vrows[half - 1] * FULL_W + vcols[c]
                self._cells[idx] = dict(BLANK); self._lock[idx] = 1
            # bottom half shifts down (each row i gets row i-1)
            for i in range(VIEW_H - 1, half, -1):
                for c in range(VIEW_W):
                    self._cells[vrows[i] * FULL_W + vcols[c]] = self._cells[vrows[i - 1] * FULL_W + vcols[c]]
            for c in range(VIEW_W):
                idx = vrows[half] * FULL_W + vcols[c]
                self._cells[idx] = dict(BLANK); self._lock[idx] = 1
            def unlock(rows=vrows, cols=vcols):
                for rr in [half - 1, half]:
                    for c in range(VIEW_W):
                        self._lock[rows[rr] * FULL_W + cols[c]] = 0
            self.set_timer(3.0, unlock)
        else:
            half = VIEW_W // 2  # = 3
            # left half shifts left (col i gets col i+1)
            for i in range(half - 1):
                for r in range(VIEW_H):
                    self._cells[vrows[r] * FULL_W + vcols[i]] = self._cells[vrows[r] * FULL_W + vcols[i + 1]]
            # blank the seam cols
            for r in range(VIEW_H):
                for cc in [half - 1, half]:
                    idx = vrows[r] * FULL_W + vcols[cc]
                    self._cells[idx] = dict(BLANK); self._lock[idx] = 1
            # right half shifts right (col i gets col i-1)
            for i in range(VIEW_W - 1, half + 1, -1):
                for r in range(VIEW_H):
                    self._cells[vrows[r] * FULL_W + vcols[i]] = self._cells[vrows[r] * FULL_W + vcols[i - 1]]
            for r in range(VIEW_H):
                idx = vrows[r] * FULL_W + vcols[half + 1]
                self._cells[idx] = dict(BLANK); self._lock[idx] = 1
            def unlock(rows=vrows, cols=vcols):
                for cc in [half - 1, half, half + 1]:
                    for r in range(VIEW_H):
                        self._lock[rows[r] * FULL_W + cols[cc]] = 0
            self.set_timer(3.0, unlock)

        self.refresh()

    def _fx_silence(self) -> None:
        """A row or column goes blank cell by cell, then slowly fills again."""
        vx0, vy0 = self._vx, self._vy
        vcols = [(vx0 + c) % FULL_W for c in range(VIEW_W)]
        vrows = [(vy0 + r) % FULL_H for r in range(VIEW_H)]
        is_row = random.random() < 0.5
        fwd    = random.random() < 0.5

        if is_row:
            row = vrows[random.randrange(VIEW_H)]
            order = list(range(VIEW_W)) if fwd else list(range(VIEW_W - 1, -1, -1))
            indices = [row * FULL_W + vcols[s] for s in order]
            delay, total = 0.23, VIEW_W
        else:
            col = vcols[random.randrange(VIEW_W)]
            order = list(range(VIEW_H)) if fwd else list(range(VIEW_H - 1, -1, -1))
            indices = [vrows[s] * FULL_W + col for s in order]
            delay, total = 0.28, VIEW_H

        def do_step(s: int) -> None:
            idx = indices[s]
            self._cells[idx] = dict(BLANK)
            self._lock[idx] = 1
            self.refresh()
            if s + 1 < total:
                self.set_timer(delay, lambda s2=s + 1: do_step(s2))
            else:
                def unlock(idxs=indices):
                    for i in idxs:
                        self._lock[i] = 0
                self.set_timer(4.0, unlock)

        do_step(0)

    def _fx_light(self) -> None:
        """A scatter of visible cells blooms bright white, then fades."""
        vx0, vy0 = self._vx, self._vy
        count = max(1, round(VIEW_W * VIEW_H * 0.28))
        targets: set[int] = set()
        while len(targets) < count:
            vr = (vy0 + random.randrange(VIEW_H)) % FULL_H
            vc = (vx0 + random.randrange(VIEW_W)) % FULL_W
            targets.add(vr * FULL_W + vc)
        for idx in targets:
            if self._cells[idx]["char"].strip():
                self._cells[idx] = {**self._cells[idx], "bright": True, "dim": False}
        self.refresh()

        def unbright(tgts=targets):
            for idx in tgts:
                if self._cells[idx].get("bright"):
                    self._cells[idx] = {**self._cells[idx], "bright": False}
            self.refresh()

        self.set_timer(1.6 + random.random() * 1.8, unbright)

    def _fx_secrecy(self) -> None:
        """A scatter of cells dims to near-black, then slowly resurfaces."""
        vx0, vy0 = self._vx, self._vy
        count = max(1, round(VIEW_W * VIEW_H * 0.28))
        targets: set[int] = set()
        while len(targets) < count:
            vr = (vy0 + random.randrange(VIEW_H)) % FULL_H
            vc = (vx0 + random.randrange(VIEW_W)) % FULL_W
            targets.add(vr * FULL_W + vc)
        for idx in targets:
            self._cells[idx] = {**self._cells[idx], "dim": True, "bright": False}
        self.refresh()

        def undim(tgts=targets):
            for idx in tgts:
                if self._cells[idx].get("dim"):
                    self._cells[idx] = {**self._cells[idx], "dim": False}
            self.refresh()

        self.set_timer(1.6 + random.random() * 1.8, undim)

    # ── Rendering ──────────────────────────────────────────────────────────────

    def render(self) -> Text:
        text = Text(no_wrap=True)
        for r in range(VIEW_H):
            vr = (self._vy + r) % FULL_H
            for c in range(VIEW_W):
                vc = (self._vx + c) % FULL_W
                cell = self._cells[vr * FULL_W + vc]
                text.append(cell["char"], style=Style(color=cell_rich_color(cell)))
            if r < VIEW_H - 1:
                text.append("\n")
        return text


# ── App ────────────────────────────────────────────────────────────────────────
class LuminaryDemoApp(App):
    CSS = f"""
    Screen {{
        background: #04080d;
        align: center middle;
    }}

    #title {{
        text-align: center;
        color: #2a2a44;
        height: 1;
        width: 100%;
    }}

    #main-row {{
        height: auto;
        width: auto;
        align: center middle;
    }}

    #right-panel {{
        width: 26;
        height: {VIEW_H + 2};
        padding: 0 1;
    }}

    #legend {{
        height: auto;
    }}

    #preset-row {{
        height: 3;
        width: 100%;
        align: center middle;
    }}

    Button {{
        min-width: 16;
        height: 1;
        border: none;
        background: transparent;
        color: #334455;
    }}

    Button:hover {{
        background: #0a1520;
        color: #7799bb;
    }}

    Button:focus {{
        background: #0a1520;
        color: #aaccee;
        border: none;
    }}

    #hint {{
        text-align: center;
        color: #1e2a1e;
        height: 1;
        width: 100%;
    }}
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("1", "preset(0)", "Preset 1"),
        ("2", "preset(1)", "Preset 2"),
        ("3", "preset(2)", "Preset 3"),
        ("4", "preset(3)", "Preset 4"),
        ("5", "preset(4)", "Preset 5"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._affs: dict = {k: 0.0 for k in DOMAIN_KEYS}
        self._affs.update(PRESETS[0]["affs"])

    def compose(self) -> ComposeResult:
        yield Static("LUMINARY PRESENCE VISUALIZER", id="title")
        with Horizontal(id="main-row"):
            yield LuminaryDisplay(self._affs, id="luminary")
            with Vertical(id="right-panel"):
                yield Static(domain_legend(self._affs), id="legend")
        with Horizontal(id="preset-row"):
            for i, p in enumerate(PRESETS):
                yield Button(p["name"], id=f"preset-{i}")
        yield Static("Q quit   1–5 presets", id="hint")

    def _apply_preset(self, idx: int) -> None:
        if not 0 <= idx < len(PRESETS):
            return
        self._affs = {k: 0.0 for k in DOMAIN_KEYS}
        self._affs.update(PRESETS[idx]["affs"])
        self.query_one("#luminary", LuminaryDisplay).set_affs(self._affs)
        self.query_one("#legend", Static).update(domain_legend(self._affs))

    @on(Button.Pressed)
    def on_button_pressed(self, event: Button.Pressed) -> None:
        bid = event.button.id or ""
        if bid.startswith("preset-"):
            self._apply_preset(int(bid.split("-")[1]))

    def action_preset(self, idx: int) -> None:
        self._apply_preset(idx)


if __name__ == "__main__":
    LuminaryDemoApp().run()
