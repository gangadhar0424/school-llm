# 📚 School LLM - Complete User Guide

## Overview

School LLM is an educational platform where:
- **Admins** curate educational content by adding website URLs
- **Students** browse resources, access PDFs, and use AI to study

---

## 🎭 Two User Roles

### 1️⃣ Admin/Developer Role
**Purpose:** Manage educational content

**What they do:**
- Login to admin panel
- Add educational website URLs (NCERT, CBSE, State Boards)
- System automatically scrapes and stores content
- Content becomes available to all students

### 2️⃣ Student/User Role
**Purpose:** Access and study with educational resources

**What they do:**
- Browse all available resources
- Click PDF links (opens in new tab)
- Use AI Assistant to:
  - Ask questions about PDFs
  - Get explanations
  - Summarize content
  - Study help

---

## 📖 Complete Student Journey

### Step 1: Sign Up & Login
1. Visit: **http://localhost:3000/signup.html**
2. Create account with email and password
3. Login at: **http://localhost:3000/login.html**

### Step 2: Browse Resources
1. Visit: **http://localhost:3000/resources.html**
2. See all educational resources added by admins
3. Features:
   - **Search** by keywords
   - **Filter** by board (NCERT, CBSE, etc.)
   - **View PDFs** directly

### Step 3: Access Documents
- Each resource card shows:
  - Title and description
  - Source website
  - List of available PDFs
- **Click any PDF link** → Opens in new browser tab
- Read, download, or study the PDF

### Step 4: Use AI Assistant (When Needed)
When you have questions about a PDF:

1. **Return to website**
2. **Click "Use AI Assistant"** in top navigation
3. **Add your PDF:**
   - **Option A:** Paste the PDF URL you just opened
   - **Option B:** Upload PDF from your computer
4. **Ask questions:**
   ```
   "Explain quadratic equations"
   "Summarize Chapter 5"
   "What are the key formulas?"
   "Give me practice problems"
   ```
5. **Get instant AI responses** based on the PDF content

---

## 🛠️ Admin Workflow

### Adding Content (One-Time Setup)

1. **Login to admin panel:**
   - http://localhost:3000/admin.html

2. **Add educational URLs:**
   - NCERT: `https://ncert.nic.in/textbook.php`
   - CBSE: `https://www.cbse.gov.in/newsite/textbooks.html`
   - State boards, university sites, etc.

3. **Click "Add & Scrape":**
   - System fetches the page
   - Extracts all content:
     - Page title
     - Description
     - All links
     - PDF file links
   - Stores in MongoDB

4. **Content appears on resources page:**
   - Students can now access it
   - PDFs are clickable
   - Searchable and filterable

---

## 🌐 Page Structure

```
┌─────────────────────────────────────────────┐
│          index.html (Homepage)              │
│  - Welcome page                             │
│  - Links to all sections                    │
└─────────────────────────────────────────────┘
                    │
        ┌───────────┼───────────┐
        │           │           │
        ▼           ▼           ▼
┌─────────────┐ ┌──────────────┐ ┌──────────────┐
│ signup.html │ │ login.html   │ │resources.html│
│             │ │              │ │              │
│ Create      │ │ Login to get │ │ Browse all   │
│ account     │ │ access       │ │ content      │
└─────────────┘ └──────────────┘ │ (Public)     │
                                  │              │
                                  │ Click PDF →  │
                                  │ Opens in tab │
                                  └──────────────┘
                                        │
                                        │ Need AI help?
                                        ▼
                                  ┌──────────────┐
                                  │ai-assistant  │
                                  │   .html      │
                                  │              │
                                  │ Paste URL or │
                                  │ Upload PDF   │
                                  │              │
                                  │ Chat with AI │
                                  └──────────────┘
```

---

## ✨ Key Features

### For Students:
✅ **No login required** to browse resources
✅ **Direct PDF access** - Opens in new tab
✅ **Search & filter** - Find content easily
✅ **AI Assistant** - Ask questions about any PDF
✅ **Two input methods:**
   - Paste PDF URL
   - Upload local file
✅ **Natural conversation** with AI about content

### For Admins:
✅ **Simple URL management** - Paste and scrape
✅ **Automatic extraction** - No manual entry
✅ **Persistent storage** - MongoDB database
✅ **Content statistics** - Track PDF count, updates
✅ **One-time setup** - Students access forever

---

## 🎯 Example Use Cases

### Use Case 1: Studying for Exam
```
Student → Browse Resources → Find NCERT Class 10 Math
       → Click Chapter 5 PDF → Opens in new tab
       → Read section on quadratic equations
       → Has a doubt → Returns to website
       → Clicks "Use AI Assistant"
       → Pastes PDF URL
       → Asks: "Explain the quadratic formula with examples"
       → Gets detailed AI explanation
       → Continues studying
```

### Use Case 2: Research Project
```
Student → Browse Resources → Filters to "CBSE"
       → Finds Science textbook
       → Downloads PDF locally
       → Works offline, highlights important parts
       → Needs summary → Opens AI Assistant
       → Uploads the PDF file
       → Asks: "Summarize the photosynthesis chapter"
       → Gets concise summary
       → Uses for project notes
```

### Use Case 3: Admin Adding Content
```
Admin → Logs in to admin panel
      → Pastes new state board URL
      → Clicks "Add & Scrape"
      → System extracts all PDFs
      → Content appears on resources page
      → All students can now access it
```

---

## 🔧 Technical Stack

**Frontend:**
- Pure HTML/CSS/JavaScript
- Responsive design
- localStorage for authentication

**Backend:**
- FastAPI (Python)
- JWT authentication
- MongoDB database

**AI:**
- OpenAI GPT-4 integration
- PDF processing
- Vector embeddings for context

**Scraping:**
- BeautifulSoup4
- Async HTTP requests
- Smart PDF detection

---

## 📁 MongoDB Collections

1. **users** - User accounts (students and admins)
2. **scraped_data** - All scraped website content
3. **textbooks** - Uploaded/processed PDFs for AI
4. **sessions** - User chat sessions

---

## 🚀 Getting Started

### First Time Setup:

1. **Start Backend:**
   ```bash
   START_BACKEND.bat
   ```

2. **Start Frontend:**
   ```bash
   cd frontend
   python -m http.server 3000
   ```

3. **Access Application:**
   - Homepage: http://localhost:3000
   - Resources: http://localhost:3000/resources.html
   - Admin: http://localhost:3000/admin.html
   - AI Assistant: http://localhost:3000/ai-assistant.html

### For Admins (First Time):
1. Create admin account via signup
2. Login and go to admin panel
3. Add educational URLs
4. Content ready for students!

### For Students:
1. Visit resources page (no login needed to browse)
2. Click PDFs to view
3. Login if you want to use AI Assistant
4. Upload or paste PDF URL
5. Ask questions and study!

---

## 💡 Pro Tips

### For Students:
- **Bookmark resources.html** for quick access
- **Copy PDF URL** before opening in new tab (easier to paste in AI)
- **Download PDFs** you use frequently
- **Ask specific questions** to AI for better answers
- **Use AI for:**
  - Concept clarification
  - Chapter summaries
  - Practice problems
  - Exam preparation

### For Admins:
- **Add all textbook index pages** first
- **Scrape official board websites** for authenticity
- **Re-scrape URLs** when content updates
- **Check PDF counts** in statistics

---

## 🎓 Perfect For:

✅ School students (Grades 1-12)
✅ Competitive exam preparation
✅ State board students
✅ CBSE/ICSE students
✅ Self-study learners
✅ Teachers creating resource libraries

---

## 📞 Need Help?

Check the following guides:
- **QUICK_START.md** - Quick setup instructions
- **COMPLETE_GUIDE.md** - Detailed technical guide
- **HOW_TO_START.md** - Backend startup guide

---

**🎉 Start exploring educational resources with AI-powered assistance today!**
