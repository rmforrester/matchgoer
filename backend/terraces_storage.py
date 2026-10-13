"""Private server-only Supabase transport. Never logs URLs, tokens or bodies."""
import hashlib
import os
import re
from urllib.parse import urljoin,urlsplit
import requests

class StorageUnavailable(Exception):
    pass

class PrivatePhotoStorage:
    def __init__(self, *, session=None):
        self.base=os.getenv('SUPABASE_URL','').rstrip('/')
        self.key=os.getenv('SUPABASE_SERVICE_ROLE_KEY','')
        p=urlsplit(self.base)
        if p.scheme!='https' or not p.hostname or p.username or p.password or p.query or p.fragment or p.path:
            raise StorageUnavailable('Private storage is unavailable')
        if not self.key:raise StorageUnavailable('Private storage is unavailable')
        self.session=session or requests.Session()
        self.bucket='terraces-photos'

    def path(self,key):
        if not re.fullmatch(r'photos/[0-9a-f]{32}/(?:display|thumbnail)\.jpg',key):
            raise StorageUnavailable('Invalid private object reservation')
        return '/storage/v1/object/'+self.bucket+'/'+key

    def request(self,method,path,**kwargs):
        try:
            return self.session.request(method,self.base+path,headers={'apikey':self.key,'Authorization':'Bearer '+self.key,**kwargs.pop('headers',{})},timeout=(5,15),allow_redirects=False,**kwargs)
        except requests.RequestException:
            raise StorageUnavailable('Private storage is unavailable') from None

    def put(self,key,data):
        path=self.path(key)
        r=self.request('POST',path,data=data,headers={'Content-Type':'image/jpeg','x-upsert':'false','cache-control':'private, no-store'})
        if 200<=r.status_code<300:return
        # A timed-out prior immutable write may already exist. Verify exact bytes,
        # never overwrite an existing object or trust a client-provided hash.
        if r.status_code in (400,409):
            existing=self.request('GET',path,stream=True)
            if existing.status_code==200:
                body=bytearray()
                try:
                    for chunk in existing.iter_content(65536):
                        body.extend(chunk)
                        if len(body)>10_000_000:raise StorageUnavailable('Private object integrity check failed')
                finally:existing.close()
                if hashlib.sha256(body).digest()==hashlib.sha256(data).digest():return
        raise StorageUnavailable('Photograph could not be stored')

    def delete(self,key):
        self.path(key)
        r=self.request('DELETE','/storage/v1/object/'+self.bucket,json={'prefixes':[key]})
        if r.status_code not in (200,204):raise StorageUnavailable('Photograph cleanup is pending')
        if r.status_code==200:
            try:
                if not isinstance(r.json(),list):raise ValueError()
            except (ValueError,TypeError):raise StorageUnavailable('Photograph cleanup is pending') from None

    def signed(self,key):
        path=self.path(key).replace('/object/','/object/sign/',1)
        r=self.request('POST',path,json={'expiresIn':90})
        if r.status_code!=200:raise StorageUnavailable('Photograph is temporarily unavailable')
        try:value=r.json()['signedURL']
        except (KeyError,ValueError,TypeError):raise StorageUnavailable('Photograph is temporarily unavailable') from None
        if not isinstance(value,str):raise StorageUnavailable('Photograph is temporarily unavailable')
        if value.startswith('/object/sign/'):
            url=self.base+'/storage/v1'+value
        else:
            url=urljoin(self.base+'/storage/v1/',value)
        parsed=urlsplit(url)
        if parsed.scheme!='https' or parsed.netloc!=urlsplit(self.base).netloc or parsed.path!='/storage/v1/object/sign/'+self.bucket+'/'+key:
            raise StorageUnavailable('Photograph is temporarily unavailable')
        return url

class LazyPrivatePhotoStorage:
    """Unpublishing must not depend on valid/available Storage configuration."""
    def __init__(self):self.client=None
    def get(self):
        if self.client is None:self.client=PrivatePhotoStorage()
        return self.client
    def put(self,key,data):return self.get().put(key,data)
    def delete(self,key):return self.get().delete(key)
    def signed(self,key):return self.get().signed(key)
