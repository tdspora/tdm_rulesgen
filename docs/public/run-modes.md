# Run Modes

`rulesgen` can run as a Docker Compose stack, as a subprocess-only local
service, or as a host-run API connected to Compose-managed OpenSandbox. Use
the simplest mode that matches the behavior you need to evaluate.

## Docker Compose with OpenSandbox

This is the recommended local evaluation mode and the mode used by
`./scripts/run_stack.sh`.

<!-- starts local containers and may build images -->
<!-- skip: start -->
```bash
./scripts/run_stack.sh
```
<!-- skip: end -->

The script starts the API and OpenSandbox support. If no provider credential
is set, it uses `RULESGEN_LLM_GATEWAY_BACKEND=stub` so local API workflows can
still run.

To pass a provider key through Compose, export it before starting the stack:

<!-- configures provider credentials in the shell; value is intentionally omitted -->
<!-- skip: start -->
```bash
export OPENAI_API_KEY
./scripts/run_stack.sh
```
<!-- skip: end -->

Stop the stack with:

<!-- stops local containers -->
<!-- skip: start -->
```bash
./scripts/run_stack.sh down
```
<!-- skip: end -->

## Docker Compose Without OpenSandbox

Use this mode when you want the API container and local subprocess dataset
executor only.

<!-- starts the base Compose stack -->
<!-- skip: start -->
```bash
export RULESGEN_LLM_GATEWAY_BACKEND=stub
docker compose up --build
```
<!-- skip: end -->

Set `RULESGEN_SANDBOX_BACKEND=subprocess` when you want to be explicit about
the local child-process execution path.

## Host-Run API with Compose OpenSandbox

This mode is useful for contributors or integrators who want fast host reloads
while keeping OpenSandbox in Docker.

Start the OpenSandbox service:

<!-- starts only the OpenSandbox service through Compose -->
<!-- skip: start -->
```bash
docker compose -f compose.yaml -f compose.opensandbox.yaml up --build -d opensandbox-server
```
<!-- skip: end -->

Build a local API image for OpenSandbox to run:

<!-- builds the local rulesgen image used by OpenSandbox -->
<!-- skip: start -->
```bash
docker build -t rulesgen:local .
```
<!-- skip: end -->

Start the API on the host:

<!-- starts a host-run development API -->
<!-- skip: start -->
```bash
uv sync --extra api --extra dev

RULESGEN_LLM_GATEWAY_BACKEND=stub \
RULESGEN_SANDBOX_BACKEND=opensandbox \
RULESGEN_OPENSANDBOX_DOMAIN=127.0.0.1:8090 \
RULESGEN_OPENSANDBOX_PROTOCOL=http \
RULESGEN_OPENSANDBOX_USE_SERVER_PROXY=false \
RULESGEN_OPENSANDBOX_IMAGE=rulesgen:local \
uv run uvicorn rulesgen.main:app --reload
```
<!-- skip: end -->

If you want real natural-language translation, configure the LLM gateway and
provider credentials as described in [Configuration](configuration.md).

## Choosing a Mode

Use Docker Compose with OpenSandbox when you want the closest local match to
the full dataset-generation path.

Use Docker Compose without OpenSandbox when you want a smaller local stack and
are comfortable with subprocess dataset execution.

Use the host-run API mode when you are changing or debugging the API while
still validating OpenSandbox integration.

## Runtime Outputs

All modes create local runtime outputs under the configured data and OSSFS
directories. The default tree is `.rulesgen-data/`. Treat generated datasets,
manifests, execution logs, semantic-cache data, and prompt audits as runtime
artifacts, not source assets.
