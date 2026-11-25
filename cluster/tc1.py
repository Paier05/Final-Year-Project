"""Talk to the TC1 head node from the machine running the agent (issue #14).

    python cluster/tc1.py run "MyTCinfo"                 # one command, one connection
    python cluster/tc1.py run "cmd one" "cmd two"        # several, same connection
    python cluster/tc1.py upload                         # the repo at HEAD + the game files
    python cluster/tc1.py put-env                        # write ~/.evo_harness_env (chmod 600)
    python cluster/tc1.py rm-env                         # delete it (when the run is finished)
    python cluster/tc1.py fetch runs/v3 logs             # copy results back

Credentials are read from the environment and used only for SSH/SFTP:
TC1_HOST, TC1_PORT, TC1_USER, TC1_PASSWORD. The password is never put on a
command line, in a file on the cluster, or in any output. The model keys for
`put-env` come from QWEN_API_KEY / QWEN_BASE_URL (environment or .env) and are
sent over SFTP into a 0600 file, not through a shell command.

Cluster rules this helper keeps: it runs no project code on the head node
(only file transfer, conda, and SLURM commands that the caller passes), it
opens one connection per invocation and closes it, and it never polls.
"""

from __future__ import annotations

import argparse
import io
import os
import posixpath
import stat
import subprocess
import sys
import tarfile
import tempfile

import paramiko

REMOTE_REPO = "evo-harness"          # under the home directory on TC1
ENV_FILE = ".evo_harness_env"
GAMES = ("ls20", "ft09", "vc33")    # game files (gitignored) uploaded with the code
# Not needed on the cluster and large: earlier runs' results and the PDFs.
ARCHIVE_EXCLUDE = (":(exclude)results", ":(exclude)Documentation_Generated", ":(exclude)data")


def connect() -> paramiko.SSHClient:
    missing = [k for k in ("TC1_HOST", "TC1_USER", "TC1_PASSWORD") if not os.environ.get(k)]
    if missing:
        raise SystemExit(f"set {', '.join(missing)} in the environment (see the issue's Credentials table)")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        os.environ["TC1_HOST"], port=int(os.environ.get("TC1_PORT", "22")),
        username=os.environ["TC1_USER"].lower(), password=os.environ["TC1_PASSWORD"],
        look_for_keys=False, allow_agent=False, timeout=30,
    )
    return client


def run(client: paramiko.SSHClient, command: str, timeout: int = 900) -> int:
    """Run one command in a login shell (so `module` and conda are set up)."""
    print(f"$ {command}", flush=True)
    _stdin, stdout, stderr = client.exec_command(f"bash -lc {_quote(command)}", timeout=timeout)
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("[stderr] " + err.rstrip().replace("\n", "\n[stderr] "))
    if code:
        print(f"[exit code {code}]")
    return code


def _quote(text: str) -> str:
    return "'" + text.replace("'", "'\"'\"'") + "'"


def _local_env(name: str) -> str:
    value = os.environ.get(name)
    if not value and os.path.exists(".env"):
        with open(".env", encoding="utf-8") as handle:
            for line in handle:
                if line.strip().startswith(f"{name}="):
                    value = line.strip().split("=", 1)[1].strip().strip('"').strip("'")
    if not value:
        raise SystemExit(f"{name} is not set (environment or .env)")
    return value


def cmd_upload(client: paramiko.SSHClient) -> int:
    """The tracked files at HEAD (the tested commit), a COMMIT file naming it,
    and the gitignored game files the run needs."""
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"],
                           capture_output=True, text=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit("the working tree has uncommitted changes; commit first so the upload is a commit")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
    with tempfile.TemporaryDirectory() as tmp:
        code_tar = os.path.join(tmp, "code.tar.gz")
        subprocess.run(["git", "archive", "--format=tar.gz", "-o", code_tar, "HEAD", "--", ".", *ARCHIVE_EXCLUDE],
                       check=True)
        extra_tar = os.path.join(tmp, "extra.tar.gz")
        with tarfile.open(extra_tar, "w:gz") as tar:
            for game in GAMES:  # ls20 for the tests, ft09 and vc33 for #15
                tar.add(os.path.join("environment_files", game), arcname=f"environment_files/{game}")
            data = (commit + "\n").encode()
            info = tarfile.TarInfo("COMMIT")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
        sftp = client.open_sftp()
        for name in (REMOTE_REPO, f"{REMOTE_REPO}/logs"):
            try:
                sftp.mkdir(name)
            except OSError:
                pass
        for local, remote in ((code_tar, f"{REMOTE_REPO}/_code.tar.gz"), (extra_tar, f"{REMOTE_REPO}/_extra.tar.gz")):
            sftp.put(local, remote)
            print(f"uploaded {os.path.getsize(local) / 1e6:.2f} MB -> ~/{remote}")
        sftp.close()
    return run(client, f"cd ~/{REMOTE_REPO} && tar xzf _code.tar.gz && tar xzf _extra.tar.gz && "
                       "rm _code.tar.gz _extra.tar.gz && cat COMMIT && file cluster/*.sh")


def cmd_put_env(client: paramiko.SSHClient) -> int:
    body = "".join(f"{name}={_local_env(name)}\n" for name in ("QWEN_API_KEY", "QWEN_BASE_URL"))
    sftp = client.open_sftp()
    with sftp.open(ENV_FILE, "w") as handle:
        handle.write(body)
    sftp.chmod(ENV_FILE, stat.S_IRUSR | stat.S_IWUSR)
    mode = stat.S_IMODE(sftp.stat(ENV_FILE).st_mode)
    sftp.close()
    print(f"wrote ~/{ENV_FILE} (mode {mode:o}, {len(body.splitlines())} variables: QWEN_API_KEY, QWEN_BASE_URL)")
    return 0


def cmd_rm_env(client: paramiko.SSHClient) -> int:
    sftp = client.open_sftp()
    try:
        sftp.remove(ENV_FILE)
        print(f"deleted ~/{ENV_FILE}")
    except OSError:
        print(f"~/{ENV_FILE} was not there")
    sftp.close()
    return 0


def cmd_fetch(client: paramiko.SSHClient, paths: list[str], dest: str) -> int:
    """Copy directories or files under ~/evo-harness back, keeping their paths."""
    sftp = client.open_sftp()
    count = size = 0

    def walk(remote: str, local: str) -> None:
        nonlocal count, size
        attrs = sftp.stat(remote)
        if stat.S_ISDIR(attrs.st_mode):
            os.makedirs(local, exist_ok=True)
            for item in sftp.listdir_attr(remote):
                walk(posixpath.join(remote, item.filename), os.path.join(local, item.filename))
            return
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        # Skip files already here with the same size and time (trajectories do not change once written).
        if os.path.exists(local) and os.path.getsize(local) == attrs.st_size \
                and int(os.path.getmtime(local)) == int(attrs.st_mtime):
            return
        sftp.get(remote, local)
        os.utime(local, (attrs.st_atime, attrs.st_mtime))
        count += 1
        size += attrs.st_size

    for path in paths:
        try:
            walk(posixpath.join(REMOTE_REPO, path), os.path.join(dest, *path.split("/")))
        except FileNotFoundError:
            print(f"not on the cluster: ~/{REMOTE_REPO}/{path}")
    sftp.close()
    print(f"fetched {count} new or changed files, {size / 1e6:.2f} MB, into {dest}")
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="TC1 head-node helper (#14)")
    sub = parser.add_subparsers(dest="command", required=True)
    runner = sub.add_parser("run")
    runner.add_argument("commands", nargs="+")
    runner.add_argument("--timeout", type=int, default=900, help="seconds without output before giving up")
    sub.add_parser("upload")
    sub.add_parser("put-env")
    sub.add_parser("rm-env")
    fetch = sub.add_parser("fetch")
    fetch.add_argument("paths", nargs="+")
    fetch.add_argument("--dest", default=".")
    args = parser.parse_args()

    client = connect()
    try:
        if args.command == "run":
            code = 0
            for command in args.commands:
                code = run(client, command, timeout=args.timeout) or code
        elif args.command == "upload":
            code = cmd_upload(client)
        elif args.command == "put-env":
            code = cmd_put_env(client)
        elif args.command == "rm-env":
            code = cmd_rm_env(client)
        else:
            code = cmd_fetch(client, args.paths, args.dest)
    finally:
        client.close()
    sys.exit(code)


if __name__ == "__main__":
    main()
