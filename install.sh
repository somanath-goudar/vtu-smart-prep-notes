#!/usr/bin/env bash
set -e

echo "=== VTU Smart Prep — Setup ==="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found. Install Python 3.9+ first."
  exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "Python $PYTHON_VERSION detected."

# Install Python dependencies
echo ""
echo "Installing Python dependencies..."
pip install -r requirements.txt

# macOS: check for pango (required by WeasyPrint)
if [[ "$OSTYPE" == "darwin"* ]]; then
  if ! command -v brew &>/dev/null; then
    echo ""
    echo "NOTE: Homebrew not found. If you get a 'pango' error when rendering,"
    echo "      install Homebrew (https://brew.sh) and then run: brew install pango"
  elif ! brew list pango &>/dev/null 2>&1; then
    echo ""
    echo "Installing pango (required by WeasyPrint on macOS)..."
    brew install pango
  fi
fi

echo ""
echo "=== Setup complete! ==="
echo ""
echo "Next steps:"
echo "  1. Open Claude Code from this directory:"
echo "       claude"
echo "  2. Run:"
echo "       /vtunotes path/to/your/chapter.pdf"
echo ""
