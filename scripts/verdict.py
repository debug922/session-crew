"""A guard's answer: ask or deny, and why."""


class Verdict:
    def __init__(self, kind, reason):
        self.kind, self.reason = kind, reason
