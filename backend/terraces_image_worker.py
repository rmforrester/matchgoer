"""Bounded image subprocess: original in memory, sanitised variants only on stdout."""
import sys,json,base64
if sys.platform=='linux':
    import resource
    resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
    resource.setrlimit(resource.RLIMIT_CPU,(10,10))
from terraces_images import sanitise_photo,MAX_INPUT_BYTES
try:
    data=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
    result=sanitise_photo(data)
    payload={'sha256':result.source_sha256,'bytes':result.source_bytes}
    for name,value in [('display',result.display),('thumbnail',result.thumbnail)]:
        payload[name]={'data':base64.b64encode(value.data).decode(),'width':value.width,'height':value.height}
    sys.stdout.write(json.dumps(payload))
except Exception:
    # No traceback/provider/native details or metadata in protocol/logs.
    sys.exit(2)
