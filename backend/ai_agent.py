import io
import json
import logging
import os
import re
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import easyocr
import google.generativeai as genai
from google.generativeai.types import HarmBlockThreshold, HarmCategory
import uvicorn
from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, HTTPException, Query, UploadFile
from pdf2image import convert_from_bytes
from PIL import Image
from pydantic import Field, ValidationError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend import crud, models, schemas
from backend.database import Base, engine
from backend.dependencies import get_db

# --- Configuration & Initialization ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
load_dotenv()

# --- Configure Gemini ---
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    logger.error("GOOGLE_API_KEY not found in environment variables.")
else:
    try:
        genai.configure(api_key=GOOGLE_API_KEY)
        logger.info("Google Generative AI SDK configured.")
    except Exception as e:
        logger.error(f"Failed to configure Google Generative AI SDK: {e}", exc_info=True)

# --- Define Generation Configuration ---
# These settings control the behavior of the Gemini model during generation.
# Adjust these values based on desired output creativity, consistency, and safety.
generation_config = genai.GenerationConfig(
    # Accuracy first. Lower values (e.g., 0.1-0.25) make the output more accurate and focused, which is generally better for data extraction tasks.
    temperature=0.1,

    # Maximum number of tokens to generate in the response. Adjust based on the
    # expected size of the JSON output for complex invoices. Too low might truncate JSON.
    max_output_tokens=16384, # Increased slightly for potentially complex invoices/JSON

    # Top-p sampling: Nucleus sampling. Considers only the most probable tokens
    # with cumulative probability p. Lower values make it more focused. Often used as an
    # alternative or complement to temperature. 0.95 is a common value.
    top_p=0.95,
)

# --- Define Safety Settings ---
safety_settings = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

try:
    ocr_reader = easyocr.Reader(['en'], gpu=True)
    logger.info("EasyOCR Reader initialized using GPU.")
except Exception:
    ocr_reader = easyocr.Reader(['en'], gpu=False)
    logger.info("EasyOCR Reader initialized using CPU.")

# --- FastAPI App Setup ---
app = FastAPI(
    title="AI Accounting Agent featuring Gemini, SQLAlchemy, and MySQL",
    description="Processes invoices using EasyOCR and Gemini (with self-review), stores data in MySQL via SQLAlchemy, and offers budgeting, reporting, and cash flow features.",
    version="1.0.0",
)

# --- Helper Functions (OCR, Extraction - Keep as before) ---
async def perform_ocr_easyocr(file_content: bytes, mimetype: str) -> str:
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

# --- Gemini Data Extraction with Self-Review Function ---
def extract_and_review_invoice_data_with_gemini(text: str) -> schemas.InvoiceDataCreate:
    """
    Uses Google Gemini Flash model to extract and self-review structured data from OCR text.
    The model itself determines if manual review is needed based on extraction confidence.
    
    Args:
        text: The raw text extracted from the invoice via OCR.

    Returns:
        An InvoiceDataCreate schema object populated with extracted data and review status,
        or an object with status 'Error' if extraction fails.
    """
    logger.info("Attempting data extraction and self-review using Gemini Flash...")

    if not GOOGLE_API_KEY:
        logger.error("Gemini API key not configured. Cannot perform AI extraction.")
        return schemas.InvoiceDataCreate(
            extractedText=text,
            processingStatus="Error",
            errorMessage="AI Service Error: API key not configured."
        )

    # --- Define the Prompt for Gemini ---
    # This prompt guides the model to extract specific fields and return JSON.
    # Adjust the prompt based on observed results for better accuracy.
    prompt = f"""
    You are an Accountant expert, your task is to Reasoning step by step below carefully.
    Analyze the following text extracted from an invoice using OCR. Extract the specified fields accurately.
    After extraction, critically review the extracted values based on the source text.
    Return the result ONLY as a valid JSON object. Do not include any introductory text, explanations, or markdown formatting like ```json.
    The JSON object should have the following keys:
    - "extractedData": (object) An object containing the extracted invoice fields:
        - "vendor": (string) The name of the vendor/supplier. Use null if not found or highly uncertain.
        - "invoiceDate": (string) The main date of the invoice in "YYYY-MM-DD" format. Use null if not found, ambiguous, or cannot be formatted correctly.
        - "dueDate": (string) The payment due date in "YYYY-MM-DD" format. Use null if not found or cannot be formatted correctly.
        - "invoiceNumber": (string) The unique invoice identifier/number. Use null if not found or highly uncertain.
        - "lineItems": (array of objects) A list of line items. Each object should have: "description" (string), "quantity" (number, default 1.0), "price" (number, default 0.0), "lineTotal" (number, default 0.0). Return [] if none are clearly identifiable.
        - "subtotal": (number) The total amount before taxes. Use null if not found or highly uncertain.
        - "tax": (number) The total tax amount. Use null if not found or highly uncertain.
        - "totalAmount": (number) The final total amount due. Use null if not found or highly uncertain.
        - "currency": (string) The currency code (e.g., "USD", "EUR"). Default to "USD" if not found.
    - "needsReview": (boolean) Set to true if you have low confidence in any key extraction (e.g., ambiguous vendor, unparseable date, unclear total, inconsistent sums), or if line item extraction was difficult/incomplete. Otherwise, set to false.
    - "reviewReason": (string) If needsReview is true, provide a brief reason (e.g., "Ambiguous invoice date format", "Total amount doesn't match line items sum", "Low confidence in vendor name"). If needsReview is false, set this to null or an empty string.

    Prioritize accuracy. If a value is uncertain or cannot be reliably extracted, represent it as null within the "extractedData" object and set "needsReview" to true with a reason. Ensure dates are strictly "YYYY-MM-DD".

    OCR Text to Analyze:
    --- START OF TEXT ---
    {text}
    --- END OF TEXT ---

    JSON Output:
    """

    try:
        model = genai.GenerativeModel('gemini-2.0-flash')
        # For high-load applications, consider running this in a thread pool:
        # response = await asyncio.to_thread(model.generate_content, prompt)
        response = model.generate_content(
            prompt,
            generation_config=generation_config,
            safety_settings=safety_settings
        )

        logger.debug(f"Gemini Raw Response Text: {response.text}")

        # --- Parse the Response ---
        try:
            # Clean potential markdown fences if the model didn't follow instructions perfectly
            cleaned_text = response.text.strip().removeprefix('```json').removesuffix('```').strip()
            gemini_result = json.loads(cleaned_text)
            
            # --- Validate Gemini Response Structure ---
            if "extractedData" not in gemini_result or "needsReview" not in gemini_result:
                logger.error("Gemini response missing required keys ('extractedData', 'needsReview').")
                logger.error(f"Gemini response was: {gemini_result}")
                return schemas.InvoiceDataCreate(
                    extractedText=text,
                    processingStatus="Error",
                    errorMessage="AI Service Error: Invalid response structure from AI."
                )

            extracted_data = gemini_result["extractedData"]
            needs_review_ai = gemini_result.get("needsReview", True) # Default to needing review if missing
            review_reason = gemini_result.get("reviewReason", "Reason not provided by AI.") if needs_review_ai else None
            
            # --- Map to Pydantic Schema ---
            extracted_data['extractedText'] = text
            extracted_data['needsReview'] = needs_review_ai # Use AI's decision
            extracted_data['errorMessage'] = review_reason if needs_review_ai else None # Use reason as error/info message
            
            # Determine processing status based on AI review
            if needs_review_ai:
                extracted_data['processingStatus'] = "Needs Review"
            else:
                extracted_data['processingStatus'] = "Processed"

            # Validate and create the Pydantic object
            try:
                # Ensure lineItems is a list, default if missing/null
                if 'lineItems' not in extracted_data or extracted_data['lineItems'] is None:
                    extracted_data['lineItems'] = []
                invoice_schema = schemas.InvoiceDataCreate(**extracted_data)
                # Pydantic validation still runs (e.g., date parsing from string)
                logger.info(f"Gemini extraction/review complete. Status determined by AI: {invoice_schema.processingStatus}")
                return invoice_schema

            except ValidationError as e:
                logger.error(f"Pydantic validation failed after Gemini extraction/review: {e}", exc_info=True)
                # Even if AI said 'Processed', if Pydantic fails, mark as Error
                return schemas.InvoiceDataCreate(
                    extractedText=text,
                    processingStatus="Error",
                    errorMessage=f"Data Validation Error after AI processing: {str(e)}",
                    needsReview=True # Force review if Pydantic fails
                )
            except Exception as pydantic_err: # Catch other potential Pydantic errors
                 logger.error(f"Error creating Pydantic schema after Gemini: {pydantic_err}", exc_info=True)
                 return schemas.InvoiceDataCreate(
                    extractedText=text,
                    processingStatus="Error",
                    errorMessage=f"Internal Error: Failed creating data structure ({type(pydantic_err).__name__}).",
                    needsReview=True
                 )

        except json.JSONDecodeError as e:
            # ... (keep JSON decode error handling as before) ...
            logger.error(f"Failed to decode JSON response from Gemini: {e}", exc_info=True)
            logger.error(f"Gemini response text was: {response.text}")
            return schemas.InvoiceDataCreate(
                extractedText=text,
                processingStatus="Error",
                errorMessage="AI Service Error: Could not parse AI response."
            )
        except Exception as e: # Catch other potential errors during parsing/mapping
             logger.error(f"Error processing Gemini response: {e}", exc_info=True)
             return schemas.InvoiceDataCreate(
                extractedText=text,
                processingStatus="Error",
                errorMessage=f"AI Service Error: Failed to process AI response ({type(e).__name__})."
            )
    
    except Exception as e:
        logger.error(f"Error calling Gemini API: {e}", exc_info=True)
        return schemas.InvoiceDataCreate(
            extractedText=text,
            processingStatus="Error",
            errorMessage=f"AI Service Error: Communication failed ({type(e).__name__})."
        )
        

# --- Accounting Engine ---
def create_transaction_schema_from_invoice(invoice_model: models.Invoice) -> Optional[schemas.TransactionCreate]:
    """Creates a TransactionCreate schema from a saved Invoice ORM model."""
    # This function now receives an Invoice model potentially populated by Gemini data
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
        entryType="Debit",
        tags=[],
        paymentMethod=None
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
    Receives invoice, performs OCR, uses Gemini for data extraction & self-review,
    saves Invoice and potentially a Transaction to the database.
    """
    logger.info(f"Received file: {file.filename}, content type: {file.content_type}")

    # --- File Validation (Basic) ---
    allowed_types = ['application/pdf', 'image/jpeg', 'image/png']
    if file.content_type not in allowed_types:
        logger.error(f"Invalid file type received: {file.content_type}")
        raise HTTPException(status_code=400, detail="Invalid file type.")

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
            return schemas.ProcessResponse.from_orm(db_invoice)

        # --- Step 4 & 5: AI Extraction & Self-Review (Gemini) ---
        invoice_create_data = extract_and_review_invoice_data_with_gemini(ocr_text)
        # The status (Processed/Needs Review/Error) is now determined by Gemini + Pydantic validation
        
        # --- Step 6a: Save Invoice Data (Result from Gemini) ---
        db_invoice = await crud.create_invoice(db=db, invoice=invoice_create_data)
        logger.info(f"Saved invoice data to DB with ID: {db_invoice.id}, Status: {db_invoice.processingStatus}")

        # --- Step 6b: Accounting Engine (Create Transaction if applicable) ---
        # Create transaction only if status is 'Processed' (as determined by AI/validation)
        if db_invoice.processingStatus == "Processed":
            transaction_create_schema = create_transaction_schema_from_invoice(db_invoice)
            if transaction_create_schema:
                try:
                    db_transaction = await crud.create_transaction(db=db, transaction=transaction_create_schema)
                    logger.info(f"Saved transaction {db_transaction.id} linked to invoice {db_invoice.id}")
                    await db.refresh(db_invoice, attribute_names=['transaction'])
                except Exception as tx_error:
                    logger.error(f"Failed to create transaction for invoice {db_invoice.id}: {tx_error}", exc_info=True)
                    await crud.update_invoice_status(db, db_invoice.id, "Error", f"Transaction Creation Error: {str(tx_error)}")
                    await db.refresh(db_invoice)
        elif db_invoice.processingStatus == "Needs Review":
            logger.info(f"Invoice {db_invoice.id} flagged for review by AI. Skipping automatic transaction creation.")
        elif db_invoice.processingStatus == "Error":
            logger.warning(f"Invoice {db_invoice.id} processing resulted in Error. Skipping transaction creation.")

        logger.info(f"Successfully processed file: {file.filename}. Final Invoice Status: {db_invoice.processingStatus}")

        response_data = schemas.ProcessResponse.from_orm(db_invoice)
        return response_data

    except HTTPException as http_exc:
        logger.error(f"HTTP Exception during processing {file.filename}: {http_exc.detail}")
        if db_invoice and db_invoice.id:
            await crud.update_invoice_status(db, db_invoice.id, "Error", f"Processing Error: {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Unexpected error processing file {file.filename}: {e}", exc_info=True)
        if db_invoice and db_invoice.id:
            await crud.update_invoice_status(db, db_invoice.id, "Error", f"Unexpected Server Error: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Unexpected Server Error: {str(e)}")
    finally:
        if file: await file.close()

@app.get("/health")
async def health_check():
    try:
        # Perform a simple query to check database connectivity
        db = get_db()
        async for session in db:
            await session.execute(text("SELECT 1"))
        db_status = "connected with"
    except Exception as e:
        logger.error(f"Database connection check failed: {e}")
        db_status = "disconnected"
    return {"status": "ok", "ocr_engine": "EasyOCR", "ai_extractor": "Gemini", "database": db_status + " MySQL (SQLAlchemy)."}

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
    logger.info("Starting AI Accounting Agent server with Gemini+SQLAlchemy+MySQL...")
    # Add logic to create tables on startup for demo purposes if needed
    if not GOOGLE_API_KEY:
        logger.warning("!!! GOOGLE_API_KEY is not set. AI extraction features will fail. !!!")
    uvicorn.run("backend.ai_agent:app", host="0.0.0.0", port=5001, log_level="info", reload=True) # Use reload for dev