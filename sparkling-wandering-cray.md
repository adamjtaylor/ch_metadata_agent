# Documentation Plan: OMOP CDM JSON Schema Converter

## Overview
Create two comprehensive markdown files documenting the OMOP CDM to JSON Schema conversion tool:
1. **README.md** - Balanced tutorial for using the tool
2. **BACKGROUND.md** - Detailed design rationale and technical context

## README.md Structure

### 1. Header & Overview
- Project title and one-line description
- What it does: Converts OMOP CDM 5.4 metadata to JSON Schema with vocabulary enums
- Key features (enum support, 6M+ concepts, UI-ready)

### 2. Quick Start
```bash
# Clone/setup
# Run converter
./convert.sh
```

### 3. Prerequisites
- Python 3.7+
- Bash shell
- OMOP CDM vocabulary files (CONCEPT.csv)
- Disk space: ~1GB for vocab, ~800MB for schemas

### 4. Installation & Setup

**Step 1: Get OMOP Vocabularies**
- Link to Athena (https://athena.ohdsi.org/)
- How to download vocabulary bundle
- Where to place CONCEPT.csv

**Step 2: Get CDM Metadata**
- Automatically downloaded by script
- Source: OHDSI CommonDataModel GitHub

**Step 3: Run Conversion**
- `./convert.sh` command
- What happens during execution
- Expected output and timing

### 5. Project Structure
```
test2/
├── convert.sh              # Main orchestration script
├── convert_to_schemas.py   # Python conversion logic
├── data/
│   ├── OMOP_CDMv5.4_Field_Level.csv
│   └── CONCEPT.csv (symlink)
└── schemas/                # Generated schemas (759MB)
    ├── person.schema.json
    ├── drug_exposure.schema.json
    └── ... (39 total)
```

### 6. Generated Schemas

**What's Included:**
- JSON Schema draft-07 format
- One file per OMOP table
- Enum arrays for CONCEPT foreign keys
- Human-readable enum names (ID - Name format)
- Field descriptions combining guidance + conventions

**Example Schema Snippet:**
```json
{
  "gender_concept_id": {
    "type": "integer",
    "enum": [0, 8507, 8532],
    "x-enumNames": {
      "0": "0 - No matching concept",
      "8507": "8507 - MALE",
      "8532": "8532 - FEMALE"
    }
  }
}
```

### 7. Usage Examples

**Validate Data:**
```python
import json
import jsonschema

with open('schemas/person.schema.json') as f:
    schema = json.load(f)

# Validate person record
person = {
    "person_id": 1,
    "gender_concept_id": 8507,  # Male
    "year_of_birth": 1990
}

jsonschema.validate(person, schema)
```

**UI Dropdowns:**
```python
# Extract enum options for UI
schema = json.load(open('schemas/person.schema.json'))
gender_enum = schema['properties']['gender_concept_id']

for id in gender_enum['enum']:
    label = gender_enum['x-enumNames'][str(id)]
    print(f"<option value='{id}'>{label}</option>")
```

### 8. Configuration

**Script Variables (convert.sh):**
- `CONCEPT_SOURCE`: Path to CONCEPT.csv
- `DATA_DIR`: Input data directory
- `SCHEMAS_DIR`: Output directory

**Python Functions:**
- Filtering logic (standard_concept='S')
- Enum size thresholds
- Domain mappings

### 9. Output Statistics
- 39 schema files generated
- 759MB total size
- 39 fields with enum support
- Domain sizes:
  - Small: Gender (3), Ethnicity (151)
  - Medium: Visit (264), Type Concept (81)
  - Large: Drug (2M+), Condition (105K)

### 10. Troubleshooting

**Issue: CONCEPT.csv not found**
- Solution: Download from Athena, place in test1/athena_export_*/

**Issue: Out of memory**
- Solution: Requires ~2GB RAM for large enums

**Issue: Schemas too large**
- Explanation: Drug domain creates 227MB files
- Solution: This is expected, use streaming/lazy loading in applications

**Issue: Missing enums for some fields**
- Explanation: Only fields with domain info get enums
- Check: x-foreignKeys for domain specification

### 11. Performance Notes
- Initial run: 10-30 seconds (loads 6M concepts)
- Subsequent runs: No caching, same time
- Memory usage: ~2GB peak during enum building
- Disk I/O: Tab-separated parsing optimized

### 12. Contributing & License
- How to report issues
- How to extend (add new vocab tables, different OMOP versions)
- License info

### 13. References
- OHDSI CommonDataModel: [link]
- Athena Vocabulary: [link]
- JSON Schema draft-07: [link]
- OMOP CDM documentation: [link]

---

## BACKGROUND.md Structure

### 1. Introduction
- Project genesis: Need for JSON Schema validation in OMOP data entry
- Problem: UI dropdowns need concept enums, but vocabularies are massive
- Solution: Generate schemas with inline enums from CONCEPT table

### 2. OMOP CDM Context

**What is OMOP CDM?**
- Observational Medical Outcomes Partnership
- Common Data Model for healthcare/research data
- Standardized vocabularies for clinical concepts

**CONCEPT Table Explained:**
- 6.3M concepts across all medical domains
- Structure: concept_id, concept_name, domain_id, vocabulary_id, standard_concept
- Domains: Drug, Condition, Measurement, Procedure, Device, etc.
- Standard vs non-standard concepts (S flag)

**How Vocabularies Work:**
- Foreign keys to CONCEPT table with domain constraints
- Example: gender_concept_id → CONCEPT WHERE domain_id='Gender'
- Standard concepts preferred for analysis/interoperability

**Why This Matters for Schemas:**
- Need to validate data against allowed concept values
- UI tools need dropdown lists of valid concepts
- Must map numeric IDs to human-readable names

### 3. Requirements Analysis

**Primary Goal:**
Enable spreadsheet/grid UI with validated dropdowns for OMOP data entry

**User Needs:**
1. JSON Schema validation (standard format)
2. Enum arrays for concept fields (dropdown values)
3. Human-readable labels (not just IDs)
4. Complete coverage (all standard concepts)
5. Self-contained schemas (no external lookups)

**Technical Constraints:**
- JSON Schema draft-07 only
- Standard library Python (no dependencies)
- Bash + Python stack
- ~1GB vocabulary files
- Must handle 2M+ drug concepts

### 4. Design Decisions (Detailed)

#### Decision 1: JSON Schema Format

**Options Considered:**

A. **enum + x-enumNames** (CHOSEN)
```json
{
  "type": "integer",
  "enum": [0, 8507, 8532],
  "x-enumNames": {
    "0": "0 - No matching concept",
    "8507": "8507 - MALE"
  }
}
```

**Pros:**
- Native JSON Schema validation on enum
- Compact representation
- x-enumNames provides UI labels
- Widely supported pattern

**Cons:**
- x-enumNames not standard (extension)
- Less rich than oneOf

B. **oneOf with const + title**
```json
{
  "oneOf": [
    {"const": 0, "title": "No matching concept"},
    {"const": 8507, "title": "MALE"}
  ]
}
```

**Pros:**
- Pure JSON Schema (no extensions)
- Richer metadata per option
- Better error messages

**Cons:**
- Much larger file size (~3x)
- Drug domain would be 600MB vs 227MB
- Slower validation

C. **External Reference Files**
```json
{
  "type": "integer",
  "$ref": "vocabularies/gender.json#/enum"
}
```

**Pros:**
- Smaller individual schemas
- Reusable vocabulary files

**Cons:**
- Not self-contained
- More complex deployment
- Extra file lookups

**Decision Rationale:**
Chose option A (enum + x-enumNames) for:
- Balance of size vs functionality
- Self-contained schemas
- Standard enum validation
- Simple UI integration

#### Decision 2: Concept Filtering

**Options:**

A. **All Concepts** (6.3M)
- Too many, includes deprecated/non-standard

B. **Standard Concepts Only** (CHOSEN)
- Filter: standard_concept = 'S'
- Reduces to ~2.5M concepts
- OHDSI best practice

C. **Limited by Size** (e.g., max 1000 per domain)
- Incomplete coverage
- Which 1000 to choose?

**Decision Rationale:**
Standard concepts only aligns with OMOP best practices and still provides complete coverage for clinical use.

#### Decision 3: Domain Coverage

**Options:**

A. **All CONCEPT FKs** (CHOSEN)
- Generate enums for all domains
- Even 2M drug concepts

B. **Small Domains Only** (<1000 concepts)
- Skip Drug, Condition, Observation
- Incomplete solution

C. **User-Configured List**
- Flexibility but setup burden

**Decision Rationale:**
Full coverage chosen because:
- User explicitly requested "all" standard concepts
- UI can implement lazy loading
- Complete = no surprises

#### Decision 4: Display Format

**Options:**

A. **"ID - Name"** (CHOSEN)
- Example: "8507 - MALE"
- Shows both identifier and label

B. **Name Only**
- Example: "MALE"
- Cleaner but loses ID context

C. **Name (ID)**
- Example: "MALE (8507)"
- Reads better but ID harder to parse

**Decision Rationale:**
ID - Name format provides:
- Clear ID for database storage
- Human-readable label for UI
- Consistent with OMOP conventions

### 5. Technical Challenges (Detailed)

#### Challenge 1: File Size Management

**Problem:**
- Drug domain: 2,048,628 concepts
- Each concept: ~50 bytes in JSON
- Result: 227MB per drug-related schema

**Solutions Explored:**
- Compression: gzip reduces to ~20MB but requires decompression
- Chunking: Violates self-contained requirement
- Abbreviation: Loses information

**Solution Implemented:**
- Accept large files
- Document for users
- Recommend streaming/lazy loading in applications

**Impact:**
- Total schemas: 759MB
- Largest: drug_exposure.schema.json (227MB)
- Medium: measurement.schema.json (9.6MB)
- Small: person.schema.json (110KB)

#### Challenge 2: Memory Usage

**Problem:**
- Loading 6.3M concepts into memory
- Building enum dictionaries
- Python dict overhead

**Solutions:**
- Stream processing: Can't build lookups
- Database: Adds dependency
- Memory mapping: Complex

**Solution Implemented:**
- Load once, build domain mappings
- Use defaultdict for efficient grouping
- Progress logging every 500K concepts
- Acceptable: ~2GB RAM peak

**Code Pattern:**
```python
concepts_by_domain = defaultdict(dict)
for row in csv.DictReader(f, delimiter='\t'):
    if row['standard_concept'] == 'S':
        concepts_by_domain[domain][id] = name
```

#### Challenge 3: TSV Parsing

**Problem:**
- CONCEPT.csv is tab-separated (not comma)
- Contains special characters in concept names
- 6.3M rows to process

**Solution:**
```python
csv.DictReader(f, delimiter='\t')
```

**Gotchas Handled:**
- Concept names with quotes, commas, tabs
- Unicode characters in medical terms
- Empty fields (checked for 'NA')

#### Challenge 4: Domain Matching

**Problem:**
- CDM metadata has fkDomain field
- CONCEPT table has domain_id field
- Must match exactly (case-sensitive)
- Some FKs have no domain specified

**Solution:**
- Exact string matching: `fk_table.upper() == 'CONCEPT'`
- Check domain exists: `if fk_domain in concept_enum_map`
- Graceful handling: Skip FKs without domain info

**Result:**
- 39 fields with enums (domain specified)
- 80+ CONCEPT FKs without enums (no domain in metadata)

#### Challenge 5: Concept ID 0

**Problem:**
- concept_id = 0 means "No matching concept"
- Has domain_id = "Metadata"
- Should appear in ALL domain enums

**Solution:**
```python
if 0 not in concepts:
    concepts[0] = "No matching concept"
```

**Ensures:**
- Every enum includes 0 for nullable fields
- Consistent across all domains

### 6. Implementation Details

**Architecture:**
```
convert.sh (bash)
  ├─ Check/symlink CONCEPT.csv
  └─ Execute convert_to_schemas.py

convert_to_schemas.py (python)
  ├─ load_csv_data() → field metadata
  ├─ load_concept_data() → 6.3M concepts by domain
  ├─ build_concept_enum_mapping() → sorted enums + labels
  └─ build_table_schema() → inject enums into properties
```

**Key Functions:**

1. `load_concept_data()`
   - Opens CONCEPT.csv with tab delimiter
   - Filters standard_concept='S'
   - Groups by domain_id
   - Returns nested dict: {domain: {id: name}}

2. `build_concept_enum_mapping()`
   - Sorts concept IDs per domain
   - Formats x-enumNames as "ID - Name"
   - Logs warnings for large domains
   - Returns (enum_array, enum_names_dict)

3. `build_table_schema()` (enhanced)
   - Existing: Build properties, required, FK arrays
   - New: Check if FK table=='CONCEPT' and has domain
   - New: Inject enum + x-enumNames from mapping

**Data Flow:**
```
CONCEPT.csv (6.3M rows)
  → Filter standard='S' (2.5M rows)
  → Group by domain (32 domains)
  → Sort IDs + format names
  → Inject into field schemas (39 fields)
  → Write JSON (39 files, 759MB)
```

### 7. Alternative Approaches Comparison

#### Alternative 1: Athena API

**Approach:**
- Query Athena REST API during conversion
- Fetch concepts dynamically

**Pros:**
- Always current vocabulary
- No local CONCEPT.csv needed

**Cons:**
- Requires internet during conversion
- API rate limits
- 6M+ API calls impractical
- Athena API not designed for bulk export

**Why Not Chosen:**
API not suitable for bulk data extraction

#### Alternative 2: Separate Vocabulary Files

**Approach:**
```
schemas/person.schema.json + vocabularies/gender.json
```

**Pros:**
- Smaller individual schemas
- Reusable vocabulary files
- Easy to update vocabs separately

**Cons:**
- Not self-contained
- More complex deployment
- $ref resolution required
- Breaks UI tool assumptions

**Why Not Chosen:**
User requirement for self-contained schemas

#### Alternative 3: Limit Enum Sizes

**Approach:**
- Max 500 concepts per enum
- Truncate large domains

**Pros:**
- Manageable file sizes
- Faster loading

**Cons:**
- Incomplete coverage
- Which 500? Most common? First 500?
- Drug domain needs full coverage

**Why Not Chosen:**
User explicitly requested all standard concepts

#### Alternative 4: oneOf Instead of enum

**Approach:**
```json
{"oneOf": [{"const": 8507, "title": "MALE"}]}
```

**Pros:**
- Pure JSON Schema (no extensions)
- Richer per-option metadata

**Cons:**
- ~3x file size
- Drug domain → 600MB
- Slower validation
- Overkill for simple dropdowns

**Why Not Chosen:**
Size/performance tradeoff not worth it

#### Alternative 5: Database Backend

**Approach:**
- Store concepts in SQLite/PostgreSQL
- Schemas reference DB

**Pros:**
- Efficient storage/queries
- Dynamic vocabulary updates

**Cons:**
- Adds dependency
- Not self-contained
- Complex deployment
- Breaks JSON Schema portability

**Why Not Chosen:**
Violates standard library + portability requirements

### 8. Trade-offs Accepted

**Large File Sizes (759MB total)**
- Acceptable: Storage is cheap
- Mitigation: Users can lazy-load in apps
- Benefit: Complete, self-contained schemas

**Slow Initial Load (10-30 seconds)**
- Acceptable: One-time setup cost
- Mitigation: Progress logging shows activity
- Benefit: No runtime dependencies

**Memory Usage (2GB peak)**
- Acceptable: Modern systems have RAM
- Mitigation: Streaming not possible with lookup building
- Benefit: Fast enum injection after load

**No Caching**
- Acceptable: Conversion is infrequent
- Mitigation: Could add if needed
- Benefit: Simpler code

**Missing Enums for Some Fields**
- Acceptable: CDM metadata doesn't specify all domains
- Mitigation: Document which fields get enums
- Benefit: Only enrich where metadata supports it

### 9. Lessons Learned

1. **OMOP Vocabularies Are Massive**
   - 6.3M concepts, 2.5M standard
   - Drug domain alone is 2M concepts
   - Plan for scale from start

2. **TSV vs CSV Matters**
   - Medical terms have commas
   - Athena exports as TSV
   - Must specify delimiter='\t'

3. **Standard Library is Powerful**
   - csv.DictReader with delimiter
   - defaultdict for grouping
   - json.dump with ensure_ascii=False
   - No external dependencies needed

4. **User Requirements Drive Design**
   - "All standard concepts" = accept large files
   - "UI dropdowns" = need human-readable labels
   - "Self-contained" = no external references

5. **Progress Feedback Essential**
   - 6M rows take time to process
   - Log every 500K to show activity
   - Users need to know it's working

### 10. Future Enhancements

**Potential Improvements:**

1. **Compression Option**
   - Gzip schemas for distribution
   - Trade storage for decompression time

2. **Vocabulary Versioning**
   - Track OMOP vocabulary version
   - Support multiple versions

3. **Incremental Updates**
   - Cache concept mappings
   - Only rebuild changed domains

4. **Custom Filtering**
   - Config file for domain selection
   - Concept count limits per domain

5. **Validation Tool**
   - Verify generated schemas
   - Check enum completeness

6. **Documentation Generator**
   - Auto-generate field docs from schemas
   - Create browsable vocabulary reference

### 11. Conclusion

The OMOP CDM JSON Schema Converter successfully bridges the gap between OMOP's massive standardized vocabularies and practical JSON Schema validation for data entry applications. By accepting large file sizes in exchange for complete, self-contained schemas, we enable UI developers to build robust, validated OMOP data entry tools without external dependencies or runtime vocabulary lookups.

The implementation demonstrates that with careful design choices—enum+x-enumNames for compact representation, standard concept filtering for data quality, and progress logging for user experience—it's possible to handle 6.3 million concepts and generate 759MB of schemas while maintaining code simplicity and maintainability using only Python's standard library.

---

## Implementation Files to Create

### 1. README.md
- **Location:** `/Users/ataylor/Documents/projects/omop-cdm-playground/test2/README.md`
- **Length:** ~500-700 lines
- **Style:** Balanced tutorial with code examples
- **Sections:** 13 sections as outlined above

### 2. BACKGROUND.md
- **Location:** `/Users/ataylor/Documents/projects/omop-cdm-playground/test2/BACKGROUND.md`
- **Length:** ~800-1000 lines
- **Style:** Detailed technical narrative
- **Sections:** 11 sections as outlined above

## Success Criteria

- [ ] README.md provides clear, working instructions for setup and usage
- [ ] BACKGROUND.md explains all major design decisions with rationale
- [ ] Both files are well-structured with clear headings
- [ ] Code examples are tested and work as shown
- [ ] Technical challenges section explains real problems solved
- [ ] Alternative approaches show comparative analysis
- [ ] OMOP context educates readers unfamiliar with CDM
- [ ] Files cross-reference each other appropriately
- [ ] Markdown formatting is clean and renders well
- [ ] Links to external resources are valid
