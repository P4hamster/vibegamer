from __future__ import annotations

import html
import json
from pathlib import Path

from tower_referee.schema import RunSummary
from tower_referee.scoring import aggregate_leaderboards


def write_dashboard(root: str | Path, summaries: list[RunSummary]) -> Path:
    root_path = Path(root)
    boards = aggregate_leaderboards(summaries)
    payload = json.dumps(boards, ensure_ascii=False)
    rows = "\n".join(
        "<tr>"
        f"<td>{html.escape(item.model_name)}</td><td>{item.round_id}</td>"
        f"<td>{item.score:.2f}</td><td>{item.waves_survived}</td>"
        f"<td>{item.base_hp}</td><td>{html.escape(item.personality)}</td>"
        "</tr>"
        for item in summaries
    )
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>6 个 AI 守城实验</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;background:#0b1020;color:#edf2ff}}
main{{max-width:1100px;margin:auto;padding:40px 20px}}h1{{font-size:38px}}.boards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px}}
.card{{background:#151d35;padding:20px;border:1px solid #293658;border-radius:16px}}.bar{{height:10px;background:#27324e;border-radius:9px;overflow:hidden}}
.fill{{height:100%;background:linear-gradient(90deg,#54e0a4,#59a7ff)}}table{{width:100%;border-collapse:collapse;margin-top:28px;background:#151d35}}
th,td{{padding:12px;border-bottom:1px solid #293658;text-align:left}}small{{color:#9bacce}}@media(max-width:800px){{.boards{{grid-template-columns:1fr}}}}
</style></head><body><main><h1>6 个 AI 守城实验</h1><p><small>所有分数均由原始 events.jsonl 可追溯复算</small></p>
<div class="boards" id="boards"></div>
<table><thead><tr><th>模型</th><th>轮次</th><th>得分</th><th>波数</th><th>生命</th><th>性格</th></tr></thead>
<tbody>{rows}</tbody></table></main>
<script>
const data={payload}; const names={{blind:"第一轮 · 裸考",review:"第二轮 · 复盘",generalization:"第三轮 · 泛化"}};
document.querySelector("#boards").innerHTML=Object.entries(data).map(([key,items])=>`<section class="card"><h2>${{names[key]}}</h2>${{items.map((x,i)=>`<p>${{i+1}}. ${{x.model}} <b>${{x.score}}</b></p><div class="bar"><div class="fill" style="width:${{x.score}}%"></div></div>`).join("")}}</section>`).join("");
</script></body></html>"""
    output = root_path / "dashboard.html"
    output.write_text(document, encoding="utf-8")
    return output


def write_campaign_dashboard(
    root: str | Path,
    summaries: list[RunSummary],
    campaign_summary: dict[str, object] | None = None,
) -> Path:
    root_path = Path(root)
    rows = "\n".join(
        "<tr>"
        f"<td>{item.round_id}</td><td>{html.escape(item.map_id)}</td>"
        f"<td>{'通关' if item.won else '失败'}</td><td>{item.score:.2f}</td>"
        f"<td>{item.waves_survived}/{item.max_waves}</td><td>{item.base_hp}</td>"
        f"<td>{item.gold_remaining}</td><td>{item.invalid_actions}</td>"
        "</tr>"
        for item in summaries
    )
    reached = (
        campaign_summary.get("reached_stages", len(summaries))
        if campaign_summary
        else len(summaries)
    )
    cleared = (
        campaign_summary.get("cleared_stages", sum(item.won for item in summaries))
        if campaign_summary
        else sum(item.won for item in summaries)
    )
    campaign_score = (
        campaign_summary.get("campaign_score")
        if campaign_summary
        else None
    )
    total_stages = campaign_summary.get("total_stages", 5) if campaign_summary else 5
    score_label = "未生成" if campaign_score is None else f"{campaign_score:.2f}"
    document = f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>AI 守城 · 五地图闯关测试</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,"PingFang SC",sans-serif;margin:0;background:#0b1020;color:#edf2ff}}
main{{max-width:1100px;margin:auto;padding:40px 20px}}h1{{font-size:38px;margin-bottom:8px}}
.summary{{display:flex;gap:16px;margin:24px 0}}.card{{background:#151d35;padding:18px 24px;border:1px solid #293658;border-radius:16px}}
.big{{font-size:30px;color:#66e3ff;font-weight:700}}table{{width:100%;border-collapse:collapse;background:#151d35}}
th,td{{padding:13px;border-bottom:1px solid #293658;text-align:left}}small{{color:#9bacce}}
</style></head><body><main><h1>AI 守城 · 五地图闯关测试</h1>
<p><small>上一关通关才进入下一关；每关结束后只向模型提供自己的复盘。</small></p>
<div class="summary"><div class="card"><div class="big">{score_label}</div>通天塔总分</div>
<div class="card"><div class="big">{cleared}/{total_stages}</div>已通关</div>
<div class="card"><div class="big">{reached}/{total_stages}</div>到达关卡</div></div>
<table><thead><tr><th>关卡</th><th>地图 ID</th><th>结果</th><th>得分</th>
<th>波数</th><th>基地生命</th><th>剩余金币</th><th>无效操作</th></tr></thead>
<tbody>{rows}</tbody></table></main></body></html>"""
    output = root_path / "campaign.html"
    output.write_text(document, encoding="utf-8")
    return output
