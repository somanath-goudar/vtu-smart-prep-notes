# VTU Smart Prep — Study Notes Generator

Generate a professional watermarked study-notes PDF from a VTU textbook chapter PDF.

**Usage:** `/vtunotes <path-to-pdf>`

> **Requirement:** Open Claude Code from the root of this project (`vtu-smart-prep/`) so all paths resolve correctly.

---

## Step 0 — Gather inputs BEFORE doing anything else

**Stop here and ask the user these questions. Do not touch the PDF until they answer.**

Present the following as a numbered list and wait for their response:

---

> **Before I start, a few quick questions to customise your notes:**
>
> 1. **Chapter / Module label** — How should the header read?
>    e.g. `Module 1 — Chapter 1: Introduction to Data Mining`
>    *(Leave blank to auto-detect from the PDF)*
>
> 2. **Subject / Course name** — What subject is this?
>    e.g. `Data Mining`, `Computer Networks`, `Machine Learning`
>    *(Leave blank to auto-detect)*
>
> 3. **Watermark text** — What should appear as the watermark on every page?
>    *(Default: `vtusmartprep.com`)*
>
> 4. **Notes depth**
>    - `detailed` *(default)* — full section-by-section coverage, lots of exam tips
>    - `concise` — key concepts only, shorter notes
>
> 5. **Topics to emphasise** *(optional)* — Any specific sections or concepts to go deeper on?

---

Store the answers as:
- `CHAPTER_LABEL` — user's answer to Q1 (or auto-detect if blank)
- `SUBJECT` — user's answer to Q2 (or auto-detect if blank)
- `WATERMARK` — user's answer to Q3 (default: `vtusmartprep.com`)
- `DEPTH` — `detailed` or `concise`
- `EMPHASIS` — free-text list of topics (may be empty)

---

## Step 1 — Verify project root and set up folders

```bash
# Verify we're in the right directory
ls generate_notes.py 2>/dev/null || { echo "ERROR: Run Claude Code from the vtu-smart-prep project root."; exit 1; }

mkdir -p <pdf_stem>/figures
```

Resolve `$ARGUMENTS` to an absolute PDF path (check relative to CWD first, then as-is).

Get page dimensions for coordinate reference:

```bash
python3 -c "
import fitz
doc = fitz.open('<resolved-pdf-path>')
p = doc[0]
print(f'Page size: {p.rect.width:.0f} x {p.rect.height:.0f} pts  ({len(doc)} pages)')
"
```

---

## Step 2 — Read the PDF and extract figures

Use the **Read** tool to read the full PDF. You see all text, diagrams, and figures on every page.

As you read, for each figure note:
- **Page index** (0-based)
- **y_top** — where figure content visually starts. Go **15–20 pts above** the top edge to avoid cutoff.
- **y_bottom** — bottom of the caption line (include full caption text)
- **Filename** — sanitize the caption: `Figure_X_Y_Short_description.png`

After reading, extract all figures in one batch:

```bash
python3 - << 'PYEOF'
import fitz, os

doc  = fitz.open("<resolved-pdf-path>")
out  = "<pdf_stem>/figures"          # relative to project root
os.makedirs(out, exist_ok=True)

# (page_0idx, y_top, y_bottom, "filename.png") — from your PDF reading
figures = [
    (2, 140, 600, "Figure_1_1_The_evolution_of.png"),
    # ...
]

for page_idx, y0, y1, name in figures:
    page = doc[page_idx]
    clip = fitz.Rect(0, y0, page.rect.width, y1)
    pix  = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=clip)
    pix.save(f"{out}/{name}")
    print(f"  Saved: {name}  ({pix.width}×{pix.height}px)")

doc.close()
print(f"\nDone — {len(figures)} figure(s) → {out}/")
PYEOF
```

> **Tips:** Page height ≈ 842 pts for A4. Be generous with y_top. Include the full caption in y_bottom.

---

## Step 3 — Confirm extracted figures

```bash
ls <pdf_stem>/figures/
```

If any figure looks cut off, re-run Step 2 for just that figure with a lower y_top.

---

## Step 4 — Generate the notes JSON

Using your PDF reading, confirmed figure filenames, and the Step 0 inputs, generate a complete JSON object. Apply `DEPTH` and `EMPHASIS` accordingly.

Write to: `<pdf_stem>/notes_response.json`

Use the **Write** tool to save it.

---

## Step 5 — Render the PDF

```bash
python3 generate_notes.py <resolved-pdf-path> --from-json
```

---

## Step 6 — Report to the user

Tell the user the output PDF is at:
```
<pdf_stem>/<pdf_stem>_notes.pdf
```

---

## JSON schema (use in Step 4)

```json
{
  "title": "Full chapter/topic title",
  "chapter_label": "<CHAPTER_LABEL from Step 0>",
  "watermark": "<WATERMARK from Step 0>",
  "overview": "2–4 sentence plain-language summary.",
  "topics_covered": ["Topic 1", "Topic 2", "Topic 3", "Topic 4"],
  "sections": [
    {
      "heading": "Section heading",
      "level": 1,
      "content": [
        { "type": "paragraph", "text": "Explanation." },
        { "type": "key_term", "term": "Term", "definition": "Clear undergraduate-level definition." },
        { "type": "bullet_list", "items": ["Point one.", "Point two."] },
        { "type": "numbered_list", "items": ["Step one.", "Step two."] },
        { "type": "figure", "filename": "Figure_1_1_The_evolution_of.png", "caption": "What the figure shows." },
        { "type": "callout", "text": "Exam tip: something students often miss." }
      ]
    }
  ],
  "summary": "3–5 sentence synthesis of core ideas."
}
```

### Field rules

| Field | Rule |
|-------|------|
| `level` | 1 = main section, 2 = sub-section, 3 = sub-sub-section |
| `filename` | Must exactly match a name from Step 3 listing |
| `topics_covered` | 4–8 items |
| `watermark` | Use the value from Step 0 |
| For `detailed` depth | All sections, 3+ callouts per section, define every term |
| For `concise` depth | Major sections only, 1 callout per section, key terms only |

---

## Troubleshooting

| Error | Fix |
|-------|-----|
| `weasyprint not found` | `pip install -r requirements.txt` |
| pango dyld error (macOS) | `brew install pango` |
| Scanned PDF (no text) | `ocrmypdf input.pdf output.pdf` first |
| Figure cut off | Re-run Step 2 for that figure with a lower y_top |
| JSON parse error | Check the JSON for missing commas or brackets |
