"""Dashboard generator: renders scan.json into a self-contained dashboard.html.

The HTML embeds the data — no network, works offline, follows OS light/dark.
"""

import json
import sys
from pathlib import Path

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Footprint</title>
<style>
:root {
  color-scheme: light;
  --page:      #f9f9f7;
  --surface:   #fcfcfb;
  --ink:       #0b0b0b;
  --ink-2:     #52514e;
  --muted:     #898781;
  --grid:      #e1e0d9;
  --baseline:  #c3c2b7;
  --border:    rgba(11,11,11,0.10);
  --series-1:  #2a78d6;
  --series-2:  #eb6834;
  --series-3:  #1baf7a;
  --series-4:  #eda100;
  --series-5:  #e87ba4;
  --series-6:  #4a3aa7;
  --seq:       #2a78d6;
  --seq-soft:  #9ec5f4;
  --good:      #0ca30c;
  --warning:   #fab219;
  --serious:   #ec835a;
  --critical:  #d03b3b;
}
@media (prefers-color-scheme: dark) {
  :root:where(:not([data-theme="light"])) {
    color-scheme: dark;
    --page:      #0d0d0d;
    --surface:   #1a1a19;
    --ink:       #ffffff;
    --ink-2:     #c3c2b7;
    --muted:     #898781;
    --grid:      #2c2c2a;
    --baseline:  #383835;
    --border:    rgba(255,255,255,0.10);
    --series-1:  #3987e5;
    --series-2:  #d95926;
    --series-3:  #199e70;
    --series-4:  #c98500;
    --series-5:  #d55181;
    --series-6:  #9085e9;
    --seq:       #3987e5;
    --seq-soft:  #184f95;
  }
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --page:      #0d0d0d;
  --surface:   #1a1a19;
  --ink:       #ffffff;
  --ink-2:     #c3c2b7;
  --muted:     #898781;
  --grid:      #2c2c2a;
  --baseline:  #383835;
  --border:    rgba(255,255,255,0.10);
  --series-1:  #3987e5;
  --series-2:  #d95926;
  --series-3:  #199e70;
  --series-4:  #c98500;
  --series-5:  #d55181;
  --series-6:  #9085e9;
  --seq:       #3987e5;
  --seq-soft:  #184f95;
}
* { box-sizing: border-box; margin: 0; }
body {
  background: var(--page); color: var(--ink);
  font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif;
  padding: 24px; max-width: 1200px; margin: 0 auto;
}
header { display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; margin-bottom: 20px; }
header h1 { font-size: 22px; font-weight: 700; }
header .meta { color: var(--muted); font-size: 12.5px; }
.tiles { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 12px; margin-bottom: 20px; }
.tile { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.tile .label { color: var(--ink-2); font-size: 12.5px; }
.tile .value { font-size: 26px; font-weight: 700; margin-top: 2px; }
.tile .sub { font-size: 12px; margin-top: 2px; color: var(--muted); }
.tile .sub.bad { color: var(--critical); font-weight: 600; }
.grid2 { display: grid; grid-template-columns: repeat(auto-fit, minmax(380px, 1fr)); gap: 12px; margin-bottom: 20px; }
.card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
.card h2 { font-size: 14px; font-weight: 600; margin-bottom: 12px; }
.card h2 .hint { color: var(--muted); font-weight: 400; font-size: 12px; margin-left: 6px; }

/* horizontal bars */
.hbar-row { display: grid; grid-template-columns: 150px 1fr 76px; gap: 8px; align-items: center; margin-bottom: 2px; min-height: 24px; }
.hbar-label { font-size: 12.5px; color: var(--ink-2); text-align: right; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.hbar-track { position: relative; height: 16px; }
.hbar-fill { position: absolute; left: 0; top: 2px; height: 12px; border-radius: 0 4px 4px 0; min-width: 2px; }
.hbar-val { font-size: 12px; color: var(--ink-2); font-variant-numeric: tabular-nums; }

/* column chart */
.cols { display: flex; align-items: flex-end; gap: 2px; height: 110px; border-bottom: 1px solid var(--baseline); }
.col { flex: 1; min-width: 3px; border-radius: 4px 4px 0 0; background: var(--seq); }
.col.zero { height: 2px !important; background: var(--grid); border-radius: 0; }
.cols-x { display: flex; justify-content: space-between; color: var(--muted); font-size: 11px; margin-top: 4px; }

/* legend */
.legend { display: flex; gap: 14px; flex-wrap: wrap; margin-top: 10px; font-size: 12px; color: var(--ink-2); }
.legend .sw { display: inline-block; width: 10px; height: 10px; border-radius: 3px; margin-right: 5px; vertical-align: -1px; }

/* tables */
table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
th { text-align: left; color: var(--muted); font-weight: 500; padding: 4px 8px; border-bottom: 1px solid var(--grid); }
td { padding: 5px 8px; border-bottom: 1px solid var(--grid); vertical-align: top; }
td.num, th.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11.5px; color: var(--ink-2); word-break: break-all; }
.badge { display: inline-flex; align-items: center; gap: 4px; font-size: 11px; font-weight: 600; padding: 1px 8px; border-radius: 999px; border: 1px solid var(--border); white-space: nowrap; }
.badge::before { font-size: 10px; }
.badge.ok       { color: var(--good); }     .badge.ok::before       { content: "✓"; }
.badge.stale    { color: var(--warning); } .badge.stale::before    { content: "◷"; }
.badge.prunable { color: var(--serious); } .badge.prunable::before { content: "⚠"; }
.badge.missing  { color: var(--critical); } .badge.missing::before { content: "✕"; }
.src { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; }
.src .sw { width: 9px; height: 9px; border-radius: 3px; }
.scroll { max-height: 420px; overflow-y: auto; }
.wide { overflow-x: auto; }
footer { color: var(--muted); font-size: 12px; margin-top: 8px; }

/* tooltip */
#tip { position: fixed; pointer-events: none; background: var(--surface); color: var(--ink);
  border: 1px solid var(--border); border-radius: 8px; padding: 6px 10px; font-size: 12px;
  box-shadow: 0 4px 14px rgba(0,0,0,0.18); display: none; z-index: 10; max-width: 320px; }
#tip .t { color: var(--muted); }
</style>
</head>
<body>
<div id="tip"></div>
<header>
  <h1>Agent Footprint</h1>
  <span class="meta" id="meta"></span>
</header>
<div class="tiles" id="tiles"></div>
<div class="grid2">
  <div class="card"><h2>Disk footprint by category</h2><div id="disk"></div></div>
  <div class="card"><h2>Worktrees by creator<span class="hint">who left these behind</span></h2><div id="wtsrc"></div><div class="legend" id="wtlegend"></div></div>
  <div class="card"><h2>Claude session activity<span class="hint">sessions last active per day, past 30 days</span></h2><div id="activity"></div></div>
  <div class="card"><h2>Claude projects by transcript size</h2><div id="projects"></div></div>
</div>
<div class="card" style="margin-bottom:12px"><h2>Worktrees<span class="hint">everything git still tracks outside the main checkout</span></h2><div class="scroll wide" id="wttable"></div></div>
<div class="grid2">
  <div class="card"><h2>Scratchpads<span class="hint">per-session temp dirs in /private/tmp</span></h2><div id="pads"></div></div>
  <div class="card"><h2>Running AI processes</h2><div class="wide" id="procs"></div></div>
  <div class="card"><h2>Background agents<span class="hint">launchd + cron</span></h2><div id="sched"></div></div>
  <div class="card"><h2>Ollama models</h2><div class="scroll" id="ollama"></div></div>
</div>
<footer>Refresh: <code>agent-footprint</code> · Clean up: <code>agent-footprint clean</code> (dry run) then <code>--apply</code></footer>

<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById("data").textContent);
const $ = (id) => document.getElementById(id);
const esc = (s) => String(s).replace(/[&<>"]/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
const fmtB = (n) => { const u=["B","KB","MB","GB","TB"]; let i=0; while(n>=1024&&i<u.length-1){n/=1024;i++;} return n.toFixed(n>=10||i===0?0:1)+" "+u[i]; };
const SRC_COLORS = {cursor:"var(--series-1)", codex:"var(--series-2)", claude:"var(--series-3)", tmp:"var(--series-4)", manual:"var(--series-5)", openclaw:"var(--series-6)"};
const SRC_ORDER = ["cursor","codex","claude","tmp","manual","openclaw"];

/* tooltip */
const tip = $("tip");
function bindTip(el, html) {
  el.addEventListener("mousemove", e => { tip.style.display="block"; tip.innerHTML=html;
    tip.style.left = Math.min(e.clientX+14, innerWidth-330)+"px"; tip.style.top=(e.clientY+14)+"px"; });
  el.addEventListener("mouseleave", () => tip.style.display="none");
}

/* header + tiles */
const S = D.summary;
$("meta").textContent = D.host + " · scanned " + new Date(D.generated_at).toLocaleString();
const totalDisk = S.claude_home_bytes + S.scratchpad_bytes + S.cache_bytes + S.worktree_bytes;
const tiles = [
  {label:"AI disk footprint", value: fmtB(totalDisk), sub:"caches + sessions + worktrees + scratch"},
  {label:"Git worktrees", value: S.worktree_count, sub: S.prunable_worktrees ? S.prunable_worktrees+" prunable" : "none prunable", bad: S.prunable_worktrees>0},
  {label:"Stale worktrees", value: S.stale_worktrees, sub:"untouched > 30 days", bad: S.stale_worktrees>0},
  {label:"Claude sessions", value: S.session_count, sub: D.claude_home.projects.length+" projects"},
  {label:"Scratchpad", value: fmtB(S.scratchpad_bytes), sub: D.scratchpads.filter(p=>p.stale).length+" stale dirs"},
  {label:"AI processes", value: S.running_processes, sub:"running now"},
];
$("tiles").innerHTML = tiles.map(t=>`<div class="tile"><div class="label">${t.label}</div><div class="value">${t.value}</div><div class="sub${t.bad?" bad":""}">${t.sub}</div></div>`).join("");

/* generic horizontal bar renderer (magnitude -> one hue) */
function hbars(el, rows, {color="var(--seq)", tipFn}={}) {
  const max = Math.max(...rows.map(r=>r.value), 1);
  el.innerHTML = rows.map((r,i)=>`
    <div class="hbar-row" data-i="${i}">
      <div class="hbar-label" title="${esc(r.label)}">${esc(r.label)}</div>
      <div class="hbar-track"><div class="hbar-fill" style="width:${Math.max(100*r.value/max,0.5)}%;background:${r.color||color}"></div></div>
      <div class="hbar-val">${r.display ?? fmtB(r.value)}</div>
    </div>`).join("");
  el.querySelectorAll(".hbar-row").forEach((rowEl,i)=>{
    const r = rows[i];
    bindTip(rowEl, tipFn ? tipFn(r) : `<b>${esc(r.label)}</b><br>${r.display ?? fmtB(r.value)}`);
  });
}

/* disk by category */
const cacheRows = D.model_caches.caches.map(c=>({label:c.name, value:c.bytes}));
hbars($("disk"), [
  ...cacheRows,
  {label:"Claude home (~/.claude)", value:S.claude_home_bytes},
  {label:"Worktree checkouts", value:S.worktree_bytes},
  {label:"Scratchpads (/tmp)", value:S.scratchpad_bytes},
].sort((a,b)=>b.value-a.value));

/* worktrees by source (identity -> categorical, color follows entity) */
const allWt = D.worktrees.flatMap(r=>r.worktrees.map(w=>({...w, repo:r.name})));
const bySrc = {};
allWt.forEach(w=>{ bySrc[w.source]=(bySrc[w.source]||0)+1; });
const srcRows = SRC_ORDER.filter(s=>bySrc[s]).map(s=>({label:s, value:bySrc[s], display:String(bySrc[s]), color:SRC_COLORS[s]}));
hbars($("wtsrc"), srcRows, {tipFn: r=>`<b>${esc(r.label)}</b><br>${r.value} worktrees`});
$("wtlegend").innerHTML = srcRows.map(r=>`<span><span class="sw" style="background:${r.color}"></span>${esc(r.label)}</span>`).join("");

/* activity columns: last 30 days */
const days = [...Array(30)].map((_,i)=>{ const d=new Date(); d.setDate(d.getDate()-(29-i)); return d.toISOString().slice(0,10); });
const perDay = Object.fromEntries(days.map(d=>[d,0]));
D.claude_home.projects.forEach(p=>p.sessions.forEach(s=>{
  const d = (s.last_active||"").slice(0,10);
  if (d in perDay) perDay[d]++;
}));
const maxDay = Math.max(...Object.values(perDay), 1);
$("activity").innerHTML = `<div class="cols">` + days.map(d=>{
  const v = perDay[d];
  return `<div class="col ${v?"":"zero"}" style="height:${Math.max(100*v/maxDay,2)}%" data-d="${d}" data-v="${v}"></div>`;
}).join("") + `</div><div class="cols-x"><span>${days[0]}</span><span>${days[29]}</span></div>`;
$("activity").querySelectorAll(".col").forEach(c=>bindTip(c, `<b>${c.dataset.d}</b><br>${c.dataset.v} session(s) active`));

/* projects by size */
hbars($("projects"), D.claude_home.projects.slice(0,8).map(p=>({
  label: p.name.replace(/^-(Users|home)-[^-]+-(Desktop-|Documents-)?/,"").replace(/^GitHub-/,""), value: p.bytes,
  _p: p,
})), {tipFn: r=>`<b>${esc(r._p.name)}</b><br>${fmtB(r.value)} · ${r._p.session_count} sessions · ${r._p.memory_files} memory files`});

/* worktree table */
function wtState(w){ return w.missing?["missing","missing"] : w.prunable?["prunable","prunable"] : w.stale?["stale","stale"] : ["ok","ok"]; }
$("wttable").innerHTML = `<table><tr><th>Repo</th><th>Branch</th><th>Creator</th><th class="num">Age</th><th class="num">Size</th><th>State</th><th>Path</th></tr>` +
  allWt.sort((a,b)=> (b.missing||b.prunable)-(a.missing||a.prunable) || (b.age_days||0)-(a.age_days||0))
  .map(w=>{ const [cls,txt]=wtState(w); return `<tr>
    <td>${esc(w.repo)}</td><td class="mono">${esc(w.branch)}</td>
    <td><span class="src"><span class="sw" style="background:${SRC_COLORS[w.source]||"var(--muted)"}"></span>${esc(w.source)}</span></td>
    <td class="num">${w.age_days!=null? w.age_days.toFixed(0)+"d":"–"}</td>
    <td class="num">${w.bytes?fmtB(w.bytes):"–"}</td>
    <td><span class="badge ${cls}">${txt}</span></td>
    <td class="mono">${esc(w.path)}</td></tr>`; }).join("") + `</table>`;

/* scratchpads */
$("pads").innerHTML = `<table><tr><th>Project</th><th class="num">Size</th><th class="num">Age</th><th>State</th></tr>` +
  D.scratchpads.map(p=>`<tr><td class="mono" title="${esc(p.path)}">${esc(p.path.split("/").slice(-1)[0])}</td>
   <td class="num">${fmtB(p.bytes)}</td><td class="num">${p.age_days!=null?p.age_days.toFixed(1)+"d":"–"}</td>
   <td><span class="badge ${p.stale?"stale":"ok"}">${p.stale?"stale":"active"}</span></td></tr>`).join("") + `</table>`;

/* processes — grouped by command so 70 copies of one binary read as one row */
const groups = {};
D.processes.forEach(p=>{
  const key = p.command.replace(/\s+-.*$/,"").slice(0,90);
  (groups[key] ||= {n:0, cpu:0, mem:0, cmd:key}).n++;
  groups[key].cpu += p.cpu_pct; groups[key].mem += p.rss_mb;
});
$("procs").innerHTML = `<table><tr><th class="num">Count</th><th class="num">CPU</th><th class="num">Mem</th><th>Command</th></tr>` +
  Object.values(groups).sort((a,b)=>b.n-a.n || b.cpu-a.cpu)
  .map(g=>`<tr><td class="num">${g.n}×</td><td class="num">${g.cpu.toFixed(1)}%</td>
   <td class="num">${g.mem} MB</td><td class="mono">${esc(g.cmd)}</td></tr>`).join("") + `</table>`;

/* schedulers */
const ai = D.schedulers.launch_agents.filter(a=>a.ai_related);
const rest = D.schedulers.launch_agents.length - ai.length;
$("sched").innerHTML = `<table><tr><th>launchd label</th></tr>` +
  ai.map(a=>`<tr><td class="mono">${esc(a.label)}</td></tr>`).join("") +
  `<tr><td class="mono" style="color:var(--muted)">… + ${rest} non-agent launch agents</td></tr>` +
  (D.schedulers.cron.length? D.schedulers.cron.map(c=>`<tr><td class="mono">cron: ${esc(c)}</td></tr>`).join(""):"") + `</table>`;

/* ollama */
$("ollama").innerHTML = D.model_caches.ollama_models.length
  ? `<table><tr><th>Model</th><th class="num">Size</th></tr>` + D.model_caches.ollama_models.map(m=>`<tr><td class="mono">${esc(m.name)}</td><td class="num">${esc(m.size)}</td></tr>`).join("") + `</table>`
  : `<div style="color:var(--muted)">ollama not reachable during scan</div>`;
</script>
</body>
</html>
"""


def report(data_dir):
    data_dir = Path(data_dir)
    scan_path = data_dir / "scan.json"
    if not scan_path.exists():
        sys.exit(f"No {scan_path} - run `agent-footprint scan` first.")
    data = json.loads(scan_path.read_text())
    html = TEMPLATE.replace("__DATA__", json.dumps(data).replace("</", "<\\/"))
    out = data_dir / "dashboard.html"
    out.write_text(html)
    print(f"Wrote {out}", file=sys.stderr)
    return out
