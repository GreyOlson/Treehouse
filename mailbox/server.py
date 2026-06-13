#!/usr/bin/env python3
"""
mailbox/server.py
-------------------
Local HTTP bridge for the Attribute Tree plugin. The Studio plugin POSTs a dump
here; this writes it into ../working/, runs the matching generators, and opens
the resulting HTML in your browser. Stdlib only.

Run:
    TREE_SRC=/path/to/YourGame/src python3 mailbox/server.py

Then in Studio: enable "Allow HTTP Requests", open the plugin, click a button.
Everything stays on localhost.

Env:
    TREE_SRC      - path to the analyzed game's Rojo src/ (for the */** markers)
    ATTRTREE_PORT - listen port (default 8787)
"""

import http.server
import os
import subprocess
import sys
import webbrowser
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
GEN = os.path.join(ROOT, "generators")
WORKING = os.path.join(ROOT, "working")
SRC = os.environ.get("TREE_SRC", "")
PORT = int(os.environ.get("ATTRTREE_PORT", "8787"))

ROUTES = {
    "/refresh/attributes": (
        "AttributeTree.luau",
        ["build_attribute_tree.py", "build_network_diagram.py"],
        ["AttributeTree.html", "NetworkDiagram.html"],
    ),
    "/refresh/values": (
        "ValueBaseTree.luau",
        ["build_valuebase_tree.py", "build_value_network_diagram.py"],
        ["ValueBaseTree.html", "ValueNetworkDiagram.html"],
    ),
    "/refresh/collisions": (
        "CollisionTree.luau",
        ["build_collision_diagram.py"],
        ["CollisionNetworkDiagram.html"],
    ),
}

# In-flight chunked uploads: id -> {chunk_index: text}. Reassembled once all
# chunks for an id have arrived (see do_POST).
CHUNKS: dict = {}


def run(script, project=None):
    env = dict(os.environ)
    if SRC:
        env["TREE_SRC"] = SRC
    if project:
        env["ATTRTREE_PROJECT"] = project  # the live place name -> page titles
    subprocess.run([sys.executable, os.path.join(GEN, script)], cwd=GEN, env=env, check=True)


class Handler(http.server.BaseHTTPRequestHandler):
    def _reply(self, code, text):
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(text.encode("utf-8", "replace"))

    def do_POST(self):
        parsed = urlparse(self.path)
        route = next((k for k in ROUTES if parsed.path.startswith(k)), None)
        if not route:
            return self._reply(404, "unknown route " + self.path)
        qs = parse_qs(parsed.query)
        project = (qs.get("project") or [None])[0]
        dump_name, scripts, outputs = ROUTES[route]
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n).decode("utf-8", "replace")

            # Chunked upload: Roblox caps a POST body at 1024 KB, so big dumps
            # arrive as ordered chunks (id + chunk + chunks). Buffer until the
            # last one, then proceed with the reassembled body.
            cid = (qs.get("id") or [None])[0]
            if cid:
                idx = int((qs.get("chunk") or ["1"])[0])
                total = int((qs.get("chunks") or ["1"])[0])
                buf = CHUNKS.setdefault(cid, {})
                buf[idx] = body
                if len(buf) < total:
                    return self._reply(200, "ack chunk %d/%d" % (idx, total))
                body = "".join(buf[i] for i in range(1, total + 1))
                CHUNKS.pop(cid, None)

            os.makedirs(WORKING, exist_ok=True)
            with open(os.path.join(WORKING, dump_name), "w", encoding="utf-8") as f:
                f.write(body)
            for s in scripts:
                run(s, project)
            for o in outputs:
                webbrowser.open("file://" + os.path.join(WORKING, o))
            self._reply(200, "wrote %d bytes -> %s, opened %s"
                        % (len(body), dump_name, ", ".join(outputs)))
        except subprocess.CalledProcessError as e:
            self._reply(500, "generator failed: %s" % e)
        except Exception as e:  # noqa: BLE001
            self._reply(500, "error: %s" % e)

    def do_GET(self):
        # Health check for the plugin's open-time ping: any GET returns 200, so
        # the plugin can tell the mailbox is up without sending a dump. The second
        # line reports the connected src (empty if TREE_SRC is unset/invalid),
        # which lets the plugin auto-tick its "project src connected" toggle.
        src = SRC if (SRC and os.path.isdir(SRC)) else ""
        self._reply(200, "Treehouse mailbox running\nsrc=" + src)

    def log_message(self, *_):
        pass


if __name__ == "__main__":
    if not SRC:
        print("WARNING: TREE_SRC unset - */** runtime markers will use the generator default.")
    print("Treehouse listening on http://localhost:%d  (working=%s)" % (PORT, WORKING))
    http.server.HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
