# 恒忆 Evermem · 三平台签名 / 公证 / 分发形态分析（2026-10-01）

> 结论先行：**Windows 代码签名与 macOS 公证没有"免费且正规"的路径**——两者都要求付费证书/账号，
> 且无法绕开（详见下）。**Linux AppImage 是唯一能免费显著提升分发体验的项**，已在本文件给出 CI 落地脚本。
> 免费且立刻可做的配套：SHA256SUMS 校验（已在 CI 生成）+ 绕过指引（SmartScreen/Gatekeeper）。

## 一、Windows：代码签名

### 现状与成本（2026 年实测报价）

| 项 | 说明 | 年成本 |
|---|---|---|
| OV 证书 | 验证组织存在；SmartScreen 信誉**逐步建立**（下载量累积） | ¥1200–4400 |
| EV 证书 | 加强验证；SmartScreen **近乎即时**消除"未知发布者"；驱动签名必须 | ¥2500–6600（Certum 最低 ≈¥2500） |
| 强制约束 | 自 2023-06-01 起私钥必须存硬件（USB token / HSM / 云签名）；2026-03 起证书最长有效期 459 天 | — |

### 免费方案评估

| 方案 | 效果 | 结论 |
|---|---|---|
| 不签名直接分发 | SmartScreen "未知发布者"蓝色警告；用户可「更多信息 → 仍要运行」 | **现状，可接受**：面向政务/技术用户，文档引导足够 |
| GPG 签名 + SHA256SUMS | 用户可校验文件真实性与完整性（不消除 SmartScreen） | ✅ **免费落地**（SUMS 已在 CI 生成；GPG 为可选增强） |
| 自建证书（makecert/自签） | 只在你自己的机器受信任，对外分发无意义 | ❌ 不推荐 |
| 申请"微软商店"路径 | 个人开发者账户 $19/年，走 MSIX/商店分发——**是另一条分发形态**，不是 exe 签名 | 可选远期 |
| 众筹/公司申请 | 若单位以组织身份申请 OV（应急管理局/筹委会），价格由单位承担 | **最可行省钱路径**：单位名义办 OV 即可显示"已验证发布者"，比个人自掏 EV 便宜 |

### 建议（按优先级）

1. **现在**：保持现状 + SHA256SUMS（已生成）+ 把 SmartScreen 绕过图文写进 `docs/USER-GUIDE.md`（免费）。
2. **若单位可承担**：以单位名义办 **Certum OV**（¥1200 档，云签名免硬件），"已验证发布者"即可，
   不需 EV（非驱动、非大规模商业分发，OV 足够）。
3. **个人自费则暂缓**：EV 的 ¥2500+/年对个人工具性软件不划算。

## 二、macOS：签名 + 公证

### 现状

| 项 | 说明 | 成本 |
|---|---|---|
| Developer ID Application 证书 | 让"任何 Mac"信任你的签名；**必须** Apple Developer Program 成员 | $99/年 |
| 公证（notarization） | 必须 Developer ID + 硬运行时 + 时间戳；免费账号（Apple Development）只能签自己注册的机器 | $99/年 |
| ad-hoc 签名（codesign -s -） | **免费**，但 Gatekeeper 的问题是"谁负责"而不是"是否完整"——ad-hoc 回答"无人"，照样拦截 | 免费但无效 |
| xattr -cr 绕过 | 用户执行 `xattr -cr` 或「右键 → 打开」可放行未签名应用 | **唯一免费可用路径** |

### 结论

- **无免费公证**：任何"免费绕过 Gatekeeper"的方案本质都是把操作成本转嫁给用户（右键打开 / xattr）。
- **决策**：若 macOS 用户占比低（个人工具，Windows 为主），保持"未签名 + 图文引导 xattr/右键打开"
  （`docs/USER-GUIDE.md` 已含）。若将来 macOS 用户增多或进入单位分发，再投入 $99/年。
- 注意：**未公证的 macOS 应用无法做自动更新**（Electron/Tauri 系同理）——与 P3 一键替换的
  Windows 优先设计一致（macOS 自动替换本就排后）。

## 三、Linux：AppImage（唯一免费的大项）

### 现状

裸 ELF 单文件，`chmod +x` 即可跑，但依赖系统 Qt 库（发行版差异大，部分精简发行版缺库）。

### 免费方案：AppImage（自带 Qt 库，双击即用）

- 工具：`appimagetool` + `linuxdeploy-plugin-qt`（开源免费，无年费）。
- 产出：`Evermem-linux-x86_64.AppImage`（约 200-250MB，含 QtWebEngine）。
- 难度：中——PySide6 的 Qt 库需通过 linuxdeploy-plugin-qt 收集（用 PySide6 自带 qmake 定位），
  首次 CI 试跑需按报错微调 1-2 轮。

### CI 落地脚本（已写入 build.yml，独立步骤且 continue-on-error，不阻塞发布主链）

```yaml
      - name: Linux AppImage（可选增强：自带 Qt 库，失败不阻塞发布）
        if: matrix.os == 'ubuntu-latest'
        continue-on-error: true
        run: |
          set -e
          sudo apt-get install -y -qq file desktop-file-utils
          wget -q https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage -O /tmp/appimagetool
          wget -q https://github.com/linuxdeploy/linuxdeploy/releases/download/continuous/linuxdeploy-x86_64.AppImage -O /tmp/linuxdeploy
          wget -q https://github.com/linuxdeploy/linuxdeploy-plugin-qt/releases/download/continuous/linuxdeploy-plugin-qt-x86_64.AppImage -O /tmp/linuxdeploy-plugin-qt
          chmod +x /tmp/appimagetool /tmp/linuxdeploy /tmp/linuxdeploy-plugin-qt
          mkdir -p AppDir/usr/bin AppDir/usr/lib
          cp dist/Evermem AppDir/usr/bin/evermem
          cat > AppDir/evermem.desktop <<'EOF'
          [Desktop Entry]
          Type=Application
          Name=Evermem
          Comment=恒忆 Evermem 个人记忆库
          Exec=evermem
          Icon=evermem
          Categories=Utility;
          EOF
          # PySide6 的 Qt 库定位：plugin-qt 用 QMAKE 探测
          export QMAKE="$(python -c 'import PySide6, os; print(os.path.join(os.path.dirname(PySide6.__file__), "qmake"))' 2>/dev/null || true)"
          export PATH="/tmp:$PATH"
          ./linuxdeploy --appdir AppDir --executable AppDir/usr/bin/evermem --plugin qt --output appimage \
            || echo "[appimage] 构建失败（continue-on-error 已放行，不影响发布）；裸 ELF 仍随 Release 分发"
          ls -1 *.AppImage 2>/dev/null || true
```

> 说明：脚本首次在 CI 试跑时可能因 Qt 库收集细节报错（WebEngine 插件、icon 缺失等），
> 已用 `continue-on-error` 保证不影响三平台主链发布；修好后可移除该开关。
> AppImage 产出后应重命名为 `Evermem-linux-v$VER.AppImage` 并加入更新清单下载链。

## 四、免费且立即可做的配套（本轮已就绪 / 待办）

| 项 | 状态 | 说明 |
|---|---|---|
| SHA256SUMS.txt 随 Release | ✅ 已在 CI 生成 | 用户可 `sha256sum -c` 校验文件 |
| SmartScreen 绕过指引 | ✅ `docs/USER-GUIDE.md` 已有 | "更多信息 → 仍要运行" 图文 |
| Gatekeeper 绕过指引 | ✅ `docs/USER-GUIDE.md` 已有 | 右键打开 / `xattr -cr` |
| Linux AppImage CI 步骤 | 🆕 本轮写入 build.yml（continue-on-error） | 首次 CI 试跑验证 |
| GPG 签名（可选） | 待办 | 若你有 GPG 密钥，可在 Release 加 `.asc` 签名文件并在 README 给公钥；没有则 SHA256 足够 |
| 单位名义 OV 证书 | 决策项 | 若应急管理局/筹委会可走单位采购，¥1200 档 OV 即显示"已验证发布者" |

## 五、决策建议（给用户）

1. **近期（零成本）**：AppImage CI 步骤跑通后替换/并存裸 ELF；SHA256+GPG 校验引导；保持 SmartScreen/Gatekeeper 绕过文档。
2. **中期（若单位承担）**：单位名义 Certum OV 签名 Windows exe（消除 SmartScreen 警告的大头）。
3. **暂缓**：macOS $99 公证（等 macOS 用户占比上来再说）、个人自购 EV（不划算）。
