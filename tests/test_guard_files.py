"""The file-tool guard: writes to the project file and to the plugin's folder."""
import os

from guardhelp import GuardCase

import config
import guard


class Files(GuardCase):
    def test_a_write_to_the_project_file_or_the_plugin_asks(self):
        project_file = config.project_file(self.work)
        other = os.path.join(config.home(), "-some-other-slug", "project.json")
        paths = [project_file, other, os.path.join(guard.ROOT, "scripts", "guard.py"),
                 os.path.join(guard.ROOT, "hooks", "hooks.json"), guard.ROOT]
        for path in paths:
            for tool in ("Write", "Edit", "MultiEdit"):
                self.assertEqual(self.files(tool, file_path=path, content="x"), "ask", (tool, path))
        self.assertEqual(self.files("NotebookEdit", notebook_path=project_file), "ask")

    def test_at_night_the_ask_is_a_refusal(self):
        self.night(True)
        self.assertEqual(self.files("Write", file_path=config.project_file(self.work)), "deny")
        self.assertEqual(self.files("Edit", file_path=guard.ROOT + "/scripts/door.py"), "deny")
        self.night(False)
        self.assertEqual(self.files("Write", file_path=config.project_file(self.work)), "ask")

    def test_drafts_handovers_and_the_rest_are_ordinary(self):
        folder = config.project_dir(self.work)
        for path in [os.path.join(folder, "drafts", "d.json"), os.path.join(folder, "boss", "h.md"),
                     os.path.join(config.home(), "project.json"), os.path.join(self.work, "project.json"),
                     os.path.join(self.work, "core", "a.txt"), guard.ROOT + "-old/x.py"]:
            self.assertIsNone(self.files("Write", file_path=path, content="x"), path)

    def test_reading_is_not_this_guards_and_a_relative_path_is_resolved(self):
        self.assertIsNone(self.files("Read", file_path=config.project_file(self.work)))
        rel = os.path.relpath(config.project_file(self.work), self.work)
        self.assertEqual(self.files("Write", file_path=rel, content="x"), "ask")

    def test_a_symlink_to_the_project_file_does_not_hide_it(self):
        link = os.path.join(self.work, "link.json")
        os.symlink(config.project_file(self.work), link)
        self.assertEqual(self.files("Write", file_path=link, content="x"), "ask")
