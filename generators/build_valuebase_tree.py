#!/usr/bin/env python3
"""
build_valuebase_tree.py
=======================
The Value-object twin of build_attribute_tree.py.

Generates a single self-contained interactive HTML map of every ValueBase
object (IntValue / NumberValue / StringValue / BoolValue / ObjectValue /
Vector3Value / CFrameValue / Color3Value / ...) in the game, as a collapsible
tree, with a runtime layer derived from the codebase.

INPUTS:
  1. DUMP_PATH : Trees/ValueBaseTree.luau   (Studio dump; format below)
  2. SRC_DIR   : src/  (scanned for `.Value =` writes to derive */**)

OUTPUT:
  Trees/ValueBaseTree.html

DUMP FORMAT (every line is an instance; Value objects carry an inline value):
  Workspace [Workspace]
    GAME_ASSETS [Folder]
      SurvivalShopItems [Folder]
        Canoe [Tool]
          CurrentHealth [IntValue] = 60 (number)
          Occupant [ObjectValue] = nil (nil)
  Container instances (Folder/Tool/Part/Model) have no ` = value (type)` tail;
  ValueBase objects do.

MARKERS (mirrors the attribute tool, applied to a Value by its NAME):
  (no marker) : the Value's `.Value` is never assigned in code -> static default,
                the easiest kind to migrate to a plain attribute.
  *           : `.Value` is assigned somewhere in code  ( x.<Name>.Value = ... ,
                FindFirstChild("<Name>").Value = ... , ["<Name>"].Value = ... ).
  **          : `.Value` is assigned a literal nil in code (e.g. an ObjectValue
                being cleared) -> can be nil after being set.
  NOTE: the */** layer is a NAME-based heuristic (same approach as the attribute
  map). Value names that repeat across instances all receive the marker.

RE-RUN: refresh Trees/ValueBaseTree.luau from Studio, then
        python3 Trees/build_valuebase_tree.py
"""

import os
import re
import html
import json
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))

# Reuse PROJECT_NAME / SRC_DIR / PROJECT_ROOT from the attribute generator so the
# whole tool-suite shares one config.
_spec = importlib.util.spec_from_file_location(
    "build_attribute_tree", os.path.join(HERE, "build_attribute_tree.py")
)
bat = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bat)

PROJECT_NAME = bat.PROJECT_NAME
SRC_DIR = bat.SRC_DIR
PROJECT_ROOT = bat.PROJECT_ROOT
WORKING = os.path.join(PROJECT_ROOT, "working")
DUMP_PATH = os.path.join(WORKING, "ValueBaseTree.luau")
OUT_PATH = os.path.join(WORKING, "ValueBaseTree.html")

# ValueBase classes that hold an Instance reference (or otherwise have no
# attribute equivalent) and so CANNOT be converted to an attribute.
NON_CONVERTIBLE = {"ObjectValue", "RayValue"}

# ---------------------------------------------------------------------------
# 1. Scan src/ for `.Value =` writes  (derives the */** layer).
# ---------------------------------------------------------------------------
# write patterns (assignment, not == comparison)
_WRITE = [
    re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)\.Value\s*=(?!=)'),
    re.compile(r'(?:FindFirstChild|WaitForChild)\(\s*["\']([^"\']+)["\']\s*\)\.Value\s*=(?!=)'),
    re.compile(r'\[\s*["\']([^"\']+)["\']\s*\]\.Value\s*=(?!=)'),
]
_NILWRITE = [
    re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)\.Value\s*=\s*nil\b'),
    re.compile(r'(?:FindFirstChild|WaitForChild)\(\s*["\']([^"\']+)["\']\s*\)\.Value\s*=\s*nil\b'),
    re.compile(r'\[\s*["\']([^"\']+)["\']\s*\]\.Value\s*=\s*nil\b'),
]
_REF = [
    re.compile(r'\.([A-Za-z_][A-Za-z0-9_]*)\.Value\b'),
    re.compile(r'(?:FindFirstChild|WaitForChild)\(\s*["\']([^"\']+)["\']\s*\)\.Value\b'),
    re.compile(r'\[\s*["\']([^"\']+)["\']\s*\]\.Value\b'),
]


def scan_value_writes(src_dir):
    writes = {}     # name -> set(files)
    nil_writes = set()
    refs = set()
    for root, _d, files in os.walk(src_dir):
        for fn in files:
            if not (fn.endswith(".luau") or fn.endswith(".lua")):
                continue
            path = os.path.join(root, fn)
            try:
                text = open(path, "r", encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            rel = os.path.relpath(path, PROJECT_ROOT)
            for rx in _WRITE:
                for nm in rx.findall(text):
                    writes.setdefault(nm, set()).add(rel)
            for rx in _NILWRITE:
                for nm in rx.findall(text):
                    nil_writes.add(nm)
            for rx in _REF:
                for nm in rx.findall(text):
                    refs.add(nm)
    return writes, nil_writes, refs


# ---------------------------------------------------------------------------
# 2. Parse the Value dump into a tree.
# ---------------------------------------------------------------------------
NODE_RE = re.compile(r'^(\s*)(.*?) \[([A-Za-z0-9_]+)\](?: = (.*))?\s*$')
VALTYPE_RE = re.compile(r'^(.*) \(([A-Za-z0-9]+)\)$')


class Node:
    __slots__ = ("name", "cls", "indent", "value", "vtype", "children")

    def __init__(self, name, cls, indent, value=None, vtype=None):
        self.name = name
        self.cls = cls
        self.indent = indent
        self.value = value      # None for container instances
        self.vtype = vtype
        self.children = []


def parse_dump(path):
    roots = []
    stack = []
    total_nodes = 0
    total_values = 0
    started = False  # skip the banner/header block before the real tree
    with open(path, "r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            if not started:
                if re.match(r'^=+\s*$', line):  # the long ===== separator
                    started = True
                continue
            if not line.strip():
                continue
            m = NODE_RE.match(line)
            if not m:
                continue  # banner / header lines
            indent = len(m.group(1))
            name = m.group(2)
            cls = m.group(3)
            tail = m.group(4)
            value, vtype = None, None
            if tail is not None:
                mt = VALTYPE_RE.match(tail)
                if mt:
                    value, vtype = mt.group(1), mt.group(2)
                else:
                    value, vtype = tail, "?"
                total_values += 1
            node = Node(name, cls, indent, value, vtype)
            total_nodes += 1
            while stack and stack[-1].indent >= indent:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                roots.append(node)
            stack.append(node)
    return roots, total_nodes, total_values


# ---------------------------------------------------------------------------
# 3. Serialize + apply markers.
# ---------------------------------------------------------------------------
def marker_for(name, writes, nil_writes):
    if name in nil_writes:
        return "**"
    if name in writes:
        return "*"
    return ""


def serialize(node, writes, nil_writes, refs, stats):
    is_value = node.value is not None
    mk = ""
    if is_value:
        stats["total_values"] += 1
        stats["by_class"][node.cls] = stats["by_class"].get(node.cls, 0) + 1
        stats["value_names"].add(node.name)
        mk = marker_for(node.name, writes, nil_writes)
        if mk == "*":
            stats["star"] += 1
        elif mk == "**":
            stats["dstar"] += 1
        else:
            stats["static"] += 1
        if node.name not in refs and not mk:
            stats["never_in_code"] += 1
    obj = {"n": node.name, "c": node.cls, "ch": []}
    if is_value:
        obj["v"] = node.value
        obj["t"] = node.vtype
        obj["m"] = mk
        if node.cls in NON_CONVERTIBLE:
            obj["nc"] = True
            stats["non_convertible"] = stats.get("non_convertible", 0) + 1
    for ch in node.children:
        obj["ch"].append(serialize(ch, writes, nil_writes, refs, stats))
    return obj


def main():
    writes, nil_writes, refs = scan_value_writes(SRC_DIR)
    roots, total_nodes, total_values = parse_dump(DUMP_PATH)

    stats = {
        "total_values": 0, "by_class": {}, "value_names": set(),
        "star": 0, "dstar": 0, "static": 0, "never_in_code": 0,
    }
    tree = [serialize(r, writes, nil_writes, refs, stats) for r in roots]

    value_names = stats["value_names"]
    written_names = set(writes.keys())
    # written in code but no Value object of that name in the dump:
    written_not_in_dump = sorted(written_names - value_names)
    appendix = [
        {"n": n, "m": "**" if n in nil_writes else "*",
         "files": sorted(writes.get(n, []))}
        for n in written_not_in_dump
    ]

    summary = {
        "project": PROJECT_NAME,
        "total_nodes": total_nodes,
        "total_values": stats["total_values"],
        "by_class": dict(sorted(stats["by_class"].items(), key=lambda kv: -kv[1])),
        "star": stats["star"],
        "dstar": stats["dstar"],
        "static": stats["static"],
        "never_in_code": stats["never_in_code"],
        "value_names": len(value_names),
        "written_names": len(written_names),
        "written_not_in_dump": len(written_not_in_dump),
    }

    out = HTML_TEMPLATE.replace("/*__DATA__*/",
                               "const DATA = " + json.dumps({"tree": tree, "appendix": appendix, "summary": summary}) + ";")
    out = out.replace("__PROJECT__", html.escape(PROJECT_NAME))
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(out)

    print("Wrote", OUT_PATH)
    print(json.dumps(summary, indent=2))


# ---------------------------------------------------------------------------
# 4. HTML -- single self-contained file, vanilla JS. (mirrors AttributeTree)
# ---------------------------------------------------------------------------
HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__PROJECT__ &mdash; ValueBase Map</title>
<style>
  :root{
    --bg:#0f1117; --panel:#161922; --row:#1b1f2a; --rowh:#232838;
    --ink:#e6e9f0; --dim:#9aa3b2; --line:#2a2f3d;
    --inst:#7cc4ff; --cls:#5f6b80; --val:#9ece6a; --type:#7a8294;
    --star:#ffb454; --dstar:#ff6b6b; --badge:#272c3a; --vcls:#b794f6;
  }
  *{box-sizing:border-box}
  html,body{margin:0;background:var(--bg);color:var(--ink);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header{position:sticky;top:0;z-index:10;background:var(--panel);
    border-bottom:1px solid var(--line);padding:12px 16px}
  h1{margin:0 0 6px;font-size:15px;font-weight:600}
  .stats{color:var(--dim);font-size:11.5px;margin-bottom:8px}
  .stats b{color:var(--ink)}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  input[type=search]{background:var(--row);border:1px solid var(--line);
    color:var(--ink);border-radius:6px;padding:6px 10px;font:inherit;width:280px}
  button{background:var(--row);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
  button:hover{background:var(--rowh)}
  label.tog{display:inline-flex;gap:5px;align-items:center;color:var(--dim);cursor:pointer;user-select:none}
  select{background:var(--row);border:1px solid var(--line);color:var(--ink);border-radius:6px;padding:6px;font:inherit}
  .legend{margin-left:auto;color:var(--dim);font-size:11px;display:flex;gap:14px;flex-wrap:wrap}
  .legend .star{color:var(--star)} .legend .dstar{color:var(--dstar)}
  main{padding:8px 12px 60px}
  ul{list-style:none;margin:0;padding:0}
  li.node>ul{padding-left:16px;border-left:1px solid var(--line);margin-left:7px}
  .row{display:flex;align-items:baseline;gap:6px;padding:1px 4px;border-radius:4px}
  .row:hover{background:var(--rowh)}
  .tw{width:12px;display:inline-block;text-align:center;color:var(--dim);cursor:pointer;user-select:none;flex:0 0 12px}
  .tw.leaf{visibility:hidden}
  .iname{color:var(--inst)}
  .node.val>.row>.iname{color:var(--ink);font-weight:600}
  .cls{color:var(--cls);font-size:11px}
  .vcls{color:var(--vcls);font-size:11px}
  li.collapsed>ul{display:none}
  .mk{font-weight:700} .mk.s{color:var(--star)} .mk.d{color:var(--dstar)} .mk.nc{color:#ff5555;margin-left:4px}
  .legend .ncl{color:#ff5555}
  .eq{color:var(--type)}
  .aval{color:var(--val);max-width:46vw;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .atype{color:var(--type);font-size:11px}
  .hidden{display:none !important}
  .match>.row{background:#2c3350}
  .section{margin-top:20px;border-top:1px solid var(--line);padding-top:12px}
  .section h2{font-size:13px;color:var(--star);margin:0 0 8px}
  .ap{padding:1px 4px 1px 18px;color:var(--ink)}
  .ap .files{color:var(--dim);font-size:10.5px;margin-left:6px}
  .count{color:var(--dim);font-size:11px;margin-left:6px}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__ &mdash; ValueBase Object Map</h1>
  <div class="stats" id="stats"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="filter by value or container name&hellip;"/>
    <button id="expandAll">Expand all</button>
    <button id="collapseAll">Collapse all</button>
    <label class="tog"><input type="checkbox" id="onlyMutated"/> only * / **</label>
    <label class="tog"><input type="checkbox" id="onlyStatic"/> only static (migration-ready)</label>
    <select id="classFilter"><option value="">all value types</option></select>
    <div class="legend">
      <span><b>no mark</b> = static default</span>
      <span class="star"><b>*</b> = written in code</span>
      <span class="dstar"><b>**</b> = set to nil in code</span>
      <span class="ncl"><b>***</b> = Instance ref, can't be an attribute</span>
    </div>
  </div>
</header>
<main>
  <div class="tree" id="tree"></div>
  <div class="section" id="appendix"></div>
</main>
<script>
/*__DATA__*/
const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function nodeEl(node){
  const li = document.createElement('li');
  const isVal = node.v !== undefined;
  li.className = 'node' + (isVal ? ' val' : '') + ' collapsed';
  const hasKids = node.ch && node.ch.length;
  const row = document.createElement('div');
  row.className = 'row';
  let h = '<span class="tw'+(hasKids?'':' leaf')+'">'+(hasKids?'▶':'')+'</span>'+
    '<span class="iname">'+esc(node.n)+'</span>';
  if(isVal){
    const mk = node.m==='**'?'<span class="mk d">**</span>':node.m==='*'?'<span class="mk s">*</span>':'';
    const nc = node.nc ? '<span class="mk nc" title="Stores an Instance reference - cannot become an attribute">***</span>' : '';
    h += '<span class="vcls">['+esc(node.c)+']</span>'+mk+
      '<span class="eq">=</span><span class="aval" title="'+esc(node.v)+'">'+esc(node.v)+'</span>'+
      '<span class="atype">('+esc(node.t)+')</span>'+nc;
  } else {
    h += '<span class="cls">['+esc(node.c)+']</span>';
  }
  row.innerHTML = h;
  li.appendChild(row);
  li.dataset.val = isVal ? '1' : '0';
  li.dataset.vtype = isVal ? node.c : '';
  li.dataset.marker = isVal ? (node.m || '') : '';
  let bag = node.n.toLowerCase() + (isVal ? ' '+String(node.v).toLowerCase() : '');
  if(hasKids){
    const ul = document.createElement('ul');
    for(const c of node.ch){ const cu = nodeEl(c); ul.appendChild(cu.li); bag += ' '+cu.bag; }
    li.appendChild(ul);
    const tw = row.querySelector('.tw');
    const toggle = ()=>{ li.classList.toggle('collapsed');
      tw.textContent = li.classList.contains('collapsed') ? '▶' : '▼'; };
    tw.addEventListener('click', e=>{ e.stopPropagation(); toggle(); });
    row.addEventListener('click', toggle);
  }
  li.dataset.bag = bag;
  return {li, bag};
}

const treeRoot = document.getElementById('tree');
const ul = document.createElement('ul');
for(const n of DATA.tree){ ul.appendChild(nodeEl(n).li); }
treeRoot.appendChild(ul);

const s = DATA.summary;
document.getElementById('stats').innerHTML =
  '<b>'+s.total_values+'</b> ValueBase objects &nbsp;&middot;&nbsp; '+
  '<b>'+s.value_names+'</b> distinct names &nbsp;&middot;&nbsp; '+
  '<span class="star"><b>'+s.star+'</b> *</span> &nbsp; '+
  '<span class="dstar"><b>'+s.dstar+'</b> **</span> &nbsp; '+
  '<b>'+s.static+'</b> static &nbsp;&middot;&nbsp; '+
  '<b>'+s.written_not_in_dump+'</b> code-written names not in dump (appendix)';

// class filter options
const cf = document.getElementById('classFilter');
Object.keys(s.by_class).forEach(c=>{
  const o=document.createElement('option'); o.value=c; o.textContent=c+' ('+s.by_class[c]+')'; cf.appendChild(o);
});

// appendix
const ap = document.getElementById('appendix');
let aph = '<h2>Written in code, no Value of that name in the dump <span class="count">'+
  DATA.appendix.length+' &mdash; likely created at runtime, renamed, or a non-Value field</span></h2>';
for(const a of DATA.appendix){
  const mk = a.m==='**'?'<span class="mk d">**</span>':'<span class="mk s">*</span>';
  aph += '<div class="ap" data-name="'+esc(a.n.toLowerCase())+'"><span class="iname">'+esc(a.n)+
    '</span>'+mk+'<span class="files">'+esc(a.files.join('  &middot;  '))+'</span></div>';
}
ap.innerHTML = aph;

// controls
const tree = document.getElementById('tree');
function setAll(collapsed){
  tree.querySelectorAll('li.node').forEach(li=>{
    if(li.querySelector(':scope > ul')){
      li.classList.toggle('collapsed', collapsed);
      const tw=li.querySelector(':scope > .row > .tw');
      if(tw && !tw.classList.contains('leaf')) tw.textContent = collapsed ? '▶' : '▼';
    }
  });
}
document.getElementById('expandAll').onclick=()=>setAll(false);
document.getElementById('collapseAll').onclick=()=>setAll(true);

const onlyMutated=document.getElementById('onlyMutated');
const onlyStatic=document.getElementById('onlyStatic');
function applyValueFilters(){
  const mut=onlyMutated.checked, stat=onlyStatic.checked, vt=cf.value;
  tree.querySelectorAll('li.node.val').forEach(li=>{
    let show=true;
    if(mut && !li.dataset.marker) show=false;
    if(stat && li.dataset.marker) show=false;
    if(vt && li.dataset.vtype!==vt) show=false;
    li.classList.toggle('hidden', !show);
  });
}
onlyMutated.onchange=applyValueFilters; onlyStatic.onchange=applyValueFilters; cf.onchange=applyValueFilters;

const search=document.getElementById('search'); let t=null;
search.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(runSearch,120);});
function runSearch(){
  const q=search.value.trim().toLowerCase();
  ap.querySelectorAll('.ap').forEach(d=>d.classList.toggle('hidden', q && d.dataset.name.indexOf(q)===-1));
  if(!q){ tree.querySelectorAll('li.node').forEach(li=>li.classList.remove('hidden','match')); setAll(true); applyValueFilters(); return; }
  tree.querySelectorAll('li.node').forEach(li=>{
    const hit=li.dataset.bag.indexOf(q)!==-1;
    li.classList.toggle('hidden', !hit);
    const nameHit=li.querySelector(':scope > .row > .iname').textContent.toLowerCase().indexOf(q)!==-1;
    li.classList.toggle('match', nameHit);
  });
  tree.querySelectorAll('li.node:not(.hidden)').forEach(li=>{
    let p=li;
    while(p && p.classList && p.classList.contains('node')){
      p.classList.remove('hidden','collapsed');
      const tw=p.querySelector(':scope > .row > .tw');
      if(tw && !tw.classList.contains('leaf')) tw.textContent='▼';
      p=p.parentElement.closest('li.node');
    }
  });
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
