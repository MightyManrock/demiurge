import { useState, useEffect, useRef, useMemo } from "react";

// ─── Domains ──────────────────────────────────────────────────────────────────
const DOMAINS = {
  order:     { label:"Order",     symbol:"⬡", color:"#90b4f0", symbols:["═","║","╔","╗","╚","╝","┼","─","┤","├","╠","╣","╦","╩"], speed:"slow" },
  silence:   { label:"Silence",   symbol:"◯", color:"#7a8fa6", symbols:["◯","·","∘","○","◌","⊹","‥","∙","⋯","⊸"],                  speed:"slow" },
  // Truth: cool near-white — distinct from Light's warm yellow
  truth:     { label:"Truth",     symbol:"◈", color:"#b8b8cc", symbols:["◈","✦","⊕","✧","⊗","⋄","⟐","◇","◆","⊞"],                  speed:"medium" },
  conflict:  { label:"Conflict",  symbol:"✖", color:"#ff6b6b", symbols:["✖","╳","✕","×","▲","⚡","▶","◀","▼","⟆"],                  speed:"fast" },
  change:    { label:"Change",    symbol:"⬍", color:"#5fcca8", symbols:["↺","↻","⟳","≈","~","⌀","⇌","⇄","↯","⇅"],                  speed:"fast" },
  fire:      { label:"Fire",      symbol:"🜂", color:"#ff9f40", symbols:["▲","△","▴","∧","^","⟨","▵","⋀","∆","ʌ"],                  speed:"fast" },
  water:     { label:"Water",     symbol:"≋", color:"#4ecdc4", symbols:["≋","≈","∿","~","⌇","⌊","∼","⌣","⏜","⌢"],                  speed:"medium" },
  void:      { label:"Void",      symbol:"∅", color:"#9b72cf", symbols:["∅","◌","□","░","▫","⊡","▭","◽","▪","◾"],                  speed:"slow" },
  growth:    { label:"Growth",    symbol:"✿", color:"#7bc67e", symbols:["✿","❀","✾","⁂","∗","⊛","❋","✳","⊕","✢"],                  speed:"medium" },
  decay:     { label:"Decay",     symbol:"☋", color:"#c4956a", symbols:["☋","⁂","∴","∵","¨","⌀","∾","⁖","⁘","⁙"],                  speed:"medium" },
  memory:    { label:"Memory",    symbol:"◉", color:"#e8c96a", symbols:["◉","◎","⊙","○","●","⊚","⊛","◌","⊜","◍"],                  speed:"slow" },
  sacrifice: { label:"Sacrifice", symbol:"⚱", color:"#e05c6c", symbols:["⚱","☽","⋆","*","✦","⛤","✵","⊶","⊷","∗"],                  speed:"medium" },
  light:     { label:"Light",     symbol:"☼", color:"#fff4a0", symbols:["☼","✴","★","✦","⟡","⊹","✧","✯","✬","✭"],                  speed:"medium" },
  mastery:   { label:"Mastery",   symbol:"⚙", color:"#b0bec5", symbols:["⚙","⬡","⊞","◧","⊡","⊟","⊠","⊝","◫","◪"],                  speed:"medium" },
  secrecy:   { label:"Secrecy",   symbol:"⛉", color:"#26c6da", symbols:["⛉","⊘","▣","▪","◾","⊡","▩","◼","▬","⊏"],                  speed:"slow" },
  community: { label:"Community", symbol:"♾", color:"#f48fb1", symbols:["♾","∞","⊕","⊞","⊛","⊗","⊎","⋈","⊍","∪"],                  speed:"medium" },
};
const KEYS = Object.keys(DOMAINS);

// ─── Grid constants ───────────────────────────────────────────────────────────
const FULL_W = 15, FULL_H = 19, FULL_SIZE = FULL_W * FULL_H;
const VIEW_W = 7,  VIEW_H = 9;
const TILE_W = FULL_W * 3, TILE_H = FULL_H * 3;
const INIT_VX = FULL_W, INIT_VY = FULL_H;
// LH < 1: rows overlap vertically, matching the horizontal crowding from 1ch columns
const LH = 0.88;
const BLANK = { char:" ", color:"#111" };

const SNAP_LO_X = FULL_W*0.5, SNAP_HI_X = FULL_W*2.5;
const SNAP_LO_Y = FULL_H*0.5, SNAP_HI_Y = FULL_H*2.5;

const TILE_TO_VIRT = new Int32Array(TILE_W * TILE_H);
for (let r = 0; r < TILE_H; r++)
  for (let c = 0; c < TILE_W; c++)
    TILE_TO_VIRT[r * TILE_W + c] = (r % FULL_H) * FULL_W + (c % FULL_W);

// ─── Helpers ──────────────────────────────────────────────────────────────────
const wrapVp = (vx, vy) => ({
  vx: vx < SNAP_LO_X ? vx+FULL_W : vx >= SNAP_HI_X ? vx-FULL_W : vx,
  vy: vy < SNAP_LO_Y ? vy+FULL_H : vy >= SNAP_HI_Y ? vy-FULL_H : vy,
});

// Viewport row/col → virtual row/col (handles all vp positions)
const vvr = (vp, r) => ((vp.vy + r) % FULL_H + FULL_H) % FULL_H;
const vvc = (vp, c) => ((vp.vx + c) % FULL_W + FULL_W) % FULL_W;

function buildPool(affs) {
  const pool = [];
  for (const k of KEYS) {
    const a=affs[k]||0; if(a<.05)continue;
    const n=Math.max(1,Math.round(a*14));
    const {symbols,color}=DOMAINS[k];
    for(let i=0;i<n;i++) pool.push({symbols,color});
  }
  return pool.length ? pool : [{symbols:[" "],color:"#111"}];
}

function pick(pool, prev) {
  const e = pool[Math.floor(Math.random()*pool.length)];
  const cell = { char:e.symbols[Math.floor(Math.random()*e.symbols.length)], color:e.color };
  // Preserve glow state when the animation tick replaces a cell
  if (prev?.bright) cell.bright = true;
  if (prev?.dim)    cell.dim    = true;
  return cell;
}

function getSpeed(affs) {
  const t=KEYS.map(k=>({k,v:affs[k]||0})).sort((a,b)=>b.v-a.v)[0]?.k;
  return ({fast:{interval:100,rate:.32},medium:{interval:210,rate:.22},slow:{interval:420,rate:.11}})[DOMAINS[t]?.speed||"medium"];
}

function getAura(affs) {
  let r=0,g=0,b=0,t=0;
  for(const k of KEYS){const a=affs[k]||0;if(a<.05)continue;const h=DOMAINS[k].color;r+=parseInt(h.slice(1,3),16)*a;g+=parseInt(h.slice(3,5),16)*a;b+=parseInt(h.slice(5,7),16)*a;t+=a;}
  return t?`rgb(${Math.round(r/t)},${Math.round(g/t)},${Math.round(b/t)})`:"#333";
}

const emptyAffs = () => Object.fromEntries(KEYS.map(k=>[k,0]));

// ─── Viewport movement patterns ───────────────────────────────────────────────
const VP = {
  // Water/Fire: tms > ms so transitions overlap → seamless continuous flow
  water:    { prob:.14, make:() => Array(3+Math.floor(Math.random()*3)).fill(null).map(()=>({dx:0,dy:-1,ms:150,tms:160})) },
  fire:     { prob:.14, make:() => Array(3+Math.floor(Math.random()*3)).fill(null).map(()=>({dx:0,dy: 1,ms:150,tms:160})) },
  change:   { prob:.12, make:() => { const d=2+Math.floor(Math.random()*4),dx=Math.random()<.5?1:-1,dy=Math.random()<.5?1:-1; return Array(d).fill(null).map(()=>({dx,dy,ms:90,tms:70})); }},
  conflict: { prob:.13, make:() => (Math.random()<.5?[{dx:1,dy:0},{dx:-2,dy:0},{dx:2,dy:0},{dx:-2,dy:0},{dx:1,dy:0}]:[{dx:0,dy:1},{dx:0,dy:-2},{dx:0,dy:2},{dx:0,dy:-2},{dx:0,dy:1}]).map(s=>({...s,ms:80,tms:0})) },
  // Order: random CW or CCW, random starting direction
  order: { prob:.07, make:() => {
    const cw = [{dx:1,dy:0},{dx:1,dy:1},{dx:0,dy:1},{dx:-1,dy:1},{dx:-1,dy:0},{dx:-1,dy:-1},{dx:0,dy:-1},{dx:1,dy:-1}];
    const steps = Math.random()<.5 ? cw : [...cw].reverse();
    const start = Math.floor(Math.random()*8);
    return [...steps.slice(start),...steps.slice(0,start)].map(s=>({...s,ms:750,tms:700}));
  }},
};

const BASE_PAN = { conflict:.18,fire:.18,change:.16,light:.07,water:.06,growth:.06,truth:.03,mastery:.03,sacrifice:.03,community:.03,decay:.03,memory:.02,order:.01,silence:.01,void:.01,secrecy:.01 };
const PAN_DIRS = [{dx:1,dy:0},{dx:-1,dy:0},{dx:0,dy:1},{dx:0,dy:-1}];

// ─── Cell effects ─────────────────────────────────────────────────────────────
// NOTE: All cell effects fire only when vpRunning is false (ensured by trigger).
// This guarantees vpRef.current matches the actual visual viewport position,
// so vvr(vp, r) correctly identifies which virtual rows are visible.

function fxMemory(vp, setCells) {
  // Alternating phases: even steps shift ONLY even viewport rows right,
  // odd steps shift ONLY odd viewport rows left. Stationary rows make
  // the skip pattern legible.
  const steps = 4 + Math.floor(Math.random()*3);
  const ids = [];
  for (let s = 0; s < steps; s++) {
    ids.push(setTimeout(() => {
      const shiftEven = (s%2===0);
      setCells(prev => {
        const next = [...prev];
        for (let vr = 0; vr < VIEW_H; vr++) {
          if ((vr%2===0) !== shiftEven) continue; // skip stationary rows
          const base = vvr(vp,vr)*FULL_W;
          if (shiftEven) {
            const last=prev[base+FULL_W-1];
            for(let c=FULL_W-1;c>0;c--) next[base+c]=prev[base+c-1];
            next[base]=last;
          } else {
            const first=prev[base];
            for(let c=0;c<FULL_W-1;c++) next[base+c]=prev[base+c+1];
            next[base+FULL_W-1]=first;
          }
        }
        return next;
      });
    }, s*360));
  }
  return ids;
}

function fxDecay(vp, setCells, lock) {
  // Column falls away: each step shifts the ENTIRE visible column DOWN one row,
  // blanking the virtual row at the TOP of the viewport and locking it.
  const col = vvc(vp, Math.floor(Math.random()*VIEW_W));
  const ids = [];
  for (let step = 0; step < VIEW_H; step++) {
    ids.push(setTimeout(() => {
      setCells(prev => {
        const next = [...prev];
        for (let vr = VIEW_H-1; vr > 0; vr--)
          next[vvr(vp,vr)*FULL_W+col] = prev[vvr(vp,vr-1)*FULL_W+col];
        const topIdx = vvr(vp,0)*FULL_W+col;
        next[topIdx] = BLANK;
        lock.current[topIdx] = 1;
        return next;
      });
    }, step*200));
  }
  ids.push(setTimeout(() => {
    for(let vr=0;vr<VIEW_H;vr++) lock.current[vvr(vp,vr)*FULL_W+col]=1;
    setTimeout(()=>{ for(let vr=0;vr<VIEW_H;vr++) lock.current[vvr(vp,vr)*FULL_W+col]=0; }, 3200);
  }, VIEW_H*200+50));
  return ids;
}

function fxSacrifice(vp, setCells, lock) {
  // Mirror of Decay: column rises away, blanks appear from the BOTTOM upward.
  const col = vvc(vp, Math.floor(Math.random()*VIEW_W));
  const ids = [];
  for (let step = 0; step < VIEW_H; step++) {
    ids.push(setTimeout(() => {
      setCells(prev => {
        const next = [...prev];
        for (let vr = 0; vr < VIEW_H-1; vr++)
          next[vvr(vp,vr)*FULL_W+col] = prev[vvr(vp,vr+1)*FULL_W+col];
        const botIdx = vvr(vp,VIEW_H-1)*FULL_W+col;
        next[botIdx] = BLANK;
        lock.current[botIdx] = 1;
        return next;
      });
    }, step*200));
  }
  ids.push(setTimeout(() => {
    for(let vr=0;vr<VIEW_H;vr++) lock.current[vvr(vp,vr)*FULL_W+col]=1;
    setTimeout(()=>{ for(let vr=0;vr<VIEW_H;vr++) lock.current[vvr(vp,vr)*FULL_W+col]=0; }, 3200);
  }, VIEW_H*200+50));
  return ids;
}

function fxGrowth(vp, setCells, pool) {
  // Column scrolls upward VIEW_H times — pronounced enough to read clearly
  const col = vvc(vp, Math.floor(Math.random()*VIEW_W));
  const ids = [];
  for (let step = 0; step < VIEW_H; step++) {
    ids.push(setTimeout(() => {
      setCells(prev => {
        const next = [...prev];
        for (let vr = 0; vr < VIEW_H-1; vr++)
          next[vvr(vp,vr)*FULL_W+col] = prev[vvr(vp,vr+1)*FULL_W+col];
        next[vvr(vp,VIEW_H-1)*FULL_W+col] = pick(pool, null);
        return next;
      });
    }, step*150));
  }
  return ids;
}

function fxTruth(frozenRef) {
  frozenRef.current = true;
  return [setTimeout(()=>{ frozenRef.current=false; }, 2000+Math.random()*2000)];
}

function fxVoid(vp, setCells, lock) {
  const horiz = Math.random()<.5;
  const ids = [];
  setCells(prev => {
    const next = [...prev];
    if (!horiz) {
      // Vertical: center row of viewport = Math.floor(VIEW_H/2) = 4
      // Top half (0..3) shifts UP; bottom half (5..8) shifts DOWN;
      // rows 3 and 4 become the blank seam.
      const half = Math.floor(VIEW_H/2); // = 4
      for(let vr=0;vr<half-1;vr++)
        for(let vc=0;vc<VIEW_W;vc++)
          next[vvr(vp,vr)*FULL_W+vvc(vp,vc)] = prev[vvr(vp,vr+1)*FULL_W+vvc(vp,vc)];
      for(let vc=0;vc<VIEW_W;vc++){
        const i=vvr(vp,half-1)*FULL_W+vvc(vp,vc); next[i]=BLANK; lock.current[i]=1;
      }
      for(let vr=VIEW_H-1;vr>half;vr--)
        for(let vc=0;vc<VIEW_W;vc++)
          next[vvr(vp,vr)*FULL_W+vvc(vp,vc)] = prev[vvr(vp,vr-1)*FULL_W+vvc(vp,vc)];
      for(let vc=0;vc<VIEW_W;vc++){
        const i=vvr(vp,half)*FULL_W+vvc(vp,vc); next[i]=BLANK; lock.current[i]=1;
      }
      ids.push(setTimeout(()=>{
        for(let vr=half-1;vr<=half;vr++) for(let vc=0;vc<VIEW_W;vc++) lock.current[vvr(vp,vr)*FULL_W+vvc(vp,vc)]=0;
      }, 3000));
    } else {
      // Horizontal: center col = Math.floor(VIEW_W/2) = 3
      const half = Math.floor(VIEW_W/2); // = 3
      for(let vc=0;vc<half-1;vc++)
        for(let vr=0;vr<VIEW_H;vr++)
          next[vvr(vp,vr)*FULL_W+vvc(vp,vc)] = prev[vvr(vp,vr)*FULL_W+vvc(vp,vc+1)];
      for(let vr=0;vr<VIEW_H;vr++){
        const i=vvr(vp,vr)*FULL_W+vvc(vp,half-1); next[i]=BLANK; lock.current[i]=1;
      }
      for(let vr=0;vr<VIEW_H;vr++){
        const i=vvr(vp,vr)*FULL_W+vvc(vp,half); next[i]=BLANK; lock.current[i]=1;
      }
      for(let vc=VIEW_W-1;vc>half+1;vc--)
        for(let vr=0;vr<VIEW_H;vr++)
          next[vvr(vp,vr)*FULL_W+vvc(vp,vc)] = prev[vvr(vp,vr)*FULL_W+vvc(vp,vc-1)];
      for(let vr=0;vr<VIEW_H;vr++){
        const i=vvr(vp,vr)*FULL_W+vvc(vp,half+1); next[i]=BLANK; lock.current[i]=1;
      }
      ids.push(setTimeout(()=>{
        for(let vc=half-1;vc<=half+1;vc++) for(let vr=0;vr<VIEW_H;vr++) lock.current[vvr(vp,vr)*FULL_W+vvc(vp,vc)]=0;
      }, 3000));
    }
    return next;
  });
  return ids;
}

function fxSilence(vp, setCells, lock) {
  const isRow = Math.random()<.5, fwd = Math.random()<.5;
  const ids = [];
  if (isRow) {
    const row = vvr(vp, Math.floor(Math.random()*VIEW_H));
    for(let s=0;s<VIEW_W;s++) {
      ids.push(setTimeout(()=>{
        const idx=row*FULL_W+vvc(vp,fwd?s:VIEW_W-1-s);
        setCells(prev=>{const n=[...prev];n[idx]=BLANK;return n;});
        lock.current[idx]=1;
      }, s*230));
    }
    ids.push(setTimeout(()=>{ for(let s=0;s<VIEW_W;s++) lock.current[row*FULL_W+vvc(vp,s)]=0; }, VIEW_W*230+4000));
  } else {
    const col = vvc(vp, Math.floor(Math.random()*VIEW_W));
    for(let s=0;s<VIEW_H;s++) {
      ids.push(setTimeout(()=>{
        const idx=vvr(vp,fwd?s:VIEW_H-1-s)*FULL_W+col;
        setCells(prev=>{const n=[...prev];n[idx]=BLANK;return n;});
        lock.current[idx]=1;
      }, s*280));
    }
    ids.push(setTimeout(()=>{ for(let s=0;s<VIEW_H;s++) lock.current[vvr(vp,s)*FULL_W+col]=0; }, VIEW_H*280+4000));
  }
  return ids;
}

function fxLight(vp, setCells) {
  // Boost brightness and saturation of ~25% of visible cells temporarily
  const targets = new Set();
  const count = Math.ceil(VIEW_W*VIEW_H*0.28);
  while (targets.size < count) {
    targets.add(vvr(vp,Math.floor(Math.random()*VIEW_H))*FULL_W + vvc(vp,Math.floor(Math.random()*VIEW_W)));
  }
  setCells(prev => {
    const next=[...prev];
    for(const idx of targets) if(next[idx]?.char?.trim()) next[idx]={...next[idx],bright:true,dim:false};
    return next;
  });
  return [setTimeout(()=>{
    setCells(prev=>{const next=[...prev]; for(const idx of targets) if(next[idx]?.bright) next[idx]={...next[idx],bright:false}; return next;});
  }, 1600+Math.random()*1800)];
}

function fxSecrecy(vp, setCells) {
  // Dim brightness and desaturate ~25% of visible cells temporarily
  const targets = new Set();
  const count = Math.ceil(VIEW_W*VIEW_H*0.28);
  while (targets.size < count) {
    targets.add(vvr(vp,Math.floor(Math.random()*VIEW_H))*FULL_W + vvc(vp,Math.floor(Math.random()*VIEW_W)));
  }
  setCells(prev => {
    const next=[...prev];
    for(const idx of targets) next[idx]={...next[idx],dim:true,bright:false};
    return next;
  });
  return [setTimeout(()=>{
    setCells(prev=>{const next=[...prev]; for(const idx of targets) if(next[idx]?.dim) next[idx]={...next[idx],dim:false}; return next;});
  }, 1600+Math.random()*1800)];
}

const CELL_FX = {
  memory:    { prob:.10, run:(vp,s,l,fr,p)=>fxMemory(vp,s) },
  decay:     { prob:.10, run:(vp,s,l,fr,p)=>fxDecay(vp,s,l) },
  sacrifice: { prob:.10, run:(vp,s,l,fr,p)=>fxSacrifice(vp,s,l) },
  growth:    { prob:.09, run:(vp,s,l,fr,p)=>fxGrowth(vp,s,p) },
  truth:     { prob:.08, run:(vp,s,l,fr,p)=>fxTruth(fr) },
  void:      { prob:.08, run:(vp,s,l,fr,p)=>fxVoid(vp,s,l) },
  silence:   { prob:.09, run:(vp,s,l,fr,p)=>fxSilence(vp,s,l) },
  light:     { prob:.09, run:(vp,s,l,fr,p)=>fxLight(vp,s) },
  secrecy:   { prob:.09, run:(vp,s,l,fr,p)=>fxSecrecy(vp,s) },
};

const PRESETS = [
  { name:"The Lawgiver",   affs:{ order:.80, truth:.55, light:.30 } },
  { name:"The Wrathful",   affs:{ conflict:.80, fire:.55, change:.35 } },
  { name:"The Watcher",    affs:{ silence:.75, memory:.60, void:.25 } },
  { name:"The Verdant",    affs:{ growth:.75, water:.55, community:.40 } },
  { name:"The Sacrificer", affs:{ sacrifice:.80, void:.45, decay:.30 } },
];

// ─── Component ────────────────────────────────────────────────────────────────
export default function App() {
  const [affs, setAffs]   = useState(()=>({...emptyAffs(),order:.80,silence:.50}));
  const [cells, setCells] = useState(()=>Array(FULL_SIZE).fill(BLANK));
  const [vp, setVp]       = useState({vx:INIT_VX,vy:INIT_VY});

  const transRef   = useRef(550);
  const poolRef    = useRef(buildPool({order:.80,silence:.50}));
  const speedRef   = useRef(getSpeed({order:.80,silence:.50}));
  const affsRef    = useRef({order:.80,silence:.50});
  const vpRef      = useRef({vx:INIT_VX,vy:INIT_VY});
  const lockGrid   = useRef(new Uint8Array(FULL_SIZE));
  const frozenRef  = useRef(false);
  const vpRunning  = useRef(false);
  const lastCellFx = useRef(0);
  const animTimer  = useRef(null);
  const seqTimer   = useRef(null);

  useEffect(()=>{ poolRef.current=buildPool(affs); speedRef.current=getSpeed(affs); affsRef.current=affs; },[affs]);
  useEffect(()=>{ vpRef.current=vp; },[vp]);

  useEffect(()=>{
    const p=buildPool(affs);
    setCells(Array(FULL_SIZE).fill(null).map(()=>pick(p,null)));
  },[]); // eslint-disable-line

  // Animation tick — preserves bright/dim state on cells it replaces
  useEffect(()=>{
    function tick(){
      if(!frozenRef.current){
        const {rate,interval}=speedRef.current;
        const count=Math.max(1,Math.round(FULL_SIZE*rate));
        const pool=poolRef.current, lock=lockGrid.current;
        setCells(prev=>{
          const next=[...prev];
          for(let i=0;i<count;i++){
            const idx=Math.floor(Math.random()*FULL_SIZE);
            if(!lock[idx]) next[idx]=pick(pool, prev[idx]); // prev passed to preserve glow
          }
          return next;
        });
      }
      animTimer.current=setTimeout(tick, speedRef.current.interval);
    }
    animTimer.current=setTimeout(tick,200);
    return ()=>clearTimeout(animTimer.current);
  },[]);

  // Viewport sequence runner
  const runSeq = useRef(null);
  runSeq.current = (steps) => {
    if(vpRunning.current) return;
    vpRunning.current=true;
    let idx=0;
    function next(){
      if(idx>=steps.length){
        transRef.current=0;
        setVp(prev=>{
          const s=wrapVp(prev.vx,prev.vy);
          setTimeout(()=>{ transRef.current=550; vpRunning.current=false; },60);
          return s;
        });
        return;
      }
      const step=steps[idx++];
      transRef.current=step.tms;
      setVp(prev=>({vx:prev.vx+step.dx,vy:prev.vy+step.dy}));
      seqTimer.current=setTimeout(next,step.ms);
    }
    next();
  };

  // Viewport pattern trigger — 500ms
  useEffect(()=>{
    const id=setInterval(()=>{
      if(vpRunning.current) return;
      const a=affsRef.current;
      for(const k of KEYS){
        const aff=a[k]||0; if(aff<.1)continue;
        const sp=VP[k];
        if(sp&&Math.random()<sp.prob*(aff/.8)){ runSeq.current(sp.make()); return; }
      }
      const top=KEYS.map(k=>({k,v:a[k]||0})).sort((x,y)=>y.v-x.v)[0]?.k;
      if(Math.random()<(BASE_PAN[top]||.02)){
        const d=PAN_DIRS[Math.floor(Math.random()*4)];
        runSeq.current([{...d,ms:500,tms:550}]);
      }
    },500);
    return ()=>clearInterval(id);
  },[]);

  // Cell effect trigger — 600ms
  // KEY FIX: only fires when vpRunning is false, ensuring vpRef.current
  // matches the actual visual viewport position (not a mid-animation value).
  useEffect(()=>{
    const id=setInterval(()=>{
      if(vpRunning.current) return;            // wait for viewport to settle
      if(Date.now()-lastCellFx.current<4200) return;
      const a=affsRef.current;
      for(const k of KEYS){
        const aff=a[k]||0; if(aff<.1)continue;
        const fx=CELL_FX[k];
        if(fx&&Math.random()<fx.prob*(aff/.8)){
          lastCellFx.current=Date.now();
          fx.run(vpRef.current,setCells,lockGrid,frozenRef,poolRef.current);
          return;
        }
      }
    },600);
    return ()=>clearInterval(id);
  },[]);

  const setAff=(k,v)=>setAffs(p=>({...p,[k]:parseFloat(v)}));
  const applyPreset=p=>{ const a=emptyAffs(); Object.entries(p.affs).forEach(([k,v])=>{a[k]=v;}); setAffs(a); };

  const aura=getAura(affs);
  const topDomains=KEYS.map(k=>({k,v:affs[k]||0})).filter(d=>d.v>=.1).sort((a,b)=>b.v-a.v);
  const tiledCells=useMemo(()=>Array.from(TILE_TO_VIRT,vi=>cells[vi]),[cells]);

  return (
    <div style={{minHeight:"100vh",background:"#04080d",color:"#aaa",display:"flex",flexDirection:"column",alignItems:"center",justifyContent:"center",padding:"2rem 1rem",gap:"1.5rem",fontFamily:'"Courier New",Courier,monospace',fontSize:"16px"}}>

      <div style={{textAlign:"center"}}>
        <div style={{fontSize:".65rem",letterSpacing:".4em",color:"#555",marginBottom:".25rem"}}>LUMINARY PRESENCE VISUALIZER</div>
        <div style={{fontSize:".55rem",letterSpacing:".2em",color:"#2a2a2a"}}>7×9 WINDOW · 15×19 FIELD · ALL EFFECTS</div>
      </div>

      <div style={{display:"flex",gap:"2.5rem",alignItems:"flex-start",flexWrap:"wrap",justifyContent:"center"}}>

        {/* Profile picture */}
        <div style={{display:"flex",flexDirection:"column",alignItems:"center",gap:".75rem"}}>
          <div style={{border:`1px solid ${aura}55`,boxShadow:`0 0 24px ${aura}35,0 0 60px ${aura}18,inset 0 0 16px #00000090`,padding:".5rem",background:"#070c12",position:"relative"}}>
            {["╔","╗","╚","╝"].map((c,i)=>(
              <span key={i} style={{position:"absolute",color:aura+"88",fontSize:".65rem",...[{top:2,left:2},{top:2,right:2},{bottom:2,left:2},{bottom:2,right:2}][i]}}>{c}</span>
            ))}
            <div style={{width:`${VIEW_W}ch`,height:`calc(${VIEW_H} * ${LH}em)`,overflow:"hidden",position:"relative"}}>
              <div style={{
                position:"absolute",top:0,left:0,
                display:"grid",gridTemplateColumns:`repeat(${TILE_W}, 1ch)`,
                lineHeight:LH,fontSize:"1rem",width:`${TILE_W}ch`,
                transition:`transform ${transRef.current}ms cubic-bezier(.4,0,.2,1)`,
                transform:`translate(calc(${-vp.vx} * 1ch),calc(${-vp.vy} * ${LH}em))`,
              }}>
                {tiledCells.map((cell,i)=>{
                  const bright=cell?.bright, dim=cell?.dim;
                  return (
                    <span key={i} style={{
                      display:"inline-block",width:"1ch",textAlign:"center",
                      // Bright: near-white with intense glow; Dim: very dark, no glow
                      color: bright?"#ffffff" : dim?"#1e1e2a" : cell.color,
                      textShadow: bright
                        ? `0 0 6px #fff, 0 0 14px ${cell.color}, 0 0 22px ${cell.color}`
                        : (dim||!cell?.char?.trim()) ? "none"
                        : `0 0 6px ${cell.color}bb`,
                    }}>
                      {cell?.char||" "}
                    </span>
                  );
                })}
              </div>
            </div>
          </div>

          <div style={{display:"flex",flexWrap:"wrap",gap:".4rem",justifyContent:"center",maxWidth:`${VIEW_W*1.4}rem`}}>
            {!topDomains.length&&<span style={{fontSize:".6rem",color:"#333",letterSpacing:".15em"}}>NO DOMAIN AFFINITY</span>}
            {topDomains.map(({k,v})=>(
              <span key={k} style={{fontSize:".6rem",color:DOMAINS[k].color,letterSpacing:".08em",opacity:.45+v*.55,border:`1px solid ${DOMAINS[k].color}33`,padding:".1rem .35rem"}}>
                {DOMAINS[k].symbol} {DOMAINS[k].label} {(v*100).toFixed(0)}%
              </span>
            ))}
          </div>

          <div style={{display:"flex",gap:".4rem",flexWrap:"wrap",justifyContent:"center"}}>
            {PRESETS.map(p=>(
              <button key={p.name} onClick={()=>applyPreset(p)} style={{background:"transparent",border:"1px solid #2a3a4a",color:"#556",fontSize:".6rem",padding:".2rem .5rem",cursor:"pointer",letterSpacing:".1em",fontFamily:"inherit"}}
                onMouseEnter={e=>{e.target.style.borderColor="#4a6a8a";e.target.style.color="#8ab";}}
                onMouseLeave={e=>{e.target.style.borderColor="#2a3a4a";e.target.style.color="#556";}}
              >{p.name}</button>
            ))}
          </div>
        </div>

        {/* Sliders */}
        <div style={{display:"grid",gridTemplateColumns:"1fr 1fr",gap:".55rem 1.8rem",minWidth:"300px"}}>
          {KEYS.map(k=>{
            const{label,symbol,color}=DOMAINS[k]; const val=affs[k]||0; const active=val>=.1;
            return (
              <div key={k}>
                <div style={{display:"flex",justifyContent:"space-between",marginBottom:"2px"}}>
                  <span style={{fontSize:".68rem",color:active?color:"#353535",letterSpacing:".05em",transition:"color .3s"}}>{symbol} {label}</span>
                  <span style={{fontSize:".62rem",color:active?color+"bb":"#2a2a2a",transition:"color .3s"}}>{val.toFixed(2)}</span>
                </div>
                <input type="range" min="0" max="0.8" step="0.05" value={val}
                  onChange={e=>setAff(k,e.target.value)}
                  style={{width:"100%",height:"2px",accentColor:color,cursor:"pointer",background:`linear-gradient(to right,${color}88 0%,${color}88 ${(val/.8)*100}%,#1a2430 ${(val/.8)*100}%)`}}
                />
              </div>
            );
          })}
        </div>
      </div>

      <div style={{fontSize:".5rem",color:"#1e1e1e",letterSpacing:".12em",textAlign:"center",maxWidth:"580px",lineHeight:"2"}}>
        VIEWPORT · WATER↑ · FIRE↓ · CHANGE DARTS · CONFLICT SHAKES · ORDER CIRCLES (CW OR CCW)
        <br/>
        CELL · MEMORY SKIPS · DECAY FALLS · SACRIFICE RISES · GROWTH SCROLLS · TRUTH FREEZES · VOID SPLITS · SILENCE WIPES · LIGHT BLOOMS · SECRECY DIMS
      </div>
    </div>
  );
}
