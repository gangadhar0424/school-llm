# Quiz Question Type Dropdown Implementation
**Date:** April 7, 2026  
**Update:** Converted from multi-select buttons to single-select dropdown

---

## 📋 Overview

The quiz module now features a **single-select dropdown** for choosing the question type. Users select ONE question type from the dropdown, and ALL generated questions will be of that type.

---

## 🎯 Question Type Options

The dropdown contains 4 options:

1. **Multiple Choice (MCQ)** - Default option
   - 4 multiple choice answers (A, B, C, D)
   - Traditional academic format
   
2. **Fill-in-the-Blank**
   - Students type the answer
   - Partial keyword matching for grading
   
3. **True/False**
   - Binary choice questions
   - Exact match grading
   
4. **Short Answer**
   - Open-ended text response
   - Partial keyword matching for grading

---

## 🎨 UI Changes

### **Before: Multi-Select Buttons**
```
Question Types:
[MCQ]      [Fill-in-blank]    [True/False]    [Short Answer]
(can select multiple)
```

### **After: Single-Select Dropdown**
```
Question Type:
┌─────────────────────────────────────────┐
│ Multiple Choice (MCQ)            ▼      │
└─────────────────────────────────────────┘
(select ONE)
```

---

## 💻 Implementation Details

### **HTML Changes**
Replaced button group with dropdown:

```html
<!-- BEFORE -->
<div class="question-type-selector">
    <label>Question Types:</label>
    <div class="type-buttons">
        <button class="type-btn active" data-type="mcq" onclick="toggleQuestionType(this)">MCQ</button>
        <button class="type-btn" data-type="fill-in-blank" onclick="toggleQuestionType(this)">Fill-in-blank</button>
        <!-- ... more buttons -->
    </div>
</div>

<!-- AFTER -->
<div class="question-type-selector">
    <label for="questionTypeDropdown">Question Type:</label>
    <select class="question-type-dropdown" id="questionTypeDropdown" onchange="selectQuestionType(this.value)">
        <option value="mcq" selected>Multiple Choice (MCQ)</option>
        <option value="fill-in-blank">Fill-in-the-Blank</option>
        <option value="true-false">True/False</option>
        <option value="short-answer">Short Answer</option>
    </select>
</div>
```

### **CSS Changes**
New styling for dropdown:

```css
.question-type-dropdown {
    width: 100%;
    padding: .7rem;
    border: 1px solid var(--border);
    border-radius: 10px;
    background: var(--surface);
    color: var(--text);
    font-size: .9rem;
    font-weight: 500;
    cursor: pointer;
    transition: all .25s;
}

.question-type-dropdown:hover {
    border-color: var(--info);
}

.question-type-dropdown:focus {
    outline: none;
    border-color: var(--info);
    box-shadow: 0 0 0 3px rgba(59,130,246,.1);
}
```

### **JavaScript Changes**

**Before:**
```javascript
let selectedQuestionTypes = ['mcq'];  // Array of types

function toggleQuestionType(btn){
    const type = btn.dataset.type;
    const isActive = btn.classList.contains('active');
    
    if(isActive){
        selectedQuestionTypes = selectedQuestionTypes.filter(t => t !== type);
        if(selectedQuestionTypes.length === 0){
            selectedQuestionTypes = ['mcq'];
        }
    } else {
        selectedQuestionTypes.push(type);
    }
}
```

**After:**
```javascript
let selectedQuestionType = 'mcq';  // Single type as string

function selectQuestionType(type){
    selectedQuestionType = type;
    console.log('Selected question type:', selectedQuestionType);
}
```

**generateQuiz() Update:**
```javascript
// BEFORE
const payload = {
    pdf_url: pdfRef,
    num_questions: numQ,
    difficulty: selectedDiff,
    question_types: selectedQuestionTypes  // Array
};

// AFTER
const payload = {
    pdf_url: pdfRef,
    num_questions: numQ,
    difficulty: selectedDiff,
    question_types: [selectedQuestionType]  // Converted to array
};
```

---

## 🔄 User Workflow

### **Step 1: Select Question Type**
1. Go to Quiz section
2. Click dropdown "Question Type:"
3. Select one option (e.g., "Fill-in-the-Blank")
4. Dropdown closes with selection highlighted

### **Step 2: Enter Topic (Optional)**
- Type search query for topic filtering

### **Step 3: Select Difficulty**
- Choose Basic, Medium, or Hard

### **Step 4: Set Number of Questions**
- Type number (1-15)

### **Step 5: Generate**
- Click "Generate Quiz"
- All questions will be of the selected type

### **Example Flow**
```
1. Dropdown: Select "True/False"
2. Topic: "Photosynthesis"
3. Difficulty: Medium
4. Number: 5

Result: 5 True/False questions about photosynthesis at medium difficulty
- Question 1: True or False: Photosynthesis requires sunlight.
- Question 2: True or False: Photosynthesis produces oxygen only.
- ... (3 more True/False questions)
```

---

## 📊 Backend Compatibility

The backend already accepts `question_types` as an array:

```python
class QuizRequest(BaseModel):
    pdf_url: str
    num_questions: Optional[int] = None
    difficulty: Optional[str] = None
    search_query: Optional[str] = None
    question_types: Optional[List[str]] = None  # ["fill-in-blank"]
```

When frontend sends single type:
```json
{
  "pdf_url": "upload_123",
  "num_questions": 3,
  "difficulty": "medium",
  "question_types": ["fill-in-blank"]  // Single type in array
}
```

Backend distributes all questions as that type (since array has only 1 element).

---

## 🎯 Question Generation Logic

### **Backend Processing**
```python
# Quiz generation with single type
question_types = ["fill-in-blank"]  # From frontend

# Backend generates 3 MCQ-format questions first
generated_questions = [q1_mcq, q2_mcq, q3_mcq]

# Then converts all to requested type
for question in generated_questions:
    converted = convert_to_question_type(question, "fill-in-blank")
    # Result: 3 fill-in-the-blank questions
```

### **Rendering**
Frontend renders based on `question.question_type`:
```javascript
if (qType === 'fill-in-blank') {
    // Show text input field
    optionsHtml = `<input type="text" class="q-fib-input" ... >`;
} else if (qType === 'mcq') {
    // Show 4 option buttons
    optionsHtml = `<div class="q-option" ...>`;
}
```

---

## ✨ Benefits of Dropdown

| Aspect | Multi-Buttons | Single-Dropdown |
|--------|---------------|-----------------|
| **Screen Space** | 4 buttons (wide) | Compact dropdown |
| **Clarity** | "Select multiple" options | "Select one" clear intent |
| **Mobile** | Cramped layout | Responsive & clean |
| **Accessibility** | Larger click targets | Standard dropdown |
| **User Confusion** | "Can I mix types?" unclear | Single type obvious |
| **UX Simplicity** | Learning curve | Familiar pattern |

---

## 🧪 Testing Scenarios

### **Test 1: Default Selection**
```
Page loads
Expected: Dropdown shows "Multiple Choice (MCQ)" selected
```

### **Test 2: Change Selection**
```
Click dropdown → Select "True/False" → Generate quiz
Expected: All questions are True/False format
```

### **Test 3: With Topic Filter**
```
Topic: "Algebra"
Type: "Short Answer"
Questions: 3
Expected: 3 short answer questions about algebra
```

### **Test 4: Answer Submission**
```
Type = "Fill-in-the-Blank"
User enters answer in text field
Submit
Expected: Grading uses keyword matching (50%+ words)
```

### **Test 5: Different Difficulties**
```
Test each combination:
- MCQ + Basic
- Fill-in-blank + Medium
- True/False + Hard
- Short Answer + Basic
Expected: All combinations work correctly
```

---

## 📝 Files Modified

**frontend/ai-features.html**

1. **HTML Section (line 870-880):**
   - Replaced button group with `<select>` dropdown
   - Added 4 `<option>` elements

2. **CSS Section (line 468-480):**
   - Removed `.type-buttons` and `.type-btn` styles
   - Added `.question-type-dropdown` styles
   - Added hover/focus effects

3. **JavaScript Section:**
   - Line ~950: Changed `selectedQuestionTypes` to `selectedQuestionType`
   - Replaced `toggleQuestionType()` with `selectQuestionType()`
   - Updated `generateQuiz()` to use single type

---

## 🚀 How to Test

1. **Restart frontend:** Automatic (no backend restart needed)
2. **Open browser:** http://localhost:3000
3. **Navigate to Quiz:**
   - Upload a PDF
   - Go to Quiz section
   - Open the "Question Type:" dropdown
   - Select a type
   - Generate quiz
   - Verify all questions are of selected type

---

## 🎉 Summary

✅ **Single-select dropdown** - Cleaner UI
✅ **One question type per quiz** - Less confusion
✅ **All questions match type** - Consistent experience
✅ **Backend compatible** - No changes needed
✅ **Mobile friendly** - Compact layout
✅ **Familiar pattern** - Standard dropdown behavior

---

**Quiz Module Successfully Upgraded!** 🎓
