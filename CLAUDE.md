# VTU Smart Prep — Claude Setup Guide

This project turns any VTU textbook chapter PDF into a professional, watermarked study-notes PDF using Claude Code's native PDF reading.

---

## If you are Claude and this repo was just cloned — run setup now

```bash
bash install.sh
```

That installs all Python dependencies (`pymupdf`, `weasyprint`, `jinja2`, `Pillow`) and, on macOS, installs `pango` via Homebrew if needed.

**After install completes, tell the user:**

> Setup complete. Open Claude Code from this directory and run:
> ```
> /vtunotes path/to/your/chapter.pdf
> ```
> I'll ask a few customisation questions (watermark, depth, focus areas) before generating your notes.

---

## What this project does

1. User runs `/vtunotes <pdf>` inside Claude Code
2. Claude asks customisation questions (chapter label, watermark, notes depth, emphasis)
3. Claude reads the PDF natively — sees all text and figures on every page
4. Claude identifies each figure's location (page + y-coordinates) and extracts them as PNGs via PyMuPDF
5. Claude writes comprehensive study notes as a JSON file
6. `generate_notes.py --from-json` renders the JSON into a watermarked PDF using WeasyPrint + Jinja2

No external API calls. Everything runs locally inside Claude Code.

---

## Project structure

```
vtu-smart-prep/
├── CLAUDE.md                        ← you are here
├── README.md                        ← user-facing docs
├── install.sh                       ← one-command setup
├── requirements.txt                 ← Python dependencies
├── generate_notes.py                ← PDF renderer (WeasyPrint + Jinja2)
├── extract_figures.py               ← fallback heuristic extractor (not used by default)
└── .claude/
    └── commands/
        └── vtunotes.md              ← the /vtunotes workflow command
```

---

## How the /vtunotes command works

The workflow lives in `.claude/commands/vtunotes.md`. When a user runs `/vtunotes chapter.pdf`, Claude:

1. **Step 0** — Asks customisation questions before starting
2. **Step 1** — Creates `<pdf_stem>/figures/` output directory, checks page dimensions
3. **Step 2** — Reads the full PDF, identifies figures by page + y-coordinates, crops them with PyMuPDF
4. **Step 3** — Confirms extracted figure filenames
5. **Step 4** — Writes `<pdf_stem>/notes_response.json` with full structured notes
6. **Step 5** — Runs `python3 generate_notes.py <pdf> --from-json` to render the final PDF
7. **Step 6** — Reports output path to user

Output lands at: `<pdf_stem>/<pdf_stem>_notes.pdf`

---

## generate_notes.py — key facts

- Entry point for PDF rendering only (figure extraction is now done by Claude directly)
- `--from-json` flag: reads `<pdf_stem>/notes_response.json` and renders the PDF
- Watermark text is read from `notes["watermark"]` (default: `"vtusmartprep.com"`)
- Uses WeasyPrint + Jinja2 for HTML→PDF rendering
- Adds a diagonal PNG watermark overlay on every page via PyMuPDF

---

## Notes JSON schema

The JSON written in Step 4 must match this structure:

```json
{
  "title": "Chapter title",
  "chapter_label": "Module X — Chapter Y",
  "watermark": "custom watermark text",
  "overview": "2–4 sentence summary",
  "topics_covered": ["Topic 1", "Topic 2"],
  "sections": [
    {
      "heading": "Section name",
      "level": 1,
      "content": [
        { "type": "paragraph", "text": "..." },
        { "type": "key_term", "term": "Term", "definition": "..." },
        { "type": "bullet_list", "items": ["...", "..."] },
        { "type": "figure", "filename": "Figure_1_1_Name.png", "caption": "..." },
        { "type": "callout", "text": "Exam tip: ..." }
      ]
    }
  ],
  "summary": "3–5 sentence synthesis"
}
```

`level`: 1 = H2 section, 2 = H3 sub-section, 3 = H4 sub-sub-section

---

## Modifying the workflow

The entire workflow is plain Markdown in `.claude/commands/vtunotes.md` — edit it directly to change what questions are asked, how notes are structured, or how figures are extracted.

To change the default watermark: edit the `watermark` field default in `generate_notes.py → validate_notes_schema()`.
