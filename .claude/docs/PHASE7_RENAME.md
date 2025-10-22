# Phase 7: Project Rename & PyPI Migration

**Created**: 2025-10-22
**Status**: Planning
**Current Name**: `vault-pydantic-simple`
**Current PyPI**: https://pypi.org/project/vault-pydantic-simple

---

## 🎯 Objectives

1. Choose a shorter, more memorable name
2. Update all references in codebase
3. Publish new package to PyPI
4. Update GitHub repository
5. (Optional) Deprecate old package gracefully

---

## 💡 Name Suggestions

### Option 1: `pydantic-vlt` ⭐ RECOMMENDED
- **Pros**: Short (13 chars), clear purpose (pydantic + vault), memorable
- **Cons**: "vlt" less obvious than "vault"
- **PyPI**: Available? Need to check
- **Import**: `from pydantic_vlt import VaultJsonConfig`

### Option 2: `vltconfig`
- **Pros**: Very short (9 chars), clean
- **Cons**: Less clear what it does
- **Import**: `from vltconfig import VaultJsonConfig`

### Option 3: `pyvault-config`
- **Pros**: Clear purpose, Python-focused
- **Cons**: Slightly longer (14 chars)
- **Import**: `from pyvault_config import VaultJsonConfig`

### Option 4: `vault-pyd`
- **Pros**: Short, combines "vault" and "pydantic"
- **Cons**: "pyd" might be confused with .pyd files
- **Import**: `from vault_pyd import VaultJsonConfig`

### Option 5: `hvac-pydantic`
- **Pros**: Clear dependency on hvac, mentions pydantic
- **Cons**: Longer, focuses on implementation detail
- **Import**: `from hvac_pydantic import VaultJsonConfig`

### Recommendation Matrix

| Name | Length | Clarity | Memorability | PyPI Clash Risk |
|------|--------|---------|--------------|----------------|
| `pydantic-vlt` | ★★★★★ | ★★★★☆ | ★★★★★ | Low |
| `vltconfig` | ★★★★★ | ★★★☆☆ | ★★★★☆ | Low |
| `pyvault-config` | ★★★★☆ | ★★★★★ | ★★★☆☆ | Medium |
| `vault-pyd` | ★★★★★ | ★★★☆☆ | ★★★★☆ | Low |
| `hvac-pydantic` | ★★★☆☆ | ★★★★★ | ★★★☆☆ | Medium |

**Final Recommendation**: `pydantic-vlt`

---

## 📋 Detailed Migration Plan

### Phase 7.1: Pre-Migration Checklist ⏱️ 30min

**Before starting, verify**:

- [ ] All Phase 1-6 tasks completed
- [ ] All tests passing (43/43)
- [ ] Coverage > 80% (currently 96.62%)
- [ ] No uncommitted changes
- [ ] Create backup branch

**Commands**:
```bash
# Create backup
git checkout -b backup/vault-pydantic-simple-v0.5.0
git push origin backup/vault-pydantic-simple-v0.5.0

# Return to dev
git checkout dev_v1
```

---

### Phase 7.2: Choose New Name ⏱️ 15min

**Decision Process**:

1. Check PyPI availability:
   ```bash
   # Try to pip install to check if exists
   pip search pydantic-vlt  # deprecated but can try
   # Or visit https://pypi.org/project/pydantic-vlt/
   ```

2. Check GitHub availability:
   ```bash
   # Visit https://github.com/tofuurem/pydantic-vlt
   ```

3. Document decision in this file

**Selected Name**: `_____________` (fill after checking)

---

### Phase 7.3: Update Package Name ⏱️ 1h

**Files to Update**:

#### 1. `pyproject.toml` (CRITICAL)

```toml
[project]
name = "pydantic-vlt"  # Changed from "vault-pydantic-simple"
version = "0.6.0"  # Bump version for new package
description = "Pydantic settings from HashiCorp Vault KV and JSON with caching"
readme = "README.md"

# ... rest stays same
```

#### 2. `README.md` - Update all mentions

- [ ] Title: `# pydantic-vlt`
- [ ] Installation: `pip install pydantic-vlt`
- [ ] PyPI link: Update badge URL
- [ ] All examples showing package name
- [ ] GitHub URLs (after repo rename)

#### 3. `CLAUDE.md` - Update project info

- [ ] Project name
- [ ] PyPI URL
- [ ] GitHub URL
- [ ] Installation instructions

#### 4. `.github/workflows/main.yml` - Update metadata

- [ ] Check if workflow name needs update
- [ ] Verify PyPI project name in publish step

#### 5. `setup.py` (if exists) - Update

- [ ] name parameter
- [ ] All metadata

#### 6. Documentation files in `.claude/docs/`

- [ ] `TASKS.md` - Update header
- [ ] `IMPROVEMENTS.md` - Update header
- [ ] `PHASE7_RENAME.md` - Mark completed

---

### Phase 7.4: Update Import Package Name ⏱️ 2h

**IMPORTANT**: This is a BREAKING CHANGE!

**Option A: Keep `vlt` as import name** (RECOMMENDED - No breaking change)
```python
# Old: from vlt import VaultJsonConfig
# New: from vlt import VaultJsonConfig  # Still works!
```

**Reasoning**:
- Package name on PyPI: `pydantic-vlt`
- Import name stays: `vlt`
- Users can upgrade without changing code
- Only installation command changes

**Option B: Rename to `pydantic_vlt`** (Breaking change)
```python
# Old: from vlt import VaultJsonConfig
# New: from pydantic_vlt import VaultJsonConfig  # BREAKS existing code
```

**Decision**: Use Option A (keep `vlt` import name)

**If choosing Option B, need to**:
- [ ] Rename `vlt/` directory to `pydantic_vlt/`
- [ ] Update all imports in tests
- [ ] Update pyproject.toml packages list
- [ ] Update README examples
- [ ] Add migration guide
- [ ] Version bump to 1.0.0 (major breaking change)

---

### Phase 7.5: Update GitHub Repository ⏱️ 30min

**Steps**:

1. **Rename Repository**:
   - Go to GitHub Settings → General
   - Repository name: `pydantic-vlt`
   - GitHub will automatically redirect old URLs

2. **Update Repository Description**:
   ```
   Pydantic settings from HashiCorp Vault KV and JSON with caching and retry
   ```

3. **Update Topics/Tags**:
   ```
   pydantic, vault, hashicorp-vault, configuration, settings,
   python, hvac, secrets-management, pydantic-settings
   ```

4. **Update Local Git Remote**:
   ```bash
   git remote set-url origin https://github.com/tofuurem/pydantic-vlt.git
   git remote -v  # Verify
   ```

---

### Phase 7.6: Create New PyPI Package ⏱️ 1h

**Pre-Publishing Checklist**:

- [ ] Version bumped to `0.6.0` in `pyproject.toml`
- [ ] All files updated with new name
- [ ] README.md updated
- [ ] All tests passing
- [ ] CHANGELOG.md created/updated

**Steps**:

1. **Clean Build**:
   ```bash
   # Remove old builds
   rm -rf dist/ build/ *.egg-info

   # Build new package
   uv build
   # or
   python -m build
   ```

2. **Verify Build**:
   ```bash
   # Check dist/ contents
   ls -lh dist/
   # Should see:
   # pydantic_vlt-0.6.0-py3-none-any.whl
   # pydantic_vlt-0.6.0.tar.gz
   ```

3. **Test Installation Locally**:
   ```bash
   # Create test venv
   python -m venv test_env
   source test_env/bin/activate

   # Install from local build
   pip install dist/pydantic_vlt-0.6.0-py3-none-any.whl

   # Test import
   python -c "from vlt import VaultJsonConfig; print('OK')"

   # Cleanup
   deactivate
   rm -rf test_env
   ```

4. **Publish to TestPyPI First** (RECOMMENDED):
   ```bash
   # Install twine if needed
   pip install twine

   # Upload to TestPyPI
   python -m twine upload --repository testpypi dist/*

   # Test installation from TestPyPI
   pip install --index-url https://test.pypi.org/simple/ pydantic-vlt
   ```

5. **Publish to PyPI** (PRODUCTION):

   **Option A: Manual Upload**:
   ```bash
   python -m twine upload dist/*
   # Enter PyPI credentials or API token
   ```

   **Option B: GitHub Actions** (RECOMMENDED):
   - Push tag to trigger release workflow
   ```bash
   git tag v0.6.0
   git push origin v0.6.0
   ```
   - GitHub Actions will build and publish automatically
   - Uses trusted publishing (no credentials needed)

6. **Verify on PyPI**:
   - Visit: https://pypi.org/project/pydantic-vlt/
   - Check metadata, description, links
   - Test installation:
   ```bash
   pip install pydantic-vlt
   ```

---

### Phase 7.7: Deprecate Old Package (Optional) ⏱️ 1h

**Purpose**: Help existing users migrate

**Steps**:

1. **Create Final Release of Old Package** (`vault-pydantic-simple` 0.5.1):

   Update `pyproject.toml`:
   ```toml
   [project]
   name = "vault-pydantic-simple"
   version = "0.5.1"
   description = "[DEPRECATED] Use 'pydantic-vlt' instead. This package will not receive updates."
   ```

2. **Add Deprecation Warning**:

   In `vlt/__init__.py`:
   ```python
   import warnings

   warnings.warn(
       "vault-pydantic-simple is deprecated. "
       "Please use 'pydantic-vlt' instead: pip install pydantic-vlt",
       DeprecationWarning,
       stacklevel=2
   )

   from vlt.json_source import PydanticJSONSource
   from vlt.vault_source import PydanticVaultSource

   class VaultJsonConfig(BaseSettings):
       # ... existing code
   ```

3. **Update Old Package README**:
   ```markdown
   # ⚠️ DEPRECATED

   This package has been renamed to **pydantic-vlt**.

   Please install the new package:
   ```bash
   pip uninstall vault-pydantic-simple
   pip install pydantic-vlt
   ```

   No code changes needed - the API is identical.
   ```

4. **Publish Final Version**:
   ```bash
   python -m build
   python -m twine upload dist/*
   ```

5. **Update PyPI Project Page**:
   - Add deprecation notice to description
   - Link to new package

---

### Phase 7.8: Update Documentation ⏱️ 30min

**Files to Update**:

- [ ] `README.md` - Installation, examples, badges
- [ ] `CLAUDE.md` - Project metadata
- [ ] `.claude/docs/TASKS.md` - Project name in header
- [ ] `.claude/docs/IMPROVEMENTS.md` - Project name
- [ ] Add `MIGRATION.md` (if breaking changes)

**Badge Updates** (README.md):

```markdown
[![PyPI version](https://badge.fury.io/py/pydantic-vlt.svg)](https://pypi.org/project/pydantic-vlt/)
[![Tests](https://github.com/tofuurem/pydantic-vlt/workflows/Tests/badge.svg)](https://github.com/tofuurem/pydantic-vlt/actions)
[![Coverage](https://codecov.io/gh/tofuurem/pydantic-vlt/branch/main/graph/badge.svg)](https://codecov.io/gh/tofuurem/pydantic-vlt)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
```

---

### Phase 7.9: Final Verification ⏱️ 30min

**Checklist**:

- [ ] New package published to PyPI
- [ ] Can install: `pip install pydantic-vlt`
- [ ] Import works: `from vlt import VaultJsonConfig`
- [ ] GitHub repo renamed
- [ ] README badges point to new URLs
- [ ] All tests pass on new package
- [ ] Documentation updated
- [ ] Git tags created
- [ ] Old package deprecated (optional)

**Test Installation**:
```bash
# Fresh environment
python -m venv test_new_package
source test_new_package/bin/activate

# Install new package
pip install pydantic-vlt

# Test basic usage
python << EOF
from vlt import VaultJsonConfig

class Config(VaultJsonConfig):
    test: str = "works"

print("✓ Package works!")
EOF

deactivate
rm -rf test_new_package
```

---

### Phase 7.10: Announce & Update Links ⏱️ 1h

**Communication**:

1. **GitHub Release**:
   - Create release v0.6.0
   - Title: "v0.6.0 - Package Renamed to pydantic-vlt"
   - Changelog:
     ```markdown
     ## Package Renamed

     This package has been renamed from `vault-pydantic-simple` to `pydantic-vlt`.

     ### Migration

     ```bash
     # Uninstall old package
     pip uninstall vault-pydantic-simple

     # Install new package
     pip install pydantic-vlt
     ```

     No code changes needed - the import name `vlt` remains the same.

     ### What's New in 0.6.0
     - ✨ Caching with configurable TTL (5 min default)
     - ✨ Retry logic with exponential backoff
     - ✨ Improved logging (trace level for details)
     - 📦 Renamed package to `pydantic-vlt`
     - ✅ 96%+ test coverage (43 tests)
     ```

2. **Update External Links** (if any):
   - Personal website
   - Portfolio
   - Blog posts
   - Social media

3. **Archive Old Package** (optional):
   - Mark old PyPI package as deprecated
   - Add "MOVED" notice to old GitHub repo description

---

## 📊 Summary

| Phase | Task | Time | Priority |
|-------|------|------|----------|
| 7.1 | Pre-Migration Checklist | 30min | 🔴 Critical |
| 7.2 | Choose New Name | 15min | 🔴 Critical |
| 7.3 | Update Package Name | 1h | 🔴 Critical |
| 7.4 | Update Import Name | 2h | 🟠 High |
| 7.5 | Update GitHub Repo | 30min | 🟠 High |
| 7.6 | Publish to PyPI | 1h | 🔴 Critical |
| 7.7 | Deprecate Old Package | 1h | 🟢 Optional |
| 7.8 | Update Documentation | 30min | 🟠 High |
| 7.9 | Final Verification | 30min | 🔴 Critical |
| 7.10 | Announce & Update Links | 1h | 🟡 Medium |

**Total Time**: ~8-9 hours

---

## ⚠️ Risks & Mitigation

### Risk 1: Package Name Already Taken on PyPI
**Mitigation**: Check availability first (Phase 7.2), have backup names ready

### Risk 2: Breaking Changes for Existing Users
**Mitigation**: Keep import name as `vlt`, only change package name

### Risk 3: Lost Search Rankings
**Mitigation**: Add deprecation notice with redirect, keep old package alive

### Risk 4: GitHub Issues/PRs Reference Old Name
**Mitigation**: GitHub auto-redirects, update links in documentation

### Risk 5: CI/CD Breaks
**Mitigation**: Update workflows before publishing, test on branch first

---

## 🎯 Success Criteria

**Phase 7 Complete When**:

- ✅ New package `pydantic-vlt` published on PyPI
- ✅ GitHub repository renamed
- ✅ All documentation updated
- ✅ Tests pass with new package name
- ✅ Can install: `pip install pydantic-vlt`
- ✅ Import works: `from vlt import VaultJsonConfig`
- ✅ Old package deprecated (optional)
- ✅ Version 0.6.0 released

---

## 📝 Notes

- **Version Strategy**: Bump to 0.6.0 for new package
  - 0.5.0 was last version of `vault-pydantic-simple`
  - 0.6.0 is first version of `pydantic-vlt`
  - Include rename in changelog

- **Import Name**: Keep as `vlt` to avoid breaking changes
  - Package: `pydantic-vlt` (PyPI name)
  - Import: `vlt` (Python import)
  - This is common practice (e.g., `Pillow` package, `PIL` import)

- **Deprecation Timeline**:
  - Immediate: Publish new package
  - Week 1: Announce deprecation
  - Month 1: Add warnings to old package
  - Month 6: Stop updates to old package
  - Year 1: Consider removing old package

---

**Ready to start?** Begin with Phase 7.1!
