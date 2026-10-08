from __future__ import annotations
from pathlib import Path
from typing import Any
from docx import Document
from ..docx_helpers import (MISSING, abbreviate_text, add_callout, add_checkbox_item, add_fact_table, add_empty_message, add_label_value, amount_value, configure_document, display_value, named_description, set_keep_with_next)

def _header(h: dict[str, Any]) -> str: return " · ".join(str(x) for x in (h.get("expediente"), h.get("nombre")) if x not in (None, "")) or MISSING
def _items(x: Any) -> list[Any]: return x if isinstance(x, list) else []
def _count(x: list[Any], one: str, many: str) -> str: return f"{len(x)} {one if len(x)==1 else many}"

def write_technical_summary(data: dict[str, Any], path: Path) -> None:
    doc=Document(); h=data.get("cabecera") if isinstance(data.get("cabecera"),dict) else {}
    configure_document(doc,title="Resumen técnico",subject="Resumen técnico del expediente",document_label="Resumen técnico",header_text=_header(h))
    _cover(doc,data,h); doc.add_page_break(); _detail(doc,data)
    path.parent.mkdir(parents=True,exist_ok=True); doc.save(path)

def _cover(doc: Document,d:dict[str,Any],h:dict[str,Any])->None:
    doc.add_heading("RESUMEN TÉCNICO",1); doc.add_paragraph(display_value(h.get("nombre")),style="LitMan Lead")
    identity=" · ".join(x for x in (display_value(h.get("organismo")) if h.get("organismo") else "",f"Expediente {h['expediente']}" if h.get("expediente") else "") if x); doc.add_paragraph(identity or MISSING,style="LitMan Metadata")
    add_fact_table(doc,["EXPEDIENTE","FECHA LÍMITE","PRESUPUESTO","FASES"],[h.get("expediente"),h.get("fecha_limite"),amount_value(h.get("presupuesto_sin_iva"),h.get("moneda")),len(_items(d.get("fases")))])
    doc.add_heading("Qué se contrata",2); doc.add_paragraph(abbreviate_text(d.get("contexto"),220," Ver detalle en “Comprensión del proyecto”."),style="LitMan Callout")
    _cover_list(doc,"Objetivos principales",_items(d.get("objetivos")),3,"objetivos"); scope=_items(d.get("alcance")); _cover_list(doc,"Alcance de un vistazo",scope,3,"elementos de alcance")
    doc.add_paragraph(" · ".join((_count(_items(d.get("trabajos")),"trabajo","trabajos"),_count(_items(d.get("entregables_contrato")),"entregable","entregables"),_count(_items(d.get("fases")),"fase","fases"))),style="LitMan Metadata")
    req=[x for x in _items(d.get("requisitos_oferta")) if isinstance(x,dict)]; selected=[x for x in req if x.get("obligatorio") is True]+[x for x in req if x.get("obligatorio") is None]
    doc.add_heading("Condicionantes de la solución",2)
    if not selected: add_empty_message(doc,"No constan requisitos obligatorios o con obligatoriedad pendiente.")
    for x in selected[:3]: doc.add_paragraph(("OBLIGATORIO" if x.get("obligatorio") is True else "NO CONSTA OBLIGATORIEDAD")+" · "+abbreviate_text(x.get("descripcion"),100),style="LitMan Compact")
    if len(selected)>3: doc.add_paragraph(f"Y {len(selected)-3} requisitos adicionales en el detalle.",style="LitMan Metadata")
    doc.add_heading("Guía para el revisor técnico",2); doc.add_paragraph("AL REVISAR LA PROPUESTA, COMPRUEBA",style="LitMan Card Title")
    for x in ("Que cubra todo el alcance y los trabajos exigidos.","Que contemple todas las fases y entregables.","Que el equipo satisfaga los perfiles mínimos.","Que la solución respete tecnologías e integraciones.","Que responda a todos los criterios evaluables."): add_checkbox_item(doc,x)

def _cover_list(doc:Document,title:str,values:list[Any],maximum:int, noun:str)->None:
    doc.add_heading(title,2)
    if not values: add_empty_message(doc,f"No consta información sobre {title.lower()}."); return
    for i,x in enumerate(values[:maximum],1): doc.add_paragraph(f"{i}. {abbreviate_text(x,80)}",style="LitMan Compact")
    if len(values)>maximum: doc.add_paragraph(f"Y {len(values)-maximum} {noun} adicionales en el detalle.",style="LitMan Metadata")

def _detail(doc:Document,d:dict[str,Any])->None:
    doc.add_heading("Comprensión del proyecto",2); _paragraph(doc,"Contexto y situación de partida",d.get("contexto"),"No consta una descripción del contexto del proyecto."); _list(doc,"Objetivos",d.get("objetivos"),True); _list(doc,"Alcance",d.get("alcance")); _list(doc,"Trabajos requeridos",d.get("trabajos"))
    doc.add_heading("Ejecución y resultados",2); _phases(doc,d.get("fases")); _cards(doc,"Entregables del contrato",d.get("entregables_contrato"),"No consta información sobre entregables contractuales.")
    doc.add_heading("Recursos y tecnología",2); _cards(doc,"Equipo y perfiles exigidos",d.get("equipo"),"No consta información sobre equipo."); _list(doc,"Tecnologías y plataformas",d.get("tecnologias"))
    doc.add_heading("Condiciones de la solución",2); _requirements(doc,d.get("requisitos_oferta")); _criteria(doc,d.get("criterios_adjudicacion")); _quality(doc,d.get("calidad"))

def _paragraph(doc:Document,title:str,value:Any,empty:str)->None: doc.add_heading(title,3); doc.add_paragraph(display_value(value) if value not in (None,"") else empty)
def _list(doc:Document,title:str,value:Any,numbered:bool=False)->None:
    doc.add_heading(title,3); values=_items(value)
    if not values: add_empty_message(doc,f"No consta información sobre {title.lower()}."); return
    for i,x in enumerate(values,1): doc.add_paragraph((f"{i}. " if numbered else "• ")+display_value(x),style="LitMan Card Body")
def _cards(doc:Document,title:str,value:Any,empty:str)->None:
    doc.add_heading(title,3); values=_items(value)
    if not values: add_empty_message(doc,empty); return
    for x in values:
        item=x if isinstance(x,dict) else {"nombre":x}; p=doc.add_paragraph(display_value(item.get("nombre")),style="LitMan Card Title"); set_keep_with_next(p); doc.add_paragraph(display_value(item.get("descripcion")),style="LitMan Card Body")
def _phases(doc:Document,value:Any)->None:
    doc.add_heading("Fases, plazos y entregables",3); values=_items(value)
    if not values: add_empty_message(doc,"No consta información sobre fases."); return
    for i,x in enumerate(values,1):
        item=x if isinstance(x,dict) else {}; p=doc.add_paragraph(f"FASE {i:02d} · {display_value(item.get('nombre'))}",style="LitMan Card Title"); set_keep_with_next(p)
        for label,key in (("Plazo","plazo"),("Descripción","descripcion")):
            add_label_value(doc,label,item.get(key))
        p=doc.add_paragraph("Entregables",style="LitMan Fact Label"); set_keep_with_next(p)
        for e in _items(item.get("entregables")) or [MISSING]: doc.add_paragraph("• "+named_description(e),style="LitMan Compact")
def _requirements(doc:Document,value:Any)->None:
    doc.add_heading("Requisitos",3)
    values=_items(value)
    if not values: add_empty_message(doc,"No constan requisitos de la oferta."); return
    for x in values:
        item=x if isinstance(x,dict) else {}; label="OBLIGATORIO" if item.get("obligatorio") is True else "NO OBLIGATORIO" if item.get("obligatorio") is False else "OBLIGATORIEDAD NO INDICADA"; add_callout(doc,label+" · "+display_value(item.get("tipo")),item.get("descripcion")); add_label_value(doc,"Dónde responder",item.get("donde_responder"))
def _criteria(doc:Document,value:Any)->None:
    doc.add_heading("Criterios",3)
    values=_items(value)
    if not values: add_empty_message(doc,"No constan criterios de adjudicación."); return
    for x in values:
        item=x if isinstance(x,dict) else {}; points=f"{item['puntuacion_maxima']} puntos" if item.get("puntuacion_maxima") is not None else "Puntuación no indicada"; add_callout(doc,display_value(item.get("nombre"))+" · "+points,item.get("descripcion")); add_label_value(doc,"Tipo",item.get("tipo")); add_label_value(doc,"Dónde responder",item.get("donde_responder"))
def _quality(doc:Document,value:Any)->None:
    q=value if isinstance(value,dict) else {}; limits=_items(q.get("limitaciones")); state=display_value(q.get("estado")).lower(); kind="success" if state=="suficiente" else "warning" if state=="parcial" else "danger" if state=="insuficiente" else "warning"; add_callout(doc,"CALIDAD DEL ANÁLISIS: "+display_value(q.get("estado")).upper(),"; ".join(display_value(x) for x in limits) if limits else "No se han registrado limitaciones relevantes.",kind=kind)
