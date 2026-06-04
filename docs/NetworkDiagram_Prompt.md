# Prompt: Generate a per-service network diagram

Copy everything below the line into a new Claude conversation, and attach the
file you choose (see note at the very bottom).

---

I'm attaching a dump of my Roblox game's instance hierarchy. I want you to
generate a **node-link network diagram, one per top-level service**, as a single
self-contained HTML file I can open in a browser.

## Input format
The attached file is an indented ASCII tree. Lines look like one of:

```
Workspace [Workspace]                         <- an instance (container)
  - MapString = "Map1" (string)               <- an ATTRIBUTE on the instance above
  BackRooms [Folder]
    Build [Folder]
      ArtPainting1 [Model]
        - Map1 = true (boolean)
```

or, for a Value-object dump, the item is the instance itself:

```
Canoe [Tool]
  CurrentHealth [IntValue] = 60 (number)       <- a VALUE object (the "item")
  Occupant [ObjectValue] = nil (nil)
```

A line `Name [ClassName]` is an instance; 2 spaces = one nesting level. The
"items" carried by an instance are either its `- Attr = value (type)` lines
(attribute dump) or its child `Name [ValueClass] = value (type)` lines (Value
dump). Top-level services are the zero-indent lines.

(If I instead attach a generated `.html` from this suite, parse the
`const DATA = {...}` JSON embedded in it; each item already has an `m` marker
field of "", "*", or "**".)

## Required behavior (important — this is the whole point)
1. **Only draw instances that actually carry items.** Do NOT draw empty
   scaffolding containers as their own nodes. There must be no "(no items)" or
   "(no attributes)" nodes anywhere.
2. **Path-compress the empty containers.** When an item-bearing instance sits
   under a chain of empty containers, re-attach it to its nearest item-bearing
   ancestor (or the service root). Preserve the full original path and show it on
   hover, so no location information is lost.
3. **Render each item as an indented child row beneath its instance** (tabbed one
   level in), showing `Name = value (type)` — plus `[ValueClass]` for Value dumps
   — and the `*`/`**` marker. Items are always visible inline; do not hide them
   behind a tooltip.
4. Markers: no mark = static/edit-time only; `*` = written in code; `**` = can be
   nil after being set. Color the small item marker accordingly.

## Layout & interaction
- One diagram per service, switchable via tabs at the top (each tab shows its
  instance and item counts). Nodes = item-bearing instances; edges = the
  (compressed) parent→child relationship; color instance nodes by ClassName with
  a legend.
- Default to showing the top ~3 depth levels expanded; clicking an instance node
  expands/collapses its branch. Provide expand-all / collapse-all and a search
  box (matches instance names, item names, and item values) that reveals and
  expands the ancestors of any hit.
- Hover an instance node to see its full pre-compression path; hover an item to
  see its value and owning instance.

## Constraints
- **One single self-contained .html file. No external/CDN dependencies** — inline
  all CSS and JS, compute the tidy-tree layout yourself in vanilla JS/SVG. Do not
  load D3, vis.js, mermaid, etc. (I need fully memory-contained code.)
- Dark theme, monospace. Don't modify or sync anything into a Roblox project.

## Before you finish
Verify your totals: the number of item rows you rendered must equal the number of
attribute/value lines in the input, and the number of instance nodes must equal
the number of distinct item-bearing instances (plus any empty service-root
anchors). Report those per-service counts so I know nothing was dropped.

---

WHICH FILE TO ATTACH:
- `Trees/AttributeTree.luau` (or `AttributeTree.html`) for the attribute network.
- `Trees/ValueBaseTree.luau` (or `ValueBaseTree.html`) for the Value-object network.

NOTE: this suite already ships generators that do exactly the above —
`build_network_diagram.py` (attributes) and `build_value_network_diagram.py`
(values). Use this prompt only if you want another Claude to rebuild the behavior
from scratch.
