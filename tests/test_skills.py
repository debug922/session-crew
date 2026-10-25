import os
import re
import unittest

from helpers import ROOT

FIELDS = {"name", "description", "argument-hint", "disable-model-invocation"}  # what both hosts read
DASHES = (chr(0x2013), chr(0x2014))


def frontmatter(name):
    with open(os.path.join(ROOT, "skills", name, "SKILL.md"), encoding="utf-8") as f:
        text = f.read()
    head = re.match(r"---\n(.*?)\n---\n", text, re.DOTALL).group(1)
    return dict(line.split(": ", 1) for line in head.splitlines()), text


class Skills(unittest.TestCase):
    def test_every_skill_has_only_the_fields_both_hosts_read_and_its_folders_name(self):
        for name in sorted(os.listdir(os.path.join(ROOT, "skills"))):
            fields, _ = frontmatter(name)
            self.assertEqual(fields["name"], name)
            self.assertTrue(set(fields) <= FIELDS, (name, set(fields) - FIELDS))
            self.assertTrue(fields["description"], name)

    def test_the_commands_the_user_starts_are_not_the_models_to_start(self):
        for name in ("push", "release", "migrate"):
            self.assertEqual(frontmatter(name)[0]["disable-model-invocation"], "true", name)
        self.assertNotIn("disable-model-invocation", frontmatter("setup")[0])

    def test_the_door_lines_name_the_plugin_by_its_root(self):
        for name, word in (("push", "push"), ("release", "tag")):
            text = frontmatter(name)[1]
            self.assertIn('python3 -I "${CLAUDE_PLUGIN_ROOT}/scripts/crew.py" %s $ARGUMENTS' % word, text)

    def test_no_skill_holds_a_long_or_medium_dash(self):
        for name in os.listdir(os.path.join(ROOT, "skills")):
            self.assertFalse(any(d in frontmatter(name)[1] for d in DASHES), name)
