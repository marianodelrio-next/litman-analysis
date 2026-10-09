from __future__ import annotations
from pathlib import Path
from typing import Any
from docx import Document
from ..docx_helpers import (MISSING, add_callout, add_checkbox_item, add_data_table, add_fact_table, add_empty_message, add_label_value, amount_value, boolean_value, configure_document, display_value, named_description, truncate_value)

GROUPS=(('documento_tecnico','Documento técnico'),('economico','Información económica'),('resumen','Resumen y coordinación'),('general','Generales'))
def _items(x:Any)->list[Any]: return x if isinstance(x,list) else []
def _header(h:dict[str,Any])->str: return ' · '.join(str(x) for x in (h.get('expediente'),h.get('nombre')) if x not in (None,'')) or MISSING
def _rules(d:dict[str,Any])->list[Any]:
    m=d.get('memoria_tecnica') if isinstance(d.get('memoria_tecnica'),dict) else {}; return _items(m.get('reglas'))

def write_bid_preparation_guide(data:dict[str,Any],path:Path)->None:
    doc=Document(); h=data.get('cabecera') if isinstance(data.get('cabecera'),dict) else {}; configure_document(doc,title='Guía de preparación de la oferta',subject='Guía operativa de preparación de oferta',document_label='Guía de preparación de la oferta',header_text=_header(h))
    _cover(doc,data,h); doc.add_page_break(); _detail(doc,data); path.parent.mkdir(parents=True,exist_ok=True); doc.save(path)

def _cover(doc:Document,d:dict[str,Any],h:dict[str,Any])->None:
    doc.add_heading('GUÍA DE PREPARACIÓN DE LA OFERTA',1); doc.add_paragraph(display_value(h.get('nombre')),style='LitMan Lead'); doc.add_paragraph(' · '.join(x for x in (display_value(h.get('organismo')) if h.get('organismo') else '',f"Expediente {h['expediente']}" if h.get('expediente') else '') if x) or MISSING,style='LitMan Metadata')
    add_fact_table(doc,['FECHA LÍMITE','PRESUPUESTO','DOCUMENTOS','PENDIENTES'],[h.get('fecha_limite'),amount_value(h.get('presupuesto_sin_iva'),h.get('moneda')),len(_items(d.get('documentos_oferta'))),len(_items(d.get('pendientes')))])
    m=d.get('memoria_tecnica') if isinstance(d.get('memoria_tecnica'),dict) else {}; docs=_items(d.get('documentos_oferta')); sections=_items(m.get('secciones')); req=_items(d.get('requisitos_oferta')); pending=_items(d.get('pendientes'))
    doc.add_paragraph(f"{len(sections)} apartados de memoria · {len(req)} requisitos · {sum(1 for x in docs if isinstance(x,dict) and x.get('obligatorio') is True)} documentos obligatorios · {len(_rules(d))} reglas formales",style='LitMan Metadata')
    doc.add_heading('Restricciones críticas de la memoria',2)
    fmt=m.get('formato') if isinstance(m.get('formato'),dict) else {}; restrictions=[]
    for r in _rules(d):
        if isinstance(r,dict) and str(r.get('tipo','')).lower()=='prohibicion': restrictions.append(('PROHIBICIÓN',r.get('descripcion')))
    if m.get('requerida') is True: restrictions.append(('OBLIGATORIO','Memoria técnica requerida'))
    if fmt.get('paginas_maximas') is not None: restrictions.append(('OBLIGATORIO',f"Máximo {fmt['paginas_maximas']} páginas"))
    if m.get('estructura_impuesta') is True: restrictions.append(('OBLIGATORIO','Estructura impuesta'))
    for label,key,word in (('FORMATO','fuente','Fuente'),('FORMATO','tamano_pt','Tamaño'),('FORMATO','interlineado','Interlineado')):
        if fmt.get(key) is not None: restrictions.append((label,f"{word} {fmt[key]}" + (' pt' if key=='tamano_pt' else '')))
    for key,text in (('portada_computa_limite','si la portada computa en el límite'),('indice_computa_limite','si el índice computa en el límite'),('anexos_computan_limite','si los anexos computan en el límite')):
        if m.get(key) is None: restrictions.append(('NO CONSTA',text))
    restrictions += [('ADVERTENCIA',r.get('descripcion')) for r in _rules(d) if isinstance(r,dict) and str(r.get('tipo','')).lower()=='advertencia']
    restrictions += [('OBLIGATORIO',r.get('descripcion')) for r in _rules(d) if isinstance(r,dict) and str(r.get('tipo','')).lower() not in ('prohibicion','advertencia')]
    for label,text in restrictions[:5]: doc.add_paragraph(label+' · '+display_value(text),style='LitMan Compact')
    if len(restrictions)>5: doc.add_paragraph(f"Y {len(restrictions)-5} reglas o restricciones adicionales en el detalle.",style='LitMan Metadata')
    if not restrictions: add_empty_message(doc,'No se han identificado restricciones formales en el dossier.')
    doc.add_heading('Pendientes por área',2); any_pending=False
    for code,label in GROUPS:
        n=sum(1 for x in pending if isinstance(x,dict) and x.get('destino')==code)
        if n: doc.add_paragraph(f'{label}  {n}',style='LitMan Card Body'); any_pending=True
    if not any_pending: add_empty_message(doc,'No se han registrado pendientes.')
    for x in pending[:4]:
        if isinstance(x,dict): doc.add_paragraph('• '+display_value(x.get('descripcion')),style='LitMan Compact')

def _detail(doc:Document,d:dict[str,Any])->None:
    _documents(doc,d); _memory(doc,d); _format(doc,d); _formal_rules(doc,d); _criteria(doc,d); _requirements(doc,d); _pending(doc,d); _quality(doc,d); doc.add_page_break(); _evidence(doc,d)

def _documents(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Documentación que presentar',2); values=[x for x in _items(d.get('documentos_oferta')) if isinstance(x,dict)]
    add_data_table(doc,['REVISADO','DOCUMENTO','SOBRE','OBLIGATORIO'],[('□',x.get('nombre'),x.get('sobre'),boolean_value(x.get('obligatorio'))) for x in values] or [('□',MISSING,MISSING,MISSING)],[1.5,6,2,3])
    doc.add_paragraph('Esta relación corresponde a los documentos de presentación de la oferta, no a los entregables del contrato.',style='LitMan Callout'); doc.add_heading('Notas sobre los documentos',3)
    for x in values:
        if x.get('descripcion') not in (None,''): add_callout(doc,display_value(x.get('nombre')),x.get('descripcion'))

def _memory(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Plano de la memoria técnica',2); m=d.get('memoria_tecnica') if isinstance(d.get('memoria_tecnica'),dict) else {}
    add_data_table(doc,['REQUERIDA','DOCUMENTO','IDIOMA','ESTRUCTURA IMPUESTA'],[(boolean_value(m.get('requerida')),m.get('nombre_documento'),m.get('idioma'),boolean_value(m.get('estructura_impuesta')))])
    sections=[x for x in _items(m.get('secciones')) if isinstance(x,dict)]
    if sections:
        for x in sorted(sections,key=lambda y:(y.get('orden') is None,y.get('orden',0))):
            title=f"{x.get('orden'):02d}" if isinstance(x.get('orden'),int) else MISSING
            obligation='OBLIGATORIO' if x.get('obligatoria') is True else 'NO OBLIGATORIO' if x.get('obligatoria') is False else 'OBLIGATORIEDAD NO INDICADA'
            points=f"{x['puntuacion']} puntos" if x.get('puntuacion') is not None else 'Puntuación no indicada'
            limit=f"Máximo {x['limite_paginas']} páginas" if x.get('limite_paginas') is not None else 'Límite no indicado'
            add_callout(doc,title+' · '+display_value(x.get('titulo')),f"{obligation} | {points} | {limit}")
            add_label_value(doc,'Objetivo del apartado',x.get('descripcion')); p=doc.add_paragraph('Debe responder a',style='LitMan Fact Label'); p.paragraph_format.keep_with_next=True
            for r in _items(x.get('requisitos_relacionados')) or [MISSING]: doc.add_paragraph('• '+display_value(r),style='LitMan Compact')
    else:
        suggested=_items(d.get('estructura_documento_tecnico'))
        if suggested:
            doc.add_paragraph('ESTRUCTURA SUGERIDA POR EL ANÁLISIS',style='LitMan Card Title'); doc.add_paragraph('No constituye una estructura obligatoria del pliego.',style='LitMan Callout')
            for x in suggested: doc.add_paragraph('• '+named_description(x),style='LitMan Card Body')
        else: add_empty_message(doc,'No se ha localizado una estructura de la memoria técnica.')

def _format(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Formato y límites',2); m=d.get('memoria_tecnica') if isinstance(d.get('memoria_tecnica'),dict) else {}; f=m.get('formato') if isinstance(m.get('formato'),dict) else {}
    formats=(('Máximo','paginas_maximas',' páginas','el límite máximo de páginas'),('Fuente','fuente','','la fuente'),('Tamaño','tamano_pt',' pt','el tamaño de fuente'),('Interlineado','interlineado','','el interlineado'),('Margen superior','margen_superior_cm',' cm','el margen superior'),('Margen inferior','margen_inferior_cm',' cm','el margen inferior'),('Margen izquierdo','margen_izquierdo_cm',' cm','el margen izquierdo'),('Margen derecho','margen_derecho_cm',' cm','el margen derecho'))
    for label,key,unit,missing_label in formats:
        if f.get(key) is None: add_callout(doc,f'REVISAR · No consta {missing_label}.',kind='warning',show_body=False)
        else: add_checkbox_item(doc,f'{label} {f[key]}{unit}')
    for label,key,verb in (('La portada','portada_computa_limite','computa'),('El índice','indice_computa_limite','computa'),('Los anexos','anexos_computan_limite','computan')):
        val=m.get(key)
        if val is None: add_callout(doc,f'REVISAR · No consta si {label.lower()} {verb} en el límite.',kind='warning',show_body=False)
        else: add_checkbox_item(doc, f'{label} {verb if val else "no " + verb} en el límite.')

def _formal_rules(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Reglas, prohibiciones y consecuencias',2); rules=[x for x in _rules(d) if isinstance(x,dict)]; order=(('prohibicion','Prohibiciones','PROHIBICIÓN'),('obligacion','Obligaciones','OBLIGACIÓN'),('advertencia','Advertencias','ADVERTENCIA'))
    used=set()
    for key,title,label in order:
        group=[x for x in rules if str(x.get('tipo','')).lower()==key]; used.update(id(x) for x in group)
        if group: doc.add_heading(title,3)
        for x in group: add_callout(doc,label,x.get('descripcion'),kind='danger' if key=='prohibicion' else 'warning' if key=='advertencia' else 'neutral'); add_label_value(doc,'Consecuencia',x.get('consecuencia') if x.get('consecuencia') not in (None,'') else 'Consecuencia no indicada.')
    other=[x for x in rules if id(x) not in used]
    if other: doc.add_heading('Otras reglas',3)
    for x in other:
        add_callout(doc,display_value(x.get('tipo')),x.get('descripcion'))
        add_label_value(doc,'Consecuencia',x.get('consecuencia') if x.get('consecuencia') not in (None,'') else 'Consecuencia no indicada.')

def _criteria(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Mapa de evaluación',2); values=[x for x in _items(d.get('criterios_adjudicacion')) if isinstance(x,dict)]; add_data_table(doc,['CRITERIO','PUNTUACIÓN','TIPO'],[(x.get('nombre'),x.get('puntuacion_maxima') if x.get('puntuacion_maxima') is not None else 'Puntuación no indicada',x.get('tipo')) for x in values] or [(MISSING,MISSING,MISSING)])
    for x in values: add_callout(doc,display_value(x.get('nombre'))+' · '+(f"{x['puntuacion_maxima']} puntos" if x.get('puntuacion_maxima') is not None else 'Puntuación no indicada'),x.get('descripcion')); add_label_value(doc,'Dónde responder',x.get('donde_responder'))
def _requirements(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Requisitos de la oferta',2); values=[x for x in _items(d.get('requisitos_oferta')) if isinstance(x,dict)]
    for flag,title in ((True,'Obligatorios'),(False,'No obligatorios'),(None,'Obligatoriedad no indicada')):
        group=[x for x in values if x.get('obligatorio') is flag]
        if group: doc.add_heading(title,3)
        for x in group: add_callout(doc,('OBLIGATORIO' if flag is True else 'NO OBLIGATORIO' if flag is False else 'OBLIGATORIEDAD NO INDICADA')+' · '+display_value(x.get('tipo')),x.get('descripcion')); add_label_value(doc,'Dónde responder',x.get('donde_responder'))
def _pending(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Pendientes',2); values=[x for x in _items(d.get('pendientes')) if isinstance(x,dict)]; any_group=False
    for code,title in GROUPS:
        group=[x for x in values if x.get('destino')==code]
        if group: doc.add_heading(title,3); any_group=True
        for x in group: add_checkbox_item(doc,x.get('descripcion')); add_label_value(doc,'Motivo',x.get('motivo') if x.get('motivo') not in (None,'') else 'Motivo no indicado.')
    if not any_group: add_empty_message(doc,'No se han registrado pendientes para preparar la oferta.')
def _quality(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Calidad y limitaciones',2); q=d.get('calidad') if isinstance(d.get('calidad'),dict) else {}; limits=_items(q.get('limitaciones')); state=display_value(q.get('estado')).lower(); kind='success' if state=='suficiente' else 'warning' if state=='parcial' else 'danger' if state=='insuficiente' else 'warning'; add_callout(doc,'CALIDAD DEL ANÁLISIS: '+display_value(q.get('estado')).upper(),'; '.join(display_value(x) for x in limits) if limits else 'No se han registrado limitaciones relevantes.',kind=kind)
def _evidence(doc:Document,d:dict[str,Any])->None:
    doc.add_heading('Anexo de fuentes y evidencias',2); groups: dict[Any,list[dict[str,Any]]] = {}
    for x in [x for x in _items(d.get('evidencias')) if isinstance(x,dict)]: groups.setdefault(x.get('campo'),[]).append(x)
    for field, evidence in groups.items():
        doc.add_heading(display_value(field),3)
        for x in evidence:
            doc.add_paragraph('Documento: '+display_value(x.get('documento_id'))+'\nPágina: '+display_value(x.get('pagina')),style='LitMan Evidence'); doc.add_paragraph('“'+truncate_value(x.get('texto_citado'))+'”',style='LitMan Evidence')
    if not groups: add_empty_message(doc,'No consta información sobre fuentes y evidencias.')
