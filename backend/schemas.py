from pydantic import BaseModel, Field, validator, root_validator, ConfigDict
from typing import List, Optional
from datetime import date, datetime
import uuid

# --- Line Item Schemas ---
class LineItemBase(BaseModel):
    description: Optional[str] = "N/A"
    quantity: Optional[float] = 1.0
    price: Optional[float] = 0.0
    lineTotal: Optional[float] = 0.0

class LineItemCreate(LineItemBase):
    pass

class LineItem(LineItemBase):
    id: int # Primary key from DB
    invoice_id: str # Foreign key

    # Use model_config for Pydantic V2
    model_config = ConfigDict(from_attributes=True) # <-- USE THIS INSTEAD OF Config class

# --- Invoice Schemas ---
class InvoiceDataBase(BaseModel):
    vendor: Optional[str] = None
    invoiceDate: Optional[date] = None
    dueDate: Optional[date] = None
    invoiceNumber: Optional[str] = None
    subtotal: Optional[float] = None
    tax: Optional[float] = None
    totalAmount: Optional[float] = None
    currency: Optional[str] = "USD" # Default currency
    extractedText: Optional[str] = None
    processingStatus: str = "Pending"
    confidenceScore: Optional[float] = None
    needsReview: bool = False
    errorMessage: Optional[str] = None

    # Keep your validators here if they apply purely to API data structure
    # Validation that requires DB lookups should happen in CRUD or service layer

class InvoiceDataCreate(InvoiceDataBase):
     # Fields required for creation
     pass

class InvoiceData(InvoiceDataBase):
    id: str # Primary key from DB
    lineItems: List[LineItem] = [] # Include related line items

    # Use model_config for Pydantic V2
    model_config = ConfigDict(from_attributes=True) # <-- USE THIS INSTEAD OF Config class

# --- Transaction Schemas ---
class TransactionBase(BaseModel):
    invoiceId: str
    transactionDate: date
    vendor: str
    description: Optional[str] = None
    amount: float
    currency: str = "USD" #Default currency
    paymentMethod: Optional[str] = None # <-- ADDED FIELD (e.g., "Credit Card ending 1234", "ACH", "Check #567")
    glAccount: str = "Uncategorized Expense"
    entryType: str # "Debit" or "Credit"
    tags: List[str] = []

class TransactionCreate(TransactionBase):
    pass

class Transaction(TransactionBase):
    id: str # Primary key from DB
    postingDate: date # Added by DB/server

    # Use model_config for Pydantic V2
    model_config = ConfigDict(from_attributes=True) # <-- USE THIS INSTEAD OF Config class

# --- Budget Schemas ---
class BudgetBase(BaseModel):
    category: str
    periodType: str
    periodValue: str
    amount: float

class BudgetCreate(BudgetBase):
    pass

class Budget(BudgetBase):
    id: str # Primary key from DB

    # Use model_config for Pydantic V2
    model_config = ConfigDict(from_attributes=True) # <-- USE THIS INSTEAD OF Config class
    
# --- Schema for Processing Response ---
# Reuse InvoiceData schema or create a specific one if needed
class ProcessResponse(InvoiceData):
    pass