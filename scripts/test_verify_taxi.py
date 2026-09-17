import unittest
from verify_taxi import verify


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.expected = [{'keys': {'id': 0}, 'features': {'ride_id': 'a', 'distance': 1.25}}]
        self.payload = {'results': [{'entityKeys': {'id': 0}, 'status': 'Success',
                                     'features': {'ride_id': 'a', 'distance': 1.25}}]}

    def test_equal(self):
        verify(self.payload, self.expected)

    def test_wrong_value(self):
        self.payload['results'][0]['features']['distance'] = 2.5
        with self.assertRaises(ValueError):
            verify(self.payload, self.expected)

    def test_partial_failure(self):
        self.payload['results'][0]['status'] = 'Failure'
        with self.assertRaises(ValueError):
            verify(self.payload, self.expected)

    def test_missing_record(self):
        with self.assertRaises(ValueError):
            verify({'results': []}, self.expected)
