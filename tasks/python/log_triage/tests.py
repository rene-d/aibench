import tempfile
import unittest
from pathlib import Path

from solution import triage

DATA = Path(__file__).resolve().parent / "data" / "app.log"


def journal(texte):
    """Écrit un journal temporaire et renvoie son chemin."""
    p = Path(tempfile.mkdtemp()) / "app.log"
    p.write_text(texte, encoding="utf-8")
    return str(p)


class TestFichierFourni(unittest.TestCase):
    """Le journal livré avec la tâche, celui que le modèle peut inspecter."""

    @classmethod
    def setUpClass(cls):
        cls.r = triage(str(DATA))

    def test_resultat_complet(self):
        self.assertEqual(self.r, [
            {"signature": "db: timeout after Ns (conn=N)", "n": 4,
             "first": "2026-01-04T08:12:03Z", "last": "2026-01-04T08:26:30Z",
             "traceback": True},
            {"signature": "auth: invalid token for user N", "n": 2,
             "first": "2026-01-04T08:09:00Z", "last": "2026-01-04T08:10:00Z",
             "traceback": False},
            {"signature": "oom: killed worker N", "n": 2,
             "first": "2026-01-04T08:20:02Z", "last": "2026-01-04T08:21:00Z",
             "traceback": True},
            {"signature": "http: N from upstream backend-N", "n": 1,
             "first": "2026-01-04T08:25:00Z", "last": "2026-01-04T08:25:00Z",
             "traceback": False},
        ])

    def test_entete_du_fichier_ignoree(self):
        self.assertNotIn("demarrage, pid N", [g["signature"] for g in self.r])


class TestHorodatages(unittest.TestCase):
    def test_tous_les_formats(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR x 1\n"
            "2026-03-01 00:00:02 ERROR x 2\n"
            "2026-03-01 00:00:03,999 ERROR x 3\n"
            "01/03/2026 00:00:04 ERROR x 4\n"
        ))
        self.assertEqual(len(r), 1)
        self.assertEqual((r[0]["n"], r[0]["first"], r[0]["last"]),
                         (4, "2026-03-01T00:00:01Z", "2026-03-01T00:00:04Z"))

    def test_horodatage_epoch(self):
        r = triage(journal("[1767514500] ERROR demarrage rate\n"))
        self.assertEqual(r[0]["first"], "2026-01-04T08:15:00Z")

    def test_ordre_chronologique_pas_ordre_des_lignes(self):
        r = triage(journal(
            "2026-03-01T12:00:00Z ERROR boom 1\n"
            "2026-03-01T09:00:00Z ERROR boom 2\n"
            "2026-03-01T23:00:00Z ERROR boom 3\n"
            "2026-03-01T10:00:00Z ERROR boom 4\n"
        ))
        self.assertEqual((r[0]["first"], r[0]["last"]),
                         ("2026-03-01T09:00:00Z", "2026-03-01T23:00:00Z"))


class TestNiveaux(unittest.TestCase):
    def test_casse_et_crochets(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR boom 1\n"
            "2026-03-01T00:00:02Z error boom 2\n"
            "2026-03-01T00:00:03Z [Error] boom 3\n"
            "2026-03-01T00:00:04Z FATAL boom 4\n"
            "2026-03-01T00:00:05Z [fatal] boom 5\n"
        ))
        self.assertEqual(r[0]["n"], 5)

    def test_niveaux_non_erreur_exclus(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z WARN boom 1\n"
            "2026-03-01T00:00:02Z WARNING boom 2\n"
            "2026-03-01T00:00:03Z INFO boom 3\n"
            "2026-03-01T00:00:04Z DEBUG boom 4\n"
            "2026-03-01T00:00:05Z TRACE boom 5\n"
        ))
        self.assertEqual(r, [])

    def test_niveau_inconnu_abandonne_avec_ses_suites(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR boom 1\n"
            "2026-03-01T00:00:02Z bidule autre chose\n"
            "  ceci suit une entree abandonnee\n"
        ))
        self.assertEqual(len(r), 1)
        self.assertFalse(r[0]["traceback"])

    def test_message_vide_abandonne(self):
        self.assertEqual(triage(journal("2026-03-01T00:00:01Z ERROR:\n")), [])


class TestSuites(unittest.TestCase):
    def test_lignes_de_suite_rattachees(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR db: timeout after 30s\n"
            "Traceback (most recent call last):\n"
            "  File \"pool.py\", line 88, in acquire\n"
            "2026-03-01T00:00:02Z ERROR db: timeout after 5s\n"
        ))
        self.assertEqual((len(r), r[0]["n"], r[0]["traceback"]), (1, 2, True))

    def test_traceback_faux_sans_suite(self):
        r = triage(journal("2026-03-01T00:00:01Z ERROR db: timeout after 30s\n\n\n"))
        self.assertFalse(r[0]["traceback"])

    def test_preambule_ignore(self):
        r = triage(journal(
            "== rotation ==\n"
            "demarrage, pid 213\n"
            "2026-03-01T00:00:01Z ERROR boom 1\n"
        ))
        self.assertEqual(len(r), 1)
        self.assertFalse(r[0]["traceback"])


class TestGroupement(unittest.TestCase):
    def test_signature_normalise_les_chiffres(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR conn 17 lost after 30s\n"
            "2026-03-01T00:00:02Z ERROR conn 4321 lost after 5s\n"
        ))
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0]["signature"], "conn N lost after Ns")

    def test_tri_par_occurrences_puis_alphabetique(self):
        r = triage(journal(
            "2026-03-01T00:00:01Z ERROR zebre\n"
            "2026-03-01T00:00:02Z ERROR alpha\n"
            "2026-03-01T00:00:03Z ERROR beta\n"
            "2026-03-01T00:00:04Z ERROR beta\n"
        ))
        self.assertEqual([(g["signature"], g["n"]) for g in r],
                         [("beta", 2), ("alpha", 1), ("zebre", 1)])

    def test_journal_vide(self):
        self.assertEqual(triage(journal("")), [])


if __name__ == "__main__":
    unittest.main()
