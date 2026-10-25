#!/usr/bin/env python3
"""Render the illustrated manual as a self-contained, printable HTML file.

Run: python3 ./manual/build_manual.py
Requires Python-Markdown (the `markdown` package). No network calls are made.
"""
import base64
import mimetypes
from pathlib import Path
import re

import markdown
from markdown.extensions.toc import slugify_unicode


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / '操作手冊.md'
TARGET = ROOT / '操作手冊.html'


def embed_image(match):
    path = (ROOT / match.group(1)).resolve()
    if not path.is_relative_to(ROOT):
        raise ValueError('Image must belong to the manual directory')
    mime = mimetypes.guess_type(path)[0]
    if not mime or not mime.startswith('image/'):
        raise ValueError(f'Unsupported manual image: {path.name}')
    encoded = base64.b64encode(path.read_bytes()).decode('ascii')
    return f'src="data:{mime};base64,{encoded}"'


def main():
    renderer = markdown.Markdown(
        extensions=['tables', 'fenced_code', 'toc'],
        extension_configs={'toc': {'slugify': slugify_unicode, 'toc_depth': '2-2'}},
    )
    body = renderer.convert(SOURCE.read_text(encoding='utf-8'))
    body = re.sub(r'src="(images/[^\"]+)"', embed_image, body)
    html = '''<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>SBOMScan 授權管理操作手冊</title>
<style>
:root { color-scheme: light; }
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; background: #f2f5fa; color: #203248;
  font: 16px/1.85 "Noto Sans CJK TC", "Microsoft JhengHei", system-ui, sans-serif; }
.toolbar { background: #17334a; color: white; padding: 14px max(24px, calc((100vw - 1050px)/2));
  display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.toolbar button { color: white; border: 1px solid #b3c4d3; background: transparent;
  padding: 7px 16px; border-radius: 6px; cursor: pointer; font: inherit; white-space: nowrap; }
main { max-width: 1100px; padding: 44px 54px; margin: 28px auto; background: white;
  box-shadow: 0 3px 22px #17334a0d; border-radius: 12px; }
h1 { font-size: 32px; line-height: 1.5; margin: 0 0 24px; }
h2 { font-size: 25px; border-bottom: 2px solid #deebf3; margin: 52px 0 22px; padding-bottom: 10px; }
h3 { font-size: 20px; margin: 32px 0 14px; }
p, ul, ol, table, pre { margin: 16px 0; }
li { margin: 8px 0; }
a { color: #1558a7; text-underline-offset: 3px; }
strong { color: #153b63; }
code { font: 0.9em/1.7 ui-monospace, "Noto Sans Mono CJK TC", monospace;
  background: #edf2f7; border-radius: 4px; padding: 2px 5px; overflow-wrap: anywhere; }
pre { background: #172c40; color: #f2f6fa; padding: 20px 22px; border-radius: 8px;
  overflow-x: auto; white-space: pre-wrap; overflow-wrap: anywhere; }
pre code { background: transparent; padding: 0; color: inherit; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th { background: #edf4fa; text-align: left; }
td, th { padding: 12px 13px; border: 1px solid #dce5ed; vertical-align: top; overflow-wrap: anywhere; }
tr:nth-child(even) td { background: #fafcfe; }
img { display: block; max-width: 100%; height: auto; margin: 24px auto;
  border: 1px solid #dce5ed; border-radius: 8px; }
details { background: #f2f7fc; border-radius: 8px; padding: 14px 22px; margin: 24px 0; }
summary { cursor: pointer; font-weight: 700; }
.toc ul { padding-left: 24px; }
@media (max-width: 700px) { main { padding: 24px 18px; margin: 0; border-radius: 0; }
  h1 { font-size: 26px; } h2 { font-size: 22px; } td, th { padding: 8px; }
  .toolbar { padding: 12px 18px; } }
@media print { body { background: white; font-size: 10pt; }
  .toolbar, .contents { display: none; } main { margin: 0; padding: 0; box-shadow: none; max-width: none; }
  h2, h3 { break-after: avoid; } img, tr, pre { break-inside: avoid; }
  img { max-height: 220mm; object-fit: contain; } a { color: inherit; }
  @page { size: A4; margin: 16mm 14mm; } }
</style>
</head><body>
<div class="toolbar"><span>SBOMScan ／ TraceWOLF 授權操作</span>
<button type="button" onclick="window.print()">列印或另存 PDF</button></div>
<main>'''
    html += '<details class="contents"><summary>展開章節目錄</summary>' + renderer.toc + '</details>'
    html += body + '</main></body></html>\n'
    TARGET.write_text(html, encoding='utf-8')
    print(f'Generated {TARGET.name}: {len(html.encode()):,} bytes (images embedded)')


if __name__ == '__main__':
    main()
