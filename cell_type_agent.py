#!/usr/bin/env python3
"""
Cell Type Agent - Identifies potential cell types from antibody panels using OLS and Claude.

This script takes panels.json and for each panel, uses Claude with OLS REST API
to identify Cell Ontology (CL) cell types that might be assigned in an antibody-based
multiplexed tissue imaging experiment.
"""

import json
import os
import requests
from anthropic import Anthropic
from typing import List, Dict, Any

import dotenv

dotenv.load_dotenv()


def load_panels(filepath="panels.json"):
    """Load panels from JSON file."""
    with open(filepath, "r") as f:
        return json.load(f)


def search_ols(query: str, ontology: str = "cl", rows: int = 10) -> Dict[str, Any]:
    """
    Search the OLS API for terms.

    Args:
        query: Search query
        ontology: Ontology to search (default: cl for Cell Ontology)
        rows: Number of results to return

    Returns:
        Dictionary with search results
    """
    url = "https://www.ebi.ac.uk/ols4/api/search"
    params = {
        "q": query,
        "ontology": ontology,
        "rows": rows,
        "exact": False,
        "type": "class",
    }

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def get_term_details(iri: str) -> Dict[str, Any]:
    """
    Get detailed information about an ontology term.

    Args:
        iri: IRI of the term

    Returns:
        Dictionary with term details
    """
    url = "https://www.ebi.ac.uk/ols4/api/terms/findByIdAndIsDefiningOntology"
    params = {"iri": iri}

    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"error": str(e)}


def create_ols_tools() -> List[Dict[str, Any]]:
    """Create tool definitions for OLS API functions."""
    return [
        {
            "name": "search_cell_ontology",
            "description": "Search the Cell Ontology (CL) for cell types matching a query. Returns ontology terms with their IDs, labels, and descriptions.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query (e.g., 'T cell', 'CD4', 'macrophage')",
                    },
                    "rows": {
                        "type": "integer",
                        "description": "Number of results to return (default: 10)",
                        "default": 10,
                    },
                },
                "required": ["query"],
            },
        },
        {
            "name": "get_term_details",
            "description": "Get detailed information about a specific Cell Ontology term by its IRI.",
            "input_schema": {
                "type": "object",
                "properties": {
                    "iri": {
                        "type": "string",
                        "description": "The IRI of the ontology term (e.g., 'http://purl.obolibrary.org/obo/CL_0000084')",
                    }
                },
                "required": ["iri"],
            },
        },
    ]


def execute_tool(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """Execute an OLS tool and return the result as a string."""
    if tool_name == "search_cell_ontology":
        results = search_ols(
            query=tool_input["query"], ontology="cl", rows=tool_input.get("rows", 10)
        )

        if "error" in results:
            return f"Error searching OLS: {results['error']}"

        # Format results
        if "response" in results and "docs" in results["response"]:
            docs = results["response"]["docs"]
            if not docs:
                return f"No results found for query: {tool_input['query']}"

            output = f"Found {len(docs)} results for '{tool_input['query']}':\n\n"
            for i, doc in enumerate(docs, 1):
                output += (
                    f"{i}. {doc.get('label', 'N/A')} ({doc.get('short_form', 'N/A')})\n"
                )
                output += f"   IRI: {doc.get('iri', 'N/A')}\n"
                if "description" in doc and doc["description"]:
                    desc = (
                        doc["description"][0]
                        if isinstance(doc["description"], list)
                        else doc["description"]
                    )
                    output += f"   Description: {desc}\n"
                output += "\n"
            return output
        else:
            return f"Unexpected response format from OLS"

    elif tool_name == "get_term_details":
        result = get_term_details(tool_input["iri"])

        if "error" in result:
            return f"Error getting term details: {result['error']}"

        # Format term details
        output = "Term Details:\n"
        output += f"Label: {result.get('label', 'N/A')}\n"
        output += f"ID: {result.get('short_form', 'N/A')}\n"
        output += f"IRI: {result.get('iri', 'N/A')}\n"
        if "description" in result and result["description"]:
            desc = (
                result["description"][0]
                if isinstance(result["description"], list)
                else result["description"]
            )
            output += f"Description: {desc}\n"
        return output

    else:
        return f"Unknown tool: {tool_name}"


def identify_cell_types_for_panel(
    client: Anthropic, panel_id: str, targets: List[str]
) -> tuple:
    """
    Use Claude with OLS REST API to identify potential cell types.

    Args:
        client: Anthropic client instance
        panel_id: Panel identifier
        targets: List of antibody targets/markers

    Returns:
        tuple: (response, messages) - Claude's final response and conversation history
    """
    # Get OLS tools
    tools = create_ols_tools()

    # Create a prompt for Claude to use OLS to find relevant cell types
    targets_str = ", ".join(targets)

    prompt = f"""Given the following protein markers from an antibody-based multiplexed tissue imaging panel (Panel ID: {panel_id}):

{targets_str}

Please use the available OLS (Ontology Lookup Service) tools to search the Cell Ontology (CL) and identify potential cell types that would express these markers.

For each cell type you identify, provide:
1. The Cell Ontology ID (CL:XXXXXXX)
2. The cell type name
3. Which markers support this cell type assignment
4. Confidence level (high/medium/low) based on marker specificity

Strategy:
- Search for key marker proteins (especially CD markers like CD3, CD4, CD8, CD68)
- Look for cell-type specific structural proteins (e.g., VIM for mesenchymal, KRT for epithelial)
- Consider marker combinations that define specific cell types
- Focus on immune cells, epithelial cells, stromal cells, and other major tissue components

After gathering information from OLS, provide a final analysis with the most likely cell types for this panel."""

    messages = [{"role": "user", "content": prompt}]

    # Agentic loop - let Claude use tools until it's done
    max_iterations = 15
    iteration = 0

    while iteration < max_iterations:
        iteration += 1

        response = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=4096,
            tools=tools,
            messages=messages,
        )

        # Check if we're done
        if response.stop_reason == "end_turn":
            break

        # Add assistant's response to messages
        messages.append({"role": "assistant", "content": response.content})

        # If Claude wants to use tools, execute them
        if response.stop_reason == "tool_use":
            tool_results = []

            for block in response.content:
                if block.type == "tool_use":
                    tool_name = block.name
                    tool_input = block.input

                    print(
                        f"    - Calling {tool_name} with query: {tool_input.get('query', tool_input.get('iri', 'N/A'))[:50]}..."
                    )

                    try:
                        result = execute_tool(tool_name, tool_input)
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result,
                            }
                        )
                    except Exception as e:
                        tool_results.append(
                            {
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": f"Error: {str(e)}",
                                "is_error": True,
                            }
                        )

            # Add tool results to messages
            messages.append({"role": "user", "content": tool_results})
        else:
            # Some other stop reason, break
            break

    return response, messages


def parse_cell_type_response(response) -> Dict[str, Any]:
    """Parse Claude's response to extract structured cell type information."""
    result = {"cell_types": [], "raw_response": ""}

    for block in response.content:
        if block.type == "text":
            result["raw_response"] += block.text

    return result


def process_all_panels(
    panels: Dict[str, Any],
    output_file: str = "cell_type_predictions.json",
    limit: int = None,
) -> Dict[str, Any]:
    """
    Process all panels and identify cell types.

    Args:
        panels: Dictionary of panels from panels.json
        output_file: Where to save the results
        limit: Optional limit on number of panels to process (for testing)
    """
    # Initialize Anthropic client
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("ANTHROPIC_API_KEY environment variable must be set")

    client = Anthropic(api_key=api_key)

    results = {}
    panel_ids = list(panels.keys())

    if limit:
        panel_ids = panel_ids[:limit]

    print(f"Processing {len(panel_ids)} panels...")
    print("Using OLS REST API at https://www.ebi.ac.uk/ols4/api/\n")

    for i, panel_id in enumerate(panel_ids, 1):
        panel_data = panels[panel_id]
        targets = panel_data.get("targets", [])

        if not targets:
            print(f"[{i}/{len(panel_ids)}] Skipping {panel_id}: no targets")
            continue

        print(
            f"[{i}/{len(panel_ids)}] Processing {panel_id} ({len(targets)} markers)..."
        )

        try:
            # Get cell type predictions from Claude + OLS
            response, _ = identify_cell_types_for_panel(client, panel_id, targets)
            parsed = parse_cell_type_response(response)

            results[panel_id] = {
                "targets": targets,
                "num_targets": len(targets),
                "predictions": parsed,
            }

            print(f"  ✓ Identified cell types for {panel_id}\n")
            print(f"Predicted cell types:\n{parsed['raw_response']}\n")

        except Exception as e:
            print(f"  ✗ Error processing {panel_id}: {str(e)}\n")
            results[panel_id] = {
                "targets": targets,
                "num_targets": len(targets),
                "error": str(e),
            }

    # Save results
    with open(output_file, "w") as f:
        json.dump(results, f, indent=2)

    print(f"\nResults saved to {output_file}")
    successful = len([r for r in results.values() if "error" not in r])
    print(f"Successfully processed {successful}/{len(results)} panels")

    return results


def main():
    """Main entry point."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Identify cell types from antibody panels using OLS and Claude"
    )
    parser.add_argument(
        "--input",
        default="panels.json",
        help="Input panels JSON file (default: panels.json)",
    )
    parser.add_argument(
        "--output",
        default="cell_type_predictions.json",
        help="Output file for predictions (default: cell_type_predictions.json)",
    )
    parser.add_argument(
        "--limit", type=int, help="Limit number of panels to process (for testing)"
    )

    args = parser.parse_args()

    # Load panels
    print(f"Loading panels from {args.input}...")
    panels = load_panels(args.input)
    print(f"Loaded {len(panels)} panels\n")

    # Process panels
    results = process_all_panels(panels, args.output, args.limit)

    return results


if __name__ == "__main__":
    main()
