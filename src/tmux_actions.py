#!/usr/bin/env python3
"""Authenticated local URL actions; never interpret session names as commands."""
import base64
import hashlib
import hmac
import json
import os
import secrets
import subprocess
from urllib.parse import urlsplit, unquote

from sentinel_config import STATE, TMUX

KEY = STATE / 'tmux-action.key'
PREFIX = 'cmux-sentinel://close/'
IDENTITY_FIELDS = ('id', 'session_created', 'pid', 'socket_path')
EXPANDED = KEY.parent / 'tmux-expanded.json'
PENDING = KEY.parent / 'tmux-close-pending.json'
LAYOUT = KEY.parent / 'sidebar-layout.json'
ACTIONS = ('close', 'toggle', 'request-close', 'confirm-close', 'cancel-close')


def key():
    KEY.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(KEY, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return KEY.read_bytes()
    with os.fdopen(fd, 'wb') as out:
        secret = secrets.token_bytes(32)
        out.write(secret)
    return secret


def identity(row):
    return {field: row[field] for field in IDENTITY_FIELDS}


def action_url(row, action):
    if action not in ACTIONS:
        raise ValueError('Unsupported action')
    values = dict(identity(row), action=action)
    if action == 'confirm-close' and '@lifecycle' in row and '@note' in row:
        values['confirm_digest'] = confirmation_digest(row)
    payload = json.dumps(values, sort_keys=True).encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip('=')
    signature = hmac.new(key(), encoded.encode(), hashlib.sha256).hexdigest()
    return 'cmux-sentinel://' + action + '/' + encoded + '.' + signature


def close_url(row):
    return action_url(row, 'request-close' if requires_confirmation(row) else 'close')


def requires_confirmation(row):
    return (row.get('@lifecycle') in ('persistent', '常驻', '长驻')
            or any(word in row.get('@note', '') for word in ('常驻', '长驻')))


def confirmation_digest(row):
    # The user's confirmation covers exactly the note/lifecycle displayed to them.
    return hashlib.sha256(json.dumps([row.get('@lifecycle', ''), row.get('@note', '')],
                                     ensure_ascii=False).encode()).hexdigest()


def expanded_session():
    return read_state(EXPANDED)


def read_state(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def write_state(path, state):
    tmp = path.with_suffix('.tmp.' + str(os.getpid()))
    try:
        tmp.write_text(json.dumps(state))
        tmp.chmod(0o600)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)


def decode_action(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'cmux-sentinel' or parsed.netloc not in ACTIONS or parsed.query or parsed.fragment:
        raise ValueError('Invalid action URL')
    encoded, signature = parsed.path[1:].rsplit('.', 1)
    expected = hmac.new(key(), encoded.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature, expected):
        raise ValueError('Invalid action signature')
    row = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
    # Bind the purpose to the signature: changing toggle to close must fail.
    if row.get('action') != parsed.netloc:
        raise ValueError('Action mismatch')
    return row


def perform_action(url):
    parsed = urlsplit(url)
    if parsed.scheme == 'cmux-sentinel' and parsed.netloc == 'layout':
        return save_layout(parsed)
    if parsed.scheme == 'cmux-sentinel' and parsed.netloc == 'notepad':
        return False  # Retired notebook links must not modify retained user notes.
    if parsed.scheme == 'cmux-sentinel' and parsed.netloc in ('console', 'terminal'):
        return False  # Retired command routes cannot start workers or create panes.
    row = decode_action(url)
    command = [TMUX, '-S', row['socket_path']]
    live_identity = subprocess.run(command + ['display-message', '-p', '-t', row['id'],
                                         '#{session_id}\t#{session_created}\t#{pid}\t#{socket_path}'],
                              capture_output=True, text=True, timeout=5)
    if live_identity.returncode or live_identity.stdout.rstrip('\n').split('\t') != [row[k] for k in IDENTITY_FIELDS]:
        return False  # Gone or replaced: stale menu is a harmless no-op.
    selected = identity(row)
    action = row['action']
    if action == 'toggle':
        state = {} if expanded_session() == selected else selected
        write_state(EXPANDED, state)
        write_state(PENDING, {})
    elif action == 'cancel-close':
        write_state(PENDING, {})
    else:
        # Check live metadata: a formerly temporary session may now be persistent.
        live = {}
        for field in ('@lifecycle', '@note'):
            result = subprocess.run(command + ['display-message', '-p', '-t', row['id'], '#{' + field + '}'],
                                    capture_output=True, text=True, timeout=5, check=True)
            live[field] = result.stdout.rstrip('\n')
        confirmed = action == 'confirm-close' and (
            row.get('confirm_digest') == confirmation_digest(live)
            or ('confirm_digest' not in row and read_state(PENDING) == selected))
        if action == 'request-close' or (requires_confirmation(live) and not confirmed):
            write_state(EXPANDED, selected)
            write_state(PENDING, selected)
        elif action == 'confirm-close' and not confirmed:
            return False
        else:
            subprocess.run(command + ['kill-session', '-t', row['id']], check=True, capture_output=True, timeout=5)
            if expanded_session() == selected:
                write_state(EXPANDED, {})
            write_state(PENDING, {})
    return True


def save_layout(parsed):
    """Allow only known section preferences; this route cannot run commands."""
    if parsed.query or parsed.fragment or len(parsed.path)>4096:
        raise ValueError('Invalid layout')
    value = json.loads(unquote(parsed.path[1:]))
    if not isinstance(value,dict):
        raise ValueError('Invalid layout object')
    ids = {'usage', 'workspaces', 'tmux'}
    order, collapsed, revision = value.get('order'), value.get('collapsed'), value.get('revision')
    if (not isinstance(order, list) or any(not isinstance(x,str) for x in order) or len(order)!=len(set(order))
            or set(order) != ids or not isinstance(collapsed,dict) or not set(collapsed)<=ids
            or any(type(v) is not bool for v in collapsed.values())
            or type(revision) is not int or not 0<revision<2**53):
        raise ValueError('Invalid layout fields')
    if revision <= read_state(LAYOUT).get('revision', 0):
        return False
    LAYOUT.parent.mkdir(parents=True,exist_ok=True)
    write_state(LAYOUT, {'order':order,
                         'collapsed':collapsed,'revision':revision})
    return True


def close_session(url):
    if decode_action(url)['action'] not in ('close', 'request-close', 'confirm-close'):
        raise ValueError('Expected close action')
    return perform_action(url)
