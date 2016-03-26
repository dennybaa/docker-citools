#!/usr/bin/env python

import logging
import subprocess
import sys

from collections import namedtuple
from docopt import docopt

# Logger output goes to console, ie it's not reaching STDOUT
log = logging.getLogger(__name__)
console = logging.StreamHandler()
console.setLevel(logging.INFO)
log.addHandler(console)
log.setLevel(logging.INFO)


__docopt__ = """
Usage: get-updated-dockerfiles.py <version-diff> [--] [<variant> ...]
"""


def shell_out(command, shell='/bin/bash'):
    """
    Basic shell command execution wrapper, returns command output.
    """
    klass_struct = namedtuple('ostruct', 'command output returncode success failed')
    # open a subprocess merging to stdout and stderr
    proc = subprocess.Popen(command, shell=True,
                            executable=shell,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)
    output, _ = proc.communicate()
    return klass_struct(command, output, proc.returncode,
                        proc.returncode == 0, proc.returncode != 0)


def updated_dockerfiles(revision_diff):
    """Return list of updated dockerfiles from_rev...to_rev or relative revision offset HEAD~n
    """
    git_diff = shell_out("git diff --name-only {} ./ | grep 'Dockerfile$'".format(revision_diff))
    if git_diff.failed:
        log.info("No dockerfiles have been updated!")
        sys.exit(0)

    return git_diff.output.strip().split("\n")


def order_files_by_variant(dockerfiles_list, variant_order):
    """Sort Dockerfile list ordered by variant, following convention
       {{ version }}/{{ variant }}/Dockerfile
    """
    def compare(path_a, path_b):
        split_a = path_a.replace('/Dockerfile', '').split('/')
        split_b = path_b.replace('/Dockerfile', '').split('/')
        # update list with _default variant, i.e. equal to ''
        for l in (split_a, split_b):
            if len(l) < 2:
                l.append('_default')

        # if versions are equal compare by variant
        versions_compared = cmp(split_a[0], split_b[0])
        if versions_compared == 0:
            return cmp(variant_order.index(split_a[1]), variant_order.index(split_b[1]))
        else:
            return versions_compared

    # sort using our custom order method
    dockerfiles_list.sort(compare)
    return dockerfiles_list


if __name__ == "__main__":
    args = docopt(__docopt__)
    updated_files = updated_dockerfiles(args['<version-diff>'])

    if not args['<variant>']:
        if updated_files:
            print "\n".join(updated_files)
    else:
        ordered_list = order_files_by_variant(updated_files, args['<variant>'])
        print "\n".join(ordered_list)
