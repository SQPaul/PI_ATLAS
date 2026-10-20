#!/usr/bin/env python3
"""Abre el dashboard desde su carpeta actual, con Python y sin dependencias."""

import argparse
import errno
import json
import sys
import threading
import webbrowser
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.request import ProxyHandler, Request, build_opener


ROOT = Path(__file__).resolve().parent
APP_ID = "explorador-campos-de-hielo"
STATUS_PATH = "/_explorador/status"


class DashboardHandler(SimpleHTTPRequestHandler):
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".mjs": "text/javascript",
        ".geojson": "application/geo+json",
    }

    def do_GET(self):
        if self.path == STATUS_PATH:
            data = json.dumps({"app": APP_ID, "directory": str(ROOT)}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)
            return
        super().do_GET()

    def log_message(self, format, *args):
        # Las solicitudes de cientos de teselas no necesitan llenar la terminal.
        if len(args) > 1 and str(args[1]).startswith(("4", "5")):
            super().log_message(format, *args)


def validate_assets():
    files = [
        "index.html", "app.js", "style.css",
        "vendor/maplibre-gl.mjs", "vendor/maplibre-gl.css",
        "vendor/maplibre-gl-worker.mjs", "vendor/maplibre-gl-shared.mjs",
        "terrain/custom-layers.json", "terrain/rgi-v6-outlines.geojson",
        "terrain/hydraulic-gradient-outlines.geojson",
    ]
    directories = [
        "surface", "surface-color", "basal", "basal-color",
        "hydraulic-filled", "hydraulic-filled-dem",
        "hydraulic-correction", "hydraulic-correction-dem",
    ]
    missing = [name for name in files if not (ROOT / name).is_file()]
    missing.extend(
        f"terrain/{name}" for name in directories
        if not (ROOT / "terrain" / name).is_dir()
    )
    if missing:
        raise ValueError("Faltan archivos del dashboard: " + ", ".join(missing))


def is_running_here(url):
    try:
        opener = build_opener(ProxyHandler({}))
        with opener.open(Request(url + STATUS_PATH), timeout=1) as response:
            data = json.load(response)
        return data == {"app": APP_ID, "directory": str(ROOT)}
    except (OSError, URLError, ValueError):
        return False


def open_browser(url):
    try:
        if webbrowser.open(url):
            return
    except webbrowser.Error:
        pass
    print(f"Abre esta dirección en el navegador: {url}", flush=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765, help="puerto inicial (8765)")
    parser.add_argument("--no-browser", action="store_true", help="no abrir el navegador")
    args = parser.parse_args(argv)
    if not 1 <= args.port <= 65535:
        parser.error("el puerto debe estar entre 1 y 65535")

    try:
        validate_assets()
        handler = partial(DashboardHandler, directory=str(ROOT))
        server = None
        for port in range(args.port, min(args.port + 10, 65536)):
            url = f"http://127.0.0.1:{port}"
            try:
                server = ThreadingHTTPServer(("127.0.0.1", port), handler)
                break
            except OSError as error:
                if error.errno != errno.EADDRINUSE:
                    raise
                if is_running_here(url):
                    print(f"El dashboard ya está abierto: {url}/", flush=True)
                    if not args.no_browser:
                        open_browser(url + "/")
                    return 0
        if server is None:
            raise ValueError("Los diez puertos están ocupados. Usa --port con otro puerto.")
    except (OSError, ValueError) as error:
        print(f"No se pudo iniciar el dashboard: {error}", file=sys.stderr)
        return 1

    with server:
        print(f"Dashboard: {url}/\nDatos: {ROOT}", flush=True)
        print("Mantén esta terminal abierta. Ctrl+C cierra el dashboard.", flush=True)
        if not args.no_browser:
            threading.Thread(target=open_browser, args=(url + "/",), daemon=True).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print("\nDashboard cerrado.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
