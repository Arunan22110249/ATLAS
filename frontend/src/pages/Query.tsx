import React, { useState } from 'react';

function Query() {
  const [query, setQuery] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleQuery = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!query.trim()) return;

    setLoading(true);
    try {
      const token = localStorage.getItem('token');
      const response = await fetch('/api/v1/query', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ query, top_k: 10 }),
      });

      if (response.ok) {
        const data = await response.json();
        setResult(data);
      }
    } catch (error) {
      alert('Query failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">RAG Query</h1>
      <form onSubmit={handleQuery} className="mb-6">
        <div className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Ask a question..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-blue-500 focus:border-blue-500"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-400"
          >
            {loading ? 'Querying...' : 'Query'}
          </button>
        </div>
      </form>

      {result && (
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Answer</h2>
          <p className="mb-6 text-gray-800">{result.answer}</p>
          
          {result.citations && result.citations.length > 0 && (
            <>
              <h3 className="text-lg font-semibold mb-3">Citations</h3>
              <div className="space-y-2">
                {result.citations.map((citation: any, i: number) => (
                  <div key={i} className="text-sm text-gray-600 border-l-4 border-blue-500 pl-4">
                    {citation.document_name} {citation.page_number && `(p. ${citation.page_number})`}
                  </div>
                ))}
              </div>
            </>
          )}
          
          <p className="text-xs text-gray-500 mt-4">
            Retrieved in {result.retrieval_time_ms.toFixed(0)}ms, Generated in {result.generation_time_ms.toFixed(0)}ms
          </p>
        </div>
      )}
    </div>
  );
}

export default Query;
