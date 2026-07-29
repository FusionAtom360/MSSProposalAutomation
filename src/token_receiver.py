from http.server import BaseHTTPRequestHandler
import json

class TokenReceiver(BaseHTTPRequestHandler):
    token = None

    def do_POST(self):
        if self.path != "/token":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers["Content-Length"])
        body = self.rfile.read(length)

        data = json.loads(body)

        TokenReceiver.token = data.get("token")[1:-1]

        self.send_response(200)
        self.end_headers()

        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        # Disable console logging
        pass
