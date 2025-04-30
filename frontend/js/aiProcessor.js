export function processFileMock(files) {
    return new Promise((resolve) => {
      setTimeout(() => {
        const processingStartTime = Date.now();
        
        // Process all files concurrently
        const processingPromises = files.map(file => {
          return new Promise((fileResolve) => {
            // Simulate variable processing time per file
            const processingDelay = 1000 + Math.random() * 1000;
            
            setTimeout(() => {
              const fileMockData = {
                // Strictly follow Python backend's output structure
                id: `mock_${Date.now()}_${Math.random().toString(16).substring(2, 8)}`,
                vendor: `Mock Vendor ${Math.floor(Math.random() * 100)}`,
                invoiceDate: new Date(Date.now() - Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
                dueDate: new Date(Date.now() + Math.random() * 30 * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
                invoiceNumber: `MOCK-${Math.random().toString(36).substring(2, 10).toUpperCase()}`,
                lineItems: [],
                subtotal: parseFloat((Math.random() * 1000).toFixed(2)),
                tax: parseFloat((Math.random() * 100).toFixed(2)),
                totalAmount: parseFloat((Math.random() * 1100).toFixed(2)),
                currency: "USD",
                extractedText: `Mock OCR text for ${file.name}...`,
                metadata: {
                  fileName: file.name,
                  fileSize: file.size,
                  processingTime: processingDelay.toFixed(0) + 'ms',
                  timestamp: new Date().toISOString()
                }
              };
              fileResolve(fileMockData);
            }, processingDelay);
          });
        });
        
        // Wait for all files to complete processing
        Promise.all(processingPromises).then(results => {
          // Aggregate results with unified output structure
          const aggregatedResult = {
            transactions: results,
            summary: {
              totalFilesProcessed: results.length,
              successful: results.length,
              failed: 0,
              totalProcessingTime: (Date.now() - processingStartTime) + 'ms',
              timestamp: new Date().toISOString()
            }
          };
          
          console.log('Aggregated mock response:', aggregatedResult);
          resolve(aggregatedResult);
        });
      }, 50); // Small delay to simulate initial request handling
    });
  }
  