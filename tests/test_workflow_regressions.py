import json
from pathlib import Path
from queue import Queue
from threading import Event
from types import SimpleNamespace

import fitz
import pytest

from auto_bid_builder.bid_workspace import (
    add_documents, analyze_workspace, create_workspace, load_manifest, save_manifest, workspace_status,
)
from auto_bid_builder.estimate.draft import EstimateDraft, EstimateLine, load_estimate, save_estimate
from auto_bid_builder.quote.jti_render import _find_bid_document, _reference_pages, write_jti_quote
from auto_bid_builder.storage import write_json


def workspace(tmp_path):
    return create_workspace(tmp_path / 'bids', {'title': 'Millwork'})


def pdf(path, text='NEW ARCHITECTURAL MILLWORK CASEWORK'):
    path.parent.mkdir(parents=True, exist_ok=True)
    with fitz.open() as doc:
        doc.new_page().insert_text((50, 50), text)
        doc.save(path)


def confirmed(root):
    draft = EstimateDraft(project_title='Millwork', lines=[EstimateLine(
        item=1, description='Verified casework', manual_add=1200, estimator_note='MANUAL: verified')],
        scope_review_confirmed=True, pricing_profile_confirmed=True, tax_rate_confirmed=True)
    save_estimate(root, draft)
    return draft


def test_unchanged_reanalysis_preserves_confirmations_and_final_quote(tmp_path):
    root = workspace(tmp_path)
    pdf(root / 'bid_docs' / 'Plans.PDF')
    analyze_workspace(root)
    draft = confirmed(root)
    write_jti_quote(root, draft)
    result = analyze_workspace(root)
    assert result['pdf_count'] == 1
    assert result['estimate_refresh']['status'] == 'unchanged'
    assert load_estimate(root).ready_for_quote
    assert (root / 'output' / 'jti_quote.pdf').exists()


def test_changed_project_metadata_invalidates_review_and_confirmations(tmp_path):
    root = workspace(tmp_path)
    pdf(root / 'bid_docs' / 'plans.pdf')
    analyze_workspace(root)
    confirmed(root)
    manifest = load_manifest(root)
    manifest['opportunity']['title'] = 'Different project'
    save_manifest(root, manifest)
    assert not workspace_status(root)['analysis_current']
    analyze_workspace(root)
    assert not load_estimate(root).scope_review_confirmed


def test_nested_same_name_documents_have_unambiguous_quote_references(tmp_path):
    root = workspace(tmp_path)
    for folder in ('plans', 'addendum'):
        pdf(root / 'bid_docs' / folder / 'sheet.pdf')
    result = analyze_workspace(root)
    assert {r['source'] for r in result['pages']} == {'plans/sheet.pdf', 'addendum/sheet.pdf'}
    assert _find_bid_document(root, 'sheet.pdf') is None
    draft = EstimateDraft(project_title='Test', lines=[EstimateLine(
        item=1, description='Casework', manual_add=100,
        source_refs=['addendum/sheet.pdf / page 1'])])
    refs = _reference_pages(root, draft)
    assert len(refs) == 1
    assert refs[0].source_path == (root / 'bid_docs' / 'addendum' / 'sheet.pdf').resolve()


def test_estimate_edit_removes_old_quote_but_identical_save_preserves_it(tmp_path):
    root = workspace(tmp_path)
    draft = confirmed(root)
    write_jti_quote(root, draft)
    save_estimate(root, draft)
    assert (root / 'output' / 'jti_quote.pdf').exists()
    draft.lines[0].manual_add = 2300
    save_estimate(root, draft)
    assert not (root / 'output' / 'jti_quote.pdf').exists()
    assert not (root / 'output' / 'AI_review_package.zip').exists()


def test_imported_addendum_clears_workflow_and_quotes(tmp_path):
    root = workspace(tmp_path)
    manifest = load_manifest(root)
    manifest['workflow'].update(documents_reviewed=True, quote_ready=True)
    save_manifest(root, manifest)
    draft = confirmed(root)
    write_jti_quote(root, draft)
    source = tmp_path / 'ADDENDUM.PDF'
    pdf(source)
    add_documents(root, [source])
    assert not load_manifest(root)['workflow']['quote_ready']
    assert not load_manifest(root)['workflow']['documents_reviewed']
    assert not (root / 'output' / 'quote_preview.pdf').exists()


def test_docx_only_changed_review_is_stale(tmp_path):
    import zipfile
    root = workspace(tmp_path)
    source = root / 'bid_docs' / 'ADDENDUM.DOCX'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('word/document.xml', '<document><p><t>NEW MILLWORK</t></p></document>')
    assert analyze_workspace(root)['docx_count'] == 1
    assert workspace_status(root)['analysis_current']
    source.unlink()
    assert workspace_status(root)['analysis_status'] == 'stale'


def test_atomic_save_failure_preserves_previous_state(tmp_path, monkeypatch):
    import auto_bid_builder.storage as storage
    path = tmp_path / 'state.json'
    write_json(path, {'old': True})
    def fail(*args):
        raise OSError('disk write failed')
    monkeypatch.setattr(storage.os, 'replace', fail)
    with pytest.raises(OSError):
        write_json(path, {'new': True})
    assert json.loads(path.read_text()) == {'old': True}
    assert list(tmp_path.iterdir()) == [path]


def test_background_failure_reaches_ui_without_tk_calls_from_worker():
    from auto_bid_builder.gui import AutoBidBuilderApp
    completed = Event()
    callbacks = Queue()
    errors = []
    fake = SimpleNamespace(_busy=False, _background_results=Queue())
    fake._set_busy = lambda busy, message: setattr(fake, '_busy', busy)
    fake.after = lambda delay, callback: callbacks.put(callback)
    fake._background_error = lambda error: errors.append(error)
    fake._poll_background = lambda: AutoBidBuilderApp._poll_background(fake)
    fake._background_done = lambda result, done: done(result)
    def work():
        completed.set()
        raise ValueError('network unavailable')
    AutoBidBuilderApp._run_background(fake, work, lambda result: None, message='Loading')
    assert completed.wait(3)
    # Queue.get waits for worker completion without invoking Tk at all.
    result = fake._background_results.get(timeout=3)
    assert not result[0]
    assert callbacks.empty()
    fake._background_results.put(result)
    AutoBidBuilderApp._poll_background(fake)
    assert str(errors[0]) == 'network unavailable'
    assert not callbacks.empty()


def test_completion_handler_failure_restores_ready_state():
    from auto_bid_builder.gui import AutoBidBuilderApp
    errors = []
    fake = SimpleNamespace(_set_busy=lambda *args: None, _background_error=errors.append)
    def done(result):
        raise ValueError('invalid provider response')
    AutoBidBuilderApp._background_done(fake, None, done)
    assert str(errors[0]) == 'invalid provider response'
