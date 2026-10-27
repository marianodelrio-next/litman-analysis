from dataclasses import replace

from fakes import AtomicSharedState, PDF, dossier_drive
from litman_harness.dossier.models import Resource
from litman_harness.dossier.service import ExpedienteService
from litman_harness.plans import PlanStore


def test_status_reports_drift_without_writes(tmp_path):
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    manifest = state.manifest
    manifest.originals[0]['copied_from'] = 'lost-source'
    manifest.summary = {'items': [{'key': 'objeto', 'value': 'x', 'source_file_id': 'lost-source'}],
                        'based_on_analyses': []}
    manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'folder_id': manifest.folders['initial'],
                          'artifacts': [{'file_id': 'artifact', 'name': 'old.pdf'}]}]
    drive.add(Resource('artifact', 'new.pdf', PDF, '1', drive_id='shared', parents=('root',)), b'a')
    drive.resources['source'] = replace(drive.resources['source'], name='changed.pdf', md5_checksum='changed')
    drive.contents[manifest.context_file_id] = b'external edit'
    drive.contents[state.manifest_file.id] = manifest.serialize().encode()
    before = (list(drive.created), list(drive.moved))
    result = service.status('root')
    codes = {(entry['code'], entry.get('id')) for entry in result['drift']}
    assert {('original_name_changed', 'source'), ('original_content_changed', 'source'),
            ('artifact_name_changed', 'artifact'), ('artifact_misplaced', 'artifact'),
            ('summary_source_unavailable', 'lost-source'), ('context_changed', manifest.context_file_id)} <= codes
    assert (drive.created, drive.moved) == before
    assert result['writes'] is False


def test_status_reports_missing_published_artifact(tmp_path):
    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    state.manifest.analyses = [{'operation_id': 'a', 'status': 'published', 'artifacts': [{'file_id': 'lost'}]}]
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    result = service.status('root')
    assert any(x['kind'] == 'artifact' and x['id'] == 'lost' for x in result['missing_resources'])
    assert any(x['code'] == 'resource_unavailable' and x['id'] == 'lost' for x in result['drift'])
