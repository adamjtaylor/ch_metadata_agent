"""
UniProt Lookup Agent: Enriches records with UniProt protein information.
"""

from pathlib import Path
from typing import Dict, Any, List
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.base_agent import BaseAgent
from tools.uniprot_api import UniProtAPI, UniProtEntry


class UniProtLookupAgent(BaseAgent):
    """
    Agent responsible for looking up protein information from UniProt.
    """

    def __init__(self, cache_dir: Path = Path("data/cache"), config: Dict = None):
        super().__init__("UniProtLookup", config)
        self.api = UniProtAPI(cache_dir)
        self.enriched_records = []

    def gather_context(self, input_data: Any) -> Dict:
        """
        Gather context: Extract targets to look up.

        Args:
            input_data: List of antibody records

        Returns:
            Context with unique targets
        """
        records = input_data

        # Extract unique targets (marker names and target names)
        targets = set()

        for record in records:
            if record.get('marker_name'):
                targets.add(record['marker_name'])
            if record.get('target_name'):
                targets.add(record['target_name'])

        return {
            'records': records,
            'targets': list(targets),
            'total_records': len(records)
        }

    def take_action(self, context: Dict) -> Any:
        """
        Take action: Look up UniProt information for each target.

        Args:
            context: Context from gather_context

        Returns:
            Enriched records
        """
        records = context['records']
        targets = context['targets']

        # Print unique targets list
        print(f"\nUnique targets to look up ({len(targets)}):")
        for i, target in enumerate(sorted(targets), 1):
            print(f"  {i}. {target}")
        print()

        # Batch lookup
        print(f"Looking up {len(targets)} unique targets in UniProt...")
        lookup_results = self.api.batch_search(targets, organism="human")

        # Enrich records
        enriched = []
        for record in records:
            enriched_record = record.copy()

            # Try lookup by marker name first, then target name
            marker = record.get('marker_name', '')
            target = record.get('target_name', '')

            uniprot_entry = None

            # First try exact match on marker
            if marker and marker in lookup_results and lookup_results[marker]:
                uniprot_entry = lookup_results[marker][0]  # Best match

            # Then try target name
            elif target and target in lookup_results and lookup_results[target]:
                uniprot_entry = lookup_results[target][0]

            # Enrich if found
            if uniprot_entry:
                enriched_record['target_id'] = uniprot_entry.accession
                enriched_record['target_name'] = uniprot_entry.gene_name or record.get('target_name')
                enriched_record['protein_name'] = uniprot_entry.protein_name
                enriched_record['organism'] = uniprot_entry.organism
                enriched_record['subcellular_location'] = uniprot_entry.subcellular_location
                enriched_record['protein_function'] = uniprot_entry.function
                enriched_record['uniprot_confidence'] = uniprot_entry.confidence_score
            else:
                enriched_record['target_id'] = None
                enriched_record['uniprot_confidence'] = 0.0

            enriched.append(enriched_record)

        self.enriched_records = enriched

        return {
            'records': enriched,
            'enriched_count': sum(1 for r in enriched if r.get('target_id')),
            'total_count': len(enriched)
        }

    def verify_work(self, result: Any, context: Dict) -> tuple[bool, List[str]]:
        """
        Verify work: Check enrichment success rate.

        Args:
            result: Enrichment result
            context: Original context

        Returns:
            Tuple of (success, errors)
        """
        errors = []

        enriched_count = result['enriched_count']
        total_count = result['total_count']

        enrichment_rate = enriched_count / total_count if total_count > 0 else 0

        # Warning if enrichment rate is low
        if enrichment_rate < 0.5:
            errors.append(
                f"Low enrichment rate: {enrichment_rate:.1%} ({enriched_count}/{total_count}) records enriched"
            )

        # Always succeed (enrichment failures are expected for some markers)
        # Just return warnings
        return (True, errors)


def enrich_with_uniprot(records: List[Dict], cache_dir: Path = Path("data/cache")) -> Dict:
    """
    Enrich antibody records with UniProt data.

    Args:
        records: List of antibody records
        cache_dir: Cache directory

    Returns:
        Agent result dictionary
    """
    agent = UniProtLookupAgent(cache_dir)
    result = agent.execute(records)
    return result.to_dict()
