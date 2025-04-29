import { processFileMock } from "./aiProcessor.js";
// import { validateInvoiceData } from "./validator.js"; // Removed validation
import { generateReport } from './reportHandler.js';

// Get backend URL from window object
const BACKEND_URL = window.BACKEND_URL || 'http://localhost:3001';

const dropArea = document.getElementById("drop-area");
const fileElem = document.getElementById("fileElem");
const fileList = document.getElementById("fileList");
const status = document.getElementById("status");
const transactionsTableBody = document.querySelector("#transactionsTable tbody");
const reportBtn = document.getElementById("generateReport");
const reportOutput = document.getElementById("reportOutput");
const emptyTablePlaceholder = transactionsTableBody.querySelector('.empty-table-placeholder');

const allowedTypes = ["application/pdf", "image/jpeg", "image/png"];
const transactions = [];

function preventDefaults(e) {
  e.preventDefault();
  e.stopPropagation();
}

function highlight() {
  dropArea.classList.add("highlight");
}

function unhighlight() {
  dropArea.classList.remove("highlight");
}

function addTransactionToTable(data, fileName) {
  // Remove placeholder row if it exists
  if (emptyTablePlaceholder && !emptyTablePlaceholder.hidden) {
    emptyTablePlaceholder.hidden = true; // Hide it instead of removing, easier to show again if table becomes empty
  }

  const row = transactionsTableBody.insertRow(); // Insert row at the end
  row.setAttribute('data-invoice-id', data.id || ''); // Add data attribute for potential future actions

  // Use Intl for formatting currency and dates potentially
  const currencyFormatter = new Intl.NumberFormat(undefined, { style: 'currency', currency: data.currency || 'USD' });
  const dateFormatter = new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' });

  row.innerHTML = `
        <td>${fileName || 'N/A'}</td>
        <td>${data.vendor || 'N/A'}</td>
        <td>${data.invoiceNumber || 'N/A'}</td>
        <td>${data.invoiceDate ? dateFormatter.format(new Date(data.invoiceDate + 'T00:00:00')) : 'N/A'}</td>
        <td>${data.totalAmount != null ? currencyFormatter.format(data.totalAmount) : 'N/A'}</td>
        <td><span class="status-${data.processingStatus?.toLowerCase().replace(' ', '-')}">${data.processingStatus || 'Unknown'}</span></td>
        <td><button type="button" class="view-details-btn" aria-label="View details for ${fileName || 'invoice'}">Details</button></td>
  `;
  transactionsTableBody.appendChild(row);
}

// Function to send file to backend
async function processFileBackend(file) {
    const formData = new FormData();
    formData.append('invoice', file); // 'invoice' is the field name expected by the backend

    try {
        const response = await fetch(`${BACKEND_URL}/upload`, { // Assuming '/upload' is the endpoint
            method: 'POST',
            body: formData,
            // Headers might be needed depending on backend setup (e.g., Authorization)
            // headers: { 'Authorization': 'Bearer YOUR_TOKEN_HERE' }
        });

        if (!response.ok) {
            // Handle HTTP errors (e.g., 4xx, 5xx)
            const errorText = await response.text();
            throw new Error(`Backend error: ${response.status} ${response.statusText} - ${errorText}`);
        }

        const data = await response.json(); // Assuming backend returns JSON data
        return data;
    } catch (error) {
        console.error('Error uploading file:', error);
        // Rethrow or return an error structure so the caller can handle it
        throw error;
    }
}


function handleFiles(files) {
  [...files].forEach(file => {
    const listItem = document.createElement("li");
    if (!allowedTypes.includes(file.type)) {
      listItem.textContent = `${file.name} - ❌ Invalid file type`;
      listItem.style.color = "red";
      status.innerHTML += `<p>❌ ${file.name} was rejected (unsupported format)</p>`;
    } else {
      listItem.textContent = `${file.name} - ⏳ Uploading & Processing...`;
      listItem.style.color = "orange";
      processFileBackend(file).then(data => { // Use the backend processing function
        // Assuming successful processing returns data object
        listItem.textContent = `${file.name} - ✅ Processed (Vendor: ${data.vendor})`;
        listItem.style.color = "green";
        status.innerHTML += `<p>✅ ${file.name} processed - Invoice #${data.invoiceNumber}, Total $${data.totalAmount}</p>`;

        transactions.push({ ...data, fileName: file.name });
        addTransactionToTable(data, file.name);
      }).catch(error => {
          // Handle errors from backend processing
          listItem.textContent = `${file.name} - ❌ Error Processing`;
          listItem.style.color = "red";
          status.innerHTML += `<p>❌ Error processing ${file.name}: ${error.message}</p>`;
          console.error(`Failed to process ${file.name}:`, error);
      });
    }
    fileList.appendChild(listItem);
  });
}

["dragenter", "dragover", "dragleave", "drop"].forEach(eventName =>
  dropArea.addEventListener(eventName, preventDefaults, false)
);
dropArea.addEventListener("dragenter", highlight);
dropArea.addEventListener("dragover", highlight);
dropArea.addEventListener("dragleave", unhighlight);
dropArea.addEventListener("drop", unhighlight);
dropArea.addEventListener("drop", e => {
  const dt = e.dataTransfer;
  handleFiles(dt.files);
});
fileElem.addEventListener("change", () => handleFiles(fileElem.files));

// 🧾 Report generation
reportBtn.addEventListener("click", () => {
  const reportType = document.getElementById("reportType").value;
  generateReport(reportType, transactions, reportOutput);
});
