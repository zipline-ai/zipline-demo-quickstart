#!/usr/bin/env python3
"""Print the privacy-safe lookup key used by the public Zipline demo."""

import argparse
import getpass
import hashlib


def email_hash(email: str) -> str:
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("email cannot be empty")
    return hashlib.sha256(normalized_email.encode("utf-8")).hexdigest()[:8]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Calculate the eight-character email hash used by try.zipline.ai."
    )
    parser.add_argument(
        "email",
        nargs="?",
        help="Email to hash. Omit it to enter the email without shell echo.",
    )
    args = parser.parse_args()

    email = args.email if args.email is not None else getpass.getpass("Email: ")
    try:
        print(email_hash(email))
    except ValueError as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
