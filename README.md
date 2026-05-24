# QuantaHire Backend — FastAPI + MongoDB

## Folder Structure
```
quantahire-backend/
├── main.py              ← app entry point
├── config.py            ← all settings (reads from .env)
├── requirements.txt     ← install these
├── .env.example         ← copy this to .env and fill in your keys
├── db/
│   └── mongo.py         ← MongoDB connection
├── services/
│   ├── llm.py           ← DeepSeek client
│   ├── embeddings.py    ← sentence-transformers
│   └── matcher.py       ← core ranking logic
└── routes/
    ├── cvs.py           ← CV upload/list endpoints
    ├── jobs.py          ← job description endpoints
    └── match.py         ← matching + feedback endpoints
```

## Setup (run these commands)

### 1. Copy and fill in your .env
```bash
cp .env.example .env
# Open .env and paste your DeepSeek API key and MongoDB URI
```

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Start the server
```bash
uvicorn main:app --reload --port 8000
```

Your API is now running at: http://localhost:8000

---

## API Endpoints

| Method | URL | What it does |
|--------|-----|-------------|
| POST | /api/cvs/upload | Upload CV files (.pdf, .docx, or .zip) |
| GET  | /api/cvs/ | List all uploaded CVs |
| POST | /api/jobs/ | Create a job description |
| GET  | /api/jobs/ | List all jobs |
| POST | /api/match/ | Run ranking for a job → returns session_id |
| POST | /api/match/{session_id}/feedback | Submit "yes" or feedback text |
| GET  | /api/match/results/{job_id} | Get final results |

---

## How to use from your Frontend

### Step 1 — Upload CVs
```js
const form = new FormData()
form.append('files', cvFile)
await fetch('http://localhost:8000/api/cvs/upload', { method: 'POST', body: form })
```

### Step 2 — Create a Job
```js
await fetch('http://localhost:8000/api/jobs/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ title: 'Software Engineer', description: '...' })
})
```

### Step 3 — Run Matching
```js
const res  = await fetch('http://localhost:8000/api/match/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ job_id: 'jd_abc123' })
})
const data = await res.json()
// data.session_id — save this for feedback
// data.top_candidates — show these to the recruiter
```

### Step 4 — Submit Feedback
```js
// Approve:
await fetch(`http://localhost:8000/api/match/${sessionId}/feedback`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ feedback: 'yes' })
})

// Or give feedback to re-rank:
await fetch(`http://localhost:8000/api/match/${sessionId}/feedback`, {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ feedback: 'Need more cloud and AWS experience' })
})
```

---

## MongoDB Collections
- `jobs` — job descriptions
- `cvs` — uploaded CVs + extracted text
- `results` — final ranked results per job
- `sessions` — human-in-the-loop session state
