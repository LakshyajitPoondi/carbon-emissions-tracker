import { ApiError } from "../api";

interface ErrorBannerProps {
  error: unknown;
  onRetry?: () => void;
}

/** Renders any thrown value as a clear, actionable banner. Branches on
 * ApiError.code (not message text) per the contract's error-handling rule,
 * and gives NO_MATCHING_FACTOR its own distinct label. */
export function ErrorBanner({ error, onRetry }: ErrorBannerProps) {
  const message = error instanceof Error ? error.message : "Something went wrong.";
  const code = error instanceof ApiError ? error.code : undefined;
  const label = code === "NO_MATCHING_FACTOR" ? "No emission factor available" : (code ?? "Error");

  return (
    <div className="error-banner" role="alert">
      <div className="error-banner__body">
        <strong className="error-banner__label">{label}</strong>
        <span>{message}</span>
      </div>
      {onRetry && (
        <button type="button" className="error-banner__retry" onClick={onRetry}>
          Retry
        </button>
      )}
    </div>
  );
}
