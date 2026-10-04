import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sidebar_metadata as metadata


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.rows = [{'id': 'meter', 'title': 'cx7d |20%|', 'index': 1, 'description': 'user note'}]
        self.lock_patch = patch.object(metadata, 'STATE', Path(self.temp.name))
        self.lock_patch.start()
        self.addCleanup(self.lock_patch.stop)
        self.read_patch = patch.object(metadata.subprocess, 'check_output', side_effect=self.read)
        self.write_patch = patch.object(metadata.subprocess, 'run', side_effect=self.write)
        self.read_patch.start()
        self.write_patch.start()
        self.addCleanup(self.read_patch.stop)
        self.addCleanup(self.write_patch.stop)

    def read(self, command, **kwargs):
        if 'list-windows' in command:
            return json.dumps([{'id': 'window'}])
        return json.dumps({'workspaces': self.rows})

    def write(self, command, **kwargs):
        identity = command[command.index('--workspace') + 1]
        row = next(row for row in self.rows if row['id'] == identity)
        row['description'] = command[command.index('--description') + 1]

    def test_both_write_orders_preserve_user_note_and_other_writer(self):
        for reverse in (False, True):
            self.rows[0]['description'] = 'user note'
            operations = [lambda: metadata.stamp(('cx7d',), 42),
                          lambda: metadata.publish({'sessions': []})]
            for operation in operations[::-1] if reverse else operations:
                operation()
            description = self.rows[0]['description']
            self.assertTrue(description.startswith('sentinel-updated:42\nuser note'))
            self.assertEqual(json.loads(description.split(metadata.DATA_MARKER)[1]), {'sessions': []})

    def test_fallback_and_returning_meter_move_carrier(self):
        self.rows = [{'id': 'ordinary', 'title': 'task', 'index': 0, 'description': 'my note'}]
        metadata.publish({'sessions': [{'name': 'build'}]})
        self.assertIn(metadata.DATA_MARKER, self.rows[0]['description'])
        self.rows.append({'id': 'meter', 'title': 'grokcredits', 'index': 1, 'description': ''})
        metadata.publish({'sessions': []})
        self.assertEqual(self.rows[0]['description'], 'my note')
        self.assertIn(metadata.DATA_MARKER, self.rows[1]['description'])

    def test_unchanged_snapshot_does_not_write(self):
        metadata.publish({'sessions': []})
        with patch.object(metadata.subprocess, 'run') as write:
            self.assertFalse(metadata.publish({'sessions': []}))
            write.assert_not_called()

    def test_empty_window_does_not_create_a_workspace(self):
        self.rows = []
        with patch.object(metadata.subprocess, 'run') as write:
            self.assertFalse(metadata.publish({'sessions': []}))
            write.assert_not_called()
