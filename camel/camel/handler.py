import kopf
import asyncio
from pathlib import Path
from provision import process, process_apply

@kopf.on.create('mindcurv.com', 'v1beta1', 'terrayaml')
async def create_fn(body, meta, new, diff, old, logger, **kwargs):
    terrayaml = new.get('spec', {}).get('terrayaml')
    apply = new.get('spec', {}).get('apply', False)
    planId = new.get('spec', {}).get('planId', None)
    process(terrayaml=terrayaml, metadata=meta,
            logger=logger)

# update functions to handle planId set and then apply being patched
@kopf.on.field('mindcurv.com', 'v1beta1', 'terrayaml', field='spec.planId')
def set_planId(old, new, meta, logger, **kwargs):
    logger.debug(f"planId new: {new}")
    logger.debug(f"planId old: {old}")
    if new and new != old:
        run_path = Path(new)
        plan_path = Path(new, 'plan')
        if run_path.exists() is False:
            raise kopf.PermanentError(f"Path to planId does not exist {new}.")
        if plan_path.exists() is False:
            raise kopf.PermanentError(f"planId file does not exist {plan_path.name}.")

        logger.info(f"Path to and planId file exists {plan_path.name}")


@kopf.on.field('mindcurv.com', 'v1beta1', 'terrayaml', field='spec.apply')
def apply(old, new, meta, logger, spec, **kwargs):
    if new is True and new != old:
        if spec.get('planId'):
            process_apply(planId=spec.get('planId'),
                          metadata=meta,
                          logger=logger)
        else:
            raise kopf.PermanentError(f"planId is not present.")