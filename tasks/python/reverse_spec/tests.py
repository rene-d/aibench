import json
import tempfile
import unittest
from pathlib import Path

from solution import rendu

DATA = Path(__file__).resolve().parent / "data"


def ventes(enregistrements):
    """Écrit un fichier de ventes temporaire et renvoie son chemin."""
    p = Path(tempfile.mkdtemp()) / "ventes.json"
    p.write_text(json.dumps(enregistrements, ensure_ascii=False), encoding="utf-8")
    return str(p)


class TestFichierFourni(unittest.TestCase):
    def test_reproduit_le_rapport_livre(self):
        attendu = (DATA / "rapport_attendu.txt").read_text(encoding="utf-8")
        self.assertEqual(rendu(str(DATA / "ventes.json")), attendu)


class TestRegles(unittest.TestCase):
    def test_cas_complet(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "Ile", "montant": 10},
            {"ref": "b", "region": " ile ", "montant": "5,50"},
            {"ref": "c", "region": "Jura", "montant": "1 000,00"},
            {"ref": "d", "region": "Jura", "montant": 1, "annule": True},
        ])), "region;commandes;total\nJURA;1;1000.00\nILE;2;15.50\nTOTAL;3;1015.50\n")

    def test_annulees_exclues(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "X", "montant": 5},
            {"ref": "b", "region": "X", "montant": 100, "annule": True},
        ])), "region;commandes;total\nX;1;5.00\nTOTAL;1;5.00\n")

    def test_annule_faux_compte(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "X", "montant": 5, "annule": False},
        ])), "region;commandes;total\nX;1;5.00\nTOTAL;1;5.00\n")

    def test_region_entierement_annulee_disparait(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "X", "montant": 5},
            {"ref": "b", "region": "Y", "montant": 9, "annule": True},
        ])), "region;commandes;total\nX;1;5.00\nTOTAL;1;5.00\n")

    def test_regions_fusionnees(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "Nord", "montant": 1},
            {"ref": "b", "region": "NORD", "montant": 1},
            {"ref": "c", "region": "  nord  ", "montant": 1},
        ])), "region;commandes;total\nNORD;3;3.00\nTOTAL;3;3.00\n")

    def test_tri_par_total_decroissant(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "Petit", "montant": 1},
            {"ref": "b", "region": "Gros", "montant": 1000},
            {"ref": "c", "region": "Moyen", "montant": 50},
        ])), "region;commandes;total\nGROS;1;1000.00\nMOYEN;1;50.00\nPETIT;1;1.00\n"
             "TOTAL;3;1051.00\n")

    def test_egalite_departagee_alphabetiquement(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "Beta", "montant": 50},
            {"ref": "b", "region": "Alpha", "montant": 50},
        ])), "region;commandes;total\nALPHA;1;50.00\nBETA;1;50.00\nTOTAL;2;100.00\n")

    def test_montants_textuels(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "X", "montant": "2 000,25"},
            {"ref": "b", "region": "X", "montant": "1 000,25"},
            {"ref": "c", "region": "X", "montant": "0,50"},
        ])), "region;commandes;total\nX;3;3001.00\nTOTAL;3;3001.00\n")

    def test_deux_decimales_toujours(self):
        self.assertEqual(rendu(ventes([
            {"ref": "a", "region": "X", "montant": 7},
        ])), "region;commandes;total\nX;1;7.00\nTOTAL;1;7.00\n")

    def test_saut_de_ligne_final(self):
        sortie = rendu(ventes([{"ref": "a", "region": "X", "montant": 1}]))
        self.assertTrue(sortie.endswith("\n"))
        self.assertFalse(sortie.endswith("\n\n"))


if __name__ == "__main__":
    unittest.main()
