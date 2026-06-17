import json
import os

if os.path.exists('latest_doc.json'):
    with open('latest_doc.json', 'r', encoding='utf-8') as f:
        doc = json.load(f)

    doc_style = doc.get('documentStyle', {})
    print('doc_style pageNumberStart:', doc_style.get('pageNumberStart'))

    for i, section in enumerate(doc.get('body', {}).get('content', [])):
        if 'sectionBreak' in section:
            style = section['sectionBreak'].get('sectionStyle', {})
            print(f'SectionBreak {i} pageNumberStart:', style.get('pageNumberStart'))
else:
    print('latest_doc.json not found')
