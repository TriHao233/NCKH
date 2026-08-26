import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from modules.generation.llm.ollama import OllamaProvider, close_ollama_client


class FakeOllamaHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        response = {
            "response": json.dumps(
                {
                    "model_received": payload.get("model"),
                    "status": "ok",
                }
            )
        }
        body = json.dumps(response).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


class OllamaHttpIntegrationTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllamaHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    async def asyncTearDown(self):
        await close_ollama_client()

    async def test_provider_calls_ollama_compatible_http_endpoint(self):
        provider = OllamaProvider("fake-model", timeout_seconds=2)
        provider.url = f"http://127.0.0.1:{self.server.server_port}/api/generate"

        result = json.loads(await provider.generate_text("test prompt"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model_received"], "fake-model")
