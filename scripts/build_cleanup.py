#!/usr/bin/env python3
"""Regenera data/enriched/cleanup.json a partir das notas dos batches enriquecidos.
Classifica registros problematicos e recomenda acao (merge/disable/delete/fix)."""
import json, glob, os, re

def classify(notes):
    n = notes.upper()
    # fechamento permanente (ignora 'possivel'/'temporario' e spa)
    if 'PERMANENTE' in n or ('FECHAD' in n and 'POSSIVEL' not in n and 'TEMPORARI' not in n and 'QUARTA' not in n and 'SPA' not in n.split('FECHAD')[0][-30:]):
        if 'FECHAD' in n or 'PERMANENTE' in n:
            return ('closed', 'disable')
    if 'CREW' in n or 'NAO E UMA SALA' in n or 'NAO E SALA' in n:
        return ('not_a_lounge', 'delete')
    if ('NAO EXISTE' in n or 'NAO HA LOUNGE' in n or 'VERIFICAR EXISTENCIA' in n
            or 'NAO FOI ENCONTRADO' in n or 'NENHUMA FONTE' in n or 'NAO OPERA' in n):
        return ('nonexistent', 'disable_or_verify')
    if 'DUPLICATA' in n:
        return ('duplicate', 'merge')
    if 'CONFLITO' in n:
        return ('data_conflict', 'fix')
    return (None, None)

def find_canonical(notes):
    m = re.search(r'id\s+([0-9a-f]{8})', notes)
    return m.group(1) if m else None

rows = []
for f in sorted(glob.glob('data/enriched/batch_*.json')):
    for r in json.load(open(f, encoding='utf-8')):
        issue, action = classify(r.get('notes', ''))
        if issue:
            rows.append({
                'lounge_id': r['lounge_id'],
                'name': r['name'],
                'airport_iata': r['airport_iata'],
                'issue_type': issue,
                'recommended_action': action,
                'related_id_hint': find_canonical(r.get('notes', '')),
                'detail': r.get('notes', ''),
            })

os.makedirs('data/enriched', exist_ok=True)
json.dump(rows, open('data/enriched/cleanup.json', 'w', encoding='utf-8'),
          ensure_ascii=False, indent=2)

from collections import Counter
c = Counter(r['issue_type'] for r in rows)
print('cleanup.json:', len(rows), 'registros sinalizados ->', dict(c))
