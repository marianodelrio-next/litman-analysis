from __future__ import annotations
import json
import shutil
from pathlib import Path
import pytest
from pypdf import PdfReader
from litman_core.generation.opportunity_report import generate_opportunity_report
from litman_core.generation.opportunity_report import build_report_model, render_html
import litman_core.generation.opportunity_report.generator as generator

def _template(): return {"id":"executive-v1", "version":"1.2.0", "document":{"max_pages":2}, "limits":{"sources":8}}
def _result(): return {"extraction":{"ficha":{"objeto_contrato":"Servicio", "presupuesto":{"base_sin_iva":10,"moneda":"EUR"}, "fecha_limite_presentacion":None, "equipo":{"perfiles":["consultor"]}, "stack_tecnologico":{"tecnologias":["CTIS"]}, "certificaciones_exigidas":[{"nombre":"ISO 9001"}], "solvencia_tecnica":"experiencia", "solvencia_economica":"volumen", "lotes":{"existen":None}}, "clasificacion":{}, "calidad_informacion":{"estado":"parcial"}, "control_documental":{"documentos":[]}}, "decision":{"accion":"continuar", "evaluaciones":[]}, "validation":{"valid":True}}

def test_overview_explains_present_and_missing_business_data():
    report = build_report_model(_result(), {"evidences":[], "by_field":{}}, _template())
    found = " ".join(x["text"] for x in report["information_overview"]["found"]); missing = " ".join(x["text"] for x in report["information_overview"]["missing"])
    assert "tecnologías principales" in found and "certificaciones exigidas" in found and "solvencia técnica y económica" in found
    assert "fecha límite" in missing and "número mínimo" in missing and "lotes" in missing

def test_confirmation_and_sources_hide_technical_details():
    result = _result(); result["validation"]["evidence_verification_errors"] = [{"path":"ficha.stack_tecnologico", "evidence_id":"ev_one"}, {"path":"ficha.stack_tecnologico", "evidence_id":"ev_two"}, {"path":"clasificacion.foo", "evidence_id":"ev_three"}]
    index = {"evidences":[{"evidence_id":"ev_one", "field":"ficha.stack_tecnologico", "document_name":"pliego.pdf", "page":2, "section":"Tecnología", "quote":"CTIS", "verification":"quote_not_found"}], "by_field":{"ficha.stack_tecnologico":["ev_one"]}}
    report = build_report_model(result, index, _template()); html = render_html(report, _template())
    assert report["information_overview"]["to_confirm"] == ["stack tecnológico"]
    for unwanted in ("ev_", "quote_not_found", "Validación técnica de la extracción", "Causa exacta", "Abrir original", "file://", "Verificación:", "verified", "ficha.", "calidad_informacion."): assert unwanted not in html
    assert "F1 · pliego.pdf · pág. 2" in html and "Tecnología" in html and "CTIS" in html

def test_confirmation_messages_for_verified_and_absent_evidence():
    index = {"evidences":[{"evidence_id":"one", "field":"ficha.equipo", "document_name":"p.pdf", "page":1, "quote":"equipo", "verification":"verified"}], "by_field":{"ficha.equipo":["one"]}}
    assert "referencias documentales localizables" in build_report_model(_result(), index, _template())["information_overview"]["confirmation_message"]
    assert "No se dispone de referencias suficientes" in build_report_model(_result(), {"evidences":[], "by_field":{}}, _template())["information_overview"]["confirmation_message"]

def test_pdf_is_business_focused_and_within_two_pages(tmp_path: Path):
    chrome = shutil.which("google-chrome")
    if not chrome: pytest.skip("Google Chrome no está disponible")
    output = tmp_path / "output"; output.mkdir()
    result = _result(); result["validation"]["evidence_verification_errors"] = [{"path":"ficha.equipo", "evidence_id":"ev_bad", "message":"quote_not_found"}]
    (output / "result.json").write_text(json.dumps(result), encoding="utf-8")
    (output / "evidence-index.json").write_text(json.dumps({"evidences":[], "by_field":{}}), encoding="utf-8")
    manifest = generate_opportunity_report(tmp_path, chrome_binary=chrome)
    if not manifest["validation"]["valid"] and "Operation not permitted" in " ".join(manifest["validation"]["errors"]): pytest.skip("Chrome bloqueado por el entorno de ejecución")
    assert manifest["validation"]["valid"]
    text = "\n".join(page.extract_text() or "" for page in PdfReader(manifest["pdf"]).pages)
    assert manifest["validation"]["page_count"] <= 2 and "Información disponible para la valoración" in text
    assert "No se ha localizado la fecha límite" in text
    for unwanted in ("quote_not_found", "ev_", "Validación técnica de la extracción", "Abrir original", "Verificación:"): assert unwanted not in text


def test_windows_browser_discovery_prefers_path(monkeypatch):
    monkeypatch.setattr(generator.platform, "system", lambda: "Windows")
    monkeypatch.setattr(generator.shutil, "which", lambda name: r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe" if name == "msedge" else None)
    assert generator._find_browser("google-chrome").endswith("msedge.exe")


def test_explicit_browser_is_preserved(monkeypatch, tmp_path: Path):
    browser = tmp_path / "browser"
    browser.write_text("", encoding="utf-8")
    monkeypatch.setattr(generator.shutil, "which", lambda name: None)
    assert generator._find_browser(str(browser)) == str(browser)
