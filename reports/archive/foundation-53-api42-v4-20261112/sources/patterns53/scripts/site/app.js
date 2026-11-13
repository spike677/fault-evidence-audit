/* ============ 昇腾算子故障模式库 · 前端应用 ============ */
(function () {
"use strict";

const D = window.__FP__;
const P = D.patterns;
const C = D.cases;
const M = D.meta;

const CAT_COLOR = {
  accuracy: "#c7000b",
  compatibility: "#b45309",
  performance: "#0d7490",
  reliability: "#6d28d9",
  resource: "#1f6f43",
  test_effectiveness: "#a16207",
  engineering: "#475569"
};
const LVL_CLS = { "高": "hi", "中": "mid", "低": "lo" };
const TRIG_ORDER = ["必须触发", "签名", "宽泛定位", "关键词", "无代码触发特征"];

const byId = {};
P.forEach(p => { byId[p.id] = p; });

/* ---------------- helpers ---------------- */
const $ = s => document.querySelector(s);
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}
function md(s) {
  if (!s) return "";
  let t = esc(s);
  t = t.replace(/`([^`]+)`/g, "<code>$1</code>");
  t = t.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  t = t.replace(/(^|[^\w])(#\d{3,5})/g, '$1<span class="iss">$2</span>');
  t = t.replace(/\n/g, "<br>");
  return t;
}
function catDot(cat) {
  return `<i style="background:${CAT_COLOR[cat] || "#888"}"></i>`;
}
function riskBadge(p) {
  return `<span class="risk ${LVL_CLS[p.level]}">${p.level}<span class="sc">S${p.s}×O${p.o}</span></span>`;
}
function toast(msg) {
  let el = $("#toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    el.style.cssText = "position:fixed;left:50%;bottom:34px;transform:translateX(-50%) translateY(10px);background:#15181e;color:#fff;font-size:12px;padding:7px 15px;border-radius:6px;z-index:200;opacity:0;transition:.2s;pointer-events:none;box-shadow:0 8px 24px rgba(0,0,0,.25)";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  requestAnimationFrame(() => { el.style.opacity = "1"; el.style.transform = "translateX(-50%) translateY(0)"; });
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.style.opacity = "0"; el.style.transform = "translateX(-50%) translateY(10px)"; }, 1400);
}

/* ---------------- state ---------------- */
const S = {
  view: "overview",
  q: "",
  cat: "all",
  lvl: "all",
  depth: "all",
  trig: "all",
  so: null,
  sort: "risk",
  caseFp: "all",
  caseQ: ""
};

/* ---------------- computed stats ---------------- */
const stats = (() => {
  const byCat = {}, byLvl = {}, byDepth = {}, byTrig = {};
  let sigTotal = 0, kwTotal = 0, broadTotal = 0, absenceTotal = 0;
  P.forEach(p => {
    byCat[p.cat] = (byCat[p.cat] || 0) + 1;
    byLvl[p.level] = (byLvl[p.level] || 0) + 1;
    byDepth[p.depth] = (byDepth[p.depth] || 0) + 1;
    byTrig[p.triggerZh || "—"] = (byTrig[p.triggerZh || "—"] || 0) + 1;
    sigTotal += (p.signatures || []).length;
    kwTotal += (p.keywords || []).length;
    broadTotal += (p.broad || []).length;
    absenceTotal += (p.absence || []).length;
  });
  const matrix = {};
  P.forEach(p => {
    const k = `S${p.s}O${p.o}`;
    (matrix[k] = matrix[k] || []).push(p.id);
  });
  const withCases = P.filter(p => p.caseCount > 0).length;
  const mustTrig = P.filter(p => p.triggerZh === "必须触发").length;
  return { byCat, byLvl, byDepth, byTrig, sigTotal, kwTotal, broadTotal, absenceTotal, matrix, withCases, mustTrig };
})();

/* ---------------- router ---------------- */
const TITLES = {
  overview: "总体概览", patterns: "故障模式", cases: "实证案例",
  triage: "症状分诊", layers: "判据分层", secondary: "第二判据",
  compositions: "组合故障", method: "库标准"
};
function go(view) {
  if (!TITLES[view]) view = "overview";
  S.view = view;
  document.querySelectorAll(".view").forEach(v => v.classList.remove("on"));
  const el = $("#v-" + view);
  if (el) el.classList.add("on");
  document.querySelectorAll("#nav a").forEach(a => a.classList.toggle("on", a.dataset.v === view));
  $("#crumb").innerHTML = view === "overview"
    ? `<span>库首页</span><b>总体概览</b>`
    : `<span>库首页</span><span>›</span><b>${TITLES[view]}</b>`;
  if (!el.dataset.done) { render[view](); el.dataset.done = "1"; }
  window.scrollTo({ top: 0, behavior: "instant" });
  if (view === "patterns") applyFilters();
  if (view === "cases") applyCaseFilters();
}
window.addEventListener("hashchange", () => go((location.hash || "#/overview").replace("#/", "")));

/* ---------------- overview ---------------- */
const render = {};

render.overview = function () {
  const hi = stats.byLvl["高"] || 0, mid = stats.byLvl["中"] || 0, lo = stats.byLvl["低"] || 0;
  const pct = n => Math.round(n / P.length * 100);

  /* risk matrix */
  const rows = [4, 3, 2, 1], cols = [3, 2, 1];
  let mx = `<div class="mx"><div></div>`;
  cols.forEach(o => { mx += `<div class="hd">O${o}</div>`; });
  rows.forEach(s => {
    mx += `<div class="rl">S${s}</div>`;
    cols.forEach(o => {
      const ids = stats.matrix[`S${s}O${o}`] || [];
      const score = s * o;
      const cls = !ids.length ? "z" : score >= 6 ? "hi" : score >= 3 ? "mid" : "lo";
      mx += `<div class="cell ${cls}" data-so="${s}-${o}" title="S${s}×O${o}｜风险 ${score}${ids.length ? "｜" + ids.join(" ") : ""}">
        <div class="n">${ids.length || "·"}</div>
        <div class="ids">${ids.slice(0, 5).join(" ") || "—"}</div>
      </div>`;
    });
  });
  mx += `</div>`;

  /* category bars */
  let bars = `<div class="bars">`;
  M.cats.forEach(c => {
    const n = stats.byCat[c] || 0;
    bars += `<div class="bar" data-cat="${c}">
      <div class="lb">${catDot(c)}${M.catZh[c]}</div>
      <div class="tr"><div class="fi" style="width:${n / P.length * 100}%;background:${CAT_COLOR[c]}"></div></div>
      <div class="vl"><b>${n}</b> 条</div>
    </div>`;
  });
  bars += `</div>`;

  /* trigger distribution */
  let tbars = `<div class="bars">`;
  TRIG_ORDER.forEach(t => {
    const n = stats.byTrig[t] || 0;
    if (!n) return;
    const col = t === "必须触发" ? "#c7000b" : t === "签名" ? "#0d7490" : t === "宽泛定位" ? "#b45309" : "#8a93a0";
    tbars += `<div class="bar" data-trig="${t}">
      <div class="lb"><i style="background:${col}"></i>${t}</div>
      <div class="tr"><div class="fi" style="width:${n / P.length * 100}%;background:${col}"></div></div>
      <div class="vl"><b>${n}</b></div>
    </div>`;
  });
  tbars += `</div>`;

  /* top risk */
  const top = P.slice().sort((a, b) => b.score - a.score || b.caseCount - a.caseCount || a.id.localeCompare(b.id)).slice(0, 7);
  let topRows = "";
  top.forEach(p => {
    topRows += `<div class="row" data-fp="${p.id}" style="grid-template-columns:58px 1fr 84px 58px">
      <div class="rid">${p.id}</div>
      <div class="rname">${esc(p.name)}</div>
      <div class="rcat">${catDot(p.cat)}${p.catZh}</div>
      <div class="rcase"><b>${p.caseCount}</b></div>
    </div>`;
  });

  /* L2 axes coverage */
  const axCount = {};
  P.forEach(p => {
    const d = p.detect;
    if (d && d.axes) d.axes.forEach(a => { axCount[a] = (axCount[a] || 0) + 1; });
  });
  const axSorted = Object.keys(axCount).sort((a, b) => axCount[b] - axCount[a]).slice(0, 8);
  let axBars = `<div class="bars">`;
  const axMax = axSorted.length ? axCount[axSorted[0]] : 1;
  axSorted.forEach(a => {
    const n = axCount[a];
    axBars += `<div class="bar" style="grid-template-columns:96px 1fr 46px">
      <div class="lb"><i style="background:#2c5282"></i>${a}</div>
      <div class="tr"><div class="fi" style="width:${n / axMax * 100}%;background:#2c5282;opacity:.8"></div></div>
      <div class="vl"><b>${n}</b></div>
    </div>`;
  });
  axBars += `</div>`;

  /* 可检出性 D 分布（v6.21） */
  const dCount = { D1: 0, D2: 0, D3: 0 };
  P.forEach(p => { if (p.detectability && dCount[p.detectability.level] != null) dCount[p.detectability.level]++; });
  let dBars = `<div class="bars">`;
  [["D1", "#1a7f45", "自动可判"], ["D2", "#b45309", "半自动"], ["D3", "#9b0009", "仅人工/上板"]].forEach(([k, col, lb]) => {
    const n = dCount[k] || 0;
    dBars += `<div class="bar" style="grid-template-columns:96px 1fr 52px;cursor:default">
      <div class="lb"><i style="background:${col}"></i>${k} ${lb}</div>
      <div class="tr"><div class="fi" style="width:${n / P.length * 100}%;background:${col};opacity:.85"></div></div>
      <div class="vl"><b>${n}</b> 条</div>
    </div>`;
  });
  dBars += `</div>`;

  /* priority = S×O×D 最高的模式 */
  const withD = P.filter(p => p.detectability && p.detectability.priority != null);
  const prioTop = withD.slice().sort((a, b) =>
    b.detectability.priority - a.detectability.priority || a.id.localeCompare(b.id)).slice(0, 7);
  let prioRows = prioTop.map(p => `<div class="row" data-fp="${p.id}"
      style="grid-template-columns:66px 1fr 62px 70px;border-radius:0">
      <div class="rid">${p.id}</div>
      <div class="rname" style="font-size:12px">${esc(p.name)}</div>
      <div><span class="dcell ${p.detectability.level}">${p.detectability.level}</span></div>
      <div class="rcase"><b>${p.detectability.priority}</b></div>
    </div>`).join("");

  $("#v-overview").innerHTML = `
  <div class="ptitle"><h2>昇腾算子故障模式库</h2><span class="tag">v${M.version}</span><span class="tag">${M.updated}</span></div>
  <p class="pdesc">把算子源码检视、跨版本核验与测试集失败分析中反复出现的<b>故障机理</b>，沉淀为「一模式一卡片」的可检索条目。
    每条包含八要素卡片、判别性检测签名、三层判据（L1 机理 / L2 怎么测 / L3 观测手段自身失效）与真实 issue 实证。</p>

  <div class="kpis">
    <div class="kpi acc"><div class="k">故障模式</div><div class="v">${P.length}<small>条</small></div>
      <div class="s">7 类 · <b>${stats.withCases}</b> 条含案例</div></div>
    <div class="kpi"><div class="k">实证案例</div><div class="v">${C.length}<small>条</small></div>
      <div class="s"><b>${M.caseStats.with_issue || 0}</b> 关联真实 issue</div></div>
    <div class="kpi"><div class="k">高危模式</div><div class="v">${hi}<small>条</small></div>
      <div class="s">占 <b>${pct(hi)}%</b> · 中 ${mid} · 低 ${lo}</div></div>
    <div class="kpi"><div class="k">检测签名</div><div class="v">${stats.sigTotal}<small>条</small></div>
      <div class="s">+ 关键词 <b>${stats.kwTotal}</b> / 宽泛 ${stats.broadTotal}</div></div>
    <div class="kpi"><div class="k">L3 判据失效</div><div class="v">${M.nL3}<small>条</small></div>
      <div class="s">跨 <b>${Object.keys(D.l3.by_oracle).length}</b> 类 oracle</div></div>
    <div class="kpi"><div class="k">第二判据</div><div class="v">${M.nSecondary}<small>条</small></div>
      <div class="s">覆盖 ${Math.round(M.nSecondary / P.length * 100)}% 模式</div></div>
  </div>
  <div class="mono-sm" style="margin-bottom:22px">数据源 · ${esc(M.layout || "")} ｜ 门禁 ${esc(M.gates || "")} ｜ 软件签名实扫脚本 scripts/scan_fp.py</div>

  <div class="grid2">
    <div class="card">
      <div class="card-h"><h4>风险矩阵</h4><span class="hint">S 严重度 × O 发生度 · 点击筛选</span></div>
      <div class="card-b">${mx}
        <div class="mono-sm" style="margin-top:11px;line-height:1.8">
          高 ≥6（含 S4×O2=8、S4×O3=12）｜ 中 3/4 ｜ 低 1/2<br>
          S4 致命 = 崩溃 / 挂死 / 数据静默损坏，共同特征是「<b style="color:#9b0009">没有结果</b>」
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h4>类别分布</h4><span class="hint">${M.cats.length} 类 · 共 ${P.length} 条</span></div>
      <div class="card-b">${bars}</div>
    </div>
  </div>

  <div class="sec-h"><h3>入口形态与判据覆盖</h3><div class="line"></div></div>
  <div class="grid2">
    <div class="card">
      <div class="card-h"><h4>触发形态</h4><span class="hint">决定扫描器怎么用这条模式</span></div>
      <div class="card-b">${tbars}
        <div class="mono-sm" style="margin-top:11px;line-height:1.8">
          <b style="color:#9b0009">必须触发</b> = 不依赖签名无条件走清单，上限 6 条<br>
          <b>签名</b> = 有可扫指纹，出候选点位 ｜ <b>宽泛定位</b> = 存在即常态，仅定位
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h4>L2 判据轴覆盖</h4><span class="hint">用例构造维度 · 前 8</span></div>
      <div class="card-b">${axBars}
        <div class="mono-sm" style="margin-top:11px">每条模式的 L2 判据给出 axes / oracle / signal / judge / kill —— 见「判据分层」</div>
      </div>
    </div>
  </div>

  <div class="sec-h"><h3>可检出性与优先级</h3><div class="line"></div>
    <span class="note">D 越大越难检出 · priority = S×O×D</span></div>
  <div class="grid2">
    <div class="card">
      <div class="card-h"><h4>可检出性分布</h4><span class="hint">FMEA Detection 维度</span></div>
      <div class="card-b">${dBars}
        <div class="mono-sm" style="margin-top:11px;line-height:1.8">
          <b>D1</b> 自动可判 ｜ <b>D2</b> 半自动 ｜ <b>D3</b> 仅人工/上板<br>
          不改变 risk.level，只用于排序「先查哪条」
        </div>
      </div>
    </div>
    <div class="card">
      <div class="card-h"><h4>优先级最高的模式</h4><span class="hint">S×O×D 降序 · 前 7</span></div>
      <div class="card-b" style="padding:0">
        ${prioRows}
      </div>
    </div>
  </div>

  <div class="sec-h"><h3>最高风险模式</h3><div class="line"></div>
    <span class="note">按 S×O 与案例数排序</span></div>
  <div class="rows">
    <div class="head-row" style="grid-template-columns:58px 1fr 84px 58px">
      <span>编号</span><span>模式</span><span>类别</span><span style="text-align:right">案例</span>
    </div>
    ${topRows}
  </div>`;
};

/* ---------------- patterns ---------------- */
/* 签名既可能是纯字符串，也可能是 {re, files} / {must, files} 等结构化对象 */
function sigText(s) {
  if (typeof s === "string") return s;
  if (!s || typeof s !== "object") return String(s || "");
  const pat = s.re || s.must || s.func || s.pattern || "";
  const scope = [s.files, s.branch, s.when].filter(Boolean).join(" · ");
  return scope ? `${pat}  ⟨${scope}⟩` : pat;
}
function sigKind(s) {
  if (typeof s !== "object" || !s) return "";
  if (s.must) return "must";
  if (s.re) return "re";
  return "";
}
function sigHay(s) {
  if (typeof s === "string") return s;
  if (!s || typeof s !== "object") return "";
  return [s.re, s.must, s.func, s.pattern, s.files, s.branch, s.when, s.note, s.level].filter(Boolean).join(" ");
}
function arrOf(v) { return Array.isArray(v) ? v : []; }

function patternMatches(p, q) {
  if (!q) return true;
  const hay = [
    p.id, p.name, p.catZh,
    p.body && p.body.mechanism, p.body && p.body.conditions,
    p.body && p.body.manifest, p.body && p.body.mapping,
    p.body && p.body.intercept, p.body && p.body.evidence_text,
    arrOf(p.signatures).map(sigHay).join(" "),
    arrOf(p.broad).map(sigHay).join(" "),
    arrOf(p.absence).map(sigHay).join(" "),
    arrOf(p.logSig).map(sigHay).join(" "),
    arrOf(p.keywords).map(sigHay).join(" "),
    arrOf(p.symptoms).join(" "), arrOf(p.detectors).join(" "),
    arrOf(p.repos).join(" "), arrOf(p.sides).join(" "), arrOf(p.carriers).join(" "),
    arrOf(p.subtypes).map(s => (s.name || "") + " " + (s.id || "")).join(" "),
    C.filter(c => c.fp === p.id).map(c => [c.title, c.trigger, c.root, c.evidence, (c.issues || []).join(" ")].join(" ")).join(" ")
  ].join(" ").toLowerCase();
  return q.toLowerCase().split(/\s+/).every(w => hay.includes(w));
}

render.patterns = function () {
  const catPills = [{ k: "all", t: "全部", n: P.length }]
    .concat(M.cats.map(c => ({ k: c, t: M.catZh[c], n: stats.byCat[c] || 0 })));
  const lvlPills = ["高", "中", "低"].map(l => ({ k: l, t: l, n: stats.byLvl[l] || 0 }));
  const depthPills = ["深度", "标准", "宽浅"].map(d => ({ k: d, t: d, n: stats.byDepth[d] || 0 }));

  $("#v-patterns").innerHTML = `
  <div class="ptitle"><h2>故障模式</h2><span class="tag">${P.length} 条</span></div>
  <p class="pdesc">按机理建条、编号永不复用。点击任一行查看八要素卡片、检测签名、L2 判据与实证案例。</p>

  <div class="fbar">
    <div class="fgrp"><span>类别</span>
      ${catPills.map(c => `<button class="pill ${S.cat === c.k ? "on" : ""}" data-fcat="${c.k}">${c.t}<span class="c">${c.n}</span></button>`).join("")}
    </div>
    <div class="fsep"></div>
    <div class="fgrp"><span>风险</span>
      ${lvlPills.map(c => `<button class="pill ${S.lvl === c.k ? "on" : ""}" data-flvl="${c.k}">${c.t}<span class="c">${c.n}</span></button>`).join("")}
    </div>
    <div class="fsep"></div>
    <div class="fgrp"><span>负载</span>
      ${depthPills.map(c => `<button class="pill ${S.depth === c.k ? "on" : ""}" data-fdepth="${c.k}">${c.t}<span class="c">${c.n}</span></button>`).join("")}
    </div>
    <div class="fright">
      <select class="sel" id="sortSel">
        <option value="risk">按风险</option>
        <option value="id">按编号</option>
        <option value="cases">按案例数</option>
        <option value="name">按名称</option>
      </select>
      <button class="pill" id="resetF">重置</button>
    </div>
  </div>
  <div class="res" style="margin:-4px 0 10px" id="pRes"></div>
  <div id="pList"></div>`;

  $("#v-patterns").addEventListener("click", e => {
    const b = e.target.closest("[data-fcat],[data-flvl],[data-fdepth]");
    if (b) {
      if (b.dataset.fcat !== undefined) S.cat = S.cat === b.dataset.fcat ? "all" : b.dataset.fcat;
      if (b.dataset.flvl !== undefined) S.lvl = S.lvl === b.dataset.flvl ? "all" : b.dataset.flvl;
      if (b.dataset.fdepth !== undefined) S.depth = S.depth === b.dataset.fdepth ? "all" : b.dataset.fdepth;
      render.patterns(); $("#v-patterns").dataset.done = "1";
      applyFilters();
      return;
    }
    if (e.target.closest("#resetF")) {
      S.cat = "all"; S.lvl = "all"; S.depth = "all"; S.trig = "all"; S.so = null; S.q = "";
      $("#q").value = "";
      render.patterns(); $("#v-patterns").dataset.done = "1";
      applyFilters();
    }
  });
  $("#sortSel").addEventListener("change", e => { S.sort = e.target.value; applyFilters(); });
};

function currentPatterns() {
  // 有关键词时：筛选让位，全局搜索，避免「搜不到」的假空结果
  if (S.q) {
    const hit = P.filter(p => patternMatches(p, S.q));
    const cmpS = {
      risk: (a, b) => b.score - a.score || b.caseCount - a.caseCount || a.id.localeCompare(b.id),
      id: (a, b) => a.id.localeCompare(b.id),
      cases: (a, b) => b.caseCount - a.caseCount || b.score - a.score,
      name: (a, b) => a.name.localeCompare(b.name, "zh")
    };
    return hit.sort(cmpS[S.sort] || cmpS.risk);
  }
  let arr = P.filter(p =>
    (S.cat === "all" || p.cat === S.cat) &&
    (S.lvl === "all" || p.level === S.lvl) &&
    (S.depth === "all" || p.depth === S.depth) &&
    (S.trig === "all" || p.triggerZh === S.trig) &&
    (!S.so || (`S${p.s}O${p.o}` === S.so))
  );
  const cmp = {
    risk: (a, b) => b.score - a.score || b.caseCount - a.caseCount || a.id.localeCompare(b.id),
    id: (a, b) => a.id.localeCompare(b.id),
    cases: (a, b) => b.caseCount - a.caseCount || b.score - a.score,
    name: (a, b) => a.name.localeCompare(b.name, "zh")
  };
  return arr.sort(cmp[S.sort] || cmp.risk);
}

function applyFilters() {
  const arr = currentPatterns();
  const res = $("#pRes"), list = $("#pList");
  if (!res || !list) return;
  const chips = [];
  if (S.so) chips.push(`S${S.so.replace("-", "×O")}`);
  if (S.trig !== "all") chips.push(S.trig);
  if (S.q) {
    res.innerHTML = `全局搜索 <b>${arr.length}</b> / ${P.length} 条 ｜ 关键词 “<b>${esc(S.q)}</b>”` +
      `<span style="color:var(--ink-4)"> ｜ 筛选条件已让位</span>`;
  } else {
    res.innerHTML = `命中 <b>${arr.length}</b> / ${P.length} 条${chips.length ? " ｜ " + chips.join(" · ") : ""}`;
  }
  if (!arr.length) {
    // 搜不到时给反向引导：从分诊表的症状词反查
    const q = (S.q || "").toLowerCase();
    const sug = [];
    if (q) {
      D.triage.entries.forEach(e => e.groups.forEach(g => g.rows.forEach(r => {
        if (r.symptom.toLowerCase().includes(q) && !sug.includes(r.fp)) sug.push(r.fp);
      })));
    }
    list.innerHTML = `<div class="empty"><div class="big">∅</div><p>没有模式正文命中 “${esc(S.q)}”</p>
      <div class="hint2">换个说法试试（如 <b>OOM</b> / <b>racecheck</b> / <b>161001</b> / <b>图模式</b>），或从症状分诊进入</div>
      ${sug.length ? `<div style="margin-top:18px;display:flex;gap:6px;justify-content:center;flex-wrap:wrap">
        ${sug.map(f => `<span class="cand" data-fp="${f}"><span class="cid">${f}</span></span>`).join("")}
      </div><div class="hint2" style="margin-top:8px">分诊表里含该症状词的候选</div>` : ""}
    </div>`;
    return;
  }
  list.innerHTML = `<div class="rows">
    <div class="head-row"><span>编号</span><span>模式名称</span><span>类别</span><span>风险</span><span>负载</span><span style="text-align:right">案例</span></div>
    ${arr.map(p => `<div class="row" data-fp="${p.id}">
      <div class="rid">${p.id}</div>
      <div class="rname">${markHits(esc(p.name), S.q)}</div>
      <div class="rcat">${catDot(p.cat)}${p.catZh}</div>
      <div>${riskBadge(p)}</div>
      <div class="rdepth">${p.depth}</div>
      <div class="rcase"><b>${p.caseCount || "—"}</b></div>
    </div>`).join("")}
  </div>`;
}

/* ---------------- cases ---------------- */
render.cases = function () {
  const fps = [...new Set(C.map(c => c.fp))].sort();
  $("#v-cases").innerHTML = `
  <div class="ptitle"><h2>实证案例</h2><span class="tag">${C.length} 条</span></div>
  <p class="pdesc">每条案例对应真实 issue 或跨仓核验，含触发条件、根因、最小复现、可执行判据与修复范式。
    <b>${M.caseStats.with_verified_anchor || 0}</b> 条带真实修复锚点（文件 + 行号 + commit）。</p>
  <div class="fbar">
    <div class="fgrp"><span>模式</span>
      <button class="pill ${S.caseFp === "all" ? "on" : ""}" data-cfp="all">全部<span class="c">${C.length}</span></button>
      ${fps.map(f => `<button class="pill ${S.caseFp === f ? "on" : ""}" data-cfp="${f}">${f}<span class="c">${C.filter(c => c.fp === f).length}</span></button>`).join("")}
    </div>
  </div>
  <div class="res" style="margin:-4px 0 10px" id="cRes"></div>
  <div class="clist" id="cList"></div>`;
  $("#v-cases").addEventListener("click", e => {
    const b = e.target.closest("[data-cfp]");
    if (b) {
      S.caseFp = S.caseFp === b.dataset.cfp ? "all" : b.dataset.cfp;
      render.cases(); $("#v-cases").dataset.done = "1"; applyCaseFilters();
    }
  });
};

function currentCases() {
  const q = (S.caseQ || S.q || "").toLowerCase();
  return C.filter(c => {
    if (!q && S.caseFp !== "all" && c.fp !== S.caseFp) return false;
    if (!q) return true;
    const hay = [c.id, c.fp, c.title, c.trigger, c.root, c.repro, c.evidence, (c.issues || []).join(" "),
      (c.code || ""), (c.criteria ? JSON.stringify(c.criteria) : ""),
      (c.anchors || []).map(a => a.file + " " + a.note).join(" ")].join(" ").toLowerCase();
    return q.split(/\s+/).every(w => hay.includes(w));
  });
}

function markHits(html, q) {
  if (!q) return html;
  const words = q.split(/\s+/).filter(Boolean).map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
  if (!words.length) return html;
  const re = new RegExp("(" + words.join("|") + ")", "gi");
  // 只对纯文本片段加高亮，避免破坏已有标签
  return html.replace(/(<[^>]*>)|([^<]+)/g, (m, tag, text) =>
    tag ? tag : text.replace(re, '<mark class="hit">$1</mark>'));
}

function applyCaseFilters() {
  const arr = currentCases();
  const res = $("#cRes"), list = $("#cList");
  if (!res || !list) return;
  res.innerHTML = S.caseQ || S.q
    ? `全局搜索 <b>${arr.length}</b> / ${C.length} 条 ｜ 关键词 “<b>${esc(S.caseQ || S.q)}</b>”`
    : `命中 <b>${arr.length}</b> / ${C.length} 条`;
  if (!arr.length) {
    list.innerHTML = `<div class="empty"><div class="big">∅</div><p>没有符合条件的案例</p>
      <div class="hint2">换个关键词试试，或按 Esc 清空搜索</div></div>`;
    return;
  }
  list.innerHTML = arr.map(c => {
    const p = byId[c.fp];
    const hasAnchor = (c.anchors || []).length > 0;
    const q = S.caseQ || S.q;
    return `<div class="cc" data-case="${c.id}">
      <div class="cc-h">
        <span class="fpid">${c.fp}</span>
        <span class="t">${markHits(esc(c.title), q)}</span>
        ${hasAnchor ? `<span class="badge-v">真实锚点</span>` : ""}
      </div>
      <div class="cc-m">
        <span>${esc(c.id)}</span>
        ${p ? `<span style="display:flex;align-items:center;gap:4px">${catDot(p.cat)}${p.catZh}</span>` : ""}
        ${(c.issues || []).slice(0, 4).map(i => `<code>${esc(i)}</code>`).join("")}
        ${c.subtype ? `<span>子型 ${esc(c.subtype)}</span>` : ""}
      </div>
      <div class="cc-d">${markHits(esc(c.root || c.trigger || "").slice(0, 260), q)}</div>
    </div>`;
  }).join("");
}

/* ---------------- triage ---------------- */
render.triage = function () {
  const T = D.triage;
  const totalRows = T.entries.reduce((s, e) => s + e.groups.reduce((a, g) => a + g.rows.length, 0), 0);
  let html = `
  <div class="ptitle"><h2>症状分诊</h2><span class="tag">${T.entries.length} 个入口</span><span class="tag">${totalRows} 条症状</span></div>
  <p class="pdesc">手上只有现象、不知道查哪条模式时从这里进。<b>按「出了什么事」分流</b>而不是按「像哪个 bug」——
    每个入口把候选收敛到 1~6 条，再进卡片做机理比对。</p>
  <div class="note-box" style="margin-bottom:18px">
    <b>用法</b>：先按后果选入口（T1~T7）→ 在入口内对齐现象词 → 打开候选卡片先核「适用」声明（仓 / 侧别 / 载体不匹配则跳过并记理由）。
    <br><b>现象级条目 ≠ 模式</b>：<code>报错</code>、<code>精度失败</code> 这类粗粒度词收敛不了，必须加上工具名 / 报错串 / 退出码才能用。
  </div>`;

  T.entries.forEach((e, i) => {
    const n = e.groups.reduce((a, g) => a + g.rows.length, 0);
    html += `<div class="tcard ${i === 0 ? "open" : ""}" data-t="${e.id}">
      <div class="tcard-h">
        <div class="tid">${e.id}</div>
        <h4>${esc(e.title)}</h4>
        <span class="cm">${n} 条症状</span>
        <span class="arw">▶</span>
      </div>
      <div class="tintro">${md(e.intro || "")}</div>
      <div class="tbody">
        ${e.groups.map(g => `
          <div class="tgrp">
            <div class="tgrp-h">${esc(g.title)}</div>
            ${g.rows.map(r => {
              const p = byId[r.fp];
              const cls = p ? LVL_CLS[p.level] : "lo";
              return `<div class="trow">
                <div class="sym">${md(r.symptom)}</div>
                <div>
                  <div class="cands">
                    <span class="cand ${cls}" data-fp="${r.fp}"><span class="cid">${r.fp}</span>
                      ${p ? `<span class="cm2">${p.level}${p.caseCount ? " · " + p.caseCount + " 案" : ""}</span>` : ""}
                    </span>
                  </div>
                  ${r.first ? `<div class="cfirst">首查 · ${md(r.first).replace(/<[^>]+>/g, "").slice(0, 64)}</div>` : ""}
                </div>
              </div>`;
            }).join("")}
          </div>`).join("")}
      </div>
    </div>`;
  });
  html += `<div class="sec-h"><h3>症状词速查</h3><div class="line"></div></div>
    <div class="rows"><div class="head-row" style="grid-template-columns:1.6fr 90px">
      <span>现象词 / 同义词</span><span style="text-align:right">入口</span></div>
      ${T.quick_index.map(q => `<div class="row" data-jump="${q.entry}" style="grid-template-columns:1.6fr 90px">
        <div class="sym">${md(q.words)}</div>
        <div class="rcase"><b>${q.entry}</b></div>
      </div>`).join("")}
    </div>`;
  $("#v-triage").innerHTML = html;
};

/* ---------------- layers ---------------- */
render.layers = function () {
  const det = P.filter(p => p.detect);
  const orc = D.l3.by_oracle;
  const orcKeys = Object.keys(orc);

  let l2 = det.map(p => {
    const d = p.detect;
    return `<div class="dcase" data-l2="${p.id}">
      <div class="dcase-h">
        <span class="cid2">${p.id}</span>
        <span class="t2">${esc(p.name)}</span>
        <span class="axes" style="flex:none">${(d.oracle || []).map(o => `<span class="orc">${o}</span>`).join("")}</span>
        <span class="arw2">▶</span>
      </div>
      <div class="dcase-b">
        <div class="axes" style="margin-top:10px">${(d.axes || []).map(a => `<span class="ax">${a}</span>`).join("")}
          <span class="mchip">signal <b>${d.signal || "—"}</b></span>
          <span class="mchip">min_cases <b>${d.min_cases || "—"}</b></span>
          <span class="mchip">lines <b>${(d.lines || []).join("/") || "—"}</b></span>
        </div>
        <div class="dgrid" style="margin-top:10px">
          <div class="dbox"><div class="dh2">constructor<code class="src">${d.sourced ? d.sourced.constructor || "" : ""}</code></div><div class="dv">${md(d.constructor)}</div></div>
          <div class="dbox"><div class="dh2">judge<code class="src">${d.sourced ? d.sourced.judge || "" : ""}</code></div><div class="dv">${md(d.judge)}</div></div>
          <div class="dbox" style="grid-column:1/-1;background:#fffdfa;border-color:#f0e4d4"><div class="dh2">kill — 怎样才算「缺陷成立」<code class="src">${d.sourced ? d.sourced.kill || "" : ""}</code></div><div class="dv">${md(d.kill)}</div></div>
        </div>
      </div>
    </div>`;
  }).join("");

  let l3 = orcKeys.map(k => `
    <div class="l3g">
      <div class="l3g-h"><span class="oid">${k}</span>
        <span class="mono-sm">被 ${det.filter(p => (p.detect.oracle || []).includes(k)).length} 条模式使用</span>
        <span class="cnt2">${orc[k].length} 条失效</span></div>
      ${orc[k].map(r => `<div class="l3r">
        <div class="kid">${r.id}</div>
        <div><span class="ft ${r.fail === "假 PASS" ? "pass" : r.fail === "假 FAIL" ? "fail" : "other"}">${r.fail}</span></div>
        <div class="ru">${md(r.rule)}</div>
      </div>`).join("")}
    </div>`).join("");

  $("#v-layers").innerHTML = `
  <div class="ptitle"><h2>判据分层</h2><span class="tag">L1 / L2 / L3</span></div>
  <p class="pdesc">知道机理（L1 卡片）不等于会测。L2 回答「用什么轴构造、判什么、怎样才算缺陷成立」；
    L3 补上更隐蔽的一层——<b>你的观测手段本身会怎么骗你</b>。</p>

  <div class="card" style="margin-bottom:22px">
    <div class="card-b" style="display:grid;grid-template-columns:repeat(3,1fr);gap:1px;background:var(--line);padding:0">
      <div style="background:#fff;padding:16px">
        <div class="mono-sm" style="color:#c7000b;font-weight:700">L1 · 机理</div>
        <div style="font-size:13px;font-weight:620;margin:6px 0 5px">52 张八要素卡片</div>
        <div style="font-size:11.5px;color:var(--ink-3);line-height:1.7">故障机理 / 触发条件 / 典型表现 / 源码审查映射点 / 测试拦截建议 / 实证案例</div>
      </div>
      <div style="background:#fff;padding:16px">
        <div class="mono-sm" style="color:#2c5282;font-weight:700">L2 · 怎么测</div>
        <div style="font-size:13px;font-weight:620;margin:6px 0 5px">${det.length} 条判据真源</div>
        <div style="font-size:11.5px;color:var(--ink-3);line-height:1.7">axes 构造轴 / oracle 判决器 / signal 信号 / min_cases 最少用例 / constructor / judge / kill</div>
      </div>
      <div style="background:#fff;padding:16px">
        <div class="mono-sm" style="color:#5b3d8f;font-weight:700">L3 · 观测失效</div>
        <div style="font-size:13px;font-weight:620;margin:6px 0 5px">${M.nL3} 条失效模式</div>
        <div style="font-size:11.5px;color:var(--ink-3);line-height:1.7">按 oracle 类别组织，不属于任何单条模式——失效机理属于观测手段自身</div>
      </div>
    </div>
  </div>

  <div class="sec-h"><h3>L2 · 判据真源</h3><div class="line"></div><span class="note">点击展开 constructor / judge / kill</span></div>
  ${l2}

  <div class="sec-h"><h3>L3 · oracle 失效清单</h3><div class="line"></div>
    <span class="note">${M.nL3} 条 · ${orcKeys.length} 类 · 来源 ${esc(D.l3.source || "")}</span></div>
  <div class="note-box" style="margin-bottom:14px">
    ${md(D.l3.note || "")}
  </div>
  <div class="l3">${l3}</div>`;
};

/* ---------------- compositions ---------------- */
render.compositions = function () {
  const comps = D.compositions || [];
  let html = `
  <div class="ptitle"><h2>组合故障</h2><span class="tag">${comps.length} 组</span></div>
  <p class="pdesc">跨调用的复合缺陷无法用单条模式区分——例如「tiling 状态残留」与「脏数据」在现象上几乎一致，
    必须靠<b>同一 executor 换 shape 重放 + 毒化 workspace</b> 这类实验设计才分得开。</p>`;
  if (!comps.length) {
    html += `<div class="empty"><div class="big">∅</div><p>暂无组合条目</p></div>`;
  } else {
    comps.forEach(c => {
      const exp = c.next_experiment || {};
      const acts = (exp.actions || []).map(a => a.type).join(" → ");
      html += `<div class="comp">
        <div class="comp-h"><span class="cid3">${c.id}</span></div>
        <div class="comp-m">${c.members.map(m => {
          const p = byId[m];
          return `<span class="pm" data-fp="${m}" style="cursor:pointer">${m}${p ? " · " + esc(p.name).slice(0, 22) : ""}</span>`;
        }).join('<span style="color:var(--ink-4);font-size:11px">＋</span>')}</div>
        <div class="comp-rat">${md(c.rationale)}</div>
        ${acts ? `<div class="comp-exp">实验序列 · ${esc(acts)}${exp.schedule ? ` ｜ 调度 ${esc(exp.schedule.mode || "")} ${esc((exp.schedule.sequence || []).join("→"))}` : ""}</div>` : ""}
      </div>`;
    });
  }
  $("#v-compositions").innerHTML = html;
};

/* ---------------- secondary oracle（第二判据，v6.19） ---------------- */
render.secondary = function () {
  const SEC = D.secondary;
  if (!SEC || !SEC.patterns) {
    $("#v-secondary").innerHTML = `<div class="ptitle"><h2>第二判据</h2></div>
      <div class="empty"><div class="big">∅</div><p>本库版本未包含第二判据数据</p></div>`;
    return;
  }
  const kinds = SEC.kinds || {};
  const withSec = P.filter(p => p.secondary);
  const kindCount = {};
  withSec.forEach(p => { const k = p.secondary.kind; kindCount[k] = (kindCount[k] || 0) + 1; });

  let kindHtml = "";
  Object.keys(kinds).forEach(k => {
    if (!kindCount[k]) return;
    kindHtml += `<div class="kindbox">
      <div class="kn">${k} · ${kindCount[k]} 条</div>
      <div class="kd">${md(kinds[k])}</div></div>`;
  });

  let list = withSec.slice().sort((a, b) =>
    b.score - a.score || a.id.localeCompare(b.id)).map(p => {
    const s = p.secondary;
    const rels = (s.relations || []).map(r => `
      <div class="rel-item">
        <div class="rh"><span class="rid3">${esc(r.id || "")}</span><span class="rnm">${esc(r.name || "")}</span></div>
        ${r.statement ? `<div class="rv">${md(r.statement)}</div>` : ""}
        ${r.kill ? `<div class="rk"><b>能杀死什么</b> · ${md(r.kill)}</div>` : ""}
        ${r.how ? `<div class="rhw">怎么测 · ${md(r.how)}</div>` : ""}
      </div>`).join("");
    return `<div class="sec" data-sec="${p.id}">
      <div class="sec-h2">
        <span class="fpid2">${p.id}</span>
        <span class="nm">${esc(p.name)}</span>
        <span class="kd2">${esc(s.kind || "")}</span>
        <span class="arw3">▶</span>
      </div>
      <div class="sec-b">
        ${s.why ? `<div class="why">${md(s.why)}</div>` : ""}
        ${rels}
      </div>
    </div>`;
  }).join("");

  const missing = P.filter(p => !p.secondary);

  $("#v-secondary").innerHTML = `
  <div class="ptitle"><h2>第二判据</h2><span class="tag">${withSec.length} / ${P.length} 条</span>
    <span class="tag">6 类关系</span></div>
  <p class="pdesc">每条模式除了 L2 的主判据，还要求一个<b>在不同失效机制上独立成立</b>的第二判据：
    任一侧报异常即升级为必须实测，两侧都过才算判据有效。这是把「判据可信度」本身也当成被测对象的做法。</p>
  <div class="note-box" style="margin-bottom:18px">
    当前 <b>${withSec.length} / ${P.length}</b> 条模式已补第二判据（数据源 <code>fault_patterns_secondary_oracle.json</code> v${esc(M.secondaryVersion || "")}），
    关系式共 <b>${withSec.reduce((n, p) => n + ((p.secondary.relations || []).length), 0)}</b> 条。
  </div>
  <div class="kindgrid">${kindHtml}</div>
  <div class="sec-h"><h3>逐模式关系式</h3><div class="line"></div>
    <span class="note">点击展开 · 按 S×O 排序</span></div>
  ${list}
  ${missing.length ? `<div class="note-box" style="margin-top:16px">
    <b>尚未补第二判据的 ${missing.length} 条</b>：${missing.map(p =>
      `<span class="cand" data-fp="${p.id}" style="margin:3px 3px 0 0"><span class="cid">${p.id}</span></span>`).join("")}
  </div>` : ""}`;
};

/* ---------------- method ---------------- */
render.method = function () {
  const R = M.riskRubric || {};
  const B = M.businessImpact || {};
  const V = M.applicabilityVocab || {};
  $("#v-method").innerHTML = `
  <div class="ptitle"><h2>库标准</h2><span class="tag">收录 · 定级 · 消费</span></div>
  <p class="pdesc">参照 CWE（条目化弱点结构）、FMEA / IEC 60812（严重度×发生度）、ODC（正交缺陷分类）、IEEE 1044 设计。</p>

  <div class="sec-h"><h3>风险定级</h3><div class="line"></div></div>
  <div class="grid2">
    <div class="card"><div class="card-h"><h4>严重度 S</h4></div><div class="card-b">
      ${Object.keys(R.severity || {}).map(k => `<div class="kv"><div class="kk">${k}</div><div class="vv">${md(R.severity[k])}</div></div>`).join("")}
    </div></div>
    <div class="card"><div class="card-h"><h4>发生度 O 与风险 = S×O</h4></div><div class="card-b">
      ${Object.keys(R.occurrence || {}).filter(k => k !== "note").map(k => `<div class="kv"><div class="kk">${k}</div><div class="vv">${md(R.occurrence[k])}</div></div>`).join("")}
      <div class="kv"><div class="kk">风险档</div><div class="vv">${md(R.risk)}</div></div>
    </div></div>
  </div>

  <div class="sec-h"><h3>业务影响轴 B（与 S×O 正交）</h3><div class="line"></div>
    <span class="note">只决定修复优先级建议，不参与定级</span></div>
  <div class="card"><div class="card-b">
    ${Object.keys(B).filter(k => /^B\d/.test(k)).map(k => `<div class="kv"><div class="kk">${k}</div><div class="vv">${md(B[k])}</div></div>`).join("")}
  </div></div>

  ${M.detectabilityRubric ? `<div class="sec-h"><h3>可检出性 D（FMEA 的 Detection 维度）</h3><div class="line"></div>
    <span class="note">不改 S×O 语义，只产出 priority = S×O×D 作为「先查哪条」的排序键</span></div>
  <div class="card"><div class="card-b">
    ${["D1", "D2", "D3"].map(k => M.detectabilityRubric[k] ? `<div class="kv"><div class="kk"><span class="dcell ${k}">${k}</span></div><div class="vv">${md(M.detectabilityRubric[k])}</div></div>` : "").join("")}
    ${M.detectabilityRubric.principle ? `<div class="kv"><div class="kk">取值纪律</div><div class="vv">${md(M.detectabilityRubric.principle)}</div></div>` : ""}
  </div></div>` : ""}

  <div class="sec-h"><h3>适用声明取值闭集</h3><div class="line"></div></div>
  <div class="card"><div class="card-b">
    ${["repos", "sides", "carriers", "depth", "trigger"].map(k => {
      const vals = V[k];
      if (!vals) return "";
      const arr = Array.isArray(vals) ? vals : Object.keys(vals);
      return `<div class="kv"><div class="kk">${k}</div><div class="vv sig-wrap">${arr.map(v => `<span class="sig kw">${esc(v)}</span>`).join("")}</div></div>`;
    }).join("")}
  </div></div>

  <div class="sec-h"><h3>消费方</h3><div class="line"></div></div>
  <div class="card"><div class="card-b"><div class="sig-wrap">
    ${(M.consumers || []).map(c => `<span class="sig">${esc(c)}</span>`).join("")}
  </div></div></div>

  <div class="sec-h"><h3>规模与门禁</h3><div class="line"></div></div>
  <div class="card"><div class="card-b">
    <div class="kv"><div class="kk">库版本</div><div class="vv">v${M.version}（${M.updated}）｜ 真源 ${esc(M.sourceVersion || "")}</div></div>
    <div class="kv"><div class="kk">规模</div><div class="vv">${P.length} 条模式 / ${M.cats.length} 类 / ${C.length} 条案例 / ${M.nSkills} 个 skill / ${M.nEvals} 份评测集</div></div>
    <div class="kv"><div class="kk">结构</div><div class="vv">${esc(M.layout || "")}</div></div>
    <div class="kv"><div class="kk">一致性门禁</div><div class="vv">${esc(M.gates || "")} —— 判据 <code>ERROR=0</code></div></div>
    <div class="kv"><div class="kk">L2 判据层</div><div class="vv">v${esc(M.detectVersion || "")}（${esc(M.detectUpdated || "")}）｜ ${M.nL3} 条 L3 失效</div></div>
  </div></div>`;
};

/* ---------------- drawer ---------------- */
const drawer = $("#drawer"), mask = $("#mask"), dh = $("#dh"), db = $("#db");

function closeDrawer() {
  drawer.classList.remove("on");
  mask.classList.remove("on");
  document.body.style.overflow = "";
}
mask.addEventListener("click", closeDrawer);

function openPattern(fp) {
  const p = byId[fp];
  if (!p) return;
  const b = p.body || {};
  const cases = C.filter(c => c.fp === fp);
  const det = p.detect;

  const fld = (n, title, val, cls, sub) => val ? `
    <div class="fld">
      <div class="fld-h"><span class="n">${n}</span><h4>${title}</h4>${sub ? `<span class="sub">${sub}</span>` : ""}</div>
      <div class="fld-b ${cls || ""}">${md(val)}</div>
    </div>` : "";

  const sigList = (arr, cls) => arrOf(arr).length
    ? `<div class="sig-wrap">${arrOf(arr).map(s => {
        const k = sigKind(s);
        return `<span class="sig ${cls || ""} ${k === "must" ? "must" : ""}" data-copy="${esc(sigText(s))}" title="${esc(typeof s === "object" && s ? (s.note || s.files || "") : "点击复制")}">${esc(sigText(s))}</span>`;
      }).join("")}</div>`
    : "";

  let subtypesHtml = "";
  if (arrOf(p.subtypes).length) {
    subtypesHtml = `<div class="fld">
      <div class="fld-h"><span class="n">⌗</span><h4>子型划分</h4><span class="sub">${p.subtypes.length} 项</span></div>
      <div class="fld-b cool">${arrOf(p.subtypes).map(s => `<div style="display:flex;gap:8px;margin-bottom:6px">
        <code style="flex:none">${esc(s.id)}</code><span>${esc(s.name)}</span></div>`).join("")}</div>
    </div>`;
  }

  let detHtml = "";
  if (det) {
    const dt = p.detectability;
    detHtml = `<div class="fld">
      <div class="fld-h"><span class="n">L</span><h4>L2 判据层</h4><span class="sub">axes / oracle / judge / kill</span></div>
      <div class="fld-b" style="padding:12px">
        <div class="axes" style="margin-bottom:10px">
          ${(det.axes || []).map(a => `<span class="ax">${a}</span>`).join("")}
          ${(det.oracle || []).map(o => `<span class="orc">${o}</span>`).join("")}
          <span class="mchip">signal <b>${det.signal || "—"}</b></span>
          <span class="mchip">min_cases <b>${det.min_cases || "—"}</b></span>
          ${dt ? `<span class="dcell ${esc(dt.level || "")}">${esc(dt.level || "")}</span>` : ""}
        </div>
        <div class="dgrid">
          <div class="dbox"><div class="dh2">constructor</div><div class="dv">${md(det.constructor)}</div></div>
          <div class="dbox"><div class="dh2">judge</div><div class="dv">${md(det.judge)}</div></div>
          <div class="dbox" style="grid-column:1/-1;background:#fffdfa;border-color:#e6d9c3"><div class="dh2">kill — 缺陷成立的判据</div><div class="dv">${md(det.kill)}</div></div>
        </div>
        ${dt ? `<div class="prio">
          <span class="pl">可检出性</span>
          <span class="pv">${esc(dt.level || "")} · D${esc(dt.d || "")}</span>
          <span class="pf">priority = S${p.s}×O${p.o}×D${esc(dt.d || "")} = ${esc(dt.priority != null ? dt.priority : "—")}</span>
        </div>
        ${dt && dt.why ? `<div style="margin-top:7px;font-size:11.5px;color:var(--ink-3)">${md(dt.why)}</div>` : ""}` : ""}
      </div>
    </div>`;
  }

  let secHtml = "";
  if (p.secondary) {
    const s = p.secondary;
    const kinds = (M.secondaryKinds || {});
    secHtml = `<div class="fld">
      <div class="fld-h"><span class="n">⊘</span><h4>第二判据</h4><span class="sub">${esc(s.kind || "")}</span></div>
      <div class="fld-b" style="padding:12px">
        ${kinds[s.kind] ? `<div style="font-size:11px;color:#5b3d8f;font-family:var(--mono);margin-bottom:8px">${esc(s.kind)} · ${esc(kinds[s.kind]).slice(0, 60)}</div>` : ""}
        ${s.why ? `<div class="why">${md(s.why)}</div>` : ""}
        ${(s.relations || []).map(r => `<div class="rel-item">
          <div class="rh"><span class="rid3">${esc(r.id || "")}</span><span class="rnm">${esc(r.name || "")}</span></div>
          ${r.statement ? `<div class="rv">${md(r.statement)}</div>` : ""}
          ${r.kill ? `<div class="rk"><b>能杀死什么</b> · ${md(r.kill)}</div>` : ""}
          ${r.how ? `<div class="rhw">怎么测 · ${md(r.how)}</div>` : ""}
        </div>`).join("")}
      </div>
    </div>`;
  }

  let caseHtml = "";
  if (cases.length) {
    caseHtml = `<div class="fld">
      <div class="fld-h"><span class="n">❐</span><h4>实证案例</h4><span class="sub">${cases.length} 条 · 点击展开</span></div>
      ${cases.map((c, i) => `<div class="dcase" data-dcase="${c.id}">
        <div class="dcase-h">
          <span class="cid2">${String(i + 1).padStart(2, "0")}</span>
          <span class="t2">${esc(c.title)}</span>
          ${(c.anchors || []).length ? `<span class="badge-v">锚点</span>` : ""}
          <span class="arw2">▶</span>
        </div>
        <div class="dcase-b">
          ${c.trigger ? `<div class="kv"><div class="kk">触发条件</div><div class="vv">${md(c.trigger)}</div></div>` : ""}
          ${c.root ? `<div class="kv"><div class="kk">根因</div><div class="vv">${md(c.root)}</div></div>` : ""}
          ${c.repro ? `<div class="kv"><div class="kk">最小复现</div><div class="vv">${md(c.repro)}</div></div>` : ""}
          ${c.criteria && c.criteria.check && c.criteria.check.length ? `<div class="kv"><div class="kk">可执行判据</div><div class="vv"><ul>${c.criteria.check.map(x => `<li>${md(x)}</li>`).join("")}</ul></div></div>` : ""}
          ${c.code ? `<div class="kv"><div class="kk">修复范式</div><pre class="code">${esc(c.code)}</pre></div>` : ""}
          ${(c.anchors || []).length ? (c.anchors || []).map(a => `<div class="kv"><div class="kk">真实锚点 · ${esc(a.repo || "")} @ ${esc(a.commit || "")}</div>
            <div class="vv"><code>${esc(a.file || "")}${a.lines ? ":" + esc(a.lines) : ""}</code><br>${md(a.note || "")}</div></div>`).join("") : ""}
          ${c.evidence ? `<div class="kv"><div class="kk">实证</div><div class="vv">${md(c.evidence)}</div></div>` : ""}
        </div>
      </div>`).join("")}
    </div>`;
  }

  let relHtml = "";
  if (arrOf(p.related).length) {
    relHtml = `<div class="fld">
      <div class="fld-h"><span class="n">↔</span><h4>关联模式</h4></div>
      <div class="rel-wrap">${arrOf(p.related).map(r => {
        const q = byId[r];
        return `<span class="rel" data-fp="${r}"><span class="rid2">${r}</span>${q ? `<span style="color:var(--ink-3);font-size:11px">${esc(q.name).slice(0, 18)}</span>` : ""}</span>`;
      }).join("")}</div>
    </div>`;
  }

  const sigBlock = (arrOf(p.signatures).length || arrOf(p.keywords).length || arrOf(p.broad).length || arrOf(p.absence).length || arrOf(p.logSig).length) ? `
    <div class="fld">
      <div class="fld-h"><span class="n">⌕</span><h4>检测签名与关键词</h4><span class="sub">点击复制</span></div>
      <div class="fld-b" style="padding:12px">
        ${arrOf(p.signatures).length ? `<div class="kk" style="font-size:10.5px;color:#9b0009;font-weight:600;margin-bottom:6px">判别性指纹 · 命中即候选（${arrOf(p.signatures).length}）</div>${sigList(p.signatures)}` : ""}
        ${arrOf(p.broad).length ? `<div class="kk" style="font-size:10.5px;color:#8a5200;font-weight:600;margin:11px 0 6px">宽泛签名 · 仅定位（${arrOf(p.broad).length}）</div>${sigList(p.broad)}` : ""}
        ${arrOf(p.absence).length ? `<div class="kk" style="font-size:10.5px;color:#2c5282;font-weight:600;margin:11px 0 6px">缺失型签名 · 找「该有却没有」（${arrOf(p.absence).length}）</div>${sigList(p.absence)}` : ""}
        ${arrOf(p.logSig).length ? `<div class="kk" style="font-size:10.5px;color:#5b3d8f;font-weight:600;margin:11px 0 6px">日志签名（${arrOf(p.logSig).length}）</div>${sigList(p.logSig)}` : ""}
        ${arrOf(p.keywords).length ? `<div class="kk" style="font-size:10.5px;color:#6b5b33;font-weight:600;margin:11px 0 6px">审查关键词 · 命中不产生候选，仅提示人审（${arrOf(p.keywords).length}）</div>${sigList(p.keywords, "kw")}` : ""}
        ${p.waiver ? `<div style="margin-top:11px;font-size:11px;color:var(--ink-3);border-top:1px dashed var(--line);padding-top:9px">产出豁免 · ${esc(p.waiver)}</div>` : ""}
      </div>
    </div>` : "";

  const evHtml = arrOf(p.evidence).length ? `
    <div class="fld">
      <div class="fld-h"><span class="n">✓</span><h4>实证索引</h4><span class="sub">${arrOf(p.evidence).length} 条</span></div>
      <div class="ev-list">${arrOf(p.evidence).map((e, i) => `<div class="ev"><span class="num">${i + 1}</span><div class="tx">${md(e)}</div></div>`).join("")}</div>
    </div>` : `<div class="fld"><div class="fld-h"><span class="n">✓</span><h4>实证状态</h4></div>
      <div class="fld-b warm">检索无对应实证 —— 属方法学型条目，证据待补充；风险评级已如实标注。</div></div>`;

  dh.innerHTML = `
    <div class="dh-top">
      <span class="fpid">${p.id}</span>
      <span class="cat">${catDot(p.cat)}${p.catZh}</span>
      <span style="margin-left:auto;display:flex;gap:6px;align-items:center">
        ${riskBadge(p)}
      </span>
    </div>
    <h2>${esc(p.name)}</h2>
    <div class="dh-meta">
      <span class="mchip">负载 <b>${p.depth}</b></span>
      <span class="mchip">触发 <b>${esc(p.triggerZh || p.trigger)}</b></span>
      <span class="mchip">侧别 <b>${esc(arrOf(p.sides).join(" / "))}</b></span>
      <span class="mchip">仓 <b>${esc(arrOf(p.repos).join(" / "))}</b></span>
      <span class="mchip">载体 <b>${esc(arrOf(p.carriers).join(" / "))}</b></span>
      <span class="mchip">案例 <b>${cases.length}</b></span>
    </div>
    <button class="dh-x" id="dx">✕</button>`;

  db.innerHTML = `
    ${fld(1, "故障机理", b.mechanism)}
    ${fld(2, "触发条件", b.conditions)}
    ${fld(3, "典型表现", b.manifest, "warm")}
    ${p.trigger ? `<div class="fld"><div class="fld-h"><span class="n">⌗</span><h4>适用声明</h4></div>
      <div class="fld-b cool">${esc(b.applicability_text || "")}</div></div>` : ""}
    ${subtypesHtml}
    ${fld(4, "源码审查映射点", b.mapping)}
    ${sigBlock}
    ${detHtml}
    ${secHtml}
    ${fld(5, "测试拦截建议", b.intercept, "cool")}
    ${caseHtml || evHtml}
    ${relHtml}
    <div class="fld"><div class="fld-h"><span class="n">i</span><h4>元数据</h4></div>
      <div class="fld-b" style="font-size:12px">${esc(b.meta_info || "")}
        ${p.file ? `<div style="margin-top:8px;padding-top:8px;border-top:1px dashed var(--line);font-family:var(--mono);font-size:10.5px;color:var(--ink-4)">${esc(p.file)}</div>` : ""}
        ${p.tocEvidence ? `<div style="margin-top:5px;font-size:11.5px;color:var(--ink-3)">总览表实证列 · ${esc(p.tocEvidence)}</div>` : ""}
      </div></div>`;

  drawer.classList.add("on");
  mask.classList.add("on");
  document.body.style.overflow = "hidden";
  db.scrollTop = 0;

  $("#dx").onclick = closeDrawer;
  db.querySelectorAll(".dcase-h").forEach(h => {
    h.addEventListener("click", () => h.parentElement.classList.toggle("open"));
  });
}

function openCase(cid) {
  const c = C.find(x => x.id === cid);
  if (!c) return;
  const p = byId[c.fp];
  dh.innerHTML = `
    <div class="dh-top">
      <span class="fpid">${c.fp}</span>
      <span class="cat">${p ? catDot(p.cat) + p.catZh : ""}</span>
      <span style="margin-left:auto;display:flex;gap:6px">${p ? riskBadge(p) : ""}</span>
    </div>
    <h2>${esc(c.title)}</h2>
    <div class="dh-meta">
      <span class="mchip">案例 <b>${c.id}</b></span>
      ${c.subtype ? `<span class="mchip">子型 <b>${esc(c.subtype)}</b></span>` : ""}
      ${(c.issues || []).map(i => `<span class="mchip iss">${esc(i)}</span>`).join("")}
      ${(c.anchors || []).length ? `<span class="mchip" style="background:#eaf7ee;border-color:#cfe9d8;color:#1a7f45">真实锚点 ${c.anchors.length}</span>` : ""}
    </div>
    <button class="dh-x" id="dx">✕</button>`;
  db.innerHTML = `
    ${c.trigger ? `<div class="fld"><div class="fld-h"><span class="n">1</span><h4>触发条件</h4></div><div class="fld-b">${md(c.trigger)}</div></div>` : ""}
    ${c.root ? `<div class="fld"><div class="fld-h"><span class="n">2</span><h4>根因</h4></div><div class="fld-b warm">${md(c.root)}</div></div>` : ""}
    ${c.repro ? `<div class="fld"><div class="fld-h"><span class="n">3</span><h4>最小复现</h4></div><div class="fld-b cool">${md(c.repro)}</div></div>` : ""}
    ${c.criteria && c.criteria.check && c.criteria.check.length ? `<div class="fld"><div class="fld-h"><span class="n">4</span><h4>可执行判据</h4></div>
      <div class="fld-b"><ul>${c.criteria.check.map(x => `<li>${md(x)}</li>`).join("")}</ul></div></div>` : ""}
    ${c.code ? `<div class="fld"><div class="fld-h"><span class="n">5</span><h4>修复范式</h4></div><pre class="code">${esc(c.code)}</pre></div>` : ""}
    ${(c.anchors || []).length ? `<div class="fld"><div class="fld-h"><span class="n">6</span><h4>真实修复锚点</h4><span class="sub">文件 + 行号 + commit</span></div>
      ${c.anchors.map(a => `<div class="fld-b" style="margin-bottom:8px">
        <div class="mono-sm" style="margin-bottom:5px">${esc(a.repo || "")} @ ${esc(a.commit || "")} ｜ ${esc(a.issue || "")}</div>
        <code>${esc(a.file || "")}${a.lines ? ":" + esc(a.lines) : ""}</code>
        <div style="margin-top:7px">${md(a.note || "")}</div></div>`).join("")}</div>` : ""}
    ${c.evidence ? `<div class="fld"><div class="fld-h"><span class="n">7</span><h4>实证</h4></div><div class="fld-b">${md(c.evidence)}</div></div>` : ""}
    ${c.skill ? `<div class="fld"><div class="fld-h"><span class="n">8</span><h4>对应 skill</h4></div><div class="fld-b"><code>${esc(c.skill)}</code></div></div>` : ""}
    <div class="fld"><div class="fld-h"><span class="n">↔</span><h4>所属模式</h4></div>
      <div class="rel-wrap"><span class="rel" data-fp="${c.fp}"><span class="rid2">${c.fp}</span>${p ? `<span style="color:var(--ink-3);font-size:11px">${esc(p.name).slice(0, 24)}</span>` : ""}</span></div></div>`;
  drawer.classList.add("on");
  mask.classList.add("on");
  document.body.style.overflow = "hidden";
  db.scrollTop = 0;
  $("#dx").onclick = closeDrawer;
}

/* ---------------- global delegation ---------------- */
document.addEventListener("click", e => {
  const t = e.target;

  const fpEl = t.closest("[data-fp]");
  if (fpEl) { openPattern(fpEl.dataset.fp); return; }

  const caseEl = t.closest("[data-case]");
  if (caseEl) { openCase(caseEl.dataset.case); return; }

  const copyEl = t.closest("[data-copy]");
  if (copyEl) {
    const v = copyEl.dataset.copy;
    if (navigator.clipboard) navigator.clipboard.writeText(v).then(() => toast("已复制签名")).catch(() => toast("复制失败"));
    else toast("当前环境不支持剪贴板");
    return;
  }

  const soEl = t.closest("[data-so]");
  if (soEl) {
    const ids = stats.matrix[soEl.dataset.so] || [];
    if (!ids.length) { toast("该组合下没有模式"); return; }
    S.so = soEl.dataset.so; S.cat = "all"; S.lvl = "all"; S.depth = "all"; S.trig = "all"; S.q = "";
    $("#q").value = "";
    go("patterns"); render.patterns(); $("#v-patterns").dataset.done = "1"; applyFilters();
    return;
  }

  const catEl = t.closest("[data-cat]");
  if (catEl) {
    S.cat = catEl.dataset.cat; S.lvl = "all"; S.depth = "all"; S.so = null; S.trig = "all";
    go("patterns"); render.patterns(); $("#v-patterns").dataset.done = "1"; applyFilters();
    return;
  }

  const trigEl = t.closest("[data-trig]");
  if (trigEl) {
    S.trig = trigEl.dataset.trig; S.cat = "all"; S.lvl = "all"; S.depth = "all"; S.so = null;
    go("patterns"); render.patterns(); $("#v-patterns").dataset.done = "1"; applyFilters();
    return;
  }

  const jumpEl = t.closest("[data-jump]");
  if (jumpEl) {
    const card = document.querySelector(`.tcard[data-t="${jumpEl.dataset.jump}"]`);
    if (card) {
      document.querySelectorAll(".tcard").forEach(c => c.classList.remove("open"));
      card.classList.add("open");
      card.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }

  const tHead = t.closest(".tcard-h");
  if (tHead) { tHead.parentElement.classList.toggle("open"); return; }

  const l2 = t.closest("[data-l2] .dcase-h");
  if (l2) { l2.parentElement.classList.toggle("open"); return; }

  const secH = t.closest("[data-sec] .sec-h2");
  if (secH) { secH.parentElement.classList.toggle("open"); return; }
});

/* ---------------- search ---------------- */
const qEl = $("#q");
let qTimer;
qEl.addEventListener("input", () => {
  clearTimeout(qTimer);
  qTimer = setTimeout(() => {
    const v = qEl.value.trim();
    S.q = v; S.caseQ = v;
    if (S.view === "patterns") applyFilters();
    else if (S.view === "cases") applyCaseFilters();
    else {
      go("patterns"); render.patterns(); $("#v-patterns").dataset.done = "1"; applyFilters();
    }
  }, 120);
});
document.addEventListener("keydown", e => {
  if (e.key === "/" && document.activeElement !== qEl) { e.preventDefault(); qEl.focus(); qEl.select(); }
  if (e.key === "Escape") {
    if (drawer.classList.contains("on")) closeDrawer();
    else if (document.activeElement === qEl) { qEl.blur(); qEl.value = ""; S.q = ""; S.caseQ = ""; if (S.view === "patterns") applyFilters(); if (S.view === "cases") applyCaseFilters(); }
  }
});

/* ---------------- boot ---------------- */
window.__FP_APP__ = { patterns: P, cases: C, meta: M, openPattern, openCase };
const h = (location.hash || "#/overview").replace("#/", "");
go(TITLES[h] ? h : "overview");
})();
