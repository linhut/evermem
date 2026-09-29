/*!
 * 恒忆 Evermem (pmem) · Copyright (c) 2026 Jose-AI · 版权所有
 * 仓库: https://github.com/linhut/evermem
 * 官网: https://www.linhut.cn
 * 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）
 */

/* ============================================================
   渠道模块（备份与同步）
   ------------------------------------------------------------
   分层：
     视图装配层  index.js      —— 只负责 8 个视图的路由
     本模块      channel.js    —— 渠道的渲染 / 交互 / 状态
     领域层      backup.py     —— 字段契约、留空保留、混淆、执行

   三条硬约束：
     1) 字段 / 分组 / 必填 / 敏感度 一律取自 /api/backup/providers，
        本文件不维护第二份字段表（此前 backup.py、行编辑器、向导各写一份）。
     2) 状态判定只有 describe() 一处实现，徽标、标题计数、图例全部消费它。
     3) 行用 data-ci 定位而非 DOM 序号；保存走「上次快照 + 单行覆盖」，
        单个渠道的操作不再顺带提交别人未确认的编辑。
   ============================================================ */

const BK = (function () {
  'use strict';

  const $ = s => document.querySelector(s);
  const J = (u, o) => fetch(u, Object.assign({ headers: { 'Content-Type': 'application/json' } }, o || {})).then(r => r.json());
  const PJ = (u, b) => J(u, { method: 'POST', body: JSON.stringify(b || {}) });

  /* 渠道类型短标签（行首徽标）；与后端 label 不同：后端 label 用于步骤 1 的选择卡 */
  const TYPE_TAG = { local: t('镜像'), archive: t('快照'), remote: t('远端'), mail: t('邮箱'), s3: t('对象存储'), 'baidu-pan': t('网盘冷备') };
  /* 色板：命名与设计令牌对齐，避免内联色值散落 */
  const TONE = {
    success: ['var(--success)', 'var(--success-bg)'],
    danger: ['var(--danger)', 'var(--danger-bg)'],
    warning: ['var(--warning)', 'var(--warning-bg)'],
    muted: ['var(--text2)', 'var(--surface2)'],
  };

  /* 设计稿 03：服务商预设。只是 Endpoint/Region 的预填值，不参与字段定义 */
  const S3_PRESETS = [
    { id: 'aliyun-oss', label: t('阿里云 OSS'), endpoint: 'https://oss-cn-hangzhou.aliyuncs.com', region: 'oss-cn-hangzhou' },
    { id: 'tencent-cos', label: t('腾讯云 COS'), endpoint: 'https://cos.ap-guangzhou.myqcloud.com', region: 'ap-guangzhou' },
    { id: 'aws-s3', label: 'AWS S3', endpoint: 'https://s3.amazonaws.com', region: 'us-east-1' },
    { id: 'minio', label: 'MinIO', endpoint: 'http://127.0.0.1:9000', region: 'us-east-1' },
    { id: 'baidu-bos', label: t('百度智能云 BOS'), endpoint: 'https://s3.bj.bcebos.com', region: 'bj' },
  ];
  const STEP_TITLES = [t('选择渠道类型'), t('连接参数'), t('加密与策略'), t('确认并保存')];

  /* 模块状态：后端返回的渠道投影快照 + 向导会话 */
  const S = { raw: [], schema: {}, step: 1, type: null, draft: {}, preset: null, tested: false, testing: false, testMsg: '' };

  const fmtBytes = b => b >= 1048576 ? (b / 1048576).toFixed(1) + ' MB'
    : b >= 1024 ? (b / 1024).toFixed(1) + ' KB' : (b || 0) + ' B';

  /* ---------------- Schema 访问器：唯一入口 ---------------- */

  const spec = t => (S.schema && S.schema[t]) || null;
  const fieldsOf = t => ((spec(t) || {}).fields) || [];
  const field = (t, k) => fieldsOf(t).find(f => f.k === k) || null;
  const layoutOf = t => ((spec(t) || {}).layout) || fieldsOf(t).map(f => ({ k: f.k }));
  const stepFields = (t, step) => fieldsOf(t).filter(f => (f.step || 'conn') === step);

  /** 渠道是否缺凭证（设计稿 04「未配置」态的判定，集中在此） */
  function missingCreds(c) {
    if (c.type === 's3') return !(c.endpoint && c.bucket && c.access_key && c.secret_key_set);
    if (c.type === 'baidu-pan') return !c.archive_password_set;
    if (c.type === 'mail') return !(c.smtp && c.smtp.host);
    return !c.target;
  }

  /* ---------------- 状态：单一真源（对应设计稿 04 状态矩阵） ---------------- */

  function describe(c) {
    const n = c.fail_count || 1;
    if (c.ok === false) {
      const err = String(c.last_error || t('连接失败')).slice(0, 40);
      return { tone: 'danger', icon: '✗', label: `${t('失败')} ×${n}`, note: `${err} · ${t('已重试')} ${n} ${t('次')}` };
    }
    if (c.type === 'baidu-pan') {
      return { tone: 'warning', icon: '▣', label: t('冷备 · 手动上传'), note: t('百度网盘 · 不自动上传 · 已生成归档包待手动上传') };
    }
    if (missingCreds(c)) {
      return { tone: 'muted', icon: '○', label: t('未配置'), note: t('尚未填写凭证 · 点击「新增渠道」开始') };
    }
    if (c.ok === true) {
      const ver = c.verified === false ? t('校验未过') : t('校验通过');
      return { tone: 'success', icon: '●', label: t('健康'),
        note: `${t('上次成功')} · ${ver} · ${fmtBytes(c.last_bytes)} / ${c.last_files || 0} ${t('文件')}` };
    }
    if (c.due) {
      return { tone: 'warning', icon: '⚠', label: t('警告'), note: `${t('已到期未备份')} · ${t('频率每')} ${c.frequency_hours}h` };
    }
    return { tone: 'muted', icon: '○', label: t('未执行'), note: t('尚无备份记录 · 点「立即备份」开始') };
  }

  const badgeHTML = d => {
    const [f, b] = TONE[d.tone] || TONE.muted;
    return `<span class="badge" style="color:${f};background:${b}">${d.icon} ${d.label}</span>`;
  };

  /** 图例由 describe() 反推生成 —— 图例与行徽标不可能再各说一套 */
  function legendHTML() {
    const samples = [
      { ok: true, verified: true, last_bytes: 13002342, last_files: 290, type: 's3', access_key: 'a', secret_key_set: true, bucket: 'b', endpoint: 'e' },
      { ok: false, fail_count: 3, last_error: '连接超时', type: 's3' },
      { type: 's3' },
      { type: 'baidu-pan', archive_password_set: true },
    ];
    return samples.map(describe).map(d => {
      const [f, b] = TONE[d.tone] || TONE.muted;
      return `<span style="display:inline-flex;align-items:center;gap:5px"><span class="badge" style="color:${f};background:${b}">${d.icon} ${d.label}</span>${d.note}</span>`;
    }).join('<span style="opacity:.4"> · </span>');
  }

  /* ---------------- 渲染 ---------------- */

  const rowSummary = c => {
    const p = [];
    if (c.type === 's3') p.push(c.bucket || '—', String(c.endpoint || '').replace(/^https?:\/\//, ''));
    else if (c.type === 'baidu-pan') p.push(c.target || '—', '归档包 + UPLOAD.md');
    else p.push(c.target || '—');
    if (c.frequency_hours) p.push(`每 ${c.frequency_hours}h`);
    if (c.last && c.last !== '-') p.push('上次 ' + c.last.slice(5, 16));
    return p.join(' · ');
  };

  /** 字段卡（设计稿 03）：一张卡承载主字段 + 可选的同行副字段 */
  function fieldCardPrimary(t, row, val) {
    const a = field(t, row.k), aid = a ? a.label : row.k;
    const b = row.companion ? field(t, row.companion) : null;
    const label = b ? `${aid}${row.sep || ' · '}${b.label}` : aid;
    const req = (a && a.required) || (b && b.required);
    return `<div class="bkfield">
      <span class="bkflabel">${label}${req ? ' <em>*</em>' : ''}</span>
      <div class="bkfrow">
        ${input(t, a, val)}${b ? input(t, b, val, true) : ''}
      </div>${(a && a.hint) || (b && b.hint) ? `<span class="bkfhint">${((a && a.hint) || (b && b.hint))}</span>` : ''}
    </div>`;
  }

  function input(t, f, val, companion) {
    if (!f) return '';
    const v = val[f.k];
    if (f.type === 'password') {
      /* 涉密字段：后端只回传布尔位，有值时不回显明文，留空＝沿用旧值 */
      const has = f.k === 'secret_key' ? val.secret_key_set : val.archive_password_set;
      return `<input data-k="${f.k}" type="password" autocomplete="new-password"
        placeholder="${has ? '已保存（留空则不变更）' : (f.placeholder || '')}" />`;
    }
    const raw = v === undefined || v === null || v === '' ? (f.default !== undefined ? f.default : '') : v;
    return `<input data-k="${f.k}" type="${f.type === 'number' ? 'number' : 'text'}" value="${String(raw).replace(/"/g, '&quot;')}"
      placeholder="${f.placeholder || ''}" aria-label="${f.label}"${companion ? ' style="flex:0 0 38%"' : ''} />`;
  }

  /** 行内编辑面板：与向导共用同一套字段卡渲染 */
  function editorHTML(c) {
    const t = c.type;
    const conn = layoutOf(t).map(r => fieldCardPrimary(t, r, c)).join('');
    const policy = stepFields(t, 'policy').map(f =>
      `<div class="bkfield"><span class="bkflabel">${f.label}${f.required ? ' <em>*</em>' : ''}</span>
        <div class="bkfrow">${input(t, f, c)}</div>
        ${f.hint ? `<span class="bkfhint">${f.hint}</span>` : ''}</div>`).join('');
    const smtp = t === 'mail' ? `<div class="bkfield"><span class="bkflabel">SMTP 服务器 · 端口</span>
        <div class="bkfrow"><input data-k="smtp_host" value="${((c.smtp || {}).host) || ''}" placeholder="smtp.example.com" />
        <input data-k="smtp_port" type="number" value="${((c.smtp || {}).port) || 465}" style="flex:0 0 30%" /></div></div>
      <div class="bkfield"><span class="bkflabel">SMTP 用户 · 密码</span>
        <div class="bkfrow"><input data-k="smtp_user" value="${((c.smtp || {}).user) || ''}" />
        <input data-k="smtp_pass" type="password" autocomplete="new-password" placeholder="留空读环境变量" style="flex:0 0 38%" /></div></div>` : '';
    const dsc = describe(c);
    return `<div class="pane bkeditor">
      <div class="bkrow-top">
        <input data-k="name" value="${String(c.name).replace(/"/g, '&quot;')}" style="width:160px;font-weight:600" aria-label="渠道名称" />
        <label class="bkcheck"><input data-k="enabled" type="checkbox" ${c.enabled ? 'checked' : ''}>${t('启用')}</label>
        <span style="flex:1"></span>
        <button class="btn plain small" data-bk="run">${t('立即备份')}</button>
        <button class="btn ghost small" data-bk="check">${t('校验')}</button>
        <button class="btn ghost small" data-bk="restore">${t('恢复')}</button>
        <button class="btn danger small" data-bk="del">${t('删除')}</button>
      </div>
      <div class="bkgrid">${conn}${smtp}${policy}
        <div class="bkfield"><span class="bkflabel">备份范围</span>
          <span class="bkfrow" style="gap:12px">${[['notes', '笔记'], ['events', '事件'], ['index', '索引'], ['meta', '配置']]
        .map(([k, l]) => `<label class="bkcheck"><input data-scope="${k}" type="checkbox" ${(c.scope || []).includes(k) ? 'checked' : ''}>${l}</label>`).join('')}</span>
        </div>
      </div>
      ${dsc.tone === 'danger' ? `<div class="bkline danger">${dsc.note} · <a data-bk="log" style="cursor:pointer;text-decoration:underline">查看日志</a></div>` : ''}
      ${t === 'baidu-pan' ? '<div class="bkline warning">百度网盘官方接口不稳定、自动化涉违规风险——本渠道只生成加密归档包与上传清单（UPLOAD.md），请按清单手动拖入网盘。</div>' : ''}
      ${t === 's3' && missingCreds(c) ? '<div class="bkline warning">凭证与归档密码可后填：留空＝沿用已存值，不影响其他字段保存。</div>' : ''}
    </div>`;
  }

  function rowHTML(c) {
    const d = describe(c);
    return `<details class="bkrow" data-ci="${String(c.name).replace(/"/g, '&quot;')}" data-type="${c.type}"${c.enabled ? '' : ' style="opacity:.72"'}>
      <summary>
        <span class="badge" style="color:var(--accent);background:var(--accent-bg)">${TYPE_TAG[c.type] || c.type}</span>
        <b style="font-size:13px">${String(c.name)}</b>
        <span class="sub" style="flex:1;min-width:110px">${rowSummary(c)}</span>
        ${badgeHTML(d)}${c.due ? '<span class="badge" style="color:var(--warning);background:var(--warning-bg)">待备份</span>' : ''}
      </summary>
      ${editorHTML(c)}
    </details>`;
  }

  function viewHTML() {
    return `<div style="width:100%;max-width:920px">
  <div style="display:flex;align-items:center;gap:10px;margin:2px 0 16px;flex-wrap:wrap">
    <h2 style="margin:0;font-size:20px;font-weight:600">${t('备份与同步')}</h2>
    <span class="sub" id="bkStatus" style="flex:1;min-width:120px">${t('读取中…')}</span>
    <button class="btn ghost" data-bk="wizard">＋ ${t('新增渠道')}</button>
    <button class="btn primary" data-bk="run-all">${t('立即备份')}</button>
  </div>

  <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin-bottom:14px">
    <div class="pane"><div class="sub">${t('上次备份')}</div><div id="bkKpi1" style="font-size:17px;font-weight:600;margin-top:3px">—</div><div class="sub" id="bkKpi1s">—</div></div>
    <div class="pane"><div class="sub">${t('云端占用（加密包）')}</div><div id="bkKpi2" style="font-size:17px;font-weight:600;margin-top:3px">—</div><div class="sub" id="bkKpi2s">${t('各渠道最近一次估算')}</div></div>
    <div class="pane"><div class="sub">${t('下次计划')}</div><div id="bkKpi3" style="font-size:17px;font-weight:600;margin-top:3px">—</div><div class="sub" id="bkKpi3s">—</div></div>
  </div>

  <div class="pane" style="margin-bottom:14px">
    <div style="display:flex;align-items:flex-start;gap:12px;flex-wrap:wrap">
      <div style="flex:1;min-width:240px">
        <div style="font-size:13px;font-weight:600">${t('主备份位置')}</div>
        <div class="sub">${t('本地是事实源，单向同步到云端目录（云盘挂载 / NAS）。加密在出本机前完成，云端只有密文。')}</div>
      </div>
      <span class="badge" id="bkMainState" style="color:var(--text2);background:var(--surface2)">${t('读取中…')}</span>
    </div>
    <div style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <select id="bkMain" style="flex:1;min-width:200px"><option value="">正在探测本机可用位置…</option></select>
      <input id="bkCustom" type="text" placeholder="或用自定义路径（云盘 / NAS / 挂载点）" style="flex:1;min-width:200px" />
      <button class="btn primary" id="bkSaveMainBtn" data-bk="save-main">${t('保存并立即备份')}</button>
      <button class="btn plain" data-bk="run-all">${t('立即备份全部')}</button>
    </div>
  </div>

  <div id="bkGroupTags" style="display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px"></div>
  <div id="bkChHead" class="section-title" style="margin:4px 0 8px">${t('备份渠道')}</div>
  <div id="bkChannels" style="display:flex;flex-direction:column;gap:8px"></div>
  <div id="bkLegend" class="sub" style="margin-top:8px;display:flex;gap:10px;flex-wrap:wrap"></div>
  <button class="dash-card" style="margin-top:10px" data-bk="wizard">＋ ${t('新增渠道')}${t('（对象存储 · S3 兼容 / 百度网盘冷备 / 快照 / 远端 / 邮箱）')}</button>

  <div class="pane" style="margin-top:12px">
    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <div style="font-size:13px;font-weight:600">备份日志</div><div style="flex:1"></div>
      <button class="btn ghost small" data-bk="log">刷新</button>
    </div>
    <div id="bkLogArea" class="log-box" style="margin-top:10px">点「刷新」查看最近 50 行</div>
  </div>

  <details style="margin-top:12px">
    <summary style="cursor:pointer;font-size:12.5px;color:var(--text2)">${t('高级设置（自动备份 / 告警邮箱）')}</summary>
    <div style="margin-top:12px;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
      <label style="display:flex;gap:6px;align-items:center;font-size:12.5px"><input id="bkAuto" type="checkbox" style="transform:scale(1.15)">自动备份（按各渠道频率，服务常驻轮询）</label>
      <label style="font-size:12px;color:var(--text2)">${t('告警邮箱')} <input id="bkAlert" type="text" placeholder="me@example.com" style="width:160px" /></label>
      <button class="btn ghost small" data-bk="save-settings">保存设置</button>
    </div>
  </details></div>`;
  }

  /* ---------------- 收集：唯一收集器 ---------------- */

  function collect(el) {
    const g = k => { const e = el.querySelector(`[data-k="${k}"]`); return e ? (e.type === 'checkbox' ? e.checked : e.value.trim()) : undefined; };
    const type = el.dataset.type;
    const c = { type, name: g('name') || type, enabled: !!g('enabled'), target: g('target') || '',
      scope: [...el.querySelectorAll('[data-scope]:checked')].map(x => x.dataset.scope) };
    const freq = parseInt(g('frequency_hours') || '', 10);
    if (!isNaN(freq)) c.frequency_hours = freq;
    const ret = parseInt(g('retention') || '', 10);
    if (!isNaN(ret)) c.retention = ret;
    if (type === 'remote') { const p = parseInt(g('ssh_port') || '', 10); if (!isNaN(p)) c.ssh_port = p; }
    if (type === 'mail') {
      const port = parseInt(g('smtp_port') || '', 10);
      c.smtp = { host: g('smtp_host') || '', user: g('smtp_user') || '' };
      if (!isNaN(port)) c.smtp.port = port;
      if (g('smtp_pass')) c.smtp.pass = g('smtp_pass');
    }
    /* 连接 / 策略字段由 schema 驱动；涉密字段空串不提交，交由后端「留空＝沿用旧值」裁决 */
    for (const f of fieldsOf(type)) {
      if (['target', 'frequency_hours', 'retention', 'ssh_port'].includes(f.k)) continue;
      if (['smtp_host', 'smtp_port', 'smtp_user', 'smtp_pass'].includes(f.k)) continue;
      const v = g(f.k);
      if (v === undefined) continue;
      if (v === '' ) { if (!f.sensitive) c[f.k] = ''; continue; }
      c[f.k] = v;
    }
    return c;
  }

  /** 完整渠道列表：DOM 中已渲染的行取编辑值，其余（含主备份）取上次快照 */
  function channelList() {
    const dom = {};
    document.querySelectorAll('#bkChannels [data-ci]').forEach(el => { dom[el.dataset.ci] = collect(el); });
    const rest = S.raw.filter(c => !(c.name in dom) && c.name !== '主备份');
    return [...rest, ...Object.values(dom)];
  }

  /* ---------------- 加载与保存 ---------------- */

  const scopeLabel = c => (c.scope || []).map(k => ({ notes: '笔记', events: '事件', index: '索引', meta: '配置' }[k] || k)).join('、');

  async function load() {
    /* 异步保存返回时用户可能已切走视图，此时视图元素不存在，直接放弃刷新 */
    if (!$('#bkStatus')) return;
    let d = null;
    try { d = await J('/api/backup'); } catch (e) { d = null; }
    if (!d) {
      $('#bkChannels').innerHTML = '<div class="errbox">备份服务未响应，请确认 pmem 服务在运行后重试。</div>';
      $('#bkStatus').textContent = '读取失败';
      return;
    }
    S.raw = d.channels || [];
    const all = S.raw;
    /* KPI 三卡（设计稿 02） */
    const hist = d.history || [];
    $('#bkKpi1').textContent = hist[0] ? hist[0].at.slice(5, 16) : '—';
    $('#bkKpi1s').textContent = hist[0] ? (hist[0].ok ? t('最近一次成功') : t('最近一次失败')) : t('尚无备份记录');
    const totalBytes = all.reduce((s, c) => s + (c.last_bytes || 0), 0);
    $('#bkKpi2').textContent = totalBytes ? fmtBytes(totalBytes) : '—';
    const freqs = all.filter(c => c.enabled && c.frequency_hours).map(c => c.frequency_hours);
    $('#bkKpi3').textContent = d.auto ? '自动' : '手动触发';
    $('#bkKpi3s').textContent = d.auto && freqs.length ? `最快每 ${Math.min(...freqs)} 小时` : (d.auto ? '' : t('仅手动「立即备份」'));
    $('#bkAuto').checked = !!d.auto;
    $('#bkAlert').value = d.alert_email || '';
    /* 主备份位置 */
    const main = all.find(c => c.type === 'local') || all[0] || {};
    const mainTarget = main.target || '';
    try {
      const tg = await J('/api/backup/targets');
      $('#bkMain').innerHTML = `<option value="">— 选择备份位置 —</option>` +
        (tg.targets || []).map(x => `<option value="${String(x.path).replace(/"/g, '&quot;')}" ${x.path === mainTarget ? 'selected' : ''}>${x.name}${x.writable ? '' : '（不可写）'}</option>`).join('');
    } catch (e) { $('#bkMain').innerHTML = '<option value="">— 位置探测失败，请用右侧自定义路径 —</option>'; }
    if (mainTarget && ![...$('#bkMain').options].some(o => o.value === mainTarget)) $('#bkCustom').value = mainTarget;
    const st = $('#bkMainState');
    const badN = all.filter(c => c.ok === false).length;
    const okN = all.filter(c => c.ok === true).length;
    if (mainTarget) {
      st.textContent = badN ? `${okN} ${t('成功')} · ${badN} ${t('失败')}` : t('已配置');
      st.style.color = badN ? 'var(--warning)' : 'var(--success)';
      st.style.background = badN ? 'var(--warning-bg)' : 'var(--success-bg)';
      $('#bkStatus').textContent = `${all.length} ${t('个渠道')} · ${t('主位置')} ${mainTarget}`;
    } else {
      st.textContent = t('未配置'); st.style.color = 'var(--danger)'; st.style.background = 'var(--danger-bg)';
      $('#bkStatus').textContent = t('未配置备份位置 · 在上面选一个位置或自定义路径');
    }
    /* 渠道列表：按类型分组渲染 */
    const extra = all.filter(c => c.name !== '主备份');
    const order = ['local', 'archive', 'remote', 'mail', 's3', 'baidu-pan'];
    $('#bkChannels').innerHTML = extra.length
      ? order.filter(t => extra.some(c => c.type === t)).map(t =>
        `<div class="section-title" style="margin:6px 0 0">${TYPE_TAG[t]} · ${extra.filter(c => c.type === t).length}</div>` +
        extra.filter(c => c.type === t).map(rowHTML).join('')).join('')
      : `<div class="empty"><div class="et">${t('暂无额外渠道')}</div><div class="ed">${t('上方主备份位置已足够；需要异地 / 对象存储时可再添加')}</div></div>`;
    /* 标题计数与图例：均由 describe() 推导，不可能与行徽标口径不一致 */
    const coldN = all.filter(c => c.type === 'baidu-pan').length;
    $('#bkChHead').innerHTML = `${t('备份渠道')} <span class="sub" style="font-weight:400">${all.length} ${t('个')} · ${okN} ${t('正常')} / ${coldN} ${t('冷备')} / ${badN} ${t('失败')}</span>`;
    $('#bkLegend').innerHTML = legendHTML();
    const nS3 = all.filter(c => c.type === 's3').length;
    const tags = [];
    if (nS3) tags.push(`<span class="badge" style="color:var(--success);background:var(--success-bg)">对象存储 ×${nS3} · 自动</span>`);
    if (coldN) tags.push(`<span class="badge" style="color:var(--warning);background:var(--warning-bg)">网盘冷备 ×${coldN} · 手动上传</span>`);
    $('#bkGroupTags').innerHTML = tags.join('')
      || '<span class="sub">' + t('尚未添加对象存储 / 网盘冷备渠道 —— 点右上「＋ 新增渠道」按向导添加（凭证可后填）') + '</span>';
    $('#bkLogArea').textContent = '点「刷新」查看最近 50 行';
  }

  async function save(channels, opts) {
    const body = { auto: $('#bkAuto').checked, alert_email: $('#bkAlert').value.trim(), channels };
    const d = await PJ('/api/backup/save', body);
    await load();
    return Object.assign({}, d, opts || {});
  }

  /* ---------------- 行操作 ---------------- */

  function rowByName(name) { return document.querySelector(`#bkChannels [data-ci="${CSS.escape(name)}"]`); }

  async function rowAct(el, op) {
    const name = el.dataset.ci;
    const c = collect(el);
    /* 单渠道操作只提交该渠道（其余沿用快照），不再顺带落盘别人未确认的编辑 */
    await save([...S.raw.filter(x => x.name !== name), Object.assign({}, S.raw.find(x => x.name === name), c)], { silent: true });
    const el2 = rowByName(name);
    if (!el2) return;
    if (op === 'run') {
      const d = await PJ('/api/backup/run', { channel: name });
      const r = (d.results || [])[0];
      toast(r ? (r.ok ? `[${r.channel}] 同步 ${r.synced} 个` : `[${r.channel}] 失败：${r.error}`) : (d.error || '未执行'), r && r.ok ? 2000 : 4000);
    } else if (op === 'check') {
      const d = await PJ('/api/backup/check', { channel: name });
      toast(d.ok ? `[${name}] ${t('校验')}通过` : `[${name}] ${d.error || '校验失败'}${d.missing_n ? ` · 缺失 ${d.missing_n}` : ''}${d.size_bad_n ? ` · 大小异常 ${d.size_bad_n}` : ''}`, d.ok ? 2000 : 4500);
    } else if (op === 'restore') {
      const ok = await askConfirm({ title: `从「${name}」${t('恢复')}`, msg: '会用该渠道的备份覆盖本地同名文件（笔记 / 事件 / 索引 / 配置）。', warn: '恢复不可逆：本地在此之后的改动可能被覆盖。建议先做一次「立即备份」留档。', ok: '仍然恢复' });
      if (!ok) { await load(); return; }
      const d = await PJ('/api/backup/restore', { channel: name });
      toast(d.ok ? `已${t('恢复')} ${d.count} 个文件` : (d.error || '恢复失败'), d.ok ? 'success' : 'danger');
    }
    await load();
  }

  async function rowDel(el) {
    const name = el.dataset.ci;
    const ok = await askConfirm({ title: '删除备份渠道', msg: `将移除渠道「${name}」。`, warn: '只删本机配置，不会删除云端已有文件。', ok: '删除渠道' });
    if (!ok) return;
    await save(S.raw.filter(c => c.name !== name), { silent: true });
    toast('渠道已删除', 'info');
  }

  async function saveMain() {
    const target = $('#bkCustom').value.trim() || $('#bkMain').value.trim();
    if (!target) { toast('请先选择或填写备份位置', 'warning'); return; }
    const main = { type: 'local', name: '主备份', enabled: true, target, scope: ['notes', 'events', 'index', 'meta'], frequency_hours: 24 };
    const btn = $('#bkSaveMainBtn'); if (btn) btn.classList.add('busy');
    try {
      await save([main, ...channelList()], {});
      toast('位置已保存，开始备份', 'success');
      await runAll();
    } catch (e) { toast('保存失败：' + e.message, 'danger'); }
    finally { if (btn) btn.classList.remove('busy'); }
  }

  async function runAll() {
    const d = await PJ('/api/backup/run', {});
    if (!d.ok && !d.results) { toast(d.error || '未配置渠道', 'warning'); return; }
    const fails = (d.results || []).filter(r => !r.ok);
    toast(fails.length ? `已执行 ${d.results.length} 个渠道，${fails.length} 个失败` : `已执行 ${d.results.length} 个渠道，全部成功`, fails.length ? 'danger' : 'success');
    await load();
  }

  async function log() {
    const d = await J('/api/backup/log');
    $('#bkLogArea').textContent = '—— backup.log（最近 50 行）——\n' + (d.lines || []).join('\n');
    document.querySelector('.log-box').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  /* ---------------- 向导（设计稿 03：4 步） ---------------- */

  /* 向导弹层骨架静态落在 index.html（与其他 modal 一致），本模块只填内容 */
  const renderMask = () => {
    const m = $('#bkWizard');
    if (m) m.innerHTML = `<div class="modal" style="max-width:560px">${wizardBody()}</div>`;
    return m;
  };

  async function wizard() {
    if (!Object.keys(S.schema).length) {
      try { const d = await J('/api/backup/providers'); S.schema = d.providers || {}; } catch (e) { S.schema = {}; }
    }
    S.step = 1; S.type = null; S.draft = {}; S.preset = S3_PRESETS[0].id; S.tested = false; S.testMsg = '';
    const m = renderMask();
    if (m) m.classList.add('show');
  }

  const closeWizard = () => { const m = $('#bkWizard'); if (m) m.classList.remove('show'); };

  function wizardBody() {
    const t = S.type, sp = spec(t);
    const stepper = `<div class="bkstepper">${STEP_TITLES.map((s, i) =>
      `<span class="bkstep${S.step === i + 1 ? ' on' : ''}${S.step > i + 1 ? ' done' : ''}">${i + 1} ${s}</span>`).join('<i></i>')}</div>`;
    const sub = S.step === 1 ? '步骤 1 / 4 · 选择渠道类型'
      : S.step === 2 ? (t === 's3' ? '步骤 2 / 4 · 连接参数（对象存储统一走 S3 兼容协议）'
        : `步骤 2 / 4 · ${((sp && sp.label) || '').replace(/（.*/, '')}连接参数`)
        : S.step === 3 ? '步骤 3 / 4 · 加密与策略' : '步骤 4 / 4 · 确认并保存';
    return `${stepper}
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;margin:14px 0 12px">
        <div><h3 style="margin:0;font-size:17px;font-weight:600">新增备份渠道</h3><div class="sub">${sub}</div></div>
        <button class="btn ghost small" data-bk="wiz-close">关闭</button>
      </div>
      <div id="bkStepBody">${stepBody()}</div>
      <div class="bkwiz-act">${actions()}</div>
      <div id="bkTestMsg" class="sub" style="margin-top:8px">${S.testMsg}</div>`;
  }

  function actions() {
    const back = S.step > 1 ? '<button class="btn ghost small" data-bk="wiz-back">上一步</button>' : '';
    if (S.step === 1) return back;
    if (S.step === 2) return `${back}<span style="flex:1"></span><button class="btn ghost small" data-bk="wiz-close">${t('取消')}</button>
      <button class="btn primary small" id="bkTestBtn" data-bk="wiz-test">${t('测试连接')}</button>
      <button class="btn ${S.tested ? 'primary' : 'plain'} small" data-bk="wiz-next">${t('下一步')}</button>`;
    if (S.step === 3) return `${back}<span style="flex:1"></span><button class="btn ghost small" data-bk="wiz-close">${t('取消')}</button>
      <button class="btn primary small" data-bk="wiz-next">${t('下一步')}</button>`;
    return `${back}<span style="flex:1"></span><button class="btn ghost small" data-bk="wiz-close">${t('取消')}</button>
      <button class="btn plain small" data-bk="wiz-finish" data-run="0">${t('仅保存')}</button>
      <button class="btn primary small" data-bk="wiz-finish" data-run="1">${t('保存并立即备份')}</button>`;
  }

  /* 把向导当前面板的输入吸入 S.draft（离开面板前统一调用，避免输入丢失） */
  function absorb() {
    const root = $('#bkStepBody');
    if (!root) return;
    root.querySelectorAll('[data-k]').forEach(e => {
      const v = e.value.trim();
      /* 涉密字段留空＝沿用旧值，空串不入草稿 */
      if (v === '') { delete S.draft[e.dataset.k]; return; }
      S.draft[e.dataset.k] = v;
    });
    const scope = [...root.querySelectorAll('[data-scope]:checked')].map(x => x.dataset.scope);
    if (scope.length) S.draft.scope = scope;
  }

  function stepBody() {
    const root = $('#bkStepBody');
    if (S.step === 1) {
      return `<div style="display:flex;flex-direction:column;gap:8px">${Object.entries(S.schema).map(([k, p]) =>
        `<div class="pane bkpick" data-bk="wiz-type" data-t="${k}"><div style="font-weight:500">${p.label}</div><div class="sub">${p.desc}</div></div>`).join('')}</div>`;
    }
    const t = S.type;
    if (S.step === 2) {
      const chips = t === 's3'
        ? `<div class="sub" style="margin-bottom:6px">服务商（对象存储统一走 S3 兼容协议，选后自动填充 Endpoint / Region）</div>
           <div class="bkchips">${S3_PRESETS.map(p =>
          `<button type="button" class="bkchip${S.preset === p.id ? ' active' : ''}" data-bk="wiz-preset" data-p="${p.id}">${p.label}</button>`).join('')}
           <button type="button" class="bkchip${S.preset === 'custom' ? ' active' : ''}" data-bk="wiz-preset" data-p="custom">自定义</button></div>`
        : '';
      const conn = layoutOf(t).map(r => fieldCardPrimary(t, r, S.draft)).join('');
      const tip = t === 's3'
        ? '<div class="bktip">密钥只写入本机配置文件，不随备份上传 · 建议在 Bucket 上开启版本控制</div>' : '';
      return chips + `<div class="bkgrid">${conn}</div>` + tip;
    }
    if (S.step === 3) {
      const policy = stepFields(t, 'policy').filter(f => f.k !== 'frequency_hours' && f.k !== 'retention');
      const freq = stepFields(t, 'policy').filter(f => ['frequency_hours', 'retention'].includes(f.k));
      const pw = stepFields(t, 'policy').find(f => f.type === 'password');
      return `<div class="bkgrid">
          <div class="bkfield"><span class="bkflabel">渠道名称</span><div class="bkfrow">
            <input data-k="name" value="${String(S.draft.name || defaultName(t)).replace(/"/g, '&quot;')}" /></div></div>
          ${policy.map(f => `<div class="bkfield"><span class="bkflabel">${f.label}${f.required ? ' <em>*</em>' : ''}</span>
            <div class="bkfrow">${input(t, f, S.draft)}</div>${f.hint ? `<span class="bkfhint">${f.hint}</span>` : ''}</div>`).join('')}
          ${freq.map(f => `<div class="bkfield"><span class="bkflabel">${f.label}</span>
            <div class="bkfrow">${input(t, f, S.draft)}</div></div>`).join('')}
        </div>
        ${pw ? '<div class="bktip warn">归档加密密码在<b>出本机前</b>生效：丢失将无法解密，请自行离线备份一份。</div>' : ''}
        <div class="bkfield" style="margin-top:10px"><span class="bkflabel">备份范围</span>
          <span class="bkfrow" style="gap:12px">${[['notes', '笔记'], ['events', '事件'], ['index', '索引'], ['meta', '配置']]
          .map(([k, l]) => `<label class="bkcheck"><input data-scope="${k}" type="checkbox" ${(!S.draft.scope || S.draft.scope.includes(k)) ? 'checked' : ''}>${l}</label>`).join('')}</span>
        </div>`;
    }
    /* 步骤 4：确认，摘要用人类可读的字段标签而非原始键名 */
    const labelOf = k => k === 'name' ? '渠道名称'
      : k === 'scope' ? '备份范围'
        : ((field(t, k) || {}).label || k);
    const rows = Object.entries(S.draft)
      .filter(([k, v]) => !['secret_key', 'archive_password'].includes(k) && String(v).trim() !== '')
      .map(([k, v]) => {
        const val = k === 'scope' ? scopeLabel({ scope: v }) : String(v);
        const long = val.length > 34 ? val.slice(0, 17) + '…' + val.slice(-14) : val;
        return `<div class="bksumrow"><span>${labelOf(k)}</span><b title="${String(val).replace(/"/g, '&quot;')}">${long}</b></div>`;
      });
    const hasPw = !!S.draft.archive_password || !!S.draft.secret_key;
    return `<div class="pane">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:10px">
        <span class="badge" style="color:var(--accent);background:var(--accent-bg)">${TYPE_TAG[t] || t}</span>
        <b>${S.draft.name || ((spec(t) || {}).label) || t}</b><span style="flex:1"></span>
        ${S.tested ? '<span class="badge" style="color:var(--success);background:var(--success-bg)">● 连接已验证</span>'
          : '<span class="badge" style="color:var(--text2);background:var(--surface2)">○ 未测试</span>'}
      </div>
      ${rows.join('')}
      ${hasPw ? '<div class="bksumrow"><span>密钥 / 归档密码</span><b>已填写（本机混淆存储）</b></div>' : ''}
      ${S.tested ? '' : '<div class="bktip warn">尚未测试连接。建议返回步骤 2 点「测试连接」验证通过后再保存。</div>'}
    </div>`;
  }

  const repaint = () => { renderMask(); };

  /* 默认渠道名：对象存储带上服务商名，其余用类型短标签 + 备份，避免出现「镜像（云盘/NAS 目录）」这类机器味名称 */
  function defaultName(t) {
    if (t === 's3') {
      const p = S3_PRESETS.find(x => x.id === S.preset);
      return `${p ? p.label : '对象存储'} 备份`;
    }
    return `${TYPE_TAG[t] || t}备份`;
  }

  function pickType(t) {
    S.type = t; S.step = 2; S.tested = false; S.testMsg = '';
    S.draft = { scope: ['notes', 'events', 'index', 'meta'] };
    if (t === 's3') { S.preset = S3_PRESETS[0].id; applyPreset(false); }
    S.draft.name = defaultName(t);
    repaint();
  }

  /** 服务商预设：只在用户还没手改过 Endpoint/Region 时才覆盖（此前无条件覆盖会吃掉手工输入） */
  function applyPreset(repaintToo) {
    if (S.preset === 'custom') { if (repaintToo) repaint(); return; }
    const p = S3_PRESETS.find(x => x.id === S.preset);
    if (!p) return;
    if (!S.draft.endpoint_user_edited) S.draft.endpoint = p.endpoint;
    if (!S.draft.region_user_edited) S.draft.region = p.region;
    if (repaintToo) repaint();
  }

  function draftMissing() {
    const t = S.type;
    const need = fieldsOf(t).filter(f => f.required && (f.step || 'conn') === 'conn').map(f => f.k)
      .filter(k => !String(S.draft[k] || '').trim());
    return need;
  }

  async function testConn() {
    absorb();
    const miss = draftMissing();
    const btn = $('#bkTestBtn');
    if (miss.length) {
      S.testMsg = `<span style="color:var(--warning)">请填写：${miss.map(k => (field(S.type, k) || {}).label || k).join(' / ')}</span>`;
      repaint(); return;
    }
    if (btn) btn.classList.add('busy');
    S.testMsg = '测试中…'; repaint();
    try {
      const d = await PJ('/api/backup/test', Object.assign({ type: S.type }, S.draft));
      S.tested = !!d.ok;
      S.testMsg = d.ok ? `<span style="color:var(--success)">✓ ${d.msg || '连接成功'}</span>`
        : `<span style="color:var(--danger)">✕ ${d.error || '测试失败'}</span>`;
    } catch (e) {
      S.tested = false;
      S.testMsg = `<span style="color:var(--danger)">✕ 请求失败：${e.message}</span>`;
    } finally {
      repaint();
      const b2 = $('#bkTestBtn'); if (b2) b2.classList.remove('busy');
    }
  }

  async function finish(runBackup) {
    absorb();
    const c = Object.assign({ type: S.type, enabled: true }, S.draft);
    if (!c.name) c.name = (spec(S.type) || {}).label || S.type;
    await save([...S.raw, c], {});
    closeWizard();
    toast('渠道已保存', 'success');
    if (runBackup) await runAll();
  }

  function goto(next) {
    absorb();
    /* 步骤 2 → 3 要求测试通过（设计稿：连接参数是必须验证的一道关） */
    if (S.step === 2 && next === 3 && !S.tested) {
      S.testMsg = '<span style="color:var(--warning)">请先点「测试连接」，通过后再进入下一步</span>';
      repaint(); return;
    }
    if (S.step === 3 && next === 4) {
      const pw = field(S.type, 'archive_password');
      if (pw && pw.min_len) {
        const v = String(S.draft.archive_password || '');
        if (v && v.length < pw.min_len) {
          S.testMsg = `<span style="color:var(--danger)">归档密码需 ≥ ${pw.min_len} 位，当前 ${v.length} 位</span>`;
          repaint(); return;
        }
      }
      const freq = parseInt(S.draft.frequency_hours, 10);
      if (!isNaN(freq) && freq < 1) { S.testMsg = '<span style="color:var(--danger)">备份频率需 ≥ 1 小时</span>'; repaint(); return; }
    }
    S.step = next;
    repaint();
  }

  /* ---------------- 事件委托：取代内联 onclick，杜绝悬空函数 ---------------- */

  function mount() {
    document.addEventListener('input', e => {
      const k = e.target && e.target.dataset ? e.target.dataset.k : null;
      if (!k) return;
      if (k === 'endpoint') S.draft.endpoint_user_edited = true;
      if (k === 'region') S.draft.region_user_edited = true;
    });
    document.addEventListener('click', async e => {
      const t = e.target.closest('[data-bk]');
      if (!t) return;
      const act = t.dataset.bk;
      const row = t.closest('[data-ci]');
      e.preventDefault();
      switch (act) {
        case 'wizard': await wizard(); break;
        case 'wiz-close': closeWizard(); break;
        case 'wiz-type': pickType(t.dataset.t); break;
        /* 不重置 *_user_edited：用户手改过 Endpoint/Region 后，切预设不得再覆盖 */
        case 'wiz-preset': S.preset = t.dataset.p; applyPreset(true); break;
        case 'wiz-next': await goto(S.step + 1); break;
        case 'wiz-back': S.step = Math.max(1, S.step - 1); repaint(); break;
        case 'wiz-test': await testConn(); break;
        case 'wiz-finish': await finish(t.dataset.run === '1'); break;
        case 'run-all': await runAll(); break;
        case 'save-main': await saveMain(); break;
        case 'save-settings': await save(channelList(), {}); toast('设置已保存'); break;
        case 'log': await log(); break;
        case 'run': case 'check': case 'restore': if (row) await rowAct(row, act); break;
        case 'del': if (row) await rowDel(row); break;
        default: break;
      }
    });
  }

  return { viewHTML, load, mount };
})();

document.addEventListener('DOMContentLoaded', () => BK.mount());
