from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from tower_referee.schema import RunSummary


class Recorder:
    def __init__(self, root: str | Path, experiment_id: str) -> None:
        self.root = Path(root) / experiment_id
        self.root.mkdir(parents=True, exist_ok=True)
        self.events_path = self.root / "events.jsonl"
        self.live_path = self.root / "live.json"
        self.summaries: list[RunSummary] = []
        self._write_live_page()

    def write_manifest(self, manifest: dict[str, Any]) -> None:
        """Freeze the harness/configuration used to produce later transcripts."""
        (self.root / "manifest.json").write_text(
            json.dumps(self._safe(manifest), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def write_validity(
        self,
        status: str,
        reason: str = "",
        details: dict[str, Any] | None = None,
    ) -> None:
        """Write an explicit gate result so invalid runs cannot look complete."""
        (self.root / "validity.json").write_text(
            json.dumps(
                self._safe(
                    {
                        "status": status,
                        "reason": reason,
                        "details": details or {},
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                ),
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def write_campaign_summary(self, summary: dict[str, Any]) -> None:
        (self.root / "campaign_summary.json").write_text(
            json.dumps(self._safe(summary), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def event(self, event_type: str, **payload: Any) -> None:
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event_type": event_type,
            **self._safe(payload),
        }
        with self.events_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        self.live_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    def add_summary(self, summary: RunSummary) -> None:
        self.summaries.append(summary)
        self.event("run_complete", summary=summary.to_dict())

    def write_summaries(self) -> None:
        rows = [summary.to_dict() for summary in self.summaries]
        (self.root / "summary.json").write_text(
            json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if rows:
            with (self.root / "summary.csv").open(
                "w", encoding="utf-8-sig", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {key: cls._safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._safe(item) for item in value]
        if hasattr(value, "__dataclass_fields__"):
            return cls._safe(asdict(value))
        return value

    def _write_live_page(self) -> None:
        """Create a zero-dependency OBS/browser-source friendly live monitor."""
        html = """<!doctype html><meta charset="utf-8">
<title>六个 AI 守城 · 实时裁判</title>
<style>
body{margin:0;background:#09111f;color:#eef4ff;font:16px system-ui;padding:24px}
.card{max-width:900px;background:#121e32;border:1px solid #2d4164;border-radius:18px;padding:24px}
h1{margin:0 0 18px;color:#66e3ff}.meta{display:flex;gap:20px;color:#a9bad6}
#reason{font-size:25px;margin:24px 0;color:#fff}.pill{display:inline-block;background:#24436b;padding:7px 12px;border-radius:99px}
pre{white-space:pre-wrap;color:#bcd0ec;background:#08101d;padding:16px;border-radius:12px;max-height:45vh;overflow:auto}
</style>
<div class="card"><h1>6 个 AI 守城 · 实时裁判</h1>
<div class="meta"><span id="model" class="pill">等待比赛</span><span id="event"></span><span id="wave"></span></div>
<div id="reason">裁判系统已就绪</div><pre id="detail"></pre></div>
<script>
async function tick(){try{let r=await fetch('live.json?'+Date.now()),d=await r.json();
model.textContent=d.model||'裁判';event.textContent=d.event_type||'';
wave.textContent=d.wave===undefined?'':'第 '+d.wave+' 波';
reason.textContent=d.analysis_summary||((d.events||[]).map(x=>x.type).join('、'))||'战局更新';
detail.textContent=JSON.stringify(d.accepted||d.rejected||d.summary||d.events||{},null,2)}
catch(e){}setTimeout(tick,500)}tick()</script>"""
        (self.root / "live.html").write_text(html, encoding="utf-8")
