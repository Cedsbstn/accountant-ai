export function validateInvoiceData(data) {
    const issues = [];
  
    // Check total calculation
    const computedSubtotal = data.lineItems.reduce(
      (sum, item) => sum + item.quantity * item.price,
      0
    );
    if (Math.abs(computedSubtotal - data.subtotal) > 0.01) {
      issues.push("Subtotal does not match calculated line items total.");
    }
  
    const computedTotal = data.subtotal + data.tax;
    if (Math.abs(computedTotal - data.totalAmount) > 0.01) {
      issues.push("Total amount does not match subtotal + tax.");
    }
  
    // Check date format (simple YYYY-MM-DD check)
    const dateRegex = /^\\d{4}-\\d{2}-\\d{2}$/;
    if (!dateRegex.test(data.invoiceDate)) {
      issues.push("Invoice date format is invalid.");
    }
    if (!dateRegex.test(data.dueDate)) {
      issues.push("Due date format is invalid.");
    }
  
    return issues;
  }
  