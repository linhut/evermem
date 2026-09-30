/*!
 * 恒忆 Evermem (pmem) · Copyright (c) 2026 Jose-AI · 版权所有
 * 仓库: https://github.com/linhut/evermem
 * 官网: https://www.linhut.cn
 * 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）
 */

/* pmem Web 前端逻辑 */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* Toast：toast(msg, type|duration) —— type: success/danger/info/warning，数字参数=停留毫秒 */
function toast(m, opt) {
  const t = $('#toast');
  const dur = typeof opt === 'number' ? opt : (String(m || '').length > 26 ? 3200 : 2400);
  t.className = 'toast' + (typeof opt === 'string' ? ' ' + opt : '');
  $('#toastMsg').textContent = m;
  t.classList.add('show');
  clearTimeout(toast._t);
  toast._t = setTimeout(() => t.classList.remove('show'), dur);
}

/* 忙碌态：顶部进度条 + 按钮自转 */
function busy(on) { $('#busyBar').classList.toggle('on', !!on); }
async function withBusy(p) { busy(true); try { return await p; } finally { busy(false); } }
function btnBusy(sel, on) { const b = typeof sel === 'string' ? $(sel) : sel; if (b) b.classList.toggle('busy', !!on); }

/* 统一请求：失败给可见的错误态而不是静默 */
async function api(u, o) {
  const r = await fetch(u, o);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
async function apiOr(u, o, fallback) { try { return await api(u, o); } catch (e) { console.warn(u, e); return fallback; } }

/* 空状态 / 骨架屏 */
const emptyState = (title, desc) => `<div class="empty">
  <svg viewBox="0 0 24 24"><path d="M3 7.5A1.5 1.5 0 0 1 4.5 6h4l1.5 2h7A1.5 1.5 0 0 1 18.5 9.5v8A1.5 1.5 0 0 1 17 19H4.5A1.5 1.5 0 0 1 3 17.5z"/><path d="M3 11h15"/></svg>
  <div class="eh">${esc(title)}</div>${desc ? `<div>${esc(desc)}</div>` : ''}</div>`;
const skeleton = (n = 5) => Array.from({ length: n }, () => '<div class="skel"><i></i><i></i></div>').join('');

/* 自建确认弹窗（替代原生 confirm，支持明暗主题与危险态） */
function askConfirm({ title = '确认操作', msg = '', warn = '', ok = '确认', danger = true }) {
  return new Promise(resolve => {
    $('#cfTitle').textContent = title;
    $('#cfMsg').innerHTML = esc(msg) + (warn ? `<div class="cf-warn">${esc(warn)}</div>` : '');
    const okBtn = $('#cfOk');
    okBtn.textContent = ok;
    okBtn.className = 'btn ' + (danger ? 'danger' : 'primary');
    $('#confirmMask').classList.add('show');
    const done = v => {
      $('#confirmMask').classList.remove('show');
      okBtn.onclick = null; $('#cfCancel').onclick = null;
      document.removeEventListener('keydown', onKey);
      resolve(v);
    };
    const onKey = e => { if (e.key === 'Escape') done(false); };
    okBtn.onclick = () => done(true);
    $('#cfCancel').onclick = () => done(false);
    document.addEventListener('keydown', onKey);
    okBtn.focus();
  });
}
/* 结果信息弹窗（替代 alert） */
function showInfo(title, bodyHtml) {
  $('#viewModalTitle').textContent = title;
  $('#viewBody').innerHTML = bodyHtml;
  const va = $('#viewActions'); va.style.display = 'none'; va.innerHTML = '';
  $('#viewMask').classList.add('show');
}

/* 类型 / 状态配色（对齐新设计令牌） */
const typeColor = t => ({ procedure: 'var(--success)', lesson: 'var(--accent)', fact: 'var(--info)' }[t] || 'var(--text2)');
const typeBg = t => ({ procedure: 'var(--success-bg)', lesson: 'var(--accent-bg)', fact: 'var(--info-bg)' }[t] || 'var(--surface2)');
const STATUS_STYLE = { active: ['var(--success)', 'var(--success-bg)'], staged: ['var(--info)', 'var(--info-bg)'],
  suspect: ['var(--warning)', 'var(--warning-bg)'], superseded: ['var(--text2)', 'var(--surface2)'] };
const statusBadge = s => { const [f, b] = STATUS_STYLE[s] || ['var(--text2)', 'var(--surface2)']; return badge(S(s), f, b); };
const badge = (t, f, b) => `<span class="badge" style="color:${f};background:${b}">${esc(t)}</span>`;
/* 来源小图标：告知记忆条目来自哪里 */
const ORIGIN_ICON = { doc: '📄', dsh: '💠', atomcode: '🧬', harvest: '🤖', mcp: '🔌', manual: '✍️', ai: '✨' };
const ORIGIN_TIP = { doc: '来自 F 盘文档提炼', dsh: '来自 DSH 会话', atomcode: '来自 atomcode 会话', harvest: '自动提取候选', mcp: 'MCP 桥写入（agent）', manual: '手动/界面新建', ai: 'AI 提炼' };
const originIco = o => ORIGIN_ICON[o] ? `<span title="${t(ORIGIN_TIP[o])}" style="font-size:11px;margin-right:3px">${ORIGIN_ICON[o]}</span>` : '';
/* 状态中文显示（内部仍用英文，界面展示本地语言） */
const STATUS_LABEL = { active: '使用中', staged: '候选', suspect: '存疑', superseded: '已替代' };
const S = s => t(STATUS_LABEL[s] || s);
const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : '{}' })
  .then(async r => {
    // 统一把 HTTP 状态并入返回对象：调用方用 r.ok 判断真实结果，禁止"404 也提示成功"
    let body = {};
    try { body = await r.json(); } catch (e) { /* 非 JSON 响应 */ }
    return Object.assign({ ok: r.ok, status: r.status }, body);
  });

/* 主题（浅/深为对等的双实现，不是补丁式反色） */
function applyTheme(tm) {
  document.documentElement.dataset.theme = tm;
  localStorage.setItem('pmem-theme', tm);
  const dark = tm === 'dark';
  $('#themeIco').innerHTML = dark
    ? '<circle cx="12" cy="12" r="4.2"/><path d="M12 2.5v2.2M12 19.3v2.2M21.5 12h-2.2M4.7 12H2.5m14.8-6.6-1.6 1.6M6.9 17.1l-1.6 1.6m0-11.4 1.6 1.6m10.2 10.2 1.6 1.6"/>'
    : '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>';
  $('#themeLabel').textContent = t(dark ? '浅色模式' : '深色模式');
}
applyTheme(localStorage.getItem('pmem-theme') || 'light');
$('#themeBtn').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

/* 视图 */
let VIEW = 'browse', CURRENT = null, EDIT_ID = null;
const VIEWS = { browse: '记忆浏览', triage: '候选审核', import: '数据导入', hot: '核心经验', stats: '统计诊断', integ: '接入设置', maint: '数据与维护', backup: '数据备份', update: '版本与更新' };
// URL 直达视图（?view=backup），便于分享/深链与自动化验证
(function () {
  const qv = new URLSearchParams(location.search).get('view');
  if (qv && VIEWS[qv]) VIEW = qv;
})();
/* 页头与视图联动：页标题 + 只属于「记忆浏览」的四个控件（搜索框/含候选/新建/Ctrl K 提示）。
   坑：这段原来只写在 .nav 的 onclick 里，于是 (?view=import) 深链进来时 VIEW 变了、侧栏高亮了，
   页头却还停在 HTML 里写死的「记忆浏览」，再加上内容区的「数据导入」卡，
   看起来就是「页头一层 + 侧栏一层 + 内容一层」三层错位；首次加载同理，
   连搜索框都还是 HTML 里的 display:none。抽成函数，导航点击与初始渲染共用一份。 */
function applyViewChrome() {
  $('#viewTitle').textContent = t(VIEWS[VIEW]);
  const showS = VIEW === 'browse';
  $('#searchWrap').style.display = showS ? '' : 'none';
  $('#allBtn').style.display = showS ? '' : 'none';
  $('#newBtn').style.display = showS ? '' : 'none';
  $('#kbdHint').style.display = showS ? '' : 'none';
  document.querySelectorAll('.nav').forEach(x => x.classList.toggle('active', x.dataset.view === VIEW));
}
document.querySelectorAll('.nav').forEach(n => n.onclick = () => {
  VIEW = n.dataset.view;
  applyViewChrome();
  render();
});

async function render() {
  const c = $('#content');
  if (VIEW === 'browse') { c.innerHTML = browseHTML(); bindBrowse(); loadNotes(true); }
  else if (VIEW === 'triage') { c.innerHTML = triageHTML(); bindTriage(); loadTriage(); }
  else if (VIEW === 'import') { c.innerHTML = importHTML(); loadSpaces(); bindImport(); }
  else if (VIEW === 'hot') { c.innerHTML = `<div style="width:100%;max-width:820px"><h2 style="font-size:20px;font-weight:600;margin-bottom:14px" id="hotTitle">${t('核心经验')}</h2><div id="hotArea">` + skeleton(3) + '</div></div>'; loadHot(); }
  else if (VIEW === 'stats') { c.innerHTML = '<div style="width:100%"><div class="stat-grid" id="statGrid"></div><div class="dist" id="distArea"></div><div id="gcArea" style="margin-top:16px"></div><p style="color:var(--text2);font-size:11.5px;margin-top:14px" id="statFoot"></p></div>'; loadStats(); }
  else if (VIEW === 'integ') { c.innerHTML = integHTML(); loadInteg(); }
  // 备份视图：全权交给渠道模块 channel.js，本文件只做路由，不再内联备份实现
  else if (VIEW === 'backup') { c.innerHTML = BK.viewHTML(); BK.load(); }
  else if (VIEW === 'update') { c.innerHTML = updateHTML(); loadUpdateView(); }
  else if (VIEW === 'maint') { c.innerHTML = maintHTML(); loadMaint(); }
}

const browseHTML = () => `<div class="col list-col">
    <div class="list-head">
      <div class="lh-top"><span id="listCount">${t('共 0 条')}</span><span id="listHint">${t('按相关度排序')}</span></div>
      <div class="chips" id="typeChips"></div>
    </div>
    <div id="noteList">${skeleton(6)}</div></div>
  <div class="col detail-col"><div class="detail-top"><div id="detailInner">${emptyState(t('选择一条记忆'), t('左侧列表点选，或用 Ctrl+K 搜索'))}</div></div>
  <div class="opbar" id="opbar" style="display:none">
  <button class="btn ghost" id="editBtn">${t('编辑')}</button><button class="btn ghost" id="hotBtn">★ ${t('核心经验')}</button>
  <button class="btn primary" id="activeBtn">${t('转正')}</button><button class="btn ghost" id="suspectBtn">${t('存疑')}</button>
  <button class="btn danger" id="supersedeBtn">${t('标记已替代')}</button></div></div>`;

/* 数据导入（父模块）：只有侧栏入口与页标题两层，不再单独成卡——
   页头已是「数据导入」，若再套一张同名卡片，父模块就被降级成与子模块并列的内容卡，
   反而多出一层嵌套。说明 + 分段控件作为切换条直接挂在页头下。
   两个子模块：① 文档导入 #paneDoc（切块进块库）② 其他记忆导入 #paneMem（收进笔记库）。
   两者共用同一套「操作卡 + 列表区」骨架，卡片数量与位置对齐。 */
const importHTML = () => `<div style="width:100%">
  <div style="margin-bottom:12px">
    <div class="sub" style="margin-bottom:8px">${t('两种来源，同一套流程')}：<b>${t('文档导入')}</b>${t('把存量文档切成文本块供 AI 提炼')}；<b>${t('其他记忆导入')}</b>${t('把别的工具导出的记忆收进笔记库')}。</div>
    <div class="seg" id="impTabs">
      <button class="seg-btn on" data-imp="doc">${t('文档导入')}</button>
      <button class="seg-btn" data-imp="mem">${t('其他记忆导入')}</button>
    </div>
  </div>

  <div id="paneDoc">
    <div class="pane">
      <div class="sub" style="margin-bottom:8px">
        ${t('导入步骤')}：<b>①</b> ${t('选择空间或输入任意目录')} → <b>②</b> ${t('扫描')}（${t('查看文档构成与体量')}） → <b>③</b> ${t('提取到块库')}（${t('生成可检索文本块')}）。<br>
        ${t('注意')}：${t('提取只写入块库、不直接进记忆库，后续由候选审核决定是否转正')}；${t('切块不改动原文档')}；${t('涉密或敏感目录请先确认范围再扫描')}。
      </div>
      <div class="btnrow" style="margin-bottom:8px">
      <select id="impSpace" style="min-width:220px"></select>
      <input type="text" id="impPath" placeholder="${t('或输入任意盘/目录路径')}" style="flex:1;min-width:160px" list="impHist">
      <datalist id="impHist"></datalist>
      <button class="btn ghost" id="impScan">${t('扫描')}</button><button class="btn primary" id="impExtract">${t('提取到块库')}</button></div>
      <div class="sub" id="impInfo">${t('选择空间或输入路径后点「扫描」')}</div></div>
    <div style="display:flex;gap:18px">
      <div class="col list-col" style="width:45%">
        <div class="list-head" style="display:flex;gap:8px;align-items:center">
          <input id="blkFilter" placeholder="${t('过滤块名…')}" style="flex:1;padding:3px 10px;font-size:12px"><span id="blkCount"></span></div>
        <div id="blkList" style="flex:1;overflow:auto;padding:8px"></div></div>
      <div class="col detail-col"><div class="detail-top">
        <div class="btnrow" style="margin-bottom:6px"><button class="btn ghost small" id="copyBlkBtn">⧉ ${t('复制块内容')}</button><span class="sub" id="blkPath"></span></div>
        <pre class="out" id="blkPreview" style="max-height:none;white-space:pre-wrap;flex:1;overflow:auto">← ${t('点击块预览')}</pre></div></div></div>
  </div>

  <div id="paneMem" style="display:none">
    <div class="pane"><h3>① ${t('导出记忆提示词')}</h3>
      <div class="sub" style="margin-bottom:8px">${t('把这段提示词复制到任意 AI 工具（新开会话），让它产出你的使用画像；再把画像整段粘贴到下方导入框收进笔记库。')}</div>
      <div class="btnrow" style="margin-bottom:8px">
        <button class="btn ghost small" id="miCopyPrompt">⧉ ${t('复制提示词')}</button>
        <button class="btn ghost small" id="miTogglePrompt">${t('展开全文')}</button>
        <span class="sub" id="miPromptInfo">${t('读取中…')}</span>
      </div>
      <pre class="out" id="miPrompt" style="max-height:170px;white-space:pre-wrap;overflow:auto;font-size:11.5px;line-height:1.65">${t('读取中…')}</pre>
    </div>

    <div class="pane"><h3>② ${t('粘贴导入记忆')}</h3>
      <div class="sub" style="margin-bottom:8px">${t('支持画像导出格式（## 分类 + [日期] - 条目）、带 frontmatter 的 Markdown、JSON 导出，也可直接指定目录批量收。')}</div>
      <div class="btnrow" style="margin-bottom:8px">
        <select id="miFmt" style="min-width:150px">
          <option value="auto">${t('自动识别格式')}</option>
          <option value="profile">${t('画像导出格式')}</option>
          <option value="markdown">Markdown</option>
          <option value="json">JSON</option>
        </select>
        <input type="text" id="miPath" placeholder="${t('或指定文件 / 目录路径（可选）')}" style="flex:1;min-width:180px">
        <button class="btn ghost" id="miParse">${t('解析')}</button>
      </div>
      <textarea id="miText" rows="7" placeholder="${t('把别的工具的记忆导出贴在这里…')}
## 指令
[2026-09-27] - 文档类任务动笔前先查记忆
## 偏好
[unknown] - 输出先给结论再给依据" style="width:100%;font-family:var(--font-mono);font-size:12px;line-height:1.6"></textarea>
      <div class="sub" id="miInfo" style="margin-top:8px">${t('粘贴内容后点「解析」，或填路径后点「解析」')}</div>
      <div class="sub">${t('导入后状态为 staged：可在「记忆浏览」查看，人工确认后转正才参与检索召回。')}</div>
    </div>
    <div style="display:flex;gap:18px">
      <div class="col list-col" style="width:45%">
        <div class="list-head" style="display:flex;gap:8px;align-items:center">
          <input id="miFilter" placeholder="${t('过滤条目…')}" style="flex:1;padding:3px 10px;font-size:12px"><span id="miCount"></span></div>
        <div id="miList" style="flex:1;overflow:auto;padding:8px"></div></div>
      <div class="col detail-col"><div class="detail-top">
        <div class="btnrow" style="margin-bottom:6px">
          <span class="sub" id="miStats">${t('尚未解析')}</span>
          <button class="btn ghost small" id="miAll">${t('全选可导入')}</button>
          <button class="btn primary small" id="miImport">${t('导入选中')}</button>
        </div>
        <pre class="out" id="miPreview" style="max-height:none;white-space:pre-wrap;flex:1;overflow:auto">← ${t('点击条目预览')}</pre></div></div>
    </div>
  </div></div>`;

const integHTML = () => `<div style="width:100%">
  <div class="pane"><h3>${t('① 技能安装')}</h3><div class="sub" style="margin-bottom:8px">选中 AI 助手 → 安装记忆技能，让每个新会话「开始查记忆、行动前查记忆、收尾存记忆」</div><div id="hostList"></div></div>
  <div class="pane"><h3>${t('② MCP 工具接入')}</h3><div class="sub" style="margin-bottom:8px">把恒忆标准 MCP 工具（查记忆/存记忆/更新/核心经验）写入各助手配置——DSH/WorkBuddy/Claude 均可原生调用。WorkBuddy/DSH 需重启或新会话生效；WorkBuddy 还须在连接器页点 Trust。</div><div id="mcpList"></div></div>
  <div class="pane"><h3>${t('③ 开机启动')}</h3>
    <div class="btnrow" style="align-items:center">
      <span class="badge" style="color:var(--accent);background:var(--accent-bg)">${t('仅桌面版')}</span>
      <span style="flex:1"></span>
      <label class="ck" style="font-size:13px;color:var(--text)" for="autoStart"><input type="checkbox" id="autoStart" disabled><span>${t('开机自启动')}</span></label>
    </div>
    <div class="sub" id="autoStartInfo" style="margin-top:6px">${t('读取中…')}</div></div>
  <div class="pane"><h3>${t('④ 兼容说明')}</h3><div class="sub">· WorkBuddy 桌面端禁用第三方插件钩子（宿主信任模型），自建能力走技能 + MCP。<br>· DSH：从 $DSH_HOME/skills（用户级）发现技能文件，目录被监视、热刷新。<br>· MCP 工具：evermem_mcp.py 标准 stdio，4 个工具，多助手通用。<br>· 核心经验注入：MEMORY.md 核心经验区 → 新会话上下文（上限 20，有进有出）。</div></div>
</div>`;

/* 数据与维护（一级模块）：从「接入设置」分出来的三张卡——数据位置是本机设置、
   同步与沉淀是本地维护动作，跟"接入别的 AI 工具"不是一回事。
   ① 数据位置 ② 核心经验同步 ③ 经验沉淀 */
const maintHTML = () => `<div style="width:100%;max-width:820px">
  <div class="sub" style="margin-bottom:12px">${t('数据位置改完需重启生效；同步与沉淀都是本地动作，不上传任何内容。')}</div>
  <div class="pane"><h3>${t('① 数据位置（可自由选择）')}</h3><div class="sub" style="margin-bottom:8px">记忆库 / 块库 / 扫描根目录可指向任意本机路径（含权限与空间检查）。配置存 pmem_config.json，所有会话共享；修改后重启生效。</div>
    <div class="btnrow" style="margin-bottom:6px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">${t('记忆库')}</label><input id="cfgHome" placeholder="${t('记忆库目录（笔记/index）')}" style="flex:2;min-width:140px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">${t('块库')}</label><input id="cfgChunks" placeholder="${t('文本块目录')}" style="flex:2;min-width:140px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">${t('扫描根')}</label><input id="cfgSpaces" placeholder="${t('扫描根目录（如 F:/）')}" style="flex:2;min-width:140px">
      <button class="btn primary" id="cfgSave">${t('保存')}</button>
    </div>
    <div class="sub" id="cfgInfo">${t('读取配置中…')}</div></div>
  <div class="pane"><h3>${t('② 核心经验同步')}</h3><div class="sub" id="hotSyncInfo"></div><div class="btnrow" style="margin-top:8px"><button class="btn primary" id="hotSyncBtn">${t('同步核心经验 → 宿主必读文件')}</button></div></div>
  <div class="pane"><h3>${t('③ 经验沉淀')}</h3><div class="sub" id="harvInfo"></div><div class="btnrow" style="margin-top:8px"><button class="btn primary" id="harvBtn">${t('提取近 3 天会话经验')}</button></div></div>
</div>`;

/* 版本与更新（一级模块）：页头已是「版本与更新」，内容只分两张卡，不再套一张同名父卡——
   父模块降级成与子卡并列的容器会多出一层嵌套（这个坑在「数据导入」上踩过）。
   ① 更新检查：当前版本 / 检查更新 / 结果（新版本·已是最新·失败含各源耗时）
   ② 更新源：自动检查开关 / 自建清单 / 加速镜像，全部回读真实生效配置 */
const updateHTML = () => `<div style="width:100%;max-width:820px">
  <div class="sub" style="margin-bottom:12px">${t('检查走 GitHub 直连 + 加速镜像并发取最快的一个；下载走外链在浏览器完成，程序不会静默改动你的文件。')}</div>
  <div class="pane"><h3>${t('① 更新检查')}</h3>
    <div class="btnrow" style="align-items:center">
      <span>${t('当前版本：')}<b id="verCurrent">${t('读取中…')}</b></span>
      <span style="flex:1"></span>
      <button class="btn ghost small" id="verCheck">${t('查看最新版本')}</button>
      <button class="btn primary small" id="updCheck">${t('检查更新')}</button>
    </div>
    <div class="sub" id="verInfo" style="margin-top:6px"></div>
    <div class="sub" id="updInfo" style="margin-top:6px"></div>
  </div>
  <div class="pane"><h3>${t('② 更新源')}</h3>
    <label class="ck" style="font-size:13px;color:var(--text)" for="updAuto"><input type="checkbox" id="updAuto"><span>${t('自动检查更新')}</span></label>
    <div class="sub">${t('打开设置页时自动检查一次，结果缓存 24 小时')}</div>
    <div style="border-top:1px solid var(--line);margin-top:10px;padding-top:10px">
      <div class="sub" style="margin-bottom:4px">${t('自建清单地址（可选，留空则不使用）')}</div>
      <div class="btnrow">
        <input id="updManifest" type="text" placeholder="${t('留空')}" style="flex:1;min-width:180px">
        <button class="btn small" id="updManifestSave">${t('保存')}</button>
      </div>
      <div class="sub">${t('留空即可：默认走 GitHub 直连 + 镜像，不需要自己托管任何文件')}</div>
    </div>
    <div style="margin-top:10px">
      <div class="sub" style="margin-bottom:4px">${t('加速镜像（一行一个，用于版本检查与下载）')}</div>
      <textarea id="updMirrors" rows="4" style="width:100%;font-family:var(--mono,monospace);font-size:12px"></textarea>
      <div class="btnrow" style="margin-top:6px">
        <button class="btn primary small" id="updSave">${t('保存')}</button>
        <button class="btn ghost small" id="updReset">${t('恢复默认')}</button>
      </div>
      <div class="sub" id="updSrcInfo"></div>
    </div>
  </div>
</div>`;

async function loadAutostart() {
  const box = $('#autoStart'); if (!box) return;
  let d = { supported: false };
  try { d = await (await fetch('/api/autostart')).json(); } catch (e) { d = { supported: false, reason: '服务未响应' }; }
  // 状态取自系统真实值，不是界面缓存；不支持时禁用并说明原因，避免点了没反应
  box.checked = !!d.enabled;
  box.disabled = !d.supported;
  const sub = $('#autoStartInfo');
  if (!d.supported) {
    sub.textContent = t('不支持：') + (d.reason || t('仅桌面版可设置'));
  } else {
    sub.textContent = (d.enabled ? t('已开启') : t('未开启')) + ' · ' + t('系统登录后自动启动恒忆，并静默驻留系统托盘。');
  }
  box.onchange = async () => {
    const want = box.checked;
    box.disabled = true;
    let r = { ok: false, error: '服务未响应' };
    try { r = await post('/api/autostart/save', { enabled: want }); } catch (e) { r = { ok: false, error: String(e) }; }
    // 失败必须把开关拉回系统真实状态：以接口返回值与重新读取的系统状态为准，
    // 只看请求是否发出去属于假成功。
    // 失败后重新读取系统状态：开关与说明文案都以系统真实值为准
    const real = r.ok ? !!r.enabled : null;
    box.checked = real === null ? !want : real;
    if (!r.ok) {
      toast(t('设置失败：') + (r.error || ''));
      await loadAutostart();
      return;
    }
    toast(want ? t('已开启') : t('未开启'), 'success');
    $('#autoStartInfo').textContent = (want ? t('已开启') : t('未开启')) + ' · ' + t('系统登录后自动启动恒忆，并静默驻留系统托盘。');
    box.disabled = false;
  };
}

// ---------- 更新源设置（自动检查 / 自建清单 / 加速镜像） ----------
async function loadUpdateSources() {
  const box = $('#updAuto'), man = $('#updManifest'), mir = $('#updMirrors'), info = $('#updSrcInfo');
  if (!box || !mir) return;
  let d = null;
  try { d = await (await fetch('/api/update/sources')).json(); } catch (e) { d = null; }
  if (!d || !d.config) {
    if (info) info.textContent = t('更新源配置读取失败');
    return;
  }
  const cfg = d.config;
  // 初值取真实生效配置，不是界面残留
  box.checked = !!cfg.auto_check;
  if (man) man.value = cfg.manifest_url || '';
  mir.value = (cfg.mirrors || []).join('\n');
  const extra = d.download_only_mirrors || [];
  const total = (cfg.mirrors || []).length + extra.length + 1;
  if (info) {
    info.textContent = extra.length
      ? `${t('下载时额外追加')} ${extra.join('、')}（${t('只通文件、不通接口')}），${t('共')} ${total} ${t('个候选')}`
      : `${t('共')} ${total} ${t('个候选')}`;
  }
  box.onchange = () => saveUpdateConfig({ auto_check: box.checked }, true);
  const b1 = $('#updManifestSave');
  if (b1) b1.onclick = () => saveUpdateConfig({ manifest_url: (man ? man.value : '').trim() });
  const b2 = $('#updSave');
  if (b2) b2.onclick = () => saveUpdateConfig({
    mirrors: mir.value.split('\n').map(s => s.trim()).filter(Boolean)
  });
  const b3 = $('#updReset');
  if (b3) b3.onclick = () => saveUpdateConfig({
    mirrors: (d.defaults || {}).mirrors || [], manifest_url: '', auto_check: true
  });
}

async function saveUpdateConfig(patch, quiet) {
  let d = { ok: false };
  try {
    const r = await fetch('/api/update/sources/save', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch)
    });
    d = await r.json();
  } catch (e) { d = { ok: false, error: String(e) }; }
  if (!d.ok) {
    toast(`${t('保存失败：')}${d.error || ''}`);
    await loadUpdateSources();  // 保存失败要把界面拉回真实值，不能停在用户以为生效的样子
    return;
  }
  await loadUpdateSources();    // 回读真实值：界面显示的就是实际生效的配置
  if (!quiet) toast(t('已保存'));
}

async function loadVersion() {
  const cur = $('#verCurrent');
  const info = $('#verInfo');
  const btn = $('#verCheck');
  if (!cur) return;
  try {
    const d = await (await fetch('/api/version')).json();
    cur.textContent = d.version || t('版本号未知');
    btn.onclick = () => {
      try { window.open(d.releases_url || 'https://github.com/linhut/evermem/releases/latest', '_blank'); }
      catch (e) { toast(t('发布页打开失败')); }
    };
    info.textContent = d.releases_url ? t('有新版本时，下载新文件覆盖原文件即可；数据不会丢失。') : '';
  } catch (e) {
    cur.textContent = t('版本号未知');
    info.textContent = String(e);
  }
}

async function loadUpdate(force) {
  const info = $('#updInfo');
  const btn = $('#updCheck');
  if (!info || !btn) return;
  btn.disabled = true;
  info.textContent = t('检查中…');
  let d = { ok: false, error: '服务未响应' };
  try { d = await (await fetch('/api/update/check' + (force ? '?force=1' : ''))).json(); }
  catch (e) { d = { ok: false, error: String(e) }; }
  btn.disabled = false;
  btn.onclick = () => loadUpdate(true);
  // 全部源不可用必须明确报出来：静默显示"已是最新"属于假成功
  if (!d.ok) {
    // 耗时一起显示：哪一跳慢、哪一跳挂了一眼可见
    const tried = (d.attempts || []).map(a => {
      const ms = Number(a.elapsed_ms || 0);
      const dur = ms >= 1000 ? (ms / 1000).toFixed(1) + 's' : Math.round(ms) + 'ms';
      return `${a.source}(${a.error || t('失败')} ${dur})`;
    }).join('、');
    info.innerHTML = `<span style="color:var(--danger,#c0392b)">${t('更新检查失败：')}${esc(d.error || '')}</span>` +
      (tried ? `<br>${t('已尝试：')}${esc(tried)}` : '') +
      `<br>${t('当前版本仍可正常使用，可稍后重试或手动下载。')}` +
      ` <a href="${esc(d.manual_url || 'https://github.com/linhut/evermem/releases/latest')}" target="_blank">${t('手动下载')}</a>`;
    return;
  }
  if (d.has_update) {
    const asset = d.asset || {};
    const urls = asset.urls || [];
    const url = urls[0] || d.manual_url;
    // 直连之外再给一个镜像加速入口：大文件走镜像通常更快
    const fast = urls.find(u => u && u !== url && !u.startsWith('https://github.com/'));
    const notes = (d.notes || '').split('\n').filter(x => x.trim()).slice(0, 3).join('<br>');
    info.innerHTML = `<b>${t('发现新版本：')}v${esc(d.latest || '')}</b>（${t('当前：')}v${esc(d.current || '')}）` +
      ` <a href="${esc(url)}" target="_blank"><button class="btn primary small">${t('下载更新')}</button></a>` +
      (fast ? ` <a href="${esc(fast)}" target="_blank"><button class="btn small">${t('镜像加速下载')}</button></a>` : '') +
      (notes ? `<br>${notes}` : '');
  } else {
    info.textContent = `${t('已是最新版本')}（v${d.latest || d.current || ''}）` + (d.cached ? ` · ${t('缓存结果')}` : '');
  }
}

function bindBrowse() {
  $('#noteList').onclick = e => {
    const it = e.target.closest('.note-item'); if (!it) return;
    document.querySelectorAll('.note-item').forEach(x => x.classList.remove('active'));
    it.classList.add('active'); showNote(it.dataset.id);
  };
  $('#editBtn').onclick = () => openEdit(CURRENT);
  $('#hotBtn').onclick = () => act(CURRENT, 'hot');
  $('#activeBtn').onclick = () => act(CURRENT, 'status', 'active');
  $('#suspectBtn').onclick = () => act(CURRENT, 'status', 'suspect');
  $('#supersedeBtn').onclick = () => act(CURRENT, 'status', 'superseded');
}
function bindImport() {
  // 双来源切换（文档 / 其他记忆）——同一模块内的分段控件，切换只换面板，骨架不变
  $('#impTabs').onclick = e => {
    const b = e.target.closest('.seg-btn'); if (!b) return;
    document.querySelectorAll('#impTabs .seg-btn').forEach(x => x.classList.toggle('on', x === b));
    const isDoc = b.dataset.imp === 'doc';
    $('#paneDoc').style.display = isDoc ? '' : 'none';
    $('#paneMem').style.display = isDoc ? 'none' : '';
  };
  bindMemImport();
  // 最近路径历史（localStorage）
  let hist = [];
  try { hist = JSON.parse(localStorage.getItem('pmem-scan-hist') || '[]'); } catch (e) { hist = []; }
  const histEl = $('#impHist');
  histEl.innerHTML = hist.map(p => `<option value="${esc(p)}">`).join('');
  const saveHist = p => {
    try {
      hist = [p, ...hist.filter(x => x !== p)].slice(0, 6);
      localStorage.setItem('pmem-scan-hist', JSON.stringify(hist));
    } catch (e) { /* ignore */ }
  };
  $('#impScan').onclick = () => {
    const p = $('#impPath').value.trim() || $('#impSpace').value;
    if (!p) { toast('先选空间或输入路径'); return; }
    saveHist(p);
    $('#impInfo').innerHTML = '扫描中…';
    fetch('/api/scan?path=' + encodeURIComponent(p)).then(r => r.json()).then(d => {
      if (d.error) { $('#impInfo').innerHTML = '❌ ' + esc(d.error); toast('路径无效'); return; }
      const exts = Object.entries(d.by_ext || {}).slice(0, 8)
        .map(([e, n]) => `${e.replace('.', '')} ${n}`).join(' · ');
      $('#impInfo').innerHTML =
        `<b>${esc(d.name)}</b>（${d.total} 文档 · ${d.size_mb} MB）<br>` +
        `构成：${exts || '—'}<br>` +
        `块库：<b>${d.blocks_now}</b> 个文本块 ${d.blocks_now ? '（已提取）' : '（未提取，点「提取到块库」生成）'}`;
      loadBlocks(d.name);
    });
  };
  $('#impExtract').onclick = async () => {
    const p = $('#impPath').value.trim() || $('#impSpace').value;
    if (!p) { toast('先选空间或输入路径'); return; }
    const name = p.split(/[\\/]/).pop();
    const ok = await askConfirm({ title: '提取到块库', msg: `将扫描「${p}」并切分为文本块。`, warn: '大目录可能耗时数分钟；已在块库中的文件会跳过。', ok: '开始提取', danger: false });
    if (!ok) return;
    $('#impInfo').innerHTML = '提取中…（后台运行，完成后自动刷新）'; toast('正在提取 ' + p, 'info');
    post('/api/extract', { path: p }).then(d => {
      if (!d.ok) { toast('失败：' + (d.error || '')); return; }
      pollTask(d.task_id, out => {
        $('#impInfo').innerHTML += `<br><pre class="out">${esc(out)}</pre>`;
        loadBlocks(name);
        toast('提取完成');
      });
    });
  };
  // 块过滤
  $('#blkFilter').addEventListener('input', e => filterBlocks(e.target.value));
  $('#copyBlkBtn').onclick = () => {
    const txt = $('#blkPreview').textContent;
    if (!txt || txt.startsWith('←')) { toast('先选中一个块'); return; }
    navigator.clipboard.writeText(txt).then(() => toast('块内容已复制，可粘贴给 AI 提炼')).catch(() => toast('复制失败（手动选中复制）'));
  };
}
/* ---- 其他记忆导入：① 导出提示词（复制出去）→ ② 粘贴导入（收进来） ---- */
let _miPlan = [];
let _miPromptText = '';
/* ① 的提示词不硬编码在前端：读 templates/usage-profile.prompt.md 的 COPY 区间，
   改模板即生效，Web 与 CLI（mem.py profile 的配套说明）共用同一份原文。 */
async function loadProfilePrompt() {
  const pre = $('#miPrompt'); if (!pre) return;
  pre.textContent = t('读取中…');
  try {
    const d = await fetch('/api/profile/prompt').then(r => r.json());
    if (d && d.ok && d.text) {
      _miPromptText = d.text;
      pre.textContent = d.text;
      $('#miPromptInfo').textContent = `${d.text.length} ${t('字')} · ${t('提示词只有一份，改模板即生效')}`;
    } else {
      $('#miPromptInfo').textContent = '❌ ' + t('未能读取提示词模板');
      pre.textContent = '（templates/usage-profile.prompt.md 未找到或 COPY 区间缺失）';
    }
  } catch (e) {
    $('#miPromptInfo').textContent = '❌ ' + t('读取失败：服务未响应');
    pre.textContent = '（服务未响应）';
  }
}
function selectNode(el) {
  try {
    const r = document.createRange(); r.selectNodeContents(el);
    const s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
  } catch (e) { /* ignore */ }
}
function bindMemImport() {
  /* ① 导出记忆提示词 —— 复制 / 展开 */
  loadProfilePrompt();
  $('#miCopyPrompt').onclick = () => {
    if (!_miPromptText) { toast(t('提示词还没加载出来，稍等一下'), 'danger'); return; }
    navigator.clipboard.writeText(_miPromptText)
      .then(() => toast(t('提示词已复制：粘到任意 AI 的新会话，拿到画像再贴回下方'), 'info'))
      .catch(() => { selectNode($('#miPrompt')); toast(t('浏览器拒绝了剪贴板：已帮你全选，按 Ctrl+C')); });
  };
  $('#miTogglePrompt').onclick = () => {
    const pre = $('#miPrompt');
    const open = pre.style.maxHeight === 'none';
    pre.style.maxHeight = open ? '170px' : 'none';
    $('#miTogglePrompt').textContent = open ? t('展开全文') : t('收起全文');
  };
  /* ② 粘贴导入 */
  $('#miParse').onclick = async () => {
    const text = $('#miText').value;
    const path = $('#miPath').value.trim();
    if (!text.trim() && !path) { toast(t('先粘贴内容或填写路径'), 'danger'); return; }
    $('#miInfo').textContent = t('解析中…');
    let d;
    try { d = await post('/api/memimport/preview', { text, path, dir: path && !path.match(/\.(md|markdown|json)$/i) ? path : '', fmt: $('#miFmt').value }); }
    catch (e) { $('#miInfo').textContent = t('解析失败：服务未响应'); toast(t('解析失败：服务未响应'), 'danger'); return; }
    if (!d || !d.ok) { $('#miInfo').textContent = '❌ ' + esc((d && d.error) || t('解析失败')); return; }
    _miPlan = d.items || [];
    $('#miInfo').innerHTML = `${t('格式')}：<b>${esc(d.format)}</b> · ${t('来源')}：${esc(d.source)} · ${t('共')} ${d.stats.total} ${t('条')}`;
    $('#miStats').innerHTML = `${t('共')} <b>${d.stats.total}</b> ${t('条')} → ${t('可导入')} <b>${d.stats.new}</b> · ${t('疑似重复')} ${d.stats.dup} · ${t('已存在')} ${d.stats.exists}`;
    renderMiPlan();
    toast(`${t('解析出')} ${d.stats.total} ${t('条')}`, 'info');
  };
  $('#miAll').onclick = () => { _miPlan.forEach(r => { r.selected = r.action === 'new'; }); renderMiPlan(); };
  $('#miImport').onclick = async () => {
    const rows = _miPlan.filter(r => r.selected);
    if (!rows.length) { toast(t('先勾选要导入的条目'), 'danger'); return; }
    const ok = await askConfirm({
      title: t('导入选中'), msg: `${t('将写入')} ${rows.length} ${t('条')}${t('到笔记库')}。`,
      warn: t('导入后状态为 staged，需人工转正才参与检索召回。'), ok: t('开始导入'), danger: false,
    });
    if (!ok) return;
    let d;
    try { d = await post('/api/memimport/run', { items: rows, status: 'staged' }); }
    catch (e) { toast(t('导入失败：服务未响应'), 'danger'); return; }
    if (!d || !d.ok) { toast(t('导入失败：') + esc((d && d.error) || ''), 'danger'); return; }
    toast(`${t('已导入')} ${d.count} ${t('条')}（staged）`, 'info');
    $('#miStats').innerHTML = `✅ ${t('已导入')} <b>${d.count}</b> ${t('条')}`;
    _miPlan = _miPlan.filter(r => !r.selected);
    renderMiPlan();
  };
  $('#miFilter').addEventListener('input', e => renderMiPlan(e.target.value));
}
function renderMiPlan(q) {
  const ql = (q || '').toLowerCase();
  const list = ql ? _miPlan.filter(r => (r.title || '').toLowerCase().includes(ql)) : _miPlan;
  const flag = a => a === 'new' ? '✅' : a === 'dup' ? '⚠️' : '⏭';
  $('#miList').innerHTML = list.map((r, i) => `<div class="note-item" data-i="${i}">
      <label style="display:flex;gap:8px;align-items:flex-start;cursor:pointer">
        <input type="checkbox" ${r.selected ? 'checked' : ''} data-mi="${i}" style="margin-top:3px">
        <span style="flex:1"><span class="t">${flag(r.action)} ${esc(r.title)}</span>
        <span class="m">${badge(r.type, typeColor(r.type), typeBg(r.type))} ${esc(r.created || '')} ${esc(r.reason || '')}</span></span>
      </label></div>`).join('')
    || emptyState(t('还没有解析出条目'), t('粘贴记忆导出内容后点「解析」'));
  $('#miCount').textContent = list.length + '/' + _miPlan.length;
  $('#miList').onclick = e => {
    const it = e.target.closest('.note-item'); if (!it) return;
    const r = _miPlan[+it.dataset.i]; if (!r) return;
    document.querySelectorAll('#miList .note-item').forEach(x => x.classList.remove('active'));
    it.classList.add('active');
    $('#miPreview').textContent = (r.body || '').slice(0, 4000);
  };
  $('#miList').onchange = e => {
    const cb = e.target.closest('input[data-mi]'); if (!cb) return;
    const r = _miPlan[+cb.dataset.mi]; if (r) r.selected = cb.checked;
    const n = _miPlan.filter(x => x.selected).length;
    $('#miCount').textContent = n + '/' + _miPlan.length;
  };
}

let _allBlocks = [];
function loadBlocks(name) {
  fetch('/api/blocks?space=' + encodeURIComponent(name)).then(r => r.json()).then(d => {
    _allBlocks = d.blocks || [];
    $('#blkCount').textContent = _allBlocks.length;
    filterBlocks($('#blkFilter').value);
  });
}
function filterBlocks(q) {
  const ql = (q || '').toLowerCase();
  const list = ql ? _allBlocks.filter(b => b.name.toLowerCase().includes(ql)) : _allBlocks;
  const el = $('#blkList');
  el.innerHTML = list.map(b => `<div class="note-item" data-path="${esc(b.path)}"><div class="t">${esc(b.name)}</div><div class="m"><span style="font-family:var(--font-mono)">${b.size} B</span></div></div>`).join('')
    || emptyState('还没有文本块', '先在上方选个目录点「扫描」，再点「提取到块库」');
  $('#blkCount').textContent = list.length + '/' + _allBlocks.length;
  el.onclick = e => {
    const it = e.target.closest('.note-item'); if (!it) return;
    document.querySelectorAll('#blkList .note-item').forEach(x => x.classList.remove('active'));
    it.classList.add('active');
    fetch('/api/block?path=' + encodeURIComponent(it.dataset.path)).then(r => r.json()).then(b => {
      $('#blkPreview').textContent = b.text;
      $('#blkPath').textContent = b.path || '';
    });
  };
}

/* 浏览 */
let deb = null;
/* 异步任务轮询（extract/harvest 后台运行不阻塞 UI） */
function pollTask(taskId, onDone) {
  // 加了超时与异常兜底：任务卡死时不再无限轮询（此前 interval 永不清除、fetch 抛错即 unhandled）
  let n = 0;
  const iv = setInterval(async () => {
    n += 1;
    try {
      const d = await (await fetch('/api/task/status?task=' + encodeURIComponent(taskId))).json();
      if (d.state === 'done') { clearInterval(iv); onDone(d.output || ''); }
      else if (d.state === 'error') { clearInterval(iv); toast('任务失败：' + (d.output || '').slice(0, 80)); }
      else if (n >= 120) { clearInterval(iv); toast('任务超时（约 3 分钟），请查看服务日志', 'warning'); }
    } catch (e) {
      if (n >= 60) { clearInterval(iv); toast('任务状态查询失败，已停止轮询', 'warning'); }
    }
  }, 1500);
}
$('#search').addEventListener('input', e => { clearTimeout(deb); deb = setTimeout(() => loadNotes(), 250); });
$('#allBtn').onclick = () => { $('#allBtn').classList.toggle('on'); loadNotes(); };

/* 浏览：缓存 + 类型过滤（列表不再因每次刷新而跳动） */
let _notesCache = [], _typeFilter = 'all', _statsCache = null;
const TYPE_LABEL = { procedure: '配方', lesson: '经验', fact: '事实' };
async function loadNotes(withSkeleton) {
  const q = $('#search').value.trim();
  if (withSkeleton) $('#noteList').innerHTML = skeleton(6);
  let list;
  try {
    if (q) {
      const d = await api('/api/search?q=' + encodeURIComponent(q) + '&all=1');
      list = d.hits.map(h => ({ id: h.id, title: h.title, type: h.type, type_label: h.type_label, status: h.status, hot: false, tags: [], score: h.score, origin: h.origin }));
    } else {
      const d = await api('/api/notes');
      list = d.notes.filter(n => $('#allBtn').classList.contains('on') || n.status === 'active');
    }
  } catch (e) {
    $('#noteList').innerHTML = '<div class="errbox">记忆列表加载失败：' + esc(e.message) +
      '<br>请确认 pmem 服务正在运行，然后切换视图重试。</div>';
    return;
  }
  _notesCache = list;
  renderNotes();
  if (_notesCache.length) showNote(_notesCache[0].id);
}
function renderNotes() {
  const list = _typeFilter === 'all' ? _notesCache : _notesCache.filter(n => n.type === _typeFilter);
  $('#noteList').innerHTML = list.map(n => `<div class="note-item" data-id="${esc(n.id)}"><div class="t">${originIco(n.origin)}${esc(n.title)}</div>
    <div class="m">${badge(n.type_label, typeColor(n.type), typeBg(n.type))}${
      n.hot ? '<span class="badge" style="color:var(--warning);background:var(--warning-bg)">★ 核心</span>' : ''
    }${statusBadge(n.status)}${n.score ? `<span style="font-family:var(--font-mono)">${n.score} 分</span>` : ''}</div></div>`).join('')
    || emptyState('没有匹配的记忆', _typeFilter !== 'all' ? '换一个类型看看' : '换个关键词，或打开「含候选」');
  const q = $('#search').value.trim();
  $('#listCount').innerHTML = `共 <b>${list.length}</b> 条${q ? ' · 搜索「' + esc(q) + '」' : ''}`;
  renderChips();
}
function renderChips() {
  const el = $('#typeChips'); if (!el) return;
  const bt = (_statsCache && _statsCache.by_type) || {};
  const items = [['all', '全部', _statsCache ? _statsCache.total : null],
    ['procedure', '配方', bt.procedure], ['lesson', '经验', bt.lesson], ['fact', '事实', bt.fact]];
  el.innerHTML = items.map(([k, l, n]) =>
    `<button class="chip${_typeFilter === k ? ' on' : ''}" data-t="${k}">${l}${n != null ? `<span class="n">${n}</span>` : ''}</button>`).join('');
  el.onclick = e => {
    const c = e.target.closest('.chip'); if (!c) return;
    _typeFilter = c.dataset.t; renderNotes();
  };
}
/* 侧栏索引状态 */
async function loadSide() {
  const d = await apiOr('/api/stats', {}, null);
  if (!d) { $('#sideIndex').textContent = '索引未就绪'; return; }
  _statsCache = d;
  $('#sideTotal').textContent = d.total;
  $('#sideIndex').textContent = '索引 ' + (d.built_at || '—');
  renderChips();
}
async function showNote(id) {
  const d = await apiOr('/api/note?id=' + encodeURIComponent(id), {}, null);
  if (!d || !d.note) return;
  CURRENT = d.note; const n = d.note;
  const bs = [badge(n.type_label, typeColor(n.type), typeBg(n.type))];
  if (n.hot) bs.push(badge('★ 核心经验', 'var(--warning)', 'var(--warning-bg)'));
  bs.push(statusBadge(n.status));
  $('#detailInner').innerHTML = `<h2>${originIco(n.origin)}${esc(n.title)}</h2><div>${bs.join(' ')}</div>
    <div class="meta">${esc((n.tags || []).join('、')) || '无标签'} ｜ ${ORIGIN_TIP[n.origin] || '来源未知'}：${esc(n.source || '—')}</div><div id="body">${md(n.body)}</div>`;
  $('#opbar').style.display = 'flex';
}
function md(s) {
  if (!s) return '';
  const L = s.split('\n'); let o = [], code = false;
  for (const l of L) {
    if (l.startsWith('```')) { code = !code; continue; }
    if (code) { o.push(`<pre>${esc(l)}</pre>`); continue; }
    if (l.startsWith('### ')) o.push(`<h3>${esc(l.slice(4))}</h3>`);
    else if (l.startsWith('## ')) o.push(`<h4>${esc(l.slice(3))}</h4>`);
    else if (l.startsWith('# ')) o.push(`<h3>${esc(l.slice(2))}</h3>`);
    else if (/^[-*] /.test(l)) o.push(`<p>• ${esc(l.slice(2))}</p>`);
    else if (l.trim()) o.push(`<p>${esc(l)}</p>`);
  }
  return o.join('');
}
async function act(n, action, extra) {
  if (!n) return;
  // 假成功修复：必须看响应，404/500 一律如实提示，不再"点了就算成功"
  const r = await post('/api/note/' + encodeURIComponent(n.id) + '/' + action, extra ? { status: extra } : {});
  if (r.ok) { toast('已更新'); loadNotes(); }
  else toast('操作失败：' + (r.error || ('HTTP ' + r.status)), 'danger');
}

/* 候选 */
const AI_COLOR = { promote: 'var(--success)', keep: 'var(--warning)', archive: 'var(--danger)', reject: 'var(--danger)' };
function aiBadge(r) {
  const c = AI_COLOR[r.ai_verdict] || 'var(--text2)';
  const roleLine = (r.roles || []).map(x => `${x.n[0]}${x.score}${x.v === 'pass' ? '✓' : (x.v === 'veto' ? '✗' : '●')}`).join(' ');
  return `<div style="font-size:11px;line-height:1.7"><span style="padding:1px 8px;border-radius:10px;border:1px solid ${c};color:${c};margin-right:6px">AI ${r.ai_total} 分·${r.ai_label}（${r.ai_passes}/6通过）</span>
    <span style="color:var(--text2)">${roleLine}</span></div>`;
}
/* 候选审核：全量数据缓存在 _triAll，筛选/勾选都只影响「可见视图」，
   工具条（搜索 + 三个筛选 + 全选/反选/清空 + 批量按钮）写在同一张卡片里，不新增卡片层级。 */
let _triAll = [], _triSel = new Set();
const _triFilter = { q: '', status: '', type: '', verdict: '' };

const triageHTML = () => `<div style="width:100%;max-width:900px">
  <div class="pane">
    <h3>${t('候选审核')}</h3>
    <div class="sub" id="triHead"></div>
    <div class="btnrow" style="margin-top:10px">
      <input type="text" id="triQ" placeholder="${t('搜索候选标题…')}" style="flex:1;min-width:150px">
      <select id="triStatus">
        <option value="">${t('全部状态')}</option>
        <option value="staged">${t('候选')} · staged</option>
        <option value="suspect">${t('存疑')} · suspect</option>
        <option value="active">${t('使用中')} · active</option>
      </select>
      <select id="triType">
        <option value="">${t('全部类型')}</option>
        <option value="procedure">${t('配方')}</option>
        <option value="lesson">${t('经验')}</option>
        <option value="fact">${t('事实')}</option>
      </select>
      <select id="triVerdict">
        <option value="">${t('全部建议')}</option>
        <option value="promote">${t('建议转正')}</option>
        <option value="keep">${t('保留观察')}</option>
        <option value="archive">${t('建议归档')}</option>
        <option value="reject">${t('否决（涉敏/危险）')}</option>
      </select>
    </div>
    <div class="btnrow" style="margin-top:6px;align-items:center">
      <label class="ck"><input type="checkbox" id="triAll"><span>${t('全选')}</span></label>
      <button class="btn ghost small" id="triInvert">${t('反选')}</button>
      <button class="btn ghost small" id="triNone">${t('清空选择')}</button>
      <span class="sub" id="triSel">${t('已选')} 0 ${t('条')}</span>
      <span style="flex:1"></span>
      <button class="btn primary small" id="triBActive">${t('批量转正')}</button>
      <button class="btn ghost small" id="triBSuspect">${t('批量存疑')}</button>
      <button class="btn ghost small" id="triBArchive">${t('批量归档')}</button>
    </div>
  </div>
  <div id="triList">${skeleton(3)}</div></div>`;

function bindTriage() {
  $('#triQ').oninput = e => { _triFilter.q = e.target.value; renderTriage(); };
  $('#triStatus').onchange = e => { _triFilter.status = e.target.value; renderTriage(); };
  $('#triType').onchange = e => { _triFilter.type = e.target.value; renderTriage(); };
  $('#triVerdict').onchange = e => { _triFilter.verdict = e.target.value; renderTriage(); };
  // 全选 / 反选 / 清空都只作用于「当前筛选后可见的条目」，避免误伤看不见的候选
  $('#triAll').onchange = e => {
    triVisible().forEach(n => e.target.checked ? _triSel.add(n.id) : _triSel.delete(n.id));
    renderTriage();
  };
  $('#triInvert').onclick = () => {
    triVisible().forEach(n => _triSel.has(n.id) ? _triSel.delete(n.id) : _triSel.add(n.id));
    renderTriage();
  };
  $('#triNone').onclick = () => { _triSel.clear(); renderTriage(); };
  $('#triBActive').onclick = () => triBatch('active');
  $('#triBSuspect').onclick = () => triBatch('suspect');
  $('#triBArchive').onclick = () => triBatch('archive');
}

/* 筛选：关键词匹配标题，再叠状态 / 类型 / AI 建议结论（三项都来自 /api/candidates 已有字段，后端不改） */
function triVisible() {
  const f = _triFilter, q = f.q.trim().toLowerCase();
  return _triAll.filter(n =>
    (!q || String(n.title || '').toLowerCase().includes(q)) &&
    (!f.status || n.status === f.status) &&
    (!f.type || n.type === f.type) &&
    (!f.verdict || n.ai_verdict === f.verdict));
}

/* 勾选态的汇总 UI：全选框三态（全选/半选/未选）+ 已选条数 */
function updateTriSelUI() {
  const vis = triVisible();
  const ck = $('#triAll');
  if (ck) {
    const all = vis.length > 0 && vis.every(n => _triSel.has(n.id));
    ck.checked = all;
    ck.indeterminate = !all && vis.some(n => _triSel.has(n.id));
  }
  const s = $('#triSel');
  if (s) s.textContent = `${t('已选')} ${_triSel.size} ${t('条')} · ${t('当前筛选')} ${vis.length} ${t('条')}`;
}

function renderTriage() {
  const vis = triVisible();
  const box = $('#triList');
  if (box) {
    box.innerHTML = vis.map(n => `<div class="pane" style="display:flex;align-items:center;gap:12px">
      <input type="checkbox" class="tri-ck" data-id="${esc(n.id)}" ${_triSel.has(n.id) ? 'checked' : ''} style="flex:0 0 auto">
      <div style="flex:1">
        <div style="font-weight:500">${esc(n.title)}</div>
        <div class="sub" style="margin-top:2px">${badge(n.type_label, typeColor(n.type), typeBg(n.type))} ${aiBadge(n)} ${n.age} 天 · ${esc(n.created)}</div></div>
      <div class="btnrow"><button class="btn ghost small" onclick="triBody('${esc(n.id)}')">${t('内容')}</button>
        <button class="btn primary small" onclick="triageAct('${esc(n.id)}','active')">${t('转正')}</button>
        <button class="btn ghost small" onclick="triageAct('${esc(n.id)}','suspect')">${t('存疑')}</button>
        <button class="btn ghost small" onclick="triageArchiveId('${esc(n.id)}')">${t('归档')}</button></div></div>`).join('')
      || emptyState(t('没有符合条件的候选'), t('换个关键词，或把筛选条件清掉'));
    // 单条勾选：就地更新集合与汇总，不整列表重绘（避免滚动位置跳动）
    box.querySelectorAll('.tri-ck').forEach(c => c.onchange = () => {
      c.checked ? _triSel.add(c.dataset.id) : _triSel.delete(c.dataset.id);
      updateTriSelUI();
    });
  }
  updateTriSelUI();
}

async function loadTriage() {
  const d = await apiOr('/api/candidates', {}, null);
  if (!d) { const b = $('#triList'); if (b) b.innerHTML = `<div class="errbox">${t('候选列表加载失败：服务未响应')}</div>`; return; }
  _triAll = d.items || [];
  // 刷新后清掉已经不存在的候选（可能已被归档/转正移走），避免勾选幽灵条目
  const alive = new Set(_triAll.map(n => n.id));
  [..._triSel].forEach(id => { if (!alive.has(id)) _triSel.delete(id); });
  const full = d.total >= d.cap;
  const head = $('#triHead');
  if (head) head.innerHTML = `${d.total} ${t('候选')}（${t('多角色评审')} + ${t('人工终审')}）· ${t('上限')} ${d.cap}${full ? ` · <b style="color:var(--danger)">${t('已满')}</b>` : ''} <button class="btn primary small" style="margin-left:8px" title="${t('多角色评审并自动处理')}" onclick="triAutoReview()">${t('多角色评审并自动处理')}</button> <button class="btn ghost small" onclick="triageArchive()">${t('归档超期(≥60天)')}</button>`;
  renderTriage();
}

/* 批量操作：归档走原生批量接口（一次请求）；转正/存疑是单条接口，循环调用后汇总成败再反馈 */
async function triBatch(op) {
  const ids = [..._triSel];
  if (!ids.length) { toast(t('请先勾选候选'), 'warning'); return; }
  if (op === 'archive') {
    const ok = await askConfirm({
      title: t('批量归档'), msg: `${t('将归档选中的')} ${ids.length} ${t('条候选')}。`,
      warn: t('归档后不再出现在审核队列，可在归档目录找回。'), ok: t('归档'),
    });
    if (!ok) return;
    const r = await withBusy(post('/api/candidates/archive', { ids }));
    const moved = ((r && r.moved) || []).length;
    toast(`${t('批量归档')}：${t('成功')} ${moved} ${t('条')}${moved < ids.length ? `，${t('失败')} ${ids.length - moved} ${t('条')}` : ''}`, moved ? 'success' : 'danger');
    _triSel.clear();
    await loadTriage(); loadSide();
    return;
  }
  const status = op === 'active' ? 'active' : 'suspect';
  const label = op === 'active' ? t('批量转正') : t('批量存疑');
  const r = await withBusy(post('/api/candidates/status', { ids, status }));
  const ok = ((r && r.updated) || []).length;
  const fails = ((r && r.failed) || []).slice();
  const tail = fails.length ? `，${t('失败')} ${fails.length} ${t('条')}（${fails.slice(0, 2).join('、')}${fails.length > 2 ? ' …' : ''}）` : '';
  toast(`${label}：${t('成功')} ${ok} ${t('条')}${tail}`, fails.length ? (ok ? 'warning' : 'danger') : 'success');
  _triSel.clear();
  await loadTriage(); loadSide();
}
async function triBody(id) {
  const d = await (await fetch('/api/candidates/body?id=' + encodeURIComponent(id))).json();
  if (!d.body) { toast('无正文'); return; }
  $('#viewMask').classList.add('show');
  $('#viewModalTitle').textContent = d.title;
  $('#viewBody').innerHTML = mdLight(d.body);
  const va = $('#viewActions');
  va.innerHTML = `<button class="btn primary small" onclick="triModalAct('${esc(id)}','active')">转正</button>
    <button class="btn ghost small" onclick="triModalAct('${esc(id)}','suspect')">存疑</button>
    <button class="btn ghost small" onclick="triModalAct('${esc(id)}','archive')">归档</button>`;
  va.style.display = 'flex';
}
/* 正文轻渲染：``` 代码块转 pre，其余按纯文本安全展示（防 XSS） */
function mdLight(t) {
  const parts = String(t).split(/```/);
  return parts.map((seg, i) => i % 2 === 1
    ? `<pre style="white-space:pre-wrap;font-size:12px;background:var(--gray-bg);padding:8px;border-radius:6px;margin:4px 0">${esc(seg)}</pre>`
    : esc(seg).replace(/\n/g, '<br>')).join('');
}
function closeView() { $('#viewMask').classList.remove('show'); }
async function triModalAct(id, op) {
  if (op === 'archive') { await triageArchiveId(id); }
  else { await triageAct(id, op); }
  closeView();
  loadTriage();
}
async function triAutoReview() {
  let d;
  try {
    d = await withBusy(post('/api/candidates/autoreview', {}));
  } catch (e) {
    toast(t('服务未响应，请确认服务运行中'), 'danger');
    return;
  }
  if (!d || typeof d !== 'object') {
    toast(t('评审请求失败，请重试'), 'danger');
    return;
  }
  const extra = (d.failed && d.failed.length) ? `，${t('转正失败')} ${d.failed.length}` : '';
  const arch = (d.archived && d.archived.length) ? `，${t('重复/低质归档')} ${d.archived.length}` : '';
  const veto = (d.veto_kept && d.veto_kept.length) ? `，${d.veto_kept.length} ${t('条涉密/危险留人工')}` : '';
  toast(`${t('评审')} ${d.reviewed} 条 → ${t('已转正')} ${d.promoted.length}、${t('保留')} ${d.kept.length}${arch}${veto}${extra}`, d.promoted.length ? 'success' : 'info');
  loadTriage(); loadSide();
}
/* 单条转正/存疑：走候选专用路由，并按返回判断成败——
   以前调 /api/note/<id>/status 对候选永远 404，却照样提示「已处理」，是假成功。 */
async function triageAct(id, status) {
  const r = await post('/api/candidates/status', { ids: [id], status });
  const ok = !!(r && (r.updated || []).length);
  toast(ok ? t('已处理') : t('处理失败：候选不在队列中'), ok ? 'success' : 'danger');
  loadTriage();
}
async function triageArchiveId(id) { const r = await post('/api/candidates/archive', { ids: [id] }); toast(`${t('已归档')} ${r.moved.length} 条`, 'info'); loadTriage(); }
async function triageArchive() {
  const ok = await askConfirm({ title: '归档超期候选', msg: '将归档停留 ≥60 天且未处理的候选。', warn: '归档后不再出现在审核队列，可在归档目录找回。', ok: '归档' });
  if (!ok) return;
  const r = await withBusy(post('/api/candidates/archive', {}));
  toast(`已归档 ${r.moved.length} 条超期候选`, 'info'); loadTriage();
}

/* 导入 */
async function loadSpaces() {
  const d = await (await fetch('/api/spaces')).json();
  const sel = $('#impSpace');
  sel.innerHTML = '<option value="">— 选空间 —</option>' + d.spaces.map(s => `<option value="${esc(s.path)}">${esc(s.name)}（${s.docs} 文档）</option>`).join('');
  sel.onchange = () => { if (sel.value) $('#impPath').value = sel.value; };
}

/* 核心经验 */
let _hotCache = [];
async function loadHot() {
  const d = await (await fetch('/api/hot')).json();
  _hotCache = d.hot || [];
  $('#hotTitle').textContent = `${t('核心经验')} ${d.count} ${t('条')}（${t('每次会话自动携带 · 上限 20')}）`;
  $('#hotArea').innerHTML = _hotCache.map(n => `<div class="hot-card" style="cursor:pointer" onclick="openHot('${esc(n.id)}')"><div>
    <div style="font-weight:500">${esc(n.title)}</div>
    <div style="font-size:11px;color:var(--text2);margin-top:2px">${badge(n.type_label, typeColor(n.type), typeBg(n.type))} ${n.status} · ${t('点击查看完整内容')}</div></div>
    <button class="btn ghost" onclick="event.stopPropagation();unhot('${esc(n.id)}')">${t('移出核心经验')}</button></div>`).join('')
    || emptyState(t('核心经验为空'), t('在记忆详情里点「★ 核心经验」，它就会随每次会话自动携带'));
}
async function unhot(id) { await post('/api/note/' + encodeURIComponent(id) + '/unhot'); toast(t('已移出核心经验'), 'info'); loadHot(); }

/* 核心经验详情：整条卡片可点。复用候选审核「内容」已在用的 #viewMask 弹窗，
   内容 = 元信息（类型/状态/创建/来源/标签/文件）+ 相关记忆 + 正文全文；
   正文走 mdLight 安全渲染，底部保留「移出核心经验」。 */
async function openHot(id) {
  const n = _hotCache.find(x => x.id === id);
  if (!n) { toast(t('这条已不在核心经验列表里，请刷新后重试'), 'warning'); return; }
  $('#viewModalTitle').textContent = n.title || '';
  const row = (k, v) => v ? `<div><span style="color:var(--text3)">${esc(k)}：</span>${esc(v)}</div>` : '';
  const tagChips = (n.tags || []).map(x =>
    `<span style="display:inline-block;font-size:11px;padding:1px 7px;margin:0 4px 4px 0;border:1px solid var(--hairline);border-radius:10px;color:var(--text2)">${esc(x)}</span>`).join('');
  const meta = `<div style="font-size:12px;color:var(--text2);line-height:1.9;margin-bottom:10px">
    ${row(t('类型'), n.type_label || n.type)}${row(t('状态'), n.status)}${row(t('创建'), n.created)}
    ${row(t('来源'), n.origin || n.source || t('未标注'))}${row(t('文件'), n.path)}
    ${tagChips ? `<div style="margin-top:2px"><span style="color:var(--text3)">${t('标签')}：</span>${tagChips}</div>` : ''}
  </div>`;
  // 相关记忆异步补位：先出正文，避免弹窗等待网络
  $('#viewBody').innerHTML = meta
    + `<div class="sub" id="hotRel" style="margin-bottom:8px">${t('相关记忆加载中…')}</div>`
    + `<div>${mdLight(n.body || t('（这条没有正文）'))}</div>`;
  const va = $('#viewActions');
  va.innerHTML = `<button class="btn ghost small" onclick="unhotFromView('${esc(id)}')">${t('移出核心经验')}</button>`;
  va.style.display = 'flex';
  $('#viewMask').classList.add('show');
  loadHotRel(id, n.title || '');
}
async function loadHotRel(id, title) {
  const box = $('#hotRel');
  if (!box) return;
  let rel = [];
  try {
    const d = await api('/api/search?q=' + encodeURIComponent(String(title).slice(0, 40)) + '&all=1');
    rel = (d.hits || []).filter(h => h.id !== id).slice(0, 5);
  } catch (e) { box.textContent = ''; return; }
  box.innerHTML = rel.length
    ? `<span style="color:var(--text3)">${t('相关记忆')}：</span>`
      + rel.map(h => `<span style="display:inline-block;margin-right:10px">· ${esc(h.title)}</span>`).join('')
    : t('暂无相关记忆');
}
async function unhotFromView(id) { await unhot(id); closeView(); }

/* 统计：4 个关键指标 + 分布（不再是摊大饼式的卡片墙） */
async function loadStats() {
  const d = await apiOr('/api/stats', {}, null);
  if (!d) { $('#statGrid').innerHTML = '<div class="errbox">统计加载失败：服务未响应</div>'; return; }
  _statsCache = d;
  const pct = d.total ? Math.round((d.by_type.procedure || 0) / d.total * 100) : 0;
  const kpi = [
    { n: d.total, l: '记忆总数', d: '笔记 + 配方 + 事实' },
    { n: `${d.hot}<span style="font-size:14px;color:var(--text3)">/20</span>`, l: '核心经验', d: '每次会话自动携带' },
    { n: d.by_status.staged || 0, l: '待审候选', d: '多角色评审 + 人工终审' },
    { n: pct + '%', l: '配方占比', d: '可复用程序性记忆' },
  ];
  $('#statGrid').innerHTML = kpi.map(c => `<div class="stat-card"><div class="n">${c.n}</div><div class="l">${c.l}</div><div class="d">${c.d}</div></div>`).join('');
  const bar = (label, v, max, cls) => `<div class="bar-row"><div class="bl"><span>${esc(label)}</span><b>${v}</b></div>
    <div class="bar ${cls}"><i style="width:${max ? Math.max(3, Math.round(v / max * 100)) : 0}%"></i></div></div>`;
  const maxT = Math.max(1, ...Object.values(d.by_type));
  const maxS = Math.max(1, ...Object.values(d.by_status));
  const typeCard = `<div class="dist-card"><h4>类型分布</h4>
    ${bar('配方 procedure', d.by_type.procedure || 0, maxT, 's')}
    ${bar('经验 lesson', d.by_type.lesson || 0, maxT, '')}
    ${bar('事实 fact', d.by_type.fact || 0, maxT, 'i')}</div>`;
  const stCard = `<div class="dist-card"><h4>状态分布</h4>
    ${bar('使用中 active', d.by_status.active || 0, maxS, 's')}
    ${bar('候选 staged', d.by_status.staged || 0, maxS, 'i')}
    ${bar('存疑 suspect', d.by_status.suspect || 0, maxS, 'w')}
    ${bar('已替代 superseded', d.by_status.superseded || 0, maxS, 'g')}</div>`;
  $('#distArea').innerHTML = typeCard + stCard;
  $('#statFoot').textContent = '索引更新：' + (d.built_at || '—') + ' · 引擎：本地检索引擎 · 无需联网、不上传';
  loadSide();
  loadGc();
}

/* 分层清理体检（只读）：报告各层容量/超期情况，执行请用命令行 mem.py gc --apply */
async function loadGc() {
  const box = $('#gcArea');
  if (!box) return;
  let d;
  try { d = await (await fetch('/api/gc')).json(); }
  catch (e) { box.innerHTML = '<div class="errbox">清理体检加载失败：服务未响应</div>'; return; }
  if (!d || typeof d !== 'object') { box.innerHTML = ''; return; }
  const rows = [
    [t('T1 正式笔记'), `${d.notes} ${t('条')}`, t('永不自动删除，只提示人工复核')],
    [t('T2 候选池'), `${d.candidates} ${t('条')} / ${t('上限')} ${d.cand_cap}`, `≥${d.cand_days} ${t('天未处理')} ${d.cand_over} ${t('条')}`],
    [t('T3 归档区'), `${d.archive} ${t('条')} / ${d.archive_mb}MB`, `${t('最老')} ${d.archive_oldest_days} ${t('天')} · ${t('受保护')} ${d.protected} ${t('条')}`],
    [t('T4 证据流'), `${d.event_files} ${t('个文件')} / ${d.event_mb}MB`, `≥${d.event_days} ${t('天转压缩')}`],
  ];
  box.innerHTML = `<div class="dist-card" style="width:100%">
    <h4>${t('分层清理体检')} <span style="font-weight:400;color:var(--text3);font-size:11px">（${t('只读报告，不改动数据')}）</span></h4>
    ${rows.map(r => `<div style="display:flex;gap:8px;align-items:baseline;padding:5px 0;border-bottom:1px solid var(--line)">
      <span style="min-width:88px;font-weight:500">${r[0]}</span>
      <b style="min-width:120px">${r[1]}</b>
      <span style="font-size:11px;color:var(--text3)">${r[2]}</span></div>`).join('')}
    <div style="font-size:11.5px;color:var(--text2);margin-top:10px;line-height:1.7">
      ${esc(d.advice || '')}<br>
      ${t('执行清理')}：<code>python mem.py gc --apply</code>（${t('默认只压缩不删；需删原文再加 --prune')}）。
    </div></div>`;
}

/* 会话集成 */
async function loadInteg() {
  const h = await (await fetch('/api/hosts')).json();
  $('#hostList').innerHTML = h.hosts.map(x => `<div class="host-row">
    <span class="host-dot ${x.installed ? 'dot-ok' : 'dot-no'}"></span>
    <span style="min-width:110px;font-weight:500">${esc(x.name)}</span>
    <span class="sub" style="flex:1">${x.installed ? '已安装（' + x.updated + '）' : '未安装'} · ${esc(x.path)}</span>
    <button class="btn ${x.installed ? 'ghost' : 'primary'} small" onclick="installHost('${esc(x.name)}')">${x.installed ? '更新' : '安装'}</button></div>`).join('');
  // MCP 安装卡
  const m = await (await fetch('/api/mcpsetup')).json();
  $('#mcpList').innerHTML = m.targets.map(t => `<div class="host-row">
    <span class="host-dot ${t.any_installed ? 'dot-ok' : 'dot-no'}"></span>
    <span style="min-width:110px;font-weight:500">${esc(t.label)}</span>
    <span class="sub" style="flex:1">${t.any_installed ? '已配置' : '未配置'} · ${t.files[0].path}</span>
    <button class="btn ${t.any_installed ? 'ghost' : 'primary'} small" onclick="mcpInstall('${t.key}')">${t.any_installed ? '更新' : '安装'}</button></div>`).join('');
  // 开机启动（开机自启开关）：浏览器模式下自动禁用
  loadAutostart();
}
/* 数据与维护模块入口：原为「接入设置」的③④⑤三张卡，已提升为侧栏一级模块 */
async function loadMaint() {
  // ① 数据位置
  loadConfig();
  // ② 核心经验同步
  $('#hotSyncBtn').onclick = () => { toast('同步中…'); post('/api/hotsync').then(d => { toast(d.ok ? '核心经验已同步' : '失败'); if (d.output) $('#hotSyncInfo').innerHTML = `<pre class="out">${esc(d.output)}</pre>`; }); };
  // ③ 经验沉淀
  $('#harvBtn').onclick = () => { toast('提取中…（后台运行）'); post('/api/harvest').then(d => {
    if (!d.ok) { toast('失败：' + (d.error || '')); return; }
    pollTask(d.task_id, out => { $('#harvInfo').innerHTML = `<pre class="out">${esc(out)}</pre>`; toast('提取完成'); });
  }); };
  const st = await (await fetch('/api/stats')).json();
  $('#hotSyncInfo').textContent = `当前核心经验 ${st.hot} 条（上限 20）· 索引更新于 ${st.built_at || '—'}`;
}
/* 版本与更新模块入口：原为「接入设置」里的第⑨张卡，已提升为侧栏一级模块，
   加载三件事——当前版本、更新检查（24h 缓存，点按钮才强制联网）、更新源配置。 */
async function loadUpdateView() {
  loadVersion();
  loadUpdate(false);
  loadUpdateSources();
}
function fmtCheck(c) {
  if (!c) return '（未知）';
  if (c.error) return '❌ ' + c.error;
  return (c.exists ? '✅ 存在' : '🆕 待创建') + (c.ok ? ' · 可写' : ' · ⚠ ' + (c.note || '不可写')) +
    (c.free_gb != null ? ` · 可用 ${c.free_gb} GB` : '');
}
async function loadConfig() {
  const d = await (await fetch('/api/config')).json();
  $('#cfgHome').value = d.current.home;
  $('#cfgChunks').value = d.current.chunks;
  $('#cfgSpaces').value = d.current.spaces;
  $('#cfgInfo').innerHTML =
    `记忆库：${fmtCheck(d.checks.home)}<br>块库：${fmtCheck(d.checks.chunks)}<br>扫描根：${fmtCheck(d.checks.spaces)}<br>` +
    `<span style="font-size:11px">${esc(d.note)}</span>`;
  $('#cfgSave').onclick = () => {
    const body = { home: $('#cfgHome').value.trim(), chunks: $('#cfgChunks').value.trim(), spaces: $('#cfgSpaces').value.trim() };
    post('/api/config/save', body).then(r => {
      if (r.ok) { toast('配置已保存，重启后生效'); $('#cfgInfo').innerHTML = '✅ 已保存到 ' + esc(r.file) + ' · ' + esc(r.note); }
      else toast('保存失败：' + (r.error || ''));
    });
  };
}
async function mcpInstall(key) {
  const d = await post('/api/mcpinstall', { host: key });
  if (!d.ok) { toast('失败：' + (d.error || '')); return; }
  const lines = (d.results || []).map(r => (r.ok ? '✓ ' : '✕ ') + r.path + (r.ok ? '' : ' — ' + r.msg)).join('\n');
  toast(d.host + ' MCP 已安装', 'success');
  showInfo(d.host + ' · MCP 安装结果', esc(lines) + (d.note ? '\n\n' + esc(d.note) : ''));
  loadInteg();
}
async function installHost(name) { const d = await post('/api/installhost', { host: name }); toast(d.ok ? '已安装到 ' + d.host : '失败：' + (d.error || '')); loadInteg(); }

/* 新建 / 编辑 */
$('#newBtn').onclick = () => { EDIT_ID = null; $('#modalTitle').textContent = '新建记忆'; $('#fTitle').value = ''; $('#fBody').value = ''; $('#fTags').value = ''; $('#fType').value = 'lesson'; $('#fStatus').value = 'staged'; $('#modalMask').classList.add('show'); };
function openEdit(n) {
  if (!n) return;
  EDIT_ID = n.id; $('#modalTitle').textContent = '编辑记忆';
  $('#fTitle').value = n.title; $('#fBody').value = n.body; $('#fTags').value = (n.tags || []).join(',');
  $('#fType').value = n.type; $('#fStatus').value = n.status;
  $('#modalMask').classList.add('show');
}
$('#cancelBtn').onclick = () => $('#modalMask').classList.remove('show');
$('#saveBtn').onclick = async () => {
  const title = $('#fTitle').value.trim(); if (!title) return;
  // 写前查重（借鉴 dsh-memoir needs-resolution）：保存前提示疑似重复
  if (!EDIT_ID) {
    try {
      const s = await (await fetch('/api/search?q=' + encodeURIComponent(title) + '&all=1')).json();
      const sim = (s.hits || []).filter(h => h.score >= 18);
      if (sim.length) {
        const names = sim.slice(0, 3).map(h => '· ' + h.title + '（' + h.score + ' 分）').join('\n');
        const go = await askConfirm({
          title: '疑似重复',
          msg: `库里已有 ${sim.length} 条相近记忆：\n${names}`,
          warn: '继续新建会多一份候选，可在「候选审核」里合并或归档。',
          ok: '仍然新建', danger: false
        });
        if (!go) return;
      }
    } catch (e) { /* 查重失败不阻断 */ }
  }
  const data = { title, body: $('#fBody').value, type: $('#fType').value, status: $('#fStatus').value, tags: $('#fTags').value };
  // 假成功修复：保存失败必须留在弹窗并如实提示（此前 404 也提示"已保存"并关窗）
  const r = EDIT_ID
    ? await post('/api/note/' + encodeURIComponent(EDIT_ID) + '/edit', data)
    : await post('/api/note', { title: data.title, body: data.body, type: data.type, status: data.status, tags: data.tags });
  if (!r.ok) { toast('保存失败：' + (r.error || ('HTTP ' + r.status)), 'danger'); return; }
  $('#modalMask').classList.remove('show'); toast('已保存', 'success'); loadNotes();
};
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#search').focus(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); $('#newBtn').click(); }
});

/* 初始：按当前 VIEW 渲染（browse 首次加载列表；?view=backup 等直达时渲染对应视图）
   先同步页头再渲染，顺序反了的话深链页面的标题会是上一个视图的。 */
applyViewChrome();
render();
/* 再挂一次：i18n.js 在 DOMContentLoaded 里会把所有 data-i18n 元素的文本重写一遍，
   #viewTitle 也带 data-i18n，于是它把上面刚设好的「数据导入」又盖回 HTML 里写死的「记忆浏览」。
   本文件在 i18n.js 之后加载，监听器也就排在它后面，DOMContentLoaded 时再盖一次即可生效。 */
document.addEventListener('DOMContentLoaded', applyViewChrome);
loadSide();
$('#kbdHint').textContent = (navigator.platform || '').toLowerCase().includes('mac') ? '⌘ K' : 'Ctrl K';

/* 数据自动刷新：切回窗口 + 每 30s 轮询（浏览/候选视图），保证展示及时 */
window.addEventListener('focus', () => { if (VIEW === 'browse') loadNotes(); else if (VIEW === 'triage') loadTriage(); });
setInterval(() => { if (VIEW === 'browse') loadNotes(); else if (VIEW === 'triage') loadTriage(); }, 30000);
