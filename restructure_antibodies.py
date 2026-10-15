#!/usr/bin/env python3
"""
Script to restructure curated_antibodies_harmonized.json:
1. Use target_name as the primary key
2. Consolidate information for each target (keeping only curated info)
3. Populate panels_seen_in from htan_data directory files using simple string search
"""

import json
import os
import re
from pathlib import Path
from collections import defaultdict


def normalize_subcellular_location(locations):
    """
    Normalize subcellular locations to highest-level categories:
    - Cell membrane
    - Cytoplasm
    - Nucleus
    """
    if not locations:
        return []

    high_level = set()

    for loc in locations:
        loc_lower = loc.lower()

        # Nucleus
        if (
            "nucleus" in loc_lower
            or "nuclear" in loc_lower
            or "chromosome" in loc_lower
        ):
            high_level.add("Nucleus")
        # Cell membrane
        elif "membrane" in loc_lower or "cell surface" in loc_lower:
            high_level.add("Cell membrane")
        # Cytoplasm (includes organelles)
        elif (
            "cytoplasm" in loc_lower
            or "cytosol" in loc_lower
            or "cytoskeleton" in loc_lower
        ):
            high_level.add("Cytoplasm")
        # Organelles map to Cytoplasm
        elif any(
            org in loc_lower
            for org in [
                "mitochondrion",
                "endoplasmic reticulum",
                "golgi",
                "lysosome",
                "peroxisome",
                "ribosome",
                "vacuole",
                "vesicle",
            ]
        ):
            high_level.add("Cytoplasm")

    return sorted(list(high_level))


def read_json(filepath):
    """Read JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def write_json(filepath, data):
    """Write JSON file with nice formatting."""
    with open(filepath, "w") as f:
        json.dump(data, f, indent=2)


def search_marker_in_file(file_path, marker_name):
    """Search for marker name in file using simple string search."""
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
            # Case-insensitive search for the marker string
            if re.search(re.escape(marker_name), content, re.IGNORECASE):
                return True
        return False
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False


def find_panels_for_marker(marker_name, htan_data_dir):
    """Find all panel files that contain the given marker."""
    panels = []
    htan_path = Path(htan_data_dir)

    if not htan_path.exists():
        print(f"Warning: {htan_data_dir} does not exist")
        return panels

    for file_path in htan_path.iterdir():
        if not file_path.is_file():
            continue

        # Only process CSV and TXT files
        if file_path.suffix not in [".csv", ".txt"]:
            continue

        file_stem = file_path.stem  # filename without extension

        if search_marker_in_file(file_path, marker_name):
            panels.append(file_stem)

    return sorted(list(set(panels)))  # Remove duplicates and sort


def restructure_antibodies(input_json, htan_data_dir):
    """
    Restructure antibodies JSON with target_name as primary key.
    Only keeps curated target information, drops marker-specific details.
    """
    antibodies_data = read_json(input_json)

    # Group by target_name
    target_groups = defaultdict(
        lambda: {
            "target_name": None,
            "uniprot_id": None,
            "protein_name": None,
            "organism": None,
            "subcellular_location": None,
            "protein_function": None,
            "uniprot_confidence": None,
            "functional_categories": None,
            "category_names": None,
            "panels_seen_in": set(),
            "curated_from": {},  # panel -> marker_name mapping
            "markers_seen": set(),  # track unique markers for this target
        }
    )

    print(f"Processing {len(antibodies_data)} antibody entries...")

    for entry in antibodies_data:
        marker = entry.get("marker", "")
        marker_info = entry.get("marker_info", {})
        target_name = marker_info.get("target_name", "Unknown")

        # Get or create target group
        target = target_groups[target_name]

        # Set target-level information (consistent across all markers for this target)
        if not target["target_name"]:
            target["target_name"] = target_name
            target["uniprot_id"] = marker_info.get("target_id")
            target["protein_name"] = marker_info.get("protein_name")
            target["organism"] = marker_info.get("organism")
            target["subcellular_location"] = marker_info.get("subcellular_location")
            target["protein_function"] = marker_info.get("protein_function")
            target["uniprot_confidence"] = marker_info.get("uniprot_confidence")
            target["functional_categories"] = marker_info.get("functional_categories")
            target["category_names"] = marker_info.get("category_names")

        # Find panels for this marker
        print(f"Searching panels for marker: {marker}")
        panels = find_panels_for_marker(marker, htan_data_dir)
        target["panels_seen_in"].update(panels)

        # Track which marker matched each panel
        for panel in panels:
            if panel not in target["curated_from"]:
                target["curated_from"][panel] = marker

        # Track unique markers for this target
        target["markers_seen"].add(marker)

    # Convert to final structure
    result = []
    for target_name, target_data in sorted(target_groups.items()):
        # Convert sets to sorted lists
        target_data["panels_seen_in"] = sorted(list(target_data["panels_seen_in"]))

        # Add count of curated markers
        target_data["n_curated_from"] = len(target_data["markers_seen"])

        # Normalize subcellular location to highest level
        target_data["subcellular_location"] = normalize_subcellular_location(
            target_data["subcellular_location"]
        )

        # Remove temporary markers_seen set (not needed in output)
        del target_data["markers_seen"]

        result.append(target_data)

    print(f"\nCreated {len(result)} unique targets")
    return result


def generate_library(antibodies_data):
    """
    Generate library.json - biological data indexed by target_name.
    """
    library = {}

    for target in antibodies_data:
        target_name = target["target_name"]
        library[target_name] = {
            "protein_name": target.get("protein_name"),
            "uniprot": target.get("uniprot_id"),
            "function": target.get("protein_function"),
            "location": target.get("subcellular_location", []),
            "categories": target.get("functional_categories", []),
        }

    return library


def generate_manifest(file_info_path):
    """
    Generate manifest.json - searchable file metadata array.
    """
    if not os.path.exists(file_info_path):
        print(f"Warning: {file_info_path} not found, skipping manifest generation")
        return []

    file_data = read_json(file_info_path)
    manifest = []

    for file_entry in file_data:
        # Strip version suffix from channel_synid to get panel_id
        channel_synid = file_entry.get("channel_synid", "")
        panel_id = channel_synid.split(".")[0] if channel_synid else ""

        manifest.append(
            {
                "file_id": file_entry.get("HTAN_Data_File_ID"),
                "entity_id": file_entry.get("file_entity_id"),
                "participant_id": file_entry.get("HTAN_Participant_ID"),
                "diagnosis": file_entry.get("Primary_Diagnosis"),
                "center": file_entry.get("HTAN_Center"),
                "assay_type": file_entry.get("imaging_assay_type"),
                "panel_id": panel_id,
            }
        )

    return manifest


def generate_panels(antibodies_data, manifest):
    """
    Generate panels.json - technical configuration mapping panel_ids to targets and channels.
    """
    panels = {}

    # Build panel_id -> center mapping from manifest
    panel_to_center = {}
    for file_entry in manifest:
        panel_id = file_entry.get("panel_id")
        center = file_entry.get("center")
        if panel_id and center:
            panel_to_center[panel_id] = center

    for target in antibodies_data:
        target_name = target["target_name"]
        curated_from = target.get("curated_from", {})

        # Add this target to each panel it appears in
        for panel_id, marker_name in curated_from.items():
            if panel_id not in panels:
                panels[panel_id] = {
                    "targets": [],
                    "channels": {},
                    "center": panel_to_center.get(panel_id, "")
                }

            # Add target to the targets list
            if target_name not in panels[panel_id]["targets"]:
                panels[panel_id]["targets"].append(target_name)

            # Map target to channel name (marker)
            panels[panel_id]["channels"][target_name] = marker_name

    # Sort targets within each panel for consistency
    for panel_data in panels.values():
        panel_data["targets"].sort()

    return panels


def generate_small_versions(manifest, panels, library, sample_size=50):
    """
    Generate small, coherent versions for development.
    Maintains connections: files -> panels -> targets
    """
    # Take a sample of files
    manifest_small = manifest[:sample_size] if len(manifest) > sample_size else manifest

    # Get unique panel_ids from sample
    panel_ids = set(f["panel_id"] for f in manifest_small)

    # Filter panels to only those in sample
    panels_small = {pid: panels[pid] for pid in panel_ids if pid in panels}

    # Get unique targets from those panels
    target_names = set()
    for panel_data in panels_small.values():
        target_names.update(panel_data["targets"])

    # Filter library to only those targets
    library_small = {
        target: library[target] for target in target_names if target in library
    }

    return manifest_small, panels_small, library_small


def main():
    # File paths
    input_json = "curated_antibodies_harmonized.json"
    htan_data_dir = "htan_data"
    file_info_json = "file_information.json"

    # Output files
    output_antibodies = "antibodies_by_target.json"
    output_library = "library.json"
    output_manifest = "manifest.json"
    output_panels = "panels.json"

    # Small development versions
    output_library_small = "library_small.json"
    output_manifest_small = "manifest_small.json"
    output_panels_small = "panels_small.json"

    # Check if input file exists
    if not os.path.exists(input_json):
        print(f"Error: {input_json} not found")
        return

    # Restructure the data
    print("=" * 60)
    print("Step 1: Restructuring antibody data by target...")
    print("=" * 60)
    restructured_data = restructure_antibodies(input_json, htan_data_dir)

    # Write antibodies_by_target.json (keep curated_from for downstream use)
    write_json(output_antibodies, restructured_data)
    print(f"\n✓ Output written to {output_antibodies}")

    # Generate and write library.json
    print("\n" + "=" * 60)
    print("Step 2: Generating library.json (biological data)...")
    print("=" * 60)
    library = generate_library(restructured_data)
    write_json(output_library, library)
    print(f"✓ Output written to {output_library}")
    print(f"  Total targets in library: {len(library)}")

    # Generate and write manifest.json
    print("\n" + "=" * 60)
    print("Step 3: Generating manifest.json (file metadata)...")
    print("=" * 60)
    manifest = generate_manifest(file_info_json)
    write_json(output_manifest, manifest)
    print(f"✓ Output written to {output_manifest}")
    print(f"  Total files in manifest: {len(manifest)}")
    if manifest:
        unique_panels = len(set(f["panel_id"] for f in manifest))
        print(f"  Unique panel IDs: {unique_panels}")

    # Generate and write panels.json
    print("\n" + "=" * 60)
    print("Step 4: Generating panels.json (panel configurations)...")
    print("=" * 60)
    panels = generate_panels(restructured_data, manifest)
    write_json(output_panels, panels)
    print(f"✓ Output written to {output_panels}")
    print(f"  Total panels: {len(panels)}")

    # Generate small development versions
    print("\n" + "=" * 60)
    print("Step 5: Generating small development versions...")
    print("=" * 60)
    manifest_small, panels_small, library_small = generate_small_versions(
        manifest, panels, library, sample_size=250
    )

    write_json(output_manifest_small, manifest_small)
    write_json(output_panels_small, panels_small)
    write_json(output_library_small, library_small)

    print(f"✓ Output written to {output_manifest_small}")
    print(f"  Files: {len(manifest_small)}")
    print(f"✓ Output written to {output_panels_small}")
    print(f"  Panels: {len(panels_small)}")
    print(f"✓ Output written to {output_library_small}")
    print(f"  Targets: {len(library_small)}")

    # Print summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Total unique targets: {len(restructured_data)}")
    targets_with_panels = sum(1 for t in restructured_data if t["panels_seen_in"])
    print(f"Targets found in panels: {targets_with_panels}")
    print(f"\nGenerated files:")
    print(f"  FULL VERSIONS:")
    print(f"    - {output_antibodies} (complete target data)")
    print(f"    - {output_library} (biological data for React app)")
    print(f"    - {output_manifest} (file metadata for React app)")
    print(f"    - {output_panels} (panel configurations for React app)")
    print(f"\n  SMALL VERSIONS (for development):")
    print(f"    - {output_library_small} ({len(library_small)} targets)")
    print(f"    - {output_manifest_small} ({len(manifest_small)} files)")
    print(f"    - {output_panels_small} ({len(panels_small)} panels)")


if __name__ == "__main__":
    main()
