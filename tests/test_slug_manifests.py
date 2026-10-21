"""The folder slug and the plugin manifests."""
import json
import os
import signal
import subprocess
import sys
import unittest.mock

from helpers import CWD, CrewCase, MB, ROOT
from test_recover_budgets import msg

import config
import recover
import registry

CREW = os.path.join(ROOT, "scripts", "crew.py")



class Slug(CrewCase):
    def test_every_non_alphanumeric_becomes_a_dash(self):
        cwd = "/home/x y/my_proj.v2"
        self.assertEqual(config.slug(cwd), "-home-x-y-my-proj-v2")

    def test_transcripts_found_under_the_slug(self):
        cwd = "/home/x y/my_proj.v2"
        folder = os.path.join(self.claude, "projects", config.slug(cwd))
        os.makedirs(folder)
        with open(os.path.join(folder, "old00000.jsonl"), "w") as f:
            f.write(json.dumps({"type": "custom-title", "customTitle": "alpha"}) + "\n"
                    + json.dumps(msg("user", "HELLO")) + "\n")
        _, _, raw = self.call(recover.run, registry.Identity("alpha", "me", cwd), "alpha")
        self.assertIn("HELLO", raw)

    def test_long_cwd_globs_the_prefix_with_the_hash(self):
        cwd = "/" + "/".join("dir%d" % i for i in range(60))
        self.assertGreater(len(config.raw_slug(cwd)), 200)
        self.assertEqual(len(config.slug(cwd)), 200)
        folder = os.path.join(self.claude, "projects", config.slug(cwd) + "-8f3a2b")
        os.makedirs(folder)
        with open(os.path.join(folder, "abc12345.jsonl"), "w") as f:
            f.write("{}\n")
        self.assertEqual(config.transcript_path(cwd, "abc12345"),
                         os.path.join(folder, "abc12345.jsonl"))

    def test_crew_folder_uses_the_same_slug(self):
        cwd = "/a b/c_d.e"
        self.assertEqual(config.project_dir(cwd), os.path.join(self.crew_home, "-a-b-c-d-e"))


class Manifests(unittest.TestCase):
    def load(self, *parts):
        with open(os.path.join(ROOT, *parts)) as f:
            return json.load(f)

    def test_plugin_and_marketplace(self):
        plugin = self.load(".claude-plugin", "plugin.json")
        self.assertEqual((plugin["name"], plugin["version"]), ("session-crew", "0.1.0"))
        market = self.load(".claude-plugin", "marketplace.json")
        self.assertEqual(market["name"], "session-crew")
        self.assertEqual([(p["name"], p["source"]) for p in market["plugins"]],
                         [("session-crew", "./")])

    def test_hooks(self):
        hooks = self.load("hooks", "hooks.json")["hooks"]
        prompt = hooks["UserPromptSubmit"][0]["hooks"]
        self.assertEqual([(h["type"], h["timeout"]) for h in prompt],
                         [("command", 10), ("command", 15)])
        self.assertTrue(prompt[0]["command"].endswith('crew.py" hook size'))
        self.assertTrue(prompt[1]["command"].endswith('crew.py" hook rename'))
        start = hooks["SessionStart"][0]
        self.assertEqual(start["matcher"], "startup|clear")
        self.assertEqual(start["hooks"][0]["timeout"], 10)
        for h in prompt + start["hooks"]:
            self.assertTrue(h["command"].startswith('python3 -I "${CLAUDE_PLUGIN_ROOT}/'))


