"""
Harmonization Agent: Reconciles duplicates and standardizes nomenclature.
"""

from pathlib import Path
from typing import Dict, Any, List, Set
import sys
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent


class HarmonizationAgent(BaseAgent):
    """
    Agent responsible for harmonizing antibody records.
    Handles duplicates, standardizes names, resolves conflicts.
    """

    def __init__(self, config: Dict = None, skip_deduplication: bool = False):
        super().__init__("Harmonization", config)
        self.skip_deduplication = skip_deduplication

    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context: Identify potential duplicates and conflicts.

        Args:
            input_data: List of classified antibody records

        Returns:
            Context with duplicate groups
        """
        records = input_data

        # Group by marker name (case-insensitive)
        marker_groups = defaultdict(list)

        for idx, record in enumerate(records):
            marker_name = record.get('marker_name') or ''
            marker = marker_name.strip().lower() if marker_name else ''
            if marker:
                marker_groups[marker].append((idx, record))

        # Identify duplicates
        duplicates = {k: v for k, v in marker_groups.items() if len(v) > 1}

        return {
            'records': records,
            'marker_groups': marker_groups,
            'duplicate_groups': duplicates,
            'duplicate_count': sum(len(v) for v in duplicates.values())
        }

    def take_action(self, context: Dict) -> Any:
        """
        Take action: Harmonize records.

        Args:
            context: Context from gather_context

        Returns:
            Harmonized records
        """
        records = context['records']
        duplicate_groups = context['duplicate_groups']

        harmonized = []
        merged_indices = set()

        if self.skip_deduplication:
            # Simplified mode: just standardize names, don't merge duplicates
            for record in records:
                standardized = self._standardize_record(record)
                harmonized.append(standardized)
        else:
            # Full mode: merge duplicates
            # Process duplicates
            for marker, group in duplicate_groups.items():
                if len(group) <= 1:
                    continue

                # Merge duplicates
                merged = self._merge_duplicates([rec for idx, rec in group])

                # Add merged record
                harmonized.append(merged)

                # Track merged indices
                for idx, _ in group:
                    merged_indices.add(idx)

            # Add non-duplicate records
            for idx, record in enumerate(records):
                if idx not in merged_indices:
                    # Standardize this record
                    standardized = self._standardize_record(record)
                    harmonized.append(standardized)

        return {
            'records': harmonized,
            'original_count': len(records),
            'harmonized_count': len(harmonized),
            'merged_count': len(records) - len(harmonized)
        }

    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work: Check harmonization results.

        Args:
            result: Harmonization result
            context: Original context

        Returns:
            Tuple of (success, errors)
        """
        errors = []

        # Check that we didn't lose too many records
        original = result['original_count']
        harmonized = result['harmonized_count']

        loss_rate = (original - harmonized) / original if original > 0 else 0

        if loss_rate > 0.5:
            errors.append(
                f"High record loss during harmonization: {loss_rate:.1%}"
            )

        return (len(errors) == 0, errors)

    def _merge_duplicates(self, records: List[Dict]) -> Dict:
        """
        Merge duplicate records, keeping best information.

        Args:
            records: List of duplicate records

        Returns:
            Merged record
        """
        if len(records) == 1:
            return records[0]

        # Start with first record
        merged = records[0].copy()

        # Merge fields, preferring non-null values
        for record in records[1:]:
            for key, value in record.items():
                # Skip if value is None or empty
                if value is None or (isinstance(value, str) and not value.strip()):
                    continue

                # If merged doesn't have this field, add it
                if key not in merged or not merged[key]:
                    merged[key] = value

                # For lists, combine and deduplicate
                elif isinstance(value, list) and isinstance(merged[key], list):
                    merged[key] = list(set(merged[key] + value))

                # For UniProt confidence, keep highest
                elif key == 'uniprot_confidence':
                    merged[key] = max(merged[key], value)

        return merged

    def _standardize_record(self, record: Dict) -> Dict:
        """
        Standardize a single record.

        Args:
            record: Antibody record

        Returns:
            Standardized record
        """
        standardized = record.copy()

        # Standardize marker name capitalization
        marker_name = standardized.get('marker_name')
        if marker_name and isinstance(marker_name, str):
            marker = marker_name.strip()

            # Common patterns
            # CD markers: CD3 not Cd3
            if marker.lower().startswith('cd'):
                parts = marker.lower().split()
                if parts[0].startswith('cd'):
                    cd_part = 'CD' + parts[0][2:]
                    standardized['marker_name'] = cd_part + ' ' + ' '.join(parts[1:]) if len(parts) > 1 else cd_part

            # Ki67, Ki-67
            if 'ki' in marker.lower() and '67' in marker:
                standardized['marker_name'] = 'Ki67'

        return standardized


def harmonize_antibody_records(records: List[Dict]) -> Dict:
    """
    Harmonize antibody records.

    Args:
        records: List of antibody records

    Returns:
        Agent result dictionary
    """
    agent = HarmonizationAgent()
    result = agent.execute(records)
    return result.to_dict()
