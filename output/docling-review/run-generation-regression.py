import sys,json,types,pytest
sources=json.loads(sys.stdin.read())
import core.config as config
old_settings=config.settings.model_dump()
exec(compile(sources['config'],config.__file__,'exec'),config.__dict__)
assert all(config.settings.model_dump().get(k)==v for k,v in old_settings.items()), 'Existing setting changed'
print('All existing Settings values preserved; Docling fields added only.')
import modules.ocr
import modules.documents.ingest.parsers.pdf
for name,key in [('modules.ocr.docling_engine','engine'),('modules.documents.ingest.parsers.pdf','pdf')]:
    module=types.ModuleType(name)
    module.__file__='/app/'+key+'.py'
    sys.modules[name]=module
    exec(compile(sources[key],name,'exec'),module.__dict__)
    parent,attr=name.rsplit('.',1)
    setattr(sys.modules[parent],attr,module)
raise SystemExit(pytest.main(['tests/test_generation_api.py','-q','--tb=no','-p','no:cacheprovider']))
