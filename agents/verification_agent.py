"""
Verification Agent: Validates curated data quality.
"""

from pathlib import Path
from typing import Dict, Any, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools.validators import ValidationSuite, ValidationLevel


class VerificationAgent(BaseAgent):
    """
    Agent responsible for validating curated antibody data.
    """

    def __init__(self, api_key: str = None, use_llm: bool = True, config: Dict = None):
        super().__init__("Verification", config)
        self.validator = ValidationSuite(api_key, use_llm)

    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context: Prepare records for validation.

        Args:
            input_data: List of harmonized antibody records

        Returns:
            Context with records
        """
        records = input_data

        return {
            'records': records,
            'total_count': len(records)
        }

    def take_action(self, context: Dict) -> Any:
        """
        Take action: Validate all records.

        Args:
            context: Context from gather_context

        Returns:
            Validation results and report
        """
        records = context['records']

        print(f"Validating {len(records)} records...")

        # Validate records
        validation_results = self.validator.validate_batch(records, use_semantic=True)

        # Generate report
        report = self.validator.generate_report(validation_results)

        # Separate records by validation status
        validated_records = []
        flagged_records = []

        for idx, record in enumerate(records):
            record_copy = record.copy()

            if idx in validation_results:
                issues = validation_results[idx]

                # Add validation info to record
                record_copy['validation_issues'] = [str(issue) for issue in issues]
                record_copy['has_errors'] = any(
                    issue.level == ValidationLevel.ERROR for issue in issues
                )
                record_copy['has_warnings'] = any(
                    issue.level == ValidationLevel.WARNING for issue in issues
                )

                # If has errors, flag for review
                if record_copy['has_errors']:
                    flagged_records.append(record_copy)
                else:
                    validated_records.append(record_copy)
            else:
                # No issues, record is clean
                record_copy['validation_issues'] = []
                record_copy['has_errors'] = False
                record_copy['has_warnings'] = False
                validated_records.append(record_copy)

        return {
            'validated_records': validated_records,
            'flagged_records': flagged_records,
            'validation_report': report,
            'total_count': len(records),
            'validated_count': len(validated_records),
            'flagged_count': len(flagged_records)
        }

    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work: Check validation results.

        Args:
            result: Validation result
            context: Original context

        Returns:
            Tuple of (success, errors)
        """
        errors = []

        flagged_count = result['flagged_count']
        total_count = result['total_count']

        flagged_rate = flagged_count / total_count if total_count > 0 else 0

        # Warning if too many flagged records
        if flagged_rate > 0.3:
            errors.append(
                f"High flagged record rate: {flagged_rate:.1%} ({flagged_count}/{total_count})"
            )

        # Always succeed - flagged records just need review
        return (True, errors)


def verify_antibody_records(
    records: List[Dict],
    api_key: str = None,
    use_llm: bool = True
) -> Dict:
    """
    Verify antibody records.

    Args:
        records: List of antibody records
        api_key: Anthropic API key for semantic validation
        use_llm: Whether to use LLM validation

    Returns:
        Agent result dictionary
    """
    agent = VerificationAgent(api_key, use_llm)
    result = agent.execute(records)
    return result.to_dict()
