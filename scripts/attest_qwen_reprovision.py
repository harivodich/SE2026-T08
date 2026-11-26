"""Record an explicit verified re-provision, never rewrite archived training pins."""
import argparse
import hashlib
import json
from pathlib import Path

from vietdoc.ml import model_provision as provision

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--root', type=Path, default=Path.cwd())
root = parser.parse_args().root.resolve(strict=True)
snapshot = root/'models'/provision.REVISION
provision.verify_snapshot(snapshot)
# Fetch fresh metadata from the official pinned upstream revision, independently
# of local inventory. Every required file is rehashed against that metadata.
upstream = provision.hub_metadata()
entries = provision._metadata(upstream)
files = [provision._verify_file(snapshot, entries[name]) for name in provision.REQUIRED_FILES]
pins = json.loads((root/'checkpoint/full-d22-train-v1/runs/full-epoch/run_manifest.json').read_text())['pins']
proof = {
    'version':'vietdoc.base-reprovision.v1', 'model_id':provision.MODEL_ID,
    'revision':provision.REVISION,
    'training_model_manifest_sha256':pins['model_manifest_sha256'],
    'current_model_manifest_sha256':hashlib.sha256((snapshot/'manifest.json').read_bytes()).hexdigest(),
    'tokenizer_sha256':hashlib.sha256((snapshot/'tokenizer.json').read_bytes()).hexdigest(),
    'reason':'Previous temporary snapshot cleaned after export; base re-downloaded from same immutable revision. Original provisioning inventory bytes were not retained.',
    'source':'official Hugging Face API, token=False, pinned revision; no model code executed',
    'upstream_metadata':upstream,'verified_files':files,
    'production_active':False,
}
path = root/'base-reprovision.json'
path.write_text(json.dumps(proof,ensure_ascii=False,indent=2)+'\n')
digest = hashlib.sha256(path.read_bytes()).hexdigest()
(root/'base-reprovision.sha256').write_text(digest+'\n')
print(json.dumps({'status':'VERIFIED_REPROVISION','sha256':digest,'old_manifest':pins['model_manifest_sha256'],'new_manifest':proof['current_model_manifest_sha256']}),flush=True)
