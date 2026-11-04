#!/bin/bash
# Setup script for local development on macOS
# Creates a virtual environment and installs dependencies

set -e

echo "========================================="
echo "Setting up ComEner-data-management venv"
echo "========================================="

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.11 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✓ Found Python $PYTHON_VERSION"

# Create virtual environment if it doesn't exist
VENV_DIR=".venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating virtual environment in $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate virtual environment
echo "→ Activating virtual environment..."
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "→ Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "→ Installing dependencies from requirements.txt..."
pip install -r requirements.txt

echo ""
echo "========================================="
echo "✓ Setup complete!"
echo "========================================="
echo ""
echo "To activate the virtual environment, run:"
echo "  source .venv/bin/activate"
echo ""
echo "To start the Flask app:"
echo "  python run.py"
echo ""
echo "The app will be available at:"
echo "  http://localhost:5000"
echo ""
