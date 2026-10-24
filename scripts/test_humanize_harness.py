"""Harness to run commentary generation and test AI detection on humanizeai.pro."""

import asyncio
import os
import re
import sys

sys.path.insert(0, os.getcwd())

from playwright.async_api import async_playwright
from src.agent.commentary import synthesize_commentary, build_prompt, build_instruction_provider, normalise_commentary_text
from src.agent.context import ContextLoader
from src.agent.guardrails import StyleGuardrail
from src.config import load_config
from src.news.extractor import ArticleExtractor
from src.news.models import CandidateSourceType
from src.twitter.auth import build_client
from src.twitter.fetcher import build_fetcher
from google import genai
from google.genai import types

class HumanizeDetectorClient:
    def __init__(self, page):
        self.page = page

    async def check(self, text: str) -> dict:
        """Call the /api/detector endpoint inside the browser context."""
        res = await self.page.evaluate("""async (text) => {
            const resp = await fetch('/api/detector', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json'
                },
                body: JSON.stringify({ text })
            });
            const data = await resp.json();
            
            // Also call explain if available
            let explain = null;
            try {
                const expResp = await fetch('/api/detector/explain', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
                    body: JSON.stringify({ text, score: data.score })
                });
                explain = await expResp.json();
            } catch (e) {}
            
            return {
                score: data.score,
                verdict: data.verdict,
                explain: explain
            };
        }""", text)
        return res

async def generate_for_item(item_type: str, item_data: dict, context, config) -> str:
    """Generate commentary for either a tweet or an article with guardrail validation."""
    client = genai.Client()
    guard = StyleGuardrail.from_markdown(
        context.writer_style_guide, min_words=55, max_words=85, min_punchlines=2
    )
    
    if item_type == "tweet":
        prompt_text = build_prompt(
            config.agent.prompt_template,
            tweet=item_data,
            writer_prompt=context.writer_system_prompt,
        )
        session_state = {"selected_tweet": item_data}
    else:
        prompt_text = build_prompt(
            config.agent.prompt_template,
            tweet=None,
            selected_item=item_data,
            extracted_article=item_data.get("extracted_article"),
            writer_prompt=context.writer_system_prompt,
        )
        session_state = {"selected_item": item_data, "extracted_article": item_data.get("extracted_article")}

    class _ContextStub:
        session = type("SessionStub", (), {"state": session_state})()

    instruction_fn = build_instruction_provider(config.agent.prompt_template, context=context)
    system_instruction = instruction_fn(_ContextStub())

    response = await client.aio.models.generate_content(
        model=config.agent.model,
        contents=prompt_text,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.7,
        ),
    )
    raw_text = response.text or ""
    text = normalise_commentary_text(raw_text, max_sentences=config.agent.max_sentences)

    # Corrective retry loop if guardrail or cadence fails
    for _ in range(2):
        guard_res = guard.validate(text)
        
        # Check if sentence 3 (paragraph 2 sentence 1) is too long
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        cadence_issue = None
        if len(paragraphs) >= 2:
            p2_s = [s.strip() for s in re.split(r"(?<=[.!?])\s+", paragraphs[1]) if s.strip()]
            if p2_s and len(p2_s[0].split()) > 7:
                cadence_issue = f"Sentence 3 ('{p2_s[0]}') has {len(p2_s[0].split())} words; it MUST be strictly 4 to 6 words (e.g. 'This goal is clumsy.', 'That price point cuts deep.')."

        if guard_res.is_valid and not cadence_issue:
            break

        feedback_parts = []
        if not guard_res.is_valid:
            feedback_parts.append(guard_res.feedback_prompt)
        if cadence_issue:
            feedback_parts.append(f"Cadence violation: {cadence_issue}")
        feedback = "\n\n".join(feedback_parts)

        reprompt = (
            f"Your previous commentary violated style constraints:\n{text}\n\n"
            f"{feedback}\n\n"
            f"Rewrite the commentary strictly adhering to the 3-paragraph structural rhythm and plain Anglo-Saxon words. "
            f"Reply with the post text only."
        )
        retry_resp = await client.aio.models.generate_content(
            model=config.agent.model,
            contents=reprompt,
            config=types.GenerateContentConfig(
                system_instruction=system_instruction,
                temperature=0.7,
            ),
        )
        if retry_resp.text:
            text = normalise_commentary_text(retry_resp.text, max_sentences=config.agent.max_sentences)

    return text

async def main():
    cfg = load_config()
    ctx_loader = ContextLoader()
    context = ctx_loader.load()
    
    # 1. Fetch data for the 4 sample inputs
    print("Fetching sample inputs...")
    t_client = build_client(cfg.twitter.cookies_path)
    f = build_fetcher(t_client, cfg.twitter)
    extractor = ArticleExtractor()
    
    # Sample 1: Mark Manson Tweet
    t1 = await f.fetch_tweet_by_id("2111895392241475803")
    t1_dict = {
        "id": t1.tweet_id,
        "tweet_id": t1.tweet_id,
        "author_handle": t1.author_handle,
        "author_name": t1.author_name,
        "permalink": t1.permalink,
        "text": t1.text,
        "created_at": t1.created_at.isoformat() if t1.created_at else "",
    }
    
    # Sample 2: Gergely Orosz Tweet
    t2 = await f.fetch_tweet_by_id("2111924637126820076")
    t2_dict = {
        "id": t2.tweet_id,
        "tweet_id": t2.tweet_id,
        "author_handle": t2.author_handle,
        "author_name": t2.author_name,
        "permalink": t2.permalink,
        "text": t2.text,
        "created_at": t2.created_at.isoformat() if t2.created_at else "",
    }
    
    # Sample 3: Mark Wahlberg TechCrunch Article
    a1 = await extractor.extract("https://techcrunch.com/2026/10/16/mark-wahlberg-wants-to-take-on-the-longevity-startup-crowd-with-an-affordable-gym-concept/")
    a1_dict = {
        "source_type": CandidateSourceType.NEWS_ARTICLE.value,
        "title": a1.title,
        "publication_name": a1.publication_name,
        "domain": a1.domain,
        "canonical_url": a1.url,
        "extracted_article": {
            "title": a1.title,
            "publication_name": a1.publication_name,
            "domain": a1.domain,
            "canonical_url": a1.url,
            "full_text": a1.full_text,
        }
    }
    
    # Sample 4: Anthropic TechCrunch Article
    a2 = await extractor.extract("https://techcrunch.com/2026/10/18/anthropic-says-its-committing-5-of-its-shares-to-a-public-benefit-fund/")
    a2_dict = {
        "source_type": CandidateSourceType.NEWS_ARTICLE.value,
        "title": a2.title,
        "publication_name": a2.publication_name,
        "domain": a2.domain,
        "canonical_url": a2.url,
        "extracted_article": {
            "title": a2.title,
            "publication_name": a2.publication_name,
            "domain": a2.domain,
            "canonical_url": a2.url,
            "full_text": a2.full_text,
        }
    }
    
    samples = [
        ("Mark Manson Tweet", "tweet", t1_dict),
        ("Gergely Orosz Tweet", "tweet", t2_dict),
        ("Mark Wahlberg TechCrunch Article", "article", a1_dict),
        ("Anthropic TechCrunch Article", "article", a2_dict),
    ]

    # 2. Launch browser for detector
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            executable_path=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            headless=True,
            args=["--disable-blink-features=AutomationControlled", "--no-sandbox"]
        )
        context_browser = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
        )
        page = await context_browser.new_page()
        await page.goto("https://www.humanizeai.pro/detector", timeout=30000)
        detector = HumanizeDetectorClient(page)
        
        print("\n================== GENERATION & AI DETECTION BENCHMARK ==================\n")
        results = []
        for label, item_type, item_data in samples:
            print(f"Generating commentary for: {label}...")
            comm = await generate_for_item(item_type, item_data, context, cfg)
            print(f"\n--- Output for {label} ---\n{comm}\n")
            
            check_res = await detector.check(comm)
            score = check_res.get("score", 0) or 0
            pct = round(score * 100)
            verdict = check_res.get("verdict", "Unknown")
            print(f"Detector Result: {pct}% AI (score={score:.4f}, verdict={verdict})")
            
            explain = check_res.get("explain") or {}
            bullets = explain.get("bullets") or []
            for b in bullets[:3]:
                if b.get("text"):
                    print(f"  • {b.get('text')}")
                    if b.get("example"):
                        print(f"    Example: {b.get('example')}")
            print("-" * 70 + "\n")
            results.append((label, pct, comm))
            
        print("\n================== SUMMARY ==================")
        for label, pct, _ in results:
            status = "PASS (<5%)" if pct < 5 else "FAIL (>=5%)"
            print(f"{label}: {pct}% AI [{status}]")
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
