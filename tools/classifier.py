"""
Functional Classification Tool for antibody markers.
Classifies markers into biological functional categories.
"""

from typing import List, Dict, Optional, Set
from dataclasses import dataclass
import yaml
from pathlib import Path

from anthropic import Anthropic


@dataclass
class FunctionalCategory:
    """Represents a functional category classification."""
    name: str
    description: str
    keywords: List[str]
    examples: List[str]


class FunctionalTaxonomy:
    """
    Manages the taxonomy of functional categories for antibody markers.
    """

    # Default taxonomy based on user requirements
    DEFAULT_CATEGORIES = {
        "immune_cell_typing": FunctionalCategory(
            name="Immune Cell Typing",
            description="Markers used to identify and classify immune cell types",
            keywords=["CD3", "CD4", "CD8", "CD20", "CD68", "lymphocyte", "T cell", "B cell", "macrophage"],
            examples=["CD3 (T cells)", "CD20 (B cells)", "CD68 (macrophages)"]
        ),
        "segmentation": FunctionalCategory(
            name="Segmentation",
            description="Markers used for cellular or tissue compartment segmentation",
            keywords=["pan-cytokeratin", "PanCK", "DAPI", "nucleus", "membrane", "cytoplasm"],
            examples=["Pan-Cytokeratin", "DAPI", "Beta-catenin"]
        ),
        "lymphocyte_profiling": FunctionalCategory(
            name="Lymphocyte Profiling",
            description="Markers specific to lymphocyte subtypes and states",
            keywords=["CD4", "CD8", "FOXP3", "CD25", "Granzyme", "T cell", "regulatory"],
            examples=["CD4", "CD8", "FOXP3 (Tregs)", "Granzyme B"]
        ),
        "myeloid_profiling": FunctionalCategory(
            name="Myeloid Profiling",
            description="Markers for myeloid cell identification and characterization",
            keywords=["CD68", "CD163", "CD11b", "CD11c", "myeloid", "macrophage", "dendritic"],
            examples=["CD68", "CD163", "CD11c"]
        ),
        "immune_activation": FunctionalCategory(
            name="Immune Activation",
            description="Markers indicating immune cell activation status",
            keywords=["HLA-DR", "CD69", "CD25", "activation", "MHC", "IFN"],
            examples=["HLA-DR", "CD69", "PD-1", "PD-L1"]
        ),
        "proliferation": FunctionalCategory(
            name="Proliferation",
            description="Markers of cell proliferation and cell cycle",
            keywords=["Ki67", "Ki-67", "PCNA", "proliferation", "cell cycle"],
            examples=["Ki67", "PCNA"]
        ),
        "tissue_architecture": FunctionalCategory(
            name="Tissue Architecture",
            description="Markers defining tissue structure and organization",
            keywords=["collagen", "SMA", "smooth muscle", "actin", "vimentin", "fibroblast", "stroma"],
            examples=["Smooth Muscle Actin", "Vimentin", "Collagen"]
        ),
        "hypoxia": FunctionalCategory(
            name="Hypoxia",
            description="Markers of hypoxic conditions in tissue",
            keywords=["HIF", "CA9", "CAIX", "hypoxia", "carbonic anhydrase"],
            examples=["CA9", "HIF1a"]
        ),
        "tumor_specific": FunctionalCategory(
            name="Tumor-Specific",
            description="Markers specific to tumor cells or tumor antigens",
            keywords=["tumor", "cancer", "carcinoma", "melanoma", "HER2", "EGFR"],
            examples=["HER2", "EGFR", "PSA"]
        ),
        "signaling": FunctionalCategory(
            name="Signaling",
            description="Markers related to cellular signaling pathways",
            keywords=["phospho", "pERK", "pAKT", "pSTAT", "signaling", "pathway"],
            examples=["pERK", "pAKT", "pSTAT3"]
        ),
        "cell_metabolism": FunctionalCategory(
            name="Cell Metabolism",
            description="Markers related to cellular metabolic processes",
            keywords=["metabolism", "GLUT", "glucose", "ATP", "mitochondrial"],
            examples=["GLUT1", "CPT1A"]
        )
    }

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize taxonomy from config file or use defaults.

        Args:
            config_path: Path to YAML configuration file
        """
        if config_path and config_path.exists():
            self.categories = self._load_from_config(config_path)
        else:
            self.categories = self.DEFAULT_CATEGORIES

    def _load_from_config(self, config_path: Path) -> Dict[str, FunctionalCategory]:
        """Load taxonomy from YAML config."""
        with open(config_path) as f:
            config = yaml.safe_load(f)

        categories = {}
        for key, data in config.get('categories', {}).items():
            categories[key] = FunctionalCategory(
                name=data['name'],
                description=data['description'],
                keywords=data.get('keywords', []),
                examples=data.get('examples', [])
            )

        return categories

    def get_category(self, key: str) -> Optional[FunctionalCategory]:
        """Get category by key."""
        return self.categories.get(key)

    def get_all_categories(self) -> Dict[str, FunctionalCategory]:
        """Get all categories."""
        return self.categories


class FunctionalClassifier:
    """
    Classifies antibody markers into functional categories using rules + LLM.
    """

    def __init__(
        self,
        taxonomy: Optional[FunctionalTaxonomy] = None,
        api_key: Optional[str] = None
    ):
        """
        Initialize classifier.

        Args:
            taxonomy: FunctionalTaxonomy instance (uses default if None)
            api_key: Anthropic API key for LLM classification
        """
        self.taxonomy = taxonomy or FunctionalTaxonomy()
        self.client = Anthropic(api_key=api_key) if api_key else None

    def classify(
        self,
        marker_name: str,
        target_name: Optional[str] = None,
        protein_function: Optional[str] = None,
        subcellular_location: Optional[List[str]] = None
    ) -> List[str]:
        """
        Classify marker into functional categories (multi-label).

        Args:
            marker_name: Marker/antibody name
            target_name: Target protein/gene name
            protein_function: Protein function description
            subcellular_location: Subcellular location(s)

        Returns:
            List of category keys that apply
        """
        # Handle empty marker name
        if not marker_name:
            return []

        # Try rule-based classification first
        categories = self._rule_based_classification(
            marker_name, target_name, subcellular_location
        )

        # If ambiguous or no matches, use LLM
        if len(categories) == 0 or self._is_ambiguous(marker_name):
            if self.client:
                llm_categories = self._llm_classification(
                    marker_name, target_name, protein_function, subcellular_location
                )
                categories.update(llm_categories)

        return sorted(list(categories))

    def _rule_based_classification(
        self,
        marker_name: str,
        target_name: Optional[str],
        subcellular_location: Optional[List[str]]
    ) -> Set[str]:
        """Rule-based classification using keyword matching."""
        categories = set()
        marker_lower = marker_name.lower() if marker_name else ""
        target_lower = target_name.lower() if target_name else ""

        # Check each category's keywords
        for key, category in self.taxonomy.get_all_categories().items():
            for keyword in category.keywords:
                if not keyword or not isinstance(keyword, str):
                    continue
                keyword_lower = keyword.lower()
                if keyword_lower in marker_lower or keyword_lower in target_lower:
                    categories.add(key)
                    break

        # Segmentation special case
        if subcellular_location:
            # Filter out None values and ensure all are strings
            valid_locations = [loc for loc in subcellular_location if loc and isinstance(loc, str)]
            if valid_locations:
                location_text = " ".join(valid_locations).lower()
                if any(loc in location_text for loc in ["nucleus", "membrane", "cytoplasm"]):
                    categories.add("segmentation")

        return categories

    def _is_ambiguous(self, marker_name: str) -> bool:
        """Check if marker might need LLM classification."""
        if not marker_name:
            return False
        # Markers with unclear names benefit from LLM
        ambiguous_patterns = ["protein", "antigen", "factor", "receptor"]
        marker_lower = marker_name.lower()
        return any(pattern in marker_lower for pattern in ambiguous_patterns)

    def _llm_classification(
        self,
        marker_name: str,
        target_name: Optional[str],
        protein_function: Optional[str],
        subcellular_location: Optional[List[str]]
    ) -> Set[str]:
        """Use LLM for classification when rules are insufficient."""
        if not self.client:
            return set()

        # Build context
        context = f"Marker: {marker_name or 'Unknown'}"
        if target_name:
            context += f"\nTarget: {target_name}"
        if protein_function:
            context += f"\nFunction: {protein_function}"
        if subcellular_location:
            # Filter out None values
            valid_locations = [loc for loc in subcellular_location if loc and isinstance(loc, str)]
            if valid_locations:
                context += f"\nLocation: {', '.join(valid_locations)}"

        # Build category descriptions
        category_desc = []
        for key, cat in self.taxonomy.get_all_categories().items():
            category_desc.append(f"- {key}: {cat.description}")

        prompt = f"""Classify this antibody marker into one or more functional categories for multiplexed tissue imaging.

{context}

Available categories:
{chr(10).join(category_desc)}

Return a JSON array of category keys that apply (can be multiple).
Only include categories that are clearly relevant based on the marker's known function.

Example: ["immune_cell_typing", "lymphocyte_profiling"]

Return ONLY the JSON array, no other text."""

        try:
            response = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",
                max_tokens=256,
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

            categories = json.loads(response_text)
            return set(categories)

        except Exception as e:
            print(f"LLM classification error: {e}")
            return set()

    def get_category_names(self, category_keys: List[str]) -> List[str]:
        """Convert category keys to human-readable names."""
        names = []
        for key in category_keys:
            cat = self.taxonomy.get_category(key)
            if cat:
                names.append(cat.name)
        return names


def classify_marker(
    marker_name: str,
    target_name: Optional[str] = None,
    protein_function: Optional[str] = None,
    subcellular_location: Optional[List[str]] = None,
    api_key: Optional[str] = None
) -> List[str]:
    """
    Convenience function to classify a marker.

    Args:
        marker_name: Marker/antibody name
        target_name: Target protein name
        protein_function: Protein function description
        subcellular_location: Subcellular locations
        api_key: Anthropic API key

    Returns:
        List of category keys
    """
    classifier = FunctionalClassifier(api_key=api_key)
    return classifier.classify(
        marker_name, target_name, protein_function, subcellular_location
    )
