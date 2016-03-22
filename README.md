# docker-citools

## docker-template.py

Template update script uses [docker-djinja](https://github.com/dennybaa/docker-jinja). To generate multiple Dockerfiles based on the following structure convention:

```
├── .
├── centos6
│   ├── curl
│   │   └── Dockerfile
│   ├── Dockerfile
│   └── scm
│       └── Dockerfile
├── centos7
│   ├── curl
│   │   └── Dockerfile
│   └── scm
│       └── Dockerfile
├── Dockerfile.template
├── Dockerfile.template-curl
├── Dockerfile.template-scm
├── docker-template.yaml
```

Script reads directories in the current working directory of dockerfiles project such as `centos6`, `centos7` which are known as versions (docker image versions). Each version may have different variants which are defined by `Dockerfile.template[-variant].


Update process based on directory structure convention, cycles through all provided `version/variant/Dockerfile` (creates variant directories if they don't exist) and invokes `dj`.  Making it possible using automatic interpolation such as:

```
FROM {{ registry }}{{ image }}:{{ version }}-scm

RUN yum -y install \
    autoconf \
    automake \
    bzip2 \
```

For details see [docker-template.md](docker-template.md).

# Setup

To download and install project dependencies you can run a shortcut:

```
# System-wide install
wget -qO- https://raw.githubusercontent.com/dennybaa/docker-citools/master/setup | sudo sh -s [revision]
```

Mind that that git and pip binaries should be present on the system.
