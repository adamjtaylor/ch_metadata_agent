"""
Orchestrator: Main controller for the antibody curation agent system.
Coordinates all sub-agents through the workflow pipeline.
"""

import json
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum

from agents.csv_parser_agent import CSVParserAgent
from agents.uniprot_agent import UniProtLookupAgent
from agents.classification_agent import ClassificationAgent
from agents.harmonization_agent import HarmonizationAgent
from agents.verification_agent import VerificationAgent


class WorkflowStatus(Enum):
    """Status of the workflow execution."""
    PENDING = "pending"
    PARSING = "parsing"
    ENRICHING = "enriching"
    CLASSIFYING = "classifying"
    HARMONIZING = "harmonizing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class WorkflowResult:
    """Result from workflow execution."""
    status: WorkflowStatus
    curated_records: List[Dict]
    flagged_records: List[Dict]
    validation_report: str
    statistics: Dict
    errors: List[str]

    def to_dict(self) -> Dict:
        return {
            'status': self.status.value,
            'curated_records': self.curated_records,
            'flagged_records': self.flagged_records,
            'validation_report': self.validation_report,
            'statistics': self.statistics,
            'errors': self.errors
        }


class StateManager:
    """
    Manages workflow state and checkpointing using SQLite.
    """

    def __init__(self, state_dir: Path = Path("data/state")):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = state_dir / "workflow_state.db"
        self._init_db()

    def _init_db(self):
        """Initialize state database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_runs (
                    run_id TEXT PRIMARY KEY,
                    start_time TEXT NOT NULL,
                    end_time TEXT,
                    status TEXT NOT NULL,
                    input_file TEXT NOT NULL,
                    current_stage TEXT,
                    metadata TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS workflow_checkpoints (
                    run_id TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    data TEXT NOT NULL,
                    PRIMARY KEY (run_id, stage)
                )
            """)
            conn.commit()

    def create_run(self, run_id: str, input_file: str) -> None:
        """Create a new workflow run."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT INTO workflow_runs (run_id, start_time, status, input_file, current_stage)
                VALUES (?, ?, ?, ?, ?)
                """,
                (run_id, datetime.now().isoformat(), WorkflowStatus.PENDING.value, input_file, "init")
            )
            conn.commit()

    def update_run_status(self, run_id: str, status: WorkflowStatus, stage: str) -> None:
        """Update workflow run status."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                UPDATE workflow_runs
                SET status = ?, current_stage = ?
                WHERE run_id = ?
                """,
                (status.value, stage, run_id)
            )
            conn.commit()

    def save_checkpoint(self, run_id: str, stage: str, data: Dict) -> None:
        """Save checkpoint data."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO workflow_checkpoints (run_id, stage, timestamp, data)
                VALUES (?, ?, ?, ?)
                """,
                (run_id, stage, datetime.now().isoformat(), json.dumps(data))
            )
            conn.commit()

    def load_checkpoint(self, run_id: str, stage: str) -> Optional[Dict]:
        """Load checkpoint data."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT data FROM workflow_checkpoints WHERE run_id = ? AND stage = ?",
                (run_id, stage)
            )
            row = cursor.fetchone()

            if row:
                return json.loads(row[0])

        return None


class AntibodyCurationOrchestrator:
    """
    Main orchestrator that coordinates all agents through the curation workflow.
    """

    def __init__(
        self,
        api_key: str,
        cache_dir: Path = Path("data/cache"),
        state_dir: Path = Path("data/state"),
        output_dir: Path = Path("data/output"),
        config_path: Optional[Path] = None
    ):
        """
        Initialize orchestrator.

        Args:
            api_key: Anthropic API key
            cache_dir: Cache directory for UniProt lookups
            state_dir: State directory for checkpointing
            output_dir: Output directory for results
            config_path: Optional taxonomy config path
        """
        self.api_key = api_key
        self.cache_dir = cache_dir
        self.state_dir = state_dir
        self.output_dir = output_dir
        self.config_path = config_path

        # Create directories
        cache_dir.mkdir(parents=True, exist_ok=True)
        state_dir.mkdir(parents=True, exist_ok=True)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state manager
        self.state_manager = StateManager(state_dir)

        # Initialize agents (lazy initialization)
        self._csv_parser = None
        self._uniprot_agent = None
        self._classification_agent = None
        self._harmonization_agent = None
        self._verification_agent = None

    def curate_antibody_csv(
        self,
        csv_file: Path,
        run_id: Optional[str] = None,
        resume: bool = False,
        simplified_output: bool = False
    ) -> WorkflowResult:
        """
        Execute full curation workflow on antibody CSV file.

        Args:
            csv_file: Path to CSV file
            run_id: Optional run ID (auto-generated if None)
            resume: Whether to resume from checkpoint
            simplified_output: If True, outputs simplified 1:1 CSV and skips deduplication

        Returns:
            WorkflowResult with curated data
        """
        # Generate run ID if not provided
        if run_id is None:
            run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

        # Create or resume run
        if not resume:
            self.state_manager.create_run(run_id, str(csv_file))

        errors = []
        current_stage = "init"

        try:
            # Stage 1: Parse CSV
            print("\n=== Stage 1: Parsing CSV ===")
            current_stage = "parsing"
            self.state_manager.update_run_status(run_id, WorkflowStatus.PARSING, current_stage)

            if resume:
                checkpoint = self.state_manager.load_checkpoint(run_id, current_stage)
                if checkpoint:
                    print("Resuming from checkpoint...")
                    parsed_records = checkpoint['records']
                else:
                    parsed_records = self._parse_csv(csv_file)
            else:
                parsed_records = self._parse_csv(csv_file)

            self.state_manager.save_checkpoint(run_id, current_stage, {'records': parsed_records})
            print(f"✓ Parsed {len(parsed_records)} records")

            # Stage 2: UniProt Enrichment
            print("\n=== Stage 2: UniProt Enrichment ===")
            current_stage = "enriching"
            self.state_manager.update_run_status(run_id, WorkflowStatus.ENRICHING, current_stage)

            enriched_records = self._enrich_with_uniprot(parsed_records)
            self.state_manager.save_checkpoint(run_id, current_stage, {'records': enriched_records})

            enriched_count = sum(1 for r in enriched_records if r.get('target_id'))
            print(f"✓ Enriched {enriched_count}/{len(enriched_records)} records with UniProt data")

            # Stage 3: Functional Classification
            print("\n=== Stage 3: Functional Classification ===")
            current_stage = "classifying"
            self.state_manager.update_run_status(run_id, WorkflowStatus.CLASSIFYING, current_stage)

            classified_records = self._classify_markers(enriched_records)
            self.state_manager.save_checkpoint(run_id, current_stage, {'records': classified_records})

            classified_count = sum(1 for r in classified_records if r.get('functional_categories'))
            print(f"✓ Classified {classified_count}/{len(classified_records)} records")

            # Stage 4: Harmonization
            print("\n=== Stage 4: Harmonization ===")
            current_stage = "harmonizing"
            self.state_manager.update_run_status(run_id, WorkflowStatus.HARMONIZING, current_stage)

            harmonized_records = self._harmonize_records(classified_records, skip_deduplication=simplified_output)
            self.state_manager.save_checkpoint(run_id, current_stage, {'records': harmonized_records})

            if simplified_output:
                print(f"✓ Standardized {len(harmonized_records)} records (deduplication skipped)")
            else:
                print(f"✓ Harmonized to {len(harmonized_records)} unique records")

            # Stage 5: Verification
            print("\n=== Stage 5: Verification ===")
            current_stage = "verifying"
            self.state_manager.update_run_status(run_id, WorkflowStatus.VERIFYING, current_stage)

            validation_result = self._verify_records(harmonized_records)

            validated_records = validation_result['validated_records']
            flagged_records = validation_result['flagged_records']
            report = validation_result['validation_report']

            print(f"✓ Validated: {len(validated_records)} records passed, {len(flagged_records)} flagged for review")

            # Save outputs
            if simplified_output:
                # Combine all records for simplified output (validated + flagged)
                all_records = validated_records + flagged_records
                self._save_simplified_output(run_id, all_records)
                print(f"\n✓ Simplified output saved to: {self.output_dir / run_id / 'curated_simple.csv'}")
            else:
                self._save_outputs(run_id, validated_records, flagged_records, report)

            # Calculate statistics
            statistics = self._calculate_statistics(
                parsed_records, enriched_records, classified_records,
                harmonized_records, validated_records, flagged_records
            )

            # Mark as completed
            self.state_manager.update_run_status(run_id, WorkflowStatus.COMPLETED, "completed")

            print("\n=== Workflow Completed Successfully ===")
            print(f"Run ID: {run_id}")
            print(f"Output: {self.output_dir / run_id}")

            return WorkflowResult(
                status=WorkflowStatus.COMPLETED,
                curated_records=validated_records,
                flagged_records=flagged_records,
                validation_report=report,
                statistics=statistics,
                errors=errors
            )

        except Exception as e:
            error_msg = f"Workflow failed at stage '{current_stage}': {str(e)}"
            errors.append(error_msg)
            print(f"\n✗ {error_msg}")

            self.state_manager.update_run_status(run_id, WorkflowStatus.FAILED, current_stage)

            return WorkflowResult(
                status=WorkflowStatus.FAILED,
                curated_records=[],
                flagged_records=[],
                validation_report="",
                statistics={},
                errors=errors
            )

    def _parse_csv(self, csv_file: Path) -> List[Dict]:
        """Parse CSV file."""
        if self._csv_parser is None:
            self._csv_parser = CSVParserAgent(self.api_key)

        result = self._csv_parser.execute(csv_file)

        if result.status.value == "failed":
            raise RuntimeError(f"CSV parsing failed: {result.errors}")

        return result.data['records']

    def _enrich_with_uniprot(self, records: List[Dict]) -> List[Dict]:
        """Enrich records with UniProt data."""
        if self._uniprot_agent is None:
            self._uniprot_agent = UniProtLookupAgent(self.cache_dir)

        result = self._uniprot_agent.execute(records)

        if result.status.value == "failed":
            raise RuntimeError(f"UniProt enrichment failed: {result.errors}")

        return result.data['records']

    def _classify_markers(self, records: List[Dict]) -> List[Dict]:
        """Classify markers into functional categories."""
        if self._classification_agent is None:
            self._classification_agent = ClassificationAgent(self.api_key, self.config_path)

        result = self._classification_agent.execute(records)

        if result.status.value == "failed":
            raise RuntimeError(f"Classification failed: {result.errors}")

        return result.data['records']

    def _harmonize_records(self, records: List[Dict], skip_deduplication: bool = False) -> List[Dict]:
        """Harmonize and deduplicate records."""
        if self._harmonization_agent is None:
            self._harmonization_agent = HarmonizationAgent(skip_deduplication=skip_deduplication)
        elif self._harmonization_agent.skip_deduplication != skip_deduplication:
            # Recreate agent if deduplication mode changed
            self._harmonization_agent = HarmonizationAgent(skip_deduplication=skip_deduplication)

        result = self._harmonization_agent.execute(records)

        if result.status.value == "failed":
            raise RuntimeError(f"Harmonization failed: {result.errors}")

        return result.data['records']

    def _verify_records(self, records: List[Dict]) -> Dict:
        """Verify and validate records."""
        if self._verification_agent is None:
            self._verification_agent = VerificationAgent(self.api_key, use_llm=True)

        result = self._verification_agent.execute(records)

        if result.status.value == "failed":
            raise RuntimeError(f"Verification failed: {result.errors}")

        return result.data

    def _save_outputs(
        self,
        run_id: str,
        validated_records: List[Dict],
        flagged_records: List[Dict],
        report: str
    ):
        """Save workflow outputs."""
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Save curated records
        import pandas as pd
        curated_df = pd.DataFrame(validated_records)
        curated_df.to_csv(run_dir / "curated_antibodies.csv", index=False)

        # Save flagged records
        if flagged_records:
            flagged_df = pd.DataFrame(flagged_records)
            flagged_df.to_csv(run_dir / "flagged_for_review.csv", index=False)

        # Save validation report
        with open(run_dir / "validation_report.txt", 'w') as f:
            f.write(report)

        # Save JSON
        with open(run_dir / "curated_antibodies.json", 'w') as f:
            json.dump(validated_records, f, indent=2)

    def _save_simplified_output(
        self,
        run_id: str,
        all_records: List[Dict]
    ):
        """
        Save simplified output with 1:1 input-output mapping.

        Creates a CSV with columns:
        - input_row: Original CSV row number
        - identified_target: Original marker name from CSV
        - harmonized_target: Standardized marker name
        - functional_categories: Comma-separated category names
        - uniprot_enriched: Boolean if UniProt data found
        - uniprot_id: UniProt accession or empty
        - validated: Boolean if passed validation
        - warnings: Comma-separated warnings or empty
        """
        run_dir = self.output_dir / run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        # Create simplified records
        simplified = []
        for record in all_records:
            # Extract warnings
            warnings_list = record.get('validation_issues', [])
            # Filter out ERROR level warnings for the warnings column
            warnings_str = '; '.join([
                w for w in warnings_list
                if isinstance(w, str) and 'ERROR' not in w
            ]) if warnings_list else ''

            # Extract functional categories
            categories_list = record.get('category_names', [])
            # Filter out None values and ensure all are strings
            valid_categories = [c for c in categories_list if c and isinstance(c, str)] if categories_list else []
            categories_str = ', '.join(valid_categories) if valid_categories else ''

            simplified_record = {
                'input_row': record.get('input_row_number', ''),
                'identified_target': record.get('identified_target_original', ''),
                'harmonized_target': record.get('marker_name', ''),
                'functional_categories': categories_str,
                'uniprot_enriched': bool(record.get('target_id')),
                'uniprot_id': record.get('target_id', ''),
                'validated': not record.get('has_errors', False),
                'warnings': warnings_str
            }
            simplified.append(simplified_record)

        # Sort by input row number to maintain order
        simplified.sort(key=lambda x: x['input_row'] if isinstance(x['input_row'], int) else 999999)

        # Save to CSV
        import pandas as pd
        df = pd.DataFrame(simplified)
        df.to_csv(run_dir / "curated_simple.csv", index=False)

        # Also save full JSON for reference
        with open(run_dir / "curated_full.json", 'w') as f:
            json.dump(all_records, f, indent=2)

    def _calculate_statistics(
        self,
        parsed: List[Dict],
        enriched: List[Dict],
        classified: List[Dict],
        harmonized: List[Dict],
        validated: List[Dict],
        flagged: List[Dict]
    ) -> Dict:
        """Calculate workflow statistics."""
        return {
            'input_records': len(parsed),
            'enriched_records': sum(1 for r in enriched if r.get('target_id')),
            'enrichment_rate': sum(1 for r in enriched if r.get('target_id')) / len(enriched) if enriched else 0,
            'classified_records': sum(1 for r in classified if r.get('functional_categories')),
            'classification_rate': sum(1 for r in classified if r.get('functional_categories')) / len(classified) if classified else 0,
            'harmonized_records': len(harmonized),
            'deduplication_count': len(classified) - len(harmonized),
            'validated_records': len(validated),
            'flagged_records': len(flagged),
            'success_rate': len(validated) / (len(validated) + len(flagged)) if (len(validated) + len(flagged)) > 0 else 0
        }
