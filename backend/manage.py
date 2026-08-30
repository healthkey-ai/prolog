#!/usr/bin/env python
import os
import sys


def main():
    # Local commands default to the development settings (DEBUG on, development
    # key accepted). A deployment is recognised by its environment: once either
    # DEBUG or SECRET_KEY is set, the production settings apply, so a host cron
    # job that exports SECRET_KEY but forgets DEBUG never runs in debug mode.
    if "DEBUG" not in os.environ and "SECRET_KEY" not in os.environ:
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "prolog.settings_dev")
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "prolog.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
