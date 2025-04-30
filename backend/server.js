const express = require('express');
const cors = require('cors');
const path = require('path');
const multer = require('multer');
const fs = require('fs');
const { promises: fsPromises } = require('fs');
const axios = require('axios');
const FormData = require('form-data');
const helmet = require('helmet');
const morgan = require('morgan');

// Configuration
const PORT = process.env.PORT || 3001;
const UPLOAD_DIR = path.join(__dirname, 'uploads');
const ALLOWED_MIME_TYPES = ['application/pdf', 'image/jpeg', 'image/png'];
const MAX_FILE_SIZE = 10 * 1024 * 1024; // 10MB

// Initialize Express app
const app = express();

// Middleware setup
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));
app.use(morgan('combined'));

// Static files
const frontendPath = path.join(__dirname, '../frontend');
app.use(express.static(frontendPath));

// Multer setup
const storage = multer.diskStorage({
  destination: async (req, file, cb) => {
    try {
      await fsPromises.access(UPLOAD_DIR);
    } catch {
      await fsPromises.mkdir(UPLOAD_DIR, { recursive: true });
    }
    cb(null, UPLOAD_DIR);
  },
  filename: (req, file, cb) => {
    const uniqueSuffix = Date.now() + '-' + Math.round(Math.random() * 1E9);
    cb(null, `${file.fieldname}-${uniqueSuffix}${path.extname(file.originalname)}`);
  }
});

const upload = multer({
  storage,
  limits: { fileSize: MAX_FILE_SIZE },
  fileFilter: (req, file, cb) => {
    if (!ALLOWED_MIME_TYPES.includes(file.mimetype)) {
      return cb(new Error('Invalid file type'));
    }
    cb(null, true);
  }
});

// Routes
app.get('/', (req, res) => {
  const indexPath = path.join(frontendPath, 'index.html');
  res.sendFile(indexPath, (err) => {
    if (err) {
      console.error('Error serving index.html:', err);
      res.status(500).send('Internal Server Error');
    }
  });
});

app.post('/upload', upload.single('invoice'), async (req, res) => {
  try {
    if (!req.file) {
      return res.status(400).json({ message: 'No file uploaded' });
    }

    console.log('File uploaded successfully:', req.file.originalname);

    // Forward file to Python AI Agent
    const formData = new FormData();
    formData.append("file", fs.createReadStream(req.file.path), req.file.originalname);

    const response = await axios.post("http://localhost:5001/process", formData, {
      headers: formData.getHeaders()
    });

    const requiredFields = [
      "vendor", "invoiceDate", "dueDate", "invoiceNumber", "lineItems", 
      "subtotal", "tax", "totalAmount"
    ];

    const missing = requiredFields.filter(f => !(f in response.data));
    if (missing.length > 0) {
      console.error("Missing fields from AI Agent:", missing);
      try {
        await fsPromises.unlink(req.file.path);
      } catch (err) {
        console.error("Error deleting temp file:", err.message);
      }
      return res.status(500).json({ 
        message: `AI response missing required fields: ${missing.join(', ')}` 
      });
    }

    res.json({
      message: 'Processed by Python AI Agent',
      data: response.data
    });

  } catch (err) {
    console.error("Error processing request:", err.message);
    
    // Clean up uploaded file if it exists
    if (req.file?.path) {
      try {
        await fsPromises.unlink(req.file.path);
      } catch (err) {
        console.error("Error deleting temp file:", err.message);
      }
    }

    res.status(500).json({ 
      message: err.message || "Internal server error" 
    });
  }
});

// Error handling middleware
app.use((err, req, res, next) => {
  console.error('Server error:', err.message);
  
  if (err.code === 'LIMIT_FILE_SIZE') {
    return res.status(413).json({ 
      message: 'File size exceeds maximum allowed limit (10MB)' 
    });
  }
  
  if (err.message === 'Invalid file type') {
    return res.status(400).json({ 
      message: 'Invalid file type' 
    });
  }
  
  res.status(500).json({ 
    message: 'Internal server error' 
  });
});

// Start server
app.listen(PORT, () => {
  console.log(`Backend server running at http://localhost:${PORT}`);
});