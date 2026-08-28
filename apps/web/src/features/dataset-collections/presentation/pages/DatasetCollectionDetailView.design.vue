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

    <nav class="tabs" aria-label="Collection sections">
      <button class="active">Overview</button><button>Classify ↗</button
      ><button>Data &amp; rules</button><button>Models</button><button>Snapshots</button
      ><button>Activity</button>
    </nav>

    <section class="member-export">
      <div>
        <strong>Linked datasets</strong>
        <span>2 records selected</span>
      </div>
      <div class="actions">
        <button>Predict selected (1)</button>
        <button>Export selected (2)</button>
      </div>
      <small>
        Parquet combines selected records. KLARF creates one complete .000/.001 file per inspection.
      </small>
    </section>

    <section class="snapshot-explainer">
      <strong>What is a snapshot?</strong>
      <span>
        It saves the linked datasets and rules plus the Dataset change numbers observed now. It does
        not copy member data; runs read current Dataset data when they start.
      </span>
    </section>

    <section class="summary">
      View contract · Current setup v4 · 3 linked datasets · Snapshot r3
    </section>
    <section class="models-panel">
      <div>
        <strong>Default prediction model</strong>
        <span>Searches compatible models only; results are loaded while this picker is open.</span>
      </div>
      <button>Choose model</button>
    </section>
    <section class="panel muted">
      The remaining content is split across Data, Models, Snapshots, and Activity.
    </section>
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
.member-export,
.models-panel,
.warning,
.summary,
.panel {
  padding: 18px;
  background: white;
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}

.tabs {
  display: flex;
  gap: 4px;
  border-bottom: 1px solid #dfe3e9;
}

.tabs button {
  border: 0;
  border-radius: 8px 8px 0 0;
}

.tabs button.active {
  color: #4057bd;
  box-shadow: inset 0 -2px #5267c9;
}

.muted {
  color: #6a7280;
  font-weight: 400;
}

.snapshot-explainer {
  display: grid;
  gap: 4px;
  border-color: #cad3fa;
  background: #f2f5ff;
}

.member-export {
  display: grid;
  gap: 12px;
}

.member-export > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.member-export span {
  color: #6a7280;
}

.models-panel {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.models-panel > div {
  display: grid;
  gap: 4px;
}

.models-panel span {
  color: #6a7280;
}

.warning {
  color: #8a4b08;
  border-color: #f0c98b;
  background: #fff8e8;
}

.panel {
  min-height: 150px;
  font-weight: 600;
}
</style>
