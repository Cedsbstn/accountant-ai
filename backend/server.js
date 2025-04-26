const express = require('express');
const cors = require('cors');
const path = require('path');
const multer = require('multer'); // Import multer
const fs = require('fs'); // File system module
const axios = require('axios');
const FormData = require('form-data');
const { error } = require('console');

// --- Multer Configuration ---
const UPLOAD_DIR = './uploads'; // Directory to save uploaded files
// Ensure upload directory exists
if (!fs.existsSync(UPLOAD_DIR)){
    fs.mkdirSync(UPLOAD_DIR, { recursive: true });
}

const storage = multer.diskStorage({
    destination: function (req, file, cb) {
        cb(null, UPLOAD_DIR); // Save files to the 'uploads' directory
    },
    filename: function (req, file, cb) {
        // Create a unique filename to avoid overwrites
        const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
        cb(null, file.fieldname + '-' + uniqueSuffix + path.extname(file.originalname));
    }
});

const upload = multer({
    storage: storage,
    limits: { fileSize: 10 * 1024 * 1024 } // Limit file size (e.g., 10MB)
});

// --- Express App Setup ---
const app = express();
const port = 3001;

app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Serve static files from frontend directory
const frontendPath = path.join(__dirname, '../frontend');
console.log('Serving frontend from:', frontendPath);

// Serve static files with proper configuration
app.use(express.static(frontendPath));

// Debug middleware to log all requests
app.use((req, res, next) => {
    console.log(`[DEBUG] ${req.method} ${req.url}`);
    next();
});

// Additional catch-all middleware for 404s
app.use((req, res, next) => {
    if (!res.headersSent) {
        console.log(`[DEBUG] 404 Not Found: ${req.url}`);
        res.status(404).send(`File not found: ${req.url}`);
    }
    next();
});

// --- Routes ---
app.get('/', (req, res) => {
    const indexPath = path.join(frontendPath, 'index.html');
    console.log('Serving index.html from:', indexPath);
    if (fs.existsSync(indexPath)) {
        res.sendFile(indexPath);
    } else {
        console.error('index.html not found at:', indexPath);
        res.status(404).send('index.html not found');
    }
});

// Updated Upload Route - using multer middleware for single file named 'invoice'
app.post('/upload', upload.single('invoice'), async (req, res) => {
    console.log("Request received on /upload");

    if (!req.file) {
        console.error("No file uploaded.");
        return res.status(400).json({ message: 'No file uploaded.' });
    }

    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png'];
    if (!allowedTypes.includes(req.file.mimetype)) {
        console.error("Invalid file type:", req.file.mimetype);
         // Delete the uploaded file since it's invalid
        fs.unlinkSync(req.file.path);
        return res.status(400).json({ message: 'Invalid file type.' });
    }
    console.log('File uploaded successfully:', req.file.originalname);

    // ✅ Forward file to Python AI Agent
  try {
    const formData = new FormData();
    formData.append("file", fs.createReadStream(req.file.path), req.file.originalname);

    const response = await axios.post("http://localhost:5001/process", formData, {
      headers: formData.getHeaders()
    });

    res.json({
      message: 'Processed by Python AI Agent',
      data: response.data
    });
    const requiredFields = [
        "vendor", "invoiceDate", "dueDate", "invoiceNumber", "lineItems", "subtotal", "tax", "totalAmount"
    ];

    const missing = requiredFields.filter(f => !(f in response.data));
    if (missing.length > 0) {
        console.error("Missing fields from AI Agent:", missing);
        return res.status(500).json({ message: `AI response missing: ${missing.join(', ')}` });
    }

  } catch (err) {
    console.error("Error communicating with AI Agent:", err.message);
    res.status(500).json({ message: "AI agent error" });
    fs.unlink(req.file.path, err => {
        if (err) console.error("Error deleting temp file:", err.message);
    });
  }
});

// --- Start Server ---
app.listen(port, () => {
  console.log(`Backend server running at http://localhost:${port}`);
});