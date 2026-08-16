<template>
  <main class="infrastructure-design">
    <header>
      <small>ADMIN</small>
      <h1>Infrastructure</h1>
      <p>Protected operator consoles for execution and storage diagnostics.</p>
    </header>

    <aside class="warning">
      <strong>Restricted operator access</strong>
      <span>Console authentication is enforced by a TLS reverse proxy or private VPN.</span>
    </aside>

    <section class="console-grid">
      <article>
        <div class="card-header">
          <h2>Prefect UI</h2>
          <span class="ready">Configured</span>
        </div>
        <p>Inspect runs, logs, deployments, and work-pool health.</p>
        <ul>
          <li>Approved retry, cancellation, and maintenance only</li>
          <li>No unmanaged deployment edits</li>
        </ul>
        <button>Open protected console ↗</button>
      </article>

      <article>
        <div class="card-header">
          <h2>MinIO Console</h2>
          <span>Not configured</span>
        </div>
        <p>Inspect artifact, manifest, and object-version metadata.</p>
        <ul>
          <li>Approved diagnostics and recovery only</li>
          <li>No object, policy, credential, or lifecycle deletion</li>
        </ul>
        <p class="muted">Launch action hidden until a protected URL is configured.</p>
      </article>
    </section>
  </main>
</template>

<style scoped>
.infrastructure-design {
  display: grid;
  gap: 20px;
  min-height: 100%;
  padding: 28px;
  color: #20242c;
  background: #f6f7f9;
}

h1,
h2,
p {
  margin: 0;
}

small {
  color: #5267c9;
  font-weight: 700;
  letter-spacing: 0.12em;
}

.warning,
article {
  padding: 18px;
  background: white;
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}

.warning {
  display: grid;
  gap: 5px;
  border-color: #e4b466;
  background: #fff9ed;
}

.console-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

article {
  display: grid;
  gap: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-header span {
  padding: 4px 8px;
  color: #646c79;
  background: #eef0f4;
  border-radius: 999px;
}

.card-header .ready {
  color: #176c41;
  background: #e5f6ed;
}

ul {
  margin: 0;
  padding-left: 20px;
}

button {
  width: fit-content;
  padding: 9px 12px;
  color: white;
  background: #5267c9;
  border: 0;
  border-radius: 8px;
}

.muted {
  color: #7a8290;
}

@media (max-width: 760px) {
  .console-grid {
    grid-template-columns: 1fr;
  }
}
</style>
