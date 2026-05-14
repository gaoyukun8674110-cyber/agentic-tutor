import { toast } from 'sonner';

import { getDefaultErrorMessage, getUserFacingError, isAbortError } from './apiClient';

export function toastError(error: unknown, fallbackMessage = getDefaultErrorMessage()) {
  if (isAbortError(error)) return;

  const message =
    error instanceof Error
      ? getUserFacingError(error)
      : typeof error === 'string'
        ? error
        : fallbackMessage;

  toast.error(message);
}
