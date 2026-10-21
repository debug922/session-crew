import os
import unittest.mock

from helpers import CWD, CrewCase

import recover
import registry


def user(text, **kw):
    return dict({"type": "user", "message": {"role": "user", "content": text}}, **kw)


def assistant(text):
    return {"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": text}, {"type": "tool_use", "name": "Bash", "input": {}}]}}


def title(name):
    return {"type": "custom-title", "customTitle": name, "sessionId": "x"}


class Recover(CrewCase):
    def ident(self):
        return registry.Identity("alpha", "mine0000", CWD)

    def test_summary_in_an_earlier_chunk(self):
        lines = [title("alpha"), user("OLD before summary"),
                 {"type": "system", "subtype": "compact_boundary"},
                 user("THE SUMMARY", isCompactSummary=True)]
        for i in range(30):
            lines.append(user("question %d " % i + "q" * 300) if i % 2 == 0
                         else assistant("answer %d " % i + "a" * 300))
        lines.append(title("alpha"))
        path = self.transcript("old00000", lines=lines)
        self.assertGreater(os.path.getsize(path), 3 * 2048)
        with unittest.mock.patch.object(recover, "CHUNK", 2048):
            rc, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("THE SUMMARY", raw)
        self.assertNotIn("OLD before summary", raw)
        self.assertIn("[user] question 0 ", raw)
        self.assertIn("[assistant] answer 29 ", raw)
        self.assertNotIn("tool_use", raw)

    def test_text_is_cut_and_total_is_bounded(self):
        lines = [title("alpha"), user("S", isCompactSummary=True)]
        lines += [user("m%d " % i + "z" * 5000) for i in range(40)]
        self.transcript("old00000", lines=lines)
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertLessEqual(len(raw), recover.TOTAL_CUT + 2000)
        self.assertNotIn("z" * (recover.PART_CUT + 1), raw)
        self.assertIn("m39 ", raw)  # the newest are kept

    def test_no_summary_still_gives_the_messages(self):
        self.transcript("old00000", lines=[title("alpha"), user("hello there")])
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("(none found)", raw)
        self.assertIn("hello there", raw)

    def test_picks_the_transcript_with_the_name_not_its_own(self):
        mine = self.transcript("mine0000", lines=[title("alpha"), user("MINE")])
        other = self.transcript("other000", lines=[title("beta"), user("OTHER")])
        old = self.transcript("old00000", lines=[title("alpha"), user("OLD")])
        os.utime(old, (1, 1))
        os.utime(mine, (3, 3))
        os.utime(other, (2, 2))
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("OLD", raw)
        self.assertNotIn("MINE", raw)
        self.assertNotIn("OTHER", raw)

    def test_last_title_wins(self):
        self.transcript("old00000", lines=[title("alpha"), user("x"), title("renamed")])
        _, _, raw = self.call(recover.run, self.ident(), "alpha")
        self.assertIn("Nothing to recover", raw)

    def test_read_limit_bounds_the_search(self):
        self.transcript("old00000", lines=[title("alpha")] + [user("f" * 200)] * 50)
        with unittest.mock.patch.object(recover, "MAX_TITLE", 1000):
            self.assertIsNone(recover.last_title(
                os.path.join(self.claude, "projects", "-work-proj", "old00000.jsonl"), recover.Budget(10**9)))

    def test_reverse_lines_handles_boundaries(self):
        path = os.path.join(self.tmp, "f")
        lines = [("line%d-" % i) * (i % 7 + 1) for i in range(200)]
        with open(path, "w") as f:
            f.write("\n".join(lines) + "\n")
        for chunk in (1, 7, 64, 1000, 10**6):
            got = [x.decode() for x in recover.reverse_lines(path, recover.Budget(10**9), chunk=chunk)]
            self.assertEqual(got, lines[::-1], chunk)
