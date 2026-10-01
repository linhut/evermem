/*!
 * 恒忆 Evermem (pmem) · Copyright (c) 2026 Jose-AI · 版权所有
 * 仓库: https://github.com/linhut/evermem
 * 官网: https://www.linhut.cn
 * 许可: MIT License（SPDX-License-Identifier: MIT，详见根目录 LICENSE）
 */

/* ============================================================
   i18n：中英语言切换
   - 中文原文即 key：t('记忆浏览') 在 en 字典里查翻译，查不到回退原文
   - 语言持久化 localStorage['pmem-lang']（zh/en），切换后整页刷新
   - 静态文案：HTML 上标 data-i18n（文本）/ data-i18n-ph（placeholder），
     DOMContentLoaded 时自动应用
   - 语言按钮 #langBtn 置于主题按钮上方（index.html）
   ============================================================ */
(function () {
  const STORE_KEY = 'pmem-lang';

  const EN = {
    /* 缺失键补齐（2026-10-01 复核审计；此前英文界面回退中文） */
    '个渠道': 'channels', '主位置': 'primary location',
    '保存并立即备份': 'Save & back up now', '已配置': 'configured',
    '仅桌面版可设置': 'desktop only', '复制块内容': 'Copy block content',
    '点击块预览': 'Click block to preview', '已移出核心经验': 'Removed from hot layer',
    '核心经验为空': 'No hot entries yet',
    '在记忆详情里点「★ 核心经验」，它就会随每次会话自动携带':
        'Star a note as ★ hot layer in its detail view; it will be carried into every session',
    '内置下载': 'Download', '下载安装包': 'Download installer',
    '更新并重启': 'Update & restart', '下载中…': 'Downloading…',
    '下载完成，可更新': 'Downloaded — update ready', '下载失败：': 'Download failed: ',
    '重试': 'Retry', '更新失败：': 'Update failed: ', '更新已启动': 'Update started',
    '将替换当前程序并重启；旧版自动备份，可手动回滚。':
        'The current program will be replaced and restarted; the old build is backed up automatically for manual rollback.',
    '安装版更新将静默安装新版安装包，数据保留在系统数据目录。':
        'The installer will run silently in the background; your data stays in the system data folder.',
    /* 关于（品牌落地） */
    '关于恒忆': 'About Evermem',
    '个人跨会话经验记忆系统': 'Personal Cross-Session Memory System',
    '经验自动进库、跨会话复用、全本地零云端': 'Capture experience automatically, reuse across sessions, local-first & zero-cloud.',
    '作者：': 'Author: ',
    '官网：': 'Homepage: ',
    '源码：': 'Source: ',
    /* 侧栏 */
    '记忆': 'Memory', '系统': 'System',
    '记忆浏览': 'Browse', '数据导入': 'Import Data',
    '核心经验': 'Hot', '接入设置': 'Integrate', '数据备份': 'Backup',
    '深色模式': 'Dark mode', '浅色模式': 'Light mode',
    '索引读取中…': 'Loading index…',
    '本地 · 零云端': 'Local · No cloud',
    /* 顶栏 */
    '搜索记忆…（融合通信 / 方案 / 公文）': 'Search memory…',
    '含候选': 'All', '＋ 新建': '+ New', 'Ctrl K': 'Ctrl K',
    /* 浏览视图 */
    '共 0 条': '0 notes', '按相关度排序': 'by relevance',
    '选择一条记忆': 'Select a note', '左侧列表点选，或用 Ctrl+K 搜索': 'Pick from the list, or press Ctrl+K to search',
    '编辑': 'Edit', '★ 核心经验': '★ Hot', '转正': 'Promote', '存疑': 'Suspect', '标记已替代': 'Supersede',
    '使用中': 'Active', '候选': 'Staged', '已替代': 'Superseded',
    '经验': 'Lesson', '配方': 'Procedure', '事实': 'Fact',
    '没有匹配的记忆': 'No matching notes', '输入关键词开始搜索，或选择左侧类型': 'Type to search or pick a type',
    /* 来源 */
    '来自 F 盘文档提炼': 'From doc distillation', '来自 DSH 会话': 'From DSH session',
    '来自 atomcode 会话': 'From atomcode session', '自动提取候选': 'Auto-harvested',
    'MCP 桥写入（agent）': 'Written via MCP (agent)', '手动/界面新建': 'Created manually', 'AI 提炼': 'AI distilled',
    /* 新建 / 编辑弹窗 */
    '新建记忆': 'New note', '编辑记忆': 'Edit note', '标题': 'Title', '一句话标题': 'One-line title',
    '类型': 'Type', '状态': 'Status', '标签（逗号分隔）': 'Tags (comma separated)',
    '正文（Markdown）': 'Body (Markdown)', '取消': 'Cancel', '保存': 'Save',
    'staged（候选）': 'staged', '已保存': 'Saved',
    /* 确认 / 信息弹窗 */
    '确认操作': 'Confirm', '确认': 'Confirm', '关闭': 'Close',
    /* 候选审核 */
    '候选审核': 'Candidate Review',
    '多角色评审': 'multi-role review', '人工终审': 'manual review', '上限': 'cap', '已满': 'FULL',
    '多角色评审并自动处理': 'Multi-role review & auto-process',
    '归档超期(≥60天)': 'Archive old (≥60d)',
    '内容': 'View', '归档': 'Archive',
    '没有待审候选': 'No pending candidates',
    '自动提取的候选会先落在这里，人工终审后才转入正式记忆': 'Auto-harvested candidates land here; promote after final review',
    '已处理': 'Done', '候选列表加载失败：服务未响应': 'Failed to load candidates: server not responding',
    '服务未响应，请确认服务运行中': 'Server not responding — is the service running?',
    '评审请求失败，请重试': 'Review request failed, please retry',
    '已归档': 'Archived',
    '评审': 'Reviewed', '已转正': 'Promoted', '保留': 'Kept', '重复/低质归档': 'Dup/low-quality archived',
    '条涉密/危险留人工': 'sensitive/dangerous kept for human', '转正失败': 'promote failed',
    '低质已归档': 'archived', '条否决留人工（敏感/危险）': ' vetoed & kept for human (sensitive/dangerous)',
    '无正文': 'No body',
    /* 候选审核 · 搜索筛选与批量操作 */
    '搜索候选标题…': 'Search candidate titles…',
    '全部状态': 'All statuses', '全部类型': 'All types', '全部建议': 'All suggestions',
    '建议转正': 'Promote', '保留观察': 'Keep watching', '建议归档': 'Archive',
    '否决（涉敏/危险）': 'Veto (sensitive/dangerous)',
    '全选': 'Select all', '反选': 'Invert', '清空选择': 'Clear',
    '已选': 'Selected', '当前筛选': 'shown',
    '批量转正': 'Promote selected', '批量存疑': 'Mark suspect', '批量归档': 'Archive selected',
    '没有符合条件的候选': 'No candidates match',
    '换个关键词，或把筛选条件清掉': 'Try another keyword, or clear the filters',
    '请先勾选候选': 'Select candidates first',
    '处理失败：候选不在队列中': 'Failed: candidate no longer in the queue',
    '将归档选中的': 'Will archive', '条候选': 'candidates',
    '归档后不再出现在审核队列，可在归档目录找回。': 'Archived items leave the queue; find them in the archive folder.',
    '成功': 'ok',
    /* 核心经验 */
    '核心经验（常驻）': 'Hot layer (resident)',
    '同步热层 → 宿主必读文件': 'Sync hot layer → host must-read file',
    '热层已满（20/20）：先移除再添加': 'Hot layer full (20/20): remove first',
    '已同步': 'Synced', '同步中…': 'Syncing…', '提取近 3 天会话经验': 'Extract 3-day session experience',
    '同步核心经验 → 宿主必读文件': 'Sync hot layer → host must-read file',
    /* 核心经验 · 条目详情（点卡片打开，复用 #viewMask 弹窗） */
    '移出核心经验': 'Remove from hot layer',
    '点击查看完整内容': 'Click to view full content',
    '这条已不在核心经验列表里，请刷新后重试': 'No longer in the hot layer — refresh and retry',
    '每次会话自动携带 · 上限 20': 'auto-carried each session · cap 20',
    '创建': 'Created', '文件路径': 'File', '标签': 'Tags', '未标注': 'unspecified',
    '相关记忆': 'Related memories', '相关记忆加载中…': 'Loading related memories…',
    '暂无相关记忆': 'No related memories', '（这条没有正文）': '(no body)',
    /* 统计 */
    '笔记总数': 'Notes', '证据条数': 'Events', '近30天活跃': 'Active 30d',
    '类型分布': 'By type', '状态分布': 'By status', '热层上限': 'Hot cap',
    '统计诊断': 'Stats & Diagnosis',
    /* 分层清理体检（GC，只读报告） */
    '分层清理体检': 'Retention Check (GC)', '只读报告，不改动数据': 'read-only, no data is modified',
    'T1 正式笔记': 'T1 Notes', 'T2 候选池': 'T2 Candidates', 'T3 归档区': 'T3 Archive', 'T4 证据流': 'T4 Evidence',
    '条': 'items', '天未处理': 'd unprocessed', '最老': 'oldest', '天': 'd',
    '受保护': 'protected', '个文件': 'files', '天转压缩': 'd → compress',
    '永不自动删除，只提示人工复核': 'never auto-deleted; flagged for manual review only',
    '执行清理': 'To run cleanup', '默认只压缩不删；需删原文再加 --prune':
      'compacts only by default; add --prune to delete originals',
    /* 数据导入（文档 / 其他记忆，同一模块两个来源） */
    '文档导入': 'Import Documents', '或输入任意盘/目录路径': 'or type a drive/dir path',
    '扫描': 'Scan', '提取到块库': 'Extract to chunk store',
    '选择空间或输入路径后点「扫描」': 'Pick a space or type a path, then Scan',
    '过滤块名…': 'Filter blocks…', '⧉ 复制块内容': '⧉ Copy block', '← 点击块预览': '← click a block to preview',
    '其他记忆导入': 'Import External Memory',
    '两种来源，同一套流程': 'Two sources, one flow',
    '把存量文档切成文本块供 AI 提炼': 'splits documents into chunks for AI distillation',
    '把别的工具导出的记忆收进笔记库': 'brings memories exported from other tools into your notes',
    /* 文档导入 · 操作指引（原位置是重名的 h3 标题，已换成步骤与注意事项） */
    '导入步骤': 'Steps', '注意': 'Note',
    '选择空间或输入任意目录': 'pick a space or type any directory',
    '查看文档构成与体量': 'see composition and size',
    '生成可检索文本块': 'generate searchable chunks',
    '提取只写入块库、不直接进记忆库，后续由候选审核决定是否转正':
      'extraction only writes to the chunk store, not to your notes — triage decides what gets promoted',
    '切块不改动原文档': 'your original documents are never modified',
    '涉密或敏感目录请先确认范围再扫描': 'confirm the scope before scanning confidential directories',
    /* 其他记忆导入 · ① 导出记忆提示词（复制出去） */
    // 序号 ①② 由 HTML 直接拼在标题前（语言无关），译文里不要再带，否则渲染成「① ①」
    '导出记忆提示词': 'Export-memory prompt',
    '粘贴导入记忆': 'Paste & import memory',
    '复制提示词': 'Copy prompt', '展开全文': 'Expand', '收起全文': 'Collapse',
    '把这段提示词复制到任意 AI 工具（新开会话），让它产出你的使用画像；再把画像整段粘贴到下方导入框收进笔记库。':
      'Copy this prompt into any AI tool (in a new session) to produce your usage profile; then paste the whole profile into the box below to file it into your notes.',
    '提示词只有一份，改模板即生效': 'single source of truth — edit the template to change it',
    '字': 'chars',
    '未能读取提示词模板': 'could not read the prompt template',
    '读取失败：服务未响应': 'read failed: server not responding',
    '提示词还没加载出来，稍等一下': 'prompt not loaded yet — try again in a moment',
    '提示词已复制：粘到任意 AI 的新会话，拿到画像再贴回下方': 'Prompt copied — paste it into a new AI session, then paste the profile back below',
    '浏览器拒绝了剪贴板：已帮你全选，按 Ctrl+C': 'Clipboard blocked — text selected, press Ctrl+C',
    '支持画像导出格式（## 分类 + [日期] - 条目）、带 frontmatter 的 Markdown、JSON 导出，也可直接指定目录批量收。':
      'Accepts profile exports (## category + [date] - item), Markdown with frontmatter, JSON exports, or a directory.',
    '自动识别格式': 'Auto-detect format', '画像导出格式': 'Profile export format',
    '或指定文件 / 目录路径（可选）': 'or a file / directory path (optional)',
    '解析': 'Parse',
    '把别的工具的记忆导出贴在这里…': 'Paste a memory export from another tool here…',
    '粘贴内容后点「解析」，或填路径后点「解析」': 'Paste content or fill a path, then Parse',
    '尚未解析': 'nothing parsed yet',
    '全选可导入': 'Select all importable', '导入选中': 'Import selected',
    '导入后状态为 staged：可在「记忆浏览」查看，人工确认后转正才参与检索召回。':
      'Imported as staged: visible in Browse, but excluded from recall until you promote it.',
    '过滤条目…': 'Filter items…', '点击条目预览': 'click an item to preview',
    '解析中…': 'Parsing…', '解析失败：服务未响应': 'Parse failed: server not responding',
    '解析失败': 'Parse failed', '格式': 'Format', '来源': 'Source',
    '共': 'total', '可导入': 'importable', '疑似重复': 'possible dupes', '已存在': 'already exists',
    '先粘贴内容或填写路径': 'Paste content or enter a path first',
    '解析出': 'parsed', '先勾选要导入的条目': 'Select items first',
    '将写入': 'Will write', '到笔记库': 'to the note store',
    '导入后状态为 staged，需人工转正才参与检索召回。': 'Imported as staged; promote manually to enable recall.',
    '开始导入': 'Start import', '已导入': 'imported',
    '导入失败：服务未响应': 'Import failed: server not responding', '导入失败：': 'Import failed: ',
    '还没有解析出条目': 'No items parsed', '粘贴记忆导出内容后点「解析」': 'Paste an export and click Parse',
    '（staged）': '(staged)',
    /* 接入设置 */
    /* 接入设置（只留对外接入 + 本机运行方式） */
    '① 技能安装': '① Skill install', '② MCP 工具接入': '② MCP tools',
    '③ 开机启动': '③ Launch at login', '④ 兼容说明': '④ Compatibility',
    /* 数据与维护（一级模块） */
    '数据与维护': 'Data & Maintenance',
    '① 数据位置（可自由选择）': '① Data location',
    '② 核心经验同步': '② Hot layer sync', '③ 经验沉淀': '③ Harvest',
    '数据位置改完需重启生效；同步与沉淀都是本地动作，不上传任何内容。':
      'Data location changes take effect after restart; sync and harvest run locally, nothing is uploaded.',
    /* 版本与更新（一级模块） */
    '版本与更新': 'Version & Update',
    '① 更新检查': '① Update check', '② 更新源': '② Update sources',
    '检查走官方云清单 + GitHub 直连 + 加速镜像并发取最快的一个；更新可内置下载、一键应用。':
      'Checks official cloud manifest + GitHub direct + mirrors in parallel, takes the fastest; updates can be downloaded and applied in one click.',
    '仅桌面版': 'Desktop only', '开机自启动': 'Launch at login',
    '当前版本：': 'Version: ', '查看最新版本': 'Check latest',     '版本号未知': 'Unknown version',
    '检查更新': 'Check for updates', '检查中…': 'Checking…', '已是最新版本': 'Up to date',
    '发现新版本：': 'New version: ', '当前：': 'current: ', '下载更新': 'Download',
    '镜像加速下载': 'Mirror (faster)',
    '自动检查更新': 'Check automatically',
    '打开设置页时自动检查一次，结果缓存 24 小时': 'Check once when settings open; result cached for 24h',
    '官方清单地址（云服务器固定文件；留空则回退 GitHub 直连 + 镜像）': 'Official manifest URL (fixed file on our cloud server; blank falls back to GitHub direct + mirrors)',
    '官方云服务器固定清单，上传一次长期有效（只下发镜像列表，版本仍由 GitHub 说了算）；留空则直接走 GitHub 直连 + 镜像。': 'A fixed manifest on our cloud server, uploaded once (mirror list only — versions always come from GitHub); blank uses GitHub direct + mirrors.',
    '留空': 'blank',
    '加速镜像（一行一个，用于版本检查与下载）': 'Acceleration mirrors (one per line, for check and download)',
    '恢复默认': 'Restore defaults',
    '下载时额外追加': 'Added for download:',
    '只通文件、不通接口': 'files only, not API',
    '个候选': 'candidates',
    '更新源配置读取失败': 'Failed to read update source config',
    '保存失败：': 'Save failed: ',
    '更新检查失败：': 'Update check failed: ', '已尝试：': 'Tried: ', '缓存结果': 'cached',
    '手动下载': 'Manual download',
    '当前版本仍可正常使用，可稍后重试或手动下载。': 'The current version keeps working; retry later or download manually.',
    '发布页打开失败': 'Failed to open release page',
    '有新版本时，下载新文件覆盖原文件即可；数据不会丢失。': 'Download the new release and overwrite the old file; your data will stay safe.',
    '已开启': 'On', '未开启': 'Off', '不支持：': 'Not supported: ', '设置失败：': 'Failed: ',
    '系统登录后自动启动恒忆，并静默驻留系统托盘。': 'Starts Evermem after login and stays in the system tray.',
    '记忆库': 'Memory root', '块库': 'Chunk store', '扫描根': 'Scan root',
    '读取配置中…': 'Loading config…',
    '记忆库目录（笔记/index）': 'memory dir (notes/index)',
    '文本块目录': 'chunk dir', '扫描根目录（如 F:/）': 'scan root (e.g. F:/)',
    /* 备份（channel.js 主要文案） */
    '备份与同步': 'Backup & Sync', '渠道': 'Channels',
    '镜像': 'Mirror', '快照': 'Snapshot', '远端': 'Remote', '邮箱': 'Mail', '对象存储': 'Object storage', '网盘冷备': 'Cloud cold backup',
    '启用': 'Enabled', '校验': 'Verify', '未执行': 'Not run yet', '连接已验证': 'Verified',
    '阿里云 OSS': 'Alibaba Cloud OSS', '腾讯云 COS': 'Tencent Cloud COS', '百度智能云 BOS': 'Baidu AI Cloud BOS',
    '密钥 / 归档密码': 'Secret / archive password', '已填写（本机混淆存储）': 'set (obfuscated locally)',
    '尚未测试连接。建议返回步骤 2 点「测试连接」验证通过后再保存。': 'Connection not tested. Go back to step 2 and run the connection test before saving.',
    '尚未填写凭证 · 点击「新增渠道」开始': 'No credentials yet · click "Add channel" to start',
    '尚无备份记录 · 点「立即备份」开始': 'No backup yet · click "Back up now"',
    '加密归档': 'Encrypted archive', '归档加密密码': 'Archive encryption password', '留空则不变更': 'leave blank to keep',
    '选择渠道类型': 'Choose channel type', '连接参数': 'Connection', '加密与策略': 'Encryption & policy', '确认并保存': 'Confirm & save',
    '上一步': 'Back', '下一步': 'Next', '仅保存': 'Save only', '保存并备份': 'Save & back up',
    '测试连接': 'Test connection', '立即备份': 'Back up now', '立即备份全部': 'Back up all', '恢复': 'Restore', '删除': 'Delete', '查看日志': 'Logs',
    '已重试': 'retried', '次': 'times', '校验未过': 'verify failed', '校验通过': 'verified',
    '上次成功': 'Last success', '文件': 'files', '备份渠道': 'Channels', '最近一次成功': 'Last run succeeded',
    '最近一次失败': 'Last run failed', '尚无备份记录': 'No backup yet', '个': '', '正常': 'ok', '已到期未备份': 'Due (not backed up)', '频率每': 'every',
    '百度网盘 · 不自动上传 · 已生成归档包待手动上传': 'Baidu Netdisk · not auto-uploaded · archive ready for manual upload',
    '仅手动「立即备份」': 'manual "Back up now" only',
    '尚未添加对象存储 / 网盘冷备渠道 —— 点右上「＋ 新增渠道」按向导添加（凭证可后填）': 'No object-storage / cloud-cold-backup channels yet — click "+ Add channel" and follow the wizard (credentials can be filled in later)',
    '（对象存储 · S3 兼容 / 百度网盘冷备 / 快照 / 远端 / 邮箱）': '(object storage · S3-compatible / Baidu cloud cold backup / snapshot / remote / mail)',
    '高级设置（自动备份 / 告警邮箱）': 'Advanced (auto backup / alert email)',
    '告警邮箱': 'Alert email',
    '未配置备份位置 · 在上面选一个位置或自定义路径': 'No primary backup location · pick one above or set a custom path',
    '暂无额外渠道': 'No additional channels',
    '上方主备份位置已足够；需要异地 / 对象存储时可再添加': 'The primary location above may be enough; add remote / object storage only when needed',
    '连接失败': 'Connection failed',
    '未配置': 'Not configured', '健康': 'Healthy', '警告': 'Warning', '失败': 'Failed', '冷备': 'Cold', '冷备 · 手动上传': 'Cold · manual',
    '新增渠道': 'Add channel', '保存渠道': 'Save channel',
    '已保存（留空则不变更）': 'Saved (leave blank to keep)',
    '备份': 'backup', '待备份': 'due', '读取中…': 'Loading…',
    '上次备份': 'Last backup', '云端占用（加密包）': 'Cloud usage (encrypted)', '各渠道最近一次估算': 'estimated per channel',
    '下次计划': 'Next run', '主备份位置': 'Primary backup location',
    '本地是事实源，单向同步到云端目录（云盘挂载 / NAS）。加密在出本机前完成，云端只有密文。': 'Local is the source of truth, synced one-way to a cloud dir (drive mount / NAS). Encryption happens before leaving the machine; only ciphertext reaches the cloud.',
  };

  let lang = localStorage.getItem(STORE_KEY) || 'zh';
  // URL 参数 ?lang=en|zh 可覆盖持久化设置（深链分享 / 自动化验证）
  const ql = new URLSearchParams(location.search).get('lang');
  if (ql === 'zh' || ql === 'en') lang = ql;
  window.__lang = lang;
  window.t = function (s) {
    if (lang === 'en' && EN[s] != null) return EN[s];
    return s;
  };
  window.setLang = function (l) {
    if (l !== lang) { localStorage.setItem(STORE_KEY, l); location.reload(); }
  };
  window.currentLang = () => lang;

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t(el.getAttribute('data-i18n')); });
    document.querySelectorAll('[data-i18n-ph]').forEach(el => { el.placeholder = t(el.getAttribute('data-i18n-ph')); });
    const lb = document.getElementById('langLabel');
    if (lb) lb.textContent = lang === 'zh' ? 'EN' : '中';
    const lbBtn = document.getElementById('langBtn');
    if (lbBtn) {
      lbBtn.title = lang === 'zh' ? 'Switch to English' : '切换到中文';
      lbBtn.onclick = () => setLang(lang === 'zh' ? 'en' : 'zh');
    }
    const fl = document.getElementById('langFlag');
    if (fl) fl.innerHTML = lang === 'zh'
      ? '<text x="6" y="16">中</text><text x="17" y="16" style="font-weight:400">EN</text>'
      : '<text x="6" y="16">EN</text><text x="17" y="16" style="font-weight:400">中</text>';
  });
})();
