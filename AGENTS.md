# Container Inventory for AI Agents

This document provides a structured inventory of all containerized services in this repository, designed to help AI agents quickly locate and remediate container vulnerabilities.

## Quick Reference

| Service | ECR Image Pattern | Directory | Dockerfile | Dependencies |
|---------|-------------------|-----------|------------|--------------|
| analyzer | `*shara-analyzer*` | agent/agents/analyzer | agent/agents/analyzer/Dockerfile | agent/agents/analyzer/requirements.txt |
| remediator | `*shara-remediator*` | agent/agents/remediator | agent/agents/remediator/Dockerfile | agent/agents/remediator/requirements.txt |
| validator | `*shara-validator*` | agent/agents/validator | agent/agents/validator/Dockerfile | agent/agents/validator/requirements.txt |
| user-service | `*user-service*` | application/services/user-service | application/services/user-service/Dockerfile | application/services/user-service/pom.xml |
| profile-service | `*profile-service*` | application/services/profile-service | application/services/profile-service/Dockerfile | application/services/profile-service/pom.xml |
| notification-service | `*notification-service*` | application/services/notification-service | application/services/notification-service/Dockerfile | application/services/notification-service/pom.xml |

## Service Categories

### Python Agent Services (agent/agents/*)

These are AI agent services built with FastAPI and AWS Bedrock AgentCore.

| Property | Value |
|----------|-------|
| Base Image | `python:3.12-slim` |
| Dependency File | `requirements.txt` |
| Dependency Manager | pip |
| Port | 8080-8082 |

**Services:**
- **analyzer** - Analyzes security findings from AWS Security Hub
- **remediator** - Executes remediation actions for vulnerabilities
- **validator** - Validates remediation results and sends approval requests

### Java Microservices (application/services/*)

These are Spring Boot microservices deployed on Amazon EKS.

| Property | Value |
|----------|-------|
| Base Image | `public.ecr.aws/docker/library/amazoncorretto:21-alpine` |
| Dependency File | `pom.xml` |
| Dependency Manager | Maven |
| Port | 8080 |

**Services:**
- **user-service** - User management and authentication
- **profile-service** - User profile management
- **notification-service** - Email notifications via AWS SES

### Frontend (application/services/frontend)

| Property | Value |
|----------|-------|
| Type | Static Web App (No Dockerfile) |
| Dependency File | `package.json` |
| Dependency Manager | npm |
| Deployment | CloudFront CDN |

## Vulnerability Remediation Guide

### Base Image Vulnerabilities

To fix base image vulnerabilities, update the `FROM` statement in the Dockerfile:

**Python services:**
```dockerfile
# Before
FROM python:3.12-slim

# After (example: update to patched version)
FROM python:3.12.1-slim
```

**Java services:**
```dockerfile
# Before
FROM public.ecr.aws/docker/library/amazoncorretto:21-alpine

# After (example: update to patched version)
FROM public.ecr.aws/docker/library/amazoncorretto:21.0.2-alpine
```

### Dependency Vulnerabilities

#### Python (requirements.txt)

```txt
# Before
requests==2.28.0

# After (update to patched version)
requests==2.31.0
```

#### Java (pom.xml)

```xml
<!-- Before -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.0.0</version>
</dependency>

<!-- After (update to patched version) -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
    <version>3.2.0</version>
</dependency>
```

#### Node.js (package.json)

```json
// Before
"dependencies": {
    "react": "18.2.0"
}

// After (update to patched version)
"dependencies": {
    "react": "18.3.1"
}
```

## File Structure

```
awsome2/
├── AGENTS.md                              # This file
├── .github/
│   └── container-inventory.json           # Machine-readable container inventory
├── agent/
│   └── agents/
│       ├── analyzer/
│       │   ├── SERVICE.yaml               # Service metadata
│       │   ├── Dockerfile
│       │   └── requirements.txt
│       ├── remediator/
│       │   ├── SERVICE.yaml
│       │   ├── Dockerfile
│       │   └── requirements.txt
│       └── validator/
│           ├── SERVICE.yaml
│           ├── Dockerfile
│           └── requirements.txt
└── application/
    └── services/
        ├── user-service/
        │   ├── SERVICE.yaml
        │   ├── Dockerfile
        │   └── pom.xml
        ├── profile-service/
        │   ├── SERVICE.yaml
        │   ├── Dockerfile
        │   └── pom.xml
        ├── notification-service/
        │   ├── SERVICE.yaml
        │   ├── Dockerfile
        │   └── pom.xml
        └── frontend/
            └── package.json
```

## Machine-Readable Data

For programmatic access, use `.github/container-inventory.json` which contains:
- All container definitions with ECR patterns
- Dockerfile and dependency file paths
- Base image information
- Language and framework metadata

## Agent Workflow

1. **Receive vulnerability** from AWS Inspector/Security Hub
2. **Extract ECR image URI** from the finding
3. **Read `.github/container-inventory.json`** to find matching service
4. **Read `SERVICE.yaml`** in the service directory for detailed metadata
5. **Update the appropriate file** (Dockerfile, requirements.txt, pom.xml, package.json)
6. **Create a Pull Request** with the fix
