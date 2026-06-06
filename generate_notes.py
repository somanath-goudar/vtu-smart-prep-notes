#!/usr/bin/env python3
# WeasyPrint on macOS needs Homebrew's pango/gobject libs on the dyld path.
# Re-exec this script with DYLD_LIBRARY_PATH set before any imports happen.
import sys, os
if sys.platform == "darwin" and not os.environ.get("_NOTES_GEN_REEXEC"):
    for _p in ("/opt/homebrew/lib", "/usr/local/lib"):
        if os.path.exists(_p):
            _e = os.environ.copy()
            _e["DYLD_LIBRARY_PATH"] = _p + (":" + _e["DYLD_LIBRARY_PATH"] if _e.get("DYLD_LIBRARY_PATH") else "")
            _e["_NOTES_GEN_REEXEC"] = "1"
            os.execve(sys.executable, [sys.executable] + sys.argv, _e)

"""
VTU Smart Prep — PDF Study Notes Generator

  Step 1:  python generate_notes.py paper.pdf
           → extracts figures to {pdf_stem}/figures/
           → writes {pdf_stem}/claude_prompt.txt

           Use /vtunotes in Claude Code — it reads the PDF and writes
           {pdf_stem}/notes_response.json automatically.
           Or attach the PDF in Claude.ai and paste the prompt manually.

  Step 2:  python generate_notes.py paper.pdf --from-json
           → validates JSON, renders {pdf_stem}/{pdf_stem}_notes.pdf

Options:
  --output    Output directory (default: {pdf_stem}/)
  --chapter   Override detected chapter title
  --scale     Figure render scale (default: 2.0)
  --ai        Claude Vision API fallback for figures (needs ANTHROPIC_API_KEY)
  --from-json Render PDF from an existing notes_response.json
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import quote as url_quote

import fitz  # PyMuPDF

# ── Optional: figure extractor ─────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))
try:
    from extract_figures import extract_figures_heuristic, extract_figures_ai
    _EXTRACTOR_AVAILABLE = True
except ImportError:
    _EXTRACTOR_AVAILABLE = False

# ── Optional: render dependencies ─────────────────────────────────────────────
try:
    from jinja2 import Environment, BaseLoader
    from weasyprint import HTML as WeasyprintHTML
    _RENDER_AVAILABLE = True
except ImportError:
    _RENDER_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
# Watermark SVG  (12 diagonal "vtusmartprep.com" labels tiled across A4)
# ══════════════════════════════════════════════════════════════════════════════

_WATERMARK_SVG = """\
<svg xmlns="http://www.w3.org/2000/svg" width="794" height="1123" viewBox="0 0 794 1123">
  <g opacity="0.075" fill="#1a3a5c"
     font-family="Georgia,serif" font-size="27" font-weight="bold">
    <text transform="translate(30,160)  rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(300,160) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(560,160) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(30,430)  rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(300,430) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(560,430) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(30,700)  rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(300,700) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(560,700) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(30,970)  rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(300,970) rotate(-35)">vtusmartprep.com</text>
    <text transform="translate(560,970) rotate(-35)">vtusmartprep.com</text>
  </g>
</svg>"""


def _watermark_uri() -> str:
    b64 = base64.b64encode(_WATERMARK_SVG.encode()).decode()
    return f"data:image/svg+xml;base64,{b64}"


# ══════════════════════════════════════════════════════════════════════════════
# HTML / CSS Template  (Jinja2 string)
# ══════════════════════════════════════════════════════════════════════════════

_NOTES_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>

@page {
  size: A4;
  margin: 2.4cm 2cm 2.8cm 2cm;
  @bottom-center {
    content: "Page " counter(page) " of " counter(pages);
    font-size: 8pt;
    color: #999;
    font-family: Georgia, serif;
  }
}

* { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: 'Palatino Linotype', Palatino, 'Book Antiqua', Georgia, serif;
  font-size: 10.5pt;
  color: #1a1a1a;
  line-height: 1.72;
}

/* ── Chapter header ── */
.chapter-header {
  background: #1a3a5c;
  color: white;
  padding: 1.8em 2.2em 1.6em;
  margin-bottom: 1.6em;
}
.chapter-label {
  font-size: 7.5pt;
  letter-spacing: 0.18em;
  text-transform: uppercase;
  opacity: 0.68;
  margin-bottom: 0.4em;
}
.chapter-title {
  font-size: 21pt;
  font-weight: bold;
  line-height: 1.25;
  margin-bottom: 0.7em;
}
.chapter-overview {
  font-size: 10pt;
  opacity: 0.87;
  line-height: 1.65;
}

/* ── Topics Covered box ── */
.topics-box {
  border-left: 4px solid #2e86ab;
  background: #f0f7ff;
  padding: 0.9em 1.4em;
  margin-bottom: 1.8em;
  page-break-inside: avoid;
}
.topics-label {
  font-size: 7.5pt;
  font-weight: bold;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  color: #2e86ab;
  margin-bottom: 0.5em;
}
.topics-box ul { padding-left: 1.3em; color: #1a3a5c; }
.topics-box li { font-size: 10pt; margin-bottom: 0.25em; }

/* ── Section headings ── */
h2 {
  font-size: 14pt;
  font-weight: bold;
  color: #1a3a5c;
  border-bottom: 2px solid #1a3a5c;
  padding-bottom: 0.2em;
  margin-top: 2em;
  margin-bottom: 0.7em;
  page-break-after: avoid;
}
h3 {
  font-size: 12pt;
  font-weight: bold;
  color: #2e86ab;
  margin-top: 1.5em;
  margin-bottom: 0.5em;
  page-break-after: avoid;
}
h4 {
  font-size: 10.5pt;
  font-weight: bold;
  font-style: italic;
  color: #444;
  margin-top: 1.1em;
  margin-bottom: 0.4em;
  page-break-after: avoid;
}

/* ── Body content ── */
p { margin-bottom: 0.75em; }
ul, ol { padding-left: 1.5em; margin-bottom: 0.75em; }
li { margin-bottom: 0.2em; }

/* ── Key term ── */
.key-term {
  margin: 0.6em 0;
  padding: 0.35em 0.9em;
  border-left: 3px solid #c0392b;
  background: #fff5f5;
}
.kt-word { font-weight: bold; color: #c0392b; }

/* ── Callout / exam tip ── */
.callout {
  background: #fffbec;
  border-left: 4px solid #f59e0b;
  padding: 0.65em 1.1em;
  margin: 0.9em 0;
  font-style: italic;
  font-size: 10pt;
  color: #5a4000;
  page-break-inside: avoid;
}

/* ── Figure block ── */
.figure-block {
  text-align: center;
  margin: 1.5em auto;
  page-break-inside: avoid;
}
.figure-block img {
  max-width: 88%;
  height: auto;
  border: 1px solid #ccc;
  border-radius: 3px;
  box-shadow: 0 1px 5px rgba(0,0,0,0.13);
}
.figure-caption {
  font-size: 9pt;
  color: #555;
  margin-top: 0.45em;
  font-style: italic;
}

/* ── Summary box ── */
.summary-box {
  background: #1a3a5c;
  color: white;
  padding: 1.2em 1.6em;
  margin-top: 2em;
  border-radius: 4px;
  page-break-inside: avoid;
}
.summary-label {
  font-size: 7.5pt;
  letter-spacing: 0.15em;
  text-transform: uppercase;
  opacity: 0.72;
  margin-bottom: 0.5em;
}
.summary-box p { font-size: 10pt; line-height: 1.65; opacity: 0.92; margin-bottom: 0; }

/* ── Brand footer ── */
.brand-footer {
  text-align: center;
  margin-top: 2.5em;
  padding-top: 0.8em;
  border-top: 1px solid #ddd;
  font-size: 7.5pt;
  color: #bbb;
  letter-spacing: 0.08em;
}

</style>
</head>
<body>

<div class="chapter-header">
  <div class="chapter-label">{{ notes.chapter_label }}</div>
  <div class="chapter-title">{{ notes.title }}</div>
  {% if notes.overview %}<div class="chapter-overview">{{ notes.overview }}</div>{% endif %}
</div>

{% if notes.topics_covered %}
<div class="topics-box">
  <div class="topics-label">Topics Covered</div>
  <ul>
    {% for t in notes.topics_covered %}<li>{{ t }}</li>{% endfor %}
  </ul>
</div>
{% endif %}

{% for section in notes.sections %}
  {% set lvl = section.level | int %}
  {% if lvl == 1 %}<h2>{{ section.heading }}</h2>
  {% elif lvl == 2 %}<h3>{{ section.heading }}</h3>
  {% else %}<h4>{{ section.heading }}</h4>
  {% endif %}

  {% for item in section.content %}
    {% if item.type == 'paragraph' %}
      <p>{{ item.text }}</p>

    {% elif item.type == 'bullet_list' %}
      <ul>{% for i in item['items'] %}<li>{{ i }}</li>{% endfor %}</ul>

    {% elif item.type == 'numbered_list' %}
      <ol>{% for i in item['items'] %}<li>{{ i }}</li>{% endfor %}</ol>

    {% elif item.type == 'key_term' %}
      <div class="key-term">
        <span class="kt-word">{{ item.term }}:</span> {{ item.definition }}
      </div>

    {% elif item.type == 'callout' %}
      <div class="callout">{{ item.text }}</div>

    {% elif item.type == 'figure' and item.get('src') %}
      <div class="figure-block">
        <img src="{{ item.src }}" alt="{{ item.caption }}">
        <div class="figure-caption">{{ item.caption }}</div>
      </div>

    {% endif %}
  {% endfor %}
{% endfor %}

{% if notes.summary %}
<div class="summary-box">
  <div class="summary-label">Chapter Summary</div>
  <p>{{ notes.summary }}</p>
</div>
{% endif %}

<div class="brand-footer">vtusmartprep.com &mdash; Smart Study Notes</div>

</body>
</html>"""


# ══════════════════════════════════════════════════════════════════════════════
# JSON schema example embedded in the prompt
# ══════════════════════════════════════════════════════════════════════════════

_SCHEMA_EXAMPLE = """\
{
  "title": "Extreme Programming (XP)",
  "chapter_label": "Module 3 — Chapter 1",
  "overview": "A 2-4 sentence plain-language description of what this chapter covers and why it matters.",
  "topics_covered": [
    "The XP lifecycle vs. traditional Waterfall",
    "XP phases: planning, analysis, design, coding, testing, deployment",
    "Team roles in XP: customer, developer, tracker, coach"
  ],
  "sections": [
    {
      "heading": "What is Extreme Programming?",
      "level": 1,
      "content": [
        {
          "type": "paragraph",
          "text": "Extreme Programming (XP) is an agile software development methodology..."
        },
        {
          "type": "key_term",
          "term": "Iteration",
          "definition": "A short, fixed-length development cycle (1-2 weeks) that produces working, deployable software."
        },
        {
          "type": "bullet_list",
          "items": [
            "Each iteration covers analysis, design, coding, and testing.",
            "Working software is delivered at the end of every iteration."
          ]
        },
        {
          "type": "figure",
          "filename": "Figure_3_2__XP_lifecycle.png",
          "caption": "The XP lifecycle: short repeated iterations each producing a release."
        },
        {
          "type": "callout",
          "text": "Exam tip: XP is an agile method — always contrast it with Waterfall in answers."
        }
      ]
    }
  ],
  "summary": "XP replaces the one-time linear waterfall with short repeated iterations, each delivering working software and incorporating customer feedback."
}"""


# ══════════════════════════════════════════════════════════════════════════════
# Stage 1 — Figure extraction
# ══════════════════════════════════════════════════════════════════════════════

def run_figure_extraction(pdf_path: str, figures_dir: str,
                          use_ai: bool, scale: float) -> list:
    if not _EXTRACTOR_AVAILABLE:
        print("  Warning: extract_figures.py not found — skipping figure extraction.")
        return []

    os.makedirs(figures_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    seen: set = set()
    all_saved = []

    for page_num in range(len(doc)):
        page = doc[page_num]
        saved = extract_figures_heuristic(page, scale, figures_dir, seen)
        if not saved and use_ai:
            saved = extract_figures_ai(page, scale, figures_dir, seen)
        all_saved.extend(saved)

    doc.close()
    return sorted(all_saved)


# ══════════════════════════════════════════════════════════════════════════════
# Stage 2 — Chapter title detection (still needed for the prompt/API call)
# ══════════════════════════════════════════════════════════════════════════════

def detect_chapter_title(pdf_path: str, user_title: str = None) -> str:
    """Find largest-font text in first 3 pages as the chapter title."""
    if user_title:
        return user_title
    doc = fitz.open(pdf_path)
    max_size, best = 0.0, ""
    for page_num in range(min(3, len(doc))):
        page = doc[page_num]
        for block in page.get_text("dict").get("blocks", []):
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    size = span.get("size", 0)
                    text = span.get("text", "").strip()
                    if size > max_size and len(text) > 4:
                        max_size, best = size, text
    doc.close()
    return best or "Study Notes"


# ══════════════════════════════════════════════════════════════════════════════
# Stage 3a — Manual mode: write a short prompt file (user attaches the PDF)
# ══════════════════════════════════════════════════════════════════════════════

def build_prompt_file(figure_filenames: list, chapter_title: str,
                      prompt_path: str, json_path: str, pdf_basename: str) -> None:
    """Write the ready-to-paste Claude prompt.  NO full text — user attaches the PDF."""
    if figure_filenames:
        fig_list = "\n".join(f"  {f}" for f in figure_filenames)
    else:
        fig_list = "  (no figures were extracted from this PDF — do not reference any figures)"

    content = f"""\
================================================================
VTU SMART PREP — STUDY NOTES GENERATION PROMPT
================================================================

HOW TO USE:
  1. Open Claude.ai → claude.ai  (new conversation)
  2. ATTACH this PDF file to the message:  {pdf_basename}
  3. Copy EVERYTHING from "COPY FROM HERE" to the end of this file
  4. Paste into Claude.ai  (PDF must be attached in the same message)
  5. Copy Claude's JSON response
  6. Save it as:  {json_path}
  7. Run:  python generate_notes.py {pdf_basename} --from-json

TIP: Run with --api to do steps 1-6 automatically (needs ANTHROPIC_API_KEY).

================================================================
COPY FROM HERE ↓
----------------------------------------------------------------

You are an expert educational content writer creating exam study notes for VTU
engineering students. Read the attached PDF and create comprehensive study notes
from it. Write clearly for undergraduates encountering this material for the
first time. Define every technical term when you introduce it. Use short
paragraphs and bullet points. Write like a knowledgeable friend explaining the
topic, not a textbook author.

CRITICAL RULES:
- Only reference figures by their EXACT filename from the AVAILABLE FIGURES list.
- Do NOT invent, mention, or describe any figures not in that list.
- If a concept needs a diagram that is not available, explain it in words instead.
- Add "Exam tip:" callout items throughout for important points students often miss.
- Output ONLY valid JSON — no markdown code fences, no text before or after the JSON.

CHAPTER TITLE: {chapter_title}

AVAILABLE FIGURES (use exact filenames only — no others):
{fig_list}

OUTPUT FORMAT — return a JSON object matching this structure exactly:

{_SCHEMA_EXAMPLE}

Rules for fields:
  "level"    : 1 (main section), 2 (sub-section), or 3 (sub-sub-section)
  "type"     : paragraph | figure | bullet_list | numbered_list | key_term | callout
  "filename" : must exactly match a name from AVAILABLE FIGURES
  "topics_covered" : 4 to 8 items
"""

    with open(prompt_path, "w", encoding="utf-8") as f:
        f.write(content)



# ══════════════════════════════════════════════════════════════════════════════
# Stage 4a — Load and validate JSON
# ══════════════════════════════════════════════════════════════════════════════

def load_notes_json(json_path: str) -> dict:
    """Parse Claude's JSON response with fallback strategies."""
    with open(json_path, "r", encoding="utf-8") as f:
        raw = f.read().strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    cleaned = re.sub(r"^```(?:json)?\s*|```\s*$", "", raw, flags=re.MULTILINE).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    m = re.search(r"\{.*\}", cleaned, re.DOTALL)
    if m:
        try:
            return json.loads(m.group())
        except json.JSONDecodeError:
            pass

    print(f"Error: Could not parse JSON from {json_path}")
    print("First 600 chars of the file:")
    print(raw[:600])
    sys.exit(1)


def validate_notes_schema(notes: dict, figures_dir: str) -> dict:
    """Ensure required keys exist; replace unavailable figure refs with callouts."""
    notes.setdefault("chapter_label", "Study Notes")
    notes.setdefault("title", "Study Notes")
    notes.setdefault("overview", "")
    notes.setdefault("topics_covered", [])
    notes.setdefault("sections", [])
    notes.setdefault("summary", "")
    notes.setdefault("watermark", "vtusmartprep.com")

    available = set()
    figures_path = Path(figures_dir)
    if figures_path.exists():
        available = {f.name for f in figures_path.iterdir() if f.suffix == ".png"}

    for section in notes["sections"]:
        section.setdefault("heading", "")
        section.setdefault("level", 1)
        section.setdefault("content", [])

        clean = []
        for item in section["content"]:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "figure":
                fn = item.get("filename", "")
                if fn not in available:
                    item = {
                        "type": "callout",
                        "text": f"[Diagram: {fn.replace('_', ' ').rstrip('.png')} — see textbook]"
                    }
            clean.append(item)
        section["content"] = clean

    return notes


# ══════════════════════════════════════════════════════════════════════════════
# Stage 4b — HTML build and PDF render
# ══════════════════════════════════════════════════════════════════════════════

def build_html(notes: dict, figures_dir: str) -> str:
    """Inject figure src URLs into notes, then render Jinja2 template."""
    figures_abs = Path(figures_dir).resolve()

    for section in notes.get("sections", []):
        for item in section.get("content", []):
            if item.get("type") == "figure":
                fig_path = figures_abs / item.get("filename", "")
                if fig_path.exists():
                    item["src"] = "file://" + url_quote(str(fig_path), safe="/")
                else:
                    item["src"] = ""

    env = Environment(loader=BaseLoader(), autoescape=True)
    tmpl = env.from_string(_NOTES_TEMPLATE)
    return tmpl.render(notes=notes)


def _make_watermark_png(page_w: float, page_h: float, text: str = "vtusmartprep.com") -> bytes:
    """Create a transparent PNG with diagonal watermark stamps."""
    from PIL import Image, ImageDraw, ImageFont
    import io as _io

    SCALE = 2
    OPACITY = 85
    NAVY_RGBA = (26, 58, 92, OPACITY)
    FONT_SIZE = int(18 * SCALE)
    TEXT = text or "vtusmartprep.com"
    ANGLE = -35

    w_px, h_px = int(page_w * SCALE), int(page_h * SCALE)
    canvas = Image.new("RGBA", (w_px, h_px), (0, 0, 0, 0))

    _font_candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Unicode.ttf",
    ]
    pil_font = None
    for fp in _font_candidates:
        if os.path.exists(fp):
            try:
                pil_font = ImageFont.truetype(fp, FONT_SIZE)
                break
            except Exception:
                continue
    if pil_font is None:
        pil_font = ImageFont.load_default()

    dummy_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    bbox = dummy_draw.textbbox((0, 0), TEXT, font=pil_font)
    tw, th = bbox[2] - bbox[0] + 8, bbox[3] - bbox[1] + 8

    txt_img = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    ImageDraw.Draw(txt_img).text((4, 4), TEXT, font=pil_font, fill=NAVY_RGBA)
    stamp = txt_img.rotate(ANGLE, expand=True, resample=Image.BICUBIC)

    for rx, ry in [(0.20, 0.23), (0.62, 0.23),
                   (0.08, 0.52), (0.50, 0.52),
                   (0.20, 0.80), (0.62, 0.80)]:
        px = int(rx * w_px) - stamp.width // 2
        py = int(ry * h_px) - stamp.height // 2
        canvas.paste(stamp, (px, py), stamp)

    buf = _io.BytesIO()
    canvas.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def _add_watermarks(pdf_path: str, text: str = "vtusmartprep.com") -> None:
    """Stamp watermark text diagonally across every page using a PNG overlay."""
    doc = fitz.open(pdf_path)
    for page in doc:
        w, h = page.rect.width, page.rect.height
        png_data = _make_watermark_png(w, h, text=text)
        page.insert_image(page.rect, stream=png_data, overlay=True)
    tmp = pdf_path + ".tmp"
    doc.save(tmp, garbage=3, deflate=True)
    doc.close()
    os.replace(tmp, pdf_path)


def render_notes_pdf(notes: dict, figures_dir: str, output_pdf: str) -> None:
    if not _RENDER_AVAILABLE:
        print("Error: weasyprint and/or jinja2 are not installed.")
        print("Run: pip install weasyprint jinja2")
        sys.exit(1)

    html = build_html(notes, figures_dir)
    WeasyprintHTML(string=html).write_pdf(output_pdf)
    watermark_text = notes.get("watermark", "vtusmartprep.com")
    _add_watermarks(output_pdf, text=watermark_text)


# ══════════════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Generate VTU study notes PDF from a PDF."
    )
    parser.add_argument("pdf", help="Input PDF file path")
    parser.add_argument("--output", "-o", default=None,
                        help="Output directory (default: <pdf_stem>/)")
    parser.add_argument("--chapter", default=None,
                        help="Chapter title override (auto-detected if omitted)")
    parser.add_argument("--scale", type=float, default=2.0,
                        help="Figure render scale factor (default: 2.0)")
    parser.add_argument("--ai", action="store_true",
                        help="Use Claude Vision API for figure extraction fallback")
    parser.add_argument("--from-json", dest="from_json", action="store_true",
                        help="Render PDF from an existing notes_response.json (manual mode step 2)")
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        sys.exit(f"Error: file not found: {args.pdf}")

    pdf_path = args.pdf
    pdf_stem = Path(pdf_path).stem
    out_dir = Path(args.output or pdf_stem)
    figures_dir = str(out_dir / "figures")
    prompt_path = str(out_dir / "claude_prompt.txt")
    json_path = str(out_dir / "notes_response.json")
    notes_pdf = str(out_dir / f"{pdf_stem}_notes.pdf")

    out_dir.mkdir(parents=True, exist_ok=True)

    # ── --from-json: render PDF from existing JSON ────────────────────────────
    if args.from_json:
        if not os.path.isfile(json_path):
            sys.exit(
                f"Error: {json_path} not found.\n\n"
                f"Run without --from-json first to generate the prompt file,\n"
                f"then paste it into Claude.ai (with PDF attached) and save:\n"
                f"  {json_path}"
            )

        print(f"Loading notes from: {json_path}")
        notes = load_notes_json(json_path)
        notes = validate_notes_schema(notes, figures_dir)

        print("Rendering PDF...")
        render_notes_pdf(notes, figures_dir, notes_pdf)
        print(f"\nDone!  →  {notes_pdf}\n")
        return

    # ── Shared: figure extraction ─────────────────────────────────────────────
    print(f"\n── Stage 1: Figure extraction ───────────────────────────────────")
    print(f"   PDF: {pdf_path}")
    figure_paths = run_figure_extraction(pdf_path, figures_dir, args.ai, args.scale)
    figure_filenames = [Path(p).name for p in figure_paths]
    if figure_filenames:
        print(f"   {len(figure_filenames)} figure(s) → {figures_dir}/")
    else:
        print("   No figures found — notes will be text-only.")

    chapter_title = detect_chapter_title(pdf_path, args.chapter)
    print(f"   Chapter title: \"{chapter_title}\"")

    # ── Write prompt file ─────────────────────────────────────────────────────
    print(f"\n── Stage 2: Writing prompt file ──────────────────────────────────")
    build_prompt_file(
        figure_filenames, chapter_title,
        prompt_path, json_path, os.path.basename(pdf_path)
    )
    print(f"   Written: {prompt_path}")

    print(f"""
════════════════════════════════════════════════════════════════
  NEXT STEPS

  Option A — Claude Code skill (recommended):
    /vtunotes {os.path.basename(pdf_path)}
    (Claude reads the PDF here and writes the JSON automatically)

  Option B — Claude.ai (manual):
  1. Open claude.ai → new conversation
  2. ATTACH this PDF:  {os.path.basename(pdf_path)}
  3. Copy everything from "COPY FROM HERE ↓" in:
       {prompt_path}
  4. Paste into Claude.ai  (with the PDF attached)
  5. Save Claude's JSON response as:
       {json_path}
  6. Run:  python3 generate_notes.py {os.path.basename(pdf_path)} --from-json
════════════════════════════════════════════════════════════════
""")


if __name__ == "__main__":
    main()
