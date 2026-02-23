# 🎯 START HERE - School LLM Setup

## 👋 Welcome!

Your complete School LLM project is ready! This guide will get you started in **3 simple steps**.

---

## ⚡ 3-Step Quick Start

### ✅ STEP 1: Get Your API Keys (5 minutes)

You need **2 required** keys:

#### 1️⃣ OpenAI API Key (Required)
1. Visit: **https://platform.openai.com/api-keys**
2. Sign up or login
3. Click "Create new secret key"
4. **Copy the key** (starts with `sk-`)
5. Save it somewhere safe!

#### 2️⃣ MongoDB (Required)
Choose one option:

**Option A: MongoDB Atlas (Cloud - Easiest)**
1. Visit: **https://www.mongodb.com/cloud/atlas**
2. Create free account
3. Create a cluster (free tier)
4. Click "Connect" → "Connect your application"
5. **Copy the connection string**
6. Replace `<password>` with your actual password

**Option B: Local MongoDB**
1. Download from: **https://www.mongodb.com/try/download/community**
2. Install MongoDB
3. Use this URI: `mongodb://localhost:27017/school_llm`

#### 3️⃣ Video API (Optional - for video feature)
Only if you want AI video generation:
- **D-ID**: https://studio.d-id.com
- **OR HeyGen**: https://app.heygen.com

---

### ✅ STEP 2: Paste Your API Keys (2 minutes)

1. **Find this file**: `.env.example` in your project folder
   ```
   c:\Users\ganga\OneDrive\Desktop\school-llm\.env.example
   ```

2. **Copy it** and **rename to**: `.env`
   ```
   c:\Users\ganga\OneDrive\Desktop\school-llm\.env
   ```

3. **Open `.env`** in Notepad (or any text editor)

4. **Paste your keys**:
   ```env
   # Paste your OpenAI key here (replace everything after =)
   OPENAI_API_KEY=sk-your-actual-key-paste-here
   
   # Paste your MongoDB URI here
   MONGODB_URI=mongodb://localhost:27017/school_llm
   # OR if using Atlas:
   # MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/school_llm
   
   # Video (optional - can skip)
   VIDEO_API_PROVIDER=d-id
   DID_API_KEY=your-did-key-if-you-have-one
   ```

5. **Save the file** (Ctrl+S)

**IMPORTANT**: 
- No spaces around `=` sign
- No quotes around values
- Replace the example text with your actual keys

---

### ✅ STEP 3: Run the Application (3 minutes)

#### Option A: Automatic (Easiest) 🚀

**Just double-click**: `start.bat`

It will:
- Create virtual environment
- Install dependencies
- Start backend
- Start frontend
- Open browser

**Done!** Dashboard opens automatically.

#### Option B: Manual (If start.bat doesn't work)

**Terminal 1 - Backend:**
```bash
# Navigate to project
cd c:\Users\ganga\OneDrive\Desktop\school-llm

# Create virtual environment (first time only)
python -m venv venv

# Activate it
venv\Scripts\activate

# Install dependencies (first time only)
cd backend
pip install -r requirements.txt

# Seed database (first time only)
python seed_data.py

# Start backend
python main.py
```

**Terminal 2 - Frontend:**
```bash
# Navigate to frontend
cd c:\Users\ganga\OneDrive\Desktop\school-llm\frontend

# Start frontend server
python -m http.server 3000
```

**Open browser**: http://localhost:3000/dashboard.html

---

## 🎉 You're Done!

If you see the dashboard with textbooks, **you're all set!**

### ✅ First Test:
1. Click on any textbook (e.g., "NCERT Mathematics Class 9")
2. Click **"Use AI"** button (top right)
3. Click **"Use Selected PDF"**
4. Wait for processing (~10 seconds)
5. Click **"Summarization"**
6. See AI-generated summary!

---

## 📚 What to Read Next

| If you want to... | Read this file |
|-------------------|----------------|
| Quick 5-min setup | `QUICKSTART.md` |
| Detailed setup steps | `SETUP_CHECKLIST.md` |
| Understand API keys | `API_KEYS_GUIDE.md` |
| Fix errors | `TROUBLESHOOTING.md` |
| Learn about features | `README.md` |
| See all files | `FILE_STRUCTURE.md` |

---

## 🐛 Something Not Working?

### Quick Checks:

**Backend won't start?**
- Check `.env` file exists (not `.env.example`)
- Verify API keys are pasted correctly
- Make sure MongoDB is running

**No textbooks showing?**
- Run: `python backend/seed_data.py`
- Check backend terminal for errors

**CORS error?**
- Don't open `dashboard.html` directly from file explorer
- Use: `python -m http.server 3000`
- Then open: http://localhost:3000/dashboard.html

**AI features not working?**
- Check OpenAI API key is correct
- Verify you have credits in OpenAI account
- Check backend terminal for error details

**Still stuck?**
- Read: `TROUBLESHOOTING.md`
- Check: `SETUP_CHECKLIST.md`

---

## 💡 Pro Tips

1. **Keep terminals open** - Both backend and frontend need to run
2. **First AI request is slow** - Loading models takes ~10 seconds
3. **Check browser console** - Press F12 to see errors
4. **Check backend terminal** - See detailed error messages
5. **Use sample textbooks** - They're already loaded after seeding

---

## 🎯 What You Can Do

### AI Features Available:
- ✅ **Summarization**: Get short or detailed summaries
- ✅ **Quiz Generation**: Test your knowledge (10+ questions)
- ✅ **Q&A Chat**: Ask questions about the content
- ✅ **Audio Overview**: Listen to summaries
- ✅ **Video Overview**: Watch AI-generated explanations

### PDF Sources:
- ✅ Use textbooks from dashboard
- ✅ Paste any PDF link
- ✅ Upload your own PDF files

---

## 🚀 Ready to Go!

### Quick Command Reference:

```bash
# Start everything
start.bat

# Or manually:
# Backend (Terminal 1):
cd backend
python main.py

# Frontend (Terminal 2):
cd frontend
python -m http.server 3000
```

### URLs to Remember:
- **Frontend**: http://localhost:3000/dashboard.html
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs

---

## 📞 Need Help?

1. Check `TROUBLESHOOTING.md`
2. Review `SETUP_CHECKLIST.md`
3. Read error messages carefully
4. Verify API keys are correct

---

## ✅ Success Checklist

- [ ] OpenAI API key obtained
- [ ] MongoDB setup (local or Atlas)
- [ ] `.env` file created from `.env.example`
- [ ] API keys pasted in `.env`
- [ ] Backend started successfully
- [ ] Frontend accessible in browser
- [ ] Dashboard shows textbooks
- [ ] Can generate summary
- [ ] All AI features working

---

## 🎓 You're All Set!

**Enjoy your AI-powered learning platform!**

Built with ❤️ for students everywhere.

---

**Next Step**: Just follow the 3 steps above and you'll be running in 10 minutes!
