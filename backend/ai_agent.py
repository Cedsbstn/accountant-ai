import os
import io
import uuid
import logging
import asyncio
from datetime import date, datetime, timedelta
import re
from typing import List, Optional, Dict, Any, Tuple
from collections import defaultdict

# --- Core Dependencies ---
import uvicorn
from fastapi import FastAPI, File, UploadFile, HTTPException, Form, Query, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
import easyocr
from PIL import Image
from pdf2image import convert_from_bytes

# --- Project Imports ---
from . import crud, models, schemas # Use relative imports
from .database import engine, Base # Import engine/Base if needed for migrations setup
from .dependencies import get_db # Import the dependency

# --- Configuration & Initialization ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Initialize EasyOCR Reader (as before)
ocr_reader = easyocr.Reader(['en'], gpu=False)
logger.info("EasyOCR Reader initialized using CPU.")

# --- FastAPI App Setup ---
app = FastAPI(
    title="AI Accounting Agent (SQLAlchemy+MySQL)",
    description="Processes invoices using EasyOCR, stores data in MySQL via SQLAlchemy, and offers budgeting, reporting, and cash flow features.",
    version="0.3.0",
)

# --- Helper Functions (OCR, Extraction - Keep as before) ---
async def perform_ocr_easyocr(file_content: bytes, mimetype: str) -> str:
    # ... (Keep the implementation from the previous response) ...
    text = ""
    logger.info(f"Starting OCR process for mimetype: {mimetype}")
    try:
        if mimetype == 'application/pdf':
            logger.info("Processing PDF file with pdf2image...")
            images = convert_from_bytes(file_content, dpi=300)
            logger.info(f"Converted PDF to {len(images)} image(s).")
            all_page_texts = []
            for i, img in enumerate(images):
                 logger.info(f"Performing EasyOCR on PDF page {i+1}...")
                 img_byte_arr = io.BytesIO()
                 img.save(img_byte_arr, format='PNG')
                 img_byte_arr = img_byte_arr.getvalue()
                 result = ocr_reader.readtext(img_byte_arr)
                 page_text = " ".join([item[1] for item in result])
                 all_page_texts.append(page_text)
                 logger.info(f"OCR for page {i+1} completed. Found {len(result)} text boxes.")
            text = "\n\n--- Page Break ---\n\n".join(all_page_texts)

        elif mimetype.startswith('image/'):
            logger.info("Processing image file with EasyOCR...")
            result = ocr_reader.readtext(file_content)
            text = " ".join([item[1] for item in result])
            logger.info(f"OCR for image completed. Found {len(result)} text boxes.")
        else:
            logger.warning(f"Unsupported mimetype for OCR: {mimetype}")
            raise HTTPException(status_code=400, detail=f"Unsupported file type for OCR: {mimetype}")

        logger.info("OCR processing finished.")
        return text.strip()

    except Exception as e:
        logger.error(f"Error during OCR processing: {e}", exc_info=True)
        if "pdf2image" in str(e).lower() or "poppler" in str(e).lower():
             raise HTTPException(status_code=500, detail="OCR Error: Failed to process PDF. Ensure Poppler is installed and in PATH.")
        raise HTTPException(status_code=500, detail=f"An error occurred during OCR: {str(e)}")


def extract_invoice_data_from_text_basic(text: str) -> schemas.InvoiceDataCreate:
    # ... (Keep the implementation from the previous response) ...
    # !!! IMPORTANT: This function should now return a Pydantic *Create* schema
    # (schemas.InvoiceDataCreate) instead of the full InvoiceData model,
    # as the 'id' and relationships are handled by the DB/ORM.
    logger.info("Attempting basic data extraction using Regex...")
    # Initialize with the Create schema defaults if applicable
    data_dict = schemas.InvoiceDataCreate().dict(exclude_unset=True)
    data_dict['extractedText'] = text

    # --- Regex Patterns (Examples - Need Refinement) ---
    inv_num_match = re.search(r'(?:Invoice|INV)\s*(?:Number|No\.?|#)[:\s]*([A-Z0-9-]+)', text, re.IGNORECASE)
    if inv_num_match: data_dict['invoiceNumber'] = inv_num_match.group(1).strip()

    date_match = re.search(r'(?:Invoice\s+Date|Date)[:\s]*([\w\s,./-]+)', text, re.IGNORECASE)
    if date_match:
        raw_date = date_match.group(1).strip()
        parsed_date = None
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y', '%b %d %Y'):
            try: parsed_date = datetime.strptime(raw_date, fmt).date(); break
            except ValueError: pass
        if parsed_date: data_dict['invoiceDate'] = parsed_date
        else: logger.warning(f"Could not parse extracted Invoice Date: {raw_date}")

    due_date_match = re.search(r'(?:Due\s+Date|Payment\s+Due)[:\s]*([\w\s,./-]+)', text, re.IGNORECASE)
    if due_date_match:
        raw_date = due_date_match.group(1).strip()
        parsed_date = None
        for fmt in ('%Y-%m-%d', '%m/%d/%Y', '%b %d, %Y', '%b %d %Y'):
             try: parsed_date = datetime.strptime(raw_date, fmt).date(); break
             except ValueError: pass
        if parsed_date: data_dict['dueDate'] = parsed_date
        else: logger.warning(f"Could not parse extracted Due Date: {raw_date}")


    total_match = re.search(r'(?:Total\s*Due|Amount\s*Due|Balance\s*Due|TOTAL)[:\s$]*([0-9,]+\.?\d{0,2})', text, re.IGNORECASE | re.MULTILINE)
    if not total_match: total_match = re.search(r'^Total[:\s$]*([0-9,]+\.?\d{0,2})', text, re.IGNORECASE | re.MULTILINE)
    if total_match:
        try: data_dict['totalAmount'] = float(total_match.group(1).replace(',', ''))
        except ValueError: logger.warning(f"Could not parse extracted Total Amount: {total_match.group(1)}")

    lines = text.split('\n')
    if lines:
        potential_vendor = next((line.strip() for line in lines if line.strip()), None)
        if potential_vendor and "invoice" not in potential_vendor.lower() and 3 < len(potential_vendor) < 50:
             data_dict['vendor'] = potential_vendor

    # --- Line Items Placeholder ---
    logger.warning("Line item, subtotal, and tax extraction not implemented with basic Regex.")
    data_dict['needsReview'] = True # Flag for review due to incomplete extraction

    # --- Confidence Score ---
    found_fields = sum([1 for field in ['invoiceNumber', 'invoiceDate', 'totalAmount', 'vendor'] if data_dict.get(field)])
    data_dict['confidenceScore'] = found_fields / 4.0
    if data_dict['confidenceScore'] < 0.75: data_dict['needsReview'] = True

    # --- Create Pydantic Schema ---
    try:
        invoice_create_schema = schemas.InvoiceDataCreate(**data_dict)
        invoice_create_schema.processingStatus = "Processed" if not invoice_create_schema.needsReview else "Needs Review"
        logger.info(f"Extraction complete. Status: {invoice_create_schema.processingStatus}")
        return invoice_create_schema
    except Exception as e:
        logger.error(f"Pydantic validation failed during extraction: {e}", exc_info=True)
        # Return a schema with error status if validation fails
        error_schema = schemas.InvoiceDataCreate(
            extractedText=text,
            processingStatus="Error",
            errorMessage=f"Extraction/Validation Error: {str(e)}"
        )
        return error_schema


def create_transaction_schema_from_invoice(invoice_model: models.Invoice) -> Optional[schemas.TransactionCreate]:
    """Creates a TransactionCreate schema from a saved Invoice ORM model."""
    if invoice_model.processingStatus == "Error" or not invoice_model.totalAmount:
        logger.warning(f"Skipping transaction creation for invoice {invoice_model.id} due to status '{invoice_model.processingStatus}' or missing total.")
        return None

    # Basic GL Account Determination (as before)
    vendor_lower = (invoice_model.vendor or "").lower()
    gl_account = "Uncategorized Expense"
    if "software" in vendor_lower or "saas" in vendor_lower or "aws" in vendor_lower or "google cloud" in vendor_lower:
        gl_account = "Software & Subscriptions"
    elif "marketing" in vendor_lower or "advertising" in vendor_lower:
        gl_account = "Marketing & Advertising"
    elif "office supplies" in vendor_lower or "staples" in vendor_lower:
        gl_account = "Office Supplies"

    transaction_schema = schemas.TransactionCreate(
        invoiceId=invoice_model.id,
        transactionDate=invoice_model.invoiceDate or date.today(),
        vendor=invoice_model.vendor or "Unknown Vendor",
        description=f"Invoice {invoice_model.invoiceNumber or 'N/A'}",
        amount=invoice_model.totalAmount,
        currency=invoice_model.currency or "USD",
        glAccount=gl_account,
        entryType="Debit", # Assuming expense
        tags=[] # Start with empty tags
    )
    logger.info(f"Prepared transaction schema for invoice {invoice_model.id} with GL Account: {gl_account}")
    return transaction_schema

# --- API Endpoints ---

@app.post("/process", response_model=schemas.ProcessResponse, status_code=201) # Use specific response schema
async def process_invoice_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db) # Inject DB session
):
    """
    Receives invoice, performs OCR, extracts data, saves Invoice and
    potentially a Transaction to the database.
    """
    logger.info(f"Received file: {file.filename}, content type: {file.content_type}")

    # --- File Validation (Basic) ---
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
    if file.content_type not in allowed_types:
        logger.error(f"Invalid file type received: {file.content_type}")
        raise HTTPException(status_code=400, detail="Invalid file type.")

    # --- Initialize response data ---
    # We will build the response from the saved DB object
    db_invoice: Optional[models.Invoice] = None

    try:
        file_content = await file.read()
        logger.info(f"File size: {len(file_content)} bytes")

        # --- Step 4: OCR ---
        ocr_text = await perform_ocr_easyocr(file_content, file.content_type)
        if not ocr_text:
             # Create an Invoice entry with Error status immediately
             error_invoice_data = schemas.InvoiceDataCreate(
                 processingStatus="Error",
                 errorMessage="OCR Error: No text could be extracted."
             )
             db_invoice = await crud.create_invoice(db=db, invoice=error_invoice_data)
             logger.warning("OCR returned no text. Saved Invoice with Error status.")
             # Return the created (error) invoice data
             # Need to manually construct the response schema if relationships are expected
             return schemas.ProcessResponse.from_orm(db_invoice)


        # --- Step 4 & 5: Extraction & Validation ---
        invoice_create_data = extract_invoice_data_from_text_basic(ocr_text)

        # --- Step 6a: Save Initial Invoice Data ---
        # Save the extracted data (or error state) to the DB
        db_invoice = await crud.create_invoice(db=db, invoice=invoice_create_data)
        logger.info(f"Saved initial invoice data to DB with ID: {db_invoice.id}, Status: {db_invoice.processingStatus}")

        # --- Step 6b: Accounting Engine (Create Transaction if applicable) ---
        if db_invoice.processingStatus != "Error":
            transaction_create_schema = create_transaction_schema_from_invoice(db_invoice)
            if transaction_create_schema:
                try:
                    db_transaction = await crud.create_transaction(db=db, transaction=transaction_create_schema)
                    logger.info(f"Saved transaction {db_transaction.id} linked to invoice {db_invoice.id}")
                    # Refresh invoice to potentially load the relationship (if configured)
                    await db.refresh(db_invoice, attribute_names=['transaction'])
                except Exception as tx_error:
                    # Handle potential transaction creation errors (e.g., unique constraint)
                    logger.error(f"Failed to create transaction for invoice {db_invoice.id}: {tx_error}", exc_info=True)
                    # Update invoice status to indicate transaction error
                    db_invoice.processingStatus = "Error"
                    db_invoice.errorMessage = f"Transaction Creation Error: {str(tx_error)}"
                    await crud.update_invoice_status(db, db_invoice.id, "Error", db_invoice.errorMessage)
                    await db.refresh(db_invoice) # Refresh after update

        logger.info(f"Successfully processed file: {file.filename}. Final Invoice Status: {db_invoice.processingStatus}")

        # Convert the final ORM model (with potential relationships loaded) to the Pydantic response model
        # Ensure relationships like line_items are loaded if needed by the response schema
        # You might need options(joinedload(models.Invoice.line_items)) in crud.get_invoice if returning full details
        response_data = schemas.ProcessResponse.from_orm(db_invoice)
        return response_data

    except HTTPException as http_exc:
        logger.error(f"HTTP Exception during processing {file.filename}: {http_exc.detail}")
        # If an invoice record was partially created before the error, update its status
        if db_invoice and db_invoice.id:
             await crud.update_invoice_status(db, db_invoice.id, "Error", f"Processing Error: {http_exc.detail}")
        # Re-raise the exception for FastAPI to handle
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error processing file {file.filename}: {e}", exc_info=True)
        # Update invoice status if possible
        if db_invoice and db_invoice.id:
             await crud.update_invoice_status(db, db_invoice.id, "Error", f"Unexpected Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected Server Error: {str(e)}")
    finally:
        if file: await file.close()


from sqlalchemy import text

@app.get("/health")
async def health_check():
    try:
        # Perform a simple query to check database connectivity
        async with get_db() as db:
            await db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        db_status = "disconnected"

    return {"status": "ok", "ocr_engine": "EasyOCR", "database": db_status}
# --- Budgeting Endpoints (Refactored) ---

@app.post("/budgets", status_code=201, response_model=schemas.Budget)
async def create_budget_endpoint(
    budget_in: schemas.BudgetCreate, # Use Create schema for input
    db: AsyncSession = Depends(get_db)
):
    """Creates a new budget record in the database."""
    logger.info(f"Received request to create budget for {budget_in.category} - {budget_in.periodValue}")
    # TODO: Add check for existing budget for the same period/category if needed
    db_budget = await crud.create_budget(db=db, budget=budget_in)
    return db_budget # Automatically converted to response_model by FastAPI

@app.get("/budgets", response_model=List[schemas.Budget])
async def get_budgets_endpoint(
    periodValue: Optional[str] = None,
    db: AsyncSession = Depends(get_db)
):
    """Retrieves budgets, optionally filtered by periodValue."""
    logger.info(f"Fetching budgets. Filter PeriodValue: {periodValue}")
    if periodValue:
        budgets = await crud.get_budgets_by_period(db=db, period_value=periodValue)
    else:
        # Implement crud.get_all_budgets if needed, or raise error/require filter
        raise HTTPException(status_code=400, detail="PeriodValue filter is required for now.")
        # budgets = await crud.get_all_budgets(db=db) # Example
    return budgets

@app.get("/budget-report/{periodValue}")
async def get_budget_report_endpoint(periodValue: str, db: AsyncSession = Depends(get_db)):
    """Generates a report comparing actual spending against budgets for a given period."""
    logger.info(f"Generating budget vs actual report for period: {periodValue}")

    # 1. Get budgets for the period
    budgets_list = await crud.get_budgets_by_period(db=db, period_value=periodValue)
    relevant_budgets = {b.category: b.amount for b in budgets_list}
    if not relevant_budgets:
        return {"period": periodValue, "report": {}, "message": "No budgets found for this period."}

    # 2. Parse period and get actual spending
    try:
        # Basic YYYY-MM parsing (expand for Q/Y)
        year, month = map(int, periodValue.split('-'))
        start_date = date(year, month, 1)
        end_date = (start_date + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    except ValueError:
         raise HTTPException(status_code=400, detail="Invalid periodValue format. Use YYYY-MM.")

    # Use the aggregation function from crud.py
    actual_spending = await crud.get_spending_by_category_for_period(db=db, start_date=start_date, end_date=end_date)

    # 3. Compare and build report
    report = {}
    all_categories = set(relevant_budgets.keys()) | set(actual_spending.keys())

    for category in all_categories:
        budget_amount = relevant_budgets.get(category)
        spent_amount = actual_spending.get(category, 0.0)
        variance = (budget_amount - spent_amount) if budget_amount is not None else -spent_amount
        report[category] = {
            "budget": budget_amount,
            "actual": round(spent_amount, 2),
            "variance": round(variance, 2)
        }

    logger.info(f"Budget report generated for {periodValue} with {len(report)} categories.")
    return {"period": periodValue, "report": report}

# --- Reporting Endpoints (Refactored) ---

@app.get("/reports/profit-loss", summary="Generate Profit and Loss Report")
async def get_profit_loss_endpoint(startDate: date, endDate: date, db: AsyncSession = Depends(get_db)):
    """Calculates simple P&L based on stored transactions within a date range."""
    logger.info(f"Generating P&L Report from {startDate} to {endDate}")

    transactions = await crud.get_transactions_by_date_range(db=db, start_date=startDate, end_date=endDate)

    revenue = 0.0
    expenses = 0.0
    REVENUE_ACCOUNTS = {"Revenue", "Sales"} # Example
    EXPENSE_ACCOUNTS = { # Example
        "Software & Subscriptions", "Marketing & Advertising", "Office Supplies",
        "Rent", "Utilities", "Salaries", "Uncategorized Expense"
    }

    for txn in transactions:
        if txn.glAccount in REVENUE_ACCOUNTS: revenue += txn.amount # Adjust logic as needed
        elif txn.glAccount in EXPENSE_ACCOUNTS: expenses += txn.amount

    net_profit = revenue - expenses
    logger.info(f"P&L Report: Revenue={revenue:.2f}, Expenses={expenses:.2f}, Net Profit={net_profit:.2f}")
    return {
        "reportType": "Profit & Loss", "startDate": startDate, "endDate": endDate,
        "data": {"totalRevenue": round(revenue, 2), "totalExpenses": round(expenses, 2), "netProfit": round(net_profit, 2)}
    }

@app.post("/transactions/{transaction_id}/tags", status_code=200, response_model=schemas.Transaction)
async def add_tag_to_transaction_endpoint(
    transaction_id: str,
    tag: str = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """Adds a custom tag to a specific transaction."""
    logger.info(f"Adding tag '{tag}' to transaction {transaction_id}")
    updated_transaction = await crud.add_tag_to_transaction(db=db, transaction_id=transaction_id, tag=tag)
    if not updated_transaction:
        raise HTTPException(status_code=404, detail="Transaction not found")
    logger.info(f"Tag '{tag}' added or already exists.")
    return updated_transaction

@app.get("/reports/expenses-by-tag", summary="Generate Expense Report Filtered by Tag")
async def get_expenses_by_tag_endpoint(
    tag: str,
    startDate: date,
    endDate: date,
    db: AsyncSession = Depends(get_db)
):
    """Calculates total expenses for a specific tag within a date range."""
    logger.info(f"Generating expense report for tag '{tag}' from {startDate} to {endDate}")
    tagged_transactions = await crud.get_transactions_by_tag(db=db, tag=tag, start_date=startDate, end_date=endDate)

    total_expenses = sum(txn.amount for txn in tagged_transactions if txn.glAccount != "Revenue") # Simple expense check

    logger.info(f"Found {len(tagged_transactions)} transactions totaling {total_expenses:.2f} for tag '{tag}'.")
    return {
        "reportType": "Expenses by Tag", "tag": tag, "startDate": startDate, "endDate": endDate,
        "totalExpenses": round(total_expenses, 2),
        "transactions": tagged_transactions # Return list of ORM objects (FastAPI converts to JSON)
    }

# --- Cash Flow Endpoint (Refactored - Still Simplified) ---
@app.get("/cashflow-forecast", summary="Generate Basic Cash Flow Forecast")
async def get_cashflow_forecast_endpoint(
    daysAhead: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db)
):
    """Basic cash flow projection based on recent recurring expenses (DB query)."""
    logger.info(f"Generating basic cash flow forecast for the next {daysAhead} days.")
    today = date.today()
    forecast_end_date = today + timedelta(days=daysAhead)
    lookback_date = today - timedelta(days=60) # Look back 60 days

    # Query recent transactions
    recent_transactions = await crud.get_transactions_by_date_range(db, start_date=lookback_date, end_date=today)

    potential_recurring = defaultdict(list)
    for txn in recent_transactions:
        if txn.glAccount != "Revenue": # Simple expense check
            potential_recurring[txn.vendor].append({"date": txn.transactionDate, "amount": txn.amount})

    projected_outflows = []
    # (Keep the same recurrence detection logic as before, operating on queried data)
    for vendor, txns in potential_recurring.items():
        if len(txns) > 1:
            txns.sort(key=lambda x: x['date'])
            d1, d2 = txns[-1]['date'], txns[-2]['date']
            delta_days = (d1 - d2).days
            amount1, amount2 = txns[-1]['amount'], txns[-2]['amount']
            if 25 <= delta_days <= 35 and abs(amount1 - amount2) / max(amount1, amount2, 1) < 0.10:
                next_date = d1 + timedelta(days=delta_days)
                if next_date <= forecast_end_date:
                    projected_outflows.append({
                        "date": next_date.isoformat(), "vendor": vendor, "amount": amount1,
                        "type": "Projected Recurring Expense"
                    })

    # --- Placeholders for AP/AR ---
    # Query unpaid invoices due within the forecast period
    # Assuming a 'Paid' status exists for invoices that have been paid.
    # We need a CRUD function like get_invoices_due_between.
    try:
        upcoming_payments_invoices = await crud.get_invoices_due_between(
            db=db,
            start_date=today,
            end_date=forecast_end_date,
            exclude_status="Paid" # Exclude invoices already marked as Paid
        )
        logger.info(f"Found {len(upcoming_payments_invoices)} unpaid invoices due between {today} and {forecast_end_date}.")
    except AttributeError:
         logger.error("CRUD function 'get_invoices_due_between' not found. Skipping Accounts Payable projection.")
         upcoming_payments_invoices = [] # Ensure it's an empty list if the function doesn't exist
    except Exception as e:
        logger.error(f"Error fetching upcoming payments from invoices: {e}", exc_info=True)
        upcoming_payments_invoices = []


    upcoming_payments = []
    for inv in upcoming_payments_invoices:
        # Ensure the invoice has a due date and amount to be considered payable
        if inv.dueDate and inv.totalAmount is not None:
            upcoming_payments.append({
                "date": inv.dueDate.isoformat(),
                "vendor": inv.vendor or "Unknown Vendor",
                "amount": inv.totalAmount,
                "type": "Projected Accounts Payable (Due Invoice)",
                "invoiceId": inv.id # Optional: Include invoice ID for reference
            })
        else:
             logger.warning(f"Invoice {inv.id} due {inv.dueDate} lacks amount ({inv.totalAmount}), excluded from cash flow.")

    projected_inflows = []
    # --- Placeholder for AR (Accounts Receivable) ---
    # Query outstanding invoices where the agent is owed money.
    # This requires a function to fetch invoices where the status is 'Unpaid' or similar.
    try:
        outstanding_invoices = await crud.get_invoices_by_status(
            db=db,
            status="Unpaid",  # Or "Outstanding", adjust to your status field
            end_date=forecast_end_date # Limit to invoices due within the forecast period
        )
        logger.info(f"Found {len(outstanding_invoices)} outstanding invoices (Accounts Receivable).")
    except AttributeError:
        logger.error("CRUD function 'get_invoices_by_status' not found. Skipping Accounts Receivable projection.")
        outstanding_invoices = []
    except Exception as e:
        logger.error(f"Error fetching outstanding invoices: {e}", exc_info=True)
        outstanding_invoices = []

    for invoice in outstanding_invoices:
        # Assuming 'dueDate' represents when payment is expected.
        if invoice.dueDate and invoice.totalAmount is not None:
            projected_inflows.append({
                "date": invoice.dueDate.isoformat(),
                "vendor": invoice.vendor or "Unknown Customer",  # 'vendor' might represent the customer here
                "amount": invoice.totalAmount,  # Amount expected
                "type": "Projected Accounts Receivable (Outstanding Invoice)",
                "invoiceId": invoice.id  # Link to the invoice
            })
        else:
            logger.warning(f"Skipping invoice {invoice.id} from AR projection due to missing due date or amount.")

    logger.warning("Cash flow forecast is highly simplified (AP/AR not included).")
    all_projections = sorted(projected_outflows + upcoming_payments + projected_inflows, key=lambda x: x['date'])

    return {
        "forecastStartDate": today.isoformat(), "forecastEndDate": forecast_end_date.isoformat(),
        "forecastDays": daysAhead, "projectedEvents": all_projections,
        "notes": [
            "Basic forecast based on potential recurring expenses detected in recent transactions.",
            "Does NOT include actual Accounts Payable or Accounts Receivable.", "Use with caution."
        ]
    }

# --- Alembic Setup (Run these commands in terminal) ---
# Make sure alembic.ini and backend/alembic/env.py are configured correctly.
# 1. alembic init backend/alembic  (Initialize Alembic repository)
# 2. Edit backend/alembic/env.py:
#    - Set `target_metadata = Base.metadata` (import Base from backend.models)
#    - Configure async connection if needed (see Alembic async docs)
# 3. Edit alembic.ini:
#    - Set `sqlalchemy.url = mysql+asyncmy://user:pass@host/db_name` (or load from env)
# 4. alembic revision --autogenerate -m "Initial migration" (Create first migration)
# 5. alembic upgrade head (Apply migration to the database)

# --- Run the Server ---
if __name__ == "__main__":
    logger.info("Starting AI Accounting Agent server with SQLAlchemy/MySQL...")
    # Add logic to create tables on startup for demo purposes if needed
    async def init_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    asyncio.run(init_db())
    uvicorn.run("backend.ai_agent:app", host="0.0.0.0", port=5001, log_level="info", reload=True) # Use reload for dev