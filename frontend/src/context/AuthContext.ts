import React, { createContext } from 'react';

export interface User {
  id: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthContextType {
  token: string | null;
  user: User | null;
  loading: boolean;
}

export const AuthContext = createContext<AuthContextType>({
  token: null,
  user: null,
  loading: true,
});
