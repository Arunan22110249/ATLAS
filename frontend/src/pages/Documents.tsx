import React, { useState } from 'react';

function Documents() {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    const formData = new FormData();
    formData.append('file', file);

    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/v1/documents/upload', {
        method: 'POST',
        headers: { 'Authorization': `Bearer ${token}` },
        body: formData,
      });

      if (response.ok) {
        const data = await response.json();
        alert(`Document uploaded: ${data.filename}`);
      }
    } catch (error) {
      alert('Upload failed');
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">Documents</h1>
      <div className="mb-6">
        <label className="inline-block px-4 py-2 bg-blue-600 text-white rounded cursor-pointer hover:bg-blue-700">
          {uploading ? 'Uploading...' : 'Upload Document'}
          <input
            type="file"
            onChange={handleFileUpload}
            disabled={uploading}
            className="hidden"
            accept=".pdf,.docx,.txt,.md,.html,.csv,.json"
          />
        </label>
      </div>
      {documents.length === 0 && (
        <p className="text-gray-600">No documents uploaded yet</p>
      )}
    </div>
  );
}

export default Documents;
