# CCCC.AI – CC Cup Chatbot.AI
# Version 4: YAML Update & Static

**Structure:**
- `frontend/` → static website (Vercel / GitHub Pages)
- `backend/` → FastAPI service (Deta / Render)
- `.gitignore` → global for both projects

**Deploy steps:**
1. Deploy `/backend` → to Deta or Render.
2. Get backend URL, e.g. `https://cccc-ai.deta.app`.
3. In `/frontend/index.html`, set:
   ```js
   window.API_BASE = "https://cccc-ai.deta.app";