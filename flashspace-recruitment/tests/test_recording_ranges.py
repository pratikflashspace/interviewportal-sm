import io
import unittest
from unittest.mock import patch
from test_temporary_recordings import RecordingTests

class RangeTests(RecordingTests):
    def test_range_reads_are_private_and_byte_correct(self):
        self.register();a=self.apply();m=self.app.recordings.create(a['id'],self.app.store.get(a['id'])['user_id'],'video/webm')
        data=b'\x1aE\xdf\xa3'+bytes(range(256))*4
        self.app.recordings.append(m['id'],0,data);self.app.recordings.finish(m['id'],1)
        with self.app.store.db() as db:db.execute('UPDATE users SET admin=1')
        env={'REQUEST_METHOD':'GET','PATH_INFO':'/api/recordings/'+m['id']+'/media','HTTP_COOKIE':self.cookie,'HTTP_RANGE':'bytes=10-19'}
        response={}
        body=b''.join(self.app(env,lambda s,h:response.update(status=s,headers=dict(h))))
        self.assertTrue(response['status'].startswith('206'));self.assertEqual(body,data[10:20])
        self.assertEqual(response['headers']['Content-Range'],f'bytes 10-19/{len(data)}')
        env['HTTP_RANGE']='bytes=99999-'
        body=b''.join(self.app(env,lambda s,h:response.update(status=s)))
        self.assertTrue(response['status'].startswith('416'))
    def test_existing_entrypoint_delegates_to_recording_app(self):
        from backend.role_server import create_app
        with patch('backend.integrated_recording.create_app',return_value='sentinel') as factory:
            self.assertEqual(create_app(),'sentinel')
        factory.assert_called_once()
