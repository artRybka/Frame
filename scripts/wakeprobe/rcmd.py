"""Run JS in the WakeProbe app via the remote console and print the result.

    rcmd.py 'webapis.epaper.getVersion()'          sync: value of the last expression
    rcmd.py --async 'tizen.x.get(done, done)'       async: whatever is passed to done()

Talks to the app through server.py's directory (WAKEPROBE_DIR, default
dist/wakeprobe): writes DIR/cmd, which remote.js polls, and reads the answer
from DIR/requests.log.
"""

import json
import os
import sys
import time
from pathlib import Path

DIR = Path(os.environ.get("WAKEPROBE_DIR", "dist/wakeprobe"))
CMD, LOG = DIR / "cmd", DIR / "requests.log"

args = sys.argv[1:]
is_async = "--async" in args
code = [a for a in args if a != "--async"][0]
last = json.loads(CMD.read_text())["id"] if CMD.exists() else 0
cid = last + 1
start = len(LOG.read_text().splitlines())
CMD.write_text(json.dumps({"id": cid, "code": code, "async": is_async}))
deadline = time.time() + float(30)
while time.time() < deadline:
    for line in LOG.read_text().splitlines()[start:]:
        if '"kind":"cmd-result"' in line:
            body = json.loads(line.split(" BODY ", 1)[1])
            if body["data"]["id"] == cid:
                print(json.dumps(body["data"]["value"], ensure_ascii=False))
                # A freshly started app would replay the last command: blank it.
                CMD.write_text(json.dumps({"id": cid, "code": "null"}))
                sys.exit(0)
    time.sleep(0.5)
print("timeout (app asleep or not running?)")
sys.exit(1)
