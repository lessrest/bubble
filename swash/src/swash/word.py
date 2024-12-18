"""
Module for looking up words in WordNet and representing them as RDF.
Uses the wn library to access WordNet data.
"""

from typing import Optional, Generator

import structlog

from wn import Lexicon, Wordnet
from rdflib import RDFS, VOID, URIRef, Literal, Namespace

from swash.prfx import SWA
from swash.util import add, new

logger = structlog.get_logger(__name__)

# Define WordNet namespace based on W3C spec
WN = Namespace("http://www.w3.org/2006/03/wn/wn20/schema/")


def describe_lexicon(lexicon: Lexicon) -> Optional[URIRef]:
    return new(
        VOID.Dataset, {}, SWA[f"lexicon/{lexicon.id}:{lexicon.version}"]
    )


def text(s: str | None) -> Literal | None:
    return Literal(s, lang="en") if s else None


def describe_word(
    word: str, pos: Optional[str] = None
) -> Generator[URIRef, None, None]:
    """
    Look up a word in WordNet and describe it as RDF.
    Yields URIs for all matching word resources.

    Args:
        word: The word to look up
        pos: Optional part of speech filter ('n', 'v', 'a', 'r')

    Yields:
        URIRef: URI for each matching word resource
    """
    logger.info("looking up word in WordNet", word=word, pos=pos)
    en = Wordnet(lang="en")  # English WordNet

    # Look up the word
    words = en.words(word, pos=pos)
    if not words:
        logger.info("word not found in WordNet", word=word, pos=pos)
        return

    for word_obj in words:
        logger.info(
            "processing word", word=word, id=word_obj.id, pos=word_obj.pos
        )

        lexicon = word_obj.lexicon()
        lexicon_node = describe_lexicon(lexicon)
        logger.debug("described lexicon", lexicon_id=lexicon.id)

        # Create word resource
        word_node = new(
            WN.Word,
            {
                WN.lemma: text(word_obj.lemma()),
                WN.partOfSpeech: WN[word_obj.pos],
                VOID.inDataset: lexicon_node,
                RDFS.label: text(
                    word_obj.lemma() + " (" + word_obj.pos + ")"
                ),
            },
            subject=SWA[f"word/{word_obj.id}"],
        )
        logger.debug("created word resource", word_id=word_obj.id)

        # Add word forms
        forms = word_obj.forms()
        logger.debug("adding word forms", count=len(forms))
        for form in forms:
            add(word_node, {WN.form: text(form)})

        # Add senses
        senses = word_obj.senses()
        logger.debug("processing word senses", count=len(senses))
        for sense in senses:
            sense_node = new(
                WN.WordSense,
                {},
                subject=SWA[f"word/{sense.id}"],
            )
            add(word_node, {WN.sense: sense_node})
            logger.debug("created sense node", sense_id=sense.id)

            # Get synset for this sense
            synset = sense.synset()
            logger.debug("processing synset", synset_id=synset.id)

            # Add definition if available
            synset_def = synset.definition()
            if synset_def:
                add(sense_node, {WN.gloss: text(synset_def)})
                logger.debug("added definition")

            # Add examples
            examples = synset.examples()
            logger.debug("adding examples", count=len(examples))
            for example_text in examples:
                add(sense_node, {WN.example: text(example_text)})

            # Add synonyms from synset
            lemmas = synset.lemmas()
            logger.debug("adding synonyms", count=len(lemmas))
            for lemma in lemmas:
                if lemma != word_obj.lemma():
                    add(sense_node, {WN.synonym: text(lemma)})

            # Add hypernyms
            hypernyms = synset.hypernyms()
            logger.debug("adding hypernyms", count=len(hypernyms))
            for hypernym in hypernyms:
                hypernym_node = new(
                    WN.Synset,
                    {
                        WN.lemma: text(hypernym.lemmas()[0]),
                        WN.gloss: text(hypernym.definition())
                        if hypernym.definition()
                        else None,
                    },
                    subject=SWA[f"word/{hypernym.id}"],
                )
                add(sense_node, {WN.hypernym: hypernym_node})

            # Add hyponyms
            hyponyms = synset.hyponyms()
            logger.debug("adding hyponyms", count=len(hyponyms))
            for hyponym in hyponyms:
                hyponym_node = new(
                    WN.Synset,
                    {
                        WN.lemma: text(hyponym.lemmas()[0]),
                        WN.gloss: text(hyponym.definition())
                        if hyponym.definition()
                        else None,
                    },
                    subject=SWA[f"word/{hyponym.id}"],
                )
                add(sense_node, {WN.hyponym: hyponym_node})

        logger.info(
            "completed word description", word=word, word_id=word_obj.id
        )
        yield word_node
