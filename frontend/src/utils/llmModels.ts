/**
 * DeepSeek model policy — frontend mirror of `backend/app/llm_model_policy.py`.
 *
 * DEEPSEEK MODEL POLICY (frozen): every DeepSeek call uses exactly one model,
 * `deepseek-flash`. There is no per-feature model choice, so the UI offers a
 * single option. The backend provider normalizes regardless, so a stale value
 * in a saved form or a stored run cannot change what is actually called.
 *
 * Other providers are unaffected and keep their own model lists.
 */

export const DEEPSEEK_MODEL = 'deepseek-flash'

/** The only DeepSeek option any selector may offer. */
export const DEEPSEEK_MODEL_OPTIONS: { value: string; label: string }[] = [
  { value: DEEPSEEK_MODEL, label: 'deepseek-flash（推荐）' },
]
