"""
CSV Parser Agent: Discovers and parses varied CSV structures.
"""

from pathlib import Path
from typing import Dict, Any, List
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools.csv_analyzer import CSVSchemaDetector, CSVParser


class CSVParserAgent(BaseAgent):
    """
    Agent responsible for parsing CSV files with varied structures.
    """

    def __init__(self, api_key: str, config: Dict = None):
        super().__init__("CSVParser", config)
        self.detector = CSVSchemaDetector(api_key)
        self.detected_mapping = None
        self.parsed_records = []

    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context: Read CSV file and detect schema.

        Args:
            input_data: Path to CSV file (str or Path)

        Returns:
            Context with file info and detected schema
        """
        file_path = Path(input_data)

        if not file_path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        # Detect schema
        try:
            mapping, df = self.detector.analyze_csv(file_path)

            return {
                'file_path': str(file_path),
                'column_mapping': mapping,
                'dataframe': df,
                'row_count': len(df)
            }

        except Exception as e:
            raise ValueError(f"Failed to analyze CSV: {e}")

    def take_action(self, context: Dict) -> Any:
        """
        Take action: Parse CSV using detected mapping.

        Args:
            context: Context from gather_context

        Returns:
            List of parsed antibody records
        """
        mapping = context['column_mapping']
        df = context['dataframe']

        self.detected_mapping = mapping

        # Parse records
        parser = CSVParser(mapping)
        records = parser.parse(df)

        self.parsed_records = records

        return {
            'records': records,
            'count': len(records),
            'mapping': mapping.to_dict()
        }

    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work: Check if parsing was successful.

        Args:
            result: Parse result
            context: Original context

        Returns:
            Tuple of (success, errors)
        """
        errors = []

        # Check record count matches
        if result['count'] != context['row_count']:
            errors.append(
                f"Record count mismatch: parsed {result['count']}, expected {context['row_count']}"
            )

        # Check that at least marker_name is mapped
        if not result['mapping']['marker_name']:
            errors.append("Critical: marker_name column not detected")

        # Check for completely empty records
        empty_count = sum(1 for rec in result['records'] if not rec.get('marker_name'))
        if empty_count > len(result['records']) * 0.5:
            errors.append(f"Too many empty records: {empty_count}/{len(result['records'])}")

        return (len(errors) == 0, errors)


# Convenience function
def parse_antibody_csv(file_path: Path, api_key: str) -> Dict:
    """
    Parse antibody CSV file using agent.

    Args:
        file_path: Path to CSV file
        api_key: Anthropic API key

    Returns:
        Agent result dictionary
    """
    agent = CSVParserAgent(api_key)
    result = agent.execute(file_path)
    return result.to_dict()
