"""Development prototype (outside the engine): gap marker chosen by Wilson lower bound."""
import math
import leobot.reading as R
Z={'z':1.96}
def wilson(p,n,z):
    if n==0: return 0.0
    phat=p/n; d=1+z*z/n
    return (phat+z*z/(2*n)-z*math.sqrt(phat*(1-phat)/n+z*z/(4*n*n)))/d
def _gap_marker(self,question):
    model=self.reading_model; df,missing=model['question_df'],model.get('question_unmatched',{})
    markers=[t for t in set(question) if self._marker_ok(t)]
    if not markers: return '*'
    return max(markers,key=lambda t:(wilson(missing.get(t,0),df[t],Z['z']),df[t],t))
R.ReadingMemoryMixin._gap_marker=_gap_marker
