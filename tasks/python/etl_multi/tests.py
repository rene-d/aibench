import unittest

from agrege import agrege
from solution import rapport

LIGNES = [
    "2026-02-03T10:15:00Z|api|INFO|120|ok",
    "2026-02-03T10:15:01Z|api|ERROR|300|boum",
    "2026-02-03T10:15:02Z|db|INFO|40|ok",
    "# commentaire",
]


def enreg(service, niveau="INFO", duree=10):
    return {"date": "2026-02-03", "service": service, "niveau": niveau,
            "duree_ms": duree, "message": "m"}


class TestAgrege(unittest.TestCase):
    def test_vide(self):
        self.assertEqual(agrege([]), {})

    def test_un_service(self):
        self.assertEqual(agrege([enreg("api", "INFO", 10)]),
                         {"api": {"total": 1, "erreurs": 0,
                                  "duree_totale": 10, "duree_max": 10}})

    def test_compte_les_erreurs(self):
        got = agrege([enreg("api", "ERROR", 5), enreg("api", "WARN", 7),
                      enreg("api", "ERROR", 9)])
        self.assertEqual(got["api"]["erreurs"], 2)
        self.assertEqual(got["api"]["total"], 3)

    def test_warn_et_debug_ne_sont_pas_des_erreurs(self):
        got = agrege([enreg("api", "WARN", 1), enreg("api", "DEBUG", 1)])
        self.assertEqual(got["api"]["erreurs"], 0)

    def test_somme_et_max(self):
        got = agrege([enreg("db", "INFO", 40), enreg("db", "INFO", 200),
                      enreg("db", "INFO", 60)])
        self.assertEqual(got["db"]["duree_totale"], 300)
        self.assertEqual(got["db"]["duree_max"], 200)

    def test_services_separes(self):
        got = agrege([enreg("api", "INFO", 1), enreg("db", "ERROR", 2)])
        self.assertEqual(sorted(got), ["api", "db"])
        self.assertEqual(got["db"]["erreurs"], 1)
        self.assertEqual(got["api"]["erreurs"], 0)

    def test_ne_modifie_pas_l_entree(self):
        entree = [enreg("api", "INFO", 3)]
        copie = [dict(e) for e in entree]
        agrege(entree)
        self.assertEqual(entree, copie)


class TestRapport(unittest.TestCase):
    def test_exemple_de_l_enonce(self):
        self.assertEqual(
            rapport(LIGNES),
            "api : 2 lignes, 1 erreurs, 210 ms en moyenne, max 300 ms\n"
            "db : 1 lignes, 0 erreurs, 40 ms en moyenne, max 40 ms")

    def test_entree_vide(self):
        self.assertEqual(rapport([]), "")

    def test_que_des_lignes_invalides(self):
        self.assertEqual(rapport(["", "   ", "# x", "a|b", "2026-01-01T0Z|s|NOPE|1|m",
                                  "2026-01-01T0Z|s|INFO|-1|m"]), "")

    def test_moyenne_est_une_division_entiere(self):
        lignes = ["2026-01-01T00:00:00Z|s|INFO|10|m", "2026-01-01T00:00:00Z|s|INFO|11|m"]
        self.assertEqual(rapport(lignes),
                         "s : 2 lignes, 0 erreurs, 10 ms en moyenne, max 11 ms")

    def test_tri_erreurs_puis_nom(self):
        lignes = [
            "2026-01-01T00:00:00Z|zeta|INFO|1|m",
            "2026-01-01T00:00:00Z|alpha|INFO|1|m",
            "2026-01-01T00:00:00Z|beta|ERROR|1|m",
        ]
        noms = [l.split(" :")[0] for l in rapport(lignes).splitlines()]
        self.assertEqual(noms, ["beta", "alpha", "zeta"])

    def test_pas_de_saut_de_ligne_final(self):
        self.assertFalse(rapport(LIGNES).endswith("\n"))

    def test_utilise_le_module_agrege(self):
        # `rapport` doit passer par agrege.agrege, pas réimplémenter l'agrégation
        import agrege as module_agrege
        appels = []
        vrai = module_agrege.agrege

        def espion(enregs):
            appels.append(len(enregs))
            return vrai(enregs)

        module_agrege.agrege = espion
        try:
            import solution
            if getattr(solution, "agrege", None) is vrai:
                solution.agrege = espion
            rapport(LIGNES)
        finally:
            module_agrege.agrege = vrai
        self.assertEqual(appels, [3])
