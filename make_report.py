"""Render data.json into a self-contained report.html.

All roster-relative analysis (waiver comparisons, sell/buy/add/drop shortlists)
lives in the page rather than here, because it depends on which team the viewer
has selected. Python's job is to emit the player table and the board metadata.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = ("RB", "WR", "TE")
SIDE = ("QB", "DST", "K")      # tracked, but never mixed into the skill board
MAX_PHOTOS = 250               # an artifact accepts at most 255 supporting files


def on_ir(p):
    return p.get("slot") == "IR" or p.get("injury") == "INJURY_RESERVE"


def trim(p):
    sc = p["scales"]
    return {
        "k": p["key"], "u": p.get("url") or "", "pid": p.get("pid"),
        "n": p["name"], "p": p["pos"], "t": p["team"] or "", "o": p["opponent"] or "",
        "own": p["owner"], "ir": on_ir(p), "sl": p.get("slot") or "",
        "by": p.get("bye") or "",
        "inj": (p["injury"] or "").replace("_", " ").title()
               if p["injury"] not in (None, "ACTIVE") else "",
        "s": {k: {"sk": sc[k]["skill"], "pr": sc[k]["pos_rank"], "pn": sc[k]["pos_num"],
                  "lo": sc[k]["lo"], "hi": sc[k]["hi"]}
              for k in ("draft", "week", "ros")},
        "m": {"week": p["pmove_week"], "ros": p["pmove_ros"], "draft": None},
    }


CSS = """
:root{
  --paper:#eef0f4; --surface:#fff; --raised:#f7f8fa;
  --ink:#131720; --muted:#69707e; --line:#d7dbe3;
  --accent:#a8741f; --accent-soft:#f0e3c8; --on-accent:#fff;
  --rise:#0d7a63; --rise-soft:#d9efe8;
  --fall:#bc4238; --fall-soft:#f7ddd9;
  --shadow:0 1px 2px rgba(19,23,32,.06),0 1px 1px rgba(19,23,32,.04);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --paper:#0e1116; --surface:#171b22; --raised:#1e232b;
  --ink:#e4e8ef; --muted:#8e97a6; --line:#2b313b;
  --accent:#d9a94e; --accent-soft:#3a2f1a; --on-accent:#1a1408;
  --rise:#4bbf9f; --rise-soft:#12302a;
  --fall:#e0756a; --fall-soft:#35211f;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}}
:root[data-theme="dark"]{
  --paper:#0e1116; --surface:#171b22; --raised:#1e232b;
  --ink:#e4e8ef; --muted:#8e97a6; --line:#2b313b;
  --accent:#d9a94e; --accent-soft:#3a2f1a; --on-accent:#1a1408;
  --rise:#4bbf9f; --rise-soft:#12302a;
  --fall:#e0756a; --fall-soft:#35211f;
  --shadow:0 1px 2px rgba(0,0,0,.4);
}
*{box-sizing:border-box}
body{background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",ui-sans-serif,system-ui,-apple-system,Segoe UI,sans-serif;
  line-height:1.45;margin:0}
.wrap{max-width:1180px;margin:0 auto;padding-inline:16px;padding-block:0 56px}
h1,h2,h3,.dname{font-family:Oswald,"Arial Narrow",Haettenschweiler,sans-serif;
  font-weight:500;letter-spacing:.01em;text-wrap:balance;margin:0}
.eyebrow{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--muted);margin:0}
.num{font-family:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,monospace;
  font-variant-numeric:tabular-nums}

header.top{border-bottom:1px solid var(--line);background:var(--surface);
  padding-block:22px 0;margin-bottom:22px}
header.top h1{font-size:clamp(26px,4.4vw,38px);text-transform:uppercase;line-height:1.05}
.sub{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:13px;color:var(--muted)}
.sub b{color:var(--ink);font-weight:600}
.scalebar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:16px;
  border-top:1px solid var(--line);padding-block:10px}
.scalebtn{font-family:Oswald,sans-serif;font-size:14px;letter-spacing:.06em;
  text-transform:uppercase;cursor:pointer;border:1px solid var(--line);
  background:var(--raised);color:var(--muted);border-radius:4px;padding:7px 14px}
.scalebtn[aria-pressed="true"]{background:var(--ink);border-color:var(--ink);color:var(--paper)}
.teampick{display:flex;align-items:center;gap:7px;margin-left:auto}
.teampick label{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.11em;
  text-transform:uppercase;color:var(--muted)}
#team{font-family:Oswald,sans-serif;font-size:14px;letter-spacing:.04em;padding:7px 10px;
  border:1px solid var(--accent);background:var(--accent-soft);color:var(--ink);border-radius:4px}
.boardnote{font-size:11.5px;color:var(--muted);flex:1 1 100%;margin:0}
.boardnote b{color:var(--ink)}
.warn{color:var(--fall)}

h2.sec{font-size:19px;text-transform:uppercase;letter-spacing:.05em;margin:34px 0 3px}
p.secsub{margin:0 0 12px;font-size:12.5px;color:var(--muted);max-width:66ch}
.secsub b{color:var(--ink)}

.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:14px}
.panel{background:var(--surface);border:1px solid var(--line);border-radius:6px;
  box-shadow:var(--shadow);overflow:hidden}
.panel>h2{font-size:15px;text-transform:uppercase;letter-spacing:.06em;
  padding:11px 14px;border-bottom:1px solid var(--line);display:flex;
  justify-content:space-between;align-items:baseline;gap:10px}
.panel>h2 span{font-size:11px;color:var(--muted);letter-spacing:.04em;
  text-transform:none;font-family:"IBM Plex Sans",sans-serif;text-align:right}
.panel.sell{border-top:3px solid var(--fall)}
.panel.buy{border-top:3px solid var(--rise)}
.panel.adds{border-top:3px solid var(--accent)}
.panel.drops{border-top:3px solid var(--muted)}
.rows{display:flex;flex-direction:column}
.row{display:flex;align-items:baseline;gap:8px;flex-wrap:wrap;
  padding:9px 14px;border-bottom:1px solid var(--line);font-size:13px}
.row:last-child{border-bottom:0}
.dname{font-size:16px;font-weight:500}
.tag{font-size:10.5px;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);
  border:1px solid var(--line);border-radius:3px;padding:1px 5px;white-space:nowrap}
.move{font-size:12.5px;color:var(--muted);width:100%}
.move .a{color:var(--ink);font-weight:600}
.delta{font-weight:600;padding:1px 6px;border-radius:3px;font-size:12px;
  font-family:"IBM Plex Mono",monospace}
.up{color:var(--rise);background:var(--rise-soft)}
.down{color:var(--fall);background:var(--fall-soft)}
.flat{color:var(--muted);background:var(--raised)}
.inj{color:var(--fall);font-size:11.5px;letter-spacing:.04em;text-transform:uppercase}
.empty{padding:14px;color:var(--muted);font-size:13px}

.controls{position:sticky;top:env(safe-area-inset-top,0px);z-index:5;
  background:var(--surface);border:1px solid var(--line);border-radius:6px 6px 0 0;
  padding:11px 12px;margin:0;display:flex;flex-wrap:wrap;gap:8px;
  align-items:center;box-shadow:var(--shadow)}
input[type=search],select{font:inherit;font-size:13px;color:var(--ink);
  background:var(--raised);border:1px solid var(--line);border-radius:4px;padding:6px 9px}
input[type=search]{flex:1 1 180px;min-width:0}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-family:"IBM Plex Mono",monospace;font-size:11.5px;letter-spacing:.06em;
  cursor:pointer;border:1px solid var(--line);background:var(--raised);color:var(--muted);
  border-radius:4px;padding:5px 9px}
.chip[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.chip:focus-visible,th:focus-visible,input:focus-visible,select:focus-visible,
.scalebtn:focus-visible{outline:2px solid var(--accent);outline-offset:2px}

.tablewrap{overflow-x:auto;background:var(--surface);border:1px solid var(--line);
  border-radius:6px}
.tablewrap.joined{border-top:0;border-radius:0 0 6px 6px}
table{border-collapse:collapse;width:100%;font-size:13px;min-width:720px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid var(--line);white-space:nowrap}
th{position:sticky;top:0;background:var(--raised);font-family:"IBM Plex Mono",monospace;
  font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);z-index:1}
th[data-k]{cursor:pointer;user-select:none}
th[aria-sort] .car{color:var(--accent)}
td.r,th.r{text-align:right}
tr.mine td{background:var(--accent-soft)}
tr.mine .pname{font-weight:600}
.pname{font-size:13.5px}
.owner{color:var(--muted);font-size:12px}
.fa{color:var(--rise);font-size:12px;font-weight:600}
.count{color:var(--muted);font-size:12px;padding:9px 2px}
.up-yes{color:var(--rise);font-weight:600}
.up-no{color:var(--muted)}
.sidegrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(290px,1fr));gap:14px;
  margin-top:14px}
.sidegrid table{min-width:280px}
.sidegrid h3{font-size:14px;text-transform:uppercase;letter-spacing:.06em;
  padding:9px 12px;border-bottom:1px solid var(--line);background:var(--raised)}
/* the button is a generous 28px hit target; only the inner span is the dot,
   so the click is easy to land without opening the row's drawer */
button.mkdot{appearance:none;cursor:pointer;border:0;background:none;padding:0;
  width:28px;height:24px;margin:-6px 0 -6px 2px;vertical-align:middle;
  display:inline-flex;align-items:center;justify-content:center}
button.mkdot .d{width:11px;height:11px;border-radius:50%;background:transparent;
  border:1.5px solid var(--muted);opacity:0;transition:opacity .12s ease}
@media (prefers-reduced-motion:reduce){button.mkdot .d{transition:none}}
/* visible on hover of that player's own row, or always once marked */
tr:hover button.mkdot .d,.row:hover button.mkdot .d{opacity:.45}
button.mkdot:focus-visible{outline:2px solid var(--accent);outline-offset:-2px;border-radius:4px}
button.mkdot:focus-visible .d{opacity:1}
button.mkdot.on .d{opacity:1}
button.mkdot.flag .d{background:var(--rise);border-color:var(--rise)}
button.mkdot.dismiss .d{background:var(--fall);border-color:var(--fall)}
tr:hover button.mkdot.on .d,.row:hover button.mkdot.on .d{opacity:1}
#markwarn{font-size:11.5px;color:var(--fall)}
.mkbtns{display:inline-flex;gap:3px;margin-left:8px;vertical-align:middle}
button.mk{cursor:pointer;font:inherit;font-size:11px;line-height:1;padding:3px 6px;
  border:1px solid var(--line);background:var(--raised);color:var(--muted);border-radius:3px}
button.mk:hover{border-color:var(--muted)}
button.mk[data-mk="flag"][aria-pressed="true"]{background:var(--rise);border-color:var(--rise);color:#fff}
button.mk[data-mk="dismiss"][aria-pressed="true"]{background:var(--fall);border-color:var(--fall);color:#fff}
button.mk:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
tr.mk-flag td{background:var(--rise-soft)!important}
tr.mk-dismiss td{background:var(--fall-soft)!important;opacity:.62}
.row.mk-flag{background:var(--rise-soft)}
.row.mk-dismiss{background:var(--fall-soft);opacity:.62}
.drawermk{display:flex;gap:8px;margin-top:10px}
.drawermk button{flex:1;font-size:13px;padding:8px}
.face{width:26px;height:26px;border-radius:50%;object-fit:cover;background:var(--raised);
  border:1px solid var(--line);vertical-align:middle;margin-right:8px;display:inline-block}
.face.big{width:56px;height:56px;border-radius:6px;margin:0}
.dhead .who{display:flex;gap:12px;align-items:flex-start}
tbody tr{cursor:pointer}
tbody tr:hover td{background:var(--raised)}
tr.mine:hover td{background:var(--accent-soft);filter:brightness(.97)}

#scrim{position:fixed;inset:0;background:rgba(10,13,18,.45);z-index:40}
#drawer{position:fixed;top:0;right:0;bottom:0;width:min(560px,100%);z-index:41;
  background:var(--surface);border-left:1px solid var(--line);overflow-y:auto;
  padding:0 0 calc(28px + env(safe-area-inset-bottom,0px));
  box-shadow:-8px 0 26px rgba(10,13,18,.18)}
.dhead{position:sticky;top:0;background:var(--surface);border-bottom:1px solid var(--line);
  padding:16px 18px 12px;display:flex;gap:12px;align-items:flex-start}
.dhead h2{font-size:24px;line-height:1.1;text-transform:uppercase}
.dmeta{font-size:12.5px;color:var(--muted);margin-top:3px}
#dclose{margin-left:auto;font:inherit;font-size:20px;line-height:1;cursor:pointer;
  background:var(--raised);border:1px solid var(--line);color:var(--ink);
  border-radius:4px;padding:5px 11px}
.dsec{padding:14px 18px;border-bottom:1px solid var(--line)}
.dsec h3{font-size:12px;letter-spacing:.11em;text-transform:uppercase;color:var(--muted);
  font-family:"IBM Plex Mono",monospace;margin-bottom:9px}
.scalegrid{display:grid;grid-template-columns:repeat(3,1fr);gap:9px}
.scalecard{background:var(--raised);border:1px solid var(--line);border-radius:5px;padding:9px 11px}
.scalecard .lbl{font-size:10.5px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  font-family:"IBM Plex Mono",monospace}
.scalecard .big{font-family:Oswald,sans-serif;font-size:23px;line-height:1.15}
.scalecard .sm{font-size:11.5px;color:var(--muted);font-family:"IBM Plex Mono",monospace}
.logwrap{overflow-x:auto}
.logwrap table{min-width:0;width:100%;font-size:12px}
.logwrap th{position:static;font-size:9.5px;letter-spacing:.06em;padding:5px 7px}
.logwrap td{padding:5px 7px}
.newsitem{padding:11px 0;border-bottom:1px solid var(--line)}
.newsitem:last-child{border-bottom:0;padding-bottom:0}
.newsitem h4{font-family:"IBM Plex Sans",sans-serif;font-size:13.5px;font-weight:600;margin:0 0 3px}
.newsitem p{margin:0 0 6px;font-size:12.5px;color:var(--muted);line-height:1.5}
.newsitem .imp{color:var(--ink);border-left:2px solid var(--accent);padding-left:9px}
.newsmeta{font-size:11px;color:var(--muted);font-family:"IBM Plex Mono",monospace;
  letter-spacing:.04em}
.dlink{display:inline-block;margin-top:2px;font-size:12.5px;color:var(--accent);font-weight:600}
@media (max-width:600px){.scalegrid{grid-template-columns:1fr}}

footer{color:var(--muted);font-size:12px;margin-top:30px;line-height:1.65;max-width:70ch}
footer b{color:var(--ink)}
@media (max-width:560px){.row{font-size:12.5px}header.top{padding-block:16px 0}
  .teampick{margin-left:0;flex:1 1 100%}#team{flex:1}}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
"""

JS = r"""
const D = window.__DATA__;
const $ = s => document.querySelector(s);

/* A republish reloads open views into the SAME document, so top-level
   addEventListener calls accumulate across versions and one click would fire
   the handler once per reload. Register through `on`, which drops the previous
   handler for that key first, so re-running this script is idempotent. */
const FR = window.__FR || (window.__FR = {});
function on(target, type, fn, key){
  if (!target) return;
  const prev = FR[key];
  if (prev && prev.target) prev.target.removeEventListener(prev.type, prev.fn);
  FR[key] = { target, type, fn };
  target.addEventListener(type, fn);
}
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
  showMarkWarn();
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
    + (b.experts <= 10 ? ` &middot; <span class="warn">thin consensus &mdash; treat as directional</span>` : "")
    + ` &middot; build ${D.build}`;
}

/* ---- flag / dismiss marks (rebuilt) ----
   Local state is authoritative. A click patches only that player's elements
   instead of re-rendering, so no snapshot or render pass can race it, and the
   db is a background mirror that never overwrites a mark made this session. */
const MARK_NEXT = { "": "flag", flag: "dismiss", dismiss: "" };
let marks = {};                  // id -> "flag" | "dismiss"
const touched = new Set();       // ids changed this session; the db must not clobber these
let marksDoc = null, writeChain = Promise.resolve(), pendingWrites = 0, markWarn = "";

function loadLocal(){
  try { return JSON.parse(localStorage.getItem("fr_marks") || "{}") || {}; }
  catch(e){ return {}; }
}
function saveLocal(){
  try { localStorage.setItem("fr_marks", JSON.stringify(marks)); } catch(e){}
}
marks = loadLocal();

const markId = p => p.pid ? "p" + p.pid : "k" + String(p.k).replace(/[^A-Za-z0-9]/g, "_");
const markOf = p => (p && marks[markId(p)]) || "";
const markClass = p => { const m = markOf(p); return m ? " mk-" + m : ""; };
const markLabel = m => m === "flag" ? "Flagged" : m === "dismiss" ? "Dismissed" : "Unmarked";

function markDot(p){
  const m = markOf(p);
  return `<button type="button" class="mkdot${m ? " on " + m : ""}" data-mark="${p.k}"
    aria-label="${markLabel(m)}: ${p.n}"
    title="Click to cycle: flag, dismiss, clear"><span class="d"></span></button>`;
}

/* Patch this player's dots and rows in place -- no re-render, nothing to race. */
function paintMark(k){
  const p = byKey[k];
  if (!p) return;
  const m = markOf(p);
  document.querySelectorAll("button.mkdot").forEach(dot => {
    if (dot.dataset.mark !== k) return;
    dot.classList.remove("on", "flag", "dismiss");
    if (m) dot.classList.add("on", m);
    dot.setAttribute("aria-label", markLabel(m) + ": " + p.n);
    const host = dot.closest("tr[data-k], .row[data-k]");
    if (host){
      host.classList.remove("mk-flag", "mk-dismiss");
      if (m) host.classList.add("mk-" + m);
    }
  });
}

function setMark(k, next){
  const p = byKey[k];
  if (!p) return;
  const id = markId(p);
  if (next) marks[id] = next; else delete marks[id];
  touched.add(id);
  saveLocal();
  if (hideDismissed) renderAll(); else paintMark(k);
  persistMarks();
}

function cycleMark(k){
  const p = byKey[k];
  if (p) setMark(k, MARK_NEXT[marks[markId(p)] || ""]);
}

function toggleMark(k, status){
  const p = byKey[k];
  if (p) setMark(k, marks[markId(p)] === status ? "" : status);
}

function persistMarks(){
  if (!marksDoc) return;
  pendingWrites++;
  writeChain = writeChain
    .then(() => marksDoc.set({ m: marks }))
    .then(() => { markWarn = ""; })
    .catch(err => { markWarn = "Saved on this device only (" + ((err && err.code) || "write failed") + ")"; })
    .then(() => { pendingWrites--; showMarkWarn(); });
}

function showMarkWarn(){
  const el = $("#markwarn");
  if (el) el.textContent = markWarn;
}

(async () => {
  const db = window.claude && await window.claude.use("db");
  if (!db) return;                        // design for absence: localStorage only
  if (FR.unsub){ try { FR.unsub(); } catch(e){} }
  marksDoc = db.doc("marks/board");
  FR.unsub = marksDoc.onSnapshot(
    snap => {
      if (!snap.exists) return;
      const server = (snap.data() || {}).m || {};
      let changed = false;
      // adopt the server's view, except for anything changed here this session
      Object.keys(server).forEach(id => {
        if (!touched.has(id) && marks[id] !== server[id]){ marks[id] = server[id]; changed = true; }
      });
      Object.keys(marks).forEach(id => {
        if (!touched.has(id) && !(id in server)){ delete marks[id]; changed = true; }
      });
      if (changed){ saveLocal(); renderAll(); }
    },
    () => { marksDoc = null; }            // degrade to local, no retry loop
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

on(document, "click", e=>{
  if (e.target.closest("#dclose") || e.target.id === "scrim"){ closePlayer(); return; }
  const dot = e.target.closest("button.mkdot");
  if (dot){
    // a listener left over from an older build may already have handled this
    // very click; the flag rides on the event object, so only one acts
    if (e.__frMark) return;
    e.__frMark = true;
    e.stopPropagation();
    cycleMark(dot.dataset.mark);
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
}, "click");
on(document, "keydown", e=>{
  if (e.key === "Escape" && !$("#drawer").hidden){ closePlayer(); return; }
  const dot = e.target.closest && e.target.closest("button.mkdot");
  if (dot && (e.key === "Enter" || e.key === " ")){
    if (e.__frMark) return;
    e.__frMark = true;
    e.preventDefault(); e.stopPropagation();
    cycleMark(dot.dataset.mark);
    return;
  }
  const rowEl = e.target.closest && e.target.closest(".row[data-k]");
  if (rowEl && (e.key === "Enter" || e.key === " ")){ e.preventDefault(); openPlayer(rowEl.dataset.k); }
}, "keydown");
on($("#team"), "change", e=>{ team = e.target.value; renderAll(); }, "team");
on($("#hide"), "change", e=>{ hideDismissed = e.target.checked; renderAll(); }, "hide");
on($("#q"), "input", e=>{ q = e.target.value.toLowerCase().trim(); renderTable(); }, "q");
on($("#owner"), "change", e=>{ owner = e.target.value; renderTable(); }, "owner");
document.querySelectorAll("th[data-k]").forEach(x=>{
  x.tabIndex = 0;
  if (x.dataset.bound) return;            // idempotent across reloads
  x.dataset.bound = "1";
  x.addEventListener("keydown", ev=>{
    if(ev.key==="Enter"||ev.key===" "){ ev.preventDefault(); x.click(); }
  });
});
renderAll();
"""


def board_title(name):
    """League name plus a noun, trimmed to a short tab-and-gallery name."""
    words = [w for w in str(name).split() if w]
    short = " ".join(words[:3]) if words else "Fantasy"
    return f"{short} Draft Board"


def esc(s):
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build(data, src_path):
    lg, ps = data["league"], data["players"]
    size = lg.get("size") or 8
    wk = data["week"]
    my_name = data["my_team"]["name"]

    detail_path = os.path.join(os.path.dirname(os.path.abspath(src_path)), "details.json")
    detail = {}
    if os.path.exists(detail_path):
        with open(detail_path, encoding="utf-8") as f:
            detail = json.load(f)

    # An artifact takes at most 255 supporting files and img/ is shared across
    # leagues, so advertise only this league's own players, rostered first and
    # then the best free agents, capped below that limit. A player without an
    # entry renders with no avatar rather than a broken image.
    img_dir = os.path.join(HERE, "img")
    have = ({f[:-4] for f in os.listdir(img_dir) if f.endswith(".png")}
            if os.path.isdir(img_dir) else set())

    def photo_prio(pl):
        return (0 if pl["owner"] else 1,
                pl["scales"]["week"]["skill"] or 9999,
                pl["scales"]["week"]["pos_num"] or 9999, pl["name"])

    photos = {}
    for pl in sorted(ps, key=photo_prio):
        pid = str(pl.get("pid") or "")
        if pid and pid in have and pid not in photos:
            photos[pid] = 1
            if len(photos) >= MAX_PHOTOS:
                break

    payload = {
        "photos": photos,
        "players": [trim(p) for p in ps],
        "boards": data["boards"],
        "myTeam": my_name,
        "size": size,
        "week": wk,
        "build": __import__("datetime").datetime.now().strftime("%H%M"),
        "detail": detail,
    }

    owners = sorted({p["owner"] for p in ps if p["owner"]})
    team_opts = "".join(
        '<option value="%s"%s>%s</option>'
        % (esc(o), " selected" if o == my_name else "", esc(o)) for o in owners)
    opts = ['<option value="ALL">All players</option>',
            '<option value="FA">Free agents only</option>',
            '<option value="MINE">Selected team only</option>'] + \
           [f'<option value="{esc(o)}">{esc(o)}</option>' for o in owners]
    chips = "".join(
        '<button class="chip" data-pos="%s" aria-pressed="%s">%s</button>'
        % (p, "true" if p == "ALL" else "false", p) for p in ["ALL", "RB", "WR", "TE"])
    sbtns = "".join(
        '<button class="scalebtn" data-scale="%s" aria-pressed="%s">%s</button>'
        % (k, "true" if k == "week" else "false", v)
        for k, v in [("week", f"Week {wk}"), ("ros", "Rest of season"), ("draft", "Draft day")])

    cols = [("sk", "Rank", 1), ("n", "Player", 0), ("p", "Pos", 0), ("t", "Tm", 0),
            ("o", "Opp", 0), ("pn", "Pos rank", 1), ("dn", "Drafted", 1),
            ("m", "Move", 1), ("lo", "Expert range", 1), ("own", "Owner", 0)]
    th = "".join('<th data-k="%s"%s>%s<span class="car"></span></th>'
                 % (k, ' class="r"' if r else "", lbl) for k, lbl, r in cols)

    def panel(cls, pid, title, sub):
        return f"""<section class="panel {cls}">
      <h2>{title}<span>{sub}</span></h2>
      <div class="rows" id="{pid}"></div>
    </section>"""

    ppr = "Full PPR" if lg["ppr"] >= 0.75 else ("Half PPR" if lg["ppr"] >= 0.25 else "Standard")
    fmt = "Superflex" if lg["superflex"] else "1-QB"
    starters = ", ".join(f"{v}{k}" for k, v in lg["slots"].items() if k not in ("Bench", "IR"))

    return f"""<title>{esc(board_title(lg['name']))}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Oswald:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{CSS}</style>

<header class="top"><div class="wrap">
  <p class="eyebrow">FantasyPros consensus &middot; {data['season']} season</p>
  <h1>{esc(lg['name'])}</h1>
  <div class="sub">
    <span><b>{size}</b> teams</span><span><b>{ppr}</b></span>
    <span><b>{fmt}</b> &middot; {esc(starters)}</span>
  </div>
  <div class="scalebar">
    {sbtns}
    <div class="teampick">
      <label for="team">Viewing as</label>
      <select id="team">{team_opts}</select>
    </div>
    <p class="boardnote" id="boardnote"></p>
  </div>
</div></header>

<div class="wrap">
  <div class="grid">
    {panel("sell", "p-sell", "Sell high", "draft-day name value they no longer earn")}
    {panel("buy", "p-buy", "Buy low", "on other rosters &middot; drafted late, producing now")}
    {panel("adds", "p-adds", "Waiver adds", "free agents above the weakest starter")}
    {panel("drops", "p-drops", "Drop candidates", "below the best free agent at that spot")}
  </div>
  {panel("", "p-stash", "IR stash", "costs no active roster spot")}

  <h2 class="sec">Roster &mdash; <span class="teamname" id="rostername"></span></h2>
  <p class="secsub">Best first. Quarterback, kicker and defense have no cross-position rank,
    so they sit at the bottom with a positional rank only.</p>
  <div class="tablewrap">
    <table><thead><tr>
      <th class="r">Rank</th><th>Player</th><th>Pos</th><th>Tm</th><th>Opp</th>
      <th class="r">Pos rank</th><th class="r">Drafted</th><th class="r">Move</th><th>Slot</th>
    </tr></thead><tbody id="rbody"></tbody></table>
  </div>

  <h2 class="sec">Waiver wire</h2>
  <p class="secsub">Best available players. The last two columns are the weakest player
    <span class="teamname"></span> holds at that position and his overall rank &mdash; compare it
    against the free agent's Rank on the left. A green Rank means the free agent outranks him,
    so the swap is an upgrade.</p>
  <div class="tablewrap">
    <table><thead><tr>
      <th class="r">Rank</th><th>Player</th><th>Pos</th><th>Tm</th><th>Opp</th>
      <th class="r">Pos rank</th><th class="r">Move</th>
      <th>Worst on this roster</th><th class="r">His overall</th>
    </tr></thead><tbody id="wbody"></tbody></table>
  </div>
  <div class="sidegrid" id="sidetables"></div>

  <h2 class="sec">Every skill player</h2>
  <p class="secsub">Running backs, receivers and tight ends ranked against each other &mdash;
    {"the order that matters when only one QB starts" if not lg["superflex"] else "ranked for this roster"}.
    The selected team's players are highlighted.</p>
  <div class="controls">
    <input type="search" id="q" placeholder="Search player or team">
    <div class="chips">{chips}</div>
    <select id="owner">{''.join(opts)}</select>
    <label style="font-size:12.5px;color:var(--muted);display:flex;align-items:center;gap:5px">
      <input type="checkbox" id="hide"> Hide dismissed</label>
    <span id="markwarn"></span>
  </div>
  <div class="tablewrap joined">
    <table><thead><tr>{th}</tr></thead><tbody id="tbody"></tbody></table>
  </div>
  <p class="count" id="count"></p>

  <div id="scrim" hidden></div>
  <aside id="drawer" role="dialog" aria-modal="true" aria-label="Player detail" hidden></aside>

  <footer>
    Click any player for their game log and recent FantasyPros news.
    <b>Viewing as</b> switches every section on the page &mdash; roster, waiver comparisons and the
    four shortlists all recompute for the chosen team, which is how you scout a trade partner.
    <b>Rank</b> is the cross-position rank among RB/WR/TE on the selected board; FantasyPros
    publishes no draft-day FLEX board, so draft-day rank is derived by removing quarterbacks from
    the overall board and renumbering, which makes all three scales cover the same population.
    <b>Move</b> is the change in <em>positional</em> rank since draft day; negative means the player
    has slid while the draft-day reputation lingers, which is what makes someone a sell-high.
    <b>Expert range</b> is the best and worst rank any single expert gave, so a wide spread means
    thin agreement. Players with no rank on a board (injured, inactive) always sort last.
  </footer>
</div>

<script>window.__DATA__ = {json.dumps(payload, separators=(',', ':'))};</script>
<script>{JS}</script>
"""


def main(src=None, dst=None):
    src = src or os.path.join(HERE, "data.json")
    dst = dst or os.path.join(HERE, "report.html")
    html = build(json.load(open(src, encoding="utf-8")), src)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {dst}  ({os.path.getsize(dst)//1024} KB)")


if __name__ == "__main__":
    main(*(sys.argv[1:] or []))
