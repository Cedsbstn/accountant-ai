const reportTypeSelect = document.getElementById('reportType');
const dateRangePicker = document.getElementById('dateRangePicker');
const startDateInput = document.getElementById('startDate');
const endDateInput = document.getElementById('endDate');
const generateReportButton = document.getElementById('generateReportButton');
const reportOutput = document.getElementById('reportOutput');

// --- Configuration ---
// Base URL for your backend API (adjust if your API is hosted elsewhere)
const API_BASE_URL = 'http://localhost:5001'; // Assuming Python backend serves reports directly

// Define which reports require a date range
const REPORTS_REQUIRING_DATES = ['pnl', 'transactions']; // Add other report type values as needed

// --- Utility Functions ---
function displayReportMessage(message, type = 'info') {
    reportOutput.innerHTML = `<p class="report-status-${type}">${message}</p>`;
}

function formatDateForAPI(date) {
    // Ensure date is in YYYY-MM-DD format for the API
    if (!date) return '';
    // If date is already a string YYYY-MM-DD, return it
    if (typeof date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(date)) {
        return date;
    }
    // If it's a Date object, format it
    if (date instanceof Date) {
        const year = date.getFullYear();
        const month = (date.getMonth() + 1).toString().padStart(2, '0');
        const day = date.getDate().toString().padStart(2, '0');
        return `${year}-${month}-${day}`;
    }
    // Otherwise, return empty or handle error
    console.warn("Could not format date for API:", date);
    return '';
}

// --- Report Generation Logic ---

async function generateReport() {
    const reportType = reportTypeSelect.value;
    const requiresDates = REPORTS_REQUIRING_DATES.includes(reportType);
    const startDate = formatDateForAPI(startDateInput.valueAsDate); // Use valueAsDate for better handling
    const endDate = formatDateForAPI(endDateInput.valueAsDate);

    // --- Input Validation ---
    if (!reportType) {
        displayReportMessage('Please select a report type.', 'warn');
        return;
    }

    if (requiresDates && (!startDate || !endDate)) {
        displayReportMessage('Please select both a start and end date for this report.', 'warn');
        return;
    }
    if (requiresDates && startDate > endDate) {
        displayReportMessage('Start date cannot be after end date.', 'warn');
        return;
    }

    // --- API Call ---
    let apiUrl = `${API_BASE_URL}/reports/`; // Adjust base path if needed
    const queryParams = new URLSearchParams();

    switch (reportType) {
        case 'pnl':
            apiUrl += 'profit-loss';
            queryParams.append('startDate', startDate);
            queryParams.append('endDate', endDate);
            break;
        case 'transactions':
            apiUrl += 'transactions'; // Assuming this endpoint exists
            queryParams.append('startDate', startDate);
            queryParams.append('endDate', endDate);
            // Add other potential filters like tags if needed
            // queryParams.append('tag', 'some-tag');
            break;
        // Add cases for other report types
        case 'balance':
            apiUrl += 'balance-sheet'; // Assuming endpoint exists
            // Balance sheets often need a single 'as of' date
            // queryParams.append('asOfDate', endDate); // Example
            displayReportMessage('Balance Sheet report generation not yet implemented.', 'info');
            return; // Remove when implemented
        case 'ap':
            apiUrl += 'ap-aging'; // Assuming endpoint exists
            // AP Aging often needs a single 'as of' date
            // queryParams.append('asOfDate', endDate); // Example
            displayReportMessage('AP Aging report generation not yet implemented.', 'info');
            return; // Remove when implemented
        case 'cashflow':
             apiUrl += 'cashflow-statement'; // Assuming endpoint exists
             // Cash flow statements typically need a date range
             // queryParams.append('startDate', startDate);
             // queryParams.append('endDate', endDate);
            displayReportMessage('Cash Flow Statement generation not yet implemented.', 'info');
            return; // Remove when implemented
        default:
            displayReportMessage(`Report type "${reportType}" is not recognized.`, 'error');
            return;
    }

    const fullUrl = `${apiUrl}?${queryParams.toString()}`;
    console.log(`Generating report: ${reportType}, URL: ${fullUrl}`);
    displayReportMessage('⏳ Generating report...', 'info');
    generateReportButton.disabled = true;

    try {
        const response = await fetch(fullUrl);
        const data = await response.json(); // Assume backend always returns JSON

        if (!response.ok) {
            // Handle API errors (4xx, 5xx)
            const errorMsg = data.detail || data.message || `HTTP error ${response.status}`;
            console.error(`API Error (${response.status}):`, data);
            displayReportMessage(`❌ Error generating report: ${errorMsg}`, 'error');
        } else {
            // --- Success: Render the report ---
            console.log("Report data received:", data);
            renderReport(reportType, data);
        }
    } catch (error) {
        // Handle network errors
        console.error("Network or fetch error generating report:", error);
        displayReportMessage(`❌ Network error: ${error.message}. Could not fetch report.`, 'error');
    } finally {
        generateReportButton.disabled = false; // Re-enable button
    }
}

// --- Report Rendering Logic ---

function renderReport(reportType, data) {
    // Clear previous output
    reportOutput.innerHTML = '';

    const reportTitle = reportTypeSelect.options[reportTypeSelect.selectedIndex].text;
    const titleElement = document.createElement('h3');
    titleElement.textContent = `${reportTitle} Report`;
    reportOutput.appendChild(titleElement);

    // Add specific rendering based on report type and data structure returned by backend
    switch (reportType) {
        case 'pnl':
            renderProfitLossReport(data);
            break;
        case 'transactions':
            renderTransactionListReport(data);
            break;
        // Add cases for other report types
        default:
            // Generic fallback if specific renderer doesn't exist yet
            const pre = document.createElement('pre');
            pre.textContent = JSON.stringify(data, null, 2); // Display raw JSON
            reportOutput.appendChild(pre);
            break;
    }
}

function renderProfitLossReport(data) {
    // Assumes data structure like: { reportType: "...", startDate: "...", endDate: "...", data: { totalRevenue: N, totalExpenses: N, netProfit: N } }
    const reportData = data.data; // Get the nested data object
    if (!reportData) {
        displayReportMessage('Received empty or invalid data for Profit & Loss report.', 'warn');
        return;
    }

    const summary = document.createElement('div');
    summary.classList.add('report-summary');
    summary.innerHTML = `
        <p><strong>Period:</strong> ${data.startDate || 'N/A'} to ${data.endDate || 'N/A'}</p>
        <p><strong>Total Revenue:</strong> ${formatCurrency(reportData.totalRevenue)}</p>
        <p><strong>Total Expenses:</strong> ${formatCurrency(reportData.totalExpenses)}</p>
        <hr>
        <p><strong>Net Profit / (Loss):</strong> ${formatCurrency(reportData.netProfit)}</p>
    `;
    reportOutput.appendChild(summary);
}

function renderTransactionListReport(data) {
    // Assumes data is an array of transaction objects (matching schemas.Transaction)
    // Or potentially an object containing a list, e.g., { transactions: [...] }
    const transactions = Array.isArray(data) ? data : (data.transactions || []);

    if (transactions.length === 0) {
        reportOutput.innerHTML += '<p>No transactions found for the selected period.</p>';
        return;
    }

    const table = document.createElement('table');
    table.classList.add('report-table'); // Add class for styling
    table.innerHTML = `
        <caption>Transaction Details</caption>
        <thead>
            <tr>
                <th>Date</th>
                <th>Vendor</th>
                <th>Description</th>
                <th>GL Account</th>
                <th>Amount</th>
                <th>Tags</th>
                <th>Payment Method</th>
            </tr>
        </thead>
        <tbody>
            ${transactions.map(tx => `
                <tr>
                    <td>${formatDateForDisplay(tx.transactionDate)}</td>
                    <td>${tx.vendor || 'N/A'}</td>
                    <td>${tx.description || 'N/A'}</td>
                    <td>${tx.glAccount || 'N/A'}</td>
                    <td class="currency">${formatCurrency(tx.amount, tx.currency)}</td>
                    <td>${(tx.tags || []).join(', ') || 'N/A'}</td>
                    <td>${tx.paymentMethod || 'N/A'}</td>
                </tr>
            `).join('')}
        </tbody>
    `;
    reportOutput.appendChild(table);
}

// --- Helper functions for rendering ---
function formatCurrency(amount, currencyCode = 'USD') {
    if (amount == null || isNaN(amount)) return 'N/A';
    try {
        return new Intl.NumberFormat(undefined, { style: 'currency', currency: currencyCode }).format(amount);
    } catch (e) {
        // Fallback for invalid currency code
        return `$${parseFloat(amount).toFixed(2)}`;
    }
}

function formatDateForDisplay(dateString) {
    if (!dateString) return 'N/A';
    try {
        // Add time component to avoid timezone issues when parsing YYYY-MM-DD
        return new Intl.DateTimeFormat(undefined, { year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(dateString + 'T00:00:00'));
    } catch (e) {
        return dateString; // Return original string if formatting fails
    }
}


// --- Event Listeners ---

// Show/Hide Date Picker based on Report Type
reportTypeSelect.addEventListener('change', () => {
    const selectedType = reportTypeSelect.value;
    if (REPORTS_REQUIRING_DATES.includes(selectedType)) {
        dateRangePicker.style.display = 'block'; // Or 'flex', 'grid' depending on CSS
    } else {
        dateRangePicker.style.display = 'none';
    }
});

// Generate Report Button Click
generateReportButton.addEventListener('click', generateReport);

// --- Initialization ---
// Set default date range (e.g., this month) - Optional
function setDefaultDates() {
    const today = new Date();
    const firstDayOfMonth = new Date(today.getFullYear(), today.getMonth(), 1);
    const lastDayOfMonth = new Date(today.getFullYear(), today.getMonth() + 1, 0); // Last day of current month

    startDateInput.valueAsDate = firstDayOfMonth;
    endDateInput.valueAsDate = lastDayOfMonth;
}

setDefaultDates(); // Call on load
console.log("Report handler initialized.");

export { generateReport };