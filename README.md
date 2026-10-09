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
*Authors*: [The ISA team](http://www.isa-tools.org/team/), Philippe Rocca-Serra <philippe.rocca-serra@oerc.ox.ac.uk>, Milo Thurston <milo.thurston@oerc.ox.ac.uk>.

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

The locked dependency set and deployment have been checked on Linux only.
Other operating systems should not be treated as supported until the lock
installs successfully and the complete test suite passes on the relevant
operating-system and processor combination.

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

The `Containerfile` uses an exact Python 3.14 slim base and a separate build
stage. Git is present only while installing the pinned isatools commit; the
runtime image contains neither Git nor compiler tooling. The deprecated
Dockerfile `MAINTAINER` instruction is represented by the OCI
`org.opencontainers.image.authors` label. It names the ISA team, which is
currently responsible for the image. A project-scoped
`uk.ac.ox.oerc.isa-rest-service.ai-assisted` label records the involvement of
OpenAI Codex. Production installation uses the fully pinned
`requirements.lock`; `requirements.txt` records the direct dependency policy
used when deliberately updating that lock.

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

Resource warnings and service-owned deprecations are treated as errors.
PyFilesystem 2.4.16 still emits its known
`pkg_resources.declare_namespace` deprecation during import; that exact warning
remains visible, while `requirements.lock` keeps Setuptools below the release
that removes the API.

An HTML report can be generated with `python -m coverage html` and opened from
`htmlcov/index.html`.

Build and run the container test target to exercise the complete suite against
the same runtime and exact dependency set as the production image:

    podman build --target test --tag localhost/isa-rest-service:test .
    podman run --rm localhost/isa-rest-service:test

The normal suite mocks the external Metabolomics Workbench service. Run its
live integration check separately when network access is intended:

    RUN_LIVE_INTEGRATION=1 python -m unittest integration_tests

The same opt-in check can be run from the test image:

    podman run --rm --env RUN_LIVE_INTEGRATION=1 \
        localhost/isa-rest-service:test \
        python -m unittest integration_tests

Appendix: macOS deployment with launchd
---------------------------------------
macOS cannot run the Linux image directly. Podman therefore runs it inside a
rootless Linux virtual machine managed by Podman Machine. A per-user
`launchd` agent can provide lifecycle management analogous to the systemd user
service on Linux.

This deployment starts after the selected macOS user logs in; it is not a
pre-login system service. Use a dedicated login account for an unattended Mac,
and configure the host not to sleep while serving requests.

### Prepare Podman Machine and the image

Install Podman, initialise its default virtual machine, and build the image as
the macOS user that will operate the service:

    brew install podman
    podman machine init --now
    podman build --target production \
        --tag localhost/isa-rest-service:1.0.0 .

Podman Machine stores images inside its Linux VM. Rebuild or pull the image
through the same macOS account and machine connection used by the agent.

**note**. One may have to disable MacOS 'AirPlay' from System Preferences > Airdrop & Continuity, to free port 5000 for the service.
Otherwise, the agent will fail to start the container with a port conflict.


### Create the service wrapper

Create these user-owned directories:

    mkdir -p "$HOME/Library/Application Support/ISA REST Service"
    mkdir -p "$HOME/Library/Logs/ISA REST Service"

Save the following as
`~/Library/Application Support/ISA REST Service/run.sh`:

```zsh
#!/bin/zsh
set -u

# This is the default Homebrew path on Apple Silicon. Intel Macs normally use
# /usr/local/bin/podman instead.
PODMAN=/opt/homebrew/bin/podman
MACHINE=podman-machine-default
CONTAINER=isa-rest-service
IMAGE=localhost/isa-rest-service:1.0.0
stopping=0

cleanup() {
    if (( stopping == 0 )); then
        stopping=1
        "$PODMAN" stop --ignore --time 60 "$CONTAINER"
        "$PODMAN" rm --force --ignore "$CONTAINER"
    fi
}

trap 'cleanup; exit 0' INT TERM
trap cleanup EXIT

if ! "$PODMAN" info >/dev/null 2>&1; then
    "$PODMAN" machine start --quiet "$MACHINE"
fi

"$PODMAN" rm --force --ignore "$CONTAINER"
"$PODMAN" run --detach \
    --name "$CONTAINER" \
    --pull=never \
    --read-only \
    --tmpfs /tmp:rw,nosuid,nodev,noexec,size=1g \
    --publish 127.0.0.1:5000:5000 \
    --env ENVIRONMENT=production \
    --security-opt=no-new-privileges \
    --cap-drop=all \
    --health-cmd "python -c \"import urllib.request; urllib.request.urlopen('http://127.0.0.1:5000/api/v1/swagger.json', timeout=5).read()\"" \
    --health-interval=30s \
    --health-timeout=10s \
    --health-start-period=20s \
    --health-retries=3 \
    --health-on-failure=kill \
    "$IMAGE"

"$PODMAN" wait "$CONTAINER" &
wait_pid=$!
wait "$wait_pid"
```

Make the wrapper executable:

    chmod 0755 "$HOME/Library/Application Support/ISA REST Service/run.sh"

The wrapper starts Podman Machine when necessary, replaces a stale service
container, waits for the new container, and stops and removes it when
`launchd` terminates the job. Confirm the `PODMAN` path before installing the
agent.

### Install the user LaunchAgent

Save the following as
`~/Library/LaunchAgents/org.isa-tools.isa-rest-service.plist`, replacing every
`YOUR_ACCOUNT` component with the macOS account name. `launchd` does not expand
shell variables or `~` in these paths.

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>org.isa-tools.isa-rest-service</string>

    <key>ProgramArguments</key>
    <array>
        <string>/bin/zsh</string>
        <string>/Users/YOUR_ACCOUNT/Library/Application Support/ISA REST Service/run.sh</string>
    </array>

    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ThrottleInterval</key>
    <integer>10</integer>
    <key>ProcessType</key>
    <string>Background</string>

    <key>StandardOutPath</key>
    <string>/Users/YOUR_ACCOUNT/Library/Logs/ISA REST Service/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/YOUR_ACCOUNT/Library/Logs/ISA REST Service/stderr.log</string>
</dict>
</plist>
```

Load and start the agent in the current graphical user session:

    launchctl bootstrap "gui/$(id -u)" \
        "$HOME/Library/LaunchAgents/org.isa-tools.isa-rest-service.plist"
    launchctl enable \
        "gui/$(id -u)/org.isa-tools.isa-rest-service"
    launchctl kickstart -k \
        "gui/$(id -u)/org.isa-tools.isa-rest-service"

Inspect the agent, container, health check, and logs with:

    launchctl print "gui/$(id -u)/org.isa-tools.isa-rest-service"
    podman ps --filter name=isa-rest-service
    podman inspect isa-rest-service
    podman healthcheck run isa-rest-service
    tail -F "$HOME/Library/Logs/ISA REST Service/stdout.log" \
        "$HOME/Library/Logs/ISA REST Service/stderr.log"

After rebuilding the `1.0.0` image, restart the agent so it creates a container
from the replacement image:

    launchctl kickstart -k \
        "gui/$(id -u)/org.isa-tools.isa-rest-service"

To stop and unload the agent:

    launchctl bootout "gui/$(id -u)" \
        "$HOME/Library/LaunchAgents/org.isa-tools.isa-rest-service.plist"

The API remains bound to `127.0.0.1:5000`. As on Linux, public exposure and TLS
should normally be provided by a separately managed reverse proxy.

Appendix: native Gunicorn and Nginx deployment
----------------------------------------------
The service can run directly from a Python virtual environment without
Podman. Gunicorn serves the application on the loopback interface and Nginx
handles client connections and TLS. This removes the container boundary, so
the service account, virtual environment, source tree, temporary storage, and
process supervision become host responsibilities.

The dependency warning above applies in particular to this deployment: the
current lock has been verified on Linux only. Before using this arrangement on
macOS or another platform, install the lock in a clean environment and run the
complete suite on every processor architecture that will be supported.

### Install the native application

Use a dedicated account and an absolute deployment path. The following
commands use `/absolute/path/to/isa-rest-service` as a placeholder:

    cd /absolute/path/to/isa-rest-service
    python3.14 -m venv .venv
    . .venv/bin/activate
    python -m pip install --upgrade pip
    python -m pip install --requirement requirements.lock
    ENVIRONMENT=production gunicorn --check-config \
        'isarest:create_app()'

The service writes temporary request and conversion data beneath
`UPLOAD_FOLDER`, which defaults to `/tmp`. Ensure that the service account can
write there and that the filesystem has enough capacity for request bodies and
expanded archives. The default request-body limit is 32 MiB and the default
expanded-archive limit is 256 MiB.

The production Gunicorn command is:

    ENVIRONMENT=production \
    /absolute/path/to/isa-rest-service/.venv/bin/gunicorn \
        --chdir /absolute/path/to/isa-rest-service \
        --bind 127.0.0.1:5000 \
        --workers 1 \
        --threads 4 \
        --timeout 300 \
        --graceful-timeout 60 \
        --access-logfile - \
        --error-logfile - \
        'isarest:create_app()'

Run this command under a process supervisor rather than leaving it attached to
an interactive terminal. On Linux, use a systemd service with the command
above as `ExecStart`. On macOS, use a per-user LaunchAgent with the Gunicorn
arguments as its `ProgramArguments`, `ENVIRONMENT=production` under
`EnvironmentVariables`, and the repository path as `WorkingDirectory`.


For testing purposes locally:

```
ENVIRONMENT=dev gunicorn --bind 127.0.0.1:5000 --reload 'isarest:create_app()'
```

### Configure Nginx

The following server configuration redirects clear-text requests to HTTPS and
proxies HTTPS traffic to Gunicorn. Replace the server name and certificate
paths:

```nginx
upstream isa_rest_service {
    server 127.0.0.1:5000;
    keepalive 16;
}

server {
    listen 80;
    server_name isa.example.org;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name isa.example.org;

    ssl_certificate /absolute/path/to/fullchain.pem;
    ssl_certificate_key /absolute/path/to/private-key.pem;

    # Keep this aligned with MAX_CONTENT_LENGTH.
    client_max_body_size 32m;

    location / {
        proxy_pass http://isa_rest_service;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 10s;
        proxy_send_timeout 310s;
        proxy_read_timeout 310s;
    }
}
```

On Linux this can normally be installed beneath `/etc/nginx/conf.d` or the
distribution's `sites-available` directory. Homebrew Nginx normally reads its
configuration beneath `/opt/homebrew/etc/nginx` on Apple Silicon or
`/usr/local/etc/nginx` on Intel Macs. Confirm the active configuration path
with the locally installed Nginx package.

Validate the Nginx configuration before reloading it. Once Gunicorn and Nginx
are running, check:

    curl --fail https://isa.example.org/docs
    curl --fail https://isa.example.org/api/v1/swagger.json

When deploying a new application version, install and test its dependencies,
stop accepting new work, restart the supervised Gunicorn process, and verify
both URLs. Nginx can normally remain running while the local upstream
restarts.

Contributing
------------
We would be very happy to receive any help and contributions (testing, feature requests, pull requests). Please feel free to contact our development team, ask a question, report a bug or file a feature request in the Github issue tracker, or fork our repository.
