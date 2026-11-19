"""PlantCare: riconoscimento visivo di piante, malattie, insetti e carenze nutrizionali."""

from plantcare.taxonomy import Taxonomy, TaxonomyError, load_taxonomy

__all__ = ["Taxonomy", "TaxonomyError", "load_taxonomy"]
__version__ = "0.1.0"
