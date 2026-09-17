import unittest

from solution import arrondi, cle_tri, fusion


class TestArrondi(unittest.TestCase):
    def test_milieux_sortent_de_zero(self):
        self.assertEqual(arrondi(2.5), 3.0)
        self.assertEqual(arrondi(3.5), 4.0)
        self.assertEqual(arrondi(-2.5), -3.0)
        self.assertEqual(arrondi(-3.5), -4.0)

    def test_milieux_avec_decimales(self):
        self.assertEqual(arrondi(0.125, 2), 0.13)
        self.assertEqual(arrondi(-0.125, 2), -0.13)
        self.assertEqual(arrondi(1.0625, 3), 1.063)

    def test_cas_ordinaires(self):
        self.assertEqual(arrondi(2.4), 2.0)
        self.assertEqual(arrondi(2.6), 3.0)
        self.assertEqual(arrondi(-2.4), -2.0)
        self.assertEqual(arrondi(0.0), 0.0)

    def test_n_par_defaut_vaut_zero(self):
        self.assertEqual(arrondi(7.5), arrondi(7.5, 0))

    def test_entiers_inchanges(self):
        self.assertEqual(arrondi(4.0), 4.0)
        self.assertEqual(arrondi(4.0, 3), 4.0)

    def test_rend_un_flottant(self):
        self.assertIsInstance(arrondi(2.5), float)

    def test_differe_de_round(self):
        # la règle du contrat n'est pas celle de round() : c'est tout l'enjeu
        self.assertNotEqual(arrondi(2.5), round(2.5))
        self.assertNotEqual(arrondi(0.125, 2), round(0.125, 2))


class TestFusion(unittest.TestCase):
    def test_none_conserve_la_valeur_de_base(self):
        self.assertEqual(fusion({"a": 1, "b": 2}, {"b": None}), {"a": 1, "b": 2})

    def test_none_sur_cle_inconnue_est_ignore(self):
        self.assertEqual(fusion({"a": 1}, {"c": None}), {"a": 1})

    def test_ecrase_les_autres_valeurs(self):
        self.assertEqual(fusion({"a": 1}, {"a": 9, "b": 0}), {"a": 9, "b": 0})

    def test_zero_et_chaine_vide_ecrasent(self):
        self.assertEqual(fusion({"a": 1, "b": "x"}, {"a": 0, "b": ""}), {"a": 0, "b": ""})

    def test_patch_vide(self):
        self.assertEqual(fusion({"a": 1}, {}), {"a": 1})

    def test_base_vide(self):
        self.assertEqual(fusion({}, {"a": 1, "b": None}), {"a": 1})

    def test_ne_modifie_pas_les_entrees(self):
        base, patch = {"a": 1}, {"a": 2, "b": None}
        fusion(base, patch)
        self.assertEqual(base, {"a": 1})
        self.assertEqual(patch, {"a": 2, "b": None})

    def test_rend_un_nouveau_dictionnaire(self):
        base = {"a": 1}
        self.assertIsNot(fusion(base, {}), base)


class TestCleTri(unittest.TestCase):
    def test_plie_accents_espaces_et_casse(self):
        self.assertEqual(cle_tri("  Émile   Zola "), ("emile zola", "  Émile   Zola "))

    def test_garde_le_nom_d_origine(self):
        self.assertEqual(cle_tri("Ana")[1], "Ana")

    def test_accents_varies(self):
        self.assertEqual(cle_tri("Çà et là")[0], "ca et la")
        self.assertEqual(cle_tri("ÜBER")[0], "uber")

    def test_sans_accent_ni_espace(self):
        self.assertEqual(cle_tri("ana"), ("ana", "ana"))

    def test_chaine_vide(self):
        self.assertEqual(cle_tri(""), ("", ""))

    def test_tri_deterministe(self):
        noms = ["Zoé", "emile", "  Ana  Lu ", "Émile"]
        plies = [cle_tri(n)[0] for n in sorted(noms, key=cle_tri)]
        self.assertEqual(plies, ["ana lu", "emile", "emile", "zoe"])

    def test_departage_par_le_nom_d_origine(self):
        self.assertNotEqual(cle_tri("Émile"), cle_tri("emile"))
        self.assertEqual(cle_tri("Émile")[0], cle_tri("emile")[0])
