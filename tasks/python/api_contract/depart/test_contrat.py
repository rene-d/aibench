"""Test fourni avec l'énoncé. Il fait partie du contrat : ne le modifie pas.

Oui, `arrondi(2.5) == 3.0` alors que `round(2.5) == 2`. C'est voulu : relis
l'énoncé, l'arrondi demandé s'éloigne de zéro sur les milieux exacts.
"""
import unittest

from solution import arrondi, cle_tri, fusion


class TestContrat(unittest.TestCase):
    def test_arrondi_milieu_sort_de_zero(self):
        self.assertEqual(arrondi(2.5), 3.0)
        self.assertEqual(arrondi(-2.5), -3.0)
        self.assertEqual(arrondi(0.5), 1.0)

    def test_arrondi_avec_decimales(self):
        self.assertEqual(arrondi(0.125, 2), 0.13)
        self.assertEqual(arrondi(1.0625, 3), 1.063)

    def test_fusion_none_ne_touche_pas(self):
        self.assertEqual(fusion({"a": 1, "b": 2}, {"b": None}), {"a": 1, "b": 2})
        self.assertEqual(fusion({"a": 1}, {"c": None}), {"a": 1})

    def test_fusion_ecrase_le_reste(self):
        self.assertEqual(fusion({"a": 1}, {"a": 9, "b": 0}), {"a": 9, "b": 0})

    def test_cle_tri_plie_accents_et_espaces(self):
        self.assertEqual(cle_tri("  Émile   Zola "), ("emile zola", "  Émile   Zola "))


if __name__ == "__main__":
    unittest.main()
