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
# A variable or table-field reference, e.g. `KEY` or `UserIdUtil.ATTRIBUTE`.
_REF = r'[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*'
SET_REF_RE = re.compile(r':SetAttribute\(\s*(' + _REF + r')\s*,')
SET_REF_NIL_RE = re.compile(r':SetAttribute\(\s*(' + _REF + r')\s*,\s*nil\s*\)')
# GetAttribute("Name") - a read. Proves the attribute is touched by code even when
# it's never SetAttribute'd in the scanned src (e.g. set elsewhere / by the engine).
GET_LITERAL_RE = re.compile(r':GetAttribute\(\s*"([^"]+)"')
GET_REF_RE = re.compile(r':GetAttribute\(\s*(' + _REF + r')\s*\)')
# `<ref> = "<string>"` (captures KEY = "Foo", UserIdUtil.ATTRIBUTE = "Foo", ...).
ASSIGN_STR_RE = re.compile(r'(' + _REF + r')\s*=\s*["\']([^"\']+)["\']')


def _module_name(path):
    """The name a require(...) uses for this file: the basename, or the parent
    folder for an init.luau / init.server.luau module."""
    fn = os.path.basename(path)
    base = fn
    for ext in (".server.luau", ".client.luau", ".luau", ".server.lua", ".client.lua", ".lua"):
        if fn.endswith(ext):
            base = fn[: -len(ext)]
            break
    return os.path.basename(os.path.dirname(path)) if base == "init" else base


def _requires(text):
    """Module names this file require()s - the last identifier inside each
    require(...), with nested parens (e.g. :GetService("X")) handled."""
    mods = set()
    for mm in re.finditer(r'require\s*\(', text):
        depth, i = 1, mm.end()
        while i < len(text) and depth > 0:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
            i += 1
        names = re.findall(r'[A-Za-z_][A-Za-z0-9_]*', text[mm.end(): i - 1])
        if names:
            mods.add(names[-1])
    return mods


def scan_runtime_attributes(src_dir):
    """Attribute names referenced in code. Catches three shapes:
      1. literal    :SetAttribute("Name") / :GetAttribute("Name")
      2. via a var  KEY = "Name" ... :SetAttribute(KEY); or a field
         UserIdUtil.ATTRIBUTE = "Name" ... :GetAttribute(UserIdUtil.ATTRIBUTE)
      3. via a module wrapper - a ModuleScript that does (2) is an attribute
         wrapper, so every script that require()s it is credited too (catches the
         indirect callers of a UserIdUtil-style helper)."""
    runtime_set, runtime_nil, runtime_read = {}, set(), {}

    # Show appendix paths from the project folder (e.g. "TsunamiGame/src/...").
    src_base = os.path.dirname(os.path.dirname(os.path.normpath(src_dir))) or PROJECT_ROOT

    luau_files = []
    for root, _dirs, files in os.walk(src_dir):
        for fn in files:
            if fn.endswith(".luau") or fn.endswith(".lua"):
                luau_files.append(os.path.join(root, fn))

    file_texts = {}
    for path in luau_files:
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as f:
                file_texts[path] = f.read()
        except OSError:
            continue

    # ref -> the string it was assigned, per file and globally. A dotted field like
    # UserIdUtil.ATTRIBUTE is globally unique; a plain KEY is resolved file-local first.
    file_ref, global_ref = {}, {}
    for path, text in file_texts.items():
        m = {}
        for a in ASSIGN_STR_RE.finditer(text):
            m[a.group(1)] = a.group(2)
            global_ref[a.group(1)] = a.group(2)
        file_ref[path] = m

    def resolve(path, ref):
        return file_ref[path].get(ref) or global_ref.get(ref)

    # main pass: literals + variable/field-resolved Get/Set. A module that resolves a
    # ref through Get/Set is an attribute "wrapper"; record what it wraps so callers
    # (scripts that require it) can be credited afterward.
    module_attrs = {}      # module name -> set(attribute names it wraps)
    file_requires = {}     # path -> set(module names required)
    for path, text in file_texts.items():
        rel = os.path.relpath(path, src_base)
        for name in SET_LITERAL_RE.findall(text):
            runtime_set.setdefault(name, set()).add(rel)
        for name in SET_LITERAL_NIL_RE.findall(text):
            runtime_nil.add(name)
        for name in GET_LITERAL_RE.findall(text):
            runtime_read.setdefault(name, set()).add(rel)
        wrapped = set()
        for ref in SET_REF_RE.findall(text):
            name = resolve(path, ref)
            if name:
                runtime_set.setdefault(name, set()).add(rel)
                wrapped.add(name)
        for ref in SET_REF_NIL_RE.findall(text):
            name = resolve(path, ref)
            if name:
                runtime_nil.add(name)
        for ref in GET_REF_RE.findall(text):
            name = resolve(path, ref)
            if name:
                runtime_read.setdefault(name, set()).add(rel)
                wrapped.add(name)
        if wrapped:
            module_attrs.setdefault(_module_name(path), set()).update(wrapped)
        file_requires[path] = _requires(text)

    # credit every script that require()s a wrapper with that wrapper's attributes
    # (the indirect callers - e.g. everything that uses UserIdUtil.Get / .Set).
    for path, mods in file_requires.items():
        rel = os.path.relpath(path, src_base)
        for mod in mods:
            for name in module_attrs.get(mod, ()):
                runtime_read.setdefault(name, set()).add(rel)

    return runtime_set, runtime_nil, runtime_read


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
    runtime_set, runtime_nil, runtime_read = scan_runtime_attributes(SRC_DIR)
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
    read_names = set(runtime_read.keys())
    runtime_names = set(runtime_set.keys()) | read_names   # any code reference (Set or Get)

    # Appendix: names referenced in code (Set OR Get) but never seen at edit time in
    # the dump. A read-only name (GetAttribute, never SetAttribute) is marked "r".
    runtime_only = sorted(runtime_names - design_names)
    appendix = []
    for name in runtime_only:
        files = sorted(set(runtime_set.get(name, set())) | set(runtime_read.get(name, set())))
        m = "**" if name in runtime_nil else ("*" if name in runtime_set else "r")
        appendix.append({"n": name, "m": m, "files": files})

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
        "runtime": bool(runtime_set or runtime_nil),  # was the src/runtime scanned?
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
<title>__PROJECT__ | Attribute Map</title>
<style>
  :root{
    --bg:#0f1117; --panel:#161922; --row:#1b1f2a; --rowh:#232838;
    --ink:#e6e9f0; --dim:#9aa3b2; --line:#2a2f3d;
    --inst:#7cc4ff; --cls:#5f6b80; --attr:#d7dbe3;
    --val:#9ece6a; --type:#7a8294; --star:#ffb454; --dstar:#ff6b6b;
    --rojo:#5a5f6e; --accent:#7cc4ff; --badge:#272c3a; --purple:#c084fc;
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  header{position:sticky;top:0;z-index:10;background:var(--panel);
    border-bottom:1px solid var(--line);padding:12px 16px}
  h1{margin:0 0 6px;font-size:15px;font-weight:600;color:var(--ink)}
  .hint{color:var(--dim);font-size:11px;margin:2px 0 6px}
  .sub{color:var(--dim);font-size:11px;margin-bottom:6px}
  .sub .num{color:var(--accent);font-weight:600}
  #hiddencount{color:var(--accent);font-size:11px;margin-top:8px}
  .stats{color:var(--dim);font-size:11.5px;margin-bottom:8px}
  .stats b{color:var(--ink);font-weight:600}
  .stats .star{color:var(--purple)} .stats .dstar{color:var(--dstar)}
  /* tree action + marker-filter buttons, matching the Attribute Treehouse */
  #treebtns{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin:6px 0 8px}
  .mbtn{background:var(--row);border:1px solid var(--line);color:var(--dim);
    border-radius:5px;padding:2px 9px;font:inherit;font-size:11px;cursor:pointer;white-space:nowrap}
  .mbtn:hover{background:var(--rowh);color:var(--ink)}
  .mbtn.disabled{color:#6b7280;cursor:not-allowed;opacity:.7}      /* no runtime: greyed, no click */
  .mbtn.disabled:hover{background:var(--row);color:#6b7280}
  .mbtn.disabled .mk{color:#6b7280}
  .mbtn .mk{font-weight:700}
  .mbtn.star .mk{color:var(--purple)} .mbtn.dstar .mk{color:var(--dstar)} .mbtn.read .mk{color:#7aa2f7}
  .mbtn.star.on{background:var(--purple);color:#0b0d12;border-color:var(--purple)}
  .mbtn.dstar.on{background:var(--dstar);color:#0b0d12;border-color:var(--dstar)}
  .mbtn.read.on{background:#7aa2f7;color:#0b0d12;border-color:#7aa2f7}
  .mbtn.star.on .mk,.mbtn.dstar.on .mk,.mbtn.read.on .mk{color:#0b0d12}
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  input[type=search]{background:var(--row);border:1px solid var(--line);
    color:var(--ink);border-radius:6px;padding:6px 10px;font:inherit;width:280px}
  button{background:var(--row);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
  button:hover{background:var(--rowh)}
  label.tog{display:inline-flex;gap:5px;align-items:center;color:var(--dim);
    cursor:pointer;user-select:none}
  .legend{margin-left:auto;color:var(--dim);font-size:11px;display:flex;gap:14px;flex-wrap:wrap}
  .legend .star{color:var(--purple)} .legend .dstar{color:var(--dstar)}
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
  .mk.s{color:var(--purple)} .mk.d{color:var(--dstar)}
  .mk.r{color:#7aa2f7;font-weight:700}   /* read-only (GetAttribute) = blue * */
  .eq{color:var(--type)}
  .aval{color:var(--val)}
  .atype{color:var(--type);font-size:11px}
  .rojo .aname,.rojo .aval{color:var(--rojo)}
  .badge{background:var(--badge);color:var(--dim);border-radius:4px;
    padding:0 5px;font-size:10px;margin-left:4px}
  .hidden{display:none !important}
  .match>.row{background:#2c3350}
  .section{margin-top:20px;border-top:1px solid var(--line);padding-top:12px}
  .section h2{font-size:13px;color:var(--star);margin:0 0 8px;cursor:pointer;user-select:none}
  .aptw{display:inline-block;width:14px;color:var(--dim)}
  #appendix.apcollapsed .ap{display:none}   /* collapsed src runtime attributes */
  .ap{padding:1px 4px 1px 18px;color:var(--attr)}
  .ap .files{color:var(--dim);font-size:10.5px;margin-left:6px}
  .count{color:var(--dim);font-size:11px;margin-left:6px}
  mark{background:#4a4020;color:#ffd479;border-radius:2px;padding:0 1px}
  .attr{cursor:default}
  /* hover tooltip + bottom-left Attribute Finder (ported from the Attribute Treehouse) */
  #tip{position:fixed;z-index:50;pointer-events:none;display:none;background:#0b0d12;
    border:1px solid var(--line);border-radius:6px;padding:7px 9px;max-width:520px;
    box-shadow:0 6px 24px rgba(0,0,0,.5);color:var(--dim);font-size:11.5px}
  #tip b{color:var(--accent)}
  #toast{position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:60;
    display:none;background:#0b0d12;border:1px solid var(--accent);border-radius:6px;
    padding:7px 12px;color:var(--ink);font-size:12px;box-shadow:0 6px 24px rgba(0,0,0,.5)}
  #attrhelper{position:fixed;left:14px;bottom:14px;z-index:55;background:#0b0d12;
    border:1px solid var(--line);border-radius:6px;padding:8px 10px;font-size:12px;
    box-shadow:0 6px 24px rgba(0,0,0,.5);max-width:96vw;width:max-content}
  #attrhelper .ah-name{color:var(--ink);font-weight:700;margin-bottom:5px}
  #attrhelper .ah-row{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-start}
  #attrhelper .ah-cell{display:flex;flex-direction:column;align-items:flex-start;gap:4px}
  #attrhelper .ah-cap{color:var(--dim);font-size:10.5px;text-align:left}
  #attrhelper code{background:#11151c;border:1px solid var(--line);border-radius:5px;
    padding:4px 8px;color:#56d4ff;cursor:pointer;white-space:nowrap}
  #attrhelper code:hover{border-color:#56d4ff}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__ | Attribute Map</h1>
  <div class="hint">The attribute map is true to game hierarchy.</div>
  <div class="sub" id="sub"></div>
  <div class="stats" id="stats"></div>
  <div id="treebtns"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="advanced search&hellip;"/>
    <input type="search" id="ignorelist" placeholder="ignore list, comma separated"/>
  </div>
  <div id="hiddencount"></div>
</header>
<main>
  <div class="tree" id="tree"></div>
  <div class="section" id="appendix"></div>
</main>
<div id="tip"></div>
<div id="toast"></div>
<div id="attrhelper" style="display:none"></div>
<script>
/*__DATA__*/

const esc = s => String(s).replace(/[&<>]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

function attrRow(a){
  const li = document.createElement('div');
  li.className = 'attr' + (a.rojo ? ' rojo' : '');
  li.dataset.name = a.n.toLowerCase();
  li.dataset.runtime = a.m ? '1' : '0';
  li.dataset.mark = a.m || '';        // '' | '*' | '**' for the marker-filter buttons
  li.dataset.rojo = a.rojo ? '1' : '0';
  const mk = a.m === '**' ? '<span class="mk d">**</span>'
           : a.m === '*'  ? '<span class="mk s">*</span>' : '';
  const rojo = a.rojo ? '<span class="badge">rojo</span>' : '';
  li.innerHTML = '<span class="aname">'+esc(a.n)+'</span>'+mk+
    '<span class="eq">=</span><span class="aval">'+esc(a.v)+'</span>'+
    '<span class="atype">('+esc(a.t)+')</span>'+rojo;
  return li;
}

function nodeEl(node, parentPath){
  const li = document.createElement('li');
  li.className = 'node collapsed';
  // full Explorer path (the synthetic "game" root contributes nothing) - used as the
  // host hierarchy in the Attribute Finder panel.
  const path = (parentPath === undefined) ? '' : (parentPath === '' ? node.n : parentPath + '.' + node.n);
  li.dataset.path = path;
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
    for(const c of (node.ch||[])){ const cu = nodeEl(c, path); ul.appendChild(cu.li); bag += ' '+cu.bag; }
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

// build tree, wrapped under a single collapsible "game" root (Roblox DataModel),
// so the whole studio-set hierarchy can be collapsed with one click.
const treeRoot = document.getElementById('tree');
const ul = document.createElement('ul');
ul.appendChild(nodeEl({n:'game', c:'DataModel', a:[], ch:DATA.tree}).li);
treeRoot.appendChild(ul);

// Global Count (matches the Attribute Treehouse; counts in accent blue)
const s = DATA.summary;
document.getElementById('sub').innerHTML =
  'Global Count: <span class="num">'+s.attributed_instances+'</span> instances with attributes, '+
  '<span class="num">'+s.real_attr_count+'</span> attributes total.';

// stats line (sits where the Treehouse's service search is). The * / ** counts are
// spelled out so the legend key is no longer needed.
document.getElementById('stats').innerHTML =
  '<b>'+s.total_nodes+'</b> tree nodes &nbsp;&middot;&nbsp; '+
  '<b>'+s.design_names+'</b> studio set attributes &nbsp;&middot;&nbsp; '+
  '<b>'+s.runtime_names+'</b> runtime attributes &nbsp;&middot;&nbsp; '+
  '<b>'+s.runtime_only+'</b> runtime-only';

// appendix
const ap = document.getElementById('appendix');
let aphtml = '<h2 id="aphead"><span class="aptw">&#9660;</span> src runtime attributes <span class="count" id="apcount"></span></h2>';
for(const a of DATA.appendix){
  const mk = a.m === '**' ? '<span class="mk d">**</span>'
           : a.m === '*'  ? '<span class="mk s">*</span>'
           : '<span class="mk r" title="read in code (GetAttribute), never set in the scanned src">*</span>';
  aphtml += '<div class="ap" data-name="'+esc(a.n.toLowerCase())+'" data-mark="'+a.m+'" data-files="'+esc(a.files.join(' ').toLowerCase())+'"><span class="aname">'+
    esc(a.n)+'</span>'+mk+'<span class="files">'+esc(a.files.join('  &middot;  '))+'</span></div>';
}
ap.innerHTML = aphtml;
// click the heading to collapse / expand all src runtime attributes
document.getElementById('aphead').onclick = ()=>{
  const collapsed = ap.classList.toggle('apcollapsed');
  document.querySelector('.aptw').innerHTML = collapsed ? '&#9654;' : '&#9660;';
};

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
// Tree action + marker-filter buttons (Expand all / Collapse all / Set in code * /
// Nil-able **) - same look as the Attribute Treehouse; replaces the only-*/** box
// and the upper-right key.
const markerFilter = new Set();   // at most one of '*' / '**' (mutually exclusive)
const HAS_RUNTIME = !!DATA.summary.runtime;   // was the src/runtime scanned?
const NO_RT_TIP = "For run-time attributes, use the 'Include Runtime' toggle in the Roblox Studio plugin menu. Follow setup directions.";
function syncMarkerBtns(){ document.querySelectorAll('#treebtns .mbtn[data-mark]').forEach(b=>b.classList.toggle('on', markerFilter.has(b.dataset.mark))); }
(function buildTreeBtns(){
  const grp = document.getElementById('treebtns');
  const exp = document.createElement('button'); exp.className='mbtn'; exp.id='expandAll'; exp.textContent='Expand all';
  exp.title='expand every branch';
  const col = document.createElement('button'); col.className='mbtn'; col.id='collapseAll'; col.textContent='Collapse all';
  col.title='collapse every branch';
  grp.appendChild(exp); grp.appendChild(col);
  const mk=(mark,label,cls,opts)=>{
    opts=opts||{};
    const glyph=opts.glyph||mark;
    const b=document.createElement('button'); b.className='mbtn '+cls; b.dataset.mark=mark;
    const g='<span class="mk">'+glyph+'</span>';
    b.innerHTML = opts.prefix ? (g+' '+label) : (label+' '+g);  // read = asterisk-first
    if(!HAS_RUNTIME){ b.classList.add('disabled'); b.title=NO_RT_TIP; } // no runtime -> not clickable
    else {
      b.title=opts.title||('show only attributes marked '+glyph);
      b.onclick=()=>{ const was=markerFilter.has(mark); markerFilter.clear(); // mutually exclusive
        if(!was) markerFilter.add(mark); syncMarkerBtns(); applyView(); };
    }
    grp.appendChild(b);
  };
  mk('*', 'Set in code', 'star');
  mk('r', 'Read in code', 'read', {glyph:'*', prefix:true,
      title:'show only attributes read in code (GetAttribute)'});
  mk('**', 'Nil-able', 'dstar');   // nil-able stays furthest right
})();
document.getElementById('expandAll').onclick = ()=>setAll(false);
document.getElementById('collapseAll').onclick = ()=>setAll(true);

// Unified view: hide [rojo], the marker buttons, and the text search ALL funnel
// here. Attributes are hidden per rojo/marker; then nodes are shown only on the
// path to a surviving attribute (and any text match), and those branches are
// expanded so the matches are actually revealed (the buttons now "sort to purpose").
const search = document.getElementById('search');
let ignoreSet = new Set();   // comma-separated names (attr OR host) to ignore everywhere
function applyView(){
  const fm = markerFilter.size > 0, q = search.value.trim().toLowerCase(), ig = ignoreSet.size > 0;
  // 0) ignore pass: mark nodes ignored by name, inherited from ancestors (doc order
  //    visits ancestors first, so a parent's flag is set before its child reads it).
  tree.querySelectorAll('li.node').forEach(li=>{
    const own = ig && ignoreSet.has(li.querySelector(':scope > .row > .iname').textContent.toLowerCase());
    const par = li.parentElement.closest('li.node');
    li.dataset._ign = (own || (par && par.dataset._ign === '1')) ? '1' : '0';
  });
  const attrIgnored = a => ig && (ignoreSet.has(a.dataset.name) || a.closest('li.node').dataset._ign === '1');
  // 1) per-attribute visibility: the marker buttons + the ignore list
  tree.querySelectorAll('.attr').forEach(a=>{
    a.classList.toggle('hidden', (fm && !markerFilter.has(a.dataset.mark)) || attrIgnored(a));
  });
  // appendix ("src runtime attributes") follows the text search, markers, and ignore
  ap.querySelectorAll('.ap').forEach(d=>{
    let show = true;
    if(q && d.dataset.name.indexOf(q) === -1) show = false;
    if(fm && !markerFilter.has(d.dataset.mark)) show = false;
    // ignore list hides an entry when the attr name is ignored OR any term appears in
    // its src file paths - so "client"/"server" act on .client.luau / .server.luau etc.
    if(ig && (ignoreSet.has(d.dataset.name) || [...ignoreSet].some(t=>d.dataset.files.indexOf(t)!==-1))) show = false;
    d.classList.toggle('hidden', !show);
  });
  if(!fm && !q){
    // 2) no search/marker -> default collapsed view (game root open), ignored hidden
    tree.querySelectorAll('li.node').forEach(li=>{ li.classList.toggle('hidden', li.dataset._ign === '1'); li.classList.remove('match'); });
    setAll(true);
    const g=tree.querySelector(':scope > ul > li.node');
    if(g && g.dataset._ign !== '1'){ g.classList.remove('collapsed'); const tw=g.querySelector(':scope > .row > .tw');
      if(tw && !tw.classList.contains('leaf')) tw.textContent='▼'; }
  } else {
    // 3) a node is relevant if its text matches (bag), its subtree still has a visible
    //    attribute (marker filter), and it isn't ignored. Hide the rest.
    tree.querySelectorAll('li.node').forEach(li=>{
      const textOk = !q || li.dataset.bag.indexOf(q) !== -1;
      const markOk = !fm || li.querySelector('.attr:not(.hidden)') !== null;
      const ignOk = li.dataset._ign !== '1';
      li.classList.toggle('hidden', !(textOk && markOk && ignOk));
      const nameHit = q && li.querySelector(':scope > .row > .iname').textContent.toLowerCase().indexOf(q) !== -1;
      li.classList.toggle('match', !!nameHit);
    });
    // 4) reveal + expand every surviving node and its ancestors
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
  // 5) two living counters - the studio-set tree, and the src-runtime appendix -
  //    each coloured green / yellow / red and recomputed on every search/toggle.
  const reasons = [];
  if(q) reasons.push('search');
  if(fm) reasons.push('marker filter');
  if(ig) reasons.push('ignore list');
  const by = reasons.length ? ' by '+reasons.join(', ')+'.' : '.';
  const col = (h,t)=> h<=0 ? '#5fd37a' : (h>=t ? '#ff6b6b' : '#e7c45a');
  const counter = (h,t,label)=>'<span style="color:'+col(h,t)+';font-weight:700">'+h+' of '+t+'</span> '+(label?label+' ':'')+'hidden'+by;
  // studio-set attributes (the tree)
  const total = tree.querySelectorAll('.attr').length;
  const hidden = tree.querySelectorAll('.attr.hidden, li.node.hidden .attr').length;
  document.getElementById('hiddencount').innerHTML = counter(hidden, total, 'studio set attributes');
  // src runtime attributes (the appendix) - lives in the appendix heading
  const apc = document.getElementById('apcount');
  if(apc){
    const apTotal = ap.querySelectorAll('.ap').length;
    const apHidden = ap.querySelectorAll('.ap.hidden').length;
    // 0 of 0 = nothing scanned from src - usually means the src isn't synced. Flag it red.
    apc.innerHTML = apTotal===0
      ? '<span style="color:#ff6b6b;font-weight:700">0 of 0</span> hidden. <span style="color:#ff6b6b">*Did you sync to your src?</span>'
      : counter(apHidden, apTotal, '');
  }
}
let t=null;
search.addEventListener('input', ()=>{ clearTimeout(t); t=setTimeout(applyView, 120); });
// ignore list: comma-separated names (attr OR host), applied across the whole view
const ignoreInput=document.getElementById('ignorelist'); let it2=null;
ignoreInput.addEventListener('input', ()=>{ clearTimeout(it2); it2=setTimeout(()=>{
  ignoreSet=new Set(ignoreInput.value.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean));
  applyView();
}, 140); });
applyView();

// ---- hover tooltip + bottom-left Attribute Finder (ported from the Treehouse) ----
const CB = navigator.userAgent.indexOf('Mac')!==-1 ? 'Cmd' : 'Ctrl';
function copyText(s){
  try{ if(navigator.clipboard && navigator.clipboard.writeText){ navigator.clipboard.writeText(s); return true; } }catch(e){}
  const ta=document.createElement('textarea'); ta.value=s; ta.style.position='fixed'; ta.style.top='-1000px';
  document.body.appendChild(ta); ta.focus(); ta.select(); let ok=false; try{ ok=document.execCommand('copy'); }catch(e){}
  document.body.removeChild(ta); return ok;
}
const tip=document.getElementById('tip'), toast=document.getElementById('toast'); let toastT=null;
function flashToast(msg, ms){ toast.textContent=msg; toast.style.display='block'; clearTimeout(toastT); toastT=setTimeout(()=>{ toast.style.display='none'; }, ms||1600); }
function flashCopied(p){ flashToast('Copied: '+p); }

// Persistent bottom-left panel: Attribute("Name") (script search) + host hierarchy (Explorer).
const attrHelper=document.getElementById('attrhelper');
function showFinder(name, host){
  attrHelper.innerHTML='';
  const title=document.createElement('div'); title.className='ah-name'; title.textContent='Attribute Finder: '+name;
  const row=document.createElement('div'); row.className='ah-row';
  const cell=(text,caption,tipt)=>{
    const colm=document.createElement('div'); colm.className='ah-cell';
    const c=document.createElement('code'); c.textContent=text; c.title=tipt;
    c.onclick=()=>{ if(copyText(text)) flashCopied(text); };
    const cap=document.createElement('div'); cap.className='ah-cap'; cap.textContent=caption;
    colm.appendChild(c); colm.appendChild(cap); row.appendChild(colm);
  };
  cell('Attribute("'+name+'")', 'Paste into "Find in Place"', 'copy for script search - matches Get & SetAttribute');
  cell(host, 'Paste into "Explorer"', 'copy the host hierarchy to find the instance(s)');
  attrHelper.appendChild(title); attrHelper.appendChild(row);
  attrHelper.style.display='block';
}

// Clicking an attribute LOCKS it into the panel for 3s, so the cursor can travel to
// the panel without other rows stealing it.
let attrLockUntil=0;
function attrLocked(){ return performance.now() < attrLockUntil; }
function attrInfo(a){
  return { name:a.querySelector('.aname').textContent,
           host:(a.closest('li.node')||{dataset:{}}).dataset.path || '',
           val:(a.querySelector('.aval')||{}).textContent || '',
           type:(a.querySelector('.atype')||{}).textContent || '',
           mk:(a.querySelector('.mk')||{}).textContent || '' };
}
tree.addEventListener('mousemove', e=>{
  const a=e.target.closest('.attr'); if(!a){ tip.style.display='none'; return; }
  const it=attrInfo(a);
  let t2='<b>'+esc(it.name)+'</b> = '+esc(it.val)+' '+esc(it.type)+(it.mk?'  '+it.mk:'');
  if(attrLocked()){
    t2+='<br/><span style="color:var(--type)">panel locked - move to it to copy</span>';
  } else {
    showFinder(it.name, it.host);
    t2+='<br/><span style="color:var(--type)">click to lock Attribute Finder panel for 3 seconds</span>';
  }
  tip.innerHTML=t2; tip.style.display='block';
  let x=e.clientX+14, y=e.clientY+14; const r=tip.getBoundingClientRect();
  if(x+r.width>innerWidth) x=e.clientX-r.width-14;
  if(y+r.height>innerHeight) y=e.clientY-r.height-14;
  tip.style.left=x+'px'; tip.style.top=y+'px';
});
tree.addEventListener('mouseleave', ()=>{ tip.style.display='none'; });
tree.addEventListener('click', e=>{
  const a=e.target.closest('.attr'); if(!a) return;
  const it=attrInfo(a);
  attrLockUntil=performance.now()+3000;
  showFinder(it.name, it.host);
  flashToast('Locked "'+it.name+'" for 3s - move to the panel to copy', 3000);
});
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
