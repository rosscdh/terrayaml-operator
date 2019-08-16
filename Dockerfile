FROM python:3-alpine

ENV TERRAFORM_VERSION=0.11.14
WORKDIR /src
ADD . .
RUN mkdir gpghome
RUN cd /tmp;wget https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_linux_amd64.zip --quiet && \
    unzip terraform_${TERRAFORM_VERSION}_linux_amd64.zip -d /usr/bin
RUN apk --update add gnupg curl jq ca-certificates openssl unzip wget && \
    apk add --update --no-cache --virtual .build-deps \
            g++ \
            libxml2 libxml2-dev && \
        apk add libxslt-dev && \
        pip install -r requirements.txt && \
        apk del .build-deps

