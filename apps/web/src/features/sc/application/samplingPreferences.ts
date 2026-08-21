import {
  cloneScSamplingProgram,
  createDefaultScAnnotationSamplingProgram,
  createDefaultScReviewSamplingProgram,
  scSamplingProgramError,
  type ScSamplingProgram,
} from "@/features/sc/domain/samplingRules";

export type ScSamplingPreferenceKind = "annotation" | "review";

const STORAGE_KEYS: Record<ScSamplingPreferenceKind, string> = {
  annotation: "sc.annotation-sampling.pipeline.v1",
  review: "sc.review-sampling.pipeline.v1",
};

function defaultProgram(kind: ScSamplingPreferenceKind): ScSamplingProgram {
  return kind === "annotation"
    ? createDefaultScAnnotationSamplingProgram()
    : createDefaultScReviewSamplingProgram();
}

export function loadScSamplingPreference(kind: ScSamplingPreferenceKind): ScSamplingProgram {
  const fallback = defaultProgram(kind);
  if (typeof localStorage === "undefined") return fallback;
  const stored = localStorage.getItem(STORAGE_KEYS[kind]);
  if (!stored) return fallback;
  try {
    const candidate = JSON.parse(stored) as ScSamplingProgram;
    if (scSamplingProgramError(candidate)) return fallback;
    return cloneScSamplingProgram(candidate);
  } catch {
    return fallback;
  }
}

export function saveScSamplingPreference(
  kind: ScSamplingPreferenceKind,
  program: ScSamplingProgram,
): void {
  if (typeof localStorage === "undefined") return;
  if (scSamplingProgramError(program)) return;
  localStorage.setItem(STORAGE_KEYS[kind], JSON.stringify(cloneScSamplingProgram(program)));
}
