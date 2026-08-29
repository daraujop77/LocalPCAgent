import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread

from personal_ai.chat import ChatMessage
from personal_ai.config import Settings
from personal_ai.qwen import HttpQwenClient


class FakeModelHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        self._write_json({"data": [{"id": "qwen-test"}]})

    def do_POST(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
        content_length = int(self.headers["Content-Length"])
        self.server.received_payload = json.loads(self.rfile.read(content_length))
        self._write_json(
            {
                "model": "qwen-test",
                "choices": [{"message": {"role": "assistant", "content": "local reply"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2},
            }
        )

    def _write_json(self, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format_string: str, *args: object) -> None:
        del format_string, args


def test_http_qwen_client_uses_openai_compatible_local_protocol() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), FakeModelHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://127.0.0.1:{server.server_port}/v1"
        settings = Settings(
            qwen_base_url=base_url,
            qwen_model="qwen-test",
            qwen_timeout_seconds=2,
            qwen_health_timeout_seconds=1,
        )
        client = HttpQwenClient(settings)

        assert client.health().ready is True
        reply = client.complete(
            (ChatMessage(role="user", content="Hello"),),
            request_id="test-request",
        )

        assert reply.content == "local reply"
        assert reply.model_name == "qwen-test"
        assert reply.usage["completion_tokens"] == 2
        assert server.received_payload["model"] == "qwen-test"
        assert server.received_payload["stream"] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
