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
/* ---- who are you ---- */
#picker{position:fixed;inset:0;z-index:60;background:var(--paper);overflow-y:auto;
  display:flex;flex-direction:column;
  padding-top:env(safe-area-inset-top,0px);padding-bottom:env(safe-area-inset-bottom,0px)}
#whoami{font-family:Oswald,sans-serif;font-weight:500;text-transform:uppercase;
  letter-spacing:.03em;text-align:center;margin:0;cursor:pointer;
  font-size:clamp(30px,7vw,64px);line-height:1.1;padding:18px 16px 14px;
  -webkit-user-select:none;user-select:none}
.pgrid{display:grid;grid-template-columns:repeat(4,1fr);gap:0;width:100%}
@media (max-width:1000px){.pgrid{grid-template-columns:repeat(3,1fr)}}
@media (max-width:700px){.pgrid{grid-template-columns:repeat(2,1fr)}}
.ptile{display:block;width:100%;padding:0;border:0;background:none;cursor:pointer;
  font:inherit;color:inherit;text-align:center}
.pshot{position:relative;width:100%;aspect-ratio:1;overflow:hidden;background:var(--raised)}
.pshot img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.pshot .p2{opacity:0;transition:opacity .12s ease}
/* hover reveals the second photo; the heading flips them all, and hovering
   while flipped flips that one back -- the two toggles compose */
.ptile:hover .pshot .p2,.ptile:focus-visible .pshot .p2{opacity:1}
.pgrid.flipped .pshot .p2{opacity:1}
.pgrid.flipped .ptile:hover .pshot .p2,
.pgrid.flipped .ptile:focus-visible .pshot .p2{opacity:0}
.ptile:focus-visible{outline:3px solid var(--accent);outline-offset:-3px}
.pname{font-family:"IBM Plex Mono",monospace;font-size:11px;letter-spacing:.08em;
  text-transform:uppercase;color:var(--muted);padding:7px 6px 12px;
  overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.ptile:hover .pname{color:var(--ink)}
@media (prefers-reduced-motion:reduce){.pshot .p2{transition:none}}
#powerwrap table{min-width:560px}
#powerwrap tbody tr{cursor:default}
#powerwrap tbody tr:hover td{background:var(--raised)}
#powerwrap tr.you td{background:var(--accent-soft)}
#powerwrap tr.you .tname{font-weight:600}
.pr{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.prank{font-family:Oswald,sans-serif;font-size:17px;color:var(--muted)}
tr.you .prank{color:var(--accent)}
#findbar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin:0 0 12px}
#findbtn{font-family:Oswald,sans-serif;font-size:14px;letter-spacing:.05em;text-transform:uppercase;
  cursor:pointer;border:1px solid var(--accent);background:var(--accent);color:var(--on-accent);
  border-radius:4px;padding:8px 16px}
#findbtn[disabled]{opacity:.6;cursor:default}
#findnote{font-size:12px;color:var(--muted)}
.deal{display:block;width:100%;text-align:left;font:inherit;cursor:pointer;
  background:var(--surface);border:1px solid var(--line);border-left:3px solid var(--rise);
  border-radius:5px;padding:10px 12px;margin-bottom:8px;color:var(--ink)}
.deal:hover{background:var(--raised)}
.deal:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.deal .who{font-family:"IBM Plex Mono",monospace;font-size:10.5px;letter-spacing:.09em;
  text-transform:uppercase;color:var(--muted);margin-bottom:5px}
.deal .legs{display:flex;flex-wrap:wrap;gap:6px 14px;align-items:baseline}
.deal .leg{font-size:13.5px}
.deal .leg b{font-family:Oswald,sans-serif;font-weight:500;font-size:15px}
.deal .arrow{color:var(--muted)}
.deal .gains{margin-top:6px;font-size:12px;color:var(--muted);
  font-family:"IBM Plex Mono",monospace}
.deal .gains b{color:var(--rise)}

.tradebar{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:12px}
.tradegrid{display:grid;grid-template-columns:1fr 1fr;gap:14px}
@media (max-width:720px){.tradegrid{grid-template-columns:1fr}}
.tradecol{background:var(--surface);border:1px solid var(--line);border-radius:6px;overflow:hidden}
.tradecol h3{font-size:13px;text-transform:uppercase;letter-spacing:.07em;padding:9px 12px;
  border-bottom:1px solid var(--line);background:var(--raised);display:flex;
  justify-content:space-between;gap:8px}
.tradecol h3 span{color:var(--muted);font-family:"IBM Plex Mono",monospace;font-size:11px}
.tradelist{max-height:320px;overflow-y:auto}
.trow{display:flex;align-items:center;gap:8px;padding:6px 12px;border-bottom:1px solid var(--line);
  font-size:12.5px;cursor:pointer;background:none;border-left:0;border-right:0;border-top:0;
  width:100%;text-align:left;color:var(--ink);font-family:inherit}
.trow:last-child{border-bottom:0}
.trow:hover{background:var(--raised)}
.trow[aria-pressed="true"]{background:var(--accent-soft)}
.trow .tick{width:13px;height:13px;border:1.5px solid var(--muted);border-radius:3px;flex:0 0 auto}
.trow[aria-pressed="true"] .tick{background:var(--accent);border-color:var(--accent)}
.trow .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.trow .rk{font-family:"IBM Plex Mono",monospace;color:var(--muted);font-size:11.5px}
.trow.nv .rk{color:var(--fall)}
#tradeout{margin-top:14px;background:var(--surface);border:1px solid var(--line);
  border-radius:6px;padding:14px}
.verdict{font-family:Oswald,sans-serif;font-size:21px;text-transform:uppercase;letter-spacing:.04em}
.verdict.good{color:var(--rise)} .verdict.bad{color:var(--fall)} .verdict.even{color:var(--muted)}
.tstat{display:flex;flex-wrap:wrap;gap:18px;margin:8px 0 4px;font-size:13px}
.tstat b{font-family:"IBM Plex Mono",monospace;font-variant-numeric:tabular-nums}
.tnote{font-size:12px;color:var(--muted);margin-top:8px;line-height:1.55}
.lineupcmp{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px;font-size:12.5px}
@media (max-width:560px){.lineupcmp{grid-template-columns:1fr}}
.lineupcmp h4{font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:var(--muted);
  font-family:"IBM Plex Mono",monospace;margin:0 0 5px}
.lineupcmp li{list-style:none;padding:2px 0}
.lineupcmp ul{margin:0;padding:0}
.lineupcmp .inn{color:var(--rise);font-weight:600}
.lineupcmp .outn{color:var(--fall);text-decoration:line-through}
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
try {
  const saved = localStorage.getItem("fr_team");
  if (saved && D.players.some(p => p.own === saved)) team = saved;
} catch(e){}
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

/* ---- who are you ----
   A first-run chooser that only sets "Viewing as". The choice is remembered
   per browser, so it is asked once and never again on that device. */
function renderPicker(){
  const grid = $("#pgrid");
  if (!grid || !(D.people || []).length) return;
  grid.innerHTML = D.people.map(p => `<button type="button" class="ptile" data-team="${p.team}">
      <span class="pshot">
        <img src="${p.img}" alt="${p.name}" loading="lazy" decoding="async">
        ${p.img2 ? `<img class="p2" src="${p.img2}" alt="" loading="lazy" decoding="async">` : ""}
      </span>
      <span class="pname">${p.team}</span>
    </button>`).join("");
}

function showPicker(){
  const el = $("#picker");
  if (!el || !(D.people || []).length) return false;
  renderPicker();
  el.hidden = false;
  return true;
}

function choose(t){
  team = t;
  try { localStorage.setItem("fr_team", t); } catch(e){}
  const el = $("#picker");
  if (el) el.hidden = true;
  const sel = $("#team");
  if (sel) sel.value = t;
  TRADE.give.clear(); TRADE.recv.clear(); clearFound();
  renderAll();
}

/* ---- league power rankings ----
   Two different questions: who fields the best starting lineup this week, and
   who holds the most value overall. A team can lead one and trail the other --
   that gap is where trades come from. */
let powerSort = "start";

function teamTotals(){
  const sc = scale;
  const names = [...new Set(D.players.filter(p => p.own).map(p => p.own))];
  return names.map(tm => {
    const roster = D.players.filter(p => p.own === tm);
    const ranked = roster.filter(p => SKILL.includes(p.p) && p.s[sc].sk != null);
    const start = lineupAt(roster, sc).total;
    const total = ranked.reduce((t, p) => t + (valueAt(p, sc) || 0), 0);
    const best = ranked.slice().sort((a, b) => a.s[sc].sk - b.s[sc].sk)[0];
    return { tm, start, total, bench: total - start, n: ranked.length, best };
  }).sort((a, b) => (powerSort === "start" ? b.start - a.start : b.total - a.total));
}

function renderPower(){
  const rows = teamTotals();
  const sc = scale;
  $("#powerbody").innerHTML = rows.map((r, i) => `<tr class="${r.tm === team ? "you" : ""}">
    <td class="prank">${i + 1}</td>
    <td class="tname">${r.tm}</td>
    <td class="pr r">${r.start.toFixed(0)}</td>
    <td class="pr r">${r.bench.toFixed(0)}</td>
    <td class="pr r">${r.total.toFixed(0)}</td>
    <td class="pr r">${r.n}</td>
    <td>${r.best ? r.best.n + ' <span class="owner">' + (r.best.s[sc].pr || "") + "</span>" : ""}</td>
  </tr>`).join("");
  document.querySelectorAll("#powerwrap th[data-ps]").forEach(th => {
    th.setAttribute("aria-sort", th.dataset.ps === powerSort ? "descending" : "none");
    th.querySelector(".car").textContent = th.dataset.ps === powerSort ? " \u25bc" : "";
  });
  const mine = rows.findIndex(r => r.tm === team);
  $("#powernote").textContent = mine < 0 ? "" :
    `${team} ranks ${mine + 1} of ${rows.length} by starting lineup` +
    (powerSort === "start" ? "" : " (sorted by full roster)") + ".";
}

/* ---- trade evaluator ----
   Value comes from the RB/WR/TE overall board, which is real FantasyPros
   cross-position data. QB, K and D/ST have no such board, so they are shown
   but never scored -- inventing a cross-position number for them would be
   guesswork dressed up as arithmetic. */
const TRADE = { partner: null, scale: "ros", give: new Set(), recv: new Set() };
const TAU = 45;   // rank at which value decays to about 1/e of the top player

function valueAt(p, sc){
  const r = p.s[sc].sk;
  return r ? 100 * Math.exp(-(r - 1) / TAU) : null;
}
function tval(p){ return valueAt(p, TRADE.scale); }

/* A 2-for-1 frees a roster spot, and that spot is worth the best player still
   on waivers -- which in a shallow league is a real asset. A 1-for-2 costs a
   spot instead and forces a drop. Both sides of a deal get the same treatment. */
function faPool(){
  const sc = TRADE.scale;
  if (!FR.fa || FR.fa.scale !== sc){
    FR.fa = { scale: sc,
      list: D.players.filter(p => !p.own && SKILL.includes(p.p) && p.s[sc].sk != null)
                     .sort((a, b) => a.s[sc].sk - b.s[sc].sk) };
  }
  return FR.fa.list;
}

function topFA(n, roster){
  const held = new Set(roster.map(p => p.k));
  const out = [];
  for (const p of faPool()){
    if (held.has(p.k)) continue;
    out.push(p);
    if (out.length >= n) break;
  }
  return out;
}

/* roster after sending `out` and receiving `inn`, with freed spots filled from
   waivers and surplus bodies dropped */
function settle(roster, out, inn){
  const outK = new Set(out.map(p => p.k));
  let r = roster.filter(p => !outK.has(p.k)).concat(inn);
  const spare = out.length - inn.length;
  if (spare > 0) return { roster: r.concat(topFA(spare, r)), adds: topFA(spare, r) };
  if (spare < 0){
    const innK = new Set(inn.map(p => p.k));
    const cuts = r.filter(p => !innK.has(p.k) && SKILL.includes(p.p))
                  .sort((a, b) => (tval(a) || 0) - (tval(b) || 0))
                  .slice(0, -spare);
    const cutK = new Set(cuts.map(p => p.k));
    return { roster: r.filter(p => !cutK.has(p.k)), adds: [], cuts };
  }
  return { roster: r, adds: [] };
}

function bestLineup(roster){ return lineupAt(roster, TRADE.scale); }

function lineupAt(roster, sc){
  const pool = roster.filter(p => SKILL.includes(p.p) && p.s[sc].sk != null)
                     .sort((a, b) => a.s[sc].sk - b.s[sc].sk);
  const picks = [], used = new Set();
  for (const pos of SKILL){
    let n = +(D.slots[pos] || 0);
    for (const p of pool){
      if (n <= 0) break;
      if (p.p === pos && !used.has(p.k)){ picks.push(p); used.add(p.k); n--; }
    }
  }
  let flex = +(D.slots.FLEX || 0);
  for (const p of pool){
    if (flex <= 0) break;
    if (!used.has(p.k)){ picks.push(p); used.add(p.k); flex--; }
  }
  return { total: picks.reduce((t, p) => t + (valueAt(p, sc) || 0), 0), picks };
}

function tradeRow(p, side){
  const on = TRADE[side].has(p.k);
  const v = tval(p);
  const rk = p.s[TRADE.scale].pr || "unranked";
  return `<button type="button" class="trow${v === null ? " nv" : ""}" data-side="${side}"
    data-tk="${p.k}" aria-pressed="${on}">
    <span class="tick"></span><span class="nm">${p.n}${p.ir ? " (IR)" : ""}</span>
    <span class="rk">${rk}${v === null ? "" : " &middot; " + v.toFixed(0)}</span></button>`;
}

function renderTrade(){
  const partners = [...new Set(D.players.filter(p => p.own && p.own !== team).map(p => p.own))].sort();
  if (!partners.includes(TRADE.partner)) TRADE.partner = partners[0] || null;
  $("#tpartner").innerHTML = partners.map(o =>
    `<option value="${o}"${o === TRADE.partner ? " selected" : ""}>${o}</option>`).join("");
  $("#tscale").value = TRADE.scale;

  const sc = TRADE.scale;
  const ord = (a, b) => (a.s[sc].sk == null ? 9999 : a.s[sc].sk) - (b.s[sc].sk == null ? 9999 : b.s[sc].sk);
  const mine = D.players.filter(p => p.own === team).sort(ord);
  const theirs = D.players.filter(p => p.own === TRADE.partner).sort(ord);
  // a selection left over from a team switch would score someone not in the deal
  TRADE.give = new Set([...TRADE.give].filter(k => mine.some(p => p.k === k)));
  TRADE.recv = new Set([...TRADE.recv].filter(k => theirs.some(p => p.k === k)));

  $("#tmine").innerHTML = mine.map(p => tradeRow(p, "give")).join("");
  $("#ttheirs").innerHTML = theirs.map(p => tradeRow(p, "recv")).join("");
  $("#tmineh").textContent = team;
  $("#ttheirsh").textContent = TRADE.partner || "-";

  const give = mine.filter(p => TRADE.give.has(p.k));
  const recv = theirs.filter(p => TRADE.recv.has(p.k));
  const out = $("#tradeout");
  if (!give.length && !recv.length){
    out.innerHTML = `<p class="tnote">Pick players on each side to evaluate a deal.</p>`;
    return;
  }

  const sum = list => list.reduce((t, p) => t + (tval(p) || 0), 0);
  const gv = sum(give), rv = sum(recv);
  const before = bestLineup(mine);
  const mySettled = settle(mine, give, recv);
  const after = bestLineup(mySettled.roster);
  const lnet = after.total - before.total;
  const fill = mySettled.adds || [], cuts = mySettled.cuts || [];
  // the same sum from the other manager's chair: a deal that hurts them is a
  // deal they decline, however good it looks from here
  const tBefore = bestLineup(theirs);
  const tAfter = bestLineup(settle(theirs, recv, give).roster);
  const tnet = tAfter.total - tBefore.total;

  const beforeK = new Set(before.picks.map(p => p.k));
  const afterK = new Set(after.picks.map(p => p.k));
  const li = (p, cls) => `<li class="${cls}">${p.p} &middot; ${p.n} <span class="rk">${p.s[sc].pr || ""}</span></li>`;

  const fillV = sum(fill), cutV = sum(cuts);
  const netAll = rv + fillV - gv - cutV;
  const mineUp = lnet > 3, mineDown = lnet < -3;
  const themUp = tnet > 3, themDown = tnet < -3;
  const verdict = mineDown ? ["bad", "Weakens your lineup"]
                : mineUp && themDown ? ["even", "Good for you, bad for them"]
                : mineUp && themUp ? ["good", "Helps both sides"]
                : mineUp ? ["good", "Improves your lineup"]
                : ["even", "Roughly a wash"];
  const likely = themDown ? "They lose ground here, so expect a no."
               : themUp ? "It helps them too, so this one is realistic."
               : "About neutral for them, so it may come down to preference.";
  const unvalued = give.concat(recv).filter(p => tval(p) === null);
  const half = Math.round(TAU * Math.LN2);
  const boardName = sc === "ros" ? "rest-of-season" : sc === "week" ? "weekly" : "draft-day";
  const slotText = SKILL.map(x => (D.slots[x] || 0) + x).join(", ") +
                   (D.slots.FLEX ? ", " + D.slots.FLEX + " FLEX" : "");

  out.innerHTML = `
    <div class="verdict ${verdict[0]}">${verdict[1]}</div>
    <div class="tstat">
      <span>You send <b>${gv.toFixed(0)}</b></span>
      <span>You get <b>${rv.toFixed(0)}</b></span>
      <span>You get <b>${fillV.toFixed(0)}</b> off waivers</span>
      <span>Asset value <b class="${netAll > 0 ? "up-yes" : netAll < 0 ? "warn" : ""}">${netAll > 0 ? "+" : ""}${netAll.toFixed(0)}</b></span>
      <span>Your lineup <b class="${lnet > 0 ? "up-yes" : lnet < 0 ? "warn" : ""}">${lnet > 0 ? "+" : ""}${lnet.toFixed(1)}</b></span>
      <span>Their lineup <b class="${tnet > 0 ? "up-yes" : tnet < 0 ? "warn" : ""}">${tnet > 0 ? "+" : ""}${tnet.toFixed(1)}</b></span>
    </div>
    <p class="tnote" style="margin-top:0">${likely}</p>
    <div class="lineupcmp">
      <div><h4>Lineup now &middot; ${before.total.toFixed(0)}</h4><ul>
        ${before.picks.map(p => li(p, afterK.has(p.k) ? "" : "outn")).join("")}</ul></div>
      <div><h4>After the trade &middot; ${after.total.toFixed(0)}</h4><ul>
        ${after.picks.map(p => li(p, beforeK.has(p.k) ? "" : "inn")).join("")}</ul></div>
    </div>
    <p class="tnote"><b>${TRADE.partner}</b> goes ${tBefore.total.toFixed(0)}
      &rarr; ${tAfter.total.toFixed(0)} (${tnet > 0 ? "+" : ""}${tnet.toFixed(1)}).</p>
    <p class="tnote">Value is <b>100 &times; e<sup>&minus;(rank&minus;1)/${TAU}</sup></b> on the
      ${boardName} RB/WR/TE board, so the best player is worth 100 and value halves about every
      ${half} ranks. <b>Asset value</b> counts everyone in the deal; <b>starting lineup</b> counts
      only what you would actually start (${slotText}), which is the number that decides games.
      Depth you never start scores in the first and not the second.${fill.length ?
      " Sending " + give.length + " for " + recv.length + " frees " + fill.length +
      " roster spot" + (fill.length > 1 ? "s" : "") + ", credited at the best player still on waivers: " +
      fill.map(p => p.n + " (" + (p.s[sc].pr || "") + ")").join(", ") + "." : ""}${cuts.length ?
      " Taking " + recv.length + " for " + give.length + " costs a roster spot, so " +
      cuts.map(p => p.n).join(", ") + " would have to be dropped." : ""}${unvalued.length ?
      " Not scored, as they have no cross-position board: " +
      unvalued.map(p => p.n + " (" + p.p + " " + (p.s[sc].pr || "unranked") + ")").join(", ") + "." : ""}${
      give.concat(recv).some(p => p.ir) ?
      " A rest-of-season rank for a player on IR assumes he returns and holds the same role." : ""}</p>`;
}

/* ---- recommended trades ----
   Scans every rival roster for deals that raise BOTH starting lineups. A trade
   that only helps you is one the other manager declines, so one-sided deals are
   not worth listing. */
function combos(arr, n){
  if (n === 1) return arr.map(x => [x]);
  const out = [];
  for (let i = 0; i < arr.length; i++)
    for (let j = i + 1; j < arr.length; j++) out.push([arr[i], arr[j]]);
  return out;
}

function findTrades(){
  const sc = TRADE.scale, POOL = 12, MIN = 1.0, PER_TEAM = 2;
  const mine = D.players.filter(p => p.own === team);
  const myBase = bestLineup(mine).total;
  const rank = list => list.filter(p => SKILL.includes(p.p) && p.s[sc].sk != null)
                           .sort((a, b) => a.s[sc].sk - b.s[sc].sk).slice(0, POOL);
  const A = rank(mine);
  const gsets = combos(A, 1).concat(combos(A, 2));
  const partners = [...new Set(D.players.filter(p => p.own && p.own !== team).map(p => p.own))];
  const found = [];

  for (const tm of partners){
    const theirs = D.players.filter(p => p.own === tm);
    const theirBase = bestLineup(theirs).total;
    const rsets = combos(rank(theirs), 1).concat(combos(rank(theirs), 2));
    const here = [];
    for (const g of gsets){
      for (const r of rsets){
        if (Math.abs(g.length - r.length) > 1) continue;   // keep roster sizes sane
        const myGain = bestLineup(settle(mine, g, r).roster).total - myBase;
        if (myGain < MIN) continue;
        const theirGain = bestLineup(settle(theirs, r, g).roster).total - theirBase;
        if (theirGain < MIN) continue;
        here.push({ tm, g, r, myGain, theirGain });
      }
    }
    // best first, and on a tie prefer the deal that moves fewer players
    here.sort((x, y) => (y.myGain + y.theirGain) - (x.myGain + x.theirGain)
                     || (x.g.length + x.r.length) - (y.g.length + y.r.length));
    // dedupe on BOTH sides: the same haul for a bigger package is not a
    // second option, it is the same option with a worse price
    const seenG = new Set(), seenR = new Set();
    let kept = 0;
    for (const t of here){
      const kg = t.g.map(p => p.k).sort().join("|");
      const kr = t.r.map(p => p.k).sort().join("|");
      if (seenG.has(kg) || seenR.has(kr)) continue;
      seenG.add(kg); seenR.add(kr);
      found.push(t);
      if (++kept >= PER_TEAM) break;
    }
  }
  found.sort((x, y) => y.myGain - x.myGain);
  return found.slice(0, 12);
}

function renderFound(list){
  const sc = TRADE.scale;
  const box = $("#findout");
  if (!list.length){
    box.innerHTML = `<p class="tnote">No trade found that improves both lineups on this board.
      That usually means your starters are already the best fit for what the league holds --
      try the weekly board, or build one by hand above.</p>`;
    return;
  }
  const names = l => l.map(p => `<b>${p.n}</b> <span class="arrow">${p.s[sc].pr || ""}</span>`).join(" + ");
  box.innerHTML = list.map((t, i) => `<button type="button" class="deal" data-deal="${i}">
      <div class="who">${t.tm}</div>
      <div class="legs">
        <span class="leg">Get ${names(t.r)}</span>
        <span class="arrow">&larr;</span>
        <span class="leg">Send ${names(t.g)}</span>
      </div>
      <div class="gains">you <b>+${t.myGain.toFixed(1)}</b> &middot; them +${t.theirGain.toFixed(1)}</div>
    </button>`).join("");
  FR.deals = list;
}

function clearFound(){
  FR.deals = null;
  FR.fa = null;
  const box = $("#findout");
  if (box) box.innerHTML = "";
  const note = $("#findnote");
  if (note) note.textContent = "";
}

function runFinder(){
  const btn = $("#findbtn");
  btn.disabled = true;
  $("#findnote").textContent = "Scanning every roster...";
  // let the button repaint before the scan blocks the thread
  setTimeout(() => {
    const t0 = performance.now();
    const list = findTrades();
    renderFound(list);
    $("#findnote").textContent =
      `${list.length} mutually useful deal${list.length === 1 ? "" : "s"} on the ` +
      (TRADE.scale === "ros" ? "rest-of-season" : TRADE.scale === "week" ? "weekly" : "draft-day") +
      ` board (${Math.round(performance.now() - t0)} ms). Click one to load it above.`;
    btn.disabled = false;
  }, 30);
}

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

function renderAll(){ renderBoard(); renderPanels(); renderPower(); renderRoster(); renderWaiver(); renderTrade(); renderTable(); }

on(document, "click", e=>{
  if (e.target.closest("#dclose") || e.target.id === "scrim"){ closePlayer(); return; }
  const tile = e.target.closest(".ptile");
  if (tile){ choose(tile.dataset.team); return; }
  if (e.target.closest("#whoami")){ $("#pgrid").classList.toggle("flipped"); return; }
  const ps = e.target.closest("#powerwrap th[data-ps]");
  if (ps){ powerSort = ps.dataset.ps; renderPower(); return; }
  const deal = e.target.closest("button.deal");
  if (deal){
    const t = (FR.deals || [])[+deal.dataset.deal];
    if (t){
      TRADE.partner = t.tm;
      TRADE.give = new Set(t.g.map(p => p.k));
      TRADE.recv = new Set(t.r.map(p => p.k));
      renderTrade();
      const el = $("#tradeout");
      if (el && typeof el.scrollIntoView === "function")
        el.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    return;
  }
  const trow = e.target.closest("button.trow");
  if (trow){
    const set = TRADE[trow.dataset.side];
    if (set.has(trow.dataset.tk)) set.delete(trow.dataset.tk); else set.add(trow.dataset.tk);
    renderTrade();
    return;
  }
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
on($("#team"), "change", e=>{ team = e.target.value;
  TRADE.give.clear(); TRADE.recv.clear(); clearFound(); renderAll(); }, "team");
on($("#tpartner"), "change", e=>{ TRADE.partner = e.target.value; TRADE.recv.clear(); renderTrade(); }, "tpartner");
on($("#tscale"), "change", e=>{ TRADE.scale = e.target.value; clearFound(); renderTrade(); }, "tscale");
on($("#findbtn"), "click", runFinder, "findbtn");
on($("#tclear"), "click", ()=>{ TRADE.give.clear(); TRADE.recv.clear(); renderTrade(); }, "tclear");
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
try {
  if (!localStorage.getItem("fr_team")) showPicker();
} catch(e){ showPicker(); }
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
        "slots": lg["slots"],
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
  <div id="picker" hidden>
    <h1 id="whoami" title="Click to flip every photo">Who are you</h1>
    <div class="pgrid" id="pgrid"></div>
  </div>

  <div class="grid">
    {panel("sell", "p-sell", "Sell high", "draft-day name value they no longer earn")}
    {panel("buy", "p-buy", "Buy low", "on other rosters &middot; drafted late, producing now")}
    {panel("adds", "p-adds", "Waiver adds", "free agents above the weakest starter")}
    {panel("drops", "p-drops", "Drop candidates", "below the best free agent at that spot")}
  </div>
  {panel("", "p-stash", "IR stash", "costs no active roster spot")}

  <h2 class="sec">League power rankings</h2>
  <p class="secsub">Every roster scored on the board selected at the top.
    <b>Starters</b> is the best lineup that roster can field; <b>bench</b> is everything else.
    A team strong on one and weak on the other is the one to trade with.
    <span id="powernote"></span></p>
  <div class="tablewrap" id="powerwrap">
    <table><thead><tr>
      <th class="r">#</th><th>Team</th>
      <th class="r" data-ps="start">Starters<span class="car"></span></th>
      <th class="r">Bench</th>
      <th class="r" data-ps="total">Full roster<span class="car"></span></th>
      <th class="r">Ranked</th><th>Best player</th>
    </tr></thead><tbody id="powerbody"></tbody></table>
  </div>

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

  <h2 class="sec">Recommended trades</h2>
  <p class="secsub">Scans every rival roster for deals that improve <b>both</b> starting lineups,
    on the board selected below. A deal only you gain from is one the other manager turns down.</p>
  <div id="findbar">
    <button id="findbtn" type="button">Find trades</button>
    <span id="findnote"></span>
  </div>
  <div id="findout"></div>

  <h2 class="sec">Trade evaluator</h2>
  <p class="secsub">Pick players from each roster. Scored on the rest-of-season board by default,
    since that is the horizon a trade is made for.</p>
  <div class="tradebar">
    <label for="tpartner" class="eyebrow">Trade with</label>
    <select id="tpartner"></select>
    <label for="tscale" class="eyebrow">Board</label>
    <select id="tscale">
      <option value="ros">Rest of season</option>
      <option value="week">This week</option>
      <option value="draft">Draft day</option>
    </select>
    <button id="tclear" class="chip" type="button">Clear</button>
  </div>
  <div class="tradegrid">
    <div class="tradecol"><h3>You send <span id="tmineh"></span></h3>
      <div class="tradelist" id="tmine"></div></div>
    <div class="tradecol"><h3>You get <span id="ttheirsh"></span></h3>
      <div class="tradelist" id="ttheirs"></div></div>
  </div>
  <div id="tradeout"></div>

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
