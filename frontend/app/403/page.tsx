export default function ForbiddenPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-4">
      <h1 className="text-4xl font-bold text-destructive">403</h1>
      <p className="text-muted-foreground text-lg">
        You do not have permission to access this page.
      </p>
      <a
        href="/rfps"
        className="text-primary underline hover:no-underline"
      >
        Return to RFPs
      </a>
    </main>
  );
}
