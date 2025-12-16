#!/usr/bin/env python3
import os
import sys
import re

# -------------------------------
# Utility Functions
# -------------------------------

def get_prompt():
    return os.environ.get("PS1", "$ ")

def resolve_path(cmd):
    if "/" in cmd:
        return cmd if os.access(cmd, os.X_OK) else None
    path = os.environ.get("PATH", "")
    for d in path.split(":"):
        full = d + "/" + cmd
        if os.access(full, os.X_OK):
            return full
    return None

def print_error(msg):
    os.write(2, (msg + "\n").encode())

# -------------------------------
# Parsing
# -------------------------------

def parse_line(line):
    line = line.strip()
    if not line:
        return None

    background = False
    if line.endswith("&"):
        background = True
        line = line[:-1].strip()

    parts = [p.strip() for p in line.split("|")]
    pipeline = []

    for part in parts:
        tokens = part.split()
        cmd = []
        stdin = None
        stdout = None
        i = 0
        while i < len(tokens):
            if tokens[i] == "<":
                stdin = tokens[i+1]
                i += 2
            elif tokens[i] == ">":
                stdout = tokens[i+1]
                i += 2
            else:
                cmd.append(tokens[i])
                i += 1

        if not cmd:
            return None

        pipeline.append({
            "argv": cmd,
            "stdin": stdin,
            "stdout": stdout
        })

    return pipeline, background

# -------------------------------
# Built-in Commands
# -------------------------------

def handle_builtin(argv):
    if argv[0] == "exit":
        sys.exit(0)

    if argv[0] == "cd":
        try:
            if len(argv) > 1:
                os.chdir(argv[1])
            else:
                os.chdir(os.environ.get("HOME", "/"))
        except Exception as e:
            print_error(str(e))
        return True

    return False

# -------------------------------
# Execution
# -------------------------------

def execute_pipeline(pipeline, background):
    num_cmds = len(pipeline)
    pipes = []

    for _ in range(num_cmds - 1):
        pipes.append(os.pipe())

    pids = []

    for i, cmd in enumerate(pipeline):
        pid = os.fork()
        if pid == 0:
            # Child

            # Input redirection
            if cmd["stdin"]:
                fd = os.open(cmd["stdin"], os.O_RDONLY)
                os.dup2(fd, 0)
                os.close(fd)

            # Output redirection
            if cmd["stdout"]:
                fd = os.open(cmd["stdout"],
                             os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
                os.dup2(fd, 1)
                os.close(fd)

            # Pipes
            if i > 0:
                os.dup2(pipes[i-1][0], 0)
            if i < num_cmds - 1:
                os.dup2(pipes[i][1], 1)

            # Close all pipe fds
            for r, w in pipes:
                os.close(r)
                os.close(w)

            path = resolve_path(cmd["argv"][0])
            if not path:
                print_error(f"{cmd['argv'][0]}: command not found")
                os._exit(1)

            try:
                os.execve(path, cmd["argv"], os.environ)
            except Exception:
                print_error(f"{cmd['argv'][0]}: command not found")
                os._exit(1)

        else:
            pids.append(pid)

    # Parent closes pipe fds
    for r, w in pipes:
        os.close(r)
        os.close(w)

    # Wait unless background
    if not background:
        for pid in pids:
            _, status = os.waitpid(pid, 0)
            if os.WIFEXITED(status):
                code = os.WEXITSTATUS(status)
                if code != 0:
                    print_error(f"Program terminated with exit code {code}.")
            else:
                print_error("Program terminated abnormally.")

# -------------------------------
# Main Loop
# -------------------------------

def main():
    while True:
        try:
            sys.stdout.write(get_prompt())
            sys.stdout.flush()

            line = sys.stdin.readline()
            if line == "":
                break

            parsed = parse_line(line)
            if not parsed:
                continue

            pipeline, background = parsed

            # Built-in only if single command and no pipes
            if len(pipeline) == 1 and handle_builtin(pipeline[0]["argv"]):
                continue

            execute_pipeline(pipeline, background)

        except EOFError:
            break
        except KeyboardInterrupt:
            sys.stdout.write("\n")
            continue

if __name__ == "__main__":
    main()