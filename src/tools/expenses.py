"""
Tools for managing expenses - these will be used by the Claude agent.
"""
from datetime import datetime
from typing import Optional
import json

from src.services.pocketbase_client import get_pocketbase_service
from src.models.schemas import ExpenseCreate


async def register_expense(
    amount: float,
    description: str,
    category_id: Optional[str] = None,
    property_id: Optional[str] = None,
    payment_method: str = "card",
    telegram_user_id: Optional[str] = None,
    notes: Optional[str] = None,
    date: Optional[str] = None,
) -> dict:
    """
    Register a new expense in the database.

    Args:
        amount: The amount of the expense in CLP
        description: Description of the expense
        category_id: ID of the category (optional)
        property_id: ID of the property (optional)
        payment_method: Payment method - 'card', 'transfer', or 'cash'
        telegram_user_id: ID of the telegram user who registered the expense
        notes: Additional notes
        date: Date of the expense in ISO format (defaults to now)

    Returns:
        Dictionary with the created expense details
    """
    pb = get_pocketbase_service()

    expense_date = datetime.fromisoformat(date) if date else datetime.now()

    expense = ExpenseCreate(
        amount=amount,
        description=description,
        date=expense_date,
        category=category_id,
        property=property_id,
        payment_method=payment_method,
        telegram_user=telegram_user_id,
        notes=notes,
    )

    created = await pb.create_expense(expense)

    # Get category and property names for response
    category_name = None
    property_name = None

    if created.category:
        cat = await pb.get_category_by_id(created.category)
        if cat:
            category_name = cat.name

    if created.property:
        prop = await pb.get_property_by_id(created.property)
        if prop:
            property_name = prop.name

    return {
        "success": True,
        "expense_id": created.id,
        "amount": created.amount,
        "description": created.description,
        "category": category_name,
        "property": property_name,
        "payment_method": created.payment_method,
        "date": created.date.isoformat() if created.date else None,
    }


async def get_recent_expenses(days: int = 7, limit: int = 10) -> dict:
    """
    Get recent expenses.

    Args:
        days: Number of days to look back
        limit: Maximum number of expenses to return

    Returns:
        Dictionary with list of recent expenses
    """
    pb = get_pocketbase_service()
    expenses = await pb.get_recent_expenses(days=days, limit=limit)
    categories = await pb.get_categories_with_parents()
    properties = await pb.get_properties()

    cat_lookup = {c["id"]: c["full_name"] for c in categories}
    prop_lookup = {p.id: p.name for p in properties}

    result = []
    for exp in expenses:
        result.append({
            "id": exp.id,
            "amount": exp.amount,
            "description": exp.description,
            "date": exp.date.isoformat() if exp.date else None,
            "category": cat_lookup.get(exp.category) if exp.category else None,
            "property": prop_lookup.get(exp.property) if exp.property else None,
            "payment_method": exp.payment_method,
        })

    return {
        "count": len(result),
        "expenses": result,
    }


async def get_expense_summary(period: str = "month") -> dict:
    """
    Get a summary of expenses for a period.

    Args:
        period: 'week', 'month', or 'year'

    Returns:
        Dictionary with expense summary by category
    """
    from datetime import timedelta

    pb = get_pocketbase_service()

    now = datetime.now()
    if period == "week":
        start_date = now - timedelta(days=7)
    elif period == "year":
        start_date = now.replace(month=1, day=1)
    else:  # month
        start_date = now.replace(day=1)

    summary = await pb.get_expense_summary(start_date=start_date, end_date=now)

    return {
        "period": period,
        "start_date": start_date.isoformat(),
        "end_date": now.isoformat(),
        "total": summary["total"],
        "count": summary["count"],
        "by_category": summary["by_category"],
    }


# Tool definitions for Claude Agent SDK
EXPENSE_TOOLS = [
    {
        "name": "register_expense",
        "description": """Register a new expense in the database. Use this tool when the user wants to record a purchase or payment.

Parameters:
- amount (required): The amount in Chilean Pesos (CLP). Convert text like "doce mil quinientos" to 12500.
- description (required): Brief description of the expense.
- category_id: The ID of the category. Use get_categories to find the right one.
- property_id: The ID of the property if the expense is related to a specific property.
- payment_method: 'card', 'transfer', or 'cash'. Default is 'card'.
- notes: Any additional notes about the expense.
- date: Date in ISO format. Defaults to current date/time.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "amount": {"type": "number", "description": "Amount in CLP"},
                "description": {"type": "string", "description": "Expense description"},
                "category_id": {"type": "string", "description": "Category ID"},
                "property_id": {"type": "string", "description": "Property ID"},
                "payment_method": {
                    "type": "string",
                    "enum": ["card", "transfer", "cash"],
                    "default": "card",
                },
                "notes": {"type": "string", "description": "Additional notes"},
                "date": {"type": "string", "description": "Date in ISO format"},
            },
            "required": ["amount", "description"],
        },
    },
    {
        "name": "get_recent_expenses",
        "description": "Get a list of recent expenses. Use this when the user asks about recent purchases or wants to see their expense history.",
        "input_schema": {
            "type": "object",
            "properties": {
                "days": {
                    "type": "integer",
                    "description": "Number of days to look back",
                    "default": 7,
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of expenses to return",
                    "default": 10,
                },
            },
        },
    },
    {
        "name": "get_expense_summary",
        "description": "Get a summary of expenses grouped by category. Use this when the user asks for totals, summaries, or 'how much have I spent'.",
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "string",
                    "enum": ["week", "month", "year"],
                    "description": "Time period for the summary",
                    "default": "month",
                },
            },
        },
    },
]
