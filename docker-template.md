# docker-template.py

## Usage

 - First you need to create variant template files or at least the default one (*Dockerfile.template*).
 - Second you need to create versions directories (such as centos6, centos7), aka `mkdir centos6 centos7 trusty wheezy etc`.
 - Third run: `docker-template.py`

For available options invoke script with `--help` option.

```
Usage: update-template.py [-q] [-d] [-v] [-e env]... [-c template.yaml] [-s version]...
                          [<version> ...] [--] [<variant> ...]

Options:
  -c template.yaml --config_path template.yaml  path to yaml config file (docker-template.yaml).
  -q --quiet                                    silence all logging output.
  -v --verbose                                  shows debug output.
  -s --skip-version version                     skip generation of Dockerfiles for given versions.
  -d --dry-run                                  show execution trace, but don't take any actions.
  -e --env envhash                              variable in form "key=value" used in the rendering.
```

The script task is rendering all the provided `version/variant/Dockerfile` using **docker-jinja**, passing through required environment.

## docker-template.py configuration and (docker-template.yaml)

Path to `docker-template.yaml` can be overridden using `-c` option.

 - **skip-version** (`-s/--skip-version` on CLI) is a list of versions which will be omitted from the operation.
 - **env** (`-e/--env` on CLI) is a hash of variables to be passed to **docker-jinja**, while it's list `-e var=value` on the command line.

**skip-version** and **env** from *docker-template.yaml* with options given via CLI, thus the prior values are overridden. **docker-template.py** script passes several important variables to **docker-jinja** which are:

 - **image** - is equal to current working directory name (while still can be overridden using **env**).
 - **version** - docker image version which is being rendered.
 - **variant** - docker image version variant which is being rendered.

Also let's have a look at an example`docker-template.yaml`:

```yaml
---
env:
  hello: world
  registry: quay.io/dennybaa/
mapping:
  _default:
    - fedora*
  scm:
    - centos{6,7}
  # Completely skip variant generation
  curl: null
skip-version:
  - junk-dir
  - ~*
```

Not yet mentioned configuration, but though very important is **mapping**, it defines strict mapping between *variant* and  *versions* available for this particular *variant*. If you noticed versions lists inside **mapping** or **skip-version**, you might have guessed that they support bash globing. For example if there are pre-created directories `fedora22, fedora23, fedora24` then default variant will be generated for all of them, but not other versions like centos etc.

When no particular mapping is provided all available *variants* will be generated for each version (of course excluding those set by **skip-version**.
