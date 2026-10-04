#!/usr/bin/env python3
"""Explicit Swift compatibility renderer; the JS worker never rewrites source."""
import os
from pathlib import Path
from sentinel_config import SIDEBAR_DIR
from tmux_actions import action_url, close_url, expanded_session, identity, read_state, PENDING

SIDEBAR = SIDEBAR_DIR / 'workspaces.swift'
BEGIN = '// BEGIN GENERATED TMUX PANEL'
END = '// END GENERATED TMUX PANEL'

def swift_string(value):
    # Never allow notes/names to become Swift interpolation or source code.
    value = ''.join(c if c >= ' ' else ' ' for c in str(value))
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"') + '"'


def text_view(value, size=12, color="#ECF2FA", bold=False):
    result = f'Text({swift_string(value)}).font(.system(size: {size}, design: .monospaced)).foregroundColor("{color}")'
    return result + ('.bold()' if bold else '')


def detail(label, value, color="#ECF2FA"):
    return [
        '        VStack(alignment: .leading, spacing: 3) {',
        '          ' + text_view(label, 10, "#AEBED1"),
        '          ' + text_view(value, 12, color) + '.multilineTextAlignment(.leading)',
        '        }',
    ]


def render(rows):
    expanded = expanded_session()
    pending = read_state(PENDING)
    lines = [BEGIN, 'func tmuxPanel() -> some View {',
             '  VStack(alignment: .leading, spacing: 6) {', '    Divider()',
             '    HStack {',
             '      ' + text_view("TMUX", 11, "#C2D6EF", True),
             '      Spacer()',
             '      ' + text_view(str(len(rows)), 11, "#AEBED1"),
             '    }.padding(9)']
    if not rows:
        lines.append('    ' + text_view("暂无 tmux 会话", 12, "#AEBED1") + '.padding(9)')
    for row in rows:
        name = row['session_name']
        opened = expanded == identity(row)
        lifecycle = {'persistent': '长驻', 'temporary': '临时'}.get(row['@lifecycle'], row['@lifecycle'] or '未标注')
        tint = '#99D98C' if row['@lifecycle'] == 'persistent' else '#FFD187'
        chevron = 'chevron.down' if opened else 'chevron.right'
        lines += ['    VStack(alignment: .leading, spacing: 0) {',
                  f'      Button(action: {{ openURL({swift_string(action_url(row, "toggle"))}) }}) {{',
                  '        HStack(alignment: .top, spacing: 8) {',
                  f'          Image(systemName: "{chevron}").font(.system(size: 10)).foregroundColor("#8DD8FF").frame(width: 12)',
                  '          ' + text_view(name, 12, '#F0F5FC', True)
                  + ('.multilineTextAlignment(.leading)' if opened else '.lineLimit(1).truncationMode(.tail)'),
                  '          Spacer()',
                  '        }.padding(9)',
                  f'        .background {{ RoundedRectangle(cornerRadius: 6).foregroundColor("{"#34485E" if opened else "#293445"}") }}',
                  f'      }}.help({swift_string(name)})']
        if opened:
            lines += ['      VStack(alignment: .leading, spacing: 12) {']
            lines += detail('备注', row['@note'] or '未填写备注')
            lines += detail('项目', row['@project'] or '未标注')
            lines += ['        HStack(spacing: 8) {',
                      '          ' + text_view(lifecycle, 11, tint, True),
                      '          Spacer()',
                      '          ' + text_view('端口 ' + (row['@port'] or '无标注'), 11, '#8DD8FF'),
                      '        }',
                      '        ' + text_view(f"{row['session_windows']} 个窗口 · {row['session_attached']} 个连接", 11, '#B5C6D9'),
                      '        Divider()']
            if pending == identity(row):
                lines += [
                    '        ' + text_view('确认关闭这个常驻会话？', 12, '#FFD187', True),
                    '        ' + text_view('该会话的所有窗口和任务将结束。', 11, '#D6E1F0'),
                    '        HStack(spacing: 8) {',
                    f'          Button(action: {{ openURL({swift_string(action_url(row, "confirm-close"))}) }}) {{',
                    '            ' + text_view('确认关闭', 12, '#FFAAA5', True) + '.padding(8)',
                    '              .background { RoundedRectangle(cornerRadius: 5).foregroundColor("#493440") }',
                    '          }',
                    f'          Button(action: {{ openURL({swift_string(action_url(row, "cancel-close"))}) }}) {{',
                    '            ' + text_view('取消', 12, '#F0F5FC') + '.padding(8)',
                    '              .background { RoundedRectangle(cornerRadius: 5).foregroundColor("#3A4D64") }',
                    '          }',
                    '        }',
                ]
            else:
                lines += [f'        Button(action: {{ openURL({swift_string(close_url(row))}) }}) {{',
                      '          HStack(spacing: 6) {',
                      '            Image(systemName: "xmark").font(.system(size: 11)).foregroundColor("#FFAAA5")',
                      '            ' + text_view('关闭会话', 12, '#FFAAA5', True),
                      '            Spacer()',
                      '          }.padding(8)',
                      '          .background { RoundedRectangle(cornerRadius: 5).foregroundColor("#493440") }',
                      '        }']
            lines += ['      }.padding(10)']
        lines += ['    }',
                  '    .background { RoundedRectangle(cornerRadius: 6).foregroundColor("#263345") }']
    lines += ['  }', '}', END]
    return '\n'.join(lines)


def update(path=SIDEBAR):
    from tmux_sidebar import sessions
    original = path.read_text()
    if original.count(BEGIN) != 1 or original.count(END) != 1:
        raise RuntimeError('tmux panel markers missing or duplicated')
    before, rest = original.split(BEGIN)
    _, after = rest.split(END)
    content = before + render(sessions()) + after
    if content == original:
        return False
    tmp = path.with_name('.' + path.name + '.tmux-' + str(os.getpid()))
    try:
        tmp.write_text(content)
        tmp.chmod(path.stat().st_mode & 0o777)
        tmp.replace(path)
    finally:
        tmp.unlink(missing_ok=True)
    return True  # cmux watches the sidebar directory and hot-reloads changes.
