FROM python:3.7
WORKDIR /src
ADD terrayaml /src
RUN pip install -r requirements.txt
CMD kopf run /src/terrayaml/handler.py --verbose