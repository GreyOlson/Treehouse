# One-Click Refresh — Plugin Automation Feasibility

A feasibility write-up for turning the current manual loop (dump in Studio →
paste into `*.luau` → run the Python generators → open the HTML) into a single
plugin button. **No code here — analysis only.**

## TL;DR verdict

- **As a Studio plugin alone: not possible.** A Roblox plugin is sandboxed. It
  has no filesystem access, cannot run Python, and cannot open a web browser. So
  a plugin by itself can dump the DataModel, but it cannot write
  `ValueBaseTree.luau`, run `build_*.py`, or open the HTML.
- **As a plugin + a tiny local "mailbox" server: fully possible.** The plugin
  collects the dump and HTTP-POSTs it to a small program running on your machine
  (alongside Rojo). That program writes the `.luau`, runs the generators, and
  opens the browser. End result is the single-button workflow you described.

So the honest answer to "can it be one button?" is **yes — but it needs one
helper process running locally, not just a plugin.**

## The one hard constraint

Studio plugins run in the same locked-down environment as game scripts:
- No `io` / `os` / filesystem — a plugin **cannot write a file to your disk**.
- No process spawning — it **cannot run `python`**.
- No shell / browser — it **cannot open a URL on your desktop**.

The only outward door a plugin has is **`HttpService`** (web requests). That one
door is enough, because anything the plugin can't do itself it can ask a local
program to do over `http://localhost`.

## Architecture that works

```
[Studio Plugin]                         [Local mailbox (python, you run it)]
  Refresh ValueBase  ──HTTP POST dump──▶  writes Trees/ValueBaseTree.luau
  Refresh Attributes                      runs build_valuebase_tree.py
                                          runs build_value_network_diagram.py
                                          (and the attribute pair)
                                          opens the HTML(s) in your browser
```

Concretely: the plugin walks the DataModel (the same logic as today's dump
scripts), builds the dump string in memory, and calls
`HttpService:PostAsync("http://localhost:8787/refresh/values", dumpText)`. The
mailbox is ~40 lines (Python `http.server` or Flask) that receives the body,
writes the `.luau`, shells out to the generators, then `webbrowser.open(...)` on
the resulting HTML files. One click → everything refreshes and the pages pop
open.

This also **removes the multi-part split** (`Part_01_of_02`, `CONFIG_VALUES`,
manual copy/paste). The plugin sends the whole dump in the POST body (chunked if
large); the mailbox concatenates. The split only existed to dodge Studio's
output/clipboard limits, which HTTP doesn't have.

## Walking through your proposed workflow

1. **Plugin GUI with "Refresh Attribute Tree" / "Refresh ValueBase Tree"** —
   yes, a `DockWidgetPluginGui` with two `TextButton`s is standard.
2. **Each button runs the respective dump** — yes, reuse today's traversal.
3. **On creation, concatenate into the local `.luau`** — yes, but done by the
   mailbox (the plugin can't write disk). Plugin POSTs → mailbox writes.
4. **Do the changed `.luau` require editing the `build_*.py`?** — **No.** The
   generators read whatever the `.luau` contains at runtime; they never need code
   edits when the data changes. They just need to be **re-run** — which the
   mailbox does. Same for the two `build_*network*.py`.
5. **Would the HTMLs then open to the updated values?** — yes, *if* the mailbox
   opens a fresh browser tab after regenerating (a fresh tab loads the new file).
   A tab you already had open won't auto-update unless we add live-reload (the
   page polling a timestamp, or the server pushing a refresh). Opening a new tab
   each run is the simplest reliable option.
6. **Single click → open browser to both the network and the diagram page** —
   yes; the mailbox can `webbrowser.open` multiple URLs (or one little index
   page that links/embeds all four). For each tree you have two HTMLs (tree +
   network), so a click could open both.

## The Rojo question

You framed file-writing as "developer synced into Rojo so the local file is
writeable." Worth clarifying: **Rojo is not what writes the dump files.**
- Rojo syncs `src/` filesystem → Studio (one-way by default). It is *not* the
  mechanism for getting Studio data back onto disk.
- Rojo *does* have an experimental **`syncback`** that can pull Studio changes to
  disk, so in theory the plugin could stuff the dump into a `Script.Source` and
  let `rojo syncback` write it out — but that path is fiddly, version-dependent,
  and would only work if the dump scripts lived under a synced path. The
  `Trees/` folder is intentionally **outside** `src/`, so Rojo ignores it anyway.
- The localhost-mailbox approach sidesteps Rojo entirely: it writes
  `Trees/*.luau` and `Trees/*.html` directly. Rojo can keep running for normal
  development; it just isn't involved in this tooling. (You only need Rojo here
  if you later decide to commit the generated dumps into the synced tree.)

So: Rojo running is fine and expected, but the **writeability comes from the
mailbox process**, not from Rojo.

## Options, ranked

1. **Plugin + localhost mailbox (recommended).** True one-click; no copy/paste;
   opens the browser. Cost: you run one small local script (could be auto-started
   with Rojo). Requires HttpService enabled and localhost requests allowed.
2. **Plugin alone, into `Script.Source`, + `rojo syncback`.** No extra process,
   but brittle, experimental, and still needs a separate step to run the
   generators and open the browser — so not actually one-click. Not recommended.
3. **Keep the plugin for dumping only + a local `build_all` runner.** Plugin
   writes the dump scripts (as today); a single local command then runs all four
   generators and opens the browser. This is "two clicks" (copy, then run) and
   needs no HTTP wiring — a reasonable middle ground if you want to avoid a
   long-running mailbox.

## What a future build would need (when you're ready)

- **Plugin side:** `DockWidgetPluginGui` + buttons; the existing dump traversal;
  `HttpService:PostAsync` to localhost; chunking for large dumps.
- **Permissions:** Game Settings → Security → *Allow HTTP Requests* on; the dev
  must accept localhost requests. Nothing leaves the machine (localhost only).
- **Mailbox side:** ~40–80 lines: an HTTP endpoint per tree that writes the
  `.luau`, runs the matching generator(s) via `subprocess`, and
  `webbrowser.open`s the outputs. Optionally launched automatically next to Rojo.
- **Nice-to-haves:** a tiny index page that embeds/links all four HTMLs; optional
  live-reload so an open tab refreshes itself; a status line in the plugin GUI
  echoing the mailbox's "wrote N values / opened browser" reply.

## Bottom line

Everything you described is achievable as **one button**, with one caveat: a
plugin can't touch your disk or open a browser on its own, so it must hand off to
a small local helper over `http://localhost`. With that helper in place, click →
dump → write `.luau` → run all generators → browser opens to the fresh pages,
exactly as you laid out. The `.py` files never need editing when data changes —
only re-running, which the helper handles.
