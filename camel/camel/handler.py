import kopf
import asyncio

from provision import process

@kopf.on.create('mindcurv.com', 'v1beta1', 'terrayaml')
async def create_fn(body, meta, new, diff, old, logger, **kwargs):
    terrayaml = new.get('spec', {}).get('terrayaml')
    process(terrayaml=terrayaml, metadata=meta,
            logger=logger)
