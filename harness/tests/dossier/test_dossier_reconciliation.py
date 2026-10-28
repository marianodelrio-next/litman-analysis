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


def test_truncated_inventory_is_explicit(monkeypatch, tmp_path):
    from litman_harness.dossier import service as service_module
    from litman_harness.dossier.tree import walk_tree

    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    monkeypatch.setattr(service_module, 'walk_tree', lambda drive, root, children: walk_tree(drive, root, children, limit=1))
    result = service.status('root')
    assert result['tree_truncated'] and not result['candidate_scan_complete']
    assert any(x['code'] == 'candidate_scan_incomplete' for x in result['drift'])
    assert not any(x['code'] == 'resource_unavailable' for x in result['drift'])


def test_moved_original_is_reported(tmp_path):
    drive = dossier_drive()
    drive.resources['source'] = replace(drive.resources['source'], capabilities={'canMoveItemWithinDrive': True})
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    drive.resources['source'] = replace(drive.resources['source'], parents=('root',))
    result = service.status('root')
    assert any(x['code'] == 'original_misplaced' and x['id'] == 'source' for x in result['drift'])
    drive.resources['source'] = replace(drive.resources['source'], parents=('unavailable-parent',))
    result = service.status('root')
    assert any(x['code'] == 'resource_unavailable' and x['id'] == 'source' for x in result['drift'])


def test_status_propagates_transient_drive_errors(tmp_path, monkeypatch):
    import pytest
    from litman_harness.errors import HarnessError

    drive = dossier_drive()
    service = ExpedienteService(drive, PlanStore(tmp_path / 'plans'), AtomicSharedState(drive))
    service.apply_incorporation(service.preview_incorporation('root', ['source']).id)
    state = service.load_state(drive.resources['root'])
    state.manifest.summary = {'items': [{'key': 'objeto', 'value': 'x', 'source_file_id': 'copied-source'}],
                              'based_on_analyses': []}
    drive.contents[state.manifest_file.id] = state.manifest.serialize().encode()
    original_get = drive.get

    def failing_get(identifier):
        if identifier == 'copied-source':
            raise HarnessError('drive_error', 'temporary', details={'http_status': 503})
        return original_get(identifier)

    monkeypatch.setattr(drive, 'get', failing_get)
    with pytest.raises(HarnessError, match='temporary'):
        service.status('root')
    monkeypatch.setattr(drive, 'get', original_get)
    original_download = drive.download

    def failing_download(identifier, path):
        if identifier == state.manifest.context_file_id:
            raise HarnessError('drive_error', 'temporary', details={'http_status': 503})
        return original_download(identifier, path)

    monkeypatch.setattr(drive, 'download', failing_download)
    with pytest.raises(HarnessError, match='temporary'):
        service.status('root')


def test_v2_retirement_preserves_history_and_excludes_active_sources():
    from litman_harness.dossier.manifest import Manifest
    from litman_harness.dossier.recommendation import recommend
    from litman_harness.dossier.context import render_context

    manifest = Manifest.new(Resource('root', 'Tender', 'folder', '1'))
    manifest.originals = [{'file_id': 'a', 'observed_name': 'A', 'md5_checksum': 'hash'}]
    manifest.summary = {'items': [{'key': 'objeto', 'value': 'X', 'source_file_id': 'a'}], 'based_on_analyses': []}
    manifest.upgrade()
    manifest.originals[0]['status'] = 'retired'
    restored = Manifest.parse(manifest.serialize())
    assert restored.originals[0]['file_id'] == 'a'
    assert not restored.active_originals()
    assert 'a' not in restored.summary_sources()
    assert ('original', 'a') not in restored.references()
    assert recommend(folder_id='root', state='adopted', manifest=restored)['kind'] == 'incorporate'
    context = render_context(restored, 'Tender')
    assert 'retirad' in context and 'open?id=a' not in context
