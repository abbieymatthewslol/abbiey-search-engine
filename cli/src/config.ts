import type {
  AnswerStyle,
  Depth,
  Evidence,
  SearchMode,
} from "./urls.js";

export type UserConfig = {
  origin: string;
  depth?: Depth;
  evidence?: Evidence;
  answerStyle?: AnswerStyle;
  mode?: SearchMode;
};

const defaults: UserConfig = {
  origin: "https://abbieysearch.com",
};

export function defaultConfig(): UserConfig {
  return { ...defaults };
}

export function mergeEnv(config: UserConfig): UserConfig {
  const origin =
    process.env.ABBIEYSEARCH_ORIGIN?.trim() ||
    process.env.ABBIEY_ORIGIN?.trim() ||
    config.origin;

  const depth = (process.env.ABBIEYSEARCH_DEPTH as Depth | undefined) ?? config.depth;
  const evidence =
    (process.env.ABBIEYSEARCH_EVIDENCE as Evidence | undefined) ?? config.evidence;
  const answerStyle =
    (process.env.ABBIEYSEARCH_ANSWER_STYLE as AnswerStyle | undefined) ??
    config.answerStyle;
  const mode = (process.env.ABBIEYSEARCH_MODE as SearchMode | undefined) ?? config.mode;

  return {
    origin,
    ...(depth ? { depth } : {}),
    ...(evidence ? { evidence } : {}),
    ...(answerStyle ? { answerStyle } : {}),
    ...(mode ? { mode } : {}),
  };
}
