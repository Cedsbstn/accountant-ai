from sqlalchemy import Column, Integer, String, Float, Date, DateTime, Boolean, Text, ForeignKey, JSON, Index
from sqlalchemy.orm import relationship
from backend.database import Base # Import Base from database.py
import uuid
from datetime import date

# Helper function for default UUIDs as strings
def default_uuid():
    return str(uuid.uuid4())

class Invoice(Base):
    __tablename__ = "invoices"

    id = Column(String(36), primary_key=True, default=default_uuid) # Use String for UUID
    vendor = Column(String(255), index=True)
    invoiceDate = Column(Date, nullable=True)
    dueDate = Column(Date, nullable=True)
    invoiceNumber = Column(String(100), index=True, nullable=True)
    subtotal = Column(Float, nullable=True)
    tax = Column(Float, nullable=True)
    totalAmount = Column(Float, nullable=True, index=True)
    currency = Column(String(10), default="USD")
    extractedText = Column(Text, nullable=True)
    processingStatus = Column(String(50), default="Pending", index=True)
    confidenceScore = Column(Float, nullable=True)
    needsReview = Column(Boolean, default=False)
    errorMessage = Column(Text, nullable=True)

    # Relationship: One-to-Many (Invoice has many LineItems)
    line_items = relationship("LineItem", back_populates="invoice", cascade="all, delete-orphan")
    # Relationship: One-to-One (Invoice can have one Transaction - adjust if needed)
    transaction = relationship("Transaction", back_populates="invoice", uselist=False, cascade="all, delete-orphan")


class LineItem(Base):
    __tablename__ = "line_items"

    id = Column(Integer, primary_key=True, index=True) # Auto-incrementing integer PK
    invoice_id = Column(String(36), ForeignKey("invoices.id"), nullable=False) # Foreign key to Invoice
    description = Column(String(500), nullable=True)
    quantity = Column(Float, default=1.0)
    price = Column(Float, default=0.0)
    lineTotal = Column(Float, default=0.0)

    # Relationship: Many-to-One (LineItem belongs to one Invoice)
    invoice = relationship("Invoice", back_populates="line_items")


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(String(36), primary_key=True, default=default_uuid)
    invoiceId = Column(String(36), ForeignKey("invoices.id"), nullable=False, unique=True) # Ensure one transaction per invoice
    transactionDate = Column(Date, nullable=False, index=True)
    postingDate = Column(Date, default=date.today, nullable=False)
    vendor = Column(String(255), index=True)
    description = Column(String(500), nullable=True)
    amount = Column(Float, nullable=False)
    currency = Column(String(10), default="USD")
    glAccount = Column(String(100), default="Uncategorized Expense", index=True)
    entryType = Column(String(20)) # "Debit" or "Credit"
    paymentMethod = Column(String(100), nullable=True, index=True) # <-- ADDED COLUMN (indexed for searching)
    # Store tags as JSON array in MySQL
    # Note: Querying JSON in MySQL can be less efficient than a separate Tags table for complex queries
    tags = Column(JSON, nullable=True, default=list)

    # Relationship: One-to-One back to Invoice
    invoice = relationship("Invoice", back_populates="transaction")


class Budget(Base):
    __tablename__ = "budgets"

    id = Column(String(36), primary_key=True, default=default_uuid)
    category = Column(String(100), index=True, nullable=False) # e.g., GL Account or specific tag
    periodType = Column(String(20), nullable=False) # "monthly", "quarterly", "annual"
    periodValue = Column(String(20), nullable=False, index=True) # "2024-01", "2024-Q1", "2024"
    amount = Column(Float, nullable=False)

    # Consider adding unique constraint on (category, periodType, periodValue)
    # from sqlalchemy import UniqueConstraint
    # __table_args__ = (UniqueConstraint('category', 'periodType', 'periodValue', name='uq_budget_period'),)

class Checkpoint(Base):
    __tablename__ = "checkpoints"
    
    thread_id = Column(String(255), primary_key=True)
    checkpoint = Column(JSON, nullable=False)
    config_data = Column(JSON, nullable=False)
    created_at = Column(DateTime, server_default='CURRENT_TIMESTAMP')
    updated_at = Column(DateTime, server_default='CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP')
    
    def to_dict(self):
        return {
            "thread_id": self.thread_id,
            "checkpoint": self.checkpoint,
            "config_data": self.config_data,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None
        }
# Add Vendor model if needed (e.g., to store default GL account)
# class Vendor(Base):
#    __tablename__ = "vendors"
#    id = Column(Integer, primary_key=True)
#    name = Column(String(255), unique=True, index=True)
#    default_gl_account = Column(String(100))
#    # ... other vendor details