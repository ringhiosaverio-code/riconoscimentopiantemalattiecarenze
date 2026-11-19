"""PlantCare: riconoscimento visivo di piante agrarie, malattie, insetti utili/dannosi e carenze."""

from plantcare.taxonomy import Taxonomy, TaxonomyError, load_taxonomy

__all__ = ["Taxonomy", "TaxonomyError", "load_taxonomy"]
__version__ = "0.2.0"
