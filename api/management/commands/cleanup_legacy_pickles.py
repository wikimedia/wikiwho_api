# -*- coding: utf-8 -*-
"""
Management command to delete legacy flat-path pickle files that have already
been migrated to the new subdirectory structure.

A legacy pickle is a file at:
    <PICKLE_FOLDER>/<page_id>.p   (old flat layout)

A migrated pickle is a file at:
    <PICKLE_FOLDER>/<subdirectory>/<page_id>.p   (new subdirectory layout)

Only legacy files that satisfy ALL of the following are deleted:
  - Older than --min-age-days (default: 7)
  - A corresponding new-format pickle already exists

Any legacy pickle whose new-format counterpart is missing is left alone;
WikiWho will regenerate it from the action API on the next request.

Usage:
    python manage.py cleanup_legacy_pickles
    python manage.py cleanup_legacy_pickles --language en --min-age-days 14 --dry-run
"""
import os
import re
import time

from django.core.management.base import BaseCommand

from api.utils_pickles import get_pickle_folder, get_pickle_path


class Command(BaseCommand):
    help = "Delete legacy flat-path pickle files that have been migrated to subdirectory layout"

    def add_arguments(self, parser):
        parser.add_argument(
            "--language",
            default="en",
            help="Wiki language code (default: en)",
        )
        parser.add_argument(
            "--min-age-days",
            type=int,
            default=7,
            dest="min_age_days",
            help="Only delete legacy files older than this many days (default: 7)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Print what would be deleted without actually deleting",
        )

    def handle(self, *args, **options):
        language = options["language"]
        min_age_days = options["min_age_days"]
        dry_run = options["dry_run"]

        pickle_folder = get_pickle_folder(language)
        if not os.path.isdir(pickle_folder):
            self.stderr.write("Pickle folder not found: {}".format(pickle_folder))
            return

        cutoff = time.time() - min_age_days * 86400
        legacy_pattern = re.compile(r"^(\d+)\.p$")

        found = deleted = skipped_no_new = skipped_too_new = 0

        for entry in os.scandir(pickle_folder):
            if not entry.is_file():
                continue
            match = legacy_pattern.match(entry.name)
            if not match:
                continue

            found += 1
            page_id = int(match.group(1))

            # skip files that are too recent
            if entry.stat().st_mtime > cutoff:
                skipped_too_new += 1
                continue

            # skip if the new-format pickle doesn't exist yet
            new_path = get_pickle_path(page_id, language)
            if not os.path.exists(new_path):
                skipped_no_new += 1
                continue

            if dry_run:
                self.stdout.write("[dry-run] would delete {}".format(entry.path))
            else:
                try:
                    os.remove(entry.path)
                    self.stdout.write("Deleted {}".format(entry.path))
                except OSError as e:
                    self.stderr.write("Failed to delete {}: {}".format(entry.path, e))
                    continue

            deleted += 1

        self.stdout.write(
            "\nDone. Found={} deleted={} skipped(too_new)={} skipped(no_new_format)={}{}".format(
                found, deleted, skipped_too_new, skipped_no_new,
                " [dry-run]" if dry_run else "",
            )
        )
