from __future__ import annotations
from html import escape
import yaml
from litman_analysis.resource_paths import resource_path
from .model import _truncate
def render_html(report: dict, template: dict) -> str:
    def refs(item: dict) -> str: return " ".join(f'<a href="#source-{escape(ref)}">[{escape(ref)}]</a>' for ref in item.get("references", []))
    def items(values: list[dict], css: str) -> str:
        return "".join(f'<li class="{css}">{escape(str(value.get("text", "")))} {refs(value)}</li>' for value in values) or "<li>No consta.</li>"
    facts = "".join(f'<div class="fact"><span>{escape(item["label"])}</span><strong>{escape(item["value"])}</strong>{refs(item)}</div>' for item in report["key_facts"])
    checks = "".join(f'<tr><td>{escape(str(item["label"]))}</td><td class="status-{escape(str(item["status"]))}">{escape(str(item["status_label"]))}</td><td>{escape(str(item.get("text") or ""))} {refs(item)}</td></tr>' for item in report["rule_checks"]) or "<tr><td colspan=\"3\">No consta una evaluación detallada de filtros en esta ejecución histórica.</td></tr>"
    conditions = "".join(f'<tr><td>{escape(item["label"])}</td><td>{escape(item["value"])} {refs(item)}</td></tr>' for item in report["conditions"])
    def document_item(item: dict) -> str:
        css = "processed" if item.get("procesado") else "not-processed"
        state = "✓ Procesado" if item.get("procesado") else "⚠ No procesado"
        name = escape(str(item.get("tipo") or item.get("documento_id")))
        observation = f" — {escape(str(item['observaciones']))}" if item.get("observaciones") else ""
        return f'<li class="{css}">{state} · {name}{observation}</li>'
    documents = "".join(document_item(item) for item in report["document_control"]) or "<li>No consta inventario documental.</li>"
    missing = "".join(f'<li class="not-processed">⚠ Ausencia relevante: {escape(str(item))}</li>'
                      for item in report.get("missing_documents", []))
    rules = report["rule_summary"]
    rule_summary = (f'{rules["triggered"]} no superadas · {rules["passed"]} superadas · '
                    f'{rules["not_applicable"]} no aplicables · {rules["other"]} otros estados')
    doc_summary = report["document_summary"]
    def source_card(item: dict) -> str:
        page = f' · pág. {escape(str(item["page"]))}' if item.get("page") else " · sin página identificada"
        section = f'<p>{escape(str(item["section"]))}</p>' if item.get("section") else ""
        return f'<article id="source-{escape(item["ref"])}"><b>{escape(item["ref"])} · {escape(str(item.get("document_name") or "Documento"))}{page}</b>{section}<blockquote>{escape(_truncate(str(item.get("quote") or ""), 150))}</blockquote></article>'
    sources = "".join(source_card(item) for item in report["sources"])
    title = escape(report["header"]["title"] or "Oportunidad sin título")
    return f'''<!doctype html><html lang="es"><head><meta charset="utf-8"><title>{title}</title><style>{_css()}</style></head><body>
<main><header><span>LITMAN ANALYSIS · FICHA DE OPORTUNIDAD</span><h1>{title}</h1><p>{escape(str(report["header"].get("organization") or "No consta"))} · {escape(str(report["header"].get("contract_id") or "Sin expediente"))}</p></header>
<section class="facts">{facts}</section><section><h2>Qué se contrata</h2><p>{escape(report["summary"])}</p><p class="tags">{" ".join(f"<span>{escape(str(tag))}</span>" for tag in report["tags"])}</p></section>
<section class="columns"><div><h2>Motivos para avanzar</h2><ul>{items(report["positive_reasons"], "positive")}</ul></div><div><h2>Alertas y causas</h2><ul>{items(report["alerts"], "alert")}</ul></div></section>
<section><h2>Filtros comerciales</h2><p class="section-summary">{escape(rule_summary)}</p><table><thead><tr><th>Regla</th><th>Resultado</th><th>Por qué</th></tr></thead><tbody>{checks}</tbody></table></section>
<section class="overview"><h2>Información disponible para la valoración</h2><div class="columns"><div><h3>Información localizada</h3><ul>{items(report["information_overview"]["found"], "positive")}</ul></div><div><h3>Información no localizada</h3><ul>{items(report["information_overview"]["missing"], "alert")}</ul></div></div><h3>Aspectos que conviene confirmar</h3><p>{escape(report["information_overview"]["confirmation_message"])}</p></section>
<section class="columns report-details"><div><h2>Condiciones relevantes</h2><table><tbody>{conditions}</tbody></table></div><div><h2>Control documental</h2><p class="section-summary">{doc_summary["processed"]}/{doc_summary["received"]} documentos procesados · calidad: {escape(str(report["information_quality"]["status"]))}</p><ul>{documents}{missing}</ul></div></section>
<section><h2>Fuentes y evidencias</h2>{sources}</section></main></body></html>'''
def load_template(template_id: str) -> dict:
    path = resource_path("templates", "opportunity-report", template_id, "template.yaml")
    return yaml.safe_load(path.read_text(encoding="utf-8"))
def _css() -> str:
    return '@page { size:A4; margin:8mm 10mm; } * { box-sizing:border-box; } body { color:#1d2935; font:7.7pt Arial,sans-serif; line-height:1.15; margin:0; } h1 { color:#1681ba; font-size:17pt; line-height:1.02; margin:3px 0; } h2 { color:#1681ba; font-size:9.3pt; margin:6px 0 2px; } h3 { font-size:8pt; margin:3px 0 1px; } p { margin:2px 0; } header>span { color:#667085; font-size:7pt; letter-spacing:.7px; } .facts { display:grid; grid-template-columns:repeat(4,1fr); gap:4px; } .fact { background:#eef8fc; min-height:40px; padding:4px; } .fact span { display:block; color:#50606d; font-size:7pt; } .fact strong { color:#123; display:block; font-size:9pt; margin-top:2px; } .columns { display:grid; grid-template-columns:1fr 1fr; gap:9px; } ul { margin:2px 0; padding-left:14px; } li { margin:2px 0; } .positive::marker,.processed::marker { color:#238636; } .alert::marker,.not-processed::marker { color:#b7791f; } .tags span { background:#ede7f0; border-radius:10px; color:#6b3d62; display:inline-block; font-size:7pt; margin:1px 2px 0 0; padding:1px 5px; } .section-summary { color:#50606d; font-size:7pt; } table { border-collapse:collapse; width:100%; } th { background:#eef4f7; color:#345; font-size:6.8pt; text-align:left; } th,td { border-bottom:1px solid #d6e1e7; padding:2px 3px; vertical-align:top; } .status-pass { color:#238636; font-weight:bold; } .status-triggered,.status-unknown { color:#b04a00; font-weight:bold; } .status-not_applicable { color:#667085; font-weight:bold; } a { color:#126c9d; font-weight:bold; text-decoration:none; } article { border-top:1px solid #d6e1e7; margin-top:3px; padding-top:2px; break-inside:avoid; } article p,article blockquote { margin:1px 0; } blockquote { color:#4d5965; font-size:7pt; }'
