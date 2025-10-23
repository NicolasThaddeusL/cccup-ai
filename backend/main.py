# backend/app.py
"""
Optimized FastAPI backend for CCCC.AI (CC Cup Chatbot.AI) // VERSION 4.0
"""

import os
import logging
import re
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
import yaml
import requests

# --------------------------------------------------------------------
# Logging & environment
# --------------------------------------------------------------------
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("cccc.backend")

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

# --------------------------------------------------------------------
# Environment constants
# --------------------------------------------------------------------
SILICONFLOW_API_KEY = os.getenv("SILICONFLOW_API_KEY", "").strip()
SILICONFLOW_CHAT_MODEL = os.getenv("SILICONFLOW_CHAT_MODEL", "THUDM/GLM-Z1-9B-0414").strip()
if not SILICONFLOW_API_KEY:
    raise RuntimeError("SILICONFLOW_API_KEY missing in backend/.env")

ORGANIZER_SITE = os.getenv("ORGANIZER_SITE", "cccup.id")
ORGANIZER_SUPPORT = os.getenv("ORGANIZER_SUPPORT", "+62 811-9628-426 (Jonas)")
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "420"))

# Basic content filter
BANNED_WORDS = {
    "knife", "grenade", "bomb", "how to make a knife",
    "bunuh", "bom", "cara buat bom", "sex", "porn"
}

PHONE_RE = re.compile(r"(\+?\d[\d\s\-]{7,}\d)")

# --------------------------------------------------------------------
# App
# --------------------------------------------------------------------
app = FastAPI(title="CCCC.AI Backend", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_headers=["*"],
    allow_methods=["*"],
)

# --------------------------------------------------------------------
# Load merged bundle
# --------------------------------------------------------------------
BUNDLE_PATH = BASE_DIR / "data" / "data.bundle.yaml"
BUNDLE: Dict[str, Any] = {}
CREATOR_NAME = "Nicolas TL (2415674)"
SPORT_CONTACTS: Dict[str, Dict[str, Any]] = {}  # sport_key -> {name, sma, smp}


def load_bundle() -> None:
    """Load structured data.bundle.yaml produced by merge.py"""
    global BUNDLE, CREATOR_NAME, SPORT_CONTACTS

    if not BUNDLE_PATH.exists():
        log.error(f"Bundle not found: {BUNDLE_PATH}")
        BUNDLE = {}
        return

    try:
        BUNDLE = yaml.safe_load(BUNDLE_PATH.read_text(encoding="utf-8")) or {}
    except Exception as e:
        log.exception(f"❌ Failed to parse bundle: {e}")
        BUNDLE = {}
        return

    sv = (BUNDLE.get("meta") or {}).get("schema_version", 1)
    if sv != 1:
        raise RuntimeError(f"Unsupported bundle schema_version={sv}")

    info = BUNDLE.get("info") or {}
    creator = info.get("creator") or {}
    if creator.get("name") and creator.get("id"):
        CREATOR_NAME = f"{creator['name']} ({creator['id']})"
        log.info(f"👤 Creator loaded from bundle: {CREATOR_NAME}")

    # Build sport contact index
    SPORT_CONTACTS.clear()
    comps = BUNDLE.get("competitions") or {}
    for key, comp in comps.items():
        name = comp.get("name") or key
        c = comp.get("contacts") or {}
        smp = c.get("smp") or {}
        sma = c.get("sma") or {}
        smp_txt = f"{smp.get('name')} {smp.get('phone')}" if smp.get("phone") else None
        sma_txt = f"{sma.get('name')} {sma.get('phone')}" if sma.get("phone") else None
        if smp_txt or sma_txt:
            SPORT_CONTACTS[key.lower().replace("_", " ")] = {
                "name": name,
                "smp": smp_txt,
                "sma": sma_txt,
            }

    log.info(f"📦 Bundle loaded: {len(SPORT_CONTACTS)} sports indexed")


load_bundle()

# --------------------------------------------------------------------
# SiliconFlow API
# --------------------------------------------------------------------
SF_CHAT_URL = "https://api.siliconflow.com/v1/chat/completions"


def call_llm(messages: List[Dict[str, str]], max_tokens: int = MAX_OUTPUT_TOKENS) -> str:
    payload = {
        "model": SILICONFLOW_CHAT_MODEL,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
        "top_p": 0.9,
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        resp = requests.post(SF_CHAT_URL, headers=headers, json=payload, timeout=(10, 60))
        resp.raise_for_status()
        data = resp.json()
        return data.get("choices", [{}])[0].get("message", {}).get("content", "") or \
            "Maaf, respons kosong dari model."
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="LLM request timed out")
    except Exception as e:
        log.exception(f"LLM request error: {e}")
        raise HTTPException(status_code=502, detail="LLM upstream error")


# --------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------
CONTACT_HINTS = [
    "kontak", "hubungi", "narahubung", "nomor", "no telp", "no hp", "cp", "contact", "siapa yang saya hubungi"
]


def normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9\s]", " ", (s or "").lower())


def sport_match_from_text(q: str) -> Optional[str]:
    nq = normalize(q)
    for key in SPORT_CONTACTS.keys():
        tokens = [t for t in key.split() if t]
        if all(t in nq for t in tokens):
            return key
    return None


def is_contact_intent(q: str) -> bool:
    nq = normalize(q)
    return any(h in nq for h in CONTACT_HINTS)


def deterministic_contact_answer(sport_key: str) -> Optional[str]:
    data = SPORT_CONTACTS.get(sport_key)
    if not data:
        return None
    lines = [f"Untuk lomba **{data['name']}**, berikut kontak resmi:"]
    if data.get("sma"):
        lines.append(f"- **SMA**: {data['sma']}")
    if data.get("smp"):
        lines.append(f"- **SMP**: {data['smp']}")
    lines.append(
        f"\nJika data tidak terbarui, silakan kunjungi **{ORGANIZER_SITE}** "
        f"atau hubungi support **{ORGANIZER_SUPPORT}**."
    )
    return "\n".join(lines)


def build_context_block(user_query: str) -> str:
    """Assemble human-readable context from bundle"""
    lines = ["# Basis Data (Ringkas)"]

    faq = BUNDLE.get("faq") or {}
    if faq:
        ov = faq.get("overview") or {}
        if ov.get("description"):
            lines.append("## Tentang CC Cup 2025")
            lines.append(ov["description"])

        pend = faq.get("pendaftaran") or {}
        if pend:
            lines.append("## Pendaftaran")
            lines.append(f"Metode: {pend.get('method', '-')}")
            lines.append(f"Biaya: {pend.get('cost', '-')}")
            lines.append(f"Batas: {pend.get('deadline', '-')}")
            c = pend.get("contacts") or {}
            smp = c.get("smp") or {}; sma = c.get("sma") or {}
            if smp.get("phone") or sma.get("phone"):
                lines.append("Kontak pendaftaran:")
                if smp.get("phone"): lines.append(f"- SMP: {smp.get('name','SMP')} {smp['phone']}")
                if sma.get("phone"): lines.append(f"- SMA: {sma.get('name','SMA')} {sma['phone']}")

    schedule = BUNDLE.get("schedule") or {}
    for sid, s in schedule.items():
        head = s.get("name") or sid.title()
        date = s.get("date") or s.get("deadline")
        time = s.get("time")
        loc = s.get("location")
        row = f"{head}: {date or '-'}"
        if time: row += f", {time}"
        if loc: row += f", {loc}"
        lines.append(row)

    # Creator & contacts
    lines.append("## Pembuat")
    lines.append(f"Chatbot ini dibuat oleh **{CREATOR_NAME}**.")

    if SPORT_CONTACTS:
        lines.append("## Kontak (Terstruktur)")
        for k, v in SPORT_CONTACTS.items():
            lines.append(f"### {v['name']}")
            if v.get("sma"): lines.append(f"- **SMA**: {v['sma']}")
            if v.get("smp"): lines.append(f"- **SMP**: {v['smp']}")

    lines.append(
        f"\nSemua informasi resmi ada di **{ORGANIZER_SITE}**. "
        f"Jika data tidak terbarui, hubungi support: **{ORGANIZER_SUPPORT}**."
    )
    return "\n\n".join(lines)


# --------------------------------------------------------------------
# Schemas & routes
# --------------------------------------------------------------------
class Msg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Msg]


@app.get("/health")
def health():
    return {
        "ok": True,
        "schema": (BUNDLE.get("meta") or {}).get("schema_version", "?"),
        "creator": CREATOR_NAME,
        "sports_indexed": list(SPORT_CONTACTS.keys()),
    }


@app.post("/v1/reload")
def reload_bundle():
    load_bundle()
    return {"ok": True, "sports_indexed": list(SPORT_CONTACTS.keys())}


SAFE_DECLINE = (
    "Maaf, saya tidak bisa membantu dengan permintaan itu. "
    f"Untuk bantuan resmi, kunjungi **{ORGANIZER_SITE}** atau hubungi **{ORGANIZER_SUPPORT}**."
)


@app.post("/v1/chat/completions")
def chat(req: ChatRequest):
    if not req.messages:
        raise HTTPException(status_code=422, detail="messages required")

    last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "") or ""

    if any(b in last_user.lower() for b in BANNED_WORDS):
        return {"content": SAFE_DECLINE}

    # Rule-based contact intent
    if is_contact_intent(last_user):
        sport = sport_match_from_text(last_user)
