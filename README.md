# VTU Smart Prep

Generate professional, exam-ready study-notes PDFs from any VTU textbook chapter PDF — powered by Claude Code.

**What you get:** A watermarked, well-formatted PDF with section headings, key-term definitions, bullet points, embedded figures, and exam-tip callout boxes — all generated directly from the textbook chapter.

---

## How it works

1. You run `/vtunotes path/to/chapter.pdf` in Claude Code
2. Claude asks a few customisation questions (watermark, depth, emphasis)
3. Claude reads the PDF natively, identifies every figure, and extracts them precisely
4. Claude writes comprehensive study notes as structured JSON
5. A Python renderer (WeasyPrint) turns the JSON into a polished PDF

No external APIs needed — Claude Code running locally does all the heavy lifting.

---

## Prerequisites

- **[Claude Code](https://claude.ai/code)** — the CLI or desktop app
- **Python 3.9+**
- **pip** packages (see [requirements.txt](requirements.txt))
- macOS/Linux (Windows untested)

---

## Setup

```bash
git clone https://github.com/your-username/vtu-smart-prep.git
cd vtu-smart-prep
bash install.sh
```

Then open Claude Code **from this directory**:

```bash
claude   # or open the Claude Code desktop app in this folder
```

---

## Usage

```
/vtunotes path/to/your/chapter.pdf
```

Claude will ask you:

| Question | Purpose |
|----------|---------|
| Chapter / Module label | Header text (e.g. `Module 2 — Chapter 1`) |
| Subject / Course | Subject name (e.g. `Data Mining`) |
| Watermark text | Appears on every page (default: `vtusmartprep.com`) |
| Notes depth | `detailed` (full coverage) or `concise` (key points only) |
| Topics to emphasise | Optional — sections to expand on more |

Output is saved at: `<pdf-name>/<pdf-name>_notes.pdf`

---

## Example output

Input: `data_mining/module1_chapter1.pdf` (Han, Kamber & Pei — Chapter 1)

Output includes:
- Full section-by-section notes for all 7 sections
- 12 embedded figures with captions
- Key term definitions (KDD, OLAP, support/confidence, etc.)
- Exam-tip callouts throughout
- Chapter summary

---

## Customising the watermark

Pass any text in response to the watermark question, e.g.:
- `CS Dept — VTU 2024`
- `Your Name`
- Leave blank to use the default `vtusmartprep.com`

---

## Project structure

```
vtu-smart-prep/
├── .claude/
│   └── commands/
│       └── vtunotes.md      ← the /vtunotes command
├── generate_notes.py         ← PDF renderer (WeasyPrint + Jinja2)
├── extract_figures.py        ← fallback heuristic extractor (not used by default)
├── requirements.txt
├── install.sh
└── README.md
```

---

## Dependencies

| Package | Purpose |
|---------|---------|
| `pymupdf` | PDF reading + figure cropping |
| `Pillow` | Watermark image generation |
| `weasyprint` | HTML → PDF rendering |
| `jinja2` | Notes HTML template engine |

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `weasyprint` not found | `pip install -r requirements.txt` |
| pango error on macOS | `brew install pango` |
| Scanned PDF (no text) | Install `ocrmypdf` and run `ocrmypdf input.pdf output.pdf` first |
| Figure cut off | Tell Claude during the run; it will re-extract with adjusted coordinates |

---

## Contributing

Pull requests welcome. The core workflow is in [`.claude/commands/vtunotes.md`](.claude/commands/vtunotes.md) — it's plain Markdown, easy to read and modify.
