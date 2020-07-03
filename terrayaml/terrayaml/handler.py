import kopf
import asyncio
from pathlib import Path
from provision import process, process_apply, process_destroy

@kopf.on.create('thicc.tech', 'v1beta1', 'terrayaml')
async def create_fn(body, meta, new, diff, old, logger, **kwargs):
    terrayaml = new.get('spec', {}).get('terrayaml')
    process(terrayaml=terrayaml,
            metadata=meta,
            logger=logger)

@kopf.on.delete('thicc.tech', 'v1beta1', 'terrayaml')
async def delete_fn(body, spec, meta, new, diff, old, logger, **kwargs):
    terrayaml = spec.get('terrayaml')
    destroyOnDelete = spec.get('destroyOnDelete', False)
    planId = spec.get('planId')
    name = meta.get('name')
    team = meta.get('team')
    env = meta.get('environment')
    app = meta.get('application')
    if destroyOnDelete is True and planId:
        kopf.info(body, reason='destroyOnDelete is True', message=f"planid: {planId} name: {name} team: {team} environment: {env} app: {app}")
        process_destroy(planId=planId,
                        logger=logger)
    else:
        kopf.info(body, reason='destroyOnDelete is False', message=f"planid: {planId} name: {name} team: {team} environment: {env} app: {app}")

# update functions to handle planId set and then apply being patched
@kopf.on.field('thicc.tech', 'v1beta1', 'terrayaml', field='spec.planId')
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


@kopf.on.field('thicc.tech', 'v1beta1', 'terrayaml', field='spec.apply')
def apply(old, new, meta, logger, spec, **kwargs):
    if new is True and new != old:
        if spec.get('planId'):
            process_apply(planId=spec.get('planId'),
                          logger=logger)
        else:
            raise kopf.PermanentError(f"planId is not present.")