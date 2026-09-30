"""Build the board for one league, end to end.

    python run.py brunch            # leagues/brunch/config.json -> report.html
    python run.py brunch --refresh  # bypass the FantasyPros page cache
    python run.py --all             # every league under leagues/

Each league gets its own directory holding config.json and its outputs. The
FantasyPros page cache, the per-player news cache and the headshots are shared
across leagues, so a second league costs very little to add.
"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
LEAGUES = os.path.join(HERE, "leagues")
PY = sys.executable
# The season model (ml/) needs pandas and scikit-learn, which live in this
# project's own .venv. Where there is none -- the hourly site build on GitHub
# Actions -- the board is built without the Model scale.
VENV_PY = (os.path.join(HERE, ".venv", "Scripts", "python.exe") if os.name == "nt"
           else os.path.join(HERE, ".venv", "bin", "python"))


def league_dir(name):
    d = os.path.join(LEAGUES, name)
    if not os.path.isdir(d):
        sys.exit(f"No league '{name}'. Expected {os.path.join(d, 'config.json')}")
    if not os.path.exists(os.path.join(d, "config.json")):
        sys.exit(f"{name}: missing config.json")
    return d


def step(label, args):
    print(f"\n=== {label} ===")
    r = subprocess.run([PY] + args, cwd=HERE)
    if r.returncode != 0:
        sys.exit(f"{label} failed ({r.returncode})")


def build(name, refresh=False, skip_extras=False):
    d = league_dir(name)
    cfg, data = os.path.join(d, "config.json"), os.path.join(d, "data.json")
    extra = ["--refresh"] if refresh else []

    step(f"{name}: rankings", ["fantasy.py", "--config", cfg, "--out", data] + extra)
    if not skip_extras:
        step(f"{name}: news + game logs", ["details.py", data] + extra)
        step(f"{name}: headshots", ["photos.py", data])
    if os.path.exists(VENV_PY):
        print(f"\n=== {name}: season model ===")
        r = subprocess.run([VENV_PY, "-m", "ml.predict", name], cwd=HERE)
        if r.returncode != 0:                   # the board still builds, on its last model.json
            print(f"{name}: season model failed ({r.returncode})")
    step(f"{name}: report", ["make_report.py", data, os.path.join(d, "report.html")])
    print(f"\n{name}: {os.path.join(d, 'report.html')}")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    refresh = "--refresh" in sys.argv
    skip = "--fast" in sys.argv          # rankings + report only
    os.makedirs(LEAGUES, exist_ok=True)

    names = args
    if "--all" in sys.argv or not names:
        names = sorted(n for n in os.listdir(LEAGUES)
                       if os.path.exists(os.path.join(LEAGUES, n, "config.json")))
        if not names:
            sys.exit(f"No leagues yet. Create {os.path.join(LEAGUES, '<name>', 'config.json')}")
    for n in names:
        build(n, refresh, skip)


if __name__ == "__main__":
    main()
