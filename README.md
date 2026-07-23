ISA REST service
================
<img align="right" src="http://www.isa-tools.org/wp-content/themes/isatools-wp-theme/img/footer_logo.svg">
The open source ISA metadata tracking tools help to manage an increasingly diverse set of life science, environmental and biomedical experiments that employing one or a combination of technologies.

Built around the ‘Investigation’ (the project context), ‘Study’ (a unit of research) and ‘Assay’ (analytical measurement) general-purpose Tabular format, the ISA tools helps you to provide rich description of the experimental metadata (i.e. sample characteristics, technology and measurement types, sample-to-data relationships) so that the resulting data and discoveries are reproducible and reusable.

The ISA REST service is a RESTful web service for interacting with the
[ISA API](https://github.com/ISA-tools/isa-api). Its requirements pin an
application-maintained ISA API commit that supports Python 3.14.

[![Tests](https://github.com/ISA-tools/isa-rest-service/actions/workflows/tests.yml/badge.svg)](https://github.com/ISA-tools/isa-rest-service/actions/workflows/tests.yml) [![Coverage Status](https://coveralls.io/repos/github/ISA-tools/isa-rest-service/badge.svg?branch=master)](https://coveralls.io/github/ISA-tools/isa-rest-service?branch=master)

To find out more about ISA, see [www.isa-tools.org](http://www.isa-tools.org)

To find out who's using ISA and about the ISA development and user community, see [www.isacommons.org](http://www.isacommons.org)

----
*Authors*: [The ISA team](http://www.isa-tools.org/team/).

*Original author*: David Johnson.

*Development assistance*: The Python 3.14 migration and container deployment
updates were developed with assistance from OpenAI Codex and reviewed and
accepted by the project maintainers.

*License*: This code is licensed under the [CPAL License](https://raw.githubusercontent.com/ISA-tools/isa-api/master/LICENSE.txt).

*Repository*:   [https://github.com/ISA-tools/isa-rest-service](https://github.com/ISA-tools/isa-rest-service)

*ISA team email*: [https://groups.google.com/forum/#!forum/isatools](https://groups.google.com/forum/#!forum/isatools)

*ISA discussion group*: [https://groups.google.com/forum/#!forum/isaforum](https://groups.google.com/forum/#!forum/isaforum)

*Github issue tracker*: [https://github.com/ISA-tools/isa-rest-service/issues](https://github.com/ISA-tools/isa-rest-service/issues)

----
Using the ISA REST service
--------------------------
Python 3.14 and Git are required. For a local development environment:

    python3.14 -m venv .venv
    . .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install --requirement requirements.txt
    ENVIRONMENT=dev python isarest.py

The Flask development server is only for local development. Use the Podman
and systemd deployment below for a production service.

The Metabolomics Workbench import endpoint requires outbound network access to
that external service. The other conversion and validation endpoints operate
on request data locally. API details and request formats are available from
the interactive documentation at `/docs`.

Production deployment
---------------------
The service is packaged as an OCI image built and run with rootless Podman.
The supported single-host deployment uses the conventional systemd user
service in `deployment/isa-rest-service.service`, not a Quadlet `.container`
unit, a system-wide service, or Compose. It invokes `/usr/bin/podman`
directly, creates a fresh container when the unit starts, and stops and
removes it with the unit.

The deployment uses:

- `Type=notify` with Podman's `--sdnotify=conmon` mode;
- an explicit `127.0.0.1:5000:5000` port mapping for use behind a reverse
  proxy;
- `ENVIRONMENT=production`;
- a read-only container filesystem with a bounded writable `/tmp`;
- a non-root user inside the image; and
- a restart-on-failure policy.

The image starts Gunicorn with one worker, four threads, a five-minute request
timeout, and a one-minute graceful shutdown timeout. These conservative
defaults limit the memory cost of ISA conversion while allowing long-running
conversions to finish. Reassess them against production workloads before
raising concurrency.

### Build the image

Install Podman and ensure the service account has subordinate UID and GID
allocations in `/etc/subuid` and `/etc/subgid`. Build or pull the image as the
same operating-system user that will run the service, because rootless Podman
storage is user-specific:

    podman build --pull=always \
        --tag localhost/isa-rest-service:1.0.0 .

The Containerfile uses an exact Python 3.14 slim base and a separate build
stage. Git is present only while installing the pinned isatools commit; the
runtime image contains neither Git nor compiler tooling. The deprecated
Dockerfile `MAINTAINER` instruction is represented by the OCI
`org.opencontainers.image.authors` label. It names the ISA team, which is
currently responsible for the image. A project-scoped
`uk.ac.ox.oerc.isa-rest-service.ai-assisted` label records the involvement of
OpenAI Codex.

### Install and operate the user service

Install the checked-in unit and start it:

    install -D --mode=0644 deployment/isa-rest-service.service \
        ~/.config/systemd/user/isa-rest-service.service
    systemctl --user daemon-reload
    systemctl --user enable --now isa-rest-service.service
    systemctl --user status isa-rest-service.service
    journalctl --user --unit isa-rest-service.service

The image name in the unit is `localhost/isa-rest-service:1.0.0`. After
rebuilding that tag, restart the service to create a container from the new
image:

    systemctl --user restart isa-rest-service.service

The user service configures a Podman health check that requests the generated
API specification. Inspect or run it manually with:

    podman inspect isa-rest-service
    podman healthcheck run isa-rest-service

By default, a user service starts with that user's systemd session. On a host
where it must start during boot and remain active after logout, an
administrator can enable lingering for the dedicated service account:

    loginctl enable-linger SERVICE_ACCOUNT

The unit gives `/tmp` a 1 GiB limit. This must cover request bodies, expanded
archives, conversion outputs, and concurrent requests; adjust it alongside
the archive limits in `config.py` if production concurrency requires more.

TLS and public network exposure should normally be handled by a host reverse
proxy. Changing the unit's published address from `127.0.0.1` to a public
interface should be an explicit deployment decision.

Once running, the interactive documentation and specification are available
at:

- `http://127.0.0.1:5000/docs`
- `http://127.0.0.1:5000/api/v1/swagger.json`

Testing and coverage
--------------------
Install the development dependencies into a Python 3.14 virtual environment:

    python -m pip install -r requirements-dev.txt

Run the test suite with branch coverage enabled:

    python -m coverage run -m unittest tests
    python -m coverage report -m

The report command enforces 100% statement and branch coverage and exits with
an error if coverage regresses.

An HTML report can be generated with `python -m coverage html` and opened from
`htmlcov/index.html`.

The normal suite mocks the external Metabolomics Workbench service. Run its
live integration check separately when network access is intended:

    python -m unittest integration_tests

Contributing
------------
We would be very happy to receive any help and contributions (testing, feature requests, pull requests). Please feel free to contact our development team, ask a question, report a bug or file a feature request in the Github issue tracker, or fork our repository.
