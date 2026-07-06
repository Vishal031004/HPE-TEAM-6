from pathlib import Path

app_path = Path(r'C:\Users\Disha S\OneDrive\Desktop\HPE-TEAM-6\main-app\app.py')
text = app_path.read_text(encoding='utf-8')
old = '''class RenameRequest(BaseModel):
    new_name: str

def _run_rag_ingestion(file_path: str, filename: str, pdf_sha: str):
'''
new = '''class RenameRequest(BaseModel):
    new_name: str

def _safe_error_message(prefix: str, exc: Exception) -> str:
    message = str(exc).strip()
    return f"{prefix}: {message}" if message else prefix

def _run_rag_ingestion(file_path: str, filename: str, pdf_sha: str):
'''
if old not in text:
    raise SystemExit('app.py insertion point not found')
text = text.replace(old, new, 1)
old = '''    os.makedirs(DATASHEETS_DIR, exist_ok=True)
    file_path = os.path.join(DATASHEETS_DIR, file.filename)
    
    with open(file_path, "wb") as f:
        f.write(await file.read())
        
    pdf_sha = pdf_hash(file_path)
'''
new = '''    os.makedirs(DATASHEETS_DIR, exist_ok=True)
    file_path = os.path.join(DATASHEETS_DIR, file.filename)

    try:
        with open(file_path, "wb") as f:
            f.write(await file.read())
    except OSError as exc:
        return {"error": _safe_error_message("Could not save the uploaded PDF", exc)}

    try:
        pdf_sha = pdf_hash(file_path)
    except Exception as exc:
        return {"error": _safe_error_message("Could not process the uploaded PDF", exc)}
'''
if old not in text:
    raise SystemExit('app.py upload block not found')
text = text.replace(old, new, 1)
app_path.write_text(text, encoding='utf-8')

html_path = Path(r'C:\Users\Disha S\OneDrive\Desktop\HPE-TEAM-6\main-app\static\index.html')
text = html_path.read_text(encoding='utf-8')
old = '''    body {
      background: var(--bg); color: var(--text); font-family: var(--sans);
      font-size: 14px; line-height: 1.6; height: 100vh; display: flex;
      flex-direction: column; overflow: hidden;
    }
'''
new = '''    body {
      background: var(--bg); color: var(--text); font-family: var(--sans);
      font-size: 14px; line-height: 1.6; height: 100vh; min-height: 100dvh;
      display: flex; flex-direction: column; overflow-x: hidden;
    }
'''
if old not in text:
    raise SystemExit('index.html body block not found')
text = text.replace(old, new, 1)
old = '''    .btn-outline:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent2); }

    /* Auth View */
'''
new = '''    .btn-outline:hover:not(:disabled) { border-color: var(--accent2); color: var(--accent2); }

    .empty-state {
      background: rgba(20, 24, 32, 0.9);
      border: 1px dashed var(--border);
      border-radius: var(--radius);
      padding: 14px 16px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }

    /* Auth View */
'''
if old not in text:
    raise SystemExit('index.html empty-state insertion point not found')
text = text.replace(old, new, 1)
old = '''  </style>
</head>
<body>
'''
new = '''    @media (max-width: 900px) {
      body {
        height: auto;
        overflow-y: auto;
      }
      #view-app {
        flex-direction: column;
        height: auto;
        min-height: 100dvh;
      }
      .sidebar {
        width: 100%;
        border-right: none;
        border-bottom: 1px solid var(--border);
        max-height: 45vh;
        overflow-y: auto;
      }
      .workspace-header {
        flex-direction: column;
        align-items: flex-start;
        gap: 8px;
      }
      .chat-container {
        padding: 20px 16px;
      }
      .chat-input-wrapper {
        padding: 12px 16px;
      }
      .chat-input-inner {
        padding: 0;
        flex-wrap: wrap;
      }
      .bubble {
        max-width: 100%;
      }
    }

    @media (max-width: 600px) {
      .auth-box {
        padding: 24px 18px;
        margin: 16px;
      }
      .chat-input-inner {
        gap: 8px;
      }
      .input-stack {
        width: 100%;
      }
      .btn {
        width: 100%;
      }
    }
  </style>
</head>
<body>
'''
if old not in text:
    raise SystemExit('index.html style end insertion point not found')
text = text.replace(old, new, 1)
old = '''    // --- UPLOAD TO SESSION ---
    async function uploadAttachedPdf(eventOrFiles) {
'''
new = '''    function appendPdfPill(fileName, container, pdfHash = "") {
      const safeName = String(fileName || "").trim();
      if (!safeName) return false;

      const duplicate = Array.from(container.children).some(child => child.innerText.includes(safeName));
      if (duplicate) return false;

      const safeHash = String(pdfHash || "").replace(/'/g, "\\'");
      const safeFileName = safeName.replace(/'/g, "\\'");
      container.innerHTML += `
        <span class="pdf-pill-group" style="display:inline-flex; align-items:center; gap:2px; margin-right:4px;">
          <a href="/api/datasheets/${encodeURIComponent(safeName)}" target="_blank" class="pdf-pill" title="Click to view PDF" style="margin-right:0; border-radius:4px 0 0 4px;">📄 ${safeName}</a>
          <button onclick="triggerFindAlternativesForFile('${safeFileName}')"
            style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--accent); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0;"
            title="Find alternatives for ${safeName}">🔍</button>
          <button onclick="detachPdfFromWorkspace('${safeHash}', '${safeFileName}')"
            style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--danger); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0 4px 4px 0;"
            title="Remove ${safeName} from workspace">✕</button>
        </span>`;
      return true;
    }

    function getFriendlyErrorMessage(err) {
      const message = err?.message || "";
      if (message.includes("Failed to fetch")) {
        return { title: "Connection error", body: "Could not reach the server. Please make sure the services are running and try again." };
      }
      if (message.includes("500") || message.includes("502") || message.includes("503")) {
        return { title: "Server error", body: "The analysis service encountered an internal error. Please try again in a moment." };
      }
      if (err?.name === "AbortError" || message.includes("timeout")) {
        return { title: "Request timed out", body: "The server took too long to respond. Please try again in a moment." };
      }
      return { title: "Something went wrong", body: message || "An unexpected error occurred while processing your request." };
    }

    // --- UPLOAD TO SESSION ---
    async function uploadAttachedPdf(eventOrFiles) {
'''
if old not in text:
    raise SystemExit('index.html helper insertion point not found')
text = text.replace(old, new, 1)
old = '''        const file = files[i];
        if (file.type !== "application/pdf") continue;
'''
new = '''        const file = files[i];
        if (file.type !== "application/pdf") {
          const invalidCard = document.createElement('div');
          invalidCard.className = 'file-card error';
          invalidCard.innerHTML = `
            <div class="file-icon-box">
              <span class="status-icon">⚠️</span>
            </div>
            <div class="file-details">
              <span class="file-name">${file.name}</span>
              <span class="file-type">Only PDF files are supported</span>
            </div>
          `;
          stagingArea.appendChild(invalidCard);
          continue;
        }
'''
if old not in text:
    raise SystemExit('index.html invalid file block not found')
text = text.replace(old, new, 1)
old = '''        } catch (err) { 
          card.className = 'file-card error';
          card.querySelector('.status-icon').innerText = '❌';
        }
'''
new = '''        } catch (err) { 
          const friendly = getFriendlyErrorMessage(err);
          card.className = 'file-card error';
          card.querySelector('.status-icon').innerText = '❌';
          card.title = friendly.body;
        }
'''
if old not in text:
    raise SystemExit('index.html upload catch block not found')
text = text.replace(old, new, 1)
old = '''      if (chatHistory.length === 0) {
          appendSystemMessage("Workspace initialized. Attach a PDF or start typing.");
      } else {
'''
new = '''      if (chatHistory.length === 0) {
          appendSystemMessage('<div class="empty-state"><strong>Workspace ready.</strong><br>Attach a PDF or ask a question to get started.</div>');
      } else {
'''
if old not in text:
    raise SystemExit('index.html initial empty state block not found')
text = text.replace(old, new, 1)
old = '''        data.attached_pdfs.forEach(pdf => { 
          if (!seenFiles.has(pdf.filename)) {
            seenFiles.add(pdf.filename);
            pdfContainer.innerHTML += `
              <span class="pdf-pill-group" style="display:inline-flex; align-items:center; gap:2px; margin-right:4px;">
                <a href="/api/datasheets/${encodeURIComponent(pdf.filename)}" target="_blank" class="pdf-pill" title="Click to view PDF" style="margin-right:0; border-radius:4px 0 0 4px;">📄 ${pdf.filename}</a>
                <button onclick="triggerFindAlternativesForFile('${pdf.filename.replace(/'/g, "\\'")}')"
                  style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--accent); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0;" 
                  title="Find alternatives for ${pdf.filename}">🔍</button>
                <button onclick="detachPdfFromWorkspace('${pdf.hash}', '${pdf.filename.replace(/'/g, "\\'")}')"
                  style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--danger); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0 4px 4px 0;" 
                  title="Remove ${pdf.filename} from workspace">✕</button>
              </span>`; 
          }
        });
'''
new = '''        data.attached_pdfs.forEach(pdf => { 
          if (!seenFiles.has(pdf.filename)) {
            seenFiles.add(pdf.filename);
            appendPdfPill(pdf.filename, pdfContainer, pdf.hash);
          }
        });
'''
if old not in text:
    raise SystemExit('index.html attached pdf block not found')
text = text.replace(old, new, 1)
old = '''          const isDuplicate = Array.from(topContainer.children).some(child => child.innerText.includes(fileName));
          if (!isDuplicate) {
            topContainer.innerHTML += `
              <span class="pdf-pill-group" style="display:inline-flex; align-items:center; gap:2px; margin-right:4px;">
                <a href="/api/datasheets/${encodeURIComponent(fileName)}" target="_blank" class="pdf-pill" title="Click to view PDF" style="margin-right:0; border-radius:4px 0 0 4px;">📄 ${fileName}</a>
                <button onclick="triggerFindAlternativesForFile('${fileName.replace(/'/g, "\\'")}')" 
                  style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--accent); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0;" 
                  title="Find alternatives for ${fileName}">🔍</button>
                <button onclick="detachPdfFromWorkspace('', '${fileName.replace(/'/g, "\\'")}')" 
                  style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--danger); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0 4px 4px 0;" 
                  title="Remove ${fileName} from workspace">✕</button>
              </span>`;
          }
'''
new = '''          appendPdfPill(fileName, topContainer);
'''
if old not in text:
    raise SystemExit('index.html first staged-file block not found')
text = text.replace(old, new, 1)
old = '''        const isDuplicate = Array.from(topContainer.children).some(child => child.innerText.includes(fileName));
        if (!isDuplicate) {
          topContainer.innerHTML += `
            <span class="pdf-pill-group" style="display:inline-flex; align-items:center; gap:2px; margin-right:4px;">
              <a href="/api/datasheets/${encodeURIComponent(fileName)}" target="_blank" class="pdf-pill" title="Click to view PDF" style="margin-right:0; border-radius:4px 0 0 4px;">📄 ${fileName}</a>
              <button onclick="triggerFindAlternativesForFile('${fileName.replace(/'/g, "\\'")}')" 
                style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--accent); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0;" 
                title="Find alternatives for ${fileName}">🔍</button>
              <button onclick="detachPdfFromWorkspace('', '${fileName.replace(/'/g, "\\'")}')" 
                style="background:var(--surface2); border:1px solid var(--border); border-left:none; color:var(--danger); cursor:pointer; padding:4px 6px; font-size:12px; border-radius:0 4px 4px 0;" 
                title="Remove ${fileName} from workspace">✕</button>
            </span>`;
        }
'''
new = '''        appendPdfPill(fileName, topContainer);
'''
if old not in text:
    raise SystemExit('index.html second staged-file block not found')
text = text.replace(old, new, 1)
old = '''      } catch (err) {
        document.getElementById(loadingId)?.remove();
        let errorMsg = '';
        if (err.message && err.message.includes('Failed to fetch')) {
          errorMsg = '🔌 <b>Connection Error</b> — Could not reach the server. Please check if all services are running and try again.';
        } else if (err.message && (err.message.includes('500') || err.message.includes('502') || err.message.includes('503'))) {
          errorMsg = '⚙️ <b>Server Error</b> — The analysis service encountered an internal error. Please try again in a moment.';
        } else if (err.name === 'AbortError' || (err.message && err.message.includes('timeout'))) {
          errorMsg = '⏳ <b>Request Timed Out</b> — The server took too long to respond. This can happen with very large datasheets.';
        } else {
          errorMsg = `⚠️ <b>Something went wrong</b> — ${err.message || 'An unexpected error occurred.'}`;
        }
        errorMsg += `<br><button onclick="sendQuestion()" style="margin-top:8px; padding:6px 16px; background:var(--surface2); border:1px solid var(--border); color:var(--accent); border-radius:4px; cursor:pointer; font-family:var(--mono); font-size:12px;">🔄 Retry</button>`;
        appendSystemMessage(`<div style="color:var(--danger)">${errorMsg}</div>`);
      }
'''
new = '''      } catch (err) {
        document.getElementById(loadingId)?.remove();
        const friendly = getFriendlyErrorMessage(err);
        const errorMsg = `⚠️ <b>${friendly.title}</b> — ${friendly.body}<br><button onclick="sendQuestion()" style="margin-top:8px; padding:6px 16px; background:var(--surface2); border:1px solid var(--border); color:var(--accent); border-radius:4px; cursor:pointer; font-family:var(--mono); font-size:12px;">🔄 Retry</button>`;
        appendSystemMessage(`<div class="empty-state" style="color:var(--danger)">${errorMsg}</div>`);
      }
'''
if old not in text:
    raise SystemExit('index.html sendQuestion error block not found')
text = text.replace(old, new, 1)
html_path.write_text(text, encoding='utf-8')
