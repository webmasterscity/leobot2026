"""G97B offline public model, used only to select literal evidence."""
import json
from pathlib import Path
import re
import selectors
import subprocess
import time

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'.leobot-data/g97'
SYSTEM = ('Selecciona el fragmento que contiene la respuesta a la pregunta, respetando las condiciones '
          'y negaciones del texto. Usa solamente los fragmentos proporcionados. Si ninguno contiene '
          'información suficiente, responde 0. Si hay respuesta, devuelve únicamente el número del '
          'fragmento, sin explicaciones. No uses conocimiento externo.')


class LLMRoute:
    def __init__(self,bot):
        self.bot=bot; self.calls=[]; begin=time.perf_counter()
        self.log=(OUT/'runner.log').open('a')
        self.process=subprocess.Popen([str(OUT/'llm_runner'),str(OUT/'model.gguf')],
                                      stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.log,
                                      text=True,bufsize=1)
        self.ready=self.read(60)
        if not self.ready.get('ready'): raise RuntimeError(self.ready)
        self.load_ms=(time.perf_counter()-begin)*1000
        self.prepare()

    def read(self,timeout):
        with selectors.DefaultSelector() as s:
            s.register(self.process.stdout,selectors.EVENT_READ)
            if not s.select(timeout):
                self.process.kill(); self.process.wait()
                raise TimeoutError('G97 local model timeout')
        line=self.process.stdout.readline()
        if not line: raise RuntimeError('G97 local model ended')
        return json.loads(line)

    def prepare(self):
        self.units=[{'numero':i+1,'texto':u['text'],'encabezado':u.get('heading','')}
                    for i,u in enumerate(self.bot.context_units)]

    def propose(self,question,history):
        content=json.dumps({'instrucciones':[u['text'] for u in getattr(self.bot,'context_instructions',[])],
                            'historial':history,'fragmentos':self.units,'pregunta':question},ensure_ascii=False)
        prompt='<|startoftext|><|im_start|>system\n'+SYSTEM+'<|im_end|>\n<|im_start|>user\n'+content+'<|im_end|>\n<|im_start|>assistant\n'
        self.process.stdin.write(json.dumps({'prompt':prompt},ensure_ascii=False)+'\n'); self.process.stdin.flush()
        reply=self.read(60); self.calls.append(reply)
        text=reply.get('text','').strip()
        if not re.fullmatch(r'[0-9]+',text): return None
        index=int(text)-1
        return {'index':index,'confidence':None} if 0<=index<len(self.units) else None

    def close(self):
        if self.process.poll() is None:
            self.process.stdin.close(); self.process.wait(timeout=20)
        self.log.close()
