"""AI assistant: chat with a PDF and one-click summaries, with page citations.

Uses the Anthropic API. The key is read from the ANTHROPIC_API_KEY environment variable; when it is
not set, the feature reports itself as disabled and the UI hides it.
"""
import math
import re
from collections import Counter
from pathlib import Path

import pymupdf as fitz

from ..config import get_settings
from .common import ToolError, open_pdf

SYSTEM_PROMPT = (
    "You are PDFDesk's document assistant. Answer using only the document pages provided in the "
    "conversation. Pages are delimited as <page number=\"N\">...</page>. After every claim, cite the "
    "page(s) it came from in square brackets, like [p. 3] or [pp. 4-5]. If the answer is not in the "
    "provided pages, say that you could not find it in the document. Be concise and use plain language."
)

TOKEN_RE = re.compile(r"[\wऀ-ॿ஀-௿]+", re.UNICODE)


def page_texts(path: Path) -> list[str]:
    doc = open_pdf(path)
    texts = [p.get_text("text", sort=True) for p in doc]
    doc.close()
    if not any(t.strip() for t in texts):
        raise ToolError("This PDF has no text the assistant can read. Run OCR on it first.")
    return texts


def _select_pages(texts: list[str], question: str, budget: int) -> list[int]:
    """Choose which pages to send: all of them if they fit, otherwise the best BM25 matches."""
    total = sum(len(t) for t in texts)
    if total <= budget:
        return list(range(len(texts)))
    docs = [Counter(w.lower() for w in TOKEN_RE.findall(t)) for t in texts]
    lengths = [sum(d.values()) or 1 for d in docs]
    avg = sum(lengths) / len(lengths)
    terms = {w.lower() for w in TOKEN_RE.findall(question) if len(w) > 2}
    n = len(docs)
    scores = []
    for i, d in enumerate(docs):
        s = 0.0
        for t in terms:
            df = sum(1 for dd in docs if t in dd)
            if not df or t not in d:
                continue
            idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
            tf = d[t]
            s += idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * lengths[i] / avg))
        scores.append((s, i))
    chosen, used = [], 0
    # Always include the first page (title, parties, summary often live there).
    for _s, i in [(1e9, 0)] + sorted(scores, reverse=True):
        if i in chosen:
            continue
        if used + len(texts[i]) > budget:
            continue
        chosen.append(i)
        used += len(texts[i])
    return sorted(chosen)


def _context_block(texts: list[str], pages: list[int]) -> str:
    return "\n".join(f'<page number="{i + 1}">\n{texts[i].strip()}\n</page>' for i in pages)


def _call(messages: list[dict]) -> str:
    import anthropic

    s = get_settings()
    if not s.ai_enabled:
        raise ToolError("The AI assistant is not configured on this server.")
    client = anthropic.Anthropic(api_key=s.anthropic_api_key, timeout=300.0, max_retries=2)
    try:
        response = client.beta.messages.create(
            model=s.llm_model,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=messages,
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
        )
    except anthropic.RateLimitError as exc:
        raise ToolError("The AI service is busy right now. Please try again in a minute.") from exc
    except anthropic.APIStatusError as exc:
        raise ToolError(f"The AI service returned an error ({exc.status_code}).") from exc
    except anthropic.APIConnectionError as exc:
        raise ToolError("Could not reach the AI service. Please try again.") from exc
    if response.stop_reason == "refusal":
        raise ToolError("The assistant declined to answer this request.")
    answer = "".join(block.text for block in response.content if block.type == "text").strip()
    return answer or "I could not produce an answer for this document."


def _citations(answer: str, page_count: int) -> list[int]:
    pages = set()
    for m in re.finditer(r"\[pp?\.\s*([\d,\s\-–]+)\]", answer):
        for part in re.split(r"[,\s]+", m.group(1)):
            if not part:
                continue
            bounds = re.split(r"[-–]", part)
            try:
                lo, hi = int(bounds[0]), int(bounds[-1])
            except ValueError:
                continue
            pages.update(p for p in range(lo, hi + 1) if 1 <= p <= page_count)
    return sorted(pages)


def summarize(path: Path) -> dict:
    s = get_settings()
    texts = page_texts(path)
    pages = _select_pages(texts, "summary overview conclusion total amount date parties", s.llm_max_context_chars)
    prompt = (
        f"{_context_block(texts, pages)}\n\nSummarise this document. Start with a one-sentence overview, "
        "then 5-10 bullet points with the key facts (who, what, amounts, dates, obligations, deadlines), "
        "each with page citations."
    )
    answer = _call([{"role": "user", "content": prompt}])
    note = "" if len(pages) == len(texts) else f"The document is long; the summary is based on {len(pages)} of {len(texts)} pages."
    return {"answer": answer, "citations": _citations(answer, len(texts)), "pages_used": [p + 1 for p in pages], "note": note}


def chat(path: Path, messages: list[dict]) -> dict:
    """`messages` is the visible conversation [{role: user|assistant, content: str}]; the last is the question."""
    s = get_settings()
    clean = [
        {"role": m["role"], "content": str(m.get("content", ""))[:8000]}
        for m in messages[-20:]
        if m.get("role") in ("user", "assistant") and str(m.get("content", "")).strip()
    ]
    if not clean or clean[-1]["role"] != "user":
        raise ToolError("Ask a question about the document.")
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    texts = page_texts(path)
    pages = _select_pages(texts, " ".join(m["content"] for m in clean if m["role"] == "user"), s.llm_max_context_chars)
    # The document goes in the first user turn so the conversation stays a stable, cacheable prefix.
    clean[0] = {"role": "user", "content": f"{_context_block(texts, pages)}\n\n{clean[0]['content']}"}
    answer = _call(clean)
    return {"answer": answer, "citations": _citations(answer, len(texts)), "pages_used": [p + 1 for p in pages]}


def page_count(path: Path) -> int:
    with fitz.open(path) as d:
        return d.page_count
