from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
from typing import Optional
from datetime import datetime, timezone
import logging

from src.config import get_settings
from src.models.schemas import (
    Property,
    Category,
    TelegramUser,
    Expense,
    ExpenseCreate,
)

logger = logging.getLogger(__name__)


class PocketBaseService:
    def __init__(self):
        settings = get_settings()
        self.client = PocketBase(settings.pocketbase_url)
        self._admin_email = settings.pocketbase_admin_email
        self._admin_password = settings.pocketbase_admin_password
        self._auth_timestamp: Optional[datetime] = None
        # Re-authenticate every 30 minutes to avoid token expiration
        self._auth_ttl_seconds = 30 * 60

    def _is_auth_valid(self) -> bool:
        """Check if authentication is still valid based on timestamp."""
        if self._auth_timestamp is None:
            return False
        elapsed = (datetime.now(timezone.utc) - self._auth_timestamp).total_seconds()
        return elapsed < self._auth_ttl_seconds

    async def _authenticate(self):
        """Authenticate with PocketBase as superuser."""
        try:
            self.client.collection("_superusers").auth_with_password(
                self._admin_email, self._admin_password
            )
            self._auth_timestamp = datetime.now(timezone.utc)
            logger.info("Authenticated with PocketBase")
        except ClientResponseError as e:
            logger.error(f"Failed to authenticate with PocketBase: {e}")
            self._auth_timestamp = None
            raise

    async def _ensure_authenticated(self):
        """Ensure we have a valid authentication token."""
        if not self._is_auth_valid():
            await self._authenticate()

    async def _execute_with_retry(self, operation, *args, **kwargs):
        """Execute an operation with automatic re-authentication on permission errors."""
        try:
            await self._ensure_authenticated()
            return operation(*args, **kwargs)
        except ClientResponseError as e:
            # Check if it's a permission/auth error (403 or 401)
            if e.status in [401, 403]:
                logger.warning(f"Auth error ({e.status}), re-authenticating...")
                self._auth_timestamp = None  # Force re-auth
                await self._authenticate()
                # Retry the operation
                return operation(*args, **kwargs)
            raise

    # Properties
    async def get_properties(self) -> list[Property]:
        await self._ensure_authenticated()
        records = self.client.collection("properties").get_full_list()
        return [Property(**r.__dict__) for r in records]

    async def get_property_by_id(self, property_id: str) -> Optional[Property]:
        await self._ensure_authenticated()
        try:
            record = self.client.collection("properties").get_one(property_id)
            return Property(**record.__dict__)
        except ClientResponseError:
            return None

    # Categories
    async def get_categories(self) -> list[Category]:
        await self._ensure_authenticated()
        records = self.client.collection("categories").get_full_list()
        return [Category(**r.__dict__) for r in records]

    async def get_category_by_id(self, category_id: str) -> Optional[Category]:
        await self._ensure_authenticated()
        try:
            record = self.client.collection("categories").get_one(category_id)
            return Category(**record.__dict__)
        except ClientResponseError:
            return None

    async def get_categories_with_parents(self) -> list[dict]:
        """Get all categories with their parent names for display"""
        await self._ensure_authenticated()
        categories = await self.get_categories()

        # Build lookup
        cat_lookup = {c.id: c for c in categories}

        result = []
        for cat in categories:
            parent_name = None
            if cat.parent:
                parent = cat_lookup.get(cat.parent)
                if parent:
                    parent_name = parent.name

            result.append({
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent,
                "parent_name": parent_name,
                "property": cat.property,
                "keywords": cat.keywords,
                "full_name": f"{parent_name} > {cat.name}" if parent_name else cat.name
            })

        return result

    async def create_category(
        self,
        name: str,
        parent_id: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        property_id: Optional[str] = None,
    ) -> Category:
        """Create a new category or subcategory"""
        data = {
            "name": name,
        }
        if parent_id:
            data["parent"] = parent_id
        if keywords:
            data["keywords"] = keywords
        if property_id:
            data["property"] = property_id

        record = await self._execute_with_retry(
            self.client.collection("categories").create, data
        )
        return Category(**record.__dict__)

    # Telegram Users
    async def get_telegram_user(self, telegram_id: str) -> Optional[TelegramUser]:
        await self._ensure_authenticated()
        try:
            records = self.client.collection("telegram_users").get_list(
                1, 1, {"filter": f'telegram_id = "{telegram_id}"'}
            )
            if records.items:
                return TelegramUser(**records.items[0].__dict__)
            return None
        except ClientResponseError:
            return None

    async def create_telegram_user(
        self, telegram_id: str, name: str, username: Optional[str] = None
    ) -> TelegramUser:
        data = {
            "telegram_id": telegram_id,
            "name": name,
            "username": username,
            "active": True,
        }
        record = await self._execute_with_retry(
            self.client.collection("telegram_users").create, data
        )
        return TelegramUser(**record.__dict__)

    async def get_or_create_telegram_user(
        self, telegram_id: str, name: str, username: Optional[str] = None
    ) -> TelegramUser:
        user = await self.get_telegram_user(telegram_id)
        if user:
            return user
        return await self.create_telegram_user(telegram_id, name, username)

    # Expenses
    async def create_expense(self, expense: ExpenseCreate, attachment_path: Optional[str] = None) -> Expense:
        data = {
            "amount": expense.amount,
            "description": expense.description,
            "date": (expense.date or datetime.now()).isoformat(),
            "category": expense.category,
            "property": expense.property,
            "payment_method": expense.payment_method,
            "telegram_user": expense.telegram_user,
            "registered_by": expense.registered_by,
            "notes": expense.notes,
            "reconciled": False,
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        if attachment_path:
            # Upload file - need special handling
            await self._ensure_authenticated()
            try:
                with open(attachment_path, "rb") as f:
                    record = self.client.collection("expenses").create(
                        data, files={"attachment": f}
                    )
            except ClientResponseError as e:
                if e.status in [401, 403]:
                    self._auth_timestamp = None
                    await self._authenticate()
                    with open(attachment_path, "rb") as f:
                        record = self.client.collection("expenses").create(
                            data, files={"attachment": f}
                        )
                else:
                    raise
        else:
            record = await self._execute_with_retry(
                self.client.collection("expenses").create, data
            )

        return Expense(**record.__dict__)

    async def get_expenses(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        category_id: Optional[str] = None,
        property_id: Optional[str] = None,
        limit: int = 50,
    ) -> list[Expense]:
        await self._ensure_authenticated()

        filters = []
        if start_date:
            filters.append(f'date >= "{start_date.isoformat()}"')
        if end_date:
            filters.append(f'date <= "{end_date.isoformat()}"')
        if category_id:
            filters.append(f'category = "{category_id}"')
        if property_id:
            filters.append(f'property = "{property_id}"')

        filter_str = " && ".join(filters) if filters else ""

        records = self.client.collection("expenses").get_list(
            1, limit, {"filter": filter_str, "sort": "-date"} if filter_str else {"sort": "-date"}
        )

        return [Expense(**r.__dict__) for r in records.items]

    async def get_recent_expenses(self, days: int = 7, limit: int = 20) -> list[Expense]:
        from datetime import timedelta
        start_date = datetime.now() - timedelta(days=days)
        return await self.get_expenses(start_date=start_date, limit=limit)

    async def get_last_expense(self, registered_by: Optional[str] = None) -> Optional[Expense]:
        """Get the most recent expense, optionally filtered by who registered it"""
        await self._ensure_authenticated()

        filter_str = f'registered_by = "{registered_by}"' if registered_by else ""

        records = self.client.collection("expenses").get_list(
            1, 1, {"filter": filter_str, "sort": "-created"} if filter_str else {"sort": "-created"}
        )

        if records.items:
            return Expense(**records.items[0].__dict__)
        return None

    async def update_expense(self, expense_id: str, data: dict) -> Expense:
        """Update an existing expense"""
        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        record = await self._execute_with_retry(
            self.client.collection("expenses").update, expense_id, data
        )
        return Expense(**record.__dict__)

    async def upload_attachment(self, expense_id: str, file_path: str) -> str:
        """Upload an attachment to an existing expense"""
        await self._ensure_authenticated()

        with open(file_path, "rb") as f:
            record = self.client.collection("expenses").update(
                expense_id, files={"attachment": f}
            )

        return record.attachment

    async def get_expense_summary(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> dict:
        """Get a summary of expenses by category"""
        expenses = await self.get_expenses(start_date=start_date, end_date=end_date, limit=1000)
        categories = await self.get_categories_with_parents()

        cat_lookup = {c["id"]: c for c in categories}

        summary = {}
        total = 0

        for exp in expenses:
            total += exp.amount
            cat_id = exp.category
            if cat_id:
                cat = cat_lookup.get(cat_id, {"full_name": "Sin categoría"})
                cat_name = cat["full_name"]
            else:
                cat_name = "Sin categoría"

            if cat_name not in summary:
                summary[cat_name] = 0
            summary[cat_name] += exp.amount

        return {
            "total": total,
            "by_category": dict(sorted(summary.items(), key=lambda x: x[1], reverse=True)),
            "count": len(expenses),
        }

    # Debts
    async def create_debt(self, debt_data: dict) -> dict:
        """Create a new debt record"""
        record = await self._execute_with_retry(
            self.client.collection("debts").create, debt_data
        )
        return record.__dict__

    async def get_pending_debts(self, debt_type: str = "all") -> list[dict]:
        """Get pending debts filtered by type"""
        await self._ensure_authenticated()

        filters = ['status != "paid"']
        if debt_type == "receivable":
            filters.append('type = "receivable"')
        elif debt_type == "payable":
            filters.append('type = "payable"')

        filter_str = " && ".join(filters)

        records = self.client.collection("debts").get_list(
            1, 100, {"filter": filter_str, "sort": "-created"}
        )

        return [r.__dict__ for r in records.items]

    async def mark_debt_paid(
        self, person: str, amount: Optional[float] = None, debt_type: Optional[str] = None
    ) -> Optional[dict]:
        """Mark a debt as paid (fully or partially)"""
        await self._ensure_authenticated()

        # Find the debt
        filters = [f'person ~ "{person}"', 'status != "paid"']
        if debt_type:
            filters.append(f'type = "{debt_type}"')

        filter_str = " && ".join(filters)

        records = self.client.collection("debts").get_list(
            1, 1, {"filter": filter_str}
        )

        if not records.items:
            return None

        debt = records.items[0]
        current_paid = debt.paid_amount or 0

        if amount is None:
            # Mark as fully paid
            new_paid = debt.amount
            new_status = "paid"
        else:
            new_paid = current_paid + amount
            if new_paid >= debt.amount:
                new_paid = debt.amount
                new_status = "paid"
            else:
                new_status = "partial"

        updated = await self._execute_with_retry(
            self.client.collection("debts").update,
            debt.id,
            {"paid_amount": new_paid, "status": new_status}
        )

        return updated.__dict__

    async def get_debt_by_id(self, debt_id: str) -> Optional[dict]:
        """Get a debt by ID"""
        await self._ensure_authenticated()
        try:
            record = self.client.collection("debts").get_one(debt_id)
            return record.__dict__
        except ClientResponseError:
            return None

    # Message-Expense Links
    async def save_message_expense_link(
        self, telegram_message_id: int, chat_id: int, expense_id: str
    ) -> None:
        """Save a link between a Telegram message and an expense"""
        data = {
            "telegram_message_id": telegram_message_id,
            "chat_id": chat_id,
            "expense": expense_id,
        }
        await self._execute_with_retry(
            self.client.collection("message_expense_links").create, data
        )

    async def get_expense_by_message_id(
        self, telegram_message_id: int, chat_id: int
    ) -> Optional[Expense]:
        """Get an expense linked to a Telegram message"""
        await self._ensure_authenticated()
        try:
            records = self.client.collection("message_expense_links").get_list(
                1, 1,
                {"filter": f'telegram_message_id = {telegram_message_id} && chat_id = {chat_id}'}
            )
            if records.items:
                expense_id = records.items[0].expense
                return await self.get_expense_by_id(expense_id)
            return None
        except ClientResponseError:
            return None

    async def get_expense_by_id(self, expense_id: str) -> Optional[Expense]:
        """Get an expense by ID"""
        await self._ensure_authenticated()
        try:
            record = self.client.collection("expenses").get_one(expense_id)
            return Expense(**record.__dict__)
        except ClientResponseError:
            return None


# Singleton instance
_pb_service: Optional[PocketBaseService] = None


def get_pocketbase_service() -> PocketBaseService:
    global _pb_service
    if _pb_service is None:
        _pb_service = PocketBaseService()
    return _pb_service
