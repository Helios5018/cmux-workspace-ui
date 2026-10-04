#!/usr/bin/env python3
"""Run behavior assertions through the INSTALLED cmux interpreter, without selecting probes.

Each assertion is the sole root view: a false/skipped condition returns no render
node, so `sidebar validate` must fail. This catches silent nil-comparison bugs
that validating the full sidebar (which has other valid views) misses.
"""
import json
from pathlib import Path
import subprocess
import uuid

source = (Path(__file__).resolve().parent.parent / 'sidebars/workspaces.swift').read_text()
helpers = source.split('// ── layout ─')[0]
checks = {
    'saved color present': 'hasWorkspaceColor(["color": "#FFCC66"])',
    'color beats busy state': 'accentColor(["color": "#FFCC66", "title": "⚡ Busy"]) == "#FFCC66"',
    'color visible while idle': 'accentOpacity(["color": "#1565C0", "selected": false]) == 1.0',
    'missing color': '!hasWorkspaceColor([:])',
    'cleared color': '!hasWorkspaceColor(["color": ""])',
    'unset retains working color': 'accentColor(["title": "⚡ Busy"]) == "#87D96C"',
    'Grok week label': 'meterWindow(["title": "grokcredits |22%|"]) == "week"',
    'progress zero is real': 'hasProgress(["progress": ["value": 0.0]])',
    'progress missing': '!hasProgress([:])',
    'progress label': 'hasProgressLabel(["progress": ["value": 0.2, "label": "20%"]])',
    'branch present': 'hasBranch(["branch": "main"])',
    'branch absent': '!hasBranch([:])',
    'PR present': 'hasPR(["pr": ["label": "#123"]])',
    'freshness expired': 'meterIsStale(["description": "sentinel-updated:1"])',
    'freshness absent': '!meterIsStale([:])',
}
name = 'sentinel-probe-' + uuid.uuid4().hex[:8]
probe = Path.home() / '.config/cmux/sidebars' / (name + '.swift')
failed = []
try:
    for title, assertion in checks.items():
        probe.write_text(helpers + '\nAnyView { let clock = ["epoch": 2000]\nif ' + assertion + ' { Text("pass") }\n}\n')
        result = subprocess.run(['cmux', 'sidebar', 'validate', name, '--json'],
                                capture_output=True, text=True, timeout=15)
        report = json.loads(result.stdout)
        passed = result.returncode == 0 and report.get('valid_count') == 1
        print(('PASS ' if passed else 'FAIL ') + title)
        if not passed:
            failed.append(title)
finally:
    probe.unlink(missing_ok=True)
raise SystemExit(bool(failed))
