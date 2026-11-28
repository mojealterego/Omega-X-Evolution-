import argparse
import asyncio
import json
from pathlib import Path
from .checkpoint import CheckpointStore, CheckpointError
from .engine import Config, run


def main():
    p=argparse.ArgumentParser(description='Run bounded offline OMEGA coevolution')
    for field in ('seed','generations','islands','workers','budget','concurrency'):
        p.add_argument('--'+field,type=int,default=getattr(Config(),field))
    p.add_argument('--evaluation-processes',type=int,default=1,help='Trusted local AST evaluation processes (1–32)')
    p.add_argument('--checkpoint',type=Path,help='Create or resume a local SQLite checkpoint')
    p.add_argument('--checkpoint-key-file',type=Path,help='Separate binary HMAC key, 32 to 4096 bytes')
    p.add_argument('--checkpoint-anchor',type=Path,help='Independent durable anchor database')
    p.add_argument('--anchor-key-file',type=Path,help='Independent 32-byte anchor key')
    p.add_argument('--run-id-file',type=Path,help='Unique independently provisioned 32-byte run ID')
    p.add_argument('--provision-anchor',action='store_true',help='Explicit one-time anchor provisioning')
    p.add_argument('--legacy-research-checkpoint',action='store_true',help='Offline-only legacy checkpoint without rollback protection')
    p.add_argument('--resume',action='store_true',help='Resume to the absolute --generations target')
    p.add_argument('--performance-regression',action='store_true',help='Enable Stage 3 paired wall-clock latency gate (non-deterministic)')
    p.add_argument('--fast-model')
    p.add_argument('--deep-model')
    p.add_argument('--allow-paid-api',action='store_true',help='Explicit opt-in; credits are NOT a hard monetary cap')
    args=vars(p.parse_args())
    evaluation_processes=args.pop('evaluation_processes')
    if not 1<=evaluation_processes<=32:p.error('evaluation-processes must be between 1 and 32')
    performance_policy=None
    if args.pop('performance_regression'):
        from .performance import Policy
        performance_policy=Policy()
    fast=args.pop('fast_model'); deep=args.pop('deep_model'); paid=args.pop('allow_paid_api')
    path=args.pop('checkpoint'); key_path=args.pop('checkpoint_key_file'); resume=args.pop('resume')
    if bool(path)!=bool(key_path) or (resume and not path):p.error('checkpoint and checkpoint-key-file must be supplied together; resume requires both')
    anchor=args.pop('checkpoint_anchor'); anchor_key=args.pop('anchor_key_file'); run_id=args.pop('run_id_file')
    provision=args.pop('provision_anchor'); legacy=args.pop('legacy_research_checkpoint')
    if legacy:
        if not path or any((anchor,anchor_key,run_id,provision)):p.error('legacy research requires checkpoint and no anchor options')
    elif path:
        if not all((anchor,anchor_key,run_id)):p.error('durable checkpoint requires anchor, anchor-key-file and run-id-file')
        if provision and resume:p.error('cannot provision on resume')
    elif any((anchor,anchor_key,run_id,provision)):p.error('anchor options require checkpoint')
    if path and (fast or deep or paid):p.error('checkpoint mode currently supports offline simulation only')
    try:cfg=Config(**args)
    except ValueError as exc:p.error(str(exc))
    checkpoint=None
    if path:
        try:
            with key_path.open('rb') as f:key=f.read(4097)
            if not 32<=len(key)<=4096:raise ValueError('checkpoint key must be 32 to 4096 bytes')
            if legacy: checkpoint=CheckpointStore(path,key)
            else:
                from .durable_checkpoint import DurableCheckpointStore
                with anchor_key.open('rb') as f: ak=f.read(33)
                with run_id.open('rb') as f: rid=f.read(33)
                checkpoint=DurableCheckpointStore(path,key,anchor=anchor,anchor_key=ak,run_id=rid)
                if provision: checkpoint.provision()
        except (OSError,ValueError,CheckpointError) as exc:p.error(f'cannot open checkpoint key: {exc}')
    if fast or deep or paid:
        if not (fast and deep and paid):p.error('live mode requires both model names and --allow-paid-api')
        from .providers import ShinkaProposal
        proposal=ShinkaProposal({'fast':fast,'deep':deep})
        result=asyncio.run(run(cfg,proposal,evaluation_processes=evaluation_processes,performance_policy=performance_policy))
        result['provider_reported_cost_usd']=proposal.reported_cost
    else:
        try:result=asyncio.run(run(cfg,checkpoint=checkpoint,resume=resume,evaluation_processes=evaluation_processes,performance_policy=performance_policy,legacy_research=legacy))
        except (CheckpointError,ValueError) as exc:p.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
