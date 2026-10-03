import React, { useContext } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { AuthContext } from '../context/AuthContext';

function Navbar({ onLogout }: { onLogout: () => void }) {
  const navigate = useNavigate();
  const { user } = useContext(AuthContext);

  const handleLogout = () => {
    onLogout();
    navigate('/');
  };

  return (
    <nav className="bg-gray-900 text-white shadow-lg">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-16">
          <div className="flex items-center space-x-8">
            <Link to="/" className="text-2xl font-bold">
              ATLAS
            </Link>
            <div className="hidden md:flex space-x-4">
              <Link to="/" className="hover:text-gray-300 px-3 py-2">
                Dashboard
              </Link>
              <Link to="/documents" className="hover:text-gray-300 px-3 py-2">
                Documents
              </Link>
              <Link to="/query" className="hover:text-gray-300 px-3 py-2">
                Query
              </Link>
            </div>
          </div>
          <div className="flex items-center space-x-4">
            <span className="text-sm">{user?.email}</span>
            <button
              onClick={handleLogout}
              className="px-4 py-2 bg-red-600 hover:bg-red-700 rounded-md text-sm font-medium"
            >
              Logout
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}

export default Navbar;
