"""Check every expected taxi feature through the deployed GroupBy HTTP API."""
import argparse
import json
import math
import os
from urllib.parse import quote
from urllib.request import Request, urlopen


def verify(payload, expected):
    results = payload.get('results', [])
    if len(results) != len(expected):
        raise ValueError('Response count does not match requested entity count')
    for result, record in zip(results, expected):
        if result.get('status') != 'Success' or result.get('entityKeys') != record['keys']:
            raise ValueError(f"Lookup failed or returned wrong keys: {record['keys']}")
        actual = result.get('features') or {}
        for name, value in record['features'].items():
            received = actual.get(name)
            if isinstance(value, float):
                matches = isinstance(received, (int, float)) and math.isclose(
                    received, value, rel_tol=1e-9, abs_tol=1e-9)
            else:
                matches = type(received) is type(value) and received == value
            if not matches:
                raise ValueError(f"Feature mismatch for {record['keys']}: {name}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected', required=True)
    parser.add_argument('--group-by', required=True)
    parser.add_argument('--host', default='https://try.zipline.ai/services/fetcher')
    args = parser.parse_args()
    with open(args.expected) as source:
        expected = json.load(source)
    if len(expected) != 500 or len({row['keys']['id'] for row in expected}) != 500:
        raise ValueError('Expected exactly 500 unique entity IDs')
    headers = {'Content-Type': 'application/json'}
    if os.environ.get('ZIPLINE_TOKEN'):
        headers['Authorization'] = 'Bearer ' + os.environ['ZIPLINE_TOKEN']
    endpoint = args.host.rstrip('/') + '/v1/fetch/groupby/' + quote(args.group_by, safe='')
    for offset in range(0, len(expected), 100):
        batch = expected[offset:offset + 100]
        request = Request(endpoint, data=json.dumps([row['keys'] for row in batch]).encode(),
                          headers=headers, method='POST')
        with urlopen(request, timeout=30) as response:
            verify(json.load(response), batch)
    print('Verified all 500 taxi records and every expected feature value.')


if __name__ == '__main__':
    main()
