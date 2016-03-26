#!/usr/bin/env python

import subprocess
import os
import sys

from collections import namedtuple
from docopt import docopt
from jinja2 import Template


logger = None
__docopt__ = """
Usage: quay/build.py -r repo -d url -t tag -p robot

Options:
  -r repo --repository repo             repository in form org/reponame
  -d url --dockerfile url               url path to a dockerfile
  -t tag --tag tag                      tag which is used during build
  -p robot --pull-robot robot           pull robot which is used

Details:
    QUAY_ACCESSTOKEN environment variable is required to trigger a build!
"""


def shell_out(command, stdin_data=None, shell='/bin/bash'):
    """
    Basic shell command execution wrapper, returns command output.
    """
    klass_struct = namedtuple('ostruct', 'command output returncode success failed')
    # open a subprocess merging to stdout and stderr
    stdin = None if stdin_data is None else subprocess.PIPE

    proc = subprocess.Popen(command, shell=True,
                            executable=shell,
                            stdin=stdin,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT)

    if stdin_data is not None:
        proc.stdin.write(stdin_data)

    output, _ = proc.communicate()
    return klass_struct(command, output, proc.returncode,
                        proc.returncode == 0, proc.returncode != 0)


def get_payload(**context):
    basedir = os.path.dirname(__file__)
    payload_filepath = os.path.join(os.path.realpath(basedir), '.build-payload')

    with open(payload_filepath, 'r') as stream:
        template = Template(stream.read(), keep_trailing_newline=True)
    return template.render(**context)


def trigger_build(repository, payload_data):
    """Trigger quay.io repository build
    """
    access_token = os.environ.get('QUAYIO_ACCESSTOKEN')
    quayio_apiurl = 'https://quay.io/api/v1/repository'

    if not access_token:
        raise RuntimeError("QUAYIO_ACCESSTOKEN environment variable is required")

    command = ('curl -XPOST', '-H "Content-Type: application/json"',
               '-H "Authorization: Bearer {}"'.format(access_token), '-d @-',
               "{api}/{repository}/build/".format(api=quayio_apiurl.strip('/'),
                                                  repository=repository.strip('/')))

    result = shell_out(' '.join(command), payload_data)
    if result.output:
        print result.output

    if result.failed:
        sys.exit(1)


if __name__ == "__main__":
    args = docopt(__docopt__)

    data = get_payload(archive_url=args['--dockerfile'], tag=args['--tag'],
                       pull_robot=args['--pull-robot'])

    reponame = args['--repository']
    trigger_build(reponame, data)
