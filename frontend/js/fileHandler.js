// js/fileHandler.js

// --- DOM Element References ---
const uploadForm = document.getElementById('uploadForm');
const dropArea = document.getElementById('drop-area');
const fileInput = document.getElementById('fileInput');
const filePreviewList = document.getElementById('filePreviewList');
const uploadButton = document.getElementById('uploadButton');
const processingStatus = document.getElementById('processingStatus');
const transactionsTableBody = document.querySelector('#transactionsTable tbody');
const emptyListPlaceholder = filePreviewList.querySelector('.empty-list-placeholder');
const emptyTablePlaceholder = transactionsTableBody.querySelector('.empty-table-placeholder');

// --- Configuration ---
const NODE_GATEWAY_UPLOAD_URL = 'http://localhost:3001/upload'; // URL of Node.js upload endpoint
// No frontend validation needed for types/size - backend handles this

// --- State ---
let filesToUpload = []; // Array to hold File objects selected by the user
let isUploading = false; // Flag to prevent concurrent upload triggers

// --- Utility Functions ---
function formatBytes(bytes, decimals = 2) {
    if (!bytes || bytes === 0) return '0 Bytes'; // Handle null/zero bytes
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB'];
    // Handle potential non-numeric input gracefully
    const bytesNum = Number(bytes);
    if (isNaN(bytesNum) || bytesNum < 0) return 'Invalid size';
    const i = Math.floor(Math.log(bytesNum) / Math.log(k));
    return parseFloat((bytesNum / Math.pow(k, i)).toFixed(dm)) + ' ' + sizes[i];
}


function displayStatusMessage(message, type = 'info') {
    const messageElement = document.createElement('p');
    messageElement.textContent = message;
    messageElement.className = `status-${type}`; // Use className for simplicity

    // Prepend new messages
    processingStatus.insertBefore(messageElement, processingStatus.firstChild);

    // Remove the initial placeholder if it's still there and not the only child
    const placeholder = processingStatus.querySelector('p:not([class])');
    if (placeholder && processingStatus.children.length > 1) {
        processingStatus.removeChild(placeholder);
    }
}

// --- Drag & Drop Event Handlers ---
function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
}

function highlight() {
    if (isUploading) return; // Don't highlight during upload
    dropArea.classList.add('highlight');
}

function unhighlight() {
    dropArea.classList.remove('highlight');
}

function handleDrop(e) {
    if (isUploading) return; // Prevent adding files during upload
    const dt = e.dataTransfer;
    const files = dt.files;
    handleFileSelection(files);
}

// --- File Handling & Preview ---
function handleFileSelection(fileList) {
    if (isUploading) {
        displayStatusMessage('Cannot add files while an upload is in progress.', 'warn');
        return;
    }
    // Convert FileList to array
    // No frontend validation needed here as per requirement 4
    const newFiles = [...fileList].filter(file => {
        // Minimal check: prevent adding duplicates already in the preview list
        return !filesToUpload.some(existingFile => existingFile.name === file.name && existingFile.size === file.size && existingFile.lastModified === file.lastModified);
    });

    if (newFiles.length > 0) {
        filesToUpload = filesToUpload.concat(newFiles);
        updateFilePreview();
    } else if ([...fileList].length > 0) {
         displayStatusMessage(`ℹ️ Selected file(s) already in the list or no new files chosen.`, 'info');
    }
}

function updateFilePreview() {
    filePreviewList.innerHTML = ''; // Clear current preview

    if (filesToUpload.length === 0) {
        // Ensure placeholder exists if needed (might have been removed)
        if (!filePreviewList.querySelector('.empty-list-placeholder')) {
             const placeholder = document.createElement('li');
             placeholder.className = 'empty-list-placeholder';
             placeholder.textContent = 'No files selected yet.';
             filePreviewList.appendChild(placeholder);
        }
        filePreviewList.querySelector('.empty-list-placeholder').style.display = 'list-item';
        uploadButton.disabled = true;
        return;
    }

    // Hide placeholder if adding items
    const placeholder = filePreviewList.querySelector('.empty-list-placeholder');
    if (placeholder) placeholder.style.display = 'none';

    filesToUpload.forEach((file, index) => {
        const listItem = document.createElement('li');
        // Display basic file info, status will be updated during upload
        listItem.innerHTML = `
            <span class="file-name">${file.name} (${formatBytes(file.size)})</span>
            <span class="file-status" data-file-index="${index}"> - Pending</span>
            <button type="button" class="remove-file-btn" data-index="${index}" aria-label="Remove ${file.name} from upload list">×</button>
        `;
        listItem.setAttribute('data-file-index', index); // Add index to list item itself
        filePreviewList.appendChild(listItem);
    });

    uploadButton.disabled = isUploading; // Keep disabled if already uploading
}

function removeFileFromPreview(indexToRemove) {
    if (isUploading) {
        displayStatusMessage('Cannot remove files while an upload is in progress.', 'warn');
        return;
    }
    const removedFile = filesToUpload.splice(indexToRemove, 1);
    if (removedFile.length > 0) {
         displayStatusMessage(`ℹ️ Removed "${removedFile[0].name}" from upload list.`, 'info');
    }
    updateFilePreview(); // Re-render the list with updated indices
}

// --- Upload Logic (Concurrent Processing) ---

/**
 * Processes a single file by sending it to the backend.
 * Updates the status of the corresponding list item.
 * @param {File} file - The file to process.
 * @param {number} index - The index of the file in the original list for UI updates.
 */
async function processSingleFile(file, index) {
    const listItem = filePreviewList.querySelector(`li[data-file-index="${index}"]`);
    const statusSpan = listItem?.querySelector('.file-status'); // Use optional chaining

    if (statusSpan) {
        statusSpan.textContent = ' - ⏳ Uploading & Processing...';
        statusSpan.style.color = 'orange';
    } else {
        // Fallback status update if list item not found (shouldn't happen often)
        displayStatusMessage(`⏳ Uploading & Processing "${file.name}"...`, 'info');
    }

    const formData = new FormData();
    formData.append('invoice', file); // Field name MUST match backend expectation

    try {
        const response = await fetch(NODE_GATEWAY_UPLOAD_URL, {
            method: 'POST',
            body: formData,
        });

        const result = await response.json(); // Attempt to parse JSON always

        if (!response.ok) {
            // Handle backend/gateway errors (4xx, 5xx)
            const errorMsg = result.message || result.detail || `HTTP error ${response.status}`;
            if (statusSpan) {
                statusSpan.textContent = ` - ❌ Error: ${errorMsg}`;
                statusSpan.style.color = 'red';
            }
            displayStatusMessage(`❌ Error processing "${file.name}": ${errorMsg}`, 'error');
            console.error(`Backend error for "${file.name}" (${response.status}):`, result);
            // Return null or an error indicator for Promise.allSettled
            return { status: 'rejected', reason: errorMsg, fileName: file.name };
        } else {
            // Handle successful response (2xx)
            if (statusSpan) {
                statusSpan.textContent = ` - ✅ Processed`;
                statusSpan.style.color = 'green';
            }
            displayStatusMessage(`✅ Successfully processed "${file.name}".`, 'success');

            // Requirement 2: Directly parse and render data from backend output
            if (result.data) {
                // No frontend validation - trust backend structure
                addTransactionToTable(result.data, file.name);
                return { status: 'fulfilled', value: result.data, fileName: file.name };
            } else {
                // Success status but no data - treat as warning/partial failure
                 if (statusSpan) {
                    statusSpan.textContent = ` - ⚠️ Processed (No Data Returned)`;
                    statusSpan.style.color = 'orange';
                }
                displayStatusMessage(`⚠️ Received success status for "${file.name}" but no data was returned.`, 'warn');
                return { status: 'rejected', reason: 'No data returned', fileName: file.name };
            }
        }
    } catch (error) {
        // Handle network errors or issues connecting to the Node.js gateway
        console.error(`Network or fetch error for "${file.name}":`, error);
        const errorMsg = `Network error: ${error.message}`;
         if (statusSpan) {
            statusSpan.textContent = ` - ❌ Error: ${errorMsg}`;
            statusSpan.style.color = 'red';
        }
        displayStatusMessage(`❌ Network error uploading "${file.name}": ${error.message}.`, 'error');
        // Return null or an error indicator for Promise.allSettled
        return { status: 'rejected', reason: errorMsg, fileName: file.name };
    }
}


/**
 * Initiates the upload process for all files currently in the filesToUpload list.
 * Uses Promise.allSettled for concurrent uploads.
 */
async function uploadAndProcessFiles() {
    if (filesToUpload.length === 0) {
        displayStatusMessage('No files selected to upload.', 'warn');
        return;
    }
    if (isUploading) {
        displayStatusMessage('Upload already in progress.', 'info');
        return;
    }

    isUploading = true;
    uploadButton.disabled = true;
    uploadButton.textContent = 'Uploading...';
    displayStatusMessage(`⏳ Starting processing for ${filesToUpload.length} file(s)...`, 'info');

    // Create an array of promises, one for each file upload/process
    const uploadPromises = filesToUpload.map((file, index) => processSingleFile(file, index));

    // Use Promise.allSettled to wait for all uploads to complete, regardless of success/failure
    const results = await Promise.allSettled(uploadPromises);

    // --- Upload Cycle Finished ---
    isUploading = false;
    uploadButton.textContent = 'Upload Selected Files';
    // Keep button disabled because the list will be cleared
    // uploadButton.disabled = false; // Or re-enable if you want users to retry failed ones easily

    let successCount = 0;
    let errorCount = 0;

    results.forEach((result, index) => {
        const originalFile = filesToUpload[index]; // Get corresponding file
        if (result.status === 'fulfilled' && result.value?.status !== 'rejected') {
            successCount++;
            // Status already updated in processSingleFile
        } else {
            errorCount++;
            // Error message already displayed in processSingleFile
            const reason = result.reason || result.value?.reason || 'Unknown error';
            console.error(`Failed processing ${originalFile?.name || `file at index ${index}`}: ${reason}`);
        }
    });

    displayStatusMessage(`--- Processing complete: ${successCount} succeeded, ${errorCount} failed. ---`, 'info');

    // Clear the list after processing attempt
    filesToUpload = [];
    updateFilePreview(); // Update UI (shows empty list, disables button)
}

// --- Update Transactions Table ---
function addTransactionToTable(backendData, fileName) {
    // Requirement 2 & 4: Directly use backend data, no frontend validation/formatting
    // Assumes backendData structure matches schemas.ProcessResponse and contains necessary fields

    // Remove placeholder row if it exists and table is empty
    if (emptyTablePlaceholder && transactionsTableBody.rows.length === 1 && transactionsTableBody.rows[0] === emptyTablePlaceholder) {
        emptyTablePlaceholder.hidden = true;
    }

    const row = transactionsTableBody.insertRow(); // Insert row at the end
    // Use optional chaining and default values for robustness against potentially missing backend fields
    row.setAttribute('data-invoice-id', backendData?.id || '');

    // Render directly from backend data
    row.innerHTML = `
        <td>${fileName || 'N/A'}</td>
        <td>${backendData?.vendor || 'N/A'}</td>
        <td>${backendData?.invoiceNumber || 'N/A'}</td>
        <td>${backendData?.invoiceDate || 'N/A'}</td> <!-- Display date string as received -->
        <td>${backendData?.totalAmount ?? 'N/A'}</td> <!-- Display amount as received -->
        <td><span class="status-${backendData?.processingStatus?.toLowerCase().replace(/ /g, '-')}">${backendData?.processingStatus || 'Unknown'}</span></td>
        <td><button type="button" class="view-details-btn" aria-label="View details for ${fileName || 'invoice'}">Details</button></td>
      `;
      // TODO: Add event listener for the details button if needed
}


// --- Event Listeners ---

// Drag and Drop Listeners
['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
});
['dragenter', 'dragover'].forEach(eventName => {
    dropArea.addEventListener(eventName, highlight, false);
});
['dragleave', 'drop'].forEach(eventName => {
    dropArea.addEventListener(eventName, unhighlight, false);
});
dropArea.addEventListener('drop', handleDrop, false);

// File Input Change Listener
fileInput.addEventListener('change', (e) => {
    handleFileSelection(e.target.files);
    e.target.value = null; // Allow selecting the same file again
}, false);

// Remove File Button Listener (using event delegation)
filePreviewList.addEventListener('click', (e) => {
    if (e.target.classList.contains('remove-file-btn')) {
        const index = parseInt(e.target.getAttribute('data-index'), 10);
        if (!isNaN(index)) {
            removeFileFromPreview(index);
        }
    }
});

// Upload Button Listener
uploadButton.addEventListener('click', uploadAndProcessFiles, false);

// Prevent default form submission
uploadForm.addEventListener('submit', (e) => {
    e.preventDefault();
    uploadAndProcessFiles();
});

// --- Initialization ---
updateFilePreview(); // Show initial state
console.log("File handler initialized.");

// Note: Report generation logic should be in reportHandler.js
// Ensure reportHandler.js is loaded and initialized if needed.