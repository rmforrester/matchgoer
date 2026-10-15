"""Diagnostic only: retain worker limits and expose only synthetic-image errors."""
import json,os,subprocess,sys,tempfile
from pathlib import Path
SOURCE=Path('/source');worker=SOURCE/'backend/terraces_image_worker.py'
data=(Path(__file__).parent/'fixtures/pug.heic').read_bytes()
text=worker.read_text().replace('except Exception:','except Exception as error:').replace('sys.exit(2)',"import traceback;traceback.print_exc();sys.exit(2)")
environment={'PATH':os.environ['PATH'],'PYTHONPATH':'/source/backend','PYTHONDONTWRITEBYTECODE':'1'}
with tempfile.TemporaryDirectory() as folder:
    target=Path(folder)/'diagnostic_worker.py';target.write_text(text)
    result=subprocess.run([sys.executable,str(target)],input=data,capture_output=True,env=environment,timeout=15)
    receipt={'current_limits_retained':True,'returncode':result.returncode,'synthetic_fixture_error':result.stderr.decode(errors='replace')[:2000]}
    Path('/output/worker-diagnostic.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('Synthetic worker diagnostic recorded; production worker untouched.')
