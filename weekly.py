"""The weekly job: every league's board and season model, logged.

Run by the Windows scheduled task "FantasyWeekly" (Tuesday and Wednesday
evenings, once the week's games are in and FantasyPros has re-ranked). It runs
under pythonw.exe -- no console window -- so it keeps its own log at
logs/weekly.log and hands the work to run.py in a hidden console.

Each run refreshes the rankings, news and headshots, reruns the season model
and rebuilds every league's report. The model run also takes the week's 2026
final-exam snapshot the first time FantasyPros has updated after the games;
the Wednesday run is the retry if Tuesday's was too early.

Afterwards it commits and pushes each league's model.json when it changed: the
hourly GitHub Actions build of the live site has no model of its own and reads
it from the repo.

Injury comments that are new since they were labelled are listed in the log
(the labelling itself needs a Claude subagent -- see ml/injury_labels.py).
"""
import datetime, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
LOG = os.path.join(HERE, "logs", "weekly.log")
PY = os.path.join(HERE, ".venv", "Scripts", "python.exe")


def main():
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONUNBUFFERED="1")
    with open(LOG, "a", encoding="utf-8") as log:
        log.write(f"\n===== {datetime.datetime.now():%Y-%m-%d %H:%M} weekly run =====\n")
        log.flush()
        r = subprocess.run([PY, "run.py", "--all"], cwd=HERE, env=env, stdout=log,
                           stderr=subprocess.STDOUT,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        log.write(f"===== finished {datetime.datetime.now():%H:%M}, exit {r.returncode} =====\n")
        log.flush()
        publish(log, env)


def publish(log, env):
    """Commit and push this week's model.json files, and nothing else."""
    def git(*args):
        return subprocess.run(["git", *args], cwd=HERE, env=env, stdout=log, stderr=subprocess.STDOUT,
                              creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
    git("add", "--", "leagues/*/model.json")
    if subprocess.run(["git", "diff", "--cached", "--quiet", "--", "leagues/*/model.json"], cwd=HERE,
                      creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0:
        log.write("model.json unchanged, nothing to publish\n")
        return
    week = datetime.date.today().isoformat()
    ok = (git("commit", "-m", f"Season model: weekly update {week}", "--", "leagues/*/model.json") == 0
          and git("pull", "--rebase", "--autostash") == 0
          and git("push") == 0)
    log.write(f"model.json {'published' if ok else 'NOT published -- push it by hand'}\n")


if __name__ == "__main__":
    main()
