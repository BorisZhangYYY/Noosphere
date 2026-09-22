export interface ArticleDraft {
  articleId: string;
  text: string;
  saved: string;
  revision: string;
}
export type DraftAction =
  | { type: "receive"; articleId: string; text: string; revision: string; hasImageChanges: boolean }
  | { type: "edit"; text: string }
  | { type: "saved"; articleId: string; submitted: string; text: string; revision: string };

export const emptyArticleDraft: ArticleDraft = { articleId: "", text: "", saved: "", revision: "" };

export function articleDraftReducer(state: ArticleDraft, action: DraftAction): ArticleDraft {
  if (action.type === "edit") return { ...state, text: action.text };
  if (action.type === "saved") {
    if (state.articleId !== action.articleId) return state;
    return { ...state, text: state.text === action.submitted ? action.text : state.text, saved: action.text, revision: action.revision };
  }
  if (state.articleId === action.articleId && (state.text !== state.saved || action.hasImageChanges)) return state;
  return { articleId: action.articleId, text: action.text, saved: action.text, revision: action.revision };
}
