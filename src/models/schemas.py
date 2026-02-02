from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class Property(BaseModel):
    id: str
    name: str
    description: Optional[str] = None


class Category(BaseModel):
    id: str
    name: str
    parent: Optional[str] = None
    property: Optional[str] = None
    keywords: Optional[list[str]] = None


class TelegramUser(BaseModel):
    id: str
    telegram_id: str
    name: str
    username: Optional[str] = None
    active: bool = True


class Expense(BaseModel):
    id: Optional[str] = None
    amount: float
    description: str
    date: datetime
    category: Optional[str] = None
    property: Optional[str] = None
    payment_method: str  # card, transfer, cash
    telegram_user: Optional[str] = None
    registered_by: Optional[str] = None
    attachment: Optional[str] = None
    notes: Optional[str] = None
    reconciled: bool = False


class ExpenseCreate(BaseModel):
    amount: float
    description: str
    date: Optional[datetime] = None
    category: Optional[str] = None
    property: Optional[str] = None
    payment_method: str = "card"
    telegram_user: Optional[str] = None
    registered_by: Optional[str] = None
    notes: Optional[str] = None


class RecurringExpense(BaseModel):
    id: str
    name: str
    amount: float
    day_of_month: int
    category: Optional[str] = None
    property: Optional[str] = None
    payment_method: str
    active: bool = True


class BankTransaction(BaseModel):
    id: str
    date: datetime
    amount: float
    description: str
    source: str  # card, account
    expense: Optional[str] = None
    import_batch: Optional[str] = None


class AgentResponse(BaseModel):
    """Response from the AI agent after processing a message"""
    amount: Optional[float] = None
    description: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    property_id: Optional[str] = None
    property_name: Optional[str] = None
    payment_method: str = "card"
    confidence: float = 0.0
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    message: Optional[str] = None
