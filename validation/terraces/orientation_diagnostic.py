from pathlib import Path
from io import BytesIO
import json, sys
sys.path[:0]=['/source','/source/backend']
from PIL import Image, ImageOps
from pillow_heif import register_heif_opener
from terraces_images import sanitise_photo
register_heif_opener(thumbnails=False)
checks=[]
for fmt in ['JPEG','PNG','HEIF']:
    im=Image.new('RGB',(32,20),'red');ex=Image.Exif();ex[274]=6
    out=BytesIO();im.save(out,format=fmt,exif=ex)
    with Image.open(BytesIO(out.getvalue())) as raw:
        before={'size':list(raw.size),'orientation':raw.getexif().get(274),'original_orientation':raw.info.get('original_orientation')}
        raw.load();after={'size':list(raw.size),'orientation':raw.getexif().get(274),'original_orientation':raw.info.get('original_orientation')}
        transposed=list(ImageOps.exif_transpose(raw).size)
    clean=sanitise_photo(out.getvalue())
    checks.append({'format':fmt,'input':{'size':[32,20],'exif_orientation':6},'opened':before,'loaded':after,'exif_transposed':transposed,'sanitised':[clean.display.width,clean.display.height]})
Path('/output/orientation-diagnostic.json').write_text(json.dumps(checks,indent=2)+'\n')
print(json.dumps(checks))
