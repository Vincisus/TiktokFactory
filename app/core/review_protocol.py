def normalize_review(report):
    if not isinstance(report, dict) or type(report.get("ok")) is not bool:
        raise ValueError("Verdetto: ok deve essere booleano.")
    issues = report.get("issues")
    if not isinstance(issues, list) or not all(isinstance(x, str) and x.strip() for x in issues):
        raise ValueError("Verdetto: issues deve contenere stringhe non vuote.")
    if issues:
        return {"ok": False, "issues": list(dict.fromkeys(x.strip() for x in issues))}
    if not report["ok"]:
        raise ValueError("Verdetto negativo senza motivazione: ripetere la revisione.")
    return {"ok": True, "issues": []}
