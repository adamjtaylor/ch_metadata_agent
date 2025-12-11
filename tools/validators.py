"""
Validation Suite for antibody metadata quality checks.
Implements rules-based validation and LLM-as-judge for semantic checks.
"""

import re
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

from anthropic import Anthropic


class ValidationLevel(Enum):
    """Severity levels for validation issues."""
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationIssue:
    """Represents a validation issue."""
    level: ValidationLevel
    field: str
    message: str
    suggestion: Optional[str] = None

    def __str__(self) -> str:
        msg = f"[{self.level.value.upper()}] {self.field}: {self.message}"
        if self.suggestion:
            msg += f" → Suggestion: {self.suggestion}"
        return msg


class AntibodyRecordValidator:
    """
    Validates antibody metadata records using rules-based checks.
    """

    # UniProt accession pattern: 1-2 letters + 5 digits or letters + digits (6-10 chars)
    UNIPROT_PATTERN = re.compile(r'^[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9]([A-Z][A-Z0-9]{2}[0-9]){1,2}$')

    def __init__(self):
        self.issues: List[ValidationIssue] = []

    def validate(self, record: Dict) -> List[ValidationIssue]:
        """
        Validate a single antibody record.

        Args:
            record: Dictionary with antibody metadata

        Returns:
            List of validation issues
        """
        self.issues = []

        # Required field checks
        self._check_required_fields(record)

        # Format validation
        self._validate_uniprot_id(record.get('target_id'))
        self._validate_marker_name(record.get('marker_name'))

        # Semantic validation
        self._check_marker_target_consistency(record)

        # Data completeness
        self._check_completeness(record)

        return self.issues

    def _check_required_fields(self, record: Dict):
        """Check if required fields are present and non-empty."""
        required = ['marker_name']

        for field in required:
            value = record.get(field)
            if not value or (isinstance(value, str) and not value.strip()):
                self.issues.append(ValidationIssue(
                    level=ValidationLevel.ERROR,
                    field=field,
                    message=f"Required field '{field}' is missing or empty"
                ))

    def _validate_uniprot_id(self, uniprot_id: Optional[str]):
        """Validate UniProt accession format."""
        if not uniprot_id or not isinstance(uniprot_id, str):
            return

        uniprot_id = uniprot_id.strip()

        if not self.UNIPROT_PATTERN.match(uniprot_id):
            self.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                field='target_id',
                message=f"UniProt ID '{uniprot_id}' doesn't match expected format",
                suggestion="Verify this is a valid UniProt accession"
            ))

    def _validate_marker_name(self, marker_name: Optional[str]):
        """Validate marker name format."""
        if not marker_name or not isinstance(marker_name, str):
            return

        marker_name = marker_name.strip()

        # Check for suspicious patterns
        if len(marker_name) < 2:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                field='marker_name',
                message=f"Marker name '{marker_name}' seems too short"
            ))

        # Check for common issues
        if marker_name.lower() in ['na', 'n/a', 'none', 'null', 'unknown']:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.ERROR,
                field='marker_name',
                message=f"Marker name '{marker_name}' is a placeholder value"
            ))

    def _check_marker_target_consistency(self, record: Dict):
        """Check if marker name and target name are consistent."""
        marker_raw = record.get('marker_name') or ''
        target_raw = record.get('target_name') or ''
        marker = marker_raw.strip().lower() if isinstance(marker_raw, str) else ''
        target = target_raw.strip().lower() if isinstance(target_raw, str) else ''

        if marker and target:
            # Simple heuristic: they should have some overlap
            # (e.g., "CD3" marker should target "CD3" protein)
            # This is a basic check; LLM validator will do deeper analysis

            # Extract alphanumeric core
            marker_core = re.sub(r'[^a-z0-9]', '', marker)
            target_core = re.sub(r'[^a-z0-9]', '', target)

            if len(marker_core) > 2 and len(target_core) > 2:
                if marker_core not in target_core and target_core not in marker_core:
                    # Flag for LLM review
                    self.issues.append(ValidationIssue(
                        level=ValidationLevel.INFO,
                        field='marker_name, target_name',
                        message=f"Marker '{marker}' and target '{target}' may be inconsistent",
                        suggestion="Review if this marker truly targets this protein"
                    ))

    def _check_completeness(self, record: Dict):
        """Check data completeness score."""
        important_fields = [
            'target_name', 'target_id', 'clone_id',
            'vendor', 'functional_categories'
        ]

        missing = []
        for field in important_fields:
            value = record.get(field)
            if not value or (isinstance(value, list) and len(value) == 0):
                missing.append(field)

        if len(missing) > len(important_fields) * 0.6:
            self.issues.append(ValidationIssue(
                level=ValidationLevel.WARNING,
                field='completeness',
                message=f"Record is missing many fields: {', '.join(missing)}",
                suggestion="Consider enriching this record with additional metadata"
            ))


class SemanticValidator:
    """
    Uses LLM to validate semantic consistency of antibody records.
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize with Anthropic API key.

        Args:
            api_key: Anthropic API key
        """
        self.client = Anthropic(api_key=api_key) if api_key else None

    def validate_semantic_consistency(self, record: Dict) -> List[ValidationIssue]:
        """
        Use LLM to check semantic consistency.

        Args:
            record: Antibody record dictionary

        Returns:
            List of validation issues
        """
        if not self.client:
            return []

        marker = record.get('marker_name', 'Unknown')
        target = record.get('target_name', 'Unknown')
        function = record.get('protein_function', 'Unknown')
        categories = record.get('functional_categories', [])

        prompt = f"""You are validating antibody metadata for a multiplexed tissue imaging experiment.

Review this record for semantic consistency:

Marker: {marker}
Target: {target}
Function: {function}
Categories: {', '.join(str(c) for c in categories if c) if categories else 'None'}

Check for:
1. Does the marker name match the target protein?
2. Is the protein function consistent with the assigned categories?
3. Are there any obvious errors or inconsistencies?

If everything looks consistent, return: {{"status": "valid", "issues": []}}

If there are issues, return:
{{
  "status": "invalid",
  "issues": [
    {{"field": "field_name", "message": "description", "level": "warning/error"}}
  ]
}}

Return ONLY the JSON object."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=512,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = response.content[0].text.strip()

            # Parse JSON
            import json
            if response_text.startswith("```"):
                response_text = response_text.split("```")[1]
                if response_text.startswith("json"):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Convert to ValidationIssue objects
            issues = []
            for issue in result.get('issues', []):
                level_str = issue.get('level', 'warning')
                level = ValidationLevel.WARNING if level_str == 'warning' else ValidationLevel.ERROR

                issues.append(ValidationIssue(
                    level=level,
                    field=issue.get('field', 'unknown'),
                    message=issue.get('message', 'Semantic inconsistency detected')
                ))

            return issues

        except Exception as e:
            print(f"Semantic validation error: {e}")
            return []


class ValidationSuite:
    """
    Complete validation suite combining rules-based and semantic validation.
    """

    def __init__(self, api_key: Optional[str] = None, use_llm: bool = True):
        """
        Initialize validation suite.

        Args:
            api_key: Anthropic API key for semantic validation
            use_llm: Whether to use LLM for semantic checks
        """
        self.rules_validator = AntibodyRecordValidator()
        self.semantic_validator = SemanticValidator(api_key) if use_llm else None

    def validate_record(self, record: Dict, use_semantic: bool = True) -> List[ValidationIssue]:
        """
        Validate a single record.

        Args:
            record: Antibody metadata record
            use_semantic: Whether to run semantic validation

        Returns:
            List of all validation issues
        """
        issues = []

        # Rules-based validation
        issues.extend(self.rules_validator.validate(record))

        # Semantic validation (if enabled and no critical errors)
        if use_semantic and self.semantic_validator:
            has_errors = any(issue.level == ValidationLevel.ERROR for issue in issues)
            if not has_errors:
                issues.extend(self.semantic_validator.validate_semantic_consistency(record))

        return issues

    def validate_batch(
        self,
        records: List[Dict],
        use_semantic: bool = True
    ) -> Dict[int, List[ValidationIssue]]:
        """
        Validate multiple records.

        Args:
            records: List of antibody records
            use_semantic: Whether to use semantic validation

        Returns:
            Dictionary mapping record index to validation issues
        """
        results = {}

        for idx, record in enumerate(records):
            issues = self.validate_record(record, use_semantic)
            if issues:
                results[idx] = issues

        return results

    def generate_report(
        self,
        validation_results: Dict[int, List[ValidationIssue]]
    ) -> str:
        """
        Generate human-readable validation report.

        Args:
            validation_results: Results from validate_batch

        Returns:
            Formatted report string
        """
        if not validation_results:
            return "✓ All records passed validation"

        lines = ["Validation Report", "=" * 50, ""]

        error_count = 0
        warning_count = 0

        for idx, issues in sorted(validation_results.items()):
            lines.append(f"Record #{idx}:")

            for issue in issues:
                lines.append(f"  {issue}")

                if issue.level == ValidationLevel.ERROR:
                    error_count += 1
                elif issue.level == ValidationLevel.WARNING:
                    warning_count += 1

            lines.append("")

        lines.append("=" * 50)
        lines.append(f"Summary: {error_count} errors, {warning_count} warnings")

        return "\n".join(lines)


def validate_antibody_records(
    records: List[Dict],
    api_key: Optional[str] = None,
    use_semantic: bool = True
) -> Tuple[Dict[int, List[ValidationIssue]], str]:
    """
    Convenience function to validate antibody records.

    Args:
        records: List of antibody metadata records
        api_key: Anthropic API key
        use_semantic: Whether to use LLM semantic validation

    Returns:
        Tuple of (validation results dict, report string)
    """
    suite = ValidationSuite(api_key, use_llm=use_semantic)
    results = suite.validate_batch(records, use_semantic)
    report = suite.generate_report(results)

    return results, report
