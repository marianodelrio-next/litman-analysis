import pytest


def dossier(**overrides) -> dict:
    value = {
        "schema_version": "detailed-analysis-v1",
        "cabecera": {"nombre": "Servicio de analítica", "expediente": "EXP-1", "organismo": "Entidad", "fecha_limite": None, "presupuesto_sin_iva": None, "moneda": "EUR"},
        "contexto": "La entidad necesita mejorar su capacidad de análisis.",
        "objetivos": ["Mejorar la calidad del dato"],
        "alcance": ["Diseño e implantación"],
        "trabajos": ["Analizar las fuentes", "Construir cuadros de mando"],
        "fases": [{"nombre": "Diseño", "descripcion": "Definición", "plazo": "2 semanas", "entregables": []}],
        "entregables_contrato": [{"nombre": "Diseño", "descripcion": "Documento técnico"}],
        "documentos_oferta": [], "equipo": [], "tecnologias": ["Power BI"],
        "requisitos_oferta": [{"descripcion": "Explicar la metodología", "tipo": "técnico", "obligatorio": True, "donde_responder": "Metodología"}],
        "criterios_adjudicacion": [{"nombre": "Metodología", "puntuacion_maxima": 20, "tipo": "juicio", "donde_responder": "Metodología", "descripcion": None}],
        "simulador_economico": {
            "aplicable": True, "presupuesto_maximo_sin_iva": 200000, "moneda": "EUR", "puntuacion_total": 100,
            "formula_precio": {"tipo": "inversa_oferta_minima", "expresion_literal": "Oferta mínima por 10 entre oferta evaluada", "puntuacion_maxima": 10, "redondeo_decimales": None, "evidencia": None},
            "criterios_no_precio": [{"nombre": "Oferta técnica", "tipo": "juicio_valor", "puntuacion_maxima": 90, "valor_minimo": 0, "valor_maximo": 90, "unidad": "puntos", "descripcion": "Valoración técnica", "evidencia": None}],
            "baja_anormal": {"aplica": True, "maximo_cualitativo": 90, "comparador": "menor_o_igual", "reglas": [{"min_licitadores": 4, "max_licitadores": None, "base": 0.85, "referencia": "media_ofertas", "peso_calidad": 0.05, "descripcion": "Regla para cuatro o más ofertas", "evidencia": None}], "formula_literal": "R=(85%+C×5%)×media", "advertencias": [], "evidencias": []},
            "restricciones": [], "advertencias": [],
        },
        "estructura_documento_tecnico": [],
        "memoria_tecnica": {"requerida": True, "nombre_documento": "Memoria técnica", "idioma": "es", "estructura_impuesta": True, "secciones": [{"orden": 1, "titulo": "Metodología", "descripcion": "Forma de prestación", "obligatoria": True, "puntuacion": 20, "limite_paginas": 2, "requisitos_relacionados": ["Explicar la metodología"], "evidencias": []}], "formato": {"paginas_maximas": 10, "fuente": "Arial", "tamano_pt": 11, "interlineado": 1.5, "margen_superior_cm": 2, "margen_inferior_cm": 2, "margen_izquierdo_cm": 2, "margen_derecho_cm": 2}, "reglas": [], "portada_computa_limite": False, "indice_computa_limite": False, "anexos_computan_limite": None},
        "pendientes": [], "evidencias": [], "calidad": {"estado": "suficiente", "limitaciones": []},
    }
    value.update(overrides)
    return value

@pytest.fixture(autouse=True)
def codex_test_auth(tmp_path_factory, monkeypatch):
    secret = tmp_path_factory.mktemp("codex-auth") / "codex-key"
    secret.write_text("test-only-secret\n", encoding="utf-8")
    monkeypatch.setenv("LITMAN_ANALYSIS_CODEX_AUTH_MODE", "api-key")
    monkeypatch.setenv("LITMAN_ANALYSIS_CODEX_API_KEY_FILE", str(secret))
