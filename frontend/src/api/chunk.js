import { apiFetch } from './client';

export function chunkDocument(documentId, collectionName = 'chunks') {
  return apiFetch('/chunk/document', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      document_id: documentId,
      collection_name: collectionName,
    }),
  });
}
