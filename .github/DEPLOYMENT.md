# GitHub Actions Deployment Setup

## Overview

This repository uses GitHub Actions for continuous integration and automated PyPI publishing with trusted publishing (OIDC).

## Workflows

### 1. CI Workflow (`ci.yml`)
- **Trigger**: Push to main/develop branches, pull requests
- **Purpose**: Run tests, linting, and build verification
- **Matrix**: Multiple Python versions (3.8-3.11) and OS (Ubuntu, macOS, Windows)

### 2. Publish to PyPI (`publish.yml`) 
- **Trigger**: GitHub releases (published)
- **Purpose**: Publish to production PyPI
- **Environment**: `pypi` 
- **URL**: https://pypi.org/p/polaris-marl

### 3. Publish to Test PyPI (`test-publish.yml`)
- **Trigger**: Tags matching `v*-test`, `v*-alpha`, `v*-beta`, `v*-rc*`  
- **Purpose**: Publish to Test PyPI for testing
- **Environment**: `testpypi`
- **URL**: https://test.pypi.org/p/polaris-marl

## Required GitHub Settings

### 1. Environments Setup

Create these environments in GitHub repository settings:

#### PyPI Environment (`pypi`)
- **Name**: `pypi` 
- **URL**: `https://pypi.org/p/polaris-marl`
- **Protection Rules**: Require reviewers (optional)

#### Test PyPI Environment (`testpypi`)  
- **Name**: `testpypi`
- **URL**: `https://test.pypi.org/p/polaris-marl`
- **Protection Rules**: None needed

### 2. PyPI Trusted Publishing Setup

#### For Production PyPI:
1. Go to https://pypi.org/manage/account/publishing/
2. Add a new publisher:
   - **PyPI Project Name**: `polaris-marl`
   - **Owner**: `ecdogaroglu` (your GitHub username)
   - **Repository name**: `polaris`  
   - **Workflow filename**: `publish.yml`
   - **Environment name**: `pypi`

#### For Test PyPI:
1. Go to https://test.pypi.org/manage/account/publishing/  
2. Add a new publisher:
   - **PyPI Project Name**: `polaris-marl`
   - **Owner**: `ecdogaroglu` (your GitHub username)
   - **Repository name**: `polaris`
   - **Workflow filename**: `test-publish.yml` 
   - **Environment name**: `testpypi`

### 3. Repository Permissions

Ensure these permissions in repository settings:

- **Actions**: Read and write permissions
- **Contents**: Read permission  
- **Metadata**: Read permission
- **Pull requests**: Write permission (for CI)

## Release Process

### Test Release
1. Create a test tag: `git tag v2.0.3-test`
2. Push tag: `git push origin v2.0.3-test`  
3. Check Test PyPI: https://test.pypi.org/p/polaris-marl

### Production Release
1. Create a GitHub release with tag `v2.0.3`
2. Publish the release
3. GitHub Actions will automatically publish to PyPI
4. Check PyPI: https://pypi.org/p/polaris-marl

## Troubleshooting

### Common Issues

1. **"Environment not found"**
   - Ensure environments are created in GitHub repository settings
   - Check environment names match exactly (`pypi`, `testpypi`)

2. **"Trusted publishing not configured"**  
   - Set up trusted publishing on PyPI/Test PyPI
   - Verify all details match exactly (repository name, workflow file, environment)

3. **"Permission denied"**
   - Check repository permissions for GitHub Actions
   - Ensure `id-token: write` permission is set in workflow

4. **"Package already exists"**
   - Version already published - increment version number
   - Check version in `polaris/__init__.py`

### Verification Commands

```bash
# Check workflow syntax
python -c "import yaml; print('Valid' if yaml.safe_load(open('.github/workflows/publish.yml')) else 'Invalid')"

# Test package build locally
python -m build
python -m twine check dist/*

# Verify package installation
pip install dist/*.whl
python -c "import polaris; print(f'polaris v{polaris.__version__}')"
```

## Security Notes

- Uses OpenID Connect (OIDC) for secure publishing without API tokens
- No secrets stored in repository  
- Environment protection rules can be added for additional security
- All workflows use pinned action versions for security