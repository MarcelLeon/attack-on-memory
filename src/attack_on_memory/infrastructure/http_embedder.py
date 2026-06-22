"""Hardened HTTP adapter for hosted semantic embedding services."""

from __future__ import annotations

import json
import math
import os
import ssl
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urlparse


DEFAULT_MAX_RESPONSE_BYTES = 16 * 1024 * 1024


@dataclass
class HTTPTextEmbedder:
    """Call an OpenAI-compatible JSON embedding endpoint without storing secrets.

    The adapter intentionally accepts the API key through an environment variable
    or callback.  Its repr and public configuration therefore never contain key
    material. Plain HTTP is rejected except when explicitly enabled for local
    integration tests.
    """

    endpoint: str
    model: str
    api_key_env: str = "AOM_EMBEDDING_API_KEY"
    timeout_seconds: float = 15.0
    expected_dimensions: int | None = None
    max_input_chars: int = 100_000
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES
    allow_insecure_localhost: bool = False
    key_provider: Callable[[], str] | None = field(
        default=None,
        repr=False,
        compare=False,
    )
    _observed_dimensions: int | None = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        parsed = urlparse(self.endpoint)
        local = parsed.hostname in {"127.0.0.1", "localhost", "::1"}
        if parsed.scheme != "https" and not (
            parsed.scheme == "http" and local and self.allow_insecure_localhost
        ):
            raise ValueError("embedding endpoint must use HTTPS")
        if not parsed.netloc or parsed.username or parsed.password:
            raise ValueError("embedding endpoint URL is invalid")
        if not self.model.strip():
            raise ValueError("embedding model cannot be empty")
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be > 0")
        if self.expected_dimensions is not None and self.expected_dimensions <= 0:
            raise ValueError("expected_dimensions must be > 0")
        if self.max_input_chars <= 0 or self.max_response_bytes <= 0:
            raise ValueError("input and response limits must be > 0")
        if not self.api_key_env.strip():
            raise ValueError("api_key_env cannot be empty")

    @property
    def identity(self) -> Mapping[str, object]:
        """Return non-secret model identity suitable for qualification reports."""
        return {
            "adapter": type(self).__name__,
            "endpoint_origin": _endpoint_origin(self.endpoint),
            "model": self.model,
            "expected_dimensions": self.expected_dimensions,
        }

    def embed(self, text: str) -> tuple[float, ...]:
        if not isinstance(text, str):
            raise TypeError("embedding input must be a string")
        if not text.strip():
            raise ValueError("embedding input cannot be empty")
        if len(text) > self.max_input_chars:
            raise ValueError("embedding input exceeds max_input_chars")
        key = self.key_provider() if self.key_provider else os.environ.get(self.api_key_env)
        if not key:
            raise RuntimeError(f"embedding credential is missing from {self.api_key_env}")
        payload = json.dumps(
            {"input": text, "model": self.model},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "attack-on-memory/0.1 embedding-qualification",
            },
        )
        try:
            with urllib.request.urlopen(
                request,
                timeout=self.timeout_seconds,
                context=ssl.create_default_context(),
            ) as response:
                content_type = response.headers.get_content_type()
                if content_type != "application/json":
                    raise RuntimeError("embedding endpoint returned non-JSON content")
                raw = response.read(self.max_response_bytes + 1)
        except urllib.error.HTTPError as exc:
            # Do not surface response bodies: providers may echo sensitive input.
            raise RuntimeError(f"embedding endpoint returned HTTP {exc.code}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError("embedding endpoint request failed") from exc
        if len(raw) > self.max_response_bytes:
            raise RuntimeError("embedding response exceeds max_response_bytes")
        vector = _parse_embedding_response(raw)
        dimensions = len(vector)
        required = self.expected_dimensions or self._observed_dimensions
        if required is not None and dimensions != required:
            raise ValueError(
                f"embedding dimensions changed: expected {required}, got {dimensions}"
            )
        self._observed_dimensions = dimensions
        return vector


def _parse_embedding_response(raw: bytes) -> tuple[float, ...]:
    try:
        parsed = json.loads(raw, object_pairs_hook=_reject_duplicate_keys)
    except (json.JSONDecodeError, UnicodeDecodeError, TypeError) as exc:
        raise RuntimeError("embedding endpoint returned invalid JSON") from exc
    if not isinstance(parsed, Mapping) or not isinstance(parsed.get("data"), list):
        raise RuntimeError("embedding response does not contain a data array")
    data = parsed["data"]
    if len(data) != 1 or not isinstance(data[0], Mapping):
        raise RuntimeError("embedding response must contain exactly one result")
    values = data[0].get("embedding")
    if not isinstance(values, list) or not values:
        raise RuntimeError("embedding response does not contain a vector")
    if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
        raise RuntimeError("embedding vector must contain only numbers")
    vector = tuple(float(value) for value in values)
    if any(not math.isfinite(value) for value in vector):
        raise RuntimeError("embedding vector contains a non-finite value")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0.0:
        raise RuntimeError("embedding vector cannot be all zero")
    return tuple(value / norm for value in vector)


def _reject_duplicate_keys(pairs: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"embedding response contains duplicate JSON key: {key}")
        result[key] = value
    return result


def _endpoint_origin(endpoint: str) -> str:
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    return f"{parsed.scheme}://{host}{port}"
