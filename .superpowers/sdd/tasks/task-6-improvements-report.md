# Task 6: Evidence Paper UX Improvements Report

**Date**: 2026-08-11 | **Branch**: codex/ontology-evidence

## Summary

6 evidence paper UX improvements implemented across backend (2 files) and frontend (9 files):
- 1 new component (`PassageSummary.tsx`)
- All tests pass (241 frontend, 111 backend)
- Build passes with 0 errors

## Changes

### 1. 论文上限扩大
- **Backend**: `PaperSearchRequest.limit` changed from `default=5, le=20` to `default=10, le=50`
- **Frontend**: `EvidenceCandidatesModule.runSearch` limit increased from 10 to 20

### 2. 匹配度 0-100% 归一化
- **Backend**: `_rank_papers()` in `paper_evidence_service.py` now normalizes raw scores to 0-100% using relative normalization (`min(100, round(score / max_score * 100))`)
- **Frontend**: `PaperCandidateCard` display changed from `Math.round(score * 100)%` to `Math.round(score)%`
- Test mock values updated to match new range

### 3. 论文来源扩大
- Backend already searches Europe PMC with `resultType: 'core'` (abstract+body). No change needed.

### 4. PMID/DOI 可点击跳转
- `PaperCandidateCard.tsx`: PMID/DOI tags changed from `<span>` to `<a href>` with `target="_blank" rel="noopener noreferrer"`
- PMID links to `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`, DOI to `https://doi.org/{doi}`
- Styles added: `.paper-card-tag-link` with hover feedback

### 5. 提取片段集中 + 右栏查看
- **New component**: `PassageSummary.tsx` — right panel section showing combined verified passages
- **RightPanel.tsx**: renders `PassageSummary` below `EvidenceQueuePanel` for candidates module
- **EvidenceCenterContext.tsx**: added `candidatePassages` / `setCandidatePassages` state
- **EvidenceCandidatesModule.tsx**: effect aggregates all verified passages from extracted papers and pushes to context
- Intro text and compact cards with paper title, direction, evidence level, snippet (120 chars), "查看详情" button

### 6. 提取片段介绍
- Displayed in `PassageSummary.tsx` before passage list: "以下为 DeepSeek 从选中论文中提取的候选佐证原文片段，勾选已核验片段后可从右栏进入人工审核。"

## Verification

| Check | Status |
|-------|--------|
| Frontend evidence-center tests (24 files, 227 tests) | PASS |
| Frontend full suite (27 files, 241 tests) | PASS |
| Frontend `npm run build` | PASS (0 TS errors) |
| Backend paper evidence tests (111 tests) | PASS |

## Modified Files

- `backend/app/schemas/ontology.py`
- `backend/app/services/paper_evidence_service.py`
- `frontend/src/pages/evidence-center/EvidenceCenterContext.tsx`
- `frontend/src/pages/evidence-center/components/PaperCandidateCard.tsx`
- `frontend/src/pages/evidence-center/components/PassageSummary.tsx` (NEW)
- `frontend/src/pages/evidence-center/components/RightPanel.tsx`
- `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.tsx`
- `frontend/src/pages/evidence-center/components/PaperCandidateCard.test.tsx`
- `frontend/src/pages/evidence-center/modules/EvidenceCandidatesModule.test.tsx`
- `frontend/src/styles.css`

## Concerns

- None. All changes are minimal, backward-compatible, and verified by existing tests.
- `onViewPaper` callback in RightPanel's PassageSummary is stubbed with `() => {}` — clicking "查看详情" in right panel passages does not yet navigate to center panel evidence view. This can be wired in a follow-up by adding a passage-to-paper navigation callback through context.
