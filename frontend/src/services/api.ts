import axios, { AxiosInstance } from 'axios';

interface ApiClientConfig {
  baseURL?: string;
}

class APIClient {
  private axiosInstance: AxiosInstance;
  private token: string | null = null;

  constructor(config?: ApiClientConfig) {
    const baseURL = config?.baseURL || process.env.REACT_APP_API_URL || '/api/v1';
    
    this.axiosInstance = axios.create({
      baseURL,
      timeout: 30000,
    });

    this.token = localStorage.getItem('token');
    this.setupInterceptors();
  }

  private setupInterceptors() {
    this.axiosInstance.interceptors.request.use((config) => {
      if (this.token) {
        config.headers.Authorization = `Bearer ${this.token}`;
      }
      return config;
    });

    this.axiosInstance.interceptors.response.use(
      (response) => response,
      (error) => {
        if (error.response?.status === 401) {
          this.setToken(null);
          window.location.href = '/';
        }
        return Promise.reject(error);
      }
    );
  }

  setToken(token: string | null) {
    this.token = token;
    if (token) {
      localStorage.setItem('token', token);
      this.axiosInstance.defaults.headers.common['Authorization'] = `Bearer ${token}`;
    } else {
      localStorage.removeItem('token');
      delete this.axiosInstance.defaults.headers.common['Authorization'];
    }
  }

  // Authentication
  register(email: string, password: string, fullName: string, tenantName: string) {
    return this.axiosInstance.post('/auth/register', {
      email,
      password,
      full_name: fullName,
      tenant_name: tenantName,
    });
  }

  login(email: string, password: string) {
    return this.axiosInstance.post('/auth/login', { email, password });
  }

  getMe() {
    return this.axiosInstance.get('/auth/me');
  }

  // Collections
  createCollection(name: string, description?: string) {
    return this.axiosInstance.post('/collections', { name, description });
  }

  getCollections(skip = 0, limit = 50) {
    return this.axiosInstance.get('/collections', { params: { skip, limit } });
  }

  getCollection(collectionId: string) {
    return this.axiosInstance.get(`/collections/${collectionId}`);
  }

  updateCollection(collectionId: string, name?: string, description?: string) {
    return this.axiosInstance.put(`/collections/${collectionId}`, { name, description });
  }

  deleteCollection(collectionId: string) {
    return this.axiosInstance.delete(`/collections/${collectionId}`);
  }

  // Documents
  uploadDocument(file: File, collectionId?: string, metadata?: Record<string, any>) {
    const formData = new FormData();
    formData.append('file', file);
    if (collectionId) formData.append('collection_id', collectionId);
    if (metadata) formData.append('metadata', JSON.stringify(metadata));

    return this.axiosInstance.post('/documents/upload', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  }

  getDocuments(collectionId?: string, status?: string, skip = 0, limit = 50) {
    const params: any = { skip, limit };
    if (collectionId) params.collection_id = collectionId;
    if (status) params.status = status;

    return this.axiosInstance.get('/documents', { params });
  }

  getDocument(documentId: string) {
    return this.axiosInstance.get(`/documents/${documentId}`);
  }

  deleteDocument(documentId: string) {
    return this.axiosInstance.delete(`/documents/${documentId}`);
  }

  // Search
  search(query: string, collectionIds?: string[], topK = 10) {
    return this.axiosInstance.post('/search', {
      query,
      collection_ids: collectionIds,
      top_k: topK,
    });
  }

  // RAG Query
  query(query: string, collectionIds?: string[], topK = 10, minConfidence = 0.3) {
    return this.axiosInstance.post('/query', {
      query,
      collection_ids: collectionIds,
      top_k: topK,
      min_confidence: minConfidence,
    });
  }

  // Health
  health() {
    return this.axiosInstance.get('/health');
  }

  ready() {
    return this.axiosInstance.get('/ready');
  }
}

export default new APIClient();
