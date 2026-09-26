"""G-57: answering from a loaded text (interface, layout units, sections, calibration)."""
import tempfile
import unittest
from pathlib import Path

from leobot import Bot

TEXT = '''HOTEL DE PRUEBA
Dirección: Calle 1 # 2-3, Villa.

HORARIOS
Lunes a viernes: 8:00 a 18:00
Sábados: 9:00 a 13:00

Habitaciones
- Sencilla: $180.000 por noche.
- Doble: $250.000 por noche.

| Plan | Precio |
|---|---|
| Básico | 10 USD |

Preguntas frecuentes
¿Aceptan mascotas?
No se admiten mascotas.

Estamos en Av. Central 12. Abrimos a las 9. Sábados ........ 8:30 a 13:30'''


def all_cells():
    return [f'{a},{b}' for a in range(5) for b in range(5)]


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        self.bot.load_context(TEXT, 'Si no sabes algo, di que llamen a recepción.')
        self.units = self.bot.context_units

    def test_title_is_not_a_unit_and_covers_every_unit(self):
        self.assertNotIn('HOTEL DE PRUEBA', [u['text'] for u in self.units])
        self.assertEqual(self.bot.context_title, ['de', 'hotel', 'prueba'])

    def test_headings_lists_and_table_rows(self):
        by_text = {u['text']: u for u in self.units}
        self.assertEqual(by_text['HORARIOS']['kind'], 'heading')
        self.assertEqual(by_text['Doble: $250.000 por noche.']['heading'], 'Habitaciones')
        self.assertEqual(by_text['Doble: $250.000 por noche.']['kind'], 'item')
        self.assertIn('Plan: Básico; Precio: 10 USD', by_text)
        self.assertEqual(by_text['No se admiten mascotas.']['heading'], '¿Aceptan mascotas?')

    def test_sentences_split_only_after_words_or_figures(self):
        texts = [u['text'] for u in self.units]
        self.assertIn('Estamos en Av. Central 12.', texts)
        self.assertIn('Abrimos a las 9.', texts)
        self.assertIn('Sábados ........ 8:30 a 13:30', texts)

    def test_instructions_are_kept_apart(self):
        self.assertEqual(len(self.bot.context_instructions), 1)
        self.assertNotIn('recepción', ' '.join(u['text'] for u in self.units))

    def test_figures_have_shapes(self):
        terms = self.bot.context_terms('$250.000 de 8:30 a 13:30, 20%')
        for shape in ('$', '9.9', '9:9', '9', '%'):
            self.assertIn(shape, terms)


class AnswerTests(unittest.TestCase):
    def setUp(self):
        self.bot = Bot()
        self.bot.context_model = {'delta': {'doble': 0.8, 'horarios': 0.3, 'mascotas': 0.8, 'gimnasio': 0.8},
                                  'rare_delta': 0.6, 'bridge': {'perro': 'mascotas:0.5'},
                                  'admitted': all_cells(), 'cells': {}}
        self.bot.load_context(TEXT)

    def test_answers_with_the_document_text(self):
        reply = self.bot.answer('¿Cuánto cuesta la doble?')
        self.assertEqual(reply['status'], 'answered')
        self.assertEqual(reply['text'], 'Doble: $250.000 por noche.')

    def test_a_heading_asks_for_its_section(self):
        reply = self.bot.answer('¿Cuáles son los horarios?')
        self.assertEqual(reply['text'], 'Horarios: Lunes a viernes: 8:00 a 18:00; Sábados: 9:00 a 13:00.')

    def test_counted_bridge_reaches_other_words(self):
        self.assertEqual(self.bot.answer('¿Puedo llevar mi perro?')['text'], 'No se admiten mascotas.')
        self.bot.bridge = False
        self.assertNotEqual(self.bot.answer('¿Puedo llevar mi perro?')['text'], 'No se admiten mascotas.')

    def test_a_greeting_is_returned_and_never_an_internal_message(self):
        self.assertEqual(self.bot.answer('Hola')['text'], 'Hola.')
        self.assertEqual(self.bot.answer('Hola')['status'], 'phatic')
        self.assertTrue(self.bot.answer('Hola, ¿cuánto cuesta la doble?')['text'].startswith('Hola. Doble'))

    def test_not_admitted_says_it_does_not_know_and_hands_the_candidate_apart(self):
        self.bot.context_model['admitted'] = []
        reply = self.bot.answer('¿Cuánto cuesta la doble?')
        self.assertEqual(reply['status'], 'unknown')
        self.assertTrue(reply['text'].startswith('No lo sé'))
        self.assertEqual(reply['candidate']['text'], 'Doble: $250.000 por noche.')

    def test_follow_up_uses_the_previous_question(self):
        self.bot.context_model['admitted'] = [c for c in all_cells() if c[0] == '0']
        history = [{'role': 'user', 'text': '¿Aceptan mascotas en las habitaciones?'},
                   {'role': 'assistant', 'text': 'No se admiten mascotas.'}]
        alone = self.bot.answer('¿Y en el gimnasio?')
        self.assertEqual(alone['status'], 'unknown')

    def test_restart_keeps_the_context(self):
        before = self.bot.answer('¿Cuánto cuesta la doble?')
        with tempfile.TemporaryDirectory() as tmp:
            self.bot.save(Path(tmp) / 'b.json')
            again = Bot.load(Path(tmp) / 'b.json')
        self.assertEqual(again.answer('¿Cuánto cuesta la doble?'), before)


class RespondTests(unittest.TestCase):
    def test_several_parts_never_reply_with_an_internal_message(self):
        reply = Bot().respond('Hola. ¿Qué hora es?')
        self.assertNotIn('Procesé', reply['text'])
        self.assertEqual(reply['total'], 2)


if __name__ == '__main__':
    unittest.main()
