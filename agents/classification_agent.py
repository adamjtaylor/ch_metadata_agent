"""
Functional Classification Agent: Assigns functional categories to markers.
"""

from pathlib import Path
from typing import Dict, Any, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools.classifier import FunctionalClassifier, FunctionalTaxonomy


class ClassificationAgent(BaseAgent):
    """
    Agent responsible for classifying markers into functional categories.
    """

    def __init__(self, api_key: str, config_path: Path = None, config: Dict = None):
        super().__init__("Classification", config)

        taxonomy = FunctionalTaxonomy(config_path) if config_path else None
        self.classifier = FunctionalClassifier(taxonomy, api_key)

    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context: Prepare records for classification.

        Args:
            input_data: List of enriched antibody records

        Returns:
            Context with records ready for classification
        """
        records = input_data

        return {
            'records': records,
            'total_count': len(records)
        }

    def take_action(self, context: Dict) -> Any:
        """
        Take action: Classify each record.

        Args:
            context: Context from gather_context

        Returns:
            Records with functional categories
        """
        records = context['records']

        classified_records = []

        print(f"Classifying {len(records)} markers...")

        for record in records:
            classified_record = record.copy()

            # Classify
            marker_name = record.get('marker_name') or ''
            categories = self.classifier.classify(
                marker_name=marker_name,
                target_name=record.get('target_name'),
                protein_function=record.get('protein_function'),
                subcellular_location=record.get('subcellular_location')
            )

            classified_record['functional_categories'] = categories
            classified_record['category_names'] = self.classifier.get_category_names(categories)

            classified_records.append(classified_record)

        return {
            'records': classified_records,
            'classified_count': sum(1 for r in classified_records if r['functional_categories']),
            'total_count': len(classified_records)
        }

    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work: Check classification coverage.

        Args:
            result: Classification result
            context: Original context

        Returns:
            Tuple of (success, errors)
        """
        errors = []

        classified_count = result['classified_count']
        total_count = result['total_count']

        classification_rate = classified_count / total_count if total_count > 0 else 0

        # Warning if too many unclassified
        if classification_rate < 0.7:
            errors.append(
                f"Low classification rate: {classification_rate:.1%} ({classified_count}/{total_count})"
            )

        # Always succeed, just return warnings
        return (True, errors)


def classify_antibody_records(
    records: List[Dict],
    api_key: str,
    config_path: Path = None
) -> Dict:
    """
    Classify antibody records into functional categories.

    Args:
        records: List of antibody records
        api_key: Anthropic API key
        config_path: Optional path to taxonomy config

    Returns:
        Agent result dictionary
    """
    agent = ClassificationAgent(api_key, config_path)
    result = agent.execute(records)
    return result.to_dict()
