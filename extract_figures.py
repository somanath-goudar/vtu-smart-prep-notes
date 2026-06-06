#!/usr/bin/env python3
"""
PDF Figure Extractor
Extracts figures from a PDF, named by their figure caption (e.g. Figure_1.png).

Usage:
    python extract_figures.py paper.pdf
    python extract_figures.py paper.pdf --output ./figures/
    python extract_figures.py paper.pdf --scale 3
    python extract_figures.py paper.pdf --ai          # Claude Vision fallback
"""

import argparse
import base64
import io
import json
import os
import re
import sys

import fitz  # PyMuPDF
from PIL import Image


# ── Caption detection ──────────────────────────────────────────────────────────

# Matches: Figure 1, Fig. 2a, FIGURE 3, fig 4b, Fig.1, Figure 12:
CAPTION_RE = re.compile(
    r"(?i)\b(fig(?:ure)?\.?\s*\d+[a-zA-Z]?)\b"
)

PADDING = 8            # pts — bottom/side crop padding
TOP_PADDING = 4        # pts — top buffer above detected figure top
MAX_CLUSTER_GAP = 50.0 # pts — max vertical gap between images in the same figure
BODY_WIDTH_RATIO = 0.55 # body text spans > 55% of page width
BODY_MIN_CHARS = 80    # body text has > 80 characters per block


def sanitize_name(label: str) -> str:
    """'Figure 3: Training Loss Curve' → 'Figure_3_Training_Loss_Curve'"""
    label = re.sub(r"(?i)fig\.\s*", "Figure_", label)
    label = re.sub(r"(?i)figure\s*", "Figure_", label)
    label = re.sub(r"[:\-–—]+", "_", label)
    label = re.sub(r"[^\w]", "_", label)
    label = re.sub(r"_+", "_", label).strip("_")
    return label


def extract_caption_label(text: str) -> str:
    """Pull the short figure id + a few words of title from raw span text."""
    text = text.strip()
    m = CAPTION_RE.search(text)
    if not m:
        return "Figure_unknown"
    prefix = sanitize_name(m.group(1))
    rest = text[m.end():].strip().lstrip(".:- ")
    words = re.split(r"\s+", rest)[:4]
    suffix = "_".join(w for w in words if re.search(r"[A-Za-z0-9]", w))
    suffix = re.sub(r"[^\w]", "_", suffix).strip("_")
    return f"{prefix}_{suffix}" if suffix else prefix


# ── Text-block helpers ─────────────────────────────────────────────────────────

def get_text_blocks(page):
    """Return list of (x0,y0,x1,y1,text) for every non-empty text block."""
    blocks = []
    for b in page.get_text("blocks"):
        x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
        if text.strip():
            blocks.append((x0, y0, x1, y1, text.strip()))
    return sorted(blocks, key=lambda b: (b[1], b[0]))


# ── Figure-top detection ───────────────────────────────────────────────────────

def _image_cluster_top(page, caption_y0: float) -> float | None:
    """
    Return the y0 of the contiguous image cluster just above the caption.
    Starts from the image whose bottom is closest to the caption and extends
    upward while consecutive images are within MAX_CLUSTER_GAP of each other.
    Used as a fallback when no body text is found above the figure.
    """
    try:
        images = page.get_images(full=True)
    except Exception:
        return None

    candidates = []
    for img_info in images:
        xref = img_info[0]
        try:
            rects = page.get_image_rects(xref)
        except Exception:
            continue
        for rect in rects:
            if rect.y1 <= caption_y0 + 5:
                candidates.append((float(rect.y0), float(rect.y1)))

    if not candidates:
        return None

    candidates.sort(key=lambda r: -r[1])  # closest to caption first

    cluster = [candidates[0]]
    for y0, y1 in candidates[1:]:
        if min(r[0] for r in cluster) - y1 <= MAX_CLUSTER_GAP:
            cluster.append((y0, y1))
        else:
            break

    return min(r[0] for r in cluster)


def find_figure_top(page, caption_y0: float, blocks: list) -> float:
    """
    Identify where the figure starts above its caption.

    Primary strategy — body-text layout detection:
      Walk upward from the caption through text blocks. The first block that
      looks like body text (spans most of the column width AND has substantial
      content) marks the end of prose and the start of the figure.  This
      reliably handles:
        • Raster-only figures  (image clips correctly without body text)
        • Vector / text-based figures (pure text diagrams, schemas)
        • Hybrid figures (e.g. IF-THEN rules + raster sub-diagram)
        • Multi-row figures (stacked sub-images with gaps between them)
        • Pages where a running header creates a large gap near the top

    Fallback — image cluster detection:
      When no body text block is found above (figure fills most of the page or
      sits at the very top), fall back to the contiguous image-cluster top.
      If that also finds nothing, return 0 (top of page).
    """
    pw = page.rect.width
    above = [b for b in blocks if b[1] < caption_y0 - PADDING]

    if not above:
        return 0.0

    # Iterate bottom-up: stop at the first block that looks like body text.
    above_sorted = sorted(above, key=lambda b: -b[1])  # closest to caption first
    for x0, y0, x1, y1, text in above_sorted:
        if (x1 - x0) >= pw * BODY_WIDTH_RATIO and len(text.strip()) >= BODY_MIN_CHARS:
            return y1  # figure starts just after this body-text block

    # No body text found — figure occupies most/all of the page.
    img_top = _image_cluster_top(page, caption_y0)
    return img_top if img_top is not None else 0.0


# ── Heuristic extraction ───────────────────────────────────────────────────────

def extract_figures_heuristic(page, scale: float, output_dir: str, seen_labels: set):
    """
    Find figure captions, compute figure region, render and save.
    Uses find_figure_top() to locate where each figure begins.
    Returns list of saved file paths.
    """
    saved = []
    pw, ph = page.rect.width, page.rect.height
    blocks = get_text_blocks(page)

    # Collect caption blocks
    caption_blocks = []
    for x0, y0, x1, y1, text in blocks:
        m = CAPTION_RE.search(text)
        if m and m.start() < 10 and len(text.strip()) < 600:
            caption_blocks.append((x0, y0, x1, y1, text))

    if not caption_blocks:
        return saved

    for cap_x0, cap_y0, cap_x1, cap_y1, cap_text in caption_blocks:
        label = extract_caption_label(cap_text)

        unique_label = label
        suffix = 1
        while unique_label in seen_labels:
            unique_label = f"{label}_v{suffix}"
            suffix += 1
        seen_labels.add(unique_label)

        # ── Determine figure top ──────────────────────────────────────────────
        fig_top = find_figure_top(page, cap_y0, blocks)
        fig_top_padded = max(0, fig_top - TOP_PADDING)
        fig_bottom = min(ph, cap_y1 + PADDING)

        if fig_bottom - fig_top_padded < 10:
            continue

        clip = fitz.Rect(0, fig_top_padded, pw, fig_bottom)
        mat = fitz.Matrix(scale, scale)
        pix = page.get_pixmap(matrix=mat, clip=clip)

        out_path = os.path.join(output_dir, f"{unique_label}.png")
        pix.save(out_path)
        saved.append(out_path)
        print(f"  Saved: {out_path}  ({pix.width}×{pix.height}px)")

    return saved


# ── AI fallback (Claude Vision) ────────────────────────────────────────────────

AI_PROMPT = """You are analysing a page from a PDF document.

Identify every figure (charts, diagrams, images, plots) on this page.
For each figure return a JSON object with:
  - "label": the full figure caption text (e.g. "Figure 3: Training Loss")
  - "bbox": [x0_pct, y0_pct, x1_pct, y1_pct]  (0–100, % of image width/height)

Return ONLY a JSON array, no markdown, no prose.  Example:
[{"label":"Figure 1: Overview", "bbox":[5,10,95,45]}]

If no figures, return [].
"""


def extract_figures_ai(page, scale: float, output_dir: str, seen_labels: set):
    """Use Claude Vision to locate figures on pages where heuristic found nothing."""
    try:
        import anthropic
    except ImportError:
        print("  [AI] anthropic SDK not installed — skipping AI fallback.")
        return []

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("  [AI] ANTHROPIC_API_KEY not set — skipping AI fallback.")
        return []

    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img_bytes = pix.tobytes("png")
    img_b64 = base64.standard_b64encode(img_bytes).decode()

    client = anthropic.Anthropic(api_key=api_key)
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": "image/png", "data": img_b64},
                    },
                    {"type": "text", "text": AI_PROMPT},
                ],
            }],
        )
    except Exception as e:
        print(f"  [AI] API call failed: {e}")
        return []

    raw = resp.content[0].text.strip()
    try:
        figures = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\[.*\]", raw, re.DOTALL)
        if m:
            try:
                figures = json.loads(m.group())
            except Exception:
                print(f"  [AI] Could not parse response: {raw[:200]}")
                return []
        else:
            print(f"  [AI] Could not parse response: {raw[:200]}")
            return []

    saved = []
    img_w, img_h = pix.width, pix.height

    for fig in figures:
        label_raw = fig.get("label", "Figure_unknown")
        bbox_pct = fig.get("bbox", [0, 0, 100, 100])
        label = extract_caption_label(label_raw)

        unique_label = label
        suffix = 1
        while unique_label in seen_labels:
            unique_label = f"{label}_v{suffix}"
            suffix += 1
        seen_labels.add(unique_label)

        x0 = max(0, int(bbox_pct[0] / 100 * img_w))
        y0 = max(0, int(bbox_pct[1] / 100 * img_h))
        x1 = min(img_w, int(bbox_pct[2] / 100 * img_w))
        y1 = min(img_h, int(bbox_pct[3] / 100 * img_h))

        if x1 - x0 < 10 or y1 - y0 < 10:
            continue

        full_img = Image.open(io.BytesIO(img_bytes))
        cropped = full_img.crop((x0, y0, x1, y1))
        out_path = os.path.join(output_dir, f"{unique_label}.png")
        cropped.save(out_path)
        saved.append(out_path)
        print(f"  [AI] Saved: {out_path}  ({cropped.width}×{cropped.height}px)")

    return saved


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Extract figures from a PDF and save as named PNGs."
    )
    parser.add_argument("pdf", help="Path to the input PDF file")
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output directory (default: <pdf_name>_figures/)"
    )
    parser.add_argument(
        "--scale", "-s", type=float, default=2.0,
        help="Render scale factor — higher = sharper (default: 2.0)"
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="Use Claude Vision API on pages where no figures are found heuristically"
    )
    args = parser.parse_args()

    if not os.path.isfile(args.pdf):
        sys.exit(f"Error: file not found: {args.pdf}")

    pdf_stem = os.path.splitext(os.path.basename(args.pdf))[0]
    output_dir = args.output or f"{pdf_stem}_figures"
    os.makedirs(output_dir, exist_ok=True)

    doc = fitz.open(args.pdf)
    total_pages = len(doc)
    seen_labels: set = set()
    total_saved = []

    print(f"\nProcessing: {args.pdf}  ({total_pages} pages)")
    print(f"Output dir: {output_dir}/\n")

    for page_num in range(total_pages):
        page = doc[page_num]
        print(f"Page {page_num + 1}/{total_pages}", end=" ... ")

        saved = extract_figures_heuristic(page, args.scale, output_dir, seen_labels)

        if not saved and args.ai:
            print("no captions found — trying AI fallback")
            saved = extract_figures_ai(page, args.scale, output_dir, seen_labels)
        elif not saved:
            print("no figures found")

        total_saved.extend(saved)

    doc.close()
    print(f"\nDone. {len(total_saved)} figure(s) extracted to '{output_dir}/'")


if __name__ == "__main__":
    main()
