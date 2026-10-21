"""Messages to the maintainer (it, en) and context lines for the session (English)."""

USER = {
    "it": {
        "pending": "Passaggio pronto: scrivi /clear e poi /migrate.",
        "big": "Questa sessione pesa {mb} MB: /handoff, /clear, /migrate.",
        "night": "Questa sessione pesa {mb} MB: prima della notte /handoff, /clear, /migrate, "
                 "poi ripeti il comando.",
        "waiting": "Passaggio in attesa per {name}: scrivi {cmd}.",
        "mode": "Questa sessione è in modalità {mode}: di notte ogni richiesta di permesso la "
                "ferma fino al mattino. Passa alla modalità auto prima di andare.",
    },
    "en": {
        "pending": "Handoff ready: type /clear and then /migrate.",
        "big": "This session weighs {mb} MB: /handoff, /clear, /migrate.",
        "night": "This session weighs {mb} MB: before the night run /handoff, /clear, /migrate, "
                 "then repeat the command.",
        "waiting": "Handoff waiting for {name}: type {cmd}.",
        "mode": "This session is in {mode} mode: at night every permission request stops it until "
                "the morning. Switch to auto mode before you go.",
    },
}

CTX = {
    "warn": "The transcript of this session is {mb} MB. Close the item under way, run /handoff "
            "at the next pause, and start no new item in this conversation.",
    "night": "The transcript of this session is {mb} MB. Do not start the unattended run in this "
             "conversation; tell the maintainer why: he must /handoff, /clear, /migrate first.",
    "mode": "The permission mode of this session is {mode}: at night every permission request "
            "would stop it. Do not start the unattended run until the mode is changed to auto.",
    "ceiling": "The transcript of this session is {mb} MB, over the unattended ceiling. Park the "
               "queue at the next release point, write the handoff and the report.",
    "waiting": "A pending handoff exists for {name}. The maintainer will type {cmd}.",
    "busy": "The session called {name} (pid {pid}) is busy or waiting, so the name was not moved "
            "to this one. The maintainer closes the old session or waits, then types "
            "/migrate {name} again.",
    "pending": "A handoff for this session is already written; the maintainer will /clear and "
               "/migrate. Finish the turn and start no new item.",
    "unverified": "The session called {name} (pid {pid}) could not be verified as still running "
                  "(its registry file has no procStart), so the name was not moved to this one. "
                  "The maintainer closes it, then types /migrate {name} again.",
    "stuck": "The session called {name} (pid {pid}) did not stop after SIGTERM, so the name was "
             "not moved to this one. The maintainer closes it, then types /migrate {name} again.",
}


def user(lang, key, **kw):
    return USER.get(lang, USER["en"])[key].format(**kw)


def ctx(key, **kw):
    return CTX[key].format(**kw)
