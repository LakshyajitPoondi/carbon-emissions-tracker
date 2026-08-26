/** Mirrors docs/api-contract.md — Standard Error Shape section. */

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
  };
}
