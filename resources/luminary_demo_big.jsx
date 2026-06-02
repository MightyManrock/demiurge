import { useState, useEffect, useRef } from "react";

const DOMAINS = {
  order:     { label: "Order",     symbol: "⬡", color: "#90b4f0", symbols: ["═","║","╔","╗","╚","╝","┼","─","┤","├","╠","╣","╦","╩"], speed: "slow" },
  silence:   { label: "Silence",   symbol: "◯", color: "#7a8fa6", symbols: ["◯","·","∘","○","◌"," "," "," ","⊹","‥"], speed: "slow" },
  truth:     { label: "Truth",     symbol: "◈", color: "#b8b8cc", symbols: ["◈","✦","⊕","✧","⊗","⋄","⟐","◇","◆","⊞"], speed: "medium" },
  conflict:  { label: "Conflict",  symbol: "✖", color: "#ff6b6b", symbols: ["✖","╳","✕","×","▲","⚡","▶","◀","▼","⟆"], speed: "fast" },
  change:    { label: "Change",    symbol: "⬍", color: "#5fcca8", symbols: ["↺","↻","⟳","≈","~","⌀","⇌","⇄","↯","⇅"], speed: "fast" },
  fire:      { label: "Fire",      symbol: "🜂", color: "#ff9f40", symbols: ["▲","△","▴","∧","^","⟨","▵","⋀","∆","ʌ"], speed: "fast" },
  water:     { label: "Water",     symbol: "≋", color: "#4ecdc4", symbols: ["≋","≈","∿","~","⌇","⌊","∼","⌣","⏜","⌢"], speed: "medium" },
  void:      { label: "Void",      symbol: "∅", color: "#9b72cf", symbols: ["∅","◌","□","░"," "," "," ","▫","⊡","▭"], speed: "slow" },
  growth:    { label: "Growth",    symbol: "✿", color: "#7bc67e", symbols: ["✿","❀","✾","⁂","∗","⊛","❋","✳","⊕","✢"], speed: "medium" },
  decay:     { label: "Decay",     symbol: "☋", color: "#c4956a", symbols: ["☋","⁂","∴","∵","¨","⌀","∾","⁖","⁘","⁙"], speed: "medium" },
  memory:    { label: "Memory",    symbol: "◉", color: "#e8c96a", symbols: ["◉","◎","⊙","○","●","⊚","⊛","◌","⊜","◍"], speed: "slow" },
  sacrifice: { label: "Sacrifice", symbol: "⚱", color: "#e05c6c", symbols: ["⚱","☽","⋆","*","✦","⛤","✵","⊶","⊷","∗"], speed: "medium" },
  light:     { label: "Light",     symbol: "☼", color: "#fff4a0", symbols: ["☼","✴","★","✦","⟡","⊹","✧","✯","✬","✭"], speed: "medium" },
  mastery:   { label: "Mastery",   symbol: "⚙", color: "#b0bec5", symbols: ["⚙","⬡","⊞","◧","⊡","⊟","⊠","⊝","◫","◪"], speed: "medium" },
  secrecy:   { label: "Secrecy",   symbol: "⛉", color: "#26c6da", symbols: ["⛉","⊘","▣","▪","◾","⊡","▩","◼","▬","⊏"], speed: "slow" },
  community: { label: "Community", symbol: "♾", color: "#f48fb1", symbols: ["♾","∞","⊕","⊞","⊛","⊗","⊎","⋈","⊍","∪"], speed: "medium" },
};

const KEYS = Object.keys(DOMAINS);
const GRID_W = 24;
const GRID_H = 13;
const GRID_SIZE = GRID_W * GRID_H;

const SPEED_PARAMS = {
  fast:   { interval: 100, rate: 0.32 },
  medium: { interval: 210, rate: 0.22 },
  slow:   { interval: 420, rate: 0.11 },
};

const PRESETS = [
  {
    name: "The Lawgiver",
    affs: { order: 0.80, truth: 0.55, light: 0.30 }
  },
  {
    name: "The Wrathful",
    affs: { conflict: 0.80, fire: 0.55, change: 0.35 }
  },
  {
    name: "The Watcher",
    affs: { silence: 0.75, memory: 0.60, void: 0.25 }
  },
  {
    name: "The Verdant",
    affs: { growth: 0.75, water: 0.55, community: 0.40 }
  },
  {
    name: "The Null",
    affs: { void: 0.80, secrecy: 0.45, decay: 0.35 }
  },
];

function buildPool(affinities) {
  const pool = [];
  for (const key of KEYS) {
    const aff = affinities[key] || 0;
    if (aff < 0.05) continue;
    const count = Math.max(1, Math.round(aff * 14));
    const { symbols, color } = DOMAINS[key];
    for (let i = 0; i < count; i++) {
      pool.push({ symbols, color, domain: key });
    }
  }
  if (!pool.length) pool.push({ symbols: [" "], color: "#222", domain: "void" });
  return pool;
}

function getAnimParams(affinities) {
  const top = KEYS
    .map(k => ({ k, v: affinities[k] || 0 }))
    .sort((a, b) => b.v - a.v)[0]?.k;
  const speedKey = DOMAINS[top]?.speed || "medium";
  return SPEED_PARAMS[speedKey];
}

function pickFromPool(pool) {
  const entry = pool[Math.floor(Math.random() * pool.length)];
  return {
    char: entry.symbols[Math.floor(Math.random() * entry.symbols.length)],
    color: entry.color,
  };
}

function getAuraColor(affinities) {
  let r = 0, g = 0, b = 0, total = 0;
  for (const key of KEYS) {
    const aff = affinities[key] || 0;
    if (aff < 0.05) continue;
    const hex = DOMAINS[key].color;
    const ri = parseInt(hex.slice(1, 3), 16);
    const gi = parseInt(hex.slice(3, 5), 16);
    const bi = parseInt(hex.slice(5, 7), 16);
    r += ri * aff; g += gi * aff; b += bi * aff; total += aff;
  }
  if (!total) return "#333";
  return `rgb(${Math.round(r/total)},${Math.round(g/total)},${Math.round(b/total)})`;
}

function emptyAffinities() {
  const a = {};
  for (const k of KEYS) a[k] = 0;
  return a;
}

export default function App() {
  const [affinities, setAffinities] = useState(() => ({
    ...emptyAffinities(),
    order: 0.80,
    silence: 0.50,
  }));

  const [cells, setCells] = useState(() =>
    Array(GRID_SIZE).fill({ char: " ", color: "#111" })
  );

  const poolRef = useRef(buildPool({ order: 0.80, silence: 0.50 }));
  const paramsRef = useRef(getAnimParams({ order: 0.80, silence: 0.50 }));
  const timerRef = useRef(null);
  const mountedRef = useRef(false);

  // Rebuild pool on affinity change
  useEffect(() => {
    poolRef.current = buildPool(affinities);
    paramsRef.current = getAnimParams(affinities);
  }, [affinities]);

  // Initialize grid once on mount
  useEffect(() => {
    const pool = buildPool(affinities);
    setCells(Array(GRID_SIZE).fill(null).map(() => pickFromPool(pool)));
    mountedRef.current = true;
  }, []);

  // Animation loop — runs once, reads from refs
  useEffect(() => {
    function tick() {
      const pool = poolRef.current;
      const { rate, interval } = paramsRef.current;
      const count = Math.max(1, Math.round(GRID_SIZE * rate));
      setCells(prev => {
        const next = [...prev];
        for (let i = 0; i < count; i++) {
          const idx = Math.floor(Math.random() * GRID_SIZE);
          next[idx] = pickFromPool(pool);
        }
        return next;
      });
      timerRef.current = setTimeout(tick, interval);
    }
    timerRef.current = setTimeout(tick, 200);
    return () => clearTimeout(timerRef.current);
  }, []);

  const setAff = (key, val) =>
    setAffinities(prev => ({ ...prev, [key]: parseFloat(val) }));

  const applyPreset = (preset) => {
    const a = emptyAffinities();
    for (const [k, v] of Object.entries(preset.affs)) a[k] = v;
    setAffinities(a);
  };

  const aura = getAuraColor(affinities);
  const topDomains = KEYS
    .map(k => ({ k, v: affinities[k] || 0 }))
    .filter(d => d.v >= 0.1)
    .sort((a, b) => b.v - a.v);

  return (
    <div style={{
      minHeight: "100vh",
      background: "#04080d",
      color: "#aaa",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      justifyContent: "center",
      padding: "2rem 1rem",
      gap: "1.5rem",
      fontFamily: '"Courier New", Courier, monospace',
    }}>

      {/* Title */}
      <div style={{ textAlign: "center" }}>
        <div style={{ fontSize: "0.65rem", letterSpacing: "0.4em", color: "#555", marginBottom: "0.25rem" }}>
          LUMINARY PRESENCE VISUALIZER
        </div>
        <div style={{ fontSize: "0.55rem", letterSpacing: "0.2em", color: "#333" }}>
          DOMAIN AFFINITY → SYMBOL POOL → ANIMATED PRESENCE
        </div>
      </div>

      {/* Main layout */}
      <div style={{
        display: "flex",
        gap: "2.5rem",
        alignItems: "flex-start",
        flexWrap: "wrap",
        justifyContent: "center",
      }}>

        {/* Left: profile + info */}
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: "0.75rem" }}>

          {/* The profile box */}
          <div style={{
            border: `1px solid ${aura}55`,
            boxShadow: `0 0 24px ${aura}30, 0 0 60px ${aura}15, inset 0 0 16px #00000080`,
            padding: "0.75rem",
            background: "#070c12",
            position: "relative",
          }}>
            {/* Corner ornaments */}
            {["╔","╗","╚","╝"].map((c, i) => (
              <span key={i} style={{
                position: "absolute",
                color: aura + "88",
                fontSize: "0.7rem",
                ...[{top:3,left:3},{top:3,right:3},{bottom:3,left:3},{bottom:3,right:3}][i]
              }}>{c}</span>
            ))}
            <div style={{
              display: "grid",
              gridTemplateColumns: `repeat(${GRID_W}, 1ch)`,
              lineHeight: "1.45",
              fontSize: "0.95rem",
              userSelect: "none",
            }}>
              {cells.map((cell, i) => (
                <span
                  key={i}
                  style={{
                    color: cell.color,
                    textShadow: cell.char.trim()
                      ? `0 0 5px ${cell.color}99`
                      : "none",
                    display: "inline-block",
                    width: "1ch",
                    textAlign: "center",
                  }}
                >
                  {cell.char}
                </span>
              ))}
            </div>
          </div>

          {/* Active domain tags */}
          <div style={{
            display: "flex",
            flexWrap: "wrap",
            gap: "0.4rem",
            justifyContent: "center",
            maxWidth: `${GRID_W * 0.95 + 1.5}rem`,
          }}>
            {topDomains.length === 0 && (
              <span style={{ fontSize: "0.6rem", color: "#333", letterSpacing: "0.15em" }}>
                NO DOMAIN AFFINITY
              </span>
            )}
            {topDomains.map(({ k, v }) => (
              <span key={k} style={{
                fontSize: "0.6rem",
                color: DOMAINS[k].color,
                letterSpacing: "0.08em",
                opacity: 0.45 + v * 0.55,
                border: `1px solid ${DOMAINS[k].color}33`,
                padding: "0.1rem 0.35rem",
              }}>
                {DOMAINS[k].symbol} {DOMAINS[k].label} {(v * 100).toFixed(0)}%
              </span>
            ))}
          </div>

          {/* Presets */}
          <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap", justifyContent: "center" }}>
            {PRESETS.map(p => (
              <button
                key={p.name}
                onClick={() => applyPreset(p)}
                style={{
                  background: "transparent",
                  border: "1px solid #2a3a4a",
                  color: "#556",
                  fontSize: "0.6rem",
                  padding: "0.2rem 0.5rem",
                  cursor: "pointer",
                  letterSpacing: "0.1em",
                  fontFamily: "inherit",
                  transition: "all 0.2s",
                }}
                onMouseEnter={e => {
                  e.target.style.borderColor = "#4a6a8a";
                  e.target.style.color = "#8ab";
                }}
                onMouseLeave={e => {
                  e.target.style.borderColor = "#2a3a4a";
                  e.target.style.color = "#556";
                }}
              >
                {p.name}
              </button>
            ))}
          </div>
        </div>

        {/* Right: domain sliders */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "1fr 1fr",
          gap: "0.55rem 1.8rem",
          minWidth: "300px",
        }}>
          {KEYS.map(key => {
            const { label, symbol, color } = DOMAINS[key];
            const val = affinities[key] || 0;
            const active = val >= 0.1;
            return (
              <div key={key}>
                <div style={{
                  display: "flex",
                  justifyContent: "space-between",
                  marginBottom: "2px",
                }}>
                  <span style={{
                    fontSize: "0.68rem",
                    color: active ? color : "#353535",
                    letterSpacing: "0.05em",
                    transition: "color 0.3s",
                  }}>
                    {symbol} {label}
                  </span>
                  <span style={{
                    fontSize: "0.62rem",
                    color: active ? color + "bb" : "#2a2a2a",
                    transition: "color 0.3s",
                  }}>
                    {val.toFixed(2)}
                  </span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="0.8"
                  step="0.05"
                  value={val}
                  onChange={e => setAff(key, e.target.value)}
                  style={{
                    width: "100%",
                    height: "2px",
                    accentColor: color,
                    cursor: "pointer",
                    background: `linear-gradient(to right, ${color}88 0%, ${color}88 ${(val/0.8)*100}%, #1a2430 ${(val/0.8)*100}%)`,
                  }}
                />
              </div>
            );
          })}
        </div>
      </div>

      {/* Footer note */}
      <div style={{
        fontSize: "0.55rem",
        color: "#252525",
        letterSpacing: "0.15em",
        textAlign: "center",
        maxWidth: "480px",
        lineHeight: "1.8",
      }}>
        SYMBOL DENSITY WEIGHTED BY AFFINITY · ANIMATION RATE DERIVED FROM DOMINANT DOMAIN CHARACTER
        <br />
        THE LUMINARY HAS NO FORM — ONLY PRESENCE
      </div>
    </div>
  );
}
