from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import urllib.request
from typing import Any, Protocol
from pathlib import Path

from .models import ModelDecision, Sample, Window, validate_model_decisions


class VisionProvider(Protocol):
    name: str

    def analyze(
        self,
        prompt: str,
        windows: list[Window],
        samples: dict[str, Sample],
    ) -> list[ModelDecision]: ...


class MockVisionProvider:
    name = "mock"

    def analyze(
        self,
        prompt: str,
        windows: list[Window],
        samples: dict[str, Sample],
    ) -> list[ModelDecision]:
        del samples
        decisions: list[ModelDecision] = []
        for window in windows:
            digest = hashlib.sha256(f"{prompt}\n{window.window_id}".encode()).digest()
            keep = digest[0] % 4 == 0
            score = round(0.55 + digest[1] / 2550, 3)
            decisions.append(
                ModelDecision(
                    window_id=window.window_id,
                    keep=keep,
                    score=score,
                    tags=["mock-candidate"] if keep else ["mock-discard"],
                    reason=(
                        f"Deterministic mock result for Prompt: {prompt[:120]}"
                    ),
                )
            )
        return decisions


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self) -> None:
        self.api_key = os.environ.get("HIGHLIGHT_API_KEY")
        self.endpoint = os.environ.get(
            "HIGHLIGHT_API_URL", "https://api.openai.com/v1/chat/completions"
        )
        self.model = os.environ.get("HIGHLIGHT_MODEL")
        if not self.api_key or not self.model:
            raise RuntimeError(
                "Set HIGHLIGHT_API_KEY and HIGHLIGHT_MODEL for the remote provider"
            )

    def analyze(
        self,
        prompt: str,
        windows: list[Window],
        samples: dict[str, Sample],
    ) -> list[ModelDecision]:
        decisions: list[ModelDecision] = []
        for batch_start in range(0, len(windows), 4):
            batch = windows[batch_start : batch_start + 4]
            raw = self._request(prompt, batch, samples)
            decisions.extend(
                validate_model_decisions(raw, {window.window_id for window in batch})
            )
        return decisions

    def _request(
        self,
        prompt: str,
        windows: list[Window],
        samples: dict[str, Sample],
    ) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": (
                    "Analyze the labeled video windows against this user Prompt. "
                    "Return only a JSON array. Each item must contain window_id, "
                    "keep (boolean), score (0..1), tags (string array), and a "
                    "short reason. Never invent a window_id.\n\n"
                    f"Prompt: {prompt}\n\nWindows:\n"
                    + "\n".join(
                        f"{window.window_id}: {window.start:.3f}-{window.end:.3f}s"
                        for window in windows
                    )
                ),
            }
        ]
        for window in windows:
            for sample_id in window.sample_ids:
                sample = samples[sample_id]
                encoded = base64.b64encode(Path(sample.path).read_bytes()).decode()
                content.append(
                    {
                        "type": "text",
                        "text": f"Frame for {window.window_id} at {sample.timestamp:.3f}s",
                    }
                )
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{encoded}",
                            "detail": "low",
                        },
                    }
                )
        payload = json.dumps(
            {
                "model": self.model,
                "temperature": 0,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a precise video highlight selector.",
                    },
                    {"role": "user", "content": content},
                ],
            }
        ).encode()
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=180) as response:
            response_data = json.loads(response.read().decode())
        message = response_data["choices"][0]["message"]["content"]
        if isinstance(message, list):
            message = "".join(item.get("text", "") for item in message)
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(message).strip())
        parsed = json.loads(cleaned)
        if not isinstance(parsed, list):
            raise ValueError("Model response must be a JSON array")
        return parsed


def make_provider(name: str) -> VisionProvider:
    if name == "mock":
        return MockVisionProvider()
    if name in {"openai", "openai-compatible"}:
        return OpenAICompatibleProvider()
    raise ValueError(f"Unknown provider: {name}")
