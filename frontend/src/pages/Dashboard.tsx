import React from 'react';

function Dashboard() {
  return (
    <div className="p-8">
      <h1 className="text-3xl font-bold mb-6">Dashboard</h1>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Recent Documents</h2>
          <p className="text-gray-600">No documents yet</p>
        </div>
        <div className="bg-white rounded-lg shadow p-6">
          <h2 className="text-xl font-semibold mb-4">Statistics</h2>
          <div className="space-y-2">
            <p className="text-gray-600">Documents: 0</p>
            <p className="text-gray-600">Collections: 0</p>
          </div>
        </div>
      </div>
    </div>
  );
}

export default Dashboard;
