#!/usr/bin/env python

import glob
import logging
import subprocess
import tempfile
import os
import sys

from collections import namedtuple
from docopt import docopt
from mergedict import ConfigDict


import yaml

logger = None
__docopt__ = """
Usage: update-template.py [-q] [-d] [-v] [-e env]... [-c template.yaml] [-s version]...
                          [<version> ...] [--] [<variant> ...]

Options:
  -c template.yaml --config_path template.yaml  path to yaml config file (docker-template.yaml).
  -q --quiet                                    silence all logging output.
  -v --verbose                                  shows debug output.
  -s --skip-version version                     skip generation of Dockerfiles for given versions.
  -d --dry-run                                  show execution trace, but don't take any actions.
  -e --env envhash                              variable in form "key=value" used in the rendering.
"""


def parse_args():
    """
    Parse argument list using docopt.
    """
    args = docopt(__docopt__)
    args_list = args['<version>']
    # docopt is not able to handle this config scenario,
    # so we help it to process positional arguments.
    args['--'] = '--' in args_list
    if args['--']:
        split_index = args_list.index('--')
        args['<version>'] = args_list[0:split_index]
        args['<variant>'] = args_list[split_index + 1:]

    return args


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


def dirglob(globstr):
    """Perform bash glob operation
    """
    res = shell_out('ls -1d {}'.format(globstr))
    if res.success:
        return filter(None, res.output.split("\n"))
    else:
        return []


class Log(object):
    """
    Setup basic console logging.
    """
    logger = None

    class OutputFormatter(logging.Formatter):
        def format(self, record):
            fmt = '{levelname}: ' if record.levelno != logging.INFO else ''
            fmt = fmt + '{msg}'
            msg = fmt.format(**vars(record))
            return msg % record.args

    @staticmethod
    def console_logger(level=logging.ERROR, name=__name__):
        if Log.logger is not None:
            return Log.logger

        _logger = logging.getLogger(name)
        console = logging.StreamHandler()
        console.setLevel(logging.DEBUG)
        formatter = Log.OutputFormatter('%(levelname)s: %(message)s')
        console.setFormatter(formatter)
        _logger.addHandler(console)
        # set logger level
        _logger.setLevel(level)
        Log.logger = _logger
        return Log.logger


class CLIOpts(object):
    """
    Template update script options constructed from docopt command line args.
    """

    options = None
    default_options = {
        'config_path': 'template.yaml'
    }

    @staticmethod
    def get():
        if CLIOpts.options is not None:
            return CLIOpts.options
        CLIOpts()

        log = Log.console_logger(CLIOpts.options['loglevel'])
        log.debug("CLI options: %s", str(CLIOpts.options))
        return CLIOpts.options

    def __init__(self):
        self.args = parse_args()
        CLIOpts.options = ConfigDict(CLIOpts.default_options)
        CLIOpts.options.merge(self.cli_options())
        CLIOpts.options['loglevel'] = self.get_loglevel()

    def cli_options(self):
        """Construcrt options dict from parsed command line options.
        """
        options = {}
        for k, v in self.args.items():
            # Remove dashes from key name '--'
            k = k if not k.startswith('--') else k[2:]
            options[k] = v
        options.pop('', None)
        options['versions'] = options.pop('<version>', [])
        options['variants'] = options.pop('<variant>', [])
        return ConfigDict(options)

    def get_loglevel(self):
        """Evaluate loglevel"""
        if self.args['--verbose']:
            return logging.DEBUG
        else:
            return logging.INFO


class TemplateConfig(object):
    """
    Class loads template.yaml config.
    """
    log = Log.console_logger(CLIOpts.get()['loglevel'])

    def __init__(self):
        self.cli = CLIOpts.get()
        self._config_path = None
        self._data = None

    @property
    def config_path(self):
        """YAML config file path (default: docker-template.yaml)
        """
        if self._config_path is not None:
            return self._config_path

        config_path = self.cli['config_path'] or 'docker-template.yaml'
        config_path = os.path.join(os.getcwd(), config_path)
        self._config_path = os.path.normpath(config_path)
        return self._config_path

    @property
    def data(self):
        """ Data loaded from config.yml file
        """
        if self._data is not None:
            return self._data

        data = {}
        try:
            data = yaml.load(open(self.config_path, 'r'))
        except (IOError, OSError) as e:
            # config may not exist, so skip it gracefully.
            self.log.error("Unable to load config file!")
            self.log.error("%s", e)
        except yaml.YAMLError as e:
            self.log.error("Unable to parse config file!")
            self.log.error("%s", e)
            sys.exit(1)

        self._data = ConfigDict(data)
        return self._data


class UpdateDockerfiles(object):
    log = Log.console_logger(CLIOpts.get()['loglevel'])

    def __init__(self):
        # Get cli options and conver env=value list to dict
        cliopts = CLIOpts().get()
        cliopts['env'] = self._convert_envlist(cliopts.get('env', []))

        self.config = TemplateConfig().data
        self._variant_list = None
        self._version_list = None
        self._djinja_conffile = None

        # cliopts override template config default values
        self.config.merge(cliopts)
        self.update_mapping()

    def _convert_envlist(self, env_args):
        """Split env=value list into dict env: value
        """
        envhash = {}
        self.log.debug("Converting env arg list to hash, given: %s", env_args)
        for env in env_args:
            try:
                k, v = env.split('=')
                envhash[k] = v
            except ValueError:
                self.log.error("Argument -e (--env) expects value in form key=value, "
                               "you passed: %s", env)
                sys.exit(1)

        return envhash

    def update_mapping(self):
        """Run bash glob for variant: versions
        """
        glob_dict = {}
        mapping = self.config.get('mapping') or {}
        for variant, versions in mapping.items():
            # Change _default variant
            if variant == '_default':
                variant = ''

            # save mapping if mapping:variant mapped to null
            if versions is None:
                glob_dict[variant] = None
                continue
            # no mapping provided
            elif not versions:
                continue
            versions = [dirglob(v) for v in versions]
            # flatten versions list
            glob_dict[variant] = [i for sublist in versions for i in sublist]

        self.log.debug("Mapping after bash globing: %s", glob_dict)
        self.config['mapping'] = glob_dict

    @property
    def version_list(self):
        """Calculate version list to be updated, based on versions available and
           versions which should be skipped.
        """
        if self._version_list is not None:
            return self._version_list

        # Favour versions given set via cli, otherwise do directory glob
        if self.config['versions']:
            version_directories = self.config['versions']
            self.log.debug('Version list overrided from CLI!')
        else:
            version_directories = [d for d in glob.glob('*') if os.path.isdir(d)]

        skip_versions = []
        for skip_globstr in self.config['skip-version']:
            skip_versions = skip_versions + dirglob(skip_globstr)

        self._version_list = [i for i in version_directories if i not in skip_versions]
        self.log.debug("Target versions: %s", str(self._version_list))
        return self._version_list

    @property
    def variant_list(self):
        """Get list of available variants, based on variants given via cli
           or glob
        """
        if self._variant_list is not None:
            return self._variant_list

        if self.config['variants']:
            variant_list = self.config['variants']
            self.log.debug('Variant list overrided from CLI!')
        else:
            variant_list = [f for f in glob.glob('Dockerfile.template*') if os.path.isfile(f)]
            variant_list = [f.replace('Dockerfile.template', '').strip('-') for f in variant_list]

        # Change _default variant to its actual value (empty string)
        if '_default' in variant_list:
            ri = variant_list.index('_default')
            variant_list[ri] = ''

        self._variant_list = variant_list
        self.log.debug("Target variants: %s", self._variant_list)
        return self._variant_list

    def process_dockerfiles(self):
        """Process dockerfiles accoriding to given configuration.
        """
        default = object()
        for variant in self.variant_list:
            mapped_versions = self.config['mapping'].get(variant, default)
            if mapped_versions is default:
                # mapping:variant doesn't exist, this means that
                # variant is valid for all versions.
                mapped_versions = self.version_list
            elif mapped_versions is None:
                self.log.debug("No versions will be processed for >%s<", variant)
                continue

            vn = variant or '_default'
            self.log.debug("Variant `%s' mapped to versions: %s", vn, mapped_versions)

            for version in mapped_versions:
                self.update_dockerfile(version, variant)

    @property
    def djinja_conffile(self):
        """Generate temporary docker djinja config
        """
        if self._djinja_conffile is not None:
            return self._djinja_conffile

        tmpfile = tempfile.NamedTemporaryFile()
        data = ConfigDict({
            'datasources': self.config.get('datasources', {})
        })
        data.merge(self.config['env'])

        try:
            tmpfile.write(yaml.dump(dict(data.viewitems()), default_flow_style=True))
            tmpfile.seek(0)
            self.log.debug("Tempfile content written: \n%s", tmpfile.read())
        except (IOError, OSError) as e:
            # config may not exist, so skip it gracefully.
            self.log.error("Unable to write docker djinja config file!")
            self.log.error("%s", e)
            sys.exit(1)

        self._djinja_conffile = tmpfile
        return self._djinja_conffile

    def update_dockerfile(self, version, variant):
        """Update dockerfile if rendered content is changed.
        """
        target_path = os.path.join(os.getcwd(), version, variant, 'Dockerfile')
        djcmd, opts = self.docker_djinja_command(version, variant)

        # Run docker djinja
        self.log.debug("update command: `%s'", djcmd)
        result = shell_out(djcmd)
        if result.failed:
            self.log.error(result.output)
            sys.exit(1)

        # Compare just rendered temp file and target file.
        diff_path = None
        if not os.path.isfile(target_path):
            tmp = tempfile.NamedTemporaryFile(prefix='Dockerfile-{}_{}'.format(version, variant))
            diff_path = tmp.name
            tmp.close()
            shell_out('touch {}'.format(diff_path))

        # diff exits with 1 if files differ
        diff = shell_out('diff -u {} {}'.format(diff_path or target_path, opts['target']))
        if diff_path:
            shell_out('rm -f {}'.format(diff_path))

        if diff.failed:
            relpath = os.path.join(opts['image'], version, variant, 'Dockerfile')
            if self.config['quiet']:
                self.log.info(relpath)
            else:
                self.log.info('***** content update %s *****', relpath)
                self.log.info("%s", diff.output)

            if not self.config['dry-run']:
                self.log.debug("Creating parent directories for `%s' using mkdir -p.", target_path)
                shell_out('mkdir -p {}'.format(os.path.dirname(target_path)))

                self.log.debug("Moving rendered Dockerfile to target path %s", target_path)
                shell_out('mv {} {}'.format(opts['target'], target_path))
        else:
            self.log.debug("No content to update!")

        # Clean up
        shell_out('rm -f {}'.format(opts['target']))

    def docker_djinja_command(self, version, variant):
        """Docker djinja invocation string and options, tuple returned.
        """
        cwd = os.getcwd()
        dj = "dj -q -c {config} -d {template} -o {target} " \
             "-e version={version} -e variant={variant} -e image={image}"

        tmp = tempfile.NamedTemporaryFile(prefix="docker-rendred-{}_{}-".format(version, variant))
        target_temp = tmp.name
        tmp.close()

        # Set template path
        template = 'Dockerfile.template'
        if variant:
            template = template + '-{}'.format(variant)
        template = os.path.join(cwd, template)

        opts = {
            'config': self.djinja_conffile.name,
            'template': template,
            'target': target_temp,
            'version': version,
            'variant': variant or '_default',
            'image': self.config['env'].get('image', os.path.basename(cwd))
        }
        return (dj.format(**opts), opts)


if __name__ == "__main__":
    update = UpdateDockerfiles()
    update.process_dockerfiles()
