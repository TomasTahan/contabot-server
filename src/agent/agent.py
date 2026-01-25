"""
Expense tracking agent using Claude Agent SDK.
"""
import asyncio
import logging
from typing import Optional, Any
from datetime import datetime, date
from dataclasses import dataclass

from claude_agent_sdk import (
    ClaudeSDKClient,
    ClaudeAgentOptions,
    AssistantMessage,
    TextBlock,
    ResultMessage,
    CLINotFoundError,
    CLIConnectionError,
    tool,
    create_sdk_mcp_server,
)

from src.agent.prompts import SYSTEM_PROMPT, SYSTEM_PROMPT_WITH_IMAGE
from src.services.pocketbase_client import get_pocketbase_service
from src.models.schemas import ExpenseCreate

logger = logging.getLogger(__name__)


@dataclass
class UserSession:
    """Stores session info for a user, valid for one day."""
    session_id: str
    date: date
    client: Optional[ClaudeSDKClient] = None


# ============= TOOLS =============

@tool(
    name="register_expense",
    description="""Registra un nuevo gasto en la base de datos.

Parámetros:
- amount (requerido): Monto en pesos chilenos (CLP)
- description (requerido): Descripción breve del gasto
- registered_by (requerido): Username o nombre del usuario que registra (viene en el contexto [Usuario: xxx])
- category_id: ID de la categoría (usa get_categories para obtenerlo)
- property_id: ID de la propiedad si aplica
- payment_method: 'card', 'transfer', o 'cash'. Por defecto 'card'
- date: Fecha del gasto en formato ISO (YYYY-MM-DD). Si no se especifica, usa la fecha actual.
- notes: Notas adicionales""",
    input_schema={
        "amount": float,
        "description": str,
        "registered_by": str,
        "category_id": str,
        "property_id": str,
        "payment_method": str,
        "date": str,
        "notes": str,
    }
)
async def register_expense(args: dict[str, Any]) -> dict[str, Any]:
    """Register a new expense."""
    pb = get_pocketbase_service()

    # Parse date if provided, otherwise use now
    expense_date = datetime.now()
    if args.get("date"):
        try:
            expense_date = datetime.fromisoformat(args["date"])
        except ValueError:
            pass  # Keep default if parsing fails

    expense = ExpenseCreate(
        amount=args["amount"],
        description=args["description"],
        date=expense_date,
        category=args.get("category_id"),
        property=args.get("property_id"),
        payment_method=args.get("payment_method", "card"),
        registered_by=args.get("registered_by"),
        notes=args.get("notes"),
    )

    created = await pb.create_expense(expense)

    # Get names for response
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

    registered_by = args.get("registered_by", "")
    date_str = created.date.strftime("%d/%m/%Y") if created.date else "Hoy"

    return {
        "content": [{
            "type": "text",
            "text": f"""Gasto registrado exitosamente:
- ID: {created.id}
- Monto: ${created.amount:,.0f}
- Descripción: {created.description}
- Fecha: {date_str}
- Categoría: {category_name or 'Sin categoría'}
- Propiedad: {property_name or 'General'}
- Método de pago: {created.payment_method}
- Registrado por: {registered_by}"""
        }]
    }


@tool(
    name="update_expense",
    description="""Actualiza un gasto existente. Usa esto cuando el usuario quiera corregir o modificar un gasto ya registrado.

Parámetros:
- expense_id: ID del gasto a modificar. Usa 'last' para el último gasto del usuario.
- registered_by: Username del usuario (para buscar su último gasto si expense_id='last')
- amount: Nuevo monto (opcional)
- description: Nueva descripción (opcional)
- category_id: Nueva categoría (opcional)
- property_id: Nueva propiedad (opcional)
- payment_method: Nuevo método de pago - 'card', 'transfer', o 'cash' (opcional)
- date: Nueva fecha en formato ISO YYYY-MM-DD (opcional)
- notes: Nuevas notas (opcional)""",
    input_schema={
        "expense_id": str,
        "registered_by": str,
        "amount": float,
        "description": str,
        "category_id": str,
        "property_id": str,
        "payment_method": str,
        "date": str,
        "notes": str,
    }
)
async def update_expense(args: dict[str, Any]) -> dict[str, Any]:
    """Update an existing expense."""
    pb = get_pocketbase_service()

    expense_id = args.get("expense_id")
    registered_by = args.get("registered_by")

    # If expense_id is 'last', get the last expense for this user
    if expense_id == "last":
        last_expense = await pb.get_last_expense(registered_by=registered_by)
        if not last_expense:
            return {
                "content": [{
                    "type": "text",
                    "text": "No encontré gastos recientes tuyos para modificar."
                }]
            }
        expense_id = last_expense.id

    # Build update data
    update_data = {}

    if args.get("amount"):
        update_data["amount"] = args["amount"]
    if args.get("description"):
        update_data["description"] = args["description"]
    if args.get("category_id"):
        update_data["category"] = args["category_id"]
    if args.get("property_id"):
        update_data["property"] = args["property_id"]
    if args.get("payment_method"):
        update_data["payment_method"] = args["payment_method"]
    if args.get("date"):
        try:
            update_data["date"] = datetime.fromisoformat(args["date"]).isoformat()
        except ValueError:
            pass
    if args.get("notes"):
        update_data["notes"] = args["notes"]

    if not update_data:
        return {
            "content": [{
                "type": "text",
                "text": "No especificaste qué cambiar. Indica qué campo quieres modificar."
            }]
        }

    updated = await pb.update_expense(expense_id, update_data)

    # Get names for response
    category_name = None
    property_name = None

    if updated.category:
        cat = await pb.get_category_by_id(updated.category)
        if cat:
            category_name = cat.name

    if updated.property:
        prop = await pb.get_property_by_id(updated.property)
        if prop:
            property_name = prop.name

    # Build response showing what changed
    changes = []
    if args.get("amount"):
        changes.append(f"Monto: ${updated.amount:,.0f}")
    if args.get("payment_method"):
        changes.append(f"Método: {updated.payment_method}")
    if args.get("category_id"):
        changes.append(f"Categoría: {category_name}")
    if args.get("property_id"):
        changes.append(f"Propiedad: {property_name}")
    if args.get("date"):
        changes.append(f"Fecha: {updated.date.strftime('%d/%m/%Y')}")
    if args.get("description"):
        changes.append(f"Descripción: {updated.description}")

    return {
        "content": [{
            "type": "text",
            "text": f"✓ Gasto actualizado:\n" + "\n".join(f"- {c}" for c in changes)
        }]
    }


@tool(
    name="get_categories",
    description="Obtiene todas las categorías disponibles con sus IDs y jerarquía.",
    input_schema={}
)
async def get_categories(args: dict[str, Any]) -> dict[str, Any]:
    """Get all available categories."""
    pb = get_pocketbase_service()
    categories = await pb.get_categories_with_parents()

    # Format for display
    parents = [c for c in categories if not c["parent_id"]]

    lines = ["Categorías disponibles:\n"]
    for parent in parents:
        lines.append(f"**{parent['name']}** (ID: {parent['id']})")
        children = [c for c in categories if c["parent_id"] == parent["id"]]
        for child in children:
            prop_note = f" [Propiedad: {child.get('property', 'N/A')}]" if child.get("property") else ""
            lines.append(f"  └─ {child['name']} (ID: {child['id']}){prop_note}")
        lines.append("")

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(lines)
        }]
    }


@tool(
    name="get_properties",
    description="Obtiene las propiedades disponibles (Pirque, Maitri, Costa Mai).",
    input_schema={}
)
async def get_properties(args: dict[str, Any]) -> dict[str, Any]:
    """Get all available properties."""
    pb = get_pocketbase_service()
    properties = await pb.get_properties()

    lines = ["Propiedades disponibles:\n"]
    for prop in properties:
        lines.append(f"- **{prop.name}** (ID: {prop.id}): {prop.description or 'Sin descripción'}")

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(lines)
        }]
    }


@tool(
    name="create_category",
    description="""Crea una nueva categoría o subcategoría.

Parámetros:
- name (requerido): Nombre de la categoría
- parent_id: ID de la categoría padre (si es subcategoría). Usa get_categories para ver las existentes.
- keywords: Lista de palabras clave para auto-categorización (ej: ["farmacia", "remedios"])
- property_id: ID de la propiedad si la categoría es específica de una propiedad""",
    input_schema={
        "name": str,
        "parent_id": str,
        "keywords": list,
        "property_id": str,
    }
)
async def create_category(args: dict[str, Any]) -> dict[str, Any]:
    """Create a new category or subcategory."""
    pb = get_pocketbase_service()

    name = args["name"]
    parent_id = args.get("parent_id")
    keywords = args.get("keywords", [])
    property_id = args.get("property_id")

    # Validate parent exists if provided
    parent_name = None
    if parent_id:
        parent = await pb.get_category_by_id(parent_id)
        if not parent:
            return {
                "content": [{
                    "type": "text",
                    "text": f"Error: No existe una categoría con ID '{parent_id}'. Usa get_categories para ver las categorías disponibles."
                }]
            }
        parent_name = parent.name

    created = await pb.create_category(
        name=name,
        parent_id=parent_id,
        keywords=keywords,
        property_id=property_id,
    )

    # Build response
    if parent_name:
        full_name = f"{parent_name} > {name}"
        category_type = "Subcategoría"
    else:
        full_name = name
        category_type = "Categoría"

    response = f"""✓ {category_type} creada:
- Nombre: {full_name}
- ID: {created.id}"""

    if keywords:
        response += f"\n- Keywords: {', '.join(keywords)}"

    return {
        "content": [{
            "type": "text",
            "text": response
        }]
    }


@tool(
    name="get_recent_expenses",
    description="Obtiene los gastos recientes. Usa esto cuando el usuario pregunte qué ha gastado últimamente.",
    input_schema={
        "days": int,
        "limit": int,
    }
)
async def get_recent_expenses(args: dict[str, Any]) -> dict[str, Any]:
    """Get recent expenses."""
    pb = get_pocketbase_service()
    days = args.get("days", 7)
    limit = args.get("limit", 10)

    expenses = await pb.get_recent_expenses(days=days, limit=limit)
    categories = await pb.get_categories_with_parents()
    properties = await pb.get_properties()

    cat_lookup = {c["id"]: c["full_name"] for c in categories}
    prop_lookup = {p.id: p.name for p in properties}

    if not expenses:
        return {
            "content": [{
                "type": "text",
                "text": f"No hay gastos registrados en los últimos {days} días."
            }]
        }

    lines = [f"Últimos {len(expenses)} gastos (últimos {days} días):\n"]
    total = 0
    for exp in expenses:
        total += exp.amount
        date_str = exp.date.strftime("%d/%m") if exp.date else "?"
        cat_name = cat_lookup.get(exp.category, "Sin categoría") if exp.category else "Sin categoría"
        lines.append(f"- {date_str}: ${exp.amount:,.0f} - {exp.description} ({cat_name})")

    lines.append(f"\n**Total: ${total:,.0f}**")

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(lines)
        }]
    }


@tool(
    name="get_expense_summary",
    description="Obtiene un resumen de gastos por categoría. Usa 'week', 'month', o 'year' como período.",
    input_schema={
        "period": str,
    }
)
async def get_expense_summary(args: dict[str, Any]) -> dict[str, Any]:
    """Get expense summary by category."""
    from datetime import timedelta

    pb = get_pocketbase_service()
    period = args.get("period", "month")

    now = datetime.now()
    if period == "week":
        start_date = now - timedelta(days=7)
        period_name = "esta semana"
    elif period == "year":
        start_date = now.replace(month=1, day=1)
        period_name = "este año"
    else:
        start_date = now.replace(day=1)
        period_name = "este mes"

    summary = await pb.get_expense_summary(start_date=start_date, end_date=now)

    lines = [f"Resumen de gastos {period_name}:\n"]
    lines.append(f"**Total: ${summary['total']:,.0f}** ({summary['count']} gastos)\n")
    lines.append("Por categoría:")

    for cat_name, amount in summary["by_category"].items():
        percentage = (amount / summary["total"] * 100) if summary["total"] > 0 else 0
        lines.append(f"  - {cat_name}: ${amount:,.0f} ({percentage:.1f}%)")

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(lines)
        }]
    }


# ============= DEBT TOOLS =============

@tool(
    name="register_debt",
    description="""Registra una deuda (nos deben o debemos).

Parámetros:
- amount (requerido): Monto de la deuda en CLP
- person (requerido): Nombre de la persona que debe o a quien debemos
- debt_type (requerido): 'receivable' (nos deben) o 'payable' (debemos)
- description (requerido): Descripción de la deuda
- registered_by (requerido): Username o nombre del usuario que registra (viene en el contexto [Usuario: xxx])
- expense_id: ID del gasto asociado (opcional, si la deuda viene de un gasto)
- notes: Notas adicionales""",
    input_schema={
        "amount": float,
        "person": str,
        "debt_type": str,
        "description": str,
        "registered_by": str,
        "expense_id": str,
        "notes": str,
    }
)
async def register_debt(args: dict[str, Any]) -> dict[str, Any]:
    """Register a new debt."""
    pb = get_pocketbase_service()

    debt_data = {
        "amount": args["amount"],
        "person": args["person"],
        "type": args["debt_type"],
        "description": args["description"],
        "status": "pending",
        "paid_amount": 0,
        "registered_by": args.get("registered_by"),
    }

    if args.get("expense_id"):
        debt_data["expense"] = args["expense_id"]
    if args.get("notes"):
        debt_data["notes"] = args["notes"]

    await pb.create_debt(debt_data)

    debt_type_text = "nos debe" if args["debt_type"] == "receivable" else "debemos a"

    return {
        "content": [{
            "type": "text",
            "text": f"""Deuda registrada:
- {args['person']} {debt_type_text} ${args['amount']:,.0f}
- Motivo: {args['description']}
- Estado: Pendiente"""
        }]
    }


@tool(
    name="get_pending_debts",
    description="Obtiene las deudas pendientes. Usa 'receivable' para ver quién nos debe, 'payable' para ver a quién debemos, o 'all' para ver todas.",
    input_schema={
        "debt_type": str,
    }
)
async def get_pending_debts(args: dict[str, Any]) -> dict[str, Any]:
    """Get pending debts."""
    pb = get_pocketbase_service()
    debt_type = args.get("debt_type", "all")

    debts = await pb.get_pending_debts(debt_type)

    if not debts:
        if debt_type == "receivable":
            return {"content": [{"type": "text", "text": "No hay deudas pendientes por cobrar."}]}
        elif debt_type == "payable":
            return {"content": [{"type": "text", "text": "No hay deudas pendientes por pagar."}]}
        else:
            return {"content": [{"type": "text", "text": "No hay deudas pendientes."}]}

    receivables = [d for d in debts if d["type"] == "receivable"]
    payables = [d for d in debts if d["type"] == "payable"]

    lines = []

    if receivables and debt_type in ["receivable", "all"]:
        total_receivable = sum(d["amount"] - d.get("paid_amount", 0) for d in receivables)
        lines.append(f"💰 NOS DEBEN: ${total_receivable:,.0f}")
        for d in receivables:
            pending = d["amount"] - d.get("paid_amount", 0)
            lines.append(f"  - {d['person']}: ${pending:,.0f} ({d['description']})")
        lines.append("")

    if payables and debt_type in ["payable", "all"]:
        total_payable = sum(d["amount"] - d.get("paid_amount", 0) for d in payables)
        lines.append(f"💸 DEBEMOS: ${total_payable:,.0f}")
        for d in payables:
            pending = d["amount"] - d.get("paid_amount", 0)
            lines.append(f"  - {d['person']}: ${pending:,.0f} ({d['description']})")

    return {
        "content": [{
            "type": "text",
            "text": "\n".join(lines)
        }]
    }


@tool(
    name="mark_debt_paid",
    description="""Marca una deuda como pagada (total o parcialmente).

Parámetros:
- person (requerido): Nombre de la persona
- amount: Monto pagado (si es parcial). Si no se especifica, se marca como pagada completamente.
- debt_type: 'receivable' o 'payable' para filtrar si hay varias deudas con la misma persona""",
    input_schema={
        "person": str,
        "amount": float,
        "debt_type": str,
    }
)
async def mark_debt_paid(args: dict[str, Any]) -> dict[str, Any]:
    """Mark a debt as paid."""
    pb = get_pocketbase_service()

    person = args["person"]
    amount = args.get("amount")
    debt_type = args.get("debt_type")

    result = await pb.mark_debt_paid(person, amount, debt_type)

    if not result:
        return {
            "content": [{
                "type": "text",
                "text": f"No encontré deudas pendientes con {person}."
            }]
        }

    if result["status"] == "paid":
        return {
            "content": [{
                "type": "text",
                "text": f"✓ Deuda con {person} marcada como PAGADA completamente."
            }]
        }
    else:
        remaining = result["amount"] - result["paid_amount"]
        return {
            "content": [{
                "type": "text",
                "text": f"✓ Pago parcial registrado. {person} aún debe ${remaining:,.0f}"
            }]
        }


# Create MCP server with tools
expense_mcp_server = create_sdk_mcp_server(
    name="expenses",
    version="1.0.0",
    tools=[
        register_expense,
        update_expense,
        get_categories,
        get_properties,
        create_category,
        get_recent_expenses,
        get_expense_summary,
        register_debt,
        get_pending_debts,
        mark_debt_paid,
    ]
)


class ExpenseAgent:
    """Agent for processing expense messages from Telegram using ClaudeSDKClient."""

    def __init__(self):
        # Base options for the agent (without resume)
        self.base_options = {
            "system_prompt": SYSTEM_PROMPT,
            "model": "claude-sonnet-4-5-20250929",
            "mcp_servers": {"expenses": expense_mcp_server},
            "allowed_tools": [
                "mcp__expenses__register_expense",
                "mcp__expenses__update_expense",
                "mcp__expenses__get_categories",
                "mcp__expenses__get_properties",
                "mcp__expenses__create_category",
                "mcp__expenses__get_recent_expenses",
                "mcp__expenses__get_expense_summary",
                "mcp__expenses__register_debt",
                "mcp__expenses__get_pending_debts",
                "mcp__expenses__mark_debt_paid",
            ],
            "permission_mode": "acceptEdits",
        }

        # User sessions: telegram_user_id -> UserSession
        self.sessions: dict[str, UserSession] = {}

    def _get_valid_session(self, telegram_user_id: str) -> Optional[UserSession]:
        """Get a valid session for today, or None if expired/doesn't exist."""
        if telegram_user_id not in self.sessions:
            return None

        session = self.sessions[telegram_user_id]
        today = date.today()

        # Check if session is from today
        if session.date != today:
            logger.info(f"Session for user {telegram_user_id} expired (was from {session.date})")
            # Clean up old session
            if session.client:
                asyncio.create_task(self._disconnect_client(session.client))
            del self.sessions[telegram_user_id]
            return None

        return session

    async def _disconnect_client(self, client: ClaudeSDKClient) -> None:
        """Disconnect a client safely."""
        try:
            await client.disconnect()
        except Exception as e:
            logger.warning(f"Error disconnecting client: {e}")

    async def _create_new_session(self, telegram_user_id: str) -> ClaudeSDKClient:
        """Create a new session without resume."""
        options = ClaudeAgentOptions(**self.base_options)
        client = ClaudeSDKClient(options=options)
        await client.connect()
        logger.info(f"Created new session for user {telegram_user_id}")
        return client

    async def _resume_session(self, telegram_user_id: str, session_id: str) -> ClaudeSDKClient:
        """Resume an existing session."""
        options = ClaudeAgentOptions(
            **self.base_options,
            resume=session_id,
        )
        client = ClaudeSDKClient(options=options)
        await client.connect()
        logger.info(f"Resumed session {session_id} for user {telegram_user_id}")
        return client

    async def process_message(
        self,
        text: str,
        telegram_user_id: str,
        telegram_username: Optional[str] = None,
        image_base64: Optional[str] = None,
        referenced_expense_id: Optional[str] = None,
    ) -> str:
        """
        Process a message from a Telegram user.
        Sessions persist for the entire day and resume automatically.
        """
        # Build the prompt with user context and current date
        today = datetime.now()
        date_context = today.strftime("%Y-%m-%d")
        weekday_names = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
        weekday = weekday_names[today.weekday()]

        user_context = f"[Usuario: {telegram_username or telegram_user_id}] [Fecha actual: {date_context} ({weekday})]"

        if referenced_expense_id:
            user_context += f" [Gasto referenciado: {referenced_expense_id}]"

        user_context += "\n\n"

        if image_base64:
            prompt_text = f"""{user_context}[El usuario envió una imagen de una boleta junto con este mensaje]

Mensaje del usuario: {text}

Analiza la imagen de la boleta y el mensaje para registrar el gasto."""
        else:
            prompt_text = f"{user_context}{text}"

        try:
            # Check for existing valid session
            existing_session = self._get_valid_session(telegram_user_id)

            if existing_session and existing_session.client:
                # Reuse existing connected client
                client = existing_session.client
                logger.info(f"Reusing existing client for user {telegram_user_id}")
            elif existing_session and existing_session.session_id:
                # Resume from session_id (client was disconnected but session_id saved)
                client = await self._resume_session(telegram_user_id, existing_session.session_id)
                existing_session.client = client
            else:
                # Create brand new session
                client = await self._create_new_session(telegram_user_id)
                self.sessions[telegram_user_id] = UserSession(
                    session_id="",  # Will be updated after first response
                    date=date.today(),
                    client=client,
                )

            # Send query
            await client.query(prompt_text)

            # Collect response
            response_parts = []
            session_id = None

            async for message in client.receive_response():
                if isinstance(message, AssistantMessage):
                    for block in message.content:
                        if isinstance(block, TextBlock):
                            response_parts.append(block.text)
                elif isinstance(message, ResultMessage):
                    # Capture the session_id for future resume
                    session_id = message.session_id
                    logger.info(f"Got session_id: {session_id} for user {telegram_user_id}")

            # Update session with the session_id
            if session_id and telegram_user_id in self.sessions:
                self.sessions[telegram_user_id].session_id = session_id

            return "".join(response_parts) if response_parts else "No pude procesar tu mensaje."

        except CLINotFoundError:
            return "Error: Claude Code CLI no está instalado. Contacta al administrador."
        except CLIConnectionError:
            # Remove the faulty session and suggest retry
            if telegram_user_id in self.sessions:
                session = self.sessions[telegram_user_id]
                if session.client:
                    await self._disconnect_client(session.client)
                del self.sessions[telegram_user_id]
            return "Error: No se pudo conectar con el agente. Intenta de nuevo."
        except Exception as e:
            import traceback
            logger.error(f"Error processing message: {e}")
            logger.error(f"Traceback: {traceback.format_exc()}")
            return f"Error: {str(e)}"


# Singleton instance
_agent: Optional[ExpenseAgent] = None


def get_expense_agent() -> ExpenseAgent:
    """Get or create the expense agent singleton."""
    global _agent
    if _agent is None:
        _agent = ExpenseAgent()
    return _agent
