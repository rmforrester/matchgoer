"""Offline Linux validation of current B1 child worker; no storage/database imports."""
import base64,hashlib,importlib.metadata,json,os,platform,subprocess,sys,tempfile
from io import BytesIO
from pathlib import Path
if sys.platform!='linux' or sys.version_info[:2]!=(3,14):raise SystemExit('BLOCKED: Linux Python 3.14 required')
assert importlib.metadata.version('Pillow')=='12.3.0'
assert importlib.metadata.version('pillow-heif')=='1.8.1'
from PIL import Image,ImageOps,ImageChops,ImageStat
from pillow_heif import register_heif_opener
register_heif_opener(thumbnails=False)
source=Path(os.getenv('B1_SOURCE','/source'));fixtures=Path(__file__).parent
worker=source/'backend/terraces_image_worker.py'
env={'PATH':os.environ['PATH'],'PYTHONPATH':str(source/'backend'),'PYTHONDONTWRITEBYTECODE':'1'}
def execute(data,path=worker):
    return subprocess.run([sys.executable,str(path)],input=data,capture_output=True,env=env,timeout=15)
def verify(data,label):
    references={}
    with Image.open(BytesIO(data)) as raw:
        expected=ImageOps.exif_transpose(raw).size
        multi=getattr(raw,'n_frames',1)!=1
        if not multi:
            with ImageOps.exif_transpose(raw) as oriented:
                with oriented.convert('RGB') as rgb:
                    for name,maximum in [('display',1600),('thumbnail',400)]:
                        reference=rgb.copy();reference.thumbnail((maximum,maximum),Image.Resampling.LANCZOS)
                        references[name]=reference
    result=execute(data)
    if multi:
        assert result.returncode==2 and json.loads(result.stdout).get('error_code') in {'unsupported_image_encoding','image_validation_failed','image_resource_limit'}
        return {'case':label,'multi_frame_rejected':True}
    assert result.returncode==0,(label,result.returncode)
    value=json.loads(result.stdout)
    quality={}
    assert value['sha256']==hashlib.sha256(data).hexdigest() and value['bytes']==len(data)
    for name,maximum in [('display',1600),('thumbnail',400)]:
        variant=value[name];out=base64.b64decode(variant['data'],validate=True)
        with Image.open(BytesIO(out)) as clean:
            clean.load()
            assert clean.format=='JPEG' and clean.size==(variant['width'],variant['height'])
            assert not clean.getexif()
            assert not any(k in clean.info for k in ('exif','xmp','icc_profile','gps'))
            assert max(clean.size)<=maximum
            assert abs(clean.width/clean.height-expected[0]/expected[1])<.05
            assert clean.size==references[name].size
            with ImageChops.difference(clean,references[name]) as difference:
                rms=ImageStat.Stat(difference).rms
            assert max(rms)<30,(label,name,rms)
            quality[name]=rms
        references[name].close()
    return {'case':label,'decode_orientation_metadata_thumbnails':'PASS','jpeg_reference_channel_rms':quality}
checks=[]
def checked(label,action):
    try:checks.append(action())
    except Exception as error:
        checks.append({'case':label,'status':'FAIL','error_type':type(error).__name__,'detail':str(error)})
for fixture in json.loads((fixtures/'fixture-manifest.json').read_text()):
    data=(fixtures/'fixtures'/fixture['file']).read_bytes()
    assert hashlib.sha256(data).hexdigest()==fixture['sha256']
    checked(fixture['file'],lambda:verify(data,fixture['file']))
for fmt in ('JPEG','PNG'):
    image=Image.new('RGB',(1800,900),'green');exif=Image.Exif();exif[274]=6
    exif[34853]={1:'N',2:(51.0,0.0,0.0),3:'W',4:(1.0,0.0,0.0)}
    stream=BytesIO();image.save(stream,format=fmt,exif=exif)
    checked(fmt+' orientation and GPS',lambda:verify(stream.getvalue(),fmt+' orientation and GPS'))
for label,data in [('malformed',b'\x00bad'),('oversized',b'x'*10_000_001),('SVG',b'<svg/>')]:
    result=execute(data);assert result.returncode==2 and json.loads(result.stdout).get('error_code') in {'unsupported_image_encoding','image_validation_failed','image_resource_limit'}
    checks.append({'case':label,'rejected':True})
# Intercept only the sanitiser in a test-only child to probe the exact limits
# installed by the unchanged worker before it processes any image.
with tempfile.TemporaryDirectory() as temporary:
    for mode in ('limits','memory','cpu'):
        probe=Path(temporary)/'probe.py'
        body="""import sys,resource,runpy,terraces_images
original=terraces_images.sanitise_photo
def probe(data):
 assert resource.getrlimit(resource.RLIMIT_AS)==(768*1024*1024,768*1024*1024)
 assert resource.getrlimit(resource.RLIMIT_CPU)==(10,10)
 MODE
 return original(data)
terraces_images.sanitise_photo=probe
runpy.run_path(WORKER,run_name='__main__')
"""
        action={'limits':'pass','memory':'allocation=bytearray(1024*1024*1024)','cpu':'while True: pass'}[mode]
        probe.write_text(body.replace('MODE',action).replace('WORKER',repr(str(worker))))
        result=execute(stream.getvalue(),probe)
        assert (result.returncode==0) if mode=='limits' else (result.returncode==2 and json.loads(result.stdout)=={'error_code':'image_resource_limit'}) if mode=='memory' else (result.returncode in (-9,-24) and not result.stdout)
        checks.append({'case':mode+' resource probe','status':'PASS'})
passed=not any(c.get('status')=='FAIL' for c in checks)
receipt={'status':'PASS' if passed else 'FAIL','platform':platform.platform(),'python':platform.python_version(),'Pillow':importlib.metadata.version('Pillow'),'pillow-heif':importlib.metadata.version('pillow-heif'),'checks':checks,'worker_sha256':hashlib.sha256(worker.read_bytes()).hexdigest(),'hosted_connections':0,'storage_uploads':0}
Path('/output/b1-worker-results.json').write_text(json.dumps(receipt,indent=2)+'\n')
print('B1 worker image/security/resource checks',receipt['status'])
raise SystemExit(0 if passed else 1)
