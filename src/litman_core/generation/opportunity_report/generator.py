from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

from .model import build_report_model
from .renderer import load_template, render_html

def generate_opportunity_report(run_dir: Path, *, template_id: str = "executive-v1",
                                chrome_binary: str = "google-chrome") -> dict:
    run_dir = run_dir.resolve()
    output = run_dir / "output"
    result = _read(output / "result.json")
    evidence_index = _load_evidence_index(run_dir)
    manifest = load_template(template_id)
    report = build_report_model(result, evidence_index, manifest)
    _write(output / "report.json", report)
    html_path = output / "ficha_oportunidad.html"
    html_path.write_text(render_html(report, manifest), encoding="utf-8")
    pdf_path = output / "ficha_oportunidad.pdf"
    validation = {"valid": False, "html": str(html_path), "pdf": str(pdf_path), "errors": [], "warnings": []}
    chrome = shutil.which(chrome_binary) or (chrome_binary if Path(chrome_binary).exists() else None)
    if not chrome:
        validation["errors"].append(f"No se encuentra el renderizador PDF: {chrome_binary}")
    else:
        try:
            # Chrome otherwise tries to derive a shared profile from HOME and can
            # fail (or collide across jobs) before headless rendering starts.
            with tempfile.TemporaryDirectory(prefix="chrome-profile-", dir=run_dir) as profile:
                command = [chrome, "--headless", "--disable-gpu", "--no-sandbox",
                           "--disable-crash-reporter", "--disable-breakpad",
                           "--disable-dev-shm-usage", "--no-pdf-header-footer",
                           f"--user-data-dir={profile}", f"--print-to-pdf={pdf_path}",
                           html_path.as_uri()]
                completed = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False)
            if completed.returncode != 0 or not pdf_path.exists():
                validation["errors"].append("Chrome no pudo generar el PDF: " + (completed.stderr.strip() or str(completed.returncode)))
            else:
                pages = len(PdfReader(str(pdf_path)).pages)
                validation["page_count"] = pages
                if pages > int(manifest["document"].get("max_pages", 2)):
                    validation["errors"].append(f"El PDF supera el máximo de páginas: {pages}")
                validation["valid"] = not validation["errors"]
        except (subprocess.TimeoutExpired, OSError) as exc:
            validation["errors"].append(f"Error al generar PDF: {exc}")
    _write(output / "report-validation.json", validation)
    report_manifest = {"generated_at": datetime.now(timezone.utc).isoformat(), "template_id": template_id,
                       "template_version": manifest["version"], "html": str(html_path), "pdf": str(pdf_path),
                       "validation": validation}
    _write(output / "report-manifest.json", report_manifest)
    return report_manifest
def _load_evidence_index(run_dir: Path) -> dict:
    path = run_dir / "output" / "evidence-index.json"
    if not path.is_file():
        raise ValueError(f"No existe el índice de evidencias requerido: {path}")
    return _read(path)

def _read(path: Path) -> dict: return json.loads(path.read_text(encoding="utf-8"))
def _write(path: Path, value: object) -> None: path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
