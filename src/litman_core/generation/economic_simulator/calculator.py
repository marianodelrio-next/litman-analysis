from __future__ import annotations


def calculate_scenario(plan: dict, scenario: dict) -> list[dict]:
    """Calcula resultados comprobables sin depender del motor de Excel."""
    bidders = scenario.get("bidders", [])
    prices = [item.get("price") for item in bidders if _positive(item.get("price"))]
    minimum = min(prices) if prices else None
    average = sum(prices) / len(prices) if prices else None
    results = []
    for bidder in bidders:
        price = bidder.get("price")
        price_points = _price_points(plan, price, minimum)
        qualitative = _technical_score(plan, bidder) if _positive(price) else None
        threshold = _abnormal_threshold(plan, len(prices), average, qualitative)
        abnormal = None
        if _positive(price) and threshold is not None:
            comparator = plan.get("abnormally_low", {}).get("comparador")
            abnormal = price < threshold if comparator == "menor" else price <= threshold
        total = qualitative + price_points if qualitative is not None and price_points is not None else None
        results.append({"name": bidder.get("name"), "price_points": price_points,
                        "qualitative_points": qualitative, "total_points": total,
                        "abnormal_threshold": threshold, "possible_abnormal": abnormal})
    ranked = sorted((item for item in results if item["total_points"] is not None),
                    key=lambda item: item["total_points"], reverse=True)
    for item in results:
        item["position"] = (ranked.index(item) + 1 if item in ranked else None)
    return results


def _price_points(plan: dict, price, minimum):
    formula = plan.get("price_formula", {})
    if not formula.get("supported") or not _positive(price) or minimum is None:
        return None
    points = minimum * float(formula.get("max_points") or 0) / price
    decimals = formula.get("rounding_decimals")
    return round(points, decimals) if decimals is not None else points


def _technical_score(plan: dict, bidder: dict):
    """Read exactly one input contract (v2 aggregate or legacy v1 breakdown)."""
    has_aggregate = "technical_score" in bidder
    has_legacy = "criterion_scores" in bidder
    if has_aggregate and has_legacy:
        raise ValueError("Un licitador no puede mezclar technical_score y criterion_scores.")
    if has_aggregate:
        value = bidder.get("technical_score")
        if value is None:
            return None
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            raise ValueError("technical_score debe ser numérica.")
        return float(value)
    if has_legacy:
        scores = bidder.get("criterion_scores") or {}
        values = [scores.get(item["id"]) for item in plan.get("criteria", [])]
        if not any(value is not None for value in values):
            return None
        if any(not isinstance(value, (int, float)) or isinstance(value, bool)
               for value in values if value is not None):
            raise ValueError("criterion_scores debe contener valores numéricos.")
        return sum(float(value or 0) for value in values)
    return None


def _abnormal_threshold(plan: dict, bidder_count: int, average, qualitative):
    abnormal = plan.get("abnormally_low", {})
    if abnormal.get("aplica") is not True or not bidder_count or qualitative is None:
        return None
    rule = next((item for item in abnormal.get("reglas", [])
                 if bidder_count >= item.get("min_licitadores", 1)
                 and (item.get("max_licitadores") is None or bidder_count <= item["max_licitadores"])), None)
    if not rule or rule.get("base") is None:
        return None
    reference = (average if rule.get("referencia") == "media_ofertas"
                 else plan.get("tender", {}).get("budget_without_tax")
                 if rule.get("referencia") == "presupuesto_maximo" else None)
    quality_max = abnormal.get("maximo_cualitativo")
    if reference is None or not quality_max:
        return None
    return (float(rule["base"]) + qualitative / quality_max * float(rule.get("peso_calidad") or 0)) * reference


def _positive(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0
