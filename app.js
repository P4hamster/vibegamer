const models = [
  {
    id: "deepseek",
    name: "DeepSeek V4 Flash",
    shortName: "DeepSeek",
    modelId: "deepseek-v4-flash",
    logo: "assets/deepseek.png",
    score: 83.87,
    cleared: 5,
    reached: 5,
    color: "#4d6bfe",
    maps: [
      { score: 82.92, hp: 4, wave: 5, won: true },
      { score: 82.56, hp: 3, wave: 5, won: true },
      { score: 85.71, hp: 7, wave: 5, won: true },
      { score: 84.82, hp: 6, wave: 5, won: true },
      { score: 83.36, hp: 4, wave: 5, won: true }
    ],
    validity: 87.18,
    damagePerGold: 74.49,
    killRate: 80.16,
    winHp: 24,
    requests: 186,
    inputTokens: null,
    outputTokens: null,
    cachedTokens: null,
    inputChars: 2706476,
    outputChars: 2301929,
    cost: "¥3.43",
    billingUrl: "https://platform.deepseek.com/usage",
    usageGuideUrl: "https://api-docs.deepseek.com/quick_start/pricing",
    radar: [100, 24, 80, 90, 87, 83],
    strength: "唯一五图全通，各图小分波动仅 3.15 分，长线稳定性最强。",
    weakness: "五张胜图平均仅剩 4.8 HP，属于高风险险胜；动作合法率 87.2%。"
  },
  {
    id: "glm",
    name: "GLM 5.3",
    shortName: "GLM",
    modelId: "openai/glm-5.3",
    logo: "assets/glm.png",
    score: 87.66,
    cleared: 5,
    reached: 5,
    color: "#303030",
    maps: [
      { score: 91.0, hp: 11, wave: 5, won: true },
      { score: 84.0, hp: 6, wave: 5, won: true },
      { score: 96.66, hp: 17, wave: 5, won: true },
      { score: 82.31, hp: 3, wave: 5, won: true },
      { score: 84.31, hp: 5, wave: 5, won: true }
    ],
    validity: 92.54,
    damagePerGold: 83.33,
    killRate: 84.86,
    winHp: 42,
    requests: 147,
    inputTokens: null,
    outputTokens: null,
    cachedTokens: null,
    inputChars: 2366737,
    outputChars: 965052,
    cost: "¥0",
    billingUrl: "https://bigmodel.cn/console/overview",
    usageGuideUrl: "https://docs.bigmodel.cn/cn/guide/capabilities/cache",
    radar: [100, 42, 85, 100, 93, 84],
    strength: "五张地图全部通关，战役总分 87.66。",
    weakness: "平均终局 HP 8.4；地图 2 仅剩 3 HP。"
  },
  {
    id: "qwen",
    name: "Qwen3.8-Max",
    shortName: "Qwen",
    modelId: "qwen3.8-max",
    logo: "assets/qwen.png",
    score: 64.49,
    cleared: 3,
    reached: 4,
    color: "#3048ff",
    maps: [
      { score: 87.89, hp: 9, wave: 5, won: true },
      { score: 83.0, hp: 3, wave: 5, won: true },
      { score: 81.57, hp: 3, wave: 5, won: true },
      { score: 70.0, hp: 0, wave: 5, won: false },
      null
    ],
    validity: 92.31,
    damagePerGold: 62.38,
    killRate: 76.87,
    winHp: 25,
    requests: 74,
    inputTokens: 622912,
    outputTokens: 15223,
    cachedTokens: 0,
    inputChars: null,
    outputChars: 40633,
    cost: "¥6.39132",
    billingUrl: "https://bailian.console.aliyun.com/",
    usageGuideUrl: "https://help.aliyun.com/zh/model-studio/model-usage-statistics",
    radar: [80, 25, 77, 76, 92, 56],
    strength: "连过前三图，地图 2 也推进至最后一波；动作合法率 92.3%。",
    weakness: "三张胜图平均仅剩 5 HP，防线容错低；资源转化效率在六模型中偏低。"
  },
  {
    id: "kimi",
    name: "Kimi K3",
    shortName: "Kimi",
    modelId: "moonshot/kimi-k3",
    logo: "assets/kimi.png",
    score: 62.13,
    cleared: 3,
    reached: 4,
    color: "#168cff",
    maps: [
      { score: 88.0, hp: 8, wave: 5, won: true },
      { score: 81.09, hp: 2, wave: 5, won: true },
      { score: 85.28, hp: 7, wave: 5, won: true },
      { score: 56.28, hp: 0, wave: 4, won: false },
      null
    ],
    validity: 89.47,
    damagePerGold: 73.01,
    killRate: 76.75,
    winHp: 28.33,
    requests: 116,
    inputTokens: 748827,
    outputTokens: 202838,
    cachedTokens: 35584,
    inputChars: 1793796,
    outputChars: 613873,
    cost: "¥35.33151",
    billingUrl: "https://platform.kimi.com/console/fee-detail",
    usageGuideUrl: "https://platform.kimi.com/docs/pricing/chat",
    radar: [76, 28, 77, 89, 89, 45],
    strength: "前三图持续通关，地图 0 拿到 88.00；资源转化与操作纪律都较均衡。",
    weakness: "地图 2 仅到第 4 波，飞行怪、冻结与云雾叠加后再规划不够及时。"
  },
  {
    id: "doubao",
    name: "豆包 Seed 2.1 Pro",
    shortName: "豆包",
    modelId: "doubao-seed-2.1-pro",
    logo: "assets/doubao.png",
    score: 47.43,
    cleared: 2,
    reached: 3,
    color: "#6b9fd4",
    maps: [
      { score: 89.44, hp: 10, wave: 5, won: true },
      { score: 78.38, hp: 6, wave: 5, won: true },
      { score: 69.33, hp: 0, wave: 5, won: false },
      null,
      null
    ],
    validity: 66.67,
    damagePerGold: 63.61,
    killRate: 78,
    winHp: 40,
    requests: 44,
    inputTokens: 280317,
    outputTokens: 127689,
    cachedTokens: null,
    inputChars: 556693,
    outputChars: 58107,
    cost: "¥5.45",
    billingUrl: "https://console.volcengine.com/finance/bill/cost-analyse",
    usageGuideUrl: "https://www.volcengine.com/docs/82379/1159199?lang=zh",
    radar: [60, 40, 78, 77, 67, 42],
    strength: "地图 0 拿到 89.44，胜图平均剩 8 HP，开局建防和基础火力不差。",
    weakness: "总动作合法率仅 66.7%；地图 1 单关出现 16 次无效动作，执行稳定性是主要短板。"
  },
  {
    id: "minimax",
    name: "MiniMax M3",
    shortName: "MiniMax",
    modelId: "MiniMax-M3",
    logo: "assets/minimax.png",
    score: 30.89,
    cleared: 1,
    reached: 2,
    color: "#ef315f",
    maps: [
      { score: 85.2, hp: 6, wave: 5, won: true },
      { score: 69.23, hp: 0, wave: 5, won: false },
      null,
      null,
      null
    ],
    validity: 92.11,
    damagePerGold: 82.44,
    killRate: 77.03,
    winHp: 30,
    requests: 69,
    inputTokens: 387962,
    outputTokens: 48942,
    cachedTokens: 13170,
    inputChars: 756336,
    outputChars: 84916,
    cost: "¥0",
    billingUrl: "https://platform.minimaxi.com/console/consumption-detail",
    usageGuideUrl: "https://platform.minimaxi.com/docs/api-reference/text-prompt-caching",
    radar: [40, 30, 77, 100, 92, 28],
    strength: "伤害/金币达 82.44，六模型最高；动作合法率 92.1%，局部资源使用很省。",
    weakness: "只通关首图，地图 1 最后一波归零；高资源效率没有转化为战役推进。"
  }
];

const radarAxes = [
  ["通关进度", "过关数与战败关波次"],
  ["剩余血量", "胜局基地平均剩余 HP"],
  ["击杀率", "击杀 / 击杀与漏怪总数"],
  ["金币效率", "每单位金币造成的伤害"],
  ["有效操作", "被系统接受的动作比例"],
  ["难图表现", "最后到达关卡的成绩"]
];

const mapNames = ["地图 0", "地图 1", "地图 3", "地图 2", "地图 4"];

const chartColors = {
  deepseek: "#3d63ff",
  glm: "#181818",
  glm52: "#181818",
  qwen: "#8b5cf6",
  kimi: "#8b9198",
  doubao: "#ff8a2a",
  minimax: "#ff2f7d"
};

const glm52ScoreSeries = {
  id: "glm52",
  name: "GLM 5.2",
  chartLabel: "GLM 5.2",
  lineDash: [10, 7],
  maps: [
    { score: 92.06 },
    { score: 89.55 },
    { score: 91.66 },
    { score: 68.93 },
    null
  ]
};

const scoreChartSeries = models.flatMap(model => model.id === "glm"
  ? [model, glm52ScoreSeries]
  : [model]
);

function formatNumber(value) {
  if (value === null || value === undefined) return '<span class="missing">-</span>';
  return new Intl.NumberFormat("zh-CN", { notation: "compact", maximumFractionDigits: 2 }).format(value);
}

function formatAuditNumber(value) {
  if (value === null || value === undefined) return '<span class="missing">-</span>';
  return new Intl.NumberFormat("zh-CN").format(value);
}

function formatCacheRate(model) {
  if (model.inputTokens === null || model.inputTokens === undefined || model.cachedTokens === null || model.cachedTokens === undefined) {
    return '<span class="missing">-</span>';
  }
  const totalInput = model.inputTokens + model.cachedTokens;
  if (totalInput === 0) return "0.00%";
  return `${(model.cachedTokens / totalInput * 100).toFixed(2)}%`;
}

function renderHeroStrip() {
  const root = document.querySelector("#heroScoreStrip");
  root.innerHTML = models.map((model, index) => `
    <div class="hero-score" style="--model-color:${model.color}">
      <span class="hero-score-name">#${index + 1} ${model.shortName}</span>
      <strong>${model.score.toFixed(2)}</strong>
    </div>
  `).join("");
}

function renderLeaderboard(sortKey = "score") {
  const root = document.querySelector("#leaderboard");
  const metric = {
    score: {
      axis: "横轴：战役得分（0-100）",
      width: model => model.score,
      value: model => model.score.toFixed(2),
      meta: model => `${model.cleared} / 5`,
      metaLabel: "通关地图"
    },
    cleared: {
      axis: "横轴：已通关地图数（共 5 张）",
      width: model => model.cleared / 5 * 100,
      value: model => `${model.cleared} / 5`,
      meta: model => model.score.toFixed(2),
      metaLabel: "战役得分"
    },
    validity: {
      axis: "横轴：有效操作率（被系统接受的动作比例）",
      width: model => model.validity,
      value: model => `${model.validity.toFixed(1)}%`,
      meta: model => model.score.toFixed(2),
      metaLabel: "战役得分"
    }
  }[sortKey];
  const sorted = [...models].sort((a, b) => {
    if (sortKey === "cleared") return b.cleared - a.cleared || b.score - a.score;
    if (sortKey === "validity") return b.validity - a.validity || b.score - a.score;
    return b.score - a.score;
  });
  document.querySelector("#leaderAxisLabel").textContent = metric.axis;
  root.innerHTML = sorted.map((model, index) => `
    <article class="leader-row" style="--model-color:${model.color};--bar-width:${metric.width(model)}%">
      <div class="leader-rank">${String(index + 1).padStart(2, "0")}</div>
      <div class="leader-name"><img src="${model.logo}" alt=""><span class="leader-name-copy"><strong>${model.name}</strong><span>${model.modelId}</span></span></div>
      <div class="leader-track" aria-label="${metric.axis}：${metric.value(model)}"><span></span></div>
      <div class="leader-score">${metric.value(model)}</div>
      <div class="leader-meta"><strong>${metric.meta(model)}</strong><span>${metric.metaLabel}</span></div>
    </article>
  `).join("");
}

function renderMapMatrix() {
  const root = document.querySelector("#mapMatrix");
  const heads = [
    '<div class="matrix-cell matrix-head">模型 / 战线</div>',
    ...mapNames.map((name, index) => `<div class="matrix-cell matrix-head">${name}<span>第 ${index + 1} 关</span></div>`)
  ];
  const rows = models.flatMap(model => {
    const nameCell = `<div class="matrix-cell matrix-name" style="--model-color:${model.color}"><strong>${model.shortName}</strong><span class="matrix-detail">战役 ${model.score.toFixed(2)}</span></div>`;
    const mapCells = model.maps.map(stage => {
      if (!stage) return '<div class="matrix-cell locked"><span class="matrix-score">—</span><span class="matrix-detail">未解锁</span></div>';
      const className = stage.won ? "win" : "loss";
      const detail = stage.won ? `WIN / ${stage.hp} HP` : `LOST / 第 ${stage.wave} 波`;
      return `<div class="matrix-cell ${className}"><span class="matrix-score">${stage.score.toFixed(2)}</span><span class="matrix-detail">${detail}</span></div>`;
    });
    return [nameCell, ...mapCells];
  });
  root.innerHTML = [...heads, ...rows].join("");
}

function renderRadarLegend() {
  document.querySelector("#radarLegend").innerHTML = radarAxes.map(([title, detail]) => `
    <div class="legend-item"><strong>${title}</strong><span>${detail}</span></div>
  `).join("");
}

function renderProfiles() {
  const root = document.querySelector("#profileGrid");
  root.innerHTML = models.map(model => `
    <article class="profile-card" style="--model-color:${model.color}">
      <div class="radar-wrap"><canvas class="radar-canvas" data-model="${model.id}" width="600" height="600" aria-label="${model.name} 能力雷达图"></canvas></div>
      <div class="profile-copy">
        <div class="profile-topline"><h3><img src="${model.logo}" alt="">${model.name}</h3><span class="profile-score">${model.score.toFixed(2)}</span></div>
        <p class="profile-result">${model.cleared} / 5 通关 · 推进至第 ${model.reached} 关 · 动作合法率 ${model.validity.toFixed(1)}%</p>
        <p class="profile-fact"><strong>高分点：</strong>${model.strength}</p>
        <p class="profile-fact weak"><strong>短板：</strong>${model.weakness}</p>
        <div class="profile-metrics">
          <div><span>击杀率</span><strong>${model.killRate.toFixed(1)}%</strong></div>
          <div><span>伤害 / 金币</span><strong>${model.damagePerGold.toFixed(2)}</strong></div>
          <div><span>输入 TOKEN</span><strong>${model.inputTokens === null ? "-" : formatNumber(model.inputTokens)}</strong></div>
          <div><span>费用</span><strong>${model.cost || "未记录"}</strong></div>
        </div>
      </div>
    </article>
  `).join("");

  root.querySelectorAll("canvas").forEach(canvas => {
    const model = models.find(item => item.id === canvas.dataset.model);
    drawRadar(canvas, model.radar, model.color);
  });
}

function hexToRgba(hex, alpha) {
  const value = hex.replace("#", "");
  const number = Number.parseInt(value, 16);
  return `rgba(${(number >> 16) & 255}, ${(number >> 8) & 255}, ${number & 255}, ${alpha})`;
}

function drawRadar(canvas, values, color) {
  const ctx = canvas.getContext("2d");
  const size = canvas.width;
  const center = size / 2;
  const radius = size * 0.32;
  const labels = radarAxes.map(item => item[0]);
  ctx.clearRect(0, 0, size, size);
  ctx.lineJoin = "miter";

  for (let level = 5; level >= 1; level -= 1) {
    const levelRadius = radius * (level / 5);
    ctx.beginPath();
    labels.forEach((_, index) => {
      const angle = -Math.PI / 2 + index * (Math.PI * 2 / labels.length);
      const x = center + Math.cos(angle) * levelRadius;
      const y = center + Math.sin(angle) * levelRadius;
      if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath();
    ctx.strokeStyle = level === 5 ? "#6f7b7b" : "#c8c4b9";
    ctx.lineWidth = level === 5 ? 3 : 2;
    ctx.stroke();
  }

  labels.forEach((label, index) => {
    const angle = -Math.PI / 2 + index * (Math.PI * 2 / labels.length);
    const x = center + Math.cos(angle) * radius;
    const y = center + Math.sin(angle) * radius;
    ctx.beginPath();
    ctx.moveTo(center, center);
    ctx.lineTo(x, y);
    ctx.strokeStyle = "#b5b3aa";
    ctx.lineWidth = 2;
    ctx.stroke();

    const labelRadius = radius + 48;
    const labelX = center + Math.cos(angle) * labelRadius;
    const labelY = center + Math.sin(angle) * labelRadius;
    ctx.fillStyle = "#3c4547";
    ctx.font = "700 22px ui-monospace, SFMono-Regular, Menlo, monospace";
    ctx.textAlign = Math.cos(angle) > 0.25 ? "left" : Math.cos(angle) < -0.25 ? "right" : "center";
    ctx.textBaseline = Math.sin(angle) > 0.35 ? "top" : Math.sin(angle) < -0.35 ? "bottom" : "middle";
    ctx.fillText(label, labelX, labelY);
  });

  ctx.beginPath();
  values.forEach((value, index) => {
    const angle = -Math.PI / 2 + index * (Math.PI * 2 / values.length);
    const pointRadius = radius * (Math.max(0, Math.min(100, value)) / 100);
    const x = center + Math.cos(angle) * pointRadius;
    const y = center + Math.sin(angle) * pointRadius;
    if (index === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.closePath();
  ctx.fillStyle = hexToRgba(color, 0.24);
  ctx.strokeStyle = color;
  ctx.lineWidth = 5;
  ctx.fill();
  ctx.stroke();

  values.forEach((value, index) => {
    const angle = -Math.PI / 2 + index * (Math.PI * 2 / values.length);
    const pointRadius = radius * (value / 100);
    const x = center + Math.cos(angle) * pointRadius;
    const y = center + Math.sin(angle) * pointRadius;
    ctx.fillStyle = "#fffdf7";
    ctx.fillRect(x - 7, y - 7, 14, 14);
    ctx.strokeStyle = color;
    ctx.lineWidth = 4;
    ctx.strokeRect(x - 7, y - 7, 14, 14);
  });
}

const scoreChartState = {
  visible: new Set(scoreChartSeries.map(model => model.id)),
  progress: 1,
  frame: null,
  points: [],
  minScore: 40
};

function drawScoreLineChart(progress = 1) {
  const canvas = document.querySelector("#scoreLineChart");
  const ctx = canvas.getContext("2d");
  const pixelRatio = Math.max(1, window.devicePixelRatio || 1);
  const width = Math.max(280, Math.round(canvas.clientWidth));
  const height = Math.max(280, Math.round(canvas.clientHeight));
  const targetWidth = Math.round(width * pixelRatio);
  const targetHeight = Math.round(height * pixelRatio);
  if (canvas.width !== targetWidth || canvas.height !== targetHeight) {
    canvas.width = targetWidth;
    canvas.height = targetHeight;
  }
  ctx.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0);
  const compact = width < 620;
  const plot = compact
    ? { left: 42, top: 20, right: width - 10, bottom: height - 48 }
    : { left: 66, top: 30, right: width - 24, bottom: height - 62 };
  const plotWidth = plot.right - plot.left;
  const plotHeight = plot.bottom - plot.top;
  const minScore = scoreChartState.minScore;
  const maxScore = 100;
  const xFor = index => plot.left + (plotWidth * index / (mapNames.length - 1));
  const yFor = score => plot.bottom - ((score - minScore) / (maxScore - minScore)) * plotHeight;

  ctx.clearRect(0, 0, width, height);
  ctx.fillStyle = "#fffdf7";
  ctx.fillRect(0, 0, width, height);
  ctx.lineJoin = "miter";
  ctx.lineCap = "butt";

  const tickStep = minScore >= 60 ? 5 : 10;
  const firstTick = Math.ceil(minScore / tickStep) * tickStep;
  const yTicks = [];
  for (let score = firstTick; score <= 100; score += tickStep) yTicks.push(score);
  if (!yTicks.includes(minScore)) yTicks.unshift(minScore);
  yTicks.forEach(score => {
    const y = yFor(score);
    ctx.beginPath();
    ctx.moveTo(plot.left, y);
    ctx.lineTo(plot.right, y);
    ctx.strokeStyle = score % 20 === 0 ? "#b9b7ae" : "#dedad0";
    ctx.lineWidth = score % 20 === 0 ? 1.5 : 1;
    ctx.stroke();
    ctx.fillStyle = "#687173";
    ctx.font = `700 ${compact ? 11 : 14}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    ctx.fillText(String(score), plot.left - 14, y);
  });

  mapNames.forEach((name, index) => {
    const x = xFor(index);
    ctx.beginPath();
    ctx.moveTo(x, plot.top);
    ctx.lineTo(x, plot.bottom);
    ctx.strokeStyle = "#e4dfd4";
    ctx.lineWidth = 1;
    ctx.stroke();
    ctx.fillStyle = "#3a4344";
    ctx.font = `800 ${compact ? 11 : 15}px ui-monospace, SFMono-Regular, Menlo, monospace`;
    ctx.textAlign = "center";
    ctx.textBaseline = "top";
    ctx.fillText(name, x, plot.bottom + 22);
  });

  scoreChartState.points = [];

  ctx.save();
  ctx.beginPath();
  ctx.rect(plot.left - 8, plot.top - 8, plotWidth + 16, plotHeight + 16);
  ctx.clip();

  scoreChartSeries.forEach(model => {
    if (!scoreChartState.visible.has(model.id)) return;
    const values = model.maps
      .map((stage, index) => stage ? { index, score: stage.score } : null)
      .filter(Boolean);
    if (!values.length) return;

    const segmentCount = Math.max(1, values.length - 1);
    const distance = progress * segmentCount;
    ctx.beginPath();
    const lineColor = chartColors[model.id];
    ctx.strokeStyle = lineColor;
    ctx.lineWidth = compact ? 3 : 4;
    ctx.setLineDash(model.lineDash || []);
    ctx.moveTo(xFor(values[0].index), yFor(values[0].score));
    for (let index = 1; index < values.length; index += 1) {
      const previous = values[index - 1];
      const current = values[index];
      const completed = Math.min(1, Math.max(0, distance - (index - 1)));
      if (completed <= 0) break;
      const x = xFor(previous.index) + (xFor(current.index) - xFor(previous.index)) * completed;
      const y = yFor(previous.score) + (yFor(current.score) - yFor(previous.score)) * completed;
      ctx.lineTo(x, y);
      if (completed < 1) break;
    }
    ctx.stroke();
    ctx.setLineDash([]);

    values.forEach((point, index) => {
      const pointProgress = values.length === 1 ? progress : Math.min(1, Math.max(0, distance - Math.max(0, index - 1)));
      if (pointProgress < 1 && index > 0) return;
      const x = xFor(point.index);
      const y = yFor(point.score);
      const pointSize = compact ? 5 : 6;
      ctx.fillStyle = "#fffdf7";
      ctx.fillRect(x - pointSize, y - pointSize, pointSize * 2, pointSize * 2);
      ctx.strokeStyle = lineColor;
      ctx.lineWidth = compact ? 2.5 : 3;
      ctx.strokeRect(x - pointSize, y - pointSize, pointSize * 2, pointSize * 2);
      scoreChartState.points.push({ model, point, x, y });
    });
  });
  ctx.restore();
}

function animateScoreLineChart() {
  if (scoreChartState.frame) cancelAnimationFrame(scoreChartState.frame);
  const startedAt = performance.now();
  const duration = 900;
  const tick = now => {
    const elapsed = Math.min(1, (now - startedAt) / duration);
    scoreChartState.progress = 1 - Math.pow(1 - elapsed, 3);
    drawScoreLineChart(scoreChartState.progress);
    if (elapsed < 1) scoreChartState.frame = requestAnimationFrame(tick);
  };
  scoreChartState.frame = requestAnimationFrame(tick);
}

function renderScoreChart() {
  const canvas = document.querySelector("#scoreLineChart");
  const legend = document.querySelector("#scoreChartLegend");
  const tooltip = document.querySelector("#scoreChartTooltip");

  legend.innerHTML = scoreChartSeries.map(model => `
    <button class="chart-key active${model.lineDash ? " is-dashed" : ""}" type="button" data-model="${model.id}" style="--model-color:${chartColors[model.id]}" aria-pressed="true">
      <span></span>${model.chartLabel || model.shortName}
    </button>
  `).join("");

  legend.querySelectorAll("button").forEach(button => {
    button.addEventListener("click", () => {
      const id = button.dataset.model;
      if (scoreChartState.visible.has(id)) scoreChartState.visible.delete(id);
      else scoreChartState.visible.add(id);
      button.classList.toggle("active", scoreChartState.visible.has(id));
      button.setAttribute("aria-pressed", String(scoreChartState.visible.has(id)));
      animateScoreLineChart();
    });
  });

  canvas.addEventListener("mousemove", event => {
    const rect = canvas.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const closest = scoreChartState.points
      .map(point => ({ ...point, distance: Math.hypot(point.x - x, point.y - y) }))
      .sort((a, b) => a.distance - b.distance)[0];
    if (!closest || closest.distance > 28) {
      tooltip.classList.remove("show");
      return;
    }
    tooltip.innerHTML = `<strong>${closest.model.name}</strong><span>${mapNames[closest.point.index]} · ${closest.point.score.toFixed(2)} 分</span>`;
    tooltip.style.left = `${closest.point.x}px`;
    tooltip.style.top = `${closest.point.y}px`;
    tooltip.classList.add("show");
  });
  canvas.addEventListener("mouseleave", () => tooltip.classList.remove("show"));

  const zoom = document.querySelector("#scoreChartZoom");
  const zoomValue = document.querySelector("#scoreChartZoomValue");
  const updateZoom = value => {
    scoreChartState.minScore = Number(value);
    zoom.value = String(value);
    zoomValue.value = `${value}-100`;
    drawScoreLineChart(1);
  };
  zoom.addEventListener("input", () => updateZoom(zoom.value));
  document.querySelector("#scoreChartReset").addEventListener("click", () => updateZoom(40));

  const resizeObserver = new ResizeObserver(() => drawScoreLineChart(scoreChartState.progress));
  resizeObserver.observe(canvas);

  drawScoreLineChart();
  const observer = new IntersectionObserver(entries => {
    if (entries.some(entry => entry.isIntersecting)) {
      animateScoreLineChart();
      observer.disconnect();
    }
  }, { threshold: 0.25 });
  observer.observe(canvas);
}

function renderAuditRows() {
  document.querySelector("#auditRows").innerHTML = models.map(model => `
    <tr style="--model-color:${model.color}">
      <td><span class="audit-model">${model.shortName}</span></td>
      <td>${model.requests}</td>
      <td>${formatAuditNumber(model.inputTokens)}</td>
      <td>${formatAuditNumber(model.outputTokens)}</td>
      <td>${formatAuditNumber(model.cachedTokens)}</td>
      <td>${formatCacheRate(model)}</td>
      <td>${formatNumber(model.inputChars)}</td>
      <td>${formatNumber(model.outputChars)}</td>
      <td><span class="audit-cost">${model.cost || '<span class="missing">-</span>'}</span></td>
      <td class="audit-links"><a href="${model.billingUrl}" target="_blank" rel="noreferrer">账单</a><a href="${model.usageGuideUrl}" target="_blank" rel="noreferrer">Token 指引</a></td>
    </tr>
  `).join("");
}

const recordingCosts = {
  deepseek: 3.43,
  glm: 0,
  qwen: 6.39132,
  kimi: 35.33151,
  doubao: 5.45,
  minimax: 0
};

function renderCostChart() {
  const root = document.querySelector("#recordingCostChart");
  const chartMax = 40;
  root.innerHTML = models.map(model => {
    const value = recordingCosts[model.id];
    const height = value / chartMax * 100;
    return `
      <div class="cost-column" style="--model-color:${model.color};--bar-height:${height}%">
        <strong class="cost-value">${model.cost}</strong>
        <div class="cost-bar-stage" aria-label="${model.shortName} 录制版实付 ${model.cost}">
          <span class="cost-bar${value === 0 ? " is-zero" : ""}"></span>
        </div>
        <span class="cost-name">${model.shortName}</span>
      </div>
    `;
  }).join("");
}

document.querySelectorAll(".sort-control button").forEach(button => {
  button.addEventListener("click", () => {
    document.querySelectorAll(".sort-control button").forEach(item => item.classList.remove("active"));
    button.classList.add("active");
    renderLeaderboard(button.dataset.sort);
  });
});

renderHeroStrip();
renderLeaderboard();
renderMapMatrix();
renderScoreChart();
renderRadarLegend();
renderProfiles();
renderAuditRows();
renderCostChart();
