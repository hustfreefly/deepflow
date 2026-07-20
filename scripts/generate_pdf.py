#!/usr/bin/env python3
"""
FixFlow #6: 标准化 PDF 生成工具
统一使用 Chrome headless，废弃 weasyprint（中文不可靠）

Usage:
  python3 scripts/generate_pdf.py <input.md> <output.pdf> [--title "Title"]
"""
import sys
import os
import subprocess
import tempfile
from pathlib import Path

CHROME_PATH = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"

def md_to_html(md_path: str, title: str = "") -> str:
    """Convert markdown to styled HTML with Chinese font support."""
    try:
        import markdown
    except ImportError:
        print("ERROR: markdown package not installed. Run: pip install markdown")
        sys.exit(1)
    
    md_content = Path(md_path).read_text(encoding='utf-8')
    html_body = markdown.markdown(md_content, extensions=['tables', 'fenced_code', 'toc', 'nl2br'])
    
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>{title or Path(md_path).stem}</title>
<style>
@page {{ size: A4; margin: 1.8cm; }}
body {{
    font-family: -apple-system, "PingFang SC", "Helvetica Neue", sans-serif;
    font-size: 10.5pt; line-height: 1.7; color: #1a1a1a; max-width: 100%;
}}
h1 {{ font-size: 20pt; color: #1a1a1a; border-bottom: 2px solid #2563eb; padding-bottom: 6px; margin-top: 28px; page-break-after: avoid; }}
h2 {{ font-size: 15pt; color: #2563eb; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; margin-top: 22px; page-break-after: avoid; }}
h3 {{ font-size: 12pt; color: #374151; margin-top: 16px; page-break-after: avoid; }}
h4 {{ font-size: 10.5pt; color: #6b7280; margin-top: 12px; }}
table {{ border-collapse: collapse; width: 100%; margin: 10px 0; font-size: 9pt; page-break-inside: avoid; }}
th, td {{ border: 1px solid #d1d5db; padding: 5px 7px; text-align: left; }}
th {{ background: #2563eb; color: white; font-weight: 600; }}
tr:nth-child(even) {{ background: #f9fafb; }}
code {{ background: #f3f4f6; padding: 1px 4px; border-radius: 3px; font-family: "SF Mono", Menlo, monospace; font-size: 8.5pt; }}
pre {{ background: #f3f4f6; padding: 10px; border-radius: 5px; font-size: 8pt; line-height: 1.4; overflow-x: auto; page-break-inside: avoid; }}
pre code {{ background: none; padding: 0; }}
blockquote {{ border-left: 3px solid #2563eb; margin: 10px 0; padding: 6px 14px; background: #eff6ff; color: #4b5563; }}
strong {{ color: #dc2626; }}
ul, ol {{ margin: 6px 0; padding-left: 22px; }}
li {{ margin: 3px 0; }}
hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 18px 0; }}
</style>
</head>
<body>
{html_body}
</body>
</html>"""

def html_to_pdf(html_path: str, pdf_path: str) -> bool:
    """Convert HTML to PDF using Chrome headless."""
    if not os.path.exists(CHROME_PATH):
        print(f"ERROR: Chrome not found at {CHROME_PATH}")
        return False
    
    cmd = [
        CHROME_PATH,
        "--headless", "--disable-gpu", "--no-sandbox",
        f"--print-to-pdf={pdf_path}",
        "--print-to-pdf-no-header",
        str(html_path)
    ]
    
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    return os.path.exists(pdf_path)

def generate_pdf(input_md: str, output_pdf: str, title: str = "") -> dict:
    """Main entry: MD → HTML → PDF"""
    # Step 1: MD → HTML
    html_content = md_to_html(input_md, title)
    
    # Step 2: Write temp HTML
    html_path = str(Path(output_pdf).with_suffix('.html'))
    Path(html_path).write_text(html_content, encoding='utf-8')
    
    # Step 3: HTML → PDF
    success = html_to_pdf(html_path, output_pdf)
    
    if success:
        size_kb = os.path.getsize(output_pdf) / 1024
        return {"success": True, "size_kb": round(size_kb, 1), "pdf_path": output_pdf}
    else:
        return {"success": False, "error": "Chrome headless PDF generation failed"}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python3 generate_pdf.py <input.md> <output.pdf> [--title 'Title']")
        sys.exit(1)
    
    input_md = sys.argv[1]
    output_pdf = sys.argv[2]
    title = ""
    if "--title" in sys.argv:
        idx = sys.argv.index("--title")
        title = sys.argv[idx + 1] if idx + 1 < len(sys.argv) else ""
    
    result = generate_pdf(input_md, output_pdf, title)
    if result["success"]:
        print(f"✅ PDF generated: {result['pdf_path']} ({result['size_kb']} KB)")
    else:
        print(f"❌ Failed: {result.get('error', 'unknown')}")
        sys.exit(1)
