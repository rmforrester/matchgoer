"""Bounded image subprocess: original in memory, sanitised variants only on stdout."""
import sys,json,base64
try:
    if sys.platform=='linux':
        import resource
        resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
        resource.setrlimit(resource.RLIMIT_CPU,(10,10))
    from terraces_images import sanitise_photo,MAX_INPUT_BYTES,UnsafeImage
    data=sys.stdin.buffer.read(MAX_INPUT_BYTES+1)
    result=sanitise_photo(data)
    payload={'sha256':result.source_sha256,'bytes':result.source_bytes}
    for name,value in [('display',result.display),('thumbnail',result.thumbnail)]:
        payload[name]={'data':base64.b64encode(value.data).decode(),'width':value.width,'height':value.height}
    sys.stdout.write(json.dumps(payload))
except Exception as error:
    # Fixed categories only: never emit exception text, metadata or native stderr.
    code = "image_processing_failed"
    if isinstance(error, MemoryError):
        code = "image_resource_limit"
    elif "UnsafeImage" in globals() and isinstance(error, UnsafeImage):
        if error.code in ("unsupported_image_encoding", "image_decode_failed", "image_resource_limit", "image_validation_failed", "image_processing_failed"):
            code = error.code
    failure = {"error_code": code}
    guard = getattr(error, "guard", None)
    if code == "unsupported_image_encoding" and guard in ("signature_or_major_brand", "heif_compatible_codec", "decoded_format"):
        failure['guard'] = guard
    sys.stdout.write(json.dumps(failure))
    sys.exit(2)
