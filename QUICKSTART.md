# Quick Start Guide

Get started with the Antibody Curation Agent System in 5 minutes!

## Prerequisites

- Python 3.9 or higher
- Anthropic API key ([Get one here](https://console.anthropic.com/))

## Installation

### Option 1: Automated Setup (Recommended)

```bash
cd ch_metadata_agent
./setup.sh
```

This will:
- Create a virtual environment
- Install all dependencies
- Create necessary directories
- Set up configuration files

### Option 2: Manual Setup

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Create directories
mkdir -p data/cache data/state data/output

# Set up environment
cp .env.example .env
```

## Configuration

Edit `.env` file and add your API key:

```bash
ANTHROPIC_API_KEY=your-api-key-here
```

## Run Your First Curation

```bash
# Activate virtual environment (if not already active)
source venv/bin/activate

# Run the example
python main.py curate example_antibodies.csv
```

This will:
1. Parse the CSV and detect columns
2. Look up each marker in UniProt
3. Classify markers into functional categories
4. Harmonize and deduplicate entries
5. Validate data quality
6. Generate curated output

## View Results

Results are saved to `data/output/<run_id>/`:

```bash
ls data/output/*/
```

Files generated:
- `curated_antibodies.csv` - Final curated data
- `curated_antibodies.json` - JSON format
- `validation_report.txt` - Quality report
- `flagged_for_review.csv` - Records needing review (if any)

## Try Other Commands

### Analyze CSV structure
```bash
python main.py analyze example_antibodies.csv
```

### Look up a protein
```bash
python main.py lookup CD3
```

### List functional categories
```bash
python main.py categories
```

## Use Your Own Data

```bash
python main.py curate path/to/your/antibodies.csv
```

The system handles varied CSV formats automatically!

## Next Steps

- Read the full [README.md](README.md) for detailed documentation
- Customize functional categories in `config/taxonomy.yaml`
- Explore the agent architecture in the code

## Troubleshooting

**Problem:** API key error
**Solution:** Make sure `ANTHROPIC_API_KEY` is set in `.env` file

**Problem:** Module not found
**Solution:** Activate virtual environment: `source venv/bin/activate`

**Problem:** Low enrichment rate
**Solution:** Check that marker names use standard nomenclature (e.g., "CD3" not "cd-3")

## Getting Help

```bash
python main.py --help
python main.py curate --help
```

For more help, see [README.md](README.md) or open an issue on GitHub.
