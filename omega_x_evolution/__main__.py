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
    if path and (fast or deep or paid):p.error('checkpoint mode currently supports offline simulation only')
    try:cfg=Config(**args)
    except ValueError as exc:p.error(str(exc))
    checkpoint=None
    if path:
        try:
            with key_path.open('rb') as f:key=f.read(4097)
            if not 32<=len(key)<=4096:raise ValueError('checkpoint key must be 32 to 4096 bytes')
            checkpoint=CheckpointStore(path,key)
        except (OSError,ValueError) as exc:p.error(f'cannot open checkpoint key: {exc}')
    if fast or deep or paid:
        if not (fast and deep and paid):p.error('live mode requires both model names and --allow-paid-api')
        from .providers import ShinkaProposal
        proposal=ShinkaProposal({'fast':fast,'deep':deep})
        result=asyncio.run(run(cfg,proposal,evaluation_processes=evaluation_processes,performance_policy=performance_policy))
        result['provider_reported_cost_usd']=proposal.reported_cost
    else:
        try:result=asyncio.run(run(cfg,checkpoint=checkpoint,resume=resume,evaluation_processes=evaluation_processes,performance_policy=performance_policy))
        except (CheckpointError,ValueError) as exc:p.error(str(exc))
    print(json.dumps(result,indent=2,allow_nan=False))

if __name__=='__main__':main()
