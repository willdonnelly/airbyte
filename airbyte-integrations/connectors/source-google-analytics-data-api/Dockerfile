FROM python:3.9.11-slim as base

# build and load all requirements
FROM base as builder
WORKDIR /airbyte/integration_code

# upgrade pip to the latest version
RUN apt update -y && apt upgrade -y

COPY setup.py ./
# install necessary packages to a temporary folder
RUN pip install --prefix=/install .

# build a clean environment
FROM base
WORKDIR /airbyte/integration_code

# copy all loaded and built libraries to a pure basic image
COPY --from=builder /install /usr/local
# add default timezone settings
COPY --from=builder /usr/share/zoneinfo/Etc/UTC /etc/localtime
RUN echo "Etc/UTC" > /etc/timezone

# copy payload code only
COPY main.py ./
COPY source_google_analytics_data_api ./source_google_analytics_data_api

ENV AIRBYTE_ENTRYPOINT "python /airbyte/integration_code/main.py"
#COPY --from=ghcr.io/estuary/airbyte-to-flow:dev /airbyte-to-flow ./
#ENTRYPOINT ["/airbyte/integration_code/airbyte-to-flow", "--connector-entrypoint", "python /airbyte/integration_code/main.py"]
ENTRYPOINT ["python /airbyte/integration_code/main.py"]

LABEL io.airbyte.version=v1
LABEL io.airbyte.name=airbyte/source-google-analytics-data-api
#LABEL FLOW_TCP_PORT=2222
