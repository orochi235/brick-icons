#!/bin/sh
# Run the lab as a pair of launchd agents, so it outlives the terminal.
# `install` links this onto PATH as `brick-lab`, the name menubar.yaml runs.
#
#   brick-lab install           write both agents, link this script, start them
#   brick-lab up | down | cycle start, stop or restart them
#   brick-lab stat              what launchd thinks, and whether each answers
#   brick-lab log               open the log directory
#   brick-lab plists            write the agents and start nothing
set -eu

# $0 is the link in ~/.local/bin when the menu bar runs this.
self=$0
while [ -L "$self" ]; do
  target=$(readlink "$self")
  case $target in
    /*) self=$target ;;
    *) self=$(dirname -- "$self")/$target ;;
  esac
done
repo=$(CDPATH= cd -- "$(dirname -- "$self")/.." && pwd)

state=${BRICK_LAB_STATE:-$HOME/.local/state/brick-icons}
agents=${BRICK_LAB_AGENTS:-$HOME/Library/LaunchAgents}
bin=${BRICK_LAB_BIN:-$HOME/.local/bin}
domain="gui/$(id -u)"
base=tech.michaelbaker.brick-icons
# The defaults in brick_icons/lab/__main__.py and lab/vite.config.ts, which a
# shell script cannot import.
api_port=8792
front_port=5178

plist() { # label, working directory, program arguments, log
  cat > "$agents/$1.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>$1</string>
	<key>ProgramArguments</key>
	<array>
$3
	</array>
	<key>WorkingDirectory</key>
	<string>$2</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>$nodedir:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
	</dict>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<true/>
	<key>StandardOutPath</key>
	<string>$state/$4.log</string>
	<key>StandardErrorPath</key>
	<string>$state/$4.log</string>
</dict>
</plist>
PLIST
}

write() {
  # launchd starts with almost no PATH, and vite is a node shebang.
  node=$(command -v node) || {
    echo "brick-lab: node is not on PATH, and vite needs it" >&2
    exit 1
  }
  nodedir=$(dirname -- "$node")
  mkdir -p "$state" "$agents"
  plist "$base.lab-api" "$repo" "		<string>$repo/.venv/bin/python</string>
		<string>-m</string>
		<string>brick_icons.lab</string>
		<string>--reload</string>
		<string>--quiet</string>" lab-api
  plist "$base.lab-front" "$repo/lab" \
    "		<string>$repo/lab/node_modules/.bin/vite</string>" lab-front
}

linked() {
  [ "$(git -C "$repo" rev-parse --git-dir)" != \
    "$(git -C "$repo" rev-parse --git-common-dir)" ]
}

fresh() {
  mkdir -p "$state"
  : > "$state/lab-api.log"
  : > "$state/lab-front.log"
}

free() { # port
  pids=$(lsof -ti "tcp:$1" 2>/dev/null || true)
  # shellcheck disable=SC2086
  [ -z "$pids" ] || kill $pids 2>/dev/null || true
}

each() { for label in "$base.lab-api" "$base.lab-front"; do "$1" "$label"; done; }
boot() { launchctl bootstrap "$domain" "$agents/$1.plist" 2>/dev/null || true; }
# bootout returns before launchd has let go of the label, and a bootstrap in
# that window fails and leaves nothing loaded.
unboot() {
  launchctl bootout "$domain/$1" 2>/dev/null || true
  tries=0
  while launchctl print "$domain/$1" >/dev/null 2>&1 && [ $tries -lt 50 ]; do
    sleep 0.1
    tries=$((tries + 1))
  done
}
kick() { launchctl kickstart -k "$domain/$1" >/dev/null 2>&1 || true; }

answers() { # url
  code=$(curl -s -m 2 -o /dev/null -w '%{http_code}' "$1") || code=no
  echo "$code"
}

case "${1:-stat}" in
  install)
    if linked; then
      echo "brick-lab: $repo is a linked worktree; install from the main checkout, or the agents die with the worktree" >&2
      exit 1
    fi
    # Without it launchd exits 78 with an empty log, forever.
    [ -x "$repo/lab/node_modules/.bin/vite" ] || {
      echo "brick-lab: $repo/lab has no node_modules; run npm ci there first" >&2
      exit 1
    }
    write
    mkdir -p "$bin"
    ln -sf "$repo/scripts/lab-agents.sh" "$bin/brick-lab"
    each unboot
    # A lab started by hand holds the port, the agent exits on start, and
    # KeepAlive turns that into a restart loop rather than an error.
    free "$api_port"
    free "$front_port"
    fresh
    each boot
    echo "installed: $base.lab-api, $base.lab-front"
    ;;
  plists) write ;;
  up)     fresh; each boot ;;
  down)   each unboot ;;
  cycle)  fresh; each kick ;;
  log)    open "$state" ;;
  stat)
    for label in "$base.lab-api" "$base.lab-front"; do
      printf '%-45s %s\n' "$label" \
        "$(launchctl print "$domain/$label" 2>/dev/null | awk '/^\tstate = /{print $3; found=1; exit} END{if (!found) print "not loaded"}')"
    done
    printf '%-45s %s\n' 'api answers' "$(answers "http://127.0.0.1:$api_port/api/health")"
    printf '%-45s %s\n' 'front answers' "$(answers "http://localhost:$front_port/")"
    ;;
  *) echo "brick-lab: no such command: $1" >&2; exit 1 ;;
esac
