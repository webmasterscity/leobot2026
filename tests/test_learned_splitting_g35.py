"""G-35: contractions and attached pronouns are split as learned from demonstrations."""
import unittest

from leobot import Bot


class LearnedSplittingTests(unittest.TestCase):
    def test_seen_forms_and_ending_rules(self):
        bot=Bot()
        bot.observe_parsed_sentence(['Vino','de','el','mercado','.'],['VERB','ADP','DET','NOUN','PUNCT'],[0,4,4,1,1])
        for verb in ('comprar','vender','hacer','traer','cambiar'):
            bot.observe_parsed_sentence([verb,'lo'],['VERB','PRON'],[0,1])
        for _ in range(2):
            bot.observe_multiword('del',['de','el'])
        for verb in ('comprar','vender','hacer'):
            bot.observe_multiword(verb+'lo',[verb,'lo'])
        self.assertEqual(bot.split_words('Vino del mercado'),['Vino','de','el','mercado'])
        self.assertEqual(bot.split_words('traerlo'),['traer','lo'])
        self.assertEqual(bot.split_words('pelo'),['pelo'])


if __name__=='__main__':
    unittest.main()
