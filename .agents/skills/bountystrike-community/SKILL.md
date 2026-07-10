```markdown
# bountystrike-community Development Patterns

> Auto-generated skill from repository analysis

## Overview
This skill covers the core development patterns, coding conventions, and operational workflows for the `bountystrike-community` Python codebase. It provides guidance on file organization, import/export styles, environment variable management, CI/CD hardening, and testing practices. Use this as a reference for contributing code, maintaining workflows, and ensuring consistency across the project.

## Coding Conventions

### File Naming
- Use **camelCase** for filenames.
  - Example: `orchestratorScript.py`, `dataLoader.py`

### Import Style
- Use **relative imports** within the package.
  - Example:
    ```python
    from .utils import fetchData
    from .models import UserModel
    ```

### Export Style
- Use **named exports** (explicitly define what is exported from a module).
  - Example:
    ```python
    # utils.py
    def fetchData():
        pass

    __all__ = ['fetchData']
    ```

## Workflows

### Environment Variable Reconciliation and Passthrough Fix
**Trigger:** When environment variables are added or changed in the codebase or scripts, and documentation or passthrough logic needs to be updated to match.  
**Command:** `/sync-env-vars`

1. **Identify** new or changed environment variables in code or scripts.
2. **Update** `.env.example` to document all required variables. Split into logical sections if needed.
    ```env
    # Database Settings
    DB_HOST=localhost
    DB_USER=user

    # API Keys
    API_KEY=your-api-key
    ```
3. **Update** scripts (e.g., `orchestrator.py`) to ensure all required environment variables are correctly passed through to subprocesses or services.
    ```python
    import os
    import subprocess

    env = os.environ.copy()
    env['API_KEY'] = os.getenv('API_KEY')
    subprocess.run(['python', 'service.py'], env=env)
    ```
4. **Test** that all services and scripts receive the correct environment variables.

**Files Involved:**  
- `.env.example`  
- `scripts/orchestrator.py`

---

### CI Infrastructure Fix and Credential Least-Privilege Hardening
**Trigger:** When CI workflows fail due to dependency/configuration drift, or when security reviews identify overbroad credential exposure.  
**Command:** `/fix-ci-and-harden-creds`

1. **Diagnose** CI workflow failures by reviewing logs and error messages.
2. **Update** CI workflow YAML files (e.g., `.github/workflows/integration-pg.yml`, `.github/workflows/license-and-imports.yml`) to fix dependency installation, service images, or configuration issues.
    ```yaml
    # .github/workflows/integration-pg.yml
    jobs:
      test:
        runs-on: ubuntu-latest
        services:
          postgres:
            image: postgres:13
            env:
              POSTGRES_USER: user
              POSTGRES_PASSWORD: pass
    ```
3. **Update** scripts (e.g., `orchestrator.py`) to scope credentials to only the necessary targets.
    ```python
    # Only pass required credentials to subprocesses
    env = {k: os.environ[k] for k in ['DB_USER', 'DB_PASSWORD']}
    subprocess.run(['python', 'target.py'], env=env)
    ```
4. **Test** CI workflows to confirm fixes and improved security.

**Files Involved:**  
- `.github/workflows/integration-pg.yml`  
- `.github/workflows/license-and-imports.yml`  
- `scripts/orchestrator.py`

## Testing Patterns

- **Test framework:** Unknown (no explicit framework detected).
- **Test file pattern:** Files matching `*.test.*` (e.g., `userService.test.py`).
- **Typical test structure:**  
  - Place test files alongside or near the code they test.
  - Use descriptive function and file names.

## Commands

| Command                | Purpose                                                                 |
|------------------------|-------------------------------------------------------------------------|
| /sync-env-vars         | Sync environment variable documentation and passthrough logic            |
| /fix-ci-and-harden-creds | Fix CI workflow issues and harden credential scoping in scripts         |
```