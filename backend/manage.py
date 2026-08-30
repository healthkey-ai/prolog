#!/usr/bin/env python
import os
import sys


def main():
    # Local commands default to the development settings (DEBUG on, development
    # key accepted); deployments set DJANGO_SETTINGS_MODULE/DEBUG explicitly.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "prolog.settings_dev")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
