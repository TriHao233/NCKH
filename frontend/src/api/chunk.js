import { apiFetch } from './client';

export function chunkDocument(documentId, collectionName) {
  const payload = { document_id: documentId };
  if (collectionName) {
    payload.collection_name = collectionName;
  }
  return apiFetch('/chunk/document', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}
