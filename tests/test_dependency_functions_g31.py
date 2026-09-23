"""G-31: dependency functions are learned from annotated sentences by counting."""
import unittest

from leobot import Bot

TRAIN=[
    (['El','perro','come','carne','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3],
     ['det','nsubj','root','obj','punct']),
    (['La','niña','lee','libros','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3],
     ['det','nsubj','root','obj','punct']),
    (['Un','gato','bebe','leche','.'],['DET','NOUN','VERB','NOUN','PUNCT'],[2,3,0,3,3],
     ['det','nsubj','root','obj','punct']),
]


class DependencyFunctionTests(unittest.TestCase):
    def test_functions_absent_without_labelled_demonstrations(self):
        bot=Bot()
        for words,tags,heads,_ in TRAIN:
            bot.observe_parsed_sentence(words,tags,heads)
        self.assertNotIn('labels',bot.parse_words(['La','vaca','come','hierba','.']))

    def test_learned_functions_for_new_sentence(self):
        bot=Bot()
        for words,tags,heads,labels in TRAIN:
            bot.observe_parsed_sentence(words,tags,heads,labels)
        parsed=bot.parse_words(['La','vaca','come','hierba','.'])
        self.assertEqual(parsed['labels'],['det','nsubj','root','obj','punct'])


if __name__=='__main__':
    unittest.main()
