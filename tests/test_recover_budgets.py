"""recover's read budgets on large transcripts."""
import json
import os
import signal
import subprocess
import sys
import unittest.mock

from helpers import CWD, CrewCase, MB, ROOT

import config
import recover
import registry

CREW = os.path.join(ROOT, "scripts", "crew.py")



def msg(kind, text):
    return {"type": kind, "message": {"content": text}}


class RecoverBudgets(CrewCase):
    def ident(self):
        return registry.Identity("alpha", "mine0000", CWD)

    def test_summary_survives_a_huge_tail(self):
        summary = "BEGIN" + "s" * 30000 + "END"
        lines = [{"type": "custom-title", "customTitle": "alpha"},
                 dict(msg("user", summary), isCompactSummary=True)]
        lines += [msg("user" if i % 2 else "assistant", "t%d " % i + "x" * 1000)
                  for i in range(150)]
        self.transcript("old00000", lines=lines)
        with unittest.mock.patch.object(recover, "CHUNK", 4096):
            _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn(summary, raw)
        self.assertIn("t149 ", raw)
        self.assertNotIn("t0 ", raw)

    def test_summary_is_cut_at_40k(self):
        lines = [{"type": "custom-title", "customTitle": "alpha"},
                 dict(msg("user", "s" * 50000), isCompactSummary=True)]
        self.transcript("old00000", lines=lines)
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("s" * recover.TOTAL_CUT, raw)
        self.assertNotIn("s" * (recover.TOTAL_CUT + 1), raw)

    def test_one_budget_for_the_whole_run(self):
        for i in range(5):
            lines = [{"type": "custom-title", "customTitle": "other"}]
            lines += [msg("user", "p" * 1000)] * 1000  # about 1 MB after the title
            path = self.transcript("c000000%d" % i, lines=lines)
            os.utime(path, (10 + i, 10 + i))
        made = []

        class Counting(recover.Budget):
            def __init__(self, left):
                super().__init__(left)
                self.total, self.spent = left, 0
                made.append(self)

            def spend(self, n):
                self.spent += n
                super().spend(n)

        with unittest.mock.patch.object(recover, "Budget", Counting), \
                unittest.mock.patch.object(recover, "MAX_READ", 2 * MB), \
                unittest.mock.patch.object(recover, "MAX_TITLE", 10 * MB), \
                unittest.mock.patch.object(recover, "CHUNK", 64 * 1024):
            self.call(recover.run, self.ident(), "alpha")
        self.assertEqual(len(made), 1)
        self.assertLessEqual(made[0].spent, 2 * MB)
        self.assertGreater(made[0].spent, MB)

    def test_title_scan_is_capped_per_candidate(self):
        lines = [{"type": "custom-title", "customTitle": "alpha"}] + [msg("user", "p" * 1000)] * 500
        path = self.transcript("old00000", lines=lines)
        with unittest.mock.patch.object(recover, "MAX_TITLE", 100 * 1024):
            self.assertIsNone(recover.last_title(path, recover.Budget(10 * MB)))

    def test_overlong_line_is_dropped(self):
        path = os.path.join(self.tmp, "f")
        lines = ["a%d" % i for i in range(50)] + ["B" * 10000] + ["c%d" % i for i in range(50)]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        with unittest.mock.patch.object(recover, "MAX_LINE", 500):
            for chunk in (64, 300, 5000):
                got = [x.decode() for x in recover.reverse_lines(path, recover.Budget(10**9),
                                                                 chunk=chunk)]
                self.assertEqual(got, [l for l in lines if l[0] != "B"][::-1], chunk)


