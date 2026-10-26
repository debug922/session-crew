import json
import os
import subprocess
import sys

from helpers import CrewCase

import registry


def dead_pid():
    """The pid of a process that has just ended."""
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    return p.pid


class FindBySessionId(CrewCase):
    def write(self, pid, name, updated):
        entry = {"pid": pid, "sessionId": "s1", "name": name, "nameSource": "user",
                 "updatedAt": updated}
        # The stale file sorts first in the listing: "1-" before "2-".
        with open(os.path.join(self.claude, "sessions", "%s.json" % name), "w") as f:
            json.dump(entry, f)

    def test_the_live_pid_wins_over_a_newer_stale_file(self):
        self.write(dead_pid(), "1-stale", updated=99)
        self.write(os.getpid(), "2-live", updated=1)
        self.assertEqual(registry.find_by_session_id("s1")["name"], "2-live")

    def test_among_live_files_the_newest_wins(self):
        self.write(os.getpid(), "1-old", updated=1)
        self.write(os.getppid(), "2-new", updated=2)
        self.assertEqual(registry.find_by_session_id("s1")["name"], "2-new")

    def test_with_none_alive_the_newest_answers(self):
        self.write(dead_pid(), "1-old", updated=1)
        self.write(dead_pid(), "2-new", updated=2)
        self.assertEqual(registry.find_by_session_id("s1")["name"], "2-new")

    def test_an_unknown_id_is_none(self):
        self.assertIsNone(registry.find_by_session_id("nope"))


class Ancestry(CrewCase):
    """The door and the guard take the registry as proof: a file counts only for the process that
    really started when it says (a stale file under a reused pid never does)."""

    def test_a_file_whose_start_time_matches_the_live_process_counts(self):
        self.session(os.getpid(), "s1", "boss")  # procStart read from the real process
        self.assertEqual(registry.find_by_ancestry()["name"], "boss")

    def test_a_file_under_a_reused_pid_does_not(self):
        self.session(os.getpid(), "s1", "boss", started="Mon Jan  1 00:00:00 2001")
        self.assertIsNone(registry.find_by_ancestry())

    def test_a_file_with_no_start_time_cannot_be_verified_and_does_not_count(self):
        self.session(os.getpid(), "s1", "boss", started=None)
        self.assertIsNone(registry.find_by_ancestry())

    def test_the_walk_goes_on_past_a_false_file_to_a_true_one_above(self):
        self.session(os.getpid(), "s1", "false", started="Mon Jan  1 00:00:00 2001")
        self.session(os.getppid(), "s2", "true")
        self.assertEqual(registry.find_by_ancestry()["name"], "true")
