#!/usr/bin/env python
content = open('backend/services/documents.py').read()

# List of functions to rename
renames = [
    ('async def check_duplicate_document', 'async def _check_duplicate_document'),
    ('async def update_document_status', 'async def _update_document_status'),
    ('async def create_processing_job', 'async def _create_processing_job'),
    ('async def get_processing_job', 'async def _get_processing_job'),
    ('async def update_job_status', 'async def _update_job_status'),
    ('async def increment_job_retry_count', 'async def _increment_job_retry_count'),
    ('async def get_pending_jobs', 'async def _get_pending_jobs'),
    ('async def delete_document', 'async def _delete_document'),
    ('async def get_document_versions', 'async def _get_document_versions'),
]

for old, new in renames:
    content = content.replace(old, new)

open('backend/services/documents.py', 'w').write(content)
print("Renamed all functions")
