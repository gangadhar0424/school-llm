# 🚀 Quick Start Guide - School LLM

## Complete Workflow

### 👨‍💼 For Admins/Developers (Content Management)

**1. Start the Backend**
```bash
START_BACKEND.bat
```

**2. Login to Admin Panel**
- Visit: http://localhost:3000/login.html
- Login with your credentials

**3. Add Educational Content**
- Go to: http://localhost:3000/admin.html
- Paste educational website URLs:
  ```
  NCERT: https://ncert.nic.in/textbook.php
  CBSE: https://www.cbse.gov.in/newsite/textbooks.html
  State Boards: Various state board URLs
  ```
- Click **"Add & Scrape"** for each URL
- System extracts: Title, Description, Links, PDF files
- Everything saves to MongoDB database

---

### 👨‍🎓 For Students/Users (Using the Platform)

**Step 1: Create Account & Login**
- Visit: http://localhost:3000/signup.html
- Create your account
- Login at: http://localhost:3000/login.html

**Step 2: Browse Educational Documents**
- Visit: http://localhost:3000/resources.html
- See all available resources
- Filter by: All Resources, PDFs Only, NCERT, CBSE
- Search by keywords

**Step 3: Access PDFs**
- Click on any PDF link
- **Opens in new tab** → You can view/download
- Multiple PDFs per resource shown

**Step 4: Use AI Assistant (Optional)**
When you want to ask questions about a PDF:

1. **Return to the website**
2. **Click "Use AI Assistant"** button (top navigation)
3. **Choose how to add PDF:**
   - **Option A: Paste URL** - Copy PDF link, paste it
   - **Option B: Upload File** - Upload from your computer
4. **Chat with AI:**
   - Ask questions about the PDF
   - Get summaries
   - Clarify concepts
   - Study assistance

---

## 📋 Example User Journey

```
1. Student logs in
   ↓
2. Goes to "Browse Resources" page
   ↓
3. Sees NCERT Class 10 Math textbook
   ↓
4. Clicks PDF link → Opens in new tab
   ↓
5. Reads Chapter 5, has a question
   ↓
6. Returns to website, clicks "Use AI Assistant"
   ↓
7. Pastes the PDF URL or uploads the file
   ↓
8. Asks: "Explain quadratic equations with examples"
   ↓
9. AI provides detailed explanation
   ↓
10. Student continues studying with AI help
```

---

## 🌐 All Pages Explained

### Public Pages (No Login)
- **index.html** - Homepage
- **resources.html** - Browse all educational content
- **signup.html** - Create account
- **login.html** - Login page

### Protected Pages (Login Required)
- **admin.html** - Add/manage URLs (for developers)
- **ai-assistant.html** - Chat with PDFs using AI

---

## 🎯 URLs You Can Add (For Admins)

### NCERT
```
https://ncert.nic.in/textbook.php
https://ncert.nic.in/exemplar-problems.php
```

### CBSE
```
https://www.cbse.gov.in/newsite/textbooks.html
https://cbseacademic.nic.in/e-books.html
```

### State Boards
```
Maharashtra: https://ebalbharati.in/
Karnataka: https://ktbs.kar.nic.in/
Tamil Nadu: https://www.tnschools.gov.in/textbooks
Delhi: http://www.edudel.nic.in/
```

---

## ✨ Features

### For Users:
✅ Browse educational content by board
✅ Click PDF links → Opens in new tab
✅ Search and filter resources
✅ AI Assistant for any PDF (URL or upload)
✅ Chat with documents using AI
✅ Get explanations and summaries

### For Admins:
✅ Manual URL submission
✅ Automatic content scraping
✅ MongoDB storage (permanent)
✅ View statistics (PDFs count, last update)

---

## 🚀 Quick Setup

```bash
# 1. Start backend
START_BACKEND.bat

# 2. Start frontend (new terminal)
cd frontend
python -m http.server 3000

# 3. Open browser
http://localhost:3000
```

**That's it! Everything is ready to use.**
