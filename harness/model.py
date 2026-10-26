"""Model client for an OpenAI-compatible chat-completions endpoint.

Two behaviours matter here beyond "call the API":

1. **Loud failure on limits.** The user asked to be told and to have the
   experiment stopped if usage limits blow up. So auth errors, quota errors and
   repeated rate limits raise `AbortExperiment`, which propagates all the way
   out of `run.py` instead of being retried into a large bill. Only genuinely
   transient faults (timeouts, 5xx, connection resets) are retried.
2. **Token accounting.** Every call's usage is accumulated so the report can
   state total tokens and cost, and so per-episode / global caps can be
   enforced.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import requests

from .perception import COLOUR_NAMES


class AbortExperiment(RuntimeError):
    """Unrecoverable condition: stop the whole experiment and report."""


class ModelCallError(RuntimeError):
    """A single call failed in a way that is the model's problem, not ours."""


@dataclass
class Usage:
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    rate_limit_hits: int = 0
    transient_retries: int = 0

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.calls += 1
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out

    @property
    def tokens_total(self) -> int:
        return self.tokens_in + self.tokens_out

    def as_dict(self) -> dict[str, int]:
        return {
            "calls": self.calls,
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "tokens_total": self.tokens_total,
            "rate_limit_hits": self.rate_limit_hits,
            "transient_retries": self.transient_retries,
        }


@dataclass
class ModelResponse:
    text: str
    tokens_in: int
    tokens_out: int
    latency_ms: int
    raw_finish_reason: str | None = None


# ---------------------------------------------------------------------------
# Image rendering (optional VLM channel)
# ---------------------------------------------------------------------------

_PALETTE_RGB = {
    0: (0, 0, 0),
    1: (0, 116, 217),
    2: (255, 65, 54),
    3: (46, 204, 64),
    4: (255, 220, 0),
    5: (170, 170, 170),
    6: (240, 18, 190),
    7: (255, 133, 27),
    8: (127, 219, 255),
    9: (135, 12, 37),
    10: (255, 155, 200),
    11: (1, 255, 112),
    12: (57, 204, 204),
    13: (133, 87, 35),
    14: (0, 31, 63),
    15: (255, 255, 255),
}


def grid_to_png_data_url(grid: np.ndarray, cell_pixels: int = 6) -> str:
    """Render a colour grid to a base64 PNG data URL for the vision channel."""
    from matplotlib import pyplot as plt  # imported lazily; only used if enabled

    height, width = grid.shape
    rgb = np.zeros((height, width, 3), dtype=np.uint8)
    for value in np.unique(grid):
        rgb[grid == value] = _PALETTE_RGB.get(int(value), (80, 80, 80))

    figure = plt.figure(
        figsize=(width * cell_pixels / 100, height * cell_pixels / 100), dpi=100
    )
    axes = figure.add_axes((0, 0, 1, 1))
    axes.imshow(rgb, interpolation="nearest")
    axes.set_axis_off()
    buffer = io.BytesIO()
    figure.savefig(buffer, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(figure)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------


def load_api_key(env_var: str = "ARC_MODEL_API_KEY") -> str:
    """Read the key from the environment, falling back to a local .env file.

    The key is never read from config.yaml so it cannot be committed.
    """
    key = os.environ.get(env_var, "").strip()
    if key:
        return key
    if os.path.exists(".env"):
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, _, value = line.partition("=")
                if name.strip() == env_var:
                    return value.strip().strip('"').strip("'")
    raise AbortExperiment(
        f"No model API key. Set {env_var} in the environment or in a .env file "
        f"at the repo root as {env_var}=sk-..."
    )


@dataclass
class ModelClient:
    base_url: str
    model: str
    api_key: str
    temperature: float = 0.2
    top_p: float = 0.9
    max_tokens: int = 1024
    thinking: str = "low"
    request_timeout_s: int = 180
    max_transient_retries: int = 2
    abort_after_consecutive_rate_limits: int = 3
    # If the endpoint fails this many calls in a row, stop the experiment. A
    # dead backend otherwise produces episodes made entirely of harness
    # fallback actions, which look like legitimate "unsolved" results and
    # silently poison the dataset. Failing loudly is the whole point.
    abort_after_consecutive_call_failures: int = 5
    global_token_cap: int = 40_000_000

    usage: Usage = field(default_factory=Usage)
    _consecutive_rate_limits: int = 0
    _consecutive_call_failures: int = 0
    _session: requests.Session | None = None

    def __post_init__(self) -> None:
        self.base_url = self.base_url.rstrip("/")
        self._session = requests.Session()

    # -- health check -------------------------------------------------------

    def preflight(self) -> dict[str, Any]:
        """Verify credentials and model availability before burning a run.

        Raises AbortExperiment with an actionable message if the endpoint
        rejects us, so a bad key is reported in seconds instead of after a
        partial experiment.
        """
        url = f"{self.base_url}/models"
        try:
            response = self._session.get(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=min(self.request_timeout_s, 60),
            )
        except requests.RequestException as error:
            raise AbortExperiment(
                f"Cannot reach the model endpoint {url}: {error}"
            ) from error

        if response.status_code in (401, 403):
            raise AbortExperiment(
                f"Model endpoint rejected the API key ({response.status_code}): "
                f"{response.text[:300]}\n"
                "Check ARC_MODEL_API_KEY. The experiment cannot run without it."
            )
        if response.status_code == 429:
            raise AbortExperiment(
                "Model endpoint is rate-limiting the credential check (429). "
                "Stopping before the experiment starts, as requested."
            )
        if response.status_code >= 400:
            # Some gateways do not implement /models. Fall back to a 1-token
            # chat call, which is the capability we actually need.
            probe = self.complete(
                [{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=8,
            )
            return {"models_endpoint": response.status_code, "probe": probe.text[:40]}

        try:
            payload = response.json()
        except ValueError:
            return {"models_endpoint": 200, "ids": []}
        ids = [entry.get("id") for entry in payload.get("data", []) or []]
        if ids and self.model not in ids:
            raise AbortExperiment(
                f"Model {self.model!r} is not served by {self.base_url}. "
                f"Available: {', '.join(str(i) for i in ids[:40])}"
            )

        # A healthy /models proves the key is valid, NOT that inference works.
        # These are different services behind the same gateway, and the gateway
        # has been seen serving /models fine while its upstream model server was
        # refusing every chat request with a 500. Probe the capability we
        # actually need, so a dead backend costs seconds rather than a wasted
        # sweep of fallback-only episodes.
        try:
            probe = self.complete(
                [{"role": "user", "content": "Reply with the single word OK."}],
                max_tokens=8,
            )
        except (ModelCallError, AbortExperiment) as error:
            raise AbortExperiment(
                f"{self.base_url} lists {self.model} and accepts the key, but "
                f"chat completions are failing: {error}\n"
                "The gateway is up but its model backend is not. Nothing to fix "
                "on our side; wait for the provider or use another endpoint."
            ) from error

        # The probe must not count toward the failure streak of the real run.
        self._consecutive_call_failures = 0
        return {"models_endpoint": 200, "ids": ids, "probe": probe.text[:40]}

    # -- completion ---------------------------------------------------------

    def _body(self, messages: list[dict[str, Any]], max_tokens: int | None) -> dict:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "max_tokens": max_tokens or self.max_tokens,
        }
        # Qwen3.8 thinking control. "off" disables reasoning entirely; any other
        # value is passed through as the reasoning_effort level.
        if self.thinking and self.thinking.lower() not in ("off", "none", "false"):
            body["reasoning_effort"] = self.thinking
        else:
            body["chat_template_kwargs"] = {"enable_thinking": False}
        return body

    def _call_failed(self, message: str) -> ModelCallError:
        """Record a failed call; escalate to an abort if they keep coming."""
        self._consecutive_call_failures += 1
        if self._consecutive_call_failures >= self.abort_after_consecutive_call_failures:
            raise AbortExperiment(
                f"{self._consecutive_call_failures} model calls failed in a row. "
                f"The endpoint looks unhealthy, and continuing would fill the "
                f"results with harness-fallback actions that masquerade as real "
                f"episodes. Last error: {message}"
            )
        return ModelCallError(message)

    def complete(
        self, messages: list[dict[str, Any]], max_tokens: int | None = None
    ) -> ModelResponse:
        if self.usage.tokens_total >= self.global_token_cap:
            raise AbortExperiment(
                f"Global token cap reached ({self.usage.tokens_total} >= "
                f"{self.global_token_cap}). Stopping the experiment."
            )

        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        body = self._body(messages, max_tokens)
        attempt = 0

        while True:
            started = time.monotonic()
            try:
                response = self._session.post(
                    url,
                    headers=headers,
                    data=json.dumps(body),
                    timeout=self.request_timeout_s,
                )
            except requests.RequestException as error:
                attempt += 1
                if attempt > self.max_transient_retries:
                    raise self._call_failed(
                        f"Network failure after {attempt} attempts: {error}"
                    ) from error
                self.usage.transient_retries += 1
                time.sleep(min(2**attempt, 10))
                continue

            latency_ms = int((time.monotonic() - started) * 1000)
            status = response.status_code
            text_body = response.text

            # --- conditions that stop the whole experiment ------------------
            if status in (401, 403):
                raise AbortExperiment(
                    f"Model endpoint returned {status} (auth/permission): "
                    f"{text_body[:300]}"
                )
            if status == 402 or "insufficient" in text_body.lower()[:400] or (
                "quota" in text_body.lower()[:400] and status >= 400
            ):
                raise AbortExperiment(
                    f"Model endpoint reports a billing/quota problem ({status}): "
                    f"{text_body[:300]}"
                )
            if status == 429:
                self.usage.rate_limit_hits += 1
                self._consecutive_rate_limits += 1
                if (
                    self._consecutive_rate_limits
                    >= self.abort_after_consecutive_rate_limits
                ):
                    raise AbortExperiment(
                        f"Hit {self._consecutive_rate_limits} consecutive rate "
                        f"limits (429) from the model endpoint. Stopping the "
                        f"experiment so it does not grind against the limit. "
                        f"Last body: {text_body[:200]}"
                    )
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(5 * 2**attempt, 60)
                time.sleep(delay)
                attempt += 1
                continue

            # --- transient server-side faults -------------------------------
            if status >= 500:
                attempt += 1
                if attempt > self.max_transient_retries:
                    raise self._call_failed(
                        f"Server error {status}: {text_body[:200]}"
                    )
                self.usage.transient_retries += 1
                time.sleep(min(2**attempt, 10))
                continue

            if status >= 400:
                raise self._call_failed(
                    f"Request rejected ({status}): {text_body[:300]}"
                )

            self._consecutive_rate_limits = 0
            try:
                payload = response.json()
            except ValueError as error:
                raise self._call_failed(
                    f"Endpoint returned non-JSON: {text_body[:200]}"
                ) from error

            choices = payload.get("choices") or []
            if not choices:
                raise self._call_failed(
                    f"No choices in response: {text_body[:200]}"
                )

            # A real answer: the endpoint is healthy again.
            self._consecutive_call_failures = 0
            message = choices[0].get("message") or {}
            content = message.get("content") or ""
            # Some gateways put thinking in a separate field; the action JSON is
            # expected in content, so reasoning_content is logged but not parsed.
            usage_payload = payload.get("usage") or {}
            tokens_in = int(usage_payload.get("prompt_tokens") or 0)
            tokens_out = int(usage_payload.get("completion_tokens") or 0)
            self.usage.add(tokens_in, tokens_out)

            return ModelResponse(
                text=content,
                tokens_in=tokens_in,
                tokens_out=tokens_out,
                latency_ms=latency_ms,
                raw_finish_reason=choices[0].get("finish_reason"),
            )


def build_user_content(
    text: str, grid: np.ndarray | None, send_image: bool
) -> str | list[dict[str, Any]]:
    """Build an OpenAI-style content payload, with an optional image part."""
    if not send_image or grid is None or grid.size == 0:
        return text
    return [
        {"type": "text", "text": text},
        {
            "type": "image_url",
            "image_url": {"url": grid_to_png_data_url(grid)},
        },
    ]


PALETTE_LEGEND = ", ".join(
    f"{value}={name}" for value, name in sorted(COLOUR_NAMES.items())
)
