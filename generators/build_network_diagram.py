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
import sys
import json
import html
import importlib.util
import traceback

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


# ---------------------------------------------------------------------------
# Code-site script hosts. Every src script that SetAttribute/GetAttribute's a
# name becomes a node at its real game-hierarchy location, hosting those
# attributes as items (set = '*' purple, read = 'r' blue). Always merged into
# the dump tree so the scripts inherit the same expand/collapse/path-compression.
# ---------------------------------------------------------------------------
_SCRIPT_EXT = [(".server.luau", "Script"), (".server.lua", "Script"),
               (".client.luau", "LocalScript"), (".client.lua", "LocalScript"),
               (".luau", "ModuleScript"), (".lua", "ModuleScript")]


def _script_game_path(rel, src_name):
    """Map a scanned src file path to (parts, leaf_class) in the game tree.
    'TsunamiGame/src/ServerScriptService/Economy/Dump.server.luau'
       -> (['ServerScriptService','Economy','Dump'], 'Script'). Rojo init.* files
    collapse onto their folder. Returns (None, None) for non-script files."""
    segs = rel.replace("\\", "/").split("/")
    if src_name in segs:
        parts = segs[segs.index(src_name) + 1:]
    elif "src" in segs:
        parts = segs[segs.index("src") + 1:]
    else:
        parts = segs[1:]                      # fall back: drop the project folder
    if not parts:
        return None, None
    fname, cls, base = parts[-1], None, parts[-1]
    for ext, c in _SCRIPT_EXT:
        if fname.endswith(ext):
            cls, base = c, fname[:-len(ext)]
            break
    if cls is None:
        return None, None                     # not a Luau script
    if base.lower() == "init":
        parts = parts[:-1]                    # init.* -> the folder is the script
    else:
        parts = parts[:-1] + [base]           # file is the script
    return (parts, cls) if parts else (None, None)


def build_script_hosts(runtime_set, runtime_read, src_dir):
    """{service: nested node}; node = {'c':class,'ch':{name:node},'items':{attr:mark}}."""
    src_name = os.path.basename(os.path.normpath(src_dir))
    by_file = {}                              # rel file -> {attr: 'set'|'read'} (set wins)
    for name, files in runtime_set.items():
        for rel in files:
            by_file.setdefault(rel, {})[name] = "set"
    for name, files in runtime_read.items():
        for rel in files:
            by_file.setdefault(rel, {}).setdefault(name, "read")

    services = {}
    for rel, names in by_file.items():
        parts, cls = _script_game_path(rel, src_name)
        if not parts:
            continue
        svc = parts[0]
        node = services.setdefault(svc, {"c": svc, "ch": {}, "items": {}})
        inner = parts[1:]
        for i, p in enumerate(inner):
            leaf = (i == len(inner) - 1)
            child = node["ch"].get(p)
            if child is None:
                child = {"c": cls if leaf else "Folder", "ch": {}, "items": {}}
                node["ch"][p] = child
            elif leaf:
                child["c"] = cls
            node = child
        for nm, kind in names.items():
            mk = "*" if kind == "set" else "r"
            if node["items"].get(nm) != "*":  # a set beats a read
                node["items"][nm] = mk
    return services


def _script_to_uniform(name, node):
    return {"n": name, "c": node["c"],
            "items": [{"n": nm, "m": mk, "code": True}
                      for nm, mk in sorted(node["items"].items())],
            "ch": [_script_to_uniform(cn, node["ch"][cn]) for cn in sorted(node["ch"])]}


def _merge_uniform(dst, src):
    """Deep-merge src (script hosts) into dst (dump tree) by child name."""
    dst["items"] = dst.get("items", []) + src.get("items", [])
    idx = {c["n"]: c for c in dst.setdefault("ch", [])}
    for sc in src.get("ch", []):
        if sc["n"] in idx:
            _merge_uniform(idx[sc["n"]], sc)
        else:
            dst["ch"].append(sc)


def main():
    runtime_set, runtime_nil, runtime_read = bat.scan_runtime_attributes(bat.SRC_DIR)
    roots, _total = bat.parse_dump(bat.DUMP_PATH)
    stats = {"rojo_attr_count": 0, "real_attr_count": 0, "design_names": set(),
             "star_count": 0, "dstar_count": 0, "attributed_instances": 0}
    serialized = [bat.serialize(r, runtime_set, runtime_nil, stats) for r in roots]

    # dump trees -> uniform, keyed by service (preserve the dump's service order)
    order = [s["n"] for s in serialized]
    uni = {s["n"]: attr_node_to_uniform(s) for s in serialized}

    # Always merge in the code-site script hosts: each src script that sets/reads an
    # attribute appears at its real place in the hierarchy, hosting those attributes.
    # Fail-safe: a problem here must NEVER block the whole Treehouse - on any error we
    # log the traceback (to working/treehouse_error.log + stderr) and fall back to the
    # plain dump tree (no code sites), so generation still succeeds.
    try:
        for svc, snode in build_script_hosts(runtime_set, runtime_read, bat.SRC_DIR).items():
            su = _script_to_uniform(svc, snode)
            if svc in uni:
                _merge_uniform(uni[svc], su)
            else:
                uni[svc] = su
                order.append(svc)
    except Exception:                              # noqa: BLE001 - never crash generation
        tb = traceback.format_exc()
        sys.stderr.write("[Treehouse] code-site script merge skipped (error below):\n" + tb)
        try:
            with open(os.path.join(bat.PROJECT_ROOT, "working", "treehouse_error.log"),
                      "w", encoding="utf-8") as _f:
                _f.write(tb)
        except OSError:
            pass

    services = []
    tot_inst = tot_items = 0
    for name in order:
        disp = compress(uni[name])
        ic, it = count_display(disp)
        services.append(disp)
        tot_inst += ic
        tot_items += it

    summary = {"project": bat.PROJECT_NAME, "item_kind": "attribute",
               "item_label": "attributes",
               "runtime": bool(runtime_set or runtime_nil or runtime_read),  # src scanned?
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
    kind = {"value": "Value*", "collision": "Collision", "ownership": "Ownership"}.get(
        summary.get("item_kind"), "Attribute")
    out = out.replace("__KIND__", kind)
    return out


ENGINE_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__PROJECT__ | __KIND__ Treehouse</title>
<style>
  :root{
    --bg:#0f1117; --panel:#161922; --ink:#e6e9f0; --dim:#9aa3b2;
    --line:#2a2f3d; --row:#1b1f2a; --rowh:#232838; --accent:#7cc4ff;
    --edge:#39414f; --star:#ffb454; --dstar:#ff6b6b; --badge:#272c3a;
    --item:#d7dbe3; --val:#9ece6a; --type:#7a8294; --vcls:#b794f6; --purple:#c084fc;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--bg);color:var(--ink);
    font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  /* flex column: header stays a fixed top bar, #wrap fills the rest and scrolls */
  body{display:flex;flex-direction:column;height:100vh;overflow:hidden}
  header{flex:0 0 auto;z-index:20;background:var(--panel);
    border-bottom:1px solid var(--line);padding:10px 14px}
  h1{margin:0 0 6px;font-size:15px;font-weight:600}
  .sub{color:var(--dim);font-size:11px;margin-bottom:6px}
  .sub .num{color:var(--accent);font-weight:600}     /* counts in accent blue */
  /* tree action + marker-filter buttons, their own row below the service tabs */
  #treebtns{display:flex;gap:6px;align-items:center;flex-wrap:wrap;margin-bottom:8px}
  .mbtn{background:var(--row);border:1px solid var(--line);color:var(--dim);
    border-radius:5px;padding:2px 9px;font:inherit;font-size:11px;cursor:pointer;white-space:nowrap}
  .mbtn:hover{background:var(--rowh);color:var(--ink)}
  .mbtn.disabled{color:#6b7280;cursor:not-allowed;opacity:.7}      /* no runtime: greyed, no click */
  .mbtn.disabled:hover{background:var(--row);color:#6b7280}
  .mbtn.disabled .mk{color:#6b7280}
  .mbtn .mk{font-weight:700}                              /* the * / ** key on the button */
  .mbtn.star .mk{color:var(--purple)}                     /* * = purple (set/declared in code) */
  .mbtn.read .mk{color:#7aa2f7}                           /* * = blue (read in code) */
  .mbtn.dstar .mk{color:var(--dstar)}                     /* ** = red */
  .mbtn.ncm .mk{color:#ff5555}                            /* *** = Instance value */
  .mbtn.star.on{background:var(--purple);color:#0b0d12;border-color:var(--purple)}
  .mbtn.read.on{background:#7aa2f7;color:#0b0d12;border-color:#7aa2f7}
  .mbtn.dstar.on{background:var(--dstar);color:#0b0d12;border-color:var(--dstar)}
  .mbtn.ncm.on{background:#ff5555;color:#0b0d12;border-color:#ff5555}
  .mbtn.ncm.on .mk{color:#0b0d12}
  .mbtn.star.on .mk,.mbtn.read.on .mk,.mbtn.dstar.on .mk{color:#0b0d12}     /* dark key on the lit button */
  .mbtn.prop.on{background:var(--accent);color:#0b0d12;border-color:var(--accent)}      /* fidelity active */
  .mbtn.prop.on-true{background:var(--accent);color:#0b0d12;border-color:var(--accent)} /* {Prop} True = blue */
  .mbtn.prop.on-false{background:var(--star);color:#0b0d12;border-color:var(--star)}     /* {Prop} False = yellow */
  /* global search: a full-width bar above the tabs; non-empty -> each tab shows
     a (match count). Distinct accent border so it reads as the cross-service one. */
  #globalsearch{display:block;width:100%;max-width:520px;min-width:240px;margin:0 0 8px;
    border-color:#34507a;flex:none}
  #globalsearch:focus{outline:none;border-color:var(--accent)}
  .tabs{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px}
  .tab{background:var(--row);border:1px solid var(--line);color:var(--dim);
    border-radius:6px;padding:5px 9px;cursor:pointer;font:inherit}
  .tab .ct{color:var(--accent);font-size:11px;font-weight:700}
  .tab .ct.zero,.tab.active .ct.zero{color:#ff6b6b} /* global search: 0 matches = red */
  .tab.active{background:var(--accent);color:#0b0d12;border-color:var(--accent)}
  .tab.active .ct{color:#0b0d12}
  .globaltab{margin-right:10px}                                                       /* Global toggle, left of the service tabs */
  .globaltab.active{background:var(--purple);color:#0b0d12;border-color:var(--purple)} /* on = purple, distinct from a blue service pick */
  .controls{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
  input[type=search]{background:var(--row);border:1px solid var(--line);
    color:var(--ink);border-radius:6px;padding:6px 10px;font:inherit;
    flex:1 1 320px;min-width:240px;max-width:520px}
  #minwrap{display:inline-flex;align-items:center;gap:6px;color:var(--dim);
    font-size:11px;white-space:nowrap}
  #minwrap input[type=range]{width:96px}
  #hideSibBtn.on{background:var(--accent);color:#0b0d12;border-color:var(--accent)}  /* Hide Siblings active */
  #minlbl{color:var(--accent);font-weight:700;min-width:22px;text-align:right}
  button{background:var(--row);border:1px solid var(--line);color:var(--ink);
    border-radius:6px;padding:6px 10px;font:inherit;cursor:pointer}
  button:hover{background:var(--rowh)}
  /* class legend on its own full-width line, left-aligned (nothing starts at the
     center/right where it could clash on small screens) */
  .legend{display:flex;gap:10px;flex-wrap:wrap;align-items:center;
    color:var(--dim);font-size:11px;margin-top:6px}
  .legend span{display:inline-flex;align-items:center;gap:4px;cursor:pointer;user-select:none}
  .legend span:hover{color:var(--ink)}
  .legend span.off{opacity:.4;text-decoration:line-through}
  #creators{margin-top:4px}
  #creators .crlab{color:var(--dim);cursor:default}
  #creators .crtag{color:var(--dim);font-size:9px;margin-left:3px;opacity:.65}
  .dot{width:9px;height:9px;border-radius:50%;display:inline-block}
  .hint{color:var(--dim);font-size:11px;margin-top:4px}
  #hiddencount{color:var(--accent);font-size:11px;margin-top:6px}
  #wrap{position:relative;overflow:auto;flex:1;min-height:0}
  svg{display:block}
  .edge{fill:none;stroke:var(--edge);stroke-width:1}
  .node{cursor:pointer}
  .node tspan.nm{fill:var(--ink)}
  .node tspan.cl{fill:var(--dim);font-size:10px}
  .node tspan.gnm{fill:var(--dim);font-weight:600;letter-spacing:.3px} /* layer group label */
  .node.match tspan.nm{fill:#ffd479;font-weight:700}
  .item tspan.inm{fill:var(--item)}
  .item tspan.ival{fill:var(--val)}
  .item tspan.itype{fill:var(--type);font-size:10px}
  .item tspan.icls{fill:var(--vcls);font-size:10px}
  .item tspan.mk.s{fill:var(--purple);font-weight:700}
  .item tspan.mk.r{fill:#7aa2f7;font-weight:700}
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
  /* bottom-RIGHT toolbar: a stack of collapsible "chat head" cards (Delete /
     Fortify / Instance Farmer), each a Command Bar snippet for the hovered
     attribute over the current scope. Sits just left of the section rail. */
  #toolbar{position:fixed;right:calc(15vw + 14px);bottom:14px;z-index:55;
    display:flex;flex-direction:column;gap:8px;align-items:stretch;
    width:min(46vw,560px);max-height:84vh}
  .tb-card{background:#0b0d12;border:1px solid var(--line);border-radius:8px;
    box-shadow:0 6px 24px rgba(0,0,0,.5);overflow:hidden}
  .tb-head{display:flex;align-items:center;justify-content:space-between;gap:10px;
    padding:8px 11px;cursor:pointer;user-select:none;font-weight:700;font-size:12.5px}
  .tb-head:hover{background:#11151c}
  .tb-chev{color:var(--dim);font-size:11px}
  .tb-body{padding:0 11px 9px;display:flex;flex-direction:column;gap:6px}
  .tb-detail{font-weight:700;font-size:12px}
  .tb-hint{color:var(--dim);font-size:11px;padding:2px 0 4px}
  .tb-cap{color:var(--dim);font-size:10.5px}
  .tb-cap b{color:var(--ink);font-weight:600}
  .tb-card pre{margin:0;background:#11151c;border:1px solid var(--line);border-radius:5px;
    padding:6px 9px;cursor:pointer;white-space:pre;overflow:auto;max-height:38vh;
    font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
  /* per-tab accent: delete=red, fortify=green, farmer=yellow */
  .tb-card.del .tb-title,.tb-card.del .tb-detail{color:#ff6b6b}
  .tb-card.del pre{color:#ff9b9b}      .tb-card.del pre:hover{border-color:#ff6b6b}
  .tb-card.fort .tb-title,.tb-card.fort .tb-detail{color:#5fd37a}
  .tb-card.fort pre{color:#9ee6a8}     .tb-card.fort pre:hover{border-color:#5fd37a}
  .tb-card.farm .tb-title,.tb-card.farm .tb-detail{color:#e7c45a}
  .tb-card.farm pre{color:#f0d98a}     .tb-card.farm pre:hover{border-color:#e7c45a}
  .tb-card.conv .tb-title,.tb-card.conv .tb-detail{color:#7cc4ff} /* convert value*=blue */
  .tb-card.conv pre{color:#a9d8ff}     .tb-card.conv pre:hover{border-color:#7cc4ff}
  .tb-card.space .tb-title,.tb-card.space .tb-detail{color:#4fd6be} /* instance spacing = teal */
  .tb-card.space pre{color:#9bead9}    .tb-card.space pre:hover{border-color:#4fd6be}
  /* Right-anchored section rail (jump to a first-layer node). Entries are
     right-aligned and overflow LEFT so long names stay full-size. */
  #mapper{position:fixed;right:0;width:15vw;z-index:40;overflow-y:auto;
    overflow-x:visible;text-align:right;padding:8px 16px 40px 10px;pointer-events:none;
    scrollbar-width:thin;scrollbar-color:#3a4150 transparent}
  #mapper::-webkit-scrollbar{width:8px}
  #mapper::-webkit-scrollbar-thumb{background:#3a4150;border-radius:4px}
  #mapper::-webkit-scrollbar-track{background:transparent}
  #mapper .m-entry{display:block;white-space:nowrap;cursor:pointer;margin:3px 0;
    line-height:1.05;color:var(--dim);transition:font-size .08s ease;pointer-events:auto}
  #mapper .m-entry .pill{display:inline-block;background:rgba(11,13,18,.88);
    border:1px solid var(--line);border-radius:6px;padding:1px 8px}
  #mapper .m-entry:hover .pill{border-color:var(--accent)}
  #mapper .m-entry.active{color:var(--ink);font-weight:700}
  #mapper .m-entry.active .pill{border-color:var(--accent);background:rgba(20,26,38,.95)}
  #mapper .m-crumb{font-size:18px;color:var(--ink);font-weight:700}
  #mapper .m-crumb .pill{border-color:var(--accent);background:rgba(20,26,38,.95)}
</style>
</head>
<body>
<header>
  <h1>__PROJECT__ | __KIND__ Treehouse</h1>
  <div class="hint" id="introhint">Only instances that carry <span id="lbl1">items</span> are shown; empty containers are path-compressed (hover a node for its real path).</div>
  <div class="sub" id="sub"></div>
  <div class="sub" id="svccount" style="color:var(--accent)"></div>
  <input type="search" id="globalsearch" placeholder="service search counter&hellip;"/>
  <div class="tabs" id="tabs"></div>
  <div id="treebtns"></div>
  <div class="controls">
    <input type="search" id="search" placeholder="advanced search&hellip;"/>
    <input type="search" id="ignorelist" placeholder="ignore list, comma separated"/>
    <label id="minwrap" title="show only instances that have at least this many">
      &ge;&nbsp;<span id="minlbl">1+</span>&nbsp;<span id="minunit">items</span>
      <input type="range" id="minattrs" min="1" max="10" step="1" value="1"/>
    </label>
    <button id="hideSibBtn" class="mbtn" title="while searching, show only the matching item on each host and hide its other (sibling) items - lock onto every instance that has the searched name">Hide Siblings</button>
  </div>
  <div class="legend" id="legend"></div>
  <div class="legend" id="creators"></div>
  <div class="hint" id="counter"></div>
  <div id="hiddencount"></div>
</header>
<div id="wrap"><svg id="svg" xmlns="http://www.w3.org/2000/svg"></svg></div>
<div id="tip"></div>
<div id="toast"></div>
<div id="attrhelper" style="display:none"></div>
<div id="toolbar" style="display:none"></div>
<div id="mapper"></div>
<script>
/*__DATA__*/

// Per-kind behavior, so one engine serves Attribute / Value* / Collision pages:
//   finder : bottom-left panel - 'both' = script + host, 'host' = host only
//   tabs   : bottom-right toolbar cards (in order); [] hides the toolbar
//   slider : the ">= N" minimum-items control
//   markers : per-item marker glyphs + the "Set in code *" filter button
//   dstarBtn: also show the second ("**") filter button. Attribute pages do NOT -
//             nil-able filtering lives only on the Attribute Map page.
const KIND = DATA.summary.item_kind;
const CFG = ({
  attribute: {finder:'both',  tabs:['delete','fortify','farmer'], slider:true,  markers:true,  dstarBtn:false, ncBtn:false, finderTitle:'Attribute Finder'},
  value:     {finder:'value', tabs:['convert','farmer'],          slider:false, markers:true,  dstarBtn:true,  ncBtn:true,  finderTitle:'Value Finder'},
  collision: {finder:'host',  tabs:['spacing'],                            slider:false, markers:false, dstarBtn:false, ncBtn:false, finderTitle:'Collision Finder'},
  ownership: {finder:'host',  tabs:[],                                     slider:false, markers:false, dstarBtn:false, ncBtn:false, creators:true, finderTitle:'Ownership Finder'},
})[KIND] || {finder:'host', tabs:[], slider:false, markers:false, dstarBtn:false, ncBtn:false, finderTitle:'Finder'};

const ROWH=20, COLW=280, PADX=20, PADY=16, NODER=4;
const PALETTE=["#7cc4ff","#9ece6a","#ffb454","#ff6b6b","#b794f6","#4fd6be",
  "#f7768e","#e0af68","#73daca","#bb9af7","#7aa2f7","#ff9e64","#41a6b5","#d19a66"];
let classColor={}, paletteIdx=0;
function colorFor(c){ if(!(c in classColor)) classColor[c]=PALETTE[paletteIdx++%PALETTE.length]; return classColor[c]; }
const esc=s=>String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

// Flatten a compressed service tree to its carrier list. Each carrier keeps its
// real path, class, and own items; the compressed carrier-to-carrier nesting is
// dropped here and re-expressed as layer GROUPS in buildGrouped() below.
function flattenCarriers(d, out){
  for(const c of (d.ch||[])){
    out.push({n:c.n, c:c.c, path:c.path, items:c.items||[]});
    flattenCarriers(c, out);
  }
  return out;
}
// Deepest grouping layer (1-based path index) for a carrier given the drill path.
// Base case groups by the 2nd layer (index 1, the direct child of the service).
// For the branch the user drilled into, allow one layer deeper (3rd, index 2) -
// but never deeper than the carrier itself. (Loops so >1 drill level is automatic.)
function groupLayerFor(parts){
  let g=1;
  for(let i=0;i<drillStack.length;i++){ if(parts[1+i]===drillStack[i]) g=2+i; else break; }
  return Math.min(g, parts.length-1);
}
// Build the displayed tree for one service:
//   service root -> layer GROUP middlemen (mirror the Layer Mapper) -> carrier
//   instances -> attribute items.
// Group depth tracks the drill: only the 2nd layer by default, plus the 3rd layer
// inside the drilled branch. A group whose full path is itself a carrier becomes
// that real instance (adopts its class + items) instead of a synthetic folder.
function buildGrouped(serviceDisp){
  const root={kind:'inst', n:serviceDisp.n, c:serviceDisp.c, path:serviceDisp.path,
    _depth:0, _p:null, _expanded:true, _children:[]};
  for(const it of (serviceDisp.items||[])){
    root._children.push({kind:'item', it, n:it.n, _depth:1, _p:root, _children:[]});
  }
  const groupMap=new Map(); groupMap.set(root.path, root);
  function getGroup(prefixParts, depth){
    const path=prefixParts.join('.');
    let g=groupMap.get(path); if(g) return g;
    const parent=groupMap.get(prefixParts.slice(0,-1).join('.')) || root;
    g={kind:'inst', _group:true, n:prefixParts[prefixParts.length-1], c:null,
       path, _depth:depth, _p:parent, _expanded:true, _children:[], _carriers:0};
    groupMap.set(path,g); parent._children.push(g);
    return g;
  }
  for(const car of flattenCarriers(serviceDisp, [])){
    const parts=car.path.split('.');
    const gl=groupLayerFor(parts);
    let deepest=root;
    for(let li=1; li<=gl; li++){ deepest=getGroup(parts.slice(0,li+1), li); }
    if(parts.length-1===gl){
      // the carrier sits exactly at the deepest group: that group IS this instance
      deepest._group=false; deepest.c=car.c;
      for(const it of car.items){ deepest._children.push({kind:'item', it, n:it.n, _depth:deepest._depth+1, _p:deepest, _children:[]}); }
    } else {
      // carrier lives below the grouping cutoff: flatten it as a leaf under `deepest`
      const leaf={kind:'inst', n:car.n, c:car.c, path:car.path,
        _depth:deepest._depth+1, _p:deepest, _expanded:true, _children:[]};
      for(const it of car.items){ leaf._children.push({kind:'item', it, n:it.n, _depth:leaf._depth+1, _p:leaf, _children:[]}); }
      deepest._children.push(leaf);
    }
  }
  // tally carriers under each group (for the group's count badge)
  (function cnt(n){ let k=0; for(const c of n._children){ if(c.kind==='item') continue; if(!c._group) k++; k+=cnt(c); } n._carriers=k; return k; })(root);
  return root;
}
let curIdx=0, current=null;
let globalOn=false;                      // Global mode: aggregate several services
const globalSel=new Set();               // picked service indices (empty = all)
const GLOBAL_LABEL='Global';
function bumpDepth(n,by){ n._depth+=by; for(const c of n._children) bumpDepth(c,by); }
// Rebuild `current` from the active service (or the Global selection) + drill state.
// Called on boot, on tab switch, on the Global toggle, and on every drill change.
// Isolation references live nodes, so it can't survive a rebuild - clear it.
function rebuildCurrent(){
  isoNode=null;
  if(globalOn){                          // synthetic root holding the picked service trees
    drillStack=[];                        // no per-service drill in Global mode
    const idxs=globalSel.size ? [...globalSel].sort((a,b)=>a-b) : DATA.services.map((_,i)=>i);
    const root={kind:'inst', n:GLOBAL_LABEL, c:'DataModel', path:GLOBAL_LABEL,
      _depth:0, _p:null, _expanded:true, _children:[], _globalRoot:true};
    for(const i of idxs){ const svc=buildGrouped(DATA.services[i]);
      svc._p=root; svc._svc=true; bumpDepth(svc,1); root._children.push(svc); }
    current=root;
  } else {
    current=buildGrouped(DATA.services[curIdx]);
  }
}

// tabs
const tabs=document.getElementById('tabs');
// Global mode toggle, left of the service tabs: view several services together.
const gbtn=document.createElement('button'); gbtn.className='tab globaltab'; gbtn.id='globalTab'; gbtn.textContent='Global';
gbtn.title='Global: view several services together. Click services to add/remove (none picked = all shown). Double-click a class in the legend to see all of it across the game. Click Global again to drop back to one service.';
gbtn.onclick=()=>toggleGlobal();
tabs.appendChild(gbtn);
DATA.summary.services.forEach((s,i)=>{
  const b=document.createElement('button');
  b.className='tab'+(i===0?' active':'');
  const nm=document.createElement('span'); nm.textContent=s.name;
  const ct=document.createElement('span'); ct.className='ct'; // global-search match count
  b.appendChild(nm); b.appendChild(document.createTextNode(' ')); b.appendChild(ct);
  b.onclick=()=>{
    if(globalOn){                      // Global: toggle this service in/out of the set
      if(globalSel.has(i)) globalSel.delete(i); else globalSel.add(i);
      syncTabActive(); rebuildCurrent(); render();
    } else {                           // single-select (original behaviour)
      saveState(); curIdx=i; loadState(i); syncTabActive(); rebuildCurrent(); render();
    }
  };
  tabs.appendChild(b);
});
// Reflect curIdx / the Global selection onto the tab buttons (Global is children[0]).
function syncTabActive(){
  gbtn.classList.toggle('active', globalOn);
  DATA.summary.services.forEach((_,i)=>{
    tabs.children[i+1].classList.toggle('active', globalOn ? globalSel.has(i) : (i===curIdx));
  });
}
// Enter Global: clear all service picks (empty = all shown); pressing a service then
// narrows to the picked set. Leave Global: return to the picked service closest to the
// Workspace side (leftmost index), or Workspace if none was picked.
function toggleGlobal(){
  if(!globalOn){ saveState(); globalOn=true; globalSel.clear(); drillStack=[]; }
  else { globalOn=false; curIdx=globalSel.size ? Math.min(...globalSel) : 0; globalSel.clear(); loadState(curIdx); }
  syncTabActive(); rebuildCurrent(); render();
}
// Global search: count items (by name OR value) matching the query within each
// service's full tree, and show "(N)" on every tab. Empty -> plain service names.
function countServiceMatches(disp, ql){
  let n=0;
  (function w(d){
    for(const it of (d.items||[])){
      if(it.n.toLowerCase().indexOf(ql)!==-1 || String(it.v).toLowerCase().indexOf(ql)!==-1) n++;
    }
    for(const c of (d.ch||[])) w(c);
  })(disp);
  return n;
}
function updateGlobalSearch(){
  const ql=document.getElementById('globalsearch').value.trim().toLowerCase();
  DATA.summary.services.forEach((s,i)=>{
    const ct=tabs.children[i+1].querySelector('.ct');   // +1: Global button is children[0]
    if(!ql){ ct.textContent=''; ct.classList.remove('zero'); return; }
    const cnt=countServiceMatches(DATA.services[i], ql);
    ct.textContent='('+cnt+')'; ct.classList.toggle('zero', cnt===0); // red when 0
  });
}
(function(){
  const gs=document.getElementById('globalsearch'); let gt=null;
  gs.addEventListener('input',()=>{ clearTimeout(gt); gt=setTimeout(updateGlobalSearch,120); });
})();
// Global Count line (just the count text; numbers in accent blue) + the tree
// action / marker-filter buttons on their own row (#treebtns) below the tabs.
(function buildSubBar(){
  const num=v=>'<span class="num">'+v+'</span>';
  document.getElementById('sub').innerHTML=
    'Global Count: '+num(DATA.summary.total_instances)+' instances with '+DATA.summary.item_label+', '+
    num(DATA.summary.total_items)+' '+DATA.summary.item_label+' total.'+
    (DATA.summary.nc_note ? ' &nbsp; <span style="color:#ff5555"><b>***</b> = stores an Instance value - cannot become an attribute.</span>' : '');
  const grp=document.getElementById('treebtns'); grp.innerHTML='';
  // Expand all / Collapse all (ids reused so the existing handlers below bind here).
  const exp=document.createElement('button'); exp.className='mbtn'; exp.id='expandAll'; exp.textContent='Expand all';
  exp.title='expand every branch and clear drill / isolation / marker filters';
  const col=document.createElement('button'); col.className='mbtn'; col.id='collapseAll'; col.textContent='Collapse all';
  col.title='collapse every branch';
  grp.appendChild(exp); grp.appendChild(col);
  if(CFG.markers){ // only kinds with * / ** markers get the filter toggles + key
    const dlab=KIND==='value' ? 'Destroyable' : 'Nil-able';
    const hasRT=!!DATA.summary.runtime;  // was runtime/src scanned?
    const noRtTip="For run-time attributes, use the 'Include Runtime' toggle in the Roblox Studio plugin menu. Follow setup directions.";
    const mk=(mark,label,cls,tip)=>{
      const b=document.createElement('button'); b.className='mbtn '+cls; b.dataset.mark=mark;
      b.innerHTML=label+' <span class="mk">'+mark+'</span>';  // marker shown in its key color
      if(!hasRT){ b.classList.add('disabled'); b.title=noRtTip; } // no runtime -> not clickable
      else { b.title=tip; b.onclick=()=>toggleMarker(mark); }
      grp.appendChild(b);
    };
    mk('*', 'Set in code', 'star', 'set in code - show only * items');
    if(KIND==='attribute'){ // Read in code (GetAttribute): blue *, asterisk-first
      const rb=document.createElement('button'); rb.className='mbtn read'; rb.dataset.mark='r';
      rb.innerHTML='<span class="mk">*</span> Read in code';
      if(!hasRT){ rb.classList.add('disabled'); rb.title=noRtTip; }
      else { rb.title='read in code (GetAttribute) - show only read items'; rb.onclick=()=>toggleMarker('r'); }
      grp.appendChild(rb);
    }
    if(CFG.dstarBtn) mk('**', dlab, 'dstar', dlab.toLowerCase()+' - show only ** items'); // attr pages skip nil-able
    if(CFG.ncBtn){ // Instance Value (***) - data-derived, so NOT gated by runtime
      const b=document.createElement('button'); b.className='mbtn ncm'; b.dataset.mark='***';
      b.innerHTML='Instance Value <span class="mk">***</span>';
      b.title='stores an Instance ref - show only *** values';
      b.onclick=()=>toggleMarker('***');
      grp.appendChild(b);
    }
  }
  if(KIND==='collision'){ // per-collision-property filter toggles (above the search)
    ['CanCollide','CanTouch','CanQuery','AudioCanCollide'].forEach(prop=>{
      const b=document.createElement('button'); b.className='mbtn prop'; b.dataset.prop=prop; b.textContent=prop;
      b.title='filter by '+prop+': off -> True -> False';
      b.onclick=()=>{ const c=propFilter.get(prop);            // off -> True -> False -> off
        if(c===undefined) propFilter.set(prop,'true');
        else if(c==='true') propFilter.set(prop,'false');
        else propFilter.delete(prop);
        syncPropButtons(); render(); };
      grp.appendChild(b);
    });
    // CollisionFidelity cycles through the enum values (off -> Box -> Default -> ...)
    const fb=document.createElement('button'); fb.className='mbtn prop fid'; fb.id='fidBtn'; fb.textContent='CollisionFidelity';
    fb.title='cycle the CollisionFidelity enum to filter by';
    fb.onclick=()=>{ fidFilter=FID_CYCLE[(FID_CYCLE.indexOf(fidFilter)+1)%FID_CYCLE.length]; syncPropButtons(); render(); };
    grp.appendChild(fb);
  }
})();

const svg=document.getElementById('svg'), tip=document.getElementById('tip');
let qRaw='';                            // search box text EXACTLY as typed (keeps case)
let q='';                              // qRaw trimmed + lowercased, used for matching only
let hiddenTypes=new Set();              // instance classes toggled off via the legend
let hiddenCreators=new Set();           // ownership: creators toggled off via the creator row
let markerFilter=new Set();             // '*' / '**' marker toggles (empty = show all)
let propFilter=new Map();               // collision: prop -> 'true' | 'false' (per-part)
let fidFilter=null;                     // collision: a CollisionFidelity enum, or null
let ignoreSet=new Set();                // names (item OR host) to ignore everywhere
function ignored(name){ return ignoreSet.size>0 && ignoreSet.has(String(name).toLowerCase()); }
const FID_CYCLE=[null,'Box','Default','Hull','PreciseConvexDecomposition']; // cycle order
let minAttrs=1;                         // slider: show instances with >= N attributes
let hideSiblings=false;                 // Hide Siblings: while searching, show only matching items per host
let isoNode=null;                       // double-clicked node: isolate its branch
let drillStack=[];                      // Layer Mapper: 2nd-layer keys drilled into
let attrLockUntil=0;                     // click-to-lock: freeze the panels until this time
let lastTotalItems=0, lastShownItems=0; // for the "hidden" counter (current service)
function attrLocked(){ return performance.now() < attrLockUntil; }

// Per-service state, so switching tabs restores where you left a service (search
// text, hidden types, the slider, drill). Isolation is NOT persisted: it points at
// live nodes that a rebuild replaces. Expansion is kept per-tree on the nodes.
const svcState = DATA.services.map(()=>({qRaw:'', hidden:[], min:1, drill:[], marks:[], props:[], fid:null}));
function saveState(){ svcState[curIdx]={qRaw:qRaw, hidden:[...hiddenTypes], min:minAttrs, drill:[...drillStack], marks:[...markerFilter], props:[...propFilter], fid:fidFilter}; }
function loadState(i){
  const st=svcState[i]||{qRaw:'', hidden:[], min:1, drill:[], marks:[], props:[], fid:null};
  qRaw=st.qRaw||''; q=qRaw.trim().toLowerCase(); // restore the box verbatim; match case-insensitively
  hiddenTypes=new Set(st.hidden); minAttrs=st.min; isoNode=null; drillStack=(st.drill||[]).slice();
  markerFilter=new Set(st.marks||[]); syncMarkerButtons();
  propFilter=new Map(st.props||[]); fidFilter=st.fid||null; syncPropButtons();
  const sb=document.getElementById('search'); if(sb) sb.value=qRaw;
  const sl=document.getElementById('minattrs'); if(sl) sl.value=minAttrs;
  const ml=document.getElementById('minlbl'); if(ml) ml.textContent=String(minAttrs)+'+';
}
// reflect markerFilter onto the toggle buttons' active state
function syncMarkerButtons(){
  document.querySelectorAll('#treebtns .mbtn[data-mark]').forEach(b=>b.classList.toggle('on', markerFilter.has(b.dataset.mark)));
}
function toggleMarker(mark){
  const was=markerFilter.has(mark);
  markerFilter.clear();          // Set in code / Nil-able are mutually exclusive
  if(!was) markerFilter.add(mark);
  syncMarkerButtons(); render();
}
// Collision property filters are PER-PART: a part must satisfy every active boolean
// constraint AND the (optional) CollisionFidelity enum. A part's boolean value is
// inferred - the dump only records the non-default (false) ones, so a part is 'false'
// for a prop when it has that item, else 'true' (the default).
function collisionActive(){ return propFilter.size>0 || !!fidFilter; }
function collisionPartOk(n){
  if(!collisionActive()) return true;
  for(const [prop, want] of propFilter){
    const isFalse = n._children.some(c=>c.kind==='item' && c.it.n===prop);
    if((isFalse ? 'false' : 'true') !== want) return false;
  }
  if(fidFilter){
    const ok = n._children.some(c=>c.kind==='item' && c.it.n==='CollisionFidelity' && String(c.it.v).split('.').pop()===fidFilter);
    if(!ok) return false;
  }
  return true;
}
// Each boolean button cycles: off (grey) -> True (blue) -> False (yellow) -> off.
function syncPropButtons(){
  document.querySelectorAll('#treebtns .mbtn.prop[data-prop]').forEach(b=>{
    const v=propFilter.get(b.dataset.prop);
    b.classList.toggle('on-true', v==='true');
    b.classList.toggle('on-false', v==='false');
    b.textContent = b.dataset.prop + (v ? (' '+(v==='true'?'True':'False')) : '');
  });
  const fb=document.getElementById('fidBtn');
  if(fb){ fb.classList.toggle('on', !!fidFilter); fb.textContent = fidFilter ? ('CollisionFidelity: '+fidFilter) : 'CollisionFidelity'; }
}
// path helpers for the Layer Mapper (works off each node's full, real path)
function nodeParts(n){ return String((n.kind==='item')?n._p.path:n.path).split('.'); }
function inDrillScope(n){
  if(!drillStack.length) return true;
  const parts=nodeParts(n);
  for(let i=0;i<drillStack.length;i++){ if(parts[1+i]!==drillStack[i]) return false; }
  return true;
}

// Set _show on every node from the active filters: search text, hidden types,
// the ">= N attributes" slider, and (if set) branch isolation. Also tally how
// many of the current service's items pass, for the hidden counter.
function computeVisibility(){
  lastTotalItems=0; lastShownItems=0;
  const filterMarks = markerFilter.size>0;            // marker toggles active?
  const filterCreators = hiddenCreators.size>0;       // ownership: any creator hidden?
  // '***' (Instance Value) filters by the nc flag; '*'/'**' filter by the m marker.
  const keepMarker = it => !filterMarks || (markerFilter.has('***') ? !!it.nc : markerFilter.has(it.m));
  const inSub=new Set(), anc=new Set();
  if(isoNode){
    (function mark(n){ inSub.add(n); n._children.forEach(mark); })(isoNode);
    for(let p=isoNode._p;p;p=p._p) anc.add(p);
  }
  function rec(n, ancIgnOk, isRoot){
    // The ignore list threads down (an ignored host hides its whole subtree). The legend
    // TYPE filter is per-node: hiding a type hides ITS own attributes, but the node still
    // acts as a container for visible descendants of other types - so isolating "Script"
    // hides a service's direct attributes yet still shows the scripts beneath it.
    const ignOk = isRoot ? true : (ancIgnOk && !ignored(n.n));
    const ownTypeOk = isRoot ? true : !hiddenTypes.has(n.c);
    const dscope = isRoot ? true : inDrillScope(n); // Layer Mapper: only the drilled branch
    const itemKeep=it => keepMarker(it) && !ignored(it.n) && !hiddenCreators.has(it.cr); // markers + ignore + creator filter
    let directCount=0, anyItemMatch=false, anyMarkerItem=false, subtreeTarget=false;
    for(const c of n._children){
      if(c.kind==='item'){
        lastTotalItems++; directCount++;
        c._matchQ = !q || c.n.toLowerCase().indexOf(q)!==-1 || String(c.it.v).toLowerCase().indexOf(q)!==-1;
        if(c._matchQ) anyItemMatch=true;
        if(itemKeep(c.it)) anyMarkerItem=true;
      } else if(rec(c, ignOk, false)) subtreeTarget=true;
    }
    const nameMatch = !q || n.n.toLowerCase().indexOf(q)!==-1;
    const countOk = directCount >= minAttrs;
    const markerQ = (!filterMarks && !filterCreators) || anyMarkerItem; // >=1 item past the marker/creator filters
    // collision filter is PER-PART (only on nodes that carry collision items)
    const partOk = (KIND!=='collision' || isRoot || directCount===0) ? true : collisionPartOk(n);
    let show, showItems, target;
    if(isoNode){
      // isolation: the isolated branch is shown in full, plus the ancestor path
      if(inSub.has(n)){ show=true; showItems=true; target=true; }
      else if(anc.has(n) || isRoot){ show=true; showItems=false; target=subtreeTarget; }
      else { show=false; showItems=false; target=false; }
    } else {
      target = dscope && ignOk && ownTypeOk && countOk && markerQ && partOk && (!q || nameMatch || anyItemMatch);
      show = isRoot ? true : (dscope && ignOk && (target || subtreeTarget));
      // root's own attributes belong to the service itself - hide them once drilled
      showItems = isRoot ? (drillStack.length===0 && countOk && markerQ && (!q || nameMatch || anyItemMatch)) : target;
    }
    if(!isRoot && !dscope){ show=false; showItems=false; target=false; } // gate iso path too
    n._show = show;
    // items: blanket per shown instance, each one still gated by the marker filter
    for(const c of n._children){ if(c.kind==='item'){ const vis=showItems && itemKeep(c.it) && (!hideSiblings || !q || c._matchQ); c._show=vis; if(vis) lastShownItems++; } }
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
    if(n.kind==='inst' && n._group){
      // synthetic layer-group middleman: a square glyph + a carrier count, no class
      const hasKids=n._children.filter(c=>c._show).length, filled=hasKids&&!n._expanded;
      const match=q&&n.n.toLowerCase().indexOf(q)!==-1;
      s+='<g class="node grp'+(match?' match':'')+'" data-i="'+n._idx+'" transform="translate('+n._x+','+n._y+')">';
      s+='<rect x="'+(-NODER)+'" y="'+(-NODER)+'" width="'+(2*NODER)+'" height="'+(2*NODER)+'" rx="1" fill="'+(filled?'#3a4150':'#0f1117')+'" stroke="#6b7587"/>';
      s+='<text x="'+(NODER+6)+'" y="3.5"><tspan class="nm gnm">'+esc(n.n)+'</tspan>'+
         '<tspan class="cl" dx="6">('+n._carriers+')</tspan></text>';
      s+='</g>';
    } else if(n.kind==='inst'){
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
      s+='<rect x="-3" y="-1.5" width="3" height="3" fill="'+(it.m==='**'?'var(--dstar)':it.m==='r'?'#7aa2f7':it.m==='*'?'var(--purple)':'#5f6b80')+'"/>';
      // Inline <tspan>s so the (type) always sits at the end of the value extent.
      s+='<text x="8" y="3.5">';
      s+='<tspan class="inm">'+esc(it.n)+'</tspan>';
      if(it.c){ s+='<tspan class="icls" dx="6">['+esc(it.c)+']</tspan>'; }
      if(it.m){ const mc=it.m==='**'?'d':it.m==='r'?'r':'s'; s+='<tspan class="mk '+mc+'" dx="6">'+(it.m==='r'?'*':it.m)+'</tspan>'; }
      if(it.code){ /* code-site row: the colour-coded * (purple=set, blue=read) says it - no text */ }
      else {
        s+='<tspan class="itype" dx="6">=</tspan>';
        s+='<tspan class="ival" dx="6">'+esc(trunc(it.v))+'</tspan>';
        s+='<tspan class="itype" dx="6">('+esc(it.t)+')</tspan>';
      }
      if(it.nc){ s+='<tspan class="ncmk" dx="6">***</tspan>'; }
      s+='</text>';
      s+='</g>';
    }
  }
  svg.innerHTML=s;
  if(globalOn){
    const idxs=globalSel.size ? [...globalSel].sort((a,b)=>a-b) : DATA.summary.services.map((_,i)=>i);
    let ic=0,it=0; idxs.forEach(i=>{ ic+=DATA.summary.services[i].instances; it+=DATA.summary.services[i].items; });
    const who=globalSel.size ? idxs.map(i=>DATA.summary.services[i].name).join(', ') : 'all services';
    document.getElementById('svccount').textContent='Global ('+who+'): '+ic+' instances, '+it+' '+DATA.summary.item_label;
  } else {
    const svc=DATA.summary.services[curIdx];
    document.getElementById('svccount').textContent=
      current.n+' Count: '+svc.instances+' instances, '+svc.items+' '+DATA.summary.item_label;
  }
  document.getElementById('counter').innerHTML = '<span style="color:var(--accent);font-weight:600">'+nodes.length+'</span> rows shown';
  const hidden=lastTotalItems-lastShownItems;
  const reasons=[];
  if(drillStack.length) reasons.push('Layer Mapper');
  if(q) reasons.push('search');
  if(hideSiblings && q) reasons.push('hide siblings');
  if(markerFilter.size) reasons.push('marker filter');
  if(propFilter.size || fidFilter) reasons.push('collision filter');
  if(ignoreSet.size) reasons.push('ignore list');
  if(hiddenTypes.size) reasons.push('hidden types');
  if(minAttrs>1) reasons.push('>= '+minAttrs+' '+DATA.summary.item_label);
  if(isoNode) reasons.push('isolation');
  // colour only the "X of Y" numbers: green = none hidden, yellow = some hidden,
  // red = all hidden (e.g. a search with no matches). The rest keeps its accent colour.
  const numColor = hidden<=0 ? '#5fd37a' : (hidden>=lastTotalItems ? '#ff6b6b' : '#e7c45a');
  document.getElementById('hiddencount').innerHTML =
    '<span style="color:'+numColor+';font-weight:700">'+hidden+' of '+lastTotalItems+'</span> '+
    DATA.summary.item_label+' hidden in '+esc(current.n)+
    (hidden>0 ? ' by: '+esc(reasons.length?reasons.join(', '):'filters')+'.' : '');
  buildLegend();
  buildCreators();
  buildMapper(nodes);
  if(CFG.tabs.includes('spacing')) renderToolbar();   // keep the scope-based Instance Spacing card live
}

// Ownership: a second filter row under the type legend - one chip per creator present
// in the CURRENT view (so it reflects whatever service / Global selection is showing).
// Single-click hides that creator's assets; double-click shows ONLY that creator.
let creatorColors={}, creatorPi=0;
function creatorColor(k){ if(!(k in creatorColors)) creatorColors[k]=PALETTE[creatorPi++%PALETTE.length]; return creatorColors[k]; }
function buildCreators(){
  const row=document.getElementById('creators'); if(!row) return;
  if(!CFG.creators){ row.style.display='none'; return; }
  const present={};
  (function w(n){ for(const c of n._children){ if(c.kind==='item'){ if(c.it.cr) present[c.it.cr]=c.it.ct||''; } else w(c); } })(current);
  const keys=Object.keys(present).sort();
  row.innerHTML=''; if(!keys.length){ row.style.display='none'; return; } row.style.display='flex';
  const lab=document.createElement('span'); lab.className='crlab'; lab.textContent='creators:'; row.appendChild(lab);
  keys.forEach(k=>{
    const typ=present[k], nm=k.slice(k.indexOf(':')+1);
    const sp=document.createElement('span');
    if(hiddenCreators.has(k)) sp.className='off';
    sp.title='click to '+(hiddenCreators.has(k)?'show':'hide')+' '+typ+' "'+nm+'" · double-click to show only this creator';
    sp.innerHTML='<span class="dot" style="background:'+creatorColor(k)+'"></span>'+esc(nm)+'<span class="crtag">'+esc(typ)+'</span>';
    let lc=0, timer=null;
    sp.onclick=()=>{
      const now=performance.now();
      if(timer && now-lc<200){ clearTimeout(timer); timer=null;           // double-click: only this creator
        hiddenCreators.clear(); keys.forEach(x=>{ if(x!==k) hiddenCreators.add(x); }); render(); return; }
      lc=now; if(timer) clearTimeout(timer);
      timer=setTimeout(()=>{ timer=null;                                   // single-click: toggle this creator
        if(hiddenCreators.has(k)) hiddenCreators.delete(k); else hiddenCreators.add(k);
        if(keys.every(x=>hiddenCreators.has(x))) hiddenCreators.clear();   // all hidden -> re-enable all
        render();
      }, 210);
    };
    row.appendChild(sp);
  });
}
function buildLegend(){
  const present={};
  current._children.forEach(function w(n){ if(n.kind==='inst'){ if(!n._group) present[n.c]=true; n._children.forEach(w);} });
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

// ---- right-side section rail: jump to a REAL Studio 2nd-layer node (a direct
// child of the service - the folders/models the dev organized). The tree is
// path-compressed, so we derive the 2nd-layer name from each node's full path
// (e.g. "Workspace.Backrooms.Build.ArtPainting1" -> "Backrooms") and group by it.
let mapSections=[];
let activeSectionKey=null;   // the Layer Mapper's current "active" section - Instance Spacing roots here
const INDENT=22;  // reverse-tab px per drilled level (deeper = more toward center)
const TOPPAD=24;  // px below the viewport top where a section's first row counts as "current"
// The group key at the CURRENT drill depth: e.g. base groups by the 2nd-layer
// (path[1]); drilled into one, it groups by the 3rd layer (path[2]).
function groupKeyOf(n){
  const parts=nodeParts(n);
  if(globalOn) return parts[0];          // Global: bucket the section rail by service
  const idx=1+drillStack.length;
  return parts.length<=idx ? '__ATTRS__' : parts[idx];
}
function attrsLabel(){
  // the __ATTRS__ group = items sitting on the scope root. At base level that root
  // is the service, so label it with the service name; when drilled, the branch.
  return drillStack.length ? '('+drillStack[drillStack.length-1]+' attributes)' : current.n;
}
function buildMapper(nodes){
  const order=[], map=new Map();
  for(const nd of nodes){
    if(nd===current || nd._group) continue; // rail buckets real carriers/items only
    const key=groupKeyOf(nd);
    let g=map.get(key);
    if(!g){ g={key, label:(key==='__ATTRS__'?attrsLabel():key), s:nd._y, e:nd._y, depth:drillStack.length};
      map.set(key,g); order.push(g); }
    else { g.s=Math.min(g.s,nd._y); g.e=Math.max(g.e,nd._y); }
  }
  const m=document.getElementById('mapper'); m.innerHTML='';
  // breadcrumbs: the drilled path, pinned at the top, each indented by its depth
  drillStack.forEach((key,depth)=>{
    const el=document.createElement('div'); el.className='m-entry m-crumb';
    el.title='double-click to exit '+key; el.style.marginRight=(depth*INDENT)+'px';
    const pill=document.createElement('span'); pill.className='pill'; pill.textContent='▸ '+key;
    el.appendChild(pill); bindRailClick(el,{kind:'crumb', key, depth});
    m.appendChild(el);
  });
  // current-level groups (indented one level past the deepest breadcrumb)
  order.forEach(sec=>{
    const el=document.createElement('div'); el.className='m-entry'; el.title=sec.label;
    el.style.marginRight=(sec.depth*INDENT)+'px';
    const pill=document.createElement('span'); pill.className='pill'; pill.textContent=sec.label;
    el.appendChild(pill); bindRailClick(el,{kind:'group', sec});
    sec.entry=el; m.appendChild(el);
  });
  mapSections=order; if(!order.length) activeSectionKey=null;
  const wrap=document.getElementById('wrap');
  m.style.top=wrap.getBoundingClientRect().top+'px';
  m.style.height=wrap.clientHeight+'px';
  updateMapper();
}
// single-click = jump to that section; double-click on a 2nd-layer entry drills
// into it (locks the tree + reveals its 3rd layer), double-click a breadcrumb pops.
function bindRailClick(el, info){
  let lc=0, timer=null;
  el.onclick=()=>{
    const now=performance.now();
    if(timer && now-lc<250){ clearTimeout(timer); timer=null; railDouble(info); return; }
    lc=now; if(timer) clearTimeout(timer);
    timer=setTimeout(()=>{ timer=null; railSingle(info); }, 250);
  };
}
function railSingle(info){
  if(info.kind==='group') gotoSection(info.sec);
  else { document.getElementById('wrap').scrollTop=0; updateMapper(); } // crumb -> top of scope
}
function railDouble(info){
  if(info.kind==='crumb'){
    drillStack=drillStack.slice(0, info.depth); // pop back out to before this crumb
    onDrillChange();
  } else if(!globalOn && drillStack.length===0 && info.sec.key!=='__ATTRS__'){ // only 2nd -> 3rd; no drill in Global
    drillStack.push(info.sec.key);
    onDrillChange();
  }
}
function onDrillChange(){
  rebuildCurrent(); // group structure depends on the drill - rebuild before drawing
  render();
  requestAnimationFrame(()=>{
    document.getElementById('wrap').scrollTop=0;
    document.getElementById('mapper').scrollTop=0;
    updateMapper();
  });
}
// Resize entries by scroll position: top-line section = 32, partly visible = 26,
// off-screen = 24.
function updateMapper(){
  const wrap=document.getElementById('wrap'); if(!wrap||!mapSections.length) return;
  const vt=wrap.scrollTop, vb=vt+wrap.clientHeight;
  // "current" = the last section whose first row has reached the TOPPAD line (a
  // few px below the viewport top). gotoSection parks a clicked section's first
  // row exactly on that line, so the section you clicked is the one that lights up.
  let cur=mapSections[0];
  for(const sec of mapSections){ if(sec.s<=vt+TOPPAD+1) cur=sec; }
  const nk = cur ? cur.key : null;       // Instance Spacing follows the active (deepest-selected) section
  if(nk!==activeSectionKey){ activeSectionKey=nk; if(CFG.tabs.includes('spacing')) renderToolbar(); }
  for(const sec of mapSections){
    let size=24;
    if(sec===cur) size=32;
    else if(sec.e>vt && sec.s<vb) size=26;
    sec.entry.style.fontSize=size+'px';
    sec.entry.classList.toggle('active', sec===cur);
  }
}
// Click a rail entry: collapse every first-layer branch NOT in this 2nd-layer
// group, expand those that are, and scroll so the group's first row is the top.
function gotoSection(sec){
  if(drillStack.length===0){ // at base level, collapse the other 2nd-layer branches
    current._children.forEach(c=>{
      if(c.kind!=='inst') return;
      c._expanded = (groupKeyOf(c)===sec.key);
    });
    render();
  }
  requestAnimationFrame(()=>{
    const ns=mapSections.find(x=>x.key===sec.key);
    const wrap=document.getElementById('wrap');
    // park the clicked section's first row TOPPAD px below the top - clear of the
    // edge, and on the exact line updateMapper() uses to pick the "current" section
    wrap.scrollTop=Math.max(0, ((ns&&ns.s!=null)?ns.s:0)-TOPPAD);
    updateMapper();
    // scroll the rail so the clicked entry is at the top, hiding the ones above
    if(ns && ns.entry){ document.getElementById('mapper').scrollTop=Math.max(0, ns.entry.offsetTop-8); }
  });
}

// index nodes for hit-testing
function indexNodes(){
  let i=0; current._all=[];
  (function w(n){ n._idx=i++; current._all.push(n); n._children.forEach(w); })(current);
}
// Single click is held 200ms so a quick double-click wins instead. Double-click:
// an instance isolates its branch; an attribute copies its host path.
let nodeTimer=null, nodeLastN=null, nodeLastT=0, preIsoScroll=0;
svg.addEventListener('click',e=>{
  const g=e.target.closest('.node,.item'); if(!g) return;
  const n=current._all[+g.dataset.i];
  if(!n) return;
  // Clicking an attribute LOCKS it into the panels for 3s, so the cursor can travel
  // over other rows on its way to the Attribute Finder / toolbar without changing it.
  if(n.kind==='item') lockAttr(n); // all kinds have a finder/toolbar to lock
  const now=performance.now();
  if(nodeTimer && nodeLastN===n && now-nodeLastT<200){ // double-click
    clearTimeout(nodeTimer); nodeTimer=null;
    if(n.kind==='inst'){
      const wrap=document.getElementById('wrap');
      if(isoNode===n){ // de-isolate: go back to where the user was before isolating
        isoNode=null; render();
        requestAnimationFrame(()=>{ wrap.scrollTop=preIsoScroll||0; updateMapper(); });
      } else { // isolate: remember the spot, then show the branch from the top
        preIsoScroll=wrap.scrollTop; isoNode=n; render();
        requestAnimationFrame(()=>{ wrap.scrollTop=0; updateMapper(); });
      }
    } else { copyNode(n); }
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
  if(n.kind==='inst' && n._group){
    tip.innerHTML='<b>'+esc(n.path)+'</b> &middot; layer group &middot; '+n._carriers+' instances'+
      '<br/><span style="color:var(--type)">'+CB+'+C to copy path · double-click a Layer Mapper entry to drill in</span>';
  } else if(n.kind==='inst'){
    tip.innerHTML='<b>'+esc(n.path)+'</b> ['+esc(n.c)+'] &middot; '+
      n._children.filter(c=>c.kind==='item').length+' items, '+
      n._children.filter(c=>c.kind==='inst').length+' child instances'+
      '<br/><span style="color:var(--type)">'+CB+'+C to copy path · double-click to '+
      (isoNode===n?'de-isolate':'isolate')+'</span>';
  } else {
    let t='<b>'+esc(n.it.n)+'</b> = '+esc(n.it.v)+' ('+esc(n.it.t)+')'+(n.it.m?'  '+n.it.m:'');
    if(attrLocked()){
      t+='<br/><span style="color:var(--type)">panels locked - move to them to copy</span>';
    } else {
      showFinder(n.it.n, n._p.path);     // bottom-left finder (host, or script+host)
      setToolbarTarget(n.it.n);          // bottom-right toolbar (no-op when CFG.tabs is empty)
      t+='<br/><span style="color:var(--type)">click to lock '+CFG.finderTitle+' panel for 3 seconds</span>';
    }
    tip.innerHTML=t;
  }
  tip.style.display='block';
  let x=e.clientX+14,y=e.clientY+14; const r=tip.getBoundingClientRect();
  if(x+r.width>innerWidth) x=e.clientX-r.width-14;
  if(y+r.height>innerHeight) y=e.clientY-r.height-14;
  tip.style.left=x+'px'; tip.style.top=y+'px';
});
svg.addEventListener('mouseleave',()=>{ tip.style.display='none'; hoverNode=null; });

// Expand all also pops out of any drilled layer, back to the highest (base) level
// the current service is built on - and the Layer Mapper reflects it (no breadcrumbs).
// Expand all = the old "Reset" too: clears drill / isolation / marker filters and
// expands every branch from the base layer (the text search + slider are left alone).
document.getElementById('expandAll').onclick=()=>{
  isoNode=null; drillStack=[]; markerFilter.clear(); syncMarkerButtons();
  rebuildCurrent(); setAll(true); render();
  requestAnimationFrame(()=>{
    document.getElementById('wrap').scrollTop=0;
    document.getElementById('mapper').scrollTop=0; updateMapper();
  });
};
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
function flashToast(msg, ms){ toast.textContent=msg; toast.style.display='block';
  clearTimeout(toastT); toastT=setTimeout(()=>{ toast.style.display='none'; }, ms||1600); }
function flashCopied(p){ flashToast('Copied: '+p); }
function copyNode(n){ const p=pathFor(n); if(copyText(p)) flashCopied(p); }
// Lock the hovered item into the panels (finder + toolbar) for 3s and point them
// at it now, so hovers in transit don't steal the target.
function lockAttr(n){
  attrLockUntil=performance.now()+3000;
  showFinder(n.it.n, n._p.path); setToolbarTarget(n.it.n);
  flashToast('Locked "'+n.it.n+'" for 3s - move to the panels to copy', 3000);
}

// Bottom-left finder: click-to-copy snippets for the hovered item. CFG.finder
// decides the columns - 'both' shows the script-search token plus the host
// hierarchy (attributes), 'host' shows only the host hierarchy (values / collision,
// where there's no attribute name to script-search).
const attrHelper=document.getElementById('attrhelper');
function showFinder(name, host){
  attrHelper.innerHTML='';
  const title=document.createElement('div'); title.className='ah-name'; title.textContent=CFG.finderTitle+': '+name;
  const row=document.createElement('div'); row.className='ah-row';
  const cell=(text,caption,tip)=>{
    const col=document.createElement('div'); col.className='ah-cell';
    const c=document.createElement('code'); c.textContent=text; c.title=tip;
    c.onclick=()=>{ if(copyText(text)) flashCopied(text); };
    const cap=document.createElement('div'); cap.className='ah-cap'; cap.textContent=caption;
    col.appendChild(c); col.appendChild(cap); row.appendChild(col);
  };
  if(CFG.finder==='both'){
    cell('Attribute("'+name+'")', 'Paste into "Find in Place"', 'script search - matches Get & SetAttribute');
  } else if(CFG.finder==='value'){
    // Values have no Get/Set prefix, and code may reach them via FindFirstChild,
    // WaitForChild, or dot access - so offer the tokens that catch each.
    cell('Child("'+name+'")', 'Find in code: FindFirst/WaitFor', 'matches :FindFirstChild("'+name+'") and :WaitForChild("'+name+'")');
    cell('.'+name, 'Find in code: dot access', 'matches direct .'+name+' access');
    cell('Attribute("'+name+'")', 'After converting: Get/SetAttribute', 'once converted, code reads/writes it via Get & SetAttribute("'+name+'")');
  }
  cell(host, 'Paste into "Explorer"', 'copy the host hierarchy to find the instance(s)');
  attrHelper.appendChild(title); attrHelper.appendChild(row);
  attrHelper.style.display='block';
}

// The highest directory the Layer Mapper is currently showing: the service when at
// the base level, or the drilled branch (e.g. Workspace.Lobby) when drilled in.
function scopeRootPath(){
  if(globalOn) return 'game';                         // whole DataModel in Global mode
  let p=current.path;                                 // service path (e.g. "Workspace")
  if(drillStack.length) p+='.'+drillStack.join('.');  // + the drilled branch
  return p;
}
// Append Luau child accessors for `segs` onto `expr`: dotted when the name is a
// plain identifier, bracket-indexed otherwise (handles spaces / punctuation).
function appendSegs(expr, segs){
  for(const seg of segs){
    expr+=/^[A-Za-z_]\w*$/.test(seg) ? '.'+seg : '["'+String(seg).replace(/"/g,'\\"')+'"]';
  }
  return expr;
}
// A full path -> a safe Luau accessor rooted at the service (game:GetService(...)).
function luauAccessor(path){ const p=path.split('.'); return p[0]==='game' ? appendSegs('game', p.slice(1)) : appendSegs('game:GetService("'+p[0]+'")', p.slice(1)); }
// Reconstruct a captured attribute value as a Luau literal from its dump
// (value-string, type). Returns null for a type we can't safely rebuild, so the
// caller can comment that line out instead of emitting broken code.
function luauValue(it){
  const t=it.t, v=String(it.v);
  switch(t){
    case 'string': case 'number': case 'boolean': return v; // already a Luau literal
    case 'EnumItem': return v;                               // Enum.X.Y
    case 'Vector3': return 'Vector3.new('+v+')';
    case 'Vector2': return 'Vector2.new('+v+')';
    case 'Color3':  return 'Color3.new('+v+')';
    case 'CFrame':  return 'CFrame.new('+v+')';
    case 'UDim':    return 'UDim.new('+v+')';
    case 'UDim2':   return 'UDim2.new('+v+')';
    case 'Rect':    return 'Rect.new('+v+')';
    case 'NumberRange': return 'NumberRange.new('+v.trim().split(/\s+/).join(', ')+')';
    case 'BrickColor':  return 'BrickColor.new("'+v.replace(/"/g,'\\"')+'")';
    default: return null;
  }
}
// Every item-node named `name` whose host instance lives within `scope`.
function hostsForAttr(name, scope){
  const pre=scope+'.', out=[];
  (function w(n){
    if(n.kind==='item'){ if(n.n===name){ const p=n._p.path; if(p===scope||p.indexOf(pre)===0) out.push(n); } return; }
    n._children.forEach(w);
  })(current);
  return out;
}

// ---- the three Command Bar snippets (one per toolbar tab) ----
function deleteCode(name, scope){
  return 'local root = '+luauAccessor(scope)+'\n'+
    'for _, inst in ipairs(root:GetDescendants()) do\n'+
    '\tinst:SetAttribute("'+name+'", nil)\n'+
    'end\n'+
    'root:SetAttribute("'+name+'", nil)';
}
// Restore each host to the EXACT value it had when this page was generated, by
// explicit per-instance statements (so it only re-applies to the original hosts,
// never adds the attribute to instances that never had it).
function fortifyCode(name, scope, hosts){
  const scopeParts=scope.split('.');
  const lines=['local root = '+luauAccessor(scope),
    '-- restore "'+name+'" to its captured state on '+hosts.length+' instance(s)'];
  for(const h of hosts){
    const rel=h._p.path.split('.').slice(scopeParts.length);
    const tgt=rel.length ? appendSegs('root', rel) : 'root';
    const lit=luauValue(h.it);
    if(lit===null) lines.push('-- '+tgt+':SetAttribute("'+name+'", ?) -- unsupported type: '+h.it.t);
    else lines.push(tgt+':SetAttribute("'+name+'", '+lit+')');
  }
  return lines.join('\n');
}
// Print every live instance hosting the item (name + current value) to the
// Output, plus a total - a quick inventory / verification workflow. Attributes
// look up GetAttribute; values look up a child ValueBase of that name.
function farmerCode(name, scope){
  const head='local root = '+luauAccessor(scope)+'\nlocal hits = {}\n';
  if(KIND==='value'){
    return head+
      'local function check(inst)\n'+
      '\tlocal v = inst:FindFirstChild("'+name+'")\n'+
      '\tif v and v:IsA("ValueBase") then\n'+
      '\t\ttable.insert(hits, v)\n'+
      '\t\tprint(v:GetFullName(), "=", v.Value)\n'+
      '\tend\n'+
      'end\n'+
      'check(root)\n'+
      'for _, inst in ipairs(root:GetDescendants()) do check(inst) end\n'+
      'print(("Found %d Value object(s) named '+name+' under %s"):format(#hits, root:GetFullName()))';
  }
  return head+
    'local function check(inst)\n'+
    '\tif inst:GetAttribute("'+name+'") ~= nil then\n'+
    '\t\ttable.insert(hits, inst)\n'+
    '\t\tprint(inst:GetFullName(), "=", inst:GetAttribute("'+name+'"))\n'+
    '\tend\n'+
    'end\n'+
    'check(root)\n'+
    'for _, inst in ipairs(root:GetDescendants()) do check(inst) end\n'+
    'print(("Found %d instance(s) hosting '+name+' under %s"):format(#hits, root:GetFullName()))';
}
// For each ValueBase named `name` under scope: copy its .Value onto its parent as
// an attribute of the same name, then Destroy the Value object. (Value* -> attribute.)
function convertCode(name, scope){
  return 'local root = '+luauAccessor(scope)+'\n'+
    'local n = 0\n'+
    'local function convert(inst)\n'+
    '\tlocal v = inst:FindFirstChild("'+name+'")\n'+
    '\tif v and v:IsA("ValueBase") then\n'+
    '\t\tinst:SetAttribute("'+name+'", v.Value)\n'+
    '\t\tv:Destroy()\n'+
    '\t\tn += 1\n'+
    '\tend\n'+
    'end\n'+
    'convert(root)\n'+
    'for _, inst in ipairs(root:GetDescendants()) do convert(inst) end\n'+
    'print(("Converted %d \''+name+'\' Value object(s) to attributes under %s"):format(n, root:GetFullName()))';
}

// ---- the collapsible bottom-right toolbar (cards listed by CFG.tabs) ----
const toolbar=document.getElementById('toolbar');
let tbAttr=null, tbScope=null;                 // item + scope the cards target
const tbOpen={};                               // per-tab open/closed (key -> bool)
// Point the toolbar at a (possibly new) item. Skips the rebuild - keeping open
// cards and their scroll position - when nothing actually changed.
function setToolbarTarget(name){
  if(!CFG.tabs.length) return;
  const scope=scopeRootPath();
  if(name===tbAttr && scope===tbScope) return;
  tbAttr=name; tbScope=scope; renderToolbar();
}
// Instance Spacing (collision only): rename every descendant so spaces / special chars
// collapse to "_", so the resulting path pastes into the Explorer search (which breaks
// on spaces and treats "." as a hierarchy separator).
// Instance Spacing roots at the deepest level selected in the Layer Mapper: the service
// + any drilled branch (scopeRootPath) + the currently-active section the user scrolled to.
function spacingScope(){
  let p=scopeRootPath();
  if(activeSectionKey && activeSectionKey!=='__ATTRS__') p+='.'+activeSectionKey;
  return p;
}
function spacingCode(scope){
  return 'local root = '+luauAccessor(scope)+'\n'+
    'local function clean(nm)\n'+
    '\tlocal s = (string.gsub(nm, "[^%w_]", "_"))  -- each space / special char -> "_"\n'+
    '\tif s == "" then s = "_" end\n'+
    '\treturn s\n'+
    'end\n'+
    'local renamed = 0\n'+
    'for _, inst in ipairs(root:GetDescendants()) do\n'+
    '\tlocal nn = clean(inst.Name)\n'+
    '\tif nn ~= inst.Name then inst.Name = nn; renamed += 1 end\n'+
    'end\n'+
    'print("Instance Spacing: renamed "..renamed.." instance(s).")';
}
function renderToolbar(){
  if(!CFG.tabs.length) return;
  const name=tbAttr, scope=tbScope;
  const TABDEFS={
    delete:{cls:'del', label:'Delete Attribute', mk:()=>({
      detail:'Delete "'+name+'" under '+scope, code:deleteCode(name,scope),
      cap:'clears <b>'+esc(name)+'</b> on every descendant of <b>'+esc(scope)+'</b>'})},
    fortify:{cls:'fort', label:'Fortify Attribute', mk:()=>{ const h=hostsForAttr(name,scope);
      return {detail:'Restore "'+name+'" under '+scope+' ('+h.length+')', code:fortifyCode(name,scope,h),
        cap:'re-applies the value each of <b>'+h.length+'</b> instance(s) had when this page was generated - undo an accidental delete'};}},
    farmer:{cls:'farm', label:'Instance Farmer', mk:()=>({
      detail:'List instances hosting "'+name+'" under '+scope, code:farmerCode(name,scope),
      cap:'prints every host + value to the Output, with a total count'})},
    convert:{cls:'conv', label:'Convert Value* to attribute', mk:()=>({
      detail:'Convert "'+name+'" under '+scope+' to attributes', code:convertCode(name,scope),
      cap:'for each <b>'+esc(name)+'</b> Value object: sets a matching attribute on its parent, then Destroys the Value.'+
        '<br><b style="color:#ff9b9b">Code change needed:</b> this snippet only changes the data model - it does NOT edit your scripts. '+
        'Any code that reads or writes this Value (<b>:FindFirstChild("'+esc(name)+'")</b>, <b>:WaitForChild</b>, or <b>.'+esc(name)+'</b>) must be updated to <b>GetAttribute / SetAttribute("'+esc(name)+'")</b>. '+
        'Use the bottom-left '+CFG.finderTitle+' Panel to locate that code first.'})},
    spacing:{cls:'space', label:'Instance Spacing', noTarget:true, mk:()=>{ const sc=spacingScope(); return {
      detail:'Underscore the names under '+sc, code:spacingCode(sc),
      cap:'<b>*underscores will replace special characters and spaces in this command</b> &middot; renames every descendant under <b>'+esc(sc)+'</b> so spaces and characters like <b>- / .</b> become <b>_</b>, making the path copyable / searchable in the Explorer. <b style="color:#ff9b9b">Heads up:</b> this renames instances - code that finds them by their old name (FindFirstChild / WaitForChild) would need updating.'};}}
  };
  toolbar.innerHTML='';
  for(const tab of CFG.tabs){
    const d=TABDEFS[tab]; if(!d) continue;
    const card=document.createElement('div'); card.className='tb-card '+d.cls;
    const head=document.createElement('div'); head.className='tb-head';
    head.innerHTML='<span class="tb-title">'+d.label+'</span><span class="tb-chev">'+(tbOpen[tab]?'▾ close':'▸ open')+'</span>';
    head.onclick=()=>{ tbOpen[tab]=!tbOpen[tab]; renderToolbar(); };
    card.appendChild(head);
    if(tbOpen[tab]){
      const body=document.createElement('div'); body.className='tb-body';
      if(!name && !d.noTarget){ body.innerHTML='<div class="tb-hint">Hover an item to target one.</div>'; }
      else{
        const info=d.mk();
        const det=document.createElement('div'); det.className='tb-detail'; det.textContent=info.detail;
        const pre=document.createElement('pre'); pre.textContent=info.code; pre.title='click to copy';
        pre.onclick=()=>{ if(copyText(info.code)) flashCopied(d.label+' snippet'); };
        const cap=document.createElement('div'); cap.className='tb-cap';
        cap.innerHTML='Paste into the <b>Command Bar</b> &middot; '+info.cap;
        body.appendChild(det); body.appendChild(pre); body.appendChild(cap);
      }
      card.appendChild(body);
    }
    toolbar.appendChild(card);
  }
}
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
// Hide Siblings: collapse the non-matching items on each host while searching, so only
// the searched item remains - the way to lock onto every instance that has it.
const hideSibBtn=document.getElementById('hideSibBtn');
hideSibBtn.onclick=()=>{ hideSiblings=!hideSiblings; hideSibBtn.classList.toggle('on',hideSiblings);
  hideSibBtn.textContent=hideSiblings?'Show Siblings':'Hide Siblings'; render(); };
if(CFG.creators) hideSibBtn.style.display='none';   // ownership: hide-siblings is irrelevant

// section rail: re-size entries as the tree scrolls; reposition on window resize
document.getElementById('wrap').addEventListener('scroll', updateMapper);
window.addEventListener('resize', ()=>{
  const m=document.getElementById('mapper'), w=document.getElementById('wrap');
  if(m && w){ m.style.top=w.getBoundingClientRect().top+'px'; m.style.height=w.clientHeight+'px'; }
  updateMapper();
});

const search=document.getElementById('search'); let t=null;
search.addEventListener('input',()=>{clearTimeout(t);t=setTimeout(doSearch,140);});

// Ignore list: comma-separated names (item OR host). Persists across services / toggles.
(function(){
  const ig=document.getElementById('ignorelist'); let it=null;
  ig.addEventListener('input',()=>{ clearTimeout(it); it=setTimeout(()=>{
    ignoreSet=new Set(ig.value.split(',').map(s=>s.trim().toLowerCase()).filter(Boolean));
    setAll(true); current._expanded=true;
    if(q){ doSearch(); } else { render(); }      // re-apply with the new ignore set
  }, 160); });
})();
function doSearch(){
  qRaw=search.value;                       // keep the user's exact text (and case)
  q=qRaw.trim().toLowerCase();              // match case-insensitively
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
  set('minunit', lab); set('lbl1', lab);
  if(KIND==='attribute'){ const ih=document.getElementById('introhint');
    if(ih) ih.innerHTML='Instances that carry attributes — plus the scripts that set ('+
      '<span style="color:var(--purple);font-weight:700">*</span>) or read ('+
      '<span style="color:#7aa2f7;font-weight:700">*</span>) them — are shown; empty containers are '+
      'path-compressed (hover a node for its real path).'; }
  const mw=document.getElementById('minwrap');
  if(mw){ mw.title='show only instances that have at least this many '+lab;
    if(!CFG.slider) mw.style.display='none'; }            // slider: attributes only
})();

// Show the bottom-right toolbar (collapsed) only for kinds that have tabs.
if(CFG.tabs.length){ toolbar.style.display='flex'; renderToolbar(); }

// re-index whenever the current service changes
const _render=render;
render=function(){ indexNodes(); _render(); };
rebuildCurrent(); // build the first service's grouped tree before the first draw
render();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    main()
