from pocketbase import PocketBase
from pocketbase.utils import ClientResponseError
from typing import Optional
from datetime import datetime
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
        self._authenticated = False
        self._admin_email = settings.pocketbase_admin_email
        self._admin_password = settings.pocketbase_admin_password

    async def _ensure_authenticated(self):
        if not self._authenticated:
            try:
                self.client.collection("_superusers").auth_with_password(
                    self._admin_email, self._admin_password
                )
                self._authenticated = True
                logger.info("Authenticated with PocketBase")
            except ClientResponseError as e:
                logger.error(f"Failed to authenticate with PocketBase: {e}")
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
        await self._ensure_authenticated()
        data = {
            "telegram_id": telegram_id,
            "name": name,
            "username": username,
            "active": True,
        }
        record = self.client.collection("telegram_users").create(data)
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
        await self._ensure_authenticated()

        data = {
            "amount": expense.amount,
            "description": expense.description,
            "date": (expense.date or datetime.now()).isoformat(),
            "category": expense.category,
            "property": expense.property,
            "payment_method": expense.payment_method,
            "telegram_user": expense.telegram_user,
            "notes": expense.notes,
            "reconciled": False,
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        if attachment_path:
            # Upload file
            with open(attachment_path, "rb") as f:
                record = self.client.collection("expenses").create(
                    data, files={"attachment": f}
                )
        else:
            record = self.client.collection("expenses").create(data)

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


# Singleton instance
_pb_service: Optional[PocketBaseService] = None


def get_pocketbase_service() -> PocketBaseService:
    global _pb_service
    if _pb_service is None:
        _pb_service = PocketBaseService()
    return _pb_service
