// School LLM - Frontend Application Logic
// API Configuration
const API_BASE_URL = 'http://localhost:8000/api';

// State Management
let appState = {
    selectedBoard: null,
    selectedClass: null,
    selectedSubject: null,
    currentTextbook: null,
    currentPdfUrl: null,
    conversationHistory: [],
    isPdfLoaded: false
};

// DOM Elements
const elements = {
    // Sidebar controls
    menuBtn: document.getElementById('menuBtn'),
    leftSidebar: document.getElementById('leftSidebar'),
    rightSidebar: document.getElementById('rightSidebar'),
    closeLeftSidebar: document.getElementById('closeLeftSidebar'),
    closeRightSidebar: document.getElementById('closeRightSidebar'),
    
    // Board and search
    boardSelector: document.getElementById('boardSelector'),
    searchInput: document.getElementById('searchInput'),
    classFilter: document.getElementById('classFilter'),
    subjectFilter: document.getElementById('subjectFilter'),
    
    // Views
    hierarchyView: document.getElementById('hierarchyView'),
    textbooksGrid: document.getElementById('textbooksGrid'),
    pdfViewer: document.getElementById('pdfViewer'),
    pdfFrame: document.getElementById('pdfFrame'),
    pdfTitle: document.getElementById('pdfTitle'),
    aiOutput: document.getElementById('aiOutput'),
    outputContent: document.getElementById('outputContent'),
    outputTitle: document.getElementById('outputTitle'),
    
    // Buttons
    useAiBtn: document.getElementById('useAiBtn'),
    backToGrid: document.getElementById('backToGrid'),
    closeOutput: document.getElementById('closeOutput'),
    
    // PDF selection
    useSelectedPdf: document.getElementById('useSelectedPdf'),
    pasteLinkBtn: document.getElementById('pasteLinkBtn'),
    uploadFileBtn: document.getElementById('uploadFileBtn'),
    fileInput: document.getElementById('fileInput'),
    pdfLinkInput: document.getElementById('pdfLinkInput'),
    pdfUrlField: document.getElementById('pdfUrlField'),
    submitPdfUrl: document.getElementById('submitPdfUrl'),
    selectedPdfInfo: document.getElementById('selectedPdfInfo'),
    
    // AI features
    pdfSelector: document.getElementById('pdfSelector'),
    aiFeatures: document.getElementById('aiFeatures'),
    summaryCard: document.getElementById('summaryCard'),
    quizCard: document.getElementById('quizCard'),
    qaCard: document.getElementById('qaCard'),
    audioCard: document.getElementById('audioCard'),
    videoCard: document.getElementById('videoCard'),
    
    // Loading
    loadingOverlay: document.getElementById('loadingOverlay'),
    loadingText: document.getElementById('loadingText')
};

// ==================== INITIALIZATION ====================
document.addEventListener('DOMContentLoaded', () => {
    initializeEventListeners();
    loadTextbooks();
});

function initializeEventListeners() {
    // Sidebar toggles
    elements.menuBtn.addEventListener('click', () => toggleSidebar('left'));
    elements.closeLeftSidebar.addEventListener('click', () => toggleSidebar('left'));
    elements.closeRightSidebar.addEventListener('click', () => toggleSidebar('right'));
    elements.useAiBtn.addEventListener('click', () => toggleSidebar('right'));
    
    // Board and filters
    elements.boardSelector.addEventListener('change', onBoardChange);
    elements.searchInput.addEventListener('input', debounce(onSearch, 300));
    elements.classFilter.addEventListener('change', applyFilters);
    elements.subjectFilter.addEventListener('change', applyFilters);
    
    // Navigation
    elements.backToGrid.addEventListener('click', showHierarchyView);
    elements.closeOutput.addEventListener('click', () => {
        elements.aiOutput.style.display = 'none';
    });
    
    // PDF selection
    elements.pasteLinkBtn.addEventListener('click', showPdfLinkInput);
    elements.uploadFileBtn.addEventListener('click', () => elements.fileInput.click());
    elements.fileInput.addEventListener('change', handleFileUpload);
    elements.submitPdfUrl.addEventListener('click', loadPdfFromUrl);
    elements.useSelectedPdf.addEventListener('click', useSelectedTextbookPdf);
    
    // AI features
    elements.summaryCard.addEventListener('click', () => generateSummary());
    elements.quizCard.addEventListener('click', () => generateQuiz());
    elements.qaCard.addEventListener('click', () => showQAChat());
    elements.audioCard.addEventListener('click', () => generateAudio());
    elements.videoCard.addEventListener('click', () => generateVideo());
    
    // Close sidebars on outside click
    document.addEventListener('click', (e) => {
        if (elements.leftSidebar.classList.contains('active') && 
            !elements.leftSidebar.contains(e.target) && 
            !elements.menuBtn.contains(e.target)) {
            toggleSidebar('left');
        }
    });
}

// ==================== SIDEBAR CONTROLS ====================
function toggleSidebar(side) {
    if (side === 'left') {
        elements.leftSidebar.classList.toggle('active');
    } else {
        elements.rightSidebar.classList.toggle('active');
    }
}

// ==================== DATA LOADING ====================
async function loadTextbooks(board = null, classFilter = null, subjectFilter = null) {
    showLoading('Loading textbooks...');
    
    try {
        let url = `${API_BASE_URL}/textbooks`;
        const params = new URLSearchParams();
        
        if (board) params.append('board', board);
        if (classFilter) params.append('class_name', classFilter);
        if (subjectFilter) params.append('subject', subjectFilter);
        
        if (params.toString()) url += `?${params.toString()}`;
        
        const response = await fetch(url);
        const data = await response.json();
        
        displayTextbooks(data.textbooks);
        updateFilterOptions(data.textbooks);
    } catch (error) {
        console.error('Error loading textbooks:', error);
        showError('Failed to load textbooks');
    } finally {
        hideLoading();
    }
}

function displayTextbooks(textbooks) {
    if (!textbooks || textbooks.length === 0) {
        elements.textbooksGrid.innerHTML = `
            <div class="loading">
                <i class="fas fa-inbox"></i>
                <p>No textbooks found</p>
            </div>
        `;
        return;
    }
    
    elements.textbooksGrid.innerHTML = textbooks.map(book => `
        <div class="textbook-card" onclick="openTextbook('${book._id}')">
            <div class="textbook-header">
                <div class="textbook-icon">
                    <i class="fas fa-book"></i>
                </div>
                <div class="textbook-info">
                    <h3>${book.title}</h3>
                    <div class="textbook-meta">${book.board} • Class ${book.class}</div>
                </div>
            </div>
            <div class="textbook-details">
                <strong>Subject:</strong> ${book.subject}<br>
            </div>
        </div>
    `).join('');
}

function updateFilterOptions(textbooks) {
    // Extract unique classes and subjects
    const classes = [...new Set(textbooks.map(b => b.class))].sort();
    const subjects = [...new Set(textbooks.map(b => b.subject))].sort();
    
    // Update class filter
    elements.classFilter.innerHTML = '<option value="">All Classes</option>' +
        classes.map(c => `<option value="${c}">Class ${c}</option>`).join('');
    
    // Update subject filter
    elements.subjectFilter.innerHTML = '<option value="">All Subjects</option>' +
        subjects.map(s => `<option value="${s}">${s}</option>`).join('');
}

// ==================== TEXTBOOK OPERATIONS ====================
async function openTextbook(textbookId) {
    showLoading('Loading textbook...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/textbooks/${textbookId}`);
        const textbook = await response.json();
        
        appState.currentTextbook = textbook;
        appState.currentPdfUrl = textbook.pdf_url;
        
        // Update UI
        elements.pdfTitle.textContent = textbook.title;
        elements.pdfFrame.src = textbook.pdf_url;
        
        // Show PDF viewer
        elements.hierarchyView.style.display = 'none';
        elements.pdfViewer.style.display = 'block';
        
        // Update PDF info in AI panel
        updateSelectedPdfInfo(textbook.title, textbook.pdf_url);
        
    } catch (error) {
        console.error('Error opening textbook:', error);
        showError('Failed to open textbook');
    } finally {
        hideLoading();
    }
}

function showHierarchyView() {
    elements.pdfViewer.style.display = 'none';
    elements.hierarchyView.style.display = 'block';
    elements.aiOutput.style.display = 'none';
}

// ==================== PDF SOURCE SELECTION ====================
function showPdfLinkInput() {
    elements.pdfLinkInput.style.display = 'block';
    document.querySelectorAll('.pdf-option').forEach(btn => btn.classList.remove('active'));
    elements.pasteLinkBtn.classList.add('active');
}

async function loadPdfFromUrl() {
    const url = elements.pdfUrlField.value.trim();
    
    if (!url) {
        alert('Please enter a PDF URL');
        return;
    }
    
    showLoading('Loading PDF...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/process_pdf_url`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pdf_url: url})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            appState.currentPdfUrl = url;
            appState.isPdfLoaded = true;
            updateSelectedPdfInfo('Uploaded PDF', url);
            showAiFeatures();
            alert('PDF loaded successfully!');
        } else {
            throw new Error(data.detail || 'Failed to load PDF');
        }
    } catch (error) {
        console.error('Error loading PDF:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

async function handleFileUpload(event) {
    const file = event.target.files[0];
    
    if (!file || file.type !== 'application/pdf') {
        alert('Please select a PDF file');
        return;
    }
    
    showLoading('Uploading PDF...');
    
    try {
        const formData = new FormData();
        formData.append('file', file);
        
        const response = await fetch(`${API_BASE_URL}/upload_pdf`, {
            method: 'POST',
            body: formData
        });
        
        const data = await response.json();
        
        if (response.ok) {
            appState.currentPdfUrl = data.pdf_identifier;
            appState.isPdfLoaded = true;
            updateSelectedPdfInfo(file.name, data.pdf_identifier);
            showAiFeatures();
            alert('PDF uploaded successfully!');
        } else {
            throw new Error(data.detail || 'Failed to upload PDF');
        }
    } catch (error) {
        console.error('Error uploading PDF:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

async function useSelectedTextbookPdf() {
    if (!appState.currentTextbook) {
        alert('Please select a textbook first');
        return;
    }
    
    showLoading('Processing PDF...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/process_pdf_url`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({pdf_url: appState.currentPdfUrl})
        });
        
        const data = await response.json();
        
        if (response.ok) {
            appState.isPdfLoaded = true;
            showAiFeatures();
            alert('PDF ready for AI features!');
        } else {
            throw new Error(data.detail || 'Failed to process PDF');
        }
    } catch (error) {
        console.error('Error processing PDF:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function updateSelectedPdfInfo(title, url) {
    elements.selectedPdfInfo.innerHTML = `
        <p class="info-text">
            <i class="fas fa-file-pdf"></i>
            <strong>${title}</strong><br>
            <small>${url.substring(0, 50)}...</small>
        </p>
    `;
}

function showAiFeatures() {
    elements.pdfSelector.style.display = 'none';
    elements.aiFeatures.style.display = 'block';
}

// ==================== AI FEATURES ====================
async function generateSummary() {
    if (!appState.currentPdfUrl) {
        alert('Please load a PDF first');
        return;
    }
    
    showLoading('Generating summary...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdf_url: appState.currentPdfUrl,
                summary_type: 'both'
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displaySummary(data);
        } else {
            throw new Error(data.detail || 'Failed to generate summary');
        }
    } catch (error) {
        console.error('Error generating summary:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function displaySummary(data) {
    elements.outputTitle.textContent = 'Summary';
    elements.outputContent.innerHTML = `
        <div class="summary-content">
            <h3>Short Summary</h3>
            <p>${data.short_summary}</p>
            
            <h3 style="margin-top: 24px;">Detailed Summary</h3>
            <p>${data.detailed_summary}</p>
        </div>
    `;
    elements.aiOutput.style.display = 'block';
}

async function generateQuiz() {
    if (!appState.currentPdfUrl) {
        alert('Please load a PDF first');
        return;
    }
    
    showLoading('Generating quiz...');
    
    try {
        const response = await fetch(`${API_BASE_URL}/quiz`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdf_url: appState.currentPdfUrl,
                num_questions: 10
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            displayQuiz(data.questions);
        } else {
            throw new Error(data.detail || 'Failed to generate quiz');
        }
    } catch (error) {
        console.error('Error generating quiz:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function displayQuiz(questions) {
    elements.outputTitle.textContent = 'Quiz';
    
    let html = '<div class="quiz-container">';
    
    questions.forEach((q, index) => {
        html += `
            <div class="question-card">
                <div class="question-text">${index + 1}. ${q.question}</div>
                <div class="options">
                    ${Object.entries(q.options).map(([key, value]) => `
                        <div class="option" onclick="selectOption(${index}, '${key}', '${q.correct_answer}')">
                            <strong>${key}:</strong> ${value}
                        </div>
                    `).join('')}
                </div>
                <div class="explanation" id="explanation-${index}" style="display: none; margin-top: 12px; padding: 12px; background: #e8f5e9; border-radius: 8px;">
                    <strong>Correct Answer: ${q.correct_answer}</strong><br>
                    ${q.explanation}
                </div>
            </div>
        `;
    });
    
    html += '</div>';
    
    elements.outputContent.innerHTML = html;
    elements.aiOutput.style.display = 'block';
}

function selectOption(questionIndex, selectedAnswer, correctAnswer) {
    const explanation = document.getElementById(`explanation-${questionIndex}`);
    explanation.style.display = 'block';
    
    if (selectedAnswer === correctAnswer) {
        explanation.style.background = '#e8f5e9';
    } else {
        explanation.style.background = '#ffebee';
    }
}

function showQAChat() {
    if (!appState.currentPdfUrl) {
        alert('Please load a PDF first');
        return;
    }
    
    elements.outputTitle.textContent = 'Q&A Chat';
    elements.outputContent.innerHTML = `
        <div class="chat-container">
            <div class="chat-messages" id="chatMessages">
                <div class="message assistant">
                    <p>Hi! I can answer questions about your PDF. What would you like to know?</p>
                </div>
            </div>
            <div class="chat-input">
                <input type="text" id="questionInput" placeholder="Ask a question..." onkeypress="if(event.key==='Enter') askQuestion()">
                <button onclick="askQuestion()">
                    <i class="fas fa-paper-plane"></i>
                </button>
            </div>
        </div>
    `;
    elements.aiOutput.style.display = 'block';
}

async function askQuestion() {
    const input = document.getElementById('questionInput');
    const question = input.value.trim();
    
    if (!question) return;
    
    const chatMessages = document.getElementById('chatMessages');
    
    // Add user message
    chatMessages.innerHTML += `
        <div class="message user">
            <p>${question}</p>
        </div>
    `;
    
    input.value = '';
    chatMessages.scrollTop = chatMessages.scrollHeight;
    
    // Show loading
    chatMessages.innerHTML += `
        <div class="message assistant" id="loadingMsg">
            <p><i class="fas fa-spinner fa-spin"></i> Thinking...</p>
        </div>
    `;
    
    try {
        const response = await fetch(`${API_BASE_URL}/ask`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdf_url: appState.currentPdfUrl,
                question: question,
                conversation_history: appState.conversationHistory
            })
        });
        
        const data = await response.json();
        
        document.getElementById('loadingMsg').remove();
        
        if (response.ok) {
            chatMessages.innerHTML += `
                <div class="message assistant">
                    <p>${data.answer}</p>
                </div>
            `;
            
            // Update conversation history
            appState.conversationHistory.push(
                {role: 'user', content: question},
                {role: 'assistant', content: data.answer}
            );
        } else {
            throw new Error(data.detail || 'Failed to get answer');
        }
    } catch (error) {
        document.getElementById('loadingMsg').remove();
        chatMessages.innerHTML += `
            <div class="message assistant">
                <p style="color: red;">Error: ${error.message}</p>
            </div>
        `;
    }
    
    chatMessages.scrollTop = chatMessages.scrollHeight;
}

async function generateAudio() {
    if (!appState.currentPdfUrl) {
        alert('Please load a PDF first');
        return;
    }
    
    showLoading('Generating audio overview...');
    
    try {
        // First get summary
        const summaryResponse = await fetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdf_url: appState.currentPdfUrl,
                summary_type: 'short'
            })
        });
        
        const summaryData = await summaryResponse.json();
        
        // Then generate audio
        const audioResponse = await fetch(`${API_BASE_URL}/audio`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                text: summaryData.summary,
                pdf_url: appState.currentPdfUrl
            })
        });
        
        const audioData = await audioResponse.json();
        
        if (audioResponse.ok) {
            displayAudio(audioData);
        } else {
            throw new Error(audioData.detail || 'Failed to generate audio');
        }
    } catch (error) {
        console.error('Error generating audio:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function displayAudio(data) {
    elements.outputTitle.textContent = 'Audio Overview';
    elements.outputContent.innerHTML = `
        <div class="audio-player">
            <i class="fas fa-headphones" style="font-size: 48px; color: var(--primary-color); margin-bottom: 16px;"></i>
            <h3>Listen to Summary</h3>
            <audio controls>
                <source src="${API_BASE_URL}/audio/${data.filename}" type="audio/mpeg">
                Your browser does not support audio playback.
            </audio>
        </div>
    `;
    elements.aiOutput.style.display = 'block';
}

async function generateVideo() {
    if (!appState.currentPdfUrl) {
        alert('Please load a PDF first');
        return;
    }
    
    showLoading('Generating video... This may take a few minutes...');
    
    try {
        // First get summary
        const summaryResponse = await fetch(`${API_BASE_URL}/summarize`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                pdf_url: appState.currentPdfUrl,
                summary_type: 'short'
            })
        });
        
        const summaryData = await summaryResponse.json();
        
        // Then generate video
        const videoResponse = await fetch(`${API_BASE_URL}/video`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                summary: summaryData.summary
            })
        });
        
        const videoData = await videoResponse.json();
        
        displayVideoResult(videoData);
    } catch (error) {
        console.error('Error generating video:', error);
        showError(error.message);
    } finally {
        hideLoading();
    }
}

function displayVideoResult(data) {
    elements.outputTitle.textContent = 'Video Overview';
    
    let html = '<div class="video-result">';
    
    if (data.status === 'completed' && data.video_url) {
        html += `
            <video controls style="width: 100%; border-radius: 12px;">
                <source src="${data.video_url}" type="video/mp4">
            </video>
        `;
    } else if (data.status === 'processing') {
        html += `
            <div style="text-align: center; padding: 40px;">
                <i class="fas fa-video" style="font-size: 48px; color: var(--primary-color); margin-bottom: 16px;"></i>
                <h3>Video is being generated</h3>
                <p>${data.message}</p>
                <p><strong>Video ID:</strong> ${data.video_id}</p>
            </div>
        `;
    } else {
        html += `
            <div style="padding: 20px; background: var(--background); border-radius: 12px;">
                <h3>Video Script</h3>
                <p>${data.script || data.message}</p>
            </div>
        `;
    }
    
    html += '</div>';
    
    elements.outputContent.innerHTML = html;
    elements.aiOutput.style.display = 'block';
}

// ==================== UTILITY FUNCTIONS ====================
function onBoardChange(e) {
    appState.selectedBoard = e.target.value;
    loadTextbooks(appState.selectedBoard);
}

function applyFilters() {
    const classValue = elements.classFilter.value;
    const subjectValue = elements.subjectFilter.value;
    loadTextbooks(appState.selectedBoard, classValue, subjectValue);
}

async function onSearch(e) {
    const query = e.target.value.trim();
    
    if (!query) {
        loadTextbooks();
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/search?q=${encodeURIComponent(query)}`);
        const data = await response.json();
        displayTextbooks(data.results);
    } catch (error) {
        console.error('Search error:', error);
    }
}

function debounce(func, wait) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
}

function showLoading(message = 'Loading...') {
    elements.loadingText.textContent = message;
    elements.loadingOverlay.style.display = 'flex';
}

function hideLoading() {
    elements.loadingOverlay.style.display = 'none';
}

function showError(message) {
    alert(`Error: ${message}`);
}

// Make functions globally accessible
window.openTextbook = openTextbook;
window.selectOption = selectOption;
window.askQuestion = askQuestion;
