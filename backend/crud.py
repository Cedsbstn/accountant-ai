from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func, cast, JSON # Import func for aggregations
from typing import List, Optional
from datetime import date

from . import models, schemas # Use relative imports within the package

# --- Invoice CRUD ---

async def create_invoice(db: AsyncSession, invoice: schemas.InvoiceDataCreate) -> models.Invoice:
    """Creates a new invoice record in the database."""
    db_invoice = models.Invoice(**invoice.dict())
    db.add(db_invoice)
    # Note: Commit is handled by the get_db dependency
    await db.flush() # Flush to get the ID if needed before commit
    await db.refresh(db_invoice) # Refresh to load defaults/generated values
    return db_invoice

async def get_invoice(db: AsyncSession, invoice_id: str) -> Optional[models.Invoice]:
    """Retrieves an invoice by its ID."""
    result = await db.execute(select(models.Invoice).where(models.Invoice.id == invoice_id))
    return result.scalar_one_or_none()

async def update_invoice_status(db: AsyncSession, invoice_id: str, status: str, error_message: Optional[str] = None) -> Optional[models.Invoice]:
    """Updates the status and optionally error message of an invoice."""
    stmt = (
        update(models.Invoice)
        .where(models.Invoice.id == invoice_id)
        .values(processingStatus=status, errorMessage=error_message)
        .returning(models.Invoice) # Return the updated model
    )
    result = await db.execute(stmt)
    # Note: Commit handled by get_db
    return result.scalar_one_or_none()

# Add get_invoices, delete_invoice etc. as needed

# --- Transaction CRUD ---

async def create_transaction(db: AsyncSession, transaction: schemas.TransactionCreate) -> models.Transaction:
    """Creates a new transaction record."""
    # Ensure tags are stored correctly if passed as list
    db_transaction = models.Transaction(**transaction.dict())
    db.add(db_transaction)
    await db.flush()
    await db.refresh(db_transaction)
    return db_transaction

async def get_transactions_by_date_range(db: AsyncSession, start_date: date, end_date: date) -> List[models.Transaction]:
    """Retrieves transactions within a specific date range."""
    stmt = select(models.Transaction).where(
        models.Transaction.transactionDate >= start_date,
        models.Transaction.transactionDate <= end_date
    ).order_by(models.Transaction.transactionDate)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_transactions_by_tag(db: AsyncSession, tag: str, start_date: date, end_date: date) -> List[models.Transaction]:
    """Retrieves transactions with a specific tag within a date range."""
    # Using JSON_CONTAINS for MySQL JSON array search
    stmt = select(models.Transaction).where(
        models.Transaction.transactionDate >= start_date,
        models.Transaction.transactionDate <= end_date,
        func.json_contains(models.Transaction.tags, cast(f'"{tag}"', JSON)) # Note: requires proper JSON casting/formatting
    ).order_by(models.Transaction.transactionDate)
    result = await db.execute(stmt)
    return result.scalars().all()

async def add_tag_to_transaction(db: AsyncSession, transaction_id: str, tag: str) -> Optional[models.Transaction]:
    """Adds a tag to a transaction's JSON tag list if it doesn't exist."""
    transaction = await db.get(models.Transaction, transaction_id) # Use db.get for PK lookup
    if not transaction:
        return None

    current_tags = transaction.tags if isinstance(transaction.tags, list) else []
    if tag not in current_tags:
        new_tags = current_tags + [tag]
        # Update the JSON field
        stmt = (
            update(models.Transaction)
            .where(models.Transaction.id == transaction_id)
            .values(tags=new_tags)
            .returning(models.Transaction)
        )
        result = await db.execute(stmt)
        # Note: Commit handled by get_db
        return result.scalar_one_or_none()
    return transaction # Return unmodified if tag exists

# --- Budget CRUD ---

async def create_budget(db: AsyncSession, budget: schemas.BudgetCreate) -> models.Budget:
    """Creates a new budget record."""
    db_budget = models.Budget(**budget.dict())
    db.add(db_budget)
    await db.flush()
    await db.refresh(db_budget)
    return db_budget

async def get_budgets_by_period(db: AsyncSession, period_value: str) -> List[models.Budget]:
    """Retrieves budgets for a specific period value."""
    stmt = select(models.Budget).where(models.Budget.periodValue == period_value)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_budget(db: AsyncSession, budget_id: str) -> Optional[models.Budget]:
    """Retrieves a budget by ID."""
    return await db.get(models.Budget, budget_id) # Use db.get for PK lookup

# --- Aggregation Examples ---

async def get_spending_by_category_for_period(db: AsyncSession, start_date: date, end_date: date) -> dict:
    """Calculates total spending per GL account within a date range."""
    stmt = (
        select(
            models.Transaction.glAccount,
            func.sum(models.Transaction.amount).label("total_spent")
        )
        .where(
            models.Transaction.transactionDate >= start_date,
            models.Transaction.transactionDate <= end_date,
            # Add filter for expense accounts if needed
            # models.Transaction.glAccount.in_(EXPENSE_ACCOUNTS)
        )
        .group_by(models.Transaction.glAccount)
    )
    result = await db.execute(stmt)
    # Returns list of Row objects [(glAccount, total_spent), ...]
    spending_data = {row.glAccount: row.total_spent for row in result.all()}
    return spending_data# backend/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func, cast, JSON # Import func for aggregations
from typing import List, Optional
from datetime import date

from . import models, schemas # Use relative imports within the package

# --- Invoice CRUD ---

async def create_invoice(db: AsyncSession, invoice: schemas.InvoiceDataCreate) -> models.Invoice:
    """Creates a new invoice record in the database."""
    db_invoice = models.Invoice(**invoice.dict())
    db.add(db_invoice)
    # Note: Commit is handled by the get_db dependency
    await db.flush() # Flush to get the ID if needed before commit
    await db.refresh(db_invoice) # Refresh to load defaults/generated values
    return db_invoice

async def get_invoice(db: AsyncSession, invoice_id: str) -> Optional[models.Invoice]:
    """Retrieves an invoice by its ID."""
    result = await db.execute(select(models.Invoice).where(models.Invoice.id == invoice_id))
    return result.scalar_one_or_none()

async def update_invoice_status(db: AsyncSession, invoice_id: str, status: str, error_message: Optional[str] = None) -> Optional[models.Invoice]:
    """Updates the status and optionally error message of an invoice."""
    stmt = (
        update(models.Invoice)
        .where(models.Invoice.id == invoice_id)
        .values(processingStatus=status, errorMessage=error_message)
        .returning(models.Invoice) # Return the updated model
    )
    result = await db.execute(stmt)
    # Note: Commit handled by get_db
    return result.scalar_one_or_none()

# Add get_invoices, delete_invoice etc. as needed

# --- Transaction CRUD ---

async def create_transaction(db: AsyncSession, transaction: schemas.TransactionCreate) -> models.Transaction:
    """Creates a new transaction record."""
    # Ensure tags are stored correctly if passed as list
    db_transaction = models.Transaction(**transaction.dict())
    db.add(db_transaction)
    await db.flush()
    await db.refresh(db_transaction)
    return db_transaction

async def get_transactions_by_date_range(db: AsyncSession, start_date: date, end_date: date) -> List[models.Transaction]:
    """Retrieves transactions within a specific date range."""
    stmt = select(models.Transaction).where(
        models.Transaction.transactionDate >= start_date,
        models.Transaction.transactionDate <= end_date
    ).order_by(models.Transaction.transactionDate)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_transactions_by_tag(db: AsyncSession, tag: str, start_date: date, end_date: date) -> List[models.Transaction]:
    """Retrieves transactions with a specific tag within a date range."""
    # Using JSON_CONTAINS for MySQL JSON array search
    stmt = select(models.Transaction).where(
        models.Transaction.transactionDate >= start_date,
        models.Transaction.transactionDate <= end_date,
        func.json_contains(models.Transaction.tags, cast(f'"{tag}"', JSON)) # Note: requires proper JSON casting/formatting
    ).order_by(models.Transaction.transactionDate)
    result = await db.execute(stmt)
    return result.scalars().all()

async def add_tag_to_transaction(db: AsyncSession, transaction_id: str, tag: str) -> Optional[models.Transaction]:
    """Adds a tag to a transaction's JSON tag list if it doesn't exist."""
    transaction = await db.get(models.Transaction, transaction_id) # Use db.get for PK lookup
    if not transaction:
        return None

    current_tags = transaction.tags if isinstance(transaction.tags, list) else []
    if tag not in current_tags:
        new_tags = current_tags + [tag]
        # Update the JSON field
        stmt = (
            update(models.Transaction)
            .where(models.Transaction.id == transaction_id)
            .values(tags=new_tags)
            .returning(models.Transaction)
        )
        result = await db.execute(stmt)
        # Note: Commit handled by get_db
        return result.scalar_one_or_none()
    return transaction # Return unmodified if tag exists

# --- Budget CRUD ---

async def create_budget(db: AsyncSession, budget: schemas.BudgetCreate) -> models.Budget:
    """Creates a new budget record."""
    db_budget = models.Budget(**budget.dict())
    db.add(db_budget)
    await db.flush()
    await db.refresh(db_budget)
    return db_budget

async def get_budgets_by_period(db: AsyncSession, period_value: str) -> List[models.Budget]:
    """Retrieves budgets for a specific period value."""
    stmt = select(models.Budget).where(models.Budget.periodValue == period_value)
    result = await db.execute(stmt)
    return result.scalars().all()

async def get_budget(db: AsyncSession, budget_id: str) -> Optional[models.Budget]:
    """Retrieves a budget by ID."""
    return await db.get(models.Budget, budget_id) # Use db.get for PK lookup

# --- Aggregation Examples ---

async def get_spending_by_category_for_period(db: AsyncSession, start_date: date, end_date: date) -> dict:
    """Calculates total spending per GL account within a date range."""
    stmt = (
        select(
            models.Transaction.glAccount,
            func.sum(models.Transaction.amount).label("total_spent")
        )
        .where(
            models.Transaction.transactionDate >= start_date,
            models.Transaction.transactionDate <= end_date,
            # Add filter for expense accounts if needed
            # models.Transaction.glAccount.in_(EXPENSE_ACCOUNTS)
        )
        .group_by(models.Transaction.glAccount)
    )
    result = await db.execute(stmt)
    # Returns list of Row objects [(glAccount, total_spent), ...]
    spending_data = {row.glAccount: row.total_spent for row in result.all()}
    return spending_data