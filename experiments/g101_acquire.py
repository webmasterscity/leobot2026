"""Acquire only the pinned Model2Vec files, preserving hashes and acquisition cost."""
import hashlib
import json
from pathlib import Path
import resource
import time
import urllib.request

REVISION='73908c3438cf03b6a01bcb9611d62b23d0726f08'
REPO='minishlab/potion-multilingual-128M'
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.leobot-data/g101/model'
FILES=('config.json','model.safetensors','tokenizer.json','tokenizer_config.json','special_tokens_map.json','README.md')


def main():
    cpu,wall=time.process_time(),time.monotonic();OUT.mkdir(exist_ok=True)
    records=[];total=0
    with urllib.request.urlopen(f'https://huggingface.co/api/models/{REPO}/revision/{REVISION}?blobs=true',timeout=30) as f:
        metadata=json.load(f)
    remote={r['rfilename']:r for r in metadata['siblings']}
    assert metadata['sha']==REVISION
    assert sum(remote[n].get('size',0) for n in FILES)<=650*1024**2
    for name in FILES:
        path=OUT/name
        if path.exists():raise FileExistsError(path)
        begin=time.monotonic();sha=hashlib.sha256();size=0;temp=path.with_suffix(path.suffix+'.part')
        with urllib.request.urlopen(f'https://huggingface.co/{REPO}/resolve/{REVISION}/{name}',timeout=90) as stream,temp.open('wb') as dest:
            while chunk:=stream.read(4*1024**2):
                dest.write(chunk);sha.update(chunk);size+=len(chunk);total+=len(chunk)
                if total>650*1024**2 or time.monotonic()-wall>900 or time.process_time()-cpu>600:
                    raise TimeoutError('G101 acquisition budget')
        expected=remote[name].get('lfs',{}).get('sha256') or remote[name].get('lfs',{}).get('oid')
        assert not expected or sha.hexdigest()==expected
        assert size==remote[name]['size']
        temp.rename(path);records.append({'file':name,'bytes':size,'sha256':sha.hexdigest(),'wall_s':time.monotonic()-begin})
        print(json.dumps(records[-1]),flush=True)
    result={'repo':REPO,'revision':REVISION,'files':records,'bytes':total,'cpu_s':time.process_time()-cpu,
            'wall_s':time.monotonic()-wall,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
            'license':'MIT, model card','scope':'No teacher model download or remote inference'}
    (ROOT/'results_v3/g101_acquisition.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
