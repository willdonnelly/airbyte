FROM python:3.9-slim

# Bash is installed for more convenient debugging.
RUN apt-get update && apt-get install -y bash && rm -rf /var/lib/apt/lists/*

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
#COPY --from=ghcr.io/estuary/airbyte-to-flow:dev /airbyte-to-flow ./
#
ENTRYPOINT ["python /airbyte/integration_code/main.py"]
WORKDIR /airbyte/integration_code
COPY source_gitlab ./source_gitlab
COPY main.py ./
COPY setup.py ./
RUN pip install .

ENTRYPOINT ["/airbyte/integration_code/airbyte-to-flow", "--connector-entrypoint", "python /airbyte/integration_code/main.py"]

LABEL io.airbyte.version=v1
LABEL io.airbyte.name=airbyte/source-gitlab
#LABEL FLOW_TCP_PORT=2222
