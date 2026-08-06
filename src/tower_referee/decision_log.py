"""Export model-visible decision rationale from an audit event stream."""

from __future__ import annotations

import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any


def export_decision_log(events_path: str | Path, output_path: str | Path) -> Path:
    """Write model JSON and any reasoning text returned by the provider API."""
    source = Path(events_path)
    destination = Path(output_path)
    records = [
        json.loads(line)
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    paired = _pair_decisions(records)

    lines = [
        "# Model Decision Log",
        "",
        "This file records the planning text and JSON that the provider API "
        "actually returned. Content not returned by the API cannot be recorded.",
        "",
    ]
    if not paired:
        lines.extend(["No model decision was recorded.", ""])
    for index, (decision, response) in enumerate(paired, start=1):
        traces = response.get("request_trace") or []
        trace = traces[-1] if traces else {}
        lines.extend(
            [
                f"## Decision {index}",
                "",
                f"- Time: `{decision.get('timestamp', '-')}`",
                f"- Model: `{decision.get('model', '-')}`",
                f"- Service response model: `{trace.get('response_model', '-')}`",
                f"- Wave: `{decision.get('wave', '-')}`",
                f"- Parse status: `{response.get('parse_status', '-')}`",
                f"- Visible rationale: {decision.get('analysis_summary') or '-'}",
                f"- Accepted actions: `{json.dumps(decision.get('accepted', []), ensure_ascii=False)}`",
                f"- Rejected actions: `{json.dumps(decision.get('rejected', []), ensure_ascii=False)}`",
                "",
            ]
        )
        for phase_trace in traces:
            reasoning = phase_trace.get("reasoning_content")
            if not reasoning:
                continue
            phase = phase_trace.get("phase") or "request"
            lines.extend(
                [
                    f"### {str(phase).replace('_', ' ').title()} Reasoning",
                    "",
                    f"- Effort: `{phase_trace.get('reasoning_effort')}`",
                    f"- Finish reason: `{phase_trace.get('finish_reason')}`",
                    f"- Characters: `{phase_trace.get('reasoning_content_chars', len(reasoning))}`",
                    f"- Complete: `{phase_trace.get('reasoning_content_complete')}`",
                    "",
                    "```text",
                    str(reasoning),
                    "```",
                    "",
                ]
            )
        lines.extend(
            [
                "### Model JSON Output",
                "",
                "```json",
                _format_json(decision.get("raw_response")),
                "```",
                "",
            ]
        )
    destination.write_text("\n".join(lines), encoding="utf-8")
    return destination


def _pair_decisions(
    records: list[dict[str, Any]],
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    pending: dict[tuple[Any, ...], deque[dict[str, Any]]] = defaultdict(deque)
    paired: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        event_type = record.get("event_type")
        key = _decision_key(record)
        if event_type == "decision_received":
            pending[key].append(record)
            continue
        if event_type != "decision":
            continue
        raw_response = record.get("raw_response") or ""
        locally_generated = _is_local_response(raw_response)
        response = {}
        if not locally_generated and pending[key]:
            response = pending[key].popleft()
        paired.append((record, response))
    return paired


def _is_local_response(raw_response: Any) -> bool:
    if not isinstance(raw_response, str):
        return False
    try:
        data = json.loads(raw_response)
    except json.JSONDecodeError:
        return False
    return isinstance(data, dict) and str(data.get("source", "")).startswith(
        "local_"
    )


def _decision_key(record: dict[str, Any]) -> tuple[Any, ...]:
    return (
        record.get("round_id"),
        record.get("run_index"),
        record.get("wave"),
        record.get("model_id"),
    )


def _format_json(value: Any) -> str:
    if isinstance(value, str):
        try:
            return json.dumps(json.loads(value), ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            return value
    return json.dumps(value, ensure_ascii=False, indent=2)
