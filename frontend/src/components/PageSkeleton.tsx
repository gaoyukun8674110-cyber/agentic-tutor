interface PageSkeletonProps {
  label?: string;
}

export function PageSkeleton({ label = 'Loading page' }: PageSkeletonProps) {
  return (
    <div
      aria-label={label}
      className="min-h-screen animate-pulse px-6 py-8"
      style={{
        background: 'var(--ai-page-gradient)',
      }}
    >
      <div className="mx-auto flex w-full max-w-7xl flex-col gap-6">
        <div
          className="h-14 rounded-3xl"
          style={{
            background: 'var(--ai-surface-muted)',
            border: '1px solid var(--ai-border-soft)',
          }}
        />
        <div className="grid gap-6 lg:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <div
              key={index}
              className="rounded-3xl p-6"
              style={{
                background: 'var(--ai-surface)',
                border: '1px solid var(--ai-border-strong)',
              }}
            >
              <div
                className="h-4 w-28 rounded-full"
                style={{ background: 'var(--ai-surface-accent)' }}
              />
              <div
                className="mt-4 h-10 w-32 rounded-2xl"
                style={{ background: 'var(--ai-surface-accent)' }}
              />
              <div
                className="mt-6 h-36 rounded-3xl"
                style={{ background: 'var(--ai-surface-muted)' }}
              />
            </div>
          ))}
        </div>
        <div
          className="h-64 rounded-3xl"
          style={{ background: 'var(--ai-surface)', border: '1px solid var(--ai-border-strong)' }}
        />
      </div>
    </div>
  );
}
