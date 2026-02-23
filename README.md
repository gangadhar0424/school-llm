# 🎓 School LLM - AI-Powered Educational Platform

A comprehensive educational platform with dual functionality:
1. **Content Management** - Admins curate educational resources from websites
2. **AI Learning Assistant** - Students interact with PDFs using advanced AI

## 🎨 Why Does It Look Like a React App?

**It's NOT React - It's Pure HTML/CSS/JavaScript!**

Your website looks modern and polished like a React app because of:

1. **CSS Animations & Transitions**
   - Smooth fade-ins and slide effects (0.3s ease transitions)
   - Hover animations with scale transforms
   - Loading spinners and progress indicators

2. **Modern CSS Techniques**
   - **Glassmorphism**: Backdrop blur effects and frosted glass cards
   - **Gradient Overlays**: Beautiful purple gradient (#667eea → #764ba2)
   - **Flexbox & Grid**: Responsive layouts that adapt perfectly
   - **Box Shadows**: Depth and elevation for UI elements

3. **Dynamic JavaScript**
   - Tab switching without page reloads
   - Async data loading with fetch API
   - DOM manipulation for real-time updates
   - localStorage for authentication state

4. **Professional Design**
   - Font Awesome icons throughout
   - Consistent color scheme and spacing
   - Responsive design for all screen sizes
   - Smooth user interactions

**Stack**: Python (FastAPI) backend + Vanilla HTML/CSS/JS frontend = Modern web app! 🚀

## 🔐 Admin Dashboard - Complete Control

### Who Gets Admin Access?
- **First user** who signs up automatically becomes admin
- Users with email: `admin@schoolllm.com` or `admin@example.com`

### Admin Features:

#### 1. 👥 User Management Tab
- **View all users** in a comprehensive table
- See username, email, full name, and admin status
- Monitor **login counts** for each user
- Check **last login timestamps**
- **Activate/Deactivate** user accounts with one click
- Filter admin users with special badges

#### 2. 📊 Activity Logs Tab
- **Real-time activity tracking** of all user actions
- View login history with timestamps
- Monitor user interactions across the platform
- Track when users access different pages
- See detailed activity timeline

#### 3. 🔗 URL Management Tab
- **View all scraped URLs** in an organized table
- See how many PDFs were found per URL
- Check scraping dates and timestamps
- **Edit URL information** (title, description)
- **Delete obsolete URLs** with confirmation
- Monitor scraping statistics

#### 4. 🌐 Web Scraping Tab
- Add new educational website URLs
- Scrape content on-demand
- View scraping statistics (total URLs, PDFs, last update)
- Monitor all scraped content
- Refresh data anytime

**Admin dashboard URL**: `/admin.html` (requires admin login)

## ✨ Core Features

### 📚 Content Management System
- **URL-based scraping**: Paste educational website URLs to extract content
- **Automatic PDF detection**: Finds and catalogs all PDF resources
- **Metadata extraction**: Title, description, keywords
- **MongoDB storage**: Permanent content database
- **Admin panel**: Easy content management interface

### 🔍 Student Resource Browser
- **Public access**: Browse all curated content without login
- **Search & filter**: Find resources by board (NCERT, CBSE, etc.)
- **Direct PDF access**: Click to open PDFs in new tab
- **Smart categorization**: Organized by educational boards
- **Real-time updates**: New content appears immediately

### 🤖 AI Assistant Features
1. **Dual Input Methods**:
   - Paste PDF URL from browsed resources
   - Upload PDF from local computer
2. **Chat Interface**: Natural conversation about PDF content
3. **Smart Q&A**: Context-aware answers using RAG
4. **Summarization**: Generate chapter/section summaries
5. **Study Help**: Explanations, formulas, practice problems

### 🎨 User Experience
- **Two-column layout**: PDF upload + AI chat
- **Tab switching**: URL paste or file upload
- **Real-time chat**: Instant AI responses
- **Message history**: Track your conversation
- **Responsive design**: Works on all devices

## 👥 User Roles

### Admin/Developer
**Purpose**: Build content library

**Workflow**:
1. Login to admin panel
2. Paste educational website URLs
3. System scrapes and stores content
4. PDFs become available to students

### Student/User
**Purpose**: Study with resources

**Workflow**:
1. Browse resources page
2. Click PDF links (opens in new tab)
3. Use AI Assistant when needed:
   - Paste PDF URL or upload file
   - Ask questions
   - Get AI-powered help

## 🏗️ Tech Stack

### Backend
- **Framework**: FastAPI (Python 3.13)
- **Authentication**: JWT tokens with bcrypt
- **LLM**: Ollama (local)
- **Embeddings**: Sentence-Transformers (local)
- **Web Scraping**: BeautifulSoup4 + aiohttp
- **Database**: MongoDB with Motor (async)
- **PDF Processing**: PyPDF2, ChromaDB

### Frontend
- **Pure HTML/CSS/JavaScript** (No frameworks)
- **Authentication**: localStorage token management
- **UI**: Gradient design, responsive layout
- **Icons**: Font Awesome 6.4.0

### Security
- **Password hashing**: bcrypt
- **JWT tokens**: 30-minute expiry
- **Protected endpoints**: Admin functions require auth
- **Public endpoints**: Resources browsable by all

## 📋 Prerequisites

- Python 3.13
- MongoDB (Atlas or local)
- Ollama installed
- Modern web browser

## 🚀 Installation

### 1. Clone or Navigate to Project
```bash
cd c:\Users\ganga\OneDrive\Desktop\school-llm
```

### 2. Set Up Python Virtual Environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
```

### 3. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 4. Configure Environment Variables

**IMPORTANT: Open `.env.example` file and save it as `.env`, then update Ollama settings:**

```env
# Required
MONGODB_URI=mongodb://localhost:27017/school_llm
JWT_SECRET_KEY=your-secret-key-change-in-production

# Ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_CHAT_MODEL=llama3.1:8b
LOCAL_EMBEDDING_MODEL=all-MiniLM-L6-v2
```

### 5. Set Up MongoDB

**Option A: Local MongoDB**
1. Install MongoDB Community Edition from mongodb.com
2. Start MongoDB service
3. Use: `MONGODB_URI=mongodb://localhost:27017/school_llm`

**Option B: MongoDB Atlas (Cloud)**
1. Create account at mongodb.com/cloud/atlas
2. Create a free cluster
3. Get connection string
4. Update `MONGODB_URI` in `.env`

## 🎮 Running the Application

### Quick Start (Recommended)

**1. Start Backend:**
```bash
# Double-click this file or run:
START_BACKEND.bat
```
Backend runs at: `http://localhost:8000`

**2. Start Frontend:**
```bash
cd frontend
python -m http.server 3000
```
Frontend runs at: `http://localhost:3000`

**3. Access the Platform:**
- Homepage: http://localhost:3000
- Browse Resources: http://localhost:3000/resources.html
- AI Assistant: http://localhost:3000/ai-assistant.html
- Admin Panel: http://localhost:3000/admin.html (login required)

## 📖 Complete Usage Guide

### For Admins (Content Setup):

1. **Create Admin Account:**
   - Visit: http://localhost:3000/signup.html
   - Fill in details and sign up
   - Login at: http://localhost:3000/login.html

2. **Add Educational Content:**
   - Go to: http://localhost:3000/admin.html
   - Paste educational website URLs:
     ```
     https://ncert.nic.in/textbook.php
     https://www.cbse.gov.in/newsite/textbooks.html
     https://ebalbharati.in/
     ```
   - Click "Add & Scrape"
   - System extracts all PDFs and content
   - Content appears on resources page

3. **Monitor Content:**
   - View statistics (total URLs, PDFs)
   - Refresh data anytime
   - Add more URLs as needed

### For Students (Using Resources):

1. **Browse Content:**
   - Visit: http://localhost:3000/resources.html
   - No login required!
   - Search by keywords
   - Filter by board (NCERT, CBSE, etc.)

2. **Access PDFs:**
   - Click any PDF link
   - Opens in new browser tab
   - Read, download, or study

3. **Use AI Assistant:**
   - Click "Use AI Assistant" in top navigation
   - **Option A - Paste URL:**
     - Copy PDF link from resources page
     - Paste in URL field
     - Click "Process PDF from URL"
   - **Option B - Upload File:**
     - Click upload area
     - Select PDF from computer
     - Click "Process Uploaded PDF"
   - **Chat with AI:**
     - Ask questions about the PDF
     - Get explanations and summaries
     - Request practice problems
     - Study assistance

### Example Workflow:

```
Student visits resources.html
    ↓
Searches "Class 10 Math"
    ↓
Finds NCERT textbook
    ↓
Clicks PDF link → Opens in new tab
    ↓
Reads Chapter 5, has doubt
    ↓
Returns to website, clicks "Use AI Assistant"
    ↓
Pastes PDF URL or uploads file
    ↓
Asks: "Explain quadratic equations"
    ↓
Gets AI-powered explanation
    ↓
Continues studying with AI help
```

## 🔑 Where to Paste API Keys

1. Navigate to `c:\Users\ganga\OneDrive\Desktop\school-llm`
2. Find the `.env.example` file
3. **Save it as `.env`** (remove the .example)
4. Open `.env` in any text editor
5. Paste your keys:
   ```
   OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxx  ← Paste your OpenAI key here
   MONGODB_URI=mongodb://localhost:27017/school_llm  ← Use this for local MongoDB
   VIDEO_API_PROVIDER=d-id
   DID_API_KEY=xxxxxxxxxxxxx  ← Paste your D-ID key here (optional)
   ```
6. Save the file

## 📁 Project Structure

```
school-llm/
├── backend/
│   ├── ai/              # AI modules (chat, summary, quiz, etc.)
│   ├── main.py          # FastAPI app with all endpoints
│   ├── auth.py          # JWT authentication & password hashing
│   ├── scraper.py       # Web scraper for educational content
│   ├── database.py      # MongoDB models (User, Scraper, Textbook)
│   ├── vector_db.py     # ChromaDB for embeddings
│   ├── pdf_handler.py   # PDF processing
│   ├── config.py        # Configuration settings
│   └── requirements.txt # Python dependencies
│
├── frontend/
│   ├── index.html           # Homepage
│   ├── resources.html       # Browse educational content (public)
│   ├── ai-assistant.html    # AI chat with PDFs
│   ├── admin.html           # Admin panel for content management
│   ├── signup.html          # User registration
│   ├── login.html           # User login
│   ├── dashboard.html       # Original dashboard (optional)
│   └── styles.css           # Styling
│
├── .env                 # Environment variables (CREATE THIS!)
├── .env.example         # Template for environment variables
├── START_BACKEND.bat    # Windows startup script
├── QUICK_START.md       # Quick setup guide
├── USER_GUIDE.md        # Complete user manual
└── README.md            # This file
```

## 🗄️ MongoDB Collections

1. **users** - User accounts with bcrypt-hashed passwords
2. **scraped_data** - Educational website content and PDF links
3. **textbooks** - Uploaded/processed PDFs for AI
4. **sessions** - User chat sessions with AI

## 📄 Page Overview

| Page | Access | Purpose |
|------|--------|---------|
| `index.html` | Public | Homepage with navigation |
| `resources.html` | Public | Browse all educational content |
| `signup.html` | Public | Create new account |
| `login.html` | Public | User login |
| `ai-assistant.html` | Public | Chat with PDFs using AI |
| `admin.html` | Protected | Manage content URLs (admin only) |

## 🐛 Troubleshooting

### "Configuration validation failed"
- Check `.env` file exists (not `.env.example`)
- Verify API keys are pasted correctly
- No spaces around the `=` sign
- Ensure JWT_SECRET_KEY is set

### MongoDB Connection Error
- Ensure MongoDB is running
- Check MONGODB_URI in `.env`
- For Atlas: Verify IP whitelist and credentials

### "Invalid token" or Authentication Errors
- Token expired (30 minutes)
- Logout and login again
- Clear browser localStorage

### Scraper Not Working
- Check URL is accessible
- Verify internet connection
- Some sites may block scraping

### CORS Error
- Use `python -m http.server 3000` to serve frontend
- Don't open HTML file directly in browser
- Check backend CORS_ORIGINS setting

## 🎯 Getting API Keys

**OpenAI (Required)**: 
1. Visit https://platform.openai.com/api-keys
2. Create new key → Copy → Paste in `.env`

**D-ID (Optional - for video generation)**:
1. Visit https://studio.d-id.com
2. Account Settings → API → Copy key → Paste in `.env`

## 📚 Documentation

- **QUICK_START.md** - Fast setup guide with examples
- **USER_GUIDE.md** - Complete user manual with workflows
- **COMPLETE_GUIDE.md** - Technical details and configuration
- **HOW_TO_START.md** - Backend startup instructions

## 🌟 Key Highlights

✅ **No automation** - Manually curate quality content
✅ **Public browsing** - Students can view without login
✅ **Dual AI input** - Paste URLs or upload local files
✅ **JWT security** - Protected admin functions
✅ **Real-time chat** - Instant AI responses
✅ **Persistent storage** - MongoDB for all data
✅ **PDF detection** - Automatically finds educational PDFs
✅ **Search & filter** - Easy content discovery

---

**🎓 Ready to transform educational content access with AI! Follow the installation steps and start curating resources.**