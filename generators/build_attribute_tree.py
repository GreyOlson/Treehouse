#!/usr/bin/env python3
"""
build_attribute_tree.py
=======================
Generates a single self-contained interactive HTML attribute map for a Roblox project.

INPUTS (both auto-discovered relative to this script; override below):
  1. DUMP_PATH : the Studio attribute dump (ASCII tree) produced by
                 AttributeDump_StudioCommand.luau  ->  Trees/AttributeTree.luau
  2. SRC_DIR   : the Rojo `src/` tree, scanned for SetAttribute calls so the
                 runtime layer (*/**) is derived programmatically, not by hand.

OUTPUT:
  OUT_PATH : Trees/AttributeTree.html  (open in any browser)

MARKERS (requirement #3):
  (no marker) : attribute exists at edit time and is never written via
                SetAttribute in code  -> purely static / design-time.
  *           : attribute name is written via :SetAttribute(...) somewhere in
                code (set at runtime).
  **          : attribute name is written with a literal nil somewhere
                ( :SetAttribute("Name", nil) ) -> can become nil after being set.

RE-RUNNING AFTER CHANGES (the whole point of a generator):
  1. Re-run AttributeDump_StudioCommand.luau in Studio, refresh Trees/AttributeTree.luau.
  2. `python3 Trees/build_attribute_tree.py`
  That's it -- the */** layer and the appendix re-derive themselves from src/.

No third-party packages. Pure standard library.
"""

import os
import re
import html
import json

# ---------------------------------------------------------------------------
# CONFIG -- edit paths here if your layout changes.
# ---------------------------------------------------------------------------
# Shown in the page title and header. The plugin/mailbox passes the live place
# name via the ATTRTREE_PROJECT env var; falls back to the placeholder otherwise.
PROJECT_NAME = os.environ.get("ATTRTREE_PROJECT") or "PROJECT_NAME"

if PROJECT_NAME == "PROJECT_NAME":
    print("WARNING: PROJECT_NAME is not set (no ATTRTREE_PROJECT); the page title will show the placeholder.")

HERE = os.path.dirname(os.path.abspath(__file__))           # generators/
PROJECT_ROOT = os.path.dirname(HERE)                        # AttributeTreePlugin/
WORKING = os.path.join(PROJECT_ROOT, "working")             # dumps in, HTML out

# Point this at the Rojo `src/` of the game you're analyzing. It lives OUTSIDE
# this plugin repo, so set the TREE_SRC env var, e.g.
#   TREE_SRC=/path/to/YourGame/src  python3 generators/build_attribute_tree.py
# The default below assumes the game repo sits next to the Plugins folder.
SRC_DIR = os.environ.get(
    "TREE_SRC",
    os.path.join(PROJECT_ROOT, "..", "..", "TsunamiGame", "src"),
)
DUMP_PATH = os.path.join(WORKING, "AttributeTree.luau")
OUT_PATH = os.path.join(WORKING, "AttributeTree.html")

# Rojo tooling attributes we flag but treat as noise.
ROJO_ATTRS = {"RojoSyncMode", "PreserveParts"}

# ---------------------------------------------------------------------------
# 1. Scan src/ for runtime attribute usage  (derives the */** layer).
# ---------------------------------------------------------------------------
SET_LITERAL_RE = re.compile(r':SetAttribute\(\s*"([^"]+)"')
SET_LITERAL_NIL_RE = re.compile(r':SetAttribute\(\s*"([^"]+)"\s*,\s*nil\s*\)')
SET_IDENT_RE = re.compile(r':SetAttribute\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*,')
CONST_ASSIGN_RE = lambda ident: re.compile(
    r'\b' + re.escape(ident) + r'\s*=\s*"([^"]+)"'
)


def scan_runtime_attributes(src_dir):
    runtime_set = {}      # name -> set(relative file paths where written)
    runtime_nil = set()   # names written with a literal nil
    ident_names = set()   # identifier args to SetAttribute (constants)

    luau_files = []
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            if fn.endswith(".luau") or fn.endswith(".lua"):
                luau_files.append(os.path.join(root, fn))

    # First pass: literals + collect identifier arg names per file text.
    file_texts = {}
    for path in luau_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
        except OSError:
            continue
        file_texts[path] = text
        rel = os.path.relpath(path, PROJECT_ROOT)
        for name in SET_LITERAL_RE.findall(text):
            runtime_set.setdefault(name, set()).add(rel)
        for name in SET_LITERAL_NIL_RE.findall(text):
            runtime_nil.add(name)
        for ident in SET_IDENT_RE.findall(text):
            # ignore obvious non-constants like `self`, table indexes handled
            ident_names.add(ident)

    # Second pass: resolve identifier args to their string-literal value
    # by searching every file for `IDENT = "value"`.
    all_text = "\n".join(file_texts.values())
    for ident in ident_names:
        m = CONST_ASSIGN_RE(ident).search(all_text)
        if m:
            name = m.group(1)
            # find which files reference the ident in a SetAttribute call
            pat = re.compile(r':SetAttribute\(\s*' + re.escape(ident) + r'\s*,')
            for path, text in file_texts.items():
                if pat.search(text):
                    rel = os.path.relpath(path, PROJECT_ROOT)
                    runtime_set.setdefault(name, set()).add(rel)

    return runtime_set, runtime_nil


# ---------------------------------------------------------------------------
# 2. Parse the Studio dump into a tree.
# ---------------------------------------------------------------------------
INSTANCE_RE = re.compile(r'^(\s*)(\S.*?) \[([A-Za-z0-9_]+)\]\s*$')
ATTR_RE = re.compile(r'^(\s*)- (.+?) = (.*)$')


class Node:
    __slots__ = ("name", "cls", "indent", "attrs", "children")

    def __init__(self, name, cls, indent):
        self.name = name
        self.cls = cls
        self.indent = indent
        self.attrs = []      # list of dicts: name,value,type,rojo
        self.children = []


def parse_attr_value(raw):
    """raw is everything after '= '. Type is the last (Type) token, with
    optional trailing '[rojo]'. Returns (value, type, is_rojo)."""
    is_rojo = False
    s = raw.rstrip()
    if s.endswith("[rojo]"):
        is_rojo = True
        s = s[: -len("[rojo]")].rstrip()
    # type is last parenthesized token
    m = re.search(r'\(([A-Za-z0-9]+)\)\s*$', s)
    if m:
        vtype = m.group(1)
        value = s[: m.start()].rstrip()
    else:
        vtype = "?"
        value = s
    return value, vtype, is_rojo


def parse_dump(path):
    root_nodes = []
    stack = []  # nodes by depth
    cur_instance = None
    total_instances = 0

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for line in lines:
        line = line.rstrip("\n")
        if not line.strip():
            continue
        mi = INSTANCE_RE.match(line)
        if mi and not line.lstrip().startswith("- "):
            indent = len(mi.group(1))
            name = mi.group(2)
            cls = mi.group(3)
            node = Node(name, cls, indent)
            total_instances += 1
            # pop to find parent
            while stack and stack[-1].indent >= indent:
                stack.pop()
            if stack:
                stack[-1].children.append(node)
            else:
                root_nodes.append(node)
            stack.append(node)
            cur_instance = node
            continue
        ma = ATTR_RE.match(line)
        if ma and cur_instance is not None:
            aname = ma.group(2).strip()
            value, vtype, is_rojo = parse_attr_value(ma.group(3))
            cur_instance.attrs.append(
                {"name": aname, "value": value, "type": vtype, "rojo": is_rojo}
            )
            continue
        # ignore header / banner lines
    return root_nodes, total_instances


# ---------------------------------------------------------------------------
# 3. Build serializable tree + stats, applying markers.
# ---------------------------------------------------------------------------
def marker_for(name, runtime_set, runtime_nil):
    if name in runtime_nil:
        return "**"
    if name in runtime_set:
        return "*"
    return ""


def serialize(node, runtime_set, runtime_nil, stats):
    obj = {
        "n": node.name,
        "c": node.cls,
        "a": [],
        "ch": [],
    }
    if any(not a["rojo"] for a in node.attrs):
        stats["attributed_instances"] += 1
    for a in node.attrs:
        mk = marker_for(a["name"], runtime_set, runtime_nil)
        if a["rojo"]:
            stats["rojo_attr_count"] += 1
        else:
            stats["real_attr_count"] += 1
            stats["design_names"].add(a["name"])
            if mk == "*":
                stats["star_count"] += 1
            elif mk == "**":
                stats["dstar_count"] += 1
        obj["a"].append({
            "n": a["name"],
            "v": a["value"],
            "t": a["type"],
            "m": mk,
            "rojo": a["rojo"],
        })
    for ch in node.children:
        obj["ch"].append(serialize(ch, runtime_set, runtime_nil, stats))
    return obj


def main():
    runtime_set, runtime_nil = scan_runtime_attributes(SRC_DIR)
    roots, total_instances = parse_dump(DUMP_PATH)

    stats = {
        "rojo_attr_count": 0,
        "real_attr_count": 0,
        "design_names": set(),
        "star_count": 0,
        "dstar_count": 0,
        "attributed_instances": 0,
    }
    tree = [serialize(r, runtime_set, runtime_nil, stats) for r in roots]

    design_names = stats["design_names"]
    runtime_names = set(runtime_set.keys())

    # Appendix: runtime attribute names never seen at edit time in the dump.
    runtime_only = sorted(runtime_names - design_names)
    appendix = []
    for name in runtime_only:
        files = sorted(runtime_set.get(name, []))
        appendix.append({
            "n": name,
            "m": "**" if name in runtime_nil else "*",
            "files": files,
        })

    summary = {
        "total_nodes": total_instances,
        "attributed_instances": stats["attributed_instances"],
        "design_names": len(design_names),
        "runtime_names": len(runtime_names),
        "overlap": len(design_names & runtime_names),
        "runtime_only": len(runtime_only),
        "star_count": stats["star_count"],
        "dstar_count": stats["dstar_count"],
        "real_attr_count": stats["real_attr_count"],
        "rojo_attr_count": stats["rojo_attr_count"],
    }

    html_out = render_html(tree, appendix, summary)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        f.write(html_out)

    print("Wrote", OUT_PATH)
    print(json.dumps(summary, indent=2))


# ---------------------------------------------------------------------------
# 4. HTML rendering -- single self-contained file, vanilla JS.
# ---------------------------------------------------------------------------
def render_html(tree, appendix, summary):
    data_json = json.dumps({"tree": tree, "appendix": appendix, "summary": summary})
    # data is embedded; the page builds the DOM from it.
    out = HTML_TEMPLATE.replace("/*__DATA__*/", "const DATA = " + data_json + ";")
    out = out.replace("__PROJECT__", html.escape(PROJECT_NAME))
    return out


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__PROJECT__ &mdash; Attribute Map</title>
<style>
  :root{
    --bg:#0f1117; --panel:#161922; --row:#1b1f2a; --rowh:#232838;
    --ink:#e6e9f0; --dim:#9aa3b2; --line:#2a2f3d;
    --inst:#7cc4ff; --cls:#5f6b80; --attr:#d7dbe3;
    --val:#9ece6a; --type:#7a8294; --star:#ffb454; --dstar:#ff6b6b;
    --rojo:#5a5f6e; --accent:#7cc4ff; --badge:#272c3a;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header{position:sticky;top:0;z-index:10;background:var(--panel);
    border-bottom:1px solid var(--line);padding:12px 16px}
  h1{margin:0 0 6px;font-size:15px;font-weight:600;color:var(--ink)}
  .stats{color:var(--dim);font-size:11.5px;margin-bottom:8px}
  .stats b{color:var(--ink);font-weight:600}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  input[type=search]{background:var(--row);border:1px solid var(--line);
    color:var(--ink);border-radius:6px;padding:6px 10px;font:inherit;width:280px}
  button{background:var(--row);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
  button:hover{background:var(--rowh)}
  label.tog{display:inline-flex;gap:5px;align-items:center;color:var(--dim);
    cursor:pointer;user-select:none}
  .legend{margin-left:auto;color:var(--dim);font-size:11px;display:flex;gap:14px;flex-wrap:wrap}
  .legend .star{color:var(--star)} .legend .dstar{color:var(--dstar)}
  main{padding:8px 12px 60px}
  ul{list-style:none;margin:0;padding:0}
  .tree>ul{padding-left:0}
  li.node>ul{padding-left:16px;border-left:1px solid var(--line);margin-left:7px}
  .row{display:flex;align-items:center;gap:6px;padding:1px 4px;border-radius:4px;cursor:default}
  .row:hover{background:var(--rowh)}
  .tw{width:12px;display:inline-block;text-align:center;color:var(--dim);
    cursor:pointer;user-select:none;flex:0 0 12px}
  .tw.leaf{visibility:hidden}
  .iname{color:var(--inst);font-weight:600}
  .cls{color:var(--cls);font-size:11px}
  li.collapsed>ul{display:none}
  .attr{display:flex;align-items:baseline;gap:6px;padding:0 4px 0 18px}
  .attr:hover{background:var(--rowh);border-radius:4px}
  .aname{color:var(--attr)}
  .mk{font-weight:700}
  .mk.s{color:var(--star)} .mk.d{color:var(--dstar)}
  .eq{color:var(--type)}
  .aval{color:var(--val)}
  .atype{color:var(--type);font-size:11px}
  .rojo .aname,.rojo .aval{color:var(--rojo)}
  .badge{background:var(--badge);color:var(--dim);border-radius:4px;
    padding:0 5px;font-size:10px;margin-left:4px}
  .hidden{display:none !important}
  .match>.row{background:#2c3350}
  .section{margin-top:20px;border-top:1px solid var(--line);padding-top:12px}
  .section h2{font-size:13px;color:var(--star);margin:0 0 8px}
  .ap{padding:1px 4px 1px 18px;color:var(--attr)}
  .ap .files{color:var(--dim);font-size:10.5px;margin-left:6px}
  .count{color:var(--dim);font-size:11px;margin-left:6px}
  mark{background:#4a4020;color:#ffd479;border-radius:2px;padding:0 1px}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__ &mdash; Attribute Map</h1>
  <div class="stats" id="stats"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="filter by instance or attribute name&hellip;"/>
    <button id="expandAll">Expand all</button>
    <button id="collapseAll">Collapse all</button>
    <label class="tog"><input type="checkbox" id="onlyRuntime"/> only * / **</label>
    <label class="tog"><input type="checkbox" id="hideRojo" checked/> hide [rojo]</label>
    <div class="legend">
      <span><b>no mark</b> = static (edit-time only)</span>
      <span class="star"><b>*</b> = set at runtime</span>
      <span class="dstar"><b>**</b> = can be nil after set</span>
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

function attrRow(a){
  const li = document.createElement('div');
  li.className = 'attr' + (a.rojo ? ' rojo' : '');
  li.dataset.name = a.n.toLowerCase();
  li.dataset.runtime = a.m ? '1' : '0';
  li.dataset.rojo = a.rojo ? '1' : '0';
  const mk = a.m === '**' ? '<span class="mk d">**</span>'
           : a.m === '*'  ? '<span class="mk s">*</span>' : '';
  const rojo = a.rojo ? '<span class="badge">rojo</span>' : '';
  li.innerHTML = '<span class="aname">'+esc(a.n)+'</span>'+mk+
    '<span class="eq">=</span><span class="aval">'+esc(a.v)+'</span>'+
    '<span class="atype">('+esc(a.t)+')</span>'+rojo;
  return li;
}

function nodeEl(node){
  const li = document.createElement('li');
  li.className = 'node collapsed';
  const hasKids = (node.ch && node.ch.length) || (node.a && node.a.length);
  const row = document.createElement('div');
  row.className = 'row';
  row.innerHTML = '<span class="tw'+(hasKids?'':' leaf')+'">'+(hasKids?'▶':'')+'</span>'+
    '<span class="iname">'+esc(node.n)+'</span><span class="cls">['+esc(node.c)+']</span>';
  li.appendChild(row);
  // searchable text
  let bag = node.n.toLowerCase();
  if(hasKids){
    const ul = document.createElement('ul');
    for(const a of (node.a||[])){ ul.appendChild(attrRow(a)); bag += ' '+a.n.toLowerCase(); }
    for(const c of (node.ch||[])){ const cu = nodeEl(c); ul.appendChild(cu.li); bag += ' '+cu.bag; }
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

// build tree
const treeRoot = document.getElementById('tree');
const ul = document.createElement('ul');
for(const n of DATA.tree){ ul.appendChild(nodeEl(n).li); }
treeRoot.appendChild(ul);

// stats
const s = DATA.summary;
document.getElementById('stats').innerHTML =
  '<b>'+s.attributed_instances+'</b> attributed instances &nbsp;&middot;&nbsp; '+
  '<b>'+s.total_nodes+'</b> tree nodes &nbsp;&middot;&nbsp; '+
  '<b>'+s.design_names+'</b> design-time attribute names &nbsp;&middot;&nbsp; '+
  '<b>'+s.runtime_names+'</b> runtime names in code &nbsp;&middot;&nbsp; '+
  '<b>'+s.overlap+'</b> overlap &nbsp;&middot;&nbsp; '+
  '<span class="star"><b>'+s.star_count+'</b> *</span> &nbsp; '+
  '<span class="dstar"><b>'+s.dstar_count+'</b> **</span> &nbsp;&middot;&nbsp; '+
  '<b>'+s.runtime_only+'</b> runtime-only (see appendix)';

// appendix
const ap = document.getElementById('appendix');
let aphtml = '<h2>Runtime-only attributes <span class="count">'+DATA.appendix.length+
  ' &mdash; written in code, not present in the Studio dump (host inferred from source files)</span></h2>';
for(const a of DATA.appendix){
  const mk = a.m === '**' ? '<span class="mk d">**</span>' : '<span class="mk s">*</span>';
  aphtml += '<div class="ap" data-name="'+esc(a.n.toLowerCase())+'"><span class="aname">'+
    esc(a.n)+'</span>'+mk+'<span class="files">'+esc(a.files.join('  &middot;  '))+'</span></div>';
}
ap.innerHTML = aphtml;

// controls
const tree = document.getElementById('tree');
function setAll(collapsed){
  tree.querySelectorAll('li.node').forEach(li=>{
    const tw = li.querySelector(':scope > .row > .tw');
    if(li.querySelector(':scope > ul')){
      li.classList.toggle('collapsed', collapsed);
      if(tw && !tw.classList.contains('leaf')) tw.textContent = collapsed ? '▶' : '▼';
    }
  });
}
document.getElementById('expandAll').onclick = ()=>setAll(false);
document.getElementById('collapseAll').onclick = ()=>setAll(true);

// only runtime filter
const onlyRuntime = document.getElementById('onlyRuntime');
const hideRojo = document.getElementById('hideRojo');
function applyAttrFilters(){
  const onlyRt = onlyRuntime.checked, hRojo = hideRojo.checked;
  tree.querySelectorAll('.attr').forEach(a=>{
    let show = true;
    if(hRojo && a.dataset.rojo === '1') show = false;
    if(onlyRt && a.dataset.runtime !== '1') show = false;
    a.classList.toggle('hidden', !show);
  });
}
onlyRuntime.onchange = applyAttrFilters;
hideRojo.onchange = applyAttrFilters;
applyAttrFilters();

// search
const search = document.getElementById('search');
let t=null;
search.addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(runSearch, 120); });
function runSearch(){
  const q = search.value.trim().toLowerCase();
  // appendix filter
  ap.querySelectorAll('.ap').forEach(d=>{
    d.classList.toggle('hidden', q && d.dataset.name.indexOf(q) === -1);
  });
  if(!q){
    tree.querySelectorAll('li.node').forEach(li=>{ li.classList.remove('hidden','match'); });
    setAll(true);
    return;
  }
  tree.querySelectorAll('li.node').forEach(li=>{
    const hit = li.dataset.bag.indexOf(q) !== -1;
    li.classList.toggle('hidden', !hit);
    // direct name match highlight
    const nameHit = li.querySelector(':scope > .row > .iname')
      .textContent.toLowerCase().indexOf(q) !== -1;
    li.classList.toggle('match', nameHit);
  });
  // reveal & expand ancestors of any visible node
  tree.querySelectorAll('li.node:not(.hidden)').forEach(li=>{
    let p = li;
    while(p && p.classList && p.classList.contains('node')){
      p.classList.remove('hidden','collapsed');
      const tw = p.querySelector(':scope > .row > .tw');
      if(tw && !tw.classList.contains('leaf')) tw.textContent = '▼';
      p = p.parentElement.closest('li.node');
    }
  });
}
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
