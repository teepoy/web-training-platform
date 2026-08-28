<template>
  <main class="models-design">
    <header>
      <div>
        <small>ML RESOURCES</small>
        <h1>Models</h1>
        <p>Search model history and manage models you own.</p>
      </div>
    </header>

    <section class="toolbar" aria-label="Model filters">
      <input value="surface" readonly aria-label="Search models" />
      <select aria-label="Training source">
        <option>All training sources</option>
      </select>
      <select aria-label="Creator scope">
        <option>My models</option>
      </select>
      <button>Clear filters (2)</button>
    </section>

    <section class="table">
      <strong>Model</strong><strong>Training source</strong><strong>Trainer</strong
      ><strong>Creator</strong><strong>Created</strong><strong>Actions</strong>
    </section>
  </main>
</template>

<style scoped>
.models-design {
  display: grid;
  gap: 18px;
  min-height: 100%;
  padding: 28px;
  color: #20242c;
  background: #f6f7f9;
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
.toolbar,
.table {
  display: grid;
  gap: 10px;
  align-items: center;
}
.toolbar {
  grid-template-columns: minmax(260px, 1fr) 210px 210px auto;
}
.table {
  grid-template-columns: 1.2fr 1.4fr 1fr 1fr 1fr auto;
  min-height: 220px;
  padding: 18px;
  background: repeating-linear-gradient(#fff, #fff 42px, #f0f2f5 43px);
  border: 1px solid #e1e4e9;
  border-radius: 12px;
}
input,
select,
button {
  padding: 9px 12px;
  background: white;
  border: 1px solid #d9dde5;
  border-radius: 8px;
}
</style>
