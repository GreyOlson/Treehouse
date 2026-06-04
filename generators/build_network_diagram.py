#!/usr/bin/env python3
"""
build_network_diagram.py
========================
Per-service node-link (network) diagram of every ATTRIBUTE-bearing instance.

DESIGN (current spec):
  - Only instances that actually carry attributes are drawn as nodes. Pure
    scaffolding containers (Folders/Models with no attributes) are PATH-COMPRESSED
    away: each attributed node re-attaches to its nearest attributed ancestor (or
    the service root). The full original path is shown on hover.
  - Each instance's attributes are drawn as indented child rows beneath it
    (tabbed one level in), showing  Name = value (type)  with the */** marker.
  - There is no full-hierarchy mode and no "(no attributes)" tooltip -- attributes
    are always visible inline.

Reuses build_attribute_tree.py for parsing + the */** marker layer.
Output: single self-contained HTML, no CDN dependencies.

INPUT  : Trees/AttributeTree.luau  + src/
OUTPUT : Trees/NetworkDiagram.html
RE-RUN : python3 Trees/build_network_diagram.py

This module also exposes `render_network(...)` and `ENGINE_TEMPLATE` so the
ValueBase network generator can reuse the exact same engine.
"""

import os
import json
import html
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    "build_attribute_tree", os.path.join(HERE, "build_attribute_tree.py")
)
bat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bat)

OUT_PATH = os.path.join(bat.PROJECT_ROOT, "working", "NetworkDiagram.html")


# ---------------------------------------------------------------------------
# Generic path-compression. Input nodes are dicts:
#   {"n":name, "c":class, "items":[{...}], "ch":[child...]}
# A node is a "carrier" if it has >=1 item. Service root is always kept.
# Output display node:
#   {"n","c","path"(full path to node),"items":[...],"ch":[display...]}
# ---------------------------------------------------------------------------
def compress(root):
    disp = {"n": root["n"], "c": root["c"], "path": root["n"],
            "items": root.get("items", []), "ch": []}

    def is_carrier(node):
        return len(node.get("items", [])) > 0

    def walk(node, parent_disp, path):
        for kid in node.get("ch", []):
            kpath = path + "." + kid["n"]
            if is_carrier(kid):
                d = {"n": kid["n"], "c": kid["c"], "path": kpath,
                     "items": kid.get("items", []), "ch": []}
                parent_disp["ch"].append(d)
                walk(kid, d, kpath)
            else:
                walk(kid, parent_disp, kpath)  # skip; re-parent descendants

    walk(root, disp, root["n"])
    return disp


def count_display(d):
    """returns (instances, items)"""
    inst, items = 1, len(d["items"])
    for c in d["ch"]:
        i2, it2 = count_display(c)
        inst += i2
        items += it2
    return inst, items


# ---------------------------------------------------------------------------
# Attribute dataset -> uniform {n,c,items,ch}
# ---------------------------------------------------------------------------
def attr_node_to_uniform(node):
    items = [{"n": a["n"], "v": a["v"], "t": a["t"], "m": a["m"]}
             for a in node["a"] if not a["rojo"]]
    return {"n": node["n"], "c": node["c"], "items": items,
            "ch": [attr_node_to_uniform(c) for c in node["ch"]]}


def main():
    runtime_set, runtime_nil = bat.scan_runtime_attributes(bat.SRC_DIR)
    roots, _total = bat.parse_dump(bat.DUMP_PATH)
    stats = {"rojo_attr_count": 0, "real_attr_count": 0, "design_names": set(),
             "star_count": 0, "dstar_count": 0, "attributed_instances": 0}
    serialized = [bat.serialize(r, runtime_set, runtime_nil, stats) for r in roots]

    services = []
    tot_inst = tot_items = 0
    for s in serialized:
        disp = compress(attr_node_to_uniform(s))
        ic, it = count_display(disp)
        # subtract the root itself if it carries no items (it's just an anchor)
        services.append(disp)
        tot_inst += ic
        tot_items += it

    summary = {"project": bat.PROJECT_NAME, "item_kind": "attribute",
               "item_label": "attributes",
               "services": [{"name": s["n"], "instances": count_display(s)[0],
                             "items": count_display(s)[1]} for s in services],
               "total_instances": tot_inst, "total_items": tot_items}

    html_out = render_network(services, summary)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)
    print("Wrote", OUT_PATH)
    print("attributed instances drawn:", stats["attributed_instances"],
          "| attribute rows:", stats["real_attr_count"])
    for s in summary["services"]:
        print(f"  {s['name']:<22} instances(+anchor)={s['instances']:<6} attributes={s['items']}")


# ---------------------------------------------------------------------------
# Renderer (shared engine).
# ---------------------------------------------------------------------------
def render_network(services, summary):
    payload = json.dumps({"services": services, "summary": summary})
    out = ENGINE_TEMPLATE.replace("/*__DATA__*/", "const DATA = " + payload + ";")
    out = out.replace("__PROJECT__", html.escape(bat.PROJECT_NAME))
    kind = "Value*" if summary.get("item_kind") == "value" else "Attribute"
    out = out.replace("__KIND__", kind)
    return out


ENGINE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__PROJECT__ - __KIND__ Treehouse</title>
<style>
  :root{
    --bg:#0f1117; --panel:#161922; --ink:#e6e9f0; --dim:#9aa3b2;
    --line:#2a2f3d; --row:#1b1f2a; --rowh:#232838; --accent:#7cc4ff;
    --edge:#39414f; --star:#ffb454; --dstar:#ff6b6b; --badge:#272c3a;
    --item:#d7dbe3; --val:#9ece6a; --type:#7a8294; --vcls:#b794f6;
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--bg);color:var(--ink);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header{position:sticky;top:0;z-index:20;background:var(--panel);
    border-bottom:1px solid var(--line);padding:10px 14px}
  h1{margin:0 0 6px;font-size:15px;font-weight:600}
  .sub{color:var(--dim);font-size:11px;margin-bottom:6px}
  .tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .tab{background:var(--row);border:1px solid var(--line);color:var(--dim);
    border-radius:6px;padding:5px 9px;cursor:pointer;font:inherit}
  .tab .ct{color:var(--accent);font-size:11px}
  .tab.active{background:var(--accent);color:#0b0d12;border-color:var(--accent)}
  .tab.active .ct{color:#0b0d12}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  input[type=search]{background:var(--row);border:1px solid var(--line);
    color:var(--ink);border-radius:6px;padding:6px 10px;font:inherit;
    flex:1 1 320px;min-width:240px;max-width:520px}
  #minwrap{display:inline-flex;align-items:center;gap:6px;color:var(--dim);
    font-size:11px;white-space:nowrap}
  #minwrap input[type=range]{width:96px}
  #minlbl{color:var(--accent);font-weight:700;min-width:22px;text-align:right}
  button{background:var(--row);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
  button:hover{background:var(--rowh)}
  .legend{margin-left:auto;display:flex;gap:10px;flex-wrap:wrap;
    color:var(--dim);font-size:11px;max-width:60%;justify-content:flex-end}
  .legend span{display:inline-flex;align-items:center;gap:4px;cursor:pointer;user-select:none}
  .legend span:hover{color:var(--ink)}
  .legend span.off{opacity:.4;text-decoration:line-through}
  .dot{width:9px;height:9px;border-radius:50%;display:inline-block}
  .hint{color:var(--dim);font-size:11px;margin-top:4px}
  #hiddencount{padding:6px 14px;background:var(--panel);border-bottom:1px solid var(--line);
    color:var(--accent);font-size:11px}
  #wrap{position:relative;overflow:auto;height:calc(100vh - 178px)}
  svg{display:block}
  .edge{fill:none;stroke:var(--edge);stroke-width:1}
  .node{cursor:pointer}
  .node tspan.nm{fill:var(--ink)}
  .node tspan.cl{fill:var(--dim);font-size:10px}
  .node.match tspan.nm{fill:#ffd479;font-weight:700}
  .item tspan.inm{fill:var(--item)}
  .item tspan.ival{fill:var(--val)}
  .item tspan.itype{fill:var(--type);font-size:10px}
  .item tspan.icls{fill:var(--vcls);font-size:10px}
  .item tspan.mk.s{fill:var(--star);font-weight:700}
  .item tspan.mk.d{fill:var(--dstar);font-weight:700}
  .item tspan.ncmk{fill:#ff5555;font-weight:700}
  #tip{position:fixed;z-index:50;pointer-events:none;display:none;
    background:#0b0d12;border:1px solid var(--line);border-radius:6px;
    padding:7px 9px;max-width:520px;box-shadow:0 6px 24px rgba(0,0,0,.5);
    color:var(--dim);font-size:11.5px}
  #tip b{color:var(--accent)}
  #toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:60;
    display:none;background:#0b0d12;border:1px solid var(--accent);border-radius:6px;
    padding:7px 12px;color:var(--ink);font-size:12px;box-shadow:0 6px 24px rgba(0,0,0,.5)}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__ - __KIND__ Treehouse</h1>
  <div class="sub" id="sub"></div>
  <div class="sub" id="svccount" style="color:var(--accent)"></div>
  <div class="tabs" id="tabs"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="find an instance or item by name or number&hellip;"/>
    <label id="minwrap" title="show only instances that have at least this many">
      &ge;&nbsp;<span id="minlbl">1+</span>&nbsp;<span id="minunit">items</span>
      <input type="range" id="minattrs" min="1" max="10" step="1" value="1"/>
    </label>
    <button id="expandAll">Expand all</button>
    <button id="collapseAll">Collapse all</button>
    <span class="hint" id="counter"></span>
    <div class="legend" id="legend"></div>
  </div>
  <div class="hint">Only instances that carry <span id="lbl1">items</span> are shown; empty containers are path-compressed (hover a node for its real path). <span id="lbl2">Items</span> are tabbed beneath their instance. <span style="color:var(--star)">*</span> set in code, <span style="color:var(--dstar)">**</span> <span id="dstarlbl">nil-able</span>.</div>
</header>
<div id="hiddencount"></div>
<div id="wrap"><svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
<div id="tip"></div>
<div id="toast"></div>
<script>
/*__DATA__*/

const ROWH=20, COLW=280, PADX=20, PADY=16, NODER=4;
const PALETTE=["#7cc4ff","#9ece6a","#ffb454","#ff6b6b","#b794f6","#4fd6be",
  "#f7768e","#e0af68","#73daca","#bb9af7","#7aa2f7","#ff9e64","#41a6b5","#d19a66"];
let classColor={}, paletteIdx=0;
function colorFor(c){ if(!(c in classColor)) classColor[c]=PALETTE[paletteIdx++%PALETTE.length]; return classColor[c]; }
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// build a render tree (instances + item-leaves) per service
function buildRender(d, depth, parent){
  const node={kind:'inst', n:d.n, c:d.c, path:d.path, _depth:depth, _p:parent,
    _expanded: depth<3, _children:[]};
  for(const it of (d.items||[])){
    node._children.push({kind:'item', it, n:it.n, _depth:depth+1, _p:node, _children:[]});
  }
  for(const c of (d.ch||[])){
    node._children.push(buildRender(c, depth+1, node));
  }
  return node;
}
const RENDER = DATA.services.map(s=>buildRender(s,0,null));
let curIdx=0, current=RENDER[curIdx];

// tabs
const tabs=document.getElementById('tabs');
DATA.summary.services.forEach((s,i)=>{
  const b=document.createElement('button');
  b.className='tab'+(i===0?' active':'');
  b.textContent=s.name; // counts moved to the per-service line below the global count
  b.onclick=()=>{ curIdx=i; current=RENDER[i];
    [...tabs.children].forEach(c=>c.classList.remove('active')); b.classList.add('active');
    document.getElementById('search').value=''; q=''; render(); };
  tabs.appendChild(b);
});
document.getElementById('sub').innerHTML =
  'Global Count: '+DATA.summary.total_instances+' instances with '+DATA.summary.item_label+', '+
  DATA.summary.total_items+' '+DATA.summary.item_label+' total (across all services).'+
  (DATA.summary.nc_note ? ' &nbsp; <span style="color:#ff5555"><b>***</b> = stores an Instance ref - cannot become an attribute.</span>' : '');

const svg=document.getElementById('svg'), tip=document.getElementById('tip');
let q='';
const hiddenTypes=new Set();            // instance classes toggled off via the legend
let minAttrs=1;                         // slider: show instances with >= N attributes
let isoNode=null;                       // double-clicked node: isolate its branch
let lastTotalItems=0, lastShownItems=0; // for the "hidden" counter (current service)

// Set _show on every node from the active filters: search text, hidden types,
// the ">= N attributes" slider, and (if set) branch isolation. Also tally how
// many of the current service's items pass, for the hidden counter.
function computeVisibility(){
  lastTotalItems=0; lastShownItems=0;
  const inSub=new Set(), anc=new Set();
  if(isoNode){
    (function mark(n){ inSub.add(n); n._children.forEach(mark); })(isoNode);
    for(let p=isoNode._p;p;p=p._p) anc.add(p);
  }
  function rec(n, ancTypeOk, isRoot){
    const typeOk = isRoot ? true : (ancTypeOk && !hiddenTypes.has(n.c));
    let directCount=0, anyItemMatch=false, subtreeTarget=false;
    for(const c of n._children){
      if(c.kind==='item'){
        lastTotalItems++; directCount++;
        c._matchQ = !q || c.n.toLowerCase().indexOf(q)!==-1 || String(c.it.v).toLowerCase().indexOf(q)!==-1;
        if(c._matchQ) anyItemMatch=true;
      } else if(rec(c, typeOk, false)) subtreeTarget=true;
    }
    const nameMatch = !q || n.n.toLowerCase().indexOf(q)!==-1;
    const countOk = directCount >= minAttrs;
    let show, showItems, target;
    if(isoNode){
      // isolation: the isolated branch is shown in full, plus the ancestor path
      if(inSub.has(n)){ show=true; showItems=true; target=true; }
      else if(anc.has(n) || isRoot){ show=true; showItems=false; target=subtreeTarget; }
      else { show=false; showItems=false; target=false; }
    } else {
      target = typeOk && countOk && (!q || nameMatch || anyItemMatch);
      show = isRoot ? true : (typeOk && (target || subtreeTarget));
      showItems = isRoot ? (countOk && (!q || nameMatch || anyItemMatch)) : target;
    }
    n._show = show;
    for(const c of n._children){ if(c.kind==='item'){ c._show=showItems; if(showItems) lastShownItems++; } }
    return target || subtreeTarget;
  }
  rec(current, true, true);
}

// Lay out only nodes that pass the filters (_show) and whose ancestors are
// expanded. Rows go only to those, so hidden branches leave no gaps.
function layout(root){
  let row=0; const nodes=[], links=[];
  (function visit(n){
    n._x=PADX+n._depth*COLW;
    const kids=n._children.filter(c=>c._show);
    const exp=n._expanded && kids.length && n.kind==='inst';
    if(exp){
      for(const c of kids){ visit(c); links.push([n,c]); }
      n._y=(kids[0]._y + kids[kids.length-1]._y)/2;
    } else {
      n._y=PADY+row*ROWH+ROWH/2; row++;
    }
    nodes.push(n);
  })(root);
  return {nodes,links,rows:row};
}
function trunc(v){ v=String(v); return v.length>40? v.slice(0,40)+'…' : v; }

function render(){
  computeVisibility();
  const {nodes,links,rows}=layout(current);
  let maxDepth=0; for(const n of nodes) if(n._depth>maxDepth) maxDepth=n._depth;
  const W=PADX*2+(maxDepth+1)*COLW+260, H=PADY*2+Math.max(rows,1)*ROWH;
  svg.setAttribute('width',W); svg.setAttribute('height',H); svg.setAttribute('viewBox','0 0 '+W+' '+H);
  let s='';
  for(const [p,c] of links){
    const x1=p._x+NODER,y1=p._y,x2=c._x-NODER,y2=c._y,mx=(x1+x2)/2;
    s+='<path class="edge" d="M'+x1+','+y1+' C'+mx+','+y1+' '+mx+','+y2+' '+x2+','+y2+'"/>';
  }
  for(const n of nodes){
    if(n.kind==='inst'){
      const hasKids=n._children.filter(c=>c._show).length;
      const col=colorFor(n.c), filled=hasKids&&!n._expanded;
      const match=q&&n.n.toLowerCase().indexOf(q)!==-1;
      s+='<g class="node'+(match?' match':'')+'" data-i="'+n._idx+'" transform="translate('+n._x+','+n._y+')">';
      s+='<circle r="'+NODER+'" fill="'+(filled?col:'#0f1117')+'" stroke="'+col+'"/>';
      const tx=NODER+6;
      s+='<text x="'+tx+'" y="3.5"><tspan class="nm">'+esc(n.n)+'</tspan>'+
         '<tspan class="cl" dx="6">['+esc(n.c)+']</tspan></text>';
      s+='</g>';
    } else {
      const it=n.it;
      const match=q&&(it.n.toLowerCase().indexOf(q)!==-1);
      s+='<g class="item'+(match?' match':'')+'" data-i="'+n._idx+'" transform="translate('+n._x+','+n._y+')">';
      s+='<rect x="-3" y="-1.5" width="3" height="3" fill="'+(it.m==='**'?'var(--dstar)':it.m==='*'?'var(--star)':'#5f6b80')+'"/>';
      // Inline <tspan>s so the (type) always sits at the end of the value extent.
      s+='<text x="8" y="3.5">';
      s+='<tspan class="inm">'+esc(it.n)+'</tspan>';
      if(it.c){ s+='<tspan class="icls" dx="6">['+esc(it.c)+']</tspan>'; }
      if(it.m){ s+='<tspan class="mk '+(it.m==='**'?'d':'s')+'" dx="6">'+it.m+'</tspan>'; }
      s+='<tspan class="itype" dx="6">=</tspan>';
      s+='<tspan class="ival" dx="6">'+esc(trunc(it.v))+'</tspan>';
      s+='<tspan class="itype" dx="6">('+esc(it.t)+')</tspan>';
      if(it.nc){ s+='<tspan class="ncmk" dx="6">***</tspan>'; }
      s+='</text>';
      s+='</g>';
    }
  }
  svg.innerHTML=s;
  const svc=DATA.summary.services[curIdx];
  document.getElementById('svccount').textContent =
    current.n+' Count: '+svc.instances+' instances, '+svc.items+' '+DATA.summary.item_label;
  document.getElementById('counter').textContent = nodes.length+' rows shown';
  const hidden=lastTotalItems-lastShownItems;
  document.getElementById('hiddencount').textContent =
    hidden+' of '+lastTotalItems+' '+DATA.summary.item_label+' hidden in '+current.n+
    (hidden>0?' by current filters (search + hidden types).':' - all shown.');
  buildLegend();
}

function buildLegend(){
  const present={};
  current._children.forEach(function w(n){ if(n.kind==='inst'){ present[n.c]=true; n._children.forEach(w);} });
  const keys=Object.keys(present);
  const lg=document.getElementById('legend'); lg.innerHTML='';
  keys.sort().forEach(c=>{
    const sp=document.createElement('span');
    const off=hiddenTypes.has(c);
    if(off) sp.className='off';
    sp.title='click to '+(off?'show':'hide')+' '+c+' instances · double-click to only show '+c+' instances';
    sp.innerHTML='<span class="dot" style="background:'+colorFor(c)+'"></span>'+esc(c);
    let lc=0, timer=null;
    sp.onclick=()=>{
      const now=performance.now();
      if(timer && now-lc<200){            // double-click: show ONLY this type
        clearTimeout(timer); timer=null;
        hiddenTypes.clear(); keys.forEach(k=>{ if(k!==c) hiddenTypes.add(k); });
        render(); return;
      }
      lc=now; if(timer) clearTimeout(timer);
      timer=setTimeout(()=>{ timer=null; // single-click: toggle this type
        if(hiddenTypes.has(c)) hiddenTypes.delete(c); else hiddenTypes.add(c);
        if(keys.every(k=>hiddenTypes.has(k))) hiddenTypes.clear(); // all hidden -> re-enable all
        render();
      }, 210);
    };
    lg.appendChild(sp);
  });
}

// index nodes for hit-testing
function indexNodes(){
  let i=0; current._all=[];
  (function w(n){ n._idx=i++; current._all.push(n); n._children.forEach(w); })(current);
}
// Single click is held 200ms so a quick double-click wins instead. Double-click:
// an instance isolates its branch; an attribute copies its host path.
let nodeTimer=null, nodeLastN=null, nodeLastT=0;
svg.addEventListener('click',e=>{
  const g=e.target.closest('.node,.item'); if(!g) return;
  const n=current._all[+g.dataset.i];
  if(!n) return;
  const now=performance.now();
  if(nodeTimer && nodeLastN===n && now-nodeLastT<200){ // double-click
    clearTimeout(nodeTimer); nodeTimer=null;
    if(n.kind==='inst'){ isoNode=(isoNode===n)?null:n; render(); }
    else { copyNode(n); }
    return;
  }
  nodeLastN=n; nodeLastT=now;
  if(nodeTimer) clearTimeout(nodeTimer);
  nodeTimer=setTimeout(()=>{ nodeTimer=null;
    if(n.kind==='inst' && n._children.length){ n._expanded=!n._expanded; render(); }
  }, 200);
});
svg.addEventListener('mousemove',e=>{
  const g=e.target.closest('.node,.item'); if(!g){ tip.style.display='none'; hoverNode=null; return; }
  const n=current._all[+g.dataset.i];
  if(!n){ tip.style.display='none'; hoverNode=null; return; }
  hoverNode=n;
  if(n.kind==='inst'){
    tip.innerHTML='<b>'+esc(n.path)+'</b> ['+esc(n.c)+'] &middot; '+
      n._children.filter(c=>c.kind==='item').length+' items, '+
      n._children.filter(c=>c.kind==='inst').length+' child instances'+
      '<br/><span style="color:var(--type)">'+CB+'+C to copy path · double-click to isolate</span>';
  } else {
    tip.innerHTML='<b>'+esc(n.it.n)+'</b> = '+esc(n.it.v)+' ('+esc(n.it.t)+')'+
      (n.it.m?'  '+n.it.m:'')+'<br/>host: <b>'+esc(n._p.path)+'</b>'+
      '<br/><span style="color:var(--type)">'+CB+'+C or double-click to copy the host path</span>';
  }
  tip.style.display='block';
  let x=e.clientX+14,y=e.clientY+14; const r=tip.getBoundingClientRect();
  if(x+r.width>innerWidth) x=e.clientX-r.width-14;
  if(y+r.height>innerHeight) y=e.clientY-r.height-14;
  tip.style.left=x+'px'; tip.style.top=y+'px';
});
svg.addEventListener('mouseleave',()=>{ tip.style.display='none'; hoverNode=null; });

document.getElementById('expandAll').onclick=()=>{ isoNode=null; setAll(true); render(); };
document.getElementById('collapseAll').onclick=()=>{ setAll(false); current._expanded=true; render(); };
function setAll(v){ (function w(n){ if(n.kind==='inst'&&n._children.length){ n._expanded=v; n._children.forEach(w);} })(current); }

// --- copy a node's service-qualified path (paste into Studio Explorer search) ---
const CB = navigator.userAgent.indexOf('Mac')!==-1 ? 'Cmd' : 'Ctrl';
let hoverNode=null;
function pathFor(n){ return n.kind==='item' ? n._p.path : n.path; }
function copyText(t){
  try{ if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(t); return true; } }catch(e){}
  const ta=document.createElement('textarea'); ta.value=t;
  ta.style.position='fixed'; ta.style.top='-1000px'; document.body.appendChild(ta);
  ta.focus(); ta.select(); let ok=false; try{ ok=document.execCommand('copy'); }catch(e){}
  document.body.removeChild(ta); return ok;
}
const toast=document.getElementById('toast'); let toastT=null;
function flashCopied(p){ toast.textContent='Copied: '+p; toast.style.display='block';
  clearTimeout(toastT); toastT=setTimeout(()=>{ toast.style.display='none'; }, 1600); }
function copyNode(n){ const p=pathFor(n); if(copyText(p)) flashCopied(p); }
document.addEventListener('keydown',e=>{
  if((e.metaKey||e.ctrlKey) && (e.key==='c'||e.key==='C')){
    const sel=window.getSelection && String(window.getSelection());
    if(sel) return;                       // don't override a real text selection
    if(hoverNode) copyNode(hoverNode);
  }
});

// --- ">= N attributes" slider ---
const minattrs=document.getElementById('minattrs');
minattrs.addEventListener('input',()=>{
  minAttrs=parseInt(minattrs.value,10);
  document.getElementById('minlbl').textContent = String(minAttrs)+'+';
  render();
});

const search=document.getElementById('search'); let t=null;
search.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(doSearch,140);});
function doSearch(){
  q=search.value.trim().toLowerCase();
  if(!q){ setAll(true); render(); return; } // cleared search -> behave like "Expand all"
  computeVisibility();
  setAll(false); current._expanded=true;
  // expand the ancestors of every node that survives the filter, so all
  // surviving leaves are revealed and non-matching branches stay collapsed/hidden
  (function w(n){
    if(n._show){ let p=n._p; while(p){ p._expanded=true; p=p._p; } }
    n._children.forEach(w);
  })(current);
  render();
}

// Label the page with this diagram's own term ("attributes" vs "values") so the
// two are never conflated. ** means nil-able for attributes, destroyable for values.
(function setLabels(){
  const lab=DATA.summary.item_label;
  const Cap=lab.charAt(0).toUpperCase()+lab.slice(1);
  const set=(id,t)=>{ const el=document.getElementById(id); if(el) el.textContent=t; };
  set('minunit', lab); set('lbl1', lab); set('lbl2', Cap);
  set('dstarlbl', DATA.summary.item_kind==='value' ? 'destroyable' : 'nil-able');
  const mw=document.getElementById('minwrap');
  if(mw) mw.title='show only instances that have at least this many '+lab;
})();

function boot(){ indexNodes(); render(); }
// re-index whenever the current service changes
const _render=render;
render=function(){ indexNodes(); _render(); };
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
