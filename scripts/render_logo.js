// 恒忆 Evermem 品牌 Logo 渲染：resvg-js 把 SVG 渲染为多尺寸 PNG
// 用法：node scripts/render_logo.js
// 前置：npm i @resvg/resvg-js（渲染期依赖，构建打包不需要）
//
// 产物：
//   brand/png/evermem-logo-{16,24,32,48,64,128,256,512,1024}.png   透明底多尺寸
//   installers/windows/wizard-image.png        安装向导左侧横幅（246x471，比例 164:314）
//   installers/windows/wizard-small-image.png  安装向导右上角小图（147x147，正方形）
//
// 尺寸为什么是这几个：
//   · 16/24/32/48/64/128/256 —— Windows ICO 常用帧（24 是 Win11 任务栏尺寸）
//   · 512/1024 —— macOS ICNS 需要 ic09(512)/ic10(1024)
//   · 横幅比例必须严格 164:314（Inno Setup 强制），否则向导里会被拉伸变形；
//     246x471 是 164x314 的 1.5 倍，满足官方"建议不小于 202x386"的高 DPI 要求。
const fs = require('fs');
const path = require('path');
const { Resvg } = require('@resvg/resvg-js');

const ROOT = path.join(__dirname, '..');
const BRAND = path.join(ROOT, 'brand');
const OUT_DIR = path.join(BRAND, 'png');
const WIN = path.join(ROOT, 'installers', 'windows');

const SIZES = [16, 24, 32, 48, 64, 128, 256, 512, 1024];

/** 取 logo SVG 的内部内容（去掉外层 <svg>，用于嵌进更大的画布） */
function innerOf(svg) {
  const m = svg.match(/<svg[^>]*>([\s\S]*)<\/svg>/);
  if (!m) throw new Error('logo SVG 结构异常：找不到内层内容');
  return m[1];
}

function render(svgText, width, height) {
  const r = new Resvg(svgText, {
    fitTo: { mode: 'width', value: width },
    background: 'rgba(0,0,0,0)',
  });
  return r.render().asPng();
}

/**
 * 把 logo 居中放进指定画布（透明底）。
 * 留白按 docs/BRAND.md：logo 占容器宽度 82%~86%，四周留白 ≥25%。
 */
function compose(canvasW, canvasH, logoRatio, offsetYRatio, out) {
  const logoW = Math.round(canvasW * logoRatio);
  const x = (canvasW - logoW) / 2;
  const y = (canvasH - logoW) * offsetYRatio;
  const inner = innerOf(fs.readFileSync(path.join(BRAND, 'evermem-logo.svg'), 'utf-8'));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${canvasW}" height="${canvasH}" `
    + `viewBox="0 0 ${canvasW} ${canvasH}">`
    + `<svg x="${x}" y="${y}" width="${logoW}" height="${logoW}" viewBox="0 0 512 512">`
    + inner + '</svg></svg>';
  fs.writeFileSync(out, render(svg, canvasW, canvasH));
  console.log(`合成 ${path.relative(ROOT, out)} (${canvasW}x${canvasH}, logo ${logoW}px)`);
}

function main() {
  fs.mkdirSync(OUT_DIR, { recursive: true });
  const svg = fs.readFileSync(path.join(BRAND, 'evermem-logo.svg'), 'utf-8');
  for (const s of SIZES) {
    fs.writeFileSync(path.join(OUT_DIR, `evermem-logo-${s}.png`), render(svg, s, s));
    console.log(`渲染 ${s}px`);
  }
  // 安装向导横幅：logo 居中，占宽 81%（留白两侧各 9.5%）
  compose(246, 471, 0.81, 0.5, path.join(WIN, 'wizard-image.png'));
  // 安装向导小图：正方形，logo 占宽 80%
  compose(147, 147, 0.80, 0.5, path.join(WIN, 'wizard-small-image.png'));
  console.log('全部渲染完成');
}

main();
