"""
CSV Analyzer Tool for detecting and mapping antibody metadata columns.
Uses LLM to handle varied column naming conventions.
"""

import csv
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
import pandas as pd

from anthropic import Anthropic


@dataclass
class ColumnMapping:
    """Represents detected column mappings in a CSV file."""
    marker_name: Optional[str] = None  # Antibody/marker name
    target_name: Optional[str] = None  # Target protein/gene name
    target_id: Optional[str] = None  # External ID (UniProt, Entrez, etc.)
    clone_id: Optional[str] = None  # Antibody clone identifier
    vendor: Optional[str] = None  # Manufacturer/vendor
    catalog_number: Optional[str] = None
    conjugate: Optional[str] = None  # Fluorophore/tag
    concentration: Optional[str] = None
    dilution: Optional[str] = None
    species: Optional[str] = None  # Host species
    additional_columns: Dict[str, str] = None  # Other relevant columns

    def to_dict(self) -> Dict[str, Optional[str]]:
        return {
            'marker_name': self.marker_name,
            'target_name': self.target_name,
            'target_id': self.target_id,
            'clone_id': self.clone_id,
            'vendor': self.vendor,
            'catalog_number': self.catalog_number,
            'conjugate': self.conjugate,
            'concentration': self.concentration,
            'dilution': self.dilution,
            'species': self.species,
            'additional_columns': self.additional_columns or {}
        }


class CSVSchemaDetector:
    """
    Detects column schemas in antibody CSV files using LLM.
    Handles varied naming conventions.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Anthropic API key.

        Args:
            api_key: Anthropic API key (or set ANTHROPIC_API_KEY env var)
        """
        self.client = Anthropic(api_key=api_key)

    def analyze_csv(self, file_path: Path) -> Tuple[ColumnMapping, pd.DataFrame]:
        """
        Analyze CSV file and detect column mappings.

        Args:
            file_path: Path to CSV file

        Returns:
            Tuple of (ColumnMapping, DataFrame with sample rows)
        """
        # Read CSV with pandas
        try:
            df = pd.read_csv(file_path)
        except Exception as e:
            raise ValueError(f"Failed to read CSV: {e}")

        if df.empty:
            raise ValueError("CSV file is empty")

        # Get column names and sample data
        columns = df.columns.tolist()
        sample_rows = df.head(5).to_dict('records')

        # Use LLM to detect column mappings
        mapping = self._detect_columns_with_llm(columns, sample_rows)

        return mapping, df

    def _detect_columns_with_llm(
        self,
        columns: List[str],
        sample_rows: List[Dict]
    ) -> ColumnMapping:
        """Use Claude to intelligently map column names."""

        prompt = f"""You are analyzing a CSV file containing antibody metadata from a multiplexed tissue imaging experiment.

Columns: {columns}

Sample data (first 5 rows):
{self._format_sample_data(sample_rows)}

Please identify which columns correspond to the following standard fields:
- marker_name: The antibody or marker name (e.g., "CD3", "Ki67", "PanCK")
- target_name: The target protein or gene name
- target_id: External identifier (UniProt ID, Entrez ID, etc.)
- clone_id: Antibody clone identifier
- vendor: Manufacturer or vendor name
- catalog_number: Product catalog number
- conjugate: Fluorophore or conjugate tag (e.g., "FITC", "Alexa488")
- concentration: Antibody concentration
- dilution: Dilution ratio
- species: Host species for the antibody

Return your answer as a JSON object mapping standard field names to the actual column names in this CSV.
Use null for fields that are not present.

Also identify any other relevant columns that don't fit these categories.

Example output format:
{{
  "marker_name": "Marker",
  "target_name": "Target",
  "target_id": null,
  "clone_id": "Clone",
  "vendor": "Vendor",
  "catalog_number": "Cat#",
  "conjugate": "Fluorophore",
  "concentration": null,
  "dilution": "Dilution",
  "species": "Host",
  "additional_columns": {{"Panel": "Panel", "Channel": "Channel"}}
}}

Return ONLY the JSON object, no additional text."""

        response = self.client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        import json
        response_text = response.content[0].text.strip()

        # Remove markdown code blocks if present
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
            response_text = response_text.strip()

        mapping_dict = json.loads(response_text)

        # Create ColumnMapping object
        return ColumnMapping(
            marker_name=mapping_dict.get('marker_name'),
            target_name=mapping_dict.get('target_name'),
            target_id=mapping_dict.get('target_id'),
            clone_id=mapping_dict.get('clone_id'),
            vendor=mapping_dict.get('vendor'),
            catalog_number=mapping_dict.get('catalog_number'),
            conjugate=mapping_dict.get('conjugate'),
            concentration=mapping_dict.get('concentration'),
            dilution=mapping_dict.get('dilution'),
            species=mapping_dict.get('species'),
            additional_columns=mapping_dict.get('additional_columns', {})
        )

    def _format_sample_data(self, sample_rows: List[Dict]) -> str:
        """Format sample rows for LLM prompt."""
        lines = []
        for i, row in enumerate(sample_rows, 1):
            lines.append(f"Row {i}:")
            for key, value in row.items():
                lines.append(f"  {key}: {value}")
        return "\n".join(lines)


class CSVParser:
    """
    Parses CSV files using detected column mappings.
    """

    def __init__(self, column_mapping: ColumnMapping):
        self.mapping = column_mapping

    def parse(self, df: pd.DataFrame) -> List[Dict]:
        """
        Parse DataFrame using column mapping.

        Args:
            df: Pandas DataFrame

        Returns:
            List of normalized records
        """
        records = []

        for idx, row in df.iterrows():
            # Add row number (1-indexed, +2 for header row)
            input_row_number = idx + 2

            marker_name_value = self._get_value(row, self.mapping.marker_name)

            record = {
                'input_row_number': input_row_number,
                'identified_target_original': marker_name_value,  # Store original before harmonization
                'marker_name': marker_name_value,
                'target_name': self._get_value(row, self.mapping.target_name),
                'target_id': self._get_value(row, self.mapping.target_id),
                'clone_id': self._get_value(row, self.mapping.clone_id),
                'vendor': self._get_value(row, self.mapping.vendor),
                'catalog_number': self._get_value(row, self.mapping.catalog_number),
                'conjugate': self._get_value(row, self.mapping.conjugate),
                'concentration': self._get_value(row, self.mapping.concentration),
                'dilution': self._get_value(row, self.mapping.dilution),
                'species': self._get_value(row, self.mapping.species),
            }

            # Add additional columns
            if self.mapping.additional_columns:
                for std_name, col_name in self.mapping.additional_columns.items():
                    record[std_name] = self._get_value(row, col_name)

            records.append(record)

        return records

    def _get_value(self, row: pd.Series, column: Optional[str]) -> Optional[str]:
        """Safely get value from row."""
        if column is None or column not in row:
            return None

        value = row[column]

        # Handle NaN values
        if pd.isna(value):
            return None

        return str(value).strip()


def analyze_antibody_csv(
    file_path: Path,
    api_key: Optional[str] = None
) -> Tuple[ColumnMapping, List[Dict]]:
    """
    Convenience function to analyze and parse antibody CSV file.

    Args:
        file_path: Path to CSV file
        api_key: Anthropic API key

    Returns:
        Tuple of (ColumnMapping, list of parsed records)
    """
    detector = CSVSchemaDetector(api_key)
    mapping, df = detector.analyze_csv(file_path)

    parser = CSVParser(mapping)
    records = parser.parse(df)

    return mapping, records
