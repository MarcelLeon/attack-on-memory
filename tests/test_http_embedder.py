from __future__ import annotations

import json
import unittest
from email.message import Message
from unittest.mock import patch

from attack_on_memory.infrastructure.http_embedder import HTTPTextEmbedder


class _Response:
    def __init__(self, body: bytes, content_type: str = "application/json") -> None:
        self.body = body
        self.headers = Message()
        self.headers["Content-Type"] = content_type

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        return None

    def read(self, limit: int) -> bytes:
        return self.body[:limit]


class HTTPTextEmbedderTests(unittest.TestCase):
    endpoint = "http://127.0.0.1:9876/v1/embeddings"

    def _embedder(self, **overrides: object) -> HTTPTextEmbedder:
        options: dict[str, object] = {
            "endpoint": self.endpoint,
            "model": "semantic-v1",
            "allow_insecure_localhost": True,
            "key_provider": lambda: "super-secret-token",
        }
        options.update(overrides)
        return HTTPTextEmbedder(**options)  # type: ignore[arg-type]

    def test_posts_compatible_payload_and_normalizes_vector(self) -> None:
        response = _Response(json.dumps({"data": [{"embedding": [3.0, 4.0]}]}).encode())
        with patch(
            "attack_on_memory.infrastructure.http_embedder.urllib.request.urlopen",
            return_value=response,
        ) as urlopen:
            embedder = self._embedder(expected_dimensions=2)
            self.assertEqual(embedder.embed("数据库恢复批准"), (0.6, 0.8))
        request = urlopen.call_args.args[0]
        self.assertEqual(request.full_url, self.endpoint)
        self.assertEqual(request.get_header("Authorization"), "Bearer super-secret-token")
        self.assertEqual(
            json.loads(request.data),
            {"input": "数据库恢复批准", "model": "semantic-v1"},
        )
        self.assertNotIn("super-secret-token", repr(embedder))
        self.assertEqual(embedder.identity["endpoint_origin"], "http://127.0.0.1:9876")

    def test_rejects_plain_http_except_explicit_local_test_mode(self) -> None:
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            HTTPTextEmbedder(self.endpoint, "semantic-v1")
        with self.assertRaisesRegex(ValueError, "HTTPS"):
            HTTPTextEmbedder(
                "http://embedding.example.com/v1/embeddings",
                "semantic-v1",
                allow_insecure_localhost=True,
            )

    def test_pins_dimensions_across_calls(self) -> None:
        responses = [
            _Response(json.dumps({"data": [{"embedding": [3.0, 4.0]}]}).encode()),
            _Response(json.dumps({"data": [{"embedding": [1.0, 2.0, 3.0]}]}).encode()),
        ]
        with patch(
            "attack_on_memory.infrastructure.http_embedder.urllib.request.urlopen",
            side_effect=responses,
        ):
            embedder = self._embedder()
            embedder.embed("first")
            with self.assertRaisesRegex(ValueError, "dimensions changed"):
                embedder.embed("second")

    def test_rejects_invalid_or_ambiguous_provider_output(self) -> None:
        duplicate = _Response(b'{"data":[{"embedding":[1.0,2.0]}],"data":[]}')
        with patch(
            "attack_on_memory.infrastructure.http_embedder.urllib.request.urlopen",
            return_value=duplicate,
        ):
            with self.assertRaisesRegex(ValueError, "duplicate JSON key"):
                self._embedder().embed("duplicate")

        zero = _Response(json.dumps({"data": [{"embedding": [0.0, 0.0]}]}).encode())
        with patch(
            "attack_on_memory.infrastructure.http_embedder.urllib.request.urlopen",
            return_value=zero,
        ):
            with self.assertRaisesRegex(RuntimeError, "all zero"):
                self._embedder().embed("zero")

    def test_requires_runtime_credential_without_exposing_input_on_failure(self) -> None:
        embedder = HTTPTextEmbedder(
            self.endpoint,
            "semantic-v1",
            api_key_env="AOM_TEST_KEY_THAT_IS_NOT_SET",
            allow_insecure_localhost=True,
        )
        with self.assertRaisesRegex(RuntimeError, "AOM_TEST_KEY_THAT_IS_NOT_SET") as caught:
            embedder.embed("sensitive payload")
        self.assertNotIn("sensitive payload", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
