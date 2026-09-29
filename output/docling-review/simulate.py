import json, sys, types, tempfile
from pathlib import Path
from types import SimpleNamespace
from pypdf import PdfWriter
from pypdf.generic import NameObject, TextStringObject
from modules.documents.ingest.models import ParseContext
import modules.documents.ingest.parsers.pdf

SOURCES = json.loads(sys.stdin.read())

def load(name, source):
    module = types.ModuleType(name)
    sys.modules[name] = module
    exec(compile(source, name, 'exec'), module.__dict__)
    return module

current = load('simulation_current_pdf', SOURCES['current_pdf'])
remote = load('simulation_remote_pdf', SOURCES['remote_pdf'])
engine = load('simulation_remote_engine', SOURCES['remote_engine'])
engine.settings = SimpleNamespace(docling_ocr_preset='tesseract', docling_ocr_backend='onnxruntime', docling_ocr_languages=['vie'])
rows = []
prose = ('Tai lieu hoc phan giai thich cau truc du lieu va thuat toan. ' * 12).strip()

def prepare(module):
    def candidates(page):
        kind = str(page['/SimKind'])
        text = '' if kind == 'scan' else prose
        quality = module.text_quality_metrics(text)
        quality['simulation_usable'] = kind != 'scan'
        return [{'method':'pypdf_plain','space_width':None,'text':text + (' TABLE' if kind=='table' else ''),'quality':quality,'score':1 if text else 0}]
    module._candidate_texts = candidates
    module._text_is_usable = lambda quality: quality.get('simulation_usable', bool(quality.get('word_count')))
    module._has_table_signature = lambda text: 'TABLE' in text
    module._image_objects = lambda resources: []

for module in (current, remote): prepare(module)
with tempfile.TemporaryDirectory(prefix='qbank-docling-simulation-') as temp:
    path = Path(temp) / 'fixture.pdf'
    context = ParseContext(document_id='simulation', source_file_name='fixture.pdf', source_uri=str(path), mime_type='application/pdf', document_type='pdf')
    for label, kinds in [('native',['plain','plain','plain']),('scan',['scan','scan','scan']),('mixed',['plain','scan','plain']),('layout',['plain','table','plain'])]:
        writer = PdfWriter()
        for kind in kinds:
            page = writer.add_blank_page(width=595,height=842)
            page[NameObject('/SimKind')] = TextStringObject(kind)
        with path.open('wb') as stream: writer.write(stream)
        entry = {'case':label, 'pages':len(kinds)}
        for name, module in [('easyocr',current),('docling',remote)]:
            called=[]
            def fake_ocr(file, pages, ctx):
                called.extend(pages)
                return {number:{'text':prose,'original_text':prose,'structured_blocks':[],'formula_blocks':[]} for number in pages}
            parsed = module.PdfParser(ocr_page_extractor=fake_ocr).parse(path,context)
            entry[name+'_selected_pages']=called
            assert len(parsed.units)==len(kinds)
            assert [unit.page_number for unit in parsed.units]==list(range(1,len(kinds)+1))
        rows.append(entry)
    assert rows[0]['easyocr_selected_pages']==rows[0]['docling_selected_pages']==[]
    assert rows[1]['easyocr_selected_pages']==rows[1]['docling_selected_pages']==[1,2,3]
    assert rows[2]['easyocr_selected_pages']==rows[2]['docling_selected_pages']==[2]
    assert rows[3]['easyocr_selected_pages']==[] and rows[3]['docling_selected_pages']==[2]

    engine.ocr_pdf = lambda file: {'pages':[{'page_number':1,'text':'page one'},{'page_number':2,'text':'page three'}], 'structured_blocks':[{'page_number':2,'block_type':'code','content':'x = 1;'}]}
    mapped = engine.ocr_pdf_pages(str(path),[3,1,3])
    assert sorted(mapped)==[1,3] and mapped[3]['text']=='page three'
    assert mapped[3]['structured_blocks'][0]['page_number']==3
    assert engine.ocr_pdf_pages(str(path),[])=={}
    fields,_ = engine._ocr_form_data()
    assert ('ocr_preset','tesseract') in fields and ('ocr_lang','vie') in fields

    # Native text remains when an optional layout service fails; scan cannot pass.
    writer=PdfWriter()
    for kind in ['plain','table','scan']:
        page=writer.add_blank_page(width=595,height=842)
        page[NameObject('/SimKind')]=TextStringObject(kind)
    with path.open('wb') as stream: writer.write(stream)
    def failed(*args): raise ConnectionError('simulated unavailable service')
    parsed=remote.PdfParser(ocr_page_extractor=failed).parse(path,context)
    statuses=[unit.quality.get('status', 'native_text') for unit in parsed.units]
    assert statuses[1]=='passed_with_warning' and statuses[2]=='quality_failed'

print(json.dumps({'mode':'mocked OCR; no real OCR or speed measurement','routing':rows,'page_mapping':'PASS (source pages 1 and 3; structured block -> page 3)','tesseract_vietnamese_request':'PASS','service_failure':statuses,'checks':'PASS'},indent=2))
