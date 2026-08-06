from __future__ import annotations

import json
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class PluginUnavailable(RuntimeError):
    """Raised when the local TowerMind observer cannot be reached."""


class PluginBridge:
    """Small localhost client for the in-game Observer/HUD plugin."""

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:17871",
        timeout: float = 1.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = max(0.1, float(timeout))

    def wait_until_ready(self, timeout: float = 10.0) -> dict[str, Any]:
        deadline = time.monotonic() + max(0.1, timeout)
        last_error: Exception | None = None
        while time.monotonic() < deadline:
            try:
                health = self.health()
                if health.get("ok"):
                    return health
            except PluginUnavailable as exc:
                last_error = exc
            time.sleep(0.05)
        detail = f": {last_error}" if last_error else ""
        raise PluginUnavailable(f"TowerMind Observer did not become ready{detail}")

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def mechanics(self) -> dict[str, Any]:
        return self._request("GET", "/mechanics")

    def state(self) -> dict[str, Any]:
        return self._request("GET", "/state")

    def decision(self) -> dict[str, Any]:
        return self._request("GET", "/decision")

    def events(self, after: int = 0) -> dict[str, Any]:
        query = urlencode({"after": max(0, int(after))})
        return self._request("GET", f"/events?{query}")

    def publish_decision(
        self,
        model: str,
        analysis_summary: str,
        action_text: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/decision",
            {
                "model": model,
                "analysis_summary": analysis_summary,
                "action_text": action_text,
            },
        )

    def publish_transition(
        self,
        outcome: str,
        title: str,
        detail: str,
        can_retry: bool = False,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/decision",
            {
                "model": "关卡结算",
                "analysis_summary": title,
                "action_text": detail,
                "view": "transition",
                "outcome": outcome,
                "can_retry": can_retry,
            },
        )

    def transition_action(self) -> str | None:
        result = self._request("GET", "/transition-action")
        action = str(result.get("action", "")).strip().lower()
        return action or None

    def command(
        self, request_id: str, actions: list[dict[str, Any]]
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/command",
            {"request_id": request_id, "actions": actions},
            timeout=6.0,
        )

    def _request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
        timeout: float | None = None,
    ) -> dict[str, Any]:
        body = (
            json.dumps(payload, ensure_ascii=False).encode("utf-8")
            if payload is not None
            else None
        )
        request = Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with urlopen(request, timeout=timeout or self.timeout) as response:
                raw = response.read().decode("utf-8")
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise PluginUnavailable(
                f"Observer HTTP {exc.code} for {path}: {detail}"
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PluginUnavailable(
                f"Observer request failed for {path}: {exc}"
            ) from exc
        try:
            result = json.loads(raw or "{}")
        except json.JSONDecodeError as exc:
            raise PluginUnavailable(
                f"Observer returned invalid JSON for {path}"
            ) from exc
        if not isinstance(result, dict):
            raise PluginUnavailable(f"Observer returned a non-object for {path}")
        return result
