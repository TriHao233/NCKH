import json,sys,types,unittest
import modules.ocr
import modules.documents.ingest.parsers.pdf
sources=json.loads(sys.stdin.read())
for name,key in [('modules.ocr.docling_engine','engine'),('modules.documents.ingest.parsers.pdf','pdf')]:
    module=types.ModuleType(name)
    module.__file__='/app/'+key+'.py'
    sys.modules[name]=module
    exec(compile(sources[key],name,'exec'),module.__dict__)
    parent,attr=name.rsplit('.',1)
    setattr(sys.modules[parent],attr,module)
compile(sources['config'],'core.config','exec')
tests=types.ModuleType('docling_contract_tests')
exec(compile(sources['test'],'docling_contract_tests','exec'),tests.__dict__)
result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(tests))
raise SystemExit(0 if result.wasSuccessful() else 1)
