#!/usr/bin/env python3
"""
Main CLI for the Antibody Curation Agent System.
"""

import os
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn
from dotenv import load_dotenv

from orchestrator import AntibodyCurationOrchestrator, WorkflowStatus

# Load environment variables
load_dotenv()

console = Console()


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """
    Antibody Curation Agent System

    An agentic system for curating and harmonizing antibody metadata
    from multiplexed tissue imaging experiments.
    """
    pass


@cli.command()
@click.argument('csv_file', type=click.Path(exists=True, path_type=Path))
@click.option(
    '--api-key',
    envvar='ANTHROPIC_API_KEY',
    required=True,
    help='Anthropic API key (or set ANTHROPIC_API_KEY env var)'
)
@click.option(
    '--output-dir',
    type=click.Path(path_type=Path),
    default='data/output',
    help='Output directory for results'
)
@click.option(
    '--cache-dir',
    type=click.Path(path_type=Path),
    default='data/cache',
    help='Cache directory for UniProt lookups'
)
@click.option(
    '--config',
    type=click.Path(exists=True, path_type=Path),
    default='config/taxonomy.yaml',
    help='Path to taxonomy configuration file'
)
@click.option(
    '--run-id',
    help='Custom run ID (auto-generated if not specified)'
)
@click.option(
    '--resume',
    is_flag=True,
    help='Resume from checkpoint'
)
@click.option(
    '--simplified-output',
    is_flag=True,
    help='Generate simplified 1:1 CSV output (skips deduplication)'
)
def curate(csv_file, api_key, output_dir, cache_dir, config, run_id, resume, simplified_output):
    """
    Curate antibody metadata from CSV file.

    This command runs the full workflow:
    1. Parse CSV and detect schema
    2. Enrich with UniProt data
    3. Classify into functional categories
    4. Harmonize and deduplicate (unless --simplified-output)
    5. Validate and generate report

    Example:
        python main.py curate antibodies.csv
        python main.py curate antibodies.csv --simplified-output
    """
    console.print("\n[bold cyan]Antibody Curation Agent System[/bold cyan]\n")

    # Initialize orchestrator
    orchestrator = AntibodyCurationOrchestrator(
        api_key=api_key,
        cache_dir=Path(cache_dir),
        output_dir=Path(output_dir),
        config_path=Path(config) if config else None
    )

    # Run workflow
    try:
        result = orchestrator.curate_antibody_csv(
            csv_file=csv_file,
            run_id=run_id,
            resume=resume,
            simplified_output=simplified_output
        )

        # Display results
        if result.status == WorkflowStatus.COMPLETED:
            console.print("\n[bold green]✓ Workflow completed successfully![/bold green]\n")

            # Display statistics table
            display_statistics(result.statistics)

            # Display summary
            console.print(f"\n[bold]Output Location:[/bold]")
            console.print(f"  {output_dir / (run_id or 'latest')}")
            console.print(f"\n[bold]Files generated:[/bold]")

            if simplified_output:
                console.print(f"  • curated_simple.csv - Simplified 1:1 output (input row → output row)")
                console.print(f"  • curated_full.json - Complete data in JSON format")
            else:
                console.print(f"  • curated_antibodies.csv - Validated antibody records")
                console.print(f"  • curated_antibodies.json - JSON format")
                console.print(f"  • validation_report.txt - Quality validation report")

                if result.flagged_records:
                    console.print(f"  • flagged_for_review.csv - Records requiring manual review")

            console.print()

        else:
            console.print("\n[bold red]✗ Workflow failed[/bold red]\n")
            for error in result.errors:
                console.print(f"  [red]• {error}[/red]")
            console.print()
            sys.exit(1)

    except Exception as e:
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]\n")
        sys.exit(1)


@cli.command()
@click.argument('csv_file', type=click.Path(exists=True, path_type=Path))
@click.option(
    '--api-key',
    envvar='ANTHROPIC_API_KEY',
    required=True,
    help='Anthropic API key'
)
def analyze(csv_file, api_key):
    """
    Analyze CSV structure without running full workflow.

    Shows detected column mappings and sample data.

    Example:
        python main.py analyze antibodies.csv
    """
    from tools.csv_analyzer import CSVSchemaDetector

    console.print("\n[bold cyan]Analyzing CSV Structure[/bold cyan]\n")

    try:
        detector = CSVSchemaDetector(api_key)
        mapping, df = detector.analyze_csv(csv_file)

        # Display mapping
        console.print("[bold]Detected Column Mapping:[/bold]\n")

        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("Standard Field")
        table.add_column("CSV Column")
        table.add_column("Status")

        mapping_dict = mapping.to_dict()
        for field, column in mapping_dict.items():
            if field != 'additional_columns':
                status = "✓ Mapped" if column else "⚠ Missing"
                style = "green" if column else "yellow"
                table.add_row(field, column or "-", f"[{style}]{status}[/{style}]")

        console.print(table)

        # Display sample data
        console.print(f"\n[bold]Sample Data:[/bold] (first 3 rows)\n")
        console.print(df.head(3).to_string())
        console.print()

    except Exception as e:
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]\n")
        sys.exit(1)


@cli.command()
@click.argument('marker_name')
@click.option(
    '--organism',
    default='human',
    help='Target organism'
)
def lookup(marker_name, organism):
    """
    Look up protein information in UniProt.

    Example:
        python main.py lookup CD3
    """
    from tools.uniprot_api import lookup_protein

    console.print(f"\n[bold cyan]Looking up: {marker_name}[/bold cyan]\n")

    try:
        entries = lookup_protein(marker_name, organism)

        if not entries:
            console.print("[yellow]No results found[/yellow]\n")
            return

        # Display results
        for i, entry in enumerate(entries[:5], 1):
            console.print(f"[bold]{i}. {entry.protein_name}[/bold]")
            console.print(f"   UniProt ID: {entry.accession}")
            console.print(f"   Gene: {entry.gene_name or 'N/A'}")
            console.print(f"   Organism: {entry.organism}")

            if entry.subcellular_location:
                valid_locations = [loc for loc in entry.subcellular_location if loc and isinstance(loc, str)]
                if valid_locations:
                    console.print(f"   Location: {', '.join(valid_locations)}")

            console.print(f"   Confidence: {entry.confidence_score:.2f}")
            console.print()

    except Exception as e:
        console.print(f"\n[bold red]✗ Error: {e}[/bold red]\n")
        sys.exit(1)


@cli.command()
def categories():
    """
    List available functional categories.

    Example:
        python main.py categories
    """
    from tools.classifier import FunctionalTaxonomy

    console.print("\n[bold cyan]Functional Categories[/bold cyan]\n")

    taxonomy = FunctionalTaxonomy()

    for key, category in taxonomy.get_all_categories().items():
        console.print(f"[bold]{category.name}[/bold] ({key})")
        console.print(f"  {category.description}")
        console.print(f"  Examples: {', '.join(category.examples[:3])}")
        console.print()


def display_statistics(stats: dict):
    """Display workflow statistics in a nice table."""
    table = Table(title="Workflow Statistics", show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")

    table.add_row("Input Records", str(stats['input_records']))
    table.add_row("Enriched with UniProt", f"{stats['enriched_records']} ({stats['enrichment_rate']:.1%})")
    table.add_row("Classified", f"{stats['classified_records']} ({stats['classification_rate']:.1%})")
    table.add_row("After Harmonization", str(stats['harmonized_records']))
    table.add_row("Duplicates Merged", str(stats['deduplication_count']))
    table.add_row("Validated Records", str(stats['validated_records']))
    table.add_row("Flagged for Review", str(stats['flagged_records']))
    table.add_row("Success Rate", f"{stats['success_rate']:.1%}", style="bold green")

    console.print(table)


if __name__ == '__main__':
    cli()
