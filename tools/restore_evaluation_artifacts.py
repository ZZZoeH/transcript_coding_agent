"""Restore published gzip prediction streams with hash checks and no model/API calls."""
import argparse
import gzip
import hashlib
import json
import os
import tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def restore(manifest_path,root=ROOT):
    root=Path(root).resolve();manifest=json.loads(Path(manifest_path).read_text());pending=[];verified=0
    for entry in manifest.get('archived_prediction_files',[]):
        target=(root/entry['path']).resolve();archive=(root/entry['archive']).resolve()
        if not target.is_relative_to(root) or not archive.is_relative_to(root):
            raise ValueError('Artifact paths must stay inside the repository')
        compressed=archive.read_bytes()
        if digest(compressed)!=entry['archive_sha256']:raise ValueError('Archive hash mismatch: '+entry['archive'])
        data=gzip.decompress(compressed)
        if digest(data)!=entry['sha256']:raise ValueError('Restored-content hash mismatch: '+entry['path'])
        if target.exists():
            if digest(target.read_bytes())!=entry['sha256']:raise ValueError('Refusing to overwrite a differing local file: '+entry['path'])
            verified+=1
        else:pending.append((target,data))
    # Validate every source/destination before writing any missing artifact.
    for target,data in pending:
        target.parent.mkdir(parents=True,exist_ok=True)
        fd,name=tempfile.mkstemp(prefix='.restoring-',dir=target.parent)
        try:
            with os.fdopen(fd,'wb') as stream:stream.write(data)
            os.link(name,target)  # Do not overwrite even if a destination appears concurrently.
        finally:Path(name).unlink(missing_ok=True)
    return {'restored':len(pending),'existing_files_verified':verified,'model_or_API_calls':0}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest',type=Path,default=ROOT/'runs/agent/reviewed_20261126/publication_manifest.json')
    args=parser.parse_args()
    try:result=restore(args.manifest)
    except (ValueError,OSError,EOFError) as error:parser.error(str(error))
    print(json.dumps(result))


if __name__=='__main__':main()
