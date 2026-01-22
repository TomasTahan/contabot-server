"""
Tools for managing categories - these will be used by the Claude agent.
"""
from typing import Optional

from src.services.pocketbase_client import get_pocketbase_service


async def get_categories() -> dict:
    """
    Get all available categories with their hierarchy.

    Returns:
        Dictionary with list of categories
    """
    pb = get_pocketbase_service()
    categories = await pb.get_categories_with_parents()

    # Separate parent categories and subcategories
    parents = [c for c in categories if not c["parent_id"]]
    children = [c for c in categories if c["parent_id"]]

    return {
        "categories": categories,
        "parent_categories": [{"id": p["id"], "name": p["name"]} for p in parents],
        "total": len(categories),
    }


async def get_properties() -> dict:
    """
    Get all available properties.

    Returns:
        Dictionary with list of properties
    """
    pb = get_pocketbase_service()
    properties = await pb.get_properties()

    return {
        "properties": [
            {"id": p.id, "name": p.name, "description": p.description}
            for p in properties
        ],
        "total": len(properties),
    }


async def suggest_category(text: str) -> dict:
    """
    Suggest a category based on keywords in the text.

    Args:
        text: Text to analyze for category suggestion

    Returns:
        Dictionary with suggested category or None
    """
    pb = get_pocketbase_service()
    categories = await pb.get_categories_with_parents()

    text_lower = text.lower()

    # Score each category based on keyword matches
    scores = []
    for cat in categories:
        score = 0
        for keyword in cat.get("keywords", []):
            if keyword.lower() in text_lower:
                score += 1
                # Bonus for exact word match
                if f" {keyword.lower()} " in f" {text_lower} ":
                    score += 1

        if score > 0:
            scores.append((cat, score))

    # Sort by score and return best match
    scores.sort(key=lambda x: x[1], reverse=True)

    if scores:
        best = scores[0][0]
        return {
            "suggested": True,
            "category_id": best["id"],
            "category_name": best["full_name"],
            "property_id": best.get("property"),
            "confidence": min(scores[0][1] / 3.0, 1.0),  # Normalize to 0-1
        }

    return {
        "suggested": False,
        "category_id": None,
        "category_name": None,
        "property_id": None,
        "confidence": 0.0,
    }


# Tool definitions for Claude Agent SDK
CATEGORY_TOOLS = [
    {
        "name": "get_categories",
        "description": """Get all available expense categories. Use this to find the correct category ID for an expense.

Categories are hierarchical - some have parent categories (e.g., 'Farmacia' is under 'SALUD').

Returns a list of all categories with their IDs, names, and parent relationships.""",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "get_properties",
        "description": """Get all available properties. Properties are the different locations/places the family has:
- Pirque: Casa principal (main house)
- Maitri: Clínica (clinic)
- Costa Mai: Departamento Maitecillo (apartment)

Use this to find the correct property ID when an expense is related to a specific location.""",
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "suggest_category",
        "description": "Suggest a category based on text analysis. This tool analyzes keywords to suggest the most likely category for an expense.",
        "input_schema": {
            "type": "object",
            "properties": {
                "text": {
                    "type": "string",
                    "description": "Text to analyze for category suggestion",
                },
            },
            "required": ["text"],
        },
    },
]
