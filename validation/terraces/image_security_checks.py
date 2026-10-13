from pathlib import Path
from io import BytesIO
from unittest.mock import patch, MagicMock
import json,sys
sys.path[:0]=['/source','/source/backend']
from PIL import Image
import terraces_images as processor
from terraces_images import sanitise_photo, UnsafeImage
results=[]
def rejected(label,data):
    try: sanitise_photo(data)
    except UnsafeImage: results.append({'check':label,'status':'PASS'});return
    raise AssertionError(label+' unexpectedly accepted')
buf=BytesIO();Image.new('RGB',(32,20),'red').save(buf,format='JPEG');jpg=buf.getvalue()
sanitise_photo(jpg+b'\0'*(processor.MAX_INPUT_BYTES-len(jpg)))
results.append({'check':'valid JPEG at exact 10,000,000-byte limit','status':'PASS'})
rejected('10,000,001 bytes',jpg+b'\0'*(processor.MAX_INPUT_BYTES+1-len(jpg)))
rejected('truncated genuine HEIC',Path('/validation/fixtures/pug.heic').read_bytes()[:64])
rejected('malformed HEIC box',b'\0\0\0\x19ftypheic'+b'\0'*40)
with patch.object(Image,'MAX_IMAGE_PIXELS',10):
    rejected('Pillow decompression-bomb rejection',jpg)
for size in [(10001,1),(6000,4001)]:
    fake=MagicMock();fake.format='JPEG';fake.size=size
    fake.__enter__.return_value=fake
    with patch.object(Image,'open',return_value=fake):
        rejected('predecode dimension cap '+str(size),jpg)
    fake.load.assert_not_called()
Path('/output/image-security-results.json').write_text(json.dumps({'status':'PASS','checks':results},indent=2)+'\n')
print(str(len(results))+' additional image boundary/security checks PASS')
