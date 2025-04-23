const validateResponse = (data) => {
  const required = ["vendor", "invoiceDate", "dueDate", "invoiceNumber", "lineItems", "subtotal", "tax", "totalAmount"];
  return required.filter(f => !(f in data));
};

test('validates complete AI response', () => {
  const mock = {
    vendor: "X", invoiceDate: "2025-01-01", dueDate: "2025-01-30",
    invoiceNumber: "INV001", lineItems: [], subtotal: 0, tax: 0, totalAmount: 0
  };
  expect(validateResponse(mock)).toEqual([]);
});

test('detects missing fields', () => {
  const mock = { vendor: "X", invoiceNumber: "INV001" };
  expect(validateResponse(mock)).toContain("subtotal");
  expect(validateResponse(mock)).toContain("invoiceDate");
});
