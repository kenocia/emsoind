#!/usr/bin/env python3
"""Convierte MANUAL_USUARIO_GASTOS_FISCAL_HN.md a HTML y PDF (sin dependencias externas)."""
import re
import subprocess
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent
MD_FILE = DOCS / 'MANUAL_USUARIO_GASTOS_FISCAL_HN.md'
HTML_FILE = DOCS / 'MANUAL_USUARIO_GASTOS_FISCAL_HN.html'
PDF_FILE = DOCS / 'MANUAL_USUARIO_GASTOS_FISCAL_HN.pdf'

CSS = """
@page { size: A4; margin: 18mm 15mm 20mm 15mm; }
body {
  font-family: 'DejaVu Sans', Arial, Helvetica, sans-serif;
  font-size: 10.5pt;
  line-height: 1.45;
  color: #1a1a1a;
}
h1 { font-size: 20pt; color: #0d3b66; border-bottom: 2px solid #0d3b66; padding-bottom: 6px; page-break-after: avoid; }
h2 { font-size: 14pt; color: #145374; margin-top: 22px; page-break-after: avoid; }
h3 { font-size: 12pt; color: #1f6f8b; margin-top: 16px; page-break-after: avoid; }
p { margin: 8px 0; }
ul, ol { margin: 6px 0 10px 20px; }
li { margin: 3px 0; }
table { border-collapse: collapse; width: 100%; margin: 10px 0 14px; font-size: 9.5pt; page-break-inside: avoid; }
th, td { border: 1px solid #bbb; padding: 5px 7px; text-align: left; vertical-align: top; }
th { background: #e8f1f5; font-weight: bold; }
tr:nth-child(even) td { background: #f8fbfc; }
code { background: #f0f0f0; padding: 1px 4px; border-radius: 3px; font-size: 9pt; }
pre {
  background: #f4f6f8; border: 1px solid #d0d7de; border-radius: 4px;
  padding: 10px; font-size: 8.5pt; line-height: 1.35; white-space: pre-wrap;
  page-break-inside: avoid;
}
img { max-width: 100%; height: auto; display: block; margin: 10px auto; border: 1px solid #ddd; }
em.caption { display: block; text-align: center; font-size: 9pt; color: #555; margin: -4px 0 14px; font-style: italic; }
hr { border: none; border-top: 1px solid #ccc; margin: 18px 0; }
blockquote.note {
  background: #fff8e6; border-left: 4px solid #e6a700;
  padding: 8px 12px; margin: 10px 0; font-size: 9.5pt;
}
a { color: #145374; text-decoration: none; }
"""


def inline_md(text: str) -> str:
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'`([^`]+)`', r'<code>\1</code>', text)
    text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
    return text


def convert_md_to_html(md: str) -> str:
    lines = md.splitlines()
    out = []
    i = 0
    in_code = False
    in_table = False
    in_ul = False
    in_ol = False

    def close_lists():
        nonlocal in_ul, in_ol
        if in_ul:
            out.append('</ul>')
            in_ul = False
        if in_ol:
            out.append('</ol>')
            in_ol = False

    while i < len(lines):
        line = lines[i]

        if line.strip().startswith('```'):
            close_lists()
            if in_code:
                out.append('</pre>')
                in_code = False
            else:
                lang = line.strip()[3:].strip()
                if lang == 'mermaid':
                    out.append('<blockquote class="note"><strong>Diagrama de flujo</strong> — ver versión digital interactiva del manual.</blockquote>')
                    i += 1
                    while i < len(lines) and not lines[i].strip().startswith('```'):
                        i += 1
                    i += 1
                    continue
                out.append('<pre>')
                in_code = True
            i += 1
            continue

        if in_code:
            out.append(line.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))
            i += 1
            continue

        if not line.strip():
            close_lists()
            if in_table:
                out.append('</tbody></table>')
                in_table = False
            i += 1
            continue

        if line.strip() == '---':
            close_lists()
            if in_table:
                out.append('</tbody></table>')
                in_table = False
            out.append('<hr/>')
            i += 1
            continue

        img = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', line.strip())
        if img:
            close_lists()
            alt, src = img.groups()
            src_path = (DOCS / src).resolve().as_uri()
            out.append(f'<img src="{src_path}" alt="{alt}"/>')
            i += 1
            if i < len(lines) and lines[i].strip().startswith('*') and lines[i].strip().endswith('*'):
                cap = lines[i].strip().strip('*')
                out.append(f'<em class="caption">{inline_md(cap)}</em>')
                i += 1
            continue

        if '|' in line and line.strip().startswith('|'):
            close_lists()
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            if i + 1 < len(lines) and re.match(r'^\|?[\s\-:|]+\|', lines[i + 1]):
                if not in_table:
                    out.append('<table><thead><tr>')
                    for c in cells:
                        out.append(f'<th>{inline_md(c)}</th>')
                    out.append('</tr></thead><tbody>')
                    in_table = True
                i += 2
                continue
            if not in_table:
                out.append('<table><tbody>')
                in_table = True
            out.append('<tr>')
            for c in cells:
                tag = 'th' if in_table and out[-1] == '<table><tbody>' else 'td'
                out.append(f'<{tag}>{inline_md(c)}</{tag}>')
            out.append('</tr>')
            i += 1
            continue

        if in_table:
            out.append('</tbody></table>')
            in_table = False

        m = re.match(r'^(#{1,3})\s+(.*)$', line)
        if m:
            close_lists()
            level = len(m.group(1))
            out.append(f'<h{level}>{inline_md(m.group(2))}</h{level}>')
            i += 1
            continue

        m = re.match(r'^(\d+)\.\s+(.*)$', line)
        if m:
            if in_ul:
                out.append('</ul>')
                in_ul = False
            if not in_ol:
                out.append('<ol>')
                in_ol = True
            out.append(f'<li>{inline_md(m.group(2))}</li>')
            i += 1
            continue

        m = re.match(r'^-\s+(.*)$', line)
        if m:
            if in_ol:
                out.append('</ol>')
                in_ol = False
            if not in_ul:
                out.append('<ul>')
                in_ul = True
            content = m.group(1)
            if content.startswith('[ ]') or content.startswith('[x]'):
                checked = 'x' in content[:3].lower()
                label = content[3:].strip()
                mark = '&#9745;' if checked else '&#9744;'
                out.append(f'<li>{mark} {inline_md(label)}</li>')
            else:
                out.append(f'<li>{inline_md(content)}</li>')
            i += 1
            continue

        if line.strip().startswith('>'):
            close_lists()
            out.append(f'<blockquote class="note">{inline_md(line.strip().lstrip("> ").strip())}</blockquote>')
            i += 1
            continue

        close_lists()
        out.append(f'<p>{inline_md(line.strip())}</p>')
        i += 1

    close_lists()
    if in_table:
        out.append('</tbody></table>')
    if in_code:
        out.append('</pre>')

    body = '\n'.join(out)
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<title>Manual de Usuario — Gastos Fiscal HN</title>
<style>{CSS}</style>
</head>
<body>
{body}
</body>
</html>"""


def main():
    md = MD_FILE.read_text(encoding='utf-8')
    html = convert_md_to_html(md)
    HTML_FILE.write_text(html, encoding='utf-8')
    print(f'HTML: {HTML_FILE}')

    cmd = [
        'wkhtmltopdf',
        '--enable-local-file-access',
        '--encoding', 'utf-8',
        '--margin-top', '15mm',
        '--margin-bottom', '15mm',
        '--margin-left', '12mm',
        '--margin-right', '12mm',
        '--footer-center', 'Manual Gastos Fiscal HN — EMSOIND — Página [page] de [topage]',
        '--footer-font-size', '8',
        str(HTML_FILE),
        str(PDF_FILE),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(result.returncode)
    print(f'PDF:  {PDF_FILE} ({PDF_FILE.stat().st_size // 1024} KB)')


if __name__ == '__main__':
    main()
