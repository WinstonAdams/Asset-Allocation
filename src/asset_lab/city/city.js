// 等角城市 Components v2 前端。只負責繪圖、動畫、命中測試與名稱牌降級：
// 所有業務判斷與顯示文字由 Python payload 決定，幾何常數由 Python 以 GEOM 前置注入。
// 公式（投影、障礙物、名稱牌位置、旗桿外框）與 city/geometry.py 各一份，函式名稱對照見該檔 docstring。
// 不使用任何會解析標記的 API；文字一律 textContent 或 canvas fillText。
const INSTANCES = new WeakMap()
let mountSeq = 0

const hash = (...n) => { let x = 2166136261; for (const v of n) { x ^= v; x = Math.imul(x, 16777619) >>> 0 } return x }
const strHash = s => { let x = 0; for (let k = 0; k < s.length; k++) x = (x * 31 + s.charCodeAt(k)) >>> 0; return x }
const rgb = h => { h = h.replace('#', ''); const n = parseInt(h, 16); return [(n >> 16) & 255, (n >> 8) & 255, n & 255] }
const mix = (a, b, t) => { const A = rgb(a), B = rgb(b); return '#' + A.map((v, i) => Math.round(v + (B[i] - v) * t).toString(16).padStart(2, '0')).join('') }
const shade = (c, amt) => (amt >= 0 ? mix(c, '#ffffff', amt) : mix(c, '#000000', -amt))

// 天氣畫法：以 payload 的 weather.sky 查表；calm（資料不足）只畫天空漸層
const SKIES = {
  clear: { tint: 0, clouds: 2, dim: 0, rain: 0, slant: 0, stars: true, storm: false, flash: false },
  cloudy: { tint: 0.38, clouds: 5, dim: 0.05, rain: 0, slant: 0, stars: true, storm: false, flash: false },
  rain: { tint: 0.62, clouds: 8, dim: 0.14, rain: 150, slant: 0.12, stars: false, storm: true, flash: false },
  typhoon: { tint: 0.78, clouds: 10, dim: 0.22, rain: 260, slant: 0.35, stars: false, storm: true, flash: true },
  calm: { tint: 0, clouds: 0, dim: 0, rain: 0, slant: 0, stars: false, storm: false, flash: false },
}
const NO_SKY = SKIES.calm

function createInstance(root) {
  const canvas = root.querySelector('#city')
  const wrap = root.querySelector('#wrap')
  const tip = root.querySelector('#tip')
  const legend = root.querySelector('#legend')
  const ctx = canvas.getContext('2d')
  const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
  const themeQuery = window.matchMedia('(prefers-color-scheme: dark)')
  const inst = {
    id: ++mountSeq, canvas, runs: 0,
    D: null, items: [], byId: new Map(), sel: null, hover: null, TK: {}, cb: {},
    curH: {}, tgtH: {}, curSite: 0, tgtSite: 0, rm: motionQuery.matches,
    W: 0, H: 0, sc: 1, ox: 0, oy: 0, hits: [], raf: 0, trees: [], treesShown: [], layoutSig: '',
    placed: [], numbers: {}, groundKey: '', groundCv: null, layoutKey: '', dataVer: 0, cc: null, tiles: [],
  }

  // ---------- 色彩：主題色讀 --st-*，區域色票為元件自有 ----------
  function toHex(color, fallback) {
    const c = document.createElement('canvas'); c.width = c.height = 1
    const x = c.getContext('2d', { willReadFrequently: true })
    x.fillStyle = '#000'; x.fillStyle = color || fallback
    x.fillRect(0, 0, 1, 1)
    const d = x.getImageData(0, 0, 1, 1).data
    return '#' + [d[0], d[1], d[2]].map(v => v.toString(16).padStart(2, '0')).join('')
  }
  function readTokens() {
    const cs = getComputedStyle(wrap)
    const g = n => cs.getPropertyValue(n).trim()
    const bg = toHex(g('--st-background-color'), '#ffffff')
    const [r, gg, b] = rgb(bg)
    const night = (0.299 * r + 0.587 * gg + 0.114 * b) < 128   // 以 Streamlit 背景亮度判斷淺色或深色
    const panel = toHex(g('--st-secondary-background-color'), '#f0f2f6')
    const ink = toHex(g('--st-text-color'), '#1c2620')
    root.querySelector('.city').dataset.night = night ? '1' : '0'
    const z = n => toHex(getComputedStyle(wrap).getPropertyValue(n).trim(), '#888888')
    inst.TK = {
      night, panel, ink, accent: toHex(g('--st-primary-color'), '#d8641f'),
      skyA: z('--sky-a'), skyB: z('--sky-b'), grass: z('--grass'), grass2: z('--grass-2'), soil: z('--soil'),
      road: z('--road'), roadLine: z('--road-line'), tree: z('--tree'), window: z('--window'), windowLit: z('--window-lit'),
      good: z('--good'), warn: z('--warn'), bad: z('--bad'),
      zone: { cash: z('--z-cash'), deposit: z('--z-deposit'), stock: z('--z-stock'), ins: z('--z-ins'), debt: z('--z-debt'), house: z('--z-house') },
      fontBody: g('--st-font') || 'system-ui, sans-serif',
    }
    inst.layoutKey = ''
  }

  // ---------- 畫布幾何（對應 geometry.fit_scale）：整塊地盤寬塞進畫布寬，畫布高等於內容高 ----------
  function resize() {
    const cw = wrap.clientWidth; if (!cw || !inst.D) return
    const [gi, gj] = inst.D.ground
    inst.sc = Math.min(GEOM.sc_max, (cw - 2 * GEOM.side_m) / ((gi + gj) * GEOM.ux))
    inst.W = cw
    inst.ox = cw / 2 - (gi - gj) * GEOM.ux * inst.sc / 2
    inst.oy = GEOM.top_m + (cw < GEOM.narrow_w ? GEOM.overlay_h : 0) + inst.D.top_pad * inst.sc   // 窄畫布頂端留一條給天氣面板
    inst.H = Math.ceil(inst.oy + (gi + gj) * GEOM.vy * inst.sc + GEOM.soil * inst.sc + GEOM.bot_m)
    const dpr = Math.min(2, window.devicePixelRatio || 1)
    canvas.width = Math.round(inst.W * dpr); canvas.height = Math.round(inst.H * dpr); canvas.style.height = inst.H + 'px'
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    inst.dpr = dpr
    if (inst.rm) draw(performance.now())
  }
  // 對應 geometry.project（加上畫布原點偏移）
  const P = (i, j) => [inst.ox + (i - j) * GEOM.ux * inst.sc, inst.oy + (i + j) * GEOM.vy * inst.sc]
  const up = (p, h) => [p[0], p[1] - h]
  const lerp = (a, b, t) => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
  function path(pts, c) { c = c || ctx; c.beginPath(); c.moveTo(pts[0][0], pts[0][1]); for (let k = 1; k < pts.length; k++) c.lineTo(pts[k][0], pts[k][1]); c.closePath() }
  function poly(pts, fill, stroke, lw, c) { c = c || ctx; path(pts, c); if (fill) { c.fillStyle = fill; c.fill() } if (stroke) { c.strokeStyle = stroke; c.lineWidth = lw || 1; c.stroke() } }
  function inPoly(x, y, pts) { let c = false; for (let i = 0, j = pts.length - 1; i < pts.length; j = i++) { const [xi, yi] = pts[i], [xj, yj] = pts[j]; if (((yi > y) !== (yj > y)) && (x < (xj - xi) * (y - yi) / (yj - yi) + xi)) c = !c } return c }
  const footprint = (lot, a) => { const [i, j, w, d] = lot; return [P(i + a, j + a), P(i + w - a, j + a), P(i + w - a, j + d - a), P(i + a, j + d - a)] }

  // ---------- 項目：把 payload 的建築與工地整理成同一種結構 ----------
  function buildItems(D) {
    const items = D.buildings.map(b => ({
      id: b.id, name: b.name, zone: b.zone, shape: b.shape, kind: b.kind, lot: b.lot, plate: b.plate,
      sub: b.sub, tip: b.tip, mode: b.plate_mode, vacant: b.vacant, value: b.value, warn: b.warn, site: false,
    }))
    const s = D.site
    items.push({
      id: s.id, name: s.name, zone: 'house', shape: 'site', kind: 'site', lot: s.lot, plate: s.plate,
      sub: s.sub, tip: s.tip, mode: 'normal', vacant: false, value: -1, warn: false, site: true,
    })
    return items
  }
  // 高度與深度（對應 geometry.asset_height、geometry.pit_depth）；空地目標為 0
  function targetOf(it) {
    const D = inst.D
    if (it.site) return 0
    if (it.vacant) return 0
    if (it.shape === 'pit') {
      if (D.max_liab <= 0) return GEOM.pit_min_depth
      return Math.max(GEOM.pit_min_depth, GEOM.pit_max_depth * Math.sqrt(Math.max(it.value, 0) / D.max_liab))
    }
    if (D.max_asset <= 0) return GEOM.h_min
    return Math.max(GEOM.h_min, GEOM.h_top * Math.sqrt(Math.max(it.value, 0) / D.max_asset))
  }

  // ---------- 地盤：整塊 [0,gi)x[0,gj)；街廓與道路皆由 Python 給 ----------
  function rebuildLayout() {
    const D = inst.D
    const sig = JSON.stringify([inst.items.map(b => [b.id, b.lot]), D.ground, D.roads, D.blocks])
    if (sig === inst.layoutSig) return false
    inst.layoutSig = sig
    const [gi, gj] = D.ground
    const occupied = new Set(), zoneAt = new Map(), roadAt = new Map()
    inst.items.forEach(({ lot: [i, j, w, d] }) => { for (let a = i; a < i + w; a++) for (let b = j; b < j + d; b++) occupied.add(a + ',' + b) })
    D.blocks.forEach(([z, i0, i1, j0, j1]) => { for (let i = i0; i < i1; i++) for (let j = j0; j < j1; j++) zoneAt.set(i + ',' + j, z) })
    D.roads.forEach(([i0, i1, j0, j1, k]) => { for (let i = i0; i < i1; i++) for (let j = j0; j < j1; j++) { const key = i + ',' + j, was = roadAt.get(key); roadAt.set(key, was && was !== k ? 'x' : k) } })
    inst.tiles = []
    for (let i = 0; i < gi; i++) for (let j = 0; j < gj; j++) { const key = i + ',' + j; inst.tiles.push([i, j, zoneAt.get(key) || null, roadAt.get(key) || null]) }
    inst.trees = []
    inst.tiles.forEach(([i, j, z, r]) => { if (r || occupied.has(i + ',' + j)) return; if (hash(i, j, 7) % (z ? 6 : 4) === 0) inst.trees.push([i, j, 0.7 + (hash(i, j, 3) % 5) / 10]) })
    inst.groundKey = ''
    return true
  }
  // 靜態地面畫到離屏畫布（瓦片可能上千塊，不必每格每幀重畫）
  function groundLayer() {
    const { TK, W, H, sc, D } = inst, key = [W, H, sc, inst.dpr, TK.night, inst.layoutSig, TK.grass, TK.road].join('|')
    if (key === inst.groundKey && inst.groundCv) return inst.groundCv
    const cv = inst.groundCv || document.createElement('canvas'), dpr = inst.dpr || 1
    cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr)
    const c = cv.getContext('2d'); c.setTransform(dpr, 0, 0, dpr, 0, 0); c.clearRect(0, 0, W, H)
    const [gi, gj] = D.ground, thick = GEOM.soil * sc
    // 底座側面（立體模型感）：左前、右前兩面
    const c0 = P(0, gj), c1 = P(gi, gj), c2 = P(gi, 0)
    poly([c0, c1, [c1[0], c1[1] + thick], [c0[0], c0[1] + thick]], shade(TK.soil, 0.05), null, 1, c)
    poly([c1, c2, [c2[0], c2[1] + thick], [c1[0], c1[1] + thick]], shade(TK.soil, -0.15), null, 1, c)
    c.lineWidth = 1
    const roadCol = TK.night ? TK.road : mix(TK.road, '#7d8288', 0.18)
    inst.tiles.forEach(([i, j, z, r]) => {
      const base = (i + j) % 2 ? TK.grass : TK.grass2
      const fill = r ? roadCol : z ? mix(base, TK.zone[z], TK.night ? 0.16 : 0.22) : base
      // 道路不畫格線，連成一整條街；草地保留格線
      poly([P(i, j), P(i + 1, j), P(i + 1, j + 1), P(i, j + 1)], fill, r ? fill : mix(fill, '#000000', 0.07), 1, c)
    })
    // 道路中線（寬 2 格的大道；交叉口不畫）
    c.strokeStyle = TK.roadLine; c.lineWidth = Math.max(1, 1.6 * sc)
    const isX = (i, j) => { const t = inst.tiles[i * gj + j]; return t && t[3] === 'x' }
    D.roads.forEach(([i0, i1, j0, j1, k]) => {
      if (k === 'j' && i1 - i0 === 2) for (let j = j0; j < j1; j++) { if (isX(i0, j)) continue; const a = P(i0 + 1, j + 0.2), b = P(i0 + 1, j + 0.8); c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke() }
      if (k === 'i' && j1 - j0 === 2) for (let i = i0; i < i1; i++) { if (isX(i, j0)) continue; const a = P(i + 0.2, j0 + 1), b = P(i + 0.8, j0 + 1); c.beginPath(); c.moveTo(a[0], a[1]); c.lineTo(b[0], b[1]); c.stroke() }
    })
    poly(footprint(D.site.lot, 0.08), mix(TK.soil, TK.grass, 0.25), mix(TK.soil, '#000000', 0.2), 1, c)
    inst.groundKey = key; inst.groundCv = cv
    return cv
  }

  const DROPS = Array.from({ length: 260 }, (_, k) => ({ x: (hash(k, 1) % 1000) / 1000, y: (hash(k, 2) % 1000) / 1000, l: 0.6 + (hash(k, 3) % 40) / 100, s: 0.7 + (hash(k, 4) % 60) / 100 }))
  const CLOUDS = Array.from({ length: 10 }, (_, k) => ({ x: (hash(k, 11) % 1000) / 1000, y: 0.04 + (hash(k, 12) % 180) / 1000, r: 0.7 + (hash(k, 13) % 60) / 100, s: 0.4 + (hash(k, 14) % 50) / 100 }))
  const STARS = Array.from({ length: 46 }, (_, k) => ({ x: (hash(k, 21) % 1000) / 1000, y: (hash(k, 22) % 300) / 1000, r: (hash(k, 23) % 3) / 2 + 0.6 }))

  function draw(t) {
    const { TK, W, H, sc, D } = inst
    if (!D || !W) return
    const sky = SKIES[D.weather.sky] || NO_SKY, night = TK.night, rm = inst.rm
    ctx.clearRect(0, 0, W, H)
    const grey = night ? '#141b26' : '#87929b'
    const g = ctx.createLinearGradient(0, 0, 0, H)
    g.addColorStop(0, mix(TK.skyA, grey, sky.tint)); g.addColorStop(1, mix(TK.skyB, grey, sky.tint * 0.8))
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H)
    if (night && sky.stars) { ctx.fillStyle = mix(TK.windowLit, '#ffffff', 0.5); STARS.forEach(s => { ctx.globalAlpha = 0.35 + 0.4 * ((Math.sin(t / 900 + s.x * 40) + 1) / 2) * (rm ? 0 : 1); ctx.beginPath(); ctx.arc(s.x * W, s.y * H, s.r * sc, 0, 7); ctx.fill() }); ctx.globalAlpha = 1 }
    const cloudCol = sky.storm ? mix(night ? '#2a3340' : '#ffffff', '#4b545e', 0.55) : (night ? mix(TK.skyB, '#ffffff', 0.1) : '#ffffff')
    for (let k = 0; k < sky.clouds; k++) { const c = CLOUDS[k]; const x = ((c.x * (W + 300) + (rm ? 0 : t * 0.008 * c.s * sc)) % (W + 300)) - 150; const y = c.y * H; const r = 34 * c.r * Math.max(sc, 0.5)
      ctx.globalAlpha = sky.storm ? 0.92 : 0.8; ctx.fillStyle = cloudCol; ctx.beginPath(); ctx.ellipse(x, y, r * 1.6, r * 0.62, 0, 0, 7); ctx.ellipse(x + r * 0.9, y - r * 0.3, r * 1.1, r * 0.6, 0, 0, 7); ctx.ellipse(x - r * 0.9, y - r * 0.15, r, r * 0.5, 0, 0, 7); ctx.fill() }
    ctx.globalAlpha = 1

    ctx.drawImage(groundLayer(), 0, 0, W, H)
    // 名稱牌位置先算（樹避開名稱牌，名稱帶保持乾淨）
    const key = [inst.W, inst.H, inst.sel, inst.hover, inst.TK.night, inst.dataVer, inst.TK.fontBody].join('|')
    if (key !== inst.layoutKey) { inst.layoutKey = key; computeLayout(); inst.cc = labelColors() }

    inst.hits = []
    const shown = it => !it.site && inst.curH[it.id] > 0.5
    inst.items.filter(it => it.shape === 'pit' && shown(it)).forEach(drawPit)
    inst.items.filter(it => it.vacant && !shown(it) && it.mode === 'faded').forEach(drawVacant)
    const objs = []
    inst.items.forEach(it => {
      const [i, j, w, d] = it.lot, depth = i + w / 2 + j + d / 2
      if (it.site) objs.push({ d: depth, fn: () => drawSite(it) })
      else if (it.shape !== 'pit' && shown(it)) objs.push({ d: depth, fn: () => drawBuilding(it) })
    })
    inst.treesShown.forEach(([i, j, s]) => objs.push({ d: i + j + 1, fn: () => drawTree(i, j, s) }))
    objs.sort((a, b) => a.d - b.d).forEach(o => o.fn())
    drawFlags(t)

    const dim = sky.dim * (night ? 0.6 : 1)
    if (dim) { ctx.fillStyle = 'rgba(10,14,22,' + dim + ')'; ctx.fillRect(0, 0, W, H) }
    if (sky.rain) {
      ctx.strokeStyle = mix(TK.window, '#ffffff', 0.35); ctx.globalAlpha = night ? 0.45 : 0.55; ctx.lineWidth = Math.max(1, 1.1 * sc); ctx.beginPath()
      for (let k = 0; k < sky.rain; k++) { const d = DROPS[k]; const y = ((d.y * H) + (rm ? 0 : t * 0.55 * d.s)) % (H + 40) - 20; const x = ((d.x * W) + (rm ? 0 : t * 0.55 * d.s * sky.slant)) % W; const L = 16 * d.l * sc; ctx.moveTo(x, y); ctx.lineTo(x - L * sky.slant, y + L) }
      ctx.stroke(); ctx.globalAlpha = 1
    }
    if (sky.flash && !rm && (t % 5200) < 110) { ctx.fillStyle = 'rgba(255,255,255,0.28)'; ctx.fillRect(0, 0, W, H) }
    drawLabels()
  }

  function windowsOn(p0, p1, hpx, cols, col, id, side, dark) {
    const { sc, TK } = inst
    const fh = 10 * sc; const floors = Math.floor((hpx - 7 * sc) / fh); if (floors < 1 || sc < 0.3) return
    const seed = strHash(id)
    for (let f = 0; f < floors; f++) for (let k = 0; k < cols; k++) {
      const t0 = (k + 0.24) / cols, t1 = (k + 0.76) / cols, v0 = 5 * sc + f * fh + fh * 0.22, v1 = v0 + fh * 0.5
      const lit = TK.night && hash(seed, f, k, side) % 5 < 3
      const fill = lit ? TK.windowLit : mix(TK.window, col, dark ? 0.45 : 0.25)
      poly([up(lerp(p0, p1, t0), v0), up(lerp(p0, p1, t1), v0), up(lerp(p0, p1, t1), v1), up(lerp(p0, p1, t0), v1)], fill)
    }
  }
  function drawBuilding(h) {
    const { sc, TK } = inst
    const [i, j, w, d] = h.lot, pad = GEOM.pad, hp = inst.curH[h.id] * sc
    const a = P(i + pad, j + pad), b = P(i + w - pad, j + pad), c = P(i + w - pad, j + d - pad), e = P(i + pad, j + d - pad)
    const col = TK.zone[h.zone]
    ctx.globalAlpha = 0.18; poly([c, b, [b[0] + 10 * sc, b[1] + 5 * sc], [c[0] + 10 * sc, c[1] + 5 * sc]], '#000000'); ctx.globalAlpha = 1
    const L = [e, c, up(c, hp), up(e, hp)], Rf = [c, b, up(b, hp), up(c, hp)], Top = [up(a, hp), up(b, hp), up(c, hp), up(e, hp)]
    poly(L, shade(col, -0.08)); poly(Rf, shade(col, -0.28)); poly(Top, shade(col, 0.2))
    const cols = Math.max(2, Math.round(w * 3))
    if (h.shape === 'tower') {
      windowsOn(e, c, hp, cols, col, h.id, 0, false); windowsOn(c, b, hp, cols, col, h.id, 1, true)
      const inset = [lerp(up(a, hp), up(c, hp), 0.18), lerp(up(b, hp), up(e, hp), 0.18), lerp(up(c, hp), up(a, hp), 0.18), lerp(up(e, hp), up(b, hp), 0.18)]
      poly(inset, shade(col, 0.05))
    } else if (h.shape === 'tank') {
      ctx.strokeStyle = shade(col, -0.32); ctx.lineWidth = Math.max(1, sc); ctx.globalAlpha = 0.5
      for (let v = 12 * sc; v < hp - 4 * sc; v += 12 * sc) { ctx.beginPath(); const l0 = up(e, v), l1 = up(c, v), r1 = up(b, v); ctx.moveTo(l0[0], l0[1]); ctx.lineTo(l1[0], l1[1]); ctx.lineTo(r1[0], r1[1]); ctx.stroke() }
      ctx.globalAlpha = 1
      const water = [lerp(up(a, hp), up(c, hp), 0.12), lerp(up(b, hp), up(e, hp), 0.12), lerp(up(c, hp), up(a, hp), 0.12), lerp(up(e, hp), up(b, hp), 0.12)]
      poly(water, mix(col, '#ffffff', TK.night ? 0.25 : 0.5))
    } else if (h.shape === 'silo') {
      ctx.strokeStyle = shade(col, -0.35); ctx.lineWidth = Math.max(1, sc); ctx.globalAlpha = 0.55
      for (let v = 8 * sc; v < hp; v += 8 * sc) { ctx.beginPath(); const l0 = up(e, v), l1 = up(c, v), r1 = up(b, v); ctx.moveTo(l0[0], l0[1]); ctx.lineTo(l1[0], l1[1]); ctx.lineTo(r1[0], r1[1]); ctx.stroke() }
      ctx.globalAlpha = 1
      const apex = up(lerp(a, c, 0.5), hp + GEOM.silo_roof * sc)
      poly([up(e, hp), up(c, hp), apex], shade(col, -0.18)); poly([up(c, hp), up(b, hp), apex], shade(col, -0.38))
    } else if (h.shape === 'station') {
      windowsOn(e, c, Math.min(hp, 22 * sc), cols, col, h.id, 0, false)
      const band = 6 * sc; poly([up(e, hp - band), up(c, hp - band), up(c, hp), up(e, hp)], shade(col, 0.55)); poly([up(c, hp - band), up(b, hp - band), up(b, hp), up(c, hp)], shade(col, 0.35))
      const m = up(lerp(e, c, 0.5), hp * 0.55), s = 6 * sc
      ctx.fillStyle = TK.night ? TK.windowLit : '#ffffff'; ctx.fillRect(m[0] - s * 0.3, m[1] - s, s * 0.6, s * 2); ctx.fillRect(m[0] - s, m[1] - s * 0.3, s * 2, s * 0.6)
    }
    poly([up(a, hp), up(b, hp), b, c, e, up(e, hp)], null, shade(col, -0.45), 1)
    const hull = [up(a, hp), up(b, hp), b, c, e, up(e, hp)]
    if (inst.sel === h.id || inst.hover === h.id) poly(hull, null, TK.accent, inst.sel === h.id ? 2.5 : 1.5)
    if (h.mode !== 'hidden') inst.hits.push({ id: h.id, poly: hull, d: i + w / 2 + j + d / 2 })
  }
  function drawPit(h) {
    const { sc, TK } = inst
    const [a, b, c, e] = footprint(h.lot, GEOM.pit_pad), dp = inst.curH[h.id] * sc
    const col = TK.zone.debt, dn = p => [p[0], p[1] + dp]
    ctx.save(); path([a, b, c, e]); ctx.clip()
    poly([a, b, c, e], shade(col, -0.6))
    poly([a, b, dn(b), dn(a)], shade(col, -0.25)); poly([e, a, dn(a), dn(e)], shade(col, -0.42)); poly([dn(a), dn(b), dn(c), dn(e)], shade(col, -0.65))
    ctx.restore()
    ctx.setLineDash([4 * sc, 3 * sc]); poly([a, b, c, e], null, TK.warn, Math.max(1.2, 2 * sc)); ctx.setLineDash([])
    if (inst.sel === h.id || inst.hover === h.id) poly([a, b, c, e], null, TK.accent, inst.sel === h.id ? 2.5 : 1.5)
    if (h.mode !== 'hidden') inst.hits.push({ id: h.id, poly: [a, b, c, e], d: -1 })
  }
  // 空地：只畫地塊虛線外框；名稱牌淡化的空地可點，留空的月份不畫也不可點
  function drawVacant(h) {
    const { sc, TK } = inst
    const quad = footprint(h.lot, GEOM.pad)
    ctx.setLineDash([4 * sc, 3 * sc]); ctx.globalAlpha = 0.7
    poly(quad, null, TK.zone[h.zone], Math.max(1, 1.5 * sc)); ctx.globalAlpha = 1; ctx.setLineDash([])
    if (inst.sel === h.id || inst.hover === h.id) poly(quad, null, TK.accent, inst.sel === h.id ? 2.5 : 1.5)
    const [i, j, w, d] = h.lot
    inst.hits.push({ id: h.id, poly: footprint(h.lot, 0), d: i + w / 2 + j + d / 2 - 1000 })
  }
  function drawTree(i, j, s) {
    const { sc, TK } = inst
    const c = P(i + 0.5, j + 0.5), k = s * sc
    ctx.strokeStyle = mix(TK.soil, '#000000', 0.2); ctx.lineWidth = Math.max(1, 2 * k); ctx.beginPath(); ctx.moveTo(c[0], c[1]); ctx.lineTo(c[0], c[1] - 8 * k); ctx.stroke()
    ctx.fillStyle = TK.tree; ctx.beginPath(); ctx.arc(c[0], c[1] - 14 * k, 8 * k, 0, 7); ctx.fill()
    ctx.fillStyle = shade(TK.tree, 0.18); ctx.beginPath(); ctx.arc(c[0] - 2.5 * k, c[1] - 16.5 * k, 4 * k, 0, 7); ctx.fill()
  }
  function drawSite(it) {
    const { sc, TK } = inst
    const [i, j, w, d] = it.lot, col = TK.zone.house
    const [a, b, c, e] = footprint(it.lot, 0.5)
    const full = GEOM.house_full * sc, hp = full * inst.curSite
    if (hp > 1) { poly([e, c, up(c, hp), up(e, hp)], mix(col, TK.panel, 0.35)); poly([c, b, up(b, hp), up(c, hp)], mix(col, '#000000', 0.15)); poly([up(a, hp), up(b, hp), up(c, hp), up(e, hp)], mix(col, TK.panel, 0.55)) }
    ctx.setLineDash([3 * sc, 3 * sc]); ctx.strokeStyle = col; ctx.lineWidth = Math.max(1, 1.3 * sc)
    ;[a, b, c, e].forEach(p => { ctx.beginPath(); ctx.moveTo(p[0], p[1]); ctx.lineTo(p[0], p[1] - full); ctx.stroke() })
    path([up(a, full), up(b, full), up(c, full), up(e, full)]); ctx.stroke()
    const apex = up(lerp(a, c, 0.5), full + GEOM.house_roof * sc); [a, b, c, e].forEach(p => { const q = up(p, full); ctx.beginPath(); ctx.moveTo(q[0], q[1]); ctx.lineTo(apex[0], apex[1]); ctx.stroke() })
    ctx.setLineDash([])
    const base = P(i + w - 0.15, j + 0.25), top = up(base, GEOM.crane_h * sc)
    ctx.strokeStyle = col; ctx.lineWidth = Math.max(1.5, 3 * sc); ctx.beginPath(); ctx.moveTo(base[0], base[1]); ctx.lineTo(top[0], top[1]); ctx.lineTo(top[0] - GEOM.crane_l * sc, top[1] + 6 * sc); ctx.moveTo(top[0], top[1]); ctx.lineTo(top[0] + GEOM.crane_r * sc, top[1] + 2 * sc); ctx.stroke()
    ctx.lineWidth = Math.max(1, 1 * sc); const hookX = top[0] - 70 * sc, hookY = top[1] + 4 * sc; ctx.beginPath(); ctx.moveTo(hookX, hookY); ctx.lineTo(hookX, hookY + (inst.rm ? 40 : 40 + 6 * Math.sin(performance.now() / 700)) * sc); ctx.stroke()
    const hull = [up(P(i, j), full + GEOM.house_roof * sc), up(P(i + w, j), full), P(i + w, j), P(i + w, j + d), P(i, j + d), up(P(i, j + d), full)]
    if (inst.sel === it.id || inst.hover === it.id) poly(footprint(it.lot, 0.08), null, TK.accent, inst.sel === it.id ? 2.5 : 1.5)
    inst.hits.push({ id: it.id, poly: hull, d: i + w / 2 + j + d / 2 })
  }

  // ---------- 旗桿：每個購屋條件一根，達成升旗、未達成降半旗 ----------
  // 旗桿排在工地正前方水平一排，布面往螢幕左上展開，輕微飄動（減少動態時靜止）
  function flagGeom() {
    const { sc, D } = inst, [li, lj, lw, ld] = D.site.lot, fs = Math.max(sc, 0.62)
    return { fs, v: li + lj + lw + ld + 0.2, uc: (li + lw / 2) - (lj + ld / 2), du: GEOM.flag_du, H: GEOM.flag_k * Math.max(40, 72 * sc) }
  }
  // 旗桿列外框（對應 geometry.flag_rect）：名稱牌與其他建築都不可碰
  function flagRect() {
    const { sc } = inst, g = flagGeom()
    const xl = P((g.v + g.uc - 2 * g.du) / 2, (g.v - g.uc + 2 * g.du) / 2)[0], xr = P((g.v + g.uc + 2 * g.du) / 2, (g.v - g.uc - 2 * g.du) / 2)[0]
    const y = inst.oy + g.v * GEOM.vy * sc
    return [xl - GEOM.flag_len * GEOM.ux * sc - 2, y - g.H - GEOM.flag_len * GEOM.vy * sc - 2.6 * g.fs * GEOM.flag_k - 2.4 * g.fs - 2, xr + 8 * g.fs + 1, y + 2 + 2.4 * g.fs]
  }
  function clothPoly(pi, pj, z0, lenI, hgt, t, k, amp, droop) {
    const top = [], bot = [], n = 6
    for (let s = 0; s <= n; s++) {
      const u = s / n, w = inst.rm ? 0 : Math.sin(t / 280 + k * 1.3 + u * 3.2) * amp * u
      const di = lenI * u, z = z0 - droop * u * u
      top.push(up(P(pi - di, pj), z + w)); bot.push(up(P(pi - di, pj), z - hgt * (1 - 0.18 * u) + w))
    }
    return top.concat(bot.reverse())
  }
  function drawFlags(t) {
    const { TK, D } = inst, g = flagGeom(), flags = D.site.flags, n = flags.length
    const pole = TK.night ? mix(TK.soil, '#ffffff', 0.6) : shade(TK.soil, -0.2)
    const lw = Math.max(1.5, 2 * g.fs)
    const at = k => { const u = g.uc + (k - (n - 1) / 2) * g.du; return [(g.v + u) / 2, (g.v - u) / 2] }
    const lenI = GEOM.flag_len, hgt = GEOM.flag_k * Math.max(13, 18 * g.fs), amp = 2.6 * g.fs * GEOM.flag_k
    for (let k = 0; k < n; k++) {
      const [pi, pj] = at(k), b = P(pi, pj), tp = up(b, g.H)
      ctx.fillStyle = 'rgba(0,0,0,0.22)'; ctx.beginPath(); ctx.ellipse(b[0] + 3 * g.fs, b[1] + 1, 5 * g.fs, 2.4 * g.fs, 0, 0, 7); ctx.fill()
      ctx.strokeStyle = pole; ctx.lineWidth = lw; ctx.beginPath(); ctx.moveTo(b[0], b[1]); ctx.lineTo(tp[0], tp[1]); ctx.stroke()
      ctx.fillStyle = TK.night ? '#ffe9a8' : '#e9c46a'; ctx.beginPath(); ctx.arc(tp[0], tp[1] - 1, Math.max(1.8, 2.4 * g.fs), 0, 7); ctx.fill()
      if (flags[k].met) {
        const col = mix(TK.good, '#ffffff', 0.08)
        poly(clothPoly(pi, pj, g.H - 1, lenI, hgt, t, k, amp, 3 * g.fs * GEOM.flag_k), col, shade(col, -0.45), 1.2)
        poly(clothPoly(pi, pj, g.H - 1 - hgt * 0.38, lenI, hgt * 0.24, t, k, amp, 3 * g.fs * GEOM.flag_k), shade(col, 0.28))
      } else {
        const col = mix(TK.road, TK.soil, 0.45)
        poly(clothPoly(pi, pj, g.H * 0.5, lenI * 0.4, hgt * 1.15, t, k, amp * 0.3, 8 * g.fs * GEOM.flag_k), col, shade(col, -0.4), 1.1)
      }
    }
  }

  // ---------- 名稱牌：固定在建築底座前緣正下方，絕不移位 ----------
  // 尺寸（寬、高、名稱各行）由 Python 依字數算好；位置公式對應 geometry.plate_rect。設計寬度下 Python 已保證
  // 全部放得下；畫布較窄（手機）時依優先序（選取、hover、市值大者）逐一放，放不下先改精簡牌，
  // 再不行改編號小牌（名稱列在畫布下方圖例）。畫出來的一律不擋任何建築、工地、吊車、坑洞、旗桿，彼此不重疊。
  const lumOf = hx => { const [r, g, b] = rgb(hx).map(v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4) }); return 0.2126 * r + 0.7152 * g + 0.0722 * b }
  const contrast = (a, b) => { const x = lumOf(a), y = lumOf(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }
  function convexHull(pts) {
    const p = pts.slice().sort((a, b) => a[0] - b[0] || a[1] - b[1]); if (p.length < 3) return p
    const cr = (o, a, b) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    const lo = []; for (const q of p) { while (lo.length >= 2 && cr(lo[lo.length - 2], lo[lo.length - 1], q) <= 0) lo.pop(); lo.push(q) }
    const hi = []; for (let k = p.length - 1; k >= 0; k--) { const q = p[k]; while (hi.length >= 2 && cr(hi[hi.length - 2], hi[hi.length - 1], q) <= 0) hi.pop(); hi.push(q) }
    return lo.slice(0, -1).concat(hi.slice(0, -1))
  }
  const bbOf = ps => { let a = 1e9, b = 1e9, c = -1e9, d = -1e9; ps.forEach(q => { a = Math.min(a, q[0]); b = Math.min(b, q[1]); c = Math.max(c, q[0]); d = Math.max(d, q[1]) }); return [a, b, c, d] }
  const mkObs = pts => { const h = convexHull(pts); return { poly: h, bb: bbOf(h) } }
  function rectHitsPoly(o, r, m) {
    const x0 = r.x - m, y0 = r.y - m, x1 = r.x + r.w + m, y1 = r.y + r.h + m
    if (o.bb[2] < x0 || o.bb[0] > x1 || o.bb[3] < y0 || o.bb[1] > y1) return false
    const rc = [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], pl = o.poly
    for (let i = 0; i < pl.length; i++) {
      const a = pl[i], b = pl[(i + 1) % pl.length], nx = b[1] - a[1], ny = a[0] - b[0]
      let pmin = 1e9, pmax = -1e9, rmin = 1e9, rmax = -1e9
      for (const q of pl) { const d = q[0] * nx + q[1] * ny; if (d < pmin) pmin = d; if (d > pmax) pmax = d }
      for (const q of rc) { const d = q[0] * nx + q[1] * ny; if (d < rmin) rmin = d; if (d > rmax) rmax = d }
      if (pmax < rmin || rmax < pmin) return false
    }
    return true
  }
  // 障礙物（對應 geometry.obstacles）：建築外殼（不含地面陰影）、坑洞、工地外框、吊車桿與吊臂、旗桿列；空地不算
  function obstacles() {
    const { sc } = inst, out = []
    inst.items.forEach(b => {
      if (b.vacant) return
      const [i, j, w, d] = b.lot
      if (b.site) {
        const full = GEOM.house_full * sc
        const cr = P(i + w - 0.15, j + 0.25), crt = up(cr, GEOM.crane_h * sc)
        const fp = [P(i, j), P(i + w, j), P(i + w, j + d), P(i, j + d)]
        out.push(mkObs(fp.concat(fp.map(q => up(q, full)), [up(P(i + w / 2, j + d / 2), full + GEOM.house_roof * sc)])))
        out.push(mkObs([cr, [cr[0] - 3, cr[1]], crt, [crt[0] + 3, crt[1]]]))
        out.push(mkObs([[crt[0] - GEOM.crane_l * sc, crt[1] + 6 * sc], [crt[0] + GEOM.crane_r * sc, crt[1] + 2 * sc], [crt[0] + GEOM.crane_r * sc, crt[1] - 3], [crt[0] - GEOM.crane_l * sc, crt[1] + GEOM.crane_hook * sc]]))
        const f = flagRect(); out.push(mkObs([[f[0], f[1]], [f[2], f[1]], [f[2], f[3]], [f[0], f[3]]]))
        return
      }
      if (b.shape === 'pit') { out.push(mkObs(footprint(b.lot, GEOM.pit_pad))); return }
      const hp = inst.tgtH[b.id] * sc, pad = GEOM.pad
      const a = P(i + pad, j + pad), bb = P(i + w - pad, j + pad), c = P(i + w - pad, j + d - pad), e = P(i + pad, j + d - pad)
      const pts = [up(a, hp), up(bb, hp), bb, c, e, up(e, hp)]
      if (b.shape === 'silo') pts.push(up(P(i + w / 2, j + d / 2), hp + GEOM.silo_roof * sc))
      out.push(mkObs(pts))
    })
    return out
  }
  const rectsHit = (a, b, m) => !(a.x + a.w + m <= b.x || b.x + b.w + m <= a.x || a.y + a.h + m <= b.y || b.y + b.h + m <= a.y)
  function labelColors() {
    const panel = inst.TK.panel
    let name = inst.TK.ink; if (contrast(name, panel) < 4.5) name = contrast('#000000', panel) > contrast('#ffffff', panel) ? '#000000' : '#ffffff'
    let sub = mix(name, panel, 0.2); if (contrast(sub, panel) < 4.5) sub = name
    return { panel, name, sub, border: mix(name, panel, 0.55) }
  }
  // 名稱牌左上角（對應 geometry.plate_rect）
  function plateAt(it, w) {
    const [i, j, lw, ld] = it.lot, pad = it.site ? 0 : it.shape === 'pit' ? GEOM.pit_pad : GEOM.pad
    const cx = P(i + lw / 2, j + ld / 2)[0]
    const y0 = it.site ? flagRect()[3] + 2 : P(i + lw - pad, j + ld - pad)[1] + GEOM.lab_gap
    return { x: cx - w / 2, y: y0 }
  }
  function variantsFor(it) {
    const { pw, ph, lines } = { pw: it.plate.w, ph: it.plate.h, lines: it.plate.lines }, out = []
    const showSub = it.mode === 'normal' && !inst.D.compact && it.sub
    const full = lines.map(t => [t, GEOM.name_px, 600, 'name'])
    if (showSub) full.push([it.sub, GEOM.sub_px, 500, 'sub'])
    const fullH = it.mode === 'faded' ? Math.floor(GEOM.name_px * lines.length + GEOM.line_gap * (lines.length - 1) + 2 * GEOM.pad_y) : ph
    out.push({ lines: full, w: pw, h: fullH })
    // 畫布比設計寬度窄（手機）時的備案：精簡牌（只留名稱），再不行改小字；位置公式不變
    for (const px of inst.D.compact ? [10] : [GEOM.name_px, 10]) {
      ctx.font = `600 ${px}px ${inst.TK.fontBody}`
      const w = Math.ceil(Math.max(...lines.map(t => ctx.measureText(t).width))) + GEOM.pad_l + GEOM.pad_r
      out.push({ lines: lines.map(t => [t, px, 600, 'name']), w: Math.min(w, pw), h: px * lines.length + GEOM.line_gap * (lines.length - 1) + 2 * GEOM.pad_y })
    }
    // 最後備案：編號小牌
    ctx.font = `700 10px ${inst.TK.fontBody}`
    out.push({ badge: true, lines: [[String(inst.numbers[it.id]), 10, 700, 'name']], w: Math.ceil(ctx.measureText(String(inst.numbers[it.id])).width) + 10, h: 15 })
    return out
  }
  function computeLayout() {
    const labelled = inst.items.filter(it => it.mode !== 'hidden')
    const order = labelled.slice().sort((a, b) => (b.id === inst.sel) - (a.id === inst.sel) || (b.id === inst.hover) - (a.id === inst.hover) || b.value - a.value || (a.id < b.id ? -1 : 1))
    const obs = obstacles()
    const free = (r, placed) => r.x >= 1 && r.x + r.w <= inst.W - 1 && r.y + r.h <= inst.H - 1 && !placed.some(p => rectsHit(r, p.rect, GEOM.eps_px)) && !obs.some(o => rectHitsPoly(o, r, 1))
    const placed = []
    order.forEach(it => {
      const vars = variantsFor(it)
      for (let vi = 0; vi < vars.length; vi++) {
        const v = vars[vi], p = plateAt(it, v.w), rect = { x: p.x, y: p.y, w: v.w, h: v.h }
        if (free(rect, placed)) { placed.push({ it, v, rect, strong: it.id === inst.sel, hover: it.id === inst.hover }); return }
      }
    })
    inst.placed = placed
    renderLegend(labelled, placed)
    // 樹避開名稱牌與旗桿列（名稱帶保持乾淨）
    const fr = flagRect(), k = inst.sc
    inst.treesShown = inst.trees.filter(([i, j, s]) => {
      const c = P(i + 0.5, j + 0.5), r = { x: c[0] - 8 * s * k, y: c[1] - 22 * s * k, w: 16 * s * k, h: 22 * s * k }
      if (!(r.x + r.w < fr[0] || r.x > fr[2] || r.y + r.h < fr[1] || r.y > fr[3])) return false
      return !placed.some(p => rectsHit(r, p.rect, 1))
    })
  }
  // 圖例：只在有項目沒顯示完整名稱（手機寬度）時出現；編號依市值由大到小，跨重跑穩定
  function renderLegend(labelled, placed) {
    const full = new Set(placed.filter(p => !p.v.badge).map(p => p.it.id))
    const badged = new Set(placed.filter(p => p.v.badge).map(p => p.it.id))
    const rest = labelled.filter(it => !full.has(it.id)).sort((a, b) => inst.numbers[a.id] - inst.numbers[b.id])
    const nodes = rest.map(it => {
      const row = document.createElement('span'), no = document.createElement('b'), sub = document.createElement('i')
      no.textContent = badged.has(it.id) ? String(inst.numbers[it.id]) : '·'
      sub.textContent = it.sub
      row.append(no, document.createTextNode(it.name + ' '), sub)
      return row
    })
    legend.replaceChildren(...nodes)
    legend.hidden = !rest.length
  }
  function drawLabels() {
    const { TK } = inst, cc = inst.cc
    inst.placed.forEach(p => {
      const r = p.rect, hot = p.strong || p.hover, it = p.it, faded = it.mode === 'faded'
      ctx.fillStyle = cc.panel; ctx.strokeStyle = hot ? TK.accent : cc.border; ctx.lineWidth = hot ? 2 : 1
      if (faded) ctx.setLineDash([3, 2])
      ctx.beginPath(); if (ctx.roundRect) ctx.roundRect(r.x, r.y, r.w, r.h, 5); else ctx.rect(r.x, r.y, r.w, r.h); ctx.fill(); ctx.stroke()
      ctx.setLineDash([])
      const cy = r.y + r.h / 2
      if (p.v.badge) {   // 編號小牌：置中編號，底邊一條區域色
        ctx.fillStyle = TK.zone[it.zone]; ctx.fillRect(r.x + 3, r.y + r.h - 3, r.w - 6, 2)
        ctx.font = `700 10px ${TK.fontBody}`; ctx.fillStyle = cc.name; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(p.v.lines[0][0], r.x + r.w / 2, cy - 1)
        return
      }
      if (it.warn) {   // 偏離警示：圓點改成警示三角
        const s = 4.6; poly([[r.x + 8, cy - s], [r.x + 8 + s, cy + s * 0.8], [r.x + 8 - s, cy + s * 0.8]], TK.warn, mix(TK.warn, '#000000', 0.35), 1)
      } else if (faded) {   // 沒有此項目：空心分區色點
        ctx.strokeStyle = TK.zone[it.zone]; ctx.lineWidth = 1.5; ctx.beginPath(); ctx.arc(r.x + 8, cy, 3.2, 0, 7); ctx.stroke()
      } else { ctx.fillStyle = TK.zone[it.zone]; ctx.beginPath(); ctx.arc(r.x + 8, cy, 3.4, 0, 7); ctx.fill() }
      ctx.textAlign = 'left'; ctx.textBaseline = 'top'
      const avail = r.w - GEOM.pad_l - GEOM.pad_r
      const tot = p.v.lines.reduce((s, ln) => s + ln[1], 0) + GEOM.line_gap * (p.v.lines.length - 1); let y = r.y + (r.h - tot) / 2
      p.v.lines.forEach(([txt, px, wt, role]) => {
        ctx.font = `${wt} ${px}px ${TK.fontBody}`
        const mw = ctx.measureText(txt).width
        if (mw > avail) ctx.font = `${wt} ${Math.max(8, px * avail / mw).toFixed(1)}px ${TK.fontBody}`   // 實際字寬超過底板：縮字，不加寬底板
        ctx.fillStyle = role === 'sub' ? cc.sub : cc.name; ctx.fillText(txt, r.x + GEOM.pad_l, y); y += px + GEOM.line_gap
      })
    })
  }

  // ---------- 互動 ----------
  const pick = (x, y) => { const cand = inst.hits.filter(h => inPoly(x, y, h.poly)).sort((a, b) => b.d - a.d); return cand.length ? cand[0].id : null }
  const localXY = ev => { const r = canvas.getBoundingClientRect(); return [ev.clientX - r.left, ev.clientY - r.top] }
  function showTip(id, x, y) {
    const it = inst.byId.get(id)
    if (!it || !it.tip.length) { tip.hidden = true; return }
    // 第一行是名稱（粗體），其餘各行為金額與比較；一律以文字節點建構
    const rows = it.tip.map((line, k) => {
      const row = document.createElement('div'), text = k === 0 ? document.createElement('b') : row
      text.textContent = line
      if (k === 0) row.append(text)
      return row
    })
    tip.replaceChildren(...rows); tip.hidden = false
    const tw = tip.offsetWidth; tip.style.left = Math.min(Math.max(8, x + 14), inst.W - tw - 8) + 'px'; tip.style.top = Math.max(8, y - 46) + 'px'
  }
  const onMove = ev => {
    const [x, y] = localXY(ev); const id = pick(x, y)
    if (id !== inst.hover) { inst.hover = id; canvas.style.cursor = id ? 'pointer' : 'default'; if (inst.rm) draw(performance.now()) }
    if (id) showTip(id, x, y); else tip.hidden = true
  }
  const onLeave = () => { inst.hover = null; tip.hidden = true; if (inst.rm) draw(performance.now()) }
  const onClick = ev => {
    const [x, y] = localXY(ev); const id = pick(x, y)
    if (!id) return
    // 本機先高亮（不等 Python 往返），同時回報持久選取
    inst.sel = id
    if (inst.cb.setStateValue) inst.cb.setStateValue('selected', id)
    if (inst.rm) draw(performance.now())
  }
  canvas.addEventListener('mousemove', onMove)
  canvas.addEventListener('mouseleave', onLeave)
  canvas.addEventListener('click', onClick)

  // ---------- 資料更新（Python 到 JS） ----------
  function renderPanels() {
    const D = inst.D, panel = root.querySelector('#weather')
    panel.dataset.sev = D.weather.severity
    root.querySelector('#wMain').textContent = D.weather.title
    root.querySelector('#wSub').textContent = D.weather.subtitle
    root.querySelector('#mon').textContent = D.month
    canvas.setAttribute('aria-label', D.aria_label)
  }
  inst.update = function (D) {
    const first = !inst.D
    inst.D = D
    inst.dataVer++
    inst.sel = D.selected ?? null
    inst.items = buildItems(D)
    inst.byId = new Map(inst.items.map(it => [it.id, it]))
    const layoutChanged = rebuildLayout()
    const ranked = inst.items.filter(it => it.mode !== 'hidden').sort((a, b) => b.value - a.value || (a.id < b.id ? -1 : 1))
    inst.numbers = Object.fromEntries(ranked.map((it, k) => [it.id, k + 1]))
    inst.items.forEach(it => { if (it.site) return; const t = targetOf(it); if (inst.curH[it.id] === undefined) inst.curH[it.id] = t; inst.tgtH[it.id] = t })
    inst.tgtSite = D.site.progress
    if (first) inst.curSite = inst.tgtSite
    renderPanels()
    readTokens()
    if (first || layoutChanged) resize()
    if (inst.rm) { snap(); draw(performance.now()) }
  }
  // 減少動態時直接呈現目標：建築直接是當月高度，工地進度同步到位
  function snap() { inst.items.forEach(it => { if (!it.site) inst.curH[it.id] = inst.tgtH[it.id] }); inst.curSite = inst.tgtSite }
  const ease = (cur, tgt) => { const next = cur + (tgt - cur) * 0.14; return Math.abs(tgt - next) < 0.05 ? tgt : next }
  function frame(t) {
    if (inst.D) {
      inst.items.forEach(it => { if (!it.site) inst.curH[it.id] = ease(inst.curH[it.id], inst.tgtH[it.id]) })
      inst.curSite = ease(inst.curSite, inst.tgtSite)
      draw(t)
    }
    inst.raf = requestAnimationFrame(frame)
  }
  function startLoop() { cancelAnimationFrame(inst.raf); inst.raf = 0; if (!inst.rm) inst.raf = requestAnimationFrame(frame) }
  // 主題切換（系統深淺色）與減少動態偏好變更時即時反應
  const onTheme = () => { readTokens(); if (inst.rm) draw(performance.now()) }
  const onMotion = () => { inst.rm = motionQuery.matches; if (inst.rm && inst.D) { snap(); draw(performance.now()) } startLoop() }
  themeQuery.addEventListener('change', onTheme)
  motionQuery.addEventListener('change', onMotion)
  inst.ro = new ResizeObserver(resize); inst.ro.observe(wrap)
  inst.destroy = () => {
    cancelAnimationFrame(inst.raf); inst.ro.disconnect()
    themeQuery.removeEventListener('change', onTheme); motionQuery.removeEventListener('change', onMotion)
    canvas.removeEventListener('mousemove', onMove); canvas.removeEventListener('mouseleave', onLeave); canvas.removeEventListener('click', onClick)
    INSTANCES.delete(root)
  }
  startLoop()
  return inst
}

export default function (component) {
  const { data, parentElement, setStateValue } = component
  let inst = INSTANCES.get(parentElement)
  // html 若被重新注入，舊 canvas 會脫離 DOM：偵測到就重建
  if (inst && !parentElement.contains(inst.canvas)) { inst.destroy(); inst = null }
  if (!inst) { inst = createInstance(parentElement); INSTANCES.set(parentElement, inst) }
  inst.cb = { setStateValue }
  inst.runs++
  inst.update(data)
  // 供人工驗證是否重新掛載（畫面上不顯示任何診斷文字）
  const host = parentElement.getRootNode().host
  if (host) { host.dataset.mount = inst.id; host.dataset.runs = inst.runs }
  return () => inst.destroy()
}
