import json
import tempfile
import unittest
from pathlib import Path

from solution import report

DATA = Path(__file__).resolve().parent / "data" / "commandes.json"

BASE = {"client": "a", "categorie": "x", "montant": 1, "devise": "EUR", "date": "2026-05-01"}


def ecrire(enregistrements):
    """Écrit un jeu de données temporaire et renvoie son chemin."""
    d = tempfile.mkdtemp()
    p = Path(d) / "jeu.json"
    p.write_text(json.dumps(enregistrements, ensure_ascii=False), encoding="utf-8")
    return str(p)


def lot(champs):
    """Un enregistrement par entrée, complété par BASE, avec des id distincts."""
    return [dict(BASE, id=i, **c) for i, c in enumerate(champs, start=1)]


class TestFichierFourni(unittest.TestCase):
    """Le jeu de données livré avec la tâche, celui que le modèle peut inspecter."""

    @classmethod
    def setUpClass(cls):
        cls.r = report(str(DATA))

    def test_compteurs(self):
        self.assertEqual(self.r["n_commandes"], 16)
        self.assertEqual(self.r["n_ignorees"], 11)
        self.assertEqual(self.r["n_doublons"], 2)

    def test_par_client(self):
        self.assertEqual(self.r["par_client"], {
            "acme": {"n": 4, "total": 1263.1},
            "globex": {"n": 4, "total": 3249.0},
            "hooli": {"n": 3, "total": 1318.4},
            "initech": {"n": 2, "total": 32.5},
            "umbrella": {"n": 3, "total": -15.5},
        })

    def test_par_mois(self):
        self.assertEqual(self.r["par_mois"], {
            "2025-12": {"n": 3, "total": 2020.9},
            "2026-01": {"n": 4, "total": 1259.1},
            "2026-02": {"n": 3, "total": 1330.0},
            "2026-03": {"n": 6, "total": 1237.5},
        })

    def test_top_categories(self):
        self.assertEqual(self.r["top_categories"], [("pro", 9), ("cloud", 4), ("particulier", 2)])

    def test_top_categories_sont_des_tuples(self):
        self.assertTrue(all(isinstance(e, tuple) for e in self.r["top_categories"]))


class TestMontants(unittest.TestCase):
    def test_toutes_les_ecritures(self):
        r = report(ecrire(lot([
            {"montant": 10},
            {"montant": "10.5"},
            {"montant": "10,5"},
            {"montant": "1 000,25"},
            {"montant": "1 000,25"},  # espace insécable, comme dans le fichier fourni
            {"montant": -0.75},
            {"montant": 0},
        ])))
        self.assertEqual(r["n_commandes"], 7)
        self.assertEqual(r["par_client"], {"a": {"n": 7, "total": 2030.75}})

    def test_montants_invalides_ignores(self):
        r = report(ecrire(lot([
            {"montant": "N/A"}, {"montant": None}, {"montant": ""}, {"montant": "  "},
            {"montant": 1},
        ])))
        self.assertEqual((r["n_commandes"], r["n_ignorees"]), (1, 4))

    def test_arrondi_sur_la_somme_seulement(self):
        r = report(ecrire(lot([{"montant": 1.005}, {"montant": 1.005}])))
        self.assertEqual(r["par_client"]["a"]["total"], 2.01)


class TestDevises(unittest.TestCase):
    def test_euro_sous_toutes_ses_formes(self):
        enregistrements = lot([
            {"devise": "EUR"}, {"devise": "eur"}, {"devise": " Eur "}, {"devise": "€"},
            {"devise": "USD"}, {"devise": "GBP"},
        ])
        del enregistrements[0]["devise"]  # devise absente : vaut euro
        r = report(ecrire(enregistrements))
        self.assertEqual((r["n_commandes"], r["n_ignorees"]), (4, 2))

    def test_devise_absente_vaut_euro(self):
        e = lot([{}])
        del e[0]["devise"]
        self.assertEqual(report(ecrire(e))["n_commandes"], 1)


class TestDates(unittest.TestCase):
    def test_formats_reconnus_et_regroupes(self):
        r = report(ecrire(lot([
            {"date": "2026-01-04"},
            {"date": "04/01/2026"},
            {"date": "2026-01-04T08:12:03Z"},
        ])))
        self.assertEqual(r["par_mois"], {"2026-01": {"n": 3, "total": 3.0}})

    def test_dates_illisibles(self):
        r = report(ecrire(lot([
            {"date": "2026-02-30"}, {"date": "31/02/2026"}, {"date": ""},
            {"date": None}, {"date": "janvier 2026"},
        ])))
        self.assertEqual((r["n_commandes"], r["n_ignorees"]), (0, 5))
        self.assertEqual(r["par_mois"], {})


class TestNormalisation(unittest.TestCase):
    def test_clients_fusionnes(self):
        r = report(ecrire(lot([
            {"client": "ACME"}, {"client": " acme "}, {"client": "Acme"},
        ])))
        self.assertEqual(r["par_client"], {"acme": {"n": 3, "total": 3.0}})

    def test_clients_vides_ignores(self):
        r = report(ecrire(lot([{"client": ""}, {"client": "   "}, {"client": None}])))
        self.assertEqual((r["n_commandes"], r["n_ignorees"]), (0, 3))

    def test_id_manquant_ignore(self):
        e = lot([{}, {}])
        del e[0]["id"]
        e[1]["id"] = None
        self.assertEqual(report(ecrire(e))["n_ignorees"], 2)

    def test_categorie_inconnue(self):
        e = lot([{"categorie": ""}, {"categorie": "  "}, {"categorie": None}, {"categorie": " Pro "}])
        del e[0]["categorie"]
        r = report(ecrire(e))
        self.assertEqual(r["top_categories"], [("inconnue", 3), ("pro", 1)])


class TestDeduplication(unittest.TestCase):
    def test_premier_retenu(self):
        e = lot([{"montant": 10}, {"montant": 99}, {"montant": 99}])
        for rec in e:
            rec["id"] = 7
        r = report(ecrire(e))
        self.assertEqual((r["n_commandes"], r["n_doublons"], r["n_ignorees"]), (1, 2, 0))
        self.assertEqual(r["par_client"], {"a": {"n": 1, "total": 10.0}})

    def test_un_invalide_ne_reserve_pas_son_id(self):
        e = lot([{"montant": "N/A"}, {"montant": 10}])
        for rec in e:
            rec["id"] = 7
        r = report(ecrire(e))
        self.assertEqual((r["n_commandes"], r["n_ignorees"], r["n_doublons"]), (1, 1, 0))


class TestAgregats(unittest.TestCase):
    def test_top_trois_avec_egalite(self):
        e = lot([{"categorie": c} for c in
                 ["pro"] * 4 + ["cloud"] * 3 + ["particulier"] * 2 + ["autre"] * 2 + ["zzz"]])
        self.assertEqual(report(ecrire(e))["top_categories"],
                         [("pro", 4), ("cloud", 3), ("autre", 2)])

    def test_fichier_vide(self):
        r = report(ecrire([]))
        self.assertEqual(r, {"n_commandes": 0, "n_ignorees": 0, "n_doublons": 0,
                             "par_client": {}, "par_mois": {}, "top_categories": []})


if __name__ == "__main__":
    unittest.main()
