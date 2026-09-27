/* pmem Web 前端逻辑 */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const toast = m => { const t = $('#toast'); t.textContent = m; t.classList.add('show'); setTimeout(() => t.classList.remove('show'), 2200); };
const typeColor = t => ({ procedure: 'var(--green)', lesson: 'var(--orange)', fact: 'var(--blue)' }[t] || 'var(--gray)');
const typeBg = t => ({ procedure: 'var(--green-bg)', lesson: 'var(--orange-bg)', fact: 'var(--blue-bg)' }[t] || 'var(--gray-bg)');
const badge = (t, f, b) => `<span class="badge" style="color:${f};background:${b}">${esc(t)}</span>`;
/* 来源小图标：告知记忆条目来自哪里 */
const ORIGIN_ICON = { doc: '📄', dsh: '💠', atomcode: '🧬', harvest: '🤖', mcp: '🔌', manual: '✍️', ai: '✨' };
const ORIGIN_TIP = { doc: '来自 F 盘文档提炼', dsh: '来自 DSH 会话', atomcode: '来自 atomcode 会话', harvest: '自动提取候选', mcp: 'MCP 桥写入（agent）', manual: '手动/界面新建', ai: 'AI 提炼' };
const originIco = o => ORIGIN_ICON[o] ? `<span title="${ORIGIN_TIP[o]}" style="font-size:11px;margin-right:3px">${ORIGIN_ICON[o]}</span>` : '';
/* 状态中文显示（内部仍用英文，界面展示中文） */
const STATUS_LABEL = { active: '使用中', staged: '候选', suspect: '存疑', superseded: '已替代' };
const S = s => STATUS_LABEL[s] || s;
const post = (u, b) => fetch(u, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: b ? JSON.stringify(b) : '{}' }).then(r => r.json());

/* 主题 */
function applyTheme(t) {
  document.documentElement.dataset.theme = t;
  localStorage.setItem('pmem-theme', t);
  $('#themeIco').innerHTML = t === 'dark'
    ? '<path d="M12 3v3m0 12v3m9-9h-3M6 12H3m14.5-6.5-2 2m-11 11 2-2m0-9 2 2m7 7 2 2"/>'
    : '<path d="M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z"/>';
}
applyTheme(localStorage.getItem('pmem-theme') || 'light');
$('#themeBtn').onclick = () => applyTheme(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark');

/* 视图 */
let VIEW = 'browse', CURRENT = null, EDIT_ID = null;
const VIEWS = { browse: '记忆浏览', triage: '候选审核', import: '文档导入', hot: '核心经验', stats: '统计诊断', integ: '接入设置', backup: '数据备份' };
document.querySelectorAll('.nav').forEach(n => n.onclick = () => {
  document.querySelectorAll('.nav').forEach(x => x.classList.remove('active'));
  n.classList.add('active');
  VIEW = n.dataset.view;
  $('#viewTitle').textContent = VIEWS[VIEW];
  const showS = VIEW === 'browse';
  $('#search').style.display = showS ? '' : 'none';
  $('#allBtn').style.display = showS ? '' : 'none';
  $('#newBtn').style.display = showS ? '' : 'none';
  render();
});

async function render() {
  const c = $('#content');
  if (VIEW === 'browse') { c.innerHTML = browseHTML(); bindBrowse(); loadNotes(); }
  else if (VIEW === 'triage') { c.innerHTML = '<div style="width:100%"><div class="pane"><h3>候选审核</h3><div class="sub" id="triHead"></div></div><div id="triList"></div></div>'; loadTriage(); }
  else if (VIEW === 'import') { c.innerHTML = importHTML(); loadSpaces(); bindImport(); }
  else if (VIEW === 'hot') { c.innerHTML = '<div style="width:100%"><h2 style="margin-bottom:14px" id="hotTitle">核心经验</h2><div id="hotArea"></div></div>'; loadHot(); }
  else if (VIEW === 'stats') { c.innerHTML = '<div style="width:100%"><div class="stat-grid" id="statGrid"></div><p style="color:var(--text2);font-size:11.5px;margin-top:14px" id="statFoot"></p></div>'; loadStats(); }
  else if (VIEW === 'integ') { c.innerHTML = integHTML(); loadInteg(); }
  else if (VIEW === 'backup') { c.innerHTML = backupHTML(); loadBackup(); }
}

const backupHTML = () => `<div style="width:100%"><div class="pane"><h3>数据备份 · 多渠道云同步</h3>
  <div class="sub">数据与代码分离：代码在 GitHub 私人仓库；数据经下方渠道冗余备份（本地=事实源，渠道=副本单向同步）</div>
  <div style="margin-top:12px;display:flex;gap:16px;align-items:center;flex-wrap:wrap">
    <label style="display:flex;gap:6px;align-items:center;font-size:12.5px"><input id="bkAuto" type="checkbox" style="transform:scale(1.15)">自动备份（按各渠道频率）</label>
    <label style="font-size:12px;color:var(--text2)">告警邮箱 <input id="bkAlert" placeholder="me@x.com" style="width:150px" /></label>
    <button class="btn primary" onclick="bkSaveAll()">保存全部设置</button>
    <button class="btn" onclick="bkRunAll()">立即备份全部渠道</button>
    <button class="btn ghost" onclick="bkLog()">查看备份日志</button>
  </div>
  <div id="bkChannels" style="margin-top:12px;display:flex;flex-direction:column;gap:10px"></div>
  <div style="margin-top:12px;display:flex;gap:8px;align-items:center">
    <select id="bkNewType" style="width:110px">
      <option value="local">local 目录</option><option value="archive">archive 快照</option>
      <option value="remote">remote 服务器</option><option value="mail">mail 邮箱</option>
    </select>
    <button class="btn ghost" onclick="bkAddChannel()">＋ 新增渠道</button>
    <span class="sub">local/archive 零依赖；remote 需本机 ssh/scp；mail 需 SMTP（pass 留空则读 PMEM_SMTP_PASS）</span>
  </div>
  <div id="bkLogArea" class="sub" style="margin-top:10px;white-space:pre-wrap;font-size:11.5px"></div>
</div></div>`;

const BK_TYPES = { local: '镜像', archive: '快照', remote: '远端', mail: '邮箱' };
const BK_SCOPES = [['notes','笔记'],['events','事件'],['index','索引'],['meta','配置']];
function bkCard(c, i) {
  const state = c.ok === true ? `<span style="color:var(--success)">● 上次成功</span>`
    : c.ok === false ? `<span style="color:var(--danger)">● 失败×${c.fail_count||1}</span>${c.last_error ? ` <span title="${esc(c.last_error)}" style="color:var(--danger)">${esc((c.last_error||'').slice(0,40))}</span>` : ''}`
    : '<span style="color:var(--text2)">○ 未执行</span>';
  return `<div class="pane" style="display:flex;flex-direction:column;gap:8px">
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span style="font-size:11px;padding:1px 8px;border-radius:10px;border:1px solid var(--blue);color:var(--blue)">${BK_TYPES[c.type]||c.type}</span>
      <input data-k="name" value="${esc(c.name)}" style="width:120px;font-weight:600" />
      <label style="display:flex;gap:5px;align-items:center;font-size:12px"><input data-k="enabled" type="checkbox" ${c.enabled?'checked':''}>启用</label>
      <span style="flex:1"></span>${state}<span class="sub">上次 ${c.last}</span>${c.due?' <span style="color:var(--warning)">待备份</span>':''}
    </div>
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:6px">
      <label class="sub" style="display:flex;flex-direction:column;gap:2px">目标（路径/主机:路径/邮箱）<input data-k="target" value="${esc(c.target||'')}" placeholder="${c.type==='local'?'D:/坚果云/evermem':c.type==='archive'?'F:/evermem-snapshots':c.type==='remote'?'user@host:/backup/evermem':'bk@x.com'}" /></label>
      <label class="sub" style="display:flex;flex-direction:column;gap:2px">频率(小时)<input data-k="frequency_hours" type="number" min="1" value="${c.frequency_hours||24}" /></label>
      ${c.type==='archive' ? `<label class="sub" style="display:flex;flex-direction:column;gap:2px">保留份数<input data-k="retention" type="number" min="1" value="${c.retention||7}" /></label>` : ''}
      ${c.type==='remote' ? `<label class="sub" style="display:flex;flex-direction:column;gap:2px">SSH端口<input data-k="ssh_port" type="number" value="${c.ssh_port||22}" /></label>` : ''}
      ${c.type==='mail' ? `<label class="sub" style="display:flex;flex-direction:column;gap:2px">SMTP host<input data-k="smtp_host" value="${esc((c.smtp&&c.smtp.host)||'')}" placeholder="smtp.xx.com" /></label>
        <label class="sub" style="display:flex;flex-direction:column;gap:2px">SMTP port<input data-k="smtp_port" type="number" value="${(c.smtp&&c.smtp.port)||465}" /></label>
        <label class="sub" style="display:flex;flex-direction:column;gap:2px">SMTP 用户<input data-k="smtp_user" value="${esc((c.smtp&&c.smtp.user)||'')}" /></label>
        <label class="sub" style="display:flex;flex-direction:column;gap:2px">SMTP 密码（留空读环境变量）<input data-k="smtp_pass" type="password" /></label>` : ''}
      <label class="sub" style="display:flex;flex-direction:column;gap:2px">范围
        <span style="display:flex;gap:10px">${BK_SCOPES.map(([k,l]) => `<label style="display:flex;gap:3px;align-items:center"><input data-scope="${k}" type="checkbox" ${(c.scope||[]).includes(k)?'checked':''}>${l}</label>`).join('')}</span></label>
    </div>
    <div class="btnrow">
      <button class="btn small" onclick="bkRunChannel(${i})">立即备份本渠道</button>
      <button class="btn ghost small" onclick="bkRestoreChannel(${i})">从本渠道恢复</button>
      <button class="btn ghost small" style="color:var(--danger)" onclick="bkDelChannel(${i})">删除渠道</button>
    </div></div>`;
}
function bkCardData(i) {
  const card = document.querySelectorAll('#bkChannels > .pane')[i];
  const g = k => { const e = card.querySelector(`[data-k="${k}"]`); return e ? (e.type === 'checkbox' ? e.checked : e.value.trim()) : undefined; };
  const c = { type: card.dataset.type, name: g('name') || card.dataset.type, enabled: !!g('enabled'),
    target: g('target') || '', frequency_hours: parseInt(g('frequency_hours') || '24', 10),
    scope: [...card.querySelectorAll('[data-scope]:checked')].map(x => x.dataset.scope) };
  if (c.type === 'archive') c.retention = parseInt(g('retention') || '7', 10);
  if (c.type === 'remote') c.ssh_port = parseInt(g('ssh_port') || '22', 10);
  if (c.type === 'mail') {
    c.smtp = { host: g('smtp_host') || '', port: parseInt(g('smtp_port') || '465', 10),
      user: g('smtp_user') || '', pass: g('smtp_pass') || undefined };
    if (!c.smtp.pass) delete c.smtp.pass;
  }
  return c;
}
async function loadBackup() {
  const d = await (await fetch('/api/backup')).json();
  $('#bkAuto').checked = !!d.auto;
  $('#bkAlert').value = d.alert_email || '';
  $('#bkChannels').innerHTML = d.channels.map((c, i) => `<div data-type="${c.type}" data-name="${esc(c.name)}">${bkCard(c, i)}</div>`).join('')
    || '<div class="empty">尚未配置渠道，点下方「新增渠道」</div>';
  $('#bkLogArea').textContent = '';
}
function bkCollectChannels() {
  const cards = document.querySelectorAll('#bkChannels > .pane');
  return [...cards].map((_, i) => bkCardData(i)).filter(c => c && c.target);
}
async function bkSaveAll() {
  const body = { auto: $('#bkAuto').checked, alert_email: $('#bkAlert').value.trim(), channels: bkCollectChannels() };
  if (!body.channels.length) { toast('请先配置至少一个渠道', 3000); return; }
  const d = await post('/api/backup/save', body);
  toast('设置已保存'); loadBackup(); bkRunAll();
}
async function bkRunAll() {
  const d = await post('/api/backup/run', {});
  if (!d.ok && !d.results) { toast(d.error || '未配置渠道', 3000); return; }
  const fails = (d.results || []).filter(r => !r.ok);
  toast(`已执行 ${(d.results||[]).length} 渠道，失败 ${fails.length}`); loadBackup();
}
async function bkRunChannel(i) {
  await bkSaveAll();
  const card = document.querySelectorAll('#bkChannels > .pane')[i];
  const name = card ? card.querySelector('[data-k="name"]').value.trim() : '';
  const d = await post('/api/backup/run', { channel: name });
  const r = (d.results || [])[0];
  toast(r ? (r.ok ? `[${r.channel}] 同步 ${r.synced} 个` : `[${r.channel}] 失败：${r.error}`) : (d.error || '未执行'), r && r.ok ? 2000 : 4000);
  loadBackup();
}
async function bkRestoreChannel(i) {
  await bkSaveAll();
  const card = document.querySelectorAll('#bkChannels > .pane')[i];
  const name = card ? card.querySelector('[data-k="name"]').value.trim() : '';
  if (!confirm(`将从渠道 [${name}] 恢复数据并覆盖本地同名文件，确定继续？`)) return;
  if (!confirm('再次确认：恢复不可逆，本地最新改动可能被覆盖！')) return;
  const d = await post('/api/backup/restore', { channel: name });
  toast(d.ok ? `已恢复 ${d.count} 个文件` : (d.error || '恢复失败'), d.ok ? 2000 : 4000);
  loadBackup();
}
function bkDelChannel(i) { const el = document.querySelectorAll('#bkChannels > .pane')[i]; if (el) el.remove(); }
function bkAddChannel() {
  const type = $('#bkNewType').value;
  const box = document.createElement('div');
  box.dataset.type = type;
  box.innerHTML = bkCard({ type, name: type === 'local' ? '主备份' : type, enabled: true, target: '', scope: BK_SCOPES.map(x=>x[0]), frequency_hours: 24, retention: 7, ssh_port: 22, smtp: {} }, 0);
  $('#bkChannels').appendChild(box);
}
async function bkLog() {
  const d = await (await fetch('/api/backup/log')).json();
  $('#bkLogArea').textContent = '—— backup.log（最近 50 行）——\n' + (d.lines || []).join('\n');
}

const browseHTML = () => `<div class="col list-col"><div class="list-head" id="listHead">共 0 条</div><div id="noteList"></div></div>
  <div class="col detail-col"><div class="detail-top"><div id="detailInner"><div class="empty">← 选择一条笔记查看</div></div></div>
  <div class="opbar" id="opbar" style="display:none">
  <button class="btn ghost" id="editBtn">✎ 编辑</button><button class="btn ghost" id="hotBtn">★ 进核心经验</button>
  <button class="btn ghost" id="activeBtn">转正</button><button class="btn ghost" id="suspectBtn">存疑</button>
  <button class="btn ghost" id="archiveBtn">归档</button></div></div>`;

const importHTML = () => `<div style="width:100%"><div class="pane"><h3>文档导入</h3>
  <div class="btnrow" style="margin-bottom:8px">
  <select id="impSpace" style="min-width:220px"></select>
  <input type="text" id="impPath" placeholder="或输入任意盘/目录路径" style="flex:1;min-width:160px" list="impHist">
  <datalist id="impHist"></datalist>
  <button class="btn ghost" id="impScan">扫描</button><button class="btn primary" id="impExtract">提取到块库</button></div>
  <div class="sub" id="impInfo">选择空间或输入路径后点「扫描」</div></div>
  <div style="display:flex;gap:18px">
  <div class="col list-col" style="width:45%">
    <div class="list-head" style="display:flex;gap:8px;align-items:center">
      <input id="blkFilter" placeholder="过滤块名…" style="flex:1;padding:3px 10px;font-size:12px"><span id="blkCount"></span></div>
    <div id="blkList" style="flex:1;overflow:auto;padding:8px"></div></div>
  <div class="col detail-col"><div class="detail-top">
    <div class="btnrow" style="margin-bottom:6px"><button class="btn ghost small" id="copyBlkBtn">⧉ 复制块内容</button><span class="sub" id="blkPath"></span></div>
    <pre class="out" id="blkPreview" style="max-height:none;white-space:pre-wrap;flex:1;overflow:auto">← 点击块预览</pre></div></div></div></div>`;

const integHTML = () => `<div style="width:100%">
  <div class="pane"><h3>① 技能安装</h3><div class="sub" style="margin-bottom:8px">选中 AI 助手 → 安装记忆技能，让每个新会话「开始查记忆、行动前查记忆、收尾存记忆」</div><div id="hostList"></div></div>
  <div class="pane"><h3>② MCP 工具接入</h3><div class="sub" style="margin-bottom:8px">把恒忆标准 MCP 工具（查记忆/存记忆/更新/核心经验）写入各助手配置——DSH/WorkBuddy/Claude 均可原生调用。WorkBuddy/DSH 需重启或新会话生效；WorkBuddy 还须在连接器页点 Trust。</div><div id="mcpList"></div></div>
  <div class="pane"><h3>③ 数据位置（可自由选择）</h3><div class="sub" style="margin-bottom:8px">记忆库 / 块库 / 扫描根目录可指向任意本机路径（含权限与空间检查）。配置存 pmem_config.json，所有会话共享；修改后重启生效。</div>
    <div class="btnrow" style="margin-bottom:6px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">记忆库</label><input id="cfgHome" placeholder="记忆库目录（笔记/index）" style="flex:2;min-width:140px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">块库</label><input id="cfgChunks" placeholder="文本块目录" style="flex:2;min-width:140px">
      <label style="min-width:52px;font-size:12px;color:var(--text2);align-self:center">扫描根</label><input id="cfgSpaces" placeholder="扫描根目录（如 F:/）" style="flex:2;min-width:140px">
      <button class="btn primary" id="cfgSave">保存</button>
    </div>
    <div class="sub" id="cfgInfo">读取配置中…</div></div>
  <div class="pane"><h3>④ 核心经验同步</h3><div class="sub" id="hotSyncInfo"></div><div class="btnrow" style="margin-top:8px"><button class="btn primary" id="hotSyncBtn">同步核心经验 → 宿主必读文件</button></div></div>
  <div class="pane"><h3>⑤ 经验沉淀</h3><div class="sub" id="harvInfo"></div><div class="btnrow" style="margin-top:8px"><button class="btn primary" id="harvBtn">提取近 3 天会话经验</button></div></div>
  <div class="pane"><h3>⑥ 兼容说明</h3><div class="sub">· WorkBuddy 桌面端禁用第三方插件钩子（宿主信任模型），自建能力走技能 + MCP。<br>· DSH：从 $DSH_HOME/skills（用户级）发现技能文件，目录被监视、热刷新。<br>· MCP 工具：evermem_mcp.py 标准 stdio，4 个工具，多助手通用。<br>· 核心经验注入：MEMORY.md 核心经验区 → 新会话上下文（上限 20，有进有出）。</div></div></div>`;

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
  $('#archiveBtn').onclick = () => act(CURRENT, 'status', 'superseded');
}
function bindImport() {
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
  $('#impExtract').onclick = () => {
    const p = $('#impPath').value.trim() || $('#impSpace').value;
    if (!p) { toast('先选空间或输入路径'); return; }
    const name = p.split(/[\\/]/).pop();
    if (!confirm('提取 ' + name + ' 到块库？（大目录可能需数分钟）')) return;
    $('#impInfo').innerHTML = '提取中…（后台运行，完成后自动刷新）'; toast('提取 ' + p);
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
  el.innerHTML = list.map(b => `<div class="note-item" data-path="${esc(b.path)}">${esc(b.name)}<div class="m">${b.size} B</div></div>`).join('') || '<div class="empty">无块（先扫描/提取）</div>';
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
  const iv = setInterval(async () => {
    const d = await (await fetch('/api/task/status?task=' + encodeURIComponent(taskId))).json();
    if (d.state === 'done') { clearInterval(iv); onDone(d.output || ''); }
    else if (d.state === 'error') { clearInterval(iv); toast('任务失败：' + (d.output || '').slice(0, 80)); }
  }, 1500);
}
$('#search').addEventListener('input', e => { clearTimeout(deb); deb = setTimeout(() => loadNotes(), 250); });
$('#allBtn').onclick = () => {
  $('#allBtn').classList.toggle('on');
  $('#allBtn').style.background = $('#allBtn').classList.contains('on') ? 'var(--blue)' : 'transparent';
  $('#allBtn').style.color = $('#allBtn').classList.contains('on') ? '#fff' : 'var(--text2)';
  loadNotes();
};
async function loadNotes() {
  const q = $('#search').value.trim(); let list;
  if (q) {
    const d = await (await fetch('/api/search?q=' + encodeURIComponent(q) + '&all=1')).json();
    list = d.hits.map(h => ({ id: h.id, title: h.title, type: h.type, type_label: h.type_label, status: h.status, hot: false, tags: [], score: h.score }));
  } else {
    const d = await (await fetch('/api/notes')).json();
    list = d.notes.filter(n => $('#allBtn').classList.contains('on') || n.status === 'active');
  }
  $('#noteList').innerHTML = list.map(n => `<div class="note-item" data-id="${esc(n.id)}"><div class="t">${originIco(n.origin)}${esc(n.title)}</div>
    <div class="m">${badge(n.type_label, typeColor(n.type), typeBg(n.type))}${n.hot ? '★ ' : ''}${S(n.status)}${n.score ? ' · ' + n.score + '分' : ''}</div></div>`).join('') || '<div class="empty">无笔记</div>';
  $('#listHead').textContent = `共 ${list.length} 条${q ? '（搜索：' + q + '）' : ''}`;
  if (list.length) showNote(list[0].id);
}
async function showNote(id) {
  const d = await (await fetch('/api/note?id=' + encodeURIComponent(id))).json(); if (!d.note) return;
  CURRENT = d.note; const n = d.note;
  const bs = [badge(n.type_label, typeColor(n.type), typeBg(n.type))];
  if (n.hot) bs.push(badge('★ 核心经验', 'var(--gold)', 'var(--gold-bg)'));
  bs.push(badge(S(n.status), { active: 'var(--green)', staged: 'var(--orange)', suspect: 'var(--gray)', superseded: 'var(--text2)' }[n.status] || 'var(--gray)', 'var(--gray-bg)'));
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
  await post('/api/note/' + encodeURIComponent(n.id) + '/' + action, extra ? { status: extra } : {});
  toast('已更新'); loadNotes();
}

/* 候选 */
const AI_COLOR = { promote: 'var(--success)', keep: 'var(--warning)', archive: 'var(--danger)', archive_dup: 'var(--danger)' };
function aiBadge(r) {
  const c = AI_COLOR[r.ai_verdict] || 'var(--text2)';
  return `<span style="font-size:11px;padding:1px 8px;border-radius:10px;border:1px solid ${c};color:${c};margin-right:6px">AI ${r.ai_score} 分 · ${r.ai_label}</span>`;
}
async function loadTriage() {
  const d = await (await fetch('/api/candidates')).json();
  const full = d.total >= d.cap;
  $('#triHead').innerHTML = `${d.total} 条候选（AI 建议 + 人工终审）· 上限 ${d.cap} · 超30天 ${d.over30} · 超60天 ${d.over60}${full ? ' · <b style="color:var(--danger)">已满，请处理</b>' : ''} <button class="btn ghost small" style="margin-left:8px" onclick="triageArchive()">归档超期(≥60天)</button>`;
  $('#triList').innerHTML = d.items.map(n => `<div class="pane" style="display:flex;align-items:center;gap:12px"><div style="flex:1">
    <div style="font-weight:500">${esc(n.title)}</div>
    <div class="sub" style="margin-top:2px">${badge(n.type_label, typeColor(n.type), typeBg(n.type))} ${aiBadge(n)} ${n.age} 天 · ${esc(n.created)}${n.ai_sim_id ? ' · 疑似重复 ' + esc(n.ai_sim_id) : ''}</div></div>
    <div class="btnrow"><button class="btn primary small" onclick="triageAct('${esc(n.id)}','active')">转正</button>
    <button class="btn ghost small" onclick="triageAct('${esc(n.id)}','suspect')">存疑</button>
    <button class="btn ghost small" onclick="triageArchiveId('${esc(n.id)}')">归档</button></div></div>`).join('') || '<div class="empty">没有候选</div>';
}
async function triageAct(id, status) { await post('/api/note/' + encodeURIComponent(id) + '/status', { status }); toast('已处理'); loadTriage(); }
async function triageArchiveId(id) { const r = await post('/api/candidates/archive', { ids: [id] }); toast(`已归档 ${r.moved.length} 条`); loadTriage(); }
async function triageArchive() { const r = await post('/api/candidates/archive', {}); toast(`已归档 ${r.moved.length} 条超期候选`); loadTriage(); }

/* 导入 */
async function loadSpaces() {
  const d = await (await fetch('/api/spaces')).json();
  const sel = $('#impSpace');
  sel.innerHTML = '<option value="">— 选空间 —</option>' + d.spaces.map(s => `<option value="${esc(s.path)}">${esc(s.name)}（${s.docs} 文档）</option>`).join('');
  sel.onchange = () => { if (sel.value) $('#impPath').value = sel.value; };
}

/* 核心经验 */
async function loadHot() {
  const d = await (await fetch('/api/hot')).json();
  $('#hotTitle').textContent = `核心经验 ${d.count} 条（每次会话自动携带 · 上限 20）`;
  $('#hotArea').innerHTML = d.hot.map(n => `<div class="hot-card"><div>
    <div style="font-weight:500">${esc(n.title)}</div>
    <div style="font-size:11px;color:var(--text2);margin-top:2px">${badge(n.type_label, typeColor(n.type), typeBg(n.type))} ${n.status}</div></div>
    <button class="btn ghost" onclick="unhot('${esc(n.id)}')">移出核心经验</button></div>`).join('') || '<div class="empty">核心经验为空</div>';
}
async function unhot(id) { await post('/api/note/' + encodeURIComponent(id) + '/unhot'); toast('已移出'); loadHot(); }

/* 统计 */
async function loadStats() {
  const d = await (await fetch('/api/stats')).json();
  const t = { fact: '事实', lesson: '经验', procedure: '配方' };
  const cards = [
    { n: d.total, l: '笔记总数' }, { n: d.hot, l: '核心经验（/20）' },
    ...Object.entries(d.by_type).map(([k, v]) => ({ n: v, l: '类型：' + (t[k] || k) })),
    ...Object.entries(d.by_status).map(([k, v]) => ({ n: v, l: '状态：' + k })),
  ];
  $('#statGrid').innerHTML = cards.map(c => `<div class="stat-card"><div class="n">${c.n}</div><div class="l">${c.l}</div></div>`).join('');
  $('#statFoot').textContent = '索引更新：' + (d.built_at || '—') + ' · 引擎：本地检索引擎 · 无需联网、不上传';
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
  $('#hotSyncBtn').onclick = () => { toast('同步中…'); post('/api/hotsync').then(d => { toast(d.ok ? '核心经验已同步' : '失败'); if (d.output) $('#hotSyncInfo').innerHTML = `<pre class="out">${esc(d.output)}</pre>`; }); };
  $('#harvBtn').onclick = () => { toast('提取中…（后台运行）'); post('/api/harvest').then(d => {
    if (!d.ok) { toast('失败：' + (d.error || '')); return; }
    pollTask(d.task_id, out => { $('#harvInfo').innerHTML = `<pre class="out">${esc(out)}</pre>`; toast('提取完成'); });
  }); };
  const st = await (await fetch('/api/stats')).json();
  $('#hotSyncInfo').textContent = `当前核心经验 ${st.hot} 条（上限 20）· 索引更新于 ${st.built_at || '—'}`;
  // 数据位置配置
  loadConfig();
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
  const lines = (d.results || []).map(r => (r.ok ? '✅ ' : '❌ ') + r.path + (r.ok ? '' : ' — ' + r.msg)).join('\n');
  toast(d.host + ' MCP 已安装');
  alert(d.host + ' MCP 安装结果：\n\n' + lines + '\n\n' + (d.note || ''));
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
        const names = sim.slice(0, 3).map(h => '· ' + h.title + '（' + h.score + '分）').join('\n');
        if (!confirm('存在 ' + sim.length + ' 条疑似重复笔记：\n' + names + '\n\n仍要新建吗？（可在候选审核里合并）')) return;
      }
    } catch (e) { /* 查重失败不阻断 */ }
  }
  const data = { title, body: $('#fBody').value, type: $('#fType').value, status: $('#fStatus').value, tags: $('#fTags').value };
  if (EDIT_ID) await post('/api/note/' + encodeURIComponent(EDIT_ID) + '/edit', data);
  else await post('/api/note', { title: data.title, body: data.body, type: data.type });
  $('#modalMask').classList.remove('show'); toast('已保存'); loadNotes();
};
document.addEventListener('keydown', e => {
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); $('#search').focus(); }
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'n') { e.preventDefault(); $('#newBtn').click(); }
});

/* 初始 */
loadNotes();
