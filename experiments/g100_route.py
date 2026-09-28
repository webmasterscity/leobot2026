"""NumPy runtime for heads adapted in G100; no training imports."""
import json
import numpy as np
from experiments.g99_interaction import InteractionRoute,ROOT,OUT as OLD

OUT=ROOT/'.leobot-data/g100'
NAMES=tuple(k+'_'+s for k in ('lexical','interaction','history') for s in ('business','general','shuffled'))


class StageRoute(InteractionRoute):
    def __init__(self,bot,name,threshold=.9):
        kind=name.split('_')[0]
        super().__init__(bot,kind,threshold,root=OLD)
        self.meta=json.loads((OUT/'models.json').read_text())
        with np.load(OUT/f'{name}.npz',allow_pickle=False) as saved:self.weights=dict(saved)
        self.gate=self.meta.get('calibration',{}).get(name)
