"""Helper for VPS operations over SSH (paramiko).

Usage:
    python scripts/vps.py run "command args..."
    python scripts/vps.py upload local_path remote_path
    python scripts/vps.py script local_script.sh   # upload & bash it

Password is read from env var VPS_PASS.
"""
import os
import sys

import paramiko

HOST = os.environ.get("VPS_HOST", "91.142.75.38")
USER = os.environ.get("VPS_USER", "root")
PASS = os.environ.get("VPS_PASS")


def connect():
    if not PASS:
        sys.exit("VPS_PASS env var is not set")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(HOST, username=USER, password=PASS, timeout=30,
                   banner_timeout=30, auth_timeout=30)
    return client


def run(cmd, client=None, check=True):
    own = client is None
    if own:
        client = connect()
    try:
        stdin, stdout, stderr = client.exec_command(cmd, timeout=600)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        code = stdout.channel.recv_exit_status()
        if out:
            print(out, end="")
        if err:
            print(err, end="", file=sys.stderr)
        if check and code != 0:
            print(f"[exit {code}]", file=sys.stderr)
        return code, out, err
    finally:
        if own:
            client.close()


def upload(local, remote, client=None):
    own = client is None
    if own:
        client = connect()
    try:
        sftp = client.open_sftp()
        # ensure remote dir exists
        rdir = os.path.dirname(remote.replace("\\", "/"))
        if rdir:
            run(f"mkdir -p {rdir}", client=client)
        sftp.put(local, remote)
        sftp.close()
        print(f"uploaded {local} -> {remote}")
    finally:
        if own:
            client.close()


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "run":
        sys.exit(run(" ".join(sys.argv[2:]))[0])
    elif mode == "upload":
        upload(sys.argv[2], sys.argv[3])
    elif mode == "script":
        local = sys.argv[2]
        remote = "/tmp/_vps_script.sh"
        upload(local, remote)
        sys.exit(run(f"bash {remote}")[0])
    else:
        sys.exit(f"unknown mode {mode}")
