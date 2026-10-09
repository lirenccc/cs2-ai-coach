from __future__ import annotations

import base64
import mimetypes
from pathlib import Path

from .models import CoachIncidentAnalysis


def _data_url(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    mime = mime or "image/jpeg"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


class OpenAiProvider:
    def __init__(self, *, api_key: str, model: str):
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")

        try:
            from openai import OpenAI
        except ImportError as exc:
            raise RuntimeError(
                "OpenAI SDK is not installed. Install analyzer with the [ai] extra."
            ) from exc

        self.client = OpenAI(api_key=api_key)
        self.model = model

    def analyze_incident(
        self,
        *,
        incident_id: str,
        fact_packet_json: str,
        image_paths: list[Path],
    ) -> CoachIncidentAnalysis:
        content: list[dict[str, object]] = [
            {
                "type": "input_text",
                "text": (
                    "Analyze this offline CS2 Demo incident. "
                    "Treat supplied demo facts as authoritative. "
                    "Do not invent game facts. If evidence is insufficient, "
                    "state uncertainty.\n\n"
                    f"incident_id={incident_id}\n"
                    f"fact_packet={fact_packet_json}"
                ),
            }
        ]

        for path in image_paths:
            content.append({
                "type": "input_image",
                "image_url": _data_url(path),
            })

        response = self.client.responses.parse(
            model=self.model,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an offline Counter-Strike 2 demo coach. "
                        "Separate facts, visual observations, tactical inferences, "
                        "recommendations, and uncertainties."
                    ),
                },
                {"role": "user", "content": content},
            ],
            text_format=CoachIncidentAnalysis,
        )

        parsed = response.output_parsed
        if parsed is None:
            raise RuntimeError("Model returned no structured result.")
        return parsed
