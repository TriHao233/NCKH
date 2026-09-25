import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import MagicMock, patch

from modules.generation.llm.gemini import GeminiProvider
from modules.generation.llm.ollama import OllamaProvider, close_ollama_client


class FakeOllamaHandler(BaseHTTPRequestHandler):
    last_payload = None

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(content_length) or b"{}")
        type(self).last_payload = payload
        generated = json.dumps({"model_received": payload.get("model"), "status": "ok"})
        midpoint = len(generated) // 2
        if self.path.endswith("/api/chat"):
            chunks = [
                {"message": {"role": "assistant", "content": generated[:midpoint]}, "done": False},
                {
                    "message": {"role": "assistant", "content": generated[midpoint:]},
                    "done": True,
                    "done_reason": "stop",
                },
            ]
        else:
            chunks = [
                {"response": generated[:midpoint], "done": False},
                {"response": generated[midpoint:], "done": True, "done_reason": "stop"},
            ]
        body = ("\n".join(json.dumps(chunk) for chunk in chunks) + "\n").encode("utf-8")
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
        provider = OllamaProvider("fake-model", timeout_seconds=2, num_ctx=8192)
        provider.url = f"http://127.0.0.1:{self.server.server_port}/api/generate"

        result = json.loads(await provider.generate_text("test prompt"))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["model_received"], "fake-model")
        self.assertTrue(FakeOllamaHandler.last_payload["stream"])
        self.assertEqual(FakeOllamaHandler.last_payload["options"]["num_ctx"], 8192)
        self.assertEqual(provider.last_response_metadata["done_reason"], "stop")

    async def test_provider_sends_roles_and_schema_to_chat_endpoint(self):
        provider = OllamaProvider("fake-model", timeout_seconds=2, num_ctx=8192)
        provider.url = f"http://127.0.0.1:{self.server.server_port}/api/generate"
        schema = {"type": "object", "properties": {"ok": {"type": "boolean"}}}

        result = json.loads(
            await provider.generate_chat(
                system_prompt="system rules",
                user_prompt="user task",
                output_schema=schema,
            )
        )

        self.assertEqual(result["status"], "ok")
        self.assertTrue(FakeOllamaHandler.last_payload["stream"])
        self.assertEqual(provider.last_response_metadata["done_reason"], "stop")
        self.assertEqual(FakeOllamaHandler.last_payload["messages"][0]["role"], "system")
        self.assertEqual(FakeOllamaHandler.last_payload["messages"][1]["role"], "user")
        self.assertEqual(FakeOllamaHandler.last_payload["format"], schema)


class GeminiProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_gemini_3_uses_interactions_api_and_cleans_json_fences(self):
        response = MagicMock()
        response.output_text = '```json\n{"ok": true}\n```'
        client = MagicMock()
        client.interactions.create.return_value = response

        with (
            patch("modules.generation.llm.gemini.settings.gemini_api_key", "test-key"),
            patch("modules.generation.llm.gemini.genai.Client", return_value=client),
        ):
            provider = GeminiProvider(model_name="gemini-3.6-flash", max_output_tokens=2048)
            result = await provider.generate_text("prompt")

        self.assertEqual(result, '{"ok": true}')
        client.interactions.create.assert_called_once()
        client.models.generate_content.assert_not_called()
