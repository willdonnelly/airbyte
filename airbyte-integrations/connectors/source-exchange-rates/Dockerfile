FROM python:3.9-slim

# Bash is installed for more convenient debugging.
RUN apt-get update && apt-get install -y bash && rm -rf /var/lib/apt/lists/*

ENV CODE_PATH="source_exchange_rates"
ENV WORKDIR=/airbyte/integration_code

WORKDIR $WORKDIR
COPY $CODE_PATH ./$CODE_PATH
COPY setup.py ./
COPY main.py ./

RUN pip install .

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
#COPY --from=ghcr.io/estuary/airbyte-to-flow:dev /airbyte-to-flow ./airbyte-to-flow
#ENTRYPOINT ["/airbyte/integration_code/airbyte-to-flow", "--connector-entrypoint", "python /airbyte/integration_code/main.py"]
ENTRYPOINT ["python /airbyte/integration_code/main.py"]

LABEL io.airbyte.version=v1
LABEL io.airbyte.name=airbyte/source-exchange-rates
#LABEL FLOW_TCP_PORT=2222
