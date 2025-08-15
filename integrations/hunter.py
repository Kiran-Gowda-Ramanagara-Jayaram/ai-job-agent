# integrations/hunter.py
import os, requests

API_KEY = os.getenv("HUNTER_API_KEY")

class HunterError(Exception):
    pass

def _get(url, params):
    if not API_KEY:
        raise HunterError("HUNTER_API_KEY not set in .env")
    params = dict(params or {})
    params["api_key"] = API_KEY
    r = requests.get(url, params=params, timeout=20)
    if r.status_code >= 400:
        raise HunterError(f"{r.status_code}: {r.text[:300]}")
    return r.json()

# Hunter department codes (what their API expects)
# Docs commonly list: executive, it, finance, management, sales, legal, support, hr, communication, marketing
_DEPT_ALIASES = {
    "human_resources": "hr",
    "human-resources": "hr",
    "human resources": "hr",
    "recruiting": "hr",
    "talent": "hr",
    "talent_acquisition": "hr",
    "talent-acquisition": "hr",
    "ta": "hr",
    # pass-through for valid codes
    "hr": "hr",
    "it": "it",
    "executive": "executive",
    "finance": "finance",
    "management": "management",
    "sales": "sales",
    "legal": "legal",
    "support": "support",
    "communication": "communication",
    "marketing": "marketing",
}

def _norm_dept(dept: str | None) -> str | None:
    if not dept:
        return None
    d = dept.strip().lower()
    return _DEPT_ALIASES.get(d, d)  # fall back to raw (in case Hunter adds new ones)

def domain_search(domain: str, department: str | None = "hr", limit: int = 10):
    """
    Returns a list of work emails for a company domain filtered by department.
    Default department is 'hr' (Hunter's code). You can pass 'human_resources', 'recruiting', etc.
    """
    params = {"domain": domain, "limit": limit}
    nd = _norm_dept(department)
    if nd:
        params["department"] = nd

    data = _get("https://api.hunter.io/v2/domain-search", params)
    org = (data.get("data") or {}).get("organization")
    dom = (data.get("data") or {}).get("domain")
    emails = (data.get("data") or {}).get("emails", [])
    results = []
    for e in emails:
        results.append({
            "first_name": e.get("first_name"),
            "last_name": e.get("last_name"),
            "position": e.get("position"),
            "email": e.get("value"),
            "confidence": e.get("confidence"),
            "type": e.get("type"),
            "linkedin": e.get("linkedin"),
            "company": org,
            "domain": dom,
        })
    return results

def email_finder(domain: str, first_name: str, last_name: str, company: str | None = None):
    """
    Find a specific person's work email at a domain.
    """
    params = {"domain": domain, "first_name": first_name, "last_name": last_name}
    if company:
        params["company"] = company
    data = _get("https://api.hunter.io/v2/email-finder", params).get("data", {})
    return {
        "email": data.get("email"),
        "score": data.get("score"),
        "sources": data.get("sources", []),
    }

def verify_email(email: str):
    """
    Verify an email’s deliverability and quality.
    """
    data = _get("https://api.hunter.io/v2/email-verifier", {"email": email}).get("data", {})
    return {"result": data.get("result"), "score": data.get("score")}
