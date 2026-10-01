#!/usr/bin/env bash
# 恒忆 Evermem · 安装版安装器打包（macOS dmg / Linux deb、rpm）
#
# 用法：bash scripts/make_installers.sh <label> <version> <dist>
#
# 由 CI 调用（label ∈ macos|linux；失败不阻塞发布，调用处 continue-on-error）。
# 产物直接落到 <dist>/：Evermem-macos-vX.dmg / Evermem-linux-vX.deb / Evermem-linux-vX.rpm
# 安装版写 install.marker（paths.py 据此把数据根落到系统数据目录）。

set -u

LABEL="$1"
VER="$2"
DIST="$3"

# cd 到 dist 之后就找不到仓库里的 assets/ 了，先把仓库根存下来
REPO_ROOT="$PWD"

cd "$DIST" || exit 1

case "$LABEL" in
  macos)
    echo "[installer] macos: 制作 dmg（拖拽安装）"
    if [ ! -d Evermem.app ]; then
      echo "[installer] macos: Evermem.app 不存在，跳过 dmg"
      exit 0
    fi
    # UDZO 压缩 dmg；volname 是挂载后显示的卷名
    hdiutil create -volname Evermem -srcfolder Evermem.app -ov -format UDZO \
      "Evermem-macos-v$VER.dmg" 2>&1 | tail -3
    ;;
  linux)
    echo "[installer] linux: 制作 deb"
    if [ ! -d Evermem ]; then
      echo "[installer] linux: 绿色版目录 Evermem 不存在，跳过 deb/rpm"
      exit 0
    fi
    rm -rf pkg-deb && mkdir -p pkg-deb/DEBIAN pkg-deb/opt/evermem
    cp -r Evermem/. pkg-deb/opt/evermem/
    touch pkg-deb/opt/evermem/install.marker
    # Non-Native Arch: dpkg 需要版本号不以零开头且为 Debian 合法版本（X.Y.Z 直接可用）
    cat > pkg-deb/DEBIAN/control <<EOF
Package: evermem
Version: $VER
Section: utils
Priority: optional
Architecture: amd64
Maintainer: Jose-AI <jose@linhut.cn>
Homepage: https://www.linhut.cn
Description: 恒忆 Evermem — 个人跨会话经验记忆系统
 Local-first personal memory: capture experience from conversations
 and reuse it across sessions. All data stays on your machine.
EOF
    # 启动器：onedir 目录里的 Evermem 只能在自身目录下跑（要找 _internal），
    # 装到 /opt 后必须有个 wrapper，否则装完在终端敲 evermem 起不来。
    mkdir -p pkg-deb/usr/bin pkg-deb/usr/share/applications pkg-deb/usr/share/icons/hicolor/256x256/apps
    cat > pkg-deb/usr/bin/evermem <<'EOF'
#!/bin/sh
exec /opt/evermem/Evermem "$@"
EOF
    chmod 0755 pkg-deb/usr/bin/evermem
    cat > pkg-deb/usr/share/applications/evermem.desktop <<'EOF'
[Desktop Entry]
Type=Application
Name=恒忆 Evermem
Comment=个人跨会话经验记忆系统
Exec=/usr/bin/evermem
Icon=evermem
Categories=Utility;
Terminal=false
EOF
    cp "$REPO_ROOT/assets/icon.png" pkg-deb/usr/share/icons/hicolor/256x256/apps/evermem.png 2>/dev/null || true
    # --root-owner 不存在（dpkg-deb 1.19+ 的正确参数是 --root-owner-group），
    # 写错会直接 error: unknown option → deb 从未产出过。
    dpkg-deb --build --root-owner-group pkg-deb "Evermem-linux-v$VER.deb" || {
      echo "[installer] dpkg-deb 失败（跳过，不影响发布）"; rm -rf pkg-deb; exit 0; }
    rm -rf pkg-deb

    echo "[installer] linux: 制作 rpm"
    command -v rpmbuild >/dev/null 2>&1 || sudo apt-get install -y -qq rpm >/dev/null 2>&1
    command -v rpmbuild >/dev/null 2>&1 || {
      echo "[installer] rpmbuild 不可用，跳过 rpm"; exit 0; }
    rm -rf rpmhome && mkdir -p rpmhome/{BUILD,RPMS,SOURCES,SPECS,SRPMS}
    cat > rpmhome/SPECS/evermem.spec <<EOF
Name:       evermem
Version:    $VER
Release:    1
Summary:    恒忆 Evermem — 个人跨会话经验记忆系统
License:    MIT
URL:        https://www.linhut.cn
BuildArch:  x86_64
%description
Local-first personal memory: capture experience from conversations and reuse
it across sessions. All data stays on your machine.
%install
mkdir -p %{buildroot}/opt/evermem
cp -r Evermem/. %{buildroot}/opt/evermem/
touch %{buildroot}/opt/evermem/install.marker
mkdir -p %{buildroot}/usr/bin %{buildroot}/usr/share/applications %{buildroot}/usr/share/icons/hicolor/256x256/apps
printf '#!/bin/sh\nexec /opt/evermem/Evermem "$@"\n' > %{buildroot}/usr/bin/evermem
chmod 0755 %{buildroot}/usr/bin/evermem
cat > %{buildroot}/usr/share/applications/evermem.desktop <<'DESKTOP'
[Desktop Entry]
Type=Application
Name=恒忆 Evermem
Comment=个人跨会话经验记忆系统
Exec=/usr/bin/evermem
Icon=evermem
Categories=Utility;
Terminal=false
DESKTOP
%files
/opt/evermem
/usr/bin/evermem
/usr/share/applications/evermem.desktop
%changelog
* $(date +"%a %b %d %Y") Jose-AI - $VER-1
- Initial package
EOF
    rpmbuild -bb --define "_topdir $PWD/rpmhome" rpmhome/SPECS/evermem.spec >rpmbuild.log 2>&1 || {
      echo "[installer] rpmbuild 失败（跳过，不影响发布）"; tail -5 rpmbuild.log; rm -rf rpmhome; exit 0; }
    # 定位产物：x86_64 子目录（Ubuntu 上通常直接输出）
    RPM="$(ls rpmhome/RPMS/*/*.rpm 2>/dev/null | head -1)"
    if [ -n "$RPM" ]; then
      mv -f "$RPM" "Evermem-linux-v$VER.rpm"
      echo "[installer] rpm 产物：Evermem-linux-v$VER.rpm"
    else
      echo "[installer] rpm 产物未找到（跳过）"
    fi
    rm -rf rpmhome rpmbuild.log
    ;;
  *)
    echo "[installer] 未知平台：$LABEL"
    exit 1
    ;;
esac
exit 0