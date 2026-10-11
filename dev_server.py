"""Local preview: python3 dev_server.py -> http://localhost:3000 (reads .env, mimics Vercel routing)."""
import importlib.util
import os
import sys
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ROOT, "api"))
for line in open(os.path.join(ROOT, ".env")):
    if "=" in line and not line.startswith("#"):
        k, v = line.rstrip("\n").split("=", 1)
        if k != "DATABASE_URL":  # the web app never uses the owner login, same as on Vercel
            os.environ.setdefault(k, v)
HANDLERS = {}


def handler_for(name):
    if name not in HANDLERS:
        path = os.path.join(ROOT, "api", name + ".py")
        if not os.path.exists(path) or name.startswith("_"):
            return None
        spec = importlib.util.spec_from_file_location("api_" + name, path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        HANDLERS[name] = mod.handler
    return HANDLERS[name]


class Dev(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=os.path.join(ROOT, "public"), **k)

    def route(self, method):
        if self.path.startswith("/api/"):
            h = handler_for(self.path[5:].split("?")[0].strip("/"))
            if not h or not hasattr(h, method):
                self.send_error(404)
                return
            getattr(h, method)(self)
            return
        if method == "do_GET":
            p = self.path.split("?")[0]
            if p != "/" and "." not in p and os.path.exists(os.path.join(ROOT, "public", p.strip("/") + ".html")):
                self.path = p + ".html"
            super().do_GET()

    def do_GET(self): self.route("do_GET")
    def do_POST(self): self.route("do_POST")
    def do_PATCH(self): self.route("do_PATCH")
    def do_DELETE(self): self.route("do_DELETE")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print("http://localhost:%d" % port)
    ThreadingHTTPServer(("127.0.0.1", port), Dev).serve_forever()
