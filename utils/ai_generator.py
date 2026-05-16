"""
AI Application Generator
Uses Google Gemini (free tier) to generate tailored cover letters,
cold emails, form answers, and resume tips for each job.

Free tier: 1500 requests/day, 15 requests/minute — more than enough.
Get your free API key at: https://aistudio.google.com/app/apikey

Usage:
    from utils.ai_generator import ApplicationGenerator
    gen = ApplicationGenerator()
    cover_letter = gen.generate_cover_letter(job)
    answers = gen.generate_form_answers(job)
"""

import json
import logging
import re
import time
import os
from typing import Optional

from google import genai
from google.genai import types

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import GEMINI_API_KEY, PROFILE

log = logging.getLogger("AIGenerator")

MODEL = "gemini-2.0-flash"   # Free tier default (2025)


def _build_profile_context() -> str:
    p = PROFILE
    exp_text = "\n".join(
        f"- {e['role']} at {e['company']} ({e['duration']}): {'; '.join(e['highlights'])}"
        for e in p["experiences"]
    )
    proj_text = "\n".join(
        f"- {pr['name']} ({pr['stack']}): {'; '.join(pr['highlights'])}"
        for pr in p["projects"]
    )
    return f"""
CANDIDATE: {p['name']}
Email: {p['email']} | Phone: {p['phone']}
Education: {p['degree']}, {p['college']} — CGPA {p['cgpa']}, graduating {p['grad_year']}

CURRENT STATUS:
- Role: {p['current_role']} at {p['current_company']} (current)
- Promoting to: {p['promoting_to']} in {p['promotion_timeline']}
- Current CTC: {p['current_ctc']}
- Target CTC: {p['target_ctc_min']}–{p['target_ctc_max']} LPA

EXPERIENCE:
{exp_text}

PROJECTS:
{proj_text}

SKILLS: {', '.join(p['skills'])}

ACHIEVEMENTS: {'; '.join(p['achievements'])}
""".strip()


class ApplicationGenerator:
    def __init__(self):
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY not set in config.py.\n"
                "Get your FREE key (no card needed) at: https://aistudio.google.com/app/apikey\n"
                "Free tier: 1500 requests/day — plenty for this bot."
            )
        self.client = genai.Client(api_key=GEMINI_API_KEY)
        self.profile_context = _build_profile_context()
        log.info(f"Gemini AI ready ({MODEL})")

    def _call_gemini(self, prompt: str, max_retries: int = 3) -> str:
        for attempt in range(max_retries):
            try:
                response = self.client.models.generate_content(
                    model=MODEL,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        temperature=0.7,
                        max_output_tokens=800,
                    )
                )
                return response.text.strip()
            except Exception as e:
                err = str(e)
                if "429" in err or "quota" in err.lower():
                    wait = 60 if attempt == 0 else 120
                    log.warning(f"Rate limit — waiting {wait}s (attempt {attempt+1}/{max_retries})")
                    time.sleep(wait)
                elif "404" in err:
                    raise RuntimeError(f"Model not found — check model name: {err}")
                else:
                    log.error(f"Gemini API error: {e}")
                    raise
        raise RuntimeError("Gemini API rate-limited after retries — try again in a minute.")

    def generate_cover_letter(self, job: dict, emphasis: str = "") -> str:
        jd_section = f"\nJOB DESCRIPTION:\n{job.get('description', '')[:1500]}" if job.get("description") else ""
        emphasis_section = f"\nADDITIONAL EMPHASIS: {emphasis}" if emphasis else ""

        prompt = f"""You are an expert career coach for the Indian tech industry. Write a cover letter for this job application.

CANDIDATE PROFILE:
{self.profile_context}

TARGET JOB:
- Title: {job['title']}
- Company: {job['company']}
- Location: {job.get('location', 'India')}
- Salary range: {job.get('salary_text', '20-35 LPA')}
{jd_section}
{emphasis_section}

STRICT REQUIREMENTS:
- 180-220 words maximum
- Do NOT start with "I am writing to" or "I would like to apply"
- Open with the Paytm backend internship + upcoming SDE-1 promotion as the hook
- Mention DTU and CGPA 8.36 naturally (not as the opening line)
- Reference 1-2 most relevant projects for THIS specific role
- State expected CTC as {PROFILE['target_ctc_min']}-{PROFILE['target_ctc_max']} LPA
- No bullet points — flowing paragraphs only
- End with a confident, specific call to action
- Sign off as {PROFILE['name']}

Write only the cover letter text. No subject line, no meta-commentary."""

        return self._call_gemini(prompt)

    def generate_linkedin_note(self, job: dict, recruiter_name: str = "") -> str:
        target = f"{recruiter_name} at {job['company']}" if recruiter_name else f"a recruiter at {job['company']}"
        prompt = f"""Write a LinkedIn connection request note from {PROFILE['name']} to {target} about the {job['title']} role.

Candidate: Backend intern at Paytm (promoting to SDE-1), DTU CS 2026, CGPA 8.36.
Company: {job['company']}

Rules:
- Under 280 characters STRICTLY
- Warm, specific, not generic
- Mention Paytm or DTU by name
- No hashtags

Write only the note text."""

        return self._call_gemini(prompt)

    def generate_cold_email(self, job: dict, recruiter_name: str = "") -> dict:
        name_line = f"Hi {recruiter_name}," if recruiter_name else "Hi,"
        prompt = f"""Write a cold outreach email from {PROFILE['name']} about the {job['title']} role at {job['company']}.

CANDIDATE:
{self.profile_context}

REQUIREMENTS:
- Subject: punchy and specific, under 60 characters
- Body: under 120 words
- Start with: {name_line}
- Lead with Paytm backend internship + upcoming SDE-1 promotion
- Include ONE specific thing about {job['company']} showing genuine interest
- End with a specific ask (15-min call or review application)
- Mention salary expectation: {PROFILE['target_ctc_min']}-{PROFILE['target_ctc_max']} LPA

Return ONLY valid JSON:
{{"subject": "...", "body": "..."}}

No markdown, no explanation."""

        raw = self._call_gemini(prompt)
        raw = re.sub(r"```json|```", "", raw).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            subject_match = re.search(r'"subject"\s*:\s*"([^"]+)"', raw)
            body_match = re.search(r'"body"\s*:\s*"([\s\S]+?)"(?:\s*})', raw)
            return {
                "subject": subject_match.group(1) if subject_match else f"SDE-1 Application — {PROFILE['name']}",
                "body": body_match.group(1).replace("\\n", "\n") if body_match else raw,
            }

    def generate_form_answers(self, job: dict) -> dict:
        prompt = f"""Generate answers to job application form questions for:
- Candidate: {PROFILE['name']}
- Role: {job['title']} at {job['company']}

CANDIDATE PROFILE:
{self.profile_context}

Answer these 5 questions (each under 150 words, tailored to {job['company']}):
1. "Tell us about yourself"
2. "Why do you want to join {job['company']}?"
3. "What is your biggest technical achievement?"
4. "What is your expected CTC and notice period?"
5. "What interests you most about this role?"

Return ONLY valid JSON:
{{"q1": "...", "q2": "...", "q3": "...", "q4": "...", "q5": "..."}}

No markdown, no explanation."""

        raw = self._call_gemini(prompt)
        raw = re.sub(r"```json|```", "", raw).strip()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            log.warning("Could not parse form answers as JSON.")
            return {"raw": raw}

    def get_resume_tailoring_tips(self, job: dict) -> str:
        prompt = f"""You are an ATS expert and resume coach for Indian tech companies.

JOB: {job['title']} at {job['company']}
JOB DESCRIPTION: {job.get('description', 'Not available')[:800]}

CANDIDATE RESUME HIGHLIGHTS:
{self.profile_context}

Give 4-5 specific, actionable resume changes for THIS role:
- Exact keywords to add from the JD
- Specific bullet points to rewrite (give revised text)
- Sections to reorder
Be concrete — no generic advice."""

        return self._call_gemini(prompt)

    def batch_generate_cover_letters(self, jobs: list, output_dir: str = "output/cover_letters") -> dict:
        os.makedirs(output_dir, exist_ok=True)
        results = {}

        for i, job in enumerate(jobs):
            job_id = job.get("id", f"job_{i}")
            safe_company = job['company'].replace(' ', '_').replace('/', '-')
            filename = f"{output_dir}/{job_id}_{safe_company}.txt"

            log.info(f"[{i+1}/{len(jobs)}] {job['title']} @ {job['company']}")
            try:
                letter = self.generate_cover_letter(job)
                with open(filename, "w") as f:
                    f.write(f"Role: {job['title']}\nCompany: {job['company']}\n")
                    f.write(f"Location: {job.get('location', 'N/A')}\n")
                    f.write(f"CTC: {job.get('salary_text', 'N/A')}\n")
                    f.write(f"URL: {job.get('url', '')}\n")
                    f.write("=" * 50 + "\n\n")
                    f.write(letter)

                results[job_id] = filename
                log.info(f"  Saved -> {filename}")

                # Respect free tier: 15 req/min
                if i < len(jobs) - 1:
                    time.sleep(4)

            except Exception as e:
                log.error(f"  Failed for {job_id}: {e}")
                results[job_id] = None

        return results
