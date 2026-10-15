"""Measure baseline/corrected workers under identical production limits."""
import base64,hashlib,json,os,subprocess,sys,tempfile
from pathlib import Path
V=Path(__file__).parent;SOURCE=Path('/source');worker=SOURCE/'backend/terraces_image_worker.py'
environment={'PATH':os.environ['PATH'],'PYTHONPATH':'/source/backend','PYTHONDONTWRITEBYTECODE':'1'}
rows=[]
for name in ('pug.heic','arrow.heic','L_exif_xmp_iptc.heic'):
    data=(V/'fixtures'/name).read_bytes();modes={}
    for mode in ('baseline','fixed'):
        wrapper="""import sys,json,resource,runpy,importlib.util
from pathlib import Path
BASELINE
import terraces_images
original=terraces_images.sanitise_photo
def measured(data):
 try:return original(data)
 finally:
  fields={line.split(':',1)[0]:line.split(':',1)[1].strip() for line in Path('/proc/self/status').read_text().splitlines() if ':' in line}
  print(json.dumps({'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'peak_virtual_kib':int(fields['VmPeak'].split()[0]),'address_space_limit_bytes':resource.getrlimit(resource.RLIMIT_AS)[0],'cpu_limit_seconds':resource.getrlimit(resource.RLIMIT_CPU)[0]}),file=sys.stderr)
terraces_images.sanitise_photo=measured
runpy.run_path(WORKER,run_name='__main__')
"""
        baseline="spec=importlib.util.spec_from_file_location('terraces_images',BASE);module=importlib.util.module_from_spec(spec);sys.modules['terraces_images']=module;spec.loader.exec_module(module)".replace('BASE',repr(str(V/'baseline_terraces_images.py'))) if mode=='baseline' else 'pass'
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'measure.py';target.write_text(wrapper.replace('BASELINE',baseline).replace('WORKER',repr(str(worker))))
            result=subprocess.run([sys.executable,str(target)],input=data,capture_output=True,env=environment,timeout=15)
        measurement=json.loads(result.stderr.splitlines()[-1]);assert measurement['address_space_limit_bytes']==768*1024*1024 and measurement['cpu_limit_seconds']==10
        measurement['returncode']=result.returncode
        if result.returncode==0:
            payload=json.loads(result.stdout)
            measurement['variant_hashes']={n:hashlib.sha256(base64.b64decode(payload[n]['data'])).hexdigest() for n in ('display','thumbnail')}
        modes[mode]=measurement
    assert modes['fixed']['returncode']==0,(name,modes)
    if name in ('pug.heic','arrow.heic'):assert modes['baseline']['returncode']==2,(name,modes)
    if modes['baseline']['returncode']==0:assert modes['baseline']['variant_hashes']==modes['fixed']['variant_hashes']
    rows.append({'fixture':name,**modes})
Path('/output/memory-comparison.json').write_text(json.dumps({'status':'PASS','measurements':rows},indent=2)+'\n')
print('Baseline failures reproduced; corrected HEIC workers fit unchanged limits; memory peaks recorded.')
