# cmux-sentinel — task runner. One source of truth for lint/format/CI so the
# pre-commit hook (lefthook.yml) and CI (.github/workflows/ci.yml) call the SAME
# targets — no drift between "passes locally" and "passes in CI".
#
#   make check   what CI runs + sidebar: shellcheck + secrets + markdown + test
#   make test    offline bridge state-machine test (stubs cmux; runs in CI too)
#   make doctor  health-check the live setup (read-only)
#   make sidebar-live  mount the repo sidebar for an honest human render check
#   make fmt     rewrite shell with shfmt (OPT-IN — see note below)
#   make help    list targets

SHELL   := bash
SCRIPTS := bin/cmux-sentinel bin/cmux-claude-usage.sh bin/cmux-codex-usage.sh bin/cmux-amp-usage.sh bin/cmux-sentinel-doctor.sh \
           bin/cmux-sentinel-setup.sh bin/cmux-sidebar-live-smoke.sh bin/cmux-group-sync.sh hooks/cmux-bridge.sh \
           install.sh scripts/check-secrets.sh scripts/make-formula.sh scripts/release-notes.sh \
           hooks/zed-bridge.sh bin/cmux-open-in-zed.sh bin/zed-usage-tui.sh \
           tests/bridge-state.sh tests/poller-gate.sh tests/codex-poller.sh \
           tests/install-hooks.sh tests/sentinel-setup.sh tests/sentinel-doctor.sh tests/group-sync.sh \
           tests/zed-bridge.sh tests/open-in-zed.sh tests/usage-tui.sh \
           tests/amp-bridge.sh tests/amp-poller.sh tests/entrypoint.sh tests/formula.sh \
           tests/release-notes.sh
MD      := $(wildcard *.md) $(wildcard docs/*.md) $(wildcard scripts/packaging/*/*.md)

.PHONY: help check ci lint shellcheck secrets markdown formula notes test doctor sidebar sidebar-live fmt fmt-check

help:
	@echo "make check   — portable CI checks + installed JS runtime + sidebar validation"
	@echo "make ci      — what CI runs (check minus sidebar; no cmux on the runner)"
	@echo "make test    — offline Python/JS + upstream bridge, poller, installer, setup, group, and Zed tests"
	@echo "make doctor  — health-check the live setup (read-only)"
	@echo "make sidebar-live — mount repo sidebar with live data for human visual inspection"
	@echo "make fmt     — reformat shell scripts with shfmt (opt-in, not a gate)"

# correctness: real bug-catching for the bash. -x follows `source`d files.
shellcheck:
	shellcheck -x $(SCRIPTS)

# never-leak guard: no real UUIDs / home paths / tokens; placeholders intact.
secrets:
	./scripts/check-secrets.sh

# docs hygiene: code-fence languages, blank lines around fences (config in
# .markdownlint.jsonc — line-length & inline-HTML are off by house style).
#
# markdownlint-cli is a NODE-VERSION-SCOPED npm global: bump the node pin in a
# .tool-versions above this repo and the binary silently disappears, so the whole
# gate dies on a bare `make: *** [markdown] Error 127` that says nothing about what
# to install. Fall back to npx at CI's pinned version (.github/workflows/ci.yml), and
# if even that is unavailable, say exactly what to install instead of exiting 127.
MDLINT_VERSION := 0.47.0
markdown:
	@if command -v markdownlint >/dev/null 2>&1; then 	  echo "markdownlint $(MD)"; markdownlint $(MD); 	elif command -v npx >/dev/null 2>&1; then 	  echo "markdownlint not on PATH (node version switch?) — falling back to npx markdownlint-cli@$(MDLINT_VERSION)"; 	  npx --yes markdownlint-cli@$(MDLINT_VERSION) $(MD); 	else 	  echo "markdownlint-cli@$(MDLINT_VERSION) is missing and npx is unavailable." >&2; 	  echo "  npm install -g markdownlint-cli@$(MDLINT_VERSION)     # per node version" >&2; 	  echo "  mise use -g npm:markdownlint-cli@$(MDLINT_VERSION)    # survives a node switch" >&2; 	  exit 1; 	fi

# packaging: the committed Homebrew formula must agree with VERSION. Offline and
# tolerant of "no formula yet" — the formula hashes a tag, so it cannot exist
# before the release it describes.
formula:
	@./scripts/make-formula.sh --check

# every tag becomes a GitHub Release whose body is VERSION's CHANGELOG section
# (.github/workflows/release.yml); fail here, before tagging, if it is missing.
notes:
	@./scripts/release-notes.sh --check

# state machines: offline, stub cmux/security/curl, run on Linux CI too.
#   bridge-state  — agent activity markers (⚡/⏳/❓)
#   poller-gate   — Claude usage-poller gating + malformed-value clamping + bare-label resolve
#   codex-poller  — Codex RPC/failure classes + duration routing + sanitized diagnostics
#   amp-poller    — Amp prose parsing + remaining→used inversion + opt-in orb meter
#   amp-bridge    — Amp lifecycle adapter + shared bridge co-tenancy/error semantics
#   install-hooks  — integration isolation + hook merge / preserve + targeted launchd reloads
#   sentinel-setup — provider-window gating + Amp orb opt-in + creation + shortcut layout
#   sentinel-doctor — multi-window resolution + live capability/named-limit diagnostics
#   group-sync     — cmux-group-sync.sh group-name → anchor-title sync (gate / rename / marker / multi-window)
#   zed-bridge     — zed-bridge.sh Zed OSC-title + JSON status sinks (agent markers, notify gating, toggles)
#   open-in-zed    — cmux-open-in-zed.sh cmux→Zed handoff (worktree-aware command composition, modes, exec)
#   usage-tui      — zed-usage-tui.sh terminal-pane meters (bar render, %, dots, provider gating, offline)
#   entrypoint     — cmux-sentinel dispatcher (routing, arg/exit pass-through, brew layout, deploy)
#   formula        — Homebrew formula generator: version agreement, offline --check
#   release-notes  — GitHub Release body from CHANGELOG + which tag may be Latest
#   amp-bridge's adapter compatibility harness uses Node.js (test-only; preinstalled in CI; actual Amp checks use make amp-live)
test: test-local test-upstream

test-upstream:
	bash tests/bridge-state.sh
	bash tests/poller-gate.sh
	bash tests/codex-poller.sh
	bash tests/install-hooks.sh
	bash tests/sentinel-setup.sh
	bash tests/sentinel-doctor.sh
	bash tests/group-sync.sh
	bash tests/zed-bridge.sh
	bash tests/open-in-zed.sh
	bash tests/usage-tui.sh
	bash tests/amp-bridge.sh
	bash tests/amp-poller.sh
	bash tests/entrypoint.sh
	bash tests/formula.sh
	bash tests/release-notes.sh

# health-check the live setup (read-only) — bridge/hooks/launchd/automation/sentinels.
doctor:
	@./bin/cmux-sentinel-doctor.sh

# sidebar PARSE check — only meaningful where cmux exists (local/pre-commit);
# skipped in CI. NB: validate interprets synthetic data but does not mount/layout;
# a green result can still render blank on a live-data branch.
# `cmux sidebar validate` only takes a NAME (it reads ~/.config/cmux/sidebars), so
# validating `workspaces` would check the DEPLOYED copy, not this repo's file — a
# broken repo sidebar could pass while the old deployed one is fine. So stage the
# REPO file under a throwaway name, validate THAT, and remove it. Always reports
# which file was checked.
SIDEBAR_DIR := $(HOME)/.config/cmux/sidebars
sidebar:
	@if command -v cmux >/dev/null 2>&1; then \
		mkdir -p "$(SIDEBAR_DIR)"; \
		tmp="$(SIDEBAR_DIR)/workspaces-makecheck-$$$$.js"; \
		cp sidebars/workspaces.js "$$tmp"; \
		if cmux sidebar validate workspaces-makecheck-$$$$ >/dev/null 2>&1; then \
			rm -f "$$tmp"; echo "sidebar validate: ok ✓ (repo file sidebars/workspaces.js)"; \
		else \
			echo "sidebar validate: FAILED for repo sidebars/workspaces.js" >&2; \
			cmux sidebar validate workspaces-makecheck-$$$$ || true; \
			rm -f "$$tmp"; exit 1; \
		fi; \
	else \
		echo "sidebar: cmux not found — skipping parse check"; \
	fi

# Honest runtime smoke: stages the repo sidebar under a throwaway name, mounts it
# through cmux's live renderer, then waits briefly (or for Return in a terminal).
# Command success is useful but deliberately NOT called a pixel/render assertion.
sidebar-live:
	@./bin/cmux-sidebar-live-smoke.sh

check: ci runtime-js sidebar
lint: check
ci: shellcheck secrets markdown formula notes syntax test   ## CI omits `sidebar` (no cmux on the runner)

# shfmt is OPT-IN, not a gate: the scripts use a deliberately terse one-liner
# style (`die() { echo ...; exit 1; }`) that shfmt would explode. Run this only
# if you intend to adopt shfmt's canonical layout wholesale.
fmt:
	shfmt -w -i 2 -ci $(SCRIPTS)

fmt-check:
	shfmt -d -i 2 -ci $(SCRIPTS)

.PHONY: test-local test-upstream runtime-js syntax

test-local:
	PYTHONPATH=src:scripts python3 -B -m unittest discover -s tests -p 'test_*.py' -v
	node tests/test_sidebar_logic.cjs

runtime-js:
	node tests/check_sidebar_js.cjs

syntax:
	python3 -B -c 'import ast,pathlib; [ast.parse(p.read_text(),filename=str(p)) for folder in ("src","scripts","tests") for p in pathlib.Path(folder).glob("*.py")]'
	node --check sidebars/workspaces.js

.PHONY: amp-live
amp-live:
	CMUX_SENTINEL_TEST_AMP_LIVE=1 bash tests/amp-bridge.sh
