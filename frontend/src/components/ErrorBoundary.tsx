import { Component, type ErrorInfo, type ReactNode } from 'react';

interface ErrorBoundaryProps {
  children: ReactNode;
  onError?: (error: Error, info: ErrorInfo) => void;
  onReset?: () => void;
}

interface ErrorBoundaryState {
  hasError: boolean;
}

export class ErrorBoundary extends Component<ErrorBoundaryProps, ErrorBoundaryState> {
  state: ErrorBoundaryState = {
    hasError: false,
  };

  static getDerivedStateFromError(): ErrorBoundaryState {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Unhandled render error', error, info.componentStack);
    this.props.onError?.(error, info);
  }

  private handleReload = () => {
    this.props.onReset?.();
    window.location.reload();
  };

  render() {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <div
        className="flex min-h-screen items-center justify-center px-6"
        style={{
          background: 'var(--ai-page-gradient)',
          color: 'var(--ai-text-primary)',
        }}
      >
        <div
          className="w-full max-w-md rounded-3xl p-8 text-center shadow-xl"
          style={{
            background: 'var(--ai-surface)',
            border: '1px solid var(--ai-border-strong)',
          }}
        >
          <p
            className="text-sm font-medium uppercase tracking-wide"
            style={{ color: 'var(--ai-text-secondary)' }}
          >
            UI Recovery
          </p>
          <h1 className="mt-3 text-2xl font-semibold">Something went wrong</h1>
          <p className="mt-3 text-sm" style={{ color: 'var(--ai-text-secondary)' }}>
            Reload the page to restore the workspace.
          </p>
          <button
            onClick={this.handleReload}
            className="mt-6 inline-flex items-center justify-center rounded-full px-5 py-2 text-sm font-medium"
            style={{
              background: 'var(--ai-primary-action-gradient)',
              color: 'var(--ai-text-inverted)',
            }}
          >
            Reload
          </button>
        </div>
      </div>
    );
  }
}
