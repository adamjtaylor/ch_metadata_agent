#!/bin/bash
# Setup script for Antibody Curation Agent System

set -e

echo "================================================"
echo "Antibody Curation Agent System - Setup"
echo "================================================"
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Found Python $python_version"

# Create virtual environment
echo ""
echo "Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo ""
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo ""
echo "Installing dependencies..."
pip install -r requirements.txt

# Create data directories
echo ""
echo "Creating data directories..."
mkdir -p data/cache data/state data/output

# Copy .env.example to .env if it doesn't exist
if [ ! -f .env ]; then
    echo ""
    echo "Creating .env file..."
    cp .env.example .env
    echo ""
    echo "⚠️  IMPORTANT: Edit .env file and add your Anthropic API key!"
    echo "   Get your API key from: https://console.anthropic.com/"
fi

echo ""
echo "================================================"
echo "Setup complete! ✓"
echo "================================================"
echo ""
echo "Next steps:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Set your Anthropic API key in .env file"
echo ""
echo "3. Run the example:"
echo "   python main.py curate example_antibodies.csv"
echo ""
echo "4. For help:"
echo "   python main.py --help"
echo ""
