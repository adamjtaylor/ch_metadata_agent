# Data Processing Workflow

## Overview
This workflow diagram shows how `restructure_antibodies.py` transforms raw antibody and file metadata into optimized files for the React app.

## Workflow Diagram

```mermaid
flowchart TD
    %% Input Files
    Input1[("curated_antibodies_harmonized.json<br/>580 antibody entries")]
    Input2[("file_information.json<br/>5,995 files")]
    Input3[("htan_data/<br/>714 panel files<br/>(CSV & TXT)")]

    %% Main Script
    Main["<b>restructure_antibodies.py</b><br/>Main Orchestrator"]

    %% Processing Steps
    Step1["<b>Step 1: Restructure Antibodies</b><br/>• Group by target_name<br/>• Search panels for each marker<br/>• Consolidate marker variants<br/>• Normalize subcellular locations"]

    Step2["<b>Step 2: Generate Library</b><br/>• Extract biological data<br/>• Index by target_name<br/>• Keep: protein info, function,<br/>location, categories"]

    Step3["<b>Step 3: Generate Manifest</b><br/>• Parse file metadata<br/>• Strip version from panel_id<br/>• Flatten to array structure"]

    Step4["<b>Step 4: Generate Panels</b><br/>• Map panel_id → targets<br/>• Map target → channel name<br/>• Build from curated_from"]

    Step5["<b>Step 5: Generate Small Versions</b><br/>• Sample 250 files<br/>• Extract related panels<br/>• Extract related targets<br/>• Maintain coherence"]

    %% Intermediate Data
    Inter1[("antibodies_by_target.json<br/>346 unique targets<br/>with curated_from")]

    %% Output Files - Full
    Out1[("library.json<br/>346 targets<br/><i>Biological data indexed<br/>by target_name</i>")]

    Out2[("manifest.json<br/>5,995 files<br/><i>Flat array of file<br/>metadata</i>")]

    Out3[("panels.json<br/>713 panels<br/><i>Panel configs with<br/>targets & channels</i>")]

    %% Output Files - Small
    OutS1[("library_small.json<br/>~150 targets<br/><i>Dev sample</i>")]

    OutS2[("manifest_small.json<br/>250 files<br/><i>Dev sample</i>")]

    OutS3[("panels_small.json<br/>~50 panels<br/><i>Dev sample</i>")]

    %% Connections
    Input1 --> Main
    Input2 --> Main
    Input3 --> Main

    Main --> Step1
    Step1 --> Inter1

    Inter1 --> Step2
    Inter1 --> Step4
    Input2 --> Step3

    Step2 --> Out1
    Step3 --> Out2
    Step4 --> Out3

    Out1 --> Step5
    Out2 --> Step5
    Out3 --> Step5

    Step5 --> OutS1
    Step5 --> OutS2
    Step5 --> OutS3

    %% React App Usage
    App["<b>React App</b><br/>Uses optimized files"]

    Out1 -.-> App
    Out2 -.-> App
    Out3 -.-> App

    Dev["<b>Development/Testing</b><br/>Uses small files"]

    OutS1 -.-> Dev
    OutS2 -.-> Dev
    OutS3 -.-> Dev

    %% Styling
    classDef inputStyle fill:#e1f5ff,stroke:#0288d1,stroke-width:2px
    classDef processStyle fill:#fff3e0,stroke:#f57c00,stroke-width:2px
    classDef outputStyle fill:#e8f5e9,stroke:#388e3c,stroke-width:2px
    classDef smallStyle fill:#f3e5f5,stroke:#7b1fa2,stroke-width:2px
    classDef appStyle fill:#fce4ec,stroke:#c2185b,stroke-width:2px,stroke-dasharray: 5 5

    class Input1,Input2,Input3 inputStyle
    class Step1,Step2,Step3,Step4,Step5,Main processStyle
    class Out1,Out2,Out3,Inter1 outputStyle
    class OutS1,OutS2,OutS3 smallStyle
    class App,Dev appStyle
```

## Process Details

### Step 1: Restructure Antibodies
**Function:** `restructure_antibodies()`
- **Input:** curated_antibodies_harmonized.json + htan_data/
- **Process:**
  1. Read 580 antibody entries
  2. Group by `target_name` (consolidates marker variants)
  3. Search each marker in htan_data files (regex search)
  4. Build `curated_from` mapping (panel → marker)
  5. Normalize subcellular locations to 3 categories
- **Output:** antibodies_by_target.json (346 unique targets)

### Step 2: Generate Library
**Function:** `generate_library()`
- **Input:** antibodies_by_target.json
- **Process:**
  1. Extract biological fields only
  2. Create object indexed by target_name
  3. Drop panels_seen_in, curated_from
- **Output:** library.json (biological encyclopedia)

### Step 3: Generate Manifest
**Function:** `generate_manifest()`
- **Input:** file_information.json
- **Process:**
  1. Read file metadata
  2. Strip version suffix from channel_synid → panel_id
  3. Rename fields for clarity
  4. Create flat array structure
- **Output:** manifest.json (searchable file list)

### Step 4: Generate Panels
**Function:** `generate_panels()`
- **Input:** antibodies_by_target.json (with curated_from)
- **Process:**
  1. Iterate through all targets
  2. For each panel in curated_from:
     - Add target to panel's targets array
     - Map target → channel name (marker)
  3. Sort targets alphabetically
- **Output:** panels.json (panel configurations)

### Step 5: Generate Small Versions
**Function:** `generate_small_versions()`
- **Input:** manifest.json, panels.json, library.json
- **Process:**
  1. Sample first 250 files from manifest
  2. Extract unique panel_ids (maintains file→panel link)
  3. Filter panels to only sampled IDs
  4. Extract unique targets from those panels (maintains panel→target link)
  5. Filter library to only those targets
- **Output:** 3 coherent small files for development

## Data Relationships

```mermaid
erDiagram
    MANIFEST ||--o{ PANELS : "references via panel_id"
    PANELS ||--o{ LIBRARY : "references via targets"

    MANIFEST {
        string file_id PK
        string data_file_id
        string participant_id
        string diagnosis
        string center
        string assay_type
        string panel_id FK
    }

    PANELS {
        string panel_id PK
        array targets FK
        object channels
    }

    LIBRARY {
        string target_name PK
        string protein_name
        string uniprot
        string function
        array location
        array categories
    }
```

## Key Features

### Data Consolidation
- 580 antibody markers → 346 unique targets
- Merges variants like "CD8a-AF488" and "CD8a-APC" into "CD8A"

### Normalization
- Subcellular locations reduced to 3 high-level categories:
  - Cell membrane
  - Cytoplasm
  - Nucleus

### Coherence (Small Versions)
- All panel_ids in manifest_small exist in panels_small ✓
- All targets in panels_small exist in library_small ✓
- Perfect for development without loading large files

### Performance Optimization
- Library: Object lookup O(1) by target_name
- Manifest: Flat array for easy filtering
- Panels: Direct mapping for quick resolution

## Usage

### Generate All Files
```bash
python3 restructure_antibodies.py
```

### Output Files

**Production (Full Dataset):**
- `library.json` - 346 targets, biological data
- `manifest.json` - 5,995 files, searchable metadata
- `panels.json` - 713 panels, technical configs
- `antibodies_by_target.json` - Complete reference data

**Development (Sample Dataset):**
- `library_small.json` - ~150 targets
- `manifest_small.json` - 250 files
- `panels_small.json` - ~50 panels

All small versions are internally coherent and connected.
