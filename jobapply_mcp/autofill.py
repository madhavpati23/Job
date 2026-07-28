"""Assisted-apply via Playwright.

Opens an application page in a real (headed) browser, fills the standard fields
from profile.json, attaches the resume, pastes the cover letter, then HANDS
CONTROL BACK TO YOU. It never clicks Submit — you review screener questions and
submit yourself. That human step is intentional.

Supported form types (best-effort field autofill):
  - Greenhouse, Lever, Ashby, Workable  -> structured forms, fields auto-filled
  - Workday                             -> opens the page; login-walled, so mostly manual
  - aggregator links (Adzuna, The Muse) -> redirect is resolved to the real ATS first
  - anything else                       -> opens the page for fully manual apply

Usage:
    python -m jobapply_mcp.autofill <application_url> [--cover path/to/draft.md]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PROFILE_PATH = ROOT / "profile.json"


def _load_profile() -> dict:
    if not PROFILE_PATH.exists():
        sys.exit("profile.json not found. Fill it in first.")
    return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))


def _cover_text(path: str | None) -> str:
    if not path:
        return ""
    p = Path(path)
    if not p.exists():
        print(f"[warn] cover file not found: {path}", file=sys.stderr)
        return ""
    text = p.read_text(encoding="utf-8")
    # Strip our markdown scaffolding: headings, quotes, rules, metadata bullets
    # (- **Company:** ...), and the footer. Keep the letter prose ("Dear ...").
    lines, started = [], False
    for ln in text.splitlines():
        s = ln.strip()
        if s.startswith(("#", ">", "---")):
            continue
        if s.startswith("- **") or s.lower().startswith("apply at:"):
            continue
        if not started:
            if not s:
                continue
            started = True
        lines.append(ln)
    return "\n".join(lines).strip()


# ---- ATS detection + aggregator redirect resolution -------------------------

_ATS_PATTERNS = {
    "greenhouse": ("greenhouse.io", "boards.greenhouse"),
    "lever": ("lever.co",),
    "ashby": ("ashbyhq.com",),
    "workable": ("workable.com",),
    "workday": ("myworkdayjobs.com", "myworkdaysite.com", ".workday.com"),
    "smartrecruiters": ("smartrecruiters.com",),
}


def _detect_ats(url: str) -> str:
    u = (url or "").lower()
    for ats, needles in _ATS_PATTERNS.items():
        if any(n in u for n in needles):
            return ats
    return "unknown"


def _resolve_url(url: str) -> str:
    """Follow redirects (Adzuna/Muse links bounce to the real ATS). Best-effort."""
    if not any(x in url.lower() for x in ("adzuna.com", "themuse.com")):
        return url
    try:
        import httpx
        try:
            import truststore
            truststore.inject_into_ssl()
        except Exception:
            pass
        r = httpx.get(url, follow_redirects=True, timeout=20,
                      headers={"User-Agent": "Mozilla/5.0"})
        return str(r.url)
    except Exception:
        return url


# ---- field filling ----------------------------------------------------------

async def _fill_first(page, selectors: list[str], value: str) -> bool:
    for sel in selectors:
        try:
            el = page.locator(sel).first
            if await el.count() and await el.is_visible():
                await el.fill(value)
                return True
        except Exception:
            continue
    return False


async def _fill_by_label(page, label_regex: str, value: str) -> bool:
    """Fallback: find a field by its visible label text (works across ATSs)."""
    try:
        el = page.get_by_label(re.compile(label_regex, re.I)).first
        if await el.count() and await el.is_visible():
            await el.fill(value)
            return True
    except Exception:
        pass
    return False


async def _try_field(page, selectors: list[str], label_regex: str, value: str) -> bool:
    if not value:
        return False
    return (await _fill_first(page, selectors, value)
            or await _fill_by_label(page, label_regex, value))


async def run(url: str, cover_path: str | None) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        sys.exit(
            "Playwright not installed. Run:\n"
            "  .venv\\Scripts\\python.exe -m pip install playwright\n"
            "  .venv\\Scripts\\python.exe -m playwright install chromium"
        )

    profile = _load_profile()
    cover = _cover_text(cover_path)

    resolved = _resolve_url(url)
    if resolved != url:
        print(f"[resolved] {url}\n        -> {resolved}")
    ats = _detect_ats(resolved)
    print(f"[ats] detected: {ats}")
    if ats == "workday":
        print("[note] Workday is login-walled and varies per employer — autofill is\n"
              "       unreliable here. Opening the page; expect to fill it manually\n"
              "       (and create/login to an account if prompted).")
    elif ats == "unknown":
        print("[note] Unrecognized form type — opening the page for manual apply.\n"
              "       I'll still try generic fields, but expect to fill most yourself.")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        page = await browser.new_page()
        print(f"[open] {resolved}")
        await page.goto(resolved, wait_until="domcontentloaded")

        # Aggregator pages (Adzuna/Muse) keep you on their domain; the real ATS
        # is behind a JS "Apply" link. Click through it in-browser, follow any
        # popup/new tab, then re-detect the ATS on the page we land on.
        if any(x in page.url.lower() for x in ("adzuna.com", "themuse.com")):
            print("[aggregator] clicking through to the employer site...")
            for label in ["Apply", "Apply Now", "Apply for this job", "View job", "Continue"]:
                try:
                    link = page.get_by_role("link", name=re.compile(label, re.I)).first
                    btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                    target = link if await link.count() else btn
                    if not await target.count() or not await target.is_visible():
                        continue
                    try:
                        async with page.context.expect_page(timeout=8000) as popinfo:
                            await target.click()
                        page = await popinfo.value  # employer opened in a new tab
                    except Exception:
                        await page.wait_for_load_state("domcontentloaded")
                    await page.wait_for_timeout(1500)
                    break
                except Exception:
                    continue
            ats = _detect_ats(page.url)
            print(f"[ats] after click-through: {ats}  ({page.url[:70]})")

        # Many ATSs hide the form behind an Apply button.
        for label in ["Apply for this job", "Apply Now", "Apply", "I'm interested"]:
            try:
                btn = page.get_by_role("button", name=re.compile(label, re.I)).first
                if await btn.count() and await btn.is_visible():
                    await btn.click()
                    await page.wait_for_timeout(1200)
                    break
            except Exception:
                pass

        filled = []
        # First / last / full name. Lever uses a single "name" field.
        if await _try_field(page, ["#first_name", "input[name='first_name']",
                                   "input[name='firstname']", "input[autocomplete='given-name']"],
                            r"first name|given name", profile.get("first_name", "")):
            filled.append("first name")
        if await _try_field(page, ["#last_name", "input[name='last_name']",
                                   "input[name='lastname']", "input[autocomplete='family-name']"],
                            r"last name|family name|surname", profile.get("last_name", "")):
            filled.append("last name")
        # Single full-name field (Lever) if first/last weren't found.
        if "first name" not in filled:
            if await _try_field(page, ["input[name='name']"], r"^full name|^name$",
                                profile.get("full_name", "")):
                filled.append("full name")
        if await _try_field(page, ["#email", "input[name='email']", "input[type='email']"],
                            r"email", profile.get("email", "")):
            filled.append("email")
        if await _try_field(page, ["#phone", "input[name='phone']", "input[type='tel']"],
                            r"phone|mobile", profile.get("phone", "")):
            filled.append("phone")
        # Optional profile links some forms ask for.
        if await _try_field(page, ["input[name*='linkedin' i]", "input[id*='linkedin' i]"],
                            r"linkedin", profile.get("linkedin", "")):
            filled.append("linkedin")

        # Resume upload (works the same across most ATSs).
        resume = profile.get("resume_path", "")
        if resume and Path(resume).exists():
            for sel in ["input[type='file']", "#resume", "input[name='resume']"]:
                try:
                    fi = page.locator(sel).first
                    if await fi.count():
                        await fi.set_input_files(resume)
                        filled.append("resume upload")
                        break
                except Exception:
                    continue
        elif resume:
            print(f"[warn] resume not found at {resume} — fix resume_path in profile.json")

        # Cover letter into a textarea if the form has one.
        if cover and await _fill_first(
            page,
            ["#cover_letter_text", "textarea[name*='cover' i]",
             "textarea[aria-label*='cover' i]", "textarea[id*='cover' i]",
             "textarea[name*='comments' i]"],
            cover,
        ):
            filled.append("cover letter")

        print(f"[filled] {', '.join(filled) if filled else 'no standard fields matched (fill manually)'}")
        print(
            "\n================ ASSISTED APPLY ================\n"
            f"Form type: {ats}. The browser is open with what I could pre-fill.\n"
            "  1. Review every field; fill anything I missed.\n"
            "  2. Answer screener / EEO / work-authorization / visa questions.\n"
            "  3. Click Submit YOURSELF when satisfied.\n"
            "This script will NOT submit. Press Enter here to close the browser\n"
            "once you've finished submitting in the window.\n"
            "===============================================\n"
        )
        try:
            input()
        except EOFError:
            await page.wait_for_timeout(600000)  # no stdin: hold open 10 min
        await browser.close()


def main() -> None:
    ap = argparse.ArgumentParser(prog="autofill")
    ap.add_argument("url", help="application URL (any ATS or an Adzuna/Muse link)")
    ap.add_argument("--cover", default=None, help="path to a saved cover-letter draft")
    args = ap.parse_args()
    import asyncio
    asyncio.run(run(args.url, args.cover))


if __name__ == "__main__":
    main()
