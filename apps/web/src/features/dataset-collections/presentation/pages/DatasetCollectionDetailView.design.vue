<template>
  <main class="collection-detail-design">
    <header>
      <div>
        <small>DATASET COLLECTION</small>
        <h1>Collection name</h1>
        <p>Collection purpose and scope</p>
      </div>
      <div class="actions">
        <button>Save current setup as snapshot</button>
        <button class="primary">Review snapshot r3</button>
      </div>
    </header>

    <section class="snapshot-explainer">
      <strong>What is a snapshot?</strong>
      <span>
        A revision is a fixed snapshot of the linked datasets and rules. Runs use a snapshot so
        their input stays reproducible when the collection changes later.
      </span>
    </section>

    <section class="summary">
      View contract · Current setup v4 · 3 linked datasets · Snapshot r3
    </section>
    <section class="panel">Linked datasets</section>
    <section class="panel">Saved snapshots (revisions)</section>
  </main>
</template>

<style scoped>
.collection-detail-design {
  display: grid;
  gap: 18px;
  min-height: 100%;
  padding: 28px;
  color: #20242c;
  background: #f6f7f9;
}

header,
.actions {
  display: flex;
  gap: 12px;
}

header {
  align-items: end;
  justify-content: space-between;
}

h1 {
  margin: 4px 0;
}

p {
  margin: 0;
  color: #6a7280;
}

small {
  color: #5267c9;
  font-weight: 700;
  letter-spacing: 0.12em;
}

button {
  padding: 9px 14px;
  background: white;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}

button.primary {
  color: white;
  background: #5267c9;
}

.snapshot-explainer,
.summary,
.panel {
  padding: 18px;
  background: white;
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}

.snapshot-explainer {
  display: grid;
  gap: 4px;
  border-color: #cad3fa;
  background: #f2f5ff;
}

.panel {
  min-height: 150px;
  font-weight: 600;
}
</style>
