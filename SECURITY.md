# SECURITY.md - ATLAS Security Model & Threat Analysis

## 1. Overview

ATLAS is an enterprise-grade multi-tenant RAG platform designed with security as a foundational requirement. This document outlines the security model, threat analysis, and best practices for deploying ATLAS.

**Security Classification**: Production-Grade
**Multi-Tenancy**: Full isolation at database, cache, and storage layers
**Target Deployment**: Enterprise (on-premise, cloud, hybrid)

---

## 2. Threat Model

### 2.1 Assets Protected
- **User Credentials**: Email, password hashes, session tokens
- **Tenant Data**: Documents, collections, embeddings, metadata
- **Inference Results**: RAG pipeline outputs, citations, confidence scores
- **System Configuration**: API keys, database URLs, infrastructure credentials

### 2.2 Threat Categories & Mitigations

| Threat | Impact | Likelihood | Mitigation |
|--------|--------|------------|-----------|
| **Unauthorized Access** | Unauthorized document access | Medium | JWT auth, role-based access, rate limiting |
| **Cross-Tenant Data Leakage** | Data exposure to other tenants | Low | Tenant isolation at DB/cache/storage |
| **SQL Injection** | Database compromise | Low | ORM parameterization, input validation |
| **Credential Exposure** | Account takeover | Low | Environment variables, secret management |
| **Document Tampering** | Metadata/content corruption | Medium | Access controls, audit logging |
| **Malicious File Upload** | Code execution, DOS | Medium | File type validation, sandboxed parsing |
| **Cache Poisoning** | Incorrect responses served | Low | Cache key validation, TTL enforcement |
| **Worker Process Hijack** | Unauthorized processing | Low | Service-to-service auth (future), ACLs |
| **DOS Attack** | Service unavailability | Medium | Rate limiting, resource limits, backpressure |
| **Man-in-the-Middle** | Credential/data interception | Low | TLS enforcement (production) |

---

## 3. Authentication & Authorization

### 3.1 Authentication Model

```
User Registration → Password Hash (PBKDF2-SHA256) → Store in DB
                                              ↓
User Login      → Verify Password            → Generate JWT Token (24hr)
                                              ↓
API Request     → Validate JWT               → Extract user_id, tenant_id
                                              ↓
Route Handler   → Check Authorization        → Grant/Deny Access
```

**JWT Token Structure:**
```json
{
  "user_id": "uuid",
  "tenant_id": "uuid",
  "exp": 1705276800,
  "iat": 1705190400,
  "alg": "HS256"
}
```

### 3.2 Password Hashing

- **Algorithm**: PBKDF2-HMAC-SHA256
- **Iterations**: 100,000 (default, configurable)
- **Salt**: 32-byte random, hex-encoded
- **Format**: `{salt}${hash_key_hex}`
- **Rationale**: OWASP-approved, resistant to rainbow table attacks, GPU-resistant

### 3.3 Authorization Model

```
┌─────────────────────────────────┐
│   Token Contains:               │
│   - user_id                     │
│   - tenant_id                   │
│   - (roles/permissions: future) │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│   Database Query Filter:        │
│   WHERE tenant_id = token.tid   │
│   AND user_id = token.uid       │
│   AND document NOT DELETED      │
└─────────────────────────────────┘
           ↓
┌─────────────────────────────────┐
│   Response                      │
│   (Only accessible data)        │
└─────────────────────────────────┘
```

### 3.4 RBAC (Role-Based Access Control)

Current implementation (v1.0):
- **ADMIN**: Can manage tenant, add/remove users
- **MEMBER**: Can view documents, create collections, search

Future enhancements:
- **VIEWER**: Read-only access
- **EDITOR**: Create/edit documents
- **ANALYST**: Run complex queries, create evaluations
- Custom roles per tenant

**Code Enforcement:**
```python
# In all database queries
WHERE tenant_id = current_user.tenant_id
```

---

## 4. Data Protection

### 4.1 Encryption at Rest

**Current Status**: ✅ Configured
- **Database**: PostgreSQL native encryption (TDE) recommended for production
- **Redis Cache**: In-memory (no persistence needed for cache)
- **MinIO Object Storage**: Server-side encryption (SSE-S3) configurable
- **Kubernetes Secrets**: Stored encrypted in etcd (with `--encryption-provider`)

**Production Recommendations**:
1. Enable PostgreSQL TLS and SSL
2. Configure MinIO server-side encryption
3. Use managed database encryption (AWS RDS, Azure SQL)
4. Enable Kubernetes secret encryption at rest

### 4.2 Encryption in Transit

**Current Status**: 🔄 Partial (development only)
- Local development: HTTP (not encrypted)
- Production deployment: TLS/HTTPS required
- Service-to-service: HTTPS or mTLS recommended

**Production Requirements**:
1. FastAPI server: TLS certificates (Let's Encrypt or CA)
2. Frontend: HTTPS only
3. Database connections: SSL/TLS
4. Cache connections: TLS if remote
5. External API calls: HTTPS only
6. Service mesh: Enable mTLS between services

### 4.3 Multi-Tenant Data Isolation

**Database Level:**
```sql
-- Every table has tenant_id
ALTER TABLE documents ADD CONSTRAINT fk_tenant_id 
  FOREIGN KEY (tenant_id) REFERENCES tenants(id);

-- All queries filter by tenant
SELECT * FROM documents 
WHERE tenant_id = ? AND user_id = ? AND status != 'DELETED';

-- Indexes prevent cross-tenant access
CREATE INDEX idx_doc_tenant ON documents(tenant_id, user_id);
```

**Cache Level:**
```python
cache_key = f"rag:cache:{tenant_id}:{query_hash}"
# Prevents accidental cross-tenant cache hits
```

**Storage Level:**
```python
object_path = f"documents/{tenant_id}/{document_id}/{filename}"
# MinIO object paths include tenant_id for access control
```

**Verification**: Tested in `tests/test_documents.py::test_multi_tenant_isolation`

---

## 5. Dependency Security

### 5.1 Dependency Management

**Current Approach**:
- `requirements.txt` pins all versions
- `package.json` pins frontend dependencies
- No transitive dependency bloat

**Maintenance Practice**:
1. Regular updates: `pip install --upgrade` + test
2. Security scanning: `bandit` for Python, `npm audit` for Node
3. CVE tracking: Monitor CVE databases for dependencies
4. Vendor updates: Subscribe to security advisories

### 5.2 Critical Dependencies

| Package | Version | Purpose | Security |
|---------|---------|---------|----------|
| FastAPI | 0.100+ | Web framework | Actively maintained, security-focused |
| SQLAlchemy | 2.0.23 | ORM | Parameterized queries prevent SQL injection |
| asyncpg | latest | PostgreSQL driver | TLS support, safe async connection handling |
| pydantic | 2.0+ | Validation | Input validation prevents injection attacks |
| cryptography | latest | Encryption | Audited cryptographic primitives |
| pytest | latest | Testing | Test security-critical code paths |

---

## 6. Input Validation & Sanitization

### 6.1 Request Validation

All API inputs validated with **Pydantic**:

```python
class DocumentUploadRequest(BaseModel):
    filename: str = Field(..., max_length=255)
    file_type: str = Field(..., pattern="^[a-zA-Z0-9]+$")  # Whitelist
    collection_id: Optional[UUID] = None
    
    @field_validator('filename')
    def validate_filename(cls, v):
        # Prevent path traversal
        if '..' in v or v.startswith('/'):
            raise ValueError("Invalid filename")
        return v
```

**Protections**:
- ✅ Type validation (UUID, string, integer, etc.)
- ✅ Length limits (max_length)
- ✅ Pattern matching (regex whitelists)
- ✅ Enum validation (predefined values)
- ✅ Custom validators (business logic)

### 6.2 Output Sanitization

Sensitive fields excluded from responses:
```python
class UserResponse(BaseModel):
    id: UUID
    email: str
    # ❌ Never include: hashed_password
    # ❌ Never include: jwt_secret
```

---

## 7. Audit Logging

### 7.1 Logged Events

```python
# Authentication events
- User registration
- User login (success + failure)
- Token generation
- Token validation failures

# Data access events
- Document upload
- Document deletion (soft delete)
- Search queries (optional: log full query)
- RAG pipeline execution

# Administrative events
- Tenant creation
- User role changes
- Configuration changes
```

**Implementation**:
```python
logger.info(f"User {user_id} deleted document {doc_id}", 
            extra={
                "user_id": str(user_id),
                "tenant_id": str(tenant_id),
                "document_id": str(doc_id),
                "timestamp": datetime.utcnow().isoformat()
            })
```

### 7.2 Log Retention & Security

**Current**: Logs written to stdout/stderr (captured by container orchestration)
**Production**:
1. Forward logs to centralized SIEM (Splunk, ELK, Datadog)
2. Ensure logs don't contain sensitive data (passwords, API keys)
3. Implement log access controls
4. Set retention policies (audit logs: 1 year, others: 30-90 days)

---

## 8. Secret Management

### 8.1 Secret Types & Storage

| Secret | Type | Storage | Rotation |
|--------|------|---------|----------|
| `JWT_SECRET` | Key | Environment variable | 90 days recommended |
| `DATABASE_URL` | Connection | Environment variable | On access policy change |
| `REDIS_URL` | Connection | Environment variable | On access policy change |
| `LLM_API_KEY` | API token | Environment variable | Per provider guidelines |
| `STORAGE_ACCESS_KEY` | Credential | Environment variable | 90 days recommended |
| Certificates | TLS | Kubernetes Secret | Before expiration |

### 8.2 Development vs. Production

**Development** (`.env.example`):
```
# ✅ Safe to commit
DATABASE_URL=postgresql+asyncpg://atlas:atlas@localhost:5432/atlas
STORAGE_ACCESS_KEY=minioadmin
JWT_SECRET=your-super-secret-key-change-in-production
```

**Production** (Environment variables):
```bash
# ✅ DO NOT commit
export DATABASE_URL="postgresql+asyncpg://user:$(aws secretsmanager ...)@..."
export JWT_SECRET=$(aws secretsmanager get-secret-value --secret-id atlas/jwt-key | jq -r .SecretString)
export LLM_API_KEY=$(azure keyvault secret show --vault-name atlas-vault --name llm-api-key --query value -o tsv)
```

### 8.3 Secret Management Best Practices

**Recommended Solutions**:
1. **Azure KeyVault** (Azure deployments)
2. **AWS Secrets Manager** (AWS deployments)
3. **HashiCorp Vault** (Self-hosted)
4. **Kubernetes Secrets with encryption** (K8s deployments)

**Access Control**:
- RBAC: Only necessary services can access each secret
- Rotation: Automatic or manual per secret policy
- Audit: Log all secret access
- Revocation: Immediate revocation capability

---

## 9. API Security

### 9.1 Rate Limiting

**Implemented**:
```python
class RateLimitMiddleware:
    """Token bucket rate limiting per user."""
    def __init__(self, rpm: int = 1000):  # Default: 1000 req/min
        self.rpm = rpm
```

**Configuration**: `RATE_LIMIT_RPM` environment variable

**Per-User Limits**:
- Default: 1000 requests/minute
- Burst: Up to limit in first second
- Penalty: 429 Too Many Requests response

### 9.2 CORS Configuration

```python
# Hardcoded allowed origins (not wildcard)
CORS_ORIGINS = ["http://localhost:3000", "https://app.example.com"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
```

**Production**: Update `CORS_ORIGINS` to match deployed frontend domain

### 9.3 HTTP Security Headers

**Recommended** (add to middleware):
```python
# Content-Security-Policy
response.headers["Content-Security-Policy"] = "default-src 'self'"

# X-Frame-Options
response.headers["X-Frame-Options"] = "DENY"

# X-Content-Type-Options
response.headers["X-Content-Type-Options"] = "nosniff"

# Strict-Transport-Security (HTTPS only)
response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
```

---

## 10. Reporting Security Issues

### 10.1 Vulnerability Disclosure Policy

**For Researchers/Security Community**:

DO NOT open public GitHub issues for security vulnerabilities. Instead:

1. Email: `security@atlas-project.io` (if applicable, or use GitHub Security Advisory)
2. Include:
   - Vulnerability description
   - Affected component and version
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if applicable)

3. **Timeline**:
   - Acknowledgment: Within 24 hours
   - Assessment: Within 7 days
   - Fix availability: Within 30 days for critical issues
   - Public disclosure: Coordinated with researcher

### 10.2 Security Updates

- Subscribe to GitHub repository watch notifications for releases
- Check RELEASE_NOTES.md for security patches
- Apply security updates as soon as available
- Report any new vulnerabilities found

---

## 11. Deployment Security Checklist

### 11.1 Pre-Deployment

- [ ] All secrets configured in secret manager (not .env files)
- [ ] TLS certificates installed (self-signed OK for testing, valid CA for production)
- [ ] Database backups tested
- [ ] Access control lists configured (firewall rules, security groups)
- [ ] Network segmentation verified
- [ ] RBAC roles defined for administrators
- [ ] Monitoring and alerting enabled

### 11.2 Kubernetes Deployment

- [ ] Pod security policies configured
- [ ] RBAC service accounts created with minimal permissions
- [ ] Network policies restrict traffic
- [ ] Resource limits configured (prevent DOS)
- [ ] Liveness and readiness probes enabled
- [ ] Secrets encrypted at rest in etcd
- [ ] Container image scanning enabled (Trivy, Clair)
- [ ] Security context enforces non-root user

### 11.3 Cloud Deployment (AWS/Azure/GCP)

- [ ] Managed database encryption enabled
- [ ] S3/Blob/GCS bucket encryption configured
- [ ] VPC/VNet with private subnets
- [ ] Load balancer with TLS termination
- [ ] WAF (Web Application Firewall) enabled
- [ ] DDoS protection enabled
- [ ] CloudTrail/Activity Logs for audit
- [ ] Managed Identity / Service Accounts for authentication

---

## 12. Incident Response

### 12.1 Incident Types

| Type | Response Time | Action |
|------|---|--------|
| **Critical Security Breach** | Immediate | Disable affected accounts, rotate secrets, publish advisory |
| **Data Exfiltration** | 4 hours | Assess scope, notify affected users, file report if required |
| **Denial of Service** | 1 hour | Increase rate limits, scale infrastructure, enable DDOS protection |
| **Unauthorized Access** | 1 hour | Reset sessions, audit access logs, reset passwords |
| **Data Corruption** | 2 hours | Restore from backup, audit change logs, verify data integrity |

### 12.2 Communication

1. **Internal**: Notify security team immediately
2. **Users**: Transparency about incident (what, when, impact)
3. **Regulatory**: Report per compliance requirements (GDPR, HIPAA, etc.)
4. **Public**: Post-incident summary (if applicable)

---

## 13. Compliance & Certifications

### 13.1 Applicable Standards

| Standard | Requirement | Status | Plan |
|----------|------------|--------|------|
| **OWASP Top 10** | Prevent common vulnerabilities | ✅ Designed for compliance | Ongoing |
| **GDPR** | Data protection (EU users) | 🔄 Encryption/audit needed | Q2 2025 |
| **HIPAA** | Health data protection (US) | 🟡 If used with PHI | Q3 2025 |
| **SOC 2** | Security & availability controls | 🟡 Audit required | Q4 2025 |
| **ISO 27001** | Information security management | 🟡 Certification path | 2025+ |

### 13.2 PII & Sensitive Data Handling

**Currently Stored**:
- User email addresses (user identity)
- Document metadata (collection names, created_at)
- User activity (search queries, document access)

**Not Stored**:
- User full names or phone numbers
- Document full text in unencrypted form (embeddings only)
- Payment information
- Health records (design supports it, not implemented)

**Future Considerations**:
- Implement field-level encryption for PII
- Right-to-deletion (GDPR compliance)
- Data retention policies
- Audit trail for compliance

---

## 14. Security Testing & Verification

### 14.1 Implemented Tests

```
✅ tests/test_auth.py::test_verify_password_invalid
✅ tests/test_auth.py::test_decode_jwt_token_invalid
✅ tests/test_documents.py::test_multi_tenant_isolation
✅ tests/test_cache.py::test_cache_tenant_isolation
✅ tests/test_retrieval.py::test_retriever_tenant_isolation
```

### 14.2 Recommended Security Testing (Future)

- [ ] **OWASP ZAP Scan**: Automated vulnerability scanning
- [ ] **Burp Suite**: Manual penetration testing
- [ ] **SQL Injection Tests**: Fuzz all database query inputs
- [ ] **Cross-Tenant Penetration**: Attempt to access other tenant data
- [ ] **File Upload Security**: Test file type validation, path traversal
- [ ] **JWT Token Replay**: Attempt token reuse with different requests
- [ ] **Rate Limit Bypass**: Test rate limiting with distributed requests
- [ ] **Dependency Audits**: Run `safety check` + `npm audit`

---

## 15. Security Resources & Further Reading

### 15.1 External Standards

- [OWASP Top 10 2021](https://owasp.org/www-project-top-ten/)
- [CWE Top 25](https://cwe.mitre.org/top25/)
- [NIST Cybersecurity Framework](https://www.nist.gov/cyberframework)
- [OWASP API Security Top 10](https://owasp.org/www-project-api-security/)

### 15.2 Libraries & Tools

- **Bandit**: Python security issue scanner
- **Safety**: Dependency vulnerability checker
- **Trivy**: Container image vulnerability scanner
- **OWASP ZAP**: Automated web application security scanning

### 15.3 Dependencies

- **cryptography**: Cryptographic recipes and primitives
- **passlib**: Password hashing library (alternative to manual PBKDF2)
- **python-jose**: JWT token library
- **pydantic**: Input validation

---

## 16. Security Roadmap

### Q1 2025
- [ ] Complete security documentation
- [ ] Implement automated security scanning in CI/CD
- [ ] Add security headers middleware
- [ ] Audit all dependencies for vulnerabilities

### Q2 2025
- [ ] Implement field-level encryption for PII
- [ ] Add GDPR compliance features
- [ ] Penetration testing by third party
- [ ] Security audit by external firm

### Q3 2025+
- [ ] HIPAA compliance pathway
- [ ] SOC 2 audit preparation
- [ ] Advanced threat detection (anomaly detection, behavioral analytics)
- [ ] Zero-trust network architecture

---

## 17. Contact & Support

**Security Team**: [To be added]
**Email**: security@atlas-project.io (if applicable)
**PGP Key**: [To be added]
**Response SLA**: 24 hours for initial response

**No Warranty Disclaimer**: This document describes security best practices and threat mitigations. ATLAS is provided "as-is" without warranty. Users are responsible for appropriate deployment, configuration, and monitoring in their environment.

---

**Last Updated**: 2025-01-14
**Document Version**: 1.0
**Status**: Production Release Candidate

