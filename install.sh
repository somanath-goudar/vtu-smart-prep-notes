#!/usr/bin/env bash
set -e

echo "=== VTU Smart Prep — Setup ==="
echo ""

# ── Check Python ───────────────────────────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.9+ first."
  exit 1
fi
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✓ Python $PYTHON_VERSION detected"

# ── Install Python dependencies ────────────────────────────────────────────────
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt -q
echo "✓ Python packages installed"

# ── macOS: pango (required by WeasyPrint) ─────────────────────────────────────
if [[ "$OSTYPE" == "darwin"* ]]; then
  if command -v brew &>/dev/null; then
    if ! brew list pango &>/dev/null 2>&1; then
      echo ""
      echo "Installing pango (required by WeasyPrint on macOS)..."
      brew install pango -q
    fi
    echo "✓ pango available"
  else
    echo ""
    echo "NOTE: Homebrew not found."
    echo "      If you see a pango error when rendering, install Homebrew then run: brew install pango"
  fi
fi

# ── Install global /vtunotes command ──────────────────────────────────────────
echo ""
echo "Installing global /vtunotes command..."
PROJ_DIR="$(pwd)"
mkdir -p ~/.claude/commands

# Substitute PROJECT_ROOT_PLACEHOLDER with this machine's actual project path
sed "s|PROJECT_ROOT_PLACEHOLDER|$PROJ_DIR|g" \
  .claude/commands/vtunotes.md > ~/.claude/commands/vtunotes.md

echo "✓ /vtunotes installed → ~/.claude/commands/vtunotes.md"
echo "  Project root pinned to: $PROJ_DIR"

# ── Done ───────────────────────────────────────────────────────────────────────
echo ""
echo "=== Setup complete! ==="
echo ""
echo "Open Claude Desktop (or Claude Code) from any directory and run:"
echo ""
echo "    /vtunotes path/to/your/chapter.pdf"
echo ""
echo "Claude will ask a few customisation questions, then generate your notes PDF."
echo "Output is saved to: $PROJ_DIR/<pdf-name>/<pdf-name>_notes.pdf"
echo ""
