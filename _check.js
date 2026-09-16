
const D = window.__DATA__;
const $ = s => document.querySelector(s);
const SKILL = ["RB","WR","TE"], SIDE = ["QB","DST","K"];
const STARTABLE = {QB:12, RB:24, WR:24, TE:12, DST:12, K:12};

let scale = "week", team = D.myTeam, pos = "ALL", owner = "ALL", q = "", hideDismissed = false;
let sortKey = "sk", sortDir = 1;

const sk = (p) => p.s[scale].sk;
const pn = (p) => p.s[scale].pn;
const mv = (p) => p.m[scale];
const mineOf = () => D.players.filter(p => p.own === team);
const fas    = () => D.players.filter(p => !p.own);
const others = () => D.players.filter(p => p.own && p.own !== team);

// nulls always sink, whichever direction the caller sorts
function by(fn){
  return (a,b)=>{
    const x = fn(a), y = fn(b);
    if (x==null && y==null) return 0;
    if (x==null) return 1;
    if (y==null) return -1;
    return x - y;
  };
}

const dcell = d => (d === null || d === undefined)
  ? '<span class="delta flat">--</span>'
  : `<span class="delta ${d>0?'up':d<0?'down':'flat'}">${d>0?'+':''}${d}</span>`;
const faceFor = p => p.pid && D.photos[p.pid]
  ? `<img class="face" src="img/${p.pid}.png" alt="" loading="lazy" width="26" height="26">`
  : "";
const nameCell = p => `${faceFor(p)}${p.n}${p.inj?` <span class="inj">${p.inj}</span>`:''}${markDot(p)}`;
const ownerCell = p => p.own
  ? `<span class="owner">${p.own}</span>` : '<span class="fa">free agent</span>';

/* Rank by the same number a column shows. The positional and flex boards are
   separate expert panels and can disagree (WR28 can outrank WR27 overall), so
   ordering skill players by positional rank would print a number that isn't
   actually the worst. */
const orderFor = position => SKILL.includes(position) ? sk : pn;

function worstAt(position){
  const list = mineOf().filter(p => p.p === position && !p.ir)
                       .sort(by(orderFor(position)));
  return list.length ? list[list.length - 1] : null;
}
function bestFaAt(position){
  const list = fas().filter(p => p.p === position && orderFor(position)(p) != null)
                    .sort(by(orderFor(position)));
  return list.length ? list[0] : null;
}

function renderRoster(){
  const r = mineOf().sort((a,b)=>{
    const x = sk(a), y = sk(b);
    if (x!=null && y!=null) return x-y;
    if (x!=null) return -1;
    if (y!=null) return 1;
    return a.p.localeCompare(b.p) || ((pn(a)??9999) - (pn(b)??9999));
  });
  $("#rbody").innerHTML = r.map(p=>`<tr class="mine${markClass(p)}" data-k="${p.k}">
    <td class="num r">${sk(p) ?? '--'}</td>
    <td class="pname">${nameCell(p)}</td>
    <td class="num">${p.p}</td><td class="num">${p.t}</td><td class="num">${p.o||''}</td>
    <td class="num r">${p.s[scale].pr || 'unranked'}</td>
    <td class="num r">${p.s.draft.pr || '--'}</td>
    <td class="r">${dcell(mv(p))}</td>
    <td class="num">${p.sl||''}</td>
  </tr>`).join("") || `<tr><td colspan="9" class="empty">No players.</td></tr>`;
  $("#rostername").textContent = team;
}

function renderWaiver(){
  const worst = {};
  for (const position of SKILL.concat(SIDE)) worst[position] = worstAt(position);

  const skillFa = fas().filter(p => SKILL.includes(p.p) && sk(p) != null
                        && !(hideDismissed && markOf(p) === "dismiss"))
                       .sort(by(sk)).slice(0, 35);
  $("#wbody").innerHTML = skillFa.map(p=>{
    const w = worst[p.p];
    const up = w && sk(p) != null && sk(w) != null && sk(p) < sk(w);
    return `<tr class="${markClass(p).trim()}" data-k="${p.k}">
      <td class="num r ${up?'up-yes':''}">${sk(p) ?? '--'}</td>
      <td class="pname">${nameCell(p)}</td>
      <td class="num">${p.p}</td><td class="num">${p.t}</td><td class="num">${p.o||''}</td>
      <td class="num r">${p.s[scale].pr||'--'}</td>
      <td class="r">${dcell(mv(p))}</td>
      <td>${w ? w.n+' <span class="owner">('+(w.s[scale].pr||'unranked')+')</span>' : '--'}</td>
      <td class="num r">${w && sk(w) != null ? sk(w) : '--'}</td>
    </tr>`;
  }).join("") || `<tr><td colspan="9" class="empty">No ranked free agents.</td></tr>`;

  $("#sidetables").innerHTML = SIDE.map(position=>{
    const w = worst[position];
    const rows = fas().filter(p => p.p === position && pn(p) != null)
                      .sort(by(pn)).slice(0,5).map(p=>{
      const up = w && pn(w) != null && pn(p) < pn(w);
      return `<tr class="${markClass(p).trim()}" data-k="${p.k}">
        <td class="num r ${up?'up-yes':''}">${p.s[scale].pr||'--'}</td>
        <td class="pname">${nameCell(p)}</td>
        <td class="num">${p.t}</td>
        <td>${w ? w.n+' <span class="owner">('+(w.s[scale].pr||'unranked')+')</span>' : '--'}</td>
      </tr>`;
    }).join("") || `<tr><td colspan="4" class="empty">None available.</td></tr>`;
    const label = position==='DST' ? 'Defense' : position==='K' ? 'Kicker' : 'Quarterback';
    return `<div class="tablewrap"><h3>${label} &mdash; best available</h3>
      <table><thead><tr><th class="r">Rank</th><th>Player</th><th>Tm</th>
      <th>Worst on this roster</th></tr></thead><tbody>${rows}</tbody></table></div>`;
  }).join("");
}

function panelRow(p, note){
  return `<div class="row${markClass(p)}" data-k="${p.k}" role="button" tabindex="0">
    ${faceFor(p)}<span class="dname">${p.n}</span>
    <span class="tag">${p.p} ${p.t}</span>${p.inj?`<span class="inj">${p.inj}</span>`:''}
    ${dcell(mv(p))}
    <span class="move">${p.s.draft.pr||'undrafted'} <span class="a">&rarr; ${p.s[scale].pr||'unranked'}</span>${note?'  &middot; '+note:''}</span>
  </div>`;
}

function renderPanels(){
  const mine = mineOf(), fa = fas(), rest = others();

  const sell = mine.filter(p => p.s.draft.pn != null && (mv(p) == null || mv(p) < -8))
                   .sort((a,b)=>(mv(a)??-9999)-(mv(b)??-9999));

  const buy = rest.filter(p => mv(p) != null && mv(p) > 8 && pn(p) != null
                    && pn(p) <= (STARTABLE[p.p]||24) * D.size / 8)
                  .sort((a,b)=>mv(b)-mv(a)).slice(0,12);

  const adds = [];
  for (const position of ["QB","RB","WR","TE","DST","K"]){
    const w = worstAt(position);
    if (!w) continue;
    const wn = pn(w);
    fa.filter(p => p.p === position && pn(p) != null && (wn == null || pn(p) < wn))
      .sort(by(pn)).slice(0,3)
      .forEach(p => adds.push([p, `${w.n} (${w.s[scale].pr || 'unranked'})`]));
  }

  const drops = [];
  mine.filter(p=>!p.ir).sort(by(pn)).reverse().forEach(p=>{
    const b = bestFaAt(p.p);
    if (b && (pn(p) == null || pn(p) > pn(b)))
      drops.push([p, `${b.n} (${b.s[scale].pr})`]);
  });

  const stash = mine.filter(p=>p.ir);

  const put = (sel, items, empty) => {
    const el = $(sel);
    el.innerHTML = items.length
      ? items.map(it => Array.isArray(it) ? panelRow(it[0], it[1]) : panelRow(it, null)).join("")
      : `<div class="empty">${empty}</div>`;
  };
  put("#p-sell", sell, "Nothing flagged.");
  put("#p-buy", buy, "Nothing flagged.");
  put("#p-adds", adds, "No free agent beats this roster's weakest starter.");
  put("#p-drops", drops, "Everyone on this roster beats the best free agent.");
  put("#p-stash", stash, "Nobody on IR.");
  document.querySelectorAll(".teamname").forEach(el => el.textContent = team);
}

function val(p, k){
  if (k === "sk") return sk(p);
  if (k === "pn") return pn(p);
  if (k === "dn") return p.s.draft.pn;
  if (k === "m")  return mv(p);
  if (k === "lo") return p.s[scale].lo;
  return p[k];
}

function renderTable(){
  const r = D.players.filter(p=>{
    if (!SKILL.includes(p.p)) return false;
    if (pos !== "ALL" && p.p !== pos) return false;
    if (owner === "FA" && p.own) return false;
    if (owner === "MINE" && p.own !== team) return false;
    if (owner !== "ALL" && owner !== "FA" && owner !== "MINE" && p.own !== owner) return false;
    if (q && !(p.n + " " + p.t).toLowerCase().includes(q)) return false;
    if (hideDismissed && markOf(p) === "dismiss") return false;
    return true;
  });
  r.sort((a,b)=>{
    let x = val(a, sortKey), y = val(b, sortKey);
    const ax = x==null||x==="", ay = y==null||y==="";
    if (ax && ay) return 0;
    if (ax) return 1;
    if (ay) return -1;
    const c = (typeof x === "string") ? x.localeCompare(y) : x - y;
    return c ? sortDir * c : (a.p.localeCompare(b.p) || a.n.localeCompare(b.n));
  });
  const total = D.players.filter(p=>SKILL.includes(p.p)).length;
  $("#tbody").innerHTML = r.map(p=>`<tr class="${p.own===team?'mine':''}${markClass(p)}" data-k="${p.k}">
    <td class="num r">${sk(p) ?? '--'}</td>
    <td class="pname">${nameCell(p)}</td>
    <td class="num">${p.p}</td><td class="num">${p.t}</td><td class="num">${p.o||''}</td>
    <td class="num r">${p.s[scale].pr || 'unranked'}</td>
    <td class="num r">${p.s.draft.pr || '--'}</td>
    <td class="r">${dcell(mv(p))}</td>
    <td class="num r">${p.s[scale].lo && p.s[scale].hi ? p.s[scale].lo+'-'+p.s[scale].hi : ''}</td>
    <td>${ownerCell(p)}</td></tr>`).join("");
  $("#count").textContent = `${r.length} of ${total} players`;
}

function renderBoard(){
  const b = D.boards[scale];
  $("#boardnote").innerHTML =
    `Skill board: <b>${b.slug}.php</b> &middot; ${b.board} &middot; updated ${b.updated} &middot; ${b.experts} expert${b.experts===1?'':'s'}`
    + (b.experts <= 10 ? ` &middot; <span class="warn">thin consensus &mdash; treat as directional</span>` : "");
}

/* ---- flag / dismiss marks ----
   Kept in one db document so a change is a single write and a single
   subscription, with localStorage as the fallback when db is unavailable. */
let marks = {}, marksDoc = null, writeChain = Promise.resolve();

function loadLocal(){
  try { return JSON.parse(localStorage.getItem("fr_marks") || "{}") || {}; }
  catch(e){ return {}; }
}
function saveLocal(){
  try { localStorage.setItem("fr_marks", JSON.stringify(marks)); } catch(e){}
}
marks = loadLocal();

const markId = p => p.pid ? "p" + p.pid : "k" + String(p.k).replace(/[^A-Za-z0-9]/g, "_");
const markOf = p => marks[markId(p)] || "";
const markClass = p => { const m = markOf(p); return m ? " mk-" + m : ""; };

function markDot(p){
  const m = markOf(p);
  const label = m === "flag" ? "Flagged" : m === "dismiss" ? "Dismissed" : "Unmarked";
  return `<button class="mkdot${m?" on "+m:""}" aria-label="${label}: ${p.n}"
    title="Click to cycle: flag, dismiss, clear"></button>`;
}

const NEXT = { "": "flag", flag: "dismiss", dismiss: "" };

function cycleMark(k){
  const p = byKey[k];
  if (!p) return;
  const id = markId(p);
  const next = NEXT[marks[id] || ""];
  if (next) marks[id] = next; else delete marks[id];
  saveLocal();
  renderAll();
  if (marksDoc){
    writeChain = writeChain.then(() => marksDoc.set({ m: marks })).catch(() => {});
  }
}

function toggleMark(k, status){
  const p = byKey[k];
  if (!p) return;
  const id = markId(p);
  if (marks[id] === status) delete marks[id]; else marks[id] = status;
  saveLocal();
  renderAll();
  if (marksDoc){
    // one write at a time per document
    writeChain = writeChain.then(() => marksDoc.set({ m: marks })).catch(() => {});
  }
}

(async () => {
  const db = window.claude && await window.claude.use("db");
  if (!db) return;                       // design for absence: localStorage only
  marksDoc = db.doc("marks/board");
  marksDoc.onSnapshot(
    snap => {
      if (!snap.exists) return;
      marks = (snap.data() || {}).m || {};
      saveLocal();
      renderAll();
    },
    () => { marksDoc = null; }           // degrade to local, no retry loop
  );
})();

/* ---- player drawer ---- */
const byKey = {};
D.players.forEach(p => byKey[p.k] = p);
let lastFocus = null;

const esc = s => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");

function scaleCard(p, key, label){
  const s = p.s[key];
  return `<div class="scalecard">
    <div class="lbl">${label}</div>
    <div class="big">${s.sk != null ? '#'+s.sk : (s.pr || '--')}</div>
    <div class="sm">${s.sk != null ? (s.pr || '') : ''}${s.lo && s.hi ? ' &middot; '+s.lo+'-'+s.hi : ''}</div>
  </div>`;
}

function openPlayer(k){
  const p = byKey[k];
  if (!p) return;
  const d = D.detail[k] || {};
  const log = d.log || {};
  const news = d.news || [];

  const logHtml = (log.rows && log.rows.length)
    ? `<div class="logwrap"><table><thead><tr>${
        log.cols.map(c=>`<th>${esc(c)}</th>`).join("")}</tr></thead><tbody>${
        log.rows.map(r=>`<tr>${r.map(c=>`<td>${esc(c)}</td>`).join("")}</tr>`).join("")
      }</tbody></table></div>`
    : `<p class="dmeta">No games played yet this season.</p>`;

  const newsHtml = news.length
    ? news.map(n=>`<div class="newsitem">
        <h4>${esc(n.head)}</h4>
        ${n.body?`<p>${esc(n.body)}</p>`:""}
        ${n.impact?`<p class="imp">${esc(n.impact)}</p>`:""}
        <div class="newsmeta">${esc(n.date||"")}${n.by?" &middot; "+esc(n.by):""}</div>
      </div>`).join("")
    : `<p class="dmeta">No news fetched for this player. Run <b>details.py</b> to widen coverage.</p>`;

  $("#drawer").dataset.k = k;
  $("#drawer").innerHTML = `
    <div class="dhead">
      <div class="who">
      ${p.pid && D.photos[p.pid] ? `<img class="face big" src="img/${p.pid}.png" alt="" width="56" height="56">` : ""}
      <div>
        <h2>${esc(p.n)}</h2>
        <div class="dmeta">${esc(p.p)} &middot; ${esc(p.t||"FA")}${p.o?" &middot; "+esc(p.o):""}${
          p.by?" &middot; bye "+esc(p.by):""}<br>
          ${p.own?"Rostered by "+esc(p.own):"Free agent"}${p.sl?" &middot; "+esc(p.sl):""}${
          p.inj?' &middot; <span class="inj">'+esc(p.inj)+'</span>':""}</div>
      </div>
      </div>
      <button id="dclose" aria-label="Close">&times;</button>
    </div>
    <div class="dsec">
      <h3>Consensus rank</h3>
      <div class="scalegrid">
        ${scaleCard(p,"draft","Draft day")}${scaleCard(p,"week","Week "+D.week)}${scaleCard(p,"ros","Rest of season")}
      </div>
      <p class="dmeta" style="margin-top:9px">Move since draft day: ${
        p.m[scale]==null ? "--" : (p.m[scale]>0?"+":"")+p.m[scale]+" places at "+esc(p.p)}</p>
    </div>
    <div class="dsec">
      <h3>Mark</h3>
      <div class="drawermk mkbtns">
        <button class="mk" data-mk="flag" aria-pressed="${markOf(p)==='flag'}">&#10003; Flag</button>
        <button class="mk" data-mk="dismiss" aria-pressed="${markOf(p)==='dismiss'}">&times; Dismiss</button>
      </div>
    </div>
    <div class="dsec"><h3>Game log</h3>${logHtml}</div>
    <div class="dsec"><h3>Recent news</h3>${newsHtml}
      ${p.u?`<a class="dlink" href="${esc(p.u)}" target="_blank" rel="noopener">Open on FantasyPros &rarr;</a>`:""}
    </div>`;
  $("#scrim").hidden = false;
  $("#drawer").hidden = false;
  lastFocus = document.activeElement;
  $("#dclose").focus();
}

function closePlayer(){
  $("#scrim").hidden = true;
  $("#drawer").hidden = true;
  if (lastFocus) lastFocus.focus();
}

function renderAll(){ renderBoard(); renderPanels(); renderRoster(); renderWaiver(); renderTable(); }

document.addEventListener("click", e=>{
  if (e.target.closest("#dclose") || e.target.id === "scrim"){ closePlayer(); return; }
  const dot = e.target.closest("button.mkdot");
  if (dot){
    e.stopPropagation();
    const holder = dot.closest("[data-k]");
    if (holder) cycleMark(holder.dataset.k);
    return;
  }
  const mk = e.target.closest("button.mk");
  if (mk){
    e.stopPropagation();
    const holder = mk.closest("[data-k]");
    if (holder) toggleMark(holder.dataset.k, mk.dataset.mk);
    return;
  }
  // scoped to rows: sortable <th> also carry data-k and must not open the drawer
  const rowEl = e.target.closest("tr[data-k], .row[data-k]");
  if (rowEl && !e.target.closest("a")){ openPlayer(rowEl.dataset.k); return; }
  const s = e.target.closest(".scalebtn");
  if (s){
    scale = s.dataset.scale;
    document.querySelectorAll(".scalebtn").forEach(x=>x.setAttribute("aria-pressed", x===s));
    renderAll(); return;
  }
  const c = e.target.closest(".chip");
  if (c){
    pos = c.dataset.pos;
    document.querySelectorAll(".chip").forEach(x=>x.setAttribute("aria-pressed", x===c));
    renderTable(); return;
  }
  const th = e.target.closest("th[data-k]");
  if (th){
    const k = th.dataset.k;
    sortDir = (k === sortKey) ? -sortDir : 1;
    sortKey = k;
    document.querySelectorAll("th[data-k]").forEach(x=>{
      x.removeAttribute("aria-sort"); x.querySelector(".car").textContent = "";
    });
    th.setAttribute("aria-sort", sortDir===1?"ascending":"descending");
    th.querySelector(".car").textContent = sortDir===1?" ▲":" ▼";
    renderTable();
  }
});
document.addEventListener("keydown", e=>{
  if (e.key === "Escape" && !$("#drawer").hidden){ closePlayer(); return; }
  const dot = e.target.closest && e.target.closest("button.mkdot");
  if (dot && (e.key === "Enter" || e.key === " ")){
    e.preventDefault(); e.stopPropagation();
    const holder = dot.closest("[data-k]");
    if (holder) cycleMark(holder.dataset.k);
    return;
  }
  const rowEl = e.target.closest && e.target.closest(".row[data-k]");
  if (rowEl && (e.key === "Enter" || e.key === " ")){ e.preventDefault(); openPlayer(rowEl.dataset.k); }
});
$("#team").addEventListener("change", e=>{ team = e.target.value; renderAll(); });
$("#hide").addEventListener("change", e=>{ hideDismissed = e.target.checked; renderAll(); });
$("#q").addEventListener("input", e=>{ q = e.target.value.toLowerCase().trim(); renderTable(); });
$("#owner").addEventListener("change", e=>{ owner = e.target.value; renderTable(); });
document.querySelectorAll("th[data-k]").forEach(x=>{
  x.tabIndex = 0;
  x.addEventListener("keydown", ev=>{
    if(ev.key==="Enter"||ev.key===" "){ ev.preventDefault(); x.click(); }
  });
});
renderAll();
