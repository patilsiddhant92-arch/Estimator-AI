"""Child processes in tests on a loaded Windows machine: a child that could not even start because too many
processes were running at once exits with 0xC0000142 (3221225794, STATUS_DLL_INIT_FAILED); it never ran, so it is
run again, up to 3 tries with a short pause. Any other exit code, a real failure, is returned (or raised with
check=True) at once, as subprocess.run does. tests/conftest.py puts this in front of subprocess.run for every test."""
from __future__ import annotations

import functools
import subprocess
import time

RESOURCE_ERROR = 3221225794          # 0xC0000142: the child could not initialise (desktop heap, too many processes)
TRIES = 3
PAUSE = 0.5                           # seconds between tries


def retrying(run, sleep=time.sleep):
    """`run` (subprocess.run) tried again only when the child exits with RESOURCE_ERROR."""
    @functools.wraps(run)
    def wrapper(*args, **kwargs):
        check = kwargs.pop("check", False)
        for attempt in range(TRIES):
            done = run(*args, **kwargs)
            if done.returncode != RESOURCE_ERROR or attempt == TRIES - 1:
                break
            sleep(PAUSE)
        if check and done.returncode != 0:
            raise subprocess.CalledProcessError(done.returncode, done.args, output=done.stdout, stderr=done.stderr)
        return done
    wrapper.retries_resource_errors = True
    return wrapper
