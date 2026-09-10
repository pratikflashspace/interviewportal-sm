import unittest
from unittest.mock import Mock
from backend.personal_drive import PersonalDrive,DriveError

class PersonalDriveTests(unittest.TestCase):
    def service(self):
        s=Mock()
        s.files.return_value.get.return_value.execute.return_value={'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':True}}
        s.permissions.return_value.list.return_value.execute.return_value={'permissions':[{'type':'user','role':'owner'}]}
        return s
    def test_private_writable_folder(self):
        s=self.service();self.assertTrue(PersonalDrive(s,'folder-example-123').validate_destination())
    def test_public_folder_rejected(self):
        for kind in ('anyone','domain'):
            s=self.service();s.permissions.return_value.list.return_value.execute.return_value={'permissions':[{'type':kind}]}
            with self.assertRaises(DriveError):PersonalDrive(s,'folder-example-123').validate_destination()
    def test_nonfolder_and_readonly_rejected(self):
        for value in ({'mimeType':'video/webm'},{'mimeType':'application/vnd.google-apps.folder','capabilities':{'canAddChildren':False}}):
            s=self.service();s.files.return_value.get.return_value.execute.return_value=value
            with self.assertRaises(DriveError):PersonalDrive(s,'folder-example-123').validate_destination()
    def test_errors_do_not_expose_provider_detail(self):
        s=self.service();s.files.return_value.get.return_value.execute.side_effect=RuntimeError('private-token')
        with self.assertRaises(DriveError) as result:PersonalDrive(s,'folder-example-123').validate_destination()
        self.assertNotIn('private-token',str(result.exception))
    def test_ambiguous_create_reconciles_exact_identity(self):
        s=self.service();drive=PersonalDrive(s,'folder-example-123');drive.validate_destination=Mock(return_value=True)
        s.files.return_value.create.return_value.execute.side_effect=TimeoutError('secret')
        recording='a'*32
        s.files.return_value.get.return_value.execute.return_value={'id':'fixed','parents':['folder-example-123'],'appProperties':{'recording_id':recording}}
        self.assertEqual(drive.initialize_file('fixed',recording)['id'],'fixed')
        s.files.return_value.get.return_value.execute.return_value={'id':'fixed','parents':['other'],'appProperties':{'recording_id':recording}}
        with self.assertRaises(DriveError):drive.initialize_file('fixed',recording)
