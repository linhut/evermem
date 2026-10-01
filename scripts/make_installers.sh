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
    dpkg-deb --build --root-owner pkg-deb "Evermem-linux-v$VER.deb" || {
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
%files
/opt/evermem
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