export function processFileMock(file) {
    return new Promise((resolve) => {
      setTimeout(() => {
        const mockData = {
          // Structure should match schemas.ProcessResponse from Python backend
          id: `mock_${Date.now()}_${Math.random().toString(16).substring(2, 8)}`,
          vendor: `Mock Vendor ${Math.floor(Math.random() * 100)}`,
          invoiceDate: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // Random date in last 30 days
          dueDate: new Date(Date.now() + Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0], // Random date in next 30 days
          invoiceNumber: `MOCK-${Math.random().toString(36).substring(2, 10).toUpperCase()}`,
          lineItems: [], // Mock line items are complex, keep empty or add simple ones
          subtotal: parseFloat((Math.random() * 1000).toFixed(2)),
          tax: parseFloat((Math.random() * 100).toFixed(2)),
          totalAmount: parseFloat((Math.random() * 1100).toFixed(2)), // Note: Mock totals won't necessarily add up
          currency: "USD",
          extractedText: `Mock OCR text for ${file.name}...`,
      };
        console.log(`Mock response for ${file.name}:`, mockData);
        resolve(mockData);
      }, 1500); // simulate processing delay
    });
  }
  