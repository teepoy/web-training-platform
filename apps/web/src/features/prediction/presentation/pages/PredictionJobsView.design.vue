<template>
  <section class="prediction-launcher-design">
    <div class="prediction-actions">
      <div>
        <small>CURRENT RESULTS</small>
        <strong>Prediction runs</strong>
      </div>
      <div><button class="primary">Start Prediction</button></div>
    </div>
    <header>
      <div>
        <small>PREDICTION</small>
        <h2>Choose a model</h2>
        <p>Search the complete model history, then select exactly one model for this run.</p>
      </div>
      <button aria-label="Close">×</button>
    </header>

    <div class="filters">
      <input value="surface" readonly aria-label="Search models" />
      <select aria-label="Training source">
        <option>All training sources</option>
      </select>
      <select aria-label="Creator">
        <option>All creators</option>
      </select>
    </div>

    <p class="compatibility-note">
      Showing only models compatible with the selected dataset's registered views.
    </p>

    <div class="model-table">
      <div class="table-head">
        <span></span><span>Model</span><span>Source</span><span>Trainer</span><span>Creator</span
        ><span>Created</span>
      </div>
      <label class="selected"
        ><input type="radio" checked /><strong>Patch classifier v14</strong
        ><span>Dataset · Line A</span><span>yolo-v8</span><span>Jin</span
        ><time>2026-08-14</time></label
      >
      <label
        ><input type="radio" /><strong>Patch classifier v3</strong
        ><span>Collection · Golden set</span><span>yolo-v8</span><span>Jin</span
        ><time>2025-11-03</time></label
      >
    </div>

    <footer>
      <span>126 models · page 1 of 7</span>
      <div><button>Cancel</button><button class="primary">Start with selected model</button></div>
    </footer>
  </section>
</template>

<style scoped>
.prediction-launcher-design {
  display: grid;
  gap: 18px;
  width: min(920px, 94vw);
  padding: 24px;
  color: #20242c;
  background: #fff;
  border: 1px solid #dfe3e9;
  border-radius: 14px;
}
.prediction-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding-bottom: 16px;
  border-bottom: 1px solid #edf0f3;
}
.prediction-actions > div:last-child {
  display: flex;
  gap: 8px;
}
.prediction-actions strong {
  display: block;
  margin-top: 4px;
  font-size: 18px;
}
header,
.filters,
.table-head,
label,
footer,
footer div {
  display: flex;
  align-items: center;
}
header,
footer {
  justify-content: space-between;
  gap: 16px;
}
h2 {
  margin: 3px 0;
  font-size: 24px;
}
p {
  margin: 0;
  color: #687180;
}
.compatibility-note {
  padding: 9px 12px;
  color: #4057bd;
  background: #f2f5ff;
  border-radius: 8px;
}
small {
  color: #5267c9;
  font-weight: 700;
  letter-spacing: 0.12em;
}
button,
input,
select {
  padding: 9px 12px;
  background: #fff;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}
.filters {
  gap: 10px;
}
.filters input {
  flex: 1;
}
.model-table {
  border: 1px solid #dfe3e9;
  border-radius: 10px;
  overflow: hidden;
}
.table-head,
label {
  display: grid;
  grid-template-columns: 34px 1.4fr 1.5fr 1fr 1fr 1fr;
  gap: 10px;
  padding: 12px;
}
.table-head {
  color: #697282;
  background: #f5f6f8;
  font-size: 12px;
  font-weight: 700;
}
label {
  border-top: 1px solid #edf0f3;
}
label.selected {
  background: #f2f5ff;
  box-shadow: inset 3px 0 #5267c9;
}
label span,
time {
  color: #697282;
  font-size: 13px;
}
.primary {
  color: #fff;
  background: #5267c9;
}
footer {
  color: #697282;
  font-size: 13px;
}
footer div {
  gap: 8px;
}
</style>
