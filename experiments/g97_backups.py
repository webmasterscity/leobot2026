"""Manual fallback ONLY for the user's explicit G97 exception. Not learned."""
import re
import time
from experiments.g57_kiosco import plain

ABSTAINED = {'unknown', 'ambiguous', 'literal_unknown', 'unrecognized'}

# Explicit, inspectable semantic rules. These are not self-learning or business facts.
CATEGORIES = {
    'hours': (r'horario|horarios|hora|horas|abren|abre|abrir|abrimos|abierto|apertura|cierran|cierra|cierre|atienden|atencion',
              r'horario|horarios|abrimos|abierto|abierta|apertura|cerramos|cerrado|cerrada|cierre|atendemos|atencion'),
    'location': (r'donde|direccion|ubicacion|ubicados|quedan|localizacion|llegar',
                 r'direccion|ubicacion|ubicad[oa]s?|estamos en|nos encontramos en|nos encuentras en|queda en'),
    'contact': (r'contacto|contactar|telefono|telefonos|llamar|correo|email|whatsapp|pagina|web',
                r'contacto|telefono|telefonos|correo|email|whatsapp|pagina|web|llamanos'),
    'payment': (r'pago|pagos|pagar|tarjeta|tarjetas|efectivo|cheque|cheques|transferencia|cuotas',
                r'pago|pagos|pagar|tarjeta|tarjetas|efectivo|cheque|cheques|transferencia|cuotas'),
    'price': (r'precio|precios|cuesta|cuestan|costo|coste|vale|valor|tarifa|tarifas',
              r'precio|precios|cuesta|cuestan|costo|coste|vale|valor|tarifa|tarifas|euros|pesos|dolares'),
    'delivery': (r'envio|envios|entrega|entregas|entregan|domicilio|reparto|despacho',
                 r'envio|envios|entrega|entregas|entregan|domicilio|reparto|despacho'),
    'booking': (r'reserva|reservar|reservas|cita|citas|turno|turnos|agendar|anticipacion',
                r'reserva|reservar|reservas|cita|citas|turno|turnos|agendar|anticipacion'),
    'cancel': (r'cancelar|cancelacion|cancelaciones|anular', r'cancelar|cancelacion|cancelaciones|anular'),
    'returns': (r'devolver|devolucion|devoluciones|reembolso|cambiar|cambios',
                r'devolver|devolucion|devoluciones|reembolso|cambiar|cambios'),
    'warranty': (r'garantia|garantias', r'garantia|garantias'),
    'parking': (r'estacionamiento|aparcar|aparcamiento|parqueadero|parking',
                r'estacionamiento|aparcar|aparcamiento|parqueadero|parking'),
    'access': (r'accesibilidad|accesible|rampa|rampas|silla de ruedas|movilidad reducida',
               r'accesibilidad|accesible|rampa|rampas|silla de ruedas|movilidad reducida'),
    'pets': (r'mascota|mascotas|perro|perros|gato|gatos|animales',
             r'mascota|mascotas|perro|perros|gato|gatos|animales'),
    'age': (r'edad|edades|menores|adultos|ninos|ninas', r'edad|edades|menores|adultos|ninos|ninas'),
}
PATTERNS = {k: tuple(re.compile(r'\b(?:'+p+r')\b') for p in pair) for k,pair in CATEGORIES.items()}
STOP = ('a al de del desde en entre hacia hasta para por con sin y o un una unos unas el la los las '
        'que cual cuales como cuanto cuantos cuanta cuantas donde es son esta estan ser estar hay tienen '
        'tiene tener puedo puede podemos podria se su sus mi me ustedes usted yo nosotros necesito '
        'quiero saber favor porfavor hola buenos buenas dias tardes noches aceptan admiten venden ofrecen '
        'puedo conseguir comprar venden venden horario horarios hora horas abren abre abrir abrimos abierto '
        'apertura cierran cierra cierre atienden atencion direccion ubicacion ubicados quedan llegar '
        'contactar contacto llamar pago pagos pagar forma formas medio medios precio precios cuesta cuestan '
        'costo coste vale valor tarifa tarifas envio envios entrega entregas entregan domicilio reparto despacho '
        'reserva reservar reservas cita citas turno turnos agendar anticipacion cancelar cancelacion '
        'cancelaciones anular devolver devolucion devoluciones reembolso cambiar cambios garantia garantias '
        'estacionamiento aparcar aparcamiento parqueadero parking accesibilidad accesible rampa rampas '
        'mascota mascotas edad edades').split()


class ManualRules:
    def __init__(self, bot):
        self.bot = bot
        self.stop = set(bot.context_terms(' '.join(STOP)))

    def prepare(self):
        self.units = []
        for unit in self.bot.context_units:
            text = unit['text']+(' '+unit['heading'] if unit.get('inherited') else '')
            normalized = plain(text)
            cats = {k for k,(_,pattern) in PATTERNS.items() if pattern.search(normalized)}
            self.units.append((set(self.bot.context_terms(text)), cats, normalized))

    def propose(self, question, history):
        normalized = plain(question)
        cats = {k for k,(pattern,_) in PATTERNS.items() if pattern.search(normalized)}
        if len(cats) > 1:
            cats -= {'hours', 'location', 'price'}
        if len(cats) > 1:
            return None
        specific = set(self.bot.context_terms(question))-self.stop
        # With a learned tagger, only nouns, names, numbers and modifiers anchor facts.
        if self.bot.syntax_model.get('sentences'):
            words = self.bot.split_words(question)
            tagged = {self.bot._term(w) for w,t in zip(words,self.bot.tag_words(words))
                      if t in ('NOUN','PROPN','NUM','ADJ')}
            specific &= tagged
        if not cats and not specific:
            return None
        possibilities = []
        for i, (terms, ucats, text) in enumerate(self.units):
            unit = self.bot.context_units[i]
            if unit.get('kind') in ('heading','question') or not specific <= terms:
                continue
            if cats and not cats <= ucats:
                continue
            if cats == {'hours'} and 'delivery' in ucats:
                continue
            # A labelled field is stronger evidence than a generic mention elsewhere.
            label = plain(unit['text'].split(':',1)[0]) if ':' in unit['text'] else ''
            labelled = int(any(PATTERNS[k][1].fullmatch(label) for k in cats))
            score = (labelled, len(specific & terms))
            possibilities.append((score,i))
        possibilities.sort(reverse=True)
        if not possibilities or (len(possibilities)>1 and possibilities[0][0]==possibilities[1][0]):
            return None
        return {'index':possibilities[0][1], 'confidence':None, 'rule_categories':sorted(cats)}


class BackupBot:
    def __init__(self, bot, route, name):
        self.bot, self.route, self.name, self.enabled = bot, route, name, True
        self.activated_ms = []
        self.route.prepare()

    def __getattr__(self, name):
        return getattr(self.bot,name)

    def load_context(self, text, instructions=''):
        result = self.bot.load_context(text,instructions)
        self.route.prepare()
        return result

    def answer(self, question, history=None):
        started = time.perf_counter()
        original = self.bot.answer(question,history)
        if not self.enabled or original.get('status') not in ABSTAINED:
            return original
        choice = self.route.propose(question,history or [])
        result = original
        if choice is not None and 0 <= choice['index'] < len(self.bot.context_units):
            i = choice['index']; unit = self.bot.context_units[i]
            result = {'status':'closest', 'text':f'Encontré este fragmento: «{unit["text"]}».',
                      'evidence':{'unit':unit['text'],'heading':unit.get('heading',''),'index':i},
                      'confidence':choice.get('confidence'),'backup':self.name}
        self.activated_ms.append(1000*(time.perf_counter()-started))
        return result
